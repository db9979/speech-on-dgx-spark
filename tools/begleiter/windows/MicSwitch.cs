namespace SparkBegleiter;

/// <summary>
/// „Mikrofon zu“ (Dominik 2026-10-14): ein Schalter für jedes Mikrofon des Begleiters. Zu heißt wirklich zu:
/// kein Gerät wird geöffnet (Weckwort, Diktieren, Mikrofon-Knöpfe, Frag Spark, Besprechung), laufende
/// Aufnahmen werden verworfen bzw. beendet. Der Zustand steht in der Einstellungsdatei (bleibt nach Neustart).
/// </summary>
internal static class MicSwitch
{
    public const string ClosedText = "Das Mikrofon ist zu. Im Begleiter-Menü „Mikrofon öffnen“ wählen.";

    private static volatile bool _closed;

    public static bool Closed => _closed;

    public static void Set(bool closed) => _closed = closed;
}
