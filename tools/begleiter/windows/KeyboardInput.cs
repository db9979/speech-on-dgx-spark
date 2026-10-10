using System.Diagnostics;
using System.Runtime.InteropServices;
using static SparkBegleiter.NativeMethods;

namespace SparkBegleiter;

/// <summary>Simulierte Tastendrücke (Strg+C / Strg+V) für das Programm im Vordergrund.</summary>
internal static class KeyboardInput
{
    /// <summary>Modifikatortasten (links/rechts) und ob sie als "extended key" gesendet werden müssen.</summary>
    private static readonly (ushort Vk, bool Extended)[] Modifiers =
    {
        (VK_LCONTROL, false), (VK_RCONTROL, true),
        (VK_LMENU, false), (VK_RMENU, true),
        (VK_LSHIFT, false), (VK_RSHIFT, false),
        (VK_LWIN, true), (VK_RWIN, true),
    };

    private static bool IsDown(ushort vk) => (GetAsyncKeyState(vk) & 0x8000) != 0;

    /// <summary>
    /// Wartet, bis die Person die Tasten des Tastenkürzels (Modifikatoren und <paramref name="key"/>) losgelassen hat (höchstens
    /// <paramref name="timeoutMs"/>), und löst dann noch gedrückte Modifikatoren per Key-up.
    /// Sonst käme beim Ziel statt Strg+C z. B. Strg+Alt+C an.
    /// </summary>
    public static async Task WaitForHotkeyReleaseAsync(ushort key, int timeoutMs)
    {
        var watch = Stopwatch.StartNew();
        while (watch.ElapsedMilliseconds < timeoutMs && (IsDown(key) || Modifiers.Any(m => IsDown(m.Vk))))
        {
            await Task.Delay(15).ConfigureAwait(true);
        }

        var ups = Modifiers.Where(m => IsDown(m.Vk)).Select(m => Key(m.Vk, up: true, m.Extended)).ToArray();
        Send(ups);
    }

    /// <summary>Sendet Strg + <paramref name="vk"/> (z. B. VK_C oder VK_V) als einen Block.</summary>
    public static void SendCtrlChord(ushort vk)
    {
        Send(new[]
        {
            Key(VK_CONTROL, up: false),
            Key(vk, up: false),
            Key(vk, up: true),
            Key(VK_CONTROL, up: true),
        });
    }

    private static INPUT Key(ushort vk, bool up, bool extended = false)
    {
        uint flags = (up ? KEYEVENTF_KEYUP : 0) | (extended ? KEYEVENTF_EXTENDEDKEY : 0);
        return new INPUT
        {
            type = INPUT_KEYBOARD,
            // Scan-Code mitgeben: manche Programme (z. B. Remote-Desktop) werten nur ihn aus.
            u = new InputUnion
            {
                ki = new KEYBDINPUT { wVk = vk, wScan = (ushort)MapVirtualKey(vk, MAPVK_VK_TO_VSC), dwFlags = flags },
            },
        };
    }

    private static void Send(INPUT[] inputs)
    {
        if (inputs.Length == 0)
        {
            return;
        }

        // Rückgabewert 0 = blockiert (z. B. Zielprogramm läuft als Administrator). Dann kommt
        // einfach kein Text an; der Aufrufer zeigt in dem Fall das leere Eingabefeld.
        _ = SendInput((uint)inputs.Length, inputs, Marshal.SizeOf<INPUT>());
    }
}
