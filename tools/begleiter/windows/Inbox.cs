using System.Runtime.InteropServices;
using System.Text.Json;

namespace SparkBegleiter;

/// <summary>
/// Teil "inbox": erledigte Kennungen (damit nichts doppelt ankommt, auch über einen Neustart hinweg) und das
/// sichere Ablegen von Dateien in &lt;Downloads&gt;\Vom Spark: Name ohne Pfadteile und verbotene Zeichen,
/// nie überschreiben („name (2).ext“).
/// </summary>
internal static class InboxStore
{
    private static readonly HashSet<string> Seen = LoadSeen();

    private static readonly string[] Reserved =
    {
        "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    };

    private static string SeenPath => Path.Combine(AppConfig.LocalFolder, "inbox-erledigt.json");

    public static bool IsSeen(string id) => Seen.Contains(id);

    public static void MarkSeen(string id)
    {
        if (Seen.Add(id))
        {
            try
            {
                Directory.CreateDirectory(AppConfig.LocalFolder);
                File.WriteAllText(SeenPath, JsonSerializer.Serialize(Seen.TakeLast(500).ToList()));
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
                // Dann nur im Speicher.
            }
        }
    }

    private static HashSet<string> LoadSeen()
    {
        try
        {
            if (File.Exists(SeenPath) && JsonSerializer.Deserialize<List<string>>(File.ReadAllText(SeenPath)) is { } list)
            {
                return new HashSet<string>(list.Where(SparkClient.IsSafeId), StringComparer.Ordinal);
            }
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException)
        {
            // neu anfangen
        }

        return new HashSet<string>(StringComparer.Ordinal);
    }

    /// <summary>&lt;Downloads&gt;\Vom Spark (der echte Downloads-Ordner, auch wenn er verschoben wurde).</summary>
    public static string Folder => Path.Combine(Downloads(), "Vom Spark");

    internal static string Downloads()
    {
        try
        {
            Guid id = NativeMethods.FolderDownloads;
            if (NativeMethods.SHGetKnownFolderPath(ref id, 0, IntPtr.Zero, out IntPtr path) == 0 && path != IntPtr.Zero)
            {
                try
                {
                    string? folder = Marshal.PtrToStringUni(path);
                    if (!string.IsNullOrEmpty(folder))
                    {
                        return folder;
                    }
                }
                finally
                {
                    Marshal.FreeCoTaskMem(path);
                }
            }
        }
        catch (Exception ex) when (ex is EntryPointNotFoundException or DllNotFoundException)
        {
            // unten
        }

        return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads");
    }

    /// <summary>Nur der Dateiname, ohne Pfadteile, Steuer- und verbotene Zeichen, höchstens 120 Zeichen.</summary>
    public static string SafeName(string? name)
    {
        string n = (name ?? "").Replace('/', '\\');
        int slash = n.LastIndexOf('\\');
        if (slash >= 0)
        {
            n = n[(slash + 1)..];
        }

        char[] invalid = Path.GetInvalidFileNameChars();
        n = new string(n.Select(c => char.IsControl(c) || invalid.Contains(c) || c == ':' ? '_' : c).ToArray()).Trim().Trim('.', ' ');
        if (n.Length == 0)
        {
            n = "Datei";
        }

        string stem = Path.GetFileNameWithoutExtension(n);
        string ext = Path.GetExtension(n);
        if (ext.Length > 16)
        {
            ext = "";
            stem = n;
        }

        if (Reserved.Contains(stem.ToUpperInvariant()))
        {
            stem = "_" + stem;
        }

        if (stem.Length + ext.Length > 120)
        {
            stem = stem[..Math.Max(1, 120 - ext.Length)];
        }

        return stem + ext;
    }

    /// <summary>Schreibt die Datei neu (nie überschreiben) und gibt den vollen Pfad zurück.</summary>
    public static string Save(string name, byte[] data)
    {
        string folder = Folder;
        Directory.CreateDirectory(folder);
        string safe = SafeName(name);
        string stem = Path.GetFileNameWithoutExtension(safe);
        string ext = Path.GetExtension(safe);
        for (int i = 1; i < 1000; i++)
        {
            string candidate = Path.Combine(folder, i == 1 ? safe : $"{stem} ({i}){ext}");
            try
            {
                using var stream = new FileStream(candidate, FileMode.CreateNew, FileAccess.Write, FileShare.None);
                stream.Write(data);
                return candidate;
            }
            catch (IOException) when (File.Exists(candidate))
            {
                // gibt es schon – nächste Nummer
            }
        }

        throw new IOException("Zu viele Dateien mit diesem Namen.");
    }
}
