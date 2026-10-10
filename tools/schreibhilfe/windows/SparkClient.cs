using System.Net;
using System.Net.Http.Headers;
using System.Reflection;
using System.Security.Authentication;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace SparkSchreibhilfe;

/// <summary>Fehler vom Spark oder der Verbindung, mit deutschem Text für die Anzeige.</summary>
internal sealed class SparkException : Exception
{
    public SparkException(int? status, string message) : base(message) => Status = status;

    /// <summary>HTTP-Status, oder <c>null</c> bei Verbindungsfehlern.</summary>
    public int? Status { get; }
}

/// <summary>Ein Stück des Wort-Diffs: '=' gleich, '-' entfernt, '+' hinzugefügt.</summary>
internal readonly record struct DiffPart(char Op, string Text);

internal sealed record AssistResult(string Text, IReadOnlyList<DiffPart>? Diff, int? Changes, int? Ms);

internal sealed record PairResult(string Key, string? Profile);

/// <summary>
/// Die Schnittstelle des Spark (/api/write/…). Es wird nur mit der eingerichteten Adresse geredet,
/// Zertifikate werden immer normal geprüft, und es wird nichts protokolliert.
/// </summary>
internal static class SparkClient
{
    private const string DeviceHeader = "X-Speech-Device";

    private static readonly HttpClient Http = CreateClient();

