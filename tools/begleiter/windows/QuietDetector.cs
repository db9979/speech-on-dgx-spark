using Microsoft.Win32;

namespace SparkBegleiter;

/// <summary>
/// Teil "quiet": erkennt, ob gerade „Nicht stören“ ist – ohne etwas mitzuhören oder Inhalte zu lesen:
/// <list type="bullet">
/// <item>Telefonat/Videokonferenz: Mikrofon oder Kamera wird von einem anderen Programm benutzt. Windows führt das
/// unter HKCU\Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\{microphone,webcam}
/// (Store-Apps als Unterschlüssel, Desktop-Programme unter NonPackaged\…): LastUsedTimeStop == 0 heißt „läuft“.
/// Der Begleiter selbst (Diktieren, Weckwort, Besprechung) zählt nicht.</item>
/// <item>Präsentation: PowerPoint-Bildschirmpräsentation vorne (Fensterklasse "screenClass") oder Windows meldet
/// Präsentationsmodus bzw. ein Vollbildprogramm (SHQueryUserNotificationState).</item>
/// </list>
/// </summary>
internal static class QuietDetector
{
    private const string ConsentStore = @"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\";

    /// <summary>"call", "present" oder <c>null</c> (nicht beschäftigt).</summary>
    public static string? Detect()
    {
        if (InUse("microphone") || InUse("webcam"))
        {
            return "call";
        }

        return Presenting() ? "present" : null;
    }

    /// <summary>Der eigene Pfad in der Schreibweise von NonPackaged (Backslash → '#').</summary>
    private static readonly string? OwnKey = Environment.ProcessPath?.Replace('\\', '#');

    private static bool InUse(string capability)
    {
        try
        {
            using RegistryKey? root = Registry.CurrentUser.OpenSubKey(ConsentStore + capability);
            if (root is null)
            {
                return false;
            }

            foreach (string name in root.GetSubKeyNames())
            {
                if (string.Equals(name, "NonPackaged", StringComparison.OrdinalIgnoreCase))
                {
                    using RegistryKey? desktop = root.OpenSubKey(name);
                    if (desktop is null)
                    {
                        continue;
                    }

                    foreach (string app in desktop.GetSubKeyNames())
                    {
                        if (OwnKey is not null && string.Equals(app, OwnKey, StringComparison.OrdinalIgnoreCase))
                        {
                            continue; // eigene Aufnahme
                        }

                        using RegistryKey? entry = desktop.OpenSubKey(app);
                        if (Running(entry))
                        {
                            return true;
                        }
                    }
                }
                else
                {
                    using RegistryKey? entry = root.OpenSubKey(name);
                    if (Running(entry))
                    {
                        return true;
                    }
                }
            }
        }
        catch (Exception ex) when (ex is System.Security.SecurityException or IOException or UnauthorizedAccessException)
        {
            // Nicht lesbar – dann eben „nicht beschäftigt“.
        }

        return false;
    }

    /// <summary>Begonnen (Start &gt; 0) und noch nicht beendet (Stop == 0).</summary>
    private static bool Running(RegistryKey? entry)
    {
        if (entry is null)
        {
            return false;
        }

        long start = ToLong(entry.GetValue("LastUsedTimeStart"));
        long stop = ToLong(entry.GetValue("LastUsedTimeStop"));
        return start > 0 && stop == 0;
    }

    private static long ToLong(object? value) => value switch
    {
        long l => l,
        int i => i,
        byte[] { Length: 8 } b => BitConverter.ToInt64(b, 0),
        _ => -1,
    };

    private static bool Presenting()
    {
        try
        {
            IntPtr front = NativeMethods.GetForegroundWindow();
            if (front != IntPtr.Zero)
            {
                char[] buffer = new char[64];
                int length = NativeMethods.GetClassName(front, buffer, buffer.Length);
                if (length > 0 && new string(buffer, 0, length) == "screenClass")
                {
                    return true; // PowerPoint-Bildschirmpräsentation
                }
            }

            if (NativeMethods.SHQueryUserNotificationState(out int state) == 0 &&
                state is NativeMethods.QUNS_PRESENTATION_MODE or NativeMethods.QUNS_BUSY)
            {
                return true;
            }
        }
        catch (Exception ex) when (ex is EntryPointNotFoundException or DllNotFoundException)
        {
            // älteres Windows
        }

        return false;
    }
}
