using System.Globalization;

namespace SparkBegleiter;

/// <summary>
/// Schreibhilfe mit Vorschau (Entwurf A): Farbverlauf, Gesicht mit Titel und Quellprogramm, Arten als Chips
/// (gewählt = Akzent), Textfeld mit Änderungen (entfernt rot durchgestrichen, neu grün), Zähler,
/// „Kopieren“ und „Übernehmen“. Voreinstellungen (Art, Sprache, Wunsch, angebotene Arten) kommen aus dem
/// Panel. Das Einfügen selbst macht <see cref="TrayContext"/> nach dem Schließen (siehe <see cref="TextToApply"/>).
/// </summary>
internal sealed class AssistForm : ThemedForm
{
    private const int MaxTextLength = 20000;

    private enum View
    {
        Diff,
        Result,
        Source,
    }

    private readonly AppConfig _config;
    private readonly Action<SparkException> _report;
    private readonly ArtInfo[] _arts;
    private readonly LangInfo[] _languages;
    private readonly string? _sourceApp;
    private readonly string? _appCategory;

    private readonly List<DictateMic> _mics = new();
    private readonly List<SparkButton> _artChips = new();
    private readonly List<SparkButton> _langChips = new();
    private readonly TLabel _langLabel = new(TextRole.SmallMuted, "Sprache:");
    private readonly TextBox _wish = new() { MaxLength = 300, PlaceholderText = "Wunsch (optional), z. B. „etwas lockerer“", AccessibleName = "Wunsch" };
    private readonly RoundedHost _wishHost;
    private readonly SparkButton _run = new(ButtonKind.Secondary, "Neu");

    private readonly SparkButton _viewDiff = new(ButtonKind.Chip, "Änderungen") { FontSize = 9f };
    private readonly SparkButton _viewResult = new(ButtonKind.Chip, "Ergebnis bearbeiten") { FontSize = 9f };
    private readonly SparkButton _viewSource = new(ButtonKind.Chip, "Ausgangstext") { FontSize = 9f };

    private readonly TextBox _source = NewTextBox("Ausgangstext");
    private readonly TextBox _result = NewTextBox("Ergebnis");
    private readonly RichTextBox _diff = new()
    {
        ReadOnly = true,
        DetectUrls = false,
        ScrollBars = RichTextBoxScrollBars.Vertical,
        AccessibleName = "Änderungen",
    };

    private readonly RoundedHost _sourceHost;
    private readonly RoundedHost _resultHost;
    private readonly RoundedHost _diffHost;

    private readonly TLabel _status = new(TextRole.SmallMuted);
    private readonly SparkButton _apply = new(ButtonKind.Primary, "Übernehmen") { Enabled = false };
    private readonly SparkButton _copy = new(ButtonKind.Secondary, "Kopieren") { Enabled = false };

    private string _art;
    private string _language;
    private View _view = View.Source;
    private AssistResult? _last;
    private CancellationTokenSource? _cts;
    private bool _busy;

    private Rectangle _face;
    private Rectangle _title;
    private Rectangle _from;

    // Leerraum am Anfang/Ende der Markierung (z. B. Absatzende in Word) bleibt beim Einfügen erhalten.
    private string _lead = "";
    private string _trail = "";

