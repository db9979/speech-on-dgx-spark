using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using static SparkBegleiter.NativeMethods;

namespace SparkBegleiter;

/// <summary>Eine Eingabe aus dem Panel (fernsicht.py prüft sie, das Programm noch einmal). Stufe 3: Kind "step"
/// mit <see cref="Step"/> (click, double, right, scroll, key, type, ask), Nummer, Grund und Warnung.</summary>
internal sealed record ViewEvent(string Kind, double X, double Y, string Button, int Dy, string Key, string Text,
                                 string Step = "", int N = 0, int Of = 0, string Why = "", string Warn = "");

/// <summary>Was die Frage am Rechner sagt und welche Knöpfe sie zeigt (Ablehnen ist immer da und vorgewählt).</summary>
internal sealed record ViewQuestion(string Window, string Title, string Question, string Detail, bool View, bool Allow,
                                    string ViewLabel, string DenyLabel = "Ablehnen", string AllowLabel = "Erlauben",
                                    string Countdown = "Ohne Antwort gilt in {0} s „Ablehnen“.");

/// <summary>
/// Gemeinsamer Kern „Bildschirm zeigen und bedienen“ für den Spark-Begleiter (<see cref="ViewSession"/>, fernsicht.py,
/// über Long-Poll) und das Programm SparkHilfe der Spontanhilfe (tools/sparkhilfe/windows, spontansteuern.py, über WSS):
/// das Bild des Hauptbildschirms (JPEG, nur im Speicher), die Eingaben aus der festen Liste, der rote Rahmen
/// (<see cref="ViewEdge"/>), die Leiste mit „Beenden“ (<see cref="ViewBar"/>) und die Frage (<see cref="ViewAskForm"/>).
/// Die Windows-Taste, Alt+Tab und Strg+Alt+Entf gibt es hier nicht; Fenster mit Schild (UAC) nimmt Windows nicht an.
/// </summary>
internal static class Sicht
{
    public const int MaxWidth = 1600;
    public const long Quality = 60L;

    /// <summary>Höchstens vier Bilder je Sekunde (fernsicht.py, spontansteuern.FPS).</summary>
    public static readonly TimeSpan FrameGap = TimeSpan.FromMilliseconds(250);

    /// <summary>Getippter Text je Eingabe höchstens so lang (fernsicht.TEXT_MAX).</summary>
    public const int TextMax = 200;

    internal const ushort VkBack = 0x08;
    internal const ushort VkTab = 0x09;
    internal const ushort VkReturn = 0x0D;
    internal const ushort VkMenu = 0x12;
    internal const ushort VkEscape = 0x1B;
    internal const ushort VkSpace = 0x20;
    internal const ushort VkPrior = 0x21;
    internal const ushort VkNext = 0x22;
    internal const ushort VkEnd = 0x23;
    internal const ushort VkHome = 0x24;
    internal const ushort VkLeft = 0x25;
    internal const ushort VkUp = 0x26;
    internal const ushort VkRight = 0x27;
    internal const ushort VkDown = 0x28;
    internal const ushort VkDelete = 0x2E;
    internal const ushort VkF = 0x46;
    internal const ushort VkS = 0x53;
    internal const ushort VkY = 0x59;
    internal const ushort VkZ = 0x5A;
    internal const ushort VkF5 = 0x74;
    internal const ushort VkF11 = 0x7A;

    /// <summary>Die Tasten aus <c>fernsicht.KEYS</c> im Panel. Keine Windows-Taste, kein Alt+Tab, kein Strg+Alt+Entf.</summary>
    public static readonly IReadOnlyDictionary<string, ushort[]> ViewKeys = new Dictionary<string, ushort[]>
    {
        ["enter"] = new[] { VkReturn }, ["escape"] = new[] { VkEscape }, ["tab"] = new[] { VkTab },
        ["backspace"] = new[] { VkBack }, ["delete"] = new[] { VkDelete }, ["space"] = new[] { VkSpace },
        ["up"] = new[] { VkUp }, ["down"] = new[] { VkDown }, ["left"] = new[] { VkLeft }, ["right"] = new[] { VkRight },
        ["home"] = new[] { VkHome }, ["end"] = new[] { VkEnd }, ["pageup"] = new[] { VkPrior }, ["pagedown"] = new[] { VkNext },
        ["undo"] = new[] { VK_CONTROL, VkZ }, ["redo"] = new[] { VK_CONTROL, VkY }, ["copy"] = new[] { VK_CONTROL, VK_C },
        ["paste"] = new[] { VK_CONTROL, VK_V }, ["save"] = new[] { VK_CONTROL, VkS }, ["reload"] = new[] { VkF5 },
        ["find"] = new[] { VK_CONTROL, VkF },
    };

