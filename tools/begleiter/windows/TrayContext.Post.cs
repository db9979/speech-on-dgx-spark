namespace SparkBegleiter;

/// <summary>
/// Teil "post" (Begleiter nachziehen 1a/2a, Dominik 2026-10-20): Abschnitt „Post“ im Tray-Fenster mit ungelesenen
/// Mails und Für dich als Zahl, den bis zu 3 dringenden Für-dich-Karten mit Erledigt und Erinnern und „E-Mail öffnen“.
/// Wichtige neue Mails kommen als Meldung (Tag "mail-new"); welche wichtig sind, entscheidet das Panel. Absender und
/// Betreff sind nur Text. Aus, bis das Panel den Teil einschaltet.
/// </summary>
internal sealed partial class TrayContext
{
    private readonly System.Windows.Forms.Timer _postTimer = new() { Interval = 5 * 60 * 1000 };
    private PostResult? _post;
    private string? _postError;
    private bool _postLoading;
    private bool _postHooked;

    private void SyncPost()
    {
        if (!_postHooked)
        {
            _postTimer.Tick += async (_, _) => await RefreshPostAsync();
            _postHooked = true;
        }

        if (IsOn(Parts.Post))
        {
            if (!_postTimer.Enabled)
            {
                _postTimer.Start();
                _ = RefreshPostAsync();
            }
        }
        else
        {
            StopPost();
        }

        if (!IsOn(Parts.Capture))
        {
            StopCapture();
        }
    }

    private void StopPost()
    {
        _postTimer.Stop();
        _post = null;
        _postError = null;
    }

    private async Task RefreshPostAsync()
    {
        if (_postLoading || !IsOn(Parts.Post) || Credentials() is not { } creds)
        {
            return;
        }

        _postLoading = true;
        try
        {
            PostResult result = await SparkClient.PostAsync(creds.Base, creds.Key, CancellationToken.None);
            if (IsOn(Parts.Post))
            {
                _post = result;
                _postError = null;
            }
        }
        catch (SparkException ex)
        {
            _postError = ex.Status is null ? "Spark nicht erreichbar – Post später." : ex.Message;
            if (ex.Status is 401 or 403 or 503)
            {
                Report(ex, fromPoll: false);
            }
        }
        finally
        {
            _postLoading = false;
            RefreshPanel();
        }
    }

    /// <summary>„Post“ im Tray-Fenster: zuerst die Zahlen mit „E-Mail öffnen“, dann die dringenden Karten. null = aus.</summary>
    private IReadOnlyList<PanelNote>? BuildPostCards()
    {
        if (!IsOn(Parts.Post))
        {
            return null;
        }

        bool canOpen = !string.IsNullOrEmpty(_config.Base);
        var list = new List<PanelNote>
        {
            new(0, PostSummary(), _postError ?? (_post is { Loading: true } ? "Wird noch gelesen …" : ""), null, null,
                canOpen && _post is not { NoMail: true } ? () => OpenPanelPage("#me=mailbox") : null, OpenLabel: "E-Mail öffnen"),
        };
        foreach (PostCard card in _post?.Cards ?? Array.Empty<PostCard>())
        {
            var extra = card.Acts.Select(a => (a == "done" ? "Erledigt" : "Erinnern", (Action)(() => _ = PostActAsync(card, a)))).ToList();
            list.Add(new PanelNote(0, Clip(card.Title, 80), Clip(card.Line, 200), null, null,
                canOpen ? () => OpenPanelPage("#weg=" + Uri.EscapeDataString("E-Mail → Für dich")) : null,
                Extra: extra, OpenLabel: "Ansehen"));
        }

        return list;
    }

    private string PostSummary()
    {
        if (_post is not { } post)
        {
            return "Wird geladen …";
        }

        if (post.NoMail)
        {
            return "Kein Postfach verbunden (E-Mail → Einstellungen).";
        }

        string unread = post.Unread is int u ? (post.More ? $"{u}+" : u.ToString()) + " ungelesen" : "Ungelesen: …";
        return post.Fuerdich is int f ? $"{unread} · {f} Für dich" : unread;
    }

    private void OpenPanelPage(string hash)
    {
        if (Wege.Open is { } open)
        {
            open(hash);
        }
        else
        {
            OpenPanel();
        }
    }

    /// <summary>Erledigt / Erinnern an einer Karte: das Panel sucht die Karte selbst und tut es.</summary>
    private async Task PostActAsync(PostCard card, string act)
    {
        if (Credentials() is not { } creds)
        {
            return;
        }

        try
        {
            string text = await SparkClient.PostActAsync(creds.Base, creds.Key, card.Id, act, CancellationToken.None);
            Notify(text, ToolTipIcon.Info);
        }
        catch (SparkException ex)
        {
            Notify(ex.Message, ToolTipIcon.Warning);
            Report(ex, fromPoll: false);
        }

        await RefreshPostAsync();
    }
}