    /// <param name="appCategory">Teil "context": Art des Quellprogramms (z. B. "outlook"), sonst <c>null</c>.</param>
    /// <param name="dictation">Einsprechen in Wunsch, Ausgangstext und Ergebnis (Teil „Diktieren“), oder <c>null</c>.</param>
    public AssistForm(AppConfig config, DeskConfig desk, string text, IntPtr target, string? sourceApp, Action<SparkException> report, string? appCategory = null, Dictation? dictation = null)
    {
        _config = config;
        _appCategory = appCategory;
        _report = report;
        _sourceApp = sourceApp;
        _arts = desk.OfferedArts().ToArray();
        _languages = desk.Languages().ToArray();
        _art = (_arts.FirstOrDefault(a => a.Id == desk.WriteArt) ?? _arts[0]).Id;
        _language = (_languages.FirstOrDefault(l => l.Id == desk.WriteSprache) ?? _languages[0]).Id;
        Target = target;

        _wishHost = new RoundedHost(_wish);
        _sourceHost = new RoundedHost(_source);
        _resultHost = new RoundedHost(_result);
        _diffHost = new RoundedHost(_diff);
        if (dictation is not null)
        {
            foreach (RoundedHost host in new[] { _wishHost, _sourceHost, _resultHost })
            {
                _mics.Add(new DictateMic(host, dictation, SetStatus));
            }
        }

        Text = "Spark-Begleiter – Text verbessern";
        TopMost = true;
        ShowInTaskbar = true;
        StartPosition = FormStartPosition.Manual;
        MinimizeBox = false;
        MaximizeBox = false;
        KeyPreview = true;

        int tab = 0;
        foreach (ArtInfo art in _arts)
        {
            var chip = new SparkButton(ButtonKind.Chip, art.Label) { TabIndex = tab++ };
            string id = art.Id;
            chip.Click += (_, _) => SelectArt(id, run: _last is not null || _source.Text.Trim().Length > 0);
            _artChips.Add(chip);
            Controls.Add(chip);
        }

        Controls.Add(_langLabel);
        foreach (LangInfo lang in _languages)
        {
            var chip = new SparkButton(ButtonKind.Chip, lang.Label) { TabIndex = tab++, FontSize = 9f };
            string id = lang.Id;
            chip.Click += (_, _) => SelectLanguage(id);
            _langChips.Add(chip);
            Controls.Add(chip);
        }

        _wishHost.TabIndex = tab++;
        _run.TabIndex = tab++;
        _viewDiff.TabIndex = tab++;
        _viewResult.TabIndex = tab++;
        _viewSource.TabIndex = tab++;
        _sourceHost.TabIndex = tab;
        _resultHost.TabIndex = tab;
        _diffHost.TabIndex = tab++;
        _copy.TabIndex = tab++;
        _apply.TabIndex = tab;

        Controls.AddRange(new Control[] { _wishHost, _run, _viewDiff, _viewResult, _viewSource, _sourceHost, _resultHost, _diffHost, _status, _copy, _apply });

        _wish.Text = desk.WriteWunsch;
        _source.Text = text;
        _source.PlaceholderText = "Kein markierter Text – Text hier einfügen, dann „Neu“";

        _run.Click += async (_, _) => await RunAsync();
        _apply.Click += (_, _) => Apply();
        _copy.Click += (_, _) => CopyResult();
        _viewDiff.Click += (_, _) => SetView(View.Diff);
        _viewResult.Click += (_, _) => SetView(View.Result);
        _viewSource.Click += (_, _) => SetView(View.Source);
        _wish.KeyDown += async (_, e) =>
        {
            if (e.KeyCode == Keys.Enter)
            {
                e.SuppressKeyPress = true;
                await RunAsync();
            }
        };

        if (Target == IntPtr.Zero)
        {
            // Aus dem Menü geöffnet: es gibt kein Fenster zum Einfügen.
            _apply.Text = "In die Zwischenablage";
            _copy.Visible = false;
        }

        UpdateChips();
        SetView(View.Source);
        PlaceNearCursor();
    }

    /// <summary>Text, der nach dem Schließen eingefügt werden soll (nur bei "Übernehmen").</summary>
    public string? TextToApply { get; private set; }

    /// <summary>Fenster, aus dem der Text stammt und in das eingefügt wird.</summary>
    public IntPtr Target { get; }

    private static TextBox NewTextBox(string name) => new()
    {
        Multiline = true,
        AcceptsReturn = true,
        ScrollBars = ScrollBars.Vertical,
        WordWrap = true,
        AccessibleName = name,
    };

    private bool Translating => _art == DeskConfig.TranslateArt;

    private void SelectArt(string id, bool run)
    {
        if (_busy)
        {
            return;
        }

        _art = id;
        UpdateChips();
        LayoutContent();
        Invalidate();
        if (run)
        {
            _ = RunAsync();
        }
    }

    /// <summary>Mit dieser Art beginnen (Knopf „Übersetzen“ in Outlook); mit Text läuft sie gleich los.</summary>
    public void StartWith(string art)
    {
        if (_arts.Any(a => a.Id == art))
        {
            SelectArt(art, run: _source.Text.Trim().Length > 0);
        }
    }

    private void SelectLanguage(string id)
    {
        if (_busy)
        {
            return;
        }

        _language = id;
        UpdateChips();
        if (_last is not null || _source.Text.Trim().Length > 0)
        {
            _ = RunAsync();
        }
    }

