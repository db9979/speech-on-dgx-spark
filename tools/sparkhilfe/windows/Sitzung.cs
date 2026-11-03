using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using SparkBegleiter;

namespace SparkHilfe;

/// <summary>
/// Eine Hilfe über WSS (spontansteuern.py): erste Nachricht der Einmal-Schlüssel, dann erst den Namen des Helfers
/// zeigen und fragen (Ablehnen / Nur ansehen / Erlauben); danach Bilder (JPEG, höchstens <see cref="MaxFrame"/> Bytes,
/// höchstens vier je Sekunde) hin und Eingaben zurück, nur aus den festen Listen des Kerns, nur nach „Erlauben“ und nur
/// solange der Helfer „Steuern“ gewählt hat. Kein Origin-Header, keine eigene Zertifikatsprüfung, keine Weiterleitung,
/// kein anderes Ziel. Bild und Eingaben liegen nur im Speicher.
/// </summary>
internal sealed class Sitzung
{
    /// <summary>Ein Bild höchstens so groß (fernsicht.MAX_FRAME); größere schickt das Programm nie.</summary>
    public const int MaxFrame = 700 * 1024;

    /// <summary>Eine Nachricht vom Panel höchstens so groß (spontanhilfe.MAX_MSG); größere beenden die Hilfe.</summary>
    public const int MaxMessage = 16 * 1024;

    /// <summary>Eingaben je Nachricht höchstens (fernsicht.MAX_EVENTS).</summary>
    public const int MaxEvents = 40;

    private const int HelperMax = 60;
    private static readonly TimeSpan Wait = TimeSpan.FromSeconds(20);
    private static readonly TimeSpan KeepAlive = TimeSpan.FromSeconds(5);

    private readonly Ziel _ziel;
    private readonly StatusForm _status;
    private readonly ClientWebSocket _ws = new();
    private readonly CancellationTokenSource _cts = new();
    private readonly SemaphoreSlim _send = new(1, 1);
    private readonly Rectangle _screen = Sicht.MainScreen();
    private List<Form> _marks = new();
    private ViewBar? _bar;
    private string _helper = "";
    private string _mode = "";
    private bool _steuern;
    private bool _stopped;
    private Task _ending = Task.CompletedTask;

    public Sitzung(Ziel ziel, StatusForm status)
    {
        _ziel = ziel;
        _status = status;
        _ws.Options.KeepAliveInterval = TimeSpan.FromSeconds(20);
    }

    /// <summary>Läuft bis zum Ende der Hilfe; gibt den Satz für das Fenster zurück (leer: einfach schließen).</summary>
    public async Task<string> RunAsync()
    {
        try
        {
            using (var connect = CancellationTokenSource.CreateLinkedTokenSource(_cts.Token))
            {
                connect.CancelAfter(Wait);
                await _ws.ConnectAsync(_ziel.Socket, connect.Token);
            }

            string art = System.Runtime.InteropServices.RuntimeInformation.ProcessArchitecture
                         == System.Runtime.InteropServices.Architecture.Arm64 ? "windows-arm64" : "windows-x64";
            await SendAsync(new Dictionary<string, string> { ["typ"] = "hallo", ["schluessel"] = _ziel.Key, ["art"] = art });
            JsonElement? hello = await ReceiveJsonAsync(Wait);
            if (hello is not { } h || Str(h, "typ") != "stand" || Str(h, "stand") != "frage")
            {
                return Texte.T("neu_laden");
            }

            _helper = Plain(Str(h, "admin"), HelperMax);   // erst jetzt: das Panel hat den Schlüssel angenommen
            if (_helper.Length == 0)
            {
                _helper = "Admin";
            }

            string mode;
            using (var form = new ViewAskForm(Question()))
            {
                mode = await form.AskAsync();
            }

            if (_stopped)
            {
                return "";
            }

            await SendAsync(new Dictionary<string, string> { ["typ"] = "antwort", ["modus"] = mode });
            if (mode is not ("view" or "control"))
            {
                await CloseAsync();
                return Texte.T("abgelehnt");
            }

            _mode = mode;
            ShowFrame();
            Task frames = FrameLoopAsync(_cts.Token);
            string why = await ReceiveLoopAsync(_cts.Token);
            Stop();
            await frames.ConfigureAwait(true);
            return why;
        }
        catch (Exception ex) when (ex is WebSocketException or OperationCanceledException or IOException or ObjectDisposedException or
                                       HttpRequestException or System.Security.Authentication.AuthenticationException or JsonException)
        {
            bool early = _mode.Length == 0 && !_stopped;
            Stop();
            return early ? Texte.T("keine_verbindung", host: _ziel.Shown) : Texte.T("beendet");
        }
        finally
        {
            Stop();
            await Task.WhenAny(_ending, Task.Delay(TimeSpan.FromSeconds(4)));
            _ws.Dispose();
        }
    }

