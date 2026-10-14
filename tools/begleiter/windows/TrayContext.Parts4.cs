using System.Diagnostics;
using System.Globalization;
using Microsoft.Win32;

namespace SparkBegleiter;

/// <summary>
/// Version 4: Vorlesen, Vom Handy auf den PC, Termine im Begleiter, Nicht stören erkennen, Besprechung mitschreiben,
/// Smart-Home-Knöpfe, Tagesstart und Feierabend. Jeder Teil ist aus, bis das Panel ihn einschaltet; ein
/// ausgeschalteter Teil hat kein Tastenkürzel, keinen Menüeintrag, keinen Abschnitt im Fenster und läuft nicht.
/// </summary>
internal sealed partial class TrayContext
{
    private static readonly CultureInfo German = CultureInfo.GetCultureInfo("de-DE");

    // speak
    private SpeakPlayer? _speaker;
    private FloatingPill? _speakPill;
    private CancellationTokenSource? _speakCts;

    // inbox
    private readonly Queue<InboxItem> _inboxQueue = new();
    private readonly HashSet<string> _inboxActive = new(StringComparer.Ordinal);
    private bool _inboxBusy;

    // agenda
    private readonly System.Windows.Forms.Timer _agendaTimer = new() { Interval = 5 * 60 * 1000 };
    private readonly System.Windows.Forms.Timer _alertTimer = new() { Interval = 30 * 1000 };
    private readonly HashSet<string> _alerted = new(StringComparer.Ordinal);
    private AgendaResult? _agenda;
    private string? _agendaError;
    private bool _agendaLoading;

    // quiet
    private string? _quietWhy;
    private bool _quietSent;

    // meeting
    private MeetingSession? _meeting;
    private bool _meetingStarting;

    // home
    private IReadOnlyList<HomeState>? _homeStates;
    private string? _homeNote;
    private bool _homeBusy;

    // daily
    private bool _dailyHooked;
    private bool _dailyBusy;
    private bool _firstPollDone;

    // act: Programmliste
    private bool _appsActOn;
    private bool _appsSending;
    private DateTime _appsSentAt = DateTime.MinValue;

    /// <summary>Was ein Klick auf den nächsten Hinweis tun soll (z. B. Ordner öffnen).</summary>
    private Action? _balloonAction;

    /// <summary>Eine laufende Besprechung.</summary>
    private sealed class MeetingSession
    {
        public MeetingSession(string id, MeetingRecorder recorder, FloatingPill pill)
        {
            Id = id;
            Recorder = recorder;
            Pill = pill;
        }

        public string Id { get; }

        public MeetingRecorder Recorder { get; }

        public FloatingPill Pill { get; }

        public Queue<byte[]> Pending { get; } = new();

        public bool Uploading { get; set; }

        public bool Ending { get; set; }

        public bool Aborted { get; set; }

        public bool DropWarned { get; set; }
    }

    // ------------------------------------------------------------------ an/aus

    private void SyncParts4()
    {
        // act: Programmliste beim Einschalten (und beim Start) schicken
        if (IsOn(Parts.Act) && !_appsActOn)
        {
            _appsActOn = true;
            _ = SendAppsAsync();
        }
        else if (!IsOn(Parts.Act))
        {
            _appsActOn = false;
        }

        // speak
        if (!IsOn(Parts.Speak))
        {
            StopSpeaking();
        }

        // inbox
        if (!IsOn(Parts.Inbox))
        {
            _inboxQueue.Clear();
        }

        // agenda
        if (IsOn(Parts.Agenda))
        {
            if (!_agendaTimer.Enabled)
            {
                _agendaTimer.Start();
                _alertTimer.Start();
                _ = RefreshAgendaAsync();
            }
        }
        else
        {
            _agendaTimer.Stop();
            _alertTimer.Stop();
            _agenda = null;
            _agendaError = null;
        }

        // quiet: Mond aus, Ende meldet die nächste Abfrage
        if (!IsOn(Parts.Quiet))
        {
            _quietWhy = null;
        }

        // meeting
        if (!IsOn(Parts.Meeting) && _meeting is { Ending: false } running)
        {
            AbortMeeting(running, "Besprechung mitschreiben wurde im Panel ausgeschaltet – die Aufnahme ist beendet.");
        }

        // home
        if (!IsOn(Parts.Home))
        {
            _homeStates = null;
            _homeNote = null;
        }

        // daily
        if (IsOn(Parts.Daily) && !_dailyHooked)
        {
            SystemEvents.SessionSwitch += OnSessionSwitch;
            _dailyHooked = true;
        }
        else if (!IsOn(Parts.Daily) && _dailyHooked)
        {
            SystemEvents.SessionSwitch -= OnSessionSwitch;
            _dailyHooked = false;
        }
    }

    private void StopParts4()
    {
        StopSpeaking();
        _inboxQueue.Clear();
        _agendaTimer.Stop();
        _alertTimer.Stop();
        _agenda = null;
        if (_meeting is { } meeting)
        {
            AbortMeeting(meeting, null);
        }

        _homeStates = null;
        _quietWhy = null;
        if (_dailyHooked)
        {
            SystemEvents.SessionSwitch -= OnSessionSwitch;
            _dailyHooked = false;
        }
    }

    private void DisposeParts4()
    {
        _agendaTimer.Dispose();
        _alertTimer.Dispose();
        _speakCts?.Dispose();
        _speakCts = null;
    }

