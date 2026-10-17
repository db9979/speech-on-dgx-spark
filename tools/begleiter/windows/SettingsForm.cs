namespace SparkBegleiter;

/// <summary>Was das Einstellungsfenster vom Programm braucht (umgesetzt von <see cref="TrayContext"/>).</summary>
internal interface IBegleiterHost
{
    AppConfig Config { get; }

    DeskConfig? Desk { get; }

    Connection Connection { get; }

    Updater Updates { get; }

    /// <summary>„Nach Updates suchen“ läuft gerade.</summary>
    bool CheckingForUpdates { get; }

    /// <summary>Kürzel ändern. <c>null</c> = übernommen, sonst ein deutscher Hinweis (ungültig, doppelt, belegt).</summary>
    string? ChangeHotkey(string part, Hotkey hotkey);

    /// <summary>Alle Kürzel vorübergehend freigeben, solange ein neues aufgenommen wird.</summary>
    void SuspendHotkeys(bool suspend);

    /// <summary>Teile, deren Kürzel beim letzten Registrieren belegt war.</summary>
    IReadOnlyCollection<string> HotkeyConflicts { get; }

    void OpenPanel();

    bool Pair(IWin32Window? owner);

    void Unpair(IWin32Window? owner);

    /// <summary>Einstellungen neu vom Spark holen (enthält die Update-Angabe).</summary>
    void CheckForUpdates();

    /// <summary>Klick auf „Aktualisieren“.</summary>
    void RequestUpdate();

    void SetAutoDownload(bool on);

    void OpenCoffee();

    /// <summary>Teil "folder": der beobachtete Ordner (lokale Einstellung).</summary>
    string WissenFolder { get; }

    /// <summary>Anderen Ordner wählen. <c>null</c> = übernommen, sonst ein deutscher Hinweis.</summary>
    string? SetWissenFolder(string path);

    /// <summary>„Antworten vorlesen“ im Fenster Frag Spark (always/spoken/never).</summary>
    void SetAskSpeak(string mode);

    /// <summary>Teil "daily": lokale Zeiten und an/aus. <c>null</c> = gespeichert, sonst ein deutscher Hinweis.</summary>
    string? SetDaily(bool morningOn, string morningTime, bool eveningOn, string eveningTime);

    /// <summary>Kopplung, Einstellungen vom Spark, Zustand oder Update haben sich geändert.</summary>
    event EventHandler? Changed;
}

/// <summary>
/// Lokale Einstellungen mit Seitenmenü wie im Panel (Entwurf „Begleiter aufpolieren“ 2a, Dominik 2026-10-17):
/// Übersicht (Zustand und Teile), Frag Spark (Antworten vorlesen), Tastenkürzel, Tagesstart, Wissen-Ordner,
/// darunter „Gerät“ mit Kopplung und „Über und Update“ (Version, Update, automatisches Laden, Kaffee).
/// Frag Spark und Tagesstart erscheinen nur, wenn der Teil an ist.
/// </summary>
internal sealed class SettingsForm : ThemedForm
{
    public const string TabOverview = "overview";
    public const string TabHotkeys = "hotkeys";
    public const string TabPairing = "pairing";
    public const string TabAbout = "about";

    private const int PartsShown = 6;

    private readonly IBegleiterHost _host;
    private readonly SparkButton _navOverview = Nav("Übersicht", Glyph.Grid);
    private readonly SparkButton _navAsk = Nav("Frag Spark", Glyph.Chat);
    private readonly SparkButton _navHotkeys = Nav("Tastenkürzel", Glyph.Key);
    private readonly SparkButton _navDaily = Nav("Tagesstart", Glyph.Sun);
    private readonly SparkButton _navFolder = Nav("Wissen-Ordner", Glyph.Folder);
    private readonly SparkButton _navPairing = Nav("Kopplung", Glyph.Link);
    private readonly SparkButton _navAbout = Nav("Über und Update", Glyph.Info);
    private readonly Panel _pageOverview = NewPage();
    private readonly Panel _pageAsk = NewPage();
    private readonly Panel _pageHotkeys = NewPage();
    private readonly Panel _pageDaily = NewPage();
    private readonly Panel _pageFolder = NewPage();
    private readonly Panel _pagePairing = NewPage();
    private readonly Panel _pageAbout = NewPage();
    private readonly SparkButton _close = new(ButtonKind.Secondary, "Schließen");
    private Rectangle _sideTitle;
    private Rectangle _sideFace;
    private Rectangle _sideGroup;
    private int _sideWidth;

    // Übersicht
    private readonly TLabel _ovTitle = new(TextRole.Title, "Übersicht");
    private readonly TLabel _ovIntro = new(TextRole.Muted, "Was dieser Begleiter auf diesem PC kann.");
    private readonly StatusCard _ovCard = new();
    private readonly TLabel _partsHeading = new(TextRole.Section, "TEILE");
    private readonly PartsList _parts = new();
    private readonly SparkButton _partsMore = new(ButtonKind.Link, "Alle zeigen");
    private readonly TLabel _partsHint = new(TextRole.SmallMuted, "Ein- und ausschalten im Panel unter Ich → Begleiter.");
    private bool _partsAll;

    // Tastenkürzel
    private readonly TLabel _hotkeyTitle = new(TextRole.Title, "Tastenkürzel");
    private readonly TLabel _hotkeyIntro = new(TextRole.Muted, "In ein Feld klicken und die neue Kombination drücken (mit Strg oder Alt, z. B. Strg+Alt+S).");
    private readonly Dictionary<string, (TLabel Label, RoundedHost Host, HotkeyBox Box, SparkButton Reset, TLabel Note)> _rows = new();

