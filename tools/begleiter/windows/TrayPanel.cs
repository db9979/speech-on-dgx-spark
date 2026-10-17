namespace SparkBegleiter;

internal enum StatusKind
{
    Ok,
    Off,
    Bad,
    Busy,
}

/// <summary>Wo ein Teil im Begleiter-Fenster steht (Dominik 2026-10-17 „Begleiter aufpolieren“, Entwurf 1a).</summary>
internal enum PanelItemKind
{
    /// <summary>Befehl als Kachel im Raster (Text verbessern, Diktieren, …).</summary>
    Tile,

    /// <summary>Schalter unter „Dieser Rechner“ (Mikrofon, Weckwort); das Fenster bleibt offen.</summary>
    Toggle,

    /// <summary>Zeile unter „Dieser Rechner“ mit einer Tätigkeit rechts (Wissen-Ordner „Öffnen“).</summary>
    Row,

    /// <summary>Link unten rechts im Fuß (Notaus, rot).</summary>
    Footer,
}

/// <summary>Ein eingeschalteter Teil im Tray-Fenster: Kachel, Schalter, Zeile oder Link im Fuß.</summary>
/// <param name="On">Nur <see cref="PanelItemKind.Toggle"/>: der Schalter steht auf an.</param>
/// <param name="Verb">Nur <see cref="PanelItemKind.Row"/>: die Tätigkeit rechts, z. B. „Öffnen“.</param>
internal sealed record PanelItem(string Text, Glyph Glyph, string? Hotkey, Action Action, bool Danger = false, bool Enabled = true,
    PanelItemKind Kind = PanelItemKind.Tile, string? Detail = null, bool On = false, string? Verb = null);

/// <summary>Teil "actions": eine Meldung im Tray-Fenster mit ihren Knöpfen (nur die angebotenen sind gesetzt).</summary>
/// <param name="Done">„OK“: die Meldung ist gesehen und verschwindet; das Fenster bleibt offen (Dominik 2026-10-16).</param>
internal sealed record PanelNote(int N, string Title, string Body, Action? Reply, Action? Later, Action? Open, Action? Remind = null, Action? Done = null);

/// <summary>Teil "agenda": eine Zeile unter „Als Nächstes“ (Zeit, Text, Ort/Hinweis).</summary>
internal sealed record PanelLine(string When, string Text, string Detail);

/// <summary>Teil "home": ein Knopf unter „Zuhause“ (Schalter mit Zustand, Szene oder Skript).</summary>
internal sealed record PanelHomeButton(string Name, bool Toggle, bool? On, bool Enabled, Action Action);

/// <summary>Der Update-Hinweis im Tray-Fenster.</summary>
internal sealed record UpdateBanner(string Title, string Detail, string? Button, bool ButtonEnabled, double? Progress, bool Error, Action? Action);

/// <summary>Was das Tray-Fenster zeigt; baut <see cref="TrayContext"/> bei jeder Änderung neu.</summary>
internal sealed class PanelModel
{
    /// <summary>Überschrift im Kopf, z. B. „Guten Morgen, Dominik“.</summary>
    public string Title { get; init; } = TrayContext.Title;

    /// <summary>Zeile unter der Überschrift (Gerät); der Zustand steht mit Punkt dahinter.</summary>
    public string Subtitle { get; init; } = "";

    public string StatusText { get; init; } = "";

    public StatusKind Status { get; init; }

    /// <summary>Rote Zeile unter dem Kopf (Notaus).</summary>
    public string? Notice { get; init; }

    public UpdateBanner? Update { get; init; }

    public IReadOnlyList<PanelItem> Items { get; init; } = Array.Empty<PanelItem>();

    /// <summary>Teil "ask": das Fragefeld oben; der Text (auch leer) geht an „Frag Spark“. <c>null</c> = kein Feld.</summary>
    public Action<string>? Ask { get; init; }

    /// <summary>Tastenkürzel von „Frag Spark“ (steht im leeren Fragefeld).</summary>
    public string? AskHotkey { get; init; }

