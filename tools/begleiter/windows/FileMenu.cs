using System.IO.Pipes;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Win32;

namespace SparkBegleiter;

/// <summary>Ein Auftrag aus dem Explorer-Menü "Mit Spark": was mit welcher Datei.</summary>
internal sealed record FileRequest(string What, string Path)
{
    public const string Argument = "--file";

    /// <summary>Erlaubte Aufträge (wie /api/desk/file "what").</summary>
    public static readonly string[] Whats = { "zusammenfassen", "uebersetzen", "erklaeren", "wissen" };

    public static string Label(string what) => what switch
    {
        "zusammenfassen" => "Zusammenfassen",
        "uebersetzen" => "Übersetzen",
        "erklaeren" => "Erklären",
        "wissen" => "Ins Wissen übernehmen",
        _ => what,
    };

    /// <summary>Liest <c>--file &lt;what&gt; "&lt;Pfad&gt;"</c>; alles andere ergibt <c>null</c>.</summary>
    public static FileRequest? FromArgs(string[] args)
    {
        if (args.Length != 3 || args[0] != Argument)
        {
            return null;
        }

        return Create(args[1], args[2]);
    }

    public static FileRequest? Create(string? what, string? path)
    {
        if (what is null || !Whats.Contains(what) || string.IsNullOrWhiteSpace(path) || path.Length > 2000)
        {
            return null;
        }

        try
        {
            string full = System.IO.Path.GetFullPath(path);
            return System.IO.Path.IsPathFullyQualified(full) ? new FileRequest(what, full) : null;
        }
        catch (Exception ex) when (ex is ArgumentException or NotSupportedException or PathTooLongException)
        {
            return null;
        }
    }
}

/// <summary>
/// Teil "files": Untermenü "Mit Spark" im Explorer (Rechtsklick auf eine Datei) – nur für das eigene Konto unter
/// HKCU\Software\Classes\SystemFileAssociations\&lt;Endung&gt;\shell, ohne Administratorrechte und ohne Shell-Erweiterung.
/// Jeder Eintrag startet die .exe mit <c>--file &lt;what&gt; "&lt;Pfad&gt;"</c>; die laufende Instanz bekommt den Auftrag
/// über <see cref="FileBridge"/>. Eingetragen nur, solange der Teil an ist.
/// </summary>
internal static class FileMenu
{
    private const string VerbName = "SparkBegleiter";

    /// <summary>Dateiarten, die /api/desk/file annimmt.</summary>
    public static readonly string[] Extensions =
    {
        ".pdf", ".docx", ".xlsx", ".pptx", ".odt", ".txt", ".md", ".eml", ".html", ".htm", ".jpg", ".jpeg", ".png", ".heic",
    };

    public static string ContentType(string extension) => extension.ToLowerInvariant() switch
    {
        ".pdf" => "application/pdf",
        ".docx" => "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx" => "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".pptx" => "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".odt" => "application/vnd.oasis.opendocument.text",
        ".txt" => "text/plain",
        ".md" => "text/markdown",
        ".eml" => "message/rfc822",
        ".html" or ".htm" => "text/html",
        ".jpg" or ".jpeg" => "image/jpeg",
        ".png" => "image/png",
        ".heic" => "image/heic",
        _ => "application/octet-stream",
    };

    public static bool IsSupported(string path) =>
        Extensions.Contains(Path.GetExtension(path).ToLowerInvariant());

    private static string KeyFor(string extension) =>
        $@"Software\Classes\SystemFileAssociations\{extension}\shell\{VerbName}";

    private static string Exe => Environment.ProcessPath ?? "";

    private static string CommandFor(string what) => $"\"{Exe}\" {FileRequest.Argument} {what} \"%1\"";

    /// <summary>Ist das Menü für genau diese .exe eingetragen?</summary>
    public static bool IsRegistered()
    {
        try
        {
            using RegistryKey? key = Registry.CurrentUser.OpenSubKey(KeyFor(Extensions[0]) + @"\shell\4wissen\command");
            return key?.GetValue(null) is string value && string.Equals(value, CommandFor("wissen"), StringComparison.OrdinalIgnoreCase);
        }
        catch (Exception ex) when (ex is System.Security.SecurityException or IOException or UnauthorizedAccessException)
        {
            return false;
        }
    }

    /// <summary>Einträgt (bzw. erneuert, wenn die .exe woanders liegt). Wirft bei Registry-Fehlern.</summary>
    public static void Register()
    {
        if (string.IsNullOrEmpty(Exe) || IsRegistered())
        {
            return;
        }

        string[] verbs = FileRequest.Whats;
        foreach (string ext in Extensions)
        {
            Registry.CurrentUser.DeleteSubKeyTree(KeyFor(ext), throwOnMissingSubKey: false);
            using RegistryKey root = Registry.CurrentUser.CreateSubKey(KeyFor(ext), writable: true);
            root.SetValue("MUIVerb", "Mit Spark", RegistryValueKind.String);
            root.SetValue("Icon", $"\"{Exe}\",0", RegistryValueKind.String);
            root.SetValue("SubCommands", "", RegistryValueKind.String);
            for (int i = 0; i < verbs.Length; i++)
            {
                // Ziffer davor: Windows sortiert die Unterpunkte nach dem Schlüsselnamen.
                using RegistryKey verb = root.CreateSubKey($@"shell\{i + 1}{verbs[i]}", writable: true);
                verb.SetValue("MUIVerb", FileRequest.Label(verbs[i]), RegistryValueKind.String);
                using RegistryKey command = verb.CreateSubKey("command", writable: true);
                command.SetValue(null, CommandFor(verbs[i]), RegistryValueKind.String);
            }
        }

        NotifyShell();
    }