    // Kopplung
    private readonly TLabel _pairTitle = new(TextRole.Title, "Kopplung");
    private readonly TLabel _pairing = new(TextRole.Muted);
    private readonly SparkButton _panel = new(ButtonKind.Secondary, "Panel öffnen");
    private readonly SparkButton _repair = new(ButtonKind.Secondary, "Neu koppeln …");
    private readonly SparkButton _unpair = new(ButtonKind.Secondary, "Entkoppeln …") { Danger = true };

    // Wissen-Ordner
    private readonly TLabel _folderTitle = new(TextRole.Title, "Wissen-Ordner");
    private readonly TLabel _folderIntro = new(TextRole.Muted, "Dateien in diesem Ordner landen im Wissen deines Profils.");
    private readonly TLabel _folderPath = new(TextRole.Normal);
    private readonly SparkButton _folderPick = new(ButtonKind.Secondary, "Ordner wählen …");
    private readonly TLabel _folderNote = new(TextRole.SmallMuted);

    // Frag Spark: Antworten vorlesen (nur mit Teil "speak")
    private readonly TLabel _askTitle = new(TextRole.Title, "Frag Spark");
    private readonly TLabel _askIntro = new(TextRole.Muted, "Wie das Fenster Frag Spark antwortet.");
    private readonly TLabel _speakHeading = new(TextRole.Section, "ANTWORTEN VORLESEN");
    private readonly Dictionary<string, SparkButton> _speakChips = AskSpeakModes.All.ToDictionary(m => m, m => new SparkButton(ButtonKind.Chip, AskSpeakModes.Label(m)));
    private readonly TLabel _speakNote = new(TextRole.SmallMuted, "Gesprochene Fragen: Mikrofon-Knopf im Fenster Frag Spark oder das Weckwort. Stop in der Pille oder eine neue Frage beendet das Vorlesen.");
    private bool _speakShown;

    // Tagesstart und Feierabend (nur wenn der Teil an ist)
    private readonly TLabel _dailyTitle = new(TextRole.Title, "Tagesstart und Feierabend");
    private readonly ToggleSwitch _morningOn = new("Tagesstart beim ersten Entsperren oder Start ab");
    private readonly TextBox _morningTime = new() { MaxLength = 5, TextAlign = HorizontalAlignment.Center, AccessibleName = "Uhrzeit Tagesstart" };
    private readonly RoundedHost _morningHost;
    private readonly ToggleSwitch _eveningOn = new("Feierabend beim Sperren des PCs ab");
    private readonly TextBox _eveningTime = new() { MaxLength = 5, TextAlign = HorizontalAlignment.Center, AccessibleName = "Uhrzeit Feierabend" };
    private readonly RoundedHost _eveningHost;
    private readonly TLabel _dailyNote = new(TextRole.SmallMuted);
    private bool _updatingDaily;
    private bool _dailyShown;

    // Über und Update
    private readonly FaceBox _face = new();
    private readonly TLabel _aboutTitle = new(TextRole.Title);
    private readonly TLabel _aboutSub = new(TextRole.SmallMuted);
    private readonly StatusPill _updatePill = new();
    private readonly SparkButton _check = new(ButtonKind.Secondary, "Nach Updates suchen");
    private readonly SparkButton _update = new(ButtonKind.Primary, "Aktualisieren");
    private readonly TLabel _updateError = new(TextRole.Error);
    private readonly ToggleSwitch _auto = new("Updates automatisch laden, vor dem Installieren fragen");
    private readonly TLabel _coffeeHeading = new(TextRole.Section, "SPARK UNTERSTÜTZEN");
    private readonly TLabel _coffeeText = new(TextRole.Muted, "Der Spark ist kostenlos. Wenn er dir hilft, freut sich der Entwickler über einen Kaffee.");
    private readonly SparkButton _coffee = new(ButtonKind.Coffee, "☕ Buy me a coffee");

    private Panel _page;
    private bool _updatingAuto;
    private bool _updateShown;

