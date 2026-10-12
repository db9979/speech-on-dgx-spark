using System.Drawing.Drawing2D;

namespace SparkBegleiter;

/// <summary>Steuerelement, das sich an Thema und DPI seines Fensters anpasst.</summary>
internal interface IThemed
{
    void ApplyTheme(int dpi);
}

/// <summary>
/// Grundlage der Fenster in Entwurf A: Karte als Hintergrund, 6-px-Farbverlauf oben, dunkle Titelleiste
/// im dunklen Modus, Schriften und Abstände je Bildschirm-DPI (Per-Monitor V2). Die Anordnung macht
/// jedes Fenster selbst in <see cref="LayoutContent"/> (in 96-DPI-Maßen über <see cref="S"/>).
/// </summary>
internal abstract class ThemedForm : Form
{
    protected ThemedForm()
    {
        AutoScaleMode = AutoScaleMode.None;
        SetStyle(ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint | ControlStyles.ResizeRedraw | ControlStyles.UserPaint, true);
        Icon = AppIcon.Icon;
        BackColor = Theme.Current.Card;
        ForeColor = Theme.Current.Fg;
        Theme.Changed += OnThemeChanged;
    }

    protected static Palette P => Theme.Current;

    /// <summary>Farbverlauf oben zeigen.</summary>
    protected virtual bool HasBar => true;

    /// <summary>Runde Ecken über DWM (für randlose Fenster; normale Fenster rundet Windows 11 ohnehin).</summary>
    protected virtual bool RoundCorners => false;

    protected int BarHeight => HasBar ? S(6) : 0;

    /// <summary>Wert in 96-DPI-Pixeln auf die DPI dieses Fensters umrechnen.</summary>
    protected int S(float value) => Draw.Scale(value, DeviceDpi);

    protected Font F(float points, FontStyle style = FontStyle.Regular) => Theme.UiFont(DeviceDpi, points, style);

    protected override void OnHandleCreated(EventArgs e)
    {
        base.OnHandleCreated(e);
        Dwm.Apply(Handle, P, RoundCorners);
        RefreshTheme();
    }

    protected override void OnLoad(EventArgs e)
    {
        base.OnLoad(e);
        RefreshTheme();
    }

    protected override void OnDpiChanged(DpiChangedEventArgs e)
    {
        base.OnDpiChanged(e);
        RefreshTheme();
    }

    private void OnThemeChanged(object? sender, EventArgs e)
    {
        if (IsHandleCreated && !IsDisposed)
        {
            Dwm.Apply(Handle, P, RoundCorners);
            RefreshTheme();
        }
    }

    /// <summary>Farben, Schriften und Anordnung neu setzen (nach Themen- oder DPI-Wechsel).</summary>
    protected void RefreshTheme()
    {
        Font = F(9);
        BackColor = P.Card;
        ForeColor = P.Fg;
        ApplyTo(Controls, DeviceDpi);
        OnThemeApplied();
        LayoutContent();
        Invalidate(true);
    }

    private static void ApplyTo(Control.ControlCollection controls, int dpi)
    {
        foreach (Control c in controls)
        {
            if (c is IThemed themed)
            {
                themed.ApplyTheme(dpi);
            }

            ApplyTo(c.Controls, dpi);
        }
    }

    protected virtual void OnThemeApplied()
    {
    }

    protected abstract void LayoutContent();

    protected override void OnResize(EventArgs e)
    {
        base.OnResize(e);
        if (IsHandleCreated)
        {
            LayoutContent();
            Invalidate();
        }
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        Graphics g = e.Graphics;
        g.Clear(P.Card);
        if (HasBar)
        {
            Draw.Bar(g, new Rectangle(0, 0, ClientSize.Width, BarHeight), P);
        }

        PaintContent(g);
    }

    protected virtual void PaintContent(Graphics g)
    {
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            Theme.Changed -= OnThemeChanged;
        }

        base.Dispose(disposing);
    }
}

internal enum ButtonKind
{
    /// <summary>Normaler Knopf: Karte, Rand.</summary>
    Secondary,

    /// <summary>Hauptknopf: Akzent-Verlauf, weiße Schrift.</summary>
    Primary,

    /// <summary>Gelbe Kaffee-Pille.</summary>
    Coffee,

