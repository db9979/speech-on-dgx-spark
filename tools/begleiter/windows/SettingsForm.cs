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

    /// <summary>Kopplung, Einstellungen vom Spark, Zustand oder Update haben sich geändert.</summary>
    event EventHandler? Changed;
}

/// <summary>
/// Lokale Einstellungen in drei Reitern: Tastenkürzel, Kopplung (mit den Teilen, die das Panel festlegt) und
/// Über (Version, Bauart, Spark, Update-Zustand, „Nach Updates suchen“, automatisches Laden, Kaffee).
/// </summary>
internal sealed class SettingsForm : ThemedForm
{
    public const string TabHotkeys = "hotkeys";
    public const string TabPairing = "pairing";
    public const string TabAbout = "about";

    private readonly IBegleiterHost _host;
    private readonly SparkButton _tabHotkeys = new(ButtonKind.Chip, "Tastenkürzel");
    private readonly SparkButton _tabPairing = new(ButtonKind.Chip, "Kopplung");
    private readonly SparkButton _tabAbout = new(ButtonKind.Chip, "Über");
    private readonly Panel _pageHotkeys = NewPage();
    private readonly Panel _pagePairing = NewPage();
    private readonly Panel _pageAbout = NewPage();
    private readonly SparkButton _close = new(ButtonKind.Secondary, "Schließen");

    // Tastenkürzel
    private readonly TLabel _hotkeyIntro = new(TextRole.Muted, "In ein Feld klicken und die neue Kombination drücken (mit Strg oder Alt, z. B. Strg+Alt+S).");
    private readonly Dictionary<string, (TLabel Label, RoundedHost Host, HotkeyBox Box, SparkButton Reset, TLabel Note)> _rows = new();

    // Kopplung
    private readonly TLabel _pairing = new(TextRole.Normal);
    private readonly SparkButton _panel = new(ButtonKind.Secondary, "Panel öffnen");
    private readonly SparkButton _repair = new(ButtonKind.Secondary, "Neu koppeln …");
    private readonly SparkButton _unpair = new(ButtonKind.Secondary, "Entkoppeln …");
    private readonly TLabel _partsHeading = new(TextRole.Heading, "Teile");
    private readonly TLabel _parts = new(TextRole.Normal);
    private readonly TLabel _partsHint = new(TextRole.SmallMuted, "Ein- und ausschalten im Panel unter Ich → Begleiter.");
    private readonly TLabel _folderHeading = new(TextRole.Heading, "Ordner Spark-Wissen");
    private readonly TLabel _folderPath = new(TextRole.Normal);
    private readonly SparkButton _folderPick = new(ButtonKind.Secondary, "Ordner wählen …");
    private readonly TLabel _folderNote = new(TextRole.SmallMuted);

    // Über
    private readonly FaceBox _face = new();
    private readonly TLabel _aboutTitle = new(TextRole.Title);
    private readonly TLabel _aboutSub = new(TextRole.SmallMuted);
    private readonly StatusPill _updatePill = new();
    private readonly SparkButton _check = new(ButtonKind.Secondary, "Nach Updates suchen");
    private readonly SparkButton _update = new(ButtonKind.Primary, "Aktualisieren");
    private readonly TLabel _updateError = new(TextRole.Error);
    private readonly ToggleSwitch _auto = new("Updates automatisch laden, vor dem Installieren fragen");
    private readonly TLabel _coffeeText = new(TextRole.Muted, "Der Spark ist kostenlos. Wenn er dir hilft, freut sich der Entwickler über einen Kaffee.");
    private readonly SparkButton _coffee = new(ButtonKind.Coffee, "☕ Buy me a coffee");

    private Panel _page;
    private Rectangle _headFace;
    private Rectangle _headTitle;
    private bool _updatingAuto;
    private bool _updateShown;

