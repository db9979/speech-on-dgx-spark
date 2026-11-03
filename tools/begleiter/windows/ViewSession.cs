using static SparkBegleiter.NativeMethods;

namespace SparkBegleiter;

/// <summary>
/// Rechner fernsteuern, Stufe 2 (fernsicht.py): eine Sitzung „Bildschirm zeigen und bedienen“. Erst fragt der Begleiter
/// hier (Ablehnen / Nur ansehen / Erlauben); dann zeigt er einen roten Rahmen und eine Leiste mit „Beenden“, schickt
/// höchstens vier Bilder je Sekunde vom Hauptbildschirm (JPEG, nur im Speicher) und führt – nur nach „Erlauben“ –
/// Klicks, Mausbewegungen, Scrollen, Tasten aus einer festen Liste und getippten Text aus. Die Windows-Taste,
/// Alt+Tab und Strg+Alt+Entf gibt es nicht. Bild, Eingaben, Rahmen, Leiste und Frage kommen aus dem gemeinsamen Kern
/// (<see cref="Sicht"/>, Sicht.cs), den auch das Programm SparkHilfe der Spontanhilfe nutzt; hier läuft nur der Weg zum
/// Panel (Long-Poll) und Stufe 3.
/// Stufe 3 (bedienen.py, <see cref="Operate"/>): niemand schaut zu; der Spark schickt einen Schritt nach dem anderen
/// ("step"), jeder wird hier mit markiertem Ziel gezeigt und erst nach „Erlauben“ ausgeführt (<see cref="StepForm"/>).
/// </summary>
internal sealed class ViewSession : IDisposable
{
    private const string Title = "Spark-Begleiter – Bildschirm wird gezeigt";
    private static readonly TimeSpan KeepAlive = TimeSpan.FromSeconds(5);

    private readonly string _base;
    private readonly string _key;
    private readonly CancellationTokenSource _cts = new();
    private readonly Action<ViewSession> _ended;
    private readonly Rectangle _screen;
    private List<Form> _marks = new();
    private bool _stopped;

    private ViewSession(string baseUrl, string key, ViewAsk ask, bool control, Action<ViewSession> ended)
    {
        _base = baseUrl;
        _key = key;
        Id = ask.Id;
        Control = control;
        Operate = ask.Operate;
        Order = ask.Task;
        _ended = ended;
        _screen = Sicht.MainScreen();
    }

    public string Id { get; }

    /// <summary>Bedienen erlaubt (sonst nur ansehen).</summary>
    public bool Control { get; }

    /// <summary>Stufe 3: der Spark bedient (Schritte statt Eingaben aus dem Panel).</summary>
    public bool Operate { get; }

    /// <summary>Stufe 3: der Auftrag in den Worten der Person (nur zum Anzeigen).</summary>
    public string Order { get; }

    /// <summary>Fragt hier am Rechner; startet die Sitzung nur nach „Nur ansehen“ oder „Erlauben“.</summary>
    public static async Task<ViewSession?> AskAsync(string baseUrl, string key, ViewAsk ask, Action<ViewSession> ended)
    {
        string mode;
        using (var form = new ViewAskForm(Question(ask)))
        {
            mode = await form.AskAsync();
        }

        string state = await SparkClient.ViewAnswerAsync(baseUrl, key, ask.Id, mode, CancellationToken.None);
        if (state is not ("view" or "control"))
        {
            return null;
        }

        var session = new ViewSession(baseUrl, key, ask, state == "control", ended);
        session.Start();
        return session;
    }

