using System.Globalization;
using System.Net.Http.Headers;
using System.Text.Json.Nodes;

namespace SparkBegleiter;

/// <summary>Eine Anfrage, den Bildschirm zu zeigen (Teil "view"): Kennung, ob auch bedient werden soll, und bei
/// Stufe 3 („Spark bedient den Rechner“, <see cref="Operate"/>) der Auftrag in den Worten der Person.</summary>
internal sealed record ViewAsk(string Id, bool Control, bool Operate = false, string Task = "");

/// <summary>Eine Eingabe aus dem Panel (fernsicht.py prüft sie, der Begleiter noch einmal). Stufe 3: Kind "step"
/// mit <see cref="Step"/> (click, double, right, scroll, key, type, ask), Nummer, Grund und Warnung.</summary>
internal sealed record ViewEvent(string Kind, double X, double Y, string Button, int Dy, string Key, string Text,
                                 string Step = "", int N = 0, int Of = 0, string Why = "", string Warn = "");

/// <summary>Rechner fernsteuern, Stufe 2: Bildschirm zeigen und bedienen (fernsicht.py im Panel).</summary>
internal static partial class SparkClient
{
    private static bool SafeId(string? id) =>
        id is { Length: > 0 and <= 64 } && id.All(c => char.IsAsciiLetterOrDigit(c) || c is '-' or '_');

    private static List<ViewAsk> ParseViews(JsonNode json)
    {
        var views = new List<ViewAsk>();
        if (json["views"] is JsonArray list)
        {
            foreach (JsonNode? item in list.Take(4))
            {
                string? id = Json.Str(item?["id"]);
                if (item is JsonObject o && SafeId(id))
                {
                    string want = Json.Str(o["want"]) ?? "view";
                    string task = Plain(Json.Str(o["task"]) ?? "", 300);
                    if (want == "operate" && task.Length == 0)
                    {
                        continue; // ohne Auftrag kein Bedienen
                    }

                    views.Add(new ViewAsk(id!, want is "control" or "operate", want == "operate", task));
                }
            }
        }

        return views;
    }

    /// <summary>POST /api/desk/view/answer {"id","mode"} – "no", "view" oder "control"; gibt den neuen Zustand zurück.</summary>
    public static async Task<string> ViewAnswerAsync(string baseUrl, string key, string id, string mode, CancellationToken ct)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/api/desk/view/answer")
        {
            Content = JsonContent(new JsonObject { ["id"] = id, ["mode"] = mode }),
        };
        JsonNode json = await SendAsync(request, key, pairing: false, ShortTimeout, ct).ConfigureAwait(false);
        return Json.Str(json["state"]) ?? "ended";
    }

    /// <summary>POST /api/desk/view/frame – ein JPEG; gibt den Zustand zurück (endet die Sitzung, hört der Begleiter auf).
    /// <paramref name="app"/>/<paramref name="exe"/>: das Programm vorn (Stufe 3 prüft es gegen die freigegebenen).</summary>
    public static async Task<string> ViewFrameAsync(string baseUrl, string key, string id, byte[] jpeg, int width, int height,
                                                    string app, string exe, CancellationToken ct)
    {
        string url = baseUrl + "/api/desk/view/frame?id=" + Uri.EscapeDataString(id) + "&w=" +
                     width.ToString(CultureInfo.InvariantCulture) + "&h=" + height.ToString(CultureInfo.InvariantCulture) +
                     "&app=" + Uri.EscapeDataString(Plain(app, 200)) + "&exe=" + Uri.EscapeDataString(Plain(exe, 200));
        var content = new ByteArrayContent(jpeg);
        content.Headers.ContentType = new MediaTypeHeaderValue("image/jpeg");
        using var request = new HttpRequestMessage(HttpMethod.Post, url) { Content = content };
        JsonNode json = await SendAsync(request, key, pairing: false, ShortTimeout, ct).ConfigureAwait(false);
        return Json.Str(json["state"]) ?? "ended";
    }

    /// <summary>GET /api/desk/view/input – wartet bis zu 20 s auf Eingaben; nur Bekanntes kommt durch.</summary>
    public static async Task<(string State, IReadOnlyList<ViewEvent> Events)> ViewInputAsync(string baseUrl, string key, string id, CancellationToken ct)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, baseUrl + "/api/desk/view/input?id=" + Uri.EscapeDataString(id));
        JsonNode json = await SendAsync(request, key, pairing: false, MediumTimeout, ct).ConfigureAwait(false);
        var events = new List<ViewEvent>();
        if (json["events"] is JsonArray list)
        {
            foreach (JsonNode? item in list.Take(200))
            {
                if (item is not JsonObject o)
                {
                    continue;
                }

                events.Add(new ViewEvent(Json.Str(o["t"]) ?? "", Num(o["x"]), Num(o["y"]), Json.Str(o["b"]) ?? "left",
                    Json.Int(o["dy"]) ?? 0, Json.Str(o["k"]) ?? "", Json.Str(o["s"]) ?? "",
                    Json.Str(o["kind"]) ?? "", Json.Int(o["n"]) ?? 0, Json.Int(o["of"]) ?? 0,
                    Plain(Json.Str(o["why"]) ?? "", 160), Plain(Json.Str(o["warn"]) ?? "", 160)));
            }
        }

        return (Json.Str(json["state"]) ?? "ended", events);
    }

    /// <summary>POST /api/desk/view/end {"id"} – hier am Rechner beendet.</summary>
    public static async Task ViewEndAsync(string baseUrl, string key, string id, CancellationToken ct)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/api/desk/view/end")
        {
            Content = JsonContent(new JsonObject { ["id"] = id }),
        };
        _ = await SendAsync(request, key, pairing: false, ShortTimeout, ct).ConfigureAwait(false);
    }

    /// <summary>POST /api/desk/view/step {"id","n","answer","error"?} – Stufe 3: done, skip, stop oder failed.</summary>
    public static async Task ViewStepAsync(string baseUrl, string key, string id, int n, string answer, string? error, CancellationToken ct)
    {
        var body = new JsonObject { ["id"] = id, ["n"] = n, ["answer"] = answer };
        if (!string.IsNullOrEmpty(error))
        {
            body["error"] = error.Length > 200 ? error[..200] : error;
        }

        using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/api/desk/view/step") { Content = JsonContent(body) };
        _ = await SendAsync(request, key, pairing: false, ShortTimeout, ct).ConfigureAwait(false);
    }

    /// <summary>Einzeilig, ohne Steuerzeichen, gekürzt: Texte vom Spark sind Daten und werden nur angezeigt.</summary>
    private static string Plain(string s, int max)
    {
        string t = string.Join(' ', new string(s.Select(c => char.IsControl(c) ? ' ' : c).ToArray())
            .Split(' ', StringSplitOptions.RemoveEmptyEntries));
        return t.Length > max ? t[..max] : t;
    }

    private static double Num(JsonNode? node) =>
        node is JsonValue v && v.TryGetValue(out double d) && double.IsFinite(d) ? d : -1;
}
