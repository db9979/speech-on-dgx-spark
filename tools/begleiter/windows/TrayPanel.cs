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

/// <summary>
/// Reiter unter den Kacheln (Dominik 2026-10-21 „Begleiter-Fenster ordnen“ 1a): nur der Reiter rollt, Kopf, Fragefeld,
/// Kacheln und Fuß mit Notaus bleiben immer sichtbar.
/// </summary>
internal enum PanelTab
{
    /// <summary>Als Nächstes, Post, Listen, Offen.</summary>
    Heute,

    /// <summary>Meldungen mit ihren Knöpfen, die neueste oben.</summary>
    Meldungen,

    /// <summary>Zuhause und Dieser Rechner.</summary>
    Rechner,
}

/// <summary>Ein eingeschalteter Teil im Tray-Fenster: Kachel, Schalter, Zeile oder Link im Fuß.</summary>
/// <param name="On">Nur <see cref="PanelItemKind.Toggle"/>: der Schalter steht auf an.</param>
/// <param name="Verb">Nur <see cref="PanelItemKind.Row"/>: die Tätigkeit rechts, z. B. „Öffnen“.</param>
internal sealed record PanelItem(string Text, Glyph Glyph, string? Hotkey, Action Action, bool Danger = false, bool Enabled = true,
    PanelItemKind Kind = PanelItemKind.Tile, string? Detail = null, bool On = false, string? Verb = null);

/// <summary>Teil "actions": eine Meldung im Tray-Fenster mit ihren Knöpfen (nur die angebotenen sind gesetzt).</summary>
/// <param name="Done">„OK“: die Meldung ist gesehen und verschwindet; das Fenster bleibt offen (Dominik 2026-10-16).</param>
/// <summary>
/// Eine Meldung im Tray-Fenster; <see cref="Extra"/> = Knöpfe ihrer Art vom Panel (Für dich: Erledigt, Erinnern),
/// <see cref="OpenLabel"/> = „Ansehen“, wenn die Meldung einen Weg ins Panel hat.
/// </summary>
internal sealed record PanelNote(int N, string Title, string Body, Action? Reply, Action? Later, Action? Open, Action? Remind = null, Action? Done = null,
    IReadOnlyList<(string Label, Action Action)>? Extra = null, string OpenLabel = "Panel öffnen");

/// <summary>Teil "agenda": eine Zeile unter „Als Nächstes“ (Zeit, Text, Ort/Hinweis).</summary>
/// <summary>Eine Zeile unter „Als Nächstes“; Who als Namen-Chip (geteilter Kalender), Open beim Klick (Termin im Panel).</summary>
internal sealed record PanelLine(string When, string Text, string Detail, string Who = "", Action? Open = null);

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

    /// <summary>Teil "post": Karten unter „Post“ (zuerst die Zahlen, dann dringende Für-dich-Karten); <c>null</c> = Abschnitt fehlt.</summary>
    public IReadOnlyList<PanelNote>? Post { get; init; }

    /// <summary>Teil "lists": eine Karte je Liste unter „Listen“; <c>null</c> = Abschnitt fehlt.</summary>
    public IReadOnlyList<PanelNote>? Lists { get; init; }

    /// <summary>Teil "offen" (Paket B): die ersten drei offenen Vorgänge mit ihren festen Knöpfen; <c>null</c> = Abschnitt fehlt.</summary>
    public IReadOnlyList<PanelNote>? Offen { get; init; }

    /// <summary>Wie viele Vorgänge offen sind (Zahl neben „Offen“).</summary>
    public int OffenCount { get; init; }

    /// <summary>Meldungen mit Knöpfen (Teil "actions").</summary>
    public IReadOnlyList<PanelNote> Notes { get; init; } = Array.Empty<PanelNote>();

    /// <summary>Teil "actions" ist an: der Reiter „Meldungen“ steht auch ohne Meldung da („Keine Meldungen.“).</summary>
    public bool NotesOn { get; init; }

    /// <summary>Reiter beim Öffnen: „Meldungen“ bei einer neuen Meldung, sonst der zuletzt gewählte (5a, 6a).</summary>
    public PanelTab StartTab { get; init; }

    /// <summary>Ein Reiter wurde gewählt (wird je Gerät gemerkt, 6a).</summary>
    public Action<PanelTab>? TabChosen { get; init; }

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
/// und Schließen; darunter der Update-Hinweis, das Fragefeld „Frag Spark …“ und die Befehle als kleine Kacheln.
/// Darunter drei Reiter (Dominik 2026-10-21 „Begleiter-Fenster ordnen“): „Heute“ (Als Nächstes, Post, Listen, Offen),
/// „Meldungen“ und „Rechner“ (Zuhause, Dieser Rechner); nur der Reiter rollt, das Fenster ist höchstens so hoch
/// wie der freie Bildschirm. Unten „Panel öffnen“ und Notaus. Schließt bei Fokusverlust und mit Esc.
/// </summary>
internal sealed class TrayPanel : ThemedForm
{
    private const float Width96 = 360;
    private const int Columns = 4; // kleine Kacheln, vier nebeneinander (3a)
    private const int FirstShown = 3; // je Abschnitt die ersten drei, darunter „Alle n zeigen“ (4a)
    private const int MaxQuestion = 2000;

