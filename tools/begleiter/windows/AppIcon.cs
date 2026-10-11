using System.Drawing.Imaging;
using System.Runtime.InteropServices;

namespace SparkBegleiter;

/// <summary>Zustand für den Punkt im Symbol.</summary>
internal enum StatusDot
{
    None,
    Green,
    Grey,
    Red,

    /// <summary>Akzentfarbe: eine neue Version ist da.</summary>
    Update,
}

/// <summary>
/// Das Programmsymbol ist das Spark-Gesicht, im Code gezeichnet (keine Binärdatei im Repository).
/// Im Infobereich bekommt es unten rechts den Zustandspunkt (grün, grau, rot, Akzent bei Update) mit
/// einem ausgesparten Ring, damit er auf heller und dunkler Taskleiste sichtbar ist. Das Symbol für den
/// Infobereich wird genau in der Pixelgröße gezeichnet, die die Taskleiste bei ihrer DPI verlangt.
/// </summary>
internal static class AppIcon
{
    private static readonly int[] WindowSizes = { 16, 20, 24, 32, 40, 48, 64, 256 };

    private static readonly Dictionary<(StatusDot Dot, int Size, bool Dark), Icon> TrayCache = new();
    private static Icon? _windowIcon;

    /// <summary>Fenster-Symbol mit allen Größen; Windows wählt die passende.</summary>
    public static Icon Icon => _windowIcon ??= BuildMulti();

    /// <summary>Das Symbol für den Infobereich in der Größe und den Farben der Taskleiste.</summary>
    public static Icon ForTray(StatusDot dot)
    {
        int size = TrayIconSize();
        Palette palette = Theme.Taskbar;
        var key = (dot, size, palette.Dark);
        if (!TrayCache.TryGetValue(key, out Icon? icon))
        {
            using Bitmap bitmap = Render(size, palette, dot);
            icon = FromImages(new[] { bitmap });
            TrayCache[key] = icon;
        }

        return icon;
    }

    /// <summary>SM_CXSMICON bei der DPI der Taskleiste (bei mehreren Bildschirmen kann sie von der System-DPI abweichen).</summary>
    public static int TrayIconSize()
    {
        try
        {
            IntPtr tray = NativeMethods.FindWindow("Shell_TrayWnd", null);
            uint dpi = tray != IntPtr.Zero ? NativeMethods.GetDpiForWindow(tray) : 0;
            if (dpi > 0)
            {
                int size = NativeMethods.GetSystemMetricsForDpi(NativeMethods.SM_CXSMICON, dpi);
                if (size > 0)
                {
                    return size;
                }
            }
        }
        catch (Exception ex) when (ex is EntryPointNotFoundException or DllNotFoundException)
        {
            // Windows vor 10 1607: Systemgröße.
        }

        return SystemInformation.SmallIconSize.Width;
    }

    private static Color? DotColor(StatusDot dot, Palette p) => dot switch
    {
        StatusDot.Green => p.HighContrast ? Palette.Light.Ok : p.Ok,
        StatusDot.Grey => p.HighContrast ? Palette.Light.Muted : p.Muted,
        StatusDot.Red => p.HighContrast ? Palette.Light.Bad : p.Bad,
        StatusDot.Update => p.HighContrast ? Palette.Light.Accent : p.Accent,
        _ => null,
    };

    /// <summary>Bild in einer Größe: Gesicht, darüber optional der Punkt mit ausgespartem Ring.</summary>
    public static Bitmap Render(int size, Palette p, StatusDot dot)
    {
        var bitmap = new Bitmap(size, size, PixelFormat.Format32bppArgb);
        using Graphics g = Graphics.FromImage(bitmap);
        Draw.HighQuality(g);
        g.Clear(Color.Transparent);
        Face.Draw(g, new RectangleF(0, 0, size, size), p, tight: true);

        if (DotColor(dot, p) is { } color)
        {
            float d = Math.Max(5f, size * 0.42f);
            float ring = Math.Max(1f, size / 16f);
            var dotRect = new RectangleF(size - d, size - d, d, d);
            g.CompositingMode = System.Drawing.Drawing2D.CompositingMode.SourceCopy;
            using (var clear = new SolidBrush(Color.Transparent))
            {
                g.FillEllipse(clear, RectangleF.Inflate(dotRect, ring, ring));
            }

            g.CompositingMode = System.Drawing.Drawing2D.CompositingMode.SourceOver;
            using var fill = new SolidBrush(color);
            g.FillEllipse(fill, dotRect);
        }

        return bitmap;
    }

    private static Icon BuildMulti()
    {
        var bitmaps = WindowSizes.Select(size => Render(size, Palette.Light, StatusDot.None)).ToList();
        try
        {
            return FromImages(bitmaps);
        }
        finally
        {
            foreach (Bitmap b in bitmaps)
            {
                b.Dispose();
            }
        }
    }

    /// <summary>Baut eine .ico im Speicher: 32-Bit-DIB je Größe (256 px als PNG).</summary>
    private static Icon FromImages(IReadOnlyList<Bitmap> images)
    {
        var entries = images.Select(b => (b.Width, Data: b.Width >= 256 ? Png(b) : Dib(b))).ToList();

        using var ico = new MemoryStream();
        using (var w = new BinaryWriter(ico, System.Text.Encoding.UTF8, leaveOpen: true))
        {
            w.Write((ushort)0);
            w.Write((ushort)1);
            w.Write((ushort)entries.Count);

            int offset = 6 + (16 * entries.Count);
            foreach (var (size, data) in entries)
            {
                w.Write((byte)(size >= 256 ? 0 : size));
                w.Write((byte)(size >= 256 ? 0 : size));
                w.Write((byte)0);
                w.Write((byte)0);
                w.Write((ushort)1);
                w.Write((ushort)32);
                w.Write(data.Length);
                w.Write(offset);
                offset += data.Length;
            }

            foreach (var (_, data) in entries)
            {
                w.Write(data);
            }
        }

        ico.Position = 0;
        return entries.Count == 1 ? new Icon(ico, entries[0].Width, entries[0].Width) : new Icon(ico);
    }

    private static byte[] Png(Bitmap bitmap)
    {
        using var png = new MemoryStream();
        bitmap.Save(png, ImageFormat.Png);
        return png.ToArray();
    }

    /// <summary>BITMAPINFOHEADER + BGRA-Pixel (von unten nach oben) + leere UND-Maske.</summary>
    private static byte[] Dib(Bitmap bitmap)
    {
        int w = bitmap.Width;
        int h = bitmap.Height;
        byte[] pixels = new byte[w * h * 4];
        BitmapData data = bitmap.LockBits(new Rectangle(0, 0, w, h), ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
        try
        {
            for (int y = 0; y < h; y++)
            {
                Marshal.Copy(data.Scan0 + (y * data.Stride), pixels, (h - 1 - y) * w * 4, w * 4);
            }
        }
        finally
        {
            bitmap.UnlockBits(data);
        }

        int maskStride = (w + 31) / 32 * 4;
        using var ms = new MemoryStream();
        using (var bw = new BinaryWriter(ms, System.Text.Encoding.UTF8, leaveOpen: true))
        {
            bw.Write(40);
            bw.Write(w);
            bw.Write(h * 2);
            bw.Write((ushort)1);
            bw.Write((ushort)32);
            bw.Write(0);
            bw.Write(pixels.Length + (maskStride * h));
            bw.Write(0);
            bw.Write(0);
            bw.Write(0);
            bw.Write(0);
            bw.Write(pixels);
            bw.Write(new byte[maskStride * h]);
        }

        return ms.ToArray();
    }
}
