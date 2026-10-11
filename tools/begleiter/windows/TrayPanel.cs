namespace SparkBegleiter;

internal enum StatusKind
{
    Ok,
    Off,
    Bad,
    Busy,
}

/// <summary>Eine Zeile im Tray-Fenster (ein eingeschalteter Teil).</summary>
internal sealed record PanelItem(string Text, Glyph Glyph, string? Hotkey, Action Action, bool Danger = false, bool Enabled = true);

/// <summary>Teil "actions": eine Meldung im Tray-Fenster mit ihren Knöpfen (nur die angebotenen sind gesetzt).</summary>
internal sealed record PanelNote(int N, string Title, string Body, Action? Reply, Action? Later, Action? Open);

/// <summary>Der Update-Hinweis im Tray-Fenster.</summary>
internal sealed record UpdateBanner(string Title, string Detail, string? Button, bool ButtonEnabled, double? Progress, bool Error, Action? Action);

/// <summary>Was das Tray-Fenster zeigt; baut <see cref="TrayContext"/> bei jeder Änderung neu.</summary>
internal sealed class PanelModel
{
    public string Subtitle { get; init; } = "";

    public string StatusText { get; init; } = "";

    public StatusKind Status { get; init; }

    /// <summary>Rote Zeile unter dem Kopf (Notaus).</summary>
    public string? Notice { get; init; }

    public UpdateBanner? Update { get; init; }

    public IReadOnlyList<PanelItem> Items { get; init; } = Array.Empty<PanelItem>();

    /// <summary>Meldungen mit Knöpfen (Teil "actions").</summary>
    public IReadOnlyList<PanelNote> Notes { get; init; } = Array.Empty<PanelNote>();

    /// <summary>Leiser Hinweis unter der Liste (z. B. weitere Teile im Panel einschalten).</summary>
    public string? Hint { get; init; }

    public Action? Settings { get; init; }

    public Action? OpenPanel { get; init; }

    public Action? Coffee { get; init; }

    public static Color StatusColor(StatusKind kind, Palette p) => kind switch
    {
        StatusKind.Ok => p.Ok,
        StatusKind.Bad => p.Bad,
        StatusKind.Busy => p.Accent,
        _ => p.Muted,
    };
}

/// <summary>
/// Entwurf A: eigenes randloses Fenster beim Linksklick aufs Symbol, an der Taskleiste verankert.
/// Oben Farbverlauf, Kopf mit Gesicht, Name, Profil · Gerät und Zustands-Pille; darunter der Update-Hinweis,
/// die eingeschalteten Teile mit Tastenkürzel, „Mein Notaus …“ in Rot; unten Einstellungen, Panel öffnen
/// und die gelbe Kaffee-Pille. Schließt bei Fokusverlust und mit Esc.
/// </summary>
internal sealed class TrayPanel : ThemedForm
{
    private const float Width96 = 360;

    private readonly Action<Action> _post;
    private readonly List<SparkButton> _items = new();
    private readonly List<Action> _actions = new();
    private readonly List<(PanelNote Note, List<SparkButton> Buttons)> _notes = new();
    private readonly List<(Rectangle Card, Rectangle Title, Rectangle Body)> _noteRects = new();
    private Rectangle _notesHeading;
    private readonly SparkButton _update = new(ButtonKind.Primary, "Aktualisieren");
    private readonly SparkButton _settings = new(ButtonKind.Secondary, "Einstellungen");
    private readonly SparkButton _panel = new(ButtonKind.Secondary, "Panel öffnen");
    private readonly SparkButton _coffee = new(ButtonKind.Coffee, "☕ Spark unterstützen");

    private PanelModel _model;
    private bool _closing;

    // Zeichenflächen (vom Layout berechnet)
    private Rectangle _face;
    private Rectangle _title;
    private Rectangle _subtitle;
    private Rectangle _pill;
    private Rectangle _notice;
    private Rectangle _banner;
    private Rectangle _bannerIcon;
    private Rectangle _bannerTitle;
    private Rectangle _bannerDetail;
    private Rectangle _hint;
    private int _footLine;