    private readonly Action<Action> _post;
    private readonly List<SparkButton> _items = new();
    private readonly List<Action> _actions = new();
    private readonly CardGroup _notes = new();
    private readonly CardGroup _postCards = new();
    private readonly CardGroup _offenCards = new();
    private readonly List<SparkButton> _lists = new();
    private readonly List<SparkButton> _home = new();
    private readonly List<Action> _homeActions = new();
    private Rectangle _agendaHeading;
    private Rectangle _agendaBox;
    private readonly List<(Rectangle When, Rectangle Text, Rectangle Detail)> _agendaRects = new();
    private readonly List<Rectangle> _agendaRows = new();
    private readonly List<int> _agendaLines = new();
    private Rectangle _agendaEmpty;
    private Rectangle _listHeading;
    private Rectangle _listBox;
    private readonly List<int> _listLines = new();
    private Rectangle _notesEmpty;
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

    // Reiter und Rollfläche (1a, 2a): die Teile des Reiters liegen auf _host und werden an seinem Rand abgeschnitten
    private readonly ScrollHost _host = new();
    private readonly SparkButton[] _tabs = { new(ButtonKind.Chip, "Heute"), new(ButtonKind.Chip, "Meldungen"), new(ButtonKind.Chip, "Rechner") };
    private readonly SparkButton _agendaMore = new(ButtonKind.Link) { FontSize = 8.5f };
    private readonly SparkButton _postMore = new(ButtonKind.Link) { FontSize = 8.5f };
    private readonly HashSet<Control> _cut = new();
    private Rectangle _tabBar;
    private PanelTab _tab;
    private int _scroll;
    private int _contentH;
    private bool _agendaAll;
    private bool _postAll;
    private int _newestNote;
    private int? _dragY;
    private int _dragScroll;

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
        _tab = model.StartTab;
        _newestNote = Newest(model);
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
        for (int i = 0; i < _tabs.Length; i++)
        {
            var tab = (PanelTab)i;
            _tabs[i].FontSize = 9f;
            _tabs[i].TabIndex = 30 + i;
            _tabs[i].Click += (_, _) => ChooseTab(tab);
            Controls.Add(_tabs[i]);
        }

        // „Alle n zeigen“ klappt auf und zu; das Fenster bleibt offen
        _agendaMore.Click += (_, _) => ShowAll(ref _agendaAll);
        _postMore.Click += (_, _) => ShowAll(ref _postAll);
        _agendaMore.TabIndex = 39;
        _postMore.TabIndex = 44;
        _host.TabIndex = 35;
        _host.Wheel = delta => ScrollTo(_scroll - (delta * S(48) / 120));
        _host.PaintTab = PaintTab;
        _host.MouseMove += OnHostMouseMove;
        _host.MouseDown += OnHostMouseDown;
        _host.MouseUp += OnHostMouseUp;
        Controls.Add(_update);
        Controls.Add(_settings);
        Controls.Add(_close);
        Controls.Add(_panel);
        Controls.Add(_askHost);
        Controls.Add(_host);
        InHost(_agendaMore);
        InHost(_postMore);
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

    private static int Newest(PanelModel model) => model.Notes.Count > 0 ? model.Notes.Max(n => n.N) : 0;

