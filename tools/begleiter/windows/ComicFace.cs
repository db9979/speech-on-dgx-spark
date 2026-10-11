using System.Drawing.Drawing2D;

namespace SparkBegleiter;

/// <summary>
/// Das Comic-Gesicht (Karikatur von Dominik) als ruhendes Bild: dieselben Formen und Farben wie im Panel
/// (static/js/face.js, comicSvg und comicIcon), in der iPhone-App und im Mac-Begleiter (ComicFace.swift).
/// Lider wie im kleinen Bild des Panels, Blick geradeaus, Mund zu; der Kopf füllt einen Kreis
/// (viewBox 36 24 128 128).
/// </summary>
internal static class ComicFace
{
    private const float Top = 36, Hw = 47, CheekY = 92, ChinW = 23, ChinY = 167;
    private const float EyeX = 21, EyeY = 90, ERx = 10.5f, ERy = 6.5f, LidBase = 0.36f;
    private const float NoseLen = 29, NoseW = 10, StacheS = 1.06f, MouthW = 8, Lw = 2.6f;
    private const float M = EyeY + NoseLen + 6;
    private const float Mcy = M + (15 * StacheS);

    private static readonly (float A, float K)[] HairTips =
    {
        (-6, 1), (-12.8f, 1.31f), (-19.7f, 1), (-26.5f, 1.19f), (-33.3f, 1), (-40.2f, 1.33f), (-47, 1), (-53.8f, 1.22f),
        (-60.7f, 1), (-67.5f, 1.3f), (-74.3f, 1), (-81.2f, 1.2f), (-88, 1), (-94.8f, 1.34f), (-101.7f, 1), (-108.5f, 1.21f),
        (-115.3f, 1), (-122.2f, 1.3f), (-129, 1), (-135.8f, 1.18f), (-142.7f, 1), (-149.5f, 1.32f), (-156.3f, 1),
        (-163.2f, 1.24f), (-170, 1),
    };

    private static readonly Color Skin = Hex(0xf0b48c), LidC = Hex(0xe09d77), Shade = Hex(0xc9825e), Hair = Hex(0x2b2626);
    private static readonly Color Stache = Hex(0x382c27), Line = Hex(0x22180f), Bg = Hex(0xd9e6f5), Shirt = Hex(0xf6e27a);
    private static readonly Color Chain = Hex(0xc9cdd2), Iris = Hex(0x6b6a3e), Pupil = Hex(0x141414), EyeWhite = Hex(0xfbfbf8);

    private static Color Hex(int v, int alpha = 255) => Color.FromArgb(alpha, (v >> 16) & 255, (v >> 8) & 255, v & 255);

    private static Color Faded(Color c, float a) => Color.FromArgb((int)Math.Round(255 * a), c);

    /// <summary>Zeichnet das Gesicht kreisrund in die Mitte von <paramref name="r"/>.</summary>
    public static void Draw(Graphics g, RectangleF r)
    {
        float side = Math.Min(r.Width, r.Height);
        if (side <= 0)
        {
            return;
        }

        var box = new RectangleF(r.X + ((r.Width - side) / 2f), r.Y + ((r.Height - side) / 2f), side, side);
        GraphicsState state = g.Save();
        try
        {
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.PixelOffsetMode = PixelOffsetMode.HighQuality;
            using (var circle = new GraphicsPath())
            {
                circle.AddEllipse(box);
                g.SetClip(circle, CombineMode.Intersect);
            }

            using (var bg = new SolidBrush(Bg))
            {
                g.FillRectangle(bg, box);
            }

            float s = side / 128f;
            g.TranslateTransform(box.X, box.Y);
            g.ScaleTransform(s, s);
            g.TranslateTransform(-36, -24);
            DrawBody(g);
        }
        finally
        {
            g.Restore(state);
        }
    }

    private static Pen RoundPen(Color c, float w) =>
        new(c, w) { StartCap = LineCap.Round, EndCap = LineCap.Round, LineJoin = LineJoin.Round };

