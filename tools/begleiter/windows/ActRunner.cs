using System.Diagnostics;
using System.Text.Json;

namespace SparkBegleiter;

/// <summary>Eine geprüfte Handlung: was die Person sieht und was dann (nur nach „Erlauben“) passiert.</summary>
internal sealed record ActPlan(string Description, Action Run);

/// <summary>
/// Teil "act": Bitten des Spark ("asks" in /api/desk/poll) prüfen, bestätigen lassen und ausführen. Erlaubt ist nur:
/// url (http/https im Standardbrowser), app (nur aus der Liste im Panel), media, volume, lock und show (reiner Text).
/// Alles andere wird abgelehnt. Jede Kennung wird höchstens einmal behandelt (auch über einen Neustart hinweg).
/// </summary>
internal static class ActRunner
{
    private static readonly HashSet<string> Seen = LoadSeen();

    /// <summary>Kennung schon behandelt? Sonst als behandelt merken und <c>false</c>.</summary>
    public static bool AlreadySeen(string id)
    {
        if (!Seen.Add(id))
        {
            return true;
        }

        SaveSeen();
        return false;
    }

    /// <summary>Prüft die Bitte. Gibt den Plan zurück oder <c>null</c> mit einem Fehlertext für den Spark.</summary>
    public static ActPlan? Plan(ActAsk ask, DeskConfig desk, out string error)
    {
        error = "";
        string arg = ask.Arg.Trim();
        switch (ask.Action)
        {
            case "url":
                if (arg.Length is 0 or > 2000 || !Uri.TryCreate(arg, UriKind.Absolute, out Uri? uri) ||
                    (uri.Scheme != Uri.UriSchemeHttps && uri.Scheme != Uri.UriSchemeHttp) || uri.UserInfo.Length > 0)
                {
                    error = "Nur http- und https-Adressen sind erlaubt.";
                    return null;
                }

                string url = uri.AbsoluteUri;
                return new ActPlan("Öffnet im Browser: " + Clip(url, 200), () =>
                {
                    using Process? p = Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
                });

            case "app":
                ActApp? app = desk.ActApps.FirstOrDefault(a => string.Equals(a.Name, arg, StringComparison.OrdinalIgnoreCase));
                if (app is null)
                {
                    error = "Dieses Programm steht nicht in der Liste des Geräts.";
                    return null;
                }

                if (!IsStartablePath(app.Path))
                {
                    error = "Der Pfad des Programms ist ungültig oder die Datei fehlt.";
                    return null;
                }

                string path = app.Path;
                return new ActPlan($"Startet „{Clip(app.Name, 60)}“ ({Clip(path, 120)})", () =>
                {
                    using Process? p = Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });
                });

            case "media":
                (byte key, string label)? media = arg switch
                {
                    "play" or "pause" => (NativeMethods.VK_MEDIA_PLAY_PAUSE, "Wiedergabe/Pause"),
                    "next" => (NativeMethods.VK_MEDIA_NEXT_TRACK, "Nächster Titel"),
                    "previous" => (NativeMethods.VK_MEDIA_PREV_TRACK, "Vorheriger Titel"),
                    _ => null,
                };
                if (media is not { } m)
                {
                    error = "Unbekannte Medientaste.";
                    return null;
                }

                return new ActPlan("Medientaste: " + m.label, () => PressKey(m.key));

            case "volume":
                (byte key, string label)? volume = arg switch
                {
                    "up" => (NativeMethods.VK_VOLUME_UP, "lauter"),
                    "down" => (NativeMethods.VK_VOLUME_DOWN, "leiser"),
                    "mute" => (NativeMethods.VK_VOLUME_MUTE, "stumm an/aus"),
                    _ => null,
                };
                if (volume is not { } v)
                {
                    error = "Unbekannte Lautstärke-Taste.";
                    return null;
                }

                return new ActPlan("Lautstärke: " + v.label, () => PressKey(v.key));

            case "lock":
                return new ActPlan("Sperrt den PC (Windows-Anmeldung nötig).", () =>
                {
                    if (!NativeMethods.LockWorkStation())
                    {
                        throw new InvalidOperationException("Der PC ließ sich nicht sperren.");
                    }
                });

            case "show":
                if (arg.Length == 0)
                {
                    error = "Kein Text zum Anzeigen.";
                    return null;
                }

                string text = arg.Length > 4000 ? arg[..4000] + " …" : arg;
                return new ActPlan("Zeigt eine Nachricht an.", () => new MessageForm(text).Show());

