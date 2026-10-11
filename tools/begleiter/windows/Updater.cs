using System.Diagnostics;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Security.Cryptography;

namespace SparkBegleiter;

/// <summary>Die neue Version laut GET /api/desk/config ("update"): Nummer, Größe und SHA-256 der Datei.</summary>
internal sealed class UpdateInfo
{
    public string Version { get; set; } = "";

    public long Size { get; set; }

    public string Sha256 { get; set; } = "";

    public bool SameAs(UpdateInfo? other) =>
        other is not null && other.Version == Version && other.Size == Size &&
        string.Equals(other.Sha256, Sha256, StringComparison.OrdinalIgnoreCase);
}

internal enum UpdatePhase
{
    /// <summary>Entwicklungsversion (1.0.0): nie Updates anbieten.</summary>
    Development,

    /// <summary>Noch keine Antwort vom Spark.</summary>
    Unknown,

    UpToDate,
    Available,
    Downloading,
    Ready,
    Installing,
    Failed,
}

/// <summary>
/// Updates laut Vertrag: Die neue Version kommt nur vom eigenen Spark (GET /api/desk/update?arch=…),
/// wird nach %LOCALAPPDATA%\Spark Begleiter\update\SparkBegleiter.new.exe geladen und nur installiert,
/// wenn Größe UND SHA-256 stimmen – und nie ohne Klick der Person. Mit "Updates automatisch laden" wird
/// im Hintergrund geladen, installiert wird trotzdem erst nach dem Klick auf „Aktualisieren“.
/// Installiert wird von der neuen .exe selbst (<see cref="UpdateInstaller"/>), nachdem dieses Programm
/// beendet ist; geht dabei etwas schief, bleibt die alte .exe und startet wieder.
/// </summary>
internal sealed class Updater : IDisposable
{
    public const string Corrupt = "Update beschädigt, nichts geändert.";

    /// <summary>Obergrenze für die Datei (Schutz vor Unsinn vom Server).</summary>
    public const long MaxSize = 512L * 1024 * 1024;

    private static readonly TimeSpan RetryAfter = TimeSpan.FromMinutes(30);

    private readonly Func<(string Base, string Key)?> _credentials;
    private CancellationTokenSource? _cts;
    private DateTime _failedAt = DateTime.MinValue;
    private bool _installRequested;
    private int _lastPercent = -1;

    public Updater(Func<(string Base, string Key)?> credentials)
    {
        _credentials = credentials;
        Phase = IsDevelopment ? UpdatePhase.Development : UpdatePhase.Unknown;
    }

    /// <summary>Zustand hat sich geändert (immer im UI-Thread).</summary>
    public event EventHandler? Changed;

    /// <summary>Die neue Version liegt geprüft bereit (für einen einmaligen Hinweis).</summary>
    public event EventHandler? Ready;

    /// <summary>Der Installer läuft – das Programm muss sich jetzt beenden.</summary>
    public event EventHandler? InstallStarted;

    /// <summary>Version dieses Programms aus der Assembly (CI: -p:Version=1.0.NNN).</summary>
    public static Version Current { get; } = Normalize(typeof(Updater).Assembly.GetName().Version);

    public static string CurrentText => Current.ToString(3);

    /// <summary>Standardwert 1.0.0 im csproj = lokal gebaut: keine Updates.</summary>
    public static bool IsDevelopment => Current.Major == 1 && Current.Minor == 0 && Current.Build == 0;

    /// <summary>"x64" oder "arm64" – wie die Dateien SparkBegleiter-&lt;arch&gt;.exe.</summary>
    public static string Arch => RuntimeInformation.ProcessArchitecture == Architecture.Arm64 ? "arm64" : "x64";

    public static string ArchLabel => Arch == "arm64" ? "Windows ARM" : "Windows x64";

    public static string Folder =>
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Spark Begleiter", "update");

    public static string NewExe => Path.Combine(Folder, "SparkBegleiter.new.exe");

    public UpdatePhase Phase { get; private set; }

    public UpdateInfo? Info { get; private set; }

    /// <summary>Fortschritt beim Laden, 0…1.</summary>
    public double Progress { get; private set; }

    public string? Error { get; private set; }

    /// <summary>Nach dem Laden gleich installieren (die Person hat schon geklickt).</summary>
    public bool InstallRequested => _installRequested;

