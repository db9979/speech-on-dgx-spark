"""Docker-Tor: puts an engine in Docker on 127.0.0.1 (Dominik 2026-10-17: Docker only on tars, only for model engines).

The container has no network at all (`--network none`, modelle.docker_args): its vLLM answers only on a Unix socket in
its own folder (STATE/docker-modelle/<id>/sock/engine.sock). This door listens on 127.0.0.1:<port> and passes bytes
to that socket and back, so the measurement and later the LLM-Tor talk to it like to every other engine. It never
reads or changes a request. It runs as the panel's user in its own unit (speech-spark.sh mess_docker). Logs
("dockertor:" lines) carry only the port, counts and fixed words.

    python3 dockertor.py <port> <socket>
"""
import asyncio
import os
import sys

from tlstor import CONNECT, MAX_CONN, _pipe, _shut

_open = set()


def pruefe(port, sock):
    """The fixed rules: a port of this installation, a socket named engine.sock in a folder sock/ of a model under
    docker-modelle/. Raises ValueError."""
    if not 31000 <= int(port) <= 31099:
        raise ValueError("port")
    parts = os.path.normpath(sock).split(os.sep)
    if not os.path.isabs(sock) or len(parts) < 5 or parts[-2:] != ["sock", "engine.sock"] or parts[-4] != "docker-modelle":
        raise ValueError("socket")
    return int(port), sock


async def handle(sock, reader, writer):
    if len(_open) >= MAX_CONN:
        print(f"dockertor: zu viele verbindungen ({MAX_CONN})", flush=True)
        return _shut(writer)
    try:
        lr, lw = await asyncio.wait_for(asyncio.open_unix_connection(sock), CONNECT)
    except (OSError, asyncio.TimeoutError):
        return _shut(writer)        # the engine is still loading: the caller asks again
    me = asyncio.current_task()
    _open.add(me)
    try:
        await asyncio.gather(_pipe(reader, lw), _pipe(lr, writer))
    finally:
        _open.discard(me)


async def main(port, sock):
    server = await asyncio.start_server(lambda r, w: handle(sock, r, w), "127.0.0.1", port)
    print(f"dockertor: offen port {port}", flush=True)
    await server.serve_forever()


if __name__ == "__main__":
    try:
        p, s = pruefe(*sys.argv[1:3])
    except (TypeError, ValueError):
        print("dockertor: abgelehnt aufruf", flush=True)
        sys.exit(2)
    try:
        asyncio.run(main(p, s))
    except OSError:
        print("dockertor: start fehlgeschlagen", flush=True)
        sys.exit(1)