    public SettingsForm(IBegleiterHost host, string? tab = null)
    {
        _host = host;
        _page = _pageOverview;
        _morningHost = new RoundedHost(_morningTime);
        _eveningHost = new RoundedHost(_eveningTime);

        Text = "Spark-Begleiter – Einstellungen";
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        MinimizeBox = false;
        ShowInTaskbar = true;
        StartPosition = FormStartPosition.Manual;
        Rectangle area = Screen.FromPoint(Cursor.Position).WorkingArea;
        Location = new Point(area.Left + (area.Width / 3), area.Top + (area.Height / 4));
        KeyPreview = true;

        int tab2 = 0;
        foreach (SparkButton nav in Navs())
        {
            nav.TabIndex = tab2++;
            Controls.Add(nav);
        }

        foreach (Panel page in Pages())
        {
            page.TabIndex = 20;
            Controls.Add(page);
        }

        Controls.Add(_close);
        _close.TabIndex = 21;

        // Übersicht
        _pageOverview.Controls.AddRange(new Control[] { _ovTitle, _ovIntro, _ovCard, _partsHeading, _parts, _partsMore, _partsHint });
        _partsMore.Click += (_, _) =>
        {
            _partsAll = !_partsAll;
            RefreshAll();
            Relayout();
        };

        // Tastenkürzel
        _pageHotkeys.Controls.AddRange(new Control[] { _hotkeyTitle, _hotkeyIntro });
        foreach (string part in Parts.WithHotkey)
        {
            var box = new HotkeyBox { AccessibleName = "Tastenkürzel " + Parts.Label(part) };
            var host2 = new RoundedHost(box);
            var label = new TLabel(TextRole.Normal, Parts.Label(part));
            var reset = new SparkButton(ButtonKind.Secondary, "Standard") { AccessibleName = "Standard für " + Parts.Label(part) };
            var note = new TLabel(TextRole.SmallMuted);
            _pageHotkeys.Controls.AddRange(new Control[] { label, host2, reset, note });
            _rows[part] = (label, host2, box, reset, note);

            string p = part;
            box.Enter += (_, _) => _host.SuspendHotkeys(true);
            box.Leave += (_, _) => _host.SuspendHotkeys(false);
            box.Captured += (_, hotkey) => Change(p, hotkey);
            box.Rejected += (_, text) => ShowNote(p, text, error: true);
            reset.Click += (_, _) => Change(p, Hotkey.DefaultFor(p));
        }

        // Kopplung
        _pagePairing.Controls.AddRange(new Control[] { _pairTitle, _pairing, _panel, _repair, _unpair });

        // Wissen-Ordner
        _pageFolder.Controls.AddRange(new Control[] { _folderTitle, _folderIntro, _folderPath, _folderPick, _folderNote });
        _folderPick.Click += (_, _) => PickFolder();

        // Frag Spark
        _pageAsk.Controls.AddRange(new Control[] { _askTitle, _askIntro, _speakHeading, _speakNote });
        foreach (var (mode, chip) in _speakChips)
        {
            chip.AccessibleName = "Antworten vorlesen: " + AskSpeakModes.Label(mode);
            _pageAsk.Controls.Add(chip);
            string m = mode;
            chip.Click += (_, _) => _host.SetAskSpeak(m);
        }

        // Tagesstart
        _pageDaily.Controls.AddRange(new Control[] { _dailyTitle, _morningOn, _morningHost, _eveningOn, _eveningHost, _dailyNote });
        _morningOn.CheckedChanged += (_, _) => SaveDaily();
        _eveningOn.CheckedChanged += (_, _) => SaveDaily();
        _morningTime.Leave += (_, _) => SaveDaily();
        _eveningTime.Leave += (_, _) => SaveDaily();

        // Über und Update (der Kaffee steht nur hier, Dominik 2026-10-17)
        _pageAbout.Controls.AddRange(new Control[] { _face, _aboutTitle, _aboutSub, _updatePill, _check, _update, _updateError, _auto, _coffeeHeading, _coffeeText, _coffee });
        _coffee.AccessibleName = "Buy me a coffee (öffnet den Browser)";

        _navOverview.Click += (_, _) => ShowPage(_pageOverview);
        _navAsk.Click += (_, _) => ShowPage(_pageAsk);
        _navHotkeys.Click += (_, _) => ShowPage(_pageHotkeys);
        _navDaily.Click += (_, _) => ShowPage(_pageDaily);
        _navFolder.Click += (_, _) => ShowPage(_pageFolder);
        _navPairing.Click += (_, _) => ShowPage(_pagePairing);
        _navAbout.Click += (_, _) => ShowPage(_pageAbout);
        _panel.Click += (_, _) => _host.OpenPanel();
        _repair.Click += (_, _) => _host.Pair(this);
        _unpair.Click += (_, _) => _host.Unpair(this);
        _check.Click += (_, _) => _host.CheckForUpdates();
        _update.Click += (_, _) => _host.RequestUpdate();
        _auto.CheckedChanged += (_, _) =>
        {
            if (!_updatingAuto)
            {
                _host.SetAutoDownload(_auto.Checked);
            }
        };
        _coffee.Click += (_, _) => _host.OpenCoffee();
        _close.Click += (_, _) => Close();
        CancelButton = _close;

        _host.Changed += OnHostChanged;
        RefreshAll();
        ShowTab(tab);
    }

    protected override void OnLoad(EventArgs e)
    {
        base.OnLoad(e);
        CenterToScreen(); // erst jetzt steht die Größe fest
    }

    private static Panel NewPage() => new() { BackColor = Theme.Current.Card, Visible = false };

    private static SparkButton Nav(string text, Glyph glyph) => new(ButtonKind.Nav, text) { Glyph = glyph };

    private IEnumerable<SparkButton> Navs() => new[] { _navOverview, _navAsk, _navHotkeys, _navDaily, _navFolder, _navPairing, _navAbout };

    private IEnumerable<Panel> Pages() => new[] { _pageOverview, _pageAsk, _pageHotkeys, _pageDaily, _pageFolder, _pagePairing, _pageAbout };

    private SparkButton NavFor(Panel page) =>
        ReferenceEquals(page, _pageAsk) ? _navAsk
        : ReferenceEquals(page, _pageHotkeys) ? _navHotkeys
        : ReferenceEquals(page, _pageDaily) ? _navDaily
        : ReferenceEquals(page, _pageFolder) ? _navFolder
        : ReferenceEquals(page, _pagePairing) ? _navPairing
        : ReferenceEquals(page, _pageAbout) ? _navAbout
        : _navOverview;

    /// <summary>Seite wählen (z. B. „Über und Update“ nach einem Klick auf den Update-Hinweis).</summary>
    public void ShowTab(string? tab) => ShowPage(tab switch
    {
        TabHotkeys => _pageHotkeys,
        TabPairing => _pagePairing,
        TabAbout => _pageAbout,
        _ => _pageOverview,
    });

    private void ShowPage(Panel page)
    {
        // Frag Spark und Tagesstart gibt es nur, solange der Teil an ist.
        if ((ReferenceEquals(page, _pageAsk) && !_speakShown) || (ReferenceEquals(page, _pageDaily) && !_dailyShown))
        {
            page = _pageOverview;
        }

        _page = page;
        foreach (Panel p in Pages())
        {
            p.Visible = ReferenceEquals(p, page);
        }

        SparkButton current = NavFor(page);
        foreach (SparkButton nav in Navs())
        {
            nav.Checked = ReferenceEquals(nav, current);
        }

        Relayout();
    }

    private void Relayout()
    {
        if (IsHandleCreated)
        {
            LayoutContent();
            Invalidate(true);
        }
    }

    protected override void OnThemeApplied()
    {
        foreach (Panel page in Pages())
        {
            page.BackColor = P.Card;
        }

        foreach (SparkButton nav in Navs())
        {
            nav.Surface = P.Soft;
        }
    }

