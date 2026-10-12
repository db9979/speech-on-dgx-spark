using System.Net;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;

namespace SparkBegleiter;

/// <summary>
/// Teil "mail" mit dem klassischen Outlook, spät gebunden über COM (IDispatch/InvokeMember, keine Interop-Assembly):
/// die offene bzw. markierte Mail lesen und eine Antwort als ENTWURF öffnen (MailItem.Reply() … Display()).
/// Es wird nie gesendet. Das neue Outlook (olk.exe) hat kein COM – dann gibt es <c>null</c>.
/// </summary>
internal sealed class OutlookMail : IDisposable
{
    public const int MaxBody = 20000;
    private const int OlMail = 43;
    private const int OlFormatHtml = 2;

    private object? _app;
    private object? _item;

    private OutlookMail(object app, object item, string sender, string subject, string body)
    {
        _app = app;
        _item = item;
        Sender = sender;
        Subject = subject;
        Body = body;
    }

    public string Sender { get; }

    public string Subject { get; }

    public string Body { get; }

    /// <summary>Was an den Spark geht: Absender, Betreff und Text (zusammen höchstens 20 000 Zeichen).</summary>
    public string ForSpark
    {
        get
        {
            string text = $"Von: {Sender}\nBetreff: {Subject}\n\n{Body}";
            return text.Length > MaxBody ? text[..MaxBody] : text;
        }
    }

    /// <summary>
    /// Die Mail im aktiven Lesefenster (keine eigenen Entwürfe) oder die erste markierte im Hauptfenster des laufenden
    /// klassischen Outlook. <c>null</c>, wenn Outlook (klassisch) nicht läuft; dann steht in <paramref name="problem"/>
    /// nichts. Läuft es, ist aber keine Mail gewählt, steht dort ein deutscher Hinweis.
    /// </summary>
    public static OutlookMail? TryOpen(out string? problem)
    {
        problem = null;
        object? app = Running();
        if (app is null)
        {
            return null;
        }

        object? item = null;
        try
        {
            item = FromInspector(app) ?? FromSelection(app);
            if (item is null)
            {
                Release(app);
                problem = "In Outlook ist keine Mail geöffnet oder markiert.";
                return null;
            }

            string sender = Get(item, "SenderName") as string ?? "";
            string subject = Get(item, "Subject") as string ?? "";
            string body = Get(item, "Body") as string ?? "";
            if (body.Length > MaxBody)
            {
                body = body[..MaxBody];
            }

            return new OutlookMail(app, item, sender, subject, body);
        }
        catch (Exception ex) when (IsComFailure(ex))
        {
            Release(item);
            Release(app);
            problem = "Outlook hat die Mail nicht herausgegeben (vielleicht ist ein Dialog offen).";
            return null;
        }
    }

    /// <summary>Antwort-Entwurf öffnen: Text über das Zitat der Originalmail, dann anzeigen. Nie senden.</summary>
    public void OpenReply(string answer)
    {
        if (_item is null)
        {
            throw new InvalidOperationException("Keine Mail.");
        }

        object? reply = null;
        try
        {
            reply = Call(_item, "Reply") ?? throw new InvalidOperationException("Outlook hat keine Antwort angelegt.");
            if (Get(reply, "BodyFormat") is int format && format == OlFormatHtml && Get(reply, "HTMLBody") is string html)
            {
                Set(reply, "HTMLBody", InsertHtml(html, answer));
            }
            else
            {
                string old = Get(reply, "Body") as string ?? "";
                Set(reply, "Body", answer.Replace("\r\n", "\n", StringComparison.Ordinal).Replace("\n", "\r\n", StringComparison.Ordinal) + "\r\n\r\n" + old);
            }

            _ = Call(reply, "Display", false); // nur anzeigen – .Send() wird nie aufgerufen
        }
        catch (Exception ex) when (IsComFailure(ex))
        {
            throw new InvalidOperationException("Outlook hat den Entwurf nicht geöffnet.", ex);
        }
        finally
        {
            Release(reply);
        }
    }

