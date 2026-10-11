using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Drawing.Text;
using System.Globalization;

namespace SparkBegleiter;

/// <summary>Wo die Pille steht.</summary>
internal enum PillPlace
{
    /// <summary>Unten rechts über dem Infobereich (wie der Diktat-Hinweis).</summary>
    BottomRight,

    /// <summary>Oben in der Mitte des Hauptbildschirms (gut sichtbar, z. B. Besprechung).</summary>
    TopCenter,
}

/// <summary>
/// Schwebende Pille in Entwurf A für Vorgänge, die sichtbar sein müssen (Vorlesen, Besprechung): Punkt, Text,
/// optional Zeit und ein Knopf (z. B. „Stop“, „Beenden“). Immer im Vordergrund, nimmt dem Programm darunter nie
/// den Fokus; nur der Knopf reagiert auf Klicks. Gezeichnet mit Alphakanal (UpdateLayeredWindow).
/// Mit <see cref="Pinned"/> lässt sie sich nicht verdecken (sie stellt sich jede Sekunde wieder nach oben).
/// </summary>
internal sealed class FloatingPill : Form
{
    private static readonly Color TextColor = Palette.Hex(0xE8EBF2);
    private static readonly Color MutedText = Palette.Hex(0xC9D0E0);

    private readonly System.Windows.Forms.Timer _timer = new() { Interval = 250 };
    private readonly PillPlace _place;
    private readonly bool _danger;
    private readonly Func<TimeSpan>? _clock;
    private readonly Screen _screen;
    private string _label;
    private string? _button;
    private Rectangle _buttonRect;
    private bool _hover;
    private int _tick;

    /// <param name="label">Text der Pille (reiner Text).</param>
    /// <param name="button">Beschriftung des Knopfs oder <c>null</c> (kein Knopf).</param>
    /// <param name="danger">Rote Pille (Besprechung) statt Visier-Farbe.</param>
    /// <param name="clock">Laufzeit für „mm:ss“ oder <c>null</c>.</param>
    public FloatingPill(string label, string? button, PillPlace place, bool danger = false, Func<TimeSpan>? clock = null)
    {
        _label = label;
        _button = button;
        _place = place;
        _danger = danger;
        _clock = clock;
        _screen = place == PillPlace.TopCenter ? Screen.PrimaryScreen ?? Screen.FromPoint(Cursor.Position) : Screen.FromPoint(Cursor.Position);

        FormBorderStyle = FormBorderStyle.None;
        ShowInTaskbar = false;
        TopMost = true;
        StartPosition = FormStartPosition.Manual;
        Size = new Size(1, 1);
        Location = new Point(-32000, -32000);
        Text = "Spark-Begleiter – " + label;
        AccessibleName = label;

        _timer.Tick += (_, _) =>
        {
            _tick++;
            if (Pinned && _tick % 4 == 0 && IsHandleCreated)
            {
                _ = NativeMethods.SetWindowPos(Handle, NativeMethods.HWND_TOPMOST, 0, 0, 0, 0,
                    NativeMethods.SWP_NOMOVE | NativeMethods.SWP_NOSIZE | NativeMethods.SWP_NOACTIVATE);
            }

            Render();
        };
    }

    /// <summary>Klick auf den Knopf.</summary>
    public event EventHandler? ButtonClicked;

    /// <summary>Nicht verdeckbar: regelmäßig wieder ganz nach oben.</summary>
    public bool Pinned { get; init; }

    protected override bool ShowWithoutActivation => true;

    protected override CreateParams CreateParams
    {
        get
        {
            CreateParams cp = base.CreateParams;
            cp.ExStyle |= NativeMethods.WS_EX_TOOLWINDOW | NativeMethods.WS_EX_NOACTIVATE | NativeMethods.WS_EX_TOPMOST | NativeMethods.WS_EX_LAYERED;
            return cp;
        }
    }

    /// <summary>Text und Knopf ändern (z. B. „wird ausgewertet …“ ohne Knopf).</summary>
    public void SetState(string label, string? button)
    {
        _label = label;
        _button = button;
        AccessibleName = label;
        Render();
    }