    /// <summary>Entfernt alle Einträge (Teil aus, Entkoppeln, <c>--entfernen</c>). Fehler werden verschluckt.</summary>
    public static void Unregister()
    {
        bool any = false;
        foreach (string ext in Extensions)
        {
            try
            {
                using (RegistryKey? existing = Registry.CurrentUser.OpenSubKey(KeyFor(ext)))
                {
                    if (existing is null)
                    {
                        continue;
                    }
                }

                Registry.CurrentUser.DeleteSubKeyTree(KeyFor(ext), throwOnMissingSubKey: false);
                any = true;
            }
            catch (Exception ex) when (ex is System.Security.SecurityException or IOException or UnauthorizedAccessException or ArgumentException)
            {
                // Dann bleibt der Eintrag; beim nächsten Abgleich neuer Versuch.
            }
        }

        if (any)
        {
            NotifyShell();
        }
    }

    private static void NotifyShell()
    {
        try
        {
            NativeMethods.SHChangeNotify(NativeMethods.SHCNE_ASSOCCHANGED, NativeMethods.SHCNF_IDLIST, IntPtr.Zero, IntPtr.Zero);
        }
        catch (Exception ex) when (ex is DllNotFoundException or EntryPointNotFoundException)
        {
            // Explorer liest die Einträge dann beim nächsten Öffnen des Menüs.
        }
    }
}

/// <summary>
/// Einzelne Instanz: eine zweite Instanz (vom Explorer-Menü gestartet) reicht ihren Auftrag über eine benannte Pipe
/// an die laufende weiter. Die Pipe ist auf das eigene Windows-Konto beschränkt (CurrentUserOnly) und nimmt nur
/// eine kurze JSON-Zeile {"what","path"} an.
/// </summary>
internal sealed class FileBridge : IDisposable
{
    private const int MaxMessage = 8192;

    private readonly CancellationTokenSource _stop = new();
    private readonly Action<FileRequest> _received;
    private readonly SynchronizationContext _context;

    private FileBridge(Action<FileRequest> received, SynchronizationContext context)
    {
        _received = received;
        _context = context;
        _ = Task.Run(() => ServeAsync(_stop.Token));
    }

    private static string PipeName =>
        $"SparkBegleiter.{System.Diagnostics.Process.GetCurrentProcess().SessionId}.{Environment.UserName}";

    /// <summary>Startet den Empfang (Aufträge kommen im UI-Thread an).</summary>
    public static FileBridge Start(Action<FileRequest> received) =>
        new(received, SynchronizationContext.Current ?? new WindowsFormsSynchronizationContext());

    /// <summary>Gibt den Auftrag an die laufende Instanz weiter (wartet bis zu 10 s, falls sie gerade startet).</summary>
    public static bool SendToRunning(FileRequest request)
    {
        byte[] payload = Encoding.UTF8.GetBytes(new JsonObject { ["what"] = request.What, ["path"] = request.Path }.ToJsonString() + "\n");
        var watch = System.Diagnostics.Stopwatch.StartNew();
        while (watch.ElapsedMilliseconds < 10000)
        {
            try
            {
                using var client = new NamedPipeClientStream(".", PipeName, PipeDirection.Out, PipeOptions.CurrentUserOnly);
                client.Connect(1500);
                client.Write(payload, 0, payload.Length);
                client.Flush();
                return true;
            }
            catch (Exception ex) when (ex is TimeoutException or IOException or UnauthorizedAccessException)
            {
                Thread.Sleep(300);
            }
        }

        return false;
    }

    private async Task ServeAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            try
            {
                using var server = new NamedPipeServerStream(PipeName, PipeDirection.In, 1,
                    PipeTransmissionMode.Byte, PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
                await server.WaitForConnectionAsync(ct).ConfigureAwait(false);

                using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
                timeout.CancelAfter(3000);
                byte[] buffer = new byte[MaxMessage];
                int total = 0;
                while (total < MaxMessage)
                {
                    int read = await server.ReadAsync(buffer.AsMemory(total, MaxMessage - total), timeout.Token).ConfigureAwait(false);
                    if (read == 0 || Array.IndexOf(buffer, (byte)'\n', total, read) >= 0)
                    {
                        total += read;
                        break;
                    }

                    total += read;
                }

                if (Parse(buffer.AsSpan(0, total)) is { } request)
                {
                    _context.Post(_ => _received(request), null);
                }
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                return;
            }
            catch (Exception ex) when (ex is IOException or OperationCanceledException or UnauthorizedAccessException)
            {
                // Abgebrochene oder fremde Verbindung: weiter warten.
                await Task.Delay(200, CancellationToken.None).ConfigureAwait(false);
            }
        }
    }

    private static FileRequest? Parse(ReadOnlySpan<byte> data)
    {
        try
        {
            if (JsonNode.Parse(Encoding.UTF8.GetString(data).Trim()) is JsonObject o)
            {
                return FileRequest.Create(Json.Str(o["what"]), Json.Str(o["path"]));
            }
        }
        catch (JsonException)
        {
            // kein gültiger Auftrag
        }

        return null;
    }

    public void Dispose() => _stop.Cancel(); // die Schleife endet von selbst; das Token bleibt gültig
}