            default:
                error = "Diese Handlung ist am PC nicht erlaubt.";
                return null;
        }
    }

    /// <summary>Nur ein vollständiger Pfad zu einer vorhandenen Datei oder ein reiner Programmname wie "notepad.exe".</summary>
    private static bool IsStartablePath(string path)
    {
        if (path.Length is 0 or > 400 || path.IndexOfAny(new[] { '"', '\n', '\r', '\t', '|', '<', '>' }) >= 0)
        {
            return false;
        }

        try
        {
            if (Path.IsPathFullyQualified(path))
            {
                return !path.StartsWith(@"\\", StringComparison.Ordinal) && File.Exists(path);
            }

            // reiner Name (über App Paths/PATH gefunden), ohne Ordner, ohne Schema
            return path.EndsWith(".exe", StringComparison.OrdinalIgnoreCase) && Path.GetFileName(path) == path && !path.Contains(':', StringComparison.Ordinal);
        }
        catch (ArgumentException)
        {
            return false;
        }
    }

    private static void PressKey(byte vk)
    {
        NativeMethods.keybd_event(vk, 0, NativeMethods.KEYEVENTF_EXTENDEDKEY, UIntPtr.Zero);
        NativeMethods.keybd_event(vk, 0, NativeMethods.KEYEVENTF_EXTENDEDKEY | NativeMethods.KEYEVENTF_KEYUP, UIntPtr.Zero);
    }

    private static string Clip(string text, int max) => text.Length <= max ? text : text[..(max - 1)] + "…";

    private static string SeenPath => Path.Combine(AppConfig.LocalFolder, "act-erledigt.json");

    private static HashSet<string> LoadSeen()
    {
        try
        {
            if (File.Exists(SeenPath) && JsonSerializer.Deserialize<List<string>>(File.ReadAllText(SeenPath)) is { } list)
            {
                return new HashSet<string>(list, StringComparer.Ordinal);
            }
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException)
        {
            // leer anfangen
        }

        return new HashSet<string>(StringComparer.Ordinal);
    }

    private static void SaveSeen()
    {
        try
        {
            Directory.CreateDirectory(AppConfig.LocalFolder);
            // Die letzten 500 reichen: der Spark schickt nur offene Bitten.
            File.WriteAllText(SeenPath, JsonSerializer.Serialize(Seen.TakeLast(500).ToList()));
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            // dann nur im Speicher
        }
    }
}

/// <summary>
/// Rückfrage im Vordergrund (Entwurf A): „Spark möchte: &lt;Text&gt;. Erlauben?“ mit der geprüften Beschreibung
/// darunter. [Erlauben] [Nein]; nach 60 Sekunden gilt Nein. Esc und Schließen = Nein.
/// </summary>
internal sealed class ActConfirmForm : ThemedForm
{
    private const int TimeoutSeconds = 60;

    private readonly TLabel _question = new(TextRole.Normal);
    private readonly TLabel _detail = new(TextRole.SmallMuted);
    private readonly TLabel _countdown = new(TextRole.SmallMuted);
    private readonly SparkButton _allow = new(ButtonKind.Primary, "Erlauben");
    private readonly SparkButton _deny = new(ButtonKind.Secondary, "Nein");
    private readonly System.Windows.Forms.Timer _timer = new() { Interval = 1000 };
    private readonly DateTime _deadline = DateTime.UtcNow.AddSeconds(TimeoutSeconds);

    private Rectangle _face;
    private Rectangle _title;

    public ActConfirmForm(string text, string description)
    {
        Text = "Spark-Begleiter – Spark möchte etwas tun";
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        MinimizeBox = false;
        TopMost = true;
        ShowInTaskbar = true;
        StartPosition = FormStartPosition.Manual;
        KeyPreview = true;

        string shown = text.Trim().ReplaceLineEndings(" ");
        if (shown.Length > 300)
        {
            shown = shown[..299] + "…";
        }

        _question.Text = $"Spark möchte: {(shown.Length > 0 ? shown : "etwas am PC tun")}. Erlauben?";
        _detail.Text = description;
        Controls.AddRange(new Control[] { _question, _detail, _countdown, _deny, _allow });
        _deny.TabIndex = 0; // Nein zuerst: Enter allein erlaubt nichts
        _allow.TabIndex = 1;
        _allow.Click += (_, _) =>
        {
            Allowed = true;
            Close();
        };
        _deny.Click += (_, _) => Close();
        AcceptButton = _deny;
        CancelButton = _deny;
        _timer.Tick += (_, _) => UpdateCountdown();
        UpdateCountdown();

        Rectangle area = Screen.PrimaryScreen?.WorkingArea ?? Screen.FromPoint(Cursor.Position).WorkingArea;
        Location = new Point(area.Left + (area.Width / 2) - Draw.Scale(220, Dwm.DpiAt(area.Location)), area.Top + (area.Height / 3));
    }

    /// <summary>„Erlauben“ geklickt.</summary>
    public bool Allowed { get; private set; }

