using System.Diagnostics;
using System.Runtime.InteropServices;
using static SparkBegleiter.NativeMethods;

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
    private const ushort VkBack = 0x08;
    private const ushort VkTab = 0x09;
    private const ushort VkReturn = 0x0D;
    private const ushort VkMenu = 0x12;
    private const ushort VkEscape = 0x1B;
    private const ushort VkSpace = 0x20;
    private const ushort VkPrior = 0x21;
    private const ushort VkNext = 0x22;
    private const ushort VkEnd = 0x23;
    private const ushort VkHome = 0x24;
    private const ushort VkLeft = 0x25;
    private const ushort VkUp = 0x26;
    private const ushort VkRight = 0x27;
    private const ushort VkDown = 0x28;
    private const ushort VkDelete = 0x2E;
    private const ushort VkF = 0x46;
    private const ushort VkS = 0x53;
    private const ushort VkY = 0x59;
    private const ushort VkZ = 0x5A;
    private const ushort VkF5 = 0x74;
    private const ushort VkF11 = 0x7A;

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

    /// <summary>Stufe 2 (Bildschirm bedienen): die Tasten aus <c>fernsicht.KEYS</c> im Panel. Keine Windows-Taste,
    /// kein Alt+Tab, kein Strg+Alt+Entf.</summary>
    public static readonly IReadOnlyDictionary<string, ushort[]> ViewKeys = new Dictionary<string, ushort[]>
    {
        ["enter"] = new[] { VkReturn }, ["escape"] = new[] { VkEscape }, ["tab"] = new[] { VkTab },
        ["backspace"] = new[] { VkBack }, ["delete"] = new[] { VkDelete }, ["space"] = new[] { VkSpace },
        ["up"] = new[] { VkUp }, ["down"] = new[] { VkDown }, ["left"] = new[] { VkLeft }, ["right"] = new[] { VkRight },
        ["home"] = new[] { VkHome }, ["end"] = new[] { VkEnd }, ["pageup"] = new[] { VkPrior }, ["pagedown"] = new[] { VkNext },
        ["undo"] = new[] { VK_CONTROL, VkZ }, ["redo"] = new[] { VK_CONTROL, VkY }, ["copy"] = new[] { VK_CONTROL, VK_C },
        ["paste"] = new[] { VK_CONTROL, VK_V }, ["save"] = new[] { VK_CONTROL, VkS }, ["reload"] = new[] { VkF5 },
        ["find"] = new[] { VK_CONTROL, VkF },
    };

    public static readonly IReadOnlyDictionary<string, string> Folders = new Dictionary<string, string>
    {
        ["documents"] = "Dokumente", ["downloads"] = "Downloads", ["desktop"] = "Desktop", ["pictures"] = "Bilder",
        ["music"] = "Musik", ["videos"] = "Videos", ["recent"] = "Zuletzt verwendet",
    };

    public static readonly string[] ScriptKinds = { ".ps1", ".bat", ".cmd", ".lnk", ".exe" };

    /// <summary>Fenster, die nie geschlossen oder verkleinert werden (Desktop, Taskleiste).</summary>
    private static readonly string[] ShellClasses = { "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd" };

    /// <summary>Drückt die Tasten nacheinander und lässt sie rückwärts los (ein Block für SendInput).</summary>
    public static void Chord(ushort[] keys)
    {
        var inputs = new List<INPUT>();
        inputs.AddRange(keys.Select(k => Key(k, up: false)));
        inputs.AddRange(keys.Reverse().Select(k => Key(k, up: true)));
        Send(inputs.ToArray());
    }

    /// <summary>Tippt den Text ins Fenster vorn (Unicode, Zeilenumbruch = Eingabe).</summary>
    public static void Type(string text)
    {
        var inputs = new List<INPUT>();
        foreach (char c in text.Replace("\r\n", "\n", StringComparison.Ordinal))
        {
            if (c == '\n')
            {
                inputs.Add(Key(VkReturn, up: false));
                inputs.Add(Key(VkReturn, up: true));
            }
            else if (!char.IsControl(c))
            {
                inputs.Add(Unicode(c, up: false));
                inputs.Add(Unicode(c, up: true));
            }
        }

        Send(inputs.ToArray());
    }

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

    private static INPUT Key(ushort vk, bool up)
    {
        bool extended = vk is VkPrior or VkNext or VkEnd or VkHome or VkLeft or VkUp or VkRight or VkDown or VkDelete;
        uint flags = (up ? KEYEVENTF_KEYUP : 0) | (extended ? KEYEVENTF_EXTENDEDKEY : 0);
        return new INPUT
        {
            type = INPUT_KEYBOARD,
            u = new InputUnion { ki = new KEYBDINPUT { wVk = vk, wScan = (ushort)MapVirtualKey(vk, MAPVK_VK_TO_VSC), dwFlags = flags } },
        };
    }

    private static INPUT Unicode(char c, bool up) => new()
    {
        type = INPUT_KEYBOARD,
        u = new InputUnion { ki = new KEYBDINPUT { wVk = 0, wScan = c, dwFlags = KEYEVENTF_UNICODE | (up ? KEYEVENTF_KEYUP : 0) } },
    };

    private static void Send(INPUT[] inputs)
    {
        if (inputs.Length > 0 && SendInput((uint)inputs.Length, inputs, Marshal.SizeOf<INPUT>()) == 0)
        {
            throw new InvalidOperationException("Windows hat die Tasten nicht angenommen (Programm vorn läuft als Administrator?).");
        }
    }
}
