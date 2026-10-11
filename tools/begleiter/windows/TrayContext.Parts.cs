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

        // wake
        if (IsOn(Parts.Wake))
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
                _wake.Paused = _wakePaused;
            }
        }
        else
        {
            StopWake();
        }

        // actions: ohne den Teil keine Meldungen mit Knöpfen
        if (!IsOn(Parts.Actions) || !IsOn(Parts.Notes))
        {
            _panelNotes.Clear();
        }

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
        _mailForm?.Close();
        if (removeFileMenu)
        {
            FileMenu.Unregister();
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

        if (IsOn(Parts.Wake))
        {
            _menu.Items.Add(new ToolStripMenuItem(WakeItemText(), null, (_, _) => ToggleWakePause()) { Enabled = _wake is not null });
            any = true;
        }

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
            items.Add(new PanelItem("Wissen-Ordner öffnen", Glyph.Folder, null, OpenWissenFolder));
        }

        if (IsOn(Parts.Wake))
        {
            items.Add(new PanelItem(WakeItemText(), Glyph.Wave, null, ToggleWakePause, Enabled: _wake is not null));
        }
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
            _wake.Paused = _wakePaused;
        }

        if (_wakePaused)
        {
            CloseWakeIndicator();
        }

        UpdateIcon();
        BuildMenu();
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
            using (var form = new ScreenAskForm(image, sel.Area))
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
            }, ReportFromWindow);
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
        if (!IsOn(Parts.Notes) || !IsOn(Parts.Actions))
        {
            return Array.Empty<PanelNote>();
        }

        return _panelNotes.AsEnumerable().Reverse().Select(n => new PanelNote(
            n.N,
            Clip((n.Title.Length > 0 ? n.Title : "Meldung vom Spark").ReplaceLineEndings(" "), 80),
            Clip(n.Body.ReplaceLineEndings(" "), 200),
            n.Actions.Contains("reply") ? () => ReplyToNote(n) : null,
            n.Actions.Contains("later") ? () => NoteLater(n) : null,
            n.Actions.Contains("open") && !string.IsNullOrEmpty(_config.Base) ? () =>
            {
                DismissNote(n);
                OpenPanel();
            } : null)).ToList();
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
                if (IsOn(Parts.Actions))
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
        string? error;
        if (_desk is null || !IsOn(Parts.Act))
        {
            error = "Der Teil ist am PC aus.";
        }
        else if (ActRunner.Plan(ask, _desk, out string problem) is not { } plan)
        {
            error = problem;
        }
        else
        {
            using var dialog = new ActConfirmForm(ask.Text, plan.Description);
            bool allowed = await dialog.AskAsync();
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
                    plan.Run();
                    ok = true;
                    error = null;
                }
                catch (Exception ex) when (ex is System.ComponentModel.Win32Exception or InvalidOperationException or FileNotFoundException
                                               or IOException or UnauthorizedAccessException or ObjectDisposedException)
                {
                    error = "Ging nicht: " + ex.Message;
                }
            }
        }

        if (Credentials() is not { } creds)
        {
            return;
        }

        try
        {
            await SparkClient.ActResultAsync(creds.Base, creds.Key, ask.Id, ok, error, CancellationToken.None);
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
