using System.Diagnostics;

namespace SparkBegleiter;

/// <summary>Verbindungszustand für Zustandspunkt, Menü und Tooltip.</summary>
internal enum Connection
{
    Unpaired,
    Unknown,
    Online,
    Offline,
    Notaus,
}

/// <summary>
/// Das eigentliche Programm: Symbol im Infobereich mit Zustandspunkt, Menü, Tastenkürzel, regelmäßige
/// Abfrage beim Spark (Herzschlag, Meldungen, Einstellungen) und die Abläufe der Teile:
/// Schreibhilfe, Frag Spark, Diktieren, Meldungen, Zustandspunkt, Mein Notaus.
/// </summary>
internal sealed class TrayContext : ApplicationContext, IBegleiterHost
{
    public const string Title = "Spark-Begleiter";

    /// <summary>Abfrageabstand bei Notaus (der Spark antwortet dann ohnehin nur mit 503).</summary>
    private const int NotausPollSeconds = 60;

    private readonly AppConfig _config = AppConfig.Load();
    private readonly NotifyIcon _tray;
    private readonly ContextMenuStrip _menu = new();
    private readonly HotkeyManager _hotkeys = new();
    private readonly Control _invoker = new();
    private readonly System.Windows.Forms.Timer _pollTimer = new();
    private readonly HashSet<string> _conflicts = new();

    private DeskConfig? _desk;
    private Connection _connection;
    private string _connectionText = "";
    private int _lastNote = -1;
    private bool _needConfig = true;
    private bool _polling;
    private bool _hotkeysSuspended;
    private bool _slowPoll;

    private AssistForm? _assist;
    private AskForm? _ask;
    private SettingsForm? _settings;
    private bool _writing;
    private bool _pairOpen;

    // Diktieren
    private Recorder? _recorder;
    private RecordingIndicator? _indicator;
    private IntPtr _dictateTarget;
    private bool _dictateBusy;

    public TrayContext()
    {
        _invoker.CreateControl();
        _desk = _config.IsPaired ? _config.Desk : null;
        _connection = _config.IsPaired ? Connection.Unknown : Connection.Unpaired;

        _tray = new NotifyIcon
        {
            Icon = AppIcon.ForTray(StatusDot.None),
            Text = Title,
            ContextMenuStrip = _menu,
            Visible = true,
        };
        _tray.MouseClick += (_, e) =>
        {
            if (e.Button == MouseButtons.Left)
            {
                OnLeftClick();
            }
        };
        _menu.Opening += (_, _) => BuildMenu();

        _hotkeys.Pressed += async (_, part) => await OnHotkeyAsync(part);
        _pollTimer.Tick += async (_, _) => await PollAsync();

        RegisterHotkeys(notify: false);
        UpdateIcon();
        BuildMenu();

        // Erst nach dem Start der Nachrichtenschleife Dialoge/Hinweise zeigen.
        Application.Idle += OnFirstIdle;

        void OnFirstIdle(object? sender, EventArgs e)
        {
            Application.Idle -= OnFirstIdle;
            NotifyConflicts(_conflicts);
            if (!_config.IsPaired)
            {
                Pair(null);
            }
            else
            {
                _ = PollAsync();
            }
        }
    }

    public event EventHandler? Changed;

    public AppConfig Config => _config;

    public DeskConfig? Desk => _desk;

    public IReadOnlyCollection<string> HotkeyConflicts => _conflicts;

    private bool IsOn(string part) => _config.IsPaired && _desk?.IsOn(part) == true;

    // ------------------------------------------------------------------ Abfrage