    /// <summary>Hinweis, dessen Klick etwas tut (z. B. „Ordner öffnen“).</summary>
    private void NotifyWithAction(string text, Action action)
    {
        Notify(text, ToolTipIcon.Info);
        _balloonAction = action;
    }

    // ------------------------------------------------------------------ Menü und Tray-Fenster

    private bool AddPartMenuItems4()
    {
        bool any = false;
        if (IsOn(Parts.Speak))
        {
            bool active = _speaker is not null || _speakCts is not null;
            _menu.Items.Add(new ToolStripMenuItem(active ? "Vorlesen stoppen" : "Zwischenablage vorlesen", null, async (_, _) => await SpeakAsync(fromHotkey: false))
            {
                ShortcutKeyDisplayString = _config.GetHotkey(Parts.Speak).ToString(),
            });
            any = true;
        }

        if (IsOn(Parts.Meeting))
        {
            _menu.Items.Add(new ToolStripMenuItem(_meeting is null ? "Besprechung mitschreiben …" : "Besprechung beenden", null, async (_, _) => await ToggleMeetingAsync())
            {
                ShortcutKeyDisplayString = _config.GetHotkey(Parts.Meeting).ToString(),
                Enabled = !_meetingStarting && _meeting?.Ending != true,
            });
            any = true;
        }

        return any;
    }

    private void AddPanelItems4(List<PanelItem> items)
    {
        if (IsOn(Parts.Speak))
        {
            bool active = _speaker is not null || _speakCts is not null;
            items.Add(new PanelItem(active ? "Vorlesen stoppen" : "Zwischenablage vorlesen", Glyph.Speaker,
                _config.GetHotkey(Parts.Speak).ToString(), () => _ = SpeakAsync(fromHotkey: false)));
        }

        if (IsOn(Parts.Meeting))
        {
            items.Add(new PanelItem(_meeting is null ? "Besprechung mitschreiben" : "Besprechung beenden", Glyph.Record,
                _config.GetHotkey(Parts.Meeting).ToString(), () => _ = ToggleMeetingAsync(),
                Danger: _meeting is not null, Enabled: !_meetingStarting && _meeting?.Ending != true));
        }
    }

    /// <summary>Zeilen für „Als Nächstes“: Termine und Erinnerungen der nächsten 24 Stunden, zeitlich sortiert.</summary>
    private IReadOnlyList<PanelLine>? BuildAgendaLines()
    {
        if (!IsOn(Parts.Agenda))
        {
            return null;
        }

        if (_agenda is not { } agenda)
        {
            return Array.Empty<PanelLine>();
        }

        DateTimeOffset now = DateTimeOffset.Now;
        var rows = new List<(DateTimeOffset At, PanelLine Line)>();
        foreach (AgendaEvent e in agenda.Events)
        {
            DateTimeOffset end = e.End ?? e.Start.AddMinutes(30);
            if (end < now)
            {
                continue;
            }

            string when = e.Start <= now ? "jetzt" : WhenText(e.Start, now);
            rows.Add((e.Start, new PanelLine(when, e.Title.Length > 0 ? e.Title : "Termin", e.Where)));
        }

        foreach (AgendaReminder r in agenda.Reminders)
        {
            if (r.Due < now.AddMinutes(-5))
            {
                continue;
            }

            rows.Add((r.Due, new PanelLine(WhenText(r.Due, now), r.Text.Length > 0 ? r.Text : "Erinnerung", "Erinnerung")));
        }

        return rows.OrderBy(r => r.At).Take(6).Select(r => r.Line).ToList();
    }

    private static string WhenText(DateTimeOffset at, DateTimeOffset now)
    {
        DateTime local = at.ToLocalTime().DateTime;
        if (local.Date == now.LocalDateTime.Date)
        {
            return local.ToString("HH:mm", German);
        }

        return (local.Date == now.LocalDateTime.Date.AddDays(1) ? "morgen " : local.ToString("ddd ", German)) + local.ToString("HH:mm", German);
    }

    private string? AgendaEmptyText() => _agendaError ?? (_agenda is null ? "Wird geladen …" : "Nichts in den nächsten 24 Stunden.");

    /// <summary>Knöpfe für „Zuhause“: Liste aus dem Panel (config.home.buttons), Zustand aus GET /api/desk/home.</summary>
    private List<PanelHomeButton>? BuildHomeButtons()
    {
        if (!IsOn(Parts.Home) || _desk is null)
        {
            return null;
        }

        var list = new List<PanelHomeButton>();
        IEnumerable<(string Id, string Name, string Kind)> buttons = _desk.HomeButtons.Count > 0
            ? _desk.HomeButtons.Select(b => (b.Id, b.Name, b.Kind))
            : (_homeStates ?? Array.Empty<HomeState>()).Select(s => (s.Id, s.Name.Length > 0 ? s.Name : s.Id, s.Kind));
        foreach (var (id, name, kind) in buttons)
        {
            HomeState? state = _homeStates?.FirstOrDefault(s => s.Id == id);
            string button = id;
            list.Add(new PanelHomeButton(name, kind == "toggle", state?.On, !_homeBusy, () => _ = PressHomeAsync(button, name)));
        }

        return list;
    }

    private string? HomeNoteText()
    {
        if (_homeNote is not null)
        {
            return _homeNote;
        }

        if (_desk is { HomeButtons.Count: 0 } && _homeStates is { Count: 0 })
        {
            return "Noch keine Knöpfe – im Panel unter Ich → Begleiter festlegen.";
        }

        return _homeStates is null && _desk?.HomeButtons.Count == 0 ? "Wird geladen …" : null;
    }

