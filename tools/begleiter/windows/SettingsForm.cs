namespace SparkBegleiter;

/// <summary>Was das Einstellungsfenster vom Programm braucht (umgesetzt von <see cref="TrayContext"/>).</summary>
internal interface IBegleiterHost
{
    AppConfig Config { get; }

    DeskConfig? Desk { get; }

    /// <summary>Kürzel ändern. <c>null</c> = übernommen, sonst ein deutscher Hinweis (ungültig, doppelt, belegt).</summary>
    string? ChangeHotkey(string part, Hotkey hotkey);

    /// <summary>Alle Kürzel vorübergehend freigeben, solange ein neues aufgenommen wird.</summary>
    void SuspendHotkeys(bool suspend);

    /// <summary>Teile, deren Kürzel beim letzten Registrieren belegt war.</summary>
    IReadOnlyCollection<string> HotkeyConflicts { get; }

    void OpenPanel();

    bool Pair(IWin32Window? owner);

    void Unpair(IWin32Window? owner);

    /// <summary>Kopplung, Einstellungen vom Spark oder Zustand haben sich geändert.</summary>
    event EventHandler? Changed;
}

/// <summary>
/// Lokale Einstellungen: Tastenkürzel je Teil, Panel öffnen, Neu koppeln, Entkoppeln.
/// Welche Teile an sind, wird nur angezeigt – das legt das Panel fest (Ich → Begleiter).
/// </summary>
internal sealed class SettingsForm : Form
{
    private readonly IBegleiterHost _host;
    private readonly Label _pairing = new() { AutoSize = true, MaximumSize = new Size(520, 0), Padding = new Padding(0, 0, 0, 6) };
    private readonly Button _panel = new() { Text = "Panel öffnen", AutoSize = true };
    private readonly Button _repair = new() { Text = "Neu koppeln …", AutoSize = true };
    private readonly Button _unpair = new() { Text = "Entkoppeln …", AutoSize = true };
    private readonly Label _parts = new() { AutoSize = true, MaximumSize = new Size(520, 0) };
    private readonly Dictionary<string, (HotkeyBox Box, Label Note)> _rows = new();

    public SettingsForm(IBegleiterHost host)
    {
        _host = host;

        SuspendLayout();
        AutoScaleDimensions = new SizeF(96F, 96F);
        AutoScaleMode = AutoScaleMode.Dpi;
        Font = SystemFonts.MessageBoxFont ?? Font;
        Text = "Spark-Begleiter – Einstellungen";
        Icon = AppIcon.Icon;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = false;
        ShowInTaskbar = true;
        StartPosition = FormStartPosition.CenterScreen;
        AutoSize = true;
        AutoSizeMode = AutoSizeMode.GrowAndShrink;
        Padding = new Padding(12);

        var root = new TableLayoutPanel { ColumnCount = 1, AutoSize = true, Dock = DockStyle.Fill };

        // Kopplung
        root.Controls.Add(Heading("Kopplung"));
        root.Controls.Add(_pairing);
        var pairButtons = new FlowLayoutPanel { AutoSize = true, WrapContents = false, Margin = Padding.Empty };
        pairButtons.Controls.Add(_panel);
        pairButtons.Controls.Add(_repair);
        pairButtons.Controls.Add(_unpair);
        root.Controls.Add(pairButtons);

        // Tastenkürzel
        root.Controls.Add(Heading("Tastenkürzel"));
        root.Controls.Add(new Label
        {
            AutoSize = true,
            MaximumSize = new Size(520, 0),
            Text = "In ein Feld klicken und die neue Kombination drücken (mit Strg oder Alt, z. B. Strg+Alt+S).",
        });
        var grid = new TableLayoutPanel { ColumnCount = 4, AutoSize = true, Margin = new Padding(0, 4, 0, 0) };
        grid.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        grid.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        grid.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        grid.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        foreach (string part in Parts.WithHotkey)
        {
            var box = new HotkeyBox { Width = 170 };
            var reset = new Button { Text = "Standard", AutoSize = true };
            var note = new Label { AutoSize = true, MaximumSize = new Size(220, 0), Anchor = AnchorStyles.Left };
            grid.Controls.Add(new Label { Text = Parts.Label(part) + ":", AutoSize = true, Anchor = AnchorStyles.Left });
            grid.Controls.Add(box);
            grid.Controls.Add(reset);
            grid.Controls.Add(note);
            _rows[part] = (box, note);

            string p = part;
            box.Enter += (_, _) => _host.SuspendHotkeys(true);
            box.Leave += (_, _) => _host.SuspendHotkeys(false);
            box.Captured += (_, hotkey) => Change(p, hotkey);
            box.Rejected += (_, text) => ShowNote(p, text, error: true);
            reset.Click += (_, _) => Change(p, Hotkey.DefaultFor(p));
        }

        root.Controls.Add(grid);

        // Teile
        root.Controls.Add(Heading("Teile"));
        root.Controls.Add(_parts);

        var close = new Button { Text = "Schließen", AutoSize = true, DialogResult = DialogResult.OK };
        var bottom = new FlowLayoutPanel { FlowDirection = FlowDirection.RightToLeft, AutoSize = true, Dock = DockStyle.Fill, Padding = new Padding(0, 10, 0, 0) };
        bottom.Controls.Add(close);
        root.Controls.Add(bottom);

        Controls.Add(root);
        CancelButton = close;
        ResumeLayout(performLayout: true);

        _panel.Click += (_, _) => _host.OpenPanel();
        _repair.Click += (_, _) => _host.Pair(this);
        _unpair.Click += (_, _) => _host.Unpair(this);
        close.Click += (_, _) => Close();

        _host.Changed += OnHostChanged;
        RefreshAll();
    }