    /// <summary>
    /// Eine Abfrage: bei Bedarf Einstellungen holen, dann /api/desk/poll (Herzschlag, Meldungen, Notaus).
    /// Danach wird die nächste Abfrage geplant (poll Sekunden, bei Notaus 60 s).
    /// </summary>
    private async Task PollAsync()
    {
        if (_polling)
        {
            return;
        }

        _pollTimer.Stop();
        string? key = _config.GetKey();
        if (key is null || string.IsNullOrEmpty(_config.Base))
        {
            SetConnection(Connection.Unpaired, "");
            return;
        }

        string baseUrl = _config.Base;
        _polling = true;
        try
        {
            if (_needConfig || _desk is null)
            {
                await RefreshConfigAsync(baseUrl, key);
            }

            PollResult poll = await SparkClient.PollAsync(baseUrl, key, Math.Max(_lastNote, 0), CancellationToken.None);
            if (!IsCurrent(baseUrl, key))
            {
                return; // inzwischen entkoppelt oder neu gekoppelt
            }

            if (_desk is null || poll.Rev != _desk.Rev)
            {
                await RefreshConfigAsync(baseUrl, key);
            }

            _slowPoll = false;
            HandleNotes(poll);
            if (poll.NotausLevel > 0)
            {
                SetConnection(Connection.Notaus, $"Notaus Stufe {poll.NotausLevel} am Spark");
            }
            else
            {
                SetConnection(Connection.Online, "");
            }
        }
        catch (SparkException ex)
        {
            if (IsCurrent(baseUrl, key))
            {
                Report(ex, fromPoll: true);
            }
        }
        catch (Exception ex) when (ex is InvalidOperationException or IOException or System.Text.Json.JsonException)
        {
            // Unerwartete Antwort – wie "nicht erreichbar" behandeln, nächster Versuch mit der nächsten Abfrage.
            SetConnection(Connection.Offline, ex.Message);
        }
        finally
        {
            _polling = false;
            ScheduleNextPoll();
        }
    }

    private bool IsCurrent(string baseUrl, string key) =>
        _config.Base == baseUrl && _config.GetKey() == key;

    private async Task RefreshConfigAsync(string baseUrl, string key)
    {
        DeskConfig desk = await SparkClient.GetConfigAsync(baseUrl, key, CancellationToken.None);
        if (!IsCurrent(baseUrl, key))
        {
            return;
        }

        _needConfig = false;
        ApplyConfig(desk);
    }

    private void ScheduleNextPoll()
    {
        if (!_config.IsPaired)
        {
            return;
        }

        int seconds = _slowPoll ? NotausPollSeconds : _desk?.Poll ?? 30;
        _pollTimer.Interval = Math.Clamp(seconds, 5, 600) * 1000;
        _pollTimer.Start();
    }

    /// <summary>Gleich noch einmal abfragen (z. B. nach dem Koppeln oder einem 403).</summary>
    private void PollSoon(bool refetchConfig)
    {
        _needConfig |= refetchConfig;
        _invoker.BeginInvoke(new Action(async () => await PollAsync()));
    }

    /// <summary>
    /// Meldungen: beim ersten Abruf nach dem Start nur die Nummer merken (ältere Meldungen nicht zeigen),
    /// danach neuere als Hinweis des Infobereichs zeigen – nur, wenn der Teil "notes" an ist.
    /// </summary>
    private void HandleNotes(PollResult poll)
    {
        if (_lastNote < 0)
        {
            _lastNote = poll.Last;
            return;
        }

        var fresh = poll.Notes.Where(n => n.N > _lastNote).OrderBy(n => n.N).ToList();
        _lastNote = Math.Max(poll.Last, fresh.Count > 0 ? fresh[^1].N : 0);
        if (fresh.Count == 0 || !IsOn(Parts.Notes))
        {
            return;
        }

        if (fresh.Count == 1)
        {
            Note note = fresh[0];
            ShowNote(string.IsNullOrWhiteSpace(note.Title) ? "Meldung vom Spark" : note.Title, note.Body);
        }
        else
        {
            string titles = string.Join(Environment.NewLine, fresh.TakeLast(5).Select(n => "• " + (n.Title.Length > 0 ? n.Title : n.Body)));
            ShowNote($"{fresh.Count} Meldungen vom Spark", titles);
        }
    }

    /// <summary>Texte vom Spark sind reiner Text; der Hinweis zeigt ohnehin nichts anderes an.</summary>
    private void ShowNote(string title, string body)
    {
        title = Clip(title.ReplaceLineEndings(" "), 63);
        body = Clip(body, 255);
        _tray.ShowBalloonTip(10000, title, body.Length == 0 ? " " : body, ToolTipIcon.Info);
    }

    private static string Clip(string text, int max) =>
        text.Length <= max ? text : text[..(max - 1)] + "…";

