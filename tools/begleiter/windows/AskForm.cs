using System.Globalization;

namespace SparkBegleiter;

/// <summary>
/// "Frag Spark": Frage eintippen (oder mit dem Mikrofon-Knopf sprechen, wenn Diktieren an ist), Senden.
/// Fragen und Antworten erscheinen als Sprechblasen (eigene mit Farbverlauf, Spark als weiche Karte mit
/// Gesicht). Antworten sind reiner Text (nie HTML), nur angezeigt, nie ausgeführt. Folgefragen behalten den
/// Zusammenhang (den hält der Spark).
/// </summary>
internal sealed class AskForm : ThemedForm
{
    private const int MaxQuestion = 2000;

    private readonly AppConfig _config;
    private readonly Action<SparkException> _report;
    private readonly Func<DeskConfig?> _desk;

    private readonly ChatView _chat = new();

    private readonly TextBox _question = new()
    {
        Multiline = true,
        AcceptsReturn = false,
        ScrollBars = ScrollBars.None,
        WordWrap = true,
        MaxLength = MaxQuestion,
        PlaceholderText = "Frag den Spark …",
        AccessibleName = "Frage",
    };

    private readonly RoundedHost _input;
    private readonly SparkButton _send = new(ButtonKind.Primary, "Senden");
    private readonly SparkButton _mic = new(ButtonKind.Round) { Glyph = Glyph.Mic, Visible = false, AccessibleName = "Sprechen" };
    private readonly TLabel _status = new(TextRole.SmallMuted);
    private readonly System.Windows.Forms.Timer _micTimer = new() { Interval = 250 };
    private readonly SparkButton _speakMode = new(ButtonKind.Chip) { FontSize = 8.5f, Visible = false };
    private readonly Action<string> _speakAnswer;
    private readonly Action _stopSpeaking;
    private readonly Action<string> _setSpeakMode;
    private bool _speakShown;

    /// <summary>Der Text im Fragefeld kam (auch) vom Mikrofon-Knopf: die Frage gilt als gesprochen.</summary>
    private bool _voiceInput;

    private Rectangle _face;
    private Rectangle _title;
    private Rectangle _hint;

    private CancellationTokenSource? _cts;
    private Recorder? _recorder;
    private bool _busy;
    private bool _micShown;
    private bool _canAsk = true;

    /// <summary>Teil "actions": die nächste Frage antwortet auf diese Meldung (Nummer).</summary>
    private int? _note;

    /// <summary>Karten unter der letzten Antwort (Rückfrage, Freigabe, Sprung): eine Reihe Knöpfe über der Statuszeile.</summary>
    private readonly List<SparkButton> _cardButtons = new();

    /// <param name="speakAnswer">Antwort vorlesen (Teil "speak", gleiche Wiedergabe und Pille wie Strg+Alt+L).</param>
    /// <param name="stopSpeaking">Laufendes Vorlesen beenden.</param>
    /// <param name="setSpeakMode">Einstellung „Antworten vorlesen“ speichern.</param>
    public AskForm(AppConfig config, Func<DeskConfig?> desk, Action<SparkException> report,
        Action<string> speakAnswer, Action stopSpeaking, Action<string> setSpeakMode)
    {
        _config = config;
        _speakAnswer = speakAnswer;
        _stopSpeaking = stopSpeaking;
        _setSpeakMode = setSpeakMode;
        _desk = desk;
        _report = report;
        _input = new RoundedHost(_question) { SoftBack = false };

        Text = "Frag Spark";
        TopMost = true;
        ShowInTaskbar = true;
        StartPosition = FormStartPosition.Manual;
        MinimizeBox = true;
        MaximizeBox = true;
        KeyPreview = true;

        Controls.Add(_chat);
        Controls.Add(_status);
        Controls.Add(_send);
        Controls.Add(_mic);
        Controls.Add(_input);
        Controls.Add(_speakMode);
        _speakMode.TabIndex = 3;
        _speakMode.Click += (_, _) =>
        {
            // Durchschalten: nur bei gesprochenen Fragen → immer → nie → …
            string next = AskSpeakModes.Normalize(_config.AskSpeak) switch
            {
                AskSpeakModes.Spoken => AskSpeakModes.Always,
                AskSpeakModes.Always => AskSpeakModes.Never,
                _ => AskSpeakModes.Spoken,
            };
            _setSpeakMode(next);
            if (next == AskSpeakModes.Never)
            {
                _stopSpeaking();
            }
        };
        _send.BringToFront();
        _mic.BringToFront();
        _input.TabIndex = 0;
        _mic.TabIndex = 1;
        _send.TabIndex = 2;

        _send.Click += async (_, _) => await SendAsync();
        _mic.Click += async (_, _) => await ToggleMicAsync();
        _micTimer.Tick += (_, _) => UpdateMicStatus();
        _question.TextChanged += (_, _) =>
        {
            if (_question.TextLength == 0)
            {
                _voiceInput = false;
            }
        };
        _chat.Copied += (_, text) => CopyText(text);
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
        PlaceCentered();
    }