    private static HttpClient CreateClient()
    {
        var handler = new SocketsHttpHandler
        {
            AutomaticDecompression = DecompressionMethods.All,
            PooledConnectionLifetime = TimeSpan.FromMinutes(5),
        };
        var client = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(180) };
        string version = Assembly.GetExecutingAssembly().GetName().Version?.ToString(3) ?? "1.0.0";
        client.DefaultRequestHeaders.UserAgent.Add(new ProductInfoHeaderValue("SparkSchreibhilfe", version));
        return client;
    }

    /// <summary>POST /api/write/pair – tauscht den Einmal-Code gegen einen Geräteschlüssel.</summary>
    public static async Task<PairResult> PairAsync(string baseUrl, string code, string deviceName, CancellationToken ct)
    {
        var body = new JsonObject { ["code"] = code, ["name"] = deviceName, ["kind"] = "windows" };
        using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/api/write/pair") { Content = JsonContent(body) };
        JsonNode json = await SendAsync(request, pairing: true, ct);

        string? key = Str(json["key"]);
        if (string.IsNullOrEmpty(key))
        {
            throw new SparkException(null, "Der Spark hat keinen Schlüssel geschickt.");
        }

        return new PairResult(key, Str(json["profile"]));
    }

    /// <summary>POST /api/write/assist – lässt den Text verbessern.</summary>
    public static async Task<AssistResult> AssistAsync(
        string baseUrl, string key, string text, string art, string? sprache, string? wunsch, CancellationToken ct)
    {
        var body = new JsonObject { ["text"] = text, ["art"] = art };
        if (!string.IsNullOrEmpty(sprache))
        {
            body["sprache"] = sprache;
        }

        if (!string.IsNullOrWhiteSpace(wunsch))
        {
            body["wunsch"] = wunsch.Trim();
        }

        using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/api/write/assist") { Content = JsonContent(body) };
        request.Headers.Add(DeviceHeader, key);
        JsonNode json = await SendAsync(request, pairing: false, ct);

        string? result = Str(json["text"]);
        if (result is null)
        {
            throw new SparkException(null, "Der Spark hat keinen Text zurückgeschickt.");
        }

        return new AssistResult(result, ParseDiff(json["diff"]), Int(json["changes"]), Int(json["ms"]));
    }

    private static StringContent JsonContent(JsonObject body) =>
        new(body.ToJsonString(), Encoding.UTF8, "application/json");

    private static async Task<JsonNode> SendAsync(HttpRequestMessage request, bool pairing, CancellationToken ct)
    {
        HttpResponseMessage response;
        try
        {
            response = await Http.SendAsync(request, ct);
        }
        catch (TaskCanceledException) when (!ct.IsCancellationRequested)
        {
            throw new SparkException(null, "Der Spark hat nicht rechtzeitig geantwortet (3 Minuten). Bitte später noch einmal versuchen.");
        }
        catch (HttpRequestException ex)
        {
            throw new SparkException(null, DescribeConnectionError(ex));
        }

        using (response)
        {
            string content = await response.Content.ReadAsStringAsync(ct);
            JsonNode? json = null;
            try
            {
                json = content.Length > 0 ? JsonNode.Parse(content) : null;
            }
            catch (JsonException)
            {
                // Keine JSON-Antwort (z. B. Fehlerseite eines Proxys) – unten allgemein melden.
            }

            int status = (int)response.StatusCode;
            if (response.IsSuccessStatusCode)
            {
                return json ?? throw new SparkException(status, "Unerwartete Antwort vom Spark.");
            }

            throw new SparkException(status, ErrorText(status, Detail(json), pairing));
        }
    }

    private static string ErrorText(int status, string? detail, bool pairing)
    {
        if (status == 401 && !pairing)
        {
            return "Diese Schreibhilfe ist am Spark nicht mehr gekoppelt. Bitte neu koppeln."
                   + (string.IsNullOrEmpty(detail) ? "" : "\n" + detail);
        }

        if (!string.IsNullOrEmpty(detail))
        {
            return detail;
        }

        return status switch
        {
            400 when pairing => "Der Code ist falsch oder abgelaufen. Bitte im Panel einen neuen Code holen.",
            403 => "Die Schreibhilfe ist für andere Programme ausgeschaltet.",
            404 => "Diese Adresse kennt die Schreibhilfe nicht – ist der Spark aktuell?",
            413 => "Der Text ist zu lang.",
            429 => "Der Spark ist gerade beschäftigt. Bitte gleich noch einmal versuchen.",
            503 => "Der Spark ist gerade nicht verfügbar.",
            _ => $"Der Spark meldet einen Fehler ({status}).",
        };
    }

    /// <summary>"detail" ist meist ein Text; bei Prüffehlern eine Liste von Objekten mit "msg".</summary>
    private static string? Detail(JsonNode? json)
    {
        JsonNode? detail = json is JsonObject obj ? obj["detail"] : null;
        if (Str(detail) is { } text)
        {
            return text;
        }

        if (detail is JsonArray list)
        {
            var parts = list.Select(item => item is JsonObject o ? Str(o["msg"]) : Str(item))
                            .Where(s => !string.IsNullOrEmpty(s));
            string joined = string.Join("; ", parts);
            return joined.Length > 0 ? joined : null;
        }

        return null;
    }

    private static string DescribeConnectionError(HttpRequestException ex)
    {
        for (Exception? inner = ex; inner is not null; inner = inner.InnerException)
        {
            if (inner is AuthenticationException)
            {
                return "Das Zertifikat des Spark ist ungültig – die Verbindung wurde abgelehnt.";
            }
        }

        return "Der Spark ist nicht erreichbar. Läuft er, und stimmt die Adresse?\n(" + ex.Message + ")";
    }

    private static List<DiffPart>? ParseDiff(JsonNode? node)
    {
        if (node is not JsonArray items)
        {
            return null;
        }

        var parts = new List<DiffPart>(items.Count);
        foreach (JsonNode? item in items)
        {
            if (item is JsonArray { Count: >= 2 } pair && Str(pair[0]) is { Length: 1 } op && Str(pair[1]) is { } text)
            {
                parts.Add(new DiffPart(op[0], text));
            }
        }

        return parts;
    }

    private static string? Str(JsonNode? node) =>
        node is JsonValue value && value.TryGetValue(out string? s) ? s : null;

    private static int? Int(JsonNode? node) =>
        node is JsonValue value && value.TryGetValue(out int i) ? i : null;
}