    /// <summary>Antwort als HTML-Absätze direkt nach &lt;body …&gt; einfügen (Text maskiert, nie als Markup übernommen).</summary>
    public static string InsertHtml(string html, string answer)
    {
        var paragraphs = new StringBuilder();
        string normalized = answer.Replace("\r\n", "\n", StringComparison.Ordinal).Trim();
        foreach (string block in normalized.Split("\n\n", StringSplitOptions.RemoveEmptyEntries))
        {
            string lines = string.Join("<br>", block.Split('\n').Select(WebUtility.HtmlEncode));
            paragraphs.Append("<p style=\"margin:0 0 10pt 0\">").Append(lines).Append("</p>");
        }

        paragraphs.Append("<p style=\"margin:0 0 10pt 0\">&nbsp;</p>");
        int body = html.IndexOf("<body", StringComparison.OrdinalIgnoreCase);
        int end = body >= 0 ? html.IndexOf('>', body) : -1;
        return end >= 0 ? html.Insert(end + 1, paragraphs.ToString()) : paragraphs + html;
    }

    private static object? Running()
    {
        try
        {
            if (NativeMethods.CLSIDFromProgID("Outlook.Application", out Guid clsid) != 0)
            {
                return null; // klassisches Outlook nicht installiert
            }

            return NativeMethods.GetActiveObject(ref clsid, IntPtr.Zero, out object? app) == 0 ? app : null;
        }
        catch (Exception ex) when (ex is DllNotFoundException or EntryPointNotFoundException or COMException)
        {
            return null;
        }
    }

    private static object? FromInspector(object app)
    {
        object? inspector = Call(app, "ActiveInspector");
        if (inspector is null)
        {
            return null;
        }

        try
        {
            object? item = Get(inspector, "CurrentItem");
            if (IsMail(item) && Get(item!, "Sent") is true)
            {
                return item; // gelesene Mail; eigene Entwürfe überspringen
            }

            Release(item);
            return null;
        }
        finally
        {
            Release(inspector);
        }
    }

    private static object? FromSelection(object app)
    {
        object? explorer = Call(app, "ActiveExplorer");
        object? selection = null;
        try
        {
            selection = explorer is null ? null : Get(explorer, "Selection");
            if (selection is null || Get(selection, "Count") is not int count || count < 1)
            {
                return null;
            }

            object? item = Call(selection, "Item", 1);
            if (IsMail(item))
            {
                return item;
            }

            Release(item);
            return null;
        }
        finally
        {
            Release(selection);
            Release(explorer);
        }
    }

    private static bool IsMail(object? item) => item is not null && Get(item, "Class") is int c && c == OlMail;

    private static object? Get(object target, string name) =>
        target.GetType().InvokeMember(name, BindingFlags.GetProperty, null, target, null, System.Globalization.CultureInfo.InvariantCulture);

    private static void Set(object target, string name, object value) =>
        target.GetType().InvokeMember(name, BindingFlags.SetProperty, null, target, new[] { value }, System.Globalization.CultureInfo.InvariantCulture);

    private static object? Call(object target, string name, params object[] args) =>
        target.GetType().InvokeMember(name, BindingFlags.InvokeMethod, null, target, args, System.Globalization.CultureInfo.InvariantCulture);

    private static bool IsComFailure(Exception ex) =>
        ex is COMException or TargetInvocationException or MissingMethodException or InvalidCastException or InvalidComObjectException;

    private static void Release(object? com)
    {
        if (com is not null && Marshal.IsComObject(com))
        {
            try
            {
                _ = Marshal.ReleaseComObject(com);
            }
            catch (Exception ex) when (ex is ArgumentException or InvalidComObjectException)
            {
                // schon freigegeben
            }
        }
    }

    public void Dispose()
    {
        Release(_item);
        Release(_app);
        _item = null;
        _app = null;
    }
}