    public SettingsForm(IBegleiterHost host, string? tab = null)
    {
        _host = host;
        _page = _pageHotkeys;

        Text = "Spark-Begleiter – Einstellungen";
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        MinimizeBox = false;
        ShowInTaskbar = true;
        StartPosition = FormStartPosition.Manual;
        Rectangle area = Screen.FromPoint(Cursor.Position).WorkingArea;
        Location = new Point(area.Left + (area.Width / 3), area.Top + (area.Height / 4));
        KeyPreview = true;

        Controls.AddRange(new Control[] { _tabHotkeys, _tabPairing, _tabAbout, _pageHotkeys, _pagePairing, _pageAbout, _close });
        _tabHotkeys.TabIndex = 0;
        _tabPairing.TabIndex = 1;
        _tabAbout.TabIndex = 2;
        _pageHotkeys.TabIndex = 3;
        _pagePairing.TabIndex = 3;
        _pageAbout.TabIndex = 3;
        _close.TabIndex = 4;

        // Tastenkürzel
        _pageHotkeys.Controls.Add(_hotkeyIntro);
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
        _pagePairing.Controls.AddRange(new Control[] { _pairing, _panel, _repair, _unpair, _partsHeading, _parts, _partsHint, _folderHeading, _folderPath, _folderPick, _folderNote });
        _folderPick.Click += (_, _) => PickFolder();

        // Über
        _pageAbout.Controls.AddRange(new Control[] { _face, _aboutTitle, _aboutSub, _updatePill, _check, _update, _updateError, _auto, _coffeeText, _coffee });
        _coffee.AccessibleName = "Buy me a coffee (öffnet den Browser)";

        _tabHotkeys.Click += (_, _) => ShowPage(_pageHotkeys);
        _tabPairing.Click += (_, _) => ShowPage(_pagePairing);
        _tabAbout.Click += (_, _) => ShowPage(_pageAbout);
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

    /// <summary>Reiter wählen (z. B. „Über“ nach einem Klick auf den Update-Hinweis).</summary>
    public void ShowTab(string? tab) => ShowPage(tab switch
    {
        TabPairing => _pagePairing,
        TabAbout => _pageAbout,
        _ => _pageHotkeys,
    });

    private void ShowPage(Panel page)
    {
        _page = page;
        foreach (Panel p in new[] { _pageHotkeys, _pagePairing, _pageAbout })
        {
            p.Visible = ReferenceEquals(p, page);
        }

        _tabHotkeys.Checked = ReferenceEquals(page, _pageHotkeys);
        _tabPairing.Checked = ReferenceEquals(page, _pagePairing);
        _tabAbout.Checked = ReferenceEquals(page, _pageAbout);
        if (IsHandleCreated)
        {
            LayoutContent();
        }
    }

    protected override void OnThemeApplied()
    {
        foreach (Panel page in new[] { _pageHotkeys, _pagePairing, _pageAbout })
        {
            page.BackColor = P.Card;
        }
    }

    protected override void LayoutContent()
    {
        int pad = S(16);
        int width = S(560);
        int inner = width - (2 * pad);
        int y = BarHeight + pad;

        int face = S(28);
        _headFace = new Rectangle(pad, y, face, face);
        _headTitle = new Rectangle(pad + face + S(10), y, inner - face - S(10), face);
        y += face + S(14);

        int x = pad;
        foreach (SparkButton tab in new[] { _tabHotkeys, _tabPairing, _tabAbout })
        {
            Size size = tab.Preferred();
            tab.Bounds = new Rectangle(x, y, size.Width, size.Height);
            x += size.Width + S(6);
        }

        y += _tabHotkeys.Height + S(16);

        int hk = LayoutHotkeys(inner);
        int pr = LayoutPairing(inner);
        int ab = LayoutAbout(inner);
        int pageH = Math.Max(hk, Math.Max(pr, ab));
        foreach (Panel page in new[] { _pageHotkeys, _pagePairing, _pageAbout })
        {
            page.Bounds = new Rectangle(pad, y, inner, pageH);
        }

        y += pageH + S(16);
        Size close = _close.Preferred();
        _close.Bounds = new Rectangle(width - pad - close.Width, y, close.Width, close.Height);
        y += close.Height + pad;
        ClientSize = new Size(width, y);
    }

    private int LayoutHotkeys(int width)
    {
        int y = 0;
        y += _hotkeyIntro.Fit(0, y, width) + S(14);
        int labelW = S(120);
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
            y += Math.Max(noteH, S(4)) + S(10);
        }

        return y;
    }

    private int LayoutPairing(int width)
    {
        int y = 0;
        y += _pairing.Fit(0, y, width) + S(12);
        int x = 0;
        foreach (SparkButton b in new[] { _panel, _repair, _unpair })
        {
            Size size = b.Preferred();
            b.Bounds = new Rectangle(x, y, size.Width, size.Height);
            x += size.Width + S(8);
        }

        y += _panel.Height + S(20);
        y += _partsHeading.Fit(0, y, width) + S(6);
        y += _parts.Fit(0, y, width) + S(8);
        y += _partsHint.Fit(0, y, width) + S(20);
        y += _folderHeading.Fit(0, y, width) + S(6);
        Size pick = _folderPick.Preferred();
        int pathH = _folderPath.Fit(0, y + Math.Max(0, (pick.Height - Draw.TextHeight(_folderPath.Text, _folderPath.Font, width - pick.Width - S(10))) / 2), width - pick.Width - S(10));
        _folderPick.Bounds = new Rectangle(width - pick.Width, y, pick.Width, pick.Height);
        y += Math.Max(pick.Height, pathH) + S(6);
        y += _folderNote.Fit(0, y, width);
        return y;
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
        y += _auto.Fit(0, y, width) + S(18);
        y += _coffeeText.Fit(0, y, width) + S(10);
        Size coffee = _coffee.Preferred();
        _coffee.Bounds = new Rectangle(0, y, coffee.Width, coffee.Height);
        y += coffee.Height;
        return y;
    }

    protected override void PaintContent(Graphics g)
    {
        Face.Draw(g, _headFace, P);
        Draw.Text(g, "Einstellungen", F(11f, FontStyle.Bold), _headTitle, P.Fg);
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

        if (desk is null)
        {
            _parts.Text = config.IsPaired ? "Noch keine Einstellungen vom Spark erhalten." : "–";
        }
        else
        {
            var lines = Parts.All.Select(p => $"{Parts.Label(p)}: "
                + (desk.IsOn(p) ? "an" : desk.Allowed.Count > 0 && !desk.IsAllowed(p) ? "nicht freigegeben" : "aus"));
            _parts.Text = string.Join(Environment.NewLine, lines);
        }

        _folderPath.Text = _host.WissenFolder;
        if (_folderNote.Role != TextRole.Error || desk is null)
        {
            _folderNote.Text = desk?.IsOn(Parts.Folder) == true
                ? "Neue und geänderte Dateien darin gehen nach 10 Sekunden Ruhe ins Wissen (höchstens 50 am Tag)."
                : "Teil ist aus (im Panel unter Ich → Begleiter einschalten).";
        }

        RefreshAbout(config);
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
