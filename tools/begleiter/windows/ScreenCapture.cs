using System.Drawing.Drawing2D;
using System.Drawing.Imaging;

namespace SparkBegleiter;

/// <summary>
/// Teil "screen": Bildschirm einfrieren, auf allen Bildschirmen abdunkeln, Bereich aufziehen (Esc bricht ab).
/// Je Bildschirm ein eigenes randloses Fenster in physischen Pixeln (Per-Monitor-DPI), damit nichts skaliert wird.
/// Das Bild bleibt nur im Speicher und wird nie auf die Platte geschrieben.
/// </summary>
internal sealed class ScreenCapture : IDisposable
{
    private readonly Rectangle _virtual;
    private readonly Bitmap _shot;
    private readonly List<Overlay> _overlays = new();
    private readonly TaskCompletionSource<Rectangle?> _done = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private Point? _start;
    private Rectangle _selection;

    private ScreenCapture()
    {
        _virtual = SystemInformation.VirtualScreen;
        _shot = new Bitmap(_virtual.Width, _virtual.Height, PixelFormat.Format32bppArgb);
        using Graphics g = Graphics.FromImage(_shot);
        g.CopyFromScreen(_virtual.Left, _virtual.Top, 0, 0, _virtual.Size, CopyPixelOperation.SourceCopy);
    }

    /// <summary>Bereich wählen lassen; gibt den Ausschnitt zurück oder <c>null</c> (abgebrochen).</summary>
    public static async Task<(Bitmap Image, Rectangle Area)?> SelectAsync()
    {
        using var capture = new ScreenCapture();
        Rectangle? area = await capture.RunAsync();
        if (area is not { Width: > 0, Height: > 0 } r)
        {
            return null;
        }

        var crop = new Rectangle(r.X - capture._virtual.X, r.Y - capture._virtual.Y, r.Width, r.Height);
        crop.Intersect(new Rectangle(Point.Empty, capture._shot.Size));
        if (crop.Width < 2 || crop.Height < 2)
        {
            return null;
        }

        return (capture._shot.Clone(crop, PixelFormat.Format32bppArgb), r);
    }

    private Task<Rectangle?> RunAsync()
    {
        foreach (Screen screen in Screen.AllScreens)
        {
            var overlay = new Overlay(this, screen.Bounds);
            _overlays.Add(overlay);
            overlay.Show();
        }

        Overlay? under = _overlays.FirstOrDefault(o => o.Bounds.Contains(Cursor.Position)) ?? _overlays.FirstOrDefault();
        if (under is not null)
        {
            under.Activate();
            _ = NativeMethods.SetForegroundWindow(under.Handle);
        }

        return _done.Task;
    }

    private void Finish(Rectangle? result)
    {
        if (!_done.TrySetResult(result))
        {
            return; // schon fertig (Schließen der Fenster ruft hier wieder an)
        }

        foreach (Overlay o in _overlays.ToList())
        {
            o.Close();
        }
    }

    private void Begin(Point global)
    {
        _start = global;
        _selection = new Rectangle(global, Size.Empty);
        Refresh();
    }

    private void Move(Point global)
    {
        if (_start is not { } s)
        {
            return;
        }

        _selection = Rectangle.FromLTRB(Math.Min(s.X, global.X), Math.Min(s.Y, global.Y), Math.Max(s.X, global.X), Math.Max(s.Y, global.Y));
        _selection.Intersect(_virtual);
        Refresh();
    }

    private void End(Point global)
    {
        if (_start is null)
        {
            return;
        }

        Move(global);
        _start = null;
        if (_selection.Width >= 8 && _selection.Height >= 8)
        {
            Finish(_selection);
        }
        else
        {
            _selection = Rectangle.Empty; // zu klein (nur geklickt): weiter wählen
            Refresh();
        }
    }

    private void Refresh()
    {
        foreach (Overlay o in _overlays)
        {
            o.Invalidate();
        }
    }

    public void Dispose()
    {
        foreach (Overlay o in _overlays)
        {
            o.Dispose();
        }

        _shot.Dispose();
    }

    /// <summary>Ein Bildschirm: eingefrorenes Bild, abgedunkelt; die Auswahl hell mit Akzent-Rahmen.</summary>
    private sealed class Overlay : Form
    {
        private readonly ScreenCapture _owner;
        private readonly Rectangle _screen;

