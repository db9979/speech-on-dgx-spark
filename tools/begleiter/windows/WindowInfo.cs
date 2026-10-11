using System.Diagnostics;

namespace SparkBegleiter;

/// <summary>Name des Programms hinter einem Fenster (für „aus Outlook“ in der Schreibhilfe).</summary>
internal static class WindowInfo
{
    public static string? AppName(IntPtr hwnd)
    {
        if (hwnd == IntPtr.Zero)
        {
            return null;
        }

        try
        {
            _ = NativeMethods.GetWindowThreadProcessId(hwnd, out uint pid);
            if (pid == 0 || pid == (uint)Environment.ProcessId)
            {
                return null;
            }

            using Process process = Process.GetProcessById((int)pid);
            string? description = null;
            try
            {
                description = process.MainModule?.FileVersionInfo.FileDescription;
            }
            catch (Exception ex) when (ex is System.ComponentModel.Win32Exception or InvalidOperationException or NotSupportedException)
            {
                // Programm mit höheren Rechten oder anderer Bauart: nur der Prozessname.
            }

            string name = string.IsNullOrWhiteSpace(description) ? process.ProcessName : description.Trim();
            return name.Length > 40 ? name[..40] + "…" : name;
        }
        catch (Exception ex) when (ex is ArgumentException or InvalidOperationException or System.ComponentModel.Win32Exception)
        {
            return null;
        }
    }
}

/// <summary>
/// Teil "context": nur die ART des Programms, aus dem der Text kommt (outlook, word, browser …), ermittelt aus
/// dem Prozessnamen des Fensters. Fenstertitel, Programmnamen oder Inhalte gehen nie an den Spark.
/// </summary>
internal static class AppCategory
{
    private static readonly Dictionary<string, string> ByProcess = new(StringComparer.OrdinalIgnoreCase)
    {
        ["outlook"] = "outlook",
        ["olk"] = "outlook",
        ["winword"] = "word",
        ["excel"] = "excel",
        ["powerpnt"] = "powerpoint",
        ["msedge"] = "browser",
        ["chrome"] = "browser",
        ["firefox"] = "browser",
        ["brave"] = "browser",
        ["opera"] = "browser",
        ["vivaldi"] = "browser",
        ["ms-teams"] = "teams",
        ["teams"] = "teams",
        ["slack"] = "chat",
        ["discord"] = "chat",
        ["whatsapp"] = "chat",
        ["whatsapp.root"] = "chat",
        ["telegram"] = "chat",
        ["signal"] = "chat",
        ["code"] = "code",
        ["devenv"] = "code",
        ["idea"] = "code",
        ["idea64"] = "code",
        ["notepad++"] = "code",
    };

    /// <summary>Kategorie des Fensters, oder <c>null</c> ohne Fenster.</summary>
    public static string? FromWindow(IntPtr hwnd)
    {
        if (hwnd == IntPtr.Zero)
        {
            return null;
        }

        string? name = ProcessName(hwnd);
        return name is not null && ByProcess.TryGetValue(name, out string? category) ? category : "other";
    }

    /// <summary>Prozessname ohne ".exe" (z. B. "OUTLOOK"), oder <c>null</c>.</summary>
    public static string? ProcessName(IntPtr hwnd)
    {
        try
        {
            _ = NativeMethods.GetWindowThreadProcessId(hwnd, out uint pid);
            if (pid == 0)
            {
                return null;
            }

            using Process process = Process.GetProcessById((int)pid);
            return process.ProcessName;
        }
        catch (Exception ex) when (ex is ArgumentException or InvalidOperationException or System.ComponentModel.Win32Exception)
        {
            return null;
        }
    }
}
