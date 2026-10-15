"""Pairing codes (Kopplung): the one-time code a profile's own browser login asks for, shown in the panel and
typed or scanned on the new device (iPhone app, Pebble watch, Schreibhilfe programs, Begleiter), which trades
it for its own device key.

One mechanic for all of them: the code comes from `secrets` (made by the caller's `make`), only its sha256 is
kept, in memory; it works once, for `seconds`, compared in constant time (hmac.compare_digest) and only for the
kind it was made for (`what`). A profile has at most `per_profile` open codes (a new one replaces the oldest), the
Spark at most `most` (then 429). The form check (`form`) runs before any lookup. Each caller keeps its own length,
alphabet, lifetime, limits, log lines and HTTP answers; the ESP32 activation, the Live monitor codes, the Android
download links and the invitations (join.py) work differently and keep their own code.
"""
import hashlib
import hmac
import re
import secrets
import threading
import time

from fastapi import HTTPException


LINK = re.compile(r"[A-Za-z0-9_\-]{20,40}")


def _hash(code):
    return hashlib.sha256(code.encode()).hexdigest()


def link_code():
    """A code that travels inside a link or a setup line, never typed: 144 random bits (iPhone, Pebble)."""
    return secrets.token_urlsafe(18)


def link_form(v):
    return v if isinstance(v, str) and LINK.fullmatch(v) else None


class Codes:
    """Open pairing codes of one module: sha256(code) -> {"uid", "t", "w"} in `pending`."""

    def __init__(self, make, form, seconds, most, per_profile, kind=""):
        self.make, self.form = make, form     # make() -> a new code; form(typed) -> the code or None
        self.kind = kind                      # the default `what`
        self.seconds, self.most, self.per_profile = seconds, most, per_profile
        self.pending = {}
        self._lock = threading.Lock()

    def _clean(self, now):
        for k in [k for k, v in self.pending.items() if now - v["t"] > self.seconds]:
            self.pending.pop(k, None)

    def new(self, uid, now=None, what=None):
        """A fresh code for the profile uid; only its hash stays here."""
        now, what = time.time() if now is None else now, self.kind if what is None else what
        code = self.make()
        with self._lock:
            self._clean(now)
            mine = sorted((v["t"], k) for k, v in self.pending.items() if v["uid"] == uid)
            for _, k in mine[:max(0, len(mine) - self.per_profile + 1)]:
                self.pending.pop(k, None)
            if len(self.pending) >= self.most:
                raise HTTPException(429, "Zu viele offene Kopplungen. Bitte in zehn Minuten noch einmal.")
            self.pending[_hash(code)] = {"uid": uid, "t": now, "w": what}
        return code

    def take(self, code, now=None, what=None):
        """The profile id the code was made for, once; None when malformed, unknown, used, expired or of another kind."""
        now, what = time.time() if now is None else now, self.kind if what is None else what
        code = self.form(code)
        if not code:
            return None
        h = _hash(code)
        with self._lock:
            self._clean(now)
            hit = next((k for k in self.pending if hmac.compare_digest(k, h) and self.pending[k]["w"] == what), None)
            return self.pending.pop(hit)["uid"] if hit else None