    /// <summary>Mikrofon im Fragefeld (nur mit Teil "dictate"): „Frag Spark“ öffnen und gleich zuhören.</summary>
    public Action? AskVoice { get; init; }

    /// <summary>Meldungen mit Knöpfen (Teil "actions").</summary>
    public IReadOnlyList<PanelNote> Notes { get; init; } = Array.Empty<PanelNote>();

    /// <summary>Teil "agenda": Zeilen unter „Als Nächstes“; <c>null</c> = Abschnitt fehlt.</summary>
    public IReadOnlyList<PanelLine>? Agenda { get; init; }

    /// <summary>Text, wenn <see cref="Agenda"/> leer ist (z. B. „Nichts in den nächsten 24 Stunden.“).</summary>
    public string? AgendaEmpty { get; init; }

    /// <summary>Teil "home": Knöpfe unter „Zuhause“; <c>null</c> = Abschnitt fehlt.</summary>
    public IReadOnlyList<PanelHomeButton>? Home { get; init; }

    /// <summary>Zeile unter den Zuhause-Knöpfen (z. B. Fehler oder „lädt …“).</summary>
    public string? HomeNote { get; init; }

    /// <summary>Leiser Hinweis unter der Liste (z. B. weitere Teile im Panel einschalten).</summary>
    public string? Hint { get; init; }

    public Action? Settings { get; init; }

    public Action? OpenPanel { get; init; }

    public static Color StatusColor(StatusKind kind, Palette p) => kind switch
    {
        StatusKind.Ok => p.Ok,
        StatusKind.Bad => p.Bad,
        StatusKind.Busy => p.Accent,
        _ => p.Muted,
    };
}

/// <summary>
/// Begleiter-Fenster beim Linksklick aufs Symbol, an der Taskleiste verankert (Entwurf „Begleiter aufpolieren“ 1a,
/// Dominik 2026-10-17): oben Farbverlauf und Kopf mit Gesicht, Gruß, Gerät und Zustandspunkt, rechts Einstellungen
/// und Schließen; darunter der Update-Hinweis, das Fragefeld „Frag Spark …“, die Befehle als Kacheln, dann Abschnitte
/// wie im Panel (Als Nächstes, Meldungen, Zuhause, Dieser Rechner mit Schaltern); unten „Panel öffnen“ und Notaus.
/// Der Kaffee steht nur noch unter Einstellungen → Über und Update. Schließt bei Fokusverlust und mit Esc.
/// </summary>
internal sealed class TrayPanel : ThemedForm
{
    private const float Width96 = 360;
    private const int Columns = 3;
    private const int MaxQuestion = 2000;

    private readonly Action<Action> _post;
    private readonly List<SparkButton> _items = new();
    private readonly List<Action> _actions = new();
    private readonly List<(PanelNote Note, List<SparkButton> Buttons)> _notes = new();
    private readonly List<(Rectangle Card, Rectangle Title, Rectangle Body)> _noteRects = new();
    private Rectangle _notesHeading;
    private readonly List<SparkButton> _home = new();
    private readonly List<Action> _homeActions = new();
    private Rectangle _agendaHeading;
    private Rectangle _agendaBox;
    private readonly List<(Rectangle When, Rectangle Text, Rectangle Detail)> _agendaRects = new();
    private readonly List<int> _agendaLines = new();
    private Rectangle _agendaEmpty;
    private Rectangle _homeHeading;
    private Rectangle _homeNote;
    private Rectangle _rowsHeading;
    private Rectangle _rowsBox;
    private readonly List<int> _rowLines = new();
    private readonly SparkButton _update = new(ButtonKind.Primary, "Aktualisieren");
    private readonly SparkButton _settings = new(ButtonKind.Icon) { Glyph = Glyph.Gear, AccessibleName = "Einstellungen" };
    private readonly SparkButton _close = new(ButtonKind.Icon) { Glyph = Glyph.Close, AccessibleName = "Schließen" };
    private readonly SparkButton _panel = new(ButtonKind.Link, "Panel öffnen") { Glyph = Glyph.External, AccessibleName = "Panel öffnen (im Browser)" };
    private readonly TextBox _ask = new() { MaxLength = MaxQuestion, AccessibleName = "Frag Spark" };
    private readonly RoundedHost _askHost;
    private readonly SparkButton _askMic = new(ButtonKind.Primary) { Glyph = Glyph.Mic, AccessibleName = "Frag Spark: sprechen" };
    private readonly ToolTip _tips = new();

