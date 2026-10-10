namespace SparkSchreibhilfe;

/// <summary>
/// "Einrichten …": Einrichtungszeile aus dem Panel (Ich → Schreibhilfe → „Programm koppeln“)
/// einfügen, Gerätename wählen, koppeln. Speichert Adresse und DPAPI-geschützten Schlüssel.
/// </summary>
internal sealed class SetupForm : Form
{
    private readonly AppConfig _config;
    private readonly TextBox _line = new() { Dock = DockStyle.Fill };
    private readonly TextBox _code = new() { Width = 140, CharacterCasing = CharacterCasing.Upper, PlaceholderText = "XXXX-XXXX" };
    private readonly TextBox _name = new() { Dock = DockStyle.Fill, MaxLength = 40 };
    private readonly Label _hint = new() { AutoSize = true, Dock = DockStyle.Fill, Padding = new Padding(0, 4, 0, 4) };
    private readonly Button _pair = new() { Text = "Koppeln", AutoSize = true };
    private readonly Button _cancel = new() { Text = "Abbrechen", AutoSize = true, DialogResult = DialogResult.Cancel };

    private CancellationTokenSource? _cts;

    public SetupForm(AppConfig config)
    {
        _config = config;

        SuspendLayout();
        AutoScaleDimensions = new SizeF(96F, 96F);
        AutoScaleMode = AutoScaleMode.Dpi;
        Font = SystemFonts.MessageBoxFont ?? Font;
        Text = "Spark Schreibhilfe einrichten";
        Icon = AppIcon.Icon;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = false;
        ShowInTaskbar = true;
        TopMost = true;
        StartPosition = FormStartPosition.CenterScreen;
        AutoSize = true;
        AutoSizeMode = AutoSizeMode.GrowAndShrink;
        Padding = new Padding(12);

        var intro = new Label
        {
            AutoSize = true,
            MaximumSize = new Size(520, 0),
            Text = "Im Panel des Spark: Ich → Schreibhilfe → „Programm koppeln“. "
                   + "Die angezeigte Einrichtungszeile hier einfügen (der Code gilt 10 Minuten).",
            Padding = new Padding(0, 0, 0, 8),
        };

        var grid = new TableLayoutPanel { ColumnCount = 2, AutoSize = true, Dock = DockStyle.Fill, Width = 520 };
        grid.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        grid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        AddRow(grid, "Einrichtungszeile:", _line);
        AddRow(grid, "Code (falls nicht in der Zeile):", _code);
        AddRow(grid, "Gerätename:", _name);

        var buttons = new FlowLayoutPanel
        {
            FlowDirection = FlowDirection.RightToLeft,
            AutoSize = true,
            Dock = DockStyle.Fill,
            Padding = new Padding(0, 8, 0, 0),
        };
        buttons.Controls.Add(_cancel);
        buttons.Controls.Add(_pair);

        var root = new TableLayoutPanel { ColumnCount = 1, AutoSize = true, Dock = DockStyle.Fill };
        root.Controls.Add(intro);
        root.Controls.Add(grid);
        root.Controls.Add(_hint);
        root.Controls.Add(buttons);
        Controls.Add(root);

        AcceptButton = _pair;
        CancelButton = _cancel;
        ResumeLayout(performLayout: true);

        _line.PlaceholderText = "https://…#schreib=XXXX-XXXX";
        _line.Text = config.Base ?? "";
        _name.Text = config.Device ?? SparkAddress.SanitizeDeviceName(Environment.MachineName);
        _line.TextChanged += (_, _) => UpdateHint();
        _pair.Click += async (_, _) => await PairAsync();
        UpdateHint();
    }

    private static void AddRow(TableLayoutPanel grid, string label, Control field)
    {
        grid.Controls.Add(new Label { Text = label, AutoSize = true, Anchor = AnchorStyles.Left, Padding = new Padding(0, 6, 8, 0) });
        grid.Controls.Add(field);
    }

    /// <summary>Hinweis unter den Feldern: Warnung bei http, sonst leer.</summary>
    private void UpdateHint()
    {
        if (_line.Text.Trim().Length > 0 && SparkAddress.TryParse(_line.Text, out var parsed, out _) && parsed.Insecure)
        {
            ShowHint("Achtung: unverschlüsselte Verbindung (http). Nur im eigenen Heimnetz verwenden.", warning: true);
        }
        else
        {
            ShowHint("", warning: false);
        }
    }

    private void ShowHint(string text, bool warning, bool error = false)
    {
        _hint.Text = text;
        _hint.ForeColor = error ? Color.Firebrick : warning ? Color.DarkOrange : SystemColors.ControlText;
    }

    private async Task PairAsync()
    {
        if (!SparkAddress.TryParse(_line.Text, out var parsed, out string error))
        {
            ShowHint(error, warning: false, error: true);
            return;
        }

        string code = _code.Text.Trim().Length > 0 ? _code.Text.Trim() : parsed.Code ?? "";
        if (!SparkAddress.LooksLikeCode(code))
        {
            ShowHint("Bitte den Code aus dem Panel angeben (8 Zeichen, z. B. ABCD-EFGH).", warning: false, error: true);
            return;
        }

        string name = _name.Text.Trim();
        if (!SparkAddress.IsValidDeviceName(name))
        {
            ShowHint("Gerätename: 1–40 Zeichen, nur Buchstaben, Ziffern, Leerzeichen und . - _", warning: false, error: true);
            return;
        }

        SetBusy(true);
        ShowHint("Kopple mit dem Spark …", warning: false);
        _cts = new CancellationTokenSource();
        try
        {
            PairResult result = await SparkClient.PairAsync(parsed.Base, code, name, _cts.Token);
            _config.Base = parsed.Base;
            _config.SetKey(result.Key);
            _config.Profile = result.Profile;
            _config.Device = name;
            _config.Save();
            DialogResult = DialogResult.OK;
            Close();
        }
        catch (SparkException ex)
        {
            ShowHint(ex.Message, warning: false, error: true);
        }
        catch (OperationCanceledException)
        {
            // Dialog wurde geschlossen.
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or System.Security.Cryptography.CryptographicException)
        {
            ShowHint("Die Einstellungen konnten nicht gespeichert werden: " + ex.Message, warning: false, error: true);
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

    private void SetBusy(bool busy)
    {
        _pair.Enabled = !busy;
        _line.Enabled = !busy;
        _code.Enabled = !busy;
        _name.Enabled = !busy;
        UseWaitCursor = busy;
    }

    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        _cts?.Cancel();
        base.OnFormClosing(e);
    }
}