        public Overlay(ScreenCapture owner, Rectangle screen)
        {
            _owner = owner;
            _screen = screen;
            AutoScaleMode = AutoScaleMode.None;
            FormBorderStyle = FormBorderStyle.None;
            StartPosition = FormStartPosition.Manual;
            ShowInTaskbar = false;
            TopMost = true;
            KeyPreview = true;
            Bounds = screen;
            Cursor = Cursors.Cross;
            Text = "Spark-Begleiter – Bereich wählen";
            AccessibleName = "Bereich aufziehen, Esc bricht ab";
            SetStyle(ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint | ControlStyles.UserPaint | ControlStyles.Opaque, true);
        }

        protected override CreateParams CreateParams
        {
            get
            {
                CreateParams cp = base.CreateParams;
                cp.ExStyle |= NativeMethods.WS_EX_TOOLWINDOW | NativeMethods.WS_EX_TOPMOST;
                return cp;
            }
        }

        protected override void WndProc(ref Message m)
        {
            // Größe bleibt in physischen Pixeln, auch wenn Windows eine andere DPI meldet.
            if (m.Msg == NativeMethods.WM_DPICHANGED)
            {
                m.Result = IntPtr.Zero;
                return;
            }

            base.WndProc(ref m);
        }

        protected override void OnShown(EventArgs e)
        {
            base.OnShown(e);
            Bounds = _screen;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            Palette p = Theme.Current;
            var source = new Rectangle(_screen.X - _owner._virtual.X, _screen.Y - _owner._virtual.Y, _screen.Width, _screen.Height);
            g.InterpolationMode = InterpolationMode.NearestNeighbor;
            g.DrawImage(_owner._shot, new Rectangle(0, 0, _screen.Width, _screen.Height), source, GraphicsUnit.Pixel);

            Rectangle sel = _owner._selection;
            sel.Offset(-_screen.X, -_screen.Y);
            using (var dim = new Region(new Rectangle(0, 0, _screen.Width, _screen.Height)))
            {
                if (sel.Width > 0 && sel.Height > 0)
                {
                    dim.Exclude(sel);
                }

                using var veil = new SolidBrush(Color.FromArgb(120, Palette.Shade));
                g.FillRegion(veil, dim);
            }

            int dpi = DeviceDpi;
            if (sel.Width > 0 && sel.Height > 0 && sel.IntersectsWith(new Rectangle(0, 0, _screen.Width, _screen.Height)))
            {
                using var pen = new Pen(p.HighContrast ? SystemColors.Highlight : p.Accent, Math.Max(2, Draw.Scale(2, dpi)));
                g.DrawRectangle(pen, sel);
                string size = $"{_owner._selection.Width} × {_owner._selection.Height}";
                Font small = Theme.UiFont(dpi, 8.5f);
                Size t = Draw.Measure(size, small);
                var label = new Rectangle(sel.X, Math.Max(0, sel.Y - t.Height - Draw.Scale(8, dpi)), t.Width + Draw.Scale(12, dpi), t.Height + Draw.Scale(4, dpi));
                g.SmoothingMode = SmoothingMode.AntiAlias;
                Draw.FillRound(g, p.HighContrast ? SystemColors.Window : Palette.HudBack, label, Draw.Scale(6, dpi));
                Draw.Text(g, size, small, label, p.HighContrast ? SystemColors.WindowText : Palette.OnColor, Draw.Line | TextFormatFlags.HorizontalCenter);
            }

            if (_screen.Contains(Cursor.Position) || _owner._overlays.Count == 1)
            {
                // Hinweis oben in der Mitte (Visier-Pille wie beim Diktieren)
                const string hint = "Bereich aufziehen  ·  Esc bricht ab";
                Font font = Theme.UiFont(dpi, 10f);
                Size t = Draw.Measure(hint, font);
                var pill = new Rectangle((_screen.Width - t.Width) / 2 - Draw.Scale(16, dpi), Draw.Scale(24, dpi), t.Width + Draw.Scale(32, dpi), t.Height + Draw.Scale(14, dpi));
                g.SmoothingMode = SmoothingMode.AntiAlias;
                Draw.FillRound(g, p.HighContrast ? SystemColors.Window : Palette.HudBack, pill, pill.Height / 2f);
                Draw.Text(g, hint, font, pill, p.HighContrast ? SystemColors.WindowText : Palette.HudText, Draw.Line | TextFormatFlags.HorizontalCenter);
            }
        }

        protected override void OnMouseDown(MouseEventArgs e)
        {
            base.OnMouseDown(e);
            if (e.Button == MouseButtons.Left)
            {
                Capture = true;
                _owner.Begin(Cursor.Position);
            }
            else if (e.Button == MouseButtons.Right)
            {
                _owner.Finish(null);
            }
        }