    public TrayPanel(PanelModel model, Action<Action> post)
    {
        _model = model;
        _post = post;

        FormBorderStyle = FormBorderStyle.None;
        ShowInTaskbar = false;
        TopMost = true;
        StartPosition = FormStartPosition.Manual;
        KeyPreview = true;
        Text = TrayContext.Title;
        AccessibleName = TrayContext.Title;

        _update.Click += (_, _) => Run(_model.Update?.Action);
        _settings.Click += (_, _) => Run(_model.Settings);
        _panel.Click += (_, _) => Run(_model.OpenPanel);
        _coffee.Click += (_, _) => Run(_model.Coffee);
        _coffee.AccessibleName = "Spark unterstützen (Buy me a coffee, öffnet den Browser)";
        Controls.Add(_update);
        Controls.Add(_settings);
        Controls.Add(_panel);
        Controls.Add(_coffee);
        BuildItems();
        BuildNotes();
    }

    protected override bool RoundCorners => true;

    protected override bool ShowWithoutActivation => false;

    protected override CreateParams CreateParams
    {
        get
        {
            CreateParams cp = base.CreateParams;
            cp.ClassStyle |= NativeMethods.CS_DROPSHADOW;
            cp.ExStyle |= NativeMethods.WS_EX_TOOLWINDOW;
            return cp;
        }
    }

    /// <summary>Neuer Inhalt, während das Fenster offen ist (z. B. Fortschritt beim Laden).</summary>
    public void SetModel(PanelModel model)
    {
        int focused = _items.FindIndex(b => b.Focused);
        bool sameRows = model.Items.Count == _model.Items.Count &&
            model.Items.Zip(_model.Items).All(pair => pair.First with { Action = pair.Second.Action } == pair.Second);
        _model = model;
        if (sameRows)
        {
            // Nur die Aktionen tauschen – die Zeilen bleiben (kein Flackern, Klick geht nicht verloren).
            _actions.Clear();
            _actions.AddRange(model.Items.Select(i => i.Action));
        }
        else
        {
            BuildItems();
        }

        BuildNotes();
        RefreshTheme();
        PlaceAtTray();
        if (focused >= 0 && focused < _items.Count)
        {
            _items[focused].Focus();
        }
    }

    /// <summary>An der Taskleiste beim Mauszeiger (bzw. beim Infobereich) zeigen und aktivieren.</summary>
    public void ShowAtTray()
    {
        // Zuerst auf den richtigen Bildschirm, damit Fenster-DPI und Maße stimmen.
        Rectangle area = Screen.FromPoint(Cursor.Position).WorkingArea;
        Location = new Point(area.Left + ((area.Width - Width) / 2), area.Top + ((area.Height - Height) / 2));
        _ = Handle;
        RefreshTheme();
        PlaceAtTray();
        Show();
        Activate();
        if (NativeMethods.GetForegroundWindow() != Handle)
        {
            // Nach dem Klick aufs Symbol darf der Begleiter nach vorn; falls Activate nicht reichte, direkt.
            _ = NativeMethods.SetForegroundWindow(Handle);
        }

        if (_items.Count > 0)
        {
            _items[0].Focus();
        }
        else
        {
            _settings.Focus();
        }
    }

    private void BuildItems()
    {
        foreach (SparkButton old in _items)
        {
            Controls.Remove(old);
            old.Dispose();
        }

        _items.Clear();
        _actions.Clear();
        int index = 0;
        foreach (PanelItem item in _model.Items)
        {
            var button = new SparkButton(ButtonKind.Item, item.Text)
            {
                Glyph = item.Glyph,
                Hotkey = item.Hotkey,
                Danger = item.Danger,
                Enabled = item.Enabled,
                TabIndex = index++,
            };
            if (item.Hotkey is { Length: > 0 } hotkey)
            {
                button.AccessibleDescription = "Tastenkürzel " + hotkey;
            }

            int slot = _actions.Count;
            _actions.Add(item.Action);
            button.Click += (_, _) => Run(slot < _actions.Count ? _actions[slot] : null);
            _items.Add(button);
            Controls.Add(button);
        }

        _update.TabIndex = 100;
        _settings.TabIndex = 101;
        _panel.TabIndex = 102;
        _coffee.TabIndex = 103;
    }

