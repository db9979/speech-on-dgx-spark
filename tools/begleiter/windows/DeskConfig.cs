using System.Text.Json.Nodes;

namespace SparkBegleiter;

/// <summary>Eine Art der Schreibhilfe (z. B. "korrigieren") mit deutscher Bezeichnung.</summary>
internal sealed class ArtInfo
{
    public string Id { get; set; } = "";

    public string Label { get; set; } = "";

    /// <summary>Ob der Spark für diese Art die Änderungen markiert.</summary>
    public bool Changes { get; set; } = true;

    public override string ToString() => Label;
}

/// <summary>Eine Zielsprache (z. B. "en" = Englisch).</summary>
internal sealed class LangInfo
{
    public string Id { get; set; } = "";

    public string Label { get; set; } = "";

    public override string ToString() => Label;
}

/// <summary>Ein Programm, das der Spark starten darf (Teil "act"): Name aus dem Panel und was gestartet wird.</summary>
internal sealed class ActApp
{
    public string Name { get; set; } = "";

    public string Path { get; set; } = "";
}

/// <summary>
/// Die zentralen Einstellungen aus GET /api/desk/config. Welche Teile an sind, legt das Panel fest
/// (Ich → Begleiter). Die letzte Fassung wird (ohne Geheimnisse) in config.json zwischengespeichert,
/// damit der Begleiter auch startet, wenn der Spark gerade nicht erreichbar ist.
/// </summary>
internal sealed class DeskConfig
{
    public const string TranslateArt = "uebersetzen";

    /// <summary>Arten, die eine erhaltene Mail brauchen – im Begleiter nicht angeboten.</summary>
    private static readonly string[] MailArts = { "antwort" };

    public int Rev { get; set; }

    public string? Profile { get; set; }

    /// <summary>Wirksame Teile (an/aus).</summary>
    public Dictionary<string, bool> Parts { get; set; } = new();

    /// <summary>Was Admin und Profilschalter überhaupt erlauben.</summary>
    public Dictionary<string, bool> Allowed { get; set; } = new();

    public string WriteArt { get; set; } = "korrigieren";

    public string WriteSprache { get; set; } = "en";

    public string WriteWunsch { get; set; } = "";

    /// <summary>Angebotene Arten (Kennungen) in der Reihenfolge des Panels.</summary>
    public List<string> WriteArts { get; set; } = new();

    /// <summary>Vorschau-Fenster zeigen (sonst direkt einfügen).</summary>
    public bool WritePreview { get; set; } = true;

    public string DictateSprache { get; set; } = "auto";

    /// <summary>Mit Windows starten; <c>null</c> = der Spark sagt nichts dazu.</summary>
    public bool? Autostart { get; set; }

    public List<ArtInfo> Arts { get; set; } = new();

    public List<LangInfo> Langs { get; set; } = new();

    /// <summary>Sekunden zwischen zwei Abfragen.</summary>
    public int Poll { get; set; } = 30;

    /// <summary>Neue Version für dieses Gerät (nur gültige Angaben), sonst <c>null</c>.</summary>
    public UpdateInfo? Update { get; set; }

    /// <summary>Versionsnummer, wie der Spark sie in "update" genannt hat (zum Vergleich mit poll).</summary>
    public string? UpdateAnnounced { get; set; }

    /// <summary>Kaffee-Link aus dem Panel (nur https://buymeacoffee.com/…), sonst <c>null</c>.</summary>
    public string? Coffee { get; set; }

    /// <summary>Programme, die der Spark (nach Rückfrage) starten darf – config.act.apps.</summary>
    public List<ActApp> ActApps { get; set; } = new();

    /// <summary>Das Weckwort des Spark (config.wake.word), nur zur Anzeige.</summary>
    public string WakeWord { get; set; } = "Hey Spark";

    public bool IsOn(string part) => Parts.TryGetValue(part, out bool on) && on;

    public bool IsAllowed(string part) => Allowed.TryGetValue(part, out bool on) && on;

    /// <summary>Die im Fenster angebotenen Arten mit Bezeichnung (unbekannte Kennungen mit der Kennung selbst).</summary>
    public List<ArtInfo> OfferedArts()
    {
        IEnumerable<string> ids = WriteArts.Count > 0 ? WriteArts : Arts.Select(a => a.Id);
        var list = new List<ArtInfo>();
        foreach (string id in ids.Where(id => !MailArts.Contains(id)).Distinct())
        {
            list.Add(Arts.FirstOrDefault(a => a.Id == id) ?? new ArtInfo { Id = id, Label = id });
        }

        if (list.Count == 0)
        {
            list.Add(new ArtInfo { Id = "korrigieren", Label = "Korrigieren" });
        }

        return list;
    }

    public List<LangInfo> Languages()
    {
        var list = Langs.Where(l => l.Id != "auto").ToList();
        if (list.Count == 0)
        {
            list.Add(new LangInfo { Id = "en", Label = "Englisch" });
            list.Add(new LangInfo { Id = "de", Label = "Deutsch" });
        }

        return list;
    }

