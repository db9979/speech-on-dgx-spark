using System.Net;
using System.Net.Http.Headers;
using System.Reflection;
using System.Security.Authentication;
using System.Security.Cryptography;
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

/// <summary>Eine Meldung; <see cref="Actions"/> = angebotene Knöpfe ("reply", "later", "open").</summary>
internal sealed record Note(int N, string Title, string Body, string? Tag, IReadOnlyList<string> Actions);

/// <summary>Eine Bitte des Spark, am PC etwas zu tun (Teil "act").</summary>
internal sealed record ActAsk(string Id, string Action, string Arg, string Text);

internal sealed record PollResult(int Rev, IReadOnlyList<Note> Notes, int Last, int NotausLevel, string? Update, IReadOnlyList<ActAsk> Asks,
    IReadOnlyList<InboxItem> Inbox);

/// <summary>Teil "inbox": etwas vom Handy für diesen PC (Text, Link oder Datei).</summary>
internal sealed record InboxItem(string Id, string Kind, string? Text, string? Name, long? Size);

/// <summary>Teil "agenda": ein Termin der nächsten 24 Stunden.</summary>
internal sealed record AgendaEvent(DateTimeOffset Start, DateTimeOffset? End, string Title, string Where);

/// <summary>Teil "agenda": eine fällige Erinnerung der nächsten 24 Stunden.</summary>
internal sealed record AgendaReminder(DateTimeOffset Due, string Text);

internal sealed record AgendaResult(IReadOnlyList<AgendaEvent> Events, IReadOnlyList<AgendaReminder> Reminders);

/// <summary>Teil "meeting": eine Aufgabe aus der Besprechung.</summary>
internal sealed record MeetingTask(string Text, DateTimeOffset? Due);

internal sealed record MeetingResult(string Summary, IReadOnlyList<MeetingTask> Tasks, int Chars);

/// <summary>Teil "home": ein Knopf mit Zustand ("on"/"off" oder unbekannt).</summary>
internal sealed record HomeState(string Id, string Name, string Kind, bool? On);

/// <summary>Antwort von /api/desk/file: Text (zusammenfassen/übersetzen/erklären) oder neuer Wissens-Eintrag.</summary>
internal sealed record FileResult(string? Text, string? Id, string? Name);

/// <summary>
/// Die Schnittstelle des Spark (/api/desk/… und /api/write/assist). Es wird nur mit der eingerichteten
/// Adresse geredet, Zertifikate werden immer normal geprüft, und es wird nichts protokolliert.
/// Der Geräteschlüssel steht nur im Kopf X-Speech-Device, nie in der Adresse.
/// </summary>
internal static partial class SparkClient
{
    private const string DeviceHeader = "X-Speech-Device";

    /// <summary>Höchstlänge für Texte vom Spark, die angezeigt werden (Fehlermeldungen).</summary>
    private const int MaxDetail = 400;

    private static readonly TimeSpan LongTimeout = TimeSpan.FromSeconds(180);
    private static readonly TimeSpan ShortTimeout = TimeSpan.FromSeconds(20);
    private static readonly TimeSpan MediumTimeout = TimeSpan.FromSeconds(60);

    /// <summary>Höchstgröße für /api/desk/file (laut Vertrag).</summary>
    public const long MaxFileBytes = 20L * 1024 * 1024;

    /// <summary>Höchstgröße für das Bild an /api/desk/screen.</summary>
    public const int MaxImageBytes = 6 * 1024 * 1024;

    private static readonly HttpClient Http = CreateClient();