    /// <summary>„Nicht stören“-Zeile für das Tray-Fenster.</summary>
    private string? QuietHint() => IsOn(Parts.Quiet) && _quietWhy is { } why
        ? (why == "call" ? "Nicht stören: Telefonat erkannt" : "Nicht stören: Präsentation erkannt") + " – Meldungen warten beim Spark."
        : null;

    /// <summary>Beim Öffnen des Tray-Fensters: Zustände der Zuhause-Knöpfe auffrischen.</summary>
    private void OnPanelOpened()
    {
        if (IsOn(Parts.Home))
        {
            _ = RefreshHomeAsync();
        }
    }

    // ------------------------------------------------------------------ speak: Vorlesen

    /// <summary>
    /// Tastenkürzel: markierten Text vorlesen; Menü/Fenster: den Text in der Zwischenablage. Läuft schon etwas
    /// (Laden oder Abspielen), stoppt derselbe Aufruf es.
    /// </summary>
    private async Task SpeakAsync(bool fromHotkey)
    {
        if (!IsOn(Parts.Speak))
        {
            return;
        }

        if (_speaker is not null || _speakCts is not null)
        {
            StopSpeaking();
            return;
        }

        string? text;
        if (fromHotkey)
        {
            _speakCts = new CancellationTokenSource(); // sperrt einen zweiten Start während des Kopierens
            try
            {
                text = await ClipboardHelper.CopySelectionAsync(_config.GetHotkey(Parts.Speak).VirtualKey);
            }
            finally
            {
                _speakCts.Dispose();
                _speakCts = null;
            }
        }
        else
        {
            try
            {
                text = Clipboard.ContainsText() ? Clipboard.GetText() : null;
            }
            catch (System.Runtime.InteropServices.ExternalException)
            {
                text = null;
            }
        }

        text = text?.Trim();
        if (string.IsNullOrEmpty(text))
        {
            Notify(fromHotkey ? "Kein Text markiert. Text markieren und das Tastenkürzel noch einmal drücken."
                : "In der Zwischenablage ist kein Text.", ToolTipIcon.Info);
            return;
        }

        await SpeakTextAsync(text);
    }

    /// <summary>
    /// Text vom Spark vorlesen lassen und abspielen (Pille mit „Stop“). Läuft schon etwas, wird es vorher beendet.
    /// Auch für „Antworten vorlesen“ im Fenster Frag Spark.
    /// </summary>
    private async Task SpeakTextAsync(string text)
    {
        if (!IsOn(Parts.Speak) || text.Trim().Length == 0)
        {
            return;
        }

        StopSpeaking();
        text = text.Trim();
        if (text.Length > 5000)
        {
            text = text[..5000];
        }

        if (Credentials() is not { } creds)
        {
            return;
        }

        var cts = new CancellationTokenSource();
        _speakCts = cts;
        ShowSpeakPill("Spark bereitet das Vorlesen vor …", "Abbrechen", null);
        BuildMenu();
        try
        {
            byte[] wav = await SparkClient.SpeakAsync(creds.Base, creds.Key, text, cts.Token);
            if (cts.IsCancellationRequested || !ReferenceEquals(_speakCts, cts))
            {
                return;
            }

            SpeakPlayer? player = SpeakPlayer.TryPlay(wav, out string error);
            if (player is null)
            {
                Notify(error, ToolTipIcon.Warning);
                return;
            }

            _speaker = player;
            var clock = Stopwatch.StartNew();
            ShowSpeakPill("Spark liest vor", "Stop", () => clock.Elapsed);
            player.Finished += (_, _) =>
            {
                if (ReferenceEquals(_speaker, player))
                {
                    _speaker = null;
                    CloseSpeakPill();
                    BuildMenu();
                }

                player.Dispose();
            };
        }
        catch (OperationCanceledException)
        {
            // gestoppt
        }
        catch (SparkException ex)
        {
            if (!cts.IsCancellationRequested)
            {
                Notify(ex.Message, ToolTipIcon.Warning);
                Report(ex, fromPoll: false);
            }
        }
        finally
        {
            if (ReferenceEquals(_speakCts, cts))
            {
                _speakCts = null;
            }

            cts.Dispose();
            if (_speaker is null && _speakCts is null)
            {
                CloseSpeakPill(); // nur, wenn nicht inzwischen ein neues Vorlesen läuft
            }

            BuildMenu();
        }
    }

    private void StopSpeakingAndMenu()
    {
        if (_speaker is not null || _speakCts is not null)
        {
            StopSpeaking();
            BuildMenu();
        }
    }

    /// <summary>„Antworten vorlesen“ (immer / nur bei gesprochenen Fragen / nie) lokal speichern.</summary>
    public void SetAskSpeak(string mode)
    {
        _config.AskSpeak = AskSpeakModes.Normalize(mode);
        TrySave();
        _ask?.RefreshParts();
        Changed?.Invoke(this, EventArgs.Empty);
    }

    private void StopSpeaking()
    {
        try
        {
            _speakCts?.Cancel();
        }
        catch (ObjectDisposedException)
        {
            // schon fertig
        }

        SpeakPlayer? player = _speaker;
        _speaker = null;
        player?.Stop();
        CloseSpeakPill();
    }

