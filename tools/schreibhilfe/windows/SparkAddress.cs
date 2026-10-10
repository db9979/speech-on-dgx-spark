using System.Net;
using System.Net.Sockets;
using System.Text.RegularExpressions;

namespace SparkSchreibhilfe;

/// <summary>Einrichtungszeile "&lt;base&gt;#schreib=XXXX-XXXX" zerlegen und die Adresse prüfen.</summary>
internal static partial class SparkAddress
{
    private const string Marker = "#schreib=";

    /// <summary>Ergebnis der Prüfung: normierte Adresse und ob sie unverschlüsselt (http) ist.</summary>
    public readonly record struct Parsed(string Base, string? Code, bool Insecure);

    /// <summary>
    /// Zerlegt die Einrichtungszeile (oder nur eine Adresse). https ist immer erlaubt, http nur für
    /// Adressen im Heimnetz. Bei Fehlern steht in <paramref name="error"/> ein deutscher Hinweis.
    /// </summary>
    public static bool TryParse(string input, out Parsed result, out string error)
    {
        result = default;
        error = "";
        string line = input.Trim();
        string? code = null;

        int marker = line.IndexOf(Marker, StringComparison.OrdinalIgnoreCase);
        if (marker >= 0)
        {
            code = line[(marker + Marker.Length)..].Trim();
            line = line[..marker].Trim();
        }

        if (line.Length == 0)
        {
            error = "Bitte die Einrichtungszeile aus dem Panel einfügen.";
            return false;
        }

        if (!line.Contains("://", StringComparison.Ordinal))
        {
            line = "https://" + line;
        }

        if (!Uri.TryCreate(line, UriKind.Absolute, out Uri? uri) ||
            (uri.Scheme != Uri.UriSchemeHttps && uri.Scheme != Uri.UriSchemeHttp) ||
            !string.IsNullOrEmpty(uri.UserInfo) || uri.Host.Length == 0)
        {
            error = "Die Adresse ist ungültig. Beispiel: https://speech.example.org";
            return false;
        }

        bool insecure = uri.Scheme == Uri.UriSchemeHttp;
        if (insecure && !IsPrivateHost(uri.DnsSafeHost))
        {
            error = "Unverschlüsseltes http ist nur im Heimnetz erlaubt. Bitte die https-Adresse des Spark verwenden.";
            return false;
        }

        // Nur Schema, Host und Port – die Schnittstelle liegt immer unter /api/write.
        result = new Parsed(uri.GetLeftPart(UriPartial.Authority), string.IsNullOrEmpty(code) ? null : code, insecure);
        return true;
    }

    /// <summary>Code-Prüfung nur grob (8 Zeichen); die eigentliche Normierung macht der Spark.</summary>
    public static bool LooksLikeCode(string code) =>
        code.Replace("-", "", StringComparison.Ordinal).Replace(" ", "", StringComparison.Ordinal).Length == 8;

    /// <summary>Gerätename für den Spark: 1–40 Zeichen aus Buchstaben, Ziffern, Leerzeichen und .-_</summary>
    public static bool IsValidDeviceName(string name) => DeviceNameRegex().IsMatch(name);

    /// <summary>Macht aus einem beliebigen Namen (z. B. dem Computernamen) einen gültigen Gerätenamen.</summary>
    public static string SanitizeDeviceName(string name)
    {
        string clean = InvalidDeviceCharRegex().Replace(name, "-").Trim();
        if (clean.Length > 40)
        {
            clean = clean[..40].Trim();
        }

        return clean.Length == 0 ? "Windows" : clean;
    }

    /// <summary>Private/LAN-Adressen laut Vertrag: 10/8, 172.16/12, 192.168/16, localhost, *.local (+ IPv6 lokal).</summary>
    public static bool IsPrivateHost(string host)
    {
        if (host.Equals("localhost", StringComparison.OrdinalIgnoreCase) ||
            host.EndsWith(".local", StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        if (!IPAddress.TryParse(host, out IPAddress? ip))
        {
            return false;
        }

        if (IPAddress.IsLoopback(ip))
        {
            return true;
        }

        if (ip.IsIPv4MappedToIPv6)
        {
            ip = ip.MapToIPv4();
        }

        if (ip.AddressFamily == AddressFamily.InterNetwork)
        {
            byte[] b = ip.GetAddressBytes();
            return b[0] == 10 ||
                   (b[0] == 172 && b[1] >= 16 && b[1] <= 31) ||
                   (b[0] == 192 && b[1] == 168);
        }

        // IPv6: Unique Local (fc00::/7) und Link-Local (fe80::/10).
        byte[] v6 = ip.GetAddressBytes();
        return (v6[0] & 0xFE) == 0xFC || ip.IsIPv6LinkLocal;
    }

    [GeneratedRegex(@"^[\p{L}\p{N} ._-]{1,40}$")]
    private static partial Regex DeviceNameRegex();

    [GeneratedRegex(@"[^\p{L}\p{N} ._-]")]
    private static partial Regex InvalidDeviceCharRegex();
}