    /// <summary>Mikrofon-Knopf nur, wenn Diktieren im Panel an ist; Eingabe nur, wenn Frag Spark an ist.</summary>
    public void RefreshParts()
    {
        // Das Fenster zeigt auch Ergebnisse anderer Teile (Dateien, Bildschirm, Weckwort); Nachfragen nur mit "ask".
        bool canAsk = _desk()?.IsOn(Parts.Ask) == true || _note is not null;
        if (canAsk != _canAsk)
        {
            _canAsk = canAsk;
            _question.Enabled = canAsk;
            _send.Enabled = canAsk && !_busy;
            _question.PlaceholderText = canAsk ? "Frag den Spark …" : "Nachfragen: Frag Spark im Panel einschalten";
        }

        // „Antworten vorlesen“ nur mit Teil "speak".
        bool speak = _desk()?.IsOn(Parts.Speak) == true;
        string mode = AskSpeakModes.Normalize(_config.AskSpeak);
        _speakMode.Text = "Antworten vorlesen: " + AskSpeakModes.Label(mode);
        _speakMode.Checked = mode != AskSpeakModes.Never;
        _speakMode.AccessibleName = _speakMode.Text + " (klicken zum Ändern)";
        if (_speakShown != speak)
        {
            _speakShown = speak;
            _speakMode.Visible = speak;
        }

        if (IsHandleCreated)
        {
            LayoutContent();
            Invalidate();
        }

        bool dictate = _canAsk && _desk()?.IsOn(Parts.Dictate) == true;
        bool visible = dictate || _recorder is not null;
        if (_micShown != visible)
        {
            _micShown = visible;
            _mic.Visible = visible;
            if (IsHandleCreated)
            {
                LayoutContent();
            }
        }
    }

    private int ButtonsWidth() => _send.Preferred().Width + S(8) + (_micShown ? S(34) + S(8) : 0);

    protected override void LayoutContent()
    {
        int pad = S(14);
        int w = ClientSize.Width;
        int h = ClientSize.Height;
        int y = pad;

        int face = S(28);
        _face = new Rectangle(pad, y, face, face);
        Size title = Draw.Measure("Frag Spark", F(10.5f, FontStyle.Bold));
        _title = new Rectangle(pad + Face.Lead(face, S(8)), y, title.Width + S(4), face);
        int hintRight = w - pad;
        if (_speakShown)
        {
            Size chip = _speakMode.Preferred();
            chip.Height = Math.Min(chip.Height, S(26));
            chip.Width = Math.Min(chip.Width, Math.Max(S(60), w - (2 * pad) - Face.Lead(face, S(8)) - title.Width));
            _speakMode.Bounds = new Rectangle(w - pad - chip.Width, y + ((face - chip.Height) / 2), chip.Width, chip.Height);
            hintRight = _speakMode.Left - S(8);
        }

        _hint = new Rectangle(_title.Right + S(8), y, Math.Max(0, hintRight - _title.Right - S(8)), face);
        y += face + S(10);

        // Eingabezeile unten: Feld mit Mikrofon und Senden darin.
        int inputH = S(58);
        int inputY = h - pad - inputH;
        _input.Padding = new Padding(S(12), S(8), S(6) + ButtonsWidth(), S(8));
        _input.Bounds = new Rectangle(pad, inputY, w - (2 * pad), inputH);
        Size send = _send.Preferred();
        _send.Bounds = new Rectangle(_input.Right - S(8) - send.Width, inputY + ((inputH - send.Height) / 2), send.Width, send.Height);
        _send.Surface = P.Card;
        if (_micShown)
        {
            int m = S(34);
            _mic.Bounds = new Rectangle(_send.Left - S(8) - m, inputY + ((inputH - m) / 2), m, m);
            _mic.Surface = P.Card;
        }

        int statusH = _status.Text.Length > 0 ? Draw.TextHeight(_status.Text, _status.Font, w - (2 * pad)) : 0;
        int statusY = inputY - S(6) - statusH;
        _status.Fit(pad, statusY, w - (2 * pad));

        int chatBottom = (statusH > 0 ? statusY : inputY) - S(8);
        if (_cardButtons.Count > 0)
        {
            // die Knöpfe der Karten in einer Reihe (bei Bedarf umbrochen) direkt über der Statuszeile
            var rows = new List<List<(SparkButton B, Size Z)>> { new() };
            int x = 0;
            foreach (SparkButton b in _cardButtons)
            {
                Size z = b.Preferred();
                if (x > 0 && x + z.Width > w - (2 * pad))
                {
                    rows.Add(new());
                    x = 0;
                }

                rows[^1].Add((b, z));
                x += z.Width + S(6);
            }

            int rowH = rows.SelectMany(r => r).Max(t => t.Z.Height);
            int top = chatBottom - (rows.Count * (rowH + S(6))) + S(6);
            for (int r = 0; r < rows.Count; r++)
            {
                int cx = pad;
                foreach (var (b, z) in rows[r])
                {
                    b.Bounds = new Rectangle(cx, top + (r * (rowH + S(6))), z.Width, z.Height);
                    cx += z.Width + S(6);
                }
            }

            chatBottom = top - S(8);
        }

        _chat.Bounds = new Rectangle(pad - S(4), y, w - (2 * pad) + S(8), Math.Max(S(40), chatBottom - y));
    }

