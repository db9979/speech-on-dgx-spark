"""Vorrat: a profile's sealed supply on the disk, the one way to keep what a service read for a profile so it answers
at once after a restart and when its source does not answer (first the Mail-Vorrat, mailvorrat.py; plan
vorrat-je-profil, Paket B, for the other services).

    USERS_DIR/<user id>/<name>   {"v": 1, "data": base64("G1" + nonce + AES-GCM(json))}

- In the profile's own folder (dateien.py registers each name): it goes with the profile, a copy of my data finds it.
- Sealed with AES-GCM (Sicherheits-Checkliste: new parts take an AEAD), its key derived from the Spark's secret key
  (vault.KEY_FILE, HKDF "speech-spark vorrat v1"), the profile and the name as associated data, so a file copied
  into another profile does not open. Without cryptography nothing is written, the memory alone; never plain text.
- Written at most every write_every seconds per profile (the SD card of the Pi); flush() writes the rest.
- sweep() deletes a file nobody wrote for idle_days: a service writes only while its profile uses it.
"""
import base64
import json
import os
import re
import threading
import time

from common import write_json
import profiles
import vault


_vkey = None      # the AES-GCM key (backup._forget_cached drops it after a restore)


def _key():
    global _vkey
    if _vkey:
        return _vkey
    if not vault.available():
        return None
    vault._key()   # makes the Spark's secret key when there is none yet
    try:
        with open(vault.KEY_FILE, "rb") as f:
            base = f.read().strip()
    except OSError:
        return None
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    _vkey = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"speech-spark vorrat v1").derive(base)
    return _vkey


def seal(data, ad):
    """bytes -> text: "G1" + nonce + AES-GCM, base64; None without a key."""
    k = _key()
    if not k:
        return None
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    return base64.b64encode(b"G1" + nonce + AESGCM(k).encrypt(nonce, data, ad.encode())).decode()


def unseal(text, ad):
    """The bytes, or None (other key, other profile, changed file)."""
    k = _key()
    try:
        raw = base64.b64decode(text or "", validate=True)
        if not k or raw[:2] != b"G1":
            return None
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.exceptions import InvalidTag
        try:
            return AESGCM(k).decrypt(raw[2:14], raw[14:], ad.encode())
        except InvalidTag:
            return None
    except ValueError:
        return None


class Vorrat:
    def __init__(self, name, idle_days, write_every=300, empty=dict):
        self.name, self.idle_days, self.write_every, self.empty = name, idle_days, write_every, empty
        self.mem = {}          # uid -> data
        self.dirty = {}        # uid -> True when changed since the last write
        self.written = {}      # uid -> when the file was written last
        self.lock = threading.RLock()

    def file(self, uid):
        return profiles._path(uid, self.name)

    def load(self, uid):
        """The profile's data (memory, else its sealed file, else empty()); never raises."""
        d = self.mem.get(uid)
        if d is not None:
            return d
        d = self.empty()
        try:
            with open(self.file(uid), encoding="utf-8") as f:
                got = json.loads(unseal(json.load(f).get("data", ""), f"{uid}/{self.name}") or b"null")
            if isinstance(got, dict):
                d.update(got)
        except (OSError, ValueError, AttributeError):
            pass
        self.mem[uid] = d
        return d

    def changed(self, uid, now=None, force=False):
        """The data of uid changed: written now when the last write is write_every seconds old (or force), else later."""
        now = time.time() if now is None else now
        if not force and now - self.written.get(uid, 0) < self.write_every:
            self.dirty[uid] = True
            return
        with self.lock:
            d = self.mem.get(uid)
            self.dirty.pop(uid, None)
            if d is None or not os.path.isdir(os.path.dirname(self.file(uid))):
                return
            sealed = seal(json.dumps(d, ensure_ascii=False, separators=(",", ":")).encode(), f"{uid}/{self.name}")
            if not sealed:   # no key: never in plain text
                return
            write_json(self.file(uid), {"v": 1, "data": sealed}, mode=0o600, dir_mode=0o700)
            self.written[uid] = now

    def flush(self, now=None):
        """Writes every changed profile. Returns how many."""
        n = 0
        for uid in list(self.dirty):
            self.changed(uid, now, force=True)
            n += 1
        return n

    def forget(self, uid):
        with self.lock:
            for d in (self.mem, self.dirty, self.written):
                d.pop(uid, None)
            try:
                os.remove(self.file(uid))
            except OSError:
                pass

    def sweep(self, now=None):
        """Files nobody wrote for idle_days go. Returns how many."""
        now = time.time() if now is None else now
        try:
            names = os.listdir(profiles.USERS_DIR)
        except OSError:
            return 0
        n = 0
        for uid in names:
            if not re.fullmatch(r"[\w-]{1,40}", uid) or uid in self.dirty:
                continue
            try:
                old = now - os.stat(self.file(uid)).st_mtime > self.idle_days * 86400
            except OSError:
                continue
            if old:
                self.forget(uid)
                n += 1
        return n

    def clear(self):
        """Memory only (tests)."""
        for d in (self.mem, self.dirty, self.written):
            d.clear()