    /// <summary>Zeile im Tray-Fenster: Symbol, Text, Tastenkürzel-Chip.</summary>
    Item,

    /// <summary>Auswahl-Chip (gewählt = Akzent).</summary>
    Chip,

    /// <summary>Runder Symbolknopf (Mikrofon).</summary>
    Round,
}

/// <summary>Selbst gezeichneter Knopf in den Formen des Entwurfs; Tastatur und Barrierefreiheit wie ein Button.</summary>
internal sealed class SparkButton : Button, IThemed
{
    private bool _hover;
    private bool _pressed;
    private bool _checked;
    private int _dpi = 96;

    public SparkButton(ButtonKind kind, string text = "")
    {
        Kind = kind;
        Text = text;
        SetStyle(ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
        FlatStyle = FlatStyle.Flat;
        FlatAppearance.BorderSize = 0;
        UseMnemonic = false;
        Cursor = Cursors.Hand;
        AccessibleName = text;
    }

    public ButtonKind Kind { get; }

    public Glyph Glyph { get; set; }

    /// <summary>Tastenkürzel rechts in der Zeile (nur <see cref="ButtonKind.Item"/>).</summary>
    public string? Hotkey { get; set; }

    /// <summary>Rot (Mein Notaus).</summary>
    public bool Danger { get; set; }

    /// <summary>Gewählt (Chip) bzw. aktiv (Mikrofon nimmt auf).</summary>
    public bool Checked
    {
        get => _checked;
        set
        {
            _checked = value;
            AccessibleRole = Kind == ButtonKind.Chip ? AccessibleRole.RadioButton : AccessibleRole.PushButton;
            Invalidate();
        }
    }

    /// <summary>Hintergrund hinter den runden Ecken (sonst der des Elternelements).</summary>
    public Color? Surface { get; set; }

    public float FontSize { get; set; } = 9.5f;

    [System.Diagnostics.CodeAnalysis.AllowNull]
    public override string Text
    {
        get => base.Text;
        set
        {
            base.Text = value;
            AccessibleName = value;
            Invalidate();
        }
    }

    public void ApplyTheme(int dpi)
    {
        _dpi = dpi;
        FontStyle style = Kind is ButtonKind.Primary or ButtonKind.Coffee ? FontStyle.Bold : FontStyle.Regular;
        Font = Theme.UiFont(dpi, Kind is ButtonKind.Coffee or ButtonKind.Chip ? FontSize - 0.5f : FontSize, style);
        Invalidate();
    }

    private int S(float v) => Draw.Scale(v, _dpi);

    /// <summary>Gewünschte Größe bei der aktuellen DPI.</summary>
    public Size Preferred()
    {
        if (Kind == ButtonKind.Round)
        {
            return new Size(S(34), S(34));
        }

        Size t = Draw.Measure(Text, Font);
        int glyph = Glyph != Glyph.None && Kind != ButtonKind.Item ? S(16 + 6) : 0;
        return Kind switch
        {
            ButtonKind.Coffee => new Size(t.Width + glyph + S(20), Math.Max(S(28), t.Height + S(10))),
            ButtonKind.Chip => new Size(t.Width + glyph + S(20), Math.Max(S(28), t.Height + S(8))),
            ButtonKind.Item => new Size(t.Width + S(80), S(44)),
            _ => new Size(t.Width + glyph + S(24), Math.Max(S(32), t.Height + S(14))),
        };
    }

    public override Size GetPreferredSize(Size proposedSize) => Preferred();

    protected override void OnMouseEnter(EventArgs e)
    {
        _hover = true;
        Invalidate();
        base.OnMouseEnter(e);
    }

    protected override void OnMouseLeave(EventArgs e)
    {
        _hover = false;
        _pressed = false;
        Invalidate();
        base.OnMouseLeave(e);
    }

    protected override void OnMouseDown(MouseEventArgs mevent)
    {
        if (mevent.Button == MouseButtons.Left)
        {
            _pressed = true;
            Invalidate();
        }

        base.OnMouseDown(mevent);
    }

    protected override void OnMouseUp(MouseEventArgs mevent)
    {
        _pressed = false;
        Invalidate();
        base.OnMouseUp(mevent);
    }

    protected override void OnGotFocus(EventArgs e)
    {
        Invalidate();
        base.OnGotFocus(e);
    }

    protected override void OnLostFocus(EventArgs e)
    {
        Invalidate();
        base.OnLostFocus(e);
    }

    protected override void OnEnabledChanged(EventArgs e)
    {
        Invalidate();
        base.OnEnabledChanged(e);
    }

    protected override void OnPaint(PaintEventArgs pevent)
    {
        Graphics g = pevent.Graphics;
        Palette p = Theme.Current;
        g.Clear(Surface ?? Parent?.BackColor ?? p.Card);
        Draw.HighQuality(g);

        var r = new RectangleF(0, 0, Width, Height);
        bool focus = Focused && ShowFocusCues;
        switch (Kind)
        {
            case ButtonKind.Primary:
                PaintPrimary(g, r, p);
                break;
            case ButtonKind.Coffee:
                PaintCoffee(g, r, p);
                break;
            case ButtonKind.Item:
                PaintItem(g, r, p, focus);
                break;
            case ButtonKind.Chip:
                PaintChip(g, r, p);
                break;
            case ButtonKind.Round:
                PaintRound(g, r, p);
                break;
            default:
                PaintSecondary(g, r, p);
                break;
        }

        if (focus && Kind != ButtonKind.Item)
        {
            float radius = Kind is ButtonKind.Coffee or ButtonKind.Chip or ButtonKind.Round ? r.Height / 2f : S(9);
            Draw.StrokeRound(g, Kind == ButtonKind.Primary ? p.Fg : p.Accent, r, radius, Math.Max(2f, S(2)));
        }
    }

    private Color TextColor(Color normal) => Enabled ? normal : Theme.Current.Muted;

    private void PaintSecondary(Graphics g, RectangleF r, Palette p)
    {
        Color back = !Enabled ? p.Card : _pressed ? p.Line : _hover ? p.Soft : p.Card;
        Draw.FillRound(g, back, r, S(9));
        Draw.StrokeRound(g, p.Line, r, S(9));
        PaintLabel(g, r, TextColor(Danger ? p.Bad : p.Fg), p.Accent);
    }

    private void PaintPrimary(Graphics g, RectangleF r, Palette p)
    {
        using (GraphicsPath path = Draw.Round(r, S(9)))
        {
            using Brush brush = Draw.AccentBrush(r, p, 45f);
            g.FillPath(brush, path);
            int overlay = !Enabled ? 110 : _pressed ? 40 : _hover ? 28 : 0;
            if (overlay > 0)
            {
                Color tint = !Enabled ? p.Card : _pressed ? Color.Black : Color.White;
                using var veil = new SolidBrush(Color.FromArgb(overlay, tint));
                g.FillPath(veil, path);
            }
        }

        PaintLabel(g, r, p.OnAccent, p.OnAccent);
    }

    private void PaintCoffee(Graphics g, RectangleF r, Palette p)
    {
        Color back = _pressed ? Palette.Mix(p.Coffee, Color.Black, 0.12f) : _hover ? Palette.Mix(p.Coffee, Color.Black, 0.06f) : p.Coffee;
        Draw.FillRound(g, back, r, r.Height / 2f);
        if (p.HighContrast)
        {
            Draw.StrokeRound(g, p.Fg, r, r.Height / 2f);
        }

        PaintLabel(g, r, p.CoffeeFg, p.CoffeeFg);
    }

    private void PaintChip(Graphics g, RectangleF r, Palette p)
    {
        if (_checked)
        {
            Draw.FillRound(g, p.Accent, r, r.Height / 2f);
            PaintLabel(g, r, Enabled ? p.OnAccent : Palette.Mix(p.OnAccent, p.Accent, 0.4f), p.OnAccent);
        }
        else
        {
            Draw.FillRound(g, _hover && Enabled ? p.Soft : p.Card, r, r.Height / 2f);
            Draw.StrokeRound(g, p.Line, r, r.Height / 2f);
            PaintLabel(g, r, TextColor(p.Fg), p.Accent);
        }
    }

    private void PaintRound(Graphics g, RectangleF r, Palette p)
    {
        var circle = RectangleF.Inflate(r, -0.5f, -0.5f);
        using (var fill = new SolidBrush(_checked ? p.Bad : _hover ? p.Line : p.Soft))
        {
            g.FillEllipse(fill, circle);
        }

        if (!_checked)
        {
            using var pen = new Pen(p.Line, 1f);
            g.DrawEllipse(pen, circle);
        }

        float gs = S(16);
        Glyphs.Draw(g, _checked ? Glyph.Stop : Glyph, new RectangleF((r.Width - gs) / 2f, (r.Height - gs) / 2f, gs, gs),
            _checked ? Color.White : Enabled ? p.Accent : p.Muted);
    }

    private void PaintItem(Graphics g, RectangleF r, Palette p, bool focus)
    {
        if ((_hover || focus || _pressed) && Enabled)
        {
            Draw.FillRound(g, _pressed ? p.Line : p.Soft, r, S(9));
        }

        if (focus)
        {
            Draw.StrokeRound(g, p.Accent, r, S(9), Math.Max(1.5f, S(1.5f)));
        }

        int box = S(28);
        var boxRect = new RectangleF(S(10), (r.Height - box) / 2f, box, box);
        Draw.FillRound(g, (_hover || focus) && Enabled ? p.Card : p.Soft, boxRect, S(8));
        float gs = S(16);
        Glyphs.Draw(g, Glyph, new RectangleF(boxRect.X + ((box - gs) / 2f), boxRect.Y + ((box - gs) / 2f), gs, gs),
            !Enabled ? p.Muted : Danger ? p.Bad : p.Accent);

        int x = S(10) + box + S(10);
        int right = Width - S(10);
        if (!string.IsNullOrEmpty(Hotkey))
        {
            Font mono = Theme.MonoFont(_dpi, 8f);
            Size k = Draw.KbdSize(Hotkey, mono, _dpi);
            var kr = new Rectangle(right - k.Width, (Height - k.Height) / 2, k.Width, k.Height);
            Draw.Kbd(g, kr, Hotkey, mono, p, _dpi);
            right = kr.X - S(8);
        }

        Draw.Text(g, Text, Font, new Rectangle(x, 0, Math.Max(0, right - x), Height), !Enabled ? p.Muted : Danger ? p.Bad : p.Fg);
    }

    /// <summary>Text (und optional Symbol) mittig.</summary>
    private void PaintLabel(Graphics g, RectangleF r, Color color, Color glyphColor)
    {
        Size t = Draw.Measure(Text, Font);
        int gs = Glyph != Glyph.None ? S(16) : 0;
        int gap = gs > 0 && Text.Length > 0 ? S(6) : 0;
        int total = gs + gap + t.Width;
        int x = (int)Math.Round((r.Width - total) / 2f);
        if (gs > 0)
        {
            Glyphs.Draw(g, Glyph, new RectangleF(x, (r.Height - gs) / 2f, gs, gs), glyphColor);
        }

        Draw.Text(g, Text, Font, new Rectangle(x + gs + gap, 0, Math.Max(1, (int)r.Width - (x + gs + gap)), (int)r.Height), color);
    }
}

internal enum TextRole
{
    Normal,
    Muted,
    Small,
    SmallMuted,
    Title,
    Heading,
    Error,
}

/// <summary>Beschriftung in den Farben und Größen des Entwurfs. Höhe setzt das Fenster (umbrechend).</summary>
internal sealed class TLabel : Label, IThemed
{
    public TLabel(TextRole role = TextRole.Normal, string text = "")
    {
        Role = role;
        Text = text;
        AutoSize = false;
        UseMnemonic = false;
        BackColor = Theme.Current.Card;
    }