    private void ShowSpeakPill(string label, string button, Func<TimeSpan>? clock)
    {
        CloseSpeakPill();
        var pill = new FloatingPill(label, button, PillPlace.BottomRight, danger: false, clock: clock);
        pill.ButtonClicked += (_, _) =>
        {
            StopSpeaking();
            BuildMenu();
        };
        _speakPill = pill;
        pill.Show();
    }

    private void CloseSpeakPill()
    {
        if (_speakPill is not null)
        {
            _speakPill.Close();
            _speakPill.Dispose();
            _speakPill = null;
        }
    }

    // ------------------------------------------------------------------ inbox: Vom Handy auf den PC

    private void HandleInbox(IReadOnlyList<InboxItem> items)
    {
        if (items.Count == 0 || !IsOn(Parts.Inbox))
        {
            return;
        }

        foreach (InboxItem item in items)
        {
            if (_inboxActive.Contains(item.Id))
            {
                continue;
            }

            if (InboxStore.IsSeen(item.Id))
            {
                // Schon gezeigt, aber „erledigt“ kam beim Spark nicht an: nur noch einmal melden.
                _ = InboxDoneAsync(item.Id);
                continue;
            }

            _inboxActive.Add(item.Id);
            _inboxQueue.Enqueue(item);
        }

        if (!_inboxBusy && _inboxQueue.Count > 0)
        {
            _ = ProcessInboxAsync();
        }
    }

    private async Task ProcessInboxAsync()
    {
        _inboxBusy = true;
        try
        {
            while (_inboxQueue.Count > 0)
            {
                InboxItem item = _inboxQueue.Dequeue();
                try
                {
                    if (IsOn(Parts.Inbox) && await HandleInboxItemAsync(item))
                    {
                        InboxStore.MarkSeen(item.Id);
                        await InboxDoneAsync(item.Id);
                    }
                }
                finally
                {
                    _inboxActive.Remove(item.Id);
                }
            }
        }
        finally
        {
            _inboxBusy = false;
        }
    }

    /// <summary>Ein Eintrag: <c>true</c> = erledigt (auch abgelehnt), <c>false</c> = später noch einmal versuchen.</summary>
    private async Task<bool> HandleInboxItemAsync(InboxItem item)
    {
        switch (item.Kind)
        {
            case "text":
            {
                string text = item.Text ?? "";
                if (text.Length == 0)
                {
                    return true;
                }

                if (!ClipboardHelper.TrySetText(text, keepOutOfHistory: false))
                {
                    Notify("Vom Spark kam Text, aber die Zwischenablage ist gerade belegt. Gleich noch einmal …", ToolTipIcon.Info);
                    return false;
                }

                Notify("Vom Spark: Text liegt in der Zwischenablage", ToolTipIcon.Info);
                return true;
            }

            case "link":
            {
                string link = (item.Text ?? "").Trim();
                bool web = Uri.TryCreate(link, UriKind.Absolute, out Uri? uri) && uri.UserInfo.Length == 0 &&
                           (uri.Scheme == Uri.UriSchemeHttps || uri.Scheme == Uri.UriSchemeHttp) && link.Length <= 2000;
                string shown = link.Length > 300 ? link[..299] + "…" : link;
                using var dialog = new ChoiceForm("Link vom Handy", "Link öffnen?", shown + (web ? "" : Environment.NewLine + "(Nur http- und https-Links lassen sich öffnen.)"),
                    new[] { ("Öffnen", "open", web), ("Kopieren", "copy", link.Length > 0), ("Nein", "no", true) }, focusIndex: 2);
                string? choice = await dialog.AskAsync();
                if (choice == "open" && web)
                {
                    try
                    {
                        using Process? browser = Process.Start(new ProcessStartInfo(uri!.AbsoluteUri) { UseShellExecute = true });
                    }
                    catch (System.ComponentModel.Win32Exception ex)
                    {
                        Notify("Der Browser ließ sich nicht öffnen: " + ex.Message, ToolTipIcon.Error);
                    }
                }
                else if (choice == "copy")
                {
                    _ = ClipboardHelper.TrySetText(link, keepOutOfHistory: false);
                }

                return true;
            }

            case "file":
            {
                if (Credentials() is not { } creds)
                {
                    return false;
                }

                if (item.Size is > SparkClient.MaxInboxBytes)
                {
                    Notify("Eine Datei vom Handy ist größer als 20 MB und wurde nicht geladen.", ToolTipIcon.Warning);
                    return true;
                }

                string name = InboxStore.SafeName(item.Name);
                try
                {
                    byte[] data = await SparkClient.InboxFileAsync(creds.Base, creds.Key, item.Id, CancellationToken.None);
                    string path = await Task.Run(() => InboxStore.Save(name, data));
                    string folder = Path.GetDirectoryName(path) ?? InboxStore.Folder;
                    NotifyWithAction($"„{Clip(Path.GetFileName(path), 80)}“ liegt in Downloads\\Vom Spark. Klicken: Ordner öffnen.", () => OpenFolder(folder, path));
                    return true;
                }
                catch (SparkException ex) when (ex.Status is 404 or 410)
                {
                    Notify(ex.Detail ?? "Die Datei ist beim Spark nicht mehr da.", ToolTipIcon.Info);
                    return true;
                }
                catch (SparkException ex)
                {
                    if (ex.Status is not null)
                    {
                        Notify(ex.Message, ToolTipIcon.Warning);
                    }

                    Report(ex, fromPoll: false);
                    return false;
                }
                catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
                {
                    Notify("Die Datei ließ sich nicht speichern: " + ex.Message, ToolTipIcon.Error);
                    return false;
                }
            }

            default:
                return true;
        }
    }