    protected override void LayoutContent()
    {
        int side = S(200);
        int pad = S(24);
        int width = S(740);
        int inner = width - side - (2 * pad);
        _sideWidth = side;

        // Seitenmenü: Gesicht und „Begleiter“, dann die Punkte; vor „Kopplung“ die Gruppe „Gerät“
        int sy = BarHeight + S(16);
        int face = S(26);
        _sideFace = new Rectangle(S(16), sy, face, face);
        _sideTitle = new Rectangle(S(16) + face + S(9), sy, side - face - S(41), face);
        sy += face + S(16);
        _navAsk.Visible = _speakShown;
        _navDaily.Visible = _dailyShown;
        foreach (SparkButton nav in Navs())
        {
            if (ReferenceEquals(nav, _navAsk) && !_speakShown || ReferenceEquals(nav, _navDaily) && !_dailyShown)
            {
                continue;
            }

            if (ReferenceEquals(nav, _navPairing))
            {
                int gh = Draw.Measure("AG", F(7.5f, FontStyle.Bold)).Height;
                sy += S(10);
                _sideGroup = new Rectangle(S(20), sy, side - S(30), gh);
                sy += gh + S(4);
            }

            int h = nav.Preferred().Height;
            nav.Bounds = new Rectangle(S(10), sy, side - S(20), h);
            sy += h + S(2);
        }

        int top = BarHeight + S(20);
        int ov = LayoutOverview(inner);
        int ak = LayoutAsk(inner);
        int hk = LayoutHotkeys(inner);
        int dy = LayoutDaily(inner);
        int fo = LayoutFolder(inner);
        int pr = LayoutPairing(inner);
        int ab = LayoutAbout(inner);
        int pageH = new[] { ov, ak, hk, dy, fo, pr, ab }.Max();
        foreach (Panel page in Pages())
        {
            page.Bounds = new Rectangle(side + pad, top, inner, pageH);
        }

        int y = Math.Max(top + pageH + S(16), sy + S(16));
        Size close = _close.Preferred();
        _close.Bounds = new Rectangle(width - pad - close.Width, y, close.Width, close.Height);
        y += close.Height + S(18);
        ClientSize = new Size(width, y);
    }

    /// <summary>Titel und ein Satz oben auf jeder Seite.</summary>
    private int Head(TLabel title, TLabel? intro, int width)
    {
        int y = title.Fit(0, 0, width) + S(2);
        if (intro is not null)
        {
            y += intro.Fit(0, y, width);
        }

        return y + S(16);
    }

    private int LayoutOverview(int width)
    {
        int y = Head(_ovTitle, _ovIntro, width);
        _ovCard.Bounds = new Rectangle(0, y, width, _ovCard.PreferredHeight(width));
        y += _ovCard.Height + S(20);
        y += _partsHeading.Fit(S(2), y, width) + S(6);
        _parts.Bounds = new Rectangle(0, y, width, _parts.PreferredHeight());
        y += _parts.Height + S(4);
        _partsMore.Visible = _parts.Hidden > 0 || _partsAll;
        if (_partsMore.Visible)
        {
            Size more = _partsMore.Preferred();
            _partsMore.Bounds = new Rectangle((width - more.Width) / 2, y, more.Width, more.Height);
            y += more.Height + S(6);
        }

        y += S(6);
        y += _partsHint.Fit(0, y, width);
        return y;
    }

    private int LayoutAsk(int width)
    {
        int y = Head(_askTitle, _askIntro, width);
        y += _speakHeading.Fit(S(2), y, width) + S(8);
        int cx = 0;
        int rowH = 0;
        foreach (SparkButton chip in _speakChips.Values)
        {
            Size size = chip.Preferred();
            chip.Bounds = new Rectangle(cx, y, size.Width, size.Height);
            cx += size.Width + S(6);
            rowH = Math.Max(rowH, size.Height);
        }

        y += rowH + S(8);
        y += _speakNote.Fit(0, y, width);
        return y;
    }

    private int LayoutHotkeys(int width)
    {
        int y = Head(_hotkeyTitle, _hotkeyIntro, width);
        int labelW = S(150);
        foreach (string part in Parts.WithHotkey)
        {
            var (label, host, _, reset, note) = _rows[part];
            int rowH = S(36);
            label.Fit(0, y + ((rowH - Draw.TextHeight(label.Text, label.Font, labelW)) / 2), labelW);
            host.Bounds = new Rectangle(labelW + S(8), y, S(190), rowH);
            Size r = reset.Preferred();
            reset.Bounds = new Rectangle(host.Right + S(8), y + ((rowH - r.Height) / 2), r.Width, r.Height);
            y += rowH + S(4);
            int noteH = note.Fit(labelW + S(8), y, width - labelW - S(8));
            y += Math.Max(noteH, S(4)) + S(8);
        }

        return y;
    }

    private int LayoutDaily(int width)
    {
        int y = Head(_dailyTitle, null, width);
        int boxW = S(76);
        int rowH = S(34);
        foreach (var (toggle, host) in new[] { (_morningOn, _morningHost), (_eveningOn, _eveningHost) })
        {
            int th = toggle.Fit(0, y, width - boxW - S(10));
            toggle.Top = y + Math.Max(0, (rowH - th) / 2);
            host.Bounds = new Rectangle(width - boxW, y, boxW, rowH);
            y += Math.Max(rowH, th) + S(10);
        }

        y += _dailyNote.Fit(0, y, width);
        return y;
    }

    private int LayoutFolder(int width)
    {
        int y = Head(_folderTitle, _folderIntro, width);
        Size pick = _folderPick.Preferred();
        int pathH = _folderPath.Fit(0, y + Math.Max(0, (pick.Height - Draw.TextHeight(_folderPath.Text, _folderPath.Font, width - pick.Width - S(10))) / 2), width - pick.Width - S(10));
        _folderPick.Bounds = new Rectangle(width - pick.Width, y, pick.Width, pick.Height);
        y += Math.Max(pick.Height, pathH) + S(8);
        y += _folderNote.Fit(0, y, width);
        return y;
    }

