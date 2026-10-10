using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Drawing.Text;

namespace SparkSchreibhilfe;

/// <summary>
/// Das Programmsymbol wird im Code gezeichnet (blaues Quadrat mit weißem "S" und Stift-Strich),
/// damit keine Binärdatei im Repository liegt. Es entsteht ein .ico mit mehreren Größen (PNG-Einträge).
/// </summary>
internal static class AppIcon
{
    private static readonly int[] Sizes = { 16, 20, 24, 32, 40, 48, 64 };

    private static Icon? _icon;

    /// <summary>Das Symbol mit allen Größen; Windows wählt für Infobereich und Fenster die passende.</summary>
    public static Icon Icon => _icon ??= Build();

    private static Icon Build()
    {
        var images = Sizes.Select(size => (size, Png: RenderPng(size))).ToList();

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

    private static byte[] RenderPng(int size)
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

            // Kleiner grüner Strich unten rechts: "verbessert".
            using var pen = new Pen(Color.FromArgb(0x4A, 0xDE, 0x80), Math.Max(1.5f, size / 10f))
            {
                StartCap = LineCap.Round,
                EndCap = LineCap.Round,
            };
            g.DrawLine(pen, size * 0.66f, size * 0.80f, size * 0.84f, size * 0.62f);
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
