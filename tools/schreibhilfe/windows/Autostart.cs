using Microsoft.Win32;

namespace SparkSchreibhilfe;

/// <summary>"Mit Windows starten": Eintrag unter HKCU\Software\Microsoft\Windows\CurrentVersion\Run.</summary>
internal static class Autostart
{
    private const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
    private const string ValueName = "SparkSchreibhilfe";

    private static string Command => $"\"{Environment.ProcessPath}\"";

    /// <summary>Nur an, wenn der Eintrag auf genau diese .exe zeigt (sonst wurde sie verschoben).</summary>
    public static bool IsEnabled
    {
        get
        {
            using RegistryKey? key = Registry.CurrentUser.OpenSubKey(RunKey);
            return key?.GetValue(ValueName) is string value &&
                   string.Equals(value, Command, StringComparison.OrdinalIgnoreCase);
        }
    }

    public static void Set(bool enabled)
    {
        using RegistryKey key = Registry.CurrentUser.CreateSubKey(RunKey, writable: true);
        if (enabled)
        {
            key.SetValue(ValueName, Command, RegistryValueKind.String);
        }
        else
        {
            key.DeleteValue(ValueName, throwOnMissingValue: false);
        }
    }
}