    public TextRole Role { get; set; }

    // Ein Weg im Text („im Panel unter Ich → Begleiter“) ist ein Sprung-Link: Hand-Zeiger, Klick öffnet die Stelle (Wege.cs)
    protected override void OnTextChanged(EventArgs e)
    {
        base.OnTextChanged(e);
        Cursor = Wege.Find(Text) is null ? Cursors.Default : Cursors.Hand;
    }

    protected override void OnClick(EventArgs e)
    {
        base.OnClick(e);
        Wege.OpenFrom(Text);
    }

    /// <summary>Statt der Rolle eine eigene Farbe (z. B. Hinweis in Orange).</summary>
    public Color? CustomColor { get; set; }

    public void ApplyTheme(int dpi)
    {
        Palette p = Theme.Current;
        Font = Role switch
        {
            TextRole.Title => Theme.UiFont(dpi, 11f, FontStyle.Bold),
            TextRole.Heading => Theme.UiFont(dpi, 9.5f, FontStyle.Bold),
            TextRole.Small or TextRole.SmallMuted => Theme.UiFont(dpi, 8.5f),
            _ => Theme.UiFont(dpi, 9.5f),
        };
        BackColor = p.Card;
        ForeColor = CustomColor ?? Role switch
        {
            TextRole.Muted or TextRole.SmallMuted => p.Muted,
            TextRole.Error => p.Bad,
            _ => p.Fg,
        };
    }

