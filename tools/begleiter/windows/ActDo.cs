using System.Diagnostics;
using System.Runtime.InteropServices;
using static SparkBegleiter.NativeMethods;
using static SparkBegleiter.Sicht;

namespace SparkBegleiter;

/// <summary>Ein Kurzbefehl, den die Person hier am PC freigegeben hat (Teil "act"): Name und Skript-Datei.</summary>
internal sealed class ActScript
{
    public string Name { get; set; } = "";

    public string Path { get; set; } = "";
}

/// <summary>
/// Rechner fernsteuern, Stufe 1 (Dominik 2026-10-17): die festen Handlungen hinter "focus", "window", "key", "type",
/// "folder", "power" und "shortcut". Alles kommt aus festen Listen; freie Tastenkombinationen (Win+R, Strg+Alt+Entf)
/// gibt es nicht. Fehler werfen <see cref="InvalidOperationException"/> mit einem Satz für den Spark.
/// </summary>
internal static class ActDo
{
    // Die Tasten-Codes (Vk…), Chord und Type stehen im gemeinsamen Kern (Sicht.cs).

    /// <summary>Die erlaubten Tasten (wie <c>begleiter.ACT_ARGS["key"]</c> im Panel) mit ihrer Kombination.</summary>
    public static readonly IReadOnlyDictionary<string, (ushort[] Keys, string Label)> Keys = new Dictionary<string, (ushort[], string)>
    {
        ["next"] = (new[] { VkNext }, "weiter (Bild ab)"),
        ["previous"] = (new[] { VkPrior }, "zurück (Bild auf)"),
        ["space"] = (new[] { VkSpace }, "Leertaste"),
        ["enter"] = (new[] { VkReturn }, "Eingabe"),
        ["escape"] = (new[] { VkEscape }, "Esc"),
        ["tab"] = (new[] { VkTab }, "Tab"),
        ["undo"] = (new[] { VK_CONTROL, VkZ }, "Strg+Z (Rückgängig)"),
        ["redo"] = (new[] { VK_CONTROL, VkY }, "Strg+Y (Wiederholen)"),
        ["copy"] = (new[] { VK_CONTROL, VK_C }, "Strg+C (Kopieren)"),
        ["paste"] = (new[] { VK_CONTROL, VK_V }, "Strg+V (Einfügen)"),
        ["save"] = (new[] { VK_CONTROL, VkS }, "Strg+S (Speichern)"),
        ["reload"] = (new[] { VkF5 }, "F5 (Neu laden)"),
        ["find"] = (new[] { VK_CONTROL, VkF }, "Strg+F (Suchen)"),
    };

    public static readonly IReadOnlyDictionary<string, string> Folders = new Dictionary<string, string>
    {
        ["documents"] = "Dokumente", ["downloads"] = "Downloads", ["desktop"] = "Desktop", ["pictures"] = "Bilder",
        ["music"] = "Musik", ["videos"] = "Videos", ["recent"] = "Zuletzt verwendet",
    };

    public static readonly string[] ScriptKinds = { ".ps1", ".bat", ".cmd", ".lnk", ".exe" };

    /// <summary>Fenster, die nie geschlossen oder verkleinert werden (Desktop, Taskleiste).</summary>
    private static readonly string[] ShellClasses = { "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd" };

    /// <summary>Holt das Programm nach vorn; läuft es nicht, wird es gestartet.</summary>
    public static void Focus(ActApp app)
    {
        if (app.Path.EndsWith(".exe", StringComparison.OrdinalIgnoreCase))
        {
            string name = System.IO.Path.GetFileNameWithoutExtension(app.Path);
            foreach (Process p in Process.GetProcessesByName(name))
            {
                using (p)
                {
                    IntPtr h = p.MainWindowHandle;
                    if (h != IntPtr.Zero)
                    {
                        Front(h);
                        return;
                    }
                }
            }
        }

        using Process? started = Process.Start(new ProcessStartInfo(app.Path) { UseShellExecute = true });
    }

    /// <summary>Ein Fenster nach vorn holen; ein kurzes Alt erlaubt es Windows auch aus dem Hintergrund.</summary>
    public static void Front(IntPtr h)
    {
        if (IsIconic(h))
        {
            _ = ShowWindow(h, SW_RESTORE);
        }

        Send(new[] { Key(VkMenu, up: false), Key(VkMenu, up: true) });
        _ = SetForegroundWindow(h);
    }

