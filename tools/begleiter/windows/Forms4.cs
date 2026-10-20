using System.Globalization;

namespace SparkBegleiter;

/// <summary>
/// Rückfrage in Entwurf A mit eigenen Knöpfen (z. B. „Link öffnen?“ oder der Hinweis vor der ersten Besprechung).
/// Der erste Knopf ist der Hauptknopf; Esc/Schließen = keine Wahl (<c>null</c>). Texte sind reiner Text.
/// </summary>
internal sealed class ChoiceForm : ThemedForm
{
    private readonly string _heading;
    private readonly TLabel _text = new(TextRole.Normal);
    private readonly TLabel _detail = new(TextRole.SmallMuted);
    private readonly List<(SparkButton Button, string Key)> _buttons = new();
    private Rectangle _face;
    private Rectangle _title;

    /// <param name="buttons">Beschriftung und Kennung; der erste ist der Hauptknopf (Verlauf).</param>
    /// <param name="focusIndex">Welcher Knopf zuerst den Fokus hat (Enter).</param>
    public ChoiceForm(string heading, string text, string? detail, IReadOnlyList<(string Label, string Key, bool Enabled)> buttons, int focusIndex = 0)
    {
        _heading = heading;
        Text = "Spark-Begleiter – " + heading;
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        MinimizeBox = false;
        TopMost = true;
        ShowInTaskbar = true;
        StartPosition = FormStartPosition.Manual;
        KeyPreview = true;

        _text.Text = text;
        _detail.Text = detail ?? "";
        Controls.Add(_text);
        Controls.Add(_detail);
        for (int i = 0; i < buttons.Count; i++)
        {
            var (label, key, enabled) = buttons[i];
            var button = new SparkButton(i == 0 ? ButtonKind.Primary : ButtonKind.Secondary, label) { Enabled = enabled, TabIndex = i };
            button.Click += (_, _) =>
            {
                Choice = key;
                Close();
            };
            _buttons.Add((button, key));
            Controls.Add(button);
        }

        FocusIndex = Math.Clamp(focusIndex, 0, Math.Max(0, buttons.Count - 1));

        Rectangle area = Screen.FromPoint(Cursor.Position).WorkingArea;
        Location = new Point(area.Left + (area.Width / 2) - Draw.Scale(230, Dwm.DpiAt(area.Location)), area.Top + (area.Height / 3));
    }

    /// <summary>Kennung des geklickten Knopfs oder <c>null</c>.</summary>
    public string? Choice { get; private set; }

    private int FocusIndex { get; }

    /// <summary>Zeigt die Rückfrage im Vordergrund und wartet auf die Antwort.</summary>
    public Task<string?> AskAsync()
    {
        var done = new TaskCompletionSource<string?>(TaskCreationOptions.RunContinuationsAsynchronously);
        FormClosed += (_, _) => done.TrySetResult(Choice);
        Show();
        Activate();
        _ = NativeMethods.SetForegroundWindow(Handle);
        if (_buttons.Count > 0)
        {
            _buttons[FocusIndex].Button.Focus();
        }

        return done.Task;
    }

    protected override bool ProcessCmdKey(ref Message msg, Keys keyData)
    {
        if (keyData == Keys.Escape)
        {
            Close();
            return true;
        }

        return base.ProcessCmdKey(ref msg, keyData);
    }

    protected override void LayoutContent()
    {
        int pad = S(16);
        int w = S(460);
        int inner = w - (2 * pad);
        int y = BarHeight + pad;
        int face = S(36);
        _face = new Rectangle(pad, y, face, face);
        _title = new Rectangle(pad + face + S(10), y, inner - face - S(10), face);
        y += face + S(12);
        y += _text.Fit(pad, y, inner) + S(8);
        int dh = _detail.Fit(pad, y, inner);
        y += dh > 0 ? dh + S(14) : S(6);

        int x = w - pad;
        int rowH = 0;
        foreach (var (button, _) in _buttons)
        {
            Size size = button.Preferred();
            x -= size.Width;
            button.Bounds = new Rectangle(x, y, size.Width, size.Height);
            x -= S(8);
            rowH = Math.Max(rowH, size.Height);
        }

        y += rowH + pad;
        ClientSize = new Size(w, y);
    }

    protected override void PaintContent(Graphics g)
    {
        Face.Draw(g, _face, P);
        Draw.Text(g, _heading, F(11f, FontStyle.Bold), _title, P.Fg);
    }
}

