namespace SparkBegleiter;

/// <summary>
/// „Am PC handeln einstellen“ (Teil "act"): welche Arten hier ohne Rückfrage laufen und welche Kurzbefehle (Skripte)
/// der Spark nennen darf. Nur hier am PC einstellbar: das Panel zeigt es nur an und kann nichts davon ändern.
/// </summary>
internal sealed class ActSettingsForm : ThemedForm
{
    private readonly AppConfig _config;
    private readonly Action _changed;
    private readonly TLabel _autoHeading = new(TextRole.Section, "OHNE RÜCKFRAGE");
    private readonly TLabel _autoNote = new(TextRole.SmallMuted,
        "Eingeschaltete Arten führt der Begleiter sofort aus, wenn du den Spark darum bittest, und zeigt danach einen Hinweis. " +
        "Seiten öffnen, Text tippen und Text zeigen fragen immer.");
    private readonly List<(string Kind, ToggleSwitch Switch)> _autos = new();
    private readonly TLabel _scriptHeading = new(TextRole.Section, "KURZBEFEHLE");
    private readonly TLabel _scriptNote = new(TextRole.SmallMuted,
        "Skripte (.ps1, .bat, .cmd), Verknüpfungen oder Programme, die der Spark auf Zuruf starten darf („Führ am PC den Kurzbefehl Feierabend aus“). " +
        "Der Spark kennt nur den Namen.");
    private readonly ListBox _scripts = new() { IntegralHeight = false, BorderStyle = BorderStyle.None, AccessibleName = "Kurzbefehle" };
    private readonly RoundedHost _scriptsHost;
    private readonly SparkButton _add = new(ButtonKind.Secondary, "Hinzufügen …");
    private readonly SparkButton _remove = new(ButtonKind.Secondary, "Entfernen");
    private readonly SparkButton _close = new(ButtonKind.Primary, "Fertig");

    public ActSettingsForm(AppConfig config, Action changed)
    {
        _config = config;
        _changed = changed;
        _scriptsHost = new RoundedHost(_scripts);
        Text = "Spark-Begleiter – Am PC handeln einstellen";
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        MinimizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        ShowInTaskbar = true;
        KeyPreview = true;

        Controls.AddRange(new Control[] { _autoHeading, _autoNote, _scriptHeading, _scriptNote, _scriptsHost, _add, _remove, _close });
        foreach (string kind in ActRunner.AutoOk)
        {
            var toggle = new ToggleSwitch(ActRunner.KindLabels[kind]) { Checked = config.ActAuto.Contains(kind) };
            toggle.CheckedChanged += (_, _) => SetAuto(kind, toggle.Checked);
            _autos.Add((kind, toggle));
            Controls.Add(toggle);
        }

        FillScripts();
        _add.Click += (_, _) => AddScript();
        _remove.Click += (_, _) => RemoveScript();
        _close.Click += (_, _) => Close();
        AcceptButton = _close;
        CancelButton = _close;
    }

    private void SetAuto(string kind, bool on)
    {
        _config.ActAuto.RemoveAll(k => k == kind || !ActRunner.AutoOk.Contains(k));
        if (on)
        {
            _config.ActAuto.Add(kind);
        }

        _changed();
    }

    private void FillScripts()
    {
        _scripts.Items.Clear();
        foreach (ActScript s in _config.ActScripts)
        {
            _scripts.Items.Add(s.Name + "  –  " + s.Path + (ActDo.IsScript(s.Path) ? "" : "  (fehlt)"));
        }

        _remove.Enabled = _config.ActScripts.Count > 0;
    }

    private void AddScript()
    {
        using var pick = new OpenFileDialog
        {
            Title = "Kurzbefehl wählen",
            Filter = "Skripte und Programme (*.ps1;*.bat;*.cmd;*.lnk;*.exe)|*.ps1;*.bat;*.cmd;*.lnk;*.exe",
            CheckFileExists = true,
            DereferenceLinks = false,
        };
        if (pick.ShowDialog(this) != DialogResult.OK || !ActDo.IsScript(pick.FileName))
        {
            return;
        }

        // Der Name ist, was man sagt: der Dateiname ohne Endung, nur Zeichen, die das Panel annimmt.
        string name = new string(Path.GetFileNameWithoutExtension(pick.FileName)
            .Where(c => !char.IsControl(c) && c is not ('"' or '\'' or '`' or '/' or '\\' or '<' or '>' or '|')).ToArray()).Trim();
        if (name.Length == 0)
        {
            return;
        }

        name = name.Length > 40 ? name[..40].Trim() : name;
        if (_config.ActScripts.Count >= 30 || _config.ActScripts.Any(x => string.Equals(x.Name, name, StringComparison.OrdinalIgnoreCase)))
        {
            MessageBox.Show(this, "Diesen Namen gibt es schon (oder es sind schon 30 Kurzbefehle).", Text, MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }

        _config.ActScripts.Add(new ActScript { Name = name, Path = pick.FileName });
        FillScripts();
        _changed();
    }

    private void RemoveScript()
    {
        int i = _scripts.SelectedIndex;
        if (i < 0 || i >= _config.ActScripts.Count)
        {
            return;
        }

        _config.ActScripts.RemoveAt(i);
        FillScripts();
        _changed();
    }

    protected override void OnThemeApplied()
    {
        _scripts.BackColor = P.Card;
        _scripts.ForeColor = P.Fg;
        _scripts.Font = F(9.5f);
    }

    protected override void LayoutContent()
    {
        int pad = S(18);
        int w = S(480);
        int inner = w - (2 * pad);
        int y = pad;
        y += _autoHeading.Fit(pad, y, inner) + S(4);
        y += _autoNote.Fit(pad, y, inner) + S(10);
        foreach ((_, ToggleSwitch t) in _autos)
        {
            y += t.Fit(pad, y, inner) + S(6);
        }

        y += S(12);
        y += _scriptHeading.Fit(pad, y, inner) + S(4);
        y += _scriptNote.Fit(pad, y, inner) + S(8);
        _scriptsHost.Bounds = new Rectangle(pad, y, inner, S(110));
        y += S(110) + S(8);
        Size add = _add.Preferred();
        Size remove = _remove.Preferred();
        _add.Bounds = new Rectangle(pad, y, add.Width, add.Height);
        _remove.Bounds = new Rectangle(_add.Right + S(8), y, remove.Width, remove.Height);
        y += add.Height + S(16);
        Size close = _close.Preferred();
        _close.Bounds = new Rectangle(w - pad - close.Width, y, close.Width, close.Height);
        y += close.Height + pad;
        ClientSize = new Size(w, y);
    }
}