    public static string SizeText(long bytes) =>
        string.Create(CultureInfo.GetCultureInfo("de-DE"), $"{Math.Max(1, (int)Math.Round(bytes / 1048576.0))} MB");

    /// <summary>Gültige Versionsnummer wie 1.0.350.</summary>
    public static bool TryParseVersion(string? text, out Version version)
    {
        version = new Version(0, 0, 0);
        if (string.IsNullOrEmpty(text) || text.Length > 32 || !text.All(c => char.IsAsciiDigit(c) || c == '.') ||
            !Version.TryParse(text, out Version? parsed) || parsed.Build < 0)
        {
            return false;
        }

        version = Normalize(parsed);
        return true;
    }

    private static Version Normalize(Version? v) =>
        v is null ? new Version(1, 0, 0) : new Version(v.Major, v.Minor, Math.Max(0, v.Build));

    /// <summary>Neue Einstellungen vom Spark: Update da, weg oder anders?</summary>
    public void OnConfig(UpdateInfo? info, bool autoDownload)
    {
        if (IsDevelopment)
        {
            Set(UpdatePhase.Development);
            return;
        }

        if (info is null || !TryParseVersion(info.Version, out Version offered) || offered <= Current)
        {
            Cancel();
            bool had = Info is not null;
            Info = null;
            Error = null;
            _installRequested = false;
            if (had)
            {
                TryDelete(NewExe);
            }

            Set(UpdatePhase.UpToDate);
            return;
        }

        if (info.SameAs(Info))
        {
            if (Phase is UpdatePhase.Available or UpdatePhase.Failed && autoDownload && DateTime.UtcNow - _failedAt > RetryAfter)
            {
                _ = DownloadAsync();
            }

            return;
        }

        Cancel();
        Info = info;
        Error = null;
        _installRequested = false;
        _failedAt = DateTime.MinValue;
        Set(UpdatePhase.Available);
        _ = AdoptAsync(info, autoDownload);
    }

    /// <summary>Liegt die Datei schon geprüft da (z. B. nach einem Neustart), muss nichts geladen werden.</summary>
    private async Task AdoptAsync(UpdateInfo info, bool autoDownload)
    {
        bool present = await Task.Run(() => FileMatches(NewExe, info)).ConfigureAwait(true);
        if (!ReferenceEquals(Info, info) || Phase != UpdatePhase.Available)
        {
            return;
        }

        if (present)
        {
            Set(UpdatePhase.Ready);
            Ready?.Invoke(this, EventArgs.Empty);
        }
        else
        {
            TryDelete(NewExe);
            if (autoDownload)
            {
                await DownloadAsync().ConfigureAwait(true);
            }
        }
    }

    /// <summary>Der Klick auf „Aktualisieren“: laden (falls nötig) und installieren.</summary>
    public void Request()
    {
        switch (Phase)
        {
            case UpdatePhase.Ready:
                _ = InstallAsync();
                break;
            case UpdatePhase.Available:
            case UpdatePhase.Failed when Info is not null:
                _installRequested = true;
                _ = DownloadAsync();
                break;
            case UpdatePhase.Downloading:
                _installRequested = true;
                Changed?.Invoke(this, EventArgs.Empty);
                break;
        }
    }

    /// <summary>Abbrechen und vergessen (z. B. beim Entkoppeln).</summary>
    public void Reset()
    {
        Cancel();
        Info = null;
        Error = null;
        _installRequested = false;
        Set(IsDevelopment ? UpdatePhase.Development : UpdatePhase.Unknown);
    }

