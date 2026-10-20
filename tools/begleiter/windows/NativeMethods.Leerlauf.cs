using System.Runtime.InteropServices;

namespace SparkBegleiter;

/// <summary>Meldung ans genutzte Gerät: wie lange die letzte Eingabe an diesem Rechner her ist (nur die Zahl, nie was).</summary>
internal static partial class NativeMethods
{
    [StructLayout(LayoutKind.Sequential)]
    private struct LASTINPUTINFO
    {
        public uint cbSize;
        public uint dwTime;
    }

    [DllImport("user32.dll")]
    private static extern bool GetLastInputInfo(ref LASTINPUTINFO plii);

    /// <summary>Sekunden seit der letzten Taste oder Mausbewegung; -1, wenn Windows es nicht sagt.</summary>
    public static int IdleSeconds()
    {
        var info = new LASTINPUTINFO { cbSize = (uint)Marshal.SizeOf<LASTINPUTINFO>() };
        if (!GetLastInputInfo(ref info))
        {
            return -1;
        }
        uint ms = unchecked((uint)Environment.TickCount - info.dwTime);
        return (int)Math.Min(ms / 1000, 7 * 86400);
    }
}
