using System.Buffers.Binary;
using System.Runtime.InteropServices;
using static SparkBegleiter.NativeMethods;

namespace SparkBegleiter;

/// <summary>
/// Teil "meeting": nimmt Mikrofon (waveIn, 16 kHz mono) und – wenn möglich – den Systemton (WASAPI-Loopback des
/// Standard-Wiedergabegeräts) auf, mischt beides zu mono 16 kHz und gibt alle 30 Sekunden ein WAV-Stück über
/// <see cref="ChunkReady"/> heraus (im UI-Thread). Das Mikrofon gibt den Takt vor; fehlt Systemton (nichts läuft),
/// zählt er als Stille. Höchstens 3 Stunden. Alles bleibt im Speicher, nichts wird auf die Festplatte geschrieben.
/// </summary>
internal sealed class MeetingRecorder : IDisposable
{
    public const int ChunkSeconds = 30;
    public static readonly TimeSpan MaxDuration = TimeSpan.FromHours(3);

    private const int Rate = Recorder.SampleRate;
    private const int ChunkSamples = ChunkSeconds * Rate;
    private const int BufferBytes = Recorder.BytesPerSecond / 10;
    private const int BufferCount = 10;

    private readonly IntPtr _device;
    private readonly IntPtr[] _headers = new IntPtr[BufferCount];
    private readonly Queue<int> _queued = new();
    private readonly SynchronizationContext? _context;
    private readonly CancellationTokenSource _stop = new();
    private readonly Task _micLoop;
    private readonly LoopbackCapture? _loopback;
    private readonly object _lock = new();
    private readonly List<short> _chunk = new(ChunkSamples);
    private long _samples;
    private bool _closed;
    private bool _limitRaised;

    private MeetingRecorder(IntPtr device, bool withSystemSound)
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

        if (withSystemSound)
        {
            _loopback = LoopbackCapture.TryStart();
        }

        _micLoop = Task.Run(() => LoopAsync(_stop.Token));
    }

    /// <summary>Ein 30-Sekunden-Stück (WAV) ist fertig – im UI-Thread.</summary>
    public event EventHandler<byte[]>? ChunkReady;

    /// <summary>3 Stunden erreicht – im UI-Thread.</summary>
    public event EventHandler? LimitReached;

    /// <summary>Wird der Systemton mit aufgenommen?</summary>
    public bool HasSystemSound => _loopback is not null;

    public TimeSpan Elapsed => TimeSpan.FromSeconds((double)Interlocked.Read(ref _samples) / Rate);

    public static MeetingRecorder? TryStart(out string error)
    {
        error = "";
        if (MicSwitch.Closed)
        {
            error = MicSwitch.ClosedText;
            return null;
        }

        if (Recorder.AnyActive)
        {
            error = "Es läuft gerade ein Diktat. Erst beenden, dann die Besprechung starten.";
            return null;
        }

        try
        {
            if (waveInGetNumDevs() == 0)
            {
                error = "Kein Mikrofon gefunden.";
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
                error = "Das Mikrofon lässt sich nicht öffnen (Einstellungen → Datenschutz → Mikrofon für Desktop-Apps erlauben).";
                return null;
            }

            var recorder = new MeetingRecorder(device, withSystemSound: true);
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
            return null;
        }
    }

    /// <summary>Beenden; gibt das letzte (kürzere) Stück zurück, wenn es mindestens eine Sekunde lang ist.</summary>
    public async Task<byte[]?> StopAsync()
    {
        await _stop.CancelAsync();
        try
        {
            await _micLoop;
        }
        catch (OperationCanceledException)
        {
            // erwartet
        }

        Close();
        lock (_lock)
        {
            byte[]? last = _chunk.Count >= Rate ? ToWav(_chunk) : null;
            _chunk.Clear();
            return last;
        }
    }

    private async Task LoopAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            Harvest(requeue: true);
            await Task.Delay(40, CancellationToken.None).ConfigureAwait(false);
        }
    }

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
                int bytes = (int)header.dwBytesRecorded;
                if (bytes >= 2)
                {
                    byte[] raw = new byte[bytes];
                    Marshal.Copy(header.lpData, raw, 0, bytes);
                    Mix(raw);
                }

                if (requeue)
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

    /// <summary>Mikrofon-Stück plus gleich viel Systemton (falls da) addieren, in 30-s-Stücke teilen.</summary>
    private void Mix(byte[] raw)
    {
        int n = raw.Length / 2;
        float[] system = _loopback?.Take(n) ?? Array.Empty<float>();
        for (int i = 0; i < n; i++)
        {
            float mic = BinaryPrimitives.ReadInt16LittleEndian(raw.AsSpan(i * 2, 2)) / 32768f;
            float mixed = mic + (i < system.Length ? system[i] * 0.8f : 0f);
            mixed = Math.Clamp(mixed, -1f, 1f);
            _chunk.Add((short)Math.Round(mixed * 32767f));
            if (_chunk.Count >= ChunkSamples)
            {
                byte[] wav = ToWav(_chunk);
                _chunk.Clear();
                Post(() => ChunkReady?.Invoke(this, wav));
            }
        }

        long total = Interlocked.Add(ref _samples, n);
        if (!_limitRaised && total >= MaxDuration.TotalSeconds * Rate)
        {
            _limitRaised = true;
            Post(() => LimitReached?.Invoke(this, EventArgs.Empty));
        }
    }

    private static byte[] ToWav(List<short> samples)
    {
        byte[] pcm = new byte[samples.Count * 2];
        for (int i = 0; i < samples.Count; i++)
        {
            BinaryPrimitives.WriteInt16LittleEndian(pcm.AsSpan(i * 2, 2), samples[i]);
        }

        return Recorder.ToWav(pcm);
    }

    private void Post(Action action)
    {
        if (_context is not null)
        {
            _context.Post(_ => action(), null);
        }
        else
        {
            action();
        }
    }

    private void Close()
    {
        lock (_lock)
        {
            if (_closed)
            {
                return;
            }

            _ = waveInReset(_device); // markiert die wartenden Puffer als fertig
            Harvest(requeue: false);
            _closed = true;
            _loopback?.Dispose();
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
        }
    }

    public void Dispose()
    {
        if (!_closed)
        {
            _stop.Cancel();
            try
            {
                _micLoop.Wait(1000);
            }
            catch (AggregateException)
            {
                // egal
            }

            Close();
        }

        _stop.Dispose();
    }
}