/// <summary>
/// „Antwort entwerfen“ (Entwurf A): zeigt, auf welche Mail geantwortet wird, nimmt optionale Stichpunkte und lässt den
/// Spark die Antwort schreiben. Mit klassischem Outlook öffnet sich danach ein Antwort-Entwurf (nie gesendet); ohne
/// (neues Outlook) liegt die Antwort in der Zwischenablage – „In die Antwort einfügen (Strg+V)“.
/// </summary>
internal sealed class MailForm : ThemedForm
{
    private readonly OutlookMail? _outlook;
    private readonly Func<string, string, CancellationToken, Task<string>> _write;
    private readonly Action<SparkException> _report;
    private readonly List<DictateMic> _mics = new();

    private readonly TLabel _from = new(TextRole.SmallMuted);
    private readonly TLabel _mailLabel = new(TextRole.Heading, "Mail-Text");
    private readonly TextBox _mail = NewBox("Mail-Text", "Den Text der Mail hier einfügen (oder vorher markieren und Strg+Alt+M)", 20000);
    private readonly RoundedHost _mailHost;
    private readonly TLabel _notesLabel = new(TextRole.Heading, "Stichpunkte für die Antwort (optional)");
    private readonly TextBox _notes = NewBox("Stichpunkte", "z. B. „Termin passt, Unterlagen folgen Freitag“", 1000);
    private readonly RoundedHost _notesHost;
    private readonly TextBox _answer = NewBox("Antwort", "", 100000);
    private readonly RoundedHost _answerHost;
    private readonly TLabel _status = new(TextRole.SmallMuted);
    private readonly SparkButton _cancel = new(ButtonKind.Secondary, "Abbrechen");
    private readonly SparkButton _copy = new(ButtonKind.Secondary, "Kopieren") { Visible = false };
    private readonly SparkButton _go;

    private Rectangle _face;
    private Rectangle _title;
    private CancellationTokenSource? _cts;
    private bool _done;

    /// <param name="outlook">Die gelesene Mail aus dem klassischen Outlook, oder <c>null</c> (Ausweichweg).</param>
    /// <param name="selection">Ausweichweg: markierter Text aus dem Programm im Vordergrund.</param>
    /// <param name="write">Ruft /api/write/assist {"art":"antwort","mail","text"} auf.</param>
    /// <param name="dictation">Einsprechen in die Felder (Teil „Diktieren“), oder <c>null</c>.</param>
    public MailForm(OutlookMail? outlook, string? selection, Func<string, string, CancellationToken, Task<string>> write, Action<SparkException> report, Dictation? dictation = null)
    {
        _outlook = outlook;
        _write = write;
        _report = report;
        _mailHost = new RoundedHost(_mail);
        _notesHost = new RoundedHost(_notes);
        _answerHost = new RoundedHost(_answer) { Visible = false };
        _answer.ReadOnly = true;
        _go = new SparkButton(ButtonKind.Primary, outlook is not null ? "Entwurf öffnen" : "Antwort schreiben");
        if (dictation is not null)
        {
            _mics.Add(new DictateMic(_notesHost, dictation, SetStatus));
            if (outlook is null)
            {
                _mics.Add(new DictateMic(_mailHost, dictation, SetStatus));
            }
        }

        Text = "Spark-Begleiter – Antwort entwerfen";
        TopMost = true;
        ShowInTaskbar = true;
        StartPosition = FormStartPosition.Manual;
        MinimizeBox = false;
        MaximizeBox = false;
        KeyPreview = true;

        if (outlook is not null)
        {
            _from.Text = $"Antwort an {Clip(outlook.Sender, 60)} · {Clip(outlook.Subject, 80)}";
            _mailHost.Visible = false;
            _mailLabel.Visible = false;
        }
        else
        {
            _from.Text = "Klassisches Outlook ist nicht geöffnet (das neue Outlook lässt sich nicht steuern). "
                         + "Die Antwort kommt in die Zwischenablage.";
            _mail.Text = selection ?? "";
        }

        Controls.AddRange(new Control[] { _from, _mailLabel, _mailHost, _notesLabel, _notesHost, _answerHost, _status, _cancel, _copy, _go });
        _mailHost.TabIndex = 0;
        _notesHost.TabIndex = 1;
        _go.TabIndex = 2;
        _copy.TabIndex = 3;
        _cancel.TabIndex = 4;

        _go.Click += async (_, _) => await RunAsync();
        _cancel.Click += (_, _) => Close();
        _copy.Click += (_, _) => SetStatus(ClipboardHelper.TrySetText(_answer.Text, keepOutOfHistory: false)
            ? "Kopiert. In die Antwort einfügen (Strg+V)." : "Die Zwischenablage ist gerade gesperrt.", error: false);

        Rectangle area = Screen.FromPoint(Cursor.Position).WorkingArea;
        int dpi = Dwm.DpiAt(Cursor.Position);
        int w = Math.Min(Draw.Scale(520, dpi), area.Width);
        int h = Math.Min(Draw.Scale(outlook is null ? 560 : 360, dpi), area.Height);
        Bounds = new Rectangle(area.Left + ((area.Width - w) / 2), area.Top + ((area.Height - h) / 2), w, h);
        MinimumSize = new Size(Math.Min(Draw.Scale(400, dpi), w), Math.Min(Draw.Scale(300, dpi), h));
    }