    /// <summary>Alles hier zu (Fenster geschlossen, „Beenden“, Ende der Hilfe).</summary>
    public void Stop()
    {
        if (_stopped)
        {
            return;
        }

        _stopped = true;
        _steuern = false;
        _cts.Cancel();
        foreach (Form f in _marks)
        {
            f.Close();
        }

        _marks.Clear();
        // erst „ende“ sagen, dann abbrechen: ein abgebrochenes Lesen schließt die Verbindung sofort
        _ending = _ws.State == WebSocketState.Open ? TellEndAsync() : Task.CompletedTask;
        _ = _ending.ContinueWith(_ => _cts.Cancel(), TaskScheduler.Default);
    }

    private ViewQuestion Question() => new(
        Texte.T("frage_fenster"), Texte.T("frage_titel"), Texte.T("frage", _helper, _ziel.Shown), Texte.T("frage_mehr"),
        View: true, Allow: true, ViewLabel: Texte.T("ansehen"), DenyLabel: Texte.T("ablehnen"), AllowLabel: Texte.T("erlauben"),
        Countdown: Texte.Raw("countdown"));

    private void ShowFrame()
    {
        _bar = new ViewBar(_screen, BarText(), Texte.T("rahmen"), BarText(), Texte.T("beenden"));
        _bar.EndRequested += (_, _) =>
        {
            Stop();
            _status.Close();
        };
        _marks = Sicht.ShowFrame(_screen, Texte.T("rahmen"), _bar);
        _status.Hide();
    }

    private string BarText() => _steuern ? Texte.T("leiste_aktiv", _helper)
        : _mode == "control" ? Texte.T("leiste_erlaubt", _helper) : Texte.T("leiste_ansehen", _helper);