/// <summary>
/// Systemton über WASAPI-Loopback (Standard-Wiedergabegerät, geteilter Modus), ohne Zusatzpaket über COM.
/// Das Mischformat (meist 32-bit float, 48 kHz, Stereo) wird auf mono 16 kHz heruntergerechnet und in einer
/// Warteschlange gesammelt, die <see cref="Take"/> leert.
/// </summary>
internal sealed class LoopbackCapture : IDisposable
{
    private const int MaxQueued = Recorder.SampleRate * 2; // höchstens 2 s Vorrat

    private readonly Queue<float> _queue = new();
    private readonly object _lock = new();
    private readonly CancellationTokenSource _stop = new();
    private Task? _loop;

    private LoopbackCapture()
    {
    }

    /// <summary>Startet die Loopback-Aufnahme; <c>null</c>, wenn es auf diesem PC nicht geht (dann nur Mikrofon).</summary>
    public static LoopbackCapture? TryStart()
    {
        var capture = new LoopbackCapture();
        var started = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        capture._loop = Task.Factory.StartNew(() => capture.Run(started), CancellationToken.None, TaskCreationOptions.LongRunning, TaskScheduler.Default);
        bool ok = started.Task.Wait(3000) && started.Task.Result;
        if (!ok)
        {
            capture.Dispose();
            return null;
        }

        return capture;
    }

    /// <summary>Bis zu <paramref name="count"/> Proben (mono 16 kHz, −1…1) entnehmen.</summary>
    public float[] Take(int count)
    {
        lock (_lock)
        {
            int n = Math.Min(count, _queue.Count);
            float[] samples = new float[n];
            for (int i = 0; i < n; i++)
            {
                samples[i] = _queue.Dequeue();
            }

            return samples;
        }
    }