    private PanelModel _model;
    private bool _closing;

    // Zeichenflächen (vom Layout berechnet)
    private Rectangle _face;
    private Rectangle _title;
    private Rectangle _subtitle;
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
        _askHost = new RoundedHost(_ask) { Accessory = _askMic };

        FormBorderStyle = FormBorderStyle.None;
        ShowInTaskbar = false;
        TopMost = true;
        StartPosition = FormStartPosition.Manual;
        KeyPreview = true;
        Text = TrayContext.Title;
        AccessibleName = TrayContext.Title;

        _update.Click += (_, _) => Run(_model.Update?.Action);
        _settings.Click += (_, _) => Run(_model.Settings);
        _close.Click += (_, _) => Close();
        _panel.Click += (_, _) => Run(_model.OpenPanel);
        _askMic.Click += (_, _) => Run(_model.AskVoice);
        _ask.KeyDown += (_, e) =>
        {
            if (e.KeyCode == Keys.Enter && e.Modifiers == Keys.None)
            {
                e.SuppressKeyPress = true;
                SendAsk();
            }
        };
        _tips.SetToolTip(_settings, "Einstellungen");
        _tips.SetToolTip(_close, "Schließen (Esc)");
        _ask.TabIndex = 0;
        Controls.Add(_update);
        Controls.Add(_settings);
        Controls.Add(_close);
        Controls.Add(_panel);
        Controls.Add(_askHost);
        BuildItems();
        BuildNotes();
        BuildHome();
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

        int homeFocused = _home.FindIndex(b => b.Focused);
        BuildNotes();
        BuildHome();
        RefreshTheme();
        PlaceAtTray();
        if (focused >= 0 && focused < _items.Count)
        {
            _items[focused].Focus();
        }
        else if (homeFocused >= 0 && homeFocused < _home.Count)
        {
            _home[homeFocused].Focus();
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

        if (_model.Ask is not null)
        {
            _ask.Focus(); // gleich lostippen
        }
        else if (_items.Count > 0)
        {
            _items[0].Focus();
        }
        else
        {
            _settings.Focus();
        }
    }

    private void SendAsk()
    {
        if (_model.Ask is not { } ask)
        {
            return;
        }

        string question = _ask.Text.Trim();
        Close();
        _post(() => ask(question));
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
        int index = 1;
        foreach (PanelItem item in _model.Items)
        {
            ButtonKind kind = item.Kind switch
            {
                PanelItemKind.Toggle => ButtonKind.Toggle,
                PanelItemKind.Row => ButtonKind.Row,
                PanelItemKind.Footer => ButtonKind.Link,
                _ => ButtonKind.Tile,
            };
            var button = new SparkButton(kind, item.Text)
            {
                Glyph = item.Glyph,
                Hotkey = item.Hotkey,
                Danger = item.Danger,
                Enabled = item.Enabled,
                Detail = item.Detail,
                Verb = item.Verb,
                Tint = TintFor(item.Glyph),
                TabIndex = item.Kind == PanelItemKind.Footer ? 104 : item.Kind == PanelItemKind.Tile ? index++ : 90 + index++,
            };
            button.Checked = item.Kind == PanelItemKind.Toggle && item.On;
            if (item.Kind == PanelItemKind.Toggle)
            {
                button.AccessibleName = $"{item.Text}, {(item.On ? "an" : "aus")}";
            }

            if (item.Hotkey is { Length: > 0 } hotkey)
            {
                button.AccessibleDescription = "Tastenkürzel " + hotkey;
            }

            int slot = _actions.Count;
            _actions.Add(item.Action);
            bool stay = item.Kind == PanelItemKind.Toggle; // Schalter: das Fenster bleibt offen und zeigt den neuen Stand
            button.Click += (_, _) =>
            {
                Action? action = slot < _actions.Count ? _actions[slot] : null;
                if (stay && action is not null)
                {
                    _post(action);
                }
                else
                {
                    Run(action);
                }
            };
            _items.Add(button);
            Controls.Add(button);
        }

        _update.TabIndex = 100;
        _panel.TabIndex = 103;
        _settings.TabIndex = 110;
        _close.TabIndex = 111;
    }

