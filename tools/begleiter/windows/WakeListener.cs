using System.Buffers.Binary;
using System.Runtime.InteropServices;
using static SparkBegleiter.NativeMethods;

namespace SparkBegleiter;

/// <summary>
/// Teil "wake": hört (nur solange der Teil an und nicht pausiert ist) am Standard-Mikrofon mit. Ein Pegel-Tor wie im
/// Browser (rms &gt; max(0,02; Grundrauschen × 3) für mindestens 80 ms) startet einen Satz; er endet nach 0,6 s Pause
/// (höchstens 5 s, mit 0,4 s Vorlauf) und geht als WAV (16 kHz, mono) über <see cref="SentenceReady"/> hinaus.
/// Nach dem Weckwort ohne Frage nimmt <see cref="ListenForQuestion"/> die Frage auf (bis zur Pause, höchstens 15 s).
/// Läuft gerade eine andere Aufnahme (Diktieren) oder wartet der Spark noch (<see cref="Busy"/>), werden die Daten
/// verworfen. Nichts wird gespeichert.
/// </summary>
internal sealed class WakeListener : IDisposable
{
    private const int Rate = Recorder.SampleRate;
    private const int FrameSamples = Rate / 50;           // 20 ms
    private const int FrameBytes = FrameSamples * 2;
    private const int StartFrames = 4;                     // 80 ms über dem Tor
    private const int PrerollFrames = 20;                  // 0,4 s
    private const int PauseFrames = 30;                    // 0,6 s
    private const int MaxSentenceFrames = 5 * 50;          // 5 s
    private const int MaxQuestionFrames = 15 * 50;         // 15 s
    private const int QuestionWaitFrames = 8 * 50;         // so lange auf den Anfang der Frage warten
    private const int BufferBytes = Recorder.BytesPerSecond / 10;
    private const int BufferCount = 10;

    private readonly IntPtr _device;
    private readonly IntPtr[] _headers = new IntPtr[BufferCount];
    private readonly Queue<int> _queued = new();
    private readonly SynchronizationContext? _context;
    private readonly CancellationTokenSource _stop = new();
    private readonly Task _loop;

    // Auswertung (nur im Hintergrund-Thread der Schleife)
    private readonly Queue<byte[]> _preroll = new();
    private readonly List<byte[]> _segment = new();
    private readonly List<byte> _pending = new();
    private double _noise = 0.005;
    private int _voicedRun;
    private int _silence;
    private int _waited;
    private bool _inSpeech;
    private volatile bool _question;
    private volatile bool _busy;
    private volatile bool _paused;
    private bool _closed;

    private WakeListener(IntPtr device)
    {
        _device = device;
        _context = SynchronizationContext.Current;
        uint size = (uint)Marshal.SizeOf<WAVEHDR>();
        for (int i = 0; i < BufferCount; i++)
        {
            var header = new WAVEHDR { lpData = Marshal.AllocHGlobal(BufferBytes), dwBufferLength = BufferBytes };
            _headers[i] = Marshal.AllocHGlobal((int)size);
            Marshal.StructureToPtr(header, _headers[i], fDeleteOld: false);
            if (waveInPrepareHeader(_device, _headers[i], size) == MMSYSERR_NOERROR &&
                waveInAddBuffer(_device, _headers[i], size) == MMSYSERR_NOERROR)
            {
                _queued.Enqueue(i);
            }
        }

        _loop = Task.Run(() => LoopAsync(_stop.Token));
    }

    /// <summary>Ein Satz ist fertig (WAV, ≤ 5 s) – im UI-Thread.</summary>
    public event EventHandler<byte[]>? SentenceReady;

    /// <summary>Die Frage nach dem Weckwort ist fertig (WAV) oder es kam nichts (<c>null</c>) – im UI-Thread.</summary>
    public event EventHandler<byte[]?>? QuestionReady;

