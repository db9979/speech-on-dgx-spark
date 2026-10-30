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

    /// <summary>Das Panel hat das Comic-Gesicht gewählt (config.face); gilt für alle Fenster und das Symbol.</summary>
    public static bool Comic { get; set; }

    /// <summary>Das Panel hat die Comic-Frau gewählt (config.face "comic_woman", V01.0.497).</summary>
    public static bool ComicWoman { get; set; }

    public static void Draw(Graphics g, RectangleF r, Palette p, bool tight = false)
    {
        if (ComicWoman)
        {
            ComicWomanFace.Draw(g, r);
            return;
        }

        if (Comic)
        {
            ComicFace.Draw(g, r);
            return;
        }

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
    Screen,
    Mail,
    Wave,
    Folder,
    Bell,
    Speaker,
    Record,
    MicOff,
    Gear,
    Close,
    Eye,
    External,
    Grid,
    Key,
    Sun,
    Link,
    Info,
    Search,
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
                case Glyph.MicOff:
                    using (GraphicsPath capsule = SparkBegleiter.Draw.Round(new RectangleF(6, 2, 4, 8), 2))
                    {
                        g.DrawPath(pen, capsule);
                    }

                    g.DrawArc(pen, 4, 4, 8, 8, 180, -180);
                    g.DrawLine(pen, 8, 12, 8, 14);
                    if (glyph == Glyph.MicOff)
                    {
                        g.DrawLine(pen, 3, 2, 13, 14); // durchgestrichen: zu
                    }

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
                case Glyph.Search:
                    // Lupe (Finden, Paket B)
                    g.DrawEllipse(pen, 2.5f, 2.5f, 8, 8);
                    g.DrawLine(pen, 9.5f, 9.5f, 13.5f, 13.5f);
                    break;
                case Glyph.Screen:
                    // Auswahlrahmen: vier Ecken
                    g.DrawLines(pen, new PointF[] { new(2, 6), new(2, 2), new(6, 2) });
                    g.DrawLines(pen, new PointF[] { new(10, 2), new(14, 2), new(14, 6) });
                    g.DrawLines(pen, new PointF[] { new(14, 10), new(14, 14), new(10, 14) });
                    g.DrawLines(pen, new PointF[] { new(6, 14), new(2, 14), new(2, 10) });
                    break;
                case Glyph.Mail:
                    using (GraphicsPath envelope = SparkBegleiter.Draw.Round(new RectangleF(2, 4, 12, 9), 1.5f))
                    {
                        g.DrawPath(pen, envelope);
                    }

                    g.DrawLines(pen, new PointF[] { new(2.5f, 5), new(8, 9), new(13.5f, 5) });
                    break;
                case Glyph.Wave:
                    g.DrawLine(pen, 2, 7, 2, 9);
                    g.DrawLine(pen, 5, 5, 5, 11);
                    g.DrawLine(pen, 8, 2, 8, 14);
                    g.DrawLine(pen, 11, 5, 11, 11);
                    g.DrawLine(pen, 14, 7, 14, 9);
                    break;
                case Glyph.Folder:
                    g.DrawPolygon(pen, new PointF[] { new(2, 4), new(6, 4), new(7.5f, 5.5f), new(14, 5.5f), new(14, 13), new(2, 13) });
                    break;
                case Glyph.Speaker:
                    g.DrawPolygon(pen, new PointF[] { new(2, 6), new(5, 6), new(9, 3), new(9, 13), new(5, 10), new(2, 10) });
                    g.DrawArc(pen, 9, 5.5f, 4, 5, -60, 120);
                    g.DrawArc(pen, 9, 3, 6.5f, 10, -60, 120);
                    break;
                case Glyph.Record:
                    g.DrawEllipse(pen, 2, 2, 12, 12);
                    using (var dot = new SolidBrush(color))
                    {
                        g.FillEllipse(dot, 5.5f, 5.5f, 5, 5);
                    }

                    break;
                case Glyph.Gear:
                    g.DrawEllipse(pen, 5.5f, 5.5f, 5, 5);
                    for (int i = 0; i < 8; i++)
                    {
                        double a = i * Math.PI / 4;
                        g.DrawLine(pen, 8 + (float)(4.6 * Math.Cos(a)), 8 + (float)(4.6 * Math.Sin(a)), 8 + (float)(6.4 * Math.Cos(a)), 8 + (float)(6.4 * Math.Sin(a)));
                    }

                    break;
                case Glyph.Close:
                    g.DrawLine(pen, 4, 4, 12, 12);
                    g.DrawLine(pen, 12, 4, 4, 12);
                    break;
                case Glyph.Eye:
                    g.DrawBezier(pen, 1.5f, 8, 4.5f, 3, 11.5f, 3, 14.5f, 8);
                    g.DrawBezier(pen, 1.5f, 8, 4.5f, 13, 11.5f, 13, 14.5f, 8);
                    g.DrawEllipse(pen, 6, 6, 4, 4);
                    break;
                case Glyph.External:
                    g.DrawLines(pen, new PointF[] { new(9, 3), new(13, 3), new(13, 7) });
                    g.DrawLine(pen, 13, 3, 7.5f, 8.5f);
                    g.DrawLines(pen, new PointF[] { new(11, 9.5f), new(11, 13), new(3, 13), new(3, 5), new(6.5f, 5) });
                    break;
                case Glyph.Grid:
                    using (GraphicsPath a = SparkBegleiter.Draw.Round(new RectangleF(2.5f, 2.5f, 4.5f, 4.5f), 1.2f))
                    using (GraphicsPath b = SparkBegleiter.Draw.Round(new RectangleF(9, 2.5f, 4.5f, 4.5f), 1.2f))
                    using (GraphicsPath c = SparkBegleiter.Draw.Round(new RectangleF(2.5f, 9, 4.5f, 4.5f), 1.2f))
                    using (GraphicsPath d = SparkBegleiter.Draw.Round(new RectangleF(9, 9, 4.5f, 4.5f), 1.2f))
                    {
                        g.DrawPath(pen, a);
                        g.DrawPath(pen, b);
                        g.DrawPath(pen, c);
                        g.DrawPath(pen, d);
                    }

                    break;
                case Glyph.Key:
                    using (GraphicsPath board = SparkBegleiter.Draw.Round(new RectangleF(1.5f, 4, 13, 8.5f), 1.5f))
                    {
                        g.DrawPath(pen, board);
                    }

                    g.DrawLine(pen, 4.5f, 7, 5, 7);
                    g.DrawLine(pen, 7.75f, 7, 8.25f, 7);
                    g.DrawLine(pen, 11, 7, 11.5f, 7);
                    g.DrawLine(pen, 5, 9.75f, 11, 9.75f);
                    break;
                case Glyph.Sun:
                    g.DrawEllipse(pen, 5, 5, 6, 6);
                    for (int i = 0; i < 8; i++)
                    {
                        double a = i * Math.PI / 4;
                        g.DrawLine(pen, 8 + (float)(5 * Math.Cos(a)), 8 + (float)(5 * Math.Sin(a)), 8 + (float)(6.6 * Math.Cos(a)), 8 + (float)(6.6 * Math.Sin(a)));
                    }

                    break;
                case Glyph.Link:
                    g.DrawArc(pen, 1.5f, 5, 7, 6, 90, 180);
                    g.DrawLine(pen, 5, 5, 7.5f, 5);
                    g.DrawLine(pen, 5, 11, 7.5f, 11);
                    g.DrawArc(pen, 7.5f, 5, 7, 6, 270, 180);
                    g.DrawLine(pen, 8.5f, 5, 11, 5);
                    g.DrawLine(pen, 8.5f, 11, 11, 11);
                    g.DrawLine(pen, 5.5f, 8, 10.5f, 8);
                    break;
                case Glyph.Info:
                    g.DrawEllipse(pen, 2, 2, 12, 12);
                    g.DrawLine(pen, 8, 7.5f, 8, 11);
                    g.DrawLine(pen, 8, 5, 8, 5.2f);
                    break;
                case Glyph.Bell:
                    g.DrawBezier(pen, 4, 11, 4, 4, 12, 4, 12, 11);
                    g.DrawLine(pen, 3, 11, 13, 11);
                    g.DrawLine(pen, 7, 13.5f, 9, 13.5f);
                    break;
            }
        }
        finally
        {
            g.Restore(state);
        }
    }
}