    /// <summary>Farbe des Kachel-Symbols: je Befehl eine eigene, aus den Panel-Farben gemischt.</summary>
    private static Color? TintFor(Glyph glyph)
    {
        Palette p = Theme.Current;
        return glyph switch
        {
            Glyph.Mic => p.Accent2,
            Glyph.Screen => Palette.Mix(p.Accent, p.Accent2, 0.35f),
            Glyph.Mail => Palette.Mix(p.Accent, p.Accent2, 0.6f),
            Glyph.Speaker => Palette.Mix(p.Accent2, p.Ok, 0.5f),
            Glyph.Record => p.Bad,
            _ => null,
        };
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
            foreach (var (label, action) in new (string, Action?)[] { ("OK", note.Done), ("Antworten", note.Reply), ("Später", note.Later), ("In 20 Min erinnern", note.Remind), ("Panel öffnen", note.Open) })
            {
                if (action is null)
                {
                    continue;
                }

                var button = new SparkButton(ButtonKind.Secondary, label) { FontSize = 8.5f, TabIndex = tab++ };
                button.AccessibleDescription = "Meldung: " + note.Title;
                Action run = action;
                bool stay = ReferenceEquals(action, note.Done); // „OK“: weitere Meldungen gleich mit bestätigen
                button.Click += (_, _) =>
                {
                    if (stay)
                    {
                        _post(run);
                    }
                    else
                    {
                        Run(run);
                    }
                };
                buttons.Add(button);
                Controls.Add(button);
            }

            _notes.Add((note, buttons));
        }
    }

    /// <summary>Zuhause-Knöpfe: Schalter als Chip (an = Akzent), Szenen/Skripte als normale Knöpfe. Das Fenster bleibt offen.</summary>
    private void BuildHome()
    {
        foreach (SparkButton b in _home)
        {
            Controls.Remove(b);
            b.Dispose();
        }

        _home.Clear();
        _homeActions.Clear();
        int tab = 80;
        foreach (PanelHomeButton item in _model.Home ?? Array.Empty<PanelHomeButton>())
        {
            string label = item.Toggle ? $"{item.Name} · {(item.On is true ? "an" : item.On is false ? "aus" : "?")}" : item.Name;
            var button = new SparkButton(item.Toggle ? ButtonKind.Chip : ButtonKind.Secondary, label)
            {
                FontSize = 9f,
                Enabled = item.Enabled,
                TabIndex = tab++,
            };
            button.Checked = item.Toggle && item.On is true;
            button.AccessibleName = item.Toggle
                ? $"{item.Name}, {(item.On is true ? "an" : item.On is false ? "aus" : "Zustand unbekannt")}, umschalten"
                : item.Name + " auslösen";
            int slot = _homeActions.Count;
            _homeActions.Add(item.Action);
            button.Click += (_, _) =>
            {
                if (slot < _homeActions.Count)
                {
                    _post(_homeActions[slot]);
                }
            };
            _home.Add(button);
            Controls.Add(button);
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

    /// <summary>Kleine Großbuchstaben-Überschrift eines Abschnitts (wie im Panel).</summary>
    private Font SectionFont => F(7.5f, FontStyle.Bold);

    private int Section(ref int y, int pad, int inner, out Rectangle heading)
    {
        int h = Draw.Measure("AG", SectionFont).Height;
        y += S(6);
        heading = new Rectangle(pad + S(2), y, inner - S(2), h);
        y += h + S(6);
        return h;
    }

    protected override void LayoutContent()
    {
        PanelModel m = _model;
        int pad = S(14);
        int width = S(Width96);

        // Breite nach dem Fuß richten, falls Schrift/Text breiter ist.
        int foot = (m.OpenPanel is not null ? _panel.Preferred().Width : 0)
                   + _items.Where(b => b.Kind == ButtonKind.Link).Sum(b => b.Preferred().Width + S(8)) + S(16);
        width = Math.Max(width, foot + (2 * pad));
        int inner = width - (2 * pad);

        int y = BarHeight + pad;

        // Kopf: Gesicht, Gruß, Gerät mit Zustandspunkt; rechts Einstellungen und Schließen
        int face = S(40);
        _face = new Rectangle(pad, y, face, face);
        Size icon = _close.Preferred();
        _close.Bounds = new Rectangle(width - pad + S(4) - icon.Width, y + ((face - icon.Height) / 2), icon.Width, icon.Height);
        _settings.Visible = m.Settings is not null;
        _settings.Bounds = new Rectangle(_close.Left - S(2) - icon.Width, _close.Top, icon.Width, icon.Height);
        int textX = pad + face + S(11);
        int textW = Math.Max(10, (m.Settings is not null ? _settings.Left : _close.Left) - S(6) - textX);
        int titleH = Draw.Measure("Ag", F(11f, FontStyle.Bold)).Height;
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
            int bannerIcon = S(28);
            int textLeft = pad + bannerPad + bannerIcon + S(10);
            int textRight = u.Button is not null ? width - pad - bannerPad - button.Width - S(10) : width - pad - bannerPad;
            int tw = Math.Max(10, textRight - textLeft);
            int th = Draw.Measure("Ag", F(9f, FontStyle.Bold)).Height;
            int dh = Math.Min(Draw.TextHeight(u.Detail, F(8.5f), tw), subH * 3);
            int contentH = Math.Max(Math.Max(bannerIcon, button.Height), th + dh);
            int bannerH = contentH + (2 * bannerPad) + (u.Progress is not null ? S(6) : 0);
            _banner = new Rectangle(pad, y, inner, bannerH);
            int cy = y + bannerPad;
            _bannerIcon = new Rectangle(pad + bannerPad, cy + ((contentH - bannerIcon) / 2), bannerIcon, bannerIcon);
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

        // Fragefeld „Frag Spark …“
        _askHost.Visible = m.Ask is not null;
        if (m.Ask is not null)
        {
            _ask.PlaceholderText = string.IsNullOrEmpty(m.AskHotkey) ? "Frag Spark …" : $"Frag Spark …   ({m.AskHotkey})";
            _ask.Font = F(10f);
            _askMic.Visible = m.AskVoice is not null;
            int h = S(42);
            _askHost.Bounds = new Rectangle(pad, y, inner, h);
            y += h + S(10);
        }

        // Befehle als Kacheln, drei nebeneinander
        var tiles = _items.Where(b => b.Kind == ButtonKind.Tile).ToList();
        if (tiles.Count > 0)
        {
            int gap = S(7);
            int tw = (inner - ((Columns - 1) * gap)) / Columns;
            int th = tiles.Any(t => !string.IsNullOrEmpty(t.Hotkey)) ? S(86) : S(70);
            for (int i = 0; i < tiles.Count; i++)
            {
                int col = i % Columns;
                int row = i / Columns;
                tiles[i].Bounds = new Rectangle(pad + (col * (tw + gap)), y + (row * (th + gap)), tw, th);
            }

            int rows = (tiles.Count + Columns - 1) / Columns;
            y += (rows * th) + ((rows - 1) * gap) + S(6);
        }

        // Als Nächstes (Teil "agenda")
        _agendaRects.Clear();
        _agendaLines.Clear();
        _agendaEmpty = Rectangle.Empty;
        _agendaBox = Rectangle.Empty;
        if (m.Agenda is { } agenda)
        {
            Section(ref y, pad, inner, out _agendaHeading);
            int boxTop = y;
            int cell = S(12);
            int lineH = Draw.Measure("Ag", F(9f)).Height;
            int smallH = Draw.Measure("Ag", F(8f)).Height;
            int whenW = S(52);
            int lineW = inner - (2 * cell) - whenW;
            y += S(8);
            for (int i = 0; i < agenda.Count; i++)
            {
                PanelLine line = agenda[i];
                if (i > 0)
                {
                    _agendaLines.Add(y);
                    y += S(8);
                }

                int dh = line.Detail.Length > 0 ? smallH : 0;
                _agendaRects.Add((new Rectangle(pad + cell, y, whenW, lineH), new Rectangle(pad + cell + whenW, y, lineW, lineH),
                    new Rectangle(pad + cell + whenW, y + lineH, lineW, dh)));
                y += lineH + dh + S(8);
            }

            if (agenda.Count == 0 && !string.IsNullOrEmpty(m.AgendaEmpty))
            {
                int h = Draw.TextHeight(m.AgendaEmpty, F(8.5f), inner - (2 * cell));
                _agendaEmpty = new Rectangle(pad + cell, y, inner - (2 * cell), h);
                y += h + S(8);
            }

            _agendaBox = new Rectangle(pad, boxTop, inner, y - boxTop);
            y += S(6);
        }
        else
        {
            _agendaHeading = Rectangle.Empty;
        }

        // Meldungen mit Knöpfen
        _noteRects.Clear();
        if (_notes.Count > 0)
        {
            Section(ref y, pad, inner, out _notesHeading);
            foreach (var (note, buttons) in _notes)
            {
                int cardPad = S(12);
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
                    if (bx > pad + cardPad && bx + size.Width > pad + cardPad + tw)
                    {
                        bx = pad + cardPad;
                        by += rowH + S(6);
                        rowH = 0;
                    }

                    b.Bounds = new Rectangle(bx, by, size.Width, size.Height);
                    b.Surface = P.Card;
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

        // Zuhause (Teil "home")
        if (m.Home is not null)
        {
            Section(ref y, pad, inner, out _homeHeading);
            int hx = pad;
            int rowH = 0;
            foreach (SparkButton b in _home)
            {
                Size size = b.Preferred();
                size.Width = Math.Min(size.Width, inner);
                if (hx > pad && hx + size.Width > pad + inner)
                {
                    hx = pad;
                    y += rowH + S(6);
                    rowH = 0;
                }

                b.Bounds = new Rectangle(hx, y, size.Width, size.Height);
                hx += size.Width + S(6);
                rowH = Math.Max(rowH, size.Height);
            }

            y += rowH + (rowH > 0 ? S(6) : 0);
            if (!string.IsNullOrEmpty(m.HomeNote))
            {
                int h = Draw.TextHeight(m.HomeNote, F(8.5f), inner);
                _homeNote = new Rectangle(pad, y, inner, h);
                y += h + S(6);
            }
            else
            {
                _homeNote = Rectangle.Empty;
            }

            y += S(4);
        }
        else
        {
            _homeHeading = Rectangle.Empty;
            _homeNote = Rectangle.Empty;
        }

        // Dieser Rechner: Schalter und Zeilen in einem Kasten
        _rowLines.Clear();
        var rows2 = _items.Where(b => b.Kind is ButtonKind.Toggle or ButtonKind.Row).ToList();
        if (rows2.Count > 0)
        {
            Section(ref y, pad, inner, out _rowsHeading);
            int boxTop = y;
            y += S(3);
            for (int i = 0; i < rows2.Count; i++)
            {
                if (i > 0)
                {
                    _rowLines.Add(y);
                    y += S(2);
                }

                int h = rows2[i].Preferred().Height;
                rows2[i].Bounds = new Rectangle(pad + S(3), y, inner - S(6), h);
                y += h + S(1);
            }

            y += S(2);
            _rowsBox = new Rectangle(pad, boxTop, inner, y - boxTop);
            y += S(8);
        }
        else
        {
            _rowsHeading = Rectangle.Empty;
            _rowsBox = Rectangle.Empty;
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

        // Fuß auf weicher Fläche: links „Panel öffnen“, rechts Notaus
        _footLine = y;
        y += S(8);
        _panel.Visible = m.OpenPanel is not null;
        Size panel = _panel.Preferred();
        if (m.OpenPanel is not null)
        {
            _panel.Bounds = new Rectangle(pad - S(6), y, panel.Width, panel.Height);
            _panel.Surface = P.Soft;
        }

        int fx = width - pad + S(6);
        foreach (SparkButton link in _items.Where(b => b.Kind == ButtonKind.Link).Reverse())
        {
            Size size = link.Preferred();
            fx -= size.Width;
            link.Bounds = new Rectangle(fx, y, size.Width, size.Height);
            link.Surface = P.Soft;
            fx -= S(8);
        }

        y += panel.Height + S(8);
        ClientSize = new Size(width, y);
    }

    protected override void PaintContent(Graphics g)
    {
        Draw.HighQuality(g);
        Palette p = P;
        PanelModel m = _model;

        // Fuß: weiche Fläche mit Linie darüber
        using (var foot = new SolidBrush(p.Soft))
        {
            g.FillRectangle(foot, 0, _footLine, ClientSize.Width, ClientSize.Height - _footLine);
        }

        using (var line = new Pen(p.Line))
        {
            g.DrawLine(line, 0, _footLine, ClientSize.Width, _footLine);
        }

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
        Draw.Text(g, m.Title, F(11f, FontStyle.Bold), _title, p.Fg);
        if (!_subtitle.IsEmpty)
        {
            // Zustandspunkt, dann „Gerät · Zustand“
            int d = S(7);
            using (var dot = new SolidBrush(PanelModel.StatusColor(m.Status, p)))
            {
                g.FillEllipse(dot, _subtitle.X, _subtitle.Y + ((_subtitle.Height - d) / 2f), d, d);
            }

            string sub = m.Subtitle.Length > 0 ? m.Subtitle + " · " + m.StatusText : m.StatusText;
            Draw.Text(g, sub, F(8.5f), Rectangle.FromLTRB(_subtitle.X + d + S(6), _subtitle.Y, _subtitle.Right, _subtitle.Bottom),
                m.Status == StatusKind.Bad ? p.Bad : p.Muted);
        }

        if (!_notice.IsEmpty && m.Notice is { } notice)
        {
            Draw.Text(g, notice, F(9f), _notice, p.Bad, Draw.Wrap);
        }

        if (!_banner.IsEmpty && m.Update is { } u)
        {
            Draw.FillRound(g, p.BannerBack, _banner, S(12));
            Draw.StrokeRound(g, u.Error ? p.Bad : p.BannerLine, _banner, S(12));
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

        if (!_agendaHeading.IsEmpty && m.Agenda is { } agenda)
        {
            PaintHeading(g, "Als Nächstes", _agendaHeading, 0);
            PaintBox(g, _agendaBox, _agendaLines);
            Font when = F(9f, FontStyle.Bold);
            for (int i = 0; i < _agendaRects.Count && i < agenda.Count; i++)
            {
                var (whenRect, text, detail) = _agendaRects[i];
                Draw.Text(g, agenda[i].When, when, whenRect, p.Accent);
                Draw.Text(g, agenda[i].Text, F(9f), text, p.Fg);
                if (detail.Height > 0)
                {
                    Draw.Text(g, agenda[i].Detail, F(8f), detail, p.Muted);
                }
            }

            if (!_agendaEmpty.IsEmpty && m.AgendaEmpty is { } empty)
            {
                Draw.Text(g, empty, F(8.5f), _agendaEmpty, p.Muted, Draw.Wrap);
            }
        }

        if (!_notesHeading.IsEmpty)
        {
            PaintHeading(g, "Meldungen", _notesHeading, _notes.Count);
            for (int i = 0; i < _noteRects.Count && i < _notes.Count; i++)
            {
                var (card, title, body) = _noteRects[i];
                PanelNote note = _notes[i].Note;
                Draw.FillRound(g, p.Card, card, S(12));
                Draw.StrokeRound(g, p.Line, card, S(12));
                Draw.Text(g, note.Title, F(9f, FontStyle.Bold), title, p.Fg);
                if (body.Height > 0)
                {
                    Draw.Text(g, note.Body, F(8.5f), body, p.Muted, Draw.Wrap | TextFormatFlags.EndEllipsis);
                }
            }
        }

        if (!_homeHeading.IsEmpty)
        {
            PaintHeading(g, "Zuhause", _homeHeading, 0);
            if (!_homeNote.IsEmpty && m.HomeNote is { } homeNote)
            {
                Draw.Text(g, homeNote, F(8.5f), _homeNote, p.Muted, Draw.Wrap);
            }
        }

        if (!_rowsHeading.IsEmpty)
        {
            PaintHeading(g, "Dieser Rechner", _rowsHeading, 0);
            PaintBox(g, _rowsBox, _rowLines);
        }

        if (!_hint.IsEmpty && m.Hint is { } hint)
        {
            Draw.Text(g, hint, F(8.5f), _hint, p.Muted, Draw.Wrap);
        }
    }

    /// <summary>Abschnittsüberschrift in kleinen Großbuchstaben, dahinter optional die Anzahl als Abzeichen.</summary>
    private void PaintHeading(Graphics g, string text, Rectangle r, int count)
    {
        Palette p = P;
        string upper = text.ToUpperInvariant();
        Draw.Text(g, upper, SectionFont, r, p.Muted);
        if (count > 0)
        {
            Font badge = F(7.5f, FontStyle.Bold);
            string n = count.ToString(System.Globalization.CultureInfo.InvariantCulture);
            Size t = Draw.Measure(n, badge);
            int x = r.X + Draw.Measure(upper, SectionFont).Width + S(4);
            var b = new Rectangle(x, r.Y + ((r.Height - t.Height) / 2) - S(1), Math.Max(t.Width + S(10), t.Height + S(2)), t.Height + S(2));
            Draw.FillRound(g, p.HighContrast ? p.Card : Palette.Mix(p.Card, p.Warn, 0.18f), b, b.Height / 2f);
            Draw.Text(g, n, badge, b, p.HighContrast ? p.Fg : p.Warn, Draw.Line | TextFormatFlags.HorizontalCenter);
        }
    }

    /// <summary>Gruppenkasten mit Rand und Trennlinien zwischen den Zeilen.</summary>
    private void PaintBox(Graphics g, Rectangle box, List<int> lines)
    {
        if (box.IsEmpty)
        {
            return;
        }

        Palette p = P;
        Draw.StrokeRound(g, p.Line, box, S(12));
        using var pen = new Pen(p.Line);
        foreach (int y in lines)
        {
            g.DrawLine(pen, box.X + S(12), y, box.Right - S(12), y);
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

    // der Hinweis unten mit einem Weg („im Panel unter Ich → Begleiter“) ist ein Sprung-Link (Wege.cs)
    private bool OverWayHint(Point at) => !_hint.IsEmpty && _hint.Contains(at) && Wege.Find(_model.Hint) is not null;

    protected override void OnMouseMove(MouseEventArgs e)
    {
        base.OnMouseMove(e);
        Cursor = OverWayHint(e.Location) ? Cursors.Hand : Cursors.Default;
    }

    protected override void OnMouseUp(MouseEventArgs e)
    {
        base.OnMouseUp(e);
        if (e.Button == MouseButtons.Left && OverWayHint(e.Location))
        {
            Wege.OpenFrom(_model.Hint);
        }
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