    private async Task InboxDoneAsync(string id)
    {
        if (Credentials() is not { } creds)
        {
            return;
        }

        try
        {
            await SparkClient.InboxDoneAsync(creds.Base, creds.Key, id, CancellationToken.None);
        }
        catch (SparkException ex)
        {
            if (ex.Status is 401 or 503)
            {
                Report(ex, fromPoll: false);
            }
        }
    }

    private void OpenFolder(string folder, string? select)
    {
        try
        {
            var start = new ProcessStartInfo("explorer.exe") { UseShellExecute = false };
            if (select is not null && File.Exists(select))
            {
                start.ArgumentList.Add("/select," + select);
            }
            else
            {
                start.ArgumentList.Add(folder);
            }

            using Process? explorer = Process.Start(start);
        }
        catch (Exception ex) when (ex is System.ComponentModel.Win32Exception or IOException)
        {
            Notify("Der Ordner ließ sich nicht öffnen: " + ex.Message, ToolTipIcon.Error);
        }
    }

    // ------------------------------------------------------------------ agenda: Termine im Begleiter

    private async Task RefreshAgendaAsync()
    {
        if (_agendaLoading || !IsOn(Parts.Agenda) || Credentials() is not { } creds)
        {
            return;
        }

        _agendaLoading = true;
        try
        {
            AgendaResult result = await SparkClient.AgendaAsync(creds.Base, creds.Key, CancellationToken.None);
            if (IsOn(Parts.Agenda))
            {
                _agenda = result;
                _agendaError = null;
                CheckAgendaAlerts();
            }
        }
        catch (SparkException ex)
        {
            _agendaError = ex.Status is null ? "Spark nicht erreichbar – Termine später." : ex.Message;
            if (ex.Status is 401 or 403 or 503)
            {
                Report(ex, fromPoll: false);
            }
        }
        finally
        {
            _agendaLoading = false;
            RefreshPanel();
        }
    }

    /// <summary>10 Minuten vor jedem Termin ein Hinweis (einmal je Termin).</summary>
    private void CheckAgendaAlerts()
    {
        if (!IsOn(Parts.Agenda) || _agenda is not { } agenda)
        {
            return;
        }

        DateTimeOffset now = DateTimeOffset.Now;
        foreach (AgendaEvent e in agenda.Events)
        {
            TimeSpan until = e.Start - now;
            if (until <= TimeSpan.Zero || until > TimeSpan.FromMinutes(10))
            {
                continue;
            }

            string key = e.Start.ToUnixTimeSeconds().ToString(CultureInfo.InvariantCulture) + "|" + e.Title;
            if (!_alerted.Add(key))
            {
                continue;
            }

            string title = Clip((e.Title.Length > 0 ? e.Title : "Termin").ReplaceLineEndings(" "), 63);
            string body = "um " + e.Start.ToLocalTime().ToString("HH:mm", German) + (e.Where.Length > 0 ? " · " + e.Where : "");
            _balloonIsNote = false;
            _balloonAction = null;
            _tray.ShowBalloonTip(10000, title, Clip(body, 255), ToolTipIcon.Info);
        }

        if (_alerted.Count > 200)
        {
            _alerted.Clear();
        }

        RefreshPanel();
    }

    /// <summary>„In 20 Min erinnern“ an einer Meldung (Teil "agenda").</summary>
    private async Task RemindNoteAsync(Note note)
    {
        DismissNote(note);
        if (Credentials() is not { } creds)
        {
            return;
        }

        try
        {
            DateTimeOffset? due = await SparkClient.RemindAsync(creds.Base, creds.Key, null, note.N, 20, CancellationToken.None);
            DateTimeOffset at = due ?? DateTimeOffset.Now.AddMinutes(20);
            Notify("Erinnerung um " + at.ToLocalTime().ToString("HH:mm", German) + " Uhr.", ToolTipIcon.Info);
            _ = RefreshAgendaAsync();
        }
        catch (SparkException ex)
        {
            Notify(ex.Message, ToolTipIcon.Warning);
            Report(ex, fromPoll: false);
        }
    }

    // ------------------------------------------------------------------ quiet: Nicht stören erkennen

    /// <summary>Bei jeder Abfrage: beschäftigt? Dann POST busy (Spark hält Meldungen zurück); Ende einmal melden.</summary>
    private async Task QuietTickAsync(string baseUrl, string key)
    {
        string? why = IsOn(Parts.Quiet) ? QuietDetector.Detect() : null;
        bool changed = why != _quietWhy;
        _quietWhy = why;
        if (changed)
        {
            UpdateIcon();
            RefreshPanel();
        }

        try
        {
            if (why is not null)
            {
                await SparkClient.BusyAsync(baseUrl, key, true, why, CancellationToken.None);
                _quietSent = true;
            }
            else if (_quietSent)
            {
                await SparkClient.BusyAsync(baseUrl, key, false, null, CancellationToken.None);
                _quietSent = false;
            }
        }
        catch (SparkException)
        {
            // Nächster Versuch mit der nächsten Abfrage (ohne Erneuerung gibt der Spark nach 120 s von selbst frei).
        }
    }