    /// <summary>Nach der Rückfrage: das Fenster, das vorher vorn war, wieder nach vorn (Tasten gehen dorthin).</summary>
    public static async Task RestoreAsync(IntPtr before)
    {
        if (before != IntPtr.Zero && IsWindow(before))
        {
            Front(before);
            await Task.Delay(250).ConfigureAwait(true);
        }
    }

    public static void Window(string what)
    {
        IntPtr h = GetForegroundWindow();
        if (h == IntPtr.Zero || IsShell(h))
        {
            throw new InvalidOperationException("Vorn liegt kein Programmfenster.");
        }

        _ = GetWindowThreadProcessId(h, out uint pid);
        if (pid == (uint)Environment.ProcessId)
        {
            throw new InvalidOperationException("Vorn liegt der Begleiter selbst.");
        }

        switch (what)
        {
            case "close":
                _ = PostMessage(h, WM_CLOSE, IntPtr.Zero, IntPtr.Zero);
                break;
            case "minimize":
                _ = ShowWindow(h, SW_MINIMIZE);
                break;
            case "maximize":
                _ = ShowWindow(h, SW_MAXIMIZE);
                break;
            case "fullscreen":
                Chord(new[] { VkF11 });
                break;
            default:
                throw new InvalidOperationException("Unbekannte Fenster-Aktion.");
        }
    }

    public static void Folder(string which)
    {
        if (which == "recent")
        {
            using Process? r = Process.Start(new ProcessStartInfo("explorer.exe") { ArgumentList = { "shell:recent" }, UseShellExecute = false });
            return;
        }

        string path = which switch
        {
            "documents" => Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
            "downloads" => InboxStore.Downloads(),
            "desktop" => Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
            "pictures" => Environment.GetFolderPath(Environment.SpecialFolder.MyPictures),
            "music" => Environment.GetFolderPath(Environment.SpecialFolder.MyMusic),
            "videos" => Environment.GetFolderPath(Environment.SpecialFolder.MyVideos),
            _ => "",
        };
        if (path.Length == 0 || !Directory.Exists(path))
        {
            throw new InvalidOperationException("Diesen Ordner gibt es auf dem PC nicht.");
        }

        using Process? p = Process.Start(new ProcessStartInfo("explorer.exe") { ArgumentList = { path }, UseShellExecute = false });
    }

    public static void Power(string what)
    {
        if (what == "display_off")
        {
            _ = PostMessage(HWND_BROADCAST, WM_SYSCOMMAND, new IntPtr(SC_MONITORPOWER), new IntPtr(2));
        }
        else if (what != "sleep" || !Application.SetSuspendState(PowerState.Suspend, force: false, disableWakeEvent: false))
        {
            throw new InvalidOperationException("Der PC ließ sich nicht in den Ruhezustand schicken.");
        }
    }

    /// <summary>Ist die Datei ein erlaubter Kurzbefehl (vorhanden, lokal, passende Endung)?</summary>
    public static bool IsScript(string path) =>
        path.Length is > 3 and <= 400 && System.IO.Path.IsPathFullyQualified(path) && !path.StartsWith(@"\\", StringComparison.Ordinal) &&
        ScriptKinds.Contains(System.IO.Path.GetExtension(path).ToLowerInvariant()) && File.Exists(path);

    public static void Script(ActScript script)
    {
        if (!IsScript(script.Path))
        {
            throw new InvalidOperationException("Die Datei des Kurzbefehls fehlt oder ist nicht erlaubt.");
        }

        ProcessStartInfo info = System.IO.Path.GetExtension(script.Path).Equals(".ps1", StringComparison.OrdinalIgnoreCase)
            ? new ProcessStartInfo("powershell.exe")
            {
                ArgumentList = { "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script.Path },
                UseShellExecute = false,
                CreateNoWindow = true,
            }
            : new ProcessStartInfo(script.Path) { UseShellExecute = true };
        using Process? p = Process.Start(info);
    }

    private static bool IsShell(IntPtr h)
    {
        var name = new char[64];
        int n = GetClassName(h, name, name.Length);
        return n > 0 && ShellClasses.Contains(new string(name, 0, n));
    }
}