    /// <summary>Breite setzen und die Höhe dem (umbrochenen) Text anpassen.</summary>
    public int Fit(int x, int y, int width)
    {
        int height = Text.Length == 0 ? 0 : Draw.TextHeight(Text, Font, width);
        Bounds = new Rectangle(x, y, width, height);
        Visible = height > 0;
        return height;
    }
}

/// <summary>Weiche, abgerundete Fläche mit Rand um ein randloses Textfeld (Akzent-Rand bei Fokus).</summary>
internal sealed class RoundedHost : Panel, IThemed
{
    private int _dpi = 96;

    public RoundedHost(Control inner)
    {
        Inner = inner;
        SetStyle(ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint | ControlStyles.ResizeRedraw | ControlStyles.UserPaint, true);
        if (inner is TextBoxBase box)
        {
            box.BorderStyle = BorderStyle.None;
        }

        Controls.Add(inner);
        inner.HandleCreated += (_, _) => Dwm.ScrollbarTheme(inner, Theme.Current.Dark);
        inner.Enter += (_, _) => Invalidate();
        inner.Leave += (_, _) => Invalidate();
        Cursor = Cursors.IBeam;
        Click += (_, _) => Inner.Focus();
    }

    public Control Inner { get; }

    /// <summary>Weicher Hintergrund (Standard) statt Karte.</summary>
    public bool SoftBack { get; set; } = true;

