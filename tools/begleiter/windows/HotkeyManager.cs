namespace SparkBegleiter;

/// <summary>Unsichtbares Fenster, das die globalen Tastenkürzel der Teile (write/ask/dictate) empfängt.</summary>
internal sealed class HotkeyManager : NativeWindow, IDisposable
{
    private readonly Dictionary<int, string> _byId = new();
    private readonly Dictionary<string, (int Id, Hotkey Hotkey)> _byPart = new();

    public HotkeyManager() => CreateHandle(new CreateParams());

    /// <summary>Wird mit der Kennung des Teils ausgelöst (z. B. "write").</summary>
    public event EventHandler<string>? Pressed;

    /// <summary>Ist für den Teil gerade dieses Kürzel registriert?</summary>
    public bool IsRegistered(string part, Hotkey hotkey) =>
        _byPart.TryGetValue(part, out var entry) && entry.Hotkey == hotkey;

    /// <summary>
    /// Registriert das Kürzel für den Teil (ein vorheriges wird freigegeben).
    /// <c>false</c>, wenn ein anderes Programm (oder Windows) die Kombination schon belegt.
    /// </summary>
    public bool Register(string part, Hotkey hotkey)
    {
        if (IsRegistered(part, hotkey))
        {
            return true;
        }

        Unregister(part);
        if (!hotkey.IsValid)
        {
            return false;
        }

        int id = Array.IndexOf(Parts.WithHotkey, part) + 1;
        if (id <= 0)
        {
            return false;
        }

        bool ok = NativeMethods.RegisterHotKey(Handle, id, hotkey.Win32Modifiers | NativeMethods.MOD_NOREPEAT, hotkey.VirtualKey);
        if (ok)
        {
            _byId[id] = part;
            _byPart[part] = (id, hotkey);
        }

        return ok;
    }

    public void Unregister(string part)
    {
        if (_byPart.Remove(part, out var entry))
        {
            NativeMethods.UnregisterHotKey(Handle, entry.Id);
            _byId.Remove(entry.Id);
        }
    }

    public void UnregisterAll()
    {
        foreach (string part in _byPart.Keys.ToList())
        {
            Unregister(part);
        }
    }

    protected override void WndProc(ref Message m)
    {
        if (m.Msg == NativeMethods.WM_HOTKEY && _byId.TryGetValue((int)m.WParam, out string? part))
        {
            Pressed?.Invoke(this, part);
            return;
        }

        base.WndProc(ref m);
    }

    public void Dispose()
    {
        UnregisterAll();
        DestroyHandle();
    }
}
