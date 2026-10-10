namespace SparkBegleiter;

/// <summary>
/// "Frag Spark": Frage eintippen (oder mit dem Mikrofon-Knopf sprechen, wenn Diktieren an ist), Senden,
/// die Antwort erscheint als reiner Text (nie als HTML). Folgefragen behalten den Zusammenhang
/// (den hält der Spark). Antworten vom Spark sind Daten: nur angezeigt, nie ausgeführt.
/// </summary>
internal sealed class AskForm : Form
{
    private const int MaxQuestion = 2000;

    private readonly AppConfig _config;
    private readonly Action<SparkException> _report;
    private readonly Func<DeskConfig?> _desk;

    private readonly TextBox _answer = new()
    {
        Dock = DockStyle.Fill,
        Multiline = true,
        ReadOnly = true,
        ScrollBars = ScrollBars.Vertical,
        WordWrap = true,
        BackColor = SystemColors.Window,
    };

    private readonly TextBox _question = new()
    {
        Dock = DockStyle.Fill,
        Multiline = true,
        AcceptsReturn = false,
        ScrollBars = ScrollBars.Vertical,
        WordWrap = true,
        MaxLength = MaxQuestion,
        PlaceholderText = "Frage an den Spark … (Enter = Senden, Umschalt+Enter = neue Zeile)",
    };

    private readonly Button _send = new() { Text = "Senden", AutoSize = true };
    private readonly Button _mic = new() { Text = "Sprechen", AutoSize = true, Visible = false };
    private readonly Button _copy = new() { Text = "Kopieren", AutoSize = true, Enabled = false };
    private readonly Button _close = new() { Text = "Schließen", AutoSize = true };
    private readonly Label _status = new() { AutoSize = true, MaximumSize = new Size(520, 0), Anchor = AnchorStyles.Left, Padding = new Padding(0, 4, 0, 0) };
    private readonly ProgressBar _progress = new() { Style = ProgressBarStyle.Marquee, Width = 90, Height = 12, Visible = false, Anchor = AnchorStyles.Left };
    private readonly System.Windows.Forms.Timer _micTimer = new() { Interval = 250 };

    private CancellationTokenSource? _cts;
    private Recorder? _recorder;
    private string _lastAnswer = "";
    private bool _busy;

    public AskForm(AppConfig config, Func<DeskConfig?> desk, Action<SparkException> report)
    {
        _config = config;
        _desk = desk;
        _report = report;

        BuildLayout();
        _send.Click += async (_, _) => await SendAsync();
        _copy.Click += (_, _) => CopyAnswer();
        _close.Click += (_, _) => Close();
        _mic.Click += async (_, _) => await ToggleMicAsync();
        _micTimer.Tick += (_, _) => UpdateMicStatus();
        _question.KeyDown += async (_, e) =>
        {
            if (e.KeyCode == Keys.Enter && !e.Shift)
            {
                e.SuppressKeyPress = true;
                await SendAsync();
            }
            else if (e.KeyCode == Keys.Enter && e.Shift)
            {
                // Neue Zeile von Hand einfügen (AcceptsReturn ist aus, damit Enter sendet).
                e.SuppressKeyPress = true;
                _question.SelectedText = Environment.NewLine;
            }
        };

        RefreshParts();
    }

    /// <summary>Mikrofon-Knopf nur, wenn Diktieren im Panel an ist.</summary>
    public void RefreshParts()
    {
        bool dictate = _desk()?.IsOn(Parts.Dictate) == true;
        _mic.Visible = dictate || _recorder is not null;
    }