    /// <summary>Die Frage dieses Begleiters (Ansehen, Bedienen, Stufe 3 bedienen, einmal hinsehen).</summary>
    private static ViewQuestion Question(ViewAsk ask)
    {
        bool control = ask.Control;
        string question = ask.Operate
            ? "Spark möchte an diesem Rechner deinen Auftrag Schritt für Schritt erledigen: „" + ask.Task + "“"
            : ask.Look
            ? "Spark möchte einmal auf diesen Bildschirm sehen, um deine Frage zu beantworten: „" + ask.Task + "“"
            : control
                ? "Dein Profil möchte diesen Bildschirm vom Handy oder Panel aus ansehen und bedienen."
                : "Dein Profil möchte diesen Bildschirm vom Handy oder Panel aus ansehen.";
        string detail = ask.Operate
            ? "Nur, wenn du das gerade selbst gesagt hast. Jeden Schritt zeigt der Begleiter mit markiertem Ziel und fragt; " +
              "„Stopp“ beendet es sofort. Der Spark sieht dafür den Bildschirm, gespeichert wird nichts."
            : ask.Look
            ? "Nur, wenn du das gerade selbst gefragt hast. Der Spark nimmt ein einziges Bild auf und beschreibt es dir; " +
              "gespeichert wird nichts, auch nicht im Verlauf."
            : "Nur, wenn du das gerade selbst angestoßen hast. Solange es läuft, siehst du einen roten Rahmen und oben „Beenden“. " +
              "Es wird nichts aufgezeichnet.";
        string title = ask.Operate ? "Spark den Rechner bedienen lassen?" : ask.Look ? "Spark hinsehen lassen?" : "Bildschirm zeigen?";
        return new ViewQuestion("Spark-Begleiter – Bildschirm zeigen?", title, question, detail, View: !ask.Operate, Allow: control,
                                ViewLabel: ask.Look ? "Erlauben" : "Nur ansehen");
    }

    private void Start()
    {
        string text = Operate
            ? "Spark bedient deinen Rechner: " + (Order.Length > 60 ? Order[..59] + "…" : Order)
            : Control ? "Spark: dein Bildschirm wird gezeigt und bedient" : "Spark: dein Bildschirm wird gezeigt";
        var bar = new ViewBar(_screen, text, Title, Control ? "Bildschirm wird gezeigt und bedient" : "Bildschirm wird gezeigt");
        bar.EndRequested += (_, _) => Stop(tell: true);
        _marks = Sicht.ShowFrame(_screen, Title, bar);

        _ = FrameLoopAsync(_cts.Token);
        if (Control)
        {
            _ = InputLoopAsync(_cts.Token);
        }
    }

    /// <summary>Beendet die Sitzung hier (Leiste, Menü, Notaus, Teil aus); <paramref name="tell"/>: dem Spark sagen.</summary>
    public void Stop(bool tell)
    {
        if (_stopped)
        {
            return;
        }

        _stopped = true;
        _cts.Cancel();
        foreach (Form f in _marks)
        {
            f.Close();
        }

        _marks.Clear();
        if (tell)
        {
            _ = TellEndAsync();
        }

        _ended(this);
    }

    private async Task TellEndAsync()
    {
        try
        {
            await SparkClient.ViewEndAsync(_base, _key, Id, CancellationToken.None);
        }
        catch (SparkException)
        {
            // Spark weg: dort endet die Sitzung von selbst, sobald keine Bilder mehr kommen.
        }
    }

    private async Task FrameLoopAsync(CancellationToken ct)
    {
        byte[]? last = null;
        DateTime sent = DateTime.MinValue;
        int errors = 0;
        while (!ct.IsCancellationRequested)
        {
            try
            {
                (string app, string exe) = FrontApp();
                (byte[] jpeg, int w, int h) = await Task.Run(() => Sicht.Capture(_screen), ct);
                bool same = last is not null && jpeg.AsSpan().SequenceEqual(last);
                if (!same || DateTime.UtcNow - sent > KeepAlive)
                {
                    string state = await SparkClient.ViewFrameAsync(_base, _key, Id, jpeg, w, h, app, exe, ct);
                    last = jpeg;
                    sent = DateTime.UtcNow;
                    errors = 0;
                    if (state is not ("view" or "control"))
                    {
                        Stop(tell: false);
                        return;
                    }
                }

                await Task.Delay(Sicht.FrameGap, ct);
            }
            catch (OperationCanceledException)
            {
                return;
            }
            catch (Exception ex) when (ex is SparkException or ExternalException or InvalidOperationException or ArgumentException)
            {
                // 403/404: Teil aus oder Sitzung weg; sonst dreimal neu versuchen, dann aufhören
                if (ex is SparkException { Status: 401 or 403 or 404 or 503 } || ++errors >= 3)
                {
                    Stop(tell: false);
                    return;
                }

                await Task.Delay(TimeSpan.FromSeconds(1), CancellationToken.None);
            }
        }
    }