    // ------------------------------------------------------------------ meeting: Besprechung mitschreiben

    private async Task ToggleMeetingAsync()
    {
        if (_meeting is { } running)
        {
            if (!running.Ending)
            {
                await EndMeetingAsync(running);
            }

            return;
        }

        await StartMeetingAsync();
    }

    private async Task StartMeetingAsync()
    {
        if (!IsOn(Parts.Meeting) || _meetingStarting || _meeting is not null)
        {
            return;
        }

        if (_recorder is not null || _dictateBusy)
        {
            Notify("Erst das Diktat beenden, dann die Besprechung starten.", ToolTipIcon.Info);
            return;
        }

        _meetingStarting = true;
        BuildMenu();
        MeetingRecorder? recorder = null;
        try
        {
            if (!_config.MeetingConsent)
            {
                using var consent = new ChoiceForm("Besprechung mitschreiben",
                    "Alle Beteiligten müssen einverstanden sein, dass mitgeschrieben wird.",
                    "Aufgenommen werden Mikrofon und Systemton dieses PCs. Alle 30 Sekunden geht ein Stück an den eigenen Spark; "
                    + "auf dem PC bleibt nichts. Während der Aufnahme ist oben eine rote Pille zu sehen (höchstens 3 Stunden).",
                    new[] { ("Verstanden, starten", "start", true), ("Abbrechen", "cancel", true) }, focusIndex: 1);
                if (await consent.AskAsync() != "start")
                {
                    return;
                }

                _config.MeetingConsent = true;
                TrySave();
            }

            if (Credentials() is not { } creds || !IsOn(Parts.Meeting))
            {
                return;
            }

            recorder = MeetingRecorder.TryStart(out string error);
            if (recorder is null)
            {
                Notify(error, ToolTipIcon.Warning);
                return;
            }

            string id = await SparkClient.MeetingStartAsync(creds.Base, creds.Key, CancellationToken.None);
            if (!IsOn(Parts.Meeting))
            {
                return;
            }

            MeetingRecorder rec = recorder;
            var pill = new FloatingPill("Besprechung wird mitgeschrieben ·", "Beenden", PillPlace.TopCenter, danger: true, clock: () => rec.Elapsed)
            {
                Pinned = true,
            };
            var session = new MeetingSession(id, rec, pill);
            recorder = null; // gehört jetzt der Sitzung
            _meeting = session;
            pill.ButtonClicked += async (_, _) =>
            {
                if (!session.Ending)
                {
                    await EndMeetingAsync(session);
                }
            };
            rec.ChunkReady += (_, wav) => QueueChunk(session, wav);
            rec.LimitReached += async (_, _) =>
            {
                if (ReferenceEquals(_meeting, session) && !session.Ending)
                {
                    Notify("3 Stunden erreicht – die Besprechung wird beendet.", ToolTipIcon.Info);
                    await EndMeetingAsync(session);
                }
            };
            pill.Show();

            // Weckwort hört während der Besprechung nicht mit.
            if (_wake is not null)
            {
                _wake.Paused = true;
            }

            if (!rec.HasSystemSound)
            {
                Notify("Der Systemton ließ sich nicht aufnehmen – es wird nur das Mikrofon mitgeschrieben.", ToolTipIcon.Info);
            }
        }
        catch (SparkException ex)
        {
            Notify(ex.Message, ToolTipIcon.Warning);
            Report(ex, fromPoll: false);
        }
        finally
        {
            recorder?.Dispose();
            _meetingStarting = false;
            BuildMenu();
        }
    }

    private void QueueChunk(MeetingSession session, byte[] wav)
    {
        if (session.Aborted)
        {
            return;
        }

        session.Pending.Enqueue(wav);

        // Spark länger nicht erreichbar: höchstens 10 Stücke (5 Minuten) im Speicher halten.
        while (session.Pending.Count > 10)
        {
            _ = session.Pending.Dequeue();
            if (!session.DropWarned)
            {
                session.DropWarned = true;
                Notify("Der Spark ist nicht erreichbar – ein Teil der Besprechung geht verloren.", ToolTipIcon.Warning);
            }
        }

        if (!session.Uploading)
        {
            _ = UploadChunksAsync(session);
        }
    }

    /// <summary>Wartende Stücke der Reihe nach schicken. <c>false</c>, wenn noch etwas übrig ist.</summary>
    private async Task<bool> UploadChunksAsync(MeetingSession session)
    {
        if (session.Uploading)
        {
            return false;
        }

        session.Uploading = true;
        try
        {
            while (session.Pending.Count > 0 && !session.Aborted)
            {
                if (Credentials() is not { } creds)
                {
                    return false;
                }

                try
                {
                    await SparkClient.MeetingChunkAsync(creds.Base, creds.Key, session.Id, session.Pending.Peek(), CancellationToken.None);
                    _ = session.Pending.Dequeue();
                }
                catch (SparkException ex) when (ex.Status is null or 429 or >= 500 && !ex.IsNotaus)
                {
                    return false; // später noch einmal (mit dem nächsten Stück)
                }
                catch (SparkException ex)
                {
                    Report(ex, fromPoll: false);
                    AbortMeeting(session, "Besprechung abgebrochen: " + ex.Message);
                    return false;
                }
            }

            return session.Pending.Count == 0;
        }
        finally
        {
            session.Uploading = false;
        }
    }

