using System.Buffers.Binary;
using System.Media;

namespace SparkBegleiter;

/// <summary>
/// Teil "speak": spielt die WAV-Datei vom Spark (16 bit PCM, ganze Datei im Speicher) über
/// <see cref="SoundPlayer"/> ab. Das Ende wird aus der Länge der Datei berechnet (SoundPlayer meldet es nicht);
/// dann kommt <see cref="Finished"/> im UI-Thread. Nichts wird auf die Festplatte geschrieben.
/// </summary>
internal sealed class SpeakPlayer : IDisposable
{
    private readonly SoundPlayer _player;
    private readonly MemoryStream _stream;
    private readonly System.Windows.Forms.Timer _timer = new();
    private bool _stopped;

    private SpeakPlayer(byte[] wav, TimeSpan duration)
    {
        _stream = new MemoryStream(wav, writable: false);
        _player = new SoundPlayer(_stream);
        Duration = duration;
        _timer.Interval = (int)Math.Clamp(duration.TotalMilliseconds + 400, 500, int.MaxValue);
        _timer.Tick += (_, _) => Stop();
    }

    /// <summary>Abspielen ist zu Ende (oder wurde gestoppt).</summary>
    public event EventHandler? Finished;

    public TimeSpan Duration { get; }

    /// <summary>Prüft die Datei und beginnt das Abspielen. <c>null</c> mit deutschem Hinweis, wenn es nicht geht.</summary>
    public static SpeakPlayer? TryPlay(byte[] wav, out string error)
    {
        error = "";
        if (!TryDuration(wav, out TimeSpan duration))
        {
            error = "Der Spark hat keine abspielbare WAV-Datei geschickt.";
            return null;
        }

        var player = new SpeakPlayer(wav, duration);
        try
        {
            player._player.Load();
            player._player.Play();
            player._timer.Start();
            return player;
        }
        catch (Exception ex) when (ex is InvalidOperationException or TimeoutException or IOException)
        {
            player.Dispose();
            error = "Die Wiedergabe ließ sich nicht starten: " + ex.Message;
            return null;
        }
    }

    public void Stop()
    {
        if (_stopped)
        {
            return;
        }

        _stopped = true;
        _timer.Stop();
        try
        {
            _player.Stop();
        }
        catch (InvalidOperationException)
        {
            // schon still
        }

        Finished?.Invoke(this, EventArgs.Empty);
    }

    /// <summary>Länge einer PCM-WAV-Datei aus "fmt " (Bytes je Sekunde) und "data" (Größe).</summary>
    internal static bool TryDuration(byte[] wav, out TimeSpan duration)
    {
        duration = TimeSpan.Zero;
        if (wav.Length < 44 || !wav.AsSpan(0, 4).SequenceEqual("RIFF"u8) || !wav.AsSpan(8, 4).SequenceEqual("WAVE"u8))
        {
            return false;
        }

        int byteRate = 0;
        long dataSize = -1;
        long pos = 12;
        while (pos + 8 <= wav.Length)
        {
            ReadOnlySpan<byte> id = wav.AsSpan((int)pos, 4);
            long size = BinaryPrimitives.ReadUInt32LittleEndian(wav.AsSpan((int)pos + 4, 4));
            int body = (int)pos + 8;
            if (id.SequenceEqual("fmt "u8) && body + 16 <= wav.Length)
            {
                byteRate = BinaryPrimitives.ReadInt32LittleEndian(wav.AsSpan(body + 8, 4));
            }
            else if (id.SequenceEqual("data"u8))
            {
                // Manche Server schreiben beim Streamen 0 oder 0xFFFFFFFF – dann bis zum Dateiende.
                dataSize = size is 0 or 0xFFFFFFFF || body + size > wav.Length ? wav.Length - body : size;
                break;
            }

            pos = body + size + (size & 1);
        }

        if (byteRate <= 0 || dataSize <= 0)
        {
            return false;
        }

        duration = TimeSpan.FromSeconds((double)dataSize / byteRate);
        return true;
    }

    public void Dispose()
    {
        _timer.Stop();
        _timer.Dispose();
        try
        {
            _player.Stop();
        }
        catch (InvalidOperationException)
        {
            // egal
        }

        _player.Dispose();
        _stream.Dispose();
    }
}