    private void BuildNotes()
    {
        foreach (var (_, buttons) in _notes)
        {
            foreach (SparkButton b in buttons)
            {
                Controls.Remove(b);
                b.Dispose();
            }
        }

        _notes.Clear();
        int tab = 50;
        foreach (PanelNote note in _model.Notes)
        {
            var buttons = new List<SparkButton>();
            foreach (var (label, action) in new (string, Action?)[] { ("Antworten", note.Reply), ("Später", note.Later), ("Panel öffnen", note.Open) })
            {
                if (action is null)
                {
                    continue;
                }

                var button = new SparkButton(ButtonKind.Secondary, label) { FontSize = 8.5f, TabIndex = tab++ };
                button.AccessibleDescription = "Meldung: " + note.Title;
                Action run = action;
                button.Click += (_, _) => Run(run);
                buttons.Add(button);
                Controls.Add(button);
            }

            _notes.Add((note, buttons));
        }
    }

    private void Run(Action? action)
    {
        if (action is null)
        {
            return;
        }

        Close();
        _post(action);
    }

    protected override void LayoutContent()
    {
        PanelModel m = _model;
        int pad = S(14);
        int width = S(Width96);

        // Breite nach dem Fuß richten, falls Schrift/Text breiter ist.
        int foot = _settings.Preferred().Width + S(6) + (m.OpenPanel is not null ? _panel.Preferred().Width + S(6) : 0)
                   + S(12) + (m.Coffee is not null ? _coffee.Preferred().Width : 0);
        width = Math.Max(width, foot + (2 * pad));
        int inner = width - (2 * pad);

        int y = BarHeight + pad;

        // Kopf
        int face = S(44);
        _face = new Rectangle(pad, y, face, face);
        Font pillFont = F(8.5f, FontStyle.Bold);
        Size pill = Draw.PillSize(m.StatusText, pillFont, DeviceDpi);
        _pill = new Rectangle(width - pad - pill.Width, y + ((face - pill.Height) / 2), pill.Width, pill.Height);
        int textX = pad + face + S(12);
        int textW = Math.Max(10, _pill.X - S(8) - textX);
        int titleH = Draw.Measure("Ag", F(10.5f, FontStyle.Bold)).Height;
        int subH = Draw.Measure("Ag", F(8.5f)).Height;
        int top = y + ((face - titleH - subH) / 2);
        _title = new Rectangle(textX, top, textW, titleH);
        _subtitle = new Rectangle(textX, top + titleH, textW, subH);
        y += face + S(12);

        // Notaus-Zeile
        if (!string.IsNullOrEmpty(m.Notice))
        {
            int h = Draw.TextHeight(m.Notice, F(9f), inner);
            _notice = new Rectangle(pad, y, inner, h);
            y += h + S(10);
        }
        else
        {
            _notice = Rectangle.Empty;
        }

        // Update-Hinweis
        if (m.Update is { } u)
        {
            Size button = _update.Preferred();
            int bannerPad = S(10);
            int icon = S(28);
            int textLeft = pad + bannerPad + icon + S(10);
            int textRight = u.Button is not null ? width - pad - bannerPad - button.Width - S(10) : width - pad - bannerPad;
            int tw = Math.Max(10, textRight - textLeft);
            int th = Draw.Measure("Ag", F(9f, FontStyle.Bold)).Height;
            int dh = Math.Min(Draw.TextHeight(u.Detail, F(8.5f), tw), subH * 3);
            int contentH = Math.Max(Math.Max(icon, button.Height), th + dh);
            int bannerH = contentH + (2 * bannerPad) + (u.Progress is not null ? S(6) : 0);
            _banner = new Rectangle(pad, y, inner, bannerH);
            int cy = y + bannerPad;
            _bannerIcon = new Rectangle(pad + bannerPad, cy + ((contentH - icon) / 2), icon, icon);
            int textTop = cy + ((contentH - th - dh) / 2);
            _bannerTitle = new Rectangle(textLeft, textTop, tw, th);
            _bannerDetail = new Rectangle(textLeft, textTop + th, tw, dh);
            _update.Visible = u.Button is not null;
            _update.Text = u.Button ?? "";
            _update.Enabled = u.ButtonEnabled;
            _update.Surface = P.BannerBack;
            _update.Bounds = new Rectangle(width - pad - bannerPad - button.Width, cy + ((contentH - button.Height) / 2), button.Width, button.Height);
            y += bannerH + S(12);
        }
        else
        {
            _banner = Rectangle.Empty;
            _update.Visible = false;
        }

        // Teile
        foreach (SparkButton item in _items)
        {
            int h = S(44);
            item.Bounds = new Rectangle(pad - S(4), y, inner + S(8), h);
            y += h + S(2);
        }

        if (_items.Count > 0)
        {
            y += S(4);
        }

        // Meldungen mit Knöpfen
        _noteRects.Clear();
        if (_notes.Count > 0)
        {
            int headH = Draw.Measure("Ag", F(8.5f, FontStyle.Bold)).Height;
            _notesHeading = new Rectangle(pad, y, inner, headH);
            y += headH + S(6);
            foreach (var (note, buttons) in _notes)
            {
                int cardPad = S(10);
                int tw = inner - (2 * cardPad);
                int th = Draw.Measure("Ag", F(9f, FontStyle.Bold)).Height;
                int lineH = Draw.Measure("Ag", F(8.5f)).Height;
                int bh = note.Body.Length > 0 ? Math.Min(Draw.TextHeight(note.Body, F(8.5f), tw), lineH * 2) : 0;
                int by = y + cardPad + th + (bh > 0 ? S(2) + bh : 0) + S(8);
                int bx = pad + cardPad;
                int rowH = 0;
                foreach (SparkButton b in buttons)
                {
                    Size size = b.Preferred();
                    size.Height = Math.Min(size.Height, S(28));
                    b.Bounds = new Rectangle(bx, by, size.Width, size.Height);
                    b.Surface = P.Soft;
                    bx += size.Width + S(6);
                    rowH = Math.Max(rowH, size.Height);
                }

                int cardH = (by - y) + rowH + cardPad;
                _noteRects.Add((new Rectangle(pad, y, inner, cardH), new Rectangle(pad + cardPad, y + cardPad, tw, th),
                    new Rectangle(pad + cardPad, y + cardPad + th + S(2), tw, bh)));
                y += cardH + S(8);
            }

            y += S(2);
        }
        else
        {
            _notesHeading = Rectangle.Empty;
        }

        if (!string.IsNullOrEmpty(m.Hint))
        {
            int h = Draw.TextHeight(m.Hint, F(8.5f), inner);
            _hint = new Rectangle(pad, y, inner, h);
            y += h + S(10);
        }
        else
        {
            _hint = Rectangle.Empty;
        }

        // Fuß
        _footLine = y;
        y += S(10);
        Size settings = _settings.Preferred();
        _settings.Bounds = new Rectangle(pad, y, settings.Width, settings.Height);
        // Hinweis: Visible eines Kindes liest sich vor dem Anzeigen als false – daher das Modell fragen.
        _settings.Visible = m.Settings is not null;
        int x = m.Settings is not null ? _settings.Right + S(6) : pad;
        _panel.Visible = m.OpenPanel is not null;
        if (m.OpenPanel is not null)
        {
            Size panel = _panel.Preferred();
            _panel.Bounds = new Rectangle(x, y, panel.Width, panel.Height);
        }

        _coffee.Visible = m.Coffee is not null;
        if (m.Coffee is not null)
        {
            Size coffee = _coffee.Preferred();
            _coffee.Bounds = new Rectangle(width - pad - coffee.Width, y + ((settings.Height - coffee.Height) / 2), coffee.Width, coffee.Height);
        }

        y += settings.Height + pad;
        ClientSize = new Size(width, y);
    }

