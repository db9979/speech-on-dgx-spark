using System.Text.RegularExpressions;

namespace SparkBegleiter;

/// <summary>
/// Wege ins Panel in einem Text („Im Panel unter Ich → Begleiter einschalten“): ein Klick öffnet
/// <c>&lt;Spark&gt;/#weg=&lt;Weg&gt;</c>, das Panel springt selbst dorthin (way.js). Dieselbe Regel wie wege.py
/// auf dem Spark; „Einstellungen → …“ ohne „Panel“ davor sind die eigenen Einstellungen oder die von Windows.
/// Nur Navigation: der Weg wird kodiert angehängt, sonst passiert nichts.
/// </summary>
internal static class Wege
{
    public const string Roots = "Einstellungen|Funktionen|Zustand|Personen und Geräte|Ich|Settings|Features|Status|People and devices|Me|Kalender|Calendar|E-Mail|E-mail|Kontakte|Contacts|Wissensbuch|Knowledge book|Krisenspiel|Crisis game";

    private static readonly Regex Way = new(
        @"(?<![\w-])(?<!Mein )(?<!My )(?<!→ )(?:" + Roots + @")\s*→[^\n.;:()!?]{1,160}",
        RegexOptions.CultureInvariant, TimeSpan.FromMilliseconds(200));

    /// <summary>Öffnet einen Hash im Panel (TrayContext.OpenPanelAt), gesetzt beim Start.</summary>
    public static Action<string>? Open { get; set; }

    /// <summary>Der erste Weg im Text oder null.</summary>
    public static string? Find(string? text)
    {
        if (string.IsNullOrEmpty(text))
        {
            return null;
        }

        string s = text.Length > 6000 ? text[..6000] : text;
        try
        {
            foreach (Match m in Way.Matches(s))
            {
                string way = m.Value.Trim(' ', ',', '–', '-');
                string before = s[Math.Max(0, m.Index - 14)..m.Index];
                if ((way.StartsWith("Einstellungen", StringComparison.Ordinal) || way.StartsWith("Settings", StringComparison.Ordinal))
                    && !before.Contains("panel", StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                return way.Length > 200 ? way[..200] : way;
            }
        }
        catch (RegexMatchTimeoutException)
        {
        }

        return null;
    }

    /// <summary>„#weg=…“ für den ersten Weg im Text oder null.</summary>
    public static string? Hash(string? text) => Find(text) is { } way ? "#weg=" + Uri.EscapeDataString(way) : null;

    /// <summary>Öffnet den Weg aus dem Text im Panel; false, wenn der Text keinen hat.</summary>
    public static bool OpenFrom(string? text)
    {
        if (Hash(text) is not { } hash || Open is null)
        {
            return false;
        }

        Open(hash);
        return true;
    }
}