    /// <summary>Neue Einstellungen vom Spark übernehmen: speichern, Kürzel, Menü, Symbol, Autostart.</summary>
    private void ApplyConfig(DeskConfig desk)
    {
        _desk = desk;
        _config.Desk = desk;
        if (!string.IsNullOrEmpty(desk.Profile))
        {
            _config.Profile = desk.Profile;
        }

        TrySave();

        var before = new HashSet<string>(_conflicts);
        RegisterHotkeys(notify: false);
        NotifyConflicts(_conflicts.Except(before));

        if (!desk.IsOn(Parts.Dictate) && _recorder is not null)
        {
            CancelDictation("Diktieren wurde im Panel ausgeschaltet.");
        }

        _ask?.RefreshParts();
        ApplyAutostart(desk.Autostart);
        UpdateIcon();
        BuildMenu();
        Changed?.Invoke(this, EventArgs.Empty);
    }

    private static void ApplyAutostart(bool? wanted)
    {
        if (wanted is not { } on)
        {
            return;
        }

        try
        {
            if (Autostart.IsEnabled != on)
            {
                Autostart.Set(on);
            }
        }
        catch (Exception ex) when (ex is UnauthorizedAccessException or System.Security.SecurityException or IOException)
        {
            // Dann eben ohne Autostart; beim nächsten Abruf neuer Versuch.
        }
    }

    // ------------------------------------------------------------------ Fehler und Zustand

    /// <summary>
    /// Gemeinsame Behandlung von Fehlern des Spark (laut Vertrag): 401 Schlüssel vergessen und neu koppeln,
    /// 403 Einstellungen neu holen, 503 Notaus rot, Netzfehler grau. Die Meldung selbst zeigt der Aufrufer.
    /// </summary>
    private void Report(SparkException ex, bool fromPoll)
    {
        if (ex.IsUnknownDevice)
        {
            if (!_config.IsPaired)
            {
                return;
            }

            ForgetPairing();
            Notify(ex.Message, ToolTipIcon.Warning);
            _invoker.BeginInvoke(new Action(() => Pair(null, ex.Message)));
        }
        else if (ex.Status == 403)
        {
            if (!fromPoll)
            {
                PollSoon(refetchConfig: true);
            }
        }
        else if (ex.IsNotaus)
        {
            _slowPoll = true;
            SetConnection(Connection.Notaus, ex.Detail ?? ex.Message);
        }
        else if (ex.Status is null || (fromPoll && ex.Status >= 500))
        {
            SetConnection(Connection.Offline, ex.Message);
        }
    }

    private void ReportFromWindow(SparkException ex) => Report(ex, fromPoll: false);

    private void SetConnection(Connection connection, string text)
    {
        bool changed = connection != _connection || text != _connectionText;
        _connection = connection;
        _connectionText = text;
        if (changed)
        {
            UpdateIcon();
            BuildMenu();
            Changed?.Invoke(this, EventArgs.Empty);
        }
    }

    private string StatusLine() => _connection switch
    {
        Connection.Unpaired => "Nicht gekoppelt",
        Connection.Unknown => "Verbinde mit dem Spark …",
        Connection.Online => "Verbunden mit " + (_desk?.Profile ?? _config.Profile ?? "dem Spark"),
        Connection.Offline => "Spark nicht erreichbar",
        Connection.Notaus => _connectionText.Length > 0 ? _connectionText : "Notaus",
        _ => "",
    };

    private void UpdateIcon()
    {
        StatusDot dot = !IsOn(Parts.Status) ? StatusDot.None : _connection switch
        {
            Connection.Online => StatusDot.Green,
            Connection.Notaus => StatusDot.Red,
            _ => StatusDot.Grey,
        };
        _tray.Icon = AppIcon.ForTray(dot);
        _tray.Text = Clip(Title + " – " + StatusLine().ReplaceLineEndings(" "), 127);
    }

    // ------------------------------------------------------------------ Menü