    protected override void OnShown(EventArgs e)
    {
        base.OnShown(e);
        Render();
        _timer.Start();
    }

    protected override void OnMouseMove(MouseEventArgs e)
    {
        base.OnMouseMove(e);
        bool hover = _button is not null && _buttonRect.Contains(e.Location);
        if (hover != _hover)
        {
            _hover = hover;
            Cursor = hover ? Cursors.Hand : Cursors.Default;
            Render();
        }
    }

    protected override void OnMouseLeave(EventArgs e)
    {
        base.OnMouseLeave(e);
        if (_hover)
        {
            _hover = false;
            Render();
        }
    }

    protected override void OnMouseClick(MouseEventArgs e)
    {
        base.OnMouseClick(e);
        if (e.Button == MouseButtons.Left && _button is not null && _buttonRect.Contains(e.Location))
        {
            ButtonClicked?.Invoke(this, EventArgs.Empty);
        }
    }

    protected override void OnPaintBackground(PaintEventArgs e)
    {
        // Gezeichnet wird über UpdateLayeredWindow.
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        // Gezeichnet wird über UpdateLayeredWindow.
    }

    private void Render()
    {
        if (!IsHandleCreated || IsDisposed)
        {
            return;
        }

        Rectangle area = _screen.WorkingArea;
        int dpi = Dwm.DpiAt(new Point(area.Left + (area.Width / 2), area.Top + 10));
        int S(float v) => Draw.Scale(v, dpi);

        Palette p = Theme.Current;
        Font font = Theme.UiFont(dpi, 9.5f);
        Font small = Theme.UiFont(dpi, 8.5f);
        Font buttonFont = Theme.UiFont(dpi, 9f, FontStyle.Bold);
        string clock = _clock is null ? "" : FormatClock(_clock());

        using var measureBitmap = new Bitmap(1, 1);
        using Graphics mg = Graphics.FromImage(measureBitmap);
        mg.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;
        SizeF labelSize = mg.MeasureString(_label, font, PointF.Empty, StringFormat.GenericTypographic);
        SizeF clockSize = clock.Length > 0 ? mg.MeasureString(clock, small, PointF.Empty, StringFormat.GenericTypographic) : SizeF.Empty;
        SizeF buttonSize = _button is not null ? mg.MeasureString(_button, buttonFont, PointF.Empty, StringFormat.GenericTypographic) : SizeF.Empty;

        int shadow = S(12);
        int height = S(38);
        int dot = S(9);
        int gap = S(10);
        int buttonW = _button is not null ? (int)Math.Ceiling(buttonSize.Width) + S(22) : 0;
        int width = S(14) + dot + gap + (int)Math.Ceiling(labelSize.Width)
                    + (clock.Length > 0 ? S(8) + (int)Math.Ceiling(clockSize.Width) : 0)
                    + (_button is not null ? gap + buttonW - S(8) : 0) + S(14);

        int bw = width + (2 * shadow);
        int bh = height + (2 * shadow);
        using var bitmap = new Bitmap(bw, bh, PixelFormat.Format32bppArgb);
        using (Graphics g = Graphics.FromImage(bitmap))
        {
            g.Clear(Color.Transparent);
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;
            var pill = new RectangleF(shadow, shadow, width, height);

            for (int i = shadow; i > 0; i -= Math.Max(1, shadow / 6))
            {
                RectangleF r = RectangleF.Inflate(pill, i * 0.8f, i * 0.8f);
                r.Offset(0, S(3));
                using var brush = new SolidBrush(Color.FromArgb((int)(28 * (1f - ((float)i / shadow))) + 4, 0, 0, 0));
                using GraphicsPath path = Draw.Round(r, r.Height / 2f);
                g.FillPath(brush, path);
            }

            Color back = _danger ? Palette.Light.Bad : p.HighContrast ? Palette.Light.Visor : p.Visor;
            using (GraphicsPath path = Draw.Round(pill, pill.Height / 2f))
            using (var fill = new SolidBrush(back))
            using (var border = new Pen(Color.FromArgb(70, 255, 255, 255), 1f))
            {
                g.FillPath(fill, path);
                g.DrawPath(border, path);
            }

            float x = pill.X + S(14);
            float cy = pill.Y + (pill.Height / 2f);
            bool blinkOn = (_tick / 3) % 2 == 0;
            Color dotColor = _danger
                ? (blinkOn ? Color.White : Color.FromArgb(150, 255, 255, 255))
                : Palette.DarkTheme.Accent2;
            using (var dotBrush = new SolidBrush(dotColor))
            {
                g.FillEllipse(dotBrush, x, cy - (dot / 2f), dot, dot);
            }

            x += dot + gap;
            using (var textBrush = new SolidBrush(TextColor))
            {
                g.DrawString(_label, font, textBrush, x, cy - (labelSize.Height / 2f), StringFormat.GenericTypographic);
            }

            x += labelSize.Width;
            if (clock.Length > 0)
            {
                x += S(8);
                using var mutedBrush = new SolidBrush(_danger ? Color.White : MutedText);
                g.DrawString(clock, small, mutedBrush, x, cy - (clockSize.Height / 2f), StringFormat.GenericTypographic);
                x += clockSize.Width;
            }

            if (_button is not null)
            {
                x += gap;
                var button = new RectangleF(x, pill.Y + S(6), buttonW, pill.Height - S(12));
                using (GraphicsPath bp = Draw.Round(button, button.Height / 2f))
                using (var bf = new SolidBrush(Color.FromArgb(_hover ? 90 : 55, 255, 255, 255)))
                {
                    g.FillPath(bf, bp);
                }

                using (var bt = new SolidBrush(Color.White))
                {
                    g.DrawString(_button, buttonFont, bt, button.X + ((button.Width - buttonSize.Width) / 2f),
                        cy - (buttonSize.Height / 2f), StringFormat.GenericTypographic);
                }

                _buttonRect = Rectangle.Round(button);
            }
            else
            {
                _buttonRect = Rectangle.Empty;
            }
        }

        Point position = _place == PillPlace.TopCenter
            ? new Point(area.Left + ((area.Width - bw) / 2), area.Top + S(8) - shadow)
            : new Point(area.Right - bw - S(16) + shadow, area.Bottom - bh - S(16) + shadow);
        Push(bitmap, position);
    }

