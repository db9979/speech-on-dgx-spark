using System.Globalization;

namespace SparkBegleiter;

/// <summary>
/// "Frag Spark": Frage eintippen (oder mit dem Mikrofon-Knopf sprechen, wenn Diktieren an ist), Senden.
/// Fragen und Antworten erscheinen als Sprechblasen (eigene mit Farbverlauf, Spark als weiche Karte mit
/// Gesicht). Antworten sind reiner Text (nie HTML), nur angezeigt, nie ausgeführt. Folgefragen behalten den
/// Zusammenhang (den hält der Spark).
/// </summary>
internal sealed class AskForm : ThemedForm
{
    private const int MaxQuestion = 2000;

    private readonly AppConfig _config;
    private readonly Action<SparkException> _report;
    private readonly Func<DeskConfig?> _desk;

    private readonly ChatView _chat = new();

    private readonly TextBox _question = new()
    {
        Multiline = true,
        AcceptsReturn = false,
        ScrollBars = ScrollBars.None,
        WordWrap = true,
        MaxLength = MaxQuestion,
        PlaceholderText = "Frag den Spark …",
        AccessibleName = "Frage",
    };

    private readonly RoundedHost _input;
    private readonly SparkButton _send = new(ButtonKind.Primary, "Senden");
    private readonly SparkButton _mic = new(ButtonKind.Round) { Glyph = Glyph.Mic, Visible = false, AccessibleName = "Sprechen" };
    private readonly TLabel _status = new(TextRole.SmallMuted);
    private readonly System.Windows.Forms.Timer _micTimer = new() { Interval = 250 };

    private Rectangle _face;
    private Rectangle _title;
    private Rectangle _hint;

    private CancellationTokenSource? _cts;
    private Recorder? _recorder;
    private bool _busy;
    private bool _micShown;

    public AskForm(AppConfig config, Func<DeskConfig?> desk, Action<SparkException> report)
    {
        _config = config;
        _desk = desk;
        _report = report;
        _input = new RoundedHost(_question) { SoftBack = false };

        Text = "Frag Spark";
        TopMost = true;
        ShowInTaskbar = true;
        StartPosition = FormStartPosition.Manual;
        MinimizeBox = true;
        MaximizeBox = true;
        KeyPreview = true;

        Controls.Add(_chat);
        Controls.Add(_status);
        Controls.Add(_send);
        Controls.Add(_mic);
        Controls.Add(_input);
        _send.BringToFront();
        _mic.BringToFront();
        _input.TabIndex = 0;
        _mic.TabIndex = 1;
        _send.TabIndex = 2;

        _send.Click += async (_, _) => await SendAsync();
        _mic.Click += async (_, _) => await ToggleMicAsync();
        _micTimer.Tick += (_, _) => UpdateMicStatus();
        _chat.Copied += (_, text) => CopyText(text);
        _question.KeyDown += async (_, e) =>
        {
            if (e.KeyCode == Keys.Enter && !e.Shift)
            {
                e.SuppressKeyPress = true;
                await SendAsync();
            }
            else if (e.KeyCode == Keys.Enter && e.Shift)
            {
                // Neue Zeile von Hand einfügen (AcceptsReturn ist aus, damit Enter sendet).
                e.SuppressKeyPress = true;
                _question.SelectedText = Environment.NewLine;
            }
        };

        RefreshParts();
        PlaceCentered();
    }

    /// <summary>Mikrofon-Knopf nur, wenn Diktieren im Panel an ist.</summary>
    public void RefreshParts()
    {
        bool dictate = _desk()?.IsOn(Parts.Dictate) == true;
        bool visible = dictate || _recorder is not null;
        if (_micShown != visible)
        {
            _micShown = visible;
            _mic.Visible = visible;
            if (IsHandleCreated)
            {
                LayoutContent();
            }
        }
    }

    private int ButtonsWidth() => _send.Preferred().Width + S(8) + (_micShown ? S(34) + S(8) : 0);