    protected override void PaintContent(Graphics g)
    {
        Draw.HighQuality(g);
        Palette p = P;
        PanelModel m = _model;

        if (!p.HighContrast)
        {
            // Rand für Windows 10 (Windows 11 zeichnet ihn über DWM).
            using var pen = new Pen(p.Line);
            g.DrawRectangle(pen, 0, 0, ClientSize.Width - 1, ClientSize.Height - 1);
        }
        else
        {
            using var pen = new Pen(p.Fg);
            g.DrawRectangle(pen, 0, 0, ClientSize.Width - 1, ClientSize.Height - 1);
        }

        Face.Draw(g, _face, p);
        Draw.Text(g, TrayContext.Title, F(10.5f, FontStyle.Bold), _title, p.Fg);
        Draw.Text(g, m.Subtitle, F(8.5f), _subtitle, p.Muted);
        Draw.Pill(g, _pill, m.StatusText, F(8.5f, FontStyle.Bold), PanelModel.StatusColor(m.Status, p), p, DeviceDpi);

        if (!_notice.IsEmpty && m.Notice is { } notice)
        {
            Draw.Text(g, notice, F(9f), _notice, p.Bad, Draw.Wrap);
        }

        if (!_banner.IsEmpty && m.Update is { } u)
        {
            Draw.FillRound(g, p.BannerBack, _banner, S(10));
            Draw.StrokeRound(g, u.Error ? p.Bad : p.BannerLine, _banner, S(10));
            Draw.FillRound(g, p.Card, _bannerIcon, S(8));
            float gs = S(16);
            Glyphs.Draw(g, Glyph.Download, new RectangleF(_bannerIcon.X + ((_bannerIcon.Width - gs) / 2f), _bannerIcon.Y + ((_bannerIcon.Height - gs) / 2f), gs, gs), u.Error ? p.Bad : p.Accent);
            Draw.Text(g, u.Title, F(9f, FontStyle.Bold), _bannerTitle, p.Fg);
            Draw.Text(g, u.Detail, F(8.5f), _bannerDetail, u.Error ? p.Bad : p.Muted, Draw.Wrap | TextFormatFlags.EndEllipsis);

            if (u.Progress is double progress)
            {
                var track = new Rectangle(_banner.X + S(10), _banner.Bottom - S(10), _banner.Width - S(20), S(4));
                Draw.FillRound(g, p.Line, track, track.Height / 2f);
                int done = (int)Math.Round(track.Width * Math.Clamp(progress, 0, 1));
                if (done > track.Height)
                {
                    var bar = new Rectangle(track.X, track.Y, done, track.Height);
                    using Brush brush = Draw.AccentBrush(bar, p, 0f);
                    using System.Drawing.Drawing2D.GraphicsPath path = Draw.Round(bar, bar.Height / 2f);
                    g.FillPath(brush, path);
                }
            }
        }

        if (!_notesHeading.IsEmpty)
        {
            Draw.Text(g, "Meldungen", F(8.5f, FontStyle.Bold), _notesHeading, p.Muted);
            for (int i = 0; i < _noteRects.Count && i < _notes.Count; i++)
            {
                var (card, title, body) = _noteRects[i];
                PanelNote note = _notes[i].Note;
                Draw.FillRound(g, p.Soft, card, S(10));
                Draw.StrokeRound(g, p.Line, card, S(10));
                Draw.Text(g, note.Title, F(9f, FontStyle.Bold), title, p.Fg);
                if (body.Height > 0)
                {
                    Draw.Text(g, note.Body, F(8.5f), body, p.Muted, Draw.Wrap | TextFormatFlags.EndEllipsis);
                }
            }
        }

        if (!_hint.IsEmpty && m.Hint is { } hint)
        {
            Draw.Text(g, hint, F(8.5f), _hint, p.Muted, Draw.Wrap);
        }

        using (var line = new Pen(p.Line))
        {
            g.DrawLine(line, S(14), _footLine, ClientSize.Width - S(14), _footLine);
        }
    }

