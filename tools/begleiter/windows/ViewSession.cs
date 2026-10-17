using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using static SparkBegleiter.NativeMethods;

namespace SparkBegleiter;

/// <summary>
/// Rechner fernsteuern, Stufe 2 (fernsicht.py): eine Sitzung „Bildschirm zeigen und bedienen“. Erst fragt der Begleiter
/// hier (Ablehnen / Nur ansehen / Erlauben); dann zeigt er einen roten Rahmen und eine Leiste mit „Beenden“, schickt
/// höchstens vier Bilder je Sekunde vom Hauptbildschirm (JPEG, nur im Speicher) und führt – nur nach „Erlauben“ –
/// Klicks, Mausbewegungen, Scrollen, Tasten aus einer festen Liste und getippten Text aus. Die Windows-Taste,
/// Alt+Tab und Strg+Alt+Entf gibt es nicht.
/// Stufe 3 (bedienen.py, <see cref="Operate"/>): niemand schaut zu; der Spark schickt einen Schritt nach dem anderen
/// ("step"), jeder wird hier mit markiertem Ziel gezeigt und erst nach „Erlauben“ ausgeführt (<see cref="StepForm"/>).
/// </summary>
internal sealed class ViewSession : IDisposable
{
    private const int MaxWidth = 1600;
    private const long Quality = 60L;
    private static readonly TimeSpan FrameGap = TimeSpan.FromMilliseconds(250);
    private static readonly TimeSpan KeepAlive = TimeSpan.FromSeconds(5);

    private readonly string _base;
    private readonly string _key;
    private readonly CancellationTokenSource _cts = new();
    private readonly Action<ViewSession> _ended;
    private readonly Rectangle _screen;
    private readonly List<Form> _marks = new();
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
        _screen = Screen.PrimaryScreen?.Bounds ?? SystemInformation.VirtualScreen;
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
        using (var form = new ViewAskForm(ask))
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