    private void BuildMenu()
    {
        var old = _menu.Items.Cast<ToolStripItem>().ToList();
        _menu.Items.Clear();
        foreach (ToolStripItem item in old)
        {
            item.Dispose();
        }

        var status = new ToolStripMenuItem(Clip(StatusLine().ReplaceLineEndings(" "), 90)) { Enabled = false };
        _menu.Items.Add(status);
        _menu.Items.Add(new ToolStripSeparator());

        if (!_config.IsPaired)
        {
            var pair = new ToolStripMenuItem("Koppeln …", null, (_, _) => Pair(null));
            pair.Font = new Font(pair.Font, FontStyle.Bold);
            _menu.Items.Add(pair);
        }
        else
        {
            bool any = false;
            if (IsOn(Parts.Write))
            {
                _menu.Items.Add(new ToolStripMenuItem("Text verbessern …", null, (_, _) => OpenWriteWindow())
                {
                    ShortcutKeyDisplayString = _config.GetHotkey(Parts.Write).ToString(),
                });
                any = true;
            }

            if (IsOn(Parts.Ask))
            {
                _menu.Items.Add(new ToolStripMenuItem("Frag Spark …", null, (_, _) => OpenAsk())
                {
                    ShortcutKeyDisplayString = _config.GetHotkey(Parts.Ask).ToString(),
                });
                any = true;
            }

            if (IsOn(Parts.Dictate))
            {
                string text = _recorder is not null ? "Diktat beenden" : "Diktieren (in die Zwischenablage)";
                _menu.Items.Add(new ToolStripMenuItem(text, null, async (_, _) => await ToggleDictationAsync(IntPtr.Zero))
                {
                    ShortcutKeyDisplayString = _config.GetHotkey(Parts.Dictate).ToString(),
                    Enabled = !_dictateBusy,
                });
                any = true;
            }

            if (IsOn(Parts.Notaus))
            {
                _menu.Items.Add(new ToolStripMenuItem("Mein Notaus auslösen …", null, async (_, _) => await TriggerNotausAsync()));
                any = true;
            }

            if (_desk is not null && Parts.All.Any(p => !_desk.IsOn(p)))
            {
                _menu.Items.Add(new ToolStripMenuItem(any ? "Weitere Teile: im Panel unter Ich → Begleiter" : "Teile im Panel unter Ich → Begleiter einschalten")
                {
                    Enabled = false,
                });
            }

            if (_connection == Connection.Notaus)
            {
                _menu.Items.Add(new ToolStripMenuItem("Panel öffnen (Notaus aufheben) …", null, (_, _) => OpenPanel()));
            }
        }

        _menu.Items.Add(new ToolStripSeparator());
        _menu.Items.Add(new ToolStripMenuItem("Einstellungen …", null, (_, _) => OpenSettings()));
        _menu.Items.Add(new ToolStripMenuItem("Beenden", null, (_, _) => ExitThread()));
    }

    private void OnLeftClick()
    {
        if (!_config.IsPaired)
        {
            Pair(null);
        }
        else if (IsOn(Parts.Write))
        {
            OpenWriteWindow();
        }
        else if (IsOn(Parts.Ask))
        {
            OpenAsk();
        }
        else
        {
            OpenSettings();
        }
    }

    // ------------------------------------------------------------------ Tastenkürzel

    /// <summary>Registriert die Kürzel der eingeschalteten Teile und gibt die der ausgeschalteten frei.</summary>
    private void RegisterHotkeys(bool notify)
    {
        var before = new HashSet<string>(_conflicts);
        _conflicts.Clear();
        foreach (string part in Parts.WithHotkey)
        {
            if (_hotkeysSuspended || !IsOn(part))
            {
                _hotkeys.Unregister(part);
                continue;
            }

            if (!_hotkeys.Register(part, _config.GetHotkey(part)))
            {
                _conflicts.Add(part);
            }
        }

        if (notify)
        {
            NotifyConflicts(_conflicts.Except(before));
        }
    }

    private void NotifyConflicts(IEnumerable<string> parts)
    {
        var list = parts.ToList();
        if (list.Count == 0)
        {
            return;
        }

        string names = string.Join(", ", list.Select(p => $"{_config.GetHotkey(p)} ({Parts.Label(p)})"));
        Notify($"Schon von einem anderen Programm belegt: {names}. In den Einstellungen eine andere Kombination wählen.",
            ToolTipIcon.Warning);
    }

