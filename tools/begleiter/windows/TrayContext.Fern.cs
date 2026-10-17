namespace SparkBegleiter;

/// <summary>
/// Rechner fernsteuern (Dominik 2026-10-17), Stufe 1: auf Bitten warten (GET /api/desk/wait, sofort statt mit der
/// nächsten Abfrage), was die Person hier eingestellt hat an den Spark melden (Kurzbefehle, ohne Rückfrage) und das
/// Fenster „Am PC handeln einstellen“. Alles nur, solange der Teil "act" an ist.
/// Stufe 2: dieselbe Wartezeit bringt Anfragen „Bildschirm zeigen“ (Teil "view", <see cref="ViewSession"/>).
/// </summary>
internal sealed partial class TrayContext
{
    private CancellationTokenSource? _waitCts;
    private string? _localSent;
    private ActSettingsForm? _actSettings;
    private ViewSession? _view;
    private bool _viewAsking;

    /// <summary>Nach jeder neuen Einstellung: Warten starten oder beenden, Eingestelltes einmal melden.</summary>
    private void SyncFern()
    {
        bool on = (IsOn(Parts.Act) || IsOn(Parts.View)) && _desk?.ActWait == true;
        if (on && _waitCts is null && Credentials() is { } creds)
        {
            _waitCts = new CancellationTokenSource();
            _ = WaitLoopAsync(creds.Base, creds.Key, _waitCts.Token);
        }
        else if (!on)
        {
            StopWait();
        }

        if (IsOn(Parts.Act))
        {
            _ = SendActLocalAsync();
        }
        else
        {
            _localSent = null;
            _actSettings?.Close();
        }

        if (!IsOn(Parts.View))
        {
            _view?.Stop(tell: true);
        }
    }

    private void StopFern()
    {
        _view?.Stop(tell: true);
        StopWait();
        _localSent = null;
        _actSettings?.Close();
    }

    private void StopWait()
    {
        _waitCts?.Cancel();
        _waitCts?.Dispose();
        _waitCts = null;
    }

    private async Task WaitLoopAsync(string baseUrl, string key, CancellationToken ct)
    {
        while (!ct.IsCancellationRequested && IsCurrent(baseUrl, key))
        {
            try
            {
                (IReadOnlyList<ActAsk> asks, IReadOnlyList<ViewAsk> views) = await SparkClient.WaitAsync(baseUrl, key, ct);
                if (!ct.IsCancellationRequested)
                {
                    HandleAsks(asks);
                    foreach (ViewAsk v in views.Take(1))
                    {
                        _ = HandleViewAsync(baseUrl, key, v);
                    }
                }
            }
            catch (OperationCanceledException)
            {
                return;
            }
            catch (SparkException ex)
            {
                if (ex.IsUnknownDevice || ex.Status == 403)
                {
                    Report(ex, fromPoll: false);
                    return;
                }

                // Spark gerade weg oder Notaus: die normale Abfrage meldet es; hier nur später neu versuchen.
                await DelayAsync(TimeSpan.FromSeconds(15), ct);
            }
            catch (Exception ex) when (ex is InvalidOperationException or IOException or System.Text.Json.JsonException)
            {
                await DelayAsync(TimeSpan.FromSeconds(15), ct);
            }
        }
    }

    private static async Task DelayAsync(TimeSpan wait, CancellationToken ct)
    {
        try
        {
            await Task.Delay(wait, ct);
        }
        catch (OperationCanceledException)
        {
            // beendet
        }
    }

    /// <summary>Kurzbefehle (nur Namen) und „ohne Rückfrage“ an den Spark; nur wenn sich etwas geändert hat.</summary>
    private async Task SendActLocalAsync()
    {
        if (Credentials() is not { } creds || !IsOn(Parts.Act))
        {
            return;
        }

        string[] names = _config.ActScripts.Where(x => ActDo.IsScript(x.Path)).Select(x => x.Name).ToArray();
        string[] auto = _config.ActAuto.Where(a => ActRunner.AutoOk.Contains(a)).ToArray();
        string state = string.Join("|", names) + "#" + string.Join("|", auto);
        if (state == _localSent)
        {
            return;
        }

        try
        {
            await SparkClient.LocalAsync(creds.Base, creds.Key, names, auto, CancellationToken.None);
            _localSent = state;
        }
        catch (SparkException ex)
        {
            Report(ex, fromPoll: false);
        }
    }

    /// <summary>Eine Anfrage „Bildschirm zeigen“: hier fragen, dann laufen lassen. Eine zur Zeit; eine neue beendet die alte.</summary>
    private async Task HandleViewAsync(string baseUrl, string key, ViewAsk ask)
    {
        if (_viewAsking || !IsOn(Parts.View))
        {
            return;
        }

        _viewAsking = true;
        try
        {
            _view?.Stop(tell: true);
            _view = await ViewSession.AskAsync(baseUrl, key, ask, ended =>
            {
                if (ReferenceEquals(_view, ended))
                {
                    _view = null;
                }
            });
        }
        catch (SparkException ex)
        {
            Report(ex, fromPoll: false);
        }
        finally
        {
            _viewAsking = false;
        }
    }

    private bool AddFernMenuItems()
    {
        bool added = false;
        if (_view is not null)
        {
            _menu.Items.Add(new ToolStripMenuItem("Bildschirm-Sitzung beenden", null, (_, _) => _view?.Stop(tell: true)));
            added = true;
        }

        if (!IsOn(Parts.Act))
        {
            return added;
        }

        _menu.Items.Add(new ToolStripMenuItem("Am PC handeln einstellen …", null, (_, _) => OpenActSettings()));
        return true;
    }

    private void OpenActSettings()
    {
        if (_actSettings is { IsDisposed: false })
        {
            _actSettings.Activate();
            return;
        }

        _actSettings = new ActSettingsForm(_config, () =>
        {
            TrySave();
            _ = SendActLocalAsync();
        });
        _actSettings.FormClosed += (_, _) => _actSettings = null;
        _actSettings.Show();
        _actSettings.Activate();
    }
}
