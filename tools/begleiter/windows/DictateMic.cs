namespace SparkBegleiter;

/// <summary>
/// Spracherkennung für ein Textfeld: der Spark erkennt die Aufnahme (Teil „Diktieren“), der Text
/// landet an der Schreibmarke. Nur Text, nie ein Befehl; nie für Codewort- oder Passwortfelder.
/// </summary>
internal sealed class Dictation
{
    private readonly Func<bool> _available;
    private readonly Func<byte[], CancellationToken, Task<string>> _run;

    public Dictation(Func<bool> available, Func<byte[], CancellationToken, Task<string>> run, Action<SparkException> report)
    {
        _available = available;
        _run = run;
        Report = report;
    }

    /// <summary>Diktieren ist im Panel an und der Begleiter gekoppelt.</summary>
    public bool Available => _available();

    public Action<SparkException> Report { get; }

    public Task<string> RunAsync(byte[] wav, CancellationToken ct) => _run(wav, ct);
}

/// <summary>Mikrofon-Knopf in einem <see cref="RoundedHost"/>; ein Klick startet, der zweite beendet die Aufnahme.</summary>
internal sealed class DictateMic : IDisposable
{
    private readonly Dictation _dictation;
    private readonly RoundedHost _host;
    private readonly TextBoxBase _box;
    private readonly Action<string, bool> _status;
    private readonly SparkButton _button = new(ButtonKind.Round) { Glyph = Glyph.Mic, AccessibleName = "Einsprechen", TabStop = false };
    private readonly System.Windows.Forms.Timer _timer = new() { Interval = 250 };
    private Recorder? _recorder;
    private CancellationTokenSource? _cts;
    private bool _disposed;

    public DictateMic(RoundedHost host, Dictation dictation, Action<string, bool> status)
    {
        if (host.Inner is not TextBoxBase box || box is TextBox { UseSystemPasswordChar: true } || box is TextBox { PasswordChar: not '\0' })
        {
            throw new ArgumentException("Nur für normale Textfelder.", nameof(host));
        }

        _host = host;
        _box = box;
        _dictation = dictation;
        _status = status;
        _button.AccessibleDescription = "Text für „" + (box.AccessibleName ?? "Feld") + "“ einsprechen";
        _button.Click += async (_, _) => await ToggleAsync();
        _timer.Tick += (_, _) => ShowElapsed();
        host.Accessory = _button;
        Refresh();
    }

    /// <summary>Gerade wird aufgenommen oder erkannt.</summary>
    public bool Busy => _recorder is not null || _cts is not null;

    /// <summary>Knopf nur zeigen, wenn Diktieren an ist und das Feld beschreibbar.</summary>
    public void Refresh()
    {
        bool show = _dictation.Available && !_box.ReadOnly && _box.Enabled;
        if (!show && _recorder is not null)
        {
            Cancel();
        }

        if (_button.Visible != show)
        {
            _button.Visible = show;
        }

        _button.Surface = _host.SoftBack ? Theme.Current.Soft : Theme.Current.Card;
    }

    private async Task ToggleAsync()
    {
        if (_disposed || _cts is not null)
        {
            return;
        }

        if (_recorder is null)
        {
            Recorder? recorder = Recorder.TryStart(out string error);
            if (recorder is null)
            {
                _status(error, true);
                return;
            }

            _recorder = recorder;
            recorder.LimitReached += async (_, _) =>
            {
                if (ReferenceEquals(_recorder, recorder))
                {
                    await ToggleAsync();
                }
            };
            _button.Checked = true;
            _button.AccessibleName = "Aufnahme beenden";
            _timer.Start();
            ShowElapsed();
            return;
        }

        Recorder current = _recorder;
        _recorder = null;
        _timer.Stop();
        _button.Checked = false;
        _button.AccessibleName = "Einsprechen";
        byte[]? wav;
        try
        {
            wav = await current.StopAsync();
        }
        finally
        {
            current.Dispose();
        }

        if (wav is null)
        {
            _status("Die Aufnahme war zu kurz.", true);
            return;
        }

        _status("Der Spark erkennt den Text …", false);
        _button.Enabled = false;
        _cts = new CancellationTokenSource();
        try
        {
            string text = (await _dictation.RunAsync(wav, _cts.Token)).Trim();
            if (_disposed || _box.IsDisposed)
            {
                return;
            }

            if (text.Length == 0)
            {
                _status("Es wurde nichts erkannt.", true);
            }
            else
            {
                Insert(text);
                _status("Erkannt – bitte prüfen.", false);
            }
        }
        catch (OperationCanceledException)
        {
            // Fenster wurde geschlossen.
        }
        catch (SparkException ex)
        {
            if (!_disposed)
            {
                _status(ex.Message, true);
            }

            _dictation.Report(ex);
        }
        finally
        {
            _cts?.Dispose();
            _cts = null;
            if (!_disposed)
            {
                _button.Enabled = true;
                _box.Focus();
            }
        }
    }

    /// <summary>Fügt den erkannten Text an der Schreibmarke ein, mit Leerzeichen davor und innerhalb der Höchstlänge.</summary>
    private void Insert(string text)
    {
        if (_box.ReadOnly)
        {
            return;
        }

        int start = Math.Clamp(_box.SelectionStart, 0, _box.TextLength);
        string before = _box.Text[..start];
        if (before.Length > 0 && !char.IsWhiteSpace(before[^1]))
        {
            text = " " + text;
        }

        int room = _box.MaxLength - (_box.TextLength - _box.SelectionLength);
        if (room <= 0)
        {
            _status("Das Feld ist voll.", true);
            return;
        }

        _box.SelectedText = text.Length > room ? text[..room] : text;
        _box.ScrollToCaret();
    }

    private void ShowElapsed()
    {
        if (_recorder is { } r)
        {
            TimeSpan t = r.Elapsed;
            _status(string.Create(System.Globalization.CultureInfo.InvariantCulture, $"Ich höre zu {(int)t.TotalMinutes}:{t.Seconds:00} … (höchstens {Recorder.MaxSeconds} s; ■ zum Beenden)"), false);
        }
    }

    private void Cancel()
    {
        _timer.Stop();
        _recorder?.Dispose();
        _recorder = null;
        _cts?.Cancel();
        _button.Checked = false;
        _button.AccessibleName = "Einsprechen";
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        Cancel();
        _timer.Dispose();
    }
}