    /// <summary>Solange der Spark an einem Satz arbeitet: alles verwerfen (höchstens ein /hear gleichzeitig).</summary>
    public bool Busy
    {
        get => _busy;
        set
        {
            _busy = value;
            if (value)
            {
                ResetRequested = true;
            }
        }
    }

    /// <summary>„Weckwort pausieren“: das Mikrofon bleibt offen, aber nichts wird ausgewertet.</summary>
    public bool Paused
    {
        get => _paused;
        set
        {
            _paused = value;
            ResetRequested = true;
        }
    }

    private volatile bool _resetRequested;

    private bool ResetRequested
    {
        get => _resetRequested;
        set => _resetRequested = value;
    }

    public static WakeListener? TryStart(out string error)
    {
        error = "";
        if (MicSwitch.Closed)
        {
            error = MicSwitch.ClosedText;
            return null;
        }

        try
        {
            if (waveInGetNumDevs() == 0)
            {
                error = "Weckwort: kein Mikrofon gefunden.";
                return null;
            }

            var format = new WAVEFORMATEX
            {
                wFormatTag = WAVE_FORMAT_PCM,
                nChannels = 1,
                nSamplesPerSec = Rate,
                nAvgBytesPerSec = Recorder.BytesPerSecond,
                nBlockAlign = 2,
                wBitsPerSample = 16,
                cbSize = 0,
            };
            if (waveInOpen(out IntPtr device, WAVE_MAPPER, ref format, IntPtr.Zero, IntPtr.Zero, CALLBACK_NULL) != MMSYSERR_NOERROR)
            {
                error = "Weckwort: das Mikrofon lässt sich nicht öffnen (Einstellungen → Datenschutz → Mikrofon für Desktop-Apps erlauben).";
                return null;
            }

            var listener = new WakeListener(device);
            if (waveInStart(device) != MMSYSERR_NOERROR)
            {
                listener.Dispose();
                error = "Weckwort: die Aufnahme ließ sich nicht starten.";
                return null;
            }

            return listener;
        }
        catch (DllNotFoundException)
        {
            error = "Aufnahme ist auf diesem Windows nicht verfügbar.";
            return null;
        }
    }

    /// <summary>Nach dem Weckwort: die nächste Äußerung als Frage aufnehmen (bis zur Pause, höchstens 15 s).</summary>
    public void ListenForQuestion()
    {
        _question = true;
        ResetRequested = true;
        _busy = false;
    }

    /// <summary>Frage abbrechen (Klick auf den Hinweis): wieder auf das Weckwort hören.</summary>
    public void CancelQuestion()
    {
        _question = false;
        ResetRequested = true;
        _busy = false;
    }

    private async Task LoopAsync(CancellationToken ct)
    {
        uint size = (uint)Marshal.SizeOf<WAVEHDR>();
        while (!ct.IsCancellationRequested)
        {
            while (_queued.Count > 0)
            {
                int i = _queued.Peek();
                var header = Marshal.PtrToStructure<WAVEHDR>(_headers[i]);
                if ((header.dwFlags & WHDR_DONE) == 0)
                {
                    break;
                }

                _queued.Dequeue();
                int take = (int)header.dwBytesRecorded;
                if (take > 0)
                {
                    byte[] chunk = new byte[take];
                    Marshal.Copy(header.lpData, chunk, 0, take);
                    Feed(chunk);
                }

                header.dwFlags &= ~WHDR_DONE;
                header.dwBytesRecorded = 0;
                Marshal.StructureToPtr(header, _headers[i], fDeleteOld: false);
                if (waveInAddBuffer(_device, _headers[i], size) == MMSYSERR_NOERROR)
                {
                    _queued.Enqueue(i);
                }
            }

            await Task.Delay(40, CancellationToken.None).ConfigureAwait(false);
        }
    }

