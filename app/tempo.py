"""Speaking tempo for streamed speech: WSOLA time stretching that keeps the pitch.

vllm-omni applies `speed` only to complete (non-streamed) audio, so the proxy stretches streamed
PCM itself, chunk by chunk as it arrives.
"""
import numpy as np


class Stretcher:
    """Feed 16-bit mono PCM bytes, get stretched PCM bytes back; call flush() at the end."""

    def __init__(self, speed, rate=24000):
        self.speed = float(speed)
        self.n = int(rate * 0.03)              # 30 ms frames
        self.hs = self.n // 2                  # synthesis hop (50 % overlap)
        self.ha = self.hs * self.speed         # analysis hop
        self.tol = int(rate * 0.008)           # search +-8 ms for the best-matching frame
        self.win = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(self.n) / self.n)).astype(np.float32)
        self.x = np.zeros(0, np.float32)       # input not yet consumed
        self.off = 0                           # input index of self.x[0]
        self.pos = 0.0                         # ideal start of the next analysis frame
        self.prev = None                       # start of the last frame taken
        self.acc = np.zeros(self.n, np.float32)
        self.fed = self.out = 0
        self.rest = b""

    def _step(self, final=False):
        out = []
        while True:
            lo = max(0, int(round(self.pos)) - self.tol)
            need = int(round(self.pos)) + self.tol + self.n
            if self.prev is not None:
                need = max(need, self.prev + self.hs + self.n)
            if need > self.off + len(self.x):
                if not final or self.pos >= self.fed:
                    break
                self.x = np.concatenate([self.x, np.zeros(need - self.off - len(self.x), np.float32)])
            if self.prev is None:
                c = 0
            else:
                # the frame that continues the last one most naturally, near the ideal position
                target = self.x[self.prev + self.hs - self.off:self.prev + self.hs - self.off + self.n]
                region = self.x[lo - self.off:lo - self.off + 2 * self.tol + self.n]
                corr = np.correlate(region, target, mode="valid")
                energy = np.sqrt(np.convolve(region ** 2, np.ones(self.n, np.float32), mode="valid")) + 1e-6
                c = lo + int(np.argmax(corr / energy))
            self.acc += self.x[c - self.off:c - self.off + self.n] * self.win
            out.append(self.acc[:self.hs].copy())
            self.acc = np.concatenate([self.acc[self.hs:], np.zeros(self.hs, np.float32)])
            self.prev, self.pos = c, self.pos + self.ha
            keep = min(self.prev + self.hs, max(0, int(round(self.pos)) - self.tol))
            if keep > self.off:  # drop input no later frame can reach
                self.x, self.off = self.x[keep - self.off:], keep
        return np.concatenate(out) if out else np.zeros(0, np.float32)

    def _pcm(self, y, limit=None):
        if limit is not None:
            y = y[:max(0, limit - self.out)]
        self.out += len(y)
        return (np.clip(y, -1, 1) * 32767).astype("<i2").tobytes()

    def feed(self, data):
        if self.speed == 1.0:
            return data
        data = self.rest + data
        cut = len(data) - len(data) % 2
        data, self.rest = data[:cut], data[cut:]
        s = np.frombuffer(data, "<i2").astype(np.float32) / 32768
        self.x = np.concatenate([self.x, s])
        self.fed += len(s)
        return self._pcm(self._step())

    def flush(self):
        if self.speed == 1.0:
            return b""
        y = np.concatenate([self._step(final=True), self.acc[:self.n - self.hs]])
        return self._pcm(y, limit=int(round(self.fed / self.speed)))
