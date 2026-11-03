using System.Globalization;

namespace SparkBegleiter;

/// <summary>Die Teile des Begleiters (Kennungen wie im Vertrag mit dem Spark).</summary>
internal static class Parts
{
    public const string Write = "write";
    public const string Ask = "ask";
    public const string Dictate = "dictate";
    public const string Notes = "notes";
    public const string Status = "status";
    public const string Notaus = "notaus";

    // Version 3 (tiefere Einbindung) – alle aus, bis das Panel sie einschaltet.
    public const string Files = "files";
    public const string Screen = "screen";
    public const string Context = "context";
    public const string Mail = "mail";
    public const string Folder = "folder";
    public const string Actions = "actions";
    public const string Act = "act";
    public const string Wake = "wake";

    // Version 4 – ebenfalls aus, bis das Panel sie einschaltet.
    public const string Speak = "speak";
    public const string Inbox = "inbox";
    public const string Agenda = "agenda";
    public const string Quiet = "quiet";
    public const string Meeting = "meeting";
    public const string Home = "home";
    public const string Daily = "daily";

    // Knopf "Spark" in Outlook classic, Word, Excel und neues Outlook einrichten (2026-10-12) – aus, bis das Panel ihn einschaltet.
    public const string Office = "office";

    // Rechner fernsteuern, Stufe 2: Bildschirm zeigen und bedienen – aus, bis das Panel ihn einschaltet.
    public const string View = "view";

    // Begleiter nachziehen 1a/2a: Post im Fenster und wichtige neue Mails als Meldung – aus, bis das Panel ihn einschaltet.
    public const string Post = "post";

    // Begleiter nachziehen 4a: Schnell erfassen (Strg+Alt+N) – aus, bis das Panel ihn einschaltet.
    public const string Capture = "capture";

    // Begleiter nachziehen 8a: die Listen (Seite Listen) im Fenster – aus, bis das Panel ihn einschaltet.
    public const string Lists = "lists";

    // Begleiter Paket B: Offen im Fenster (Heute) und Finden (Strg+Alt+F) – aus, bis das Panel sie einschaltet.
    public const string Offen = "offen";
    public const string Find = "find";

    /// <summary>Alle Teile in der Reihenfolge, in der sie angezeigt werden.</summary>
    public static readonly string[] All =
    {
        Write, Ask, Dictate, Notes, Status, Notaus, Files, Screen, Context, Mail, Folder, Actions, Act, Wake,
        Speak, Inbox, Agenda, Quiet, Meeting, Home, Daily, Office, View, Post, Capture, Lists, Offen, Find,
    };

    /// <summary>Teile mit eigenem Tastenkürzel.</summary>
    public static readonly string[] WithHotkey = { Write, Ask, Dictate, Screen, Mail, Speak, Meeting, Capture, Find };

    public static string Label(string part) => part switch
    {
        Write => "Schreibhilfe",
        Ask => "Frag Spark",
        Dictate => "Diktieren",
        Notes => "Meldungen",
        Status => "Zustandspunkt",
        Notaus => "Mein-Notaus-Knopf",
        Files => "Rechtsklick auf Dateien",
        Screen => "Bildschirm fragen",
        Context => "App erkennen",
        Mail => "Antwort entwerfen (Outlook)",
        Folder => "Ordner Spark-Wissen",
        Actions => "Knöpfe in Meldungen",
        Act => "Spark darf am PC handeln",
        Wake => "Weckwort",
        Speak => "Vorlesen",
        Inbox => "Vom Handy auf den PC",
        Agenda => "Termine im Begleiter",
        Quiet => "Nicht stören erkennen",
        Meeting => "Besprechung mitschreiben",
        Home => "Smart-Home-Knöpfe",
        Daily => "Tagesstart und Feierabend",
        Office => "Office-Add-ins",
        View => "Bildschirm zeigen und bedienen",
        Post => "Post im Begleiter",
        Capture => "Schnell erfassen",
        Lists => "Listen im Begleiter",
        Offen => "Offen im Begleiter",
        Find => "Finden im Begleiter",
        _ => part,
    };
}

/// <summary>Einstellung „Antworten vorlesen“ im Fenster Frag Spark.</summary>
internal static class AskSpeakModes
{
    public const string Always = "always";
    public const string Spoken = "spoken";
    public const string Never = "never";

    public static readonly string[] All = { Always, Spoken, Never };

    public static string Normalize(string? mode) => mode is Always or Never ? mode : Spoken;

    public static string Label(string mode) => Normalize(mode) switch
    {
        Always => "immer",
        Never => "nie",
        _ => "nur bei gesprochenen Fragen",
    };
}

