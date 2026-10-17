using System.Runtime.InteropServices;

namespace SparkBegleiter;

/// <summary>Win32 für „Rechner fernsteuern“: Fenster, Unicode-Tippen, Bildschirm aus, Maus (Stufe 2).</summary>
internal static partial class NativeMethods
{
    public const uint KEYEVENTF_UNICODE = 0x0004;
    public const uint WM_CLOSE = 0x0010;
    public const uint WM_SYSCOMMAND = 0x0112;
    public const int SC_MONITORPOWER = 0xF170;
    public const int SW_MINIMIZE = 6;
    public const int SW_MAXIMIZE = 3;
    public static readonly IntPtr HWND_BROADCAST = new(0xFFFF);
    public const uint INPUT_MOUSE = 0;
    public const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
    public const uint MOUSEEVENTF_LEFTUP = 0x0004;
    public const uint MOUSEEVENTF_RIGHTDOWN = 0x0008;
    public const uint MOUSEEVENTF_RIGHTUP = 0x0010;
    public const uint MOUSEEVENTF_WHEEL = 0x0800;
    public const int WS_EX_TRANSPARENT = 0x00000020;

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool SetCursorPos(int x, int y);

    /// <summary>WDA_EXCLUDEFROMCAPTURE (Windows 10 2004+): Rahmen, Leiste und Rückfragen nicht im Bild an den Spark.</summary>
    public const uint WDA_EXCLUDEFROMCAPTURE = 0x11;

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool SetWindowDisplayAffinity(IntPtr hWnd, uint affinity);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool PostMessage(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);
}