    private static TextBox NewBox(string name, string placeholder, int max) => new()
    {
        Multiline = true,
        AcceptsReturn = true,
        ScrollBars = ScrollBars.Vertical,
        WordWrap = true,
        MaxLength = max,
        PlaceholderText = placeholder,
        AccessibleName = name,
    };

    private static string Clip(string text, int max) => text.Length <= max ? text : text[..(max - 1)] + "…";

    protected override void OnLoad(EventArgs e)
    {
        base.OnLoad(e);
        ActiveControl = _outlook is null && _mail.TextLength == 0 ? _mail : _notes;
    }

    protected override void LayoutContent()
    {
        int pad = S(14);
        int w = ClientSize.Width;
        int h = ClientSize.Height;
        int inner = w - (2 * pad);
        int y = BarHeight + pad;
        int face = S(28);
        _face = new Rectangle(pad, y, face, face);
        _title = new Rectangle(pad + face + S(8), y, inner - face - S(8), face);
        y += face + S(8);
        y += _from.Fit(pad, y, inner) + S(10);

        Size go = _go.Preferred();
        int buttonsY = h - pad - go.Height;
        _go.Bounds = new Rectangle(w - pad - go.Width, buttonsY, go.Width, go.Height);
        int x = _go.Left - S(8);
        if (_copy.Visible)
        {
            Size c = _copy.Preferred();
            _copy.Bounds = new Rectangle(x - c.Width, buttonsY, c.Width, c.Height);
            x = _copy.Left - S(8);
        }

        Size cancel = _cancel.Preferred();
        _cancel.Bounds = new Rectangle(x - cancel.Width, buttonsY, cancel.Width, cancel.Height);
        int statusH = _status.Text.Length > 0 ? Draw.TextHeight(_status.Text, _status.Font, inner) : 0;
        int statusY = buttonsY - S(8) - statusH;
        _status.Fit(pad, statusY, inner);
        int bottom = (statusH > 0 ? statusY : buttonsY) - S(10);

        if (_answerHost.Visible)
        {
            _answerHost.Bounds = new Rectangle(pad, y, inner, Math.Max(S(60), bottom - y));
            _mailLabel.Visible = false;
            _mailHost.Visible = false;
            _notesLabel.Visible = false;
            _notesHost.Visible = false;
            return;
        }

        int notesH = S(84);
        if (_outlook is null)
        {
            y += _mailLabel.Fit(pad, y, inner) + S(4);
            int labelH = Draw.TextHeight(_notesLabel.Text, _notesLabel.Font, inner);
            int mailH = Math.Max(S(60), bottom - y - S(10) - labelH - S(4) - notesH);
            _mailHost.Bounds = new Rectangle(pad, y, inner, mailH);
            y += mailH + S(10);
        }

        y += _notesLabel.Fit(pad, y, inner) + S(4);
        _notesHost.Bounds = new Rectangle(pad, y, inner, Math.Max(S(48), bottom - y));
    }

