"""Telefon: the sound of a call (telefon.py). Codecs and sample rates, no network.

G.711 (PCMA, PCMU, 8 kHz) with tables through numpy; G.722 (16 kHz, "HD-Telefonie") as the sub-band ADPCM of
ITU-T G.722 at 64 kbit/s, written after the reference algorithm (blocks 1L-6H, QMF), because Python 3.13 has no
audioop any more and the Spark brings no foreign codec library. Resampling between 8, 16 and 24 kHz (the speech
output speaks at 24 kHz) through a short windowed-sinc filter.

Everything here is pure computing on bytes: 16-bit signed little-endian mono PCM in and out."""
import numpy as np

# ---------------------------------------------------------------- G.711
_SEG_AEND = (0x1F, 0x3F, 0x7F, 0xFF, 0x1FF, 0x3FF, 0x7FF, 0xFFF)


def _alaw_byte(pcm_val):
    pcm_val >>= 3
    if pcm_val >= 0:
        mask = 0xD5
    else:
        mask = 0x55
        pcm_val = -pcm_val - 1
    seg = next((i for i, end in enumerate(_SEG_AEND) if pcm_val <= end), 8)
    if seg >= 8:
        return 0x7F ^ mask
    aval = seg << 4
    aval |= ((pcm_val >> 1) if seg < 2 else (pcm_val >> seg)) & 0x0F
    return aval ^ mask


def _alaw_value(a):
    a ^= 0x55
    t = (a & 0x0F) << 4
    seg = (a & 0x70) >> 4
    if seg == 0:
        t += 8
    elif seg == 1:
        t += 0x108
    else:
        t = (t + 0x108) << (seg - 1)
    return t if a & 0x80 else -t


_BIAS, _CLIP = 0x84, 32635


def _ulaw_byte(pcm_val):
    sign = 0x80 if pcm_val < 0 else 0
    if sign:
        pcm_val = -pcm_val
    pcm_val = min(pcm_val, _CLIP) + _BIAS
    exp, mask = 7, 0x4000
    while exp > 0 and not pcm_val & mask:
        exp -= 1
        mask >>= 1
    mant = (pcm_val >> (exp + 3)) & 0x0F
    return ~(sign | (exp << 4) | mant) & 0xFF


def _ulaw_value(u):
    u = ~u & 0xFF
    t = (((u & 0x0F) << 3) + _BIAS) << ((u & 0x70) >> 4)
    return _BIAS - t if u & 0x80 else t - _BIAS


# lookup tables: 65536 entries for encoding (indexed by the sample as unsigned 16 bit), 256 for decoding
_A_ENC = np.array([_alaw_byte(v - 65536 if v > 32767 else v) for v in range(65536)], dtype=np.uint8)
_U_ENC = np.array([_ulaw_byte(v - 65536 if v > 32767 else v) for v in range(65536)], dtype=np.uint8)
_A_DEC = np.array([_alaw_value(b) for b in range(256)], dtype="<i2")
_U_DEC = np.array([_ulaw_value(b) for b in range(256)], dtype="<i2")