/// <summary>Teil "home": nach dem Codewort fragen (verdeckte Eingabe, wird nicht gespeichert).</summary>
internal sealed class CodeWordForm : ThemedForm
{
    private readonly TLabel _text = new(TextRole.Normal);
    private readonly TextBox _box = new() { UseSystemPasswordChar = true, AccessibleName = "Codewort", MaxLength = 200 };
    private readonly RoundedHost _host;
    private readonly SparkButton _ok = new(ButtonKind.Primary, "Senden");
    private readonly SparkButton _cancel = new(ButtonKind.Secondary, "Abbrechen");
    private Rectangle _face;
    private Rectangle _title;

    public CodeWordForm(string detail, string buttonName)
    {
        Text = "Spark-Begleiter – Codewort";
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        MinimizeBox = false;
        TopMost = true;
        ShowInTaskbar = true;
        StartPosition = FormStartPosition.Manual;
        _host = new RoundedHost(_box);
        _text.Text = $"„{buttonName}“: {detail}";
        Controls.AddRange(new Control[] { _text, _host, _cancel, _ok });
        _host.TabIndex = 0;
        _ok.TabIndex = 1;
        _cancel.TabIndex = 2;
        _ok.Click += (_, _) =>
        {
            if (_box.Text.Length > 0)
            {
                DialogResult = DialogResult.OK;
            }
        };
        _cancel.Click += (_, _) => DialogResult = DialogResult.Cancel;
        AcceptButton = _ok;
        CancelButton = _cancel;
        Rectangle area = Screen.FromPoint(Cursor.Position).WorkingArea;
        Location = new Point(area.Left + (area.Width / 2) - Draw.Scale(200, Dwm.DpiAt(area.Location)), area.Top + (area.Height / 3));
    }

    public string Code => _box.Text;

    protected override void OnShown(EventArgs e)
    {
        base.OnShown(e);
        _ = NativeMethods.SetForegroundWindow(Handle);
        _box.Focus();
    }

    protected override void LayoutContent()
    {
        int pad = S(16);
        int w = S(400);
        int inner = w - (2 * pad);
        int y = BarHeight + pad;
        int face = S(32);
        _face = new Rectangle(pad, y, face, face);
        _title = new Rectangle(pad + face + S(10), y, inner - face - S(10), face);
        y += face + S(12);
        y += _text.Fit(pad, y, inner) + S(10);
        _host.Bounds = new Rectangle(pad, y, inner, S(36));
        y += S(36) + S(14);
        Size ok = _ok.Preferred();
        Size cancel = _cancel.Preferred();
        _ok.Bounds = new Rectangle(w - pad - ok.Width, y, ok.Width, ok.Height);
        _cancel.Bounds = new Rectangle(_ok.Left - S(8) - cancel.Width, y, cancel.Width, cancel.Height);
        y += Math.Max(ok.Height, cancel.Height) + pad;
        ClientSize = new Size(w, y);
    }

    protected override void PaintContent(Graphics g)
    {
        Face.Draw(g, _face, P);
        Draw.Text(g, "Codewort nötig", F(11f, FontStyle.Bold), _title, P.Fg);
    }
}

/// <summary>Häkchen in Entwurf A (Kästchen mit Akzentfarbe), Text umbrechend; Leertaste und Klick wie eine CheckBox.</summary>
internal sealed class TaskCheck : CheckBox, IThemed
{
    private int _dpi = 96;