    private void Feed(byte[] chunk)
    {
        if (ResetRequested)
        {
            ResetRequested = false;
            ResetSegment();
            _waited = 0;
        }

        // Während Diktat/Mikrofon-Knopf, Pause oder laufender Anfrage: verwerfen.
        if (_paused || _busy || Recorder.AnyActive)
        {
            _pending.Clear();
            if (_inSpeech || _preroll.Count > 0)
            {
                ResetSegment();
            }

            return;
        }

        _pending.AddRange(chunk);
        while (_pending.Count >= FrameBytes)
        {
            byte[] frame = _pending.GetRange(0, FrameBytes).ToArray();
            _pending.RemoveRange(0, FrameBytes);
            Frame(frame);
            if (_busy)
            {
                _pending.Clear();
                return;
            }
        }
    }

    private void Frame(byte[] frame)
    {
        double rms = Rms(frame);
        double gate = Math.Max(0.02, _noise * 3);
        bool voiced = rms > gate;

        if (!_inSpeech)
        {
            _preroll.Enqueue(frame);
            while (_preroll.Count > PrerollFrames)
            {
                _preroll.Dequeue();
            }

            if (voiced)
            {
                _voicedRun++;
            }
            else
            {
                _voicedRun = 0;
                _noise = Math.Clamp((_noise * 0.95) + (rms * 0.05), 0.001, 0.2);
            }

            if (_voicedRun >= StartFrames)
            {
                _inSpeech = true;
                _silence = 0;
                _segment.Clear();
                _segment.AddRange(_preroll);
                _preroll.Clear();
            }
            else if (_question && ++_waited > QuestionWaitFrames)
            {
                _question = false;
                _waited = 0;
                Post(() => QuestionReady?.Invoke(this, null));
            }

            return;
        }

        _segment.Add(frame);
        _silence = voiced ? 0 : _silence + 1;
        int max = _question ? MaxQuestionFrames : MaxSentenceFrames;
        if (_silence >= PauseFrames || _segment.Count >= max)
        {
            byte[] pcm = new byte[_segment.Count * FrameBytes];
            for (int i = 0; i < _segment.Count; i++)
            {
                Buffer.BlockCopy(_segment[i], 0, pcm, i * FrameBytes, FrameBytes);
            }

            bool question = _question;
            _question = false;
            _busy = true; // bis der Spark geantwortet hat
            ResetSegment();
            byte[] wav = Recorder.ToWav(pcm);
            Post(() =>
            {
                if (question)
                {
                    QuestionReady?.Invoke(this, wav);
                }
                else
                {
                    SentenceReady?.Invoke(this, wav);
                }
            });
        }
    }

    private void ResetSegment()
    {
        _inSpeech = false;
        _voicedRun = 0;
        _silence = 0;
        _segment.Clear();
        _preroll.Clear();
    }

    private static double Rms(byte[] frame)
    {
        int n = frame.Length / 2;
        double sum = 0;
        for (int i = 0; i < n; i++)
        {
            double v = BinaryPrimitives.ReadInt16LittleEndian(frame.AsSpan(i * 2, 2)) / 32768.0;
            sum += v * v;
        }

        return n == 0 ? 0 : Math.Sqrt(sum / n);
    }

    private void Post(Action action)
    {
        if (_closed)
        {
            return;
        }

        if (_context is not null)
        {
            _context.Post(_ =>
            {
                if (!_closed)
                {
                    action();
                }
            }, null);
        }
        else
        {
            action();
        }
    }

    public void Dispose()
    {
        if (_closed)
        {
            return;
        }

        _closed = true;
        _stop.Cancel();
        try
        {
            _loop.Wait(1000);
        }
        catch (AggregateException)
        {
            // egal
        }

        _ = waveInReset(_device);
        uint size = (uint)Marshal.SizeOf<WAVEHDR>();
        foreach (IntPtr ptr in _headers)
        {
            if (ptr == IntPtr.Zero)
            {
                continue;
            }

            var header = Marshal.PtrToStructure<WAVEHDR>(ptr);
            _ = waveInUnprepareHeader(_device, ptr, size);
            Marshal.FreeHGlobal(header.lpData);
            Marshal.FreeHGlobal(ptr);
        }

        _ = waveInClose(_device);
        _stop.Dispose();
    }
}
