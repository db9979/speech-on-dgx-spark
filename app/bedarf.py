"""An engine that runs only on demand (Bilder malen: bild_server.py, Musik machen: musik_server.py): the service starts
it as its child process for the first job and ends it after some idle minutes, so it holds no memory while nobody
uses it (Dominik 2026-10-14 „3a“, 2026-10-16 „nur bei Benutzung laden“). One place for what both services share:
the child process, its states, the stop and the idle loop. Log lines carry only the service's word and fixed words.

One model at a time (Dominik 2026-10-18 „soll immer nur ein Model geladen sein, beide nicht gleichzeitig“, plan
plaene/schwere-auftraege.md 6a): before an engine starts, its service takes the lock STATE/bedarf.lock (flock, only
this machine, released by stop() or when the process ends); while another service holds it, claim() raises Belegt
and the service answers 503 "belegt". The panel's queue (panel/schwer.py) frees the place first, this lock holds
the rule even for a call that passes the panel by.
"""
import asyncio
import fcntl
import os
import subprocess
import time

import httpx

from common import STATE

LOCK = os.path.join(STATE, "bedarf.lock")


class Belegt(Exception):
    """Another model on demand holds the place (bedarf.lock)."""


class OnDemand:
    """The child engine of a service. state: off | starting | ready | error; busy while a job runs; used = the
    end of the last job (time.time)."""

    def __init__(self, word):
        self.word = word           # the log area of the service ("bild", "musik")
        self.proc = None
        self.state = "off"
        self.used = 0.0
        self.busy = False
        self.lock = asyncio.Lock()
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(30, connect=3))
        self.held = None           # the open lock file while this engine holds the one place

    def claim(self):
        """Takes the one place for the models on demand, or raises Belegt (another service holds it)."""
        if self.held is not None:
            return
        f = open(os.open(LOCK, os.O_WRONLY | os.O_CREAT, 0o600), "w")
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            f.close()
            print(f"{self.word}: engine nicht gestartet belegt", flush=True)
            raise Belegt()
        self.held = f

    def release(self):
        if self.held is not None:
            try:
                fcntl.flock(self.held, fcntl.LOCK_UN)
            finally:
                self.held.close()
                self.held = None

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def spawn(self, command, cwd):
        """Starts the engine: list arguments, no shell; its own output stays out of the journal (it would name
        prompts, captions or lyrics)."""
        self.proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, cwd=cwd, start_new_session=True)

    def stop(self, why):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(20)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(5)
            print(f"{self.word}: engine beendet {why}", flush=True)
        self.proc = None
        self.release()
        if self.state != "error" or why != "fehler":
            self.state = "off"

    def idle(self):
        """The engine is loaded and nothing runs or waits."""
        return self.state == "ready" and not self.busy and not self.lock.locked()


def idle_loop(engine, idle_min):
    """Starts the loop that ends the engine after idle_min() minutes without a job and notices when it died."""
    async def loop():
        while True:
            await asyncio.sleep(30)
            if engine.idle() and time.time() - engine.used > max(1, int(idle_min())) * 60:
                engine.stop("leerlauf")
            elif engine.state == "ready" and not engine.alive():
                engine.state = "error"
                print(f"{engine.word}: engine beendet code {engine.proc.returncode if engine.proc else -1}", flush=True)
    return asyncio.create_task(loop())
