using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Drawing.Text;
using System.Globalization;

namespace SparkBegleiter;

/// <summary>
/// Hinweis beim Diktieren (Entwurf A): dunkle Pille in Visier-Farbe unten rechts mit rotem Punkt,
/// „Ich höre zu“, Zeit, kleinen Pegel-Balken und dem Tastenkürzel. Immer im Vordergrund, nimmt dem
/// Zielprogramm nie den Fokus; ein Klick darauf beendet die Aufnahme. Gezeichnet als Fenster mit
/// Alphakanal (UpdateLayeredWindow), damit Rundung und Schatten sauber sind.
/// </summary>
internal sealed class RecordingIndicator : Form
{
    private static readonly Color TextColor = Palette.HudText;
    private static readonly Color MutedText = Palette.HudMuted;
    private static readonly Color ChipLine = Palette.HudLine;

    private readonly System.Windows.Forms.Timer _timer = new() { Interval = 70 };
    private readonly Func<TimeSpan> _elapsed;
    private readonly Func<float> _level;
    private readonly string _hotkey;
    private readonly float[] _bars = new float[5];
    private readonly Screen _screen;
    private bool _working;
    private int _tick;

    public RecordingIndicator(string hotkey, Func<TimeSpan> elapsed, Func<float> level)
    {
        _hotkey = hotkey;
        _elapsed = elapsed;
        _level = level;
        _screen = Screen.FromPoint(Cursor.Position);

        FormBorderStyle = FormBorderStyle.None;
        ShowInTaskbar = false;
        TopMost = true;
        StartPosition = FormStartPosition.Manual;
        Size = new Size(1, 1);
        Location = new Point(_screen.WorkingArea.Right - 2, _screen.WorkingArea.Bottom - 2);
        Cursor = Cursors.Hand;
        Text = "Spark-Begleiter – Aufnahme";
        AccessibleName = "Ich höre zu – klicken zum Beenden";

        _timer.Tick += (_, _) => Render();
    }

    /// <summary>Klick auf den Hinweis.</summary>
    public event EventHandler? StopRequested;

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

    /// <summary>Nach dem Beenden: der Spark erkennt den Text.</summary>
    public void ShowWorking()
    {
        _working = true;
        AccessibleName = "Der Spark erkennt den Text";
        Render();
    }

    protected override void OnShown(EventArgs e)
    {
        base.OnShown(e);
        Render();
        _timer.Start();
    }