    private static void Outline(Graphics g, GraphicsPath p, Color fill)
    {
        using (var b = new SolidBrush(fill))
        {
            g.FillPath(b, p);
        }

        using var pen = RoundPen(Line, Lw);
        g.DrawPath(pen, p);
    }

    private static void Stroke(Graphics g, GraphicsPath p, Color c, float w)
    {
        using var pen = RoundPen(c, w);
        g.DrawPath(pen, p);
    }

    private static void DrawBody(Graphics g)
    {
        const float c = ChinY;

        // Hals, Hemd, Kette
        using (var neck = new GraphicsPath())
        {
            neck.AddPolygon(new[] { new PointF(80, c - 26), new PointF(78, 200), new PointF(122, 200), new PointF(120, c - 26) });
            Outline(g, neck, Skin);
        }

        using (var sh = new Pen2(0, 200))
        {
            sh.Line(0, c + 30).Quad(30, c + 14, 78, c + 11).Quad(100, c + 27, 122, c + 11).Quad(170, c + 14, 200, c + 30).Line(200, 200);
            sh.Path.CloseFigure();
            Outline(g, sh.Path, Shirt);
        }

        using (var ch = new Pen2(83, c + 8))
        {
            ch.Quad(100, c + 24, 117, c + 8);
            using var pen = new Pen(Chain, 2.2f) { DashPattern = new[] { 1.8f / 2.2f, 1.3f / 2.2f }, DashCap = DashCap.Round };
            g.DrawPath(pen, ch.Path);
        }

        // Ohren
        foreach (float k in new[] { -1f, 1f })
        {
            float ex = 100 + (k * (Hw + 1));
            using (var ear = new GraphicsPath())
            {
                ear.AddEllipse(ex - 7, EyeY + 8 - 13, 14, 26);
                Outline(g, ear, Skin);
            }

            using var e = new Pen2(ex - k, EyeY + 1);
            e.Quad(ex + (2 * k), EyeY + 7, ex - k, EyeY + 14);
            Stroke(g, e.Path, Shade, 1.3f);
        }

        // Gesicht mit Bartschatten
        using (GraphicsPath face = FacePath())
        {
            Outline(g, face, Skin);
            GraphicsState st = g.Save();
            g.SetClip(face, CombineMode.Intersect);
            using (var stubble = new SolidBrush(Faded(Hair, 0.13f)))
            {
                g.FillEllipse(stubble, 100 - (Hw - 2), M + 30 - 36, 2 * (Hw - 2), 72);
            }

            g.Restore(st);
        }

        using (var chin = new Pen2(100, c - 9))
        {
            chin.Quad(94, c - 6, 91, c - 10);
            chin.Move(100, c - 9).Quad(106, c - 6, 109, c - 10);
            Stroke(g, chin.Path, Faded(Shade, 0.6f), 1.2f);
        }

        // Augen, Lider, Brauen
        foreach (float k in new[] { -1f, 1f })
        {
            float x = 100 + (k * EyeX), y = EyeY, by = y - ERy - 7;
            using var eye = new GraphicsPath();
            eye.AddEllipse(x - ERx, y - ERy, 2 * ERx, 2 * ERy);
            GraphicsState st = g.Save();
            g.SetClip(eye, CombineMode.Intersect);
            using (var b = new SolidBrush(EyeWhite))
            {
                g.FillPath(b, eye);
            }

            using (var b = new SolidBrush(Iris))
            {
                g.FillEllipse(b, x - 5.53f, y - 5.53f, 11.06f, 11.06f);
            }

            using (var b = new SolidBrush(Pupil))
            {
                g.FillEllipse(b, x - 2.76f, y - 2.76f, 5.52f, 5.52f);
            }

            using (var b = new SolidBrush(Color.White))
            {
                g.FillEllipse(b, x + 0.5f, y - 2.9f, 2.2f, 2.2f);
            }

            float y0 = y - ERy - 1, h = ((2 * ERy) + 2) * LidBase, ly = y0 + h;
            using (var b = new SolidBrush(LidC))
            {
                g.FillRectangle(b, x - ERx - 1, y0, (2 * ERx) + 2, h);
            }

            g.Restore(st);
            Stroke(g, eye, Line, Lw * 0.7f);
            using (var lid = new Pen2(x - ERx - 0.5f, ly))
            {
                lid.Quad(x, ly + 1.6f, x + ERx + 0.5f, ly);
                Stroke(g, lid.Path, Line, Lw * 0.95f);
            }

            using var brow = new Pen2(x - (k * 12), by + 1);
            brow.Quad(x + k, by - 5, x + (k * 13), by + 2);
            Stroke(g, brow.Path, Hair, 5);
        }

        // Nase
        const float ny = EyeY, nl = NoseLen, nw = NoseW;
        using (var ns = new Pen2(100 - (nw * 0.5f), ny + nl - 6))
        {
            ns.Cubic(100 - nw - 1, ny + nl - 3, 100 - nw, ny + nl + 5, 97, ny + nl + 4)
              .Quad(100, ny + nl + 6, 103, ny + nl + 4)
              .Cubic(100 + nw, ny + nl + 5, 100 + nw + 1, ny + nl - 3, 100 + (nw * 0.5f), ny + nl - 6);
            using var b = new SolidBrush(Faded(Shade, 0.35f));
            g.FillPath(b, ns.Path);
        }

        using (var nose = new Pen2(97, ny + 4))
        {
            nose.Cubic(97, ny + (nl * 0.5f), 100 - (nw * 0.5f), ny + (nl * 0.75f), 100 - (nw * 0.6f), ny + nl - 4)
                .Cubic(100 - nw - 1, ny + nl, 100 - nw + 1, ny + nl + 5, 96, ny + nl + 4)
                .Quad(100, ny + nl + 6, 104, ny + nl + 4)
                .Cubic(100 + nw - 1, ny + nl + 5, 100 + nw + 1, ny + nl, 100 + (nw * 0.6f), ny + nl - 4);
            Stroke(g, nose.Path, Line, Lw);
        }

        // geschlossener Mund und Unterlippe unter dem Schnurrbart
        const float w = MouthW, my = Mcy;
        using (var ml = new Pen2(100 - w, my))
        {
            ml.Quad(100, my + 0.6f, 100 + w, my);
            Stroke(g, ml.Path, Line, Lw * 0.9f);
        }

        const float lipY = my + 4;
        using (var lip = new Pen2(100 - (w * 0.55f), lipY))
        {
            lip.Quad(100, lipY + 2.4f, 100 + (w * 0.55f), lipY);
            Stroke(g, lip.Path, Faded(Shade, 0.7f), 1.4f);
        }

        // Schnurrbart, um (100, M) vergrößert
        using (var around = new Matrix())
        {
            around.Translate(100, M);
            around.Scale(StacheS, StacheS);
            around.Translate(-100, -M);
            using (GraphicsPath mu = StachePath())
            {
                mu.Transform(around);
                Outline(g, mu, Stache);
            }

            using var strands = new GraphicsPath();
            foreach ((float x, float dy, float dx, float ey) in new[] { (88f, 3f, -3f, 7f), (95f, 2f, -1f, 7f), (105f, 2f, 1f, 7f), (112f, 3f, 3f, 7f), (80f, 7f, -4f, 7f), (120f, 7f, 4f, 7f) })
            {
                strands.StartFigure();
                strands.AddLine(x, M + dy, x + dx, M + dy + ey);
            }

            using (var own = new Matrix())
            {
                own.Translate(100, M);
                own.Scale(0.63f, 0.77f);
                own.Translate(-100, -M);
                strands.Transform(own);
            }

            strands.Transform(around);
            Stroke(g, strands, Faded(Color.Black, 0.25f), 0.9f);
        }

        using (GraphicsPath hair = HairPath())
        {
            Outline(g, hair, Hair);
        }
    }

