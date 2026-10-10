using System.Buffers.Binary;
using System.Runtime.InteropServices;
using static SparkBegleiter.NativeMethods;

namespace SparkBegleiter;

/// <summary>
/// Aufnahme vom Standard-Mikrofon über waveIn (winmm): PCM 16 bit, mono, 16 kHz, höchstens 60 Sekunden.
/// Es nimmt immer nur ein Recorder gleichzeitig auf. Die Daten bleiben im Speicher und gehen nur an den Spark.
/// </summary>
internal sealed class Recorder : IDisposable
{
    public const int SampleRate = 16000;
    public const int BytesPerSecond = SampleRate * 2;
    public const int MaxSeconds = 60;
    private const int MaxBytes = MaxSeconds * BytesPerSecond;
    private const int MinBytes = BytesPerSecond * 3 / 10;
    private const int BufferBytes = BytesPerSecond / 10; // 100 ms je Puffer
    private const int BufferCount = 10;

    private static int _active;

    private readonly IntPtr _device;
    private readonly IntPtr[] _headers = new IntPtr[BufferCount];
    private readonly Queue<int> _queued = new();
    private readonly MemoryStream _pcm = new();
    private readonly SynchronizationContext? _context;
    private readonly CancellationTokenSource _stop = new();
    private readonly Task _loop;
    private readonly object _lock = new();
    private bool _limitRaised;
    private bool _closed;

    private Recorder(IntPtr device)
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

    /// <summary>Läuft gerade irgendeine Aufnahme?</summary>
    public static bool AnyActive => Volatile.Read(ref _active) != 0;

    /// <summary>Wird (im UI-Thread) ausgelöst, wenn 60 Sekunden erreicht sind.</summary>
    public event EventHandler? LimitReached;

    /// <summary>Bisher aufgenommene Zeit.</summary>
    public TimeSpan Elapsed
    {
        get
        {
            lock (_lock)
            {
                return TimeSpan.FromSeconds((double)_pcm.Length / BytesPerSecond);
            }
        }
    }

    /// <summary>Startet die Aufnahme. Bei Fehlern steht in <paramref name="error"/> ein deutscher Hinweis.</summary>
    public static Recorder? TryStart(out string error)
    {
        error = "";
        if (Interlocked.CompareExchange(ref _active, 1, 0) != 0)
        {
            error = "Es läuft schon eine Aufnahme.";
            return null;
        }

        try
        {
            if (waveInGetNumDevs() == 0)
            {
                error = "Kein Mikrofon gefunden.";
                Volatile.Write(ref _active, 0);
                return null;
            }

            var format = new WAVEFORMATEX
            {
                wFormatTag = WAVE_FORMAT_PCM,
                nChannels = 1,
                nSamplesPerSec = SampleRate,
                nAvgBytesPerSec = BytesPerSecond,
                nBlockAlign = 2,
                wBitsPerSample = 16,
                cbSize = 0,
            };
            uint result = waveInOpen(out IntPtr device, WAVE_MAPPER, ref format, IntPtr.Zero, IntPtr.Zero, CALLBACK_NULL);
            if (result != MMSYSERR_NOERROR)
            {
                error = "Das Mikrofon lässt sich nicht öffnen (Fehler " + result.ToString(System.Globalization.CultureInfo.InvariantCulture)
                        + "). Ist es angeschlossen und unter Einstellungen → Datenschutz → Mikrofon für Desktop-Apps erlaubt?";
                Volatile.Write(ref _active, 0);
                return null;
            }

            var recorder = new Recorder(device);
            if (waveInStart(device) != MMSYSERR_NOERROR)
            {
                recorder.Dispose();
                error = "Die Aufnahme ließ sich nicht starten.";
                return null;
            }

            return recorder;
        }
        catch (DllNotFoundException)
        {
            error = "Aufnahme ist auf diesem Windows nicht verfügbar.";
            Volatile.Write(ref _active, 0);
            return null;
        }
    }

    /// <summary>Beendet die Aufnahme und gibt die WAV-Datei zurück (<c>null</c>, wenn sie zu kurz war).</summary>
    public async Task<byte[]?> StopAsync()
    {
        await StopLoopAsync();
        byte[] pcm;
        lock (_lock)
        {
            pcm = _pcm.ToArray();
        }

        Close();
        return pcm.Length < MinBytes ? null : ToWav(pcm);
    }