    private async Task InputLoopAsync(CancellationToken ct)
    {
        int errors = 0;
        while (!ct.IsCancellationRequested)
        {
            try
            {
                (string state, IReadOnlyList<ViewEvent> events) = await SparkClient.ViewInputAsync(_base, _key, Id, ct);
                errors = 0;
                if (state != "control")
                {
                    if (state != "view")
                    {
                        Stop(tell: false);
                    }

                    return;
                }

                foreach (ViewEvent e in events)
                {
                    if (Operate && e.Kind == "step")
                    {
                        await StepAsync(e, ct);
                    }
                    else if (!Operate)
                    {
                        Sicht.Apply(_screen, e);
                    }
                }
            }
            catch (OperationCanceledException)
            {
                return;
            }
            catch (SparkException ex)
            {
                if (ex.Status is 401 or 403 or 404 or 503 || ++errors >= 3)
                {
                    Stop(tell: false);
                    return;
                }

                await Task.Delay(TimeSpan.FromSeconds(1), CancellationToken.None);
            }
        }
    }

    /// <summary>Das Programm vorn: Name (Dateibeschreibung oder Prozessname) und Pfad; leer, wenn nicht lesbar.</summary>
    private static (string App, string Exe) FrontApp()
    {
        IntPtr h = GetForegroundWindow();
        if (h == IntPtr.Zero)
        {
            return ("", "");
        }

        _ = GetWindowThreadProcessId(h, out uint pid);
        try
        {
            using var p = System.Diagnostics.Process.GetProcessById((int)pid);
            string exe = "";
            string name = p.ProcessName;
            try
            {
                exe = p.MainModule?.FileName ?? "";
                string desc = exe.Length > 0 ? System.Diagnostics.FileVersionInfo.GetVersionInfo(exe).FileDescription ?? "" : "";
                if (desc.Trim().Length > 0)
                {
                    name = desc.Trim();
                }
            }
            catch (Exception ex) when (ex is System.ComponentModel.Win32Exception or InvalidOperationException or FileNotFoundException)
            {
                // ein Programm mit Administratorrechten: nur der Prozessname
            }

            return (name, exe);
        }
        catch (ArgumentException)
        {
            return ("", "");
        }
    }

    /// <summary>Stufe 3: einen Schritt zeigen (Ziel markiert), fragen, nach „Erlauben“ ausführen, Antwort melden.</summary>
    private async Task StepAsync(ViewEvent e, CancellationToken ct)
    {
        IntPtr before = GetForegroundWindow();
        Point? target = e.Step is "click" or "double" or "right" ? Sicht.PointOf(_screen, e.X, e.Y) : null;
        ViewMarker? marker = target is { } t ? new ViewMarker(t) : null;
        if (marker is not null)
        {
            marker.Show();
            Sicht.Hide(marker);
        }

        string answer;
        using (var form = new StepForm(e, _screen, target))
        {
            _marks.Add(form);
            answer = await form.AskAsync();
            _marks.Remove(form);
        }

        marker?.Close();
        marker?.Dispose();
        if (_stopped)
        {
            return;
        }

        string? error = null;
        if (answer == "done" && e.Step != "ask")
        {
            await ActDo.RestoreAsync(before);
            try
            {
                Execute(e);
            }
            catch (InvalidOperationException ex)
            {
                answer = "failed";
                error = ex.Message;
            }

            await Task.Delay(300, CancellationToken.None);
        }

        try
        {
            await SparkClient.ViewStepAsync(_base, _key, Id, e.N, answer, error, ct);
        }
        catch (SparkException)
        {
            Stop(tell: true);
            return;
        }

        if (answer == "stop")
        {
            Stop(tell: true);
        }
    }

    /// <summary>Stufe 3: der erlaubte Schritt; Unbekanntes wird nicht ausgeführt.</summary>
    private void Execute(ViewEvent e)
    {
        switch (e.Step)
        {
            case "click" or "double" or "right" when Sicht.PointOf(_screen, e.X, e.Y) is { } p:
                _ = SetCursorPos(p.X, p.Y);
                Sicht.Click(e.Step == "click" ? "left" : e.Step);
                break;
            case "scroll" when e.Dy is >= -10 and <= 10 and not 0:
                Sicht.Mouse(MOUSEEVENTF_WHEEL, e.Dy * 120);
                break;
            case "key" when Sicht.ViewKeys.TryGetValue(e.Key, out ushort[]? keys):
                Sicht.Chord(keys);
                break;
            case "type" when e.Text.Length is > 0 and <= Sicht.TextMax:
                Sicht.Type(e.Text);
                break;
            default:
                throw new InvalidOperationException("Diesen Schritt kennt der Begleiter nicht.");
        }
    }

    public void Dispose()
    {
        Stop(tell: false);
        _cts.Dispose();
    }
}