    protected override void PaintContent(Graphics g)
    {
        Face.DrawHeader(g, _face, P);
        Draw.Text(g, "Frag Spark", F(10.5f, FontStyle.Bold), _title, P.Fg);
        Draw.Text(g, "Enter = Senden · Umschalt+Enter = neue Zeile", F(8.5f), _hint, P.Muted, Draw.Line | TextFormatFlags.Right);
    }

    /// <summary>Mitte des Bildschirms mit dem Mauszeiger – vor dem Erzeugen, damit die Fenster-DPI gleich stimmt.</summary>
    private void PlaceCentered()
    {
        Rectangle area = Screen.FromPoint(Cursor.Position).WorkingArea;
        int dpi = Dwm.DpiAt(Cursor.Position);
        int width = Math.Min(Draw.Scale(520, dpi), area.Width);
        int height = Math.Min(Draw.Scale(560, dpi), area.Height);
        MinimumSize = new Size(Math.Min(Draw.Scale(380, dpi), width), Math.Min(Draw.Scale(340, dpi), height));
        Bounds = new Rectangle(area.Left + ((area.Width - width) / 2), area.Top + ((area.Height - height) / 2), width, height);
    }

    protected override void OnLoad(EventArgs e)
    {
        base.OnLoad(e);
        ActiveControl = _question;
    }

    protected override void OnDpiChanged(DpiChangedEventArgs e)
    {
        base.OnDpiChanged(e);
        MinimumSize = new Size(S(380), S(340));
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
        if (_busy || !_canAsk)
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

        bool spoken = _voiceInput;
        _voiceInput = false;
        await SendTextAsync(question, spoken);
    }

    /// <summary>Weckwort (gesprochen) bzw. Fragefeld im Begleiter-Fenster (getippt): die Frage stellen und die Antwort zeigen.</summary>
    public async Task AskQuestionAsync(string question, bool spoken = true)
    {
        await WaitIdleAsync();
        if (IsDisposed)
        {
            return;
        }

        question = question.Trim();
        if (question.Length > MaxQuestion)
        {
            question = question[..MaxQuestion];
        }

        if (question.Length > 0)
        {
            await SendTextAsync(question, spoken); // Weckwort: gesprochene Frage, Fragefeld: getippt
        }
    }