    private static GraphicsPath FacePath()
    {
        var f = new Pen2(100, Top);
        f.Cubic(100 + (Hw * 0.72f), Top, 100 + Hw, Top + 22, 100 + Hw, CheekY)
         .Cubic(100 + Hw, CheekY + 36, 100 + ChinW + 13, ChinY - 15, 100 + ChinW, ChinY - 5)
         .Quad(100, ChinY + 6, 100 - ChinW, ChinY - 5)
         .Cubic(100 - ChinW - 13, ChinY - 15, 100 - Hw, CheekY + 36, 100 - Hw, CheekY)
         .Cubic(100 - Hw, Top + 22, 100 - (Hw * 0.72f), Top, 100, Top);
        f.Path.CloseFigure();
        return f.Take();
    }

    private static GraphicsPath HairPath()
    {
        const float cy = Top + 44, rx = Hw + 4;
        var h = new Pen2(100 + Hw + 2, cy);
        foreach ((float a, float k) in HairTips)
        {
            double rad = a * Math.PI / 180;
            h.Line(100 + (float)(Math.Cos(rad) * rx * k), cy + (float)(Math.Sin(rad) * 50 * k));
        }

        h.Line(100 - Hw - 2, cy).Line(100 - Hw + 3, Top + 38)
         .Quad(100 - (Hw * 0.45f), Top + 13, 100, Top + 18)
         .Quad(100 + (Hw * 0.45f), Top + 13, 100 + Hw - 3, Top + 38);
        h.Path.CloseFigure();
        return h.Take();
    }