    private int LayoutPairing(int width)
    {
        int y = Head(_pairTitle, _pairing, width);
        int x = 0;
        foreach (SparkButton b in new[] { _panel, _repair, _unpair })
        {
            Size size = b.Preferred();
            b.Bounds = new Rectangle(x, y, size.Width, size.Height);
            x += size.Width + S(8);
        }

        return y + _panel.Height;
    }

    private int LayoutAbout(int width)
    {
        int y = 0;
        int face = S(52);
        _face.Bounds = new Rectangle(0, y, face, face);
        int tx = face + S(14);
        int th = Draw.TextHeight(_aboutTitle.Text, _aboutTitle.Font, width - tx);
        int sh = Draw.TextHeight(_aboutSub.Text, _aboutSub.Font, width - tx);
        int top = y + Math.Max(0, (face - th - sh) / 2);
        _aboutTitle.Fit(tx, top, width - tx);
        _aboutSub.Fit(tx, top + th + S(2), width - tx);
        y += Math.Max(face, th + sh + S(2)) + S(16);

        Size pill = _updatePill.Preferred();
        Size check = _check.Preferred();
        int rowH = Math.Max(pill.Height, check.Height);
        int maxPill = width - check.Width - S(8) - (_updateShown ? _update.Preferred().Width + S(8) : 0);
        _updatePill.Bounds = new Rectangle(0, y + ((rowH - pill.Height) / 2), Math.Min(pill.Width, Math.Max(S(60), maxPill)), pill.Height);
        int x = _updatePill.Right + S(8);
        _check.Bounds = new Rectangle(x, y + ((rowH - check.Height) / 2), check.Width, check.Height);
        x = _check.Right + S(8);
        if (_updateShown)
        {
            Size up = _update.Preferred();
            _update.Bounds = new Rectangle(x, y + ((rowH - up.Height) / 2), up.Width, up.Height);
        }

        y += rowH + S(8);
        int errH = _updateError.Fit(0, y, width);
        y += errH > 0 ? errH + S(8) : S(4);
        y += _auto.Fit(0, y, width) + S(24);
        y += _coffeeHeading.Fit(S(2), y, width) + S(6);
        y += _coffeeText.Fit(0, y, width) + S(10);
        Size coffee = _coffee.Preferred();
        _coffee.Bounds = new Rectangle(0, y, coffee.Width, coffee.Height);
        y += coffee.Height;
        return y;
    }

    protected override void PaintContent(Graphics g)
    {
        Draw.HighQuality(g);
        using (var side = new SolidBrush(P.Soft))
        {
            g.FillRectangle(side, 0, BarHeight, _sideWidth, ClientSize.Height - BarHeight);
        }

        using (var line = new Pen(P.Line))
        {
            g.DrawLine(line, _sideWidth, BarHeight, _sideWidth, ClientSize.Height);
        }

        Face.Draw(g, _sideFace, P);
        Draw.Text(g, "Begleiter", F(10.5f, FontStyle.Bold), _sideTitle, P.Fg);
        Draw.Text(g, "GERÄT", F(7.5f, FontStyle.Bold), _sideGroup, P.Muted);
    }

    private void OnHostChanged(object? sender, EventArgs e)
    {
        if (!IsDisposed)
        {
            RefreshAll();
            if (IsHandleCreated)
            {
                LayoutContent();
                Invalidate(true);
            }
        }
    }

