"""Hält fest, welche Kopfzeilen SparkHilfe (Mac) beim Verbinden schickt (Selbsttest in CI, Pruefung/main.swift):
nimmt Verbindungen auf 127.0.0.1 an, bis eine eine HTTP-Anfrage bringt (die Probe „nc -z“ davor bringt nichts),
schreibt deren Kopfzeilen in die Datei und schließt. Nur stdlib."""
import socket
import sys

port, out = int(sys.argv[1]), sys.argv[2]
with socket.create_server(("127.0.0.1", port)) as srv:
    srv.settimeout(60)
    for _ in range(10):
        conn, _addr = srv.accept()
        conn.settimeout(10)
        data = b""
        try:
            while b"\r\n\r\n" not in data and len(data) < 16384:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
        except OSError:
            pass
        conn.close()
        if b"\r\n\r\n" in data:
            with open(out, "wb") as f:
                f.write(data.split(b"\r\n\r\n", 1)[0])
            break