    protected override void OnMouseClick(MouseEventArgs e)
    {
        base.OnMouseClick(e);
        if (!_working)
        {
            StopRequested?.Invoke(this, EventArgs.Empty);
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

        _tick++;
        float level = _working ? 0 : _level();
        for (int i = 0; i < _bars.Length; i++)
        {
            // Jeder Balken folgt dem Pegel etwas anders, damit es lebendig wirkt.
            float wobble = 0.55f + (0.45f * (float)Math.Abs(Math.Sin((_tick * 0.35) + (i * 1.7))));
            float target = Math.Clamp((level * wobble) + 0.12f, 0.12f, 1f);
            _bars[i] += (target - _bars[i]) * 0.45f;
        }

        Palette p = Theme.Current;
        int dpi = Dwm.DpiAt(new Point(_screen.WorkingArea.Right - 10, _screen.WorkingArea.Bottom - 10));
        int S(float v) => Draw.Scale(v, dpi);

        Font font = Theme.UiFont(dpi, 9.5f);
        Font time = Theme.UiFont(dpi, 8.5f);
        Font mono = Theme.MonoFont(dpi, 8f);

        TimeSpan t = _elapsed();
        string label = _working ? "Der Spark erkennt den Text …" : "Ich höre zu";
        string clock = string.Create(CultureInfo.InvariantCulture, $"{(int)t.TotalMinutes}:{t.Seconds:00}");

        using var measureBitmap = new Bitmap(1, 1);
        using Graphics mg = Graphics.FromImage(measureBitmap);
        mg.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;
        SizeF labelSize = mg.MeasureString(label, font, PointF.Empty, StringFormat.GenericTypographic);
        SizeF clockSize = mg.MeasureString(clock, time, PointF.Empty, StringFormat.GenericTypographic);
        SizeF keySize = mg.MeasureString(_hotkey, mono, PointF.Empty, StringFormat.GenericTypographic);

        int shadow = S(12);
        int height = S(36);
        int dot = S(9);
        int gap = S(10);
        int waveW = (5 * S(3)) + (4 * S(3));
        int chipW = (int)Math.Ceiling(keySize.Width) + S(12);
        int chipH = (int)Math.Ceiling(keySize.Height) + S(4);
        int width = S(14) + dot + gap + (int)Math.Ceiling(labelSize.Width)
                    + (_working ? 0 : S(6) + (int)Math.Ceiling(clockSize.Width) + gap + waveW + gap + chipW) + S(14);

        int bw = width + (2 * shadow);
        int bh = height + (2 * shadow);
        using var bitmap = new Bitmap(bw, bh, PixelFormat.Format32bppArgb);
        using (Graphics g = Graphics.FromImage(bitmap))
        {
            g.Clear(Color.Transparent);
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;

            var pill = new RectangleF(shadow, shadow, width, height);

            // Weicher Schatten
            for (int i = shadow; i > 0; i -= Math.Max(1, shadow / 6))
            {
                RectangleF r = RectangleF.Inflate(pill, i * 0.8f, i * 0.8f);
                r.Offset(0, S(3));
                using var brush = new SolidBrush(Color.FromArgb((int)(28 * (1f - ((float)i / shadow))) + 4, Palette.Shade));
                using GraphicsPath path = Draw.Round(r, r.Height / 2f);
                g.FillPath(brush, path);
            }

            Color visor = p.HighContrast ? Palette.Light.Visor : p.Visor;
            using (GraphicsPath path = Draw.Round(pill, pill.Height / 2f))
            using (var fill = new SolidBrush(visor))
            using (var border = new Pen(Color.FromArgb(60, Palette.OnColor), 1f))
            {
                g.FillPath(fill, path);
                g.DrawPath(border, path);
            }

            float x = pill.X + S(14);
            float cy = pill.Y + (pill.Height / 2f);
            bool blinkOn = _working || (_tick / 7) % 2 == 0;
            Color dotColor = _working ? Palette.DarkTheme.Accent : blinkOn ? Palette.Light.Bad : Palette.Mix(Palette.Light.Bad, visor, 0.55f);
            using (var dotBrush = new SolidBrush(dotColor))
            {
                g.FillEllipse(dotBrush, x, cy - (dot / 2f), dot, dot);
            }

            x += dot + gap;
            using (var textBrush = new SolidBrush(TextColor))
            {
                g.DrawString(label, font, textBrush, x, cy - (labelSize.Height / 2f), StringFormat.GenericTypographic);
            }

            x += labelSize.Width;
            if (!_working)
            {
                x += S(6);
                using (var mutedBrush = new SolidBrush(MutedText))
                {
                    g.DrawString(clock, time, mutedBrush, x, cy - (clockSize.Height / 2f), StringFormat.GenericTypographic);
                }

                x += clockSize.Width + gap;
                using (var barBrush = new SolidBrush(Palette.DarkTheme.Accent))
                {
                    float maxH = S(18);
                    for (int i = 0; i < _bars.Length; i++)
                    {
                        float bh2 = Math.Max(S(3), maxH * _bars[i]);
                        using GraphicsPath bar = Draw.Round(new RectangleF(x, cy - (bh2 / 2f), S(3), bh2), S(1.5f));
                        g.FillPath(barBrush, bar);
                        x += S(3) + S(3);
                    }
                }

                x += gap - S(3);
                var chip = new RectangleF(x, cy - (chipH / 2f), chipW, chipH);
                using (GraphicsPath chipPath = Draw.Round(chip, S(6)))
                using (var chipPen = new Pen(ChipLine, 1f))
                {
                    g.DrawPath(chipPen, chipPath);
                }

                using var keyBrush = new SolidBrush(Palette.Eye);
                g.DrawString(_hotkey, mono, keyBrush, chip.X + S(6), cy - (keySize.Height / 2f), StringFormat.GenericTypographic);
            }
        }

        Rectangle area = _screen.WorkingArea;
        var position = new Point(area.Right - bw - S(16) + shadow, area.Bottom - bh - S(16) + shadow);
        Push(bitmap, position);
    }

    /// <summary>Bild mit Alphakanal als Fensterinhalt setzen.</summary>
    private void Push(Bitmap bitmap, Point position)
    {
        IntPtr screenDc = NativeMethods.GetDC(IntPtr.Zero);
        IntPtr memDc = NativeMethods.CreateCompatibleDC(screenDc);
        IntPtr hBitmap = IntPtr.Zero;
        IntPtr old = IntPtr.Zero;
        try
        {
            hBitmap = bitmap.GetHbitmap(Color.FromArgb(0, Palette.Shade));
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
