using System.Globalization;

namespace SparkBegleiter;

/// <summary>
/// Kleiner Hinweis unten rechts, immer im Vordergrund, solange aufgenommen wird:
/// "● Aufnahme 0:07 … (Strg+Alt+D zum Beenden)". Er nimmt dem Zielprogramm nie den Fokus weg;
/// ein Klick darauf beendet die Aufnahme ebenfalls.
/// </summary>
internal sealed class RecordingIndicator : Form
{
    private readonly Label _dot = new()
    {
        AutoSize = true,
        Text = "●",
        ForeColor = Color.FromArgb(0xEF, 0x44, 0x44),
        Margin = new Padding(0, 0, 6, 0),
        Anchor = AnchorStyles.Left,
    };

    private readonly Label _text = new() { AutoSize = true, ForeColor = Color.White, Anchor = AnchorStyles.Left };
    private readonly System.Windows.Forms.Timer _timer = new() { Interval = 250 };
    private readonly Func<TimeSpan> _elapsed;
    private readonly string _hotkey;
    private bool _working;
    private bool _blink;

    public RecordingIndicator(string hotkey, Func<TimeSpan> elapsed)
    {
        _hotkey = hotkey;
        _elapsed = elapsed;

        SuspendLayout();
        AutoScaleDimensions = new SizeF(96F, 96F);
        AutoScaleMode = AutoScaleMode.Dpi;
        Font = SystemFonts.MessageBoxFont ?? Font;
        FormBorderStyle = FormBorderStyle.None;
        ShowInTaskbar = false;
        TopMost = true;
        StartPosition = FormStartPosition.Manual;
        BackColor = Color.FromArgb(0x1F, 0x29, 0x37);
        AutoSize = true;
        AutoSizeMode = AutoSizeMode.GrowAndShrink;
        Padding = new Padding(12, 8, 12, 8);
        Cursor = Cursors.Hand;

        var row = new FlowLayoutPanel { AutoSize = true, WrapContents = false, Margin = Padding.Empty, BackColor = BackColor };
        row.Controls.Add(_dot);
        row.Controls.Add(_text);
        Controls.Add(row);
        ResumeLayout(performLayout: true);

        foreach (Control c in new Control[] { this, row, _dot, _text })
        {
            c.Click += (_, _) => StopRequested?.Invoke(this, EventArgs.Empty);
        }

        _timer.Tick += (_, _) => UpdateText();
        UpdateText();
    }

    /// <summary>Klick auf den Hinweis.</summary>
    public event EventHandler? StopRequested;

    protected override bool ShowWithoutActivation => true;

    protected override CreateParams CreateParams
    {
        get
        {
            CreateParams cp = base.CreateParams;
            cp.ExStyle |= NativeMethods.WS_EX_TOOLWINDOW | NativeMethods.WS_EX_NOACTIVATE | NativeMethods.WS_EX_TOPMOST;
            return cp;
        }
    }

    /// <summary>Nach dem Beenden: der Spark erkennt den Text.</summary>
    public void ShowWorking()
    {
        _working = true;
        _timer.Stop();
        _dot.ForeColor = Color.FromArgb(0x60, 0xA5, 0xFA);
        _text.Text = "Der Spark erkennt den Text …";
        PlaceBottomRight();
    }

    protected override void OnShown(EventArgs e)
    {
        base.OnShown(e);
        PlaceBottomRight();
        _timer.Start();
    }

    private void UpdateText()
    {
        if (_working)
        {
            return;
        }

        TimeSpan t = _elapsed();
        string time = string.Format(CultureInfo.InvariantCulture, "{0}:{1:00}", (int)t.TotalMinutes, t.Seconds);
        _text.Text = $"Aufnahme {time} … ({_hotkey} zum Beenden)";
        _blink = !_blink;
        _dot.ForeColor = _blink ? Color.FromArgb(0xEF, 0x44, 0x44) : Color.FromArgb(0x7F, 0x1D, 0x1D);
    }

    private void PlaceBottomRight()
    {
        Rectangle area = Screen.FromPoint(Cursor.Position).WorkingArea;
        Location = new Point(area.Right - Width - 16, area.Bottom - Height - 16);
    }

    protected override void OnLayout(LayoutEventArgs levent)
    {
        base.OnLayout(levent);
        if (Visible)
        {
            PlaceBottomRight();
        }
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
