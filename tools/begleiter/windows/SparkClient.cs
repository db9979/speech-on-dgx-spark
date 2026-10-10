using System.Net;
using System.Net.Http.Headers;
using System.Reflection;
using System.Security.Authentication;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace SparkBegleiter;

/// <summary>Fehler vom Spark oder der Verbindung, mit deutschem Text für die Anzeige.</summary>
internal sealed class SparkException : Exception
{
    public SparkException(int? status, string message, string? detail = null) : base(message)
    {
        Status = status;
        Detail = detail;
    }

    /// <summary>HTTP-Status, oder <c>null</c> bei Verbindungsfehlern.</summary>
    public int? Status { get; }

    /// <summary>Der Text aus {"detail": …} (reiner Text, nie Markup).</summary>
    public string? Detail { get; }

    /// <summary>Gerät am Spark unbekannt (im Panel entfernt).</summary>
    public bool IsUnknownDevice => Status == 401;

    /// <summary>Notaus oder Mein Notaus: der Spark nimmt gerade nichts an.</summary>
    public bool IsNotaus => Status == 503 && Detail is { } d &&
        (d.StartsWith("Notaus", StringComparison.Ordinal) || d.StartsWith("Mein Notaus", StringComparison.Ordinal));
}

/// <summary>Ein Stück des Wort-Diffs: '=' gleich, '-' entfernt, '+' hinzugefügt.</summary>
internal readonly record struct DiffPart(char Op, string Text);

internal sealed record AssistResult(string Text, IReadOnlyList<DiffPart>? Diff, int? Changes, int? Ms);

internal sealed record PairResult(string Key, string? Profile);

internal sealed record Note(int N, string Title, string Body, string? Tag);

internal sealed record PollResult(int Rev, IReadOnlyList<Note> Notes, int Last, int NotausLevel);

/// <summary>
/// Die Schnittstelle des Spark (/api/desk/… und /api/write/assist). Es wird nur mit der eingerichteten
/// Adresse geredet, Zertifikate werden immer normal geprüft, und es wird nichts protokolliert.
/// Der Geräteschlüssel steht nur im Kopf X-Speech-Device, nie in der Adresse.
/// </summary>
internal static class SparkClient
{
    private const string DeviceHeader = "X-Speech-Device";

    /// <summary>Höchstlänge für Texte vom Spark, die angezeigt werden (Fehlermeldungen).</summary>
    private const int MaxDetail = 400;

    private static readonly TimeSpan LongTimeout = TimeSpan.FromSeconds(180);
    private static readonly TimeSpan ShortTimeout = TimeSpan.FromSeconds(20);

    private static readonly HttpClient Http = CreateClient();

    private static HttpClient CreateClient()
    {
        var handler = new SocketsHttpHandler
        {
            AutomaticDecompression = DecompressionMethods.All,
            PooledConnectionLifetime = TimeSpan.FromMinutes(5),
            UseCookies = false,
            AllowAutoRedirect = false,
        };
        // Zeitlimits je Anfrage über CancellationToken (siehe SendAsync).
        var client = new HttpClient(handler) { Timeout = Timeout.InfiniteTimeSpan };
        string version = Assembly.GetExecutingAssembly().GetName().Version?.ToString(3) ?? "1.0.0";
        client.DefaultRequestHeaders.UserAgent.Add(new ProductInfoHeaderValue("SparkBegleiter", version));
        return client;
    }

    /// <summary>POST /api/desk/pair – tauscht den Einmal-Code gegen einen Geräteschlüssel.</summary>
    public static async Task<PairResult> PairAsync(string baseUrl, string code, string deviceName, CancellationToken ct)
    {
        var body = new JsonObject { ["code"] = code, ["name"] = deviceName, ["kind"] = "windows" };
        using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/api/desk/pair") { Content = JsonContent(body) };
        JsonNode json = await SendAsync(request, null, pairing: true, ShortTimeout, ct).ConfigureAwait(true);

        string? key = Json.Str(json["key"]);
        if (string.IsNullOrEmpty(key))
        {
            throw new SparkException(null, "Der Spark hat keinen Schlüssel geschickt.");
        }

        return new PairResult(key, Json.Str(json["profile"]));
    }

