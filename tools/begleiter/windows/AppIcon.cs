using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Drawing.Text;

namespace SparkBegleiter;

/// <summary>Zustand für den Punkt im Symbol (Teil "status").</summary>
internal enum StatusDot
{
    None,
    Green,
    Grey,
    Red,
}

/// <summary>
/// Das Programmsymbol wird im Code gezeichnet (blaues Quadrat mit weißem "S", optional mit farbigem
/// Zustandspunkt unten rechts), damit keine Binärdatei im Repository liegt. Es entsteht ein .ico mit
/// mehreren Größen (PNG-Einträge).
/// </summary>
internal static class AppIcon
{
    private static readonly int[] Sizes = { 16, 20, 24, 32, 40, 48, 64 };

    private static readonly Dictionary<StatusDot, Icon> Cache = new();

    /// <summary>Das Symbol ohne Punkt mit allen Größen; Windows wählt für Infobereich und Fenster die passende.</summary>
    public static Icon Icon => For(StatusDot.None);

    /// <summary>Das Symbol mit Zustandspunkt.</summary>
    public static Icon For(StatusDot dot)
    {
        if (!Cache.TryGetValue(dot, out Icon? icon))
        {
            icon = Build(dot);
            Cache[dot] = icon;
        }

        return icon;
    }

    private static readonly Dictionary<StatusDot, Icon> TrayCache = new();

    /// <summary>Das Symbol in der kleinen Größe für den Infobereich (sonst skaliert Windows unschön).</summary>
    public static Icon ForTray(StatusDot dot)
    {
        if (!TrayCache.TryGetValue(dot, out Icon? icon))
        {
            icon = new Icon(For(dot), SystemInformation.SmallIconSize);
            TrayCache[dot] = icon;
        }

        return icon;
    }

    private static Color? DotColor(StatusDot dot) => dot switch
    {
        StatusDot.Green => Color.FromArgb(0x22, 0xC5, 0x5E),
        StatusDot.Grey => Color.FromArgb(0x9C, 0xA3, 0xAF),
        StatusDot.Red => Color.FromArgb(0xEF, 0x44, 0x44),
        _ => null,
    };

    private static Icon Build(StatusDot dot)
    {
        var images = Sizes.Select(size => (size, Png: RenderPng(size, DotColor(dot)))).ToList();

        using var ico = new MemoryStream();
        using (var w = new BinaryWriter(ico, System.Text.Encoding.UTF8, leaveOpen: true))
        {
            // ICONDIR
            w.Write((ushort)0);
            w.Write((ushort)1);
            w.Write((ushort)images.Count);

            // ICONDIRENTRY je Größe; Daten folgen hinter allen Einträgen.
            int offset = 6 + (16 * images.Count);
            foreach (var (size, png) in images)
            {
                w.Write((byte)(size >= 256 ? 0 : size));
                w.Write((byte)(size >= 256 ? 0 : size));
                w.Write((byte)0);   // keine Palette
                w.Write((byte)0);   // reserviert
                w.Write((ushort)1); // Farbebenen
                w.Write((ushort)32); // Bit pro Pixel
                w.Write(png.Length);
                w.Write(offset);
                offset += png.Length;
            }

            foreach (var (_, png) in images)
            {
                w.Write(png);
            }
        }

        ico.Position = 0;
        return new Icon(ico);
    }

    private static byte[] RenderPng(int size, Color? dot)
    {
        using var bitmap = new Bitmap(size, size, PixelFormat.Format32bppArgb);
        using (Graphics g = Graphics.FromImage(bitmap))
        {
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;
            g.Clear(Color.Transparent);

            float inset = Math.Max(0.5f, size / 32f);
            var box = new RectangleF(inset, inset, size - (2 * inset), size - (2 * inset));
            using (GraphicsPath path = RoundedRect(box, size * 0.22f))
            using (var fill = new LinearGradientBrush(box, Color.FromArgb(0x3B, 0x82, 0xF6), Color.FromArgb(0x1D, 0x4E, 0xD8), 90f))
            {
                g.FillPath(fill, path);
            }

            // Weißes "S" mittig.
            using var font = new Font("Segoe UI", size * 0.58f, FontStyle.Bold, GraphicsUnit.Pixel);
            using var format = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center };
            var textBox = new RectangleF(0, -size * 0.04f, size * 0.92f, size);
            g.DrawString("S", font, Brushes.White, textBox, format);

            // Zustandspunkt unten rechts mit weißem Rand, damit er auf hellen und dunklen Leisten sichtbar ist.
            if (dot is { } color)
            {
                float d = size * 0.46f;
                var circle = new RectangleF(size - d, size - d, d, d);
                using var ring = new SolidBrush(Color.White);
                using var fillDot = new SolidBrush(color);
                g.FillEllipse(ring, circle);
                float border = Math.Max(1f, size / 16f);
                circle.Inflate(-border, -border);
                g.FillEllipse(fillDot, circle);
            }
        }

        using var png = new MemoryStream();
        bitmap.Save(png, ImageFormat.Png);
        return png.ToArray();
    }

    private static GraphicsPath RoundedRect(RectangleF r, float radius)
    {
        float d = radius * 2;
        var path = new GraphicsPath();
        path.AddArc(r.X, r.Y, d, d, 180, 90);
        path.AddArc(r.Right - d, r.Y, d, d, 270, 90);
        path.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
        path.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
        path.CloseFigure();
        return path;
    }
}