    private async Task DownloadAsync()
    {
        if (Info is not { } info || Phase == UpdatePhase.Downloading || _credentials() is not { } creds)
        {
            return;
        }

        Cancel();
        var cts = new CancellationTokenSource();
        _cts = cts;
        Progress = 0;
        _lastPercent = -1;
        Error = null;
        Set(UpdatePhase.Downloading);

        string part = NewExe + ".part";
        try
        {
            // Schon geprüft vorhanden (z. B. Ordner war nicht beschreibbar)? Dann nicht noch einmal laden.
            if (await Task.Run(() => FileMatches(NewExe, info), cts.Token).ConfigureAwait(true))
            {
                if (ReferenceEquals(Info, info))
                {
                    Set(UpdatePhase.Ready);
                    if (_installRequested)
                    {
                        await InstallAsync().ConfigureAwait(true);
                    }
                }

                return;
            }

            Directory.CreateDirectory(Folder);
            var progress = new Progress<long>(bytes => OnProgress(info, bytes));
            (long size, string sha) result;
            var file = new FileStream(part, FileMode.Create, FileAccess.Write, FileShare.None, 81920, useAsync: true);
            await using (file.ConfigureAwait(true))
            {
                result = await SparkClient.DownloadUpdateAsync(creds.Base, creds.Key, Arch, info.Size, file, progress, cts.Token).ConfigureAwait(true);
                await file.FlushAsync(cts.Token).ConfigureAwait(true);
            }

            if (result.size != info.Size || !string.Equals(result.sha, info.Sha256, StringComparison.OrdinalIgnoreCase))
            {
                TryDelete(part);
                Fail(info, Corrupt);
                return;
            }

            File.Move(part, NewExe, overwrite: true);
            if (!ReferenceEquals(Info, info))
            {
                return;
            }

            Set(UpdatePhase.Ready);
            Ready?.Invoke(this, EventArgs.Empty);
            if (_installRequested)
            {
                await InstallAsync().ConfigureAwait(true);
            }
        }
        catch (OperationCanceledException)
        {
            TryDelete(part);
            if (ReferenceEquals(Info, info) && Phase == UpdatePhase.Downloading)
            {
                Set(UpdatePhase.Available);
            }
        }
        catch (SparkException ex)
        {
            TryDelete(part);
            Fail(info, ex.Message);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            TryDelete(part);
            Fail(info, "Die neue Version ließ sich nicht speichern: " + ex.Message);
        }
        finally
        {
            if (ReferenceEquals(_cts, cts))
            {
                _cts = null;
            }

            cts.Dispose();
        }
    }

    private void OnProgress(UpdateInfo info, long bytes)
    {
        if (!ReferenceEquals(Info, info) || Phase != UpdatePhase.Downloading || info.Size <= 0)
        {
            return;
        }

        Progress = Math.Clamp((double)bytes / info.Size, 0, 1);
        int percent = (int)(Progress * 100);
        if (percent != _lastPercent)
        {
            _lastPercent = percent;
            Changed?.Invoke(this, EventArgs.Empty);
        }
    }

    /// <summary>
    /// Noch einmal prüfen, dann die neue .exe als Installer starten. Er wartet, bis dieses Programm beendet
    /// ist, ersetzt die .exe und startet sie neu. Ist der Ordner nicht beschreibbar: Ordner öffnen, Hinweis.
    /// </summary>
    private async Task InstallAsync()
    {
        if (Phase != UpdatePhase.Ready || Info is not { } info)
        {
            return;
        }

        _installRequested = false;
        Set(UpdatePhase.Installing);

        string? target = Environment.ProcessPath;
        if (string.IsNullOrEmpty(target) || !File.Exists(target))
        {
            Fail(info, "Der Begleiter findet seine eigene Datei nicht – bitte die neue Version von Hand installieren.");
            return;
        }

        bool ok = await Task.Run(() => FileMatches(NewExe, info)).ConfigureAwait(true);
        if (!ReferenceEquals(Info, info))
        {
            return;
        }

        if (!ok)
        {
            TryDelete(NewExe);
            Fail(info, Corrupt);
            return;
        }

        string folder = Path.GetDirectoryName(target)!;
        if (!CanWrite(folder))
        {
            ShowInExplorer(NewExe);
            Fail(info, $"Der Ordner „{folder}“ ist nicht beschreibbar. Die geprüfte neue Version liegt im geöffneten "
                       + "Ordner – bitte die alte .exe damit selbst ersetzen.");
            return;
        }

        try
        {
            var start = new ProcessStartInfo(NewExe) { UseShellExecute = false, WorkingDirectory = Folder };
            start.ArgumentList.Add(UpdateInstaller.InstallArgument);
            start.ArgumentList.Add(Environment.ProcessId.ToString(CultureInfo.InvariantCulture));
            start.ArgumentList.Add(target);
            using Process? helper = Process.Start(start);
            if (helper is null)
            {
                Fail(info, "Das Update ließ sich nicht starten.");
                return;
            }
        }
        catch (Exception ex) when (ex is System.ComponentModel.Win32Exception or IOException or UnauthorizedAccessException)
        {
            Fail(info, "Das Update ließ sich nicht starten: " + ex.Message);
            return;
        }

        InstallStarted?.Invoke(this, EventArgs.Empty);
    }