    /// <summary>Bei jeder Abfrage von Einstellungen und Herzschlag: eigene Version und Bauart (für Updates).</summary>
    private static string VersionQuery =>
        "version=" + Uri.EscapeDataString(Updater.CurrentText) + "&arch=" + Uri.EscapeDataString(Updater.Arch);

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
        using var request = new HttpRequestMessage(HttpMethod.Get, baseUrl + "/api/desk/config?" + VersionQuery);
        JsonNode json = await SendAsync(request, key, pairing: false, ShortTimeout, ct).ConfigureAwait(true);
        return DeskConfig.Parse(json);
    }

    /// <summary>GET /api/desk/poll – Herzschlag, neue Meldungen, Notaus-Stufe.</summary>
    /// <param name="micClosed">„Mikrofon zu“ – das Panel zeigt es unter Ich → Begleiter (nur dieser Zustand, nie Ton).</param>
    public static async Task<PollResult> PollAsync(string baseUrl, string key, int after, bool micClosed, CancellationToken ct)
    {
        string url = baseUrl + "/api/desk/poll?after=" + Math.Max(0, after).ToString(System.Globalization.CultureInfo.InvariantCulture)
                     + "&mic=" + (micClosed ? "closed" : "open") + "&" + VersionQuery;
        using var request = new HttpRequestMessage(HttpMethod.Get, url);
        JsonNode json = await SendAsync(request, key, pairing: false, ShortTimeout, ct).ConfigureAwait(true);

        var notes = new List<Note>();
        if (json["notes"] is JsonArray list)
        {
            foreach (JsonNode? item in list)
            {
                if (item is JsonObject o && Json.Int(o["n"]) is { } n)
                {
                    var actions = new List<string>();
                    if (o["actions"] is JsonArray acts)
                    {
                        actions.AddRange(acts.Select(Json.Str).OfType<string>().Where(a => a is "reply" or "later" or "open").Distinct());
                    }

                    notes.Add(new Note(n, Json.Str(o["title"]) ?? "", Json.Str(o["body"]) ?? "", Json.Str(o["tag"]), actions));
                }
            }
        }

        List<ActAsk> asks = ParseAsks(json);

        var inbox = new List<InboxItem>();
        if (json["inbox"] is JsonArray inboxList)
        {
            foreach (JsonNode? item in inboxList.Take(20))
            {
                string? id = Json.Str(item?["id"]) ?? Json.Long(item?["id"])?.ToString(System.Globalization.CultureInfo.InvariantCulture);
                if (item is JsonObject o && IsSafeId(id) && Json.Str(o["kind"]) is "text" or "link" or "file")
                {
                    inbox.Add(new InboxItem(id!, Json.Str(o["kind"])!, Json.Str(o["text"]), Json.Str(o["name"]), Json.Long(o["size"])));
                }
            }
        }

        int level = json["notaus"] is JsonObject notaus ? Json.Int(notaus["level"]) ?? 0 : 0;
        return new PollResult(Json.Int(json["rev"]) ?? 0, notes, Json.Int(json["last"]) ?? after, level, Json.Str(json["update"]), asks, inbox);
    }

    /// <summary>Kennungen, die in eine Adresse oder JSON zurückgehen: nur Buchstaben, Ziffern, '-' und '_'.</summary>
    public static bool IsSafeId(string? id) =>
        id is { Length: > 0 and <= 64 } && id.All(c => char.IsAsciiLetterOrDigit(c) || c is '-' or '_');

    // ------------------------------------------------------------------ Version 4

    /// <summary>Höchstgröße einer Datei aus dem Posteingang (laut Vertrag 20 MB).</summary>
    public const long MaxInboxBytes = 20L * 1024 * 1024;

    /// <summary>Höchstgröße der Vorlese-Datei (5000 Zeichen sind wenige Minuten Sprache).</summary>
    private const long MaxSpeakBytes = 64L * 1024 * 1024;

    /// <summary>POST /api/desk/speak – Text (≤ 5000 Zeichen) in der Stimme des Profils, Antwort: WAV.</summary>
    public static async Task<byte[]> SpeakAsync(string baseUrl, string key, string text, CancellationToken ct)
    {
        var body = new JsonObject { ["text"] = text.Length > 5000 ? text[..5000] : text };
        using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/api/desk/speak") { Content = JsonContent(body) };
        return await SendForBytesAsync(request, key, LongTimeout, MaxSpeakBytes, ct).ConfigureAwait(true);
    }

    /// <summary>GET /api/desk/inbox/file?id=… – die Datei selbst (≤ 20 MB).</summary>
    public static async Task<byte[]> InboxFileAsync(string baseUrl, string key, string id, CancellationToken ct)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, baseUrl + "/api/desk/inbox/file?id=" + Uri.EscapeDataString(id));
        return await SendForBytesAsync(request, key, LongTimeout, MaxInboxBytes, ct).ConfigureAwait(true);
    }

    /// <summary>GET /api/desk/office/&lt;app&gt;.xml – das Manifest des Office-Add-ins (word, excel, outlook; ≤ 64 KB).</summary>
    public static async Task<byte[]> OfficeManifestAsync(string baseUrl, string key, string app, CancellationToken ct)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, baseUrl + "/api/desk/office/" + Uri.EscapeDataString(app) + ".xml");
        return await SendForBytesAsync(request, key, ShortTimeout, 64 * 1024, ct).ConfigureAwait(true);
    }

    /// <summary>POST /api/desk/inbox/done {"id"} – erledigt (auch bei abgelehnten Links).</summary>
    public static async Task InboxDoneAsync(string baseUrl, string key, string id, CancellationToken ct)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/api/desk/inbox/done") { Content = JsonContent(new JsonObject { ["id"] = id }) };
        _ = await SendAsync(request, key, pairing: false, ShortTimeout, ct).ConfigureAwait(true);
    }

    /// <summary>GET /api/desk/agenda – Termine und Erinnerungen der nächsten 24 Stunden (je höchstens 10).</summary>
    public static async Task<AgendaResult> AgendaAsync(string baseUrl, string key, CancellationToken ct)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, baseUrl + "/api/desk/agenda");
        JsonNode json = await SendAsync(request, key, pairing: false, ShortTimeout, ct).ConfigureAwait(true);
        var events = new List<AgendaEvent>();
        if (json["events"] is JsonArray eventList)
        {
            foreach (JsonNode? item in eventList.Take(10))
            {
                if (item is JsonObject o && ParseTime(Json.Str(o["start"])) is { } start)
                {
                    events.Add(new AgendaEvent(start, ParseTime(Json.Str(o["end"])), Clean(Json.Str(o["title"]), 120), Clean(Json.Str(o["where"]), 120)));
                }
            }
        }

        var reminders = new List<AgendaReminder>();
        if (json["reminders"] is JsonArray reminderList)
        {
            foreach (JsonNode? item in reminderList.Take(10))
            {
                if (item is JsonObject o && ParseTime(Json.Str(o["due"])) is { } due)
                {
                    reminders.Add(new AgendaReminder(due, Clean(Json.Str(o["text"]), 300)));
                }
            }
        }

        return new AgendaResult(events, reminders);
    }

    /// <summary>POST /api/desk/remind – Text oder Meldung in <paramref name="minutes"/> Minuten erinnern. Gibt die Fälligkeit zurück.</summary>
    public static async Task<DateTimeOffset?> RemindAsync(string baseUrl, string key, string? text, int? note, int minutes, CancellationToken ct)
    {
        var body = new JsonObject { ["minutes"] = Math.Clamp(minutes, 1, 1440) };
        if (note is { } n)
        {
            body["note"] = n;
        }
        else
        {
            string t = (text ?? "").Trim();
            body["text"] = t.Length > 300 ? t[..300] : t;
        }

        using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/api/desk/remind") { Content = JsonContent(body) };
        JsonNode json = await SendAsync(request, key, pairing: false, ShortTimeout, ct).ConfigureAwait(true);
        return ParseTime(Json.Str(json["due"]));
    }

    /// <summary>POST /api/desk/busy – „Nicht stören“ (Telefonat/Präsentation) melden oder beenden.</summary>
    public static async Task BusyAsync(string baseUrl, string key, bool busy, string? why, CancellationToken ct)
    {
        var body = new JsonObject { ["busy"] = busy };
        if (busy && why is not null)
        {
            body["why"] = why;
        }

        using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/api/desk/busy") { Content = JsonContent(body) };
        _ = await SendAsync(request, key, pairing: false, ShortTimeout, ct).ConfigureAwait(true);
    }

    /// <summary>POST /api/desk/meeting/start {} – neue Besprechung, gibt die Kennung zurück.</summary>
    public static async Task<string> MeetingStartAsync(string baseUrl, string key, CancellationToken ct)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/api/desk/meeting/start") { Content = JsonContent(new JsonObject()) };
        JsonNode json = await SendAsync(request, key, pairing: false, ShortTimeout, ct).ConfigureAwait(true);
        string? id = Json.Str(json["id"]) ?? Json.Long(json["id"])?.ToString(System.Globalization.CultureInfo.InvariantCulture);
        return IsSafeId(id) ? id! : throw new SparkException(null, "Der Spark hat keine Kennung für die Besprechung geschickt.");
    }

    /// <summary>POST /api/desk/meeting/chunk – ein Stück Aufnahme (WAV 16 kHz mono, ≤ 60 s).</summary>
    public static async Task MeetingChunkAsync(string baseUrl, string key, string id, byte[] wav, CancellationToken ct)
    {
        using var form = new MultipartFormDataContent();
        form.Add(new StringContent(id, Encoding.UTF8), "id");
        var file = new ByteArrayContent(wav);
        file.Headers.ContentType = new MediaTypeHeaderValue("audio/wav");
        form.Add(file, "file", "stueck.wav");
        using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/api/desk/meeting/chunk") { Content = form };
        _ = await SendAsync(request, key, pairing: false, LongTimeout, ct).ConfigureAwait(true);
    }

    /// <summary>POST /api/desk/meeting/end {"id"} – Zusammenfassung und Aufgaben.</summary>
    public static async Task<MeetingResult> MeetingEndAsync(string baseUrl, string key, string id, CancellationToken ct)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/api/desk/meeting/end") { Content = JsonContent(new JsonObject { ["id"] = id }) };
        JsonNode json = await SendAsync(request, key, pairing: false, TimeSpan.FromMinutes(6), ct).ConfigureAwait(true);
        var tasks = new List<MeetingTask>();
        if (json["tasks"] is JsonArray list)
        {
            foreach (JsonNode? item in list.Take(50))
            {
                if (item is JsonObject o && Json.Str(o["text"]) is { } text && text.Trim().Length > 0)
                {
                    tasks.Add(new MeetingTask(Clean(text, 300), ParseTime(Json.Str(o["due"]))));
                }
            }
        }

        return new MeetingResult(Json.Str(json["summary"]) ?? "", tasks, Json.Int(json["chars"]) ?? 0);
    }

    /// <summary>POST /api/desk/meeting/keep – gewählte Aufgaben als Erinnerung und/oder aufs reMarkable.</summary>
    public static async Task<(int Reminders, bool Remarkable)> MeetingKeepAsync(
        string baseUrl, string key, string id, IEnumerable<int> tasks, bool remarkable, CancellationToken ct)
    {
        var list = new JsonArray();
        foreach (int i in tasks)
        {
            list.Add(i);
        }

        var body = new JsonObject { ["id"] = id, ["tasks"] = list, ["remarkable"] = remarkable };
        using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/api/desk/meeting/keep") { Content = JsonContent(body) };
        JsonNode json = await SendAsync(request, key, pairing: false, MediumTimeout, ct).ConfigureAwait(true);
        return (Json.Int(json["reminders"]) ?? 0, Json.Bool(json["remarkable"]) ?? false);
    }

    /// <summary>GET /api/desk/home – die Knöpfe mit Zustand.</summary>
    public static async Task<IReadOnlyList<HomeState>> HomeAsync(string baseUrl, string key, CancellationToken ct)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, baseUrl + "/api/desk/home");
        JsonNode json = await SendAsync(request, key, pairing: false, ShortTimeout, ct).ConfigureAwait(true);
        var states = new List<HomeState>();
        if (json["buttons"] is JsonArray list)
        {
            foreach (JsonNode? item in list.Take(24))
            {
                string? id = Json.Str(item?["id"]) ?? Json.Long(item?["id"])?.ToString(System.Globalization.CultureInfo.InvariantCulture);
                if (item is JsonObject o && HomeButton.IsValidId(id))
                {
                    states.Add(new HomeState(id!, Clean(Json.Str(o["name"]), 40), HomeButton.NormalizeKind(Json.Str(o["kind"])), OnOff(Json.Str(o["state"]))));
                }
            }
        }

        return states;
    }

    /// <summary>POST /api/desk/home {"id","code"?} – Knopf drücken; gibt den neuen Zustand zurück.</summary>
    public static async Task<bool?> HomePressAsync(string baseUrl, string key, string id, string? code, CancellationToken ct)
    {
        var body = new JsonObject { ["id"] = id };
        if (!string.IsNullOrEmpty(code))
        {
            body["code"] = code;
        }

        using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/api/desk/home") { Content = JsonContent(body) };
        JsonNode json = await SendAsync(request, key, pairing: false, MediumTimeout, ct).ConfigureAwait(true);
        return OnOff(Json.Str(json["state"]));
    }

    /// <summary>POST /api/desk/apps – installierte Programme (Teil "act"), damit das Panel sie zur Auswahl anbietet.</summary>
    public static async Task AppsAsync(string baseUrl, string key, IEnumerable<(string Name, string Path)> apps, CancellationToken ct)
    {
        var list = new JsonArray();
        foreach (var (name, path) in apps)
        {
            list.Add(new JsonObject { ["name"] = name, ["path"] = path });
        }

        using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/api/desk/apps") { Content = JsonContent(new JsonObject { ["apps"] = list }) };
        _ = await SendAsync(request, key, pairing: false, MediumTimeout, ct).ConfigureAwait(true);
    }

    /// <summary>
    /// GET /api/desk/daily?kind=morning|evening – Tagesstart bzw. Feierabend: Text ohne Zeichen (Hinweis), Md mit
    /// Markdown für das Fenster „Frag Spark“ (fehlt bei älteren Sparks und beim Feierabend).
    /// </summary>
    public static async Task<(string Text, string? Md)> DailyAsync(string baseUrl, string key, bool morning, CancellationToken ct)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, baseUrl + "/api/desk/daily?kind=" + (morning ? "morning" : "evening"));
        JsonNode json = await SendAsync(request, key, pairing: false, LongTimeout, ct).ConfigureAwait(true);
        string text = Json.Str(json["text"]) ?? throw new SparkException(null, "Der Spark hat keinen Text zurückgeschickt.");
        return (text, Json.Str(json["md"]));
    }

    private static bool? OnOff(string? state) => state switch
    {
        "on" => true,
        "off" => false,
        _ => null,
    };

    /// <summary>Text vom Spark für eine Zeile: ohne Zeilenumbrüche, gekürzt.</summary>
    private static string Clean(string? text, int max)
    {
        string t = (text ?? "").Trim().ReplaceLineEndings(" ");
        return t.Length > max ? t[..(max - 1)] + "…" : t;
    }

    /// <summary>ISO-Zeit; ohne Zeitzone gilt die Ortszeit dieses PCs.</summary>
    private static DateTimeOffset? ParseTime(string? text) =>
        !string.IsNullOrWhiteSpace(text) && DateTimeOffset.TryParse(text.Trim(), System.Globalization.CultureInfo.InvariantCulture,
            System.Globalization.DateTimeStyles.AssumeLocal, out DateTimeOffset t)
            ? t
            : null;

    /// <summary>Anfrage, deren Antwort Bytes sind (WAV, Datei); Fehler wie bei <see cref="SendAsync"/>.</summary>
    private static async Task<byte[]> SendForBytesAsync(HttpRequestMessage request, string key, TimeSpan timeout, long maxBytes, CancellationToken ct)
    {
        request.Headers.Add(DeviceHeader, key);
        using var timeoutCts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        timeoutCts.CancelAfter(timeout);

        HttpResponseMessage response;
        try
        {
            response = await Http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, timeoutCts.Token).ConfigureAwait(true);
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested)
        {
            throw new SparkException(null, "Der Spark hat nicht rechtzeitig geantwortet. Bitte später noch einmal versuchen.");
        }
        catch (HttpRequestException ex)
        {
            throw new SparkException(null, DescribeConnectionError(ex));
        }

        using (response)
        {
            int status = (int)response.StatusCode;
            try
            {
                if (!response.IsSuccessStatusCode)
                {
                    string? detail = null;
                    try
                    {
                        string content = await response.Content.ReadAsStringAsync(timeoutCts.Token).ConfigureAwait(true);
                        detail = Detail(content.Length is > 0 and < 20000 ? JsonNode.Parse(content) : null);
                    }
                    catch (JsonException)
                    {
                        // ohne Text
                    }

                    throw new SparkException(status, ErrorText(status, detail, pairing: false), detail);
                }

                if (response.Content.Headers.ContentLength is long length && length > maxBytes)
                {
                    throw new SparkException(null, "Die Antwort des Spark ist zu groß.");
                }

                using var buffer = new MemoryStream();
                Stream body = await response.Content.ReadAsStreamAsync(timeoutCts.Token).ConfigureAwait(true);
                await using (body.ConfigureAwait(true))
                {
                    byte[] chunk = new byte[81920];
                    while (true)
                    {
                        int read = await body.ReadAsync(chunk, timeoutCts.Token).ConfigureAwait(true);
                        if (read == 0)
                        {
                            break;
                        }

                        if (buffer.Length + read > maxBytes)
                        {
                            throw new SparkException(null, "Die Antwort des Spark ist zu groß.");
                        }

                        buffer.Write(chunk, 0, read);
                    }
                }

                return buffer.ToArray();
            }
            catch (OperationCanceledException) when (!ct.IsCancellationRequested)
            {
                throw new SparkException(null, "Der Spark antwortet nicht.");
            }
            catch (HttpRequestException ex)
            {
                throw new SparkException(null, DescribeConnectionError(ex));
            }
            catch (IOException)
            {
                throw new SparkException(null, "Die Verbindung zum Spark ist abgebrochen.");
            }
        }
    }

    /// <summary>
    /// POST /api/desk/ask – Frage an den Spark (bis zu 3 Minuten). Answer ist schlichter Text (Vorlesen), Md die
    /// Antwort mit Markdown zum gegliederten Anzeigen (fehlt bei älteren Sparks).
    /// </summary>
    public static async Task<(string Answer, string? Md)> AskAsync(string baseUrl, string key, string text, CancellationToken ct, int? note = null)
    {
        var body = new JsonObject { ["text"] = text };
        if (note is { } n)
        {
            body["note"] = n; // Antwort auf eine Meldung (Teil "actions")
        }

        if (LocalIanaTimeZone() is { } tz)
        {
            body["tz"] = tz;
        }

        using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/api/desk/ask") { Content = JsonContent(body) };
        JsonNode json = await SendAsync(request, key, pairing: false, LongTimeout, ct).ConfigureAwait(true);
        string answer = Json.Str(json["answer"]) ?? throw new SparkException(null, "Der Spark hat keine Antwort geschickt.");
        return (answer, Json.Str(json["md"]));
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
        string baseUrl, string key, string text, string art, string? sprache, string? wunsch, CancellationToken ct,
        string? app = null, string? mail = null)
    {
        var body = new JsonObject { ["text"] = text, ["art"] = art };
        if (app is not null)
        {
            body["app"] = app; // nur die Art des Programms (Teil "context"), nie Titel oder Inhalte
        }

        if (mail is not null)
        {
            body["mail"] = mail; // Teil "mail": die Mail, auf die geantwortet wird
        }

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

    /// <summary>POST /api/desk/file – Datei zusammenfassen/übersetzen/erklären lassen oder ins Wissen übernehmen.</summary>
    public static async Task<FileResult> FileAsync(
        string baseUrl, string key, byte[] data, string fileName, string contentType, string what, string? sprache, CancellationToken ct,
        string? ordner = null)
    {
        using var form = new MultipartFormDataContent();
        var file = new ByteArrayContent(data);
        file.Headers.ContentType = new MediaTypeHeaderValue(contentType);
        form.Add(file, "file", fileName);
        form.Add(new StringContent(what, Encoding.UTF8), "what");
        if (ordner is not null && what == "wissen")
        {
            // der Unterordner von Spark-Wissen („/a/b“, „/“ = direkt darin): das Panel lässt ausgelassene Ordner aus
            form.Add(new StringContent(ordner.Length > 500 ? ordner[..500] : ordner, Encoding.UTF8), "ordner");
        }
        if (!string.IsNullOrEmpty(sprache))
        {
            form.Add(new StringContent(sprache, Encoding.UTF8), "sprache");
        }

        using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/api/desk/file") { Content = form };
        JsonNode json = await SendAsync(request, key, pairing: false, LongTimeout, ct).ConfigureAwait(true);
        return new FileResult(Json.Str(json["text"]), Json.Str(json["id"]) ?? Json.Long(json["id"])?.ToString(System.Globalization.CultureInfo.InvariantCulture), Json.Str(json["name"]));
    }

    /// <summary>POST /api/desk/screen – Bildschirmausschnitt mit optionaler Frage.</summary>
    public static async Task<string> ScreenAsync(
        string baseUrl, string key, byte[] image, string contentType, string question, string what, CancellationToken ct)
    {
        using var form = new MultipartFormDataContent();
        var file = new ByteArrayContent(image);
        file.Headers.ContentType = new MediaTypeHeaderValue(contentType);
        form.Add(file, "image", contentType == "image/png" ? "ausschnitt.png" : "ausschnitt.jpg");
        form.Add(new StringContent(question, Encoding.UTF8), "question");
        form.Add(new StringContent(what, Encoding.UTF8), "what");

        using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/api/desk/screen") { Content = form };
        JsonNode json = await SendAsync(request, key, pairing: false, LongTimeout, ct).ConfigureAwait(true);
        return Json.Str(json["text"]) ?? throw new SparkException(null, "Der Spark hat keinen Text zurückgeschickt.");
    }

    /// <summary>POST /api/desk/hear – kurzer Satz (≤ 5 s): Weckwort gehört? Und was danach kam.</summary>
    public static async Task<(bool Wake, string After)> HearAsync(string baseUrl, string key, byte[] wav, CancellationToken ct)
    {
        using var form = new MultipartFormDataContent();
        var file = new ByteArrayContent(wav);
        file.Headers.ContentType = new MediaTypeHeaderValue("audio/wav");
        form.Add(file, "file", "satz.wav");

        using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/api/desk/hear") { Content = form };
        JsonNode json = await SendAsync(request, key, pairing: false, MediumTimeout, ct).ConfigureAwait(true);
        return (Json.Bool(json["wake"]) ?? false, (Json.Str(json["rest"]) ?? "").Trim());
    }

    private static List<ActAsk> ParseAsks(JsonNode json)
    {
        var asks = new List<ActAsk>();
        if (json["asks"] is JsonArray askList)
        {
            foreach (JsonNode? item in askList.Take(20))
            {
                // Kennung als Text oder Zahl; nur harmlose Zeichen, weil sie in die Adresse kommt.
                string? id = Json.Str(item?["id"]) ?? Json.Long(item?["id"])?.ToString(System.Globalization.CultureInfo.InvariantCulture);
                if (item is JsonObject o && id is { Length: > 0 and <= 64 } && id.All(c => char.IsAsciiLetterOrDigit(c) || c is '-' or '_'))
                {
                    asks.Add(new ActAsk(id, Json.Str(o["action"]) ?? "", Json.Str(o["arg"]) ?? "", Json.Str(o["text"]) ?? ""));
                }
            }
        }

        return asks;
    }

    /// <summary>GET /api/desk/wait – wartet bis zu 25 s auf neue Bitten (Teil "act") und Bildschirm-Anfragen
    /// (Teil "view"); leer, wenn keine kam.</summary>
    public static async Task<(IReadOnlyList<ActAsk> Asks, IReadOnlyList<ViewAsk> Views)> WaitAsync(string baseUrl, string key, CancellationToken ct)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, baseUrl + "/api/desk/wait");
        JsonNode json = await SendAsync(request, key, pairing: false, MediumTimeout, ct).ConfigureAwait(true);
        return (ParseAsks(json), ParseViews(json));
    }

    /// <summary>POST /api/desk/ordner – die Unterordner von Spark-Wissen (nur Namen, „a/b“), für den Ordnerbaum im Panel.</summary>
    public static async Task DirsAsync(string baseUrl, string key, IEnumerable<string> dirs, CancellationToken ct)
    {
        var body = new JsonObject { ["dirs"] = new JsonArray(dirs.Take(2000).Select(d => (JsonNode?)JsonValue.Create(d)).ToArray()) };
        using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/api/desk/ordner") { Content = JsonContent(body) };
        _ = await SendAsync(request, key, pairing: false, ShortTimeout, ct).ConfigureAwait(true);
    }

    /// <summary>POST /api/desk/local – was die Person hier am PC eingestellt hat: Namen der Kurzbefehle und „ohne Rückfrage“.</summary>
    public static async Task LocalAsync(string baseUrl, string key, IEnumerable<string> shortcuts, IEnumerable<string> auto, CancellationToken ct)
    {
        var body = new JsonObject
        {
            ["shortcuts"] = new JsonArray(shortcuts.Take(30).Select(n => (JsonNode?)JsonValue.Create(n)).ToArray()),
            ["auto"] = new JsonArray(auto.Take(20).Select(n => (JsonNode?)JsonValue.Create(n)).ToArray()),
        };
        using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/api/desk/local") { Content = JsonContent(body) };
        _ = await SendAsync(request, key, pairing: false, ShortTimeout, ct).ConfigureAwait(true);
    }

    /// <summary>POST /api/desk/act {"id","ok","error"?,"auto"?} – Ergebnis einer Bitte (erlaubt und ausgeführt, abgelehnt oder Fehler).</summary>
    /// <param name="auto">Ohne Rückfrage gelaufen (hier am PC so eingestellt).</param>
    /// <param name="failed">Erlaubt, aber es ging nicht (oder der Begleiter kann es nicht) – nicht „abgelehnt“.</param>
    public static async Task ActResultAsync(string baseUrl, string key, string id, bool ok, string? error, CancellationToken ct,
                                            bool auto = false, bool failed = false)
    {
        var body = new JsonObject { ["id"] = id, ["ok"] = ok, ["auto"] = auto, ["failed"] = failed };
        if (!ok && !string.IsNullOrEmpty(error))
        {
            body["error"] = error.Length > 300 ? error[..300] : error;
        }

        using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/api/desk/act") { Content = JsonContent(body) };
        _ = await SendAsync(request, key, pairing: false, ShortTimeout, ct).ConfigureAwait(true);
    }

    /// <summary>
    /// GET /api/desk/update?arch=… – lädt die neue Version (nur vom eigenen Spark, keine Umleitungen) in
    /// <paramref name="target"/> und gibt Größe und SHA-256 (Hex) der geladenen Bytes zurück. Bricht ab,
    /// sobald mehr kommt als angekündigt.
    /// </summary>
    public static async Task<(long Size, string Sha256)> DownloadUpdateAsync(
        string baseUrl, string key, string arch, long expectedSize, Stream target, IProgress<long>? progress, CancellationToken ct)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, baseUrl + "/api/desk/update?arch=" + Uri.EscapeDataString(arch));
        request.Headers.Add(DeviceHeader, key);

        // Zeitlimit ohne Fortschritt (die Datei selbst darf länger brauchen).
        using var idle = CancellationTokenSource.CreateLinkedTokenSource(ct);
        TimeSpan stall = TimeSpan.FromSeconds(60);
        idle.CancelAfter(stall);

        HttpResponseMessage response;
        try
        {
            response = await Http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, idle.Token).ConfigureAwait(true);
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested)
        {
            throw new SparkException(null, "Der Spark antwortet nicht.");
        }
        catch (HttpRequestException ex)
        {
            throw new SparkException(null, DescribeConnectionError(ex));
        }

        using (response)
        {
            int status = (int)response.StatusCode;
            if (!response.IsSuccessStatusCode)
            {
                string? detail = null;
                try
                {
                    string content = await response.Content.ReadAsStringAsync(idle.Token).ConfigureAwait(true);
                    detail = Detail(content.Length is > 0 and < 20000 ? JsonNode.Parse(content) : null);
                }
                catch (Exception ex) when (ex is JsonException or HttpRequestException or OperationCanceledException)
                {
                    // ohne Text
                }

                string message = status == 404 && detail is null
                    ? "Der Spark hat die neue Version (noch) nicht bereit."
                    : ErrorText(status, detail, pairing: false);
                throw new SparkException(status, message, detail);
            }

            if (response.Content.Headers.ContentEncoding.Count == 0 &&
                response.Content.Headers.ContentLength is long length && length != expectedSize)
            {
                throw new SparkException(null, Updater.Corrupt);
            }

            using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
            byte[] buffer = new byte[81920];
            long total = 0;
            try
            {
                Stream body = await response.Content.ReadAsStreamAsync(idle.Token).ConfigureAwait(true);
                await using (body.ConfigureAwait(true))
                {
                    while (true)
                    {
                        idle.CancelAfter(stall);
                        int read = await body.ReadAsync(buffer, idle.Token).ConfigureAwait(true);
                        if (read == 0)
                        {
                            break;
                        }

                        total += read;
                        if (total > expectedSize)
                        {
                            throw new SparkException(null, Updater.Corrupt);
                        }

                        hash.AppendData(buffer, 0, read);
                        await target.WriteAsync(buffer.AsMemory(0, read), ct).ConfigureAwait(true);
                        progress?.Report(total);
                    }
                }
            }
            catch (OperationCanceledException) when (!ct.IsCancellationRequested)
            {
                throw new SparkException(null, "Das Laden ist hängen geblieben. Später noch einmal versuchen.");
            }
            catch (HttpRequestException ex)
            {
                throw new SparkException(null, DescribeConnectionError(ex));
            }
            catch (IOException ex) when (ex.InnerException is System.Net.Sockets.SocketException or HttpRequestException)
            {
                throw new SparkException(null, "Die Verbindung zum Spark ist beim Laden abgebrochen.");
            }

            return (total, Convert.ToHexString(hash.GetHashAndReset()));
        }
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