    /// <summary>Neuer Inhalt, während das Fenster offen ist (z. B. Fortschritt beim Laden).</summary>
    public void SetModel(PanelModel model)
    {
        int focused = _items.FindIndex(b => b.Focused);
        bool sameRows = model.Items.Count == _model.Items.Count &&
            model.Items.Zip(_model.Items).All(pair => pair.First with { Action = pair.Second.Action } == pair.Second);
        _model = model;
        int newest = Newest(model);
        if (newest > _newestNote && _tab != PanelTab.Meldungen)
        {
            // eine neue Meldung kommt, während das Fenster offen ist: gleich auf „Meldungen“ (5a)
            _tab = PanelTab.Meldungen;
            _scroll = 0;
        }

        _newestNote = Math.Max(_newestNote, newest);
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

    /// <summary>Ein Teil des Reiters: liegt auf der Rollfläche, das Mausrad rollt, der Fokus holt ihn ins Bild.</summary>
    private void InHost(Control c)
    {
        _host.Controls.Add(c);
        c.Enter += (_, _) => ShowInView(c);
    }

    private static void Drop(Control c)
    {
        c.Parent?.Controls.Remove(c);
        c.Dispose();
    }

    private void BuildItems()
    {
        foreach (SparkButton old in _items)
        {
            Drop(old);
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
                Compact = kind == ButtonKind.Tile,
                FontSize = kind == ButtonKind.Tile ? 8f : 9.5f,
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
                if (kind == ButtonKind.Tile)
                {
                    _tips.SetToolTip(button, $"{item.Text} ({hotkey})"); // kleine Kachel: das Kürzel als Tooltip (3a)
                }
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
            if (kind is ButtonKind.Toggle or ButtonKind.Row)
            {
                InHost(button); // Reiter „Rechner“
            }
            else
            {
                Controls.Add(button);
            }
        }

        _update.TabIndex = 100;
        _panel.TabIndex = 103;
        _settings.TabIndex = 110;
        _close.TabIndex = 111;
    }

    /// <summary>Farbe des Kachel-Symbols (Klar 2): Linien-Icon im einen Akzent, nur Mitschreiben in Rot.</summary>
    private static Color? TintFor(Glyph glyph)
    {
        Palette p = Theme.Current;
        return glyph switch
        {
            Glyph.Record => p.Bad,
            _ => p.Accent,
        };
    }

    private void BuildNotes()
    {
        BuildCards(_postCards, _model.Post ?? Array.Empty<PanelNote>(), 40);
        BuildLists();
        BuildCards(_offenCards, _model.Offen ?? Array.Empty<PanelNote>(), 70);
        BuildCards(_notes, _model.Notes, 50);
    }

    /// <summary>Karten mit Knöpfen (Meldungen, Post): alte Knöpfe weg, neue nach der Reihe.</summary>
    private void BuildCards(CardGroup group, IReadOnlyList<PanelNote> list, int tab)
    {
        foreach (var (_, buttons) in group.Cards)
        {
            foreach (SparkButton b in buttons)
            {
                Drop(b);
            }
        }

        group.Cards.Clear();
        foreach (PanelNote note in list)
        {
            var buttons = new List<SparkButton>();
            var row = new List<(string, Action?)> { ("OK", note.Done) };
            row.AddRange((note.Extra ?? Array.Empty<(string, Action)>()).Select(e => (e.Label, (Action?)e.Action)));
            row.AddRange(new (string, Action?)[] { ("Antworten", note.Reply), ("Später", note.Later), ("In 20 Min erinnern", note.Remind), (note.OpenLabel, note.Open) });
            foreach (var (label, action) in row)
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
                InHost(button);
            }

            group.Cards.Add((note, buttons));
        }
    }

    /// <summary>Listen: je Liste eine Zeile (Name, Zahl, letzter Eintrag), ein Klick öffnet die Seite Listen (4a).</summary>
    private void BuildLists()
    {
        foreach (SparkButton b in _lists)
        {
            Drop(b);
        }

        _lists.Clear();
        int tab = 45;
        foreach (PanelNote note in _model.Lists ?? Array.Empty<PanelNote>())
        {
            string text = note.Body.Length > 0 ? note.Title + " · " + note.Body : note.Title;
            var button = new SparkButton(ButtonKind.Row, text)
            {
                FontSize = 9f,
                Verb = note.Open is not null ? note.OpenLabel : null,
                Enabled = note.Open is not null,
                TabIndex = tab++,
            };
            button.AccessibleName = text + (note.Open is not null ? ", " + note.OpenLabel : "");
            _tips.SetToolTip(button, text);
            Action? open = note.Open;
            button.Click += (_, _) => Run(open);
            _lists.Add(button);
            InHost(button);
        }
    }