    private void RefreshAll()
    {
        AppConfig config = _host.Config;
        DeskConfig? desk = _host.Desk;

        if (config.IsPaired)
        {
            string profile = desk?.Profile ?? config.Profile ?? "?";
            _pairing.Text = $"Gekoppelt mit dem Profil „{profile}“ auf {config.Base}"
                            + (string.IsNullOrEmpty(config.Device) ? "." : $" als „{config.Device}“.");
        }
        else
        {
            _pairing.Text = "Nicht gekoppelt. Im Panel unter Ich → Begleiter „Gerät koppeln“ wählen und hier „Koppeln“.";
        }

        _panel.Enabled = !string.IsNullOrEmpty(config.Base);
        _unpair.Enabled = config.IsPaired;
        _repair.Text = config.IsPaired ? "Neu koppeln …" : "Koppeln …";

        foreach (string part in Parts.WithHotkey)
        {
            HotkeyBox box = _rows[part].Box;
            box.Hotkey = config.GetHotkey(part);
            if (_host.HotkeyConflicts.Contains(part))
            {
                ShowNote(part, $"{box.Hotkey} ist schon von einem anderen Programm belegt.", error: true);
            }
            else if (desk is null || !desk.IsOn(part))
            {
                ShowNote(part, "Teil ist aus (im Panel unter Ich → Begleiter einschalten).", error: false);
            }
            else
            {
                ShowNote(part, "", error: false);
            }
        }

        // Übersicht: Zustand als Satz, dann die Teile (an zuerst)
        (string title, string detail, StatusKind kind) = (config.IsPaired, _host.Connection) switch
        {
            (false, _) => ("Nicht gekoppelt", "Unter Kopplung mit dem Spark verbinden.", StatusKind.Off),
            (_, Connection.Notaus) => ("Notaus ist an", "Aufheben nur im Panel im Browser mit der PIN.", StatusKind.Bad),
            (_, Connection.Online) => ("Alles läuft", AboutLine(config, desk), StatusKind.Ok),
            (_, Connection.Unknown) => ("Verbinde …", AboutLine(config, desk), StatusKind.Off),
            _ => ("Spark nicht erreichbar", AboutLine(config, desk), StatusKind.Off),
        };
        _ovCard.Set(title, detail, kind);
        if (desk is null)
        {
            _parts.Set(Array.Empty<(string, string, bool)>(), 0);
            _partsHeading.Text = "TEILE";
        }
        else
        {
            var rows = Parts.All
                .Select(p => (Name: Parts.Label(p), State: desk.IsOn(p) ? "an" : desk.Allowed.Count > 0 && !desk.IsAllowed(p) ? "nicht freigegeben" : "aus", On: desk.IsOn(p)))
                .OrderBy(r => r.On ? 0 : 1)
                .ToList();
            _parts.Set(rows, _partsAll ? rows.Count : PartsShown);
            _partsHeading.Text = $"TEILE · {rows.Count(r => r.On)} VON {rows.Count} AN";
        }

        _partsMore.Text = _partsAll ? "Weniger zeigen" : $"Weitere {_parts.Hidden} zeigen";

        _folderPath.Text = _host.WissenFolder;
        if (_folderNote.Role != TextRole.Error || desk is null)
        {
            _folderNote.Text = desk?.IsOn(Parts.Folder) == true
                ? "Neue und geänderte Dateien darin gehen nach 10 Sekunden Ruhe ins Wissen (höchstens 50 am Tag)."
                : "Teil ist aus (im Panel unter Ich → Begleiter einschalten).";
        }

        _speakShown = desk?.IsOn(Parts.Speak) == true;
        string speakMode = AskSpeakModes.Normalize(config.AskSpeak);
        foreach (var (mode, chip) in _speakChips)
        {
            chip.Checked = mode == speakMode;
        }

        _dailyShown = desk?.IsOn(Parts.Daily) == true;
        if (!_morningTime.Focused && !_eveningTime.Focused)
        {
            _updatingDaily = true;
            _morningOn.Checked = config.DailyMorningOn;
            _eveningOn.Checked = config.DailyEveningOn;
            _morningTime.Text = config.DailyMorningTime;
            _eveningTime.Text = config.DailyEveningTime;
            _updatingDaily = false;
        }

        if (_dailyNote.Role != TextRole.Error)
        {
            _dailyNote.Text = "Einmal am Tag als Hinweis und im Fenster „Frag Spark“. Feierabend: die ersten Termine von morgen und offene Aufgaben.";
        }

        RefreshAbout(config);
        if ((ReferenceEquals(_page, _pageAsk) && !_speakShown) || (ReferenceEquals(_page, _pageDaily) && !_dailyShown))
        {
            ShowPage(_pageOverview); // der Teil wurde gerade im Panel ausgeschaltet
        }
    }

    /// <summary>„Verbunden mit … · Profil … · Version …“ unter dem Zustand.</summary>
    private static string AboutLine(AppConfig config, DeskConfig? desk)
    {
        string host = Uri.TryCreate(config.Base, UriKind.Absolute, out Uri? uri) ? uri.Authority : config.Base ?? "";
        string profile = desk?.Profile ?? config.Profile ?? "";
        string version = Updater.IsDevelopment ? "Entwicklungsversion" : "Version " + Updater.CurrentText;
        return string.Join(" · ", new[] { "Spark " + host, profile.Length > 0 ? "Profil " + profile : "", version }.Where(s => s.Length > 0));
    }

    private void SaveDaily()
    {
        if (_updatingDaily)
        {
            return;
        }

        string? error = _host.SetDaily(_morningOn.Checked, _morningTime.Text, _eveningOn.Checked, _eveningTime.Text);
        _dailyNote.Role = error is null ? TextRole.SmallMuted : TextRole.Error;
        _dailyNote.Text = error ?? "Gespeichert.";
        _dailyNote.ApplyTheme(DeviceDpi);
        if (IsHandleCreated)
        {
            LayoutContent();
            Invalidate(true);
        }
    }

    private void PickFolder()
    {
        using var dialog = new FolderBrowserDialog
        {
            Description = "Ordner für Spark-Wissen wählen",
            UseDescriptionForTitle = true,
            ShowNewFolderButton = true,
            InitialDirectory = Directory.Exists(_host.WissenFolder) ? _host.WissenFolder : "",
        };
        if (dialog.ShowDialog(this) != DialogResult.OK || string.IsNullOrEmpty(dialog.SelectedPath))
        {
            return;
        }

        string? error = _host.SetWissenFolder(dialog.SelectedPath);
        _folderNote.Role = error is null ? TextRole.SmallMuted : TextRole.Error;
        if (error is not null)
        {
            _folderNote.Text = error;
        }

        _folderNote.ApplyTheme(DeviceDpi);
        RefreshAll();
        if (IsHandleCreated)
        {
            LayoutContent();
            Invalidate(true);
        }
    }