    public string? ChangeHotkey(string part, Hotkey hotkey)
    {
        if (!hotkey.IsValid)
        {
            return "Bitte mit Strg oder Alt kombinieren (z. B. Strg+Alt+S).";
        }

        foreach (string other in Parts.WithHotkey.Where(p => p != part))
        {
            if (_config.GetHotkey(other) == hotkey)
            {
                return $"{hotkey} ist schon für {Parts.Label(other)} vergeben.";
            }
        }

        Hotkey old = _config.GetHotkey(part);
        if (hotkey != old || _conflicts.Contains(part))
        {
            // Probe: lässt sich die Kombination registrieren? (Auch für ausgeschaltete Teile, damit der Konflikt sichtbar ist.)
            _hotkeys.Unregister(part);
            if (!_hotkeys.Register(part, hotkey))
            {
                RegisterHotkeys(notify: false);
                return $"{hotkey} ist schon von einem anderen Programm (oder Windows) belegt.";
            }
        }

        _config.SetHotkey(part, hotkey);
        TrySave();
        _hotkeys.Unregister(part);
        RegisterHotkeys(notify: false);
        BuildMenu();
        return null;
    }

    public void SuspendHotkeys(bool suspend)
    {
        if (_hotkeysSuspended == suspend)
        {
            return;
        }

        _hotkeysSuspended = suspend;
        if (suspend)
        {
            _hotkeys.UnregisterAll();
        }
        else
        {
            RegisterHotkeys(notify: false);
        }
    }

    private async Task OnHotkeyAsync(string part)
    {
        if (!IsOn(part) || _pairOpen)
        {
            return;
        }

        try
        {
            switch (part)
            {
                case Parts.Write:
                    await WriteFromHotkeyAsync();
                    break;
                case Parts.Ask:
                    OpenAsk();
                    break;
                case Parts.Dictate:
                    await ToggleDictationAsync(NativeMethods.GetForegroundWindow());
                    break;
            }
        }
        catch (Exception ex) when (ex is InvalidOperationException or System.ComponentModel.Win32Exception or IOException or ObjectDisposedException)
        {
            // Ein Fehler hier darf das Programm nicht beenden.
            Notify("Das hat nicht geklappt: " + ex.Message, ToolTipIcon.Error);
        }
    }

    // ------------------------------------------------------------------ Schreibhilfe

    /// <summary>
    /// Tastenkürzel der Schreibhilfe: markierten Text holen; mit Vorschau das Fenster zeigen,
    /// ohne Vorschau direkt mit den Voreinstellungen aus dem Panel verbessern und einfügen.
    /// </summary>
    private async Task WriteFromHotkeyAsync()
    {
        if (_writing)
        {
            Notify("Die Schreibhilfe arbeitet noch.", ToolTipIcon.Info);
            return;
        }

        IntPtr target = NativeMethods.GetForegroundWindow();

        // Ist das eigene Fenster schon vorne, nichts kopieren – nur nach vorn holen.
        if (_assist is { IsDisposed: false } open)
        {
            if (target == open.Handle)
            {
                open.Activate();
                return;
            }

            open.Close();
        }

        DeskConfig desk = _desk!;
        _writing = true;
        try
        {
            ushort vk = _config.GetHotkey(Parts.Write).VirtualKey;
            string? text = await ClipboardHelper.CopySelectionAsync(vk);
            if (desk.WritePreview)
            {
                ShowAssist(text, target);
            }
            else if (string.IsNullOrWhiteSpace(text))
            {
                Notify("Kein Text markiert. Text markieren und das Tastenkürzel noch einmal drücken.", ToolTipIcon.Info);
            }
            else
            {
                await WriteDirectAsync(desk, text, target);
            }
        }
        finally
        {
            _writing = false;
        }
    }

    /// <summary>Ohne Vorschau: verbessern und sofort an der Stelle der Markierung einfügen.</summary>
    private async Task WriteDirectAsync(DeskConfig desk, string text, IntPtr target)
    {
        string? key = _config.GetKey();
        if (key is null || string.IsNullOrEmpty(_config.Base))
        {
            return;
        }

        string core = text.Trim();
        int start = text.IndexOf(core, StringComparison.Ordinal);
        string lead = text[..start];
        string trail = text[(start + core.Length)..];
        string art = desk.OfferedArts().Any(a => a.Id == desk.WriteArt) ? desk.WriteArt : desk.OfferedArts()[0].Id;
        string? sprache = art == DeskConfig.TranslateArt ? desk.WriteSprache : null;

        _tray.Text = Clip(Title + " – Der Spark schreibt …", 127);
        try
        {
            AssistResult result = await SparkClient.AssistAsync(_config.Base, key, core, art, sprache, desk.WriteWunsch, CancellationToken.None);
            string improved = result.Text.Trim();
            if (result.Changes == 0 || improved == core)
            {
                Notify("Keine Änderungen nötig.", ToolTipIcon.Info);
                return;
            }

            await ApplyAsync(lead + improved + trail, target, _config.GetHotkey(Parts.Write).VirtualKey);
        }
        catch (SparkException ex)
        {
            Notify(ex.Message, ToolTipIcon.Warning);
            Report(ex, fromPoll: false);
        }
        finally
        {
            UpdateIcon();
        }
    }