    private void Start()
    {
        int t = Draw.Scale(4, Dwm.DpiAt(_screen.Location));
        Rectangle s = _screen;
        foreach (Rectangle r in new[]
                 {
                     new Rectangle(s.Left, s.Top, s.Width, t), new Rectangle(s.Left, s.Bottom - t, s.Width, t),
                     new Rectangle(s.Left, s.Top, t, s.Height), new Rectangle(s.Right - t, s.Top, t, s.Height),
                 })
        {
            var edge = new ViewEdge(r);
            _marks.Add(edge);
            edge.Show();
            Hide(edge);
        }

        var bar = new ViewBar(s, Control, Operate ? Order : null);
        bar.EndRequested += (_, _) => Stop(tell: true);
        _marks.Add(bar);
        bar.Show();
        Hide(bar);

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

    /// <summary>Eigene Fenster nicht mit aufnehmen (der Spark und das Panel sehen nur den Rechner selbst).</summary>
    internal static void Hide(Form f) => _ = SetWindowDisplayAffinity(f.Handle, WDA_EXCLUDEFROMCAPTURE);

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
                (byte[] jpeg, int w, int h) = await Task.Run(Capture, ct);
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

                await Task.Delay(FrameGap, ct);
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

    /// <summary>Der Hauptbildschirm als JPEG, höchstens <see cref="MaxWidth"/> Pixel breit.</summary>
    private (byte[] Jpeg, int Width, int Height) Capture()
    {
        Rectangle s = _screen;
        using var full = new Bitmap(s.Width, s.Height, PixelFormat.Format24bppRgb);
        using (Graphics g = Graphics.FromImage(full))
        {
            g.CopyFromScreen(s.Left, s.Top, 0, 0, s.Size, CopyPixelOperation.SourceCopy);
        }

        Bitmap shown = full;
        if (s.Width > MaxWidth)
        {
            int h = (int)Math.Round(s.Height * (double)MaxWidth / s.Width);
            shown = new Bitmap(MaxWidth, h, PixelFormat.Format24bppRgb);
            using Graphics g = Graphics.FromImage(shown);
            g.InterpolationMode = InterpolationMode.HighQualityBilinear;
            g.DrawImage(full, new Rectangle(0, 0, MaxWidth, h));
        }

        try
        {
            ImageCodecInfo jpeg = ImageCodecInfo.GetImageEncoders().First(c => c.FormatID == ImageFormat.Jpeg.Guid);
            using var args = new EncoderParameters(1);
            args.Param[0] = new EncoderParameter(System.Drawing.Imaging.Encoder.Quality, Quality);
            using var ms = new MemoryStream();
            shown.Save(ms, jpeg, args);
            return (ms.ToArray(), shown.Width, shown.Height);
        }
        finally
        {
            if (!ReferenceEquals(shown, full))
            {
                shown.Dispose();
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
                        Apply(e);
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
        Point? target = e.Step is "click" or "double" or "right" ? Point(e) : null;
        ViewMarker? marker = target is { } t ? new ViewMarker(t) : null;
        if (marker is not null)
        {
            marker.Show();
            Hide(marker);
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
            case "click" or "double" or "right" when Point(e) is { } p:
                _ = SetCursorPos(p.X, p.Y);
                Click(e.Step == "click" ? "left" : e.Step);
                break;
            case "scroll" when e.Dy is >= -10 and <= 10 and not 0:
                Mouse(MOUSEEVENTF_WHEEL, e.Dy * 120);
                break;
            case "key" when ActDo.ViewKeys.TryGetValue(e.Key, out ushort[]? keys):
                ActDo.Chord(keys);
                break;
            case "type" when e.Text.Length is > 0 and <= 200:
                ActDo.Type(e.Text);
                break;
            default:
                throw new InvalidOperationException("Diesen Schritt kennt der Begleiter nicht.");
        }
    }

    /// <summary>Eine Eingabe ausführen; Unbekanntes und Punkte außerhalb des Bildes werden übergangen.</summary>
    private void Apply(ViewEvent e)
    {
        try
        {
            switch (e.Kind)
            {
                case "move" when Point(e) is { } p:
                    _ = SetCursorPos(p.X, p.Y);
                    break;
                case "click" when Point(e) is { } p:
                    _ = SetCursorPos(p.X, p.Y);
                    Click(e.Button);
                    break;
                case "scroll" when e.Dy is >= -10 and <= 10 and not 0:
                    Mouse(MOUSEEVENTF_WHEEL, e.Dy * 120);
                    break;
                case "key" when ActDo.ViewKeys.TryGetValue(e.Key, out ushort[]? keys):
                    ActDo.Chord(keys);
                    break;
                case "text" when e.Text.Length is > 0 and <= 200:
                    ActDo.Type(e.Text);
                    break;
            }
        }
        catch (InvalidOperationException)
        {
            // Windows nahm die Eingabe nicht an (Programm vorn als Administrator): nächste Eingabe
        }
    }

    private Point? Point(ViewEvent e)
    {
        if (e.X is < 0 or > 1 || e.Y is < 0 or > 1)
        {
            return null;
        }

        return new Point(_screen.Left + (int)Math.Round(e.X * (_screen.Width - 1)), _screen.Top + (int)Math.Round(e.Y * (_screen.Height - 1)));
    }

    private static void Click(string button)
    {
        (uint down, uint up) = button == "right" ? (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP) : (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP);
        int times = button == "double" ? 2 : 1;
        for (int i = 0; i < times; i++)
        {
            Mouse(down, 0);
            Mouse(up, 0);
        }
    }

    private static void Mouse(uint flags, int data)
    {
        var input = new[]
        {
            new INPUT { type = INPUT_MOUSE, u = new InputUnion { mi = new MOUSEINPUT { dwFlags = flags, mouseData = unchecked((uint)data) } } },
        };
        if (SendInput(1, input, Marshal.SizeOf<INPUT>()) == 0)
        {
            throw new InvalidOperationException("Maus nicht angenommen.");
        }
    }

    public void Dispose()
    {
        Stop(tell: false);
        _cts.Dispose();
    }
}

/// <summary>Ein Streifen des roten Rahmens: immer vorn, klickt durch, nimmt nie den Fokus.</summary>
internal sealed class ViewEdge : Form
{
    public ViewEdge(Rectangle bounds)
    {
        FormBorderStyle = FormBorderStyle.None;
        ShowInTaskbar = false;
        TopMost = true;
        StartPosition = FormStartPosition.Manual;
        BackColor = Palette.Hex(0xE5484D);
        Bounds = bounds;
        Text = "Spark-Begleiter – Bildschirm wird gezeigt";
    }

    protected override bool ShowWithoutActivation => true;

    protected override CreateParams CreateParams
    {
        get
        {
            CreateParams cp = base.CreateParams;
            cp.ExStyle |= WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST | WS_EX_LAYERED | WS_EX_TRANSPARENT;
            return cp;
        }
    }

    protected override void OnHandleCreated(EventArgs e)
    {
        base.OnHandleCreated(e);
        Opacity = 0.9;
    }
}

/// <summary>Die Leiste oben in der Mitte: was gerade geschieht und „Beenden“.</summary>
internal sealed class ViewBar : Form
{
    private readonly Label _text = new() { AutoSize = true, ForeColor = Color.White, BackColor = Color.Transparent };
    private readonly Button _end = new() { Text = "Beenden", AutoSize = true, FlatStyle = FlatStyle.Flat, ForeColor = Color.White };

    /// <param name="task">Stufe 3: der Auftrag, den der Spark gerade erledigt; sonst <c>null</c>.</param>
    public ViewBar(Rectangle screen, bool control, string? task = null)
    {
        FormBorderStyle = FormBorderStyle.None;
        ShowInTaskbar = false;
        TopMost = true;
        StartPosition = FormStartPosition.Manual;
        BackColor = Palette.Hex(0xB4232A);
        Text = "Spark-Begleiter – Bildschirm wird gezeigt";
        AccessibleName = control ? "Bildschirm wird gezeigt und bedient" : "Bildschirm wird gezeigt";
        _text.Text = task is not null
            ? "Spark bedient deinen Rechner: " + (task.Length > 60 ? task[..59] + "…" : task)
            : control ? "Spark: dein Bildschirm wird gezeigt und bedient" : "Spark: dein Bildschirm wird gezeigt";
        _text.Font = new Font("Segoe UI", 10f, FontStyle.Bold);
        _end.FlatAppearance.BorderColor = Color.White;
        _end.Click += (_, _) => EndRequested?.Invoke(this, EventArgs.Empty);
        Controls.Add(_text);
        Controls.Add(_end);
        int dpi = Dwm.DpiAt(screen.Location);
        int pad = Draw.Scale(10, dpi);
        Size text = _text.GetPreferredSize(Size.Empty);
        Size end = _end.GetPreferredSize(Size.Empty);
        int h = Math.Max(text.Height, end.Height) + (2 * pad);
        int w = text.Width + end.Width + (3 * pad);
        _text.Location = new Point(pad, (h - text.Height) / 2);
        _end.Location = new Point(pad + text.Width + pad, (h - end.Height) / 2);
        Bounds = new Rectangle(screen.Left + ((screen.Width - w) / 2), screen.Top + Draw.Scale(8, dpi), w, h);
    }

    /// <summary>„Beenden“ geklickt.</summary>
    public event EventHandler? EndRequested;

    protected override bool ShowWithoutActivation => true;

    protected override CreateParams CreateParams
    {
        get
        {
            CreateParams cp = base.CreateParams;
            cp.ExStyle |= WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST;
            return cp;
        }
    }
}

/// <summary>Die Frage hier am Rechner: Ablehnen (vorgewählt), Nur ansehen, Erlauben (nur wenn auch bedienen gefragt war).</summary>
internal sealed class ViewAskForm : ThemedForm
{
    private const int TimeoutSeconds = 60;

    private readonly TLabel _question = new(TextRole.Normal);
    private readonly TLabel _detail = new(TextRole.SmallMuted);
    private readonly TLabel _countdown = new(TextRole.SmallMuted);
    private readonly SparkButton _deny = new(ButtonKind.Secondary, "Ablehnen");
    private readonly SparkButton _view = new(ButtonKind.Secondary, "Nur ansehen");
    private readonly SparkButton _allow = new(ButtonKind.Primary, "Erlauben");
    private readonly bool _control;
    private readonly bool _operate;
    private readonly System.Windows.Forms.Timer _timer = new() { Interval = 1000 };
    private readonly DateTime _deadline = DateTime.UtcNow.AddSeconds(TimeoutSeconds);
    private Rectangle _face;
    private Rectangle _title;
    private string _mode = "no";

    public ViewAskForm(ViewAsk ask)
    {
        bool control = ask.Control;
        _control = control;
        _operate = ask.Operate;
        Text = "Spark-Begleiter – Bildschirm zeigen?";
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        MinimizeBox = false;
        TopMost = true;
        ShowInTaskbar = true;
        StartPosition = FormStartPosition.CenterScreen;
        KeyPreview = true;
        _question.Text = _operate
            ? "Spark möchte an diesem Rechner deinen Auftrag Schritt für Schritt erledigen: „" + ask.Task + "“"
            : control
                ? "Dein Profil möchte diesen Bildschirm vom Handy oder Panel aus ansehen und bedienen."
                : "Dein Profil möchte diesen Bildschirm vom Handy oder Panel aus ansehen.";
        _detail.Text = _operate
            ? "Nur, wenn du das gerade selbst gesagt hast. Jeden Schritt zeigt der Begleiter mit markiertem Ziel und fragt; " +
              "„Stopp“ beendet es sofort. Der Spark sieht dafür den Bildschirm, gespeichert wird nichts."
            : "Nur, wenn du das gerade selbst angestoßen hast. Solange es läuft, siehst du einen roten Rahmen und oben „Beenden“. " +
              "Es wird nichts aufgezeichnet.";
        Controls.AddRange(new Control[] { _question, _detail, _countdown, _deny });
        if (!_operate)
        {
            Controls.Add(_view);
        }
        if (control)
        {
            Controls.Add(_allow);
        }

        _deny.TabIndex = 0; // Ablehnen zuerst: Enter allein gibt nichts frei
        _view.TabIndex = 1;
        _allow.TabIndex = 2;
        _deny.Click += (_, _) => Close();
        _view.Click += (_, _) => Pick("view");
        _allow.Click += (_, _) => Pick("control");
        AcceptButton = _deny;
        CancelButton = _deny;
        _timer.Tick += (_, _) => UpdateCountdown();
        UpdateCountdown();
    }

    private void Pick(string mode)
    {
        _mode = mode;
        Close();
    }

    /// <summary>Zeigt die Frage und wartet auf die Antwort (ohne Antwort nach 60 s: „no“).</summary>
    public Task<string> AskAsync()
    {
        var done = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);
        FormClosed += (_, _) => done.TrySetResult(_mode);
        Show();
        Activate();
        _ = SetForegroundWindow(Handle);
        _deny.Focus();
        _timer.Start();
        return done.Task;
    }

    private void UpdateCountdown()
    {
        int left = (int)Math.Ceiling((_deadline - DateTime.UtcNow).TotalSeconds);
        if (left <= 0)
        {
            _timer.Stop();
            Close();
            return;
        }

        _countdown.Text = $"Ohne Antwort gilt in {left} s „Ablehnen“.";
        if (IsHandleCreated)
        {
            LayoutContent();
            _countdown.Invalidate();
        }
    }

    protected override void LayoutContent()
    {
        int pad = S(16);
        int w = S(460);
        int inner = w - (2 * pad);
        int y = BarHeight + pad;
        int face = S(36);
        _face = new Rectangle(pad, y, face, face);
        _title = new Rectangle(pad + face + S(10), y, inner - face - S(10), face);
        y += face + S(12);
        y += _question.Fit(pad, y, inner) + S(8);
        y += _detail.Fit(pad, y, inner) + S(10);
        y += _countdown.Fit(pad, y, inner) + S(14);
        int x = w - pad;
        int bh = 0;
        foreach (SparkButton b in _operate ? new[] { _allow, _deny } : _control ? new[] { _allow, _view, _deny } : new[] { _view, _deny })
        {
            Size size = b.Preferred();
            x -= size.Width;
            b.Bounds = new Rectangle(x, y, size.Width, size.Height);
            x -= S(8);
            bh = Math.Max(bh, size.Height);
        }

        y += bh + pad;
        ClientSize = new Size(w, y);
    }

    protected override void PaintContent(Graphics g)
    {
        Face.Draw(g, _face, P);
        Draw.Text(g, _operate ? "Spark den Rechner bedienen lassen?" : "Bildschirm zeigen?", F(11f, FontStyle.Bold), _title, P.Fg);
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            _timer.Dispose();
        }

        base.Dispose(disposing);
    }
}