    private void RefreshAbout(AppConfig config)
    {
        Updater u = _host.Updates;
        _aboutTitle.Text = Updater.IsDevelopment
            ? "Spark-Begleiter · Entwicklungsversion"
            : "Spark-Begleiter " + Updater.CurrentText;
        string where = config.IsPaired && Uri.TryCreate(config.Base, UriKind.Absolute, out Uri? uri)
            ? "gekoppelt mit " + uri.Authority
            : "nicht gekoppelt";
        _aboutSub.Text = Updater.ArchLabel + " · " + where;

        string? button = null;
        bool buttonEnabled = true;
        (string text, StatusKind dot) = (Updater.IsDevelopment, config.IsPaired, _host.CheckingForUpdates, u.Phase) switch
        {
            (true, _, _, _) => ("Entwicklungsversion – keine Updates", StatusKind.Off),
            (_, false, _, _) => ("Nicht gekoppelt", StatusKind.Off),
            (_, _, true, _) => ("Suche …", StatusKind.Busy),
            (_, _, _, UpdatePhase.Available) => ($"Neue Version {u.Info?.Version} · {Updater.SizeText(u.Info?.Size ?? 0)}", StatusKind.Busy),
            (_, _, _, UpdatePhase.Downloading) => ($"Wird geladen … {(int)(u.Progress * 100)} %", StatusKind.Busy),
            (_, _, _, UpdatePhase.Ready) => ($"Bereit zum Installieren: {u.Info?.Version}", StatusKind.Busy),
            (_, _, _, UpdatePhase.Installing) => ("Wird installiert …", StatusKind.Busy),
            (_, _, _, UpdatePhase.Failed) => ("Update hat nicht geklappt", StatusKind.Bad),
            _ when _host.Connection == Connection.Offline => ("Spark nicht erreichbar", StatusKind.Off),
            (_, _, _, UpdatePhase.UpToDate) => ("Neueste Version", StatusKind.Ok),
            _ => ("Noch nicht geprüft", StatusKind.Off),
        };

        if (!Updater.IsDevelopment && config.IsPaired)
        {
            switch (u.Phase)
            {
                case UpdatePhase.Available:
                case UpdatePhase.Ready:
                    button = "Aktualisieren";
                    break;
                case UpdatePhase.Downloading:
                    button = u.InstallRequested ? "Wird danach installiert" : "Aktualisieren";
                    buttonEnabled = !u.InstallRequested;
                    break;
                case UpdatePhase.Failed when u.Info is not null:
                    button = "Erneut versuchen";
                    break;
            }
        }

        _updatePill.Text = text;
        _updatePill.DotColor = p => PanelModel.StatusColor(dot, p);
        _updateShown = button is not null;
        _update.Visible = _updateShown;
        _update.Text = button ?? "";
        _update.Enabled = buttonEnabled;
        _updateError.Text = u.Phase == UpdatePhase.Failed && !Updater.IsDevelopment ? u.Error ?? "" : "";
        _check.Enabled = !Updater.IsDevelopment && config.IsPaired && !_host.CheckingForUpdates;

        _updatingAuto = true;
        _auto.Checked = config.AutoDownloadUpdates;
        _updatingAuto = false;
        _auto.Enabled = !Updater.IsDevelopment;
    }

    private void Change(string part, Hotkey hotkey)
    {
        string? error = _host.ChangeHotkey(part, hotkey);
        _rows[part].Box.Hotkey = _host.Config.GetHotkey(part);
        ShowNote(part, error ?? "Gespeichert.", error is not null);
    }

    private void ShowNote(string part, string text, bool error)
    {
        TLabel note = _rows[part].Note;
        note.Text = text;
        note.Role = error ? TextRole.Error : TextRole.SmallMuted;
        note.ApplyTheme(DeviceDpi);
        if (IsHandleCreated)
        {
            LayoutContent();
        }
    }

    /// <summary>Wechselt die Person in ein anderes Programm, gelten die Kürzel wieder.</summary>
    protected override void OnDeactivate(EventArgs e)
    {
        _host.SuspendHotkeys(false);
        base.OnDeactivate(e);
    }

    protected override void OnActivated(EventArgs e)
    {
        base.OnActivated(e);
        if (ActiveControl is HotkeyBox || (ActiveControl as ContainerControl)?.ActiveControl is HotkeyBox)
        {
            _host.SuspendHotkeys(true);
        }
    }

    protected override void OnFormClosed(FormClosedEventArgs e)
    {
        _host.Changed -= OnHostChanged;
        _host.SuspendHotkeys(false);
        base.OnFormClosed(e);
    }

    /// <summary>Zustand der Übersicht als Satz in einer leicht getönten Karte mit rundem Farbsymbol.</summary>
    private sealed class StatusCard : Control, IThemed
    {
        private int _dpi = 96;
        private string _title = "";
        private string _detail = "";
        private StatusKind _kind;

        public StatusCard()
        {
            SetStyle(ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint | ControlStyles.ResizeRedraw | ControlStyles.UserPaint, true);
            TabStop = false;
            AccessibleRole = AccessibleRole.StaticText;
        }

        public void Set(string title, string detail, StatusKind kind)
        {
            _title = title;
            _detail = detail;
            _kind = kind;
            AccessibleName = title + ". " + detail;
            Invalidate();
        }

        public void ApplyTheme(int dpi)
        {
            _dpi = dpi;
            Invalidate();
        }

        private int S(float v) => Draw.Scale(v, _dpi);

        public int PreferredHeight(int width)
        {
            int text = width - S(14 + 36 + 12 + 14);
            return Math.Max(S(62), Draw.Measure("Ag", Theme.UiFont(_dpi, 10f, FontStyle.Bold)).Height
                + Draw.TextHeight(_detail, Theme.UiFont(_dpi, 8.5f), text) + S(26));
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            Palette p = Theme.Current;
            g.Clear(Parent?.BackColor ?? p.Card);
            Draw.HighQuality(g);
            Color c = PanelModel.StatusColor(_kind, p);
            var r = new RectangleF(0, 0, Width, Height);
            Draw.FillRound(g, p.HighContrast ? p.Card : Palette.Mix(p.Card, c, 0.07f), r, S(14));
            Draw.StrokeRound(g, p.HighContrast ? p.Fg : Palette.Mix(p.Line, c, 0.4f), r, S(14));
            int d = S(36);
            var circle = new RectangleF(S(14), (Height - d) / 2f, d, d);
            using (var fill = new SolidBrush(p.HighContrast ? p.Card : Palette.Mix(p.Card, c, 0.18f)))
            {
                g.FillEllipse(fill, circle);
            }

            Draw.Text(g, _kind == StatusKind.Ok ? "✓" : "!", Theme.UiFont(_dpi, 11f, FontStyle.Bold), Rectangle.Round(circle), c,
                Draw.Line | TextFormatFlags.HorizontalCenter);
            int x = S(14) + d + S(12);
            int w = Math.Max(1, Width - x - S(14));
            Font title = Theme.UiFont(_dpi, 10f, FontStyle.Bold);
            Font small = Theme.UiFont(_dpi, 8.5f);
            int th = Draw.Measure("Ag", title).Height;
            int dh = Draw.TextHeight(_detail, small, w);
            int top = (Height - th - dh) / 2;
            Draw.Text(g, _title, title, new Rectangle(x, top, w, th), p.Fg);
            Draw.Text(g, _detail, small, new Rectangle(x, top + th, w, dh), p.Muted, Draw.Wrap);
        }
    }

