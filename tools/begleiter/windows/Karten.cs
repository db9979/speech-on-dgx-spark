using System.Text.Json.Nodes;

namespace SparkBegleiter;

/// <summary>
/// Knöpfe in Meldungen je Art (Begleiter nachziehen 3a): welche Knöpfe eine Meldung hat, legt das Panel fest
/// (begleiter.NOTE_ACTS); hier nur, welche dieses Programm kennt und wie sie heißen. Unbekannte fallen weg.
/// </summary>
internal static class NoteActs
{
    public static readonly string[] Known = { "reply", "later", "open", "done", "fdremind", "draft", "read", "copy" };

    /// <summary>Bestätigungscodes (mailcode.py): der Code einer Meldung ist ihr erstes Wort (4 bis 8 Großbuchstaben oder Ziffern), sonst null.</summary>
    public static string? CodeOf(string body)
    {
        var first = body.Split(' ', 2)[0];
        return System.Text.RegularExpressions.Regex.IsMatch(first, "^[A-Z0-9]{4,8}$") ? first : null;
    }

    /// <summary>Beschriftung eines Knopfs, der nur über das Panel wirkt (POST /api/desk/note/act).</summary>
    public static string? Label(string act) => act switch
    {
        "done" => "Erledigt",
        "fdremind" => "Erinnern",
        "read" => "Gelesen",
        _ => null,
    };

    /// <summary>„Antwort entwerfen“ zu einer neuen Mail: diese Bitte steht dann im Fragefeld von Frag Spark.</summary>
    public const string DraftQuestion = "Entwirf eine kurze Antwort auf diese Mail. Nicht senden.";

    /// <summary>Der Weg zu „Ansehen“: nur ein Weg, wie ihn auch <see cref="Wege"/> im Text findet, sonst null.</summary>
    public static string? CleanWeg(string? weg) => string.IsNullOrWhiteSpace(weg) ? null : Wege.Find(weg);
}

/// <summary>
/// Karten unter einer Antwort in Frag Spark (Begleiter nachziehen 5a): Rückfrage („Ja“/„Nein“, „A oder B?“),
/// Freigabe („Termin wartet auf dein Ja“) und Sprünge („Im Kalender ansehen“). Ein Knopf schickt nur sein festes
/// Wort wie getippt; geöffnet werden nur die Seiten aus <see cref="Pages"/>.
/// </summary>
internal static class AskCards
{
    public const int MaxCards = 3;
    public const int MaxButtons = 5;
    public const int MaxLabel = 30;

    /// <summary>Die Panel-Seiten, die ein Sprung-Knopf öffnen darf (chat.DESK_GOTO).</summary>
    public static readonly string[] Pages = { "#me=calbox", "#me=mailbox" };

    public static IReadOnlyList<AskCard> Parse(JsonNode? node)
    {
        var cards = new List<AskCard>();
        if (node is not JsonArray list)
        {
            return cards;
        }

        foreach (JsonNode? item in list.Take(MaxCards))
        {
            if (item is not JsonObject o || o["buttons"] is not JsonArray raw)
            {
                continue;
            }

            var buttons = new List<AskButton>();
            foreach (JsonNode? b in raw.Take(MaxButtons))
            {
                string label = Short(b?["label"]);
                string send = Short(b?["send"]);
                string? open = b?["open"] is JsonValue v && v.TryGetValue(out string? page) && Pages.Contains(page) ? page : null;
                bool focus = b?["focus"] is JsonValue f && f.TryGetValue(out bool yes) && yes;
                bool main = b?["main"] is JsonValue m && m.TryGetValue(out bool isMain) && isMain;
                if (label.Length == 0 || (send.Length == 0 && open is null && !focus))
                {
                    continue;
                }

                buttons.Add(new AskButton(label, send.Length > 0 ? send : null, send.Length > 0 ? null : open, send.Length == 0 && open is null && focus, main));
            }

            if (buttons.Count > 0)
            {
                cards.Add(new AskCard(Short(o["title"], 60), buttons));
            }
        }

        return cards;
    }

    private static string Short(JsonNode? node, int max = MaxLabel)
    {
        string text = node is JsonValue v && v.TryGetValue(out string? s) ? s : "";
        text = string.Concat(text.Where(c => !char.IsControl(c))).Trim();
        return text.Length > max ? text[..max] : text;
    }
}