    private static Label Heading(string text) => new()
    {
        Text = text,
        AutoSize = true,
        Font = new Font(SystemFonts.MessageBoxFont ?? Control.DefaultFont, FontStyle.Bold),
        Padding = new Padding(0, 10, 0, 4),
    };

    private void OnHostChanged(object? sender, EventArgs e)
    {
        if (!IsDisposed)
        {
            RefreshAll();
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
            _pairing.Text = "Nicht gekoppelt. Im Panel unter Ich → Begleiter „Gerät koppeln“ wählen und hier „Neu koppeln“.";
        }

        _panel.Enabled = !string.IsNullOrEmpty(config.Base);
        _unpair.Enabled = config.IsPaired;
        _repair.Text = config.IsPaired ? "Neu koppeln …" : "Koppeln …";

        foreach (string part in Parts.WithHotkey)
        {
            var (box, _) = _rows[part];
            box.Hotkey = config.GetHotkey(part);
            if (_host.HotkeyConflicts.Contains(part))
            {
                ShowNote(part, $"{box.Hotkey} ist schon von einem anderen Programm belegt.", error: true);
            }
            else if (desk is null || !desk.IsOn(part))
            {
                ShowNote(part, "Teil ist aus", error: false);
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
            _parts.Text = string.Join(Environment.NewLine, lines)
                          + Environment.NewLine + Environment.NewLine
                          + "Ein- und ausschalten im Panel unter Ich → Begleiter.";
        }
    }

    private void Change(string part, Hotkey hotkey)
    {
        string? error = _host.ChangeHotkey(part, hotkey);
        _rows[part].Box.Hotkey = _host.Config.GetHotkey(part);
        if (error is null)
        {
            ShowNote(part, "Gespeichert.", error: false);
        }
        else
        {
            ShowNote(part, error, error: true);
        }
    }

    private void ShowNote(string part, string text, bool error)
    {
        Label note = _rows[part].Note;
        note.Text = text;
        note.ForeColor = error ? Color.Firebrick : SystemColors.GrayText;
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
        if (ActiveControl is HotkeyBox)
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
            BackColor = SystemColors.Window;
            ShortcutsEnabled = false;
            TextAlign = HorizontalAlignment.Center;
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