    public TaskCheck(string text)
    {
        Text = text;
        SetStyle(ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
        AutoSize = false;
        UseMnemonic = false;
        Cursor = Cursors.Hand;
    }

    public void ApplyTheme(int dpi)
    {
        _dpi = dpi;
        Font = Theme.UiFont(dpi, 9.5f);
        Invalidate();
    }

    private int S(float v) => Draw.Scale(v, _dpi);

    public int Fit(int x, int y, int width)
    {
        int h = Math.Max(S(22), Draw.TextHeight(Text, Font, Math.Max(1, width - S(28))) + S(4));
        Bounds = new Rectangle(x, y, width, h);
        return h;
    }

    protected override void OnCheckedChanged(EventArgs e)
    {
        Invalidate();
        base.OnCheckedChanged(e);
    }

    protected override void OnGotFocus(EventArgs e)
    {
        Invalidate();
        base.OnGotFocus(e);
    }

    protected override void OnLostFocus(EventArgs e)
    {
        Invalidate();
        base.OnLostFocus(e);
    }

    protected override void OnPaint(PaintEventArgs pevent)
    {
        Graphics g = pevent.Graphics;
        Palette p = Theme.Current;
        g.Clear(Parent?.BackColor ?? p.Card);
        Draw.HighQuality(g);
        var box = new RectangleF(S(1), S(3), S(16), S(16));
        if (Checked)
        {
            Draw.FillRound(g, p.Accent, box, S(4));
            using var pen = new Pen(p.OnAccent, Math.Max(1.5f, S(2)));
            g.DrawLines(pen, new PointF[]
            {
                new(box.X + S(3.5f), box.Y + S(8)),
                new(box.X + S(6.5f), box.Y + S(11)),
                new(box.X + S(12.5f), box.Y + S(5)),
            });
        }
        else
        {
            Draw.FillRound(g, p.Soft, box, S(4));
            Draw.StrokeRound(g, p.Muted, box, S(4));
        }

        if (Focused && ShowFocusCues)
        {
            Draw.StrokeRound(g, p.Accent, RectangleF.Inflate(box, S(2), S(2)), S(6), Math.Max(1.5f, S(1.5f)));
        }

        int tx = S(28);
        TextRenderer.DrawText(g, Text, Font, new Rectangle(tx, S(2), Math.Max(1, Width - tx), Height - S(2)),
            Enabled ? p.Fg : p.Muted, Draw.Wrap);
    }
}

/// <summary>
/// Teil "meeting", nach dem Beenden: Zusammenfassung (markier- und kopierbar), Aufgaben als Häkchen (keins
/// vorausgewählt), „Ausgewählte auf die Liste“ mit Listenwahl (Standard „Aufgaben“, nur wenn der Spark Listen schickt),
/// „Als Erinnerung“, „Aufs reMarkable“ (nur wenn das Panel es anbietet), „Schließen“.
/// </summary>
internal sealed class MeetingEndForm : ThemedForm
{
    private readonly TextBox _summary = new()
    {
        Multiline = true,
        ReadOnly = true,
        ScrollBars = ScrollBars.Vertical,
        WordWrap = true,
        AccessibleName = "Zusammenfassung",
    };

    private readonly RoundedHost _summaryHost;
    private readonly SparkButton _copy = new(ButtonKind.Secondary, "Kopieren");
    private readonly TLabel _tasksHeading = new(TextRole.Heading, "Aufgaben");
    private readonly Panel _tasksPanel = new() { AutoScroll = true };
    private readonly List<TaskCheck> _checks = new();
    private readonly TLabel _status = new(TextRole.SmallMuted);
    private readonly SparkButton _toList = new(ButtonKind.Primary, "Ausgewählte auf die Liste");
    private readonly SparkButton _listPick = new(ButtonKind.Secondary);
    private readonly ContextMenuStrip _listMenu = new();
    private readonly SparkButton _remind;
    private readonly IReadOnlyList<ListRow> _lists;
    private ListRow? _list;
    private readonly SparkButton _remarkable = new(ButtonKind.Secondary, "Aufs reMarkable");
    private readonly SparkButton _close = new(ButtonKind.Secondary, "Schließen");
    private readonly Func<int[], string?, bool, Task<string>> _keep;
    private readonly bool _offerRemarkable;
    private readonly string _subtitle;
    private Rectangle _face;
    private Rectangle _title;
    private Rectangle _sub;
    private bool _busy;