    /// <summary>
    /// Neben die Taskleiste setzen: beim Mauszeiger, wenn er auf der Taskleiste ist (Klick aufs Symbol),
    /// sonst in die Ecke beim Infobereich. Taskleiste unten, oben, links oder rechts; auch automatisch ausgeblendet.
    /// </summary>
    private void PlaceAtTray()
    {
        Point cursor = Cursor.Position;
        Screen screen = Screen.FromPoint(cursor);
        Rectangle bounds = screen.Bounds;
        Rectangle work = screen.WorkingArea;
        int gap = S(10);

        uint edge = NativeMethods.ABE_BOTTOM;
        Rectangle bar;
        if (work.Bottom < bounds.Bottom)
        {
            bar = Rectangle.FromLTRB(bounds.Left, work.Bottom, bounds.Right, bounds.Bottom);
        }
        else if (work.Top > bounds.Top)
        {
            edge = NativeMethods.ABE_TOP;
            bar = Rectangle.FromLTRB(bounds.Left, bounds.Top, bounds.Right, work.Top);
        }
        else if (work.Left > bounds.Left)
        {
            edge = NativeMethods.ABE_LEFT;
            bar = Rectangle.FromLTRB(bounds.Left, bounds.Top, work.Left, bounds.Bottom);
        }
        else if (work.Right < bounds.Right)
        {
            edge = NativeMethods.ABE_RIGHT;
            bar = Rectangle.FromLTRB(work.Right, bounds.Top, bounds.Right, bounds.Bottom);
        }
        else
        {
            // Automatisch ausgeblendet: Lage über die Shell erfragen.
            bar = Rectangle.FromLTRB(bounds.Left, bounds.Bottom - S(48), bounds.Right, bounds.Bottom);
            try
            {
                var data = new NativeMethods.APPBARDATA { cbSize = System.Runtime.InteropServices.Marshal.SizeOf<NativeMethods.APPBARDATA>() };
                if (NativeMethods.SHAppBarMessage(NativeMethods.ABM_GETTASKBARPOS, ref data) != UIntPtr.Zero)
                {
                    edge = data.uEdge;
                    bar = Rectangle.FromLTRB(data.rc.Left, data.rc.Top, data.rc.Right, data.rc.Bottom);
                    if (!bar.IntersectsWith(bounds))
                    {
                        bar = Rectangle.FromLTRB(bounds.Left, bounds.Bottom - S(48), bounds.Right, bounds.Bottom);
                        edge = NativeMethods.ABE_BOTTOM;
                    }
                }
            }
            catch (EntryPointNotFoundException)
            {
                // unten annehmen
            }
        }

        bool onBar = bar.Contains(cursor);
        int w = Width;
        int h = Height;
        int x;
        int y;
        switch (edge)
        {
            case NativeMethods.ABE_TOP:
                y = Math.Max(bar.Bottom, work.Top) + gap;
                x = onBar ? cursor.X - (w / 2) : work.Right - w - gap;
                break;
            case NativeMethods.ABE_LEFT:
                x = Math.Max(bar.Right, work.Left) + gap;
                y = onBar ? cursor.Y - (h / 2) : work.Bottom - h - gap;
                break;
            case NativeMethods.ABE_RIGHT:
                x = Math.Min(bar.Left, work.Right) - w - gap;
                y = onBar ? cursor.Y - (h / 2) : work.Bottom - h - gap;
                break;
            default:
                y = Math.Min(bar.Top, work.Bottom) - h - gap;
                x = onBar ? cursor.X - (w / 2) : work.Right - w - gap;
                break;
        }

        x = Math.Clamp(x, bounds.Left + gap, Math.Max(bounds.Left + gap, bounds.Right - w - gap));
        y = Math.Clamp(y, bounds.Top + gap, Math.Max(bounds.Top + gap, bounds.Bottom - h - gap));
        Location = new Point(x, y);
    }

    protected override void OnDpiChanged(DpiChangedEventArgs e)
    {
        base.OnDpiChanged(e);
        PlaceAtTray();
    }

    protected override bool ProcessCmdKey(ref Message msg, Keys keyData)
    {
        switch (keyData)
        {
            case Keys.Escape:
                Close();
                return true;
            case Keys.Down:
                SelectNextControl(ActiveControl, forward: true, tabStopOnly: true, nested: true, wrap: true);
                return true;
            case Keys.Up:
                SelectNextControl(ActiveControl, forward: false, tabStopOnly: true, nested: true, wrap: true);
                return true;
            default:
                return base.ProcessCmdKey(ref msg, keyData);
        }
    }

    protected override void OnDeactivate(EventArgs e)
    {
        base.OnDeactivate(e);
        if (!_closing && Visible)
        {
            BeginInvoke(new Action(Close));
        }
    }

    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        _closing = true;
        base.OnFormClosing(e);
    }
}
