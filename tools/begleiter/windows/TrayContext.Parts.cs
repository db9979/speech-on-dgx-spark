using System.Diagnostics;
using System.Media;
using System.Runtime.InteropServices;

namespace SparkBegleiter;

/// <summary>
/// Version 3 (tiefere Einbindung): Rechtsklick auf Dateien, Bildschirm fragen, App erkennen, Antwort entwerfen in
/// Outlook, Ordner Spark-Wissen, Knöpfe in Meldungen, Spark darf am PC handeln, Weckwort. Jeder Teil ist aus, bis das
/// Panel ihn einschaltet; ein ausgeschalteter Teil hat kein Tastenkürzel, keinen Menüeintrag und läuft nicht.
/// </summary>
internal sealed partial class TrayContext
{
    private const int MaxPanelNotes = 3;
    private const int MaxFileQueue = 20;

    private readonly FileBridge _fileBridge;
    private readonly Queue<FileRequest> _fileQueue = new();
    private readonly List<Note> _panelNotes = new();
    private readonly List<System.Windows.Forms.Timer> _laterTimers = new();
    private readonly Queue<ActAsk> _actQueue = new();

    private bool _balloonIsNote;
    private bool _filesBusy;
    private bool _screenBusy;
    private MailForm? _mailForm;
    private bool _mailBusy;
    private bool _actBusy;
    private FolderWatcher? _folder;
    private WakeListener? _wake;
    private bool _wakePaused;
    private bool _wakeErrorShown;
    private RecordingIndicator? _wakeIndicator;
    private Stopwatch? _wakeQuestionClock;

    /// <summary>Teil "context": Art des Programms hinter dem Fenster (nur wenn an), sonst <c>null</c>.</summary>
    private string? ContextFor(IntPtr target) => IsOn(Parts.Context) ? AppCategory.FromWindow(target) : null;

    // ------------------------------------------------------------------ An/aus abgleichen

    /// <summary>Nach jeder neuen Einstellung: Explorer-Menü, Ordner-Beobachtung und Weckwort an- bzw. ausschalten.</summary>
    private void SyncParts()
    {
        // files: Einträge nur, solange der Teil an ist
        if (IsOn(Parts.Files))
        {
            try
            {
                FileMenu.Register();
            }
            catch (Exception ex) when (ex is UnauthorizedAccessException or System.Security.SecurityException or IOException)
            {
                Notify("Das Explorer-Menü „Mit Spark“ ließ sich nicht eintragen: " + ex.Message, ToolTipIcon.Warning);
            }
        }
        else
        {
            FileMenu.Unregister();
        }

        // folder
        if (IsOn(Parts.Folder))
        {
            string path = _config.WissenPath;
            if (_folder is null || !string.Equals(_folder.Folder, Path.GetFullPath(path), StringComparison.OrdinalIgnoreCase))
            {
                _folder?.Dispose();
                _folder = null;
                try
                {
                    _folder = new FolderWatcher(path, Credentials, text => Notify(text, ToolTipIcon.Info), ReportFromWindow);
                }
                catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException)
                {
                    Notify($"Der Ordner „{path}“ lässt sich nicht beobachten: {ex.Message}", ToolTipIcon.Warning);
                }
            }
        }
        else if (_folder is not null)
        {
            _folder.Dispose();
            _folder = null;
        }

        if (_folder is not null && _desk is not null)
        {
            _folder.SetLeftOut(_desk.LeftOut);
        }

        // wake (nie bei „Mikrofon zu“)
        if (IsOn(Parts.Wake) && !MicSwitch.Closed)
        {
            if (_wake is null)
            {
                _wake = WakeListener.TryStart(out string error);
                if (_wake is null)
                {
                    if (!_wakeErrorShown)
                    {
                        _wakeErrorShown = true;
                        Notify(error, ToolTipIcon.Warning);
                    }
                }
                else
                {
                    _wakeErrorShown = false;
                    _wake.SentenceReady += async (_, wav) => await OnWakeSentenceAsync(wav);
                    _wake.QuestionReady += async (_, wav) => await OnWakeQuestionAsync(wav);
                }
            }

            if (_wake is not null)
            {
                _wake.Paused = _wakePaused || _meeting is not null;
            }
        }
        else
        {
            StopWake();
        }