    private void UpdateChips()
    {
        for (int i = 0; i < _arts.Length; i++)
        {
            _artChips[i].Checked = _arts[i].Id == _art;
            _artChips[i].Enabled = !_busy;
        }

        for (int i = 0; i < _languages.Length; i++)
        {
            _langChips[i].Checked = _languages[i].Id == _language;
            _langChips[i].Enabled = !_busy;
            _langChips[i].Visible = Translating;
        }

        _langLabel.Visible = Translating;
        _viewDiff.Checked = _view == View.Diff;
        _viewResult.Checked = _view == View.Result;
        _viewSource.Checked = _view == View.Source;
        bool hasResult = _last is not null;
        _viewDiff.Visible = hasResult;
        _viewResult.Visible = hasResult;
        _viewSource.Visible = hasResult;
    }

    private void SetView(View view)
    {
        _view = view;
        _sourceHost.Visible = view == View.Source;
        _resultHost.Visible = view == View.Result;
        _diffHost.Visible = view == View.Diff;
        UpdateChips();
        if (IsHandleCreated)
        {
            (view switch { View.Result => (Control)_result, View.Source => _source, _ => _diff }).Focus();
        }
    }

    protected override void OnThemeApplied()
    {
        _mics.ForEach(m => m.Refresh());
        if (_last is not null)
        {
            RenderDiff(_last.Diff, _last.Text.Trim());
        }
    }

    protected override void LayoutContent()
    {
        int pad = S(14);
        int w = ClientSize.Width;
        int h = ClientSize.Height;
        int inner = w - (2 * pad);
        int y = BarHeight + pad;

        int face = S(28);
        _face = new Rectangle(pad, y, face, face);
        Size title = Draw.Measure("Text verbessern", F(10.5f, FontStyle.Bold));
        _title = new Rectangle(pad + face + S(8), y, title.Width + S(4), face);
        _from = new Rectangle(_title.Right + S(8), y, Math.Max(0, w - pad - _title.Right - S(8)), face);
        y += face + S(12);

        y = Flow(_artChips, pad, y, inner) + S(8);
        if (Translating)
        {
            Size label = Draw.Measure(_langLabel.Text, _langLabel.Font);
            int chipH = _langChips.Count > 0 ? _langChips[0].Preferred().Height : S(28);
            _langLabel.Bounds = new Rectangle(pad, y + ((chipH - label.Height) / 2), label.Width + S(2), label.Height);
            y = Flow(_langChips, pad + label.Width + S(8), y, inner - label.Width - S(8)) + S(8);
        }

        Size run = _run.Preferred();
        int rowH = Math.Max(S(36), run.Height);
        _wishHost.Bounds = new Rectangle(pad, y, inner - run.Width - S(8), rowH);
        _run.Bounds = new Rectangle(w - pad - run.Width, y + ((rowH - run.Height) / 2), run.Width, run.Height);
        y += rowH + S(10);

        if (_last is not null)
        {
            int x = pad;
            foreach (SparkButton chip in new[] { _viewDiff, _viewResult, _viewSource })
            {
                Size size = chip.Preferred();
                size.Height = S(26);
                chip.Bounds = new Rectangle(x, y, size.Width, size.Height);
                x += size.Width + S(6);
            }

            y += S(26) + S(8);
        }

        // Fuß: Zustand links, Knöpfe rechts.
        Size apply = _apply.Preferred();
        Size copy = _copy.Preferred();
        int footY = h - pad - apply.Height;
        _apply.Bounds = new Rectangle(w - pad - apply.Width, footY, apply.Width, apply.Height);
        int left = _apply.Left - S(8);
        if (Target != IntPtr.Zero)
        {
            _copy.Bounds = new Rectangle(left - copy.Width, footY, copy.Width, copy.Height);
            left = _copy.Left - S(8);
        }

        int statusW = Math.Max(S(40), left - S(4) - pad);
        int statusH = Math.Min(Draw.TextHeight(_status.Text, _status.Font, statusW), apply.Height + S(8));
        _status.Bounds = new Rectangle(pad, footY + ((apply.Height - statusH) / 2), statusW, statusH);
        _status.Visible = _status.Text.Length > 0;

        var area = new Rectangle(pad, y, inner, Math.Max(S(60), footY - S(12) - y));
        _sourceHost.Bounds = area;
        _resultHost.Bounds = area;
        _diffHost.Bounds = area;
    }