    /// <summary>Zuhause-Knöpfe: Schalter als Chip (an = Akzent), Szenen/Skripte als normale Knöpfe. Das Fenster bleibt offen.</summary>
    private void BuildHome()
    {
        foreach (SparkButton b in _home)
        {
            Drop(b);
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
            InHost(button);
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

    /// <summary>Hat der Reiter etwas zu zeigen? Reiter ohne Inhalt fehlen in der Leiste.</summary>
    private bool Has(PanelTab tab) => tab switch
    {
        PanelTab.Heute => _model.Agenda is not null || _postCards.Cards.Count > 0 || _model.Lists is not null || _model.Offen is not null,
        PanelTab.Meldungen => _model.NotesOn || _notes.Cards.Count > 0,
        _ => _model.Home is not null || _items.Any(b => b.Kind is ButtonKind.Toggle or ButtonKind.Row),
    };

    private void ChooseTab(PanelTab tab)
    {
        if (tab == _tab)
        {
            return;
        }

        _tab = tab;
        _scroll = 0;
        if (_model.TabChosen is { } chosen)
        {
            _post(() => chosen(tab)); // je Gerät gemerkt (6a)
        }

        LayoutContent();
        Invalidate(true);
    }

    private void ShowAll(ref bool all)
    {
        all = !all;
        LayoutContent();
        PlaceAtTray();
        Invalidate(true);
    }

    /// <summary>Den Reiter rollen (begrenzt auf seinen Inhalt).</summary>
    private void ScrollTo(int value)
    {
        int most = Math.Max(0, _contentH - _host.Height);
        value = Math.Clamp(value, 0, most);
        if (value == _scroll)
        {
            return;
        }

        _scroll = value;
        LayoutContent();
        _host.Invalidate();
    }

    /// <summary>Mit der Tastatur erreicht: ins Bild rollen.</summary>
    private void ShowInView(Control c)
    {
        if (c.Top < 0)
        {
            ScrollTo(_scroll + c.Top - S(8));
        }
        else if (c.Bottom > _host.Height)
        {
            ScrollTo(_scroll + c.Bottom - _host.Height + S(8));
        }
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

        int y = pad;

        // Kopf: Gesicht, Gruß, Gerät mit Zustandspunkt; rechts Einstellungen und Schließen
        int face = S(40);
        _face = new Rectangle(pad, y, face, face);
        Size icon = _close.Preferred();
        _close.Bounds = new Rectangle(width - pad + S(4) - icon.Width, y + ((face - icon.Height) / 2), icon.Width, icon.Height);
        _settings.Visible = m.Settings is not null;
        _settings.Bounds = new Rectangle(_close.Left - S(2) - icon.Width, _close.Top, icon.Width, icon.Height);
        int textX = pad + Face.Lead(face, S(11));
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

        // Befehle als kleine Kacheln, vier nebeneinander (3a)
        var tiles = _items.Where(b => b.Kind == ButtonKind.Tile).ToList();
        if (tiles.Count > 0)
        {
            int gap = S(6);
            int tw = (inner - ((Columns - 1) * gap)) / Columns;
            int th = S(66);
            for (int i = 0; i < tiles.Count; i++)
            {
                int col = i % Columns;
                int row = i / Columns;
                tiles[i].Bounds = new Rectangle(pad + (col * (tw + gap)), y + (row * (th + gap)), tw, th);
            }

            int rows = (tiles.Count + Columns - 1) / Columns;
            y += (rows * th) + ((rows - 1) * gap) + S(8);
        }

        // Reiterleiste: nur Reiter mit Inhalt, keine Leiste bei nur einem
        var open = Enum.GetValues<PanelTab>().Where(Has).ToList();
        if (open.Count > 0 && !open.Contains(_tab))
        {
            _tab = open[0];
            _scroll = 0;
        }

        _tabBar = Rectangle.Empty;
        int chipH = S(28);
        int barPad = S(3);
        int cw = open.Count > 1 ? (inner - (2 * barPad)) / open.Count : 0;
        int cx = pad + barPad;
        for (int i = 0; i < _tabs.Length; i++)
        {
            var tab = (PanelTab)i;
            bool shown = open.Count > 1 && open.Contains(tab);
            _tabs[i].Visible = shown;
            if (!shown)
            {
                continue;
            }

            int count = tab == PanelTab.Meldungen ? _notes.Cards.Count : 0;
            _tabs[i].Text = count > 0 ? $"{tab} {count}" : tab.ToString();
            _tabs[i].Checked = tab == _tab;
            _tabs[i].Surface = P.Soft;
            _tabs[i].Bounds = new Rectangle(cx, y + barPad, cw, chipH);
            cx += cw;
        }

        if (open.Count > 1)
        {
            _tabBar = new Rectangle(pad, y, inner, chipH + (2 * barPad));
            y += _tabBar.Height + S(4);
        }

        // unten fest: Hinweis und Fuß
        int hintH = string.IsNullOrEmpty(m.Hint) ? 0 : Draw.TextHeight(m.Hint, F(8.5f), inner);
        Size panel = _panel.Preferred();
        int below = (hintH > 0 ? hintH + S(10) : 0) + S(8) + panel.Height + S(8);

        // der Reiter: höchstens so hoch wie der freie Bildschirm, nur er rollt (2a); alle Reiter gleich hoch, nichts springt
        _cut.Clear();
        _host.Visible = open.Count > 0;
        if (open.Count > 0)
        {
            int most = 0;
            foreach (PanelTab tab in open)
            {
                int h = LayoutTab(tab, 0, pad, inner);
                most = Math.Max(most, h);
                if (tab == _tab)
                {
                    _contentH = h;
                }
            }

            Rectangle work = Screen.FromPoint(Cursor.Position).WorkingArea;
            int room = work.Height - (2 * S(10)) - y - S(6) - below;
            int viewH = Math.Min(most, Math.Max(S(160), room));
            _scroll = Math.Clamp(_scroll, 0, Math.Max(0, _contentH - viewH));
            LayoutTab(_tab, -_scroll, pad, inner);
            _host.Bounds = new Rectangle(0, y, width, viewH);
            _host.Thumb = ThumbFor(width, viewH);
            y += viewH + S(6);
        }

        foreach (Control c in _host.Controls)
        {
            c.Visible = TabOf(c) == _tab && !_cut.Contains(c);
        }

        if (hintH > 0)
        {
            _hint = new Rectangle(pad, y, inner, hintH);
            y += hintH + S(10);
        }
        else
        {
            _hint = Rectangle.Empty;
        }

        // Fuß auf weicher Fläche: links „Panel öffnen“, rechts Notaus
        _footLine = y;
        y += S(8);
        _panel.Visible = m.OpenPanel is not null;
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

    /// <summary>Zu welchem Reiter ein Teil auf der Rollfläche gehört.</summary>
    private PanelTab TabOf(Control c)
    {
        if (c == _agendaMore || c == _postMore || (c is SparkButton b && (_lists.Contains(b) || _postCards.Cards.Any(card => card.Buttons.Contains(b))
            || _offenCards.Cards.Any(card => card.Buttons.Contains(b)))))
        {
            return PanelTab.Heute;
        }

        return c is SparkButton n && _notes.Cards.Any(card => card.Buttons.Contains(n)) ? PanelTab.Meldungen : PanelTab.Rechner;
    }

    /// <summary>Schmaler Daumen rechts, wenn der Reiter mehr hat als Platz (eine Leiste zum Rollen).</summary>
    private Rectangle ThumbFor(int width, int viewH)
    {
        if (_contentH <= viewH || viewH <= 0)
        {
            return Rectangle.Empty;
        }

        int track = viewH - S(8);
        int h = Math.Max(S(28), track * viewH / _contentH);
        int y = S(4) + ((track - h) * _scroll / Math.Max(1, _contentH - viewH));
        return new Rectangle(width - S(9), y, S(5), h);
    }

    /// <summary>Inhalt eines Reiters ab <paramref name="y0"/> (Koordinaten der Rollfläche); gibt seine Höhe zurück.</summary>
    private int LayoutTab(PanelTab tab, int y0, int pad, int inner)
    {
        int y = y0 + S(2);
        switch (tab)
        {
            case PanelTab.Heute:
                LayoutAgenda(ref y, pad, inner);
                LayoutCards(_postCards, ref y, pad, inner, _postAll ? int.MaxValue : FirstShown);
                More(_postMore, _postCards.Cards.Count, _postAll, ref y, pad);
                LayoutLists(ref y, pad, inner);
                LayoutCards(_offenCards, ref y, pad, inner, int.MaxValue);
                break;
            case PanelTab.Meldungen:
                // die Leiste nennt den Reiter schon; ohne Leiste steht die Überschrift da
                LayoutCards(_notes, ref y, pad, inner, int.MaxValue, heading: _tabBar.IsEmpty);
                _notesEmpty = Rectangle.Empty;
                if (_notes.Cards.Count == 0)
                {
                    int h = Draw.TextHeight("Keine Meldungen.", F(8.5f), inner);
                    _notesEmpty = new Rectangle(pad + S(2), y + S(8), inner - S(2), h);
                    y += h + S(16);
                }

                break;
            default:
                LayoutHome(ref y, pad, inner);
                LayoutRows(ref y, pad, inner);
                break;
        }

        return y - y0 + S(2);
    }

    /// <summary>„Alle n zeigen“ unter einem gekürzten Abschnitt (4a); bei höchstens drei fehlt der Link.</summary>
    private void More(SparkButton more, int count, bool all, ref int y, int pad)
    {
        if (count <= FirstShown)
        {
            _cut.Add(more);
            return;
        }

        more.Text = all ? "Weniger zeigen" : $"Alle {count} zeigen";
        Size size = more.Preferred();
        more.Bounds = new Rectangle(pad - S(6), y - S(6), size.Width, size.Height);
        y += size.Height - S(2);
    }

    // Als Nächstes (Teil "agenda"): die ersten drei, „Alle n zeigen“ klappt den Rest auf
    private void LayoutAgenda(ref int y, int pad, int inner)
    {
        PanelModel m = _model;
        _agendaRects.Clear();
        _agendaRows.Clear();
        _agendaLines.Clear();
        _agendaEmpty = Rectangle.Empty;
        _agendaBox = Rectangle.Empty;
        _agendaHeading = Rectangle.Empty;
        if (m.Agenda is not { } agenda)
        {
            _cut.Add(_agendaMore);
            return;
        }

        Section(ref y, pad, inner, out _agendaHeading);
        int boxTop = y;
        int cell = S(12);
        int lineH = Draw.Measure("Ag", F(9f)).Height;
        int smallH = Draw.Measure("Ag", F(8f)).Height;
        int whenW = S(52);
        int lineW = inner - (2 * cell) - whenW;
        int count = _agendaAll ? agenda.Count : Math.Min(agenda.Count, FirstShown);
        y += S(8);
        for (int i = 0; i < count; i++)
        {
            PanelLine line = agenda[i];
            if (i > 0)
            {
                _agendaLines.Add(y);
                y += S(8);
            }

            int dh = line.Detail.Length > 0 || line.Who.Length > 0 ? smallH + S(2) : 0;
            _agendaRects.Add((new Rectangle(pad + cell, y, whenW, lineH), new Rectangle(pad + cell + whenW, y, lineW, lineH),
                new Rectangle(pad + cell + whenW, y + lineH, lineW, dh)));
            _agendaRows.Add(new Rectangle(pad, y - S(4), inner, lineH + dh + S(8)));
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
        More(_agendaMore, agenda.Count, _agendaAll, ref y, pad);
    }

    // Listen (Teil "lists"): eine Zeile je Liste in einem Kasten
    private void LayoutLists(ref int y, int pad, int inner)
    {
        _listLines.Clear();
        _listHeading = Rectangle.Empty;
        _listBox = Rectangle.Empty;
        if (_model.Lists is null)
        {
            return;
        }

        Section(ref y, pad, inner, out _listHeading);
        int boxTop = y;
        y += S(3);
        for (int i = 0; i < _lists.Count; i++)
        {
            if (i > 0)
            {
                _listLines.Add(y);
                y += S(2);
            }

            int h = S(36);
            _lists[i].Bounds = new Rectangle(pad + S(3), y, inner - S(6), h);
            y += h + S(1);
        }

        y += S(2);
        _listBox = new Rectangle(pad, boxTop, inner, y - boxTop);
        y += S(8);
    }

    // Zuhause (Teil "home")
    private void LayoutHome(ref int y, int pad, int inner)
    {
        PanelModel m = _model;
        _homeHeading = Rectangle.Empty;
        _homeNote = Rectangle.Empty;
        if (m.Home is null)
        {
            return;
        }

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

        y += S(4);
    }

    // Dieser Rechner: Schalter und Zeilen in einem Kasten
    private void LayoutRows(ref int y, int pad, int inner)
    {
        _rowLines.Clear();
        _rowsHeading = Rectangle.Empty;
        _rowsBox = Rectangle.Empty;
        var rows = _items.Where(b => b.Kind is ButtonKind.Toggle or ButtonKind.Row).ToList();
        if (rows.Count == 0)
        {
            return;
        }

        Section(ref y, pad, inner, out _rowsHeading);
        int boxTop = y;
        y += S(3);
        for (int i = 0; i < rows.Count; i++)
        {
            if (i > 0)
            {
                _rowLines.Add(y);
                y += S(2);
            }

            int h = rows[i].Preferred().Height;
            rows[i].Bounds = new Rectangle(pad + S(3), y, inner - S(6), h);
            y += h + S(1);
        }

        y += S(2);
        _rowsBox = new Rectangle(pad, boxTop, inner, y - boxTop);
        y += S(8);
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

        Face.DrawHeader(g, _face, p);
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
            Draw.FillRound(g, p.BannerBack, _banner, S(Draw.RBox));
            Draw.StrokeRound(g, u.Error ? p.Bad : p.BannerLine, _banner, S(Draw.RBox));
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
                    using var brush = new SolidBrush(p.Accent);
                    using System.Drawing.Drawing2D.GraphicsPath path = Draw.Round(bar, bar.Height / 2f);
                    g.FillPath(brush, path);
                }
            }
        }

        if (!_tabBar.IsEmpty)
        {
            Draw.FillRound(g, p.Soft, _tabBar, S(10));
        }

        if (!_hint.IsEmpty && m.Hint is { } hint)
        {
            Draw.Text(g, hint, F(8.5f), _hint, p.Muted, Draw.Wrap);
        }
    }

    /// <summary>Der offene Reiter auf der Rollfläche (Koordinaten der Rollfläche, schon um das Rollen verschoben).</summary>
    private void PaintTab(Graphics g)
    {
        Draw.HighQuality(g);
        Palette p = P;
        PanelModel m = _model;
        switch (_tab)
        {
            case PanelTab.Heute:
                PaintAgenda(g);
                PaintCards(g, _postCards, "Post", 0);
                if (!_listHeading.IsEmpty)
                {
                    PaintHeading(g, "Listen", _listHeading, 0);
                    PaintBox(g, _listBox, _listLines);
                }

                PaintCards(g, _offenCards, "Offen", _model.OffenCount);
                break;
            case PanelTab.Meldungen:
                PaintCards(g, _notes, "Meldungen", _notes.Cards.Count);
                if (!_notesEmpty.IsEmpty)
                {
                    Draw.Text(g, "Keine Meldungen.", F(8.5f), _notesEmpty, p.Muted, Draw.Wrap);
                }

                break;
            default:
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

                break;
        }

        if (!_host.Thumb.IsEmpty)
        {
            using var thumb = new SolidBrush(_dragY is null ? p.Line : p.Muted);
            using System.Drawing.Drawing2D.GraphicsPath path = Draw.Round(_host.Thumb, _host.Thumb.Width / 2f);
            g.FillPath(thumb, path);
        }
    }

    private void PaintAgenda(Graphics g)
    {
        Palette p = P;
        PanelModel m = _model;
        if (_agendaHeading.IsEmpty || m.Agenda is not { } agenda)
        {
            return;
        }

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
                Rectangle rest = detail;
                if (agenda[i].Who.Length > 0)
                {
                    // Namen-Chip: wessen geteilter Kalender (Begleiter nachziehen 7a)
                    Font chip = F(7.5f, FontStyle.Bold);
                    int cw = Math.Min(detail.Width / 2, Draw.Measure(agenda[i].Who, chip).Width + S(10));
                    var box = new Rectangle(detail.X, detail.Y + S(1), cw, detail.Height - S(2));
                    Draw.FillRound(g, p.BannerBack, box, S(6));
                    Draw.Text(g, agenda[i].Who, chip, Rectangle.Inflate(box, -S(5), 0), p.Accent);
                    rest = new Rectangle(box.Right + S(6), detail.Y, Math.Max(0, detail.Right - box.Right - S(6)), detail.Height);
                }

                Draw.Text(g, agenda[i].Detail, F(8f), rest, p.Muted);
            }
        }

