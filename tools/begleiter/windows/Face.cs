using System.Drawing.Drawing2D;

namespace SparkBegleiter;

/// <summary>
/// Das Spark-Gesicht aus dem Entwurf (SVG mit viewBox 0 0 200 200), mit GDI+-Pfaden nachgezeichnet:
/// Antenne, Kopf mit Verlauf Akzent → Akzent 2 und Glanz, Visier, zwei Augen, Lächeln.
/// </summary>
internal static class Face
{
    /// <summary>Ganzer Entwurf (mit Rand) bzw. eng um das Gesicht – für kleine Symbole.</summary>
    private static readonly RectangleF FullBox = new(0, 0, 200, 200);
    private static readonly RectangleF TightBox = new(16, 4, 168, 168);

    public static void Draw(Graphics g, RectangleF r, Palette p, bool tight = false)
    {
        RectangleF vb = tight ? TightBox : FullBox;
        float s = Math.Min(r.Width / vb.Width, r.Height / vb.Height);
        if (s <= 0)
        {
            return;
        }

        float ox = r.X + ((r.Width - (vb.Width * s)) / 2f) - (vb.X * s);
        float oy = r.Y + ((r.Height - (vb.Height * s)) / 2f) - (vb.Y * s);

        GraphicsState state = g.Save();
        try
        {
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.PixelOffsetMode = PixelOffsetMode.HighQuality;
            g.TranslateTransform(ox, oy);
            g.ScaleTransform(s, s);

            Color acc = p.HighContrast ? Palette.Light.Accent : p.Accent;
            Color acc2 = p.HighContrast ? Palette.Light.Accent2 : p.Accent2;
            Color visor = p.HighContrast ? Palette.Light.Visor : p.Visor;

            // Antenne: Stiel und Kugel.
            using (var stem = new Pen(acc2, 6f) { StartCap = LineCap.Round, EndCap = LineCap.Round })
            {
                g.DrawLine(stem, 100, 34, 100, 18);
            }

            using (var ball = new SolidBrush(acc2))
            {
                g.FillEllipse(ball, 92, 7, 16, 16);
            }

            // Kopf mit diagonalem Verlauf.
            var head = new RectangleF(26, 34, 148, 136);
            using (GraphicsPath headPath = SparkBegleiter.Draw.Round(head, 56))
            {
                using (var gradient = new LinearGradientBrush(new PointF(25, 33), new PointF(175, 171), acc, acc2))
                {
                    g.FillPath(gradient, headPath);
                }

                // Glanz: radialer Verlauf (Mitte bei 35 % / 25 %, Radius 80 %), weiß 45 % → 0 bei der Hälfte.
                GraphicsState clip = g.Save();
                g.SetClip(headPath, CombineMode.Intersect);
                using (var glossPath = new GraphicsPath())
                {
                    float cx = head.X + (head.Width * 0.35f);
                    float cy = head.Y + (head.Height * 0.25f);
                    float rx = head.Width * 0.8f;
                    float ry = head.Height * 0.8f;
                    glossPath.AddEllipse(cx - rx, cy - ry, rx * 2, ry * 2);
                    using var gloss = new PathGradientBrush(glossPath)
                    {
                        CenterPoint = new PointF(cx, cy),
                        InterpolationColors = new ColorBlend
                        {
                            Colors = new[] { Color.FromArgb(0, 255, 255, 255), Color.FromArgb(0, 255, 255, 255), Color.FromArgb(115, 255, 255, 255) },
                            Positions = new[] { 0f, 0.5f, 1f },
                        },
                    };
                    g.FillPath(gloss, glossPath);
                }

                g.Restore(clip);
            }

            // Visier.
            using (var visorBrush = new SolidBrush(visor))
            using (GraphicsPath visorPath = SparkBegleiter.Draw.Round(new RectangleF(44, 62, 112, 82), 38))
            {
                g.FillPath(visorBrush, visorPath);
            }

            // Augen.
            using (var eye = new SolidBrush(Palette.Eye))
            {
                using (GraphicsPath left = SparkBegleiter.Draw.Round(new RectangleF(66, 84, 18, 24), 9))
                {
                    g.FillPath(eye, left);
                }

                using GraphicsPath right = SparkBegleiter.Draw.Round(new RectangleF(116, 84, 18, 24), 9);
                g.FillPath(eye, right);
            }

            // Lächeln: M86 122 Q100 130 114 122 (als kubische Kurve).
            using var smile = new Pen(Palette.Eye, 5f) { StartCap = LineCap.Round, EndCap = LineCap.Round };
            g.DrawBezier(smile, 86, 122, 95.333f, 127.333f, 104.667f, 127.333f, 114, 122);
        }
        finally
        {
            g.Restore(state);
        }
    }
}

/// <summary>Kleine Strich-Symbole aus dem Entwurf (viewBox 0 0 16 16, Strich 1,6).</summary>
internal enum Glyph
{
    None,
    Pencil,
    Chat,
    Mic,
    Octagon,
    Download,
    Stop,
    Plus,
}

internal static class Glyphs
{
    public static void Draw(Graphics g, Glyph glyph, RectangleF r, Color color)
    {
        if (glyph == Glyph.None)
        {
            return;
        }

        float s = Math.Min(r.Width, r.Height) / 16f;
        GraphicsState state = g.Save();
        try
        {
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.PixelOffsetMode = PixelOffsetMode.HighQuality;
            g.TranslateTransform(r.X + ((r.Width - (16 * s)) / 2f), r.Y + ((r.Height - (16 * s)) / 2f));
            g.ScaleTransform(s, s);
            using var pen = new Pen(color, 1.6f) { LineJoin = LineJoin.Round, StartCap = LineCap.Round, EndCap = LineCap.Round };
            switch (glyph)
            {
                case Glyph.Pencil:
                    g.DrawPolygon(pen, new PointF[] { new(3, 11), new(10, 4), new(12, 6), new(5, 13), new(3, 13) });
                    break;
                case Glyph.Chat:
                    g.DrawPolygon(pen, new PointF[] { new(3, 4), new(13, 4), new(13, 10), new(7, 10), new(4, 13), new(4, 10), new(3, 10) });
                    break;
                case Glyph.Mic:
                    using (GraphicsPath capsule = SparkBegleiter.Draw.Round(new RectangleF(6, 2, 4, 8), 2))
                    {
                        g.DrawPath(pen, capsule);
                    }

                    g.DrawArc(pen, 4, 4, 8, 8, 180, -180);
                    g.DrawLine(pen, 8, 12, 8, 14);
                    break;
                case Glyph.Octagon:
                    g.DrawPolygon(pen, new PointF[] { new(5.5f, 2), new(10.5f, 2), new(14, 5.5f), new(14, 10.5f), new(10.5f, 14), new(5.5f, 14), new(2, 10.5f), new(2, 5.5f) });
                    break;
                case Glyph.Download:
                    g.DrawLine(pen, 8, 2, 8, 10);
                    g.DrawLines(pen, new PointF[] { new(5, 7), new(8, 10), new(11, 7) });
                    g.DrawLine(pen, 3, 13, 13, 13);
                    break;
                case Glyph.Stop:
                    using (var fill = new SolidBrush(color))
                    using (GraphicsPath square = SparkBegleiter.Draw.Round(new RectangleF(4, 4, 8, 8), 1.5f))
                    {
                        g.FillPath(fill, square);
                    }

                    break;
                case Glyph.Plus:
                    g.DrawLine(pen, 8, 3, 8, 13);
                    g.DrawLine(pen, 3, 8, 13, 8);
                    break;
            }
        }
        finally
        {
            g.Restore(state);
        }
    }
}
