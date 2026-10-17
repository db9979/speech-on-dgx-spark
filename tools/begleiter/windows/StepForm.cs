using System.Drawing.Drawing2D;
using static SparkBegleiter.NativeMethods;

namespace SparkBegleiter;

/// <summary>
/// Stufe 3 („Spark bedient den Rechner“): ein Schritt des Spark, bevor er geschieht. Zeigt, was getan werden soll
/// (Klick mit markiertem Ziel, Scrollen, Taste, Text) und fragt: Stopp, Überspringen, Erlauben. Ohne Antwort nach
/// 60 s gilt Stopp. Text, der nicht im Auftrag stand, steht ausdrücklich darüber. Die Rückfrage („ask“, wenn auf
/// dem Bildschirm etwas wie eine Anweisung aussah) hat nur Nein und Weiter.
/// </summary>
internal sealed class StepForm : ThemedForm
{
    private const int TimeoutSeconds = 60;

    private readonly TLabel _what = new(TextRole.Normal);
    private readonly TLabel _warn = new(TextRole.Normal);
    private readonly TLabel _countdown = new(TextRole.SmallMuted);
    private readonly SparkButton _stop = new(ButtonKind.Secondary, "Stopp");
    private readonly SparkButton _skip = new(ButtonKind.Secondary, "Überspringen");
    private readonly SparkButton _allow = new(ButtonKind.Primary, "Erlauben");
    private readonly System.Windows.Forms.Timer _timer = new() { Interval = 1000 };
    private readonly DateTime _deadline = DateTime.UtcNow.AddSeconds(TimeoutSeconds);
    private readonly bool _ask;
    private readonly string _title;
    private Rectangle _face;
    private Rectangle _titleBox;
    private string _answer = "stop";

    public StepForm(ViewEvent e, Rectangle screen, Point? target)
    {
        _ask = e.Step == "ask";
        _title = _ask ? "Spark fragt nach" : $"Spark, Schritt {e.N} von {Math.Max(e.N, e.Of)}";
        Text = "Spark-Begleiter – " + _title;
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        MinimizeBox = false;
        TopMost = true;
        ShowInTaskbar = true;
        StartPosition = FormStartPosition.Manual;
        KeyPreview = true;

        string why = e.Why.Length > 0 ? e.Why : "ohne Begründung";
        _what.Text = e.Step switch
        {
            "ask" => why,
            "click" => "Klick (rot markiert): " + why,
            "double" => "Doppelklick (rot markiert): " + why,
            "right" => "Rechtsklick (rot markiert): " + why,
            "scroll" => (e.Dy > 0 ? "Nach oben scrollen: " : "Nach unten scrollen: ") + why,
            "key" => $"Taste „{e.Key}“: " + why,
            "type" => $"Tippt: „{e.Text}“ – " + why,
            _ => why,
        };
        _warn.Text = e.Warn.Length > 0 ? "⚠ " + e.Warn : "";
        if (_ask)
        {
            _skip.Text = "Nein";
            _allow.Text = "Weiter";
        }

        Controls.AddRange(new Control[] { _what, _warn, _countdown, _stop, _allow });
        if (!_ask)
        {
            Controls.Add(_skip);
        }

        _stop.TabIndex = 0; // Stopp zuerst: Enter allein führt nichts aus
        _skip.TabIndex = 1;
        _allow.TabIndex = 2;
        _stop.Click += (_, _) => Pick("stop");
        _skip.Click += (_, _) => Pick("skip");
        _allow.Click += (_, _) => Pick("done");
        AcceptButton = _stop;
        CancelButton = _stop;
        _timer.Tick += (_, _) => UpdateCountdown();
        UpdateCountdown();

        // nie über dem Ziel: liegt es oben, kommt die Frage nach unten und umgekehrt
        int dpi = Dwm.DpiAt(screen.Location);
        int w = Draw.Scale(460, dpi);
        bool low = target is { } t && t.Y < screen.Top + (screen.Height / 2);
        int y = low ? screen.Bottom - Draw.Scale(300, dpi) : screen.Top + Draw.Scale(60, dpi);
        Location = new Point(screen.Left + ((screen.Width - w) / 2), y);
    }

    private void Pick(string answer)
    {
        _answer = answer;
        Close();
    }

    /// <summary>Zeigt den Schritt und wartet: "done" (Erlauben/Weiter), "skip" (Überspringen/Nein) oder "stop".</summary>
    public Task<string> AskAsync()
    {
        var done = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);
        FormClosed += (_, _) => done.TrySetResult(_answer);
        Show();
        ViewSession.Hide(this);
        Activate();
        _ = SetForegroundWindow(Handle);
        _stop.Focus();
        _timer.Start();
        return done.Task;
    }

    private void UpdateCountdown()
    {
        int left = (int)Math.Ceiling((_deadline - DateTime.UtcNow).TotalSeconds);
        if (left <= 0)
        {
            _timer.Stop();
            Pick("stop");
            return;
        }

        _countdown.Text = $"Ohne Antwort gilt in {left} s „Stopp“.";
        if (IsHandleCreated)
        {
            LayoutContent();
            _countdown.Invalidate();
        }
    }

    protected override void OnThemeApplied()
    {
        _warn.ForeColor = Palette.Hex(0xE5484D);
    }

    protected override void LayoutContent()
    {
        int pad = S(16);
        int w = S(460);
        int inner = w - (2 * pad);
        int y = BarHeight + pad;
        int face = S(36);
        _face = new Rectangle(pad, y, face, face);
        _titleBox = new Rectangle(pad + face + S(10), y, inner - face - S(10), face);
        y += face + S(12);
        y += _what.Fit(pad, y, inner) + S(8);
        if (_warn.Text.Length > 0)
        {
            y += _warn.Fit(pad, y, inner) + S(8);
        }

        y += _countdown.Fit(pad, y, inner) + S(14);
        int x = w - pad;
        int bh = 0;
        foreach (SparkButton b in _ask ? new[] { _allow, _stop } : new[] { _allow, _skip, _stop })
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
        Draw.Text(g, _title, F(11f, FontStyle.Bold), _titleBox, P.Fg);
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

/// <summary>Der rote Ring um das Ziel eines Klicks: klickt durch, nimmt nie den Fokus.</summary>
internal sealed class ViewMarker : Form
{
    public ViewMarker(Point center)
    {
        int dpi = Dwm.DpiAt(center);
        int size = Draw.Scale(44, dpi);
        int ring = Draw.Scale(5, dpi);
        FormBorderStyle = FormBorderStyle.None;
        ShowInTaskbar = false;
        TopMost = true;
        StartPosition = FormStartPosition.Manual;
        BackColor = Palette.Hex(0xE5484D);
        Bounds = new Rectangle(center.X - (size / 2), center.Y - (size / 2), size, size);
        Text = "Spark-Begleiter – Ziel";
        using var path = new GraphicsPath { FillMode = FillMode.Alternate };
        path.AddEllipse(0, 0, size, size);
        path.AddEllipse(ring, ring, size - (2 * ring), size - (2 * ring));
        Region = new Region(path);
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
        Opacity = 0.95;
    }
}