    private void Run(TaskCompletionSource<bool> started)
    {
        IAudioClient? client = null;
        IAudioCaptureClient? capture = null;
        IntPtr mixFormat = IntPtr.Zero;
        bool running = false;
        try
        {
            var enumerator = (IMMDeviceEnumerator)new MMDeviceEnumeratorComObject();
            if (enumerator.GetDefaultAudioEndpoint(0 /* eRender */, 0 /* eConsole */, out IMMDevice device) != 0)
            {
                started.TrySetResult(false);
                return;
            }

            Guid audioClientId = typeof(IAudioClient).GUID;
            if (device.Activate(ref audioClientId, 0x17 /* CLSCTX_ALL */, IntPtr.Zero, out object clientObject) != 0)
            {
                started.TrySetResult(false);
                return;
            }

            client = (IAudioClient)clientObject;
            if (client.GetMixFormat(out mixFormat) != 0 || mixFormat == IntPtr.Zero)
            {
                started.TrySetResult(false);
                return;
            }

            if (!SampleFormat.TryRead(mixFormat, out SampleFormat format))
            {
                started.TrySetResult(false);
                return;
            }

            const int AUDCLNT_SHAREMODE_SHARED = 0;
            const int AUDCLNT_STREAMFLAGS_LOOPBACK = 0x00020000;
            if (client.Initialize(AUDCLNT_SHAREMODE_SHARED, AUDCLNT_STREAMFLAGS_LOOPBACK, 10_000_000, 0, mixFormat, IntPtr.Zero) != 0)
            {
                started.TrySetResult(false);
                return;
            }

            Guid captureId = typeof(IAudioCaptureClient).GUID;
            if (client.GetService(ref captureId, out object captureObject) != 0)
            {
                started.TrySetResult(false);
                return;
            }

            capture = (IAudioCaptureClient)captureObject;
            if (client.Start() != 0)
            {
                started.TrySetResult(false);
                return;
            }

            running = true;
            started.TrySetResult(true);
            var resampler = new Downsampler(format.Rate, Recorder.SampleRate);
            while (!_stop.IsCancellationRequested)
            {
                while (capture.GetNextPacketSize(out uint packet) == 0 && packet > 0)
                {
                    if (capture.GetBuffer(out IntPtr data, out uint frames, out uint flags, out _, out _) != 0)
                    {
                        break;
                    }

                    const uint AUDCLNT_BUFFERFLAGS_SILENT = 0x2;
                    var mono = new float[frames];
                    if ((flags & AUDCLNT_BUFFERFLAGS_SILENT) == 0 && data != IntPtr.Zero)
                    {
                        format.ToMono(data, (int)frames, mono);
                    }

                    _ = capture.ReleaseBuffer(frames);
                    Enqueue(resampler.Process(mono));
                }

                Thread.Sleep(20);
            }
        }
        catch (Exception ex) when (ex is COMException or InvalidCastException or ArgumentException or OutOfMemoryException)
        {
            started.TrySetResult(false);
        }
        finally
        {
            if (running)
            {
                _ = client?.Stop();
            }

            if (mixFormat != IntPtr.Zero)
            {
                Marshal.FreeCoTaskMem(mixFormat);
            }

            if (capture is not null)
            {
                _ = Marshal.ReleaseComObject(capture);
            }

            if (client is not null)
            {
                _ = Marshal.ReleaseComObject(client);
            }
        }
    }

    private void Enqueue(List<float> samples)
    {
        lock (_lock)
        {
            foreach (float s in samples)
            {
                _queue.Enqueue(s);
            }

            while (_queue.Count > MaxQueued)
            {
                _ = _queue.Dequeue();
            }
        }
    }

    public void Dispose()
    {
        _stop.Cancel();
        try
        {
            _loop?.Wait(1500);
        }
        catch (AggregateException)
        {
            // egal
        }

        _stop.Dispose();
    }

    /// <summary>Mischformat des Geräts: float32 oder PCM 16/24/32 bit, beliebig viele Kanäle.</summary>
    private readonly struct SampleFormat
    {
        private static readonly Guid FloatSubtype = new("00000003-0000-0010-8000-00aa00389b71");
        private static readonly Guid PcmSubtype = new("00000001-0000-0010-8000-00aa00389b71");

        private SampleFormat(int rate, int channels, int bits, bool isFloat, int blockAlign)
        {
            Rate = rate;
            Channels = channels;
            Bits = bits;
            IsFloat = isFloat;
            BlockAlign = blockAlign;
        }

        public int Rate { get; }

        public int Channels { get; }

        public int Bits { get; }

        public bool IsFloat { get; }

        public int BlockAlign { get; }

        public static bool TryRead(IntPtr ptr, out SampleFormat format)
        {
            format = default;
            ushort tag = (ushort)Marshal.ReadInt16(ptr, 0);
            int channels = (ushort)Marshal.ReadInt16(ptr, 2);
            int rate = Marshal.ReadInt32(ptr, 4);
            int blockAlign = (ushort)Marshal.ReadInt16(ptr, 12);
            int bits = (ushort)Marshal.ReadInt16(ptr, 14);
            bool isFloat;
            switch (tag)
            {
                case 3: // WAVE_FORMAT_IEEE_FLOAT
                    isFloat = true;
                    break;
                case 1: // WAVE_FORMAT_PCM
                    isFloat = false;
                    break;
                case 0xFFFE: // WAVE_FORMAT_EXTENSIBLE: SubFormat ab Byte 24
                    byte[] guid = new byte[16];
                    Marshal.Copy(ptr + 24, guid, 0, 16);
                    var sub = new Guid(guid);
                    if (sub == FloatSubtype)
                    {
                        isFloat = true;
                    }
                    else if (sub == PcmSubtype)
                    {
                        isFloat = false;
                    }
                    else
                    {
                        return false;
                    }

                    break;
                default:
                    return false;
            }

            if (channels <= 0 || rate < 8000 || blockAlign <= 0 || (isFloat && bits != 32) || (!isFloat && bits is not (16 or 24 or 32)))
            {
                return false;
            }

            format = new SampleFormat(rate, channels, bits, isFloat, blockAlign);
            return true;
        }

        /// <summary>Kanäle mitteln.</summary>
        public void ToMono(IntPtr data, int frames, float[] mono)
        {
            int bytesPerSample = Bits / 8;
            byte[] raw = new byte[frames * BlockAlign];
            Marshal.Copy(data, raw, 0, raw.Length);
            for (int f = 0; f < frames; f++)
            {
                float sum = 0;
                int frameStart = f * BlockAlign;
                for (int c = 0; c < Channels; c++)
                {
                    int o = frameStart + (c * bytesPerSample);
                    if (o + bytesPerSample > raw.Length)
                    {
                        break;
                    }

                    sum += IsFloat ? BinaryPrimitives.ReadSingleLittleEndian(raw.AsSpan(o, 4))
                        : Bits switch
                        {
                            16 => BinaryPrimitives.ReadInt16LittleEndian(raw.AsSpan(o, 2)) / 32768f,
                            24 => ((raw[o] << 8) | (raw[o + 1] << 16) | (raw[o + 2] << 24)) / 2147483648f,
                            _ => BinaryPrimitives.ReadInt32LittleEndian(raw.AsSpan(o, 4)) / 2147483648f,
                        };
                }

                mono[f] = sum / Channels;
            }
        }
    }