    protected override void LayoutContent()
    {
        int pad = S(14);
        int w = ClientSize.Width;
        int h = ClientSize.Height;
        int y = BarHeight + pad;

        int face = S(28);
        _face = new Rectangle(pad, y, face, face);
        Size title = Draw.Measure("Frag Spark", F(10.5f, FontStyle.Bold));
        _title = new Rectangle(pad + face + S(8), y, title.Width + S(4), face);
        _hint = new Rectangle(_title.Right + S(8), y, Math.Max(0, w - pad - _title.Right - S(8)), face);
        y += face + S(10);

        // Eingabezeile unten: Feld mit Mikrofon und Senden darin.
        int inputH = S(58);
        int inputY = h - pad - inputH;
        _input.Padding = new Padding(S(12), S(8), S(6) + ButtonsWidth(), S(8));
        _input.Bounds = new Rectangle(pad, inputY, w - (2 * pad), inputH);
        Size send = _send.Preferred();
        _send.Bounds = new Rectangle(_input.Right - S(8) - send.Width, inputY + ((inputH - send.Height) / 2), send.Width, send.Height);
        _send.Surface = P.Card;
        if (_micShown)
        {
            int m = S(34);
            _mic.Bounds = new Rectangle(_send.Left - S(8) - m, inputY + ((inputH - m) / 2), m, m);
            _mic.Surface = P.Card;
        }

        int statusH = _status.Text.Length > 0 ? Draw.TextHeight(_status.Text, _status.Font, w - (2 * pad)) : 0;
        int statusY = inputY - S(6) - statusH;
        _status.Fit(pad, statusY, w - (2 * pad));

        int chatBottom = (statusH > 0 ? statusY : inputY) - S(8);
        _chat.Bounds = new Rectangle(pad - S(4), y, w - (2 * pad) + S(8), Math.Max(S(40), chatBottom - y));
    }

    protected override void PaintContent(Graphics g)
    {
        Face.Draw(g, _face, P);
        Draw.Text(g, "Frag Spark", F(10.5f, FontStyle.Bold), _title, P.Fg);
        Draw.Text(g, "Enter = Senden · Umschalt+Enter = neue Zeile", F(8.5f), _hint, P.Muted, Draw.Line | TextFormatFlags.Right);
    }

    /// <summary>Mitte des Bildschirms mit dem Mauszeiger – vor dem Erzeugen, damit die Fenster-DPI gleich stimmt.</summary>
    private void PlaceCentered()
    {
        Rectangle area = Screen.FromPoint(Cursor.Position).WorkingArea;
        int dpi = Dwm.DpiAt(Cursor.Position);
        int width = Math.Min(Draw.Scale(520, dpi), area.Width);
        int height = Math.Min(Draw.Scale(560, dpi), area.Height);
        MinimumSize = new Size(Math.Min(Draw.Scale(380, dpi), width), Math.Min(Draw.Scale(340, dpi), height));
        Bounds = new Rectangle(area.Left + ((area.Width - width) / 2), area.Top + ((area.Height - height) / 2), width, height);
    }

    protected override void OnLoad(EventArgs e)
    {
        base.OnLoad(e);
        ActiveControl = _question;
    }

    protected override void OnDpiChanged(DpiChangedEventArgs e)
    {
        base.OnDpiChanged(e);
        MinimumSize = new Size(S(380), S(340));
    }

    /// <summary>Nach vorn holen und den Cursor ins Fragefeld setzen.</summary>
    public void Bring()
    {
        if (WindowState == FormWindowState.Minimized)
        {
            WindowState = FormWindowState.Normal;
        }

        Activate();
        _question.Focus();
    }