        protected override void OnMouseMove(MouseEventArgs e)
        {
            base.OnMouseMove(e);
            _owner.Move(Cursor.Position);
        }

        protected override void OnMouseUp(MouseEventArgs e)
        {
            base.OnMouseUp(e);
            if (e.Button == MouseButtons.Left)
            {
                Capture = false;
                _owner.End(Cursor.Position);
            }
        }

        protected override bool ProcessCmdKey(ref Message msg, Keys keyData)
        {
            if (keyData == Keys.Escape)
            {
                _owner.Finish(null);
                return true;
            }

            return base.ProcessCmdKey(ref msg, keyData);
        }

        protected override void OnFormClosed(FormClosedEventArgs e)
        {
            base.OnFormClosed(e);
            _owner.Finish(null); // z. B. Alt+F4
        }
    }
}

/// <summary>Bild für /api/desk/screen: lange Seite ≤ 2000 px, PNG (sonst JPEG), höchstens 6 MB – nur im Speicher.</summary>
internal static class ScreenImage
{
    public const int MaxSide = 2000;

    public static (byte[] Data, string ContentType) Encode(Bitmap image)
    {
        double scale = Math.Min(1.0, MaxSide / (double)Math.Max(image.Width, image.Height));
        for (int attempt = 0; attempt < 6; attempt++)
        {
            int w = Math.Max(1, (int)Math.Round(image.Width * scale));
            int h = Math.Max(1, (int)Math.Round(image.Height * scale));
            using Bitmap scaled = Resize(image, w, h);

            byte[] png = Save(scaled, ImageFormat.Png, null);
            if (png.Length <= SparkClient.MaxImageBytes)
            {
                return (png, "image/png");
            }

            byte[] jpeg = Save(scaled, ImageFormat.Jpeg, 85L);
            if (jpeg.Length <= SparkClient.MaxImageBytes)
            {
                return (jpeg, "image/jpeg");
            }

            scale *= 0.7;
        }

        throw new SparkException(null, "Der Ausschnitt ist zu groß. Bitte einen kleineren Bereich wählen.");
    }

    private static Bitmap Resize(Bitmap image, int w, int h)
    {
        var result = new Bitmap(w, h, PixelFormat.Format24bppRgb);
        using Graphics g = Graphics.FromImage(result);
        g.InterpolationMode = w == image.Width ? InterpolationMode.NearestNeighbor : InterpolationMode.HighQualityBicubic;
        g.PixelOffsetMode = PixelOffsetMode.Half;
        g.DrawImage(image, new Rectangle(0, 0, w, h));
        return result;
    }

    private static byte[] Save(Bitmap bitmap, ImageFormat format, long? quality)
    {
        using var ms = new MemoryStream();
        if (quality is { } q && ImageCodecInfo.GetImageEncoders().FirstOrDefault(c => c.FormatID == format.Guid) is { } codec)
        {
            using var parameters = new EncoderParameters(1);
            parameters.Param[0] = new EncoderParameter(System.Drawing.Imaging.Encoder.Quality, q);
            bitmap.Save(ms, codec, parameters);
        }
        else
        {
            bitmap.Save(ms, format);
        }

        return ms.ToArray();
    }
}

/// <summary>
/// Kleines Fenster nach der Auswahl (Entwurf A): Vorschau, optionale Frage, drei Chips Erklären / Text herauslesen /
/// Übersetzen. Ein Klick auf einen Chip schickt ab (Enter = Erklären), Esc bricht ab.
/// </summary>
internal sealed class ScreenAskForm : ThemedForm
{
    private readonly Bitmap _image;
    private readonly TextBox _question = new() { MaxLength = 500, PlaceholderText = "Frage (optional)", AccessibleName = "Frage zum Ausschnitt" };
    private readonly RoundedHost _questionHost;
    private readonly TLabel _status = new(TextRole.SmallMuted);
    private readonly DictateMic? _mic;
    private readonly SparkButton _explain = new(ButtonKind.Chip, "Erklären") { Checked = true };
    private readonly SparkButton _text = new(ButtonKind.Chip, "Text herauslesen");
    private readonly SparkButton _translate = new(ButtonKind.Chip, "Übersetzen");
    private readonly Rectangle _near;

    private Rectangle _face;
    private Rectangle _title;
    private Rectangle _preview;

