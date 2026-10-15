"""Server-sent events to open pages and apps (one source for chats.py and verlauf.py): per key (a profile)
a few streams, each with its own queue on its own event loop. An event goes into every queue of the key; a full
queue drops its oldest event (the pages ask again now and then anyway). A stream ends after `seconds` or when
`alive()` turns false, sends a comment line every `beat` seconds so proxies keep a quiet stream open, and leaves
the list when it ends (also when the page goes away). Only fixed event dicts pass here, never texts."""
import asyncio
import json
import secrets
import threading
import time

from fastapi.responses import StreamingResponse


class Hub:
    def __init__(self, queue, most, beat=25):
        self.queue, self.most, self.beat = queue, most, beat   # events per stream, streams per key, keep-alive
        self.subs = {}             # key -> {stream id: (loop, queue)}
        self._lock = threading.Lock()

    def count(self):
        """Open streams (for the live view: only the number)."""
        with self._lock:
            return sum(len(x) for x in self.subs.values())

    def listening(self, key):
        with self._lock:
            return bool(self.subs.get(key))

    def send(self, key, ev):
        """Puts ev into every stream of key (from any thread)."""
        with self._lock:
            subs = list(self.subs.get(key, {}).values())
        for loop, q in subs:
            def put(q=q):
                if q.full():
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                q.put_nowait(ev)
            try:
                loop.call_soon_threadsafe(put)
            except RuntimeError:   # the stream's loop is gone
                pass

    def stream(self, key, alive, seconds, first=None):
        """The response for a new stream of key (call inside the request); `first()` gives events sent at once."""
        loop, q, sid = asyncio.get_running_loop(), asyncio.Queue(maxsize=self.queue), secrets.token_hex(6)
        with self._lock:
            mine = self.subs.setdefault(key, {})
            if len(mine) >= self.most:   # the oldest page gives way (it asks again now and then anyway)
                mine.pop(next(iter(mine)))
            mine[sid] = (loop, q)

        async def events():
            end_at = time.monotonic() + seconds
            try:
                yield "retry: 5000\n\n"
                for ev in (first() if first else ()):
                    yield f"data: {json.dumps(ev)}\n\n"
                while time.monotonic() < end_at and alive():
                    try:
                        ev = await asyncio.wait_for(q.get(), self.beat)
                    except asyncio.TimeoutError:
                        yield ": .\n\n"
                        continue
                    yield f"data: {json.dumps(ev)}\n\n"
            finally:
                with self._lock:
                    (self.subs.get(key) or {}).pop(sid, None)
                    if key in self.subs and not self.subs[key]:
                        self.subs.pop(key)
        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
