namespace SparkBegleiter;

/// <summary>Teil "office": Knöpfe in Office einrichten und die Knöpfe des Outlook-classic-Add-ins ausführen.</summary>
internal sealed partial class TrayContext
{
    private bool _officeBusy;

    /// <summary>Teil aus: alles austragen. Teil an und schon eingerichtet: die DLL der laufenden Version nachziehen.</summary>
    private void SyncOffice()
    {
        if (!IsOn(Parts.Office))
        {
            if (OfficeSetup.ClassicInstalled() || OfficeSetup.WebInstalled())
            {
                OfficeSetup.Uninstall();
                Notify("Die Office-Knöpfe des Spark sind ausgetragen (wirkt beim nächsten Start von Outlook, Word und Excel).", ToolTipIcon.Info);
            }

            return;
        }

        if (OfficeSetup.HasClassic && OfficeSetup.ClassicInstalled())
        {
            try
            {
                OfficeSetup.InstallClassic();
            }
            catch (Exception ex) when (ex is InvalidOperationException or IOException or UnauthorizedAccessException or System.Security.SecurityException)
            {
                // Outlook hält die alte DLL: beim nächsten Abgleich
            }
        }
    }

    /// <summary>Menü „Office-Add-ins einrichten …“: fragt erst, dann Outlook classic, Word, Excel und auf Wunsch das neue Outlook.</summary>
    private async Task SetupOfficeAsync()
    {
        if (!IsOn(Parts.Office) || _officeBusy || _desk is null)
        {
            return;
        }

        bool web = _desk.OfficeWeb;
        string what = "Der Begleiter richtet für dein Windows-Konto ein:\n\n"
            + (OfficeSetup.HasClassic ? "• Outlook classic: Knopf „Spark“ (verbessern, Antwort entwerfen, übersetzen)\n" : "")
            + (web ? "• Word und Excel: Knopf „Spark Schreibhilfe“\n" : "")
            + "\nEs wirkt beim nächsten Start der Programme. Gesendet wird nie etwas. Startet Outlook danach nicht, "
            + "unter Ich → Begleiter den Teil „Office-Add-ins“ ausschalten: der Begleiter trägt dann alles aus. Weiter?";
        if (!OfficeSetup.HasClassic && !web)
        {
            Notify("Für Word und Excel das Panel einmal über seine https-Adresse öffnen, unter Ich → Begleiter speichern "
                + "und „In anderen Programmen“ der Schreibhilfe einschalten.", ToolTipIcon.Info);
            return;
        }

        if (MessageBox.Show(what, Title, MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes)
        {
            return;
        }

        _officeBusy = true;
        var done = new List<string>();
        try
        {
            if (OfficeSetup.HasClassic)
            {
                OfficeSetup.InstallClassic();
                done.Add("Outlook classic");
            }

            if (web && Credentials() is { } creds)
            {
                var manifests = new Dictionary<string, byte[]>();
                foreach ((string app, _) in OfficeSetup.WebApps)
                {
                    manifests[app] = await SparkClient.OfficeManifestAsync(creds.Base, creds.Key, app, CancellationToken.None);
                }

                OfficeSetup.InstallWeb(manifests);
                done.Add("Word und Excel");

                if (MessageBox.Show("Auch im neuen Outlook oder in Outlook im Web? Microsoft lässt das nur von dir selbst "
                        + "hinzufügen: Es öffnet sich eine Seite, dort „Aus Datei hinzufügen“ wählen und die gezeigte Datei "
                        + "„spark-outlook.xml“ nehmen. Das gilt dann für dein Postfach (Microsoft 365, Exchange oder Outlook.com, "
                        + "nicht iCloud oder IMAP).", Title, MessageBoxButtons.YesNo, MessageBoxIcon.Question) == DialogResult.Yes)
                {
                    OfficeSetup.OfferOutlook(await SparkClient.OfficeManifestAsync(creds.Base, creds.Key, "outlook", CancellationToken.None));
                }
            }

            Notify("Eingerichtet: " + string.Join(", ", done) + ". Bitte die Programme neu starten.", ToolTipIcon.Info);
        }
        catch (SparkException ex)
        {
            Notify((done.Count > 0 ? "Eingerichtet: " + string.Join(", ", done) + ". " : "") + ex.Message, ToolTipIcon.Warning);
        }
        catch (Exception ex) when (ex is InvalidOperationException or IOException or UnauthorizedAccessException
                                       or System.Security.SecurityException or System.ComponentModel.Win32Exception)
        {
            Notify("Office-Add-ins: " + ex.Message, ToolTipIcon.Warning);
        }
        finally
        {
            _officeBusy = false;
        }
    }

    /// <summary>Ein Knopf des Add-ins in Outlook classic: dasselbe wie das Tastenkürzel des passenden Teils.</summary>
    private async Task OnOfficeButtonAsync(string word)
    {
        if (_pairOpen || !_config.IsPaired)
        {
            return;
        }

        if (!IsOn(Parts.Office))
        {
            Notify("Die Office-Knöpfe sind für diesen Rechner aus (Ich → Begleiter → Office-Add-ins).", ToolTipIcon.Info);
            return;
        }

        string part = word == "antwort" ? Parts.Mail : Parts.Write;
        if (!IsOn(part))
        {
            Notify($"„{Parts.Label(part)}“ ist für diesen Rechner aus (Ich → Begleiter).", ToolTipIcon.Info);
            return;
        }

        try
        {
            switch (word)
            {
                case "verbessern":
                    await WriteFromHotkeyAsync();
                    break;
                case "antwort":
                    await DraftReplyAsync(fromHotkey: false);
                    break;
                case "uebersetzen":
                    await TranslateFromOutlookAsync();
                    break;
            }
        }
        catch (Exception ex) when (ex is InvalidOperationException or System.ComponentModel.Win32Exception or IOException or ObjectDisposedException)
        {
            Notify("Das hat nicht geklappt: " + ex.Message, ToolTipIcon.Error);
        }
    }

    /// <summary>„Übersetzen“: markierter Text, sonst die geöffnete oder markierte Mail; das Fenster der Schreibhilfe
    /// beginnt mit der Art „Übersetzen“. Eine ganze Mail wird nie zurück eingefügt (nur Kopieren).</summary>
    private async Task TranslateFromOutlookAsync()
    {
        if (_writing || _desk is null)
        {
            return;
        }

        IntPtr target = NativeMethods.GetForegroundWindow();
        _writing = true;
        try
        {
            string? text = await ClipboardHelper.CopySelectionAsync(_config.GetHotkey(Parts.Write).VirtualKey);
            if (string.IsNullOrWhiteSpace(text))
            {
                using OutlookMail? mail = OutlookMail.TryOpen(out _);
                text = mail?.Body;
                target = IntPtr.Zero;
            }

            ShowAssist(text, target);
            _assist?.StartWith(DeskConfig.TranslateArt);
        }
        finally
        {
            _writing = false;
        }
    }
}