    /// <summary>„Mikrofon zu“ während einer Besprechung: sie endet wie über „Beenden“.</summary>
    private void EndMeetingForMic()
    {
        if (_meeting is { Ending: false } session)
        {
            _ = EndMeetingAsync(session);
        }
    }

    private async Task EndMeetingAsync(MeetingSession session)
    {
        if (session.Ending || session.Aborted)
        {
            return;
        }

        session.Ending = true;
        session.Pill.SetState("Besprechung wird ausgewertet …", null);
        BuildMenu();
        TimeSpan duration = session.Recorder.Elapsed;
        try
        {
            byte[]? last = await session.Recorder.StopAsync();
            session.Recorder.Dispose();
            RestoreWake();
            if (last is not null)
            {
                session.Pending.Enqueue(last);
            }

            // Restliche Stücke schicken (ein paar Versuche, falls der Spark kurz weg war).
            for (int attempt = 0; attempt < 4 && session.Pending.Count > 0 && !session.Aborted; attempt++)
            {
                while (session.Uploading)
                {
                    await Task.Delay(200);
                }

                if (!await UploadChunksAsync(session) && session.Pending.Count > 0)
                {
                    await Task.Delay(3000);
                }
            }

            if (session.Aborted)
            {
                return;
            }

            if (Credentials() is not { } creds)
            {
                return;
            }

            MeetingResult result = await SparkClient.MeetingEndAsync(creds.Base, creds.Key, session.Id, CancellationToken.None);
            CloseMeeting(session);
            bool remarkable = _desk?.MeetingRemarkable == true;
            var form = new MeetingEndForm(result, duration, remarkable, async (tasks, toRemarkable) =>
            {
                (string Base, string Key) c = Credentials() ?? throw new SparkException(null, "Der Begleiter ist nicht gekoppelt.");
                (int reminders, bool ok) = await SparkClient.MeetingKeepAsync(c.Base, c.Key, session.Id, tasks, toRemarkable, CancellationToken.None);
                if (toRemarkable)
                {
                    return ok ? "Aufs reMarkable geschickt." : "Das reMarkable hat es nicht angenommen.";
                }

                return reminders == 1 ? "1 Erinnerung angelegt." : string.Create(German, $"{reminders} Erinnerungen angelegt.");
            });
            form.FormClosed += (_, _) => form.Dispose();
            form.Show();
            form.Activate();
            _ = NativeMethods.SetForegroundWindow(form.Handle);
        }
        catch (SparkException ex)
        {
            Notify("Die Besprechung ließ sich nicht auswerten: " + ex.Message, ToolTipIcon.Warning);
            Report(ex, fromPoll: false);
        }
        finally
        {
            CloseMeeting(session);
            BuildMenu();
        }
    }

    /// <summary>Sofort beenden ohne Auswertung (Teil aus, Entkoppeln, Beenden, Fehler).</summary>
    private void AbortMeeting(MeetingSession session, string? message)
    {
        session.Aborted = true;
        session.Pending.Clear();
        session.Recorder.Dispose();
        CloseMeeting(session);
        RestoreWake();
        if (message is not null)
        {
            Notify(message, ToolTipIcon.Warning);
        }

        BuildMenu();
    }

    private void CloseMeeting(MeetingSession session)
    {
        if (!session.Pill.IsDisposed)
        {
            session.Pill.Close();
            session.Pill.Dispose();
        }

        if (ReferenceEquals(_meeting, session))
        {
            _meeting = null;
        }
    }

    private void RestoreWake()
    {
        if (_wake is not null)
        {
            _wake.Paused = _wakePaused;
        }
    }

    // ------------------------------------------------------------------ home: Smart-Home-Knöpfe

    private async Task RefreshHomeAsync()
    {
        if (!IsOn(Parts.Home) || Credentials() is not { } creds)
        {
            return;
        }

        try
        {
            IReadOnlyList<HomeState> states = await SparkClient.HomeAsync(creds.Base, creds.Key, CancellationToken.None);
            if (IsOn(Parts.Home))
            {
                _homeStates = states;
                _homeNote = null;
            }
        }
        catch (SparkException ex)
        {
            _homeNote = ex.Status is null ? "Spark nicht erreichbar." : ex.Message;
            if (ex.Status is 401 or 403 or 503)
            {
                Report(ex, fromPoll: false);
            }
        }

        RefreshPanel();
    }

    private async Task PressHomeAsync(string id, string name)
    {
        if (_homeBusy || !IsOn(Parts.Home) || Credentials() is not { } creds)
        {
            return;
        }

        _homeBusy = true;
        _homeNote = null;
        RefreshPanel();
        try
        {
            bool? state;
            try
            {
                state = await SparkClient.HomePressAsync(creds.Base, creds.Key, id, null, CancellationToken.None);
            }
            catch (SparkException ex) when (ex.Status == 403 && ex.Detail?.StartsWith("Codewort", StringComparison.Ordinal) == true)
            {
                string? code;
                using (var ask = new CodeWordForm(ex.Detail, name))
                {
                    code = ask.ShowDialog() == DialogResult.OK ? ask.Code : null;
                }

                if (code is null)
                {
                    return;
                }

                state = await SparkClient.HomePressAsync(creds.Base, creds.Key, id, code, CancellationToken.None);
            }

            if (_homeStates is not null)
            {
                _homeStates = _homeStates.Select(s => s.Id == id ? s with { On = state } : s).ToList();
            }

            _ = RefreshHomeAsync();
        }
        catch (SparkException ex)
        {
            _homeNote = ex.Message;
            Notify(ex.Message, ToolTipIcon.Warning);
            if (ex.Status is 401 or 503 || (ex.Status == 403 && ex.Detail?.StartsWith("Codewort", StringComparison.Ordinal) != true))
            {
                Report(ex, fromPoll: false);
            }
        }
        finally
        {
            _homeBusy = false;
            RefreshPanel();
        }
    }