    /// <summary>
    /// Ergebnis eines anderen Teils (Datei, Bildschirm) im Verlauf zeigen: eigene Blase mit <paramref name="mine"/>,
    /// „denkt nach“, dann die Antwort (reiner Text, kopierbar) oder der Fehler; <paramref name="md"/>: dieselbe Antwort
    /// mit Markdown, gegliedert gezeigt (Tagesstart).
    /// </summary>
    public async Task RunExternalAsync(string mine, Func<CancellationToken, Task<string>> work, string? md = null)
    {
        await WaitIdleAsync();
        if (IsDisposed)
        {
            return;
        }

        _chat.Add(mine: true, mine);
        _chat.Pending = true;
        SetBusy(true, "");
        _cts = new CancellationTokenSource();
        try
        {
            string answer = await work(_cts.Token);
            if (IsDisposed)
            {
                return;
            }

            _chat.Pending = false;
            _chat.Add(mine: false, answer.Trim().Length > 0 ? answer.Trim() : "(Der Spark hat keinen Text geschickt.)", md);
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
                _chat.Pending = false;
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
            }
        }
    }

    /// <summary>Teil "actions" → Antworten: die Meldung als Zitat zeigen; die nächste Frage geht mit "note" an den Spark.</summary>
    /// <param name="ask">Steht danach schon im Fragefeld (z. B. „Antwort entwerfen“ zu einer neuen Mail), nichts wird gesendet.</param>
    public void QuoteNote(Note note, string? ask = null)
    {
        string title = note.Title.Trim();
        string quote = "Meldung" + (title.Length > 0 ? ": " + title : "") + (note.Body.Trim().Length > 0 ? Environment.NewLine + note.Body.Trim() : "");
        _chat.Add(mine: false, quote);
        _note = note.N;
        RefreshParts();
        _question.PlaceholderText = "Antwort auf die Meldung …";
        if (ask is not null)
        {
            _question.Text = ask;
            _question.SelectionStart = _question.TextLength;
        }

        SetStatus("Deine Antwort bezieht sich auf diese Meldung.", error: false);
        Bring();
    }

    private async Task WaitIdleAsync()
    {
        while (_busy && !IsDisposed)
        {
            await Task.Delay(150);
        }
    }

    private async Task SendTextAsync(string question, bool spoken)
    {
        _stopSpeaking(); // neue Frage beendet das Vorlesen
        string? key = _config.GetKey();
        if (key is null || string.IsNullOrEmpty(_config.Base))
        {
            SetStatus("Der Begleiter ist nicht gekoppelt (Einstellungen → Neu koppeln).", error: true);
            return;
        }

        _chat.Add(mine: true, question);
        _question.Clear();
        ShowCards(Array.Empty<AskCard>());
        _chat.Pending = true;
        SetBusy(true, "");
        _cts = new CancellationTokenSource();
        try
        {
            AskReply reply = await SparkClient.AskAsync(_config.Base, key, question, _cts.Token, _note);
            (string answer, string? md) = (reply.Answer, reply.Md);
            if (IsDisposed)
            {
                return;
            }

            if (_note is not null)
            {
                _note = null;
                RefreshParts();
                _question.PlaceholderText = _canAsk ? "Frag weiter …" : _question.PlaceholderText;
            }

            _chat.Pending = false;
            _chat.Add(mine: false, answer.Trim(), md?.Trim());
            string mode = AskSpeakModes.Normalize(_config.AskSpeak);
            if (answer.Trim().Length > 0 && _desk()?.IsOn(Parts.Speak) == true && _desk()?.Aloud != false &&
                (mode == AskSpeakModes.Always || (mode == AskSpeakModes.Spoken && spoken)))
            {
                string text = answer.Trim();
                _speakAnswer(text.Length > 5000 ? text[..5000] : text);
            }

            if (_canAsk)
            {
                _question.PlaceholderText = "Frag weiter …";
            }

            string title = string.Join(" · ", reply.Cards.Select(c => c.Title).Where(t => t.Length > 0));
            SetStatus(string.Join(" · ", new[] { reply.Steps ?? "", title }.Where(t => t.Length > 0)), error: false);
            ShowCards(reply.Cards);
        }
        catch (OperationCanceledException)
        {
            // Fenster wurde geschlossen.
        }
        catch (SparkException ex)
        {
            if (!IsDisposed)
            {
                _chat.Pending = false;
                SetStatus(ex.Message, error: true);
                if (_question.TextLength == 0)
                {
                    _question.Text = question; // Frage nicht verlieren
                    _question.SelectionStart = _question.TextLength;
                }
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

    private void CopyText(string text)
    {
        string normalized = text.Replace("\r\n", "\n", StringComparison.Ordinal).Replace("\n", Environment.NewLine, StringComparison.Ordinal);
        SetStatus(ClipboardHelper.TrySetText(normalized, keepOutOfHistory: false)
            ? "Antwort kopiert."
            : "Die Zwischenablage ist gerade gesperrt. Bitte noch einmal versuchen.", error: false);
    }

    /// <summary>Mikrofon im Fragefeld des Begleiter-Fensters: gleich zuhören, wie ein Klick auf den Mikrofon-Knopf.</summary>
    public void StartVoice()
    {
        if (_mic.Visible && _mic.Enabled && _recorder is null)
        {
            _ = ToggleMicAsync();
        }
    }

    /// <summary>Mikrofon: erster Klick startet, zweiter beendet; der erkannte Text kommt ins Fragefeld.</summary>
    private async Task ToggleMicAsync()
    {
        if (_recorder is null)
        {
            _stopSpeaking(); // sonst nimmt das Mikrofon die Vorlesestimme auf
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
            _mic.Checked = true;
            _mic.AccessibleName = "Aufnahme beenden";
            _send.Enabled = false;
            _micTimer.Start();
            UpdateMicStatus();
            return;
        }

        Recorder current = _recorder;
        _recorder = null;
        _micTimer.Stop();
        _mic.Checked = false;
        _mic.AccessibleName = "Sprechen";
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
            SetStatus(Recorder.NothingText, error: true);
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
                _voiceInput = true;
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
            SetStatus(string.Create(CultureInfo.InvariantCulture, $"Ich höre zu {(int)t.TotalMinutes}:{t.Seconds:00} … (höchstens {Recorder.MaxSeconds} s; ■ zum Beenden)"), error: false);
        }
    }

    /// <summary>
    /// Die Karten der letzten Antwort als Knöpfe: „send“ schickt das feste Wort wie getippt (das Panel entscheidet mit
    /// seinen Regeln), „open“ öffnet eine Seite im Panel (nur <see cref="AskCards.Pages"/>), „focus“ setzt den Cursor ins Feld.
    /// </summary>
    private void ShowCards(IReadOnlyList<AskCard> cards)
    {
        foreach (SparkButton old in _cardButtons)
        {
            Controls.Remove(old);
            old.Dispose();
        }

        _cardButtons.Clear();
        int tab = 10;
        foreach (AskCard card in cards)
        {
            foreach (AskButton b in card.Buttons)
            {
                var button = new SparkButton(b.Main ? ButtonKind.Primary : ButtonKind.Secondary, b.Open is null ? b.Label : b.Label + " ↗")
                {
                    FontSize = 9f,
                    TabIndex = tab++,
                    AccessibleDescription = card.Title.Length > 0 ? card.Title : "Antwort auf die Frage des Spark",
                    Surface = P.Card,
                };
                AskButton pick = b;
                button.Click += async (_, _) => await PickCardAsync(pick);
                _cardButtons.Add(button);
                Controls.Add(button);
            }
        }

        if (IsHandleCreated)
        {
            LayoutContent();
            Invalidate();
        }
    }

    private async Task PickCardAsync(AskButton b)
    {
        if (b.Send is { } word)
        {
            if (_busy || !_canAsk)
            {
                return;
            }

            await SendTextAsync(word, spoken: false);
        }
        else if (b.Open is { } page)
        {
            Wege.Open?.Invoke(page);
        }
        else
        {
            _question.Focus();
        }
    }

    private void SetBusy(bool busy, string? text)
    {
        _busy = busy;
        _send.Enabled = !busy && _canAsk;
        _mic.Enabled = !busy;
        if (text is not null)
        {
            SetStatus(text, error: false);
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

    protected override bool ProcessCmdKey(ref Message msg, Keys keyData)
    {
        if (keyData == Keys.Escape)
        {
            Close();
            return true;
        }

        if (keyData == (Keys.Control | Keys.C) && _question.SelectionLength == 0 && _chat.LastAnswer is { } last)
        {
            CopyText(last);
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

/// <summary>
/// Verlauf als Sprechblasen, selbst gezeichnet: eigene Fragen rechts mit Akzent-Verlauf, Antworten links als
/// weiche Karte mit dem Gesicht daneben und „Kopieren“ darunter. Rechtsklick auf eine Blase: Kopieren.
/// Antworten mit Markdown (MdText) erscheinen gegliedert: Überschriften fett, Listen mit Zeichen und Einzug,
/// Code in Monospace; kopiert und vorgelesen wird der schlichte Text.
/// </summary>
internal sealed class ChatView : Panel, IThemed
{
    private readonly List<(bool Mine, string Text, List<MdLine>? Md)> _messages = new();
    private readonly List<Block> _blocks = new();
    private readonly System.Windows.Forms.Timer _dots = new() { Interval = 400 };
    private readonly ContextMenuStrip _menu = new();
    private int _dpi = 96;
    private int _dotCount;
    private bool _pending;
    private int _hoverCopy = -1;
    private int _menuIndex = -1;

    public ChatView()
    {
        SetStyle(ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint | ControlStyles.ResizeRedraw | ControlStyles.UserPaint, true);
        AutoScroll = true;
        TabStop = false;
        AccessibleRole = AccessibleRole.List;
        AccessibleName = "Unterhaltung";
        _dots.Tick += (_, _) =>
        {
            _dotCount = (_dotCount + 1) % 4;
            Invalidate();
        };
        _menu.Items.Add(new ToolStripMenuItem("Kopieren", null, (_, _) =>
        {
            if (_menuIndex >= 0 && _menuIndex < _messages.Count)
            {
                Copied?.Invoke(this, _messages[_menuIndex].Text);
            }
        }));
        HandleCreated += (_, _) => Dwm.ScrollbarTheme(this, Theme.Current.Dark);
    }

    /// <summary>„Kopieren“ wurde gewählt (Text der Blase).</summary>
    public event EventHandler<string>? Copied;

    public string? LastAnswer => _messages.LastOrDefault(m => !m.Mine).Text;

    /// <summary>„Der Spark denkt nach …“ als Blase zeigen.</summary>
    public bool Pending
    {
        get => _pending;
        set
        {
            _pending = value;
            if (value)
            {
                _dots.Start();
            }
            else
            {
                _dots.Stop();
            }

            Relayout(scrollToEnd: true);
        }
    }

    /// <summary>Eine Blase anfügen; md ist die Antwort mit Markdown (gegliedert gezeigt), text der schlichte Text.</summary>
    public void Add(bool mine, string text, string? md = null)
    {
        List<MdLine>? lines = !mine && !string.IsNullOrWhiteSpace(md) ? MdText.Lines(md) : null;
        _messages.Add((mine, text, lines is { Count: > 0 } ? lines : null));
        AccessibleDescription = (mine ? "Du: " : "Spark: ") + text;
        Relayout(scrollToEnd: true);
    }

    public void ApplyTheme(int dpi)
    {
        _dpi = dpi;
        BackColor = Theme.Current.Card;
        Font = Theme.UiFont(dpi, 10f);
        Dwm.ScrollbarTheme(this, Theme.Current.Dark);
        Relayout(scrollToEnd: false);
    }

    private int S(float v) => Draw.Scale(v, _dpi);

    private sealed record Block(int Index, bool Mine, string Text, Rectangle Bubble, Rectangle TextRect, Rectangle Avatar, Rectangle Copy, List<Row>? Rows = null);

    /// <summary>Eine gezeichnete Zeile einer gegliederten Antwort, relativ zur Textfläche der Blase.</summary>
    private sealed record Row(MdKind Kind, string Text, string Mark, Rectangle Rect, Rectangle MarkRect, Font Font);

    /// <summary>Die Zeilen einer gegliederten Antwort für die Breite maxText messen und untereinander legen.</summary>
    private (List<Row> Rows, Size Size) LayoutMd(List<MdLine> lines, int maxText)
    {
        var rows = new List<Row>();
        int y = 0;
        int width = 0;
        int step = S(16);
        Font bold = Theme.UiFont(_dpi, 10f, FontStyle.Bold);
        Font mono = Theme.MonoFont(_dpi, 9f);
        for (int i = 0; i < lines.Count; i++)
        {
            MdLine l = lines[i];
            if (l.Kind == MdKind.Blank)
            {
                y += S(7);
                continue;
            }

            if (l.Kind == MdKind.Rule)
            {
                rows.Add(new Row(l.Kind, "", "", new Rectangle(0, y + S(2), Math.Max(S(40), width), S(9)), Rectangle.Empty, Font));
                y += S(13);
                continue;
            }

            if (l.Kind == MdKind.Heading && rows.Count > 0 && lines[i - 1].Kind != MdKind.Blank)
            {
                y += S(4);
            }

            Font font = l.Kind == MdKind.Heading ? bold : l.Kind == MdKind.Code ? mono : Font;
            int indent = l.Level * step;
            Rectangle markRect = Rectangle.Empty;
            if (l.Mark.Length > 0)
            {
                Size m = TextRenderer.MeasureText(l.Mark, Font, new Size(1000, 1000), TextFormatFlags.NoPrefix);
                markRect = new Rectangle(indent, y, m.Width, m.Height);
                indent += Math.Max(step, m.Width + S(4));
            }

            int room = Math.Max(S(40), maxText - indent);
            string shown = l.Text.Length > 0 ? l.Text : " ";
            Size size = TextRenderer.MeasureText(shown, font, new Size(room, 100000), TextFlags);
            var rect = new Rectangle(indent, y, room, size.Height);   // drawn as wide as measured, so it wraps the same
            rows.Add(new Row(l.Kind, shown, l.Mark, rect, markRect, font));
            width = Math.Max(width, indent + Math.Min(room, size.Width));
            y = rect.Bottom + (l.Kind == MdKind.Code ? 0 : S(2));
        }

        return (rows, new Size(Math.Max(1, width), Math.Max(1, y)));
    }

    private const TextFormatFlags TextFlags = TextFormatFlags.WordBreak | TextFormatFlags.TextBoxControl | TextFormatFlags.NoPrefix;

    private void Relayout(bool scrollToEnd)
    {
        _blocks.Clear();
        int avail = Math.Max(S(120), ClientSize.Width - S(8));
        int x0 = S(4);
        int y = S(4);
        int padX = S(12);
        int padY = S(9);
        int avatar = S(30);

        IEnumerable<(int Index, bool Mine, string Text, List<MdLine>? Md)> items = _messages.Select((m, i) => (i, m.Mine, m.Text, m.Md));
        if (_pending)
        {
            items = items.Append((-1, false, "Der Spark denkt nach", (List<MdLine>?)null));
        }

        foreach (var (index, mine, text, md) in items)
        {
            if (mine)
            {
                int maxText = (int)(avail * 0.85) - (2 * padX);
                Size size = TextRenderer.MeasureText(text, Font, new Size(Math.Max(1, maxText), 100000), TextFlags);
                var bubble = new Rectangle(x0 + avail - size.Width - (2 * padX), y, size.Width + (2 * padX), size.Height + (2 * padY));
                _blocks.Add(new Block(index, true, text, bubble, Rectangle.Inflate(bubble, -padX, -padY), Rectangle.Empty, Rectangle.Empty));
                y = bubble.Bottom + S(10);
            }
            else
            {
                int bx = x0 + Face.Lead(avatar, S(8));
                int maxText = Math.Max(1, (int)((avail - Face.Lead(avatar, S(8))) * 0.92) - (2 * padX));
                List<Row>? rows = null;
                Size size;
                if (md is not null)
                {
                    (rows, size) = LayoutMd(md, maxText);
                }
                else
                {
                    size = TextRenderer.MeasureText(index < 0 ? text + " ..." : text, Font, new Size(maxText, 100000), TextFlags);
                }

                var bubble = new Rectangle(bx, y, size.Width + (2 * padX), size.Height + (2 * padY));
                Rectangle copy = Rectangle.Empty;
                int bottom = bubble.Bottom;
                if (index >= 0)
                {
                    Font small = Theme.UiFont(_dpi, 8.5f);
                    Size c = Draw.Measure("Kopieren", small);
                    copy = new Rectangle(bx + S(4), bubble.Bottom + S(3), c.Width, c.Height);
                    bottom = copy.Bottom;
                }

                _blocks.Add(new Block(index, false, text, bubble, Rectangle.Inflate(bubble, -padX, -padY), new Rectangle(x0, y, avatar, avatar), copy, rows));
                y = bottom + S(12);
            }
        }

        AutoScrollMinSize = new Size(0, y);
        if (scrollToEnd)
        {
            AutoScrollPosition = new Point(0, y);
        }

        Invalidate();
    }

    protected override void OnResize(EventArgs eventargs)
    {
        base.OnResize(eventargs);
        Relayout(scrollToEnd: false);
    }

    protected override void OnScroll(ScrollEventArgs se)
    {
        base.OnScroll(se);
        Invalidate();
    }

    protected override void OnMouseWheel(MouseEventArgs e)
    {
        base.OnMouseWheel(e);
        Invalidate();
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        Graphics g = e.Graphics;
        Palette p = Theme.Current;
        g.Clear(p.Card);
        Draw.HighQuality(g);
        Point offset = AutoScrollPosition;

        if (_blocks.Count == 0)
        {
            var empty = new Rectangle(S(24), S(24), Math.Max(1, ClientSize.Width - S(48)), Math.Max(1, ClientSize.Height - S(48)));
            TextRenderer.DrawText(g, "Frag den Spark etwas – zum Beispiel nach deinen Terminen. Folgefragen behalten den Zusammenhang.",
                Theme.UiFont(_dpi, 9.5f), empty, p.Muted, TextFlags | TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter);
            return;
        }

        foreach (Block b in _blocks)
        {
            Rectangle bubble = b.Bubble;
            bubble.Offset(offset);
            if (bubble.Bottom < -S(40) || bubble.Top > ClientSize.Height + S(40))
            {
                continue;
            }

            Rectangle text = b.TextRect;
            text.Offset(offset);
            float r = S(14);
            float small = S(4);
            if (b.Mine)
            {
                using System.Drawing.Drawing2D.GraphicsPath path = Draw.Round(bubble, r, r, small, r);
                using var brush = new SolidBrush(p.Accent);
                g.FillPath(brush, path);
                TextRenderer.DrawText(g, b.Text, Font, text, p.OnAccent, TextFlags);
            }
            else
            {
                Rectangle avatar = b.Avatar;
                avatar.Offset(offset);
                Face.DrawHeader(g, avatar, p);
                using (System.Drawing.Drawing2D.GraphicsPath path = Draw.Round(bubble, r, r, r, small))
                {
                    using var fill = new SolidBrush(p.Soft);
                    g.FillPath(fill, path);
                    using var pen = new Pen(p.Line);
                    g.DrawPath(pen, path);
                }

                if (b.Rows is { } rows)
                {
                    PaintRows(g, rows, text, p);
                }
                else
                {
                    string shown = b.Index < 0 ? b.Text + " " + new string('.', _dotCount) : b.Text;
                    TextRenderer.DrawText(g, shown, Font, text, b.Index < 0 ? p.Muted : p.Fg, TextFlags);
                }

                if (!b.Copy.IsEmpty)
                {
                    Rectangle copy = b.Copy;
                    copy.Offset(offset);
                    Font f = Theme.UiFont(_dpi, 8.5f, b.Index == _hoverCopy ? FontStyle.Underline : FontStyle.Regular);
                    TextRenderer.DrawText(g, "Kopieren", f, copy, b.Index == _hoverCopy ? p.Accent : p.Muted, TextFormatFlags.NoPrefix);
                }
            }
        }
    }

    private void PaintRows(Graphics g, List<Row> rows, Rectangle area, Palette p)
    {
        Point origin = area.Location;
        foreach (Row row in rows)
        {
            Rectangle rect = row.Rect;
            rect.Offset(origin);
            if (row.Kind == MdKind.Rule)
            {
                using var pen = new Pen(p.Line);
                g.DrawLine(pen, area.Left, rect.Top + (rect.Height / 2), area.Right, rect.Top + (rect.Height / 2));
                continue;
            }

            if (!row.MarkRect.IsEmpty)
            {
                Rectangle mark = row.MarkRect;
                mark.Offset(origin);
                TextRenderer.DrawText(g, row.Mark, Font, mark, p.Muted, TextFormatFlags.NoPrefix);
            }

            TextRenderer.DrawText(g, row.Text, row.Font, rect, p.Fg, TextFlags);
        }
    }

    private Block? HitBlock(Point location, bool copyOnly)
    {
        Point offset = AutoScrollPosition;
        foreach (Block b in _blocks)
        {
            Rectangle copy = b.Copy;
            copy.Offset(offset);
            Rectangle bubble = b.Bubble;
            bubble.Offset(offset);
            if (!copy.IsEmpty && Rectangle.Inflate(copy, S(3), S(2)).Contains(location))
            {
                return b;
            }

            if (!copyOnly && b.Index >= 0 && bubble.Contains(location))
            {
                return b;
            }
        }

        return null;
    }

    protected override void OnMouseMove(MouseEventArgs e)
    {
        base.OnMouseMove(e);
        int hover = HitBlock(e.Location, copyOnly: true)?.Index ?? -1;
        if (hover != _hoverCopy)
        {
            _hoverCopy = hover;
            Cursor = hover >= 0 ? Cursors.Hand : Cursors.Default;
            Invalidate();
        }
    }

    protected override void OnMouseLeave(EventArgs e)
    {
        base.OnMouseLeave(e);
        if (_hoverCopy >= 0)
        {
            _hoverCopy = -1;
            Cursor = Cursors.Default;
            Invalidate();
        }
    }

    protected override void OnMouseClick(MouseEventArgs e)
    {
        base.OnMouseClick(e);
        if (e.Button == MouseButtons.Left && HitBlock(e.Location, copyOnly: true) is { } copy && copy.Index >= 0)
        {
            Copied?.Invoke(this, _messages[copy.Index].Text);
        }
        else if (e.Button == MouseButtons.Right && HitBlock(e.Location, copyOnly: false) is { } block && block.Index >= 0)
        {
            _menuIndex = block.Index;
            _menu.Show(this, e.Location);
        }
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            _dots.Dispose();
            _menu.Dispose();
        }

        base.Dispose(disposing);
    }
}
