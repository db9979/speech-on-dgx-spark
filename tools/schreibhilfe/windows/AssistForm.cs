namespace SparkSchreibhilfe;

/// <summary>
/// Das kleine Fenster am Mauszeiger: Art wählen, Text schicken, Änderungen ansehen, übernehmen.
/// Das Einfügen selbst macht <see cref="TrayContext"/> nach dem Schließen (siehe <see cref="TextToApply"/>).
/// </summary>
internal sealed class AssistForm : Form
{
    private const int MaxTextLength = 20000;
    private const string TranslateArt = "uebersetzen";

    private static readonly Choice[] Arts =
    {
        new("korrigieren", "Korrigieren"),
        new("glaetten", "Glätten"),
        new("kuerzer", "Kürzer"),
        new("freundlicher", "Freundlicher"),
        new("foermlicher", "Förmlicher"),
        new(TranslateArt, "Übersetzen"),
    };

    private static readonly Choice[] Languages =
    {
        new("en", "Englisch"),
        new("de", "Deutsch"),
        new("fr", "Französisch"),
        new("es", "Spanisch"),
        new("it", "Italienisch"),
        new("nl", "Niederländisch"),
    };

    private static readonly Color RemovedColor = Color.FromArgb(0xB9, 0x1C, 0x1C);
    private static readonly Color RemovedBack = Color.FromArgb(0xFE, 0xE2, 0xE2);
    private static readonly Color AddedColor = Color.FromArgb(0x15, 0x80, 0x3D);
    private static readonly Color AddedBack = Color.FromArgb(0xDC, 0xFC, 0xE7);

    private readonly AppConfig _config;
    private readonly Func<IWin32Window?, bool> _repair;

