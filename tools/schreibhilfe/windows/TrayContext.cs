namespace SparkSchreibhilfe;

/// <summary>
/// Das eigentliche Programm: Symbol im Infobereich, Menü, Tastenkürzel und der Ablauf
/// "markierten Text holen → Fenster zeigen → Ergebnis einfügen".
/// </summary>
internal sealed class TrayContext : ApplicationContext
{
    private const string Title = "Spark Schreibhilfe";

    private readonly AppConfig _config = AppConfig.Load();
    private readonly NotifyIcon _tray;
    private readonly HotkeyWindow _hotkey = new();
    private readonly ToolStripMenuItem _autostartItem;

    private AssistForm? _assist;
    private bool _capturing;
    private bool _setupOpen;

    public TrayContext()
    {
        var menu = new ContextMenuStrip();
        var improveItem = new ToolStripMenuItem("Text verbessern (Strg+Alt+S)", null, (_, _) => ShowAssist(null, IntPtr.Zero));
        improveItem.Font = new Font(improveItem.Font, FontStyle.Bold);
        _autostartItem = new ToolStripMenuItem("Mit Windows starten", null, (_, _) => ToggleAutostart());
        menu.Items.Add(improveItem);
        menu.Items.Add("Einrichten …", null, (_, _) => ShowSetup(null));
        menu.Items.Add(_autostartItem);
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("Beenden", null, (_, _) => ExitThread());
        menu.Opening += (_, _) => _autostartItem.Checked = SafeIsAutostart();

        _tray = new NotifyIcon
        {
            Icon = new Icon(AppIcon.Icon, SystemInformation.SmallIconSize),
            Text = Title,
            ContextMenuStrip = menu,
            Visible = true,
        };
        _tray.MouseClick += (_, e) =>
        {
            if (e.Button == MouseButtons.Left)
            {
                ShowAssist(null, IntPtr.Zero);
            }
        };

        _hotkey.Pressed += async (_, _) => await OnHotkeyAsync();
        bool hotkeyOk = _hotkey.Register();

        // Erst nach dem Start der Nachrichtenschleife Dialoge/Hinweise zeigen.
        Application.Idle += OnFirstIdle;

        void OnFirstIdle(object? sender, EventArgs e)
        {
            Application.Idle -= OnFirstIdle;
            if (!hotkeyOk)
            {
                Notify("Strg+Alt+S ist schon von einem anderen Programm belegt. "
                       + "Die Schreibhilfe ist über das Symbol im Infobereich erreichbar.", ToolTipIcon.Warning);
            }

            if (!_config.IsPaired)
            {
                ShowSetup(null);
            }
        }
    }

    /// <summary>Strg+Alt+S: markierten Text aus dem Programm im Vordergrund holen und das Fenster zeigen.</summary>
    private async Task OnHotkeyAsync()
    {
        if (_capturing || _setupOpen)
        {
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

        if (!_config.IsPaired)
        {
            ShowSetup(null);
            return;
        }

        _capturing = true;
        try
        {
            string? text = await ClipboardHelper.CopySelectionAsync();
            ShowAssist(text, target);
        }
        catch (Exception ex)
        {
            // Ein Fehler hier darf das Programm nicht beenden.
            Notify("Der markierte Text konnte nicht geholt werden: " + ex.Message, ToolTipIcon.Error);
        }
        finally
        {
            _capturing = false;
        }
    }

    /// <summary>Zeigt das Fenster. <paramref name="target"/> = Fenster, in das später eingefügt wird (oder keins).</summary>
    private void ShowAssist(string? text, IntPtr target)
    {
        if (!_config.IsPaired)
        {
            ShowSetup(null);
            return;
        }

        if (_assist is { IsDisposed: false } existing)
        {
            if (text is null)
            {
                existing.Activate();
                return;
            }

            existing.Close();
        }

        var form = new AssistForm(_config, text ?? "", target, owner => ShowSetup(owner));
        form.FormClosed += async (_, _) =>
        {
            if (ReferenceEquals(_assist, form))
            {
                _assist = null;
            }

            IntPtr target = form.Target;
            string? result = form.TextToApply;
            if (result is not null)
            {
                try
                {
                    await ApplyAsync(result, target);
                }
                catch (Exception ex)
                {
                    Notify("Der Text konnte nicht eingefügt werden: " + ex.Message, ToolTipIcon.Error);
                }
            }
        };
        _assist = form;
        form.Show();
        form.Activate();
    }

    /// <summary>"Übernehmen": Ergebnis in das gemerkte Fenster einfügen, sonst in der Zwischenablage lassen.</summary>
    private async Task ApplyAsync(string text, IntPtr target)
    {
        bool pasted = await ClipboardHelper.PasteIntoAsync(target, text);
        if (!pasted)
        {
            Notify("Der Text liegt in der Zwischenablage – mit Strg+V einfügen.", ToolTipIcon.Info);
        }
    }

    /// <summary>Einrichten/Koppeln. Gibt <c>true</c> zurück, wenn neu gekoppelt wurde.</summary>
    private bool ShowSetup(IWin32Window? owner)
    {
        if (_setupOpen)
        {
            return false;
        }

        _setupOpen = true;
        try
        {
            using var dialog = new SetupForm(_config);
            bool paired = dialog.ShowDialog(owner) == DialogResult.OK;
            if (paired)
            {
                Notify($"Gekoppelt{(string.IsNullOrEmpty(_config.Profile) ? "" : " mit " + _config.Profile)}. "
                       + "Text markieren und Strg+Alt+S drücken.", ToolTipIcon.Info);
            }

            return paired;
        }
        finally
        {
            _setupOpen = false;
        }
    }

    private void ToggleAutostart()
    {
        try
        {
            Autostart.Set(!Autostart.IsEnabled);
        }
        catch (Exception ex) when (ex is UnauthorizedAccessException or System.Security.SecurityException or IOException)
        {
            Notify("Autostart konnte nicht geändert werden: " + ex.Message, ToolTipIcon.Error);
        }
    }

    private static bool SafeIsAutostart()
    {
        try
        {
            return Autostart.IsEnabled;
        }
        catch (Exception ex) when (ex is UnauthorizedAccessException or System.Security.SecurityException or IOException)
        {
            return false;
        }
    }

    private void Notify(string text, ToolTipIcon icon) => _tray.ShowBalloonTip(5000, Title, text, icon);

    protected override void ExitThreadCore()
    {
        _assist?.Close();
        _tray.Visible = false;
        base.ExitThreadCore();
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            _hotkey.Dispose();
            _tray.ContextMenuStrip?.Dispose();
            _tray.Dispose();
        }

        base.Dispose(disposing);
    }
}