    private static string FormatClock(TimeSpan t) => t.TotalHours >= 1
        ? string.Create(CultureInfo.InvariantCulture, $"{(int)t.TotalHours}:{t.Minutes:00}:{t.Seconds:00}")
        : string.Create(CultureInfo.InvariantCulture, $"{(int)t.TotalMinutes:00}:{t.Seconds:00}");

    /// <summary>Bild mit Alphakanal als Fensterinhalt setzen.</summary>
    private void Push(Bitmap bitmap, Point position)
    {
        IntPtr screenDc = NativeMethods.GetDC(IntPtr.Zero);
        IntPtr memDc = NativeMethods.CreateCompatibleDC(screenDc);
        IntPtr hBitmap = IntPtr.Zero;
        IntPtr old = IntPtr.Zero;
        try
        {
            hBitmap = bitmap.GetHbitmap(Color.FromArgb(0));
            old = NativeMethods.SelectObject(memDc, hBitmap);
            var size = new NativeMethods.SIZE(bitmap.Width, bitmap.Height);
            var source = new NativeMethods.POINT(0, 0);
            var top = new NativeMethods.POINT(position.X, position.Y);
            var blend = new NativeMethods.BLENDFUNCTION
            {
                BlendOp = NativeMethods.AC_SRC_OVER,
                SourceConstantAlpha = 255,
                AlphaFormat = NativeMethods.AC_SRC_ALPHA,
            };
            _ = NativeMethods.UpdateLayeredWindow(Handle, screenDc, ref top, ref size, memDc, ref source, 0, ref blend, NativeMethods.ULW_ALPHA);
        }
        finally
        {
            if (old != IntPtr.Zero)
            {
                NativeMethods.SelectObject(memDc, old);
            }

            if (hBitmap != IntPtr.Zero)
            {
                NativeMethods.DeleteObject(hBitmap);
            }

            NativeMethods.DeleteDC(memDc);
            _ = NativeMethods.ReleaseDC(IntPtr.Zero, screenDc);
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