    /// <summary>Die Maustasten aus <c>fernsicht.BUTTONS</c>.</summary>
    public static readonly IReadOnlySet<string> Buttons = new HashSet<string> { "left", "right", "double" };

    /// <summary>Der Hauptbildschirm (Bild und Eingaben beziehen sich nur auf ihn).</summary>
    public static Rectangle MainScreen() => Screen.PrimaryScreen?.Bounds ?? SystemInformation.VirtualScreen;

    /// <summary>Eigene Fenster nicht mit aufnehmen (der Spark und das Panel sehen nur den Rechner selbst).</summary>
    public static void Hide(Form f) => _ = SetWindowDisplayAffinity(f.Handle, WDA_EXCLUDEFROMCAPTURE);

    /// <summary>Roter Rahmen um den Bildschirm und die Leiste oben; gibt die Fenster zum späteren Schließen zurück.</summary>
    public static List<Form> ShowFrame(Rectangle s, string title, ViewBar bar)
    {
        var marks = new List<Form>();
        int t = Draw.Scale(4, Dwm.DpiAt(s.Location));
        foreach (Rectangle r in new[]
                 {
                     new Rectangle(s.Left, s.Top, s.Width, t), new Rectangle(s.Left, s.Bottom - t, s.Width, t),
                     new Rectangle(s.Left, s.Top, t, s.Height), new Rectangle(s.Right - t, s.Top, t, s.Height),
                 })
        {
            var edge = new ViewEdge(r, title);
            marks.Add(edge);
            edge.Show();
            Hide(edge);
        }

        marks.Add(bar);
        bar.Show();
        Hide(bar);
        return marks;
    }

