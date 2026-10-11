using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json;

namespace SparkBegleiter;

/// <summary>
/// Teil "folder": beobachtet einen lokalen Ordner (Standard %USERPROFILE%\Spark-Wissen) mit FileSystemWatcher und einem
/// Durchgang beim Start. Neue oder geänderte Dateien (Größe + Änderungszeit + SHA-256, Liste in
/// %LOCALAPPDATA%\Spark Begleiter\wissen.json) gehen nach 10 Sekunden Ruhe an /api/desk/file mit what=wissen.
/// Höchstens 50 am Tag; 409 (schon da) zählt als erledigt. Versteckte und Zwischendateien werden übersprungen.
/// </summary>
internal sealed class FolderWatcher : IDisposable
{
    public const int MaxPerDay = 50;
    private static readonly TimeSpan Quiet = TimeSpan.FromSeconds(10);
    private static readonly TimeSpan RetryAfter = TimeSpan.FromMinutes(5);
    private static readonly string[] TempExtensions = { ".tmp", ".part", ".crdownload", ".partial", ".download" };

    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = false };

    private readonly string _folder;
    private readonly Func<(string Base, string Key)?> _credentials;
    private readonly Action<string> _notify;
    private readonly Action<SparkException> _report;
    private readonly FileSystemWatcher? _watcher;
    private readonly System.Windows.Forms.Timer _timer = new() { Interval = 2000 };
    private readonly object _lock = new();
    private readonly HashSet<string> _dirty = new(StringComparer.OrdinalIgnoreCase);
    private readonly State _state;
    private DateTime _lastEvent = DateTime.MinValue;
    private DateTime _retryAt = DateTime.MinValue;
    private bool _rescan = true;
    private bool _busy;
    private bool _limitNotified;
    private bool _disposed;

    public FolderWatcher(string folder, Func<(string Base, string Key)?> credentials, Action<string> notify, Action<SparkException> report)
    {
        _folder = Path.GetFullPath(folder);
        _credentials = credentials;
        _notify = notify;
        _report = report;
        _state = State.Load();

        Directory.CreateDirectory(_folder);
        try
        {
            _watcher = new FileSystemWatcher(_folder)
            {
                IncludeSubdirectories = true,
                NotifyFilter = NotifyFilters.FileName | NotifyFilters.DirectoryName | NotifyFilters.LastWrite | NotifyFilters.Size,
                InternalBufferSize = 64 * 1024,
            };
            _watcher.Created += (_, e) => Touch(e.FullPath);
            _watcher.Changed += (_, e) => Touch(e.FullPath);
            _watcher.Renamed += (_, e) => Touch(e.FullPath);
            _watcher.Error += (_, _) => RescanLater();
            _watcher.EnableRaisingEvents = true;
        }
        catch (Exception ex) when (ex is ArgumentException or IOException or PlatformNotSupportedException)
        {
            _watcher = null; // dann nur der Durchgang beim Start
        }

        _lastEvent = DateTime.UtcNow - Quiet; // Durchgang beim Start ohne Wartezeit
        _timer.Tick += async (_, _) => await TickAsync();
        _timer.Start();
    }

    public string Folder => _folder;

    private void Touch(string path)
    {
        lock (_lock)
        {
            _dirty.Add(path);
            _lastEvent = DateTime.UtcNow;
        }
    }

    private void RescanLater()
    {
        lock (_lock)
        {
            _rescan = true;
            _lastEvent = DateTime.UtcNow;
        }
    }

    private async Task TickAsync()
    {
        if (_busy || _disposed)
        {
            return;
        }

        List<string> paths;
        lock (_lock)
        {
            if (DateTime.UtcNow - _lastEvent < Quiet || DateTime.UtcNow < _retryAt || (_dirty.Count == 0 && !_rescan))
            {
                return;
            }

            paths = _dirty.ToList();
            _dirty.Clear();
            if (_rescan)
            {
                _rescan = false;
                paths.AddRange(SafeEnumerate(_folder));
            }
        }

        _busy = true;
        try
        {
            await ProcessAsync(paths.Distinct(StringComparer.OrdinalIgnoreCase).ToList());
        }
        finally
        {
            _busy = false;
        }
    }

    private static IEnumerable<string> SafeEnumerate(string folder)
    {
        try
        {
            return Directory.EnumerateFiles(folder, "*", new EnumerationOptions
            {
                RecurseSubdirectories = true,
                IgnoreInaccessible = true,
                AttributesToSkip = FileAttributes.Hidden | FileAttributes.System | FileAttributes.Temporary,
            }).Take(5000).ToList();
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return Array.Empty<string>();
        }
    }

    private async Task ProcessAsync(List<string> paths)
    {
        int uploaded = 0;
        for (int i = 0; i < paths.Count && !_disposed; i++)
        {
            string path = paths[i];
            if (Directory.Exists(path))
            {
                paths.AddRange(SafeEnumerate(path).Where(p => !paths.Contains(p, StringComparer.OrdinalIgnoreCase)));
                continue;
            }

            if (Skip(path) || !File.Exists(path))
            {
                continue;
            }

            Outcome outcome = await HandleAsync(path);
            if (outcome == Outcome.Uploaded)
            {
                uploaded++;
            }
            else if (outcome == Outcome.Retry)
            {
                // Spark nicht erreichbar o. Ä.: den Rest später noch einmal
                lock (_lock)
                {
                    foreach (string rest in paths.Skip(i))
                    {
                        _dirty.Add(rest);
                    }
                }

                _retryAt = DateTime.UtcNow + RetryAfter;
                break;
            }
            else if (outcome == Outcome.Stop)
            {
                break;
            }
        }

        _state.Save();
        if (uploaded > 0)
        {
            _notify(uploaded == 1 ? "1 Datei ins Wissen übernommen." : $"{uploaded} Dateien ins Wissen übernommen.");
        }
    }

    private enum Outcome
    {
        Skipped,
        Uploaded,
        Retry,
        Stop,
    }

    /// <summary>Versteckte Dateien, Office-Sperrdateien (~$…) und halbe Downloads (.tmp, .part, .crdownload) auslassen.</summary>
    public static bool Skip(string path)
    {
        string name = Path.GetFileName(path);
        string ext = Path.GetExtension(path).ToLowerInvariant();
        if (name.Length == 0 || name.StartsWith("~$", StringComparison.Ordinal) || name.StartsWith('.') || name.StartsWith('~') ||
            TempExtensions.Contains(ext) || !FileMenu.IsSupported(path))
        {
            return true;
        }

        try
        {
            FileAttributes attributes = File.GetAttributes(path);
            return (attributes & (FileAttributes.Hidden | FileAttributes.System | FileAttributes.Temporary | FileAttributes.Directory)) != 0;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return true;
        }
    }

    private async Task<Outcome> HandleAsync(string path)
    {
        FileInfo info;
        try
        {
            info = new FileInfo(path);
            info.Refresh();
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or ArgumentException)
        {
            return Outcome.Skipped;
        }

        long mtime = info.LastWriteTimeUtc.Ticks;
        string key = info.FullName;
        if (_state.Files.TryGetValue(key, out Entry? known) && known.Size == info.Length && known.Mtime == mtime)
        {
            return Outcome.Skipped;
        }

        if (info.Length == 0 || info.Length > SparkClient.MaxFileBytes)
        {
            return Outcome.Skipped;
        }

        byte[] data;
        try
        {
            data = await File.ReadAllBytesAsync(info.FullName);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            Touch(path); // noch in Arbeit (gesperrt): später noch einmal
            return Outcome.Skipped;
        }

        string sha = Convert.ToHexString(await Task.Run(() => SHA256.HashData(data)));
        if (known is not null && known.Sha256 == sha)
        {
            _state.Files[key] = new Entry { Size = info.Length, Mtime = mtime, Sha256 = sha };
            return Outcome.Skipped; // nur die Zeit hat sich geändert
        }

        string today = DateTime.Now.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
        if (_state.Day != today)
        {
            _state.Day = today;
            _state.Count = 0;
            _limitNotified = false;
        }

        if (_state.Count >= MaxPerDay)
        {
            if (!_limitNotified)
            {
                _limitNotified = true;
                _notify($"Heute sind schon {MaxPerDay} Dateien ins Wissen gegangen. Der Rest folgt morgen.");
            }

            lock (_lock)
            {
                _dirty.Add(path);
            }

            _retryAt = DateTime.Now.Date.AddDays(1).ToUniversalTime();
            return Outcome.Stop;
        }

        if (_credentials() is not { } creds)
        {
            return Outcome.Stop;
        }

        try
        {
            _ = await SparkClient.FileAsync(creds.Base, creds.Key, data, info.Name, FileMenu.ContentType(info.Extension), "wissen", null, CancellationToken.None);
            _state.Count++;
            _state.Files[key] = new Entry { Size = info.Length, Mtime = mtime, Sha256 = sha };
            return Outcome.Uploaded;
        }
        catch (SparkException ex) when (ex.Status == 409)
        {
            _state.Files[key] = new Entry { Size = info.Length, Mtime = mtime, Sha256 = sha }; // schon im Wissen
            return Outcome.Skipped;
        }
        catch (SparkException ex) when (ex.Status is 400 or 413 or 415 or 422)
        {
            // Diese Fassung nimmt der Spark nicht an – merken, damit sie nicht immer wieder geschickt wird.
            _state.Files[key] = new Entry { Size = info.Length, Mtime = mtime, Sha256 = sha };
            return Outcome.Skipped;
        }
        catch (SparkException ex)
        {
            if (ex.Status is 401 or 403 or 503)
            {
                _report(ex);
            }

            return Outcome.Retry;
        }
    }

    public void Dispose()
    {
        _disposed = true;
        _timer.Stop();
        _timer.Dispose();
        _watcher?.Dispose();
    }

    private sealed class Entry
    {
        public long Size { get; set; }

        public long Mtime { get; set; }

        public string Sha256 { get; set; } = "";
    }

    /// <summary>Lokale Liste der übernommenen Dateien und der Tageszähler.</summary>
    private sealed class State
    {
        private static string FilePath => Path.Combine(AppConfig.LocalFolder, "wissen.json");

        public Dictionary<string, Entry> Files { get; set; } = new(StringComparer.OrdinalIgnoreCase);

        public string Day { get; set; } = "";

        public int Count { get; set; }

        public static State Load()
        {
            try
            {
                if (File.Exists(FilePath) && JsonSerializer.Deserialize<State>(File.ReadAllText(FilePath), JsonOptions) is { } state)
                {
                    state.Files = new Dictionary<string, Entry>(state.Files, StringComparer.OrdinalIgnoreCase);
                    return state;
                }
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException)
            {
                // neu anfangen
            }

            return new State();
        }

        public void Save()
        {
            try
            {
                Directory.CreateDirectory(AppConfig.LocalFolder);
                string temp = FilePath + ".tmp";
                File.WriteAllText(temp, JsonSerializer.Serialize(this, JsonOptions));
                File.Move(temp, FilePath, overwrite: true);
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
                // beim nächsten Mal
            }
        }
    }
}