    public ScreenAskForm(Bitmap image, Rectangle near, Dictation? dictation = null)
    {
        _image = image;
        _near = near;
        _questionHost = new RoundedHost(_question);
        _mic = dictation is null ? null : new DictateMic(_questionHost, dictation, SetStatus);

        Text = "Spark-Begleiter – Bildschirm fragen";
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        MinimizeBox = false;
        TopMost = true;
        ShowInTaskbar = true;
        StartPosition = FormStartPosition.Manual;
        KeyPreview = true;

        Controls.AddRange(new Control[] { _questionHost, _status, _explain, _text, _translate });
        _questionHost.TabIndex = 0;
        _explain.TabIndex = 1;
        _text.TabIndex = 2;
        _translate.TabIndex = 3;

        _explain.Click += (_, _) => Choose("erklaeren");
        _text.Click += (_, _) => Choose("text");
        _translate.Click += (_, _) => Choose("uebersetzen");
        _question.KeyDown += (_, e) =>
        {
            if (e.KeyCode == Keys.Enter)
            {
                e.SuppressKeyPress = true;
                Choose("erklaeren");
            }
        };

        Point anchor = new(near.Left, near.Bottom);
        Rectangle area = Screen.FromPoint(anchor).WorkingArea;
        int dpi = Dwm.DpiAt(anchor);
        int w = Draw.Scale(400, dpi);
        int h = Draw.Scale(330, dpi);
        int x = Math.Clamp(near.Left, area.Left, Math.Max(area.Left, area.Right - w));
        int y = near.Bottom + Draw.Scale(10, dpi) + h <= area.Bottom ? near.Bottom + Draw.Scale(10, dpi)
            : near.Top - Draw.Scale(10, dpi) - h >= area.Top ? near.Top - Draw.Scale(10, dpi) - h
            : area.Top + ((area.Height - h) / 2);
        Location = new Point(x, y);
        Size = new Size(w, h);
    }

    /// <summary>Gewählt: what (erklaeren | text | uebersetzen) und die Frage.</summary>
    public (string What, string Question)? Choice { get; private set; }

    protected override void LayoutContent()
    {
        int pad = S(14);
        int w = S(400) - S(2);
        int inner = w - (2 * pad);
        int y = pad;

        int face = S(28);
        _face = new Rectangle(pad, y, face, face);
        _title = new Rectangle(pad + Face.Lead(face, S(8)), y, inner - Face.Lead(face, S(8)), face);
        y += face + S(10);

        int maxH = S(150);
        double scale = Math.Min(1.0, Math.Min(inner / (double)_image.Width, maxH / (double)_image.Height));
        int pw = Math.Max(1, (int)(_image.Width * scale));
        int ph = Math.Max(1, (int)(_image.Height * scale));
        _preview = new Rectangle(pad + ((inner - pw) / 2), y, pw, ph);
        y += ph + S(12);

        _questionHost.Bounds = new Rectangle(pad, y, inner, S(36));
        y += S(36) + S(10);
        int statusH = _status.Fit(pad, y, inner);
        if (statusH > 0)
        {
            y += statusH + S(8);
        }

        int x = pad;
        foreach (SparkButton chip in new[] { _explain, _text, _translate })
        {
            Size size = chip.Preferred();
            chip.Bounds = new Rectangle(x, y, size.Width, size.Height);
            x += size.Width + S(6);
        }

        y += _explain.Height + pad;
        ClientSize = new Size(w, y);
    }

    protected override void PaintContent(Graphics g)
    {
        Face.DrawHeader(g, _face, P);
        Draw.Text(g, "Bildschirm fragen", F(10.5f, FontStyle.Bold), _title, P.Fg);
        g.InterpolationMode = InterpolationMode.HighQualityBicubic;
        g.DrawImage(_image, _preview);
        using var pen = new Pen(P.Line);
        g.DrawRectangle(pen, _preview);
    }

    protected override void OnLoad(EventArgs e)
    {
        base.OnLoad(e);
        ActiveControl = _question;
    }

    protected override void OnThemeApplied() => _mic?.Refresh();

    private void SetStatus(string text, bool error)
    {
        _status.Text = text;
        _status.Role = error ? TextRole.Error : TextRole.SmallMuted;
        _status.ApplyTheme(DeviceDpi);
        if (IsHandleCreated)
        {
            LayoutContent();
            Invalidate(true);
        }
    }

    private void Choose(string what)
    {
        if (_mic is { Busy: true })
        {
            SetStatus("Bitte zuerst die Aufnahme beenden (■).", true);
            return;
        }

        Choice = (what, _question.Text.Trim());
        Close();
    }

    protected override bool ProcessCmdKey(ref Message msg, Keys keyData)
    {
        if (keyData == Keys.Escape)
        {
            Close();
            return true;
        }

        return base.ProcessCmdKey(ref msg, keyData);
    }

    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        _mic?.Dispose();
        base.OnFormClosing(e);
    }
}