    private async Task SendAsync()
    {
        if (_busy)
        {
            return;
        }

        string question = _question.Text.Trim();
        if (question.Length == 0)
        {
            SetStatus("Bitte zuerst eine Frage eingeben.", error: true);
            _question.Focus();
            return;
        }

        string? key = _config.GetKey();
        if (key is null || string.IsNullOrEmpty(_config.Base))
        {
            SetStatus("Der Begleiter ist nicht gekoppelt (Einstellungen → Neu koppeln).", error: true);
            return;
        }

        _chat.Add(mine: true, question);
        _question.Clear();
        _chat.Pending = true;
        SetBusy(true, "");
        _cts = new CancellationTokenSource();
        try
        {
            string answer = await SparkClient.AskAsync(_config.Base, key, question, _cts.Token);
            if (IsDisposed)
            {
                return;
            }

            _chat.Pending = false;
            _chat.Add(mine: false, answer.Trim());
            _question.PlaceholderText = "Frag weiter …";
            SetStatus("", error: false);
        }
        catch (OperationCanceledException)
        {
            // Fenster wurde geschlossen.
        }
        catch (SparkException ex)
        {
            if (!IsDisposed)
            {
                _chat.Pending = false;
                SetStatus(ex.Message, error: true);
                if (_question.TextLength == 0)
                {
                    _question.Text = question; // Frage nicht verlieren
                    _question.SelectionStart = _question.TextLength;
                }
            }

            _report(ex);
        }
        finally
        {
            _cts?.Dispose();
            _cts = null;
            if (!IsDisposed)
            {
                SetBusy(false, null);
                _question.Focus();
            }
        }
    }

    private void CopyText(string text)
    {
        string normalized = text.Replace("\r\n", "\n", StringComparison.Ordinal).Replace("\n", Environment.NewLine, StringComparison.Ordinal);
        SetStatus(ClipboardHelper.TrySetText(normalized, keepOutOfHistory: false)
            ? "Antwort kopiert."
            : "Die Zwischenablage ist gerade gesperrt. Bitte noch einmal versuchen.", error: false);
    }

    /// <summary>Mikrofon: erster Klick startet, zweiter beendet; der erkannte Text kommt ins Fragefeld.</summary>
    private async Task ToggleMicAsync()
    {
        if (_recorder is null)
        {
            Recorder? recorder = Recorder.TryStart(out string error);
            if (recorder is null)
            {
                SetStatus(error, error: true);
                return;
            }

            _recorder = recorder;
            recorder.LimitReached += async (_, _) =>
            {
                if (ReferenceEquals(_recorder, recorder))
                {
                    await ToggleMicAsync();
                }
            };
            _mic.Checked = true;
            _mic.AccessibleName = "Aufnahme beenden";
            _send.Enabled = false;
            _micTimer.Start();
            UpdateMicStatus();
            return;
        }

        Recorder current = _recorder;
        _recorder = null;
        _micTimer.Stop();
        _mic.Checked = false;
        _mic.AccessibleName = "Sprechen";
        byte[]? wav;
        try
        {
            wav = await current.StopAsync();
        }
        finally
        {
            current.Dispose();
        }

        if (wav is null)
        {
            SetStatus("Die Aufnahme war zu kurz.", error: true);
            _send.Enabled = !_busy;
            RefreshParts();
            return;
        }

        string? key = _config.GetKey();
        if (key is null || string.IsNullOrEmpty(_config.Base))
        {
            SetStatus("Der Begleiter ist nicht gekoppelt.", error: true);
            _send.Enabled = !_busy;
            return;
        }

        SetBusy(true, "Der Spark erkennt den Text …");
        _cts = new CancellationTokenSource();
        try
        {
            string text = (await SparkClient.DictateAsync(_config.Base, key, wav, _desk()?.DictateSprache ?? "auto", _cts.Token)).Trim();
            if (IsDisposed)
            {
                return;
            }

            if (text.Length == 0)
            {
                SetStatus("Es wurde nichts erkannt.", error: true);
            }
            else
            {
                string joined = _question.Text.Trim().Length > 0 ? _question.Text.TrimEnd() + " " + text : text;
                _question.Text = joined.Length > MaxQuestion ? joined[..MaxQuestion] : joined;
                _question.SelectionStart = _question.TextLength;
                SetStatus("Erkannt – prüfen und Senden.", error: false);
            }
        }
        catch (OperationCanceledException)
        {
            // Fenster wurde geschlossen.
        }
        catch (SparkException ex)
        {
            if (!IsDisposed)
            {
                SetStatus(ex.Message, error: true);
            }

            _report(ex);
        }
        finally
        {
            _cts?.Dispose();
            _cts = null;
            if (!IsDisposed)
            {
                SetBusy(false, null);
                RefreshParts();
                _question.Focus();
            }
        }
    }