    /// <summary>Einfaches Herunterrechnen: Mittelwert über die Eingangsproben jeder Ausgangsprobe.</summary>
    private sealed class Downsampler
    {
        private readonly int _inRate;
        private readonly int _outRate;
        private long _phase;
        private float _sum;
        private int _count;
        private float _last;

        public Downsampler(int inRate, int outRate)
        {
            _inRate = inRate;
            _outRate = outRate;
        }

        public List<float> Process(float[] input)
        {
            var output = new List<float>((int)((long)input.Length * _outRate / _inRate) + 2);
            foreach (float x in input)
            {
                _sum += x;
                _count++;
                _phase += _outRate;
                while (_phase >= _inRate)
                {
                    _phase -= _inRate;
                    float value = _count > 0 ? _sum / _count : _last;
                    output.Add(value);
                    _last = value;
                    _sum = 0;
                    _count = 0;
                }
            }

            return output;
        }
    }

    // ---- COM-Schnittstellen von WASAPI (Reihenfolge der Methoden wie in mmdeviceapi.h / audioclient.h) ----

    [ComImport]
    [Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
    private class MMDeviceEnumeratorComObject
    {
    }

    [ComImport]
    [Guid("A95664D2-9614-4F35-A746-DE8DB63617E6")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IMMDeviceEnumerator
    {
        [PreserveSig]
        int EnumAudioEndpoints(int dataFlow, int stateMask, out IntPtr devices);

        [PreserveSig]
        int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice endpoint);
    }

    [ComImport]
    [Guid("D666063F-1587-4E43-81F1-B948E807363F")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IMMDevice
    {
        [PreserveSig]
        int Activate(ref Guid iid, int clsCtx, IntPtr activationParams, [MarshalAs(UnmanagedType.IUnknown)] out object instance);
    }

    [ComImport]
    [Guid("1CB9AD4C-DBFA-4c32-B178-C2F568A703B2")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IAudioClient
    {
        [PreserveSig]
        int Initialize(int shareMode, int streamFlags, long bufferDuration, long periodicity, IntPtr format, IntPtr audioSessionGuid);

        [PreserveSig]
        int GetBufferSize(out uint frames);

        [PreserveSig]
        int GetStreamLatency(out long latency);

        [PreserveSig]
        int GetCurrentPadding(out uint padding);

        [PreserveSig]
        int IsFormatSupported(int shareMode, IntPtr format, out IntPtr closestMatch);

        [PreserveSig]
        int GetMixFormat(out IntPtr format);

        [PreserveSig]
        int GetDevicePeriod(out long defaultPeriod, out long minimumPeriod);

        [PreserveSig]
        int Start();

        [PreserveSig]
        int Stop();

        [PreserveSig]
        int Reset();

        [PreserveSig]
        int SetEventHandle(IntPtr eventHandle);

        [PreserveSig]
        int GetService(ref Guid iid, [MarshalAs(UnmanagedType.IUnknown)] out object service);
    }

    [ComImport]
    [Guid("C8ADBD64-E71E-48a0-A4DE-185C395CD317")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IAudioCaptureClient
    {
        [PreserveSig]
        int GetBuffer(out IntPtr data, out uint frames, out uint flags, out ulong devicePosition, out ulong qpcPosition);

        [PreserveSig]
        int ReleaseBuffer(uint frames);

        [PreserveSig]
        int GetNextPacketSize(out uint frames);
    }
}