/// <summary>
/// Ein globales Tastenkürzel: Modifikatoren (Strg/Alt/Umschalt) plus eine Taste.
/// Gespeichert wird es als Text wie <c>"S, Control, Alt"</c> (Schreibweise von <see cref="Keys"/>).
/// </summary>
internal readonly record struct Hotkey(Keys Modifiers, Keys Key)
{
    public static Hotkey DefaultFor(string part) => part switch
    {
        Parts.Ask => new Hotkey(Keys.Control | Keys.Alt, Keys.A),
        Parts.Dictate => new Hotkey(Keys.Control | Keys.Alt, Keys.D),
        Parts.Screen => new Hotkey(Keys.Control | Keys.Alt, Keys.B),
        Parts.Mail => new Hotkey(Keys.Control | Keys.Alt, Keys.M),
        Parts.Speak => new Hotkey(Keys.Control | Keys.Alt, Keys.L),
        Parts.Meeting => new Hotkey(Keys.Control | Keys.Alt, Keys.R),
        Parts.Capture => new Hotkey(Keys.Control | Keys.Alt, Keys.N),
        Parts.Find => new Hotkey(Keys.Control | Keys.Alt, Keys.F),
        _ => new Hotkey(Keys.Control | Keys.Alt, Keys.S),
    };

    /// <summary>Aus einem KeyDown-Ereignis (KeyData = Taste | Modifikatoren).</summary>
    public static Hotkey FromKeyData(Keys keyData) =>
        new(keyData & (Keys.Control | Keys.Alt | Keys.Shift), keyData & Keys.KeyCode);

    public static bool TryParse(string? text, out Hotkey hotkey)
    {
        hotkey = default;
        if (string.IsNullOrWhiteSpace(text) || !Enum.TryParse(text, ignoreCase: true, out Keys keys))
        {
            return false;
        }

        hotkey = FromKeyData(keys);
        return hotkey.IsValid;
    }

    /// <summary>Text zum Speichern.</summary>
    public string Serialize() => (Key | Modifiers).ToString();

    /// <summary>Gültig nur mit Strg oder Alt (Umschalt allein würde beim Tippen stören) und einer echten Taste.</summary>
    public bool IsValid =>
        (Modifiers & (Keys.Control | Keys.Alt)) != 0 && !IsModifierKey(Key) && Key != Keys.None;

    /// <summary>Taste für Win32 (virtueller Tastencode).</summary>
    public ushort VirtualKey => (ushort)Key;

    /// <summary>Modifikatoren für RegisterHotKey.</summary>
    public uint Win32Modifiers =>
        ((Modifiers & Keys.Control) != 0 ? NativeMethods.MOD_CONTROL : 0) |
        ((Modifiers & Keys.Alt) != 0 ? NativeMethods.MOD_ALT : 0) |
        ((Modifiers & Keys.Shift) != 0 ? NativeMethods.MOD_SHIFT : 0);

    public static bool IsModifierKey(Keys key) => key is Keys.ControlKey or Keys.LControlKey or Keys.RControlKey
        or Keys.ShiftKey or Keys.LShiftKey or Keys.RShiftKey or Keys.Menu or Keys.LMenu or Keys.RMenu
        or Keys.LWin or Keys.RWin or Keys.Apps;

    /// <summary>Deutsche Anzeige, z. B. "Strg+Alt+S".</summary>
    public override string ToString()
    {
        var parts = new List<string>(4);
        if ((Modifiers & Keys.Control) != 0)
        {
            parts.Add("Strg");
        }

        if ((Modifiers & Keys.Alt) != 0)
        {
            parts.Add("Alt");
        }

        if ((Modifiers & Keys.Shift) != 0)
        {
            parts.Add("Umschalt");
        }

        parts.Add(KeyName(Key));
        return string.Join("+", parts);
    }

    private static string KeyName(Keys key)
    {
        if (key is >= Keys.A and <= Keys.Z)
        {
            return ((char)key).ToString();
        }

        if (key is >= Keys.D0 and <= Keys.D9)
        {
            return ((int)(key - Keys.D0)).ToString(CultureInfo.InvariantCulture);
        }

        if (key is >= Keys.NumPad0 and <= Keys.NumPad9)
        {
            return "Num " + ((int)(key - Keys.NumPad0)).ToString(CultureInfo.InvariantCulture);
        }

        return key switch
        {
            Keys.None => "?",
            Keys.Space => "Leertaste",
            Keys.Return => "Eingabe",
            Keys.Back => "Rücktaste",
            Keys.Tab => "Tab",
            Keys.Insert => "Einfg",
            Keys.Delete => "Entf",
            Keys.Home => "Pos1",
            Keys.End => "Ende",
            Keys.PageUp => "Bild↑",
            Keys.PageDown => "Bild↓",
            Keys.Up => "↑",
            Keys.Down => "↓",
            Keys.Left => "←",
            Keys.Right => "→",
            Keys.Escape => "Esc",
            Keys.Pause => "Pause",
            Keys.OemPeriod => ".",
            Keys.Oemcomma => ",",
            Keys.OemMinus => "-",
            Keys.Oemplus => "+",
            _ => key.ToString(),
        };
    }
}