    /// <summary>Menü/Linksklick: Fenster ohne markierten Text (das Ergebnis landet in der Zwischenablage).</summary>
    private void OpenWriteWindow()
    {
        if (_assist is { IsDisposed: false } existing)
        {
            existing.Activate();
            return;
        }

        ShowAssist(null, IntPtr.Zero);
    }

    /// <summary>Zeigt das Fenster. <paramref name="target"/> = Fenster, in das später eingefügt wird (oder keins).</summary>
    private void ShowAssist(string? text, IntPtr target)
    {
        if (_desk is null || !_config.IsPaired)
        {
            return;
        }

        if (_assist is { IsDisposed: false } existing)
        {
            existing.Close();
        }

        var form = new AssistForm(_config, _desk, text ?? "", target, ReportFromWindow);
        form.FormClosed += async (_, _) =>
        {
            if (ReferenceEquals(_assist, form))
            {
                _assist = null;
            }

            string? result = form.TextToApply;
            if (result is not null)
            {
                await ApplyAsync(result, form.Target, _config.GetHotkey(Parts.Write).VirtualKey);
            }

            form.Dispose();
        };
        _assist = form;
        form.Show();
        form.Activate();
    }

    /// <summary>Ergebnis in das gemerkte Fenster einfügen, sonst in der Zwischenablage lassen.</summary>
    private async Task ApplyAsync(string text, IntPtr target, ushort hotkeyKey)
    {
        try
        {
            await KeyboardInput.WaitForHotkeyReleaseAsync(hotkeyKey, timeoutMs: 1500);
            bool pasted = await ClipboardHelper.PasteIntoAsync(target, text);
            if (!pasted)
            {
                Notify("Der Text liegt in der Zwischenablage – mit Strg+V einfügen.", ToolTipIcon.Info);
            }
        }
        catch (Exception ex) when (ex is InvalidOperationException or System.Runtime.InteropServices.ExternalException)
        {
            Notify("Der Text konnte nicht eingefügt werden: " + ex.Message, ToolTipIcon.Error);
        }
    }

    // ------------------------------------------------------------------ Frag Spark

    private void OpenAsk()
    {
        if (!IsOn(Parts.Ask))
        {
            return;
        }

        if (_ask is { IsDisposed: false } open)
        {
            open.Bring();
            return;
        }

        var form = new AskForm(_config, () => _desk, ReportFromWindow);
        form.FormClosed += (_, _) =>
        {
            if (ReferenceEquals(_ask, form))
            {
                _ask = null;
            }

            form.Dispose();
        };
        _ask = form;
        form.Show();
        form.Bring();
    }

    // ------------------------------------------------------------------ Diktieren

    /// <summary>
    /// Erster Druck: Aufnahme starten (Hinweis unten rechts), zweiter Druck: beenden, an den Spark schicken
    /// und den erkannten Text in das Fenster einfügen, das beim Start vorne war.
    /// </summary>
    private async Task ToggleDictationAsync(IntPtr target)
    {
        if (_dictateBusy)
        {
            Notify("Der Spark erkennt noch das letzte Diktat.", ToolTipIcon.Info);
            return;
        }

        if (_recorder is null)
        {
            StartDictation(target);
        }
        else
        {
            await FinishDictationAsync();
        }
    }