    private void BuildLayout()
    {
        SuspendLayout();
        AutoScaleDimensions = new SizeF(96F, 96F);
        AutoScaleMode = AutoScaleMode.Dpi;
        Font = SystemFonts.MessageBoxFont ?? Font;
        Text = "Frag Spark";
        Icon = AppIcon.Icon;
        TopMost = true;
        ShowInTaskbar = true;
        StartPosition = FormStartPosition.Manual;
        MinimizeBox = true;
        MaximizeBox = true;
        ClientSize = new Size(560, 520);
        MinimumSize = new Size(400, 360);
        Padding = new Padding(10);

        var statusRow = new FlowLayoutPanel { AutoSize = true, Dock = DockStyle.Fill, WrapContents = false, Margin = Padding.Empty };
        statusRow.Controls.Add(_progress);
        statusRow.Controls.Add(_status);

        var buttons = new FlowLayoutPanel { AutoSize = true, Dock = DockStyle.Fill, FlowDirection = FlowDirection.RightToLeft, Margin = Padding.Empty };
        buttons.Controls.Add(_close);
        buttons.Controls.Add(_copy);
        buttons.Controls.Add(_send);
        buttons.Controls.Add(_mic);

        var root = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1 };
        root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        AddRow(root, new Label { Text = "Antwort:", AutoSize = true, Padding = new Padding(0, 0, 0, 2) }, SizeType.AutoSize);
        AddRow(root, _answer, SizeType.Percent, 72);
        AddRow(root, new Label { Text = "Frage:", AutoSize = true, Padding = new Padding(0, 6, 0, 2) }, SizeType.AutoSize);
        AddRow(root, _question, SizeType.Percent, 28);
        AddRow(root, statusRow, SizeType.AutoSize);
        AddRow(root, buttons, SizeType.AutoSize);
        Controls.Add(root);