    /// <summary>Zeigt die Rückfrage und wartet auf die Antwort (oder 60 s).</summary>
    public Task<bool> AskAsync()
    {
        var done = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        FormClosed += (_, _) => done.TrySetResult(Allowed);
        Show();
        Activate();
        _ = NativeMethods.SetForegroundWindow(Handle);
        _deny.Focus();
        _timer.Start();
        return done.Task;
    }

    private void UpdateCountdown()
    {
        int left = (int)Math.Ceiling((_deadline - DateTime.UtcNow).TotalSeconds);
        if (left <= 0)
        {
            _timer.Stop();
            Close();
            return;
        }

        _countdown.Text = $"Ohne Antwort gilt in {left} s „Nein“.";
        if (IsHandleCreated)
        {
            LayoutContent();
            _countdown.Invalidate();
        }
    }

    protected override void LayoutContent()
    {
        int pad = S(16);
        int w = S(440);
        int inner = w - (2 * pad);
        int y = BarHeight + pad;
        int face = S(36);
        _face = new Rectangle(pad, y, face, face);
        _title = new Rectangle(pad + face + S(10), y, inner - face - S(10), face);
        y += face + S(12);
        y += _question.Fit(pad, y, inner) + S(8);
        y += _detail.Fit(pad, y, inner) + S(10);
        y += _countdown.Fit(pad, y, inner) + S(14);
        Size allow = _allow.Preferred();
        Size deny = _deny.Preferred();
        _allow.Bounds = new Rectangle(w - pad - allow.Width, y, allow.Width, allow.Height);
        _deny.Bounds = new Rectangle(_allow.Left - S(8) - deny.Width, y, deny.Width, deny.Height);
        y += Math.Max(allow.Height, deny.Height) + pad;
        ClientSize = new Size(w, y);
    }

    protected override void PaintContent(Graphics g)
    {
        Face.Draw(g, _face, P);
        Draw.Text(g, "Spark möchte etwas tun", F(11f, FontStyle.Bold), _title, P.Fg);
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            _timer.Dispose();
        }

        base.Dispose(disposing);
    }
}

/// <summary>Nachricht des Spark (act "show"): reiner Text, markier- und kopierbar, nie als Markup.</summary>
internal sealed class MessageForm : ThemedForm
{
    private readonly TextBox _text = new()
    {
        Multiline = true,
        ReadOnly = true,
        ScrollBars = ScrollBars.Vertical,
        WordWrap = true,
        AccessibleName = "Nachricht",
    };

    private readonly RoundedHost _host;
    private readonly SparkButton _ok = new(ButtonKind.Primary, "OK");
    private Rectangle _face;
    private Rectangle _title;

    public MessageForm(string text)
    {
        _host = new RoundedHost(_text);
        _text.Text = text.Replace("\r\n", "\n", StringComparison.Ordinal).Replace("\n", Environment.NewLine, StringComparison.Ordinal);
        Text = "Spark-Begleiter – Nachricht vom Spark";
        TopMost = true;
        ShowInTaskbar = true;
        StartPosition = FormStartPosition.Manual;
        MinimizeBox = false;
        MaximizeBox = false;
        KeyPreview = true;
        Controls.AddRange(new Control[] { _host, _ok });
        _ok.Click += (_, _) => Close();
        AcceptButton = _ok;
        CancelButton = _ok;

        Rectangle area = Screen.FromPoint(Cursor.Position).WorkingArea;
        int dpi = Dwm.DpiAt(Cursor.Position);
        int w = Math.Min(Draw.Scale(440, dpi), area.Width);
        int h = Math.Min(Draw.Scale(300, dpi), area.Height);
        Bounds = new Rectangle(area.Left + ((area.Width - w) / 2), area.Top + ((area.Height - h) / 2), w, h);
    }

    protected override void OnLoad(EventArgs e)
    {
        base.OnLoad(e);
        ActiveControl = _ok;
    }

    protected override void LayoutContent()
    {
        int pad = S(14);
        int w = ClientSize.Width;
        int h = ClientSize.Height;
        int y = BarHeight + pad;
        int face = S(28);
        _face = new Rectangle(pad, y, face, face);
        _title = new Rectangle(pad + face + S(8), y, w - (2 * pad) - face - S(8), face);
        y += face + S(10);
        Size ok = _ok.Preferred();
        _ok.Bounds = new Rectangle(w - pad - ok.Width, h - pad - ok.Height, ok.Width, ok.Height);
        _host.Bounds = new Rectangle(pad, y, w - (2 * pad), Math.Max(S(40), _ok.Top - S(10) - y));
    }

    protected override void PaintContent(Graphics g)
    {
        Face.Draw(g, _face, P);
        Draw.Text(g, "Nachricht vom Spark", F(10.5f, FontStyle.Bold), _title, P.Fg);
    }
}
