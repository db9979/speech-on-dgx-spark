using System.Drawing.Drawing2D;
using Microsoft.Win32;

namespace SparkBegleiter;

/// <summary>
/// Die Farben von „Klar 2 · Systemstil“ (Redesign Stufe 9, Werte wie <c>app/panel/static/tokens.css</c>): neutrale
/// Grautöne und ein Akzent (Blau), hell und dunkel wie im Panel, keine Verläufe. Bei hohem Kontrast kommen die
/// Systemfarben von Windows. Jede Farbe der Fenster steht hier (test_design_tokens.Begleiter).
/// </summary>
/// <param name="Soft">Leiste und weicher Grund (Chips, Tastenkürzel, Zustand): Token <c>--side</c>.</param>
/// <param name="Faint">Platzhalter und Pfeile: <c>--faint</c>.</param>
/// <param name="OkText">Text in Grün, Gelb, Rot und Akzent auf hellem Grund (mindestens 4,5 : 1): <c>--okt --warnt --badt --acct</c>.</param>
internal sealed record Palette(
    bool Dark,
    bool HighContrast,
    Color Bg,
    Color Card,
    Color Fg,
    Color Muted,
    Color Line,
    Color Accent,
    Color Ok,
    Color Warn,
    Color Bad,
    Color Visor,
    Color Soft,
    Color Faint,
    Color OkText,
    Color WarnText,
    Color BadText,
    Color AccentText,
    Color InsBg,
    Color InsFg,
    Color DelBg,
    Color DelFg,
    Color Coffee,
    Color CoffeeFg,
    Color OnAccent)
{
    public static readonly Palette Light = new(
        Dark: false, HighContrast: false,
        Bg: Hex(0xF5F5F7), Card: Hex(0xFFFFFF), Fg: Hex(0x1D1D1F), Muted: Hex(0x6E6E73), Line: Hex(0xE2E2E7),
        Accent: Hex(0x0071E3), Ok: Hex(0x28A745), Warn: Hex(0xE08600), Bad: Hex(0xE5342B),
        Visor: Hex(0x151A2E), Soft: Hex(0xEFEFF2), Faint: Hex(0xA1A1A6),
        OkText: Hex(0x1F7A35), WarnText: Hex(0xA35A00), BadText: Hex(0xC4271F), AccentText: Hex(0x0060C0),
        InsBg: Hex(0xDCFCE7), InsFg: Hex(0x166534), DelBg: Hex(0xFEE2E2), DelFg: Hex(0x991B1B),
        Coffee: Hex(0xFFDD00), CoffeeFg: Hex(0x1F1A00), OnAccent: Hex(0xFFFFFF));

    public static readonly Palette DarkTheme = new(
        Dark: true, HighContrast: false,
        Bg: Hex(0x161618), Card: Hex(0x242426), Fg: Hex(0xF5F5F7), Muted: Hex(0xA1A1A6), Line: Hex(0x38383B),
        Accent: Hex(0x0A84FF), Ok: Hex(0x32D74B), Warn: Hex(0xFF9F0A), Bad: Hex(0xFF453A),
        Visor: Hex(0x070912), Soft: Hex(0x1F1F21), Faint: Hex(0x6E6E73),
        OkText: Hex(0x32D74B), WarnText: Hex(0xFFB340), BadText: Hex(0xFF6961), AccentText: Hex(0x4DA3FF),
        InsBg: Hex(0x123524), InsFg: Hex(0x86EFAC), DelBg: Hex(0x3B1717), DelFg: Hex(0xFCA5A5),
        Coffee: Hex(0xFFDD00), CoffeeFg: Hex(0x1F1A00), OnAccent: Hex(0xFFFFFF));

    /// <summary>Farbe des Augen und des Lächelns im Gesicht (in beiden Themen gleich).</summary>
    public static readonly Color Eye = Hex(0xBFF6FF);

    /// <summary>Text auf farbigem Grund (Akzent, Rot, Bild), in hell und dunkel gleich: Token <c>--on-acc</c>.</summary>
    public static readonly Color OnColor = Hex(0xFFFFFF);

    /// <summary>Schwarz für Schleier und Abdunkeln (immer mit Deckkraft, nie als Fläche).</summary>
    public static readonly Color Shade = Hex(0x000000);

    /// <summary>Die schwebenden Anzeigen (Aufnahme, Diktat, Bildschirmauswahl) liegen immer auf dunklem Grund.</summary>
    public static readonly Color HudBack = Light.Visor;

    public static Color HudText => DarkTheme.Fg;

    public static Color HudMuted => DarkTheme.Muted;

    public static Color HudLine => DarkTheme.Line;

    /// <summary>Systemfarben für hohen Kontrast (keine eigenen Farbtöne).</summary>
    public static Palette FromSystem() => new(
        Dark: SystemColors.Window.GetBrightness() < 0.5f, HighContrast: true,
        Bg: SystemColors.Window, Card: SystemColors.Window, Fg: SystemColors.WindowText, Muted: SystemColors.GrayText,
        Line: SystemColors.WindowText, Accent: SystemColors.Highlight,
        Ok: SystemColors.WindowText, Warn: SystemColors.WindowText, Bad: SystemColors.WindowText,
        Visor: SystemColors.WindowText, Soft: SystemColors.Window, Faint: SystemColors.GrayText,
        OkText: SystemColors.WindowText, WarnText: SystemColors.WindowText, BadText: SystemColors.WindowText, AccentText: SystemColors.Highlight,
        InsBg: SystemColors.Window, InsFg: SystemColors.WindowText, DelBg: SystemColors.Window, DelFg: SystemColors.GrayText,
        Coffee: SystemColors.ButtonFace, CoffeeFg: SystemColors.ControlText, OnAccent: SystemColors.HighlightText);

    public static Color Hex(int rgb) => Color.FromArgb(0xFF, (rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF);

    /// <summary>Mischung wie CSS color-mix: <paramref name="amount"/> Anteil von <paramref name="b"/>.</summary>
    public static Color Mix(Color a, Color b, float amount)
    {
        float t = Math.Clamp(amount, 0f, 1f);
        return Color.FromArgb(
            (int)Math.Round(a.R + ((b.R - a.R) * t)),
            (int)Math.Round(a.G + ((b.G - a.G) * t)),
            (int)Math.Round(a.B + ((b.B - a.B) * t)));
    }

    /// <summary>Hintergrund des Update-Hinweises: 10 % Akzent auf der Karte.</summary>
    public Color BannerBack => HighContrast ? Card : Mix(Card, Accent, 0.10f);

    /// <summary>Rand des Update-Hinweises: 35 % Akzent auf der Linienfarbe.</summary>
    public Color BannerLine => HighContrast ? Line : Mix(Line, Accent, 0.35f);
}

/// <summary>
/// Hell oder dunkel nach der Windows-Einstellung "App-Modus" (Registry AppsUseLightTheme), hoher Kontrast
/// nach der Systemeinstellung. Ändert sich das, wird <see cref="Changed"/> ausgelöst.
/// </summary>
internal static class Theme
{
    private const string PersonalizeKey = @"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize";

    private static readonly Dictionary<(int Dpi, float Pt, FontStyle Style, bool Mono), Font> Fonts = new();
    private static Palette? _current;
    private static Palette? _taskbar;
    private static string? _family;
    private static string? _monoFamily;
    private static bool _watching;

    /// <summary>Farben für die Fenster des Begleiters.</summary>
    public static Palette Current => _current ??= Load(apps: true);

    /// <summary>Farben passend zur Taskleiste (SystemUsesLightTheme) – für das Symbol im Infobereich.</summary>
    public static Palette Taskbar => _taskbar ??= Load(apps: false);

    /// <summary>Hell/dunkel oder hoher Kontrast hat sich geändert.</summary>
    public static event EventHandler? Changed;

    public static void Watch()
    {
        if (!_watching)
        {
            _watching = true;
            SystemEvents.UserPreferenceChanged += OnUserPreferenceChanged;
        }
    }

    public static void Unwatch()
    {
        if (_watching)
        {
            _watching = false;
            SystemEvents.UserPreferenceChanged -= OnUserPreferenceChanged;
        }
    }

    private static void OnUserPreferenceChanged(object? sender, UserPreferenceChangedEventArgs e)
    {
        Palette apps = Load(apps: true);
        Palette bar = Load(apps: false);
        if (apps != _current || bar != _taskbar)
        {
            _current = apps;
            _taskbar = bar;
            Changed?.Invoke(null, EventArgs.Empty);
        }
    }

    private static Palette Load(bool apps)
    {
        if (SystemInformation.HighContrast)
        {
            return Palette.FromSystem();
        }

        return ReadLight(apps ? "AppsUseLightTheme" : "SystemUsesLightTheme") ? Palette.Light : Palette.DarkTheme;
    }

    /// <summary>Fehlt der Wert (älteres Windows), gilt hell.</summary>
    private static bool ReadLight(string valueName)
    {
        try
        {
            using RegistryKey? key = Registry.CurrentUser.OpenSubKey(PersonalizeKey);
            return key?.GetValue(valueName) is not int value || value != 0;
        }
        catch (Exception ex) when (ex is System.Security.SecurityException or IOException or UnauthorizedAccessException)
        {
            return true;
        }
    }

    /// <summary>Systemschrift (Segoe UI Variable, sonst Segoe UI) in Pixeln für die DPI des Fensters.</summary>
    public static Font UiFont(int dpi, float points, FontStyle style = FontStyle.Regular) => GetFont(dpi, points, style, mono: false);

    /// <summary>Schrift für Tastenkürzel-Chips (Cascadia Mono, sonst Consolas).</summary>
    public static Font MonoFont(int dpi, float points) => GetFont(dpi, points, FontStyle.Regular, mono: true);

    private static Font GetFont(int dpi, float points, FontStyle style, bool mono)
    {
        var key = (dpi, points, style, mono);
        if (!Fonts.TryGetValue(key, out Font? font))
        {
            string family = mono
                ? _monoFamily ??= FirstInstalled("Cascadia Mono", "Consolas")
                : _family ??= FirstInstalled("Segoe UI Variable Text", "Segoe UI");
            font = new Font(family, points * Math.Max(dpi, 96) / 72f, style, GraphicsUnit.Pixel);
            Fonts[key] = font;
        }

        return font;
    }

    /// <summary>GDI+ ersetzt unbekannte Schriften still durch eine andere – daher am Namen prüfen.</summary>
    private static string FirstInstalled(string preferred, string fallback)
    {
        using var probe = new Font(preferred, 10f);
        return string.Equals(probe.Name, preferred, StringComparison.OrdinalIgnoreCase) ? preferred : fallback;
    }
}

/// <summary>Zeichenhilfen: abgerundete Rechtecke, Text, Pillen (keine Verläufe, keine Schatten: Klar 2).</summary>
internal static class Draw
{
    public const TextFormatFlags Line = TextFormatFlags.SingleLine | TextFormatFlags.NoPrefix | TextFormatFlags.EndEllipsis | TextFormatFlags.VerticalCenter;

    /// <summary>Radien der Tokens (<c>--r-ctl --r-item --r-box</c>): Knopf und Feld 6, Listenzeile 8, Gruppe und Karte 10.</summary>
    public const float RCtl = 6, RItem = 8, RBox = 10;

    public const TextFormatFlags Wrap = TextFormatFlags.WordBreak | TextFormatFlags.NoPrefix | TextFormatFlags.TextBoxControl;

    public static int Scale(float value, int dpi) => (int)Math.Round(value * dpi / 96f);

    public static void HighQuality(Graphics g)
    {
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.InterpolationMode = InterpolationMode.HighQualityBicubic;
        g.PixelOffsetMode = PixelOffsetMode.Half;
    }

    public static GraphicsPath Round(RectangleF r, float radius) => Round(r, radius, radius, radius, radius);

    /// <summary>Rechteck mit eigenen Radien je Ecke (oben links, oben rechts, unten rechts, unten links).</summary>
    public static GraphicsPath Round(RectangleF r, float tl, float tr, float br, float bl)
    {
        var path = new GraphicsPath();
        float max = Math.Min(r.Width, r.Height) / 2f;
        tl = Math.Clamp(tl, 0, max);
        tr = Math.Clamp(tr, 0, max);
        br = Math.Clamp(br, 0, max);
        bl = Math.Clamp(bl, 0, max);
        if (r.Width <= 0 || r.Height <= 0)
        {
            path.AddRectangle(r);
            return path;
        }

        Corner(path, r.X, r.Y, tl, 180);
        Corner(path, r.Right - (tr * 2), r.Y, tr, 270);
        Corner(path, r.Right - (br * 2), r.Bottom - (br * 2), br, 0);
        Corner(path, r.X, r.Bottom - (bl * 2), bl, 90);
        path.CloseFigure();
        return path;

        static void Corner(GraphicsPath p, float x, float y, float radius, float start)
        {
            if (radius <= 0.01f)
            {
                p.AddLine(x, y, x, y); // spitze Ecke
                return;
            }

            p.AddArc(x, y, radius * 2, radius * 2, start, 90);
        }
    }


    public static void FillRound(Graphics g, Color color, RectangleF r, float radius)
    {
        using var brush = new SolidBrush(color);
        using GraphicsPath path = Round(r, radius);
        g.FillPath(brush, path);
    }

    public static void StrokeRound(Graphics g, Color color, RectangleF r, float radius, float width = 1f)
    {
        using var pen = new Pen(color, width);
        RectangleF inner = RectangleF.Inflate(r, -width / 2f, -width / 2f);
        using GraphicsPath path = Round(inner, Math.Max(0, radius - (width / 2f)));
        g.DrawPath(pen, path);
    }

    public static void Text(Graphics g, string text, Font font, Rectangle r, Color color, TextFormatFlags flags = Line) =>
        TextRenderer.DrawText(g, text, font, r, color, flags);

    public static Size Measure(string text, Font font) =>
        TextRenderer.MeasureText(text, font, new Size(int.MaxValue, int.MaxValue), TextFormatFlags.SingleLine | TextFormatFlags.NoPrefix);

    public static int TextHeight(string text, Font font, int width) =>
        text.Length == 0 ? 0 : TextRenderer.MeasureText(text, font, new Size(Math.Max(1, width), 100000), Wrap).Height;

    /// <summary>Zustands-Pille wie im Panel: weiche Fläche, Rand, farbiger Punkt, kurzer Text.</summary>
    public static void Pill(Graphics g, Rectangle r, string text, Font font, Color dot, Palette p, int dpi)
    {
        FillRound(g, p.Soft, r, r.Height / 2f);
        StrokeRound(g, p.Line, r, r.Height / 2f);
        int d = Scale(8, dpi);
        int x = r.X + Scale(9, dpi);
        using (var brush = new SolidBrush(dot))
        {
            g.FillEllipse(brush, x, r.Y + ((r.Height - d) / 2f), d, d);
        }

        var textRect = new Rectangle(x + d + Scale(6, dpi), r.Y, r.Right - (x + d + Scale(6, dpi)) - Scale(8, dpi), r.Height);
        Text(g, text, font, textRect, p.Fg);
    }

    public static Size PillSize(string text, Font font, int dpi)
    {
        Size t = Measure(text, font);
        return new Size(t.Width + Scale(9 + 8 + 6 + 8, dpi), Math.Max(Scale(22, dpi), t.Height + Scale(6, dpi)));
    }

    /// <summary>Tastenkürzel-Chip (kbd): kleine Monospace-Schrift mit Rand.</summary>
    public static Size KbdSize(string text, Font font, int dpi)
    {
        Size t = Measure(text, font);
        return new Size(t.Width + Scale(12, dpi), t.Height + Scale(4, dpi));
    }

    public static void Kbd(Graphics g, Rectangle r, string text, Font font, Palette p, int dpi, Color? back = null, Color? fore = null, Color? border = null)
    {
        if (back is not { } b || b.A > 0)
        {
            FillRound(g, back ?? p.Soft, r, Scale(6, dpi));
        }

        StrokeRound(g, border ?? p.Line, r, Scale(6, dpi));
        Text(g, text, font, r, fore ?? p.Muted, Line | TextFormatFlags.HorizontalCenter);
    }
}

/// <summary>Fenster-Rahmen über DWM: dunkle Titelleiste, runde Ecken (Windows 11), Randfarbe.</summary>
internal static class Dwm
{
    public static void Apply(IntPtr hwnd, Palette p, bool round)
    {
        try
        {
            int dark = p.Dark ? 1 : 0;
            if (NativeMethods.DwmSetWindowAttribute(hwnd, NativeMethods.DWMWA_USE_IMMERSIVE_DARK_MODE, ref dark, sizeof(int)) != 0)
            {
                _ = NativeMethods.DwmSetWindowAttribute(hwnd, NativeMethods.DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, ref dark, sizeof(int));
            }

            if (round)
            {
                int corner = NativeMethods.DWMWCP_ROUND;
                _ = NativeMethods.DwmSetWindowAttribute(hwnd, NativeMethods.DWMWA_WINDOW_CORNER_PREFERENCE, ref corner, sizeof(int));
                int border = ColorTranslator.ToWin32(p.Line);
                _ = NativeMethods.DwmSetWindowAttribute(hwnd, NativeMethods.DWMWA_BORDER_COLOR, ref border, sizeof(int));
            }
        }
        catch (Exception ex) when (ex is DllNotFoundException or EntryPointNotFoundException)
        {
            // Älteres Windows: dann eben ohne.
        }
    }

    /// <summary>Dunkle Bildlaufleisten für Textfelder (wie der Explorer im dunklen Modus).</summary>
    public static void ScrollbarTheme(Control control, bool dark)
    {
        if (!control.IsHandleCreated)
        {
            return;
        }

        try
        {
            _ = NativeMethods.SetWindowTheme(control.Handle, dark ? "DarkMode_Explorer" : "Explorer", null);
        }
        catch (Exception ex) when (ex is DllNotFoundException or EntryPointNotFoundException)
        {
            // ohne Thema
        }
    }

    /// <summary>DPI des Bildschirms an einem Punkt (Windows 8.1+), sonst die System-DPI.</summary>
    public static int DpiAt(Point point)
    {
        try
        {
            IntPtr monitor = NativeMethods.MonitorFromPoint(new NativeMethods.POINT(point.X, point.Y), NativeMethods.MONITOR_DEFAULTTONEAREST);
            if (monitor != IntPtr.Zero && NativeMethods.GetDpiForMonitor(monitor, NativeMethods.MDT_EFFECTIVE_DPI, out uint x, out _) == 0 && x > 0)
            {
                return (int)x;
            }
        }
        catch (Exception ex) when (ex is DllNotFoundException or EntryPointNotFoundException)
        {
            // unten: System-DPI
        }

        using Graphics g = Graphics.FromHwnd(IntPtr.Zero);
        return (int)Math.Round(g.DpiX);
    }
}