    private void UpdateMicStatus()
    {
        if (_recorder is { } r)
        {
            TimeSpan t = r.Elapsed;
            SetStatus(string.Create(CultureInfo.InvariantCulture, $"Ich höre zu {(int)t.TotalMinutes}:{t.Seconds:00} … (höchstens {Recorder.MaxSeconds} s; ■ zum Beenden)"), error: false);
        }
    }

    private void SetBusy(bool busy, string? text)
    {
        _busy = busy;
        _send.Enabled = !busy;
        _mic.Enabled = !busy;
        if (text is not null)
        {
            SetStatus(text, error: false);
        }
    }

    private void SetStatus(string text, bool error)
    {
        _status.Text = text;
        _status.Role = error ? TextRole.Error : TextRole.SmallMuted;
        _status.ApplyTheme(DeviceDpi);
        if (IsHandleCreated)
        {
            LayoutContent();
        }
    }

    protected override bool ProcessCmdKey(ref Message msg, Keys keyData)
    {
        if (keyData == Keys.Escape)
        {
            Close();
            return true;
        }

        if (keyData == (Keys.Control | Keys.C) && _question.SelectionLength == 0 && _chat.LastAnswer is { } last)
        {
            CopyText(last);
            return true;
        }

        return base.ProcessCmdKey(ref msg, keyData);
    }

    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        _cts?.Cancel();
        _micTimer.Stop();
        _recorder?.Dispose();
        _recorder = null;
        base.OnFormClosing(e);
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            _micTimer.Dispose();
            _recorder?.Dispose();
        }

        base.Dispose(disposing);
    }
}

/// <summary>
/// Verlauf als Sprechblasen, selbst gezeichnet: eigene Fragen rechts mit Akzent-Verlauf, Antworten links als
/// weiche Karte mit dem Gesicht daneben und „Kopieren“ darunter. Rechtsklick auf eine Blase: Kopieren.
/// </summary>
internal sealed class ChatView : Panel, IThemed
{
    private readonly List<(bool Mine, string Text)> _messages = new();
    private readonly List<Block> _blocks = new();
    private readonly System.Windows.Forms.Timer _dots = new() { Interval = 400 };
    private readonly ContextMenuStrip _menu = new();
    private int _dpi = 96;
    private int _dotCount;
    private bool _pending;
    private int _hoverCopy = -1;
    private int _menuIndex = -1;

    public ChatView()
    {
        SetStyle(ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint | ControlStyles.ResizeRedraw | ControlStyles.UserPaint, true);
        AutoScroll = true;
        TabStop = false;
        AccessibleRole = AccessibleRole.List;
        AccessibleName = "Unterhaltung";
        _dots.Tick += (_, _) =>
        {
            _dotCount = (_dotCount + 1) % 4;
            Invalidate();
        };
        _menu.Items.Add(new ToolStripMenuItem("Kopieren", null, (_, _) =>
        {
            if (_menuIndex >= 0 && _menuIndex < _messages.Count)
            {
                Copied?.Invoke(this, _messages[_menuIndex].Text);
            }
        }));
        HandleCreated += (_, _) => Dwm.ScrollbarTheme(this, Theme.Current.Dark);
    }

    /// <summary>„Kopieren“ wurde gewählt (Text der Blase).</summary>
    public event EventHandler<string>? Copied;

    public string? LastAnswer => _messages.LastOrDefault(m => !m.Mine).Text;

    /// <summary>„Der Spark denkt nach …“ als Blase zeigen.</summary>
    public bool Pending
    {
        get => _pending;
        set
        {
            _pending = value;
            if (value)
            {
                _dots.Start();
            }
            else
            {
                _dots.Stop();
            }

            Relayout(scrollToEnd: true);
        }
    }

