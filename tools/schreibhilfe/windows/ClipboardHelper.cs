using System.Diagnostics;
using System.Runtime.InteropServices;

namespace SparkSchreibhilfe;

/// <summary>
/// Zwischenablage: Inhalt sichern und wiederherstellen, markierten Text holen, Ergebnis einfügen.
/// Die Zwischenablage kann kurz von anderen Programmen gesperrt sein, daher überall try/catch
/// und die eingebauten Wiederholungen von <see cref="Clipboard.SetDataObject(object, bool, int, int)"/>.
/// </summary>
internal static class ClipboardHelper
{
    /// <summary>Wie lange nach Strg+C höchstens auf Text gewartet wird.</summary>
    private const int CopyTimeoutMs = 600;

    /// <summary>Formate, die gesichert werden – die üblichen; exotische Formate gehen dabei verloren.</summary>
    private static readonly string[] SavedFormats =
    {
        DataFormats.UnicodeText, DataFormats.Rtf, DataFormats.Html, DataFormats.Bitmap, DataFormats.FileDrop,
    };

    /// <summary>Gesicherter Inhalt der Zwischenablage.</summary>
    public sealed class Snapshot
    {
        private readonly List<(string Format, object Data)> _items = new();

        public static Snapshot Take()
        {
            var snapshot = new Snapshot();
            try
            {
                IDataObject? data = Clipboard.GetDataObject();
                if (data is null)
                {
                    return snapshot;
                }

                foreach (string format in SavedFormats)
                {
                    try
                    {
                        if (data.GetDataPresent(format, autoConvert: false) &&
                            data.GetData(format, autoConvert: false) is { } value)
                        {
                            snapshot._items.Add((format, value));
                        }
                    }
                    catch (Exception ex) when (ex is ExternalException or OutOfMemoryException or InvalidOperationException)
                    {
                        // Format ließ sich nicht lesen – überspringen.
                    }
                }
            }
            catch (ExternalException)
            {
                // Zwischenablage gesperrt – dann gibt es eben nichts wiederherzustellen.
            }

            return snapshot;
        }

        public void Restore()
        {
            try
            {
                if (_items.Count == 0)
                {
                    Clipboard.Clear();
                    return;
                }

                var data = new DataObject();
                foreach (var (format, value) in _items)
                {
                    data.SetData(format, value);
                }

                Clipboard.SetDataObject(data, copy: true, retryTimes: 10, retryDelay: 50);
            }
            catch (ExternalException)
            {
                // Nicht schlimm: dann bleibt der zuletzt gesetzte Inhalt stehen.
            }
        }
    }

    /// <summary>
    /// Holt den markierten Text aus dem Programm im Vordergrund: Zwischenablage sichern, leeren,
    /// Strg+C senden, bis zu ~600 ms auf Text warten, Zwischenablage wiederherstellen.
    /// Gibt <c>null</c> zurück, wenn nichts markiert war (oder das Programm nichts kopiert hat).
    /// </summary>
    public static async Task<string?> CopySelectionAsync()
    {
        Snapshot original = Snapshot.Take();

        // Die Person hält Strg+Alt(+S) vermutlich noch gedrückt.
        await KeyboardInput.WaitForHotkeyReleaseAsync(timeoutMs: 800);

        TryClear();
        uint sequence = NativeMethods.GetClipboardSequenceNumber();
        KeyboardInput.SendCtrlChord(NativeMethods.VK_C);

        string? text = null;
        var watch = Stopwatch.StartNew();
        while (watch.ElapsedMilliseconds < CopyTimeoutMs)
        {
            await Task.Delay(30);
            if (NativeMethods.GetClipboardSequenceNumber() == sequence)
            {
                continue;
            }

            text = TryGetText();
            if (!string.IsNullOrEmpty(text))
            {
                break;
            }
        }

        original.Restore();
        return string.IsNullOrEmpty(text) ? null : text;
    }

    /// <summary>
    /// Fügt <paramref name="text"/> per Strg+V in <paramref name="target"/> ein und stellt danach
    /// die vorherige Zwischenablage wieder her. Gelingt das Aktivieren des Zielfensters nicht,
    /// bleibt der Text in der Zwischenablage und es wird <c>false</c> zurückgegeben.
    /// </summary>
    public static async Task<bool> PasteIntoAsync(IntPtr target, string text)
    {
        if (target == IntPtr.Zero || !NativeMethods.IsWindow(target))
        {
            TrySetText(text, keepOutOfHistory: false);
            return false;
        }

        Snapshot original = Snapshot.Take();
        if (!TrySetText(text, keepOutOfHistory: true))
        {
            return false;
        }

        if (NativeMethods.IsIconic(target))
        {
            NativeMethods.ShowWindow(target, NativeMethods.SW_RESTORE);
        }

        NativeMethods.SetForegroundWindow(target);
        await Task.Delay(120);

        // Nur einfügen, wenn wirklich das gemerkte Fenster vorne ist – sonst landet der Text woanders.
        if (NativeMethods.GetForegroundWindow() != target)
        {
            TrySetText(text, keepOutOfHistory: false);
            return false;
        }

        KeyboardInput.SendCtrlChord(NativeMethods.VK_V);

        // Das Zielprogramm liest die Zwischenablage oft erst etwas später.
        await Task.Delay(500);
        original.Restore();
        return true;
    }

    /// <summary>Legt Text in die Zwischenablage (für "Kopieren" ohne spätere Wiederherstellung).</summary>
    public static bool TrySetText(string text, bool keepOutOfHistory)
    {
        try
        {
            var data = new DataObject();
            data.SetData(DataFormats.UnicodeText, text);
            if (keepOutOfHistory)
            {
                // Nur kurz in der Zwischenablage: nicht in den Verlauf (Win+V) und nicht in die Cloud.
                data.SetData("CanIncludeInClipboardHistory", new MemoryStream(BitConverter.GetBytes(0)));
                data.SetData("CanUploadToCloudClipboard", new MemoryStream(BitConverter.GetBytes(0)));
            }

            Clipboard.SetDataObject(data, copy: true, retryTimes: 10, retryDelay: 50);
            return true;
        }
        catch (ExternalException)
        {
            return false;
        }
    }

    private static string? TryGetText()
    {
        try
        {
            return Clipboard.ContainsText() ? Clipboard.GetText() : null;
        }
        catch (ExternalException)
        {
            return null;
        }
    }

    private static void TryClear()
    {
        try
        {
            Clipboard.Clear();
        }
        catch (ExternalException)
        {
            // Gesperrt – die Sequenznummer zeigt trotzdem, ob danach etwas Neues kam.
        }
    }
}