    /// <summary>Der Bildschirm als JPEG, höchstens <paramref name="maxWidth"/> Pixel breit.</summary>
    public static (byte[] Jpeg, int Width, int Height) Capture(Rectangle s, int maxWidth = MaxWidth, long quality = Quality)
    {
        using var full = new Bitmap(s.Width, s.Height, PixelFormat.Format24bppRgb);
        using (Graphics g = Graphics.FromImage(full))
        {
            g.CopyFromScreen(s.Left, s.Top, 0, 0, s.Size, CopyPixelOperation.SourceCopy);
        }

        Bitmap shown = full;
        if (s.Width > maxWidth)
        {
            int h = (int)Math.Round(s.Height * (double)maxWidth / s.Width);
            shown = new Bitmap(maxWidth, h, PixelFormat.Format24bppRgb);
            using Graphics g = Graphics.FromImage(shown);
            g.InterpolationMode = InterpolationMode.HighQualityBilinear;
            g.DrawImage(full, new Rectangle(0, 0, maxWidth, h));
        }

        try
        {
            ImageCodecInfo jpeg = ImageCodecInfo.GetImageEncoders().First(c => c.FormatID == ImageFormat.Jpeg.Guid);
            using var args = new EncoderParameters(1);
            args.Param[0] = new EncoderParameter(System.Drawing.Imaging.Encoder.Quality, quality);
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

    /// <summary>Ein Punkt 0..1 des Bildes auf dem Bildschirm; außerhalb: null.</summary>
    public static Point? PointOf(Rectangle screen, double x, double y)
    {
        if (x is < 0 or > 1 || y is < 0 or > 1 || double.IsNaN(x) || double.IsNaN(y))
        {
            return null;
        }

        return new Point(screen.Left + (int)Math.Round(x * (screen.Width - 1)), screen.Top + (int)Math.Round(y * (screen.Height - 1)));
    }

    /// <summary>Eine Eingabe ausführen; Unbekanntes und Punkte außerhalb des Bildes werden übergangen.</summary>
    public static void Apply(Rectangle screen, ViewEvent e)
    {
        try
        {
            switch (e.Kind)
            {
                case "move" when PointOf(screen, e.X, e.Y) is { } p:
                    _ = SetCursorPos(p.X, p.Y);
                    break;
                case "click" when Buttons.Contains(e.Button) && PointOf(screen, e.X, e.Y) is { } p:
                    _ = SetCursorPos(p.X, p.Y);
                    Click(e.Button);
                    break;
                case "scroll" when e.Dy is >= -10 and <= 10 and not 0:
                    Mouse(MOUSEEVENTF_WHEEL, e.Dy * 120);
                    break;
                case "key" when ViewKeys.TryGetValue(e.Key, out ushort[]? keys):
                    Chord(keys);
                    break;
                case "text" when e.Text.Length is > 0 and <= TextMax:
                    Type(e.Text);
                    break;
            }
        }
        catch (InvalidOperationException)
        {
            // Windows nahm die Eingabe nicht an (Programm vorn als Administrator): nächste Eingabe
        }
    }

    public static void Click(string button)
    {
        (uint down, uint up) = button == "right" ? (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP) : (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP);
        int times = button == "double" ? 2 : 1;
        for (int i = 0; i < times; i++)
        {
            Mouse(down, 0);
            Mouse(up, 0);
        }
    }

    public static void Mouse(uint flags, int data)
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

    /// <summary>Drückt die Tasten nacheinander und lässt sie rückwärts los (ein Block für SendInput).</summary>
    public static void Chord(ushort[] keys)
    {
        var inputs = new List<INPUT>();
        inputs.AddRange(keys.Select(k => Key(k, up: false)));
        inputs.AddRange(keys.Reverse().Select(k => Key(k, up: true)));
        Send(inputs.ToArray());
    }

    /// <summary>Tippt den Text ins Fenster vorn (Unicode, Zeilenumbruch = Eingabe).</summary>
    public static void Type(string text)
    {
        var inputs = new List<INPUT>();
        foreach (char c in text.Replace("\r\n", "\n", StringComparison.Ordinal))
        {
            if (c == '\n')
            {
                inputs.Add(Key(VkReturn, up: false));
                inputs.Add(Key(VkReturn, up: true));
            }
            else if (!char.IsControl(c))
            {
                inputs.Add(Unicode(c, up: false));
                inputs.Add(Unicode(c, up: true));
            }
        }

        Send(inputs.ToArray());
    }

    internal static INPUT Key(ushort vk, bool up)
    {
        bool extended = vk is VkPrior or VkNext or VkEnd or VkHome or VkLeft or VkUp or VkRight or VkDown or VkDelete;
        uint flags = (up ? KEYEVENTF_KEYUP : 0) | (extended ? KEYEVENTF_EXTENDEDKEY : 0);
        return new INPUT
        {
            type = INPUT_KEYBOARD,
            u = new InputUnion { ki = new KEYBDINPUT { wVk = vk, wScan = (ushort)MapVirtualKey(vk, MAPVK_VK_TO_VSC), dwFlags = flags } },
        };
    }

    private static INPUT Unicode(char c, bool up) => new()
    {
        type = INPUT_KEYBOARD,
        u = new InputUnion { ki = new KEYBDINPUT { wVk = 0, wScan = c, dwFlags = KEYEVENTF_UNICODE | (up ? KEYEVENTF_KEYUP : 0) } },
    };

    internal static void Send(INPUT[] inputs)
    {
        if (inputs.Length > 0 && SendInput((uint)inputs.Length, inputs, Marshal.SizeOf<INPUT>()) == 0)
        {
            throw new InvalidOperationException("Windows hat die Tasten nicht angenommen (Programm vorn läuft als Administrator?).");
        }
    }
}

/// <summary>Ein Streifen des roten Rahmens: immer vorn, klickt durch, nimmt nie den Fokus.</summary>
internal sealed class ViewEdge : Form
{
    public ViewEdge(Rectangle bounds, string title)
    {
        FormBorderStyle = FormBorderStyle.None;
        ShowInTaskbar = false;
        TopMost = true;
        StartPosition = FormStartPosition.Manual;
        BackColor = Palette.Light.Bad;
        Bounds = bounds;
        Text = title;
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
    private readonly Label _text = new() { AutoSize = true, ForeColor = Palette.OnColor, BackColor = Color.Transparent };
    private readonly Button _end = new() { AutoSize = true, FlatStyle = FlatStyle.Flat, ForeColor = Palette.OnColor };
    private readonly Rectangle _screen;

    public ViewBar(Rectangle screen, string text, string title, string accessible, string endLabel = "Beenden")
    {
        _screen = screen;
        FormBorderStyle = FormBorderStyle.None;
        ShowInTaskbar = false;
        TopMost = true;
        StartPosition = FormStartPosition.Manual;
        BackColor = Palette.Light.BadText;
        Text = title;
        AccessibleName = accessible;
        _end.Text = endLabel;
        _text.Font = new Font("Segoe UI", 10f, FontStyle.Bold);
        _end.FlatAppearance.BorderColor = Palette.OnColor;
        _end.Click += (_, _) => EndRequested?.Invoke(this, EventArgs.Empty);
        Controls.Add(_text);
        Controls.Add(_end);
        Say(text, accessible);
    }

    /// <summary>„Beenden“ geklickt.</summary>
    public event EventHandler? EndRequested;

    /// <summary>Neuer Text (etwa „Steuerung aktiv“); die Leiste bleibt oben in der Mitte.</summary>
    public void Say(string text, string accessible)
    {
        _text.Text = text;
        AccessibleName = accessible;
        int dpi = Dwm.DpiAt(_screen.Location);
        int pad = Draw.Scale(10, dpi);
        Size size = _text.GetPreferredSize(Size.Empty);
        Size end = _end.GetPreferredSize(Size.Empty);
        int h = Math.Max(size.Height, end.Height) + (2 * pad);
        int w = size.Width + end.Width + (3 * pad);
        _text.Location = new Point(pad, (h - size.Height) / 2);
        _end.Location = new Point(pad + size.Width + pad, (h - end.Height) / 2);
        Bounds = new Rectangle(_screen.Left + ((_screen.Width - w) / 2), _screen.Top + Draw.Scale(8, dpi), w, h);
    }

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

/// <summary>Die Frage hier am Rechner: Ablehnen (vorgewählt), Nur ansehen, Erlauben – welche, sagt <see cref="ViewQuestion"/>.</summary>
internal sealed class ViewAskForm : ThemedForm
{
    private const int TimeoutSeconds = 60;

    private readonly TLabel _question = new(TextRole.Normal);
    private readonly TLabel _detail = new(TextRole.SmallMuted);
    private readonly TLabel _countdown = new(TextRole.SmallMuted);
    private readonly SparkButton _deny;
    private readonly SparkButton _view;
    private readonly SparkButton _allow;
    private readonly ViewQuestion _q;
    private readonly System.Windows.Forms.Timer _timer = new() { Interval = 1000 };
    private readonly DateTime _deadline = DateTime.UtcNow.AddSeconds(TimeoutSeconds);
    private Rectangle _face;
    private Rectangle _title;
    private string _mode = "no";

    public ViewAskForm(ViewQuestion q)
    {
        _q = q;
        _deny = new SparkButton(ButtonKind.Secondary, q.DenyLabel);
        _view = new SparkButton(ButtonKind.Secondary, q.ViewLabel);
        _allow = new SparkButton(ButtonKind.Primary, q.AllowLabel);
        Text = q.Window;
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        MinimizeBox = false;
        TopMost = true;
        ShowInTaskbar = true;
        StartPosition = FormStartPosition.CenterScreen;
        KeyPreview = true;
        _question.Text = q.Question;
        _detail.Text = q.Detail;
        Controls.AddRange(new Control[] { _question, _detail, _countdown, _deny });
        if (q.View)
        {
            Controls.Add(_view);
        }

        if (q.Allow)
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

        _countdown.Text = string.Format(System.Globalization.CultureInfo.InvariantCulture, _q.Countdown, left);
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
        int y = pad;
        int face = S(36);
        _face = new Rectangle(pad, y, face, face);
        _title = new Rectangle(pad + Face.Lead(face, S(10)), y, inner - Face.Lead(face, S(10)), face);
        y += face + S(12);
        y += _question.Fit(pad, y, inner) + S(8);
        y += _detail.Fit(pad, y, inner) + S(10);
        y += _countdown.Fit(pad, y, inner) + S(14);
        int x = w - pad;
        int bh = 0;
        var buttons = new List<SparkButton>();
        if (_q.Allow)
        {
            buttons.Add(_allow);
        }

        if (_q.View)
        {
            buttons.Add(_view);
        }

        buttons.Add(_deny);
        foreach (SparkButton b in buttons)
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
        Face.DrawHeader(g, _face, P);
        Draw.Text(g, _q.Title, F(11f, FontStyle.Bold), _title, P.Fg);
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