    /// <param name="keep">Gewählte Aufgaben (Indizes), die Liste (null: als Erinnerung) und ob aufs reMarkable; gibt den
    /// Hinweis für die Statuszeile zurück.</param>
    public MeetingEndForm(MeetingResult result, TimeSpan duration, bool offerRemarkable, Func<int[], string?, bool, Task<string>> keep)
    {
        _keep = keep;
        _lists = result.Lists;
        _list = _lists.Count > 0 ? _lists[0] : null;
        _remind = new SparkButton(_list is null ? ButtonKind.Primary : ButtonKind.Secondary,
                                  _list is null ? "Ausgewählte als Erinnerung" : "Als Erinnerung");
        _offerRemarkable = offerRemarkable;
        _subtitle = string.Create(CultureInfo.InvariantCulture, $"Dauer {(int)duration.TotalMinutes} min")
                    + (result.Chars > 0 ? string.Create(CultureInfo.GetCultureInfo("de-DE"), $" · {result.Chars:N0} Zeichen mitgeschrieben") : "");
        Text = "Spark-Begleiter – Besprechung";
        ShowInTaskbar = true;
        MaximizeBox = false;
        MinimizeBox = true;
        StartPosition = FormStartPosition.Manual;
        KeyPreview = true;

        _summaryHost = new RoundedHost(_summary);
        string summary = result.Summary.Trim().Length > 0 ? result.Summary.Trim() : "(Der Spark hat keine Zusammenfassung geschickt.)";
        _summary.Text = summary.Replace("\r\n", "\n", StringComparison.Ordinal).Replace("\n", Environment.NewLine, StringComparison.Ordinal);

        Controls.AddRange(new Control[] { _summaryHost, _copy, _tasksHeading, _tasksPanel, _status, _toList, _listPick, _remind, _remarkable, _close });
        int tab = 0;
        _summaryHost.TabIndex = tab++;
        _copy.TabIndex = tab++;
        _tasksPanel.TabIndex = tab++;
        foreach (MeetingTask task in result.Tasks)
        {
            string label = task.Text + (task.Due is { } due ? " (bis " + due.ToLocalTime().ToString("ddd dd.MM. HH:mm", CultureInfo.GetCultureInfo("de-DE")) + ")" : "");
            var check = new TaskCheck(label) { TabIndex = _checks.Count };
            check.CheckedChanged += (_, _) => UpdateButtons();
            _checks.Add(check);
            _tasksPanel.Controls.Add(check);
        }

        if (_checks.Count == 0)
        {
            _tasksHeading.Text = "Aufgaben: keine erkannt";
        }

        _toList.TabIndex = tab++;
        _listPick.TabIndex = tab++;
        _remind.TabIndex = tab++;
        _remarkable.TabIndex = tab++;
        _toList.Visible = _listPick.Visible = _list is not null;
        foreach (ListRow l in _lists)
        {
            ListRow row = l;
            _listMenu.Items.Add(row.Icon + " " + row.Name, null, (_, _) =>
            {
                _list = row;
                ShowList();
            });
        }

        ShowList();
        _listPick.Click += (_, _) => _listMenu.Show(_listPick, new Point(0, _listPick.Height));
        Disposed += (_, _) => _listMenu.Dispose();
        _close.TabIndex = tab;
        _remarkable.Visible = offerRemarkable;
        _copy.Click += (_, _) =>
        {
            _status.Text = ClipboardHelper.TrySetText(_summary.Text, keepOutOfHistory: false)
                ? "Zusammenfassung kopiert."
                : "Die Zwischenablage ist gerade belegt – bitte noch einmal.";
            _status.Role = TextRole.SmallMuted;
            _status.ApplyTheme(DeviceDpi);
            LayoutContent();
        };
        _toList.Click += async (_, _) => await KeepAsync(remarkable: false, toList: true);
        _remind.Click += async (_, _) => await KeepAsync(remarkable: false, toList: false);
        _remarkable.Click += async (_, _) => await KeepAsync(remarkable: true, toList: false);
        _close.Click += (_, _) => Close();
        CancelButton = _close;
        UpdateButtons();

        Rectangle area = Screen.FromPoint(Cursor.Position).WorkingArea;
        int dpi = Dwm.DpiAt(Cursor.Position);
        int w = Math.Min(Draw.Scale(560, dpi), area.Width);
        int h = Math.Min(Draw.Scale(600, dpi), area.Height);
        Bounds = new Rectangle(area.Left + ((area.Width - w) / 2), area.Top + ((area.Height - h) / 2), w, h);
    }

    protected override void OnLoad(EventArgs e)
    {
        base.OnLoad(e);
        MinimumSize = new Size(S(420), S(420));
        ActiveControl = _close;
    }

    private void ShowList()
    {
        _listPick.Text = _list is null ? "" : "Liste: " + _list.Name + " ▾";
        _listPick.AccessibleName = _listPick.Text;
        if (IsHandleCreated)
        {
            LayoutContent();
        }
    }

    private void UpdateButtons()
    {
        bool any = _checks.Any(c => c.Checked);
        _toList.Enabled = !_busy && any;
        _listPick.Enabled = !_busy;
        _remind.Enabled = !_busy && any;
        _remarkable.Enabled = !_busy && _offerRemarkable;
        _close.Enabled = !_busy;
    }

    private async Task KeepAsync(bool remarkable, bool toList)
    {
        if (_busy)
        {
            return;
        }

        int[] selected = remarkable ? Array.Empty<int>() : _checks.Select((c, i) => (c.Checked, i)).Where(t => t.Checked).Select(t => t.i).ToArray();
        _busy = true;
        UpdateButtons();
        string? listId = toList ? _list?.Id : null;
        SetStatus(remarkable ? "Wird aufs reMarkable geschickt …" : listId is not null ? "Kommt auf die Liste …" : "Erinnerungen werden angelegt …", error: false);
        try
        {
            string text = await _keep(selected, listId, remarkable);
            if (!IsDisposed)
            {
                SetStatus(text, error: false);
                if (!remarkable)
                {
                    foreach (TaskCheck c in _checks.Where(c => c.Checked))
                    {
                        c.Checked = false; // schon auf der Liste bzw. als Erinnerung angelegt (der Spark legt keine doppelt an)
                    }
                }
            }
        }
        catch (SparkException ex)
        {
            if (!IsDisposed)
            {
                SetStatus(ex.Message, error: true);
            }
        }
        finally
        {
            _busy = false;
            if (!IsDisposed)
            {
                UpdateButtons();
            }
        }
    }