    private void Fail(UpdateInfo info, string message)
    {
        if (!ReferenceEquals(Info, info))
        {
            return;
        }

        _failedAt = DateTime.UtcNow;
        _installRequested = false;
        Error = message;
        Set(UpdatePhase.Failed);
    }

    private void Set(UpdatePhase phase)
    {
        Phase = phase;
        Changed?.Invoke(this, EventArgs.Empty);
    }

    private void Cancel()
    {
        try
        {
            _cts?.Cancel();
        }
        catch (ObjectDisposedException)
        {
            // schon fertig
        }

        _cts = null;
    }

    /// <summary>Größe und SHA-256 der Datei stimmen mit den Angaben des Spark überein.</summary>
    public static bool FileMatches(string path, UpdateInfo info)
    {
        try
        {
            var file = new FileInfo(path);
            if (!file.Exists || file.Length != info.Size)
            {
                return false;
            }

            using FileStream stream = file.OpenRead();
            string sha = Convert.ToHexString(SHA256.HashData(stream));
            return string.Equals(sha, info.Sha256, StringComparison.OrdinalIgnoreCase);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return false;
        }
    }

    private static bool CanWrite(string folder)
    {
        string probe = Path.Combine(folder, ".spark-begleiter-" + Guid.NewGuid().ToString("N") + ".tmp");
        try
        {
            using (File.Create(probe, 1, FileOptions.DeleteOnClose))
            {
            }

            return true;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return false;
        }
    }

    private static void ShowInExplorer(string path)
    {
        try
        {
            using Process? explorer = Process.Start(new ProcessStartInfo("explorer.exe", "/select,\"" + path + "\"") { UseShellExecute = true });
        }
        catch (System.ComponentModel.Win32Exception)
        {
            // Dann nur der Hinweis.
        }
    }

    public static void TryDelete(string path)
    {
        try
        {
            File.Delete(path);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            // Später noch einmal.
        }
    }

    /// <summary>Nach einem Update: alte .exe (.old) und die geladene Datei aufräumen (der Installer endet gerade).</summary>
    public static async Task CleanupAfterUpdateAsync()
    {
        string? exe = Environment.ProcessPath;
        for (int attempt = 0; attempt < 10; attempt++)
        {
            await Task.Delay(TimeSpan.FromSeconds(2)).ConfigureAwait(false);
            if (exe is not null)
            {
                TryDelete(exe + ".old");
            }

            TryDelete(NewExe);
            if ((exe is null || !File.Exists(exe + ".old")) && !File.Exists(NewExe))
            {
                return;
            }
        }
    }

    public void Dispose() => Cancel();
}

/// <summary>
/// Läuft als neue .exe mit "--update-install &lt;pid&gt; &lt;ziel&gt;": wartet, bis die alte Version beendet ist,
/// legt sich als &lt;ziel&gt;.new daneben, benennt die alte in &lt;ziel&gt;.old um und sich selbst in &lt;ziel&gt;,
/// startet sie mit "--updated". Bei jedem Fehler bleibt (bzw. kommt zurück) die alte .exe und startet mit
/// "--update-failed".
/// </summary>
internal static class UpdateInstaller
{
    public const string InstallArgument = "--update-install";
    public const string UpdatedArgument = "--updated";
    public const string FailedArgument = "--update-failed";