        CancelButton = _close;
        ResumeLayout(performLayout: true);
    }

    private static void AddRow(TableLayoutPanel table, Control control, SizeType sizeType, float size = 0)
    {
        table.RowStyles.Add(new RowStyle(sizeType, size));
        table.Controls.Add(control, 0, table.RowStyles.Count - 1);
    }

    protected override void OnLoad(EventArgs e)
    {
        base.OnLoad(e);
        Rectangle area = Screen.FromPoint(Cursor.Position).WorkingArea;
        int width = Math.Min(Width, area.Width);
        int height = Math.Min(Height, area.Height);
        Bounds = new Rectangle(area.Left + ((area.Width - width) / 2), area.Top + ((area.Height - height) / 2), width, height);
        ActiveControl = _question;
        SetStatus("", error: false);
    }

    /// <summary>Nach vorn holen und den Cursor ins Fragefeld setzen.</summary>
    public void Bring()
    {
        if (WindowState == FormWindowState.Minimized)
        {
            WindowState = FormWindowState.Normal;
        }

        Activate();
        _question.Focus();
    }

    private async Task SendAsync()
    {
        if (_busy)
        {
            return;
        }

        string question = _question.Text.Trim();
        if (question.Length == 0)
        {
            SetStatus("Bitte zuerst eine Frage eingeben.", error: true);
            _question.Focus();
            return;
        }

        string? key = _config.GetKey();
        if (key is null || string.IsNullOrEmpty(_config.Base))
        {
            SetStatus("Der Begleiter ist nicht gekoppelt (Einstellungen → Neu koppeln).", error: true);
            return;
        }

        SetBusy(true, "Der Spark denkt nach …");
        _cts = new CancellationTokenSource();
        try
        {
            string answer = await SparkClient.AskAsync(_config.Base, key, question, _cts.Token);
            if (IsDisposed)
            {
                return;
            }

            AppendExchange(question, answer.Trim());
            _question.Clear();
            SetStatus("", error: false);
        }
        catch (OperationCanceledException)
        {
            // Fenster wurde geschlossen.
        }
        catch (SparkException ex)
        {
            if (!IsDisposed)
            {
                SetStatus(ex.Message, error: true);
            }

            _report(ex);
        }
        finally
        {
            _cts?.Dispose();
            _cts = null;
            if (!IsDisposed)
            {
                SetBusy(false, null);
                _question.Focus();
            }
        }
    }

    /// <summary>Frage und Antwort als reinen Text unten anhängen.</summary>
    private void AppendExchange(string question, string answer)
    {
        _lastAnswer = answer;
        string block = "Du: " + question + Environment.NewLine + Environment.NewLine
                       + "Spark: " + NormalizeNewlines(answer) + Environment.NewLine;
        if (_answer.TextLength > 0)
        {
            block = Environment.NewLine + "────────" + Environment.NewLine + Environment.NewLine + block;
        }

        _answer.AppendText(block);
        _answer.SelectionStart = _answer.TextLength;
        _answer.ScrollToCaret();
        _copy.Enabled = true;
    }

    private static string NormalizeNewlines(string text) =>
        text.Replace("\r\n", "\n", StringComparison.Ordinal).Replace("\n", Environment.NewLine, StringComparison.Ordinal);

    private void CopyAnswer()
    {
        SetStatus(ClipboardHelper.TrySetText(NormalizeNewlines(_lastAnswer), keepOutOfHistory: false)
            ? "Antwort kopiert."
            : "Die Zwischenablage ist gerade gesperrt. Bitte noch einmal versuchen.", error: false);
    }

    /// <summary>Mikrofon: erster Klick startet, zweiter beendet; der erkannte Text kommt ins Fragefeld.</summary>
    private async Task ToggleMicAsync()
    {
        if (_recorder is null)
        {
            Recorder? recorder = Recorder.TryStart(out string error);
            if (recorder is null)
            {
                SetStatus(error, error: true);
                return;
            }

            _recorder = recorder;
            recorder.LimitReached += async (_, _) =>
            {
                if (ReferenceEquals(_recorder, recorder))
                {
                    await ToggleMicAsync();
                }
            };
            _mic.Text = "■ Stopp";
            _send.Enabled = false;
            _micTimer.Start();
            UpdateMicStatus();
            return;
        }

        Recorder current = _recorder;
        _recorder = null;
        _micTimer.Stop();
        _mic.Text = "Sprechen";
        byte[]? wav;
        try
        {
            wav = await current.StopAsync();
        }
        finally
        {
            current.Dispose();
        }

        if (wav is null)
        {
            SetStatus("Die Aufnahme war zu kurz.", error: true);
            _send.Enabled = !_busy;
            RefreshParts();
            return;
        }

        string? key = _config.GetKey();
        if (key is null || string.IsNullOrEmpty(_config.Base))
        {
            SetStatus("Der Begleiter ist nicht gekoppelt.", error: true);
            _send.Enabled = !_busy;
            return;
        }

        SetBusy(true, "Der Spark erkennt den Text …");
        _cts = new CancellationTokenSource();
        try
        {
            string text = (await SparkClient.DictateAsync(_config.Base, key, wav, _desk()?.DictateSprache ?? "auto", _cts.Token)).Trim();
            if (IsDisposed)
            {
                return;
            }

            if (text.Length == 0)
            {
                SetStatus("Es wurde nichts erkannt.", error: true);
            }
            else
            {
                string joined = _question.Text.Trim().Length > 0 ? _question.Text.TrimEnd() + " " + text : text;
                _question.Text = joined.Length > MaxQuestion ? joined[..MaxQuestion] : joined;
                _question.SelectionStart = _question.TextLength;
                SetStatus("Erkannt – prüfen und Senden.", error: false);
            }
        }
        catch (OperationCanceledException)
        {
            // Fenster wurde geschlossen.
        }
        catch (SparkException ex)
        {
            if (!IsDisposed)
            {
                SetStatus(ex.Message, error: true);
            }

            _report(ex);
        }
        finally
        {
            _cts?.Dispose();
            _cts = null;
            if (!IsDisposed)
            {
                SetBusy(false, null);
                RefreshParts();
                _question.Focus();
            }
        }
    }

    private void UpdateMicStatus()
    {
        if (_recorder is { } r)
        {
            TimeSpan t = r.Elapsed;
            SetStatus($"Aufnahme {(int)t.TotalMinutes}:{t.Seconds:00} … (höchstens {Recorder.MaxSeconds} s; „Stopp“ zum Beenden)", error: false);
        }
    }

    private void SetBusy(bool busy, string? text)
    {
        _busy = busy;
        _send.Enabled = !busy;
        _mic.Enabled = !busy;
        _progress.Visible = busy;
        if (text is not null)
        {
            SetStatus(text, error: false);
        }
    }

    private void SetStatus(string text, bool error)
    {
        _status.Text = text;
        _status.ForeColor = error ? Color.Firebrick : SystemColors.ControlText;
    }

    protected override bool ProcessCmdKey(ref Message msg, Keys keyData)
    {
        if (keyData == Keys.Escape)
        {
            Close();
            return true;
        }

        return base.ProcessCmdKey(ref msg, keyData);
    }

    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        _cts?.Cancel();
        _micTimer.Stop();
        _recorder?.Dispose();
        _recorder = null;
        base.OnFormClosing(e);
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            _micTimer.Dispose();
            _recorder?.Dispose();
        }

        base.Dispose(disposing);
    }
}