    private void SetStatus(string text, bool error)
    {
        _status.Text = text;
        _status.Role = error ? TextRole.Error : TextRole.SmallMuted;
        _status.ApplyTheme(DeviceDpi);
        if (IsHandleCreated)
        {
            LayoutContent();
        }
    }

    protected override void OnThemeApplied() => _tasksPanel.BackColor = P.Card;

    protected override void LayoutContent()
    {
        int pad = S(16);
        int w = ClientSize.Width;
        int h = ClientSize.Height;
        int inner = Math.Max(S(100), w - (2 * pad));
        int y = BarHeight + pad;
        int face = S(32);
        _face = new Rectangle(pad, y, face, face);
        int titleH = Draw.Measure("Ag", F(11f, FontStyle.Bold)).Height;
        int subH = Draw.Measure("Ag", F(8.5f)).Height;
        int top = y + Math.Max(0, (face - titleH - subH) / 2);
        _title = new Rectangle(pad + face + S(10), top, inner - face - S(10), titleH);
        _sub = new Rectangle(pad + face + S(10), top + titleH, inner - face - S(10), subH);
        y += face + S(12);

        // Fuß von unten
        Size close = _close.Preferred();
        int footY = h - pad - close.Height;
        _close.Bounds = new Rectangle(w - pad - close.Width, footY, close.Width, close.Height);
        int x = pad;
        Size remind = _remind.Preferred();
        _remind.Bounds = new Rectangle(x, footY, remind.Width, remind.Height);
        x = _remind.Right + S(8);
        if (_offerRemarkable)
        {
            Size rm = _remarkable.Preferred();
            _remarkable.Bounds = new Rectangle(x, footY, rm.Width, rm.Height);
        }

        if (_list is not null)
        {
            // eine Zeile darüber: „Ausgewählte auf die Liste“ und die Listenwahl
            Size toList = _toList.Preferred();
            footY -= toList.Height + S(8);
            _toList.Bounds = new Rectangle(pad, footY, toList.Width, toList.Height);
            Size pick = _listPick.Preferred();
            _listPick.Bounds = new Rectangle(_toList.Right + S(8), footY, Math.Min(pick.Width, Math.Max(S(60), w - pad - _toList.Right - S(8))), pick.Height);
        }

        int statusH = _status.Text.Length > 0 ? Draw.TextHeight(_status.Text, _status.Font, inner) : 0;
        int statusY = footY - S(8) - statusH;
        _status.Fit(pad, statusY, inner);

        // Aufgaben: so viel Platz wie nötig, höchstens 40 % der Höhe
        int listInner = inner - SystemInformation.VerticalScrollBarWidth;
        int listH = 0;
        foreach (TaskCheck c in _checks)
        {
            listH += c.Fit(0, 0, listInner) + S(6);
        }

        int available = statusY - S(8) - y;
        int summaryMin = S(120);
        int headingH = Draw.TextHeight(_tasksHeading.Text, _tasksHeading.Font, inner);
        int tasksH = Math.Min(listH, Math.Max(S(40), (int)(available * 0.4)));
        if (_checks.Count == 0)
        {
            tasksH = 0;
        }

        int summaryH = Math.Max(summaryMin, available - headingH - S(6) - tasksH - S(52) - S(14));
        Size copy = _copy.Preferred();
        _summaryHost.Bounds = new Rectangle(pad, y, inner, summaryH);
        y += summaryH + S(8);
        _copy.Bounds = new Rectangle(w - pad - copy.Width, y, copy.Width, copy.Height);
        y += copy.Height + S(10);
        _tasksHeading.Fit(pad, y, inner);
        y += headingH + S(6);
        _tasksPanel.Bounds = new Rectangle(pad, y, inner, Math.Max(0, tasksH));
        int cy = 0;
        foreach (TaskCheck c in _checks)
        {
            int ch = c.Fit(0, cy + _tasksPanel.AutoScrollPosition.Y, listInner);
            cy += ch + S(6);
        }
    }

    protected override void PaintContent(Graphics g)
    {
        Face.Draw(g, _face, P);
        Draw.Text(g, "Besprechung – Zusammenfassung", F(11f, FontStyle.Bold), _title, P.Fg);
        Draw.Text(g, _subtitle, F(8.5f), _sub, P.Muted);
    }
}