    /// <summary>Die Teile als Liste in einem Kasten: Name links, Zustand („an“ grün, sonst grau) rechts.</summary>
    private sealed class PartsList : Control, IThemed
    {
        private int _dpi = 96;
        private IReadOnlyList<(string Name, string State, bool On)> _rows = Array.Empty<(string, string, bool)>();
        private int _shown;

        public PartsList()
        {
            SetStyle(ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint | ControlStyles.ResizeRedraw | ControlStyles.UserPaint, true);
            TabStop = false;
            AccessibleRole = AccessibleRole.List;
            AccessibleName = "Teile";
        }

        /// <summary>Teile, die erst nach „Weitere zeigen“ erscheinen.</summary>
        public int Hidden => Math.Max(0, _rows.Count - _shown);

        public void Set(IReadOnlyList<(string Name, string State, bool On)> rows, int shown)
        {
            _rows = rows;
            _shown = Math.Min(shown, rows.Count);
            AccessibleDescription = string.Join(", ", rows.Take(_shown).Select(r => r.Name + ": " + r.State));
            Invalidate();
        }

        public void ApplyTheme(int dpi)
        {
            _dpi = dpi;
            Invalidate();
        }

        private int S(float v) => Draw.Scale(v, _dpi);

        private int RowH => S(36);

        public int PreferredHeight() => _shown == 0 ? 0 : (_shown * RowH) + S(2);

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            Palette p = Theme.Current;
            g.Clear(Parent?.BackColor ?? p.Card);
            if (_shown == 0)
            {
                return;
            }

            Draw.HighQuality(g);
            var box = new RectangleF(0, 0, Width, Height);
            Draw.StrokeRound(g, p.Line, box, S(12));
            Font name = Theme.UiFont(_dpi, 9.5f);
            Font pill = Theme.UiFont(_dpi, 8f, FontStyle.Bold);
            using var line = new Pen(p.Line);
            for (int i = 0; i < _shown; i++)
            {
                int y = S(1) + (i * RowH);
                if (i > 0)
                {
                    g.DrawLine(line, S(14), y, Width - S(14), y);
                }

                var (text, state, on) = _rows[i];
                Size t = Draw.Measure(state, pill);
                var pr = new Rectangle(Width - S(14) - t.Width - S(16), y + ((RowH - t.Height - S(4)) / 2), t.Width + S(16), t.Height + S(4));
                Color c = on ? p.Ok : p.Muted;
                Draw.FillRound(g, p.HighContrast ? p.Card : Palette.Mix(p.Card, c, 0.15f), pr, pr.Height / 2f);
                Draw.Text(g, state, pill, pr, c, Draw.Line | TextFormatFlags.HorizontalCenter);
                Draw.Text(g, text, name, new Rectangle(S(14), y, Math.Max(1, pr.X - S(24)), RowH), on ? p.Fg : p.Muted);
            }
        }
    }

    /// <summary>Feld, das die nächste Tastenkombination aufnimmt statt Text.</summary>
    private sealed class HotkeyBox : TextBox
    {
        private Hotkey _hotkey;

        public HotkeyBox()
        {
            ReadOnly = true;
            ShortcutsEnabled = false;
            TextAlign = HorizontalAlignment.Center;
            Cursor = Cursors.Hand;
        }

        public event EventHandler<Hotkey>? Captured;

        public event EventHandler<string>? Rejected;

        public Hotkey Hotkey
        {
            get => _hotkey;
            set
            {
                _hotkey = value;
                Text = value.ToString();
            }
        }

        protected override bool IsInputKey(Keys keyData) => (keyData & Keys.KeyCode) != Keys.Tab || (keyData & Keys.Modifiers) != 0;

        protected override bool ProcessCmdKey(ref Message msg, Keys keyData)
        {
            // Alles hier behandeln (auch Alt+Taste, die sonst Menü/Mnemonics auslöst); Esc und Tab wie gewohnt.
            if (keyData is Keys.Escape or Keys.Tab or (Keys.Tab | Keys.Shift))
            {
                return base.ProcessCmdKey(ref msg, keyData);
            }

            HandleKey(keyData);
            return true;
        }

        protected override void OnKeyDown(KeyEventArgs e)
        {
            e.SuppressKeyPress = true;
            e.Handled = true;
        }

        protected override void OnKeyUp(KeyEventArgs e)
        {
            e.Handled = true;
            if (!Hotkey.IsModifierKey(e.KeyCode) || e.Modifiers != Keys.None)
            {
                return;
            }

            // Nur Modifikatoren gedrückt und wieder losgelassen: alte Anzeige zurück.
            Text = _hotkey.ToString();
        }

        private void HandleKey(Keys keyData)
        {
            Hotkey candidate = Hotkey.FromKeyData(keyData);
            if (Hotkey.IsModifierKey(candidate.Key))
            {
                // Noch nicht fertig: Vorschau "Strg+Alt+…"
                string mods = new Hotkey(candidate.Modifiers, Keys.None).ToString();
                Text = mods.EndsWith('?') ? mods[..^1] + "…" : mods;
                return;
            }

            if (!candidate.IsValid)
            {
                Text = _hotkey.ToString();
                Rejected?.Invoke(this, "Bitte mit Strg oder Alt kombinieren (z. B. Strg+Alt+S).");
                return;
            }

            Captured?.Invoke(this, candidate);
        }
    }
}
