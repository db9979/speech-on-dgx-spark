using static SparkBegleiter.NativeMethods;

namespace SparkBegleiter;

/// <summary>
/// Schnell erfassen (Begleiter nachziehen 4a/8a, Strg+Alt+N): eine Zeile wie „Zahnarzt Fr 10 Uhr bei Dr. Weber“ oder
/// „Milch, Eier auf Einkauf“; der
/// Spark liest sie nach festen Regeln und zeigt, was er erkannt hat (Art, Tag und Uhrzeit, Ort) als Chips. Gespeichert
/// wird erst mit „Eintragen“, danach steht das Ergebnis mit „Rückgängig“ im Fenster (10 Minuten lang möglich, das
/// Fenster schließt nach 12 Sekunden). Markierter Text kommt als Zeile mit.
/// </summary>
internal sealed class CaptureForm : ThemedForm
{
    private const int MaxText = 200;

    private readonly TextBox _line = new() { MaxLength = MaxText, AccessibleName = "Was soll ich eintragen?" };
    private readonly RoundedHost _lineHost;
    private readonly TLabel _chips = new(TextRole.SmallMuted);
    private readonly TLabel _result = new(TextRole.Normal);
    private readonly SparkButton _termin = new(ButtonKind.Chip, "Termin");
    private readonly SparkButton _erinnerung = new(ButtonKind.Chip, "Erinnerung");
    private readonly SparkButton _liste = new(ButtonKind.Chip, "Liste");
    private readonly SparkButton _save = new(ButtonKind.Primary, "Eintragen");
    private readonly SparkButton _cancel = new(ButtonKind.Secondary, "Abbrechen");
    private readonly SparkButton _undo = new(ButtonKind.Secondary, "Rückgängig");
    private readonly System.Windows.Forms.Timer _wait = new() { Interval = 400 };
    private readonly System.Windows.Forms.Timer _closeTimer = new() { Interval = 12000 };
    private readonly Func<string, string, Task<CapturePreview>> _preview;
    private readonly Func<string, string, Task<(string Text, string? Undo)>> _store;
    private readonly Func<string, Task<string>> _takeBack;
    private string _kind = "";
    private string? _undoKey;
    private int _seq;
    private bool _busy;
    private Rectangle _titleBox;

    public CaptureForm(string line, Func<string, string, Task<CapturePreview>> preview,
        Func<string, string, Task<(string Text, string? Undo)>> store, Func<string, Task<string>> takeBack)
    {
        _preview = preview;
        _store = store;
        _takeBack = takeBack;
        _lineHost = new RoundedHost(_line);
        Text = "Spark-Begleiter – Schnell erfassen";
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        MinimizeBox = false;
        TopMost = true;
        ShowInTaskbar = true;
        StartPosition = FormStartPosition.CenterScreen;
        KeyPreview = true;
        _line.PlaceholderText = "z. B. Zahnarzt Fr 10 Uhr bei Dr. Weber";
        string clean = string.Concat(line.ReplaceLineEndings(" ").Where(c => !char.IsControl(c))).Trim();
        _line.Text = clean.Length > MaxText ? clean[..MaxText] : clean;
        _termin.Visible = _erinnerung.Visible = _liste.Visible = false;
        _undo.Visible = false;
        _result.Visible = false;
        Controls.AddRange(new Control[] { _lineHost, _chips, _termin, _erinnerung, _liste, _save, _cancel, _undo, _result });
        _line.TabIndex = 0;
        _termin.TabIndex = 1;
        _erinnerung.TabIndex = 2;
        _liste.TabIndex = 3;
        _save.TabIndex = 4;
        _cancel.TabIndex = 5;
        _line.TextChanged += (_, _) => Later();
        _line.KeyDown += (_, e) =>
        {
            if (e.KeyCode == Keys.Enter && e.Modifiers == Keys.None)
            {
                e.SuppressKeyPress = true;
                _ = SaveAsync();
            }
        };
        _termin.Click += (_, _) => Pick("termin");
        _erinnerung.Click += (_, _) => Pick("erinnerung");
        _liste.Click += (_, _) => Pick("liste");
        _save.Click += async (_, _) => await SaveAsync();
        _cancel.Click += (_, _) => Close();
        _undo.Click += async (_, _) => await UndoAsync();
        CancelButton = _cancel;
        _wait.Tick += async (_, _) =>
        {
            _wait.Stop();
            await PreviewAsync();
        };
        _closeTimer.Tick += (_, _) => Close();
    }

    /// <summary>Zeigen und das Feld in den Vordergrund holen (auch aus einem anderen Programm heraus).</summary>
    public void Bring()
    {
        Show();
        Activate();
        _ = SetForegroundWindow(Handle);
        _line.Focus();
        _line.SelectionStart = _line.TextLength;
        if (_line.TextLength > 0)
        {
            _ = PreviewAsync();
        }
        else
        {
            Show(chips: "Termin oder Erinnerung, mit Tag, Uhrzeit und Ort.", error: false);
        }
    }