def _samples(pcm):
    return np.frombuffer(pcm[:len(pcm) // 2 * 2], dtype="<i2")


def alaw_encode(pcm: bytes) -> bytes:
    return _A_ENC[_samples(pcm).view(np.uint16)].tobytes()


def alaw_decode(data: bytes) -> bytes:
    return _A_DEC[np.frombuffer(data, dtype=np.uint8)].tobytes()


def ulaw_encode(pcm: bytes) -> bytes:
    return _U_ENC[_samples(pcm).view(np.uint16)].tobytes()


def ulaw_decode(data: bytes) -> bytes:
    return _U_DEC[np.frombuffer(data, dtype=np.uint8)].tobytes()


# ---------------------------------------------------------------- G.722 (64 kbit/s)
_Q6 = (0, 35, 72, 110, 150, 190, 233, 276, 323, 370, 422, 473, 530, 587, 650, 714, 786, 858, 940, 1023, 1121, 1219,
       1339, 1458, 1612, 1765, 1980, 2195, 2557, 2919, 0, 0)
_ILN = (0, 63, 62, 31, 30, 29, 28, 27, 26, 25, 24, 23, 22, 21, 20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8, 7,
        6, 5, 4, 0)
_ILP = (0, 61, 60, 59, 58, 57, 56, 55, 54, 53, 52, 51, 50, 49, 48, 47, 46, 45, 44, 43, 42, 41, 40, 39, 38, 37, 36,
        35, 34, 33, 32, 0)
_WL = (-60, -30, 58, 172, 334, 538, 1198, 3042)
_RL42 = (0, 7, 6, 5, 4, 3, 2, 1, 7, 6, 5, 4, 3, 2, 1, 0)
_ILB = (2048, 2093, 2139, 2186, 2233, 2282, 2332, 2383, 2435, 2489, 2543, 2599, 2656, 2714, 2774, 2834, 2896, 2960,
        3025, 3091, 3158, 3228, 3298, 3371, 3444, 3520, 3597, 3676, 3756, 3838, 3922, 4008)
_QM4 = (0, -20456, -12896, -8968, -6288, -4240, -2584, -1200, 20456, 12896, 8968, 6288, 4240, 2584, 1200, 0)
_QM2 = (-7408, -1616, 7408, 1616)
_QM6 = (-136, -136, -136, -136, -24808, -21904, -19008, -16704, -14984, -13512, -12280, -11192, -10232, -9360, -8576,
        -7856, -7192, -6576, -6000, -5456, -4944, -4464, -4008, -3576, -3168, -2776, -2400, -2032, -1688, -1360, -1040,
        -728, 24808, 21904, 19008, 16704, 14984, 13512, 12280, 11192, 10232, 9360, 8576, 7856, 7192, 6576, 6000, 5456,
        4944, 4464, 4008, 3576, 3168, 2776, 2400, 2032, 1688, 1360, 1040, 728, 432, 136, -432, -136)
_QMF = (3, -11, 12, 32, -210, 951, 3876, -805, 362, -156, 53, -11)
_IHN = (0, 1, 0)
_IHP = (0, 3, 2)
_WH = (0, -214, 798)
_RH2 = (2, 1, 2, 1)


def _sat(v):
    return 32767 if v > 32767 else -32768 if v < -32768 else v


class _Band:
    __slots__ = ("s", "sp", "sz", "r", "a", "p", "d", "b", "nb", "det")

    def __init__(self, det):
        self.s = self.sp = self.sz = 0
        self.r = [0, 0, 0]
        self.a = [0, 0, 0]
        self.p = [0, 0, 0]
        self.d = [0] * 7
        self.b = [0] * 7
        self.nb = 0
        self.det = det

    def update(self, dx):
        """Block 4 of G.722: reconstruction, pole and zero predictor update, the next estimate (the six zero taps
        written out: this runs twice per sample pair in pure Python, the loops cost more than the sums)."""
        d, b, r, p, a = self.d, self.b, self.r, self.p, self.a
        v = self.s + dx
        r0 = 32767 if v > 32767 else -32768 if v < -32768 else v
        v = self.sz + dx
        p0 = 32767 if v > 32767 else -32768 if v < -32768 else v
        sg0, sg1, sg2 = p0 >> 15, p[1] >> 15, p[2] >> 15
        a1, a2 = a[1], a[2]
        wd1 = a1 << 2
        wd1 = 32767 if wd1 > 32767 else -32768 if wd1 < -32768 else wd1
        wd2 = -wd1 if sg0 == sg1 else wd1
        if wd2 > 32767:
            wd2 = 32767
        wd3 = (128 if sg0 == sg2 else -128) + (wd2 >> 7) + ((a2 * 32512) >> 15)
        wd3 = 12288 if wd3 > 12288 else -12288 if wd3 < -12288 else wd3
        v = (192 if sg0 == sg1 else -192) + ((a1 * 32640) >> 15)
        ap1 = 32767 if v > 32767 else -32768 if v < -32768 else v
        lim = 15360 - wd3
        lim = 32767 if lim > 32767 else -32768 if lim < -32768 else lim
        ap1 = lim if ap1 > lim else -lim if ap1 < -lim else ap1
        self.p[0] = p0
        # zero predictor: b[i] follows the sign agreement of the new and the i-th old difference
        step = 0 if dx == 0 else 128
        s0 = dx >> 15
        d1, d2, d3, d4, d5, d6 = d[1], d[2], d[3], d[4], d[5], d[6]
        up, dn = (step, -step) if s0 == 0 else (-step, step)     # same sign as dx: +step, else -step
        v = (up if d1 >= 0 else dn) + ((b[1] * 32640) >> 15)
        b1 = 32767 if v > 32767 else -32768 if v < -32768 else v
        v = (up if d2 >= 0 else dn) + ((b[2] * 32640) >> 15)
        b2 = 32767 if v > 32767 else -32768 if v < -32768 else v
        v = (up if d3 >= 0 else dn) + ((b[3] * 32640) >> 15)
        b3 = 32767 if v > 32767 else -32768 if v < -32768 else v
        v = (up if d4 >= 0 else dn) + ((b[4] * 32640) >> 15)
        b4 = 32767 if v > 32767 else -32768 if v < -32768 else v
        v = (up if d5 >= 0 else dn) + ((b[5] * 32640) >> 15)
        b5 = 32767 if v > 32767 else -32768 if v < -32768 else v
        v = (up if d6 >= 0 else dn) + ((b[6] * 32640) >> 15)
        b6 = 32767 if v > 32767 else -32768 if v < -32768 else v
        b[1], b[2], b[3], b[4], b[5], b[6] = b1, b2, b3, b4, b5, b6
        d[0], d[1], d[2], d[3], d[4], d[5], d[6] = dx, dx, d1, d2, d3, d4, d5
        r[2], r[1], r[0] = r[1], r0, r0
        p[2], p[1] = p[1], p0
        a[1], a[2] = ap1, wd3
        v = r0 + r0
        t1 = 32767 if v > 32767 else -32768 if v < -32768 else v
        v = r[2] + r[2]
        t2 = 32767 if v > 32767 else -32768 if v < -32768 else v
        v = ((ap1 * t1) >> 15) + ((wd3 * t2) >> 15)
        sp = 32767 if v > 32767 else -32768 if v < -32768 else v
        # the differences are 16-bit values doubled: saturate each, then the six products
        sz = 0
        for di, bi in ((dx, b1), (d1, b2), (d2, b3), (d3, b4), (d4, b5), (d5, b6)):
            v = di + di
            sz += (bi * (32767 if v > 32767 else -32768 if v < -32768 else v)) >> 15
        sz = 32767 if sz > 32767 else -32768 if sz < -32768 else sz
        self.sp, self.sz = sp, sz
        v = sp + sz
        self.s = 32767 if v > 32767 else -32768 if v < -32768 else v


_QMF_A = np.array(_QMF, dtype=np.int64)
_QMF_B = _QMF_A[::-1].copy()


def _qmf(x, tail):
    """The QMF sums of every sample pair at once (numpy instead of 24 products per pair in Python): x is the kept
    history of 24 samples, tail the new samples; (sum over the even ones, sum over the odd ones) per pair and the
    new history. Exactly the integers of the loop in the standard."""
    xs = np.concatenate([np.array(x, dtype=np.int64), tail.astype(np.int64)])
    even, odd = xs[0::2], xs[1::2]
    return np.correlate(even[1:], _QMF_A, "valid"), np.correlate(odd[1:], _QMF_B, "valid"), xs[-24:].tolist()


def _scale(nb, base):
    wd1 = (nb >> 6) & 31
    wd2 = base - (nb >> 11)
    return ((_ILB[wd1] << -wd2) if wd2 < 0 else (_ILB[wd1] >> wd2)) << 2


class G722Encoder:
    """16 kHz PCM in, one byte per two samples out (64 kbit/s); keeps its state from frame to frame."""

    def __init__(self):
        self.low, self.high = _Band(32), _Band(8)
        self.x = [0] * 24

    def encode(self, pcm: bytes) -> bytes:
        amp = _samples(pcm)
        amp = amp[:len(amp) // 2 * 2]
        out = bytearray()
        if not len(amp):
            return bytes(out)
        sodd, seven, self.x = _qmf(self.x, amp)
        lows = ((seven + sodd) >> 14).tolist()
        highs = ((seven - sodd) >> 14).tolist()
        low, high = self.low, self.high
        for xlow, xhigh in zip(lows, highs):
            # low band: 6 bits
            el = _sat(xlow - low.s)
            wd = el if el >= 0 else -(el + 1)
            i = 1
            while i < 30 and wd >= (_Q6[i] * low.det) >> 12:
                i += 1
            ilow = _ILN[i] if el < 0 else _ILP[i]
            ril = ilow >> 2
            dlow = (low.det * _QM4[ril]) >> 15
            nb = ((low.nb * 127) >> 7) + _WL[_RL42[ril]]
            low.nb = 0 if nb < 0 else 18432 if nb > 18432 else nb
            low.det = _scale(low.nb, 8)
            low.update(dlow)
            # high band: 2 bits
            eh = _sat(xhigh - high.s)
            wd = eh if eh >= 0 else -(eh + 1)
            mih = 2 if wd >= (564 * high.det) >> 12 else 1
            ihigh = _IHN[mih] if eh < 0 else _IHP[mih]
            dhigh = (high.det * _QM2[ihigh]) >> 15
            nb = ((high.nb * 127) >> 7) + _WH[_RH2[ihigh]]
            high.nb = 0 if nb < 0 else 22528 if nb > 22528 else nb
            high.det = _scale(high.nb, 10)
            high.update(dhigh)
            out.append(((ihigh << 6) | ilow) & 0xFF)
        return bytes(out)


class G722Decoder:
    """One byte per two samples in, 16 kHz PCM out."""

    def __init__(self):
        self.low, self.high = _Band(32), _Band(8)
        self.x = [0] * 24

    def decode(self, data: bytes) -> bytes:
        rows = []
        low, high = self.low, self.high
        for code in data:
            wd1 = code & 0x3F
            ihigh = (code >> 6) & 0x03
            rlow = low.s + ((low.det * _QM6[wd1]) >> 15)
            rlow = 16383 if rlow > 16383 else -16384 if rlow < -16384 else rlow
            ril = wd1 >> 2
            dlowt = (low.det * _QM4[ril]) >> 15
            nb = ((low.nb * 127) >> 7) + _WL[_RL42[ril]]
            low.nb = 0 if nb < 0 else 18432 if nb > 18432 else nb
            low.det = _scale(low.nb, 8)
            low.update(dlowt)
            dhigh = (high.det * _QM2[ihigh]) >> 15
            rhigh = dhigh + high.s
            rhigh = 16383 if rhigh > 16383 else -16384 if rhigh < -16384 else rhigh
            nb = ((high.nb * 127) >> 7) + _WH[_RH2[ihigh]]
            high.nb = 0 if nb < 0 else 22528 if nb > 22528 else nb
            high.det = _scale(high.nb, 10)
            high.update(dhigh)
            rows.append(rlow + rhigh)
            rows.append(rlow - rhigh)
        if not rows:
            return b""
        xout2, xout1, self.x = _qmf(self.x, np.array(rows, dtype=np.int64))
        out = np.empty(2 * len(xout1), dtype=np.int64)
        out[0::2], out[1::2] = xout1 >> 11, xout2 >> 11
        return np.clip(out, -32768, 32767).astype("<i2").tobytes()


# ---------------------------------------------------------------- sample rates
def _kernel(up, down, taps=16):
    """Windowed-sinc low-pass for resampling by up/down (cut at the lower Nyquist frequency)."""
    cut = 0.5 / max(up, down) * 0.92
    n = np.arange(-taps * max(up, down), taps * max(up, down) + 1)
    h = 2 * cut * np.sinc(2 * cut * n) * np.kaiser(len(n), 7.0)
    return h * up / np.sum(h)


_KERNELS = {}


class Resampler:
    """Rate change by a small fraction (8000↔16000, 24000→16000 or 8000) that keeps its state between frames,
    so a stream cut into 20 ms pieces sounds the same as one long piece."""

    def __init__(self, rate_in, rate_out):
        g = int(np.gcd(rate_in, rate_out))
        self.up, self.down = rate_out // g, rate_in // g
        key = (self.up, self.down)
        if key not in _KERNELS:
            _KERNELS[key] = _kernel(self.up, self.down)
        self.h = _KERNELS[key]
        n = len(self.h) - 1
        self.buf = np.zeros(-(-n // self.up))   # input kept from before (zeros at the start: the filter's delay)
        self.k = n                                # index of the next output in the upsampled, filtered signal

    def feed(self, pcm: bytes) -> bytes:
        if self.up == self.down:
            return pcm[:len(pcm) // 2 * 2]
        buf = np.concatenate([self.buf, _samples(pcm).astype(np.float64)])
        u = np.zeros(len(buf) * self.up)
        u[::self.up] = buf
        y = np.convolve(u, self.h)
        ks = np.arange(self.k, len(buf) * self.up, self.down)
        out = y[ks]
        if len(ks):
            self.k = int(ks[-1]) + self.down
        drop = min(len(buf), max(0, (self.k - (len(self.h) - 1)) // self.up))
        self.buf = buf[drop:]
        self.k -= drop * self.up
        return np.clip(np.round(out), -32768, 32767).astype("<i2").tobytes()


# ---------------------------------------------------------------- codecs for the SDP
# payload type, name in the SDP, RTP clock rate, sample rate of the PCM, bytes per 20 ms
CODECS = {9: ("G722", 8000, 16000, 160), 8: ("PCMA", 8000, 8000, 160), 0: ("PCMU", 8000, 8000, 160)}
PREFER = (9, 8, 0)         # HD first (the speech recognition hears 16 kHz), then the two kinds of G.711


class Codec:
    """Encoder and decoder of one call's payload type, from and to 16 kHz PCM (what the speech recognition takes)."""

    def __init__(self, pt):
        if pt not in CODECS:
            raise ValueError("codec not supported")
        self.pt = pt
        self.name, self.clock, self.rate, self.frame = CODECS[pt]
        if pt == 9:
            self._enc, self._dec = G722Encoder(), G722Decoder()
        self.up = Resampler(self.rate, 16000)      # what is heard, to 16 kHz
        self.out = Resampler(24000, self.rate)     # the speech output's 24 kHz, to the call's rate

    def decode(self, payload: bytes) -> bytes:
        pcm = self._dec.decode(payload) if self.pt == 9 else alaw_decode(payload) if self.pt == 8 else ulaw_decode(payload)
        return self.up.feed(pcm)

    def encode(self, pcm: bytes) -> bytes:
        """PCM at the call's own rate (self.rate) to payload."""
        return self._enc.encode(pcm) if self.pt == 9 else alaw_encode(pcm) if self.pt == 8 else ulaw_encode(pcm)

    def samples_per_frame(self):
        return self.rate // 50     # 20 ms