    private static GraphicsPath StachePath()
    {
        var s = new Pen2(100, M);
        s.Cubic(106.33f, M - 2, 115.2f, M + 2, 119, M + 4.5f)
         .Cubic(120.9f, M + 6.7f, 120.33f, M + 9, 118.43f, M + 10)
         .Cubic(116.53f, M + 7.8f, 111.4f, M + 11, 105.13f, M + 10)
         .Quad(100, M + 8, 94.87f, M + 10)
         .Cubic(88.6f, M + 11, 83.47f, M + 7.8f, 81.57f, M + 10)
         .Cubic(79.67f, M + 9, 79.1f, M + 6.7f, 81, M + 4.5f)
         .Cubic(84.8f, M + 2, 93.67f, M - 2, 100, M);
        s.Path.CloseFigure();
        return s.Take();
    }

    /// <summary>Ein Pfad wie im SVG: Startpunkt, dann Linien, quadratische und kubische Kurven.</summary>
    private sealed class Pen2 : IDisposable
    {
        private GraphicsPath? _path = new();
        private PointF _at;

        public Pen2(float x, float y)
        {
            _at = new PointF(x, y);
            Path.StartFigure();
        }

        public GraphicsPath Path => _path ?? throw new ObjectDisposedException(nameof(Pen2));

        public Pen2 Move(float x, float y)
        {
            Path.StartFigure();
            _at = new PointF(x, y);
            return this;
        }

        public Pen2 Line(float x, float y)
        {
            var to = new PointF(x, y);
            Path.AddLine(_at, to);
            _at = to;
            return this;
        }

        public Pen2 Cubic(float x1, float y1, float x2, float y2, float x, float y)
        {
            var to = new PointF(x, y);
            Path.AddBezier(_at, new PointF(x1, y1), new PointF(x2, y2), to);
            _at = to;
            return this;
        }

        /// <summary>Quadratische Kurve als kubische (Kontrollpunkte bei 2/3).</summary>
        public Pen2 Quad(float qx, float qy, float x, float y)
        {
            var c1 = new PointF(_at.X + ((qx - _at.X) * 2f / 3f), _at.Y + ((qy - _at.Y) * 2f / 3f));
            var c2 = new PointF(x + ((qx - x) * 2f / 3f), y + ((qy - y) * 2f / 3f));
            return Cubic(c1.X, c1.Y, c2.X, c2.Y, x, y);
        }

        /// <summary>Gibt den Pfad heraus; Dispose räumt ihn dann nicht mehr weg.</summary>
        public GraphicsPath Take()
        {
            GraphicsPath p = Path;
            _path = null;
            return p;
        }

        public void Dispose()
        {
            _path?.Dispose();
            _path = null;
        }
    }
}