        // actions/agenda: ohne die Teile keine Meldungen im Tray-Fenster
        if ((!IsOn(Parts.Actions) && !IsOn(Parts.Agenda)) || !IsOn(Parts.Notes))
        {
            _panelNotes.Clear();
        }

        SyncParts4();
        SyncPost();
        SyncLists();
        SyncOffen();
        SyncOffice();
        SyncFern();
        UpdateIcon();
    }

    /// <summary>Alles anhalten (Beenden, Entkoppeln). Das Explorer-Menü nur beim Entkoppeln austragen.</summary>
    private void StopParts(bool removeFileMenu)
    {
        _folder?.Dispose();
        _folder = null;
        StopWake();
        _panelNotes.Clear();
        foreach (System.Windows.Forms.Timer t in _laterTimers)
        {
            t.Dispose();
        }

        _laterTimers.Clear();
        _fileQueue.Clear();
        _actQueue.Clear();
        StopFern();
        _mailForm?.Close();
        StopParts4();
        StopPost();
        StopLists();
        StopOffen();
        StopFind();
        StopCapture();
        if (removeFileMenu)
        {
            FileMenu.Unregister();
            OfficeSetup.Uninstall();
        }
    }

    private void StopWake()
    {
        CloseWakeIndicator();
        _wake?.Dispose();
        _wake = null;
    }

    // ------------------------------------------------------------------ Menü und Tray-Fenster

    /// <summary>Einträge der eingeschalteten neuen Teile im Rechtsklick-Menü. <c>true</c>, wenn welche dazukamen.</summary>
    private bool AddPartMenuItems()
    {
        bool any = false;
        if (IsOn(Parts.Screen))
        {
            _menu.Items.Add(new ToolStripMenuItem("Bildschirm fragen …", null, async (_, _) => await AskScreenAsync())
            {
                ShortcutKeyDisplayString = _config.GetHotkey(Parts.Screen).ToString(),
            });
            any = true;
        }

        if (IsOn(Parts.Mail))
        {
            _menu.Items.Add(new ToolStripMenuItem("Antwort entwerfen …", null, async (_, _) => await DraftReplyAsync(fromHotkey: false))
            {
                ShortcutKeyDisplayString = _config.GetHotkey(Parts.Mail).ToString(),
            });
            any = true;
        }

        if (IsOn(Parts.Folder))
        {
            _menu.Items.Add(new ToolStripMenuItem("Wissen-Ordner öffnen", null, (_, _) => OpenWissenFolder()));
            any = true;
        }

        if (UsesMic())
        {
            _menu.Items.Add(new ToolStripMenuItem(MicItemText(), null, (_, _) => ToggleMic()));
            any = true;
        }

        if (IsOn(Parts.Wake) && !MicSwitch.Closed)
        {
            _menu.Items.Add(new ToolStripMenuItem(WakeItemText(), null, (_, _) => ToggleWakePause()) { Enabled = _wake is not null });
            any = true;
        }

        if (IsOn(Parts.Office))
        {
            _menu.Items.Add(new ToolStripMenuItem("Office-Add-ins einrichten …", null, async (_, _) => await SetupOfficeAsync()));
            any = true;
        }

        any |= AddPartMenuItems4();
        any |= AddFernMenuItems();
        return any;
    }

    private void AddPanelItems(List<PanelItem> items)
    {
        if (IsOn(Parts.Screen))
        {
            items.Add(new PanelItem("Bildschirm fragen", Glyph.Screen, _config.GetHotkey(Parts.Screen).ToString(), () => _ = AskScreenAsync()));
        }

        if (IsOn(Parts.Mail))
        {
            items.Add(new PanelItem("Antwort entwerfen", Glyph.Mail, _config.GetHotkey(Parts.Mail).ToString(), () => _ = DraftReplyAsync(fromHotkey: false)));
        }

        if (IsOn(Parts.Folder))
        {
            items.Add(new PanelItem("Wissen-Ordner", Glyph.Folder, null, OpenWissenFolder,
                Kind: PanelItemKind.Row, Detail: "Neue Dateien darin gehen ins Wissen.", Verb: "Öffnen"));
        }

        if (UsesMic())
        {
            items.Add(new PanelItem("Mikrofon", MicSwitch.Closed ? Glyph.MicOff : Glyph.Mic, null, ToggleMic,
                Kind: PanelItemKind.Toggle, On: !MicSwitch.Closed,
                Detail: MicSwitch.Closed ? "Zu: der Begleiter hört nichts." : "Offen für Diktat, Fragen und Weckwort."));
        }

        if (IsOn(Parts.Wake) && !MicSwitch.Closed)
        {
            items.Add(new PanelItem($"Weckwort „{_desk?.WakeWord ?? "Hey Spark"}“", Glyph.Wave, null, ToggleWakePause, Enabled: _wake is not null,
                Kind: PanelItemKind.Toggle, On: _wake is not null && !_wakePaused,
                Detail: _wake is null ? "Kein Mikrofon gefunden." : _wakePaused ? "Pausiert." : "Hört zu."));
        }

        if (IsOn(Parts.Office))
        {
            items.Add(new PanelItem("Office-Add-ins", Glyph.Mail, null, () => _ = SetupOfficeAsync(),
                Kind: PanelItemKind.Row, Detail: "Schreibhilfe in Word, Excel und Outlook.", Verb: "Einrichten"));
        }

        if (IsOn(Parts.Act))
        {
            items.Add(new PanelItem("Am PC handeln", Glyph.Gear, null, OpenActSettings,
                Kind: PanelItemKind.Row, Detail: "Ohne Rückfrage, Kurzbefehle.", Verb: "Einstellen"));
        }

        if (_view is not null)
        {
            items.Add(new PanelItem("Bildschirm-Sitzung beenden", Glyph.Stop, null, () => _view?.Stop(tell: true), Danger: true));
        }

        AddPanelItems4(items);
    }

    /// <summary>Teile, die das Mikrofon öffnen können (Mikrofon-Knöpfe in den Fenstern hängen an „Diktieren“).</summary>
    private bool UsesMic() => IsOn(Parts.Dictate) || IsOn(Parts.Ask) || IsOn(Parts.Wake) || IsOn(Parts.Meeting);

    private static string MicItemText() => MicSwitch.Closed ? "Mikrofon öffnen (ist zu)" : "Mikrofon schließen (ist offen)";

    /// <summary>
    /// „Mikrofon offen/zu“ (Dominik 2026-10-14): zu schließt wirklich – Weckwort aus, laufende Aufnahmen verworfen,
    /// eine Besprechung endet (das bisher Mitgeschriebene wird wie beim Beenden ausgewertet). Bleibt nach Neustart.
    /// </summary>
    private void ToggleMic()
    {
        bool closed = !MicSwitch.Closed;
        MicSwitch.Set(closed);
        _config.MicClosed = closed;
        TrySave();
        if (closed)
        {
            StopWake();
            Recorder.DiscardActive();
            EndMeetingForMic();
        }

        SyncParts();
        BuildMenu();
        RefreshPanel();
        Notify(closed ? "Mikrofon zu: der Begleiter hört nichts, bis du es wieder öffnest." : "Mikrofon offen.", ToolTipIcon.Info);
        _ = PollAsync(); // das Panel erfährt den neuen Zustand gleich
    }

    private string WakeItemText()
    {
        if (_wake is null)
        {
            return "Weckwort: kein Mikrofon";
        }

        string word = _desk?.WakeWord ?? "Hey Spark";
        return _wakePaused ? $"Weckwort fortsetzen („{word}“)" : $"Weckwort pausieren („{word}“)";
    }

    private void ToggleWakePause()
    {
        _wakePaused = !_wakePaused;
        if (_wake is not null)
        {
            _wake.Paused = _wakePaused || _meeting is not null;
        }

        if (_wakePaused)
        {
            CloseWakeIndicator();
        }

        UpdateIcon();
        BuildMenu();
        RefreshPanel(); // der Schalter im Begleiter-Fenster zeigt den neuen Stand
        Changed?.Invoke(this, EventArgs.Empty);
    }

    private void OpenWissenFolder()
    {
        try
        {
            string path = _folder?.Folder ?? _config.WissenPath;
            Directory.CreateDirectory(path);
            using Process? explorer = Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });
        }
        catch (Exception ex) when (ex is System.ComponentModel.Win32Exception or IOException or UnauthorizedAccessException)
        {
            Notify("Der Ordner ließ sich nicht öffnen: " + ex.Message, ToolTipIcon.Error);
        }
    }

    /// <summary>Für die Einstellungen: der beobachtete Ordner.</summary>
    public string WissenFolder => _config.WissenPath;

    /// <summary>Anderen Ordner für "folder" wählen (lokal). <c>null</c> = übernommen, sonst ein Hinweis.</summary>
    public string? SetWissenFolder(string path)
    {
        try
        {
            string full = Path.GetFullPath(path);
            Directory.CreateDirectory(full);
            string standard = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Spark-Wissen");
            _config.WissenFolder = string.Equals(full, standard, StringComparison.OrdinalIgnoreCase) ? null : full;
            TrySave();
            SyncParts();
            Changed?.Invoke(this, EventArgs.Empty);
            return null;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException)
        {
            return "Dieser Ordner geht nicht: " + ex.Message;
        }
    }

    // ------------------------------------------------------------------ files: Rechtsklick auf Dateien

    private void EnqueueFile(FileRequest request)
    {
        if (!_config.IsPaired)
        {
            Notify("Der Begleiter ist nicht gekoppelt.", ToolTipIcon.Warning);
            return;
        }

        if (!IsOn(Parts.Files))
        {
            Notify("„Rechtsklick auf Dateien“ ist aus – im Panel unter Ich → Begleiter einschalten.", ToolTipIcon.Info);
            return;
        }

        if (_fileQueue.Count >= MaxFileQueue)
        {
            Notify("Es warten schon viele Dateien. Bitte etwas später weitermachen.", ToolTipIcon.Info);
            return;
        }

        _fileQueue.Enqueue(request);
        if (!_filesBusy)
        {
            _ = ProcessFilesAsync();
        }
    }

    private async Task ProcessFilesAsync()
    {
        _filesBusy = true;
        try
        {
            while (_fileQueue.Count > 0)
            {
                await HandleFileAsync(_fileQueue.Dequeue());
            }
        }
        finally
        {
            _filesBusy = false;
        }
    }

    private async Task HandleFileAsync(FileRequest request)
    {
        string name = Path.GetFileName(request.Path);
        if (!FileMenu.IsSupported(request.Path))
        {
            Notify($"„{Clip(name, 60)}“: diese Dateiart nimmt der Spark nicht an.", ToolTipIcon.Info);
            return;
        }

        byte[] data;
        try
        {
            var info = new FileInfo(request.Path);
            if (!info.Exists)
            {
                Notify($"„{Clip(name, 60)}“ gibt es nicht mehr.", ToolTipIcon.Warning);
                return;
            }

            if (info.Length > SparkClient.MaxFileBytes)
            {
                Notify($"„{Clip(name, 60)}“ ist größer als 20 MB.", ToolTipIcon.Warning);
                return;
            }

            data = await File.ReadAllBytesAsync(info.FullName);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            Notify($"„{Clip(name, 60)}“ lässt sich nicht lesen: {ex.Message}", ToolTipIcon.Warning);
            return;
        }

        if (Credentials() is not { } creds)
        {
            return;
        }

        string contentType = FileMenu.ContentType(Path.GetExtension(name));
        if (request.What == "wissen")
        {
            try
            {
                FileResult result = await SparkClient.FileAsync(creds.Base, creds.Key, data, name, contentType, "wissen", null, CancellationToken.None);
                Notify($"„{Clip(result.Name ?? name, 80)}“ ist jetzt im Wissen.", ToolTipIcon.Info);
            }
            catch (SparkException ex) when (ex.Status == 409)
            {
                Notify(ex.Detail is { Length: > 0 } d ? d : $"„{Clip(name, 80)}“ ist schon im Wissen.", ToolTipIcon.Info);
            }
            catch (SparkException ex)
            {
                Notify(ex.Message, ToolTipIcon.Warning);
                Report(ex, fromPoll: false);
            }

            return;
        }

        string? sprache = request.What == "uebersetzen" ? _desk?.WriteSprache ?? "en" : null;
        AskForm ask = EnsureAsk();
        await ask.RunExternalAsync($"{FileRequest.Label(request.What)}: {name}", async ct =>
        {
            FileResult result = await SparkClient.FileAsync(creds.Base, creds.Key, data, name, contentType, request.What, sprache, ct);
            return result.Text ?? throw new SparkException(null, "Der Spark hat keinen Text zurückgeschickt.");
        });
    }

    // ------------------------------------------------------------------ screen: Bildschirm fragen

    private async Task AskScreenAsync()
    {
        if (_screenBusy || !IsOn(Parts.Screen))
        {
            return;
        }

        _screenBusy = true;
        try
        {
            (Bitmap Image, Rectangle Area)? selection = await ScreenCapture.SelectAsync();
            if (selection is not { } sel)
            {
                return;
            }

            using Bitmap image = sel.Image;
            (string What, string Question)? choice;
            using (var form = new ScreenAskForm(image, sel.Area, NewDictation()))
            {
                var closed = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
                form.FormClosed += (_, _) => closed.TrySetResult();
                form.Show();
                form.Activate();
                _ = NativeMethods.SetForegroundWindow(form.Handle);
                await closed.Task;
                choice = form.Choice;
            }

            if (choice is not { } c || Credentials() is not { } creds)
            {
                return;
            }

            (byte[] data, string type) = await Task.Run(() => ScreenImage.Encode(image));
            string label = c.What switch
            {
                "text" => "Text herauslesen",
                "uebersetzen" => "Übersetzen",
                _ => "Erklären",
            };
            string question = c.Question.Length > 500 ? c.Question[..500] : c.Question;
            AskForm ask = EnsureAsk();
            await ask.RunExternalAsync("Bildschirm · " + label + (question.Length > 0 ? ": " + question : ""),
                ct => SparkClient.ScreenAsync(creds.Base, creds.Key, data, type, question, c.What, ct));
        }
        catch (SparkException ex)
        {
            Notify(ex.Message, ToolTipIcon.Warning);
        }
        catch (Exception ex) when (ex is ExternalException or ArgumentException or OutOfMemoryException)
        {
            Notify("Der Bildschirm ließ sich nicht aufnehmen: " + ex.Message, ToolTipIcon.Error);
        }
        finally
        {
            _screenBusy = false;
        }
    }

    // ------------------------------------------------------------------ mail: Antwort entwerfen

    private async Task DraftReplyAsync(bool fromHotkey)
    {
        if (!IsOn(Parts.Mail) || _mailBusy)
        {
            return;
        }

        if (_mailForm is { IsDisposed: false } open)
        {
            open.Activate();
            return;
        }

        _mailBusy = true;
        try
        {
            IntPtr foreground = NativeMethods.GetForegroundWindow();
            OutlookMail? outlook = OutlookMail.TryOpen(out string? problem);
            if (outlook is null && problem is not null)
            {
                Notify(problem, ToolTipIcon.Info);
                return;
            }

            string? selection = null;
            if (outlook is null && fromHotkey)
            {
                // Neues Outlook (kein COM) oder anderes Mailprogramm: markierten Text als Mail nehmen.
                selection = await ClipboardHelper.CopySelectionAsync(_config.GetHotkey(Parts.Mail).VirtualKey);
            }

            string? app = IsOn(Parts.Context) ? (outlook is not null ? "outlook" : AppCategory.FromWindow(foreground)) : null;
            var form = new MailForm(outlook, selection, async (mail, notes, ct) =>
            {
                (string Base, string Key) creds = Credentials() ?? throw new SparkException(null, "Der Begleiter ist nicht gekoppelt.");
                AssistResult result = await SparkClient.AssistAsync(creds.Base, creds.Key, notes, "antwort", null, null, ct, app, mail);
                return result.Text;
            }, ReportFromWindow, NewDictation(), new MailHelp(
                async (mail, ct) =>
                {
                    (string Base, string Key) creds = Credentials() ?? throw new SparkException(null, "Der Begleiter ist nicht gekoppelt.");
                    return await SparkClient.SuggestAsync(creds.Base, creds.Key, mail, ct);
                },
                async (art, text, ct) =>
                {
                    (string Base, string Key) creds = Credentials() ?? throw new SparkException(null, "Der Begleiter ist nicht gekoppelt.");
                    AssistResult result = await SparkClient.AssistAsync(creds.Base, creds.Key, text, art, art == "uebersetzen" ? "en" : null, null, ct, app);
                    return result.Text;
                }));
            form.FormClosed += (_, _) =>
            {
                if (ReferenceEquals(_mailForm, form))
                {
                    _mailForm = null;
                }

                form.Dispose();
            };
            _mailForm = form;
            form.Show();
            form.Activate();
            _ = NativeMethods.SetForegroundWindow(form.Handle);
        }
        finally
        {
            _mailBusy = false;
        }
    }

    // ------------------------------------------------------------------ actions: Knöpfe in Meldungen

    private void AddPanelNote(Note note)
    {
        _panelNotes.RemoveAll(n => n.N == note.N);
        _panelNotes.Add(note);
        while (_panelNotes.Count > MaxPanelNotes)
        {
            _panelNotes.RemoveAt(0);
        }

        RefreshPanel();
    }

    private void DismissNote(Note note)
    {
        _panelNotes.RemoveAll(n => n.N == note.N);
        RefreshPanel();
    }

    private IReadOnlyList<PanelNote> BuildPanelNotes()
    {
        bool actions = IsOn(Parts.Actions);
        bool agenda = IsOn(Parts.Agenda);
        if (!IsOn(Parts.Notes) || (!actions && !agenda))
        {
            return Array.Empty<PanelNote>();
        }

        return _panelNotes.AsEnumerable().Reverse().Select(n => new PanelNote(
            n.N,
            Clip((n.Title.Length > 0 ? n.Title : "Meldung vom Spark").ReplaceLineEndings(" "), 80),
            Clip(n.Body.ReplaceLineEndings(" "), 200),
            actions && n.Actions.Contains("reply") ? () => ReplyToNote(n) : null,
            actions && n.Actions.Contains("later") ? () => NoteLater(n) : null,
            actions && n.Actions.Contains("open") && !string.IsNullOrEmpty(_config.Base) ? () =>
            {
                DismissNote(n);
                OpenNoteWay(n);
            } : null,
            agenda && !n.Actions.Contains("fdremind") ? () => _ = RemindNoteAsync(n) : null,
            () => DismissNote(n),
            actions ? NoteExtras(n) : null,
            n.Weg is null ? "Panel öffnen" : "Ansehen")).ToList();
    }

    /// <summary>Die Knöpfe ihrer Art: „Antwort entwerfen“ (neue Mail, mit Frag Spark) und die, die über das Panel wirken.</summary>
    private List<(string, Action)> NoteExtras(Note n)
    {
        var extra = new List<(string, Action)>();
        if (n.Actions.Contains("draft") && IsOn(Parts.Ask))
        {
            extra.Add(("Antwort entwerfen", () =>
            {
                DismissNote(n);
                EnsureAsk().QuoteNote(n, NoteActs.DraftQuestion);
            }));
        }

        // Bestätigungscodes: „Code kopieren“ legt den Code nur hier in die Zwischenablage, nichts geht an den Spark
        if (n.Actions.Contains("copy") && NoteActs.CodeOf(n.Body) is { } code)
        {
            extra.Add(("Code kopieren", () =>
            {
                DismissNote(n);
                Clipboard.SetText(code);
            }));
        }

        extra.AddRange(n.Actions.Where(a => NoteActs.Label(a) is not null)
            .Select(a => (NoteActs.Label(a)!, (Action)(() => _ = NoteActAsync(n, a)))));
        return extra;
    }

    /// <summary>„Ansehen“: der Weg der Meldung im Panel (z. B. E-Mail → Für dich), sonst die Startseite.</summary>
    private void OpenNoteWay(Note note)
    {
        if (note.Weg is null || !Wege.OpenFrom(note.Weg))
        {
            OpenPanel();
        }
    }

    /// <summary>Ein Knopf ihrer Art (Für dich: Erledigt, Erinnern): das Panel prüft Meldung und Karte und tut es.</summary>
    private async Task NoteActAsync(Note note, string act)
    {
        DismissNote(note);
        if (Credentials() is not { } creds)
        {
            return;
        }

        try
        {
            string text = await SparkClient.NoteActAsync(creds.Base, creds.Key, note.N, act, CancellationToken.None);
            Notify(text, ToolTipIcon.Info);
        }
        catch (SparkException ex)
        {
            Notify(ex.Message, ToolTipIcon.Warning);
            Report(ex, fromPoll: false);
        }
    }

    private void ReplyToNote(Note note)
    {
        DismissNote(note);
        EnsureAsk().QuoteNote(note);
    }

    /// <summary>„Später“: in einer Stunde noch einmal zeigen (nur im Speicher).</summary>
    private void NoteLater(Note note)
    {
        DismissNote(note);
        var timer = new System.Windows.Forms.Timer { Interval = 60 * 60 * 1000 };
        timer.Tick += (_, _) =>
        {
            timer.Stop();
            _laterTimers.Remove(timer);
            timer.Dispose();
            if (IsOn(Parts.Notes))
            {
                if (IsOn(Parts.Actions) || IsOn(Parts.Agenda))
                {
                    AddPanelNote(note);
                }

                ShowNote(string.IsNullOrWhiteSpace(note.Title) ? "Meldung vom Spark" : note.Title, note.Body);
            }
        };
        _laterTimers.Add(timer);
        timer.Start();
    }

    // ------------------------------------------------------------------ act: Spark darf am PC handeln

    private void HandleAsks(IReadOnlyList<ActAsk> asks)
    {
        if (asks.Count == 0 || !IsOn(Parts.Act))
        {
            return;
        }

        foreach (ActAsk ask in asks)
        {
            if (!ActRunner.AlreadySeen(ask.Id))
            {
                _actQueue.Enqueue(ask);
            }
        }

        if (!_actBusy && _actQueue.Count > 0)
        {
            _ = ProcessActsAsync();
        }
    }

    private async Task ProcessActsAsync()
    {
        _actBusy = true;
        try
        {
            while (_actQueue.Count > 0)
            {
                await HandleActAsync(_actQueue.Dequeue());
            }
        }
        finally
        {
            _actBusy = false;
        }
    }

    private async Task HandleActAsync(ActAsk ask)
    {
        bool ok = false;
        bool auto = false;
        bool failed = false;
        string? error;
        if (_desk is null || !IsOn(Parts.Act))
        {
            error = "Der Teil ist am PC aus.";
            failed = true;
        }
        else if (ActRunner.Plan(ask, _desk, _config.ActScripts, out string problem) is not { } plan)
        {
            error = problem;
            failed = true;
        }
        else
        {
            // „ohne Rückfrage“ stellt die Person nur hier am PC ein (Am PC handeln einstellen), nie das Panel
            auto = ActRunner.MaySkip(ask.Action, _config);
            bool allowed = auto;
            IntPtr before = NativeMethods.GetForegroundWindow();
            if (!auto)
            {
                using var dialog = new ActConfirmForm(ask.Text, plan.Description,
                    ActRunner.AutoOk.Contains(ask.Action) ? ActRunner.KindLabels[ask.Action] : null);
                allowed = await dialog.AskAsync();
                if (dialog.SkipFromNow && !_config.ActAuto.Contains(ask.Action))
                {
                    _config.ActAuto.Add(ask.Action);
                    TrySave();
                    _ = SendActLocalAsync();
                }
            }

            if (!allowed)
            {
                error = "Am PC abgelehnt (oder keine Antwort in 60 s).";
            }
            else if (!IsOn(Parts.Act))
            {
                error = "Der Teil wurde inzwischen ausgeschaltet.";
            }
            else
            {
                try
                {
                    if (!auto && ActRunner.NeedsFront.Contains(ask.Action))
                    {
                        await ActDo.RestoreAsync(before);   // Tasten und Fenster-Befehle gehen an das Fenster von vorher
                    }

                    plan.Run();
                    ok = true;
                    error = null;
                    if (auto)
                    {
                        Notify("Spark (ohne Rückfrage): " + plan.Description, ToolTipIcon.Info);
                    }
                }
                catch (Exception ex) when (ex is System.ComponentModel.Win32Exception or InvalidOperationException or FileNotFoundException
                                               or IOException or UnauthorizedAccessException or ObjectDisposedException)
                {
                    error = "Ging nicht: " + ex.Message;
                    failed = true;
                }
            }
        }

        if (Credentials() is not { } creds)
        {
            return;
        }

        try
        {
            await SparkClient.ActResultAsync(creds.Base, creds.Key, ask.Id, ok, error, CancellationToken.None, auto, failed);
        }
        catch (SparkException ex)
        {
            Report(ex, fromPoll: false);
        }
    }

    // ------------------------------------------------------------------ wake: Weckwort

    /// <summary>Ein Satz ist da: /api/desk/hear. Weckwort + Frage → fragen; nur Weckwort → Ton, Frage aufnehmen.</summary>
    private async Task OnWakeSentenceAsync(byte[] wav)
    {
        WakeListener? listener = _wake;
        if (listener is null || Credentials() is not { } creds || !IsOn(Parts.Wake))
        {
            return;
        }

        bool keepBusy = false;
        try
        {
            (bool wake, string rest) = await SparkClient.HearAsync(creds.Base, creds.Key, wav, CancellationToken.None);
            if (!wake || !ReferenceEquals(listener, _wake) || listener.Paused)
            {
                return;
            }

            if (rest.Length > 0)
            {
                _ = EnsureAsk().AskQuestionAsync(rest);
                return;
            }

            // Nur das Weckwort: kurzer Ton, dann die Frage aufnehmen (etwas warten, damit der Ton nicht mit hineinkommt).
            keepBusy = true;
            SystemSounds.Asterisk.Play();
            ShowWakeIndicator();
            await Task.Delay(450);
            if (ReferenceEquals(listener, _wake))
            {
                listener.ListenForQuestion();
            }
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
            if (!keepBusy && ReferenceEquals(listener, _wake))
            {
                listener.Busy = false;
            }
        }
    }

    private async Task OnWakeQuestionAsync(byte[]? wav)
    {
        WakeListener? listener = _wake;
        CloseWakeIndicator();
        if (listener is null)
        {
            return;
        }

        try
        {
            if (wav is null)
            {
                Notify("Keine Frage gehört.", ToolTipIcon.Info);
                return;
            }

            if (Credentials() is not { } creds)
            {
                return;
            }

            string text = (await SparkClient.DictateAsync(creds.Base, creds.Key, wav, _desk?.DictateSprache ?? "auto", CancellationToken.None)).Trim();
            if (text.Length == 0)
            {
                Notify("Es wurde nichts erkannt.", ToolTipIcon.Info);
                return;
            }

            _ = EnsureAsk().AskQuestionAsync(text);
        }
        catch (SparkException ex)
        {
            Notify(ex.Message, ToolTipIcon.Warning);
            Report(ex, fromPoll: false);
        }
        finally
        {
            if (ReferenceEquals(listener, _wake))
            {
                listener.Busy = false;
            }
        }
    }

    private void ShowWakeIndicator()
    {
        CloseWakeIndicator();
        _wakeQuestionClock = Stopwatch.StartNew();
        Stopwatch clock = _wakeQuestionClock;
        _wakeIndicator = new RecordingIndicator("Weckwort", () => clock.Elapsed, () => 0.4f);
        _wakeIndicator.StopRequested += (_, _) =>
        {
            CloseWakeIndicator();
            _wake?.CancelQuestion(); // wieder auf das Weckwort hören
        };
        _wakeIndicator.Show();
    }

    private void CloseWakeIndicator()
    {
        if (_wakeIndicator is not null)
        {
            _wakeIndicator.Close();
            _wakeIndicator.Dispose();
            _wakeIndicator = null;
        }

        _wakeQuestionClock = null;
    }
}