    private void StartDictation(IntPtr target)
    {
        Recorder? recorder = Recorder.TryStart(out string error);
        if (recorder is null)
        {
            Notify(error, ToolTipIcon.Warning);
            return;
        }

        _recorder = recorder;
        _dictateTarget = target;
        recorder.LimitReached += async (_, _) =>
        {
            if (ReferenceEquals(_recorder, recorder))
            {
                await FinishDictationAsync();
            }
        };

        _indicator = new RecordingIndicator(_config.GetHotkey(Parts.Dictate).ToString(), () => recorder.Elapsed);
        _indicator.StopRequested += async (_, _) =>
        {
            if (ReferenceEquals(_recorder, recorder))
            {
                await FinishDictationAsync();
            }
        };
        _indicator.Show();
        BuildMenu();
    }

    private async Task FinishDictationAsync()
    {
        Recorder? recorder = _recorder;
        if (recorder is null)
        {
            return;
        }

        _recorder = null;
        _dictateBusy = true;
        _indicator?.ShowWorking();
        BuildMenu();
        try
        {
            byte[]? wav;
            try
            {
                wav = await recorder.StopAsync();
            }
            finally
            {
                recorder.Dispose();
            }

            if (wav is null)
            {
                Notify("Die Aufnahme war zu kurz.", ToolTipIcon.Info);
                return;
            }

            string? key = _config.GetKey();
            if (key is null || string.IsNullOrEmpty(_config.Base))
            {
                return;
            }

            string text = (await SparkClient.DictateAsync(_config.Base, key, wav, _desk?.DictateSprache ?? "auto", CancellationToken.None)).Trim();
            CloseIndicator();
            if (text.Length == 0)
            {
                Notify("Es wurde nichts erkannt.", ToolTipIcon.Info);
                return;
            }

            await ApplyAsync(text, _dictateTarget, _config.GetHotkey(Parts.Dictate).VirtualKey);
        }
        catch (SparkException ex)
        {
            Notify(ex.Message, ToolTipIcon.Warning);
            Report(ex, fromPoll: false);
        }
        finally
        {
            CloseIndicator();
            _dictateBusy = false;
            _dictateTarget = IntPtr.Zero;
            BuildMenu();
        }
    }

    private void CancelDictation(string message)
    {
        Recorder? recorder = _recorder;
        _recorder = null;
        recorder?.Dispose();
        CloseIndicator();
        Notify(message, ToolTipIcon.Info);
    }

    private void CloseIndicator()
    {
        if (_indicator is not null)
        {
            _indicator.Close();
            _indicator.Dispose();
            _indicator = null;
        }
    }

    // ------------------------------------------------------------------ Mein Notaus