    /// <summary>GET /api/desk/config – welche Teile an sind und die Voreinstellungen.</summary>
    public static async Task<DeskConfig> GetConfigAsync(string baseUrl, string key, CancellationToken ct)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, baseUrl + "/api/desk/config");
        JsonNode json = await SendAsync(request, key, pairing: false, ShortTimeout, ct).ConfigureAwait(true);
        return DeskConfig.Parse(json);
    }

    /// <summary>GET /api/desk/poll – Herzschlag, neue Meldungen, Notaus-Stufe.</summary>
    public static async Task<PollResult> PollAsync(string baseUrl, string key, int after, CancellationToken ct)
    {
        string url = baseUrl + "/api/desk/poll?after=" + Math.Max(0, after).ToString(System.Globalization.CultureInfo.InvariantCulture);
        using var request = new HttpRequestMessage(HttpMethod.Get, url);
        JsonNode json = await SendAsync(request, key, pairing: false, ShortTimeout, ct).ConfigureAwait(true);

        var notes = new List<Note>();
        if (json["notes"] is JsonArray list)
        {
            foreach (JsonNode? item in list)
            {
                if (item is JsonObject o && Json.Int(o["n"]) is { } n)
                {
                    notes.Add(new Note(n, Json.Str(o["title"]) ?? "", Json.Str(o["body"]) ?? "", Json.Str(o["tag"])));
                }
            }
        }

        int level = json["notaus"] is JsonObject notaus ? Json.Int(notaus["level"]) ?? 0 : 0;
        return new PollResult(Json.Int(json["rev"]) ?? 0, notes, Json.Int(json["last"]) ?? after, level);
    }

    /// <summary>POST /api/desk/ask – Frage an den Spark (bis zu 3 Minuten).</summary>
    public static async Task<string> AskAsync(string baseUrl, string key, string text, CancellationToken ct)
    {
        var body = new JsonObject { ["text"] = text };
        if (LocalIanaTimeZone() is { } tz)
        {
            body["tz"] = tz;
        }

        using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/api/desk/ask") { Content = JsonContent(body) };
        JsonNode json = await SendAsync(request, key, pairing: false, LongTimeout, ct).ConfigureAwait(true);
        return Json.Str(json["answer"]) ?? throw new SparkException(null, "Der Spark hat keine Antwort geschickt.");
    }

    /// <summary>POST /api/desk/dictate – WAV (16 kHz, mono, 16 bit) in Text umwandeln.</summary>
    public static async Task<string> DictateAsync(string baseUrl, string key, byte[] wav, string sprache, CancellationToken ct)
    {
        using var form = new MultipartFormDataContent();
        var file = new ByteArrayContent(wav);
        file.Headers.ContentType = new MediaTypeHeaderValue("audio/wav");
        form.Add(file, "file", "aufnahme.wav");
        form.Add(new StringContent(string.IsNullOrEmpty(sprache) ? "auto" : sprache, Encoding.UTF8), "sprache");

        using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/api/desk/dictate") { Content = form };
        JsonNode json = await SendAsync(request, key, pairing: false, LongTimeout, ct).ConfigureAwait(true);
        return Json.Str(json["text"]) ?? throw new SparkException(null, "Der Spark hat keinen Text zurückgeschickt.");
    }

    /// <summary>POST /api/desk/notaus – Mein Notaus: das ganze Profil hält an.</summary>
    public static async Task NotausAsync(string baseUrl, string key, CancellationToken ct)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/api/desk/notaus") { Content = JsonContent(new JsonObject()) };
        _ = await SendAsync(request, key, pairing: false, ShortTimeout, ct).ConfigureAwait(true);
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
        JsonNode json = await SendAsync(request, key, pairing: false, LongTimeout, ct).ConfigureAwait(true);

        string? result = Json.Str(json["text"]);
        if (result is null)
        {
            throw new SparkException(null, "Der Spark hat keinen Text zurückgeschickt.");
        }

        return new AssistResult(result, ParseDiff(json["diff"]), Json.Int(json["changes"]), Json.Int(json["ms"]));
    }

    /// <summary>Die Windows-Zeitzone als IANA-Name (z. B. Europe/Berlin), wenn sie sich umrechnen lässt.</summary>
    private static string? LocalIanaTimeZone()
    {
        TimeZoneInfo local = TimeZoneInfo.Local;
        if (local.HasIanaId)
        {
            return local.Id;
        }

        return TimeZoneInfo.TryConvertWindowsIdToIanaId(local.Id, out string? iana) ? iana : null;
    }

    private static StringContent JsonContent(JsonObject body) =>
        new(body.ToJsonString(), Encoding.UTF8, "application/json");

    private static async Task<JsonNode> SendAsync(
        HttpRequestMessage request, string? key, bool pairing, TimeSpan timeout, CancellationToken ct)
    {
        if (key is not null)
        {
            request.Headers.Add(DeviceHeader, key);
        }

        using var timeoutCts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        timeoutCts.CancelAfter(timeout);

        HttpResponseMessage response;
        try
        {
            response = await Http.SendAsync(request, timeoutCts.Token).ConfigureAwait(true);
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested)
        {
            throw new SparkException(null, timeout >= LongTimeout
                ? "Der Spark hat nicht rechtzeitig geantwortet (3 Minuten). Bitte später noch einmal versuchen."
                : "Der Spark antwortet nicht.");
        }
        catch (HttpRequestException ex)
        {
            throw new SparkException(null, DescribeConnectionError(ex));
        }

        using (response)
        {
            string content;
            try
            {
                content = await response.Content.ReadAsStringAsync(timeoutCts.Token).ConfigureAwait(true);
            }
            catch (OperationCanceledException) when (!ct.IsCancellationRequested)
            {
                throw new SparkException(null, "Der Spark antwortet nicht.");
            }
            catch (HttpRequestException ex)
            {
                throw new SparkException(null, DescribeConnectionError(ex));
            }

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
                return json as JsonObject ?? throw new SparkException(null, "Unerwartete Antwort vom Spark.");
            }

            string? detail = Detail(json);
            throw new SparkException(status, ErrorText(status, detail, pairing), detail);
        }
    }

    private static string ErrorText(int status, string? detail, bool pairing)
    {
        if (status == 401 && !pairing)
        {
            return "Der Spark kennt dieses Gerät nicht mehr. Neu koppeln.";
        }

        if (!string.IsNullOrEmpty(detail))
        {
            return detail;
        }

        return status switch
        {
            400 or 409 when pairing => "Der Code ist falsch oder abgelaufen. Bitte im Panel einen neuen Code holen.",
            403 => "Dieser Teil ist im Panel ausgeschaltet (Ich → Begleiter).",
            404 => "Diese Adresse kennt der Begleiter nicht – ist der Spark aktuell?",
            413 => "Zu groß für den Spark.",
            429 => "Der Spark arbeitet noch. Bitte gleich noch einmal versuchen.",
            503 => "Der Spark ist gerade nicht verfügbar.",
            _ => $"Der Spark meldet einen Fehler ({status}).",
        };
    }

    /// <summary>"detail" ist meist ein Text; bei Prüffehlern eine Liste von Objekten mit "msg".</summary>
    private static string? Detail(JsonNode? json)
    {
        JsonNode? detail = json is JsonObject obj ? obj["detail"] : null;
        string? text = Json.Str(detail);
        if (text is null && detail is JsonArray list)
        {
            var parts = list.Select(item => item is JsonObject o ? Json.Str(o["msg"]) : Json.Str(item))
                            .Where(s => !string.IsNullOrEmpty(s));
            text = string.Join("; ", parts);
        }

        if (string.IsNullOrWhiteSpace(text))
        {
            return null;
        }

        text = text.Trim();
        return text.Length > MaxDetail ? text[..MaxDetail] + " …" : text;
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

        return "Der Spark ist nicht erreichbar. Läuft er, und stimmt die Adresse?";
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
            if (item is JsonArray { Count: >= 2 } pair && Json.Str(pair[0]) is { Length: 1 } op && Json.Str(pair[1]) is { } text)
            {
                parts.Add(new DiffPart(op[0], text));
            }
        }

        return parts;
    }
}