    /// <summary>Chips nebeneinander, bei Bedarf umbrechen; gibt das untere Ende zurück.</summary>
    private int Flow(List<SparkButton> chips, int left, int top, int width)
    {
        int x = left;
        int y = top;
        int rowH = 0;
        foreach (SparkButton chip in chips)
        {
            Size size = chip.Preferred();
            if (x > left && x + size.Width > left + width)
            {
                x = left;
                y += rowH + S(6);
                rowH = 0;
            }

            chip.Bounds = new Rectangle(x, y, Math.Min(size.Width, width), size.Height);
            x += size.Width + S(6);
            rowH = Math.Max(rowH, size.Height);
        }

        return y + rowH;
    }

    protected override void PaintContent(Graphics g)
    {
        Face.Draw(g, _face, P);
        Draw.Text(g, "Text verbessern", F(10.5f, FontStyle.Bold), _title, P.Fg);
        if (!string.IsNullOrEmpty(_sourceApp))
        {
            Draw.Text(g, "aus " + _sourceApp, F(8.5f), _from, P.Muted, Draw.Line | TextFormatFlags.Right);
        }
    }

    protected override void OnLoad(EventArgs e)
    {
        base.OnLoad(e);

        if (_source.Text.Trim().Length > 0)
        {
            ActiveControl = _source;
            BeginInvoke(new Action(async () => await RunAsync()));
        }
        else
        {
            ActiveControl = _source;
            SetStatus("Text eingeben oder einfügen, dann „Neu“.", error: false);
        }
    }

    protected override void OnDpiChanged(DpiChangedEventArgs e)
    {
        base.OnDpiChanged(e);
        MinimumSize = new Size(S(460), S(420));
    }

    /// <summary>Rechts unterhalb des Mauszeigers, aber immer ganz auf dem Bildschirm.</summary>
    private void PlaceNearCursor()
    {
        Point cursor = Cursor.Position;
        Rectangle area = Screen.FromPoint(cursor).WorkingArea;
        int dpi = Dwm.DpiAt(cursor);
        int width = Math.Min(Draw.Scale(620, dpi), area.Width);
        int height = Math.Min(Draw.Scale(540, dpi), area.Height);
        MinimumSize = new Size(Math.Min(Draw.Scale(460, dpi), width), Math.Min(Draw.Scale(420, dpi), height));
        int x = Math.Clamp(cursor.X + 16, area.Left, area.Right - width);
        int y = Math.Clamp(cursor.Y + 16, area.Top, area.Bottom - height);
        Bounds = new Rectangle(x, y, width, height);
    }

    protected override bool ProcessCmdKey(ref Message msg, Keys keyData)
    {
        switch (keyData)
        {
            case Keys.Escape:
                Close();
                return true;
            case Keys.Control | Keys.Enter:
                if (_apply.Enabled)
                {
                    Apply();
                }

                return true;
            default:
                return base.ProcessCmdKey(ref msg, keyData);
        }
    }

    /// <summary>Schickt den Text an den Spark und zeigt Ergebnis und Änderungen.</summary>
    private async Task RunAsync()
    {
        if (_busy)
        {
            return;
        }

        if (_mics.Exists(m => m.Busy))
        {
            SetStatus("Bitte zuerst die Aufnahme beenden (■).", error: true);
            return;
        }

        string full = _source.Text;
        string core = full.Trim();
        if (core.Length == 0)
        {
            SetView(View.Source);
            SetStatus("Bitte zuerst Text eingeben.", error: true);
            return;
        }

        if (core.Length > MaxTextLength)
        {
            SetStatus(string.Create(CultureInfo.GetCultureInfo("de-DE"), $"Der Text ist zu lang (höchstens {MaxTextLength:N0} Zeichen)."), error: true);
            return;
        }

        string? key = _config.GetKey();
        if (key is null || string.IsNullOrEmpty(_config.Base))
        {
            SetStatus("Der Begleiter ist nicht gekoppelt (Einstellungen → Neu koppeln).", error: true);
            return;
        }

        int start = full.IndexOf(core, StringComparison.Ordinal);
        _lead = full[..start];
        _trail = full[(start + core.Length)..];

        string art = _art;
        string? language = Translating ? _language : null;

        SetBusy(true);
        _cts = new CancellationTokenSource();
        try
        {
            AssistResult result = await SparkClient.AssistAsync(_config.Base, key, core, art, language, _wish.Text, _cts.Token, _appCategory);
            if (IsDisposed)
            {
                return;
            }

            ShowResult(result);
        }
        catch (OperationCanceledException)
        {
            // Fenster wurde geschlossen.
        }
        catch (SparkException ex)
        {
            if (IsDisposed)
            {
                return;
            }

            SetStatus(ex.Message, error: true);
            _report(ex);
        }
        finally
        {
            _cts?.Dispose();
            _cts = null;
            if (!IsDisposed)
            {
                SetBusy(false);
            }
        }
    }

