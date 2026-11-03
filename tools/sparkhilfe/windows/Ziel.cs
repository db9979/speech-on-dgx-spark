using System.Text.RegularExpressions;

namespace SparkHilfe;

/// <summary>
/// Wohin das Programm darf: Adresse und Einmal-Schlüssel stehen nur im eigenen Dateinamen, so wie /hilfe ihn vergibt
/// (spontanhilfe-seite.js: <c>SparkHilfe-&lt;host&gt;-&lt;Schlüssel&gt;.exe</c>, ein Doppelpunkt vor dem Port wird zu „_“;
/// der Browser hängt bei einer zweiten Datei „ (1)“ an). Der Schlüssel hat 22 Zeichen (128 Bit,
/// <c>spontansteuern.KEY</c>). Fehlt etwas oder passt etwas nicht, verbindet sich das Programm nirgends hin.
/// </summary>
internal sealed record Ziel(string Host, int Port, string Key)
{
    private static readonly Regex Name = new(
        @"^SparkHilfe-(?<host>[A-Za-z0-9._\-]{1,260})-(?<key>[A-Za-z0-9_\-]{22})(?: ?\(\d{1,3}\))?\.exe$",
        RegexOptions.CultureInvariant, TimeSpan.FromMilliseconds(200));

    private static readonly Regex HostPort = new(
        @"^(?<name>[a-z0-9.\-]{1,253})(?:_(?<port>[0-9]{1,5}))?$", RegexOptions.CultureInvariant, TimeSpan.FromMilliseconds(200));

    private static readonly Regex Label = new(@"^[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?$", RegexOptions.CultureInvariant,
        TimeSpan.FromMilliseconds(200));

    /// <summary>„spark.example.org“ oder „spark.example.org:8443“, so wie es die Fragen zeigen.</summary>
    public string Shown => Port == 443 ? Host : Host + ":" + Port.ToString(System.Globalization.CultureInfo.InvariantCulture);

    /// <summary>Der einzige Weg, den das Programm öffnet: wss, normale Zertifikatsprüfung.</summary>
    public Uri Socket => new UriBuilder("wss", Host, Port, "/api/hilfe/steuern").Uri;

    /// <summary>Aus dem Dateinamen (ohne Ordner); null, wenn er keine Hilfe nennt.</summary>
    public static Ziel? FromFileName(string? fileName)
    {
        if (string.IsNullOrEmpty(fileName) || fileName.Length > 300)
        {
            return null;
        }

        try
        {
            Match m = Name.Match(fileName);
            if (!m.Success)
            {
                return null;
            }

            Match h = HostPort.Match(m.Groups["host"].Value.ToLowerInvariant());
            if (!h.Success)
            {
                return null;
            }

            string host = h.Groups["name"].Value;
            if (host.Split('.').Any(l => !Label.IsMatch(l)))
            {
                return null;
            }

            int port = 443;
            if (h.Groups["port"].Success && (!int.TryParse(h.Groups["port"].Value, out port) || port is < 1 or > 65535))
            {
                return null;
            }

            return new Ziel(host, port, m.Groups["key"].Value);
        }
        catch (RegexMatchTimeoutException)
        {
            return null;
        }
    }

    /// <summary>Nie der Schlüssel in einem Text (Fehlermeldung, Fenster).</summary>
    public override string ToString() => Shown;

    /// <summary>Aus dem Pfad des laufenden Programms.</summary>
    public static Ziel? FromProcess() => FromFileName(Path.GetFileName(Environment.ProcessPath));
}