    private async Task TriggerNotausAsync()
    {
        DialogResult answer = MessageBox.Show(
            "Mein Notaus hält das ganze Profil am Spark an: Gespräche, Schreibhilfe, Diktieren und alle Geräte "
            + "dieses Profils werden gesperrt.\n\nAufheben geht nur im Panel im Browser mit der PIN.\n\nJetzt auslösen?",
            Title + " – Mein Notaus", MessageBoxButtons.YesNo, MessageBoxIcon.Warning, MessageBoxDefaultButton.Button2);
        if (answer != DialogResult.Yes)
        {
            return;
        }

        string? key = _config.GetKey();
        if (key is null || string.IsNullOrEmpty(_config.Base))
        {
            return;
        }

        try
        {
            await SparkClient.NotausAsync(_config.Base, key, CancellationToken.None);
            _slowPoll = true;
            SetConnection(Connection.Notaus, "Mein Notaus ist an");
            ScheduleNextPoll();
            DialogResult open = MessageBox.Show(
                "Mein Notaus ist an. Aufheben nur im Panel im Browser mit der PIN.\n\nPanel jetzt öffnen?",
                Title, MessageBoxButtons.YesNo, MessageBoxIcon.Information, MessageBoxDefaultButton.Button2);
            if (open == DialogResult.Yes)
            {
                OpenPanel();
            }
        }
        catch (SparkException ex)
        {
            Report(ex, fromPoll: false);
            MessageBox.Show(ex.Message, Title, MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
    }

    // ------------------------------------------------------------------ Kopplung und Einstellungen

    public void OpenPanel()
    {
        if (string.IsNullOrEmpty(_config.Base) ||
            !SparkAddress.TryParse(_config.Base, out SparkAddress.Parsed parsed, out _))
        {
            return;
        }

        try
        {
            using Process? browser = Process.Start(new ProcessStartInfo(parsed.Base + "/") { UseShellExecute = true });
        }
        catch (System.ComponentModel.Win32Exception ex)
        {
            Notify("Der Browser ließ sich nicht öffnen: " + ex.Message, ToolTipIcon.Error);
        }
    }

    private void OpenSettings()
    {
        if (_settings is { IsDisposed: false } open)
        {
            open.Activate();
            return;
        }

        var form = new SettingsForm(this);
        form.FormClosed += (_, _) =>
        {
            if (ReferenceEquals(_settings, form))
            {
                _settings = null;
            }

            form.Dispose();
        };
        _settings = form;
        form.Show();
        form.Activate();
    }

    public bool Pair(IWin32Window? owner) => Pair(owner, null);

    /// <summary>Koppeln/Neu koppeln. Gibt <c>true</c> zurück, wenn neu gekoppelt wurde.</summary>
    private bool Pair(IWin32Window? owner, string? message)
    {
        if (_pairOpen)
        {
            return false;
        }

        _pairOpen = true;
        try
        {
            using var dialog = new PairForm(_config, message);
            if (dialog.ShowDialog(owner) != DialogResult.OK)
            {
                return false;
            }

            // Neu gekoppelt: Zustand zurücksetzen und gleich abfragen.
            _desk = _config.Desk;
            _lastNote = -1;
            SetConnection(Connection.Unknown, "");
            RegisterHotkeys(notify: true);
            Notify($"Gekoppelt{(string.IsNullOrEmpty(_config.Profile) ? "" : " mit " + _config.Profile)}. "
                   + "Welche Teile an sind, steht im Panel unter Ich → Begleiter.", ToolTipIcon.Info);
            PollSoon(refetchConfig: true);
            Changed?.Invoke(this, EventArgs.Empty);
            return true;
        }
        finally
        {
            _pairOpen = false;
        }
    }

    public void Unpair(IWin32Window? owner)
    {
        DialogResult answer = MessageBox.Show(owner,
            "Den Begleiter vom Spark entkoppeln? Der Schlüssel wird auf diesem PC gelöscht und "
            + "„Mit Windows starten“ ausgeschaltet.\n\n"
            + "Im Panel unter Ich → Begleiter lässt sich das Gerät danach auch dort entfernen.",
            Title, MessageBoxButtons.YesNo, MessageBoxIcon.Question, MessageBoxDefaultButton.Button2);
        if (answer != DialogResult.Yes)
        {
            return;
        }

        ForgetPairing();
        ApplyAutostart(false);
    }

    /// <summary>Schlüssel und Spark-Einstellungen vergessen (Adresse und Gerätename bleiben zum Neu-Koppeln).</summary>
    private void ForgetPairing()
    {
        _pollTimer.Stop();
        if (_recorder is not null)
        {
            CancelDictation("Diktat abgebrochen.");
        }

        _assist?.Close();
        _ask?.Close();
        _config.ForgetKey();
        _config.Desk = null;
        _config.Profile = null;
        TrySave();
        _desk = null;
        _lastNote = -1;
        _needConfig = true;
        _hotkeys.UnregisterAll();
        _conflicts.Clear();
        SetConnection(Connection.Unpaired, "");
        UpdateIcon();
        BuildMenu();
        Changed?.Invoke(this, EventArgs.Empty);
    }

    // ------------------------------------------------------------------ Hilfen

    private void TrySave()
    {
        try
        {
            _config.Save();
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            Notify("Die Einstellungen konnten nicht gespeichert werden: " + ex.Message, ToolTipIcon.Error);
        }
    }

    private void Notify(string text, ToolTipIcon icon) =>
        _tray.ShowBalloonTip(5000, Title, Clip(text, 255), icon);

    protected override void ExitThreadCore()
    {
        _pollTimer.Stop();
        _recorder?.Dispose();
        _recorder = null;
        CloseIndicator();
        _assist?.Close();
        _ask?.Close();
        _settings?.Close();
        _tray.Visible = false;
        base.ExitThreadCore();
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            _pollTimer.Dispose();
            _hotkeys.Dispose();
            _menu.Dispose();
            _tray.Dispose();
            _invoker.Dispose();
        }

        base.Dispose(disposing);
    }
}