    private readonly ComboBox _art = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 130 };
    private readonly ComboBox _language = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 120 };
    private readonly TextBox _wish = new() { Width = 200, MaxLength = 300, PlaceholderText = "Wunsch (optional)" };
    private readonly Button _run = new() { Text = "Neu", AutoSize = true };
    private readonly TextBox _source = NewTextBox(readOnly: false);
    private readonly RichTextBox _diff = new()
    {
        Dock = DockStyle.Fill,
        ReadOnly = true,
        BackColor = SystemColors.Window,
        DetectUrls = false,
        ScrollBars = RichTextBoxScrollBars.Vertical,
    };

    private readonly TextBox _result = NewTextBox(readOnly: false);
    private readonly Label _status = new() { AutoSize = true, MaximumSize = new Size(500, 0), Anchor = AnchorStyles.Left, Padding = new Padding(0, 4, 0, 0) };
    private readonly ProgressBar _progress = new() { Style = ProgressBarStyle.Marquee, Width = 90, Height = 12, Visible = false, Anchor = AnchorStyles.Left };
    private readonly Button _apply = new() { Text = "Übernehmen", AutoSize = true, Enabled = false };
    private readonly Button _copy = new() { Text = "Kopieren", AutoSize = true, Enabled = false };
    private readonly Button _cancel = new() { Text = "Abbrechen", AutoSize = true };
    private readonly Button _repairButton = new() { Text = "Neu koppeln", AutoSize = true, Visible = false };

    private CancellationTokenSource? _cts;
    private bool _busy;

    // Leerraum am Anfang/Ende der Markierung (z. B. Absatzende in Word) bleibt beim Einfügen erhalten.
    private string _lead = "";
    private string _trail = "";

    public AssistForm(AppConfig config, string text, IntPtr target, Func<IWin32Window?, bool> repair)
    {
        _config = config;
        _repair = repair;
        Target = target;

        BuildLayout();

        _art.Items.AddRange(Arts);
        _language.Items.AddRange(Languages);
        _art.SelectedItem = Arts.FirstOrDefault(a => a.Id == config.Art) ?? Arts[0];
        _language.SelectedItem = Languages.FirstOrDefault(l => l.Id == config.Sprache) ?? Languages[0];
        _language.Visible = SelectedArt == TranslateArt;
        _art.SelectedIndexChanged += (_, _) => _language.Visible = SelectedArt == TranslateArt;

        _source.Text = text;
        _source.PlaceholderText = "Kein markierter Text – Text hier einfügen";

        _run.Click += async (_, _) => await RunAsync();
        _apply.Click += (_, _) => Apply();
        _copy.Click += (_, _) => CopyResult();
        _cancel.Click += (_, _) => Close();
        _repairButton.Click += (_, _) => Repair();
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
            _apply.Text = "Übernehmen (Zwischenablage)";
        }
    }

    /// <summary>Text, der nach dem Schließen eingefügt werden soll (nur bei "Übernehmen").</summary>
    public string? TextToApply { get; private set; }

    /// <summary>Fenster, aus dem der Text stammt und in das eingefügt wird.</summary>
    public IntPtr Target { get; }

    private string SelectedArt => (_art.SelectedItem as Choice)?.Id ?? Arts[0].Id;

    private string SelectedLanguage => (_language.SelectedItem as Choice)?.Id ?? Languages[0].Id;

    private static TextBox NewTextBox(bool readOnly) => new()
    {
        Dock = DockStyle.Fill,
        Multiline = true,
        AcceptsReturn = true,
        ReadOnly = readOnly,
        ScrollBars = ScrollBars.Vertical,
        WordWrap = true,
    };

    private void BuildLayout()
    {
        SuspendLayout();
        AutoScaleDimensions = new SizeF(96F, 96F);
        AutoScaleMode = AutoScaleMode.Dpi;
        Font = SystemFonts.MessageBoxFont ?? Font;
        Text = "Spark Schreibhilfe";
        Icon = AppIcon.Icon;
        TopMost = true;
        ShowInTaskbar = true;
        StartPosition = FormStartPosition.Manual;
        MinimizeBox = false;
        MaximizeBox = false;
        ClientSize = new Size(620, 600);
        MinimumSize = new Size(460, 420);
        Padding = new Padding(10);

        var options = new FlowLayoutPanel { AutoSize = true, Dock = DockStyle.Fill, WrapContents = true, Margin = Padding.Empty };
        options.Controls.Add(_art);
        options.Controls.Add(_language);
        options.Controls.Add(_wish);
        options.Controls.Add(_run);

        var statusRow = new FlowLayoutPanel { AutoSize = true, Dock = DockStyle.Fill, WrapContents = false, Margin = Padding.Empty };
        statusRow.Controls.Add(_progress);
        statusRow.Controls.Add(_status);

        var buttons = new FlowLayoutPanel { AutoSize = true, Dock = DockStyle.Fill, FlowDirection = FlowDirection.RightToLeft, Margin = Padding.Empty };
        buttons.Controls.Add(_cancel);
        buttons.Controls.Add(_copy);
        buttons.Controls.Add(_apply);
        buttons.Controls.Add(_repairButton);

        var root = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1 };
        root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        AddRow(root, options, SizeType.AutoSize);
        AddRow(root, Caption("Text:"), SizeType.AutoSize);
        AddRow(root, _source, SizeType.Percent, 25);
        AddRow(root, Caption("Änderungen:"), SizeType.AutoSize);
        AddRow(root, _diff, SizeType.Percent, 40);
        AddRow(root, Caption("Ergebnis (änderbar):"), SizeType.AutoSize);
        AddRow(root, _result, SizeType.Percent, 35);
        AddRow(root, statusRow, SizeType.AutoSize);
        AddRow(root, buttons, SizeType.AutoSize);
        Controls.Add(root);

        AcceptButton = null; // Enter gehört den Textfeldern; Strg+Enter = Übernehmen.
        CancelButton = _cancel;
        ResumeLayout(performLayout: true);
    }

    private static void AddRow(TableLayoutPanel table, Control control, SizeType sizeType, float size = 0)
    {
        table.RowStyles.Add(new RowStyle(sizeType, size));
        table.Controls.Add(control, 0, table.RowStyles.Count - 1);
    }

    private static Label Caption(string text) =>
        new() { Text = text, AutoSize = true, Padding = new Padding(0, 6, 0, 2) };

    protected override void OnLoad(EventArgs e)
    {
        base.OnLoad(e);
        PlaceNearCursor();

        if (_source.Text.Trim().Length > 0)
        {
            ActiveControl = _result;
            BeginInvoke(new Action(async () => await RunAsync()));
        }
        else
        {
            ActiveControl = _source;
            SetStatus("Text eingeben oder einfügen, dann „Neu“.", error: false);
        }
    }

    /// <summary>Rechts unterhalb des Mauszeigers, aber immer ganz auf dem Bildschirm.</summary>
    private void PlaceNearCursor()
    {
        Point cursor = Cursor.Position;
        Rectangle area = Screen.FromPoint(cursor).WorkingArea;
        int width = Math.Min(Width, area.Width);
        int height = Math.Min(Height, area.Height);
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

        string full = _source.Text;
        string core = full.Trim();
        if (core.Length == 0)
        {
            SetStatus("Bitte zuerst Text eingeben.", error: true);
            _source.Focus();
            return;
        }

        if (core.Length > MaxTextLength)
        {
            SetStatus($"Der Text ist zu lang (höchstens {MaxTextLength:N0} Zeichen).", error: true);
            return;
        }

        string? key = _config.GetKey();
        if (key is null || string.IsNullOrEmpty(_config.Base))
        {
            ShowRepair("Diese Schreibhilfe ist nicht gekoppelt.");
            return;
        }

        int start = full.IndexOf(core, StringComparison.Ordinal);
        _lead = full[..start];
        _trail = full[(start + core.Length)..];

        string art = SelectedArt;
        string? language = art == TranslateArt ? SelectedLanguage : null;
        _config.Art = art;
        _config.Sprache = SelectedLanguage;
        TrySaveConfig();

        SetBusy(true);
        _cts = new CancellationTokenSource();
        try
        {
            AssistResult result = await SparkClient.AssistAsync(_config.Base, key, core, art, language, _wish.Text, _cts.Token);
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

            if (ex.Status == 401)
            {
                ShowRepair(ex.Message);
            }
            else
            {
                SetStatus(ex.Message, error: true);
            }
        }
        catch (Exception ex) when (!IsDisposed)
        {
            // Unerwartetes (z. B. kaputte Antwort) – anzeigen statt das Programm zu beenden.
            SetStatus("Unerwarteter Fehler: " + ex.Message, error: true);
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
        string text = result.Text.Trim();
        _result.Text = text;
        RenderDiff(result.Diff, text);

        string status = result.Diff is null
            ? "Fertig."
            : result.Changes switch
            {
                0 => "Keine Änderungen nötig.",
                1 => "1 Änderung.",
                { } n => $"{n} Änderungen.",
                null => "Fertig.",
            };
        if (result.Ms is { } ms)
        {
            status += $" ({ms / 1000.0:0.0} s)";
        }

        SetStatus(status, error: false);
        _apply.Enabled = true;
        _copy.Enabled = true;
        _apply.Focus();
    }

    /// <summary>Entferntes rot und durchgestrichen, Hinzugefügtes grün; ohne Diff (Übersetzung) nur der Text.</summary>
    private void RenderDiff(IReadOnlyList<DiffPart>? diff, string fallback)
    {
        _diff.Clear();
        Font normal = _diff.Font;
        using var struck = new Font(normal, FontStyle.Strikeout);
        using var italic = new Font(normal, FontStyle.Italic);

        if (diff is null)
        {
            Append("(Bei dieser Art gibt es keine Markierung der Änderungen.)\n\n", italic, SystemColors.GrayText, _diff.BackColor);
            Append(fallback, normal, SystemColors.WindowText, _diff.BackColor);
        }
        else
        {
            foreach (DiffPart part in diff)
            {
                switch (part.Op)
                {
                    case '-':
                        Append(part.Text, struck, RemovedColor, RemovedBack);
                        break;
                    case '+':
                        Append(part.Text, normal, AddedColor, AddedBack);
                        break;
                    default:
                        Append(part.Text, normal, SystemColors.WindowText, _diff.BackColor);
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

    private void ShowRepair(string message)
    {
        SetStatus(message, error: true);
        _repairButton.Visible = true;
    }

    private void Repair()
    {
        if (_repair(this))
        {
            _repairButton.Visible = false;
            SetStatus("Neu gekoppelt.", error: false);
            if (_source.Text.Trim().Length > 0)
            {
                BeginInvoke(new Action(async () => await RunAsync()));
            }
        }
    }

    private void SetBusy(bool busy)
    {
        _busy = busy;
        _run.Enabled = !busy;
        _art.Enabled = !busy;
        _language.Enabled = !busy;
        _progress.Visible = busy;
        if (busy)
        {
            _apply.Enabled = false;
            _copy.Enabled = false;
            _repairButton.Visible = false;
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
        _status.ForeColor = error ? Color.Firebrick : SystemColors.ControlText;
    }

    private void TrySaveConfig()
    {
        try
        {
            _config.Save();
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            // Nur die zuletzt gewählte Art – nicht wichtig genug für eine Meldung.
        }
    }

    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        _cts?.Cancel();
        base.OnFormClosing(e);
    }

    /// <summary>Eintrag für die Auswahllisten: Kennung für den Spark, deutscher Text für die Anzeige.</summary>
    private sealed record Choice(string Id, string Label)
    {
        public override string ToString() => Label;
    }
}
