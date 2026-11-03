using SparkBegleiter;

namespace SparkHilfe;

internal static class Program
{
    private const string MutexName = @"Local\SparkHilfe.SingleInstance";

    /// <summary>Keine Argumente, keine Einstellungen, nichts auf der Platte: nur der eigene Dateiname zählt.</summary>
    [STAThread]
    private static int Main()
    {
        Application.SetHighDpiMode(HighDpiMode.PerMonitorV2);
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        using var mutex = new Mutex(initiallyOwned: false, MutexName);
        bool owned;
        try
        {
            owned = mutex.WaitOne(TimeSpan.Zero);
        }
        catch (AbandonedMutexException)
        {
            owned = true;
        }

        if (!owned)
        {
            MessageBox.Show(Texte.T("laeuft_schon"), Texte.T("fenster"), MessageBoxButtons.OK, MessageBoxIcon.Information);
            return 0;
        }

        try
        {
            Application.Run(new HilfeContext(Ziel.FromProcess()));
        }
        finally
        {
            mutex.ReleaseMutex();
        }

        return 0;
    }
}

/// <summary>Das Programm: ein kleines Fenster mit dem Stand, dann die Frage, dann Rahmen und Leiste. Schließen des
/// Fensters oder „Beenden“ in der Leiste beendet alles; danach läuft nichts weiter.</summary>
internal sealed class HilfeContext : ApplicationContext
{
    private readonly StatusForm _status = new();
    private readonly Ziel? _ziel;
    private Sitzung? _sitzung;

    public HilfeContext(Ziel? ziel)
    {
        _ziel = ziel;
        MainForm = _status;
        _status.FormClosed += (_, _) => Ende();
        _status.Shown += async (_, _) => await StartAsync();
        _status.Show();
    }

    private async Task StartAsync()
    {
        if (_ziel is null)
        {
            _status.Say(Texte.T("name_falsch"), done: true);
            return;
        }

        _status.Say(Texte.T("verbinde", host: _ziel.Shown), done: false);
        _sitzung = new Sitzung(_ziel, _status);
        string ende = await _sitzung.RunAsync();
        _sitzung = null;
        if (ende.Length == 0)
        {
            Ende();
            return;
        }

        if (!_status.IsDisposed)
        {
            _status.Say(ende, done: true);
            _status.Show();
            _status.Activate();
        }
    }

    private void Ende()
    {
        _sitzung?.Stop();
        ExitThread();
    }
}

/// <summary>Das kleine Fenster mit dem Stand („Verbinde …“, „bitte neu laden“, „beendet“) und „Schließen“.</summary>
internal sealed class StatusForm : ThemedForm
{
    private readonly TLabel _text = new(TextRole.Normal);
    private readonly SparkButton _close;
    private Rectangle _face;
    private Rectangle _title;

    public StatusForm()
    {
        _close = new SparkButton(ButtonKind.Secondary, Texte.T("schliessen"));
        Text = Texte.T("fenster");
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        MinimizeBox = true;
        ShowInTaskbar = true;
        StartPosition = FormStartPosition.CenterScreen;
        Controls.Add(_text);
        Controls.Add(_close);
        _close.Click += (_, _) => Close();
        AcceptButton = _close;
        CancelButton = _close;
    }

    /// <summary>Neuer Stand; <paramref name="done"/>: nur noch „Schließen“ bleibt.</summary>
    public void Say(string text, bool done)
    {
        _text.Text = text;
        _close.Visible = true;
        if (IsHandleCreated)
        {
            LayoutContent();
            Invalidate(true);
        }

        if (done)
        {
            _close.Focus();
        }
    }

    protected override void LayoutContent()
    {
        int pad = S(16);
        int w = S(420);
        int inner = w - (2 * pad);
        int y = pad;
        int face = S(36);
        _face = new Rectangle(pad, y, face, face);
        _title = new Rectangle(pad + Face.Lead(face, S(10)), y, inner - Face.Lead(face, S(10)), face);
        y += face + S(12);
        y += _text.Fit(pad, y, inner) + S(14);
        Size size = _close.Preferred();
        _close.Bounds = new Rectangle(w - pad - size.Width, y, size.Width, size.Height);
        y += size.Height + pad;
        ClientSize = new Size(w, y);
    }

    protected override void PaintContent(Graphics g)
    {
        Face.DrawHeader(g, _face, P);
        Draw.Text(g, Texte.T("fenster"), F(11f, FontStyle.Bold), _title, P.Fg);
    }
}
