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