    public void Add(bool mine, string text)
    {
        _messages.Add((mine, text));
        AccessibleDescription = (mine ? "Du: " : "Spark: ") + text;
        Relayout(scrollToEnd: true);
    }

    public void ApplyTheme(int dpi)
    {
        _dpi = dpi;
        BackColor = Theme.Current.Card;
        Font = Theme.UiFont(dpi, 10f);
        Dwm.ScrollbarTheme(this, Theme.Current.Dark);
        Relayout(scrollToEnd: false);
    }

    private int S(float v) => Draw.Scale(v, _dpi);

    private sealed record Block(int Index, bool Mine, string Text, Rectangle Bubble, Rectangle TextRect, Rectangle Avatar, Rectangle Copy);

    private const TextFormatFlags TextFlags = TextFormatFlags.WordBreak | TextFormatFlags.TextBoxControl | TextFormatFlags.NoPrefix;

    private void Relayout(bool scrollToEnd)
    {
        _blocks.Clear();
        int avail = Math.Max(S(120), ClientSize.Width - S(8));
        int x0 = S(4);
        int y = S(4);
        int padX = S(12);
        int padY = S(9);
        int avatar = S(30);

        IEnumerable<(int Index, bool Mine, string Text)> items = _messages.Select((m, i) => (i, m.Mine, m.Text));
        if (_pending)
        {
            items = items.Append((-1, false, "Der Spark denkt nach"));
        }

        foreach (var (index, mine, text) in items)
        {
            if (mine)
            {
                int maxText = (int)(avail * 0.85) - (2 * padX);
                Size size = TextRenderer.MeasureText(text, Font, new Size(Math.Max(1, maxText), 100000), TextFlags);
                var bubble = new Rectangle(x0 + avail - size.Width - (2 * padX), y, size.Width + (2 * padX), size.Height + (2 * padY));
                _blocks.Add(new Block(index, true, text, bubble, Rectangle.Inflate(bubble, -padX, -padY), Rectangle.Empty, Rectangle.Empty));
                y = bubble.Bottom + S(10);
            }
            else
            {
                int bx = x0 + avatar + S(8);
                int maxText = Math.Max(1, (int)((avail - avatar - S(8)) * 0.92) - (2 * padX));
                Size size = TextRenderer.MeasureText(index < 0 ? text + " ..." : text, Font, new Size(maxText, 100000), TextFlags);
                var bubble = new Rectangle(bx, y, size.Width + (2 * padX), size.Height + (2 * padY));
                Rectangle copy = Rectangle.Empty;
                int bottom = bubble.Bottom;
                if (index >= 0)
                {
                    Font small = Theme.UiFont(_dpi, 8.5f);
                    Size c = Draw.Measure("Kopieren", small);
                    copy = new Rectangle(bx + S(4), bubble.Bottom + S(3), c.Width, c.Height);
                    bottom = copy.Bottom;
                }

                _blocks.Add(new Block(index, false, text, bubble, Rectangle.Inflate(bubble, -padX, -padY), new Rectangle(x0, y, avatar, avatar), copy));
                y = bottom + S(12);
            }
        }

        AutoScrollMinSize = new Size(0, y);
        if (scrollToEnd)
        {
            AutoScrollPosition = new Point(0, y);
        }

        Invalidate();
    }

    protected override void OnResize(EventArgs eventargs)
    {
        base.OnResize(eventargs);
        Relayout(scrollToEnd: false);
    }

    protected override void OnScroll(ScrollEventArgs se)
    {
        base.OnScroll(se);
        Invalidate();
    }