    private void ShowResult(AssistResult result)
    {
        _last = result;
        string text = result.Text.Trim();
        _result.Text = text;
        RenderDiff(result.Diff, text);

        CultureInfo de = CultureInfo.GetCultureInfo("de-DE");
        string status = result.Diff is null
            ? "Fertig"
            : result.Changes switch
            {
                0 => "Keine Änderungen nötig",
                1 => "1 Änderung",
                { } n => string.Create(de, $"{n} Änderungen"),
                null => "Fertig",
            };
        if (result.Ms is { } ms)
        {
            status += string.Create(de, $" · {ms / 1000.0:0.0} s");
        }

        SetStatus(status, error: false);
        _apply.Enabled = true;
        _copy.Enabled = true;
        SetView(View.Diff);
        LayoutContent();
        Invalidate();
        _apply.Focus();
    }

    /// <summary>Entferntes rot und durchgestrichen, Hinzugefügtes grün; ohne Diff (Übersetzung) nur der Text.</summary>
    private void RenderDiff(IReadOnlyList<DiffPart>? diff, string fallback)
    {
        Palette p = P;
        _diff.Clear();
        _diff.BackColor = p.Soft;
        Font normal = Theme.UiFont(DeviceDpi, 10f);
        _diff.Font = normal;
        Font struck = Theme.UiFont(DeviceDpi, 10f, FontStyle.Strikeout);
        Font added = p.HighContrast ? Theme.UiFont(DeviceDpi, 10f, FontStyle.Underline) : normal;
        Font italic = Theme.UiFont(DeviceDpi, 9f, FontStyle.Italic);

        if (diff is null)
        {
            Append("(Bei dieser Art gibt es keine Markierung der Änderungen.)\n\n", italic, p.Muted, p.Soft);
            Append(fallback, normal, p.Fg, p.Soft);
        }
        else
        {
            foreach (DiffPart part in diff)
            {
                switch (part.Op)
                {
                    case '-':
                        Append(part.Text, struck, p.DelFg, p.DelBg);
                        break;
                    case '+':
                        Append(part.Text, added, p.InsFg, p.InsBg);
                        break;
                    default:
                        Append(part.Text, normal, p.Fg, p.Soft);
                        break;
                }
            }
        }

        _diff.SelectionStart = 0;
        _diff.SelectionLength = 0;
        _diff.ScrollToCaret();
    }

    private void Append(string text, Font font, Color color, Color back)
    {
        _diff.SelectionStart = _diff.TextLength;
        _diff.SelectionLength = 0;
        _diff.SelectionFont = font;
        _diff.SelectionColor = color;
        _diff.SelectionBackColor = back;
        _diff.AppendText(text);
    }

    private void Apply()
    {
        string text = _result.Text;
        if (text.Trim().Length == 0)
        {
            SetStatus("Das Ergebnis ist leer.", error: true);
            return;
        }

        if (Target == IntPtr.Zero)
        {
            CopyResult();
            return;
        }

        TextToApply = _lead + text + _trail;
        Close();
    }

    private void CopyResult()
    {
        if (ClipboardHelper.TrySetText(_result.Text, keepOutOfHistory: false))
        {
            Close();
        }
        else
        {
            SetStatus("Die Zwischenablage ist gerade gesperrt. Bitte noch einmal versuchen.", error: true);
        }
    }

    private void SetBusy(bool busy)
    {
        _busy = busy;
        _run.Enabled = !busy;
        UpdateChips();
        if (busy)
        {
            _apply.Enabled = false;
            _copy.Enabled = false;
            SetStatus("Der Spark schreibt …", error: false);
        }
        else if (_result.Text.Length > 0)
        {
            _apply.Enabled = true;
            _copy.Enabled = true;
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

    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        _cts?.Cancel();
        _mics.ForEach(m => m.Dispose());
        base.OnFormClosing(e);
    }
}