    private async Task TellEndAsync()
    {
        try
        {
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(3));
            await _send.WaitAsync(cts.Token);
            try
            {
                byte[] data = JsonSerializer.SerializeToUtf8Bytes(new Dictionary<string, string> { ["typ"] = "ende" });
                await _ws.SendAsync(data, WebSocketMessageType.Text, true, cts.Token);
                await _ws.CloseOutputAsync(WebSocketCloseStatus.NormalClosure, "", cts.Token);
            }
            finally
            {
                _send.Release();
            }
        }
        catch (Exception ex) when (ex is WebSocketException or OperationCanceledException or ObjectDisposedException)
        {
            // weg: das Panel sieht die Verbindung ohnehin enden
        }
    }

    private async Task CloseAsync()
    {
        try
        {
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(3));
            await _ws.CloseOutputAsync(WebSocketCloseStatus.NormalClosure, "", cts.Token);
        }
        catch (Exception ex) when (ex is WebSocketException or OperationCanceledException)
        {
        }
    }

    private async Task SendAsync(Dictionary<string, string> message)
    {
        byte[] data = JsonSerializer.SerializeToUtf8Bytes(message);
        await _send.WaitAsync(_cts.Token);
        try
        {
            await _ws.SendAsync(data, WebSocketMessageType.Text, true, _cts.Token);
        }
        finally
        {
            _send.Release();
        }
    }

    private async Task SendFrameAsync(byte[] jpeg, CancellationToken ct)
    {
        await _send.WaitAsync(ct);
        try
        {
            await _ws.SendAsync(jpeg, WebSocketMessageType.Binary, true, ct);
        }
        finally
        {
            _send.Release();
        }
    }

    /// <summary>Das Bild des Hauptbildschirms, höchstens viermal je Sekunde; ein zu großes wird kleiner gerechnet.</summary>
    private async Task FrameLoopAsync(CancellationToken ct)
    {
        byte[]? last = null;
        DateTime sent = DateTime.MinValue;
        while (!ct.IsCancellationRequested)
        {
            try
            {
                byte[]? jpeg = await Task.Run(Picture, ct);
                if (_stopped)
                {
                    return;
                }

                if (jpeg is not null && (last is null || !jpeg.AsSpan().SequenceEqual(last) || DateTime.UtcNow - sent > KeepAlive))
                {
                    await SendFrameAsync(jpeg, ct);
                    last = jpeg;
                    sent = DateTime.UtcNow;
                }

                await Task.Delay(Sicht.FrameGap, ct);
            }
            catch (OperationCanceledException)
            {
                return;
            }
            catch (Exception ex) when (ex is WebSocketException or ObjectDisposedException)
            {
                return;
            }
            catch (Exception ex) when (ex is System.Runtime.InteropServices.ExternalException or InvalidOperationException or ArgumentException)
            {
                // gesperrter Bildschirm oder Wechsel der Anzeige: gleich noch einmal
                await Task.Delay(TimeSpan.FromSeconds(1), CancellationToken.None);
            }
        }
    }

    private byte[]? Picture()
    {
        (byte[] jpeg, _, _) = Sicht.Capture(_screen);
        if (jpeg.Length <= MaxFrame)
        {
            return jpeg;
        }

        (jpeg, _, _) = Sicht.Capture(_screen, 1280, 40L);
        return jpeg.Length <= MaxFrame ? jpeg : null;
    }

    /// <summary>Nachrichten vom Panel bis zum Ende; gibt den Satz für das Fenster zurück.</summary>
    private async Task<string> ReceiveLoopAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            JsonElement? got = await ReceiveJsonAsync(null);
            if (got is not { } m)
            {
                return Texte.T("beendet");
            }

            switch (Str(m, "typ"))
            {
                case "modus":
                    bool an = _mode == "control" && m.TryGetProperty("steuern", out JsonElement s) && s.ValueKind == JsonValueKind.True;
                    if (an != _steuern)
                    {
                        _steuern = an;
                        _bar?.Say(BarText(), BarText());
                    }

                    break;
                case "eingabe" when _mode == "control" && _steuern:
                    foreach (ViewEvent e in Events(m))
                    {
                        if (!_steuern || _stopped)
                        {
                            break;
                        }

                        Sicht.Apply(_screen, e);
                    }

                    break;
                case "stand" when Str(m, "stand") == "zu":
                case "fehler":
                    return Texte.T("beendet");
            }
        }

        return Texte.T("beendet");
    }

    /// <summary>Die Eingaben einer Nachricht, jede noch einmal geprüft (wie fernsicht.clean_events); Unbekanntes fällt weg.</summary>
    internal static List<ViewEvent> Events(JsonElement m)
    {
        var out_ = new List<ViewEvent>();
        if (!m.TryGetProperty("events", out JsonElement list) || list.ValueKind != JsonValueKind.Array)
        {
            return out_;
        }

        foreach (JsonElement e in list.EnumerateArray().Take(MaxEvents))
        {
            if (e.ValueKind != JsonValueKind.Object)
            {
                continue;
            }

            switch (Str(e, "t"))
            {
                case "move" or "click" when Num(e, "x") is { } x and >= 0 and <= 1 && Num(e, "y") is { } y and >= 0 and <= 1:
                    string b = e.TryGetProperty("b", out _) ? Str(e, "b") : "left";
                    if (Str(e, "t") == "click" && !Sicht.Buttons.Contains(b))
                    {
                        continue;
                    }

                    out_.Add(new ViewEvent(Str(e, "t"), x, y, b, 0, "", ""));
                    break;
                case "scroll" when Num(e, "dy") is { } dy && dy == Math.Floor(dy) && dy is >= -10 and <= 10 and not 0:
                    out_.Add(new ViewEvent("scroll", 0, 0, "left", (int)dy, "", ""));
                    break;
                case "key" when Sicht.ViewKeys.ContainsKey(Str(e, "k")):
                    out_.Add(new ViewEvent("key", 0, 0, "left", 0, Str(e, "k"), ""));
                    break;
                case "text":
                    string text = new(Str(e, "s").Where(c => c == '\n' || !char.IsControl(c)).Take(Sicht.TextMax).ToArray());
                    if (text.Length > 0)
                    {
                        out_.Add(new ViewEvent("text", 0, 0, "left", 0, "", text));
                    }

                    break;
            }
        }

        return out_;
    }

    private async Task<JsonElement?> ReceiveJsonAsync(TimeSpan? within)
    {
        using var cts = CancellationTokenSource.CreateLinkedTokenSource(_cts.Token);
        if (within is { } w)
        {
            cts.CancelAfter(w);
        }

        var buffer = new byte[4096];
        while (true)
        {
            using var ms = new MemoryStream();
            WebSocketReceiveResult r;
            do
            {
                r = await _ws.ReceiveAsync(buffer, cts.Token);
                if (r.MessageType == WebSocketMessageType.Close)
                {
                    return null;
                }

                ms.Write(buffer, 0, r.Count);
                if (ms.Length > MaxMessage)
                {
                    return null;   // zu groß: das ist nicht das Panel
                }
            }
            while (!r.EndOfMessage);

            if (r.MessageType != WebSocketMessageType.Text)
            {
                continue;          // vom Panel kommen keine Bilder
            }

            try
            {
                using JsonDocument doc = JsonDocument.Parse(ms.ToArray());
                if (doc.RootElement.ValueKind == JsonValueKind.Object)
                {
                    return doc.RootElement.Clone();
                }
            }
            catch (JsonException)
            {
                // kein JSON: übergehen
            }
        }
    }

    private static string Str(JsonElement e, string name) =>
        e.TryGetProperty(name, out JsonElement v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? "" : "";

    private static double? Num(JsonElement e, string name) =>
        e.TryGetProperty(name, out JsonElement v) && v.ValueKind == JsonValueKind.Number && v.TryGetDouble(out double d) ? d : null;

    /// <summary>Nur druckbare Zeichen, höchstens <paramref name="max"/> (der Name des Helfers kommt vom Panel).</summary>
    private static string Plain(string s, int max)
    {
        var sb = new StringBuilder();
        foreach (char c in s)
        {
            if (sb.Length >= max)
            {
                break;
            }

            if (!char.IsControl(c) && c is not ('‪' or '‫' or '‬' or '‭' or '‮' or '⁦' or '⁧' or '⁨' or '⁩'))
            {
                sb.Append(c);
            }
        }

        return sb.ToString().Trim();
    }
}