    /// <summary>Bricht ab und verwirft die Aufnahme.</summary>
    public void Dispose()
    {
        if (!_closed)
        {
            _stop.Cancel();
            try
            {
                _loop.Wait(1000);
            }
            catch (AggregateException)
            {
                // Schleife abgebrochen – egal.
            }

            Close();
        }

        _stop.Dispose();
        _pcm.Dispose();
    }

    private async Task StopLoopAsync()
    {
        await _stop.CancelAsync();
        try
        {
            await _loop;
        }
        catch (OperationCanceledException)
        {
            // erwartet
        }
    }

    private async Task LoopAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            Harvest(requeue: true);
            await Task.Delay(40, CancellationToken.None);
        }
    }

    /// <summary>Holt fertige Puffer in Aufnahme-Reihenfolge ab und reiht sie (bis zur Höchstlänge) wieder ein.</summary>
    private void Harvest(bool requeue)
    {
        uint size = (uint)Marshal.SizeOf<WAVEHDR>();
        lock (_lock)
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
                int take = (int)Math.Min(header.dwBytesRecorded, (uint)Math.Max(0, MaxBytes - _pcm.Length));
                if (take > 0)
                {
                    byte[] chunk = new byte[take];
                    Marshal.Copy(header.lpData, chunk, 0, take);
                    _pcm.Write(chunk, 0, take);
                }

                if (_pcm.Length >= MaxBytes)
                {
                    RaiseLimit();
                }
                else if (requeue)
                {
                    header.dwFlags &= ~WHDR_DONE;
                    header.dwBytesRecorded = 0;
                    Marshal.StructureToPtr(header, _headers[i], fDeleteOld: false);
                    if (waveInAddBuffer(_device, _headers[i], size) == MMSYSERR_NOERROR)
                    {
                        _queued.Enqueue(i);
                    }
                }
            }
        }
    }

    private void RaiseLimit()
    {
        if (_limitRaised)
        {
            return;
        }

        _limitRaised = true;
        if (_context is not null)
        {
            _context.Post(_ => LimitReached?.Invoke(this, EventArgs.Empty), null);
        }
        else
        {
            LimitReached?.Invoke(this, EventArgs.Empty);
        }
    }

    /// <summary>Gerät anhalten, letzte Puffer abholen, alles freigeben.</summary>
    private void Close()
    {
        if (_closed)
        {
            return;
        }

        _closed = true;
        _ = waveInReset(_device); // markiert alle wartenden Puffer als fertig
        Harvest(requeue: false);

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
        Volatile.Write(ref _active, 0);
    }

    /// <summary>PCM in eine WAV-Datei packen (44 Byte Kopf).</summary>
    private static byte[] ToWav(byte[] pcm)
    {
        byte[] wav = new byte[44 + pcm.Length];
        Span<byte> h = wav.AsSpan(0, 44);
        "RIFF"u8.CopyTo(h);
        BinaryPrimitives.WriteInt32LittleEndian(h[4..], 36 + pcm.Length);
        "WAVE"u8.CopyTo(h[8..]);
        "fmt "u8.CopyTo(h[12..]);
        BinaryPrimitives.WriteInt32LittleEndian(h[16..], 16);
        BinaryPrimitives.WriteInt16LittleEndian(h[20..], 1);          // PCM
        BinaryPrimitives.WriteInt16LittleEndian(h[22..], 1);          // mono
        BinaryPrimitives.WriteInt32LittleEndian(h[24..], SampleRate);
        BinaryPrimitives.WriteInt32LittleEndian(h[28..], BytesPerSecond);
        BinaryPrimitives.WriteInt16LittleEndian(h[32..], 2);          // Blockgröße
        BinaryPrimitives.WriteInt16LittleEndian(h[34..], 16);         // Bit
        "data"u8.CopyTo(h[36..]);
        BinaryPrimitives.WriteInt32LittleEndian(h[40..], pcm.Length);
        pcm.CopyTo(wav, 44);
        return wav;
    }
}