    public void ApplyTheme(int dpi)
    {
        _dpi = dpi;
        Palette p = Theme.Current;
        Color back = SoftBack ? p.Soft : p.Card;
        BackColor = p.Card;
        Inner.BackColor = back;
        Inner.ForeColor = p.Fg;
        Inner.Font = Theme.UiFont(dpi, 10f);
        Dwm.ScrollbarTheme(Inner, p.Dark);
        Padding = new Padding(Draw.Scale(10, dpi), Draw.Scale(7, dpi), Draw.Scale(6, dpi), Draw.Scale(7, dpi));
        PerformLayout();
        Invalidate();
    }

    protected override void OnLayout(LayoutEventArgs levent)
    {
        base.OnLayout(levent);
        Rectangle area = DisplayRectangle;
        if (Inner is TextBox { Multiline: false } single)
        {
            int h = single.PreferredHeight;
            Inner.Bounds = new Rectangle(area.X, area.Y + ((area.Height - h) / 2), area.Width, h);
        }
        else
        {
            Inner.Bounds = area;
        }
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        Graphics g = e.Graphics;
        Palette p = Theme.Current;
        g.Clear(Parent?.BackColor ?? p.Card);
        Draw.HighQuality(g);
        var r = new RectangleF(0, 0, Width, Height);
        float radius = Draw.Scale(10, _dpi);
        Draw.FillRound(g, SoftBack ? p.Soft : p.Card, r, radius);
        bool focus = Inner.ContainsFocus;
        Draw.StrokeRound(g, focus ? p.Accent : p.Line, r, radius, focus ? Math.Max(1.5f, Draw.Scale(1.5f, _dpi)) : 1f);
    }
}

/// <summary>Schalter (an/aus) statt Häkchen; Leertaste und Klick wie eine CheckBox.</summary>
internal sealed class ToggleSwitch : CheckBox, IThemed
{
    private int _dpi = 96;