    private void Later()
    {
        _wait.Stop();
        _wait.Start();
    }

    private void Pick(string kind)
    {
        _kind = kind;
        _ = PreviewAsync();
    }

    private async Task PreviewAsync()
    {
        string text = _line.Text.Trim();
        int seq = ++_seq;
        if (text.Length == 0)
        {
            Show(chips: "Termin oder Erinnerung, mit Tag, Uhrzeit und Ort.", error: false);
            return;
        }

        try
        {
            CapturePreview p = await _preview(text, _kind);
            if (seq != _seq || IsDisposed)
            {
                return;
            }

            _kind = p.Kind;
            _termin.Visible = p.Kinds.Contains("termin");
            _erinnerung.Visible = p.Kinds.Contains("erinnerung");
            _liste.Visible = p.Kinds.Contains("liste");
            _termin.Checked = p.Kind == "termin";
            _erinnerung.Checked = p.Kind == "erinnerung";
            _liste.Checked = p.Kind == "liste";
            string what = p.Kind switch { "erinnerung" => "Erinnerung", "liste" => "Liste", _ => "Termin" };
            Show(chips: $"{what}: {p.Title}" + (p.Chips.Count > 0 ? " · " + string.Join(" · ", p.Chips) : ""), error: false);
        }
        catch (SparkException ex)
        {
            if (seq == _seq && !IsDisposed)
            {
                Show(chips: ex.Message, error: true);
            }
        }
    }

    private async Task SaveAsync()
    {
        string text = _line.Text.Trim();
        if (_busy || text.Length == 0 || _undoKey is not null)
        {
            return;
        }

        _busy = true;
        _save.Enabled = false;
        try
        {
            var (said, undo) = await _store(text, _kind);
            if (IsDisposed)
            {
                return;
            }

            _undoKey = undo;
            _result.Text = said;
            _result.Visible = true;
            _undo.Visible = undo is not null;
            _line.ReadOnly = true;
            _save.Visible = false;
            _cancel.Text = "Schließen";
            _closeTimer.Start();
            LayoutContent();
            (_undo.Visible ? _undo : _cancel).Focus();
        }
        catch (SparkException ex)
        {
            Show(chips: ex.Message, error: true);
            _save.Enabled = true;
        }
        finally
        {
            _busy = false;
        }
    }

    private async Task UndoAsync()
    {
        if (_undoKey is not { } key || _busy)
        {
            return;
        }

        _busy = true;
        _closeTimer.Stop();
        try
        {
            _result.Text = await _takeBack(key);
            _undoKey = null;
            _undo.Visible = false;
        }
        catch (SparkException ex)
        {
            _result.Text = ex.Message;
        }
        finally
        {
            _busy = false;
            if (!IsDisposed)
            {
                _closeTimer.Start();
                LayoutContent();
            }
        }
    }

    private void Show(string chips, bool error)
    {
        _chips.Text = chips;
        _chips.ForeColor = error ? Palette.Hex(0xE5484D) : P.Muted;
        if (IsHandleCreated)
        {
            LayoutContent();
            Invalidate();
        }
    }

    protected override void LayoutContent()
    {
        int pad = S(16);
        int w = S(440);
        int inner = w - (2 * pad);
        int y = BarHeight + pad;
        int th = Draw.Measure("Ag", F(11f, FontStyle.Bold)).Height;
        _titleBox = new Rectangle(pad, y, inner, th);
        y += th + S(10);
        _line.Font = F(10.5f);
        _lineHost.Bounds = new Rectangle(pad, y, inner, S(40));
        y += S(40) + S(8);
        y += _chips.Fit(pad, y, inner) + S(8);
        int x = pad;
        int ch = 0;
        foreach (SparkButton b in new[] { _termin, _erinnerung, _liste }.Where(b => b.Visible))
        {
            Size size = b.Preferred();
            b.Bounds = new Rectangle(x, y, size.Width, size.Height);
            x += size.Width + S(6);
            ch = Math.Max(ch, size.Height);
        }

        y += ch > 0 ? ch + S(10) : 0;
        if (_result.Visible)
        {
            y += _result.Fit(pad, y, inner) + S(10);
        }

        int right = w - pad;
        int bh = 0;
        foreach (SparkButton b in new[] { _save, _undo, _cancel }.Where(b => b.Visible))
        {
            Size size = b.Preferred();
            right -= size.Width;
            b.Bounds = new Rectangle(right, y, size.Width, size.Height);
            right -= S(8);
            bh = Math.Max(bh, size.Height);
        }

        y += bh + pad;
        ClientSize = new Size(w, y);
    }

    protected override void PaintContent(Graphics g)
    {
        Draw.Text(g, "Schnell erfassen", F(11f, FontStyle.Bold), _titleBox, P.Fg);
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            _wait.Dispose();
            _closeTimer.Dispose();
        }

        base.Dispose(disposing);
    }
}
