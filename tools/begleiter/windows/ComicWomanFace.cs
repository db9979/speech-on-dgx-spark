using System.Drawing.Drawing2D;
using System.Globalization;

namespace SparkBegleiter;

/// <summary>
/// Die Comic-Frau (V01.0.490, "comic_woman") als ruhendes Bild: dieselbe Zeichnung wie im Panel
/// (static/js/face.js, comicWSvg und comicIcon), in der iPhone-App und im Mac-Begleiter, als feste Ebenen
/// (Pfad, Füllung, Linie, Breite, Deckkraft) im 200 × 200-Feld des Panels. Gezeichnet werden nur diese
/// festen Texte; der Kopf füllt einen Kreis (viewBox 36 24 128 128) wie beim Comic-Gesicht.
/// </summary>
internal static class ComicWomanFace
{
    private static readonly Color Bg = Color.FromArgb(255, 0xf5, 0xdf, 0xe6);

    private static readonly (string D, int Fill, int Stroke, float W, float A)[] Layers =
    {
        ("M82 138 L80 200 L120 200 L118 138Z", 0xf0b48c, 0x22180f, 2.6f, 1f),
        ("M0 200 L0 196 Q30 180 80 177 Q100 194 120 177 Q170 180 200 196 L200 200Z", 0x7cc4b8, 0x22180f, 2.6f, 1f),
        ("M86 174 Q100 186 114 174", -1, 0xd9b45a, 1.6f, 1f),
        ("M102.6 183 C102.6 184.44 101.44 185.6 100 185.6 C98.56 185.6 97.4 184.44 97.4 183 C97.4 181.56 98.56 180.4 100 180.4 C101.44 180.4 102.6 181.56 102.6 183Z", 0xe9c46a, 0x22180f, 1f, 1f),
        ("M100 24 C152 24 164 66 160 118 C157 156 166 184 176 200 L121 200 L119 140 L81 140 L79 200 L24 200 C34 184 43 156 40 118 C36 66 48 24 100 24Z", 0x4a2c22, 0x22180f, 2.6f, 1f),
        ("M52 96 C44 130 46 168 34 200 L62 200 C64 172 58 140 60 110Z M148 96 C156 130 154 168 166 200 L138 200 C136 172 142 140 140 110Z", 0x4a2c22, 0x22180f, 2.6f, 1f),
        ("M100 38 C132.4 38 145 60 145 92 C145 128 132 149 119 159 Q100 169 81 159 C68 149 55 128 55 92 C55 60 67.6 38 100 38Z", 0xf0b48c, 0x22180f, 2.6f, 1f),
        ("M100 156 Q95 158.5 92 155 M100 156 Q105 158.5 108 155", -1, 0xc9825e, 1.1f, 0.5f),
        ("M82 112 C82 114.76 77.97 117 73 117 C68.03 117 64 114.76 64 112 C64 109.24 68.03 107 73 107 C77.97 107 82 109.24 82 112Z", 0xef7f86, -1, 0f, 0.35f),
        ("M136 112 C136 114.76 131.97 117 127 117 C122.03 117 118 114.76 118 112 C118 109.24 122.03 107 127 107 C131.97 107 136 109.24 136 112Z", 0xef7f86, -1, 0f, 0.35f),
        ("M89.5 91 C89.5 94.87 84.8 98 79 98 C73.2 98 68.5 94.87 68.5 91 C68.5 87.13 73.2 84 79 84 C84.8 84 89.5 87.13 89.5 91Z", 0xfbfbf8, -1, 0f, 1f),
        ("M84.8 91.5 C84.8 94.7 82.2 97.3 79 97.3 C75.8 97.3 73.2 94.7 73.2 91.5 C73.2 88.3 75.8 85.7 79 85.7 C82.2 85.7 84.8 88.3 84.8 91.5Z", 0x6b4a2e, -1, 0f, 1f),
        ("M81.8 91.5 C81.8 93.05 80.55 94.3 79 94.3 C77.45 94.3 76.2 93.05 76.2 91.5 C76.2 89.95 77.45 88.7 79 88.7 C80.55 88.7 81.8 89.95 81.8 91.5Z", 0x141414, -1, 0f, 1f),
        ("M81.8 89.6 C81.8 90.26 81.26 90.8 80.6 90.8 C79.94 90.8 79.4 90.26 79.4 89.6 C79.4 88.94 79.94 88.4 80.6 88.4 C81.26 88.4 81.8 88.94 81.8 89.6Z", 0xffffff, -1, 0f, 1f),
        ("M73.8 84.92 Q79 83.08 84.2 84.92Z", 0xe09d77, -1, 0f, 1f),
        ("M89.5 91 C89.5 94.87 84.8 98 79 98 C73.2 98 68.5 94.87 68.5 91 C68.5 87.13 73.2 84 79 84 C84.8 84 89.5 87.13 89.5 91Z", -1, 0x22180f, 1.82f, 1f),
        ("M68 84.92 Q79 86.52 90 84.92", -1, 0x22180f, 2.99f, 1f),
        ("M70.4 85 L66.2 81.4 M68.6 87.2 L64 85.6 M73.2 84.4 L70.6 80.4", -1, 0x22180f, 1.6f, 1f),
        ("M90 78 Q77 71 67 77", -1, 0x4a2c22, 3.2f, 1f),
        ("M131.5 91 C131.5 94.87 126.8 98 121 98 C115.2 98 110.5 94.87 110.5 91 C110.5 87.13 115.2 84 121 84 C126.8 84 131.5 87.13 131.5 91Z", 0xfbfbf8, -1, 0f, 1f),
        ("M126.8 91.5 C126.8 94.7 124.2 97.3 121 97.3 C117.8 97.3 115.2 94.7 115.2 91.5 C115.2 88.3 117.8 85.7 121 85.7 C124.2 85.7 126.8 88.3 126.8 91.5Z", 0x6b4a2e, -1, 0f, 1f),
        ("M123.8 91.5 C123.8 93.05 122.55 94.3 121 94.3 C119.45 94.3 118.2 93.05 118.2 91.5 C118.2 89.95 119.45 88.7 121 88.7 C122.55 88.7 123.8 89.95 123.8 91.5Z", 0x141414, -1, 0f, 1f),
        ("M123.8 89.6 C123.8 90.26 123.26 90.8 122.6 90.8 C121.94 90.8 121.4 90.26 121.4 89.6 C121.4 88.94 121.94 88.4 122.6 88.4 C123.26 88.4 123.8 88.94 123.8 89.6Z", 0xffffff, -1, 0f, 1f),
        ("M115.8 84.92 Q121 83.08 126.2 84.92Z", 0xe09d77, -1, 0f, 1f),
        ("M131.5 91 C131.5 94.87 126.8 98 121 98 C115.2 98 110.5 94.87 110.5 91 C110.5 87.13 115.2 84 121 84 C126.8 84 131.5 87.13 131.5 91Z", -1, 0x22180f, 1.82f, 1f),
        ("M110 84.92 Q121 86.52 132 84.92", -1, 0x22180f, 2.99f, 1f),
        ("M129.6 85 L133.8 81.4 M131.4 87.2 L136 85.6 M126.8 84.4 L129.4 80.4", -1, 0x22180f, 1.6f, 1f),
        ("M110 78 Q123 71 133 77", -1, 0x4a2c22, 3.2f, 1f),
        ("M96 110 C91 113 92 121 97.5 120 Q100 122 102.5 120 C108 121 109 113 104 110", 0xc9825e, -1, 0f, 0.3f),
        ("M97.5 97 C97.5 103.5 96 109.75 95.2 112 C91 116 93 120 96.5 119.5 Q100 121 103.5 119.5 C107 120 109 116 104.8 112", -1, 0x22180f, 2.6f, 1f),
        ("M89 133 Q95 128.8 100 131 Q105 128.8 111 133 Q100 133 89 133Z", 0xc8565a, 0x22180f, 1.56f, 1f),
        ("M89 133 Q100 141.5 111 133 Q100 133 89 133Z", 0xc8565a, 0x22180f, 1.56f, 1f),
        ("M90 133 Q100 133.6 110 133", -1, 0x22180f, 2.08f, 1f),
        ("M52 104 C44 54 68 27 101 27 C134 27 156 54 148 104 C146 84 142 70 136 62 C126 50 116 47 107 47 C90 50 74 60 66 74 C60 82 55 92 52 104Z", 0x4a2c22, 0x22180f, 2.6f, 1f),
        ("M107 47 C96 52 82 60 72 74 M107 47 C120 52 132 62 138 74", -1, 0x22180f, 1.3f, 0.45f),
    };

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
            foreach ((string d, int fill, int stroke, float w, float a) in Layers)
            {
                using GraphicsPath p = PathOf(d);
                int alpha = (int)Math.Round(255 * a);
                if (fill >= 0)
                {
                    using var b = new SolidBrush(Color.FromArgb(alpha, (fill >> 16) & 255, (fill >> 8) & 255, fill & 255));
                    g.FillPath(b, p);
                }

                if (stroke >= 0)
                {
                    using var pen = new Pen(Color.FromArgb(alpha, (stroke >> 16) & 255, (stroke >> 8) & 255, stroke & 255), w)
                    {
                        StartCap = LineCap.Round,
                        EndCap = LineCap.Round,
                        LineJoin = LineJoin.Round,
                    };
                    g.DrawPath(pen, p);
                }
            }
        }
        finally
        {
            g.Restore(state);
        }
    }

    /// <summary>Absolutes M, L, C, Q und Z eines festen Pfads (Q als kubische Kurve, Kontrollpunkte bei 2/3).</summary>
    private static GraphicsPath PathOf(string d)
    {
        var path = new GraphicsPath();
        var nums = new List<float>();
        var num = new System.Text.StringBuilder();
        char cmd = 'M';
        PointF at = PointF.Empty;

        void Take()
        {
            if (num.Length > 0)
            {
                nums.Add(float.Parse(num.ToString(), CultureInfo.InvariantCulture));
                num.Clear();
            }
        }

        void Run()
        {
            int i = 0;
            switch (cmd)
            {
                case 'M':
                    if (nums.Count >= 2)
                    {
                        path.StartFigure();
                        at = new PointF(nums[0], nums[1]);
                        i = 2;
                    }

                    for (; i + 1 < nums.Count; i += 2)
                    {
                        var to = new PointF(nums[i], nums[i + 1]);
                        path.AddLine(at, to);
                        at = to;
                    }

                    break;
                case 'L':
                    for (; i + 1 < nums.Count; i += 2)
                    {
                        var to = new PointF(nums[i], nums[i + 1]);
                        path.AddLine(at, to);
                        at = to;
                    }

                    break;
                case 'C':
                    for (; i + 5 < nums.Count; i += 6)
                    {
                        var to = new PointF(nums[i + 4], nums[i + 5]);
                        path.AddBezier(at, new PointF(nums[i], nums[i + 1]), new PointF(nums[i + 2], nums[i + 3]), to);
                        at = to;
                    }

                    break;
                case 'Q':
                    for (; i + 3 < nums.Count; i += 4)
                    {
                        float qx = nums[i], qy = nums[i + 1];
                        var to = new PointF(nums[i + 2], nums[i + 3]);
                        var c1 = new PointF(at.X + ((qx - at.X) * 2f / 3f), at.Y + ((qy - at.Y) * 2f / 3f));
                        var c2 = new PointF(to.X + ((qx - to.X) * 2f / 3f), to.Y + ((qy - to.Y) * 2f / 3f));
                        path.AddBezier(at, c1, c2, to);
                        at = to;
                    }

                    break;
                case 'Z':
                    path.CloseFigure();
                    break;
            }

            nums.Clear();
        }

        foreach (char ch in d)
        {
            if (char.IsLetter(ch))
            {
                Take();
                Run();
                cmd = ch;
            }
            else if (ch == ' ' || ch == ',')
            {
                Take();
            }
            else if (ch == '-')
            {
                Take();
                num.Append(ch);
            }
            else
            {
                num.Append(ch);
            }
        }

        Take();
        Run();
        return path;
    }
}