    // ------------------------------------------------------------------ act: installierte Programme

    /// <summary>POST /api/desk/apps mit den Startmenü-Verknüpfungen – nur solange der Teil "act" an ist.</summary>
    private async Task SendAppsAsync()
    {
        if (_appsSending || !IsOn(Parts.Act) || Credentials() is not { } creds)
        {
            return;
        }

        _appsSending = true;
        try
        {
            List<(string Name, string Path)> apps = await Task.Run(InstalledApps.Scan);
            if (!IsOn(Parts.Act))
            {
                return;
            }

            await SparkClient.AppsAsync(creds.Base, creds.Key, apps, CancellationToken.None);
            _appsSentAt = DateTime.UtcNow;
        }
        catch (SparkException ex)
        {
            if (ex.Status is 401 or 503)
            {
                Report(ex, fromPoll: false);
            }
        }
        finally
        {
            _appsSending = false;
        }
    }

    // ------------------------------------------------------------------ daily: Tagesstart und Feierabend

    private void OnSessionSwitch(object? sender, SessionSwitchEventArgs e)
    {
        if (e.Reason == SessionSwitchReason.SessionUnlock)
        {
            _invoker.BeginInvoke(new Action(() => _ = DailyCheckAsync(morning: true)));
        }
        else if (e.Reason == SessionSwitchReason.SessionLock)
        {
            _invoker.BeginInvoke(new Action(() => _ = DailyCheckAsync(morning: false)));
        }
    }

    /// <summary>Nach der ersten erfolgreichen Abfrage: Start des Tages prüfen.</summary>
    private void OnPolledOk()
    {
        // act: Programmliste einmal am Tag erneuern
        if (IsOn(Parts.Act) && DateTime.UtcNow - _appsSentAt > TimeSpan.FromDays(1))
        {
            _ = SendAppsAsync();
        }

        if (!_firstPollDone)
        {
            _firstPollDone = true;
            _ = DailyCheckAsync(morning: true);
        }
    }

    /// <summary>Einmal am Tag: Tagesstart (Entsperren/Start ab der Morgenzeit) bzw. Feierabend (Sperren ab der Abendzeit).</summary>
    private async Task DailyCheckAsync(bool morning)
    {
        if (!IsOn(Parts.Daily) || _dailyBusy || Credentials() is not { } creds)
        {
            return;
        }

        bool on = morning ? _config.DailyMorningOn : _config.DailyEveningOn;
        TimeSpan from = morning
            ? AppConfig.ParseTime(_config.DailyMorningTime, new TimeSpan(6, 0, 0))
            : AppConfig.ParseTime(_config.DailyEveningTime, new TimeSpan(17, 30, 0));
        DateTime now = DateTime.Now;
        string today = now.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
        string? done = morning ? _config.DailyMorningDone : _config.DailyEveningDone;
        if (!on || done == today || now.TimeOfDay < from)
        {
            return;
        }

        _dailyBusy = true;
        try
        {
            string text = (await SparkClient.DailyAsync(creds.Base, creds.Key, morning, CancellationToken.None)).Trim();
            if (morning)
            {
                _config.DailyMorningDone = today;
            }
            else
            {
                _config.DailyEveningDone = today;
            }

            TrySave();
            if (text.Length == 0)
            {
                return;
            }

            string title = morning ? "Guten Morgen" : "Feierabend";
            _balloonIsNote = false;
            _balloonAction = null;
            _tray.ShowBalloonTip(10000, title, Clip(text.ReplaceLineEndings(" "), 255), ToolTipIcon.Info);
            _ = EnsureAsk().RunExternalAsync(morning ? "Tagesstart" : "Feierabend", _ => Task.FromResult(text));
        }
        catch (SparkException ex)
        {
            if (ex.Status is 401 or 403 or 503)
            {
                Report(ex, fromPoll: false);
            }
        }
        finally
        {
            _dailyBusy = false;
        }
    }

    /// <summary>Für die Einstellungen: Tagesstart/Feierabend lokal setzen. <c>null</c> = gespeichert, sonst ein Hinweis.</summary>
    public string? SetDaily(bool morningOn, string morningTime, bool eveningOn, string eveningTime)
    {
        TimeSpan invalid = TimeSpan.FromDays(-1);
        TimeSpan m = AppConfig.ParseTime(morningTime, invalid);
        TimeSpan e = AppConfig.ParseTime(eveningTime, invalid);
        if (m == invalid || e == invalid)
        {
            return "Bitte die Uhrzeit als HH:MM eingeben, z. B. 06:00.";
        }

        _config.DailyMorningOn = morningOn;
        _config.DailyMorningTime = m.ToString(@"hh\:mm", CultureInfo.InvariantCulture);
        _config.DailyEveningOn = eveningOn;
        _config.DailyEveningTime = e.ToString(@"hh\:mm", CultureInfo.InvariantCulture);
        TrySave();
        Changed?.Invoke(this, EventArgs.Empty);
        return null;
    }
}
