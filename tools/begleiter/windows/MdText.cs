using System.Text.RegularExpressions;

namespace SparkBegleiter;

/// <summary>Art einer Zeile einer Spark-Antwort (wie das Panel sie formatiert zeigt, md.js).</summary>
internal enum MdKind
{
    Text,
    Blank,
    Heading,
    Bullet,
    Number,
    Code,
    Rule,
}

/// <summary>Eine Zeile: Art, Text ohne Markdown-Zeichen, Listenzeichen („•“ oder „3.“) und Einrückung.</summary>
internal readonly record struct MdLine(MdKind Kind, string Text, string Mark, int Level);

/// <summary>
/// Antworten des Sparks als gegliederter Text: Überschriften und „**Termine**“-Zeilen fett, Listen mit Zeichen
/// und Einzug, Codeblöcke in Monospace. Fett, kursiv und `Code` im Satz werden zu ihren Wörtern, Links zu
/// „Text (Adresse)“. Alles bleibt Text: nichts wird geöffnet oder ausgeführt.
/// </summary>
internal static class MdText
{
    private const int MaxChars = 60000;
    private static readonly TimeSpan Budget = TimeSpan.FromMilliseconds(200);
    private static readonly Regex Head = new(@"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$", RegexOptions.None, Budget);
    private static readonly Regex BoldLine = new(@"^\s*\*\*([^*\n]{1,120})\*\*\s*$", RegexOptions.None, Budget);
    private static readonly Regex Bullet = new(@"^(\s*)[-*+•]\s+(.*)$", RegexOptions.None, Budget);
    private static readonly Regex Number = new(@"^(\s*)(\d{1,3}[.)])\s+(.*)$", RegexOptions.None, Budget);
    private static readonly Regex Fence = new(@"^\s{0,3}(```|~~~)", RegexOptions.None, Budget);
    private static readonly Regex Separator = new(@"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$", RegexOptions.None, Budget);
    private static readonly Regex RuleLine = new(@"^\s{0,3}([-*_])(\s*\1){2,}\s*$", RegexOptions.None, Budget);
    private static readonly Regex Inline = new(
        @"`([^`\n]{1,2000})`|\*\*(?=\S)([^\n]{1,2000}?\S)\*\*|(?<![\w*])\*(?=[^\s*])([^*\n]{0,2000}?[^\s*])\*(?![\w*])|" +
        @"~~(?=\S)([^\n]{1,2000}?\S)~~|!?\[([^\]\n]{1,300})\]\(\s*<?([^\s)>]{1,2000})>?\s*\)",
        RegexOptions.None, Budget);

    /// <summary>Fett, kursiv, `Code` und Links eines Satzes als schlichter Text.</summary>
    public static string Words(string s)
    {
        try
        {
            return Inline.Replace(s, m =>
                m.Groups[1].Success ? m.Groups[1].Value :
                m.Groups[2].Success ? m.Groups[2].Value :
                m.Groups[3].Success ? m.Groups[3].Value :
                m.Groups[4].Success ? m.Groups[4].Value :
                m.Groups[5].Value == m.Groups[6].Value ? m.Groups[6].Value : m.Groups[5].Value + " (" + m.Groups[6].Value + ")");
        }
        catch (RegexMatchTimeoutException)
        {
            return s;
        }
    }

    private static int Indent(string lead) => Math.Min(3, lead.Replace("\t", "    ", StringComparison.Ordinal).Length / 2);

    /// <summary>Die Zeilen einer Antwort; sehr lange Antworten bleiben eine einzige Textzeile.</summary>
    public static List<MdLine> Lines(string text)
    {
        var list = new List<MdLine>();
        if (text.Length > MaxChars)
        {
            list.Add(new MdLine(MdKind.Text, text, "", 0));
            return list;
        }

        bool code = false;
        try
        {
            foreach (string raw in text.Replace("\r\n", "\n", StringComparison.Ordinal).Split('\n'))
            {
                if (Fence.IsMatch(raw))
                {
                    code = !code;
                    continue;
                }

                if (code)
                {
                    list.Add(new MdLine(MdKind.Code, raw.TrimEnd(), "", 0));
                    continue;
                }

                string line = raw.TrimEnd();
                string trimmed = line.Trim();
                Match m;
                if (trimmed.Length == 0)
                {
                    if (list.Count > 0 && list[^1].Kind != MdKind.Blank)
                    {
                        list.Add(new MdLine(MdKind.Blank, "", "", 0));
                    }
                }
                else if (RuleLine.IsMatch(line))
                {
                    list.Add(new MdLine(MdKind.Rule, "", "", 0));
                }
                else if (Separator.IsMatch(line) && line.Contains('-', StringComparison.Ordinal))
                {
                    continue; // Trennzeile einer Tabelle
                }
                else if ((m = Head.Match(line)).Success)
                {
                    list.Add(new MdLine(MdKind.Heading, Words(m.Groups[1].Value), "", 0));
                }
                else if ((m = BoldLine.Match(line)).Success)
                {
                    list.Add(new MdLine(MdKind.Heading, Words(m.Groups[1].Value), "", 0));
                }
                else if ((m = Bullet.Match(line)).Success)
                {
                    list.Add(new MdLine(MdKind.Bullet, Words(m.Groups[2].Value), "•", Indent(m.Groups[1].Value)));
                }
                else if ((m = Number.Match(line)).Success)
                {
                    list.Add(new MdLine(MdKind.Number, Words(m.Groups[3].Value), m.Groups[2].Value, Indent(m.Groups[1].Value)));
                }
                else if (trimmed.StartsWith('>'))
                {
                    list.Add(new MdLine(MdKind.Text, Words(trimmed.TrimStart('>').Trim()), "", 1));
                }
                else if (trimmed.StartsWith('|'))
                {
                    list.Add(new MdLine(MdKind.Text, string.Join(" · ", trimmed.Trim('|').Split('|').Select(c => Words(c.Trim()))), "", 0));
                }
                else
                {
                    list.Add(new MdLine(MdKind.Text, Words(trimmed), "", 0));
                }
            }
        }
        catch (RegexMatchTimeoutException)
        {
            list.Clear();
            list.Add(new MdLine(MdKind.Text, text, "", 0));
        }

        while (list.Count > 0 && list[^1].Kind == MdKind.Blank)
        {
            list.RemoveAt(list.Count - 1);
        }

        return list;
    }

    /// <summary>Die Antwort ohne Markdown-Zeichen (Kopieren, Vorlesen, Bedienungshilfen).</summary>
    public static string Plain(string text) => string.Join("\n", Lines(text).Where(l => l.Kind != MdKind.Rule).Select(l =>
        l.Kind == MdKind.Bullet || l.Kind == MdKind.Number
            ? new string(' ', l.Level * 2) + l.Mark + " " + l.Text
            : l.Text));
}