/// <summary>
/// Teil "capture" (Begleiter nachziehen 4a): Schnell erfassen per Strg+Alt+N, Kachel „Erfassen“ im Tray-Fenster oder
/// Menü. Markierter Text kommt als Zeile mit; das Panel liest sie, gespeichert wird erst mit „Eintragen“.
/// </summary>
internal sealed partial class TrayContext
{
    private CaptureForm? _captureForm;

    private async Task OpenCaptureAsync(bool fromHotkey)
    {
        if (!IsOn(Parts.Capture) || Credentials() is null)
        {
            return;
        }

        if (_captureForm is { IsDisposed: false } open)
        {
            open.Bring();
            return;
        }

        string line = "";
        if (fromHotkey)
        {
            line = await ClipboardHelper.CopySelectionAsync(_config.GetHotkey(Parts.Capture).VirtualKey) ?? "";
        }

        var form = new CaptureForm(line,
            (text, kind) => Credentials() is { } c ? SparkClient.CapturePreviewAsync(c.Base, c.Key, text, kind, CancellationToken.None)
                : throw new SparkException(null, "Nicht gekoppelt."),
            (text, kind) => Credentials() is { } c ? SaveAndRefresh(SparkClient.CaptureSaveAsync(c.Base, c.Key, text, kind, CancellationToken.None))
                : throw new SparkException(null, "Nicht gekoppelt."),
            undo => Credentials() is { } c ? SparkClient.CaptureUndoAsync(c.Base, c.Key, undo, CancellationToken.None)
                : throw new SparkException(null, "Nicht gekoppelt."));
        form.FormClosed += (_, _) =>
        {
            if (ReferenceEquals(_captureForm, form))
            {
                _captureForm = null;
            }
        };
        _captureForm = form;
        form.Bring();
    }

    // nach „Eintragen“ gleich „Listen“ auffrischen
    private async Task<(string Text, string? Undo)> SaveAndRefresh(Task<(string Text, string? Undo)> save)
    {
        var result = await save;
        _ = RefreshListsAsync();
        return result;
    }

    private void StopCapture()
    {
        _captureForm?.Close();
        _captureForm = null;
    }
}

/// <summary>
/// Teil "lists" (Begleiter nachziehen 8a): Abschnitt „Listen“ im Tray-Fenster mit den Listen, auf denen etwas offen
/// ist: Symbol, Name, wie viele offen sind und was zuletzt dazukam; „Öffnen“ führt zur Seite Listen im Panel. Die
/// Einträge sind nur Text. Aus, bis das Panel den Teil einschaltet.
/// </summary>
internal sealed partial class TrayContext
{
    private readonly System.Windows.Forms.Timer _listsTimer = new() { Interval = 5 * 60 * 1000 };
    private IReadOnlyList<ListRow>? _lists;
    private string? _listsError;
    private bool _listsLoading;
    private bool _listsHooked;

    private void SyncLists()
    {
        if (!_listsHooked)
        {
            _listsTimer.Tick += async (_, _) => await RefreshListsAsync();
            _listsHooked = true;
        }

        if (IsOn(Parts.Lists))
        {
            if (!_listsTimer.Enabled)
            {
                _listsTimer.Start();
                _ = RefreshListsAsync();
            }
        }
        else
        {
            StopLists();
        }
    }

    private void StopLists()
    {
        _listsTimer.Stop();
        _lists = null;
        _listsError = null;
    }

    private async Task RefreshListsAsync()
    {
        if (_listsLoading || !IsOn(Parts.Lists) || Credentials() is not { } creds)
        {
            return;
        }

        _listsLoading = true;
        try
        {
            IReadOnlyList<ListRow> rows = await SparkClient.ListsAsync(creds.Base, creds.Key, CancellationToken.None);
            if (IsOn(Parts.Lists))
            {
                _lists = rows;
                _listsError = null;
            }
        }
        catch (SparkException ex)
        {
            _listsError = ex.Status is null ? "Spark nicht erreichbar – Listen später." : ex.Message;
            if (ex.Status is 401 or 403 or 503)
            {
                Report(ex, fromPoll: false);
            }
        }
        finally
        {
            _listsLoading = false;
            RefreshPanel();
        }
    }

    /// <summary>„Listen“ im Tray-Fenster: eine Karte je Liste mit „Öffnen“. null = aus.</summary>
    private IReadOnlyList<PanelNote>? BuildListCards()
    {
        if (!IsOn(Parts.Lists))
        {
            return null;
        }

        bool canOpen = !string.IsNullOrEmpty(_config.Base);
        Action? open = canOpen ? () => OpenPanelPage("#me=taskbox") : null;
        if (_lists is not { Count: > 0 } lists)
        {
            return new[] { new PanelNote(0, _listsError ?? (_lists is null ? "Wird geladen …" : "Keine Listen."), "", null, null, open, OpenLabel: "Öffnen") };
        }

        return lists.Select(l => new PanelNote(0, Clip((l.Icon.Length > 0 ? l.Icon + " " : "") + l.Name, 60),
            Clip((l.Open is int n ? $"{n} offen" : "nicht erreichbar") + (l.Last.Length > 0 ? " · " + l.Last : ""), 160),
            null, null, open, OpenLabel: "Öffnen")).ToList();
    }
}