    public static int Run(string[] args)
    {
        if (args.Length < 3 || !int.TryParse(args[1], NumberStyles.None, CultureInfo.InvariantCulture, out int pid))
        {
            return 2;
        }

        string target;
        string? self = Environment.ProcessPath;
        try
        {
            target = Path.GetFullPath(args[2]);
        }
        catch (Exception ex) when (ex is ArgumentException or NotSupportedException or PathTooLongException)
        {
            return 2;
        }

        if (self is null || !target.EndsWith(".exe", StringComparison.OrdinalIgnoreCase) ||
            string.Equals(Path.GetFullPath(self), target, StringComparison.OrdinalIgnoreCase) || !File.Exists(target))
        {
            return 2;
        }

        if (!WaitForExit(pid))
        {
            return 3; // Die alte Version läuft noch – nichts anfassen.
        }

        string staged = target + ".new";
        string backup = target + ".old";
        bool replaced = false;
        try
        {
            Retry(() => File.Copy(self, staged, overwrite: true));
            if (new FileInfo(staged).Length != new FileInfo(self).Length)
            {
                throw new IOException("Kopie unvollständig");
            }

            Retry(() => File.Move(target, backup, overwrite: true));
            try
            {
                Retry(() => File.Move(staged, target));
                replaced = true;
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
                Restore(backup, target);
            }
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            // Alte .exe ist unverändert (oder wiederhergestellt).
        }
        finally
        {
            Updater.TryDelete(staged);
        }

        Start(target, replaced ? UpdatedArgument : FailedArgument);
        return replaced ? 0 : 1;
    }

    private static bool WaitForExit(int pid)
    {
        try
        {
            using Process old = Process.GetProcessById(pid);
            return old.WaitForExit(60000);
        }
        catch (ArgumentException)
        {
            return true; // schon beendet
        }
        catch (InvalidOperationException)
        {
            return true;
        }
    }

    private static void Restore(string backup, string target)
    {
        try
        {
            if (!File.Exists(target))
            {
                Retry(() => File.Move(backup, target));
            }
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            try
            {
                File.Copy(backup, target, overwrite: false);
            }
            catch (Exception inner) when (inner is IOException or UnauthorizedAccessException)
            {
                // Nichts mehr zu machen; die alte Datei liegt als .old daneben.
            }
        }
    }

    /// <summary>Kurz nach dem Beenden kann die .exe noch gesperrt sein (Virenscanner) – einige Male versuchen.</summary>
    private static void Retry(Action action)
    {
        for (int attempt = 1; ; attempt++)
        {
            try
            {
                action();
                return;
            }
            catch (Exception ex) when ((ex is IOException or UnauthorizedAccessException) && attempt < 40)
            {
                Thread.Sleep(250);
            }
        }
    }

    private static void Start(string exe, string argument)
    {
        try
        {
            var start = new ProcessStartInfo(exe) { UseShellExecute = false, WorkingDirectory = Path.GetDirectoryName(exe) };
            start.ArgumentList.Add(argument);
            using Process? process = Process.Start(start);
        }
        catch (Exception ex) when (ex is System.ComponentModel.Win32Exception or IOException)
        {
            // Dann startet die Person den Begleiter selbst.
        }
    }
}

/// <summary>Der Kaffee-Link: nur https://buymeacoffee.com/…, nur auf Klick im Standardbrowser.</summary>
internal static class CoffeeLink
{
    public const string Fallback = "https://buymeacoffee.com/zquu1xu570";

    /// <summary>Normierte Adresse, wenn sie https://buymeacoffee.com/&lt;name&gt; ist – sonst <c>null</c>.</summary>
    public static string? Accept(string? url)
    {
        if (string.IsNullOrWhiteSpace(url) || url.Length > 200 ||
            !Uri.TryCreate(url.Trim(), UriKind.Absolute, out Uri? uri) ||
            uri.Scheme != Uri.UriSchemeHttps || !uri.IsDefaultPort || uri.UserInfo.Length > 0 ||
            !string.Equals(uri.Host, "buymeacoffee.com", StringComparison.OrdinalIgnoreCase) ||
            uri.Query.Length > 0 || uri.Fragment.Length > 0)
        {
            return null;
        }

        string path = uri.AbsolutePath.TrimEnd('/');
        if (path.Length < 2 || path.Length > 65 || path[0] != '/' ||
            !path[1..].All(c => char.IsAsciiLetterOrDigit(c) || c is '_' or '-' or '.'))
        {
            return null;
        }

        return "https://buymeacoffee.com" + path;
    }

    /// <summary>Öffnet den Link im Standardbrowser. <c>false</c>, wenn das nicht ging.</summary>
    public static bool Open(string? url)
    {
        string target = Accept(url) ?? Fallback;
        try
        {
            using Process? browser = Process.Start(new ProcessStartInfo(target) { UseShellExecute = true });
            return true;
        }
        catch (System.ComponentModel.Win32Exception)
        {
            return false;
        }
    }
}