    protected override void PaintContent(Graphics g)
    {
        Face.Draw(g, _face, P);
        Draw.Text(g, "Antwort entwerfen", F(10.5f, FontStyle.Bold), _title, P.Fg);
    }

    private async Task RunAsync()
    {
        if (_done)
        {
            Close();
            return;
        }

        if (_mics.Exists(m => m.Busy))
        {
            SetStatus("Bitte zuerst die Aufnahme beenden (■).", error: true);
            return;
        }

        string mail = _outlook?.ForSpark ?? _mail.Text.Trim();
        if (mail.Length == 0)
        {
            SetStatus("Bitte zuerst den Text der Mail einfügen.", error: true);
            _mail.Focus();
            return;
        }

        if (mail.Length > OutlookMail.MaxBody)
        {
            mail = mail[..OutlookMail.MaxBody];
        }

        _go.Enabled = false;
        _notes.ReadOnly = true;
        _mail.ReadOnly = true;
        RefreshMics();
        SetStatus("Der Spark schreibt die Antwort …", error: false);
        _cts = new CancellationTokenSource();
        try
        {
            string answer = (await _write(mail, _notes.Text.Trim(), _cts.Token)).Trim();
            if (IsDisposed)
            {
                return;
            }

            if (_outlook is not null)
            {
                try
                {
                    _outlook.OpenReply(answer);
                    Close();
                    return;
                }
                catch (InvalidOperationException ex)
                {
                    // Outlook wollte nicht: dann wie beim neuen Outlook über die Zwischenablage.
                    ShowAnswer(answer, ex.Message + " ");
                    return;
                }
            }

            ShowAnswer(answer, "");
        }
        catch (OperationCanceledException)
        {
            // Fenster geschlossen
        }
        catch (SparkException ex)
        {
            if (!IsDisposed)
            {
                SetStatus(ex.Message, error: true);
                _go.Enabled = true;
                _notes.ReadOnly = false;
                _mail.ReadOnly = false;
                RefreshMics();
            }

            _report(ex);
        }
        finally
        {
            _cts?.Dispose();
            _cts = null;
        }
    }

    private void ShowAnswer(string answer, string prefix)
    {
        _done = true;
        _answer.Text = answer.Replace("\r\n", "\n", StringComparison.Ordinal).Replace("\n", Environment.NewLine, StringComparison.Ordinal);
        _answerHost.Visible = true;
        _copy.Visible = true;
        _cancel.Visible = false;
        _go.Text = "Schließen";
        _go.Enabled = true;
        bool copied = ClipboardHelper.TrySetText(_answer.Text, keepOutOfHistory: false);
        SetStatus(prefix + (copied ? "Die Antwort liegt in der Zwischenablage. In die Antwort einfügen (Strg+V)."
            : "Die Zwischenablage war gesperrt – „Kopieren“ klicken."), error: false);
    }

    private void RefreshMics() => _mics.ForEach(m => m.Refresh());

    protected override void OnThemeApplied() => RefreshMics();

    protected override void OnActivated(EventArgs e)
    {
        base.OnActivated(e);
        RefreshMics();
    }

    private void SetStatus(string text, bool error)
    {
        _status.Text = text;
        _status.Role = error ? TextRole.Error : TextRole.SmallMuted;
        _status.ApplyTheme(DeviceDpi);
        if (IsHandleCreated)
        {
            LayoutContent();
            Invalidate(true);
        }
    }

    protected override bool ProcessCmdKey(ref Message msg, Keys keyData)
    {
        if (keyData == Keys.Escape)
        {
            Close();
            return true;
        }

        if (keyData == (Keys.Control | Keys.Enter) && _go.Enabled)
        {
            _ = RunAsync();
            return true;
        }

        return base.ProcessCmdKey(ref msg, keyData);
    }

    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        _cts?.Cancel();
        _mics.ForEach(m => m.Dispose());
        base.OnFormClosing(e);
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            _outlook?.Dispose();
        }

        base.Dispose(disposing);
    }
}