    protected override void OnMouseWheel(MouseEventArgs e)
    {
        base.OnMouseWheel(e);
        Invalidate();
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        Graphics g = e.Graphics;
        Palette p = Theme.Current;
        g.Clear(p.Card);
        Draw.HighQuality(g);
        Point offset = AutoScrollPosition;

        if (_blocks.Count == 0)
        {
            var empty = new Rectangle(S(24), S(24), Math.Max(1, ClientSize.Width - S(48)), Math.Max(1, ClientSize.Height - S(48)));
            TextRenderer.DrawText(g, "Frag den Spark etwas – zum Beispiel nach deinen Terminen. Folgefragen behalten den Zusammenhang.",
                Theme.UiFont(_dpi, 9.5f), empty, p.Muted, TextFlags | TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter);
            return;
        }

        foreach (Block b in _blocks)
        {
            Rectangle bubble = b.Bubble;
            bubble.Offset(offset);
            if (bubble.Bottom < -S(40) || bubble.Top > ClientSize.Height + S(40))
            {
                continue;
            }

            Rectangle text = b.TextRect;
            text.Offset(offset);
            float r = S(14);
            float small = S(4);
            if (b.Mine)
            {
                using System.Drawing.Drawing2D.GraphicsPath path = Draw.Round(bubble, r, r, small, r);
                using Brush brush = Draw.AccentBrush(bubble, p, 45f);
                g.FillPath(brush, path);
                TextRenderer.DrawText(g, b.Text, Font, text, p.OnAccent, TextFlags);
            }
            else
            {
                Rectangle avatar = b.Avatar;
                avatar.Offset(offset);
                Face.Draw(g, avatar, p);
                using (System.Drawing.Drawing2D.GraphicsPath path = Draw.Round(bubble, r, r, r, small))
                {
                    using var fill = new SolidBrush(p.Soft);
                    g.FillPath(fill, path);
                    using var pen = new Pen(p.Line);
                    g.DrawPath(pen, path);
                }

                string shown = b.Index < 0 ? b.Text + " " + new string('.', _dotCount) : b.Text;
                TextRenderer.DrawText(g, shown, Font, text, b.Index < 0 ? p.Muted : p.Fg, TextFlags);
                if (!b.Copy.IsEmpty)
                {
                    Rectangle copy = b.Copy;
                    copy.Offset(offset);
                    Font f = Theme.UiFont(_dpi, 8.5f, b.Index == _hoverCopy ? FontStyle.Underline : FontStyle.Regular);
                    TextRenderer.DrawText(g, "Kopieren", f, copy, b.Index == _hoverCopy ? p.Accent : p.Muted, TextFormatFlags.NoPrefix);
                }
            }
        }
    }

    private Block? HitBlock(Point location, bool copyOnly)
    {
        Point offset = AutoScrollPosition;
        foreach (Block b in _blocks)
        {
            Rectangle copy = b.Copy;
            copy.Offset(offset);
            Rectangle bubble = b.Bubble;
            bubble.Offset(offset);
            if (!copy.IsEmpty && Rectangle.Inflate(copy, S(3), S(2)).Contains(location))
            {
                return b;
            }

            if (!copyOnly && b.Index >= 0 && bubble.Contains(location))
            {
                return b;
            }
        }

        return null;
    }

    protected override void OnMouseMove(MouseEventArgs e)
    {
        base.OnMouseMove(e);
        int hover = HitBlock(e.Location, copyOnly: true)?.Index ?? -1;
        if (hover != _hoverCopy)
        {
            _hoverCopy = hover;
            Cursor = hover >= 0 ? Cursors.Hand : Cursors.Default;
            Invalidate();
        }
    }

    protected override void OnMouseLeave(EventArgs e)
    {
        base.OnMouseLeave(e);
        if (_hoverCopy >= 0)
        {
            _hoverCopy = -1;
            Cursor = Cursors.Default;
            Invalidate();
        }
    }

    protected override void OnMouseClick(MouseEventArgs e)
    {
        base.OnMouseClick(e);
        if (e.Button == MouseButtons.Left && HitBlock(e.Location, copyOnly: true) is { } copy && copy.Index >= 0)
        {
            Copied?.Invoke(this, _messages[copy.Index].Text);
        }
        else if (e.Button == MouseButtons.Right && HitBlock(e.Location, copyOnly: false) is { } block && block.Index >= 0)
        {
            _menuIndex = block.Index;
            _menu.Show(this, e.Location);
        }
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            _dots.Dispose();
            _menu.Dispose();
        }

        base.Dispose(disposing);
    }
}
