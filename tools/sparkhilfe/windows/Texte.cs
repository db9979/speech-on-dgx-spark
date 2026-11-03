using System.Globalization;

namespace SparkHilfe;

/// <summary>Alle Texte des Programms, deutsch und englisch (nach der Sprache von Windows). Platzhalter: {0} der Name
/// des Helfers, {1} die Adresse des Sparks; nie etwas anderes von außen.</summary>
internal static class Texte
{
    private static readonly Dictionary<string, (string De, string En)> All = new()
    {
        ["fenster"] = ("SparkHilfe", "SparkHilfe"),
        ["verbinde"] = ("Verbinde mit {1} …", "Connecting to {1} …"),
        ["name_falsch"] = ("Diese Datei gehört zu keiner Hilfe. Bitte laden Sie das Programm auf der Hilfe-Seite neu.",
                           "This file belongs to no help. Please load the program again on the help page."),
        ["neu_laden"] = ("Diese Datei ist abgelaufen oder schon benutzt. Bitte laden Sie das Programm auf der Hilfe-Seite neu.",
                         "This file has expired or was used already. Please load the program again on the help page."),
        ["keine_verbindung"] = ("Keine Verbindung zu {1}. Bitte prüfen Sie das Internet und laden Sie das Programm auf der Hilfe-Seite neu.",
                                "No connection to {1}. Please check the internet and load the program again on the help page."),
        ["frage_fenster"] = ("SparkHilfe – Steuern erlauben?", "SparkHilfe – allow control?"),
        ["frage_titel"] = ("Ihren PC steuern lassen?", "Let someone control your PC?"),
        ["frage"] = ("{0} ({1}) möchte Ihren PC steuern.", "{0} ({1}) would like to control your PC."),
        ["frage_mehr"] = ("Nur, wenn Sie gerade selbst um Hilfe gebeten haben. Solange es läuft, sehen Sie einen roten Rahmen und oben „Beenden“. " +
                          "Fenster mit Schild (Administrator) klicken Sie selbst. Es wird nichts aufgezeichnet.",
                          "Only if you asked for help just now. While it runs you see a red frame and “End” at the top. " +
                          "Windows with a shield (administrator) you click yourself. Nothing is recorded."),
        ["ablehnen"] = ("Ablehnen", "Decline"),
        ["ansehen"] = ("Nur ansehen", "View only"),
        ["erlauben"] = ("Erlauben", "Allow"),
        ["countdown"] = ("Ohne Antwort gilt in {0} s „Ablehnen“.", "Without an answer, “Decline” applies in {0} s."),
        ["rahmen"] = ("SparkHilfe – Bildschirm wird gezeigt", "SparkHilfe – screen is shown"),
        ["leiste_ansehen"] = ("{0} sieht Ihren Bildschirm", "{0} sees your screen"),
        ["leiste_erlaubt"] = ("{0} sieht Ihren Bildschirm · Steuern erlaubt", "{0} sees your screen · control allowed"),
        ["leiste_aktiv"] = ("Steuerung aktiv · {0}", "Control active · {0}"),
        ["beenden"] = ("Beenden", "End"),
        ["schliessen"] = ("Schließen", "Close"),
        ["abgelehnt"] = ("Abgelehnt. Niemand steuert Ihren PC.", "Declined. Nobody controls your PC."),
        ["beendet"] = ("Die Hilfe ist beendet. Sie können dieses Fenster schließen.", "The help has ended. You can close this window."),
        ["laeuft_schon"] = ("SparkHilfe läuft bereits.", "SparkHilfe is already running."),
    };

    /// <summary>Deutsch, wenn Windows deutsch spricht; sonst englisch.</summary>
    public static bool German { get; set; } = CultureInfo.CurrentUICulture.TwoLetterISOLanguageName == "de";

    public static string T(string key, string helper = "", string host = "")
    {
        (string de, string en) = All[key];
        return string.Format(CultureInfo.InvariantCulture, German ? de : en, helper, host);
    }

    /// <summary>Der Text mit „{0}“ als Platzhalter für eine Zahl (Countdown).</summary>
    public static string Raw(string key) => German ? All[key].De : All[key].En;
}