        if (!_agendaEmpty.IsEmpty && m.AgendaEmpty is { } empty)
        {
            Draw.Text(g, empty, F(8.5f), _agendaEmpty, p.Muted, Draw.Wrap);
        }
    }

    /// <summary>Überschrift und Karten einer Gruppe; leer = kein Abschnitt. Mehr als <paramref name="limit"/> Karten bleiben zu.</summary>
    private void LayoutCards(CardGroup group, ref int y, int pad, int inner, int limit, bool heading = true)
    {
        group.Rects.Clear();
        group.Heading = Rectangle.Empty;
        if (group.Cards.Count == 0)
        {
            return;
        }

        if (heading)
        {
            Section(ref y, pad, inner, out group.Heading);
        }
        else
        {
            y += S(6);
        }

        int index = 0;
        foreach (var (note, buttons) in group.Cards)
        {
            if (index++ >= limit)
            {
                _cut.UnionWith(buttons);
                continue;
            }

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
            group.Rects.Add((new Rectangle(pad, y, inner, cardH), new Rectangle(pad + cardPad, y + cardPad, tw, th),
                new Rectangle(pad + cardPad, y + cardPad + th + S(2), tw, bh)));
            y += cardH + S(8);
        }

        y += S(2);
    }

    /// <summary>Karten einer Gruppe zeichnen (Hintergrund, Titel, Text; die Knöpfe sind eigene Steuerelemente).</summary>
    private void PaintCards(Graphics g, CardGroup group, string heading, int count)
    {
        Palette p = P;
        if (!group.Heading.IsEmpty)
        {
            PaintHeading(g, heading, group.Heading, count);
        }

        for (int i = 0; i < group.Rects.Count && i < group.Cards.Count; i++)
        {
            var (card, title, body) = group.Rects[i];
            PanelNote note = group.Cards[i].Note;
            Draw.FillRound(g, p.Card, card, S(Draw.RBox));
            Draw.StrokeRound(g, p.Line, card, S(Draw.RBox));
            Draw.Text(g, note.Title, F(9f, FontStyle.Bold), title, p.Fg);
            if (body.Height > 0)
            {
                Draw.Text(g, note.Body, F(8.5f), body, p.Muted, Draw.Wrap | TextFormatFlags.EndEllipsis);
            }
        }
    }

    /// <summary>Karten mit Knöpfen unter einer Überschrift (Meldungen, Post).</summary>
    private sealed class CardGroup
    {
        public readonly List<(PanelNote Note, List<SparkButton> Buttons)> Cards = new();
        public readonly List<(Rectangle Card, Rectangle Title, Rectangle Body)> Rects = new();
        public Rectangle Heading;
    }

    /// <summary>
    /// Rollfläche des Reiters: schneidet ihre Teile am Rand ab, zeichnet über <see cref="PaintTab"/> und gibt das
    /// Mausrad (auch das ihrer Knöpfe, Windows reicht es nach oben weiter) an <see cref="Wheel"/>.
    /// </summary>
    private sealed class ScrollHost : Panel
    {
        public ScrollHost()
        {
            SetStyle(ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint | ControlStyles.ResizeRedraw | ControlStyles.UserPaint, true);
            TabStop = false;
        }

        public Action<int>? Wheel { get; set; }

        public Action<Graphics>? PaintTab { get; set; }

        public Rectangle Thumb { get; set; }

        protected override void OnPaint(PaintEventArgs e)
        {
            e.Graphics.Clear(Theme.Current.Card);
            PaintTab?.Invoke(e.Graphics);
        }

        protected override void OnMouseWheel(MouseEventArgs e)
        {
            Wheel?.Invoke(e.Delta);
            if (e is HandledMouseEventArgs handled)
            {
                handled.Handled = true;
            }
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
        Draw.StrokeRound(g, p.Line, box, S(Draw.RBox));
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

    // ein Termin unter „Als Nächstes“ öffnet seinen Tag im Kalender des Panels (Begleiter nachziehen 7a)
    private Action? AgendaOpenAt(Point at)
    {
        if (_tab != PanelTab.Heute || _model.Agenda is not { } agenda)
        {
            return null;
        }

        for (int i = 0; i < _agendaRows.Count && i < agenda.Count; i++)
        {
            if (_agendaRows[i].Contains(at))
            {
                return agenda[i].Open;
            }
        }

        return null;
    }

    // Daumen breiter fassen als gezeichnet, damit er sich gut greifen lässt
    private bool OverThumb(Point at) => !_host.Thumb.IsEmpty && Rectangle.Inflate(_host.Thumb, S(5), 0).Contains(at);

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

    protected override void OnMouseWheel(MouseEventArgs e)
    {
        base.OnMouseWheel(e);
        // das Mausrad über dem Fragefeld oder den Kacheln rollt den Reiter, wenn der Zeiger über ihm steht
        if (_host.Visible && _host.RectangleToScreen(_host.ClientRectangle).Contains(Cursor.Position))
        {
            ScrollTo(_scroll - (e.Delta * S(48) / 120));
        }
    }

    private void OnHostMouseMove(object? sender, MouseEventArgs e)
    {
        if (_dragY is int from && _host.Thumb.Height > 0)
        {
            int track = Math.Max(1, _host.Height - S(8) - _host.Thumb.Height);
            ScrollTo(_dragScroll + ((e.Y - from) * Math.Max(0, _contentH - _host.Height) / track));
            return;
        }

        _host.Cursor = AgendaOpenAt(e.Location) is not null ? Cursors.Hand : Cursors.Default;
    }

    private void OnHostMouseDown(object? sender, MouseEventArgs e)
    {
        if (e.Button == MouseButtons.Left && OverThumb(e.Location))
        {
            _dragY = e.Y;
            _dragScroll = _scroll;
            _host.Capture = true;
            _host.Invalidate();
        }
    }

    private void OnHostMouseUp(object? sender, MouseEventArgs e)
    {
        if (_dragY is not null)
        {
            _dragY = null;
            _host.Capture = false;
            _host.Invalidate();
            return;
        }

        if (e.Button == MouseButtons.Left && AgendaOpenAt(e.Location) is { } open)
        {
            open();
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
