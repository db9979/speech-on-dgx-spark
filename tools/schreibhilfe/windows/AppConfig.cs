using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace SparkSchreibhilfe;

/// <summary>
/// Einstellungen in %APPDATA%\SparkSchreibhilfe\config.json.
/// Der Geräteschlüssel liegt nur DPAPI-verschlüsselt (an das Windows-Konto gebunden) als Base64 darin.
/// </summary>
internal sealed class AppConfig
{
    private static readonly byte[] Entropy = Encoding.UTF8.GetBytes("SparkSchreibhilfe.v1");

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    };

    /// <summary>Adresse des Spark, z. B. https://speech.example.org (ohne Pfad).</summary>
    public string? Base { get; set; }

    /// <summary>Geräteschlüssel, DPAPI-geschützt (CurrentUser), Base64.</summary>
    public string? ProtectedKey { get; set; }

    /// <summary>Profilname, den der Spark beim Koppeln genannt hat (nur zur Anzeige).</summary>
    public string? Profile { get; set; }

    /// <summary>Gerätename, unter dem dieses Programm im Panel erscheint.</summary>
    public string? Device { get; set; }

    /// <summary>Zuletzt gewählte Art und Zielsprache.</summary>
    public string? Art { get; set; }

    public string? Sprache { get; set; }

    public static string Folder =>
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "SparkSchreibhilfe");

    private static string FilePath => Path.Combine(Folder, "config.json");

    public bool IsPaired => !string.IsNullOrEmpty(Base) && GetKey() is not null;

    public static AppConfig Load()
    {
        try
        {
            if (File.Exists(FilePath))
            {
                return JsonSerializer.Deserialize<AppConfig>(File.ReadAllText(FilePath), JsonOptions) ?? new AppConfig();
            }
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException)
        {
            // Unlesbare Datei: wie nicht eingerichtet behandeln.
        }

        return new AppConfig();
    }

    /// <summary>Schreibt erst eine temporäre Datei und ersetzt dann, damit nie eine halbe Datei entsteht.</summary>
    public void Save()
    {
        Directory.CreateDirectory(Folder);
        string temp = FilePath + ".tmp";
        File.WriteAllText(temp, JsonSerializer.Serialize(this, JsonOptions));
        File.Move(temp, FilePath, overwrite: true);
    }

    /// <summary>Entschlüsselter Schlüssel oder <c>null</c> (nicht gekoppelt / anderes Windows-Konto).</summary>
    public string? GetKey()
    {
        if (string.IsNullOrEmpty(ProtectedKey))
        {
            return null;
        }

        try
        {
            byte[] plain = ProtectedData.Unprotect(Convert.FromBase64String(ProtectedKey), Entropy, DataProtectionScope.CurrentUser);
            return Encoding.UTF8.GetString(plain);
        }
        catch (Exception ex) when (ex is CryptographicException or FormatException)
        {
            return null;
        }
    }

    public void SetKey(string key)
    {
        byte[] secret = ProtectedData.Protect(Encoding.UTF8.GetBytes(key), Entropy, DataProtectionScope.CurrentUser);
        ProtectedKey = Convert.ToBase64String(secret);
    }

    public void ForgetKey() => ProtectedKey = null;
}