    public ToggleSwitch(string text)
    {
        Text = text;
        SetStyle(ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
        AutoSize = false;
        UseMnemonic = false;
        Cursor = Cursors.Hand;
    }

    public void ApplyTheme(int dpi)
    {
        _dpi = dpi;
        Font = Theme.UiFont(dpi, 9.5f);
        Invalidate();
    }

    private int S(float v) => Draw.Scale(v, _dpi);

    public int Fit(int x, int y, int width)
    {
        int textWidth = Math.Max(1, width - S(34 + 10));
        int h = Math.Max(S(22), Draw.TextHeight(Text, Font, textWidth));
        Bounds = new Rectangle(x, y, width, h);
        return h;
    }

    protected override void OnCheckedChanged(EventArgs e)
    {
        Invalidate();
        base.OnCheckedChanged(e);
    }

    protected override void OnGotFocus(EventArgs e)
    {
        Invalidate();
        base.OnGotFocus(e);
    }

    protected override void OnLostFocus(EventArgs e)
    {
        Invalidate();
        base.OnLostFocus(e);
    }

    protected override void OnPaint(PaintEventArgs pevent)
    {
        Graphics g = pevent.Graphics;
        Palette p = Theme.Current;
        g.Clear(Parent?.BackColor ?? p.Card);
        Draw.HighQuality(g);

        var track = new RectangleF(S(1), S(2), S(34), S(18));
        Color trackColor = !Enabled ? p.Line : Checked ? p.Accent : p.Line;
        Draw.FillRound(g, trackColor, track, track.Height / 2f);
        if (!Checked)
        {
            Draw.StrokeRound(g, p.Muted, track, track.Height / 2f);
        }

        float knob = S(12);
        float kx = Checked ? track.Right - knob - S(3) : track.X + S(3);
        using (var brush = new SolidBrush(Checked ? p.OnAccent : p.Muted))
        {
            g.FillEllipse(brush, kx, track.Y + ((track.Height - knob) / 2f), knob, knob);
        }

        if (Focused && ShowFocusCues)
        {
            Draw.StrokeRound(g, p.Fg, RectangleF.Inflate(track, S(2), S(2)), (track.Height / 2f) + S(2), Math.Max(1.5f, S(1.5f)));
        }

        int tx = S(34 + 10);
        TextRenderer.DrawText(g, Text, Font, new Rectangle(tx, 0, Math.Max(1, Width - tx), Height),
            Enabled ? p.Fg : p.Muted, Draw.Wrap | TextFormatFlags.VerticalCenter);
    }
}

/// <summary>Das Spark-Gesicht als Steuerelement.</summary>
internal sealed class FaceBox : Control, IThemed
{
    public FaceBox()
    {
        SetStyle(ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint | ControlStyles.ResizeRedraw | ControlStyles.UserPaint, true);
        TabStop = false;
        AccessibleRole = AccessibleRole.Graphic;
        AccessibleName = "Spark-Gesicht";
    }

    public void ApplyTheme(int dpi) => Invalidate();

    protected override void OnPaint(PaintEventArgs e)
    {
        e.Graphics.Clear(Parent?.BackColor ?? Theme.Current.Card);
        Face.Draw(e.Graphics, new RectangleF(0, 0, Width, Height), Theme.Current);
    }
}

/// <summary>Zustands-Pille als Steuerelement (z. B. "Neueste Version").</summary>
internal sealed class StatusPill : Control, IThemed
{
    private int _dpi = 96;

    public StatusPill()
    {
        SetStyle(ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint | ControlStyles.ResizeRedraw | ControlStyles.UserPaint, true);
        TabStop = false;
        AccessibleRole = AccessibleRole.StaticText;
    }

    /// <summary>Farbe des Punkts aus der Palette.</summary>
    public Func<Palette, Color> DotColor { get; set; } = p => p.Ok;

    [System.Diagnostics.CodeAnalysis.AllowNull]
    public override string Text
    {
        get => base.Text;
        set
        {
            base.Text = value;
            AccessibleName = value;
            Invalidate();
        }
    }

    public void ApplyTheme(int dpi)
    {
        _dpi = dpi;
        Font = Theme.UiFont(dpi, 8.5f, FontStyle.Bold);
        Invalidate();
    }

    public Size Preferred() => Draw.PillSize(Text, Font, _dpi);

    protected override void OnPaint(PaintEventArgs e)
    {
        Palette p = Theme.Current;
        e.Graphics.Clear(Parent?.BackColor ?? p.Card);
        Draw.HighQuality(e.Graphics);
        Draw.Pill(e.Graphics, new Rectangle(0, 0, Width, Height), Text, Font, DotColor(p), p, _dpi);
    }
}