    /// <summary>Liest die Antwort des Spark; fehlende Felder bekommen die Standardwerte.</summary>
    public static DeskConfig Parse(JsonNode json)
    {
        var config = new DeskConfig
        {
            Rev = Json.Int(json["rev"]) ?? 0,
            Profile = Json.Str(json["profile"]),
            Parts = Bools(json["parts"]),
            Allowed = Bools(json["allowed"]),
            Autostart = Json.Bool(json["autostart"]),
            Poll = Math.Clamp(Json.Int(json["poll"]) ?? 30, 5, 600),
        };

        if (json["write"] is JsonObject write)
        {
            config.WriteArt = Json.Str(write["art"]) ?? config.WriteArt;
            config.WriteSprache = Json.Str(write["sprache"]) ?? config.WriteSprache;
            config.WriteWunsch = Json.Str(write["wunsch"]) ?? "";
            config.WritePreview = Json.Bool(write["preview"]) ?? true;
            if (write["arts"] is JsonArray arts)
            {
                config.WriteArts = arts.Select(Json.Str).OfType<string>().ToList();
            }
        }

        if (json["update"] is JsonObject update)
        {
            string? version = Json.Str(update["version"]);
            long? size = Json.Long(update["size"]);
            string? sha = Json.Str(update["sha256"]);
            config.UpdateAnnounced = version;
            if (Updater.TryParseVersion(version, out _) && size is > 0 and <= Updater.MaxSize &&
                sha is { Length: 64 } && sha.All(char.IsAsciiHexDigit))
            {
                config.Update = new UpdateInfo { Version = version!, Size = size.Value, Sha256 = sha };
            }
        }

        config.Coffee = CoffeeLink.Accept(Json.Str(json["coffee"]));

        if (json["dictate"] is JsonObject dictate)
        {
            config.DictateSprache = Json.Str(dictate["sprache"]) ?? "auto";
        }

        if (json["act"] is JsonObject act && act["apps"] is JsonArray apps)
        {
            foreach (JsonNode? item in apps)
            {
                if (item is JsonObject o && Json.Str(o["name"]) is { Length: > 0 and <= 80 } name &&
                    Json.Str(o["path"]) is { Length: > 0 and <= 400 } path)
                {
                    config.ActApps.Add(new ActApp { Name = name.Trim(), Path = path.Trim() });
                }
            }
        }

        if (json["wake"] is JsonObject wake && Json.Str(wake["word"]) is { } word && word.Trim().Length is > 0 and <= 40)
        {
            config.WakeWord = word.Trim();
        }

        if (json["arts"] is JsonArray artList)
        {
            foreach (JsonNode? item in artList)
            {
                if (item is JsonObject o && Json.Str(o["id"]) is { Length: > 0 } id)
                {
                    config.Arts.Add(new ArtInfo { Id = id, Label = Json.Str(o["de"]) ?? id, Changes = Json.Bool(o["changes"]) ?? true });
                }
            }
        }

        if (json["langs"] is JsonArray langList)
        {
            foreach (JsonNode? item in langList)
            {
                if (item is JsonObject o && Json.Str(o["id"]) is { Length: > 0 } id)
                {
                    config.Langs.Add(new LangInfo { Id = id, Label = Json.Str(o["de"]) ?? id });
                }
            }
        }

        // Wirksam kann nur sein, was erlaubt ist.
        foreach (string part in SparkBegleiter.Parts.All)
        {
            if (config.IsOn(part) && config.Allowed.Count > 0 && !config.IsAllowed(part))
            {
                config.Parts[part] = false;
            }
        }

        return config;
    }

    private static Dictionary<string, bool> Bools(JsonNode? node)
    {
        var map = new Dictionary<string, bool>();
        if (node is JsonObject obj)
        {
            foreach (string part in SparkBegleiter.Parts.All)
            {
                map[part] = Json.Bool(obj[part]) ?? false;
            }
        }

        return map;
    }
}

/// <summary>Kleine Helfer zum Lesen von JSON-Werten ohne Ausnahmen.</summary>
internal static class Json
{
    public static string? Str(JsonNode? node) =>
        node is JsonValue value && value.TryGetValue(out string? s) ? s : null;

    public static int? Int(JsonNode? node)
    {
        if (node is not JsonValue value)
        {
            return null;
        }

        if (value.TryGetValue(out int i))
        {
            return i;
        }

        return value.TryGetValue(out double d) && d is >= int.MinValue and <= int.MaxValue ? (int)d : null;
    }

    public static long? Long(JsonNode? node)
    {
        if (node is not JsonValue value)
        {
            return null;
        }

        if (value.TryGetValue(out long l))
        {
            return l;
        }

        return value.TryGetValue(out double d) && d is >= 0 and <= long.MaxValue && Math.Floor(d) == d ? (long)d : null;
    }

    public static bool? Bool(JsonNode? node) =>
        node is JsonValue value && value.TryGetValue(out bool b) ? b : null;
}
