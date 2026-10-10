namespace SparkSchreibhilfe;

/// <summary>Unsichtbares Fenster, das das globale Tastenkürzel Strg+Alt+S empfängt.</summary>
internal sealed class HotkeyWindow : NativeWindow, IDisposable
{
    private const int HotkeyId = 0x5348; // "SH"

    private bool _registered;

    public HotkeyWindow() => CreateHandle(new CreateParams());

    public event EventHandler? Pressed;

    /// <summary>Registriert Strg+Alt+S. <c>false</c>, wenn ein anderes Programm es schon belegt.</summary>
    public bool Register()
    {
        _registered = NativeMethods.RegisterHotKey(
            Handle, HotkeyId,
            NativeMethods.MOD_CONTROL | NativeMethods.MOD_ALT | NativeMethods.MOD_NOREPEAT,
            NativeMethods.VK_S);
        return _registered;
    }

    protected override void WndProc(ref Message m)
    {
        if (m.Msg == NativeMethods.WM_HOTKEY && m.WParam == HotkeyId)
        {
            Pressed?.Invoke(this, EventArgs.Empty);
            return;
        }

        base.WndProc(ref m);
    }

    public void Dispose()
    {
        if (_registered)
        {
            NativeMethods.UnregisterHotKey(Handle, HotkeyId);
            _registered = false;
        }

        DestroyHandle();
    }
}
