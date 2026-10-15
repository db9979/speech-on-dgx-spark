"""Spark teilen, stage B2 (plan Raspberry-Pi split): the panel on another computer reaches the models on the DGX only
through the TLS-Tor (tlstor.py) with TLS 1.3 and exactly the certificate the pairing pinned (models.cert). Without
the pin, with another certificate or from another address nothing gets through; System One (/v1/systemone) goes the
same way as every other request. A tool's client (netguard) never gets this way, and the all-in-one install is
unchanged. The DGX is played by 127.0.0.2 with a fake service on 127.0.0.1; nothing depends on the time of day."""
import asyncio
import json
import os
import socket
import ssl
import tempfile
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import common  # noqa: E402
import httpx  # noqa: E402
import llm  # noqa: E402
import netguard  # noqa: E402
import systemone  # noqa: E402
import teilen  # noqa: E402
import tlstor  # noqa: E402
from tests.test_richtlinie import repo_file  # noqa: E402

DIR = tempfile.mkdtemp(dir=helpers.TMP)
CERT, KEY = os.path.join(DIR, "dgx.pem"), os.path.join(DIR, "dgx.key")
OTHER, OTHER_KEY = os.path.join(DIR, "other.pem"), os.path.join(DIR, "other.key")
tlstor.make_cert(CERT, KEY, ["dgx.test", "127.0.0.2"])
tlstor.make_cert(OTHER, OTHER_KEY, ["dgx.test"])
PEM, OTHER_PEM = open(CERT).read(), open(OTHER).read()
DGX = "127.0.0.2"
_real = socket.getaddrinfo


def _lookup(host, *a, **kw):
    return _real(DGX if host in ("dgx.test", b"dgx.test") else host, *a, **kw)


class Fake:
    """A plain HTTP service on 127.0.0.1: answers every request with JSON, notes path and key."""
    def __init__(self):
        self.got = []

    async def handle(self, r, w):
        head = await r.readuntil(b"\r\n\r\n")
        lines = head.decode().split("\r\n")
        hdr = {k.lower(): v.strip() for k, _, v in (x.partition(":") for x in lines[1:] if x)}
        body = await r.readexactly(int(hdr.get("content-length", "0") or 0))
        path = lines[0].split()[1]
        self.got.append((path, hdr.get("authorization", "")))
        out = {"answers": {"wichtig": {"noul": 0.9}}} if path.endswith("/systemone") else {"status": "ready",
                                                                                           "len": len(body)}
        data = json.dumps(out).encode()
        w.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "
                + str(len(data)).encode() + b"\r\n\r\n" + data)
        await w.drain()
        w.close()


def config(port, cert=PEM, host="dgx.test", tls_from=("127.0.0.1", DGX)):
    c = json.loads(json.dumps(common.load_config()))
    for sec in ("asr", "tts", "llm", "image"):
        c[sec]["enabled"] = sec == "llm"
    c["llm"]["port"] = port
    c["models"].update(host=host, cert=cert)
    c["api"].update(tls_listen=DGX, tls_from=list(tls_from))
    c["chat"]["llm_url"] = f"https://dgx.test:{port}/v1"
    return c


def run(case, **kw):
    """Starts the fake service and the door, writes the config, runs case(port, fake) in the same loop."""
    old = common.load_config()

    async def go():
        fake = Fake()
        srv = await asyncio.start_server(fake.handle, "127.0.0.1", 0)
        port = srv.sockets[0].getsockname()[1]
        cfg = config(port, **kw)
        helpers.write_config(cfg)
        doors = await tlstor.serve(cfg, CERT, KEY)
        try:
            return await case(port, fake)
        finally:
            for s in doors + [srv]:
                s.close()
    try:
        with mock.patch.object(socket, "getaddrinfo", _lookup):
            return asyncio.run(go())
    finally:
        helpers.write_config(old)


async def get(port, path="/health"):
    async with httpx.AsyncClient(timeout=5) as c:
        r = await c.get(f"https://dgx.test:{port}{path}")
        r.raise_for_status()
        return r.json()


class Door(unittest.TestCase):
    def test_with_the_pinned_certificate_it_gets_through(self):
        async def case(port, fake):
            self.assertEqual(common.model_url("llm", "/health"), f"https://dgx.test:{port}/health")
            self.assertEqual((await get(port))["status"], "ready")
            return fake.got
        self.assertEqual(run(case), [("/health", "")])

    def test_another_certificate_or_none_is_refused(self):
        async def case(port, fake):
            with self.assertRaises(httpx.ConnectError):
                await get(port)
            return fake.got
        self.assertEqual(run(case, cert=OTHER_PEM), [], "nothing reached the service")
        self.assertEqual(run(case, cert=""), [])
        self.assertEqual(run(case, cert="-----BEGIN CERTIFICATE-----\nkaputt\n-----END CERTIFICATE-----\n"), [])

    def test_only_the_panel_computer_is_let_in(self):
        async def case(port, fake):
            with self.assertRaises(httpx.HTTPError):
                await get(port)
            return fake.got
        self.assertEqual(run(case, tls_from=("192.168.178.20",)), [])
        self.assertEqual(run(case, tls_from=()), [])

    def test_tls_13_only(self):
        async def case(port, fake):
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
            ctx.maximum_version = ssl.TLSVersion.TLSv1_2
            with self.assertRaises((ssl.SSLError, OSError)):
                r, w = await asyncio.open_connection(DGX, port, ssl=ctx)
                w.close()
            return fake.got
        self.assertEqual(run(case), [])

    def test_system_one_goes_the_same_way(self):
        async def case(port, fake):
            ccfg = common.load_config()["chat"]
            self.assertTrue(llm.own_tor(ccfg))
            out = await systemone.ask(ccfg, "wichtig", "Betreff: Rechnung", {"wichtig": systemone.noul("Wichtig?")})
            self.assertAlmostEqual(out["wichtig"]["yes"], 0.9)
            return fake.got
        got = run(case)
        self.assertEqual([p for p, _ in got], ["/v1/systemone"])
        self.assertEqual(got[0][1], "Bearer sk-test", "the LLM-Tor on the DGX gets the API key")

        async def without_pin(port, fake):
            with self.assertRaises(systemone.Unavailable):
                await systemone.ask(common.load_config()["chat"], "wichtig", "x",
                                    {"wichtig": systemone.noul("Wichtig?")})
            return fake.got
        self.assertEqual(run(without_pin, cert=""), [])


class Clients(unittest.TestCase):
    def test_a_tool_never_gets_the_pinned_way(self):
        cfg = config(31006)
        with mock.patch.object(common, "load_config", return_value=cfg):
            self.assertIn("https://dgx.test", common.model_mounts(cfg))
            c = netguard.client(netguard.HOME)
            self.assertEqual(c._mounts, {}, "netguard brings its own transport")
            plain = httpx.AsyncClient(trust_env=False)
            self.assertEqual([str(p.host) for p in plain._mounts], ["dgx.test"])
            own = httpx.AsyncClient(verify=False, trust_env=False)
            self.assertEqual(own._mounts, {}, "a client with its own verify (Home Assistant) is left alone")
            sync = httpx.Client(trust_env=False)
            self.assertEqual([str(p.host) for p in sync._mounts], ["dgx.test"])
            for x in (plain, own, c):
                asyncio.run(x.aclose())
            sync.close()

    def test_all_in_one_is_unchanged(self):
        cfg = config(31006, host="127.0.0.1")
        with mock.patch.object(common, "load_config", return_value=cfg):
            self.assertIsNone(common.model_mounts(cfg))
            c = httpx.AsyncClient(trust_env=False)
            self.assertEqual(c._mounts, {})
            asyncio.run(c.aclose())

    def test_the_panel_can_not_move_the_models(self):
        import admin
        new = json.loads(json.dumps(common.load_config()))
        new["models"].update(host="192.168.178.99", cert=OTHER_PEM)
        new["api"].update(tls_listen="0.0.0.0", tls_from=["0.0.0.0"])
        admin.validate(new)
        old = common.load_config()
        self.assertEqual((new["models"], new["api"]["tls_listen"], new["api"]["tls_from"]),
                         (old["models"], old["api"]["tls_listen"], old["api"]["tls_from"]))


class Firewall(unittest.TestCase):
    """B3: the door's ports answer only the panel computer; the rules come from checked addresses only."""
    def cfg(self, listen="192.168.178.171", von=("192.168.178.20",)):
        c = json.loads(json.dumps(common.load_config()))
        c["llm"]["enabled"] = True
        for sec, port in (("asr", 31001), ("tts", 31002), ("llm", 31006)):
            c[sec]["port"] = port
        c["api"].update(tls_listen=listen, tls_from=list(von))
        return c

    def test_only_the_panel_computer(self):
        r = teilen.regeln(self.cfg(von=("192.168.178.20", "fd00::20")))
        ports = "{ 31001, 31002, 31006, 31007 }"
        self.assertIn('iif "lo" accept', r)
        self.assertIn("ip saddr { 192.168.178.20 } tcp dport " + ports + " accept", r)
        self.assertIn("ip6 saddr { fd00::20 } tcp dport " + ports + " accept", r)
        self.assertTrue(r.rstrip().endswith("tcp dport " + ports + " drop\n  }\n}"), r)
        self.assertEqual([x.strip() for x in r.splitlines() if x.endswith(" accept")][0], 'iif "lo" accept')
        self.assertEqual(sum(x.endswith(" accept") for x in r.splitlines()), 3, "lo, v4 and v6 only")

    def test_nothing_but_addresses(self):
        for listen, von in (("0.0.0.0", ["192.168.178.20"]), ("dgx", ["192.168.178.20"]),
                            ("192.168.178.171", []), ("192.168.178.171", ["0.0.0.0"]),
                            ("192.168.178.171", ["127.0.0.1"]), ("192.168.178.171", ["1.2.3.4; drop"]),
                            ("192.168.178.171", ["192.168.178.2%s" % i for i in range(5)]),
                            ("", ["192.168.178.20"])):
            with self.assertRaises(teilen.Fehler, msg=(listen, von)):
                teilen.regeln(self.cfg(listen, von))

    def test_fingerprint(self):
        fp = teilen.fingerabdruck(CERT)
        self.assertRegex(fp, r"^([0-9A-F]{2}:){31}[0-9A-F]{2}$")
        self.assertNotEqual(fp, teilen.fingerabdruck(OTHER))
        self.assertEqual(teilen.fingerabdruck(os.path.join(DIR, "fehlt.pem")), "")


class Ports(unittest.TestCase):
    def test_the_door_opens_only_what_is_installed(self):
        c = {"asr": {"enabled": True, "port": 31001}, "tts": {"enabled": True, "port": 31002},
             "llm": {"enabled": False, "port": 31006}, "image": {"enabled": True, "port": 31005}}
        self.assertEqual(tlstor.ports(c), [31001, 31002, 31005, 31007])

    def test_shut_without_an_address(self):
        cfg = config(31006)
        cfg["api"]["tls_listen"] = ""
        self.assertEqual(asyncio.run(tlstor.serve(cfg, CERT, KEY)), [])


if __name__ == "__main__":
    unittest.main()


class Kopplung(unittest.TestCase):
    """B6a: the pairing code. Only a panel computer that knows the code and sees the real certificate gets the keys;
    a wrong code three times, an old code or a man in the middle with his own certificate get nothing."""
    CFG = {"api": {"key": "sk-alt0123456789abcdef"}}

    def _dgx(self, code, cert=CERT, key=KEY, shown=None, cfg=None, uhr=None):
        """The model computer in a thread; shown: the certificate the handshake shows (a man in the middle)."""
        ctx = teilen._Ctx(cert, key)
        if shown:
            ctx.ctx = teilen._Ctx(*shown).ctx
        sock = teilen.lauschen(0, "127.0.0.1")
        out = {}

        def run():
            try:
                out["ok"] = teilen.warten(cfg or self.CFG, code, ctx, sock, **({"uhr": uhr} if uhr else {}))
            except teilen.Fehler as e:
                out["fehler"] = str(e)
            finally:
                sock.close()
        import threading
        t = threading.Thread(target=run, daemon=True)
        t.start()
        return sock.getsockname()[1], t, out

    def test_the_right_code_hands_over_keys_and_pin(self):
        port, t, out = self._dgx("ABCDEF")
        got = teilen.koppeln("127.0.0.1", port, "abc-def")
        t.join(10)
        self.assertEqual(got["pem"].strip(), PEM.strip())
        self.assertEqual(got["waerter_key"], out["ok"]["waerter_key"])
        self.assertEqual(len(bytes.fromhex(got["waerter_key"])), 32)
        self.assertEqual(got["api_key"], "sk-alt0123456789abcdef")
        self.assertEqual((out["ok"]["von"], out["ok"]["hier"]), ("127.0.0.1", "127.0.0.1"))
        self.assertEqual(common.pinned_context(got["pem"]).verify_mode, ssl.CERT_REQUIRED)

    def test_without_an_api_key_a_new_one(self):
        port, t, out = self._dgx("ABCDEF", cfg={"api": {"key": ""}})
        got = teilen.koppeln("127.0.0.1", port, "ABCDEF")
        t.join(10)
        self.assertRegex(got["api_key"], r"^sk-[0-9a-f]{48}$")
        self.assertEqual(out["ok"]["api_key"], got["api_key"])

    def test_three_wrong_codes_end_it(self):
        port, t, out = self._dgx("ABCDEF")
        for _ in range(teilen.CODE_TRIES):
            with self.assertRaises(teilen.Fehler) as e:
                teilen.koppeln("127.0.0.1", port, "ABCDEG")
            self.assertEqual(str(e.exception), "code")
        t.join(10)
        self.assertEqual(out, {"fehler": "abgelehnt"})
        with self.assertRaises(teilen.Fehler):       # nothing listens any more
            teilen.koppeln("127.0.0.1", port, "ABCDEF")

    def test_a_man_in_the_middle_gets_nothing(self):
        """He shows his own certificate: the proof the panel makes for it does not fit the real one."""
        port, t, out = self._dgx("ABCDEF", shown=(OTHER, OTHER_KEY))
        with self.assertRaises(teilen.Fehler) as e:
            teilen.koppeln("127.0.0.1", port, "ABCDEF")
        self.assertEqual(str(e.exception), "code")
        for _ in range(teilen.CODE_TRIES - 1):
            with self.assertRaises(teilen.Fehler):
                teilen.koppeln("127.0.0.1", port, "ABCDEF")
        t.join(10)
        self.assertEqual(out, {"fehler": "abgelehnt"})

    def test_an_old_code_is_gone(self):
        ticks = iter([0, teilen.CODE_SECS + 1])
        port, t, out = self._dgx("ABCDEF", uhr=lambda: next(ticks))
        t.join(10)
        self.assertEqual(out, {"fehler": "abgelaufen"})

    def test_a_changed_answer_is_refused(self):
        k = teilen.schluessel("ABCDEF", b"x")
        daten = {"waerter_key": "a" * 64, "api_key": "sk-123456789012345678"}
        mac = teilen.antwort_mac(k, "1" * 32, "2" * 32, daten)
        self.assertNotEqual(mac, teilen.antwort_mac(k, "1" * 32, "2" * 32, dict(daten, api_key="sk-other1234567890")))
        self.assertNotEqual(mac, teilen.antwort_mac(teilen.schluessel("ABCDEG", b"x"), "1" * 32, "2" * 32, daten))

    def test_code_shape_and_strength(self):
        self.assertEqual(teilen.code_lesen(" abc-def "), "ABCDEF")
        for bad in ("ABCDE", "ABCDE0", "ABCDEFG", "ABCDE1", ""):
            with self.assertRaises(teilen.Fehler):
                teilen.code_lesen(bad)
        self.assertEqual(len(teilen.CODE_ABC), 32)
        self.assertTrue(all(teilen.code_lesen(teilen.code_neu()) for _ in range(20)))
        self.assertGreaterEqual(teilen.SCRYPT["n"], 2 ** 15)
        self.assertLessEqual(teilen.CODE_SECS, 600)
        self.assertLessEqual(teilen.CODE_TRIES, 3)

    def test_the_shell_writes_only_checked_values(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "speech-spark.sh")) as f:
            sh = f.read()
        self.assertIn("code) teilen_code", sh)
        self.assertIn("koppeln) teilen_koppeln", sh)
        self.assertEqual(sh.count("chown --reference=\"$CONFIG\""), 1)     # one config writer (cfg_put)


class Installation(unittest.TestCase):
    """B6b: install.sh --mode api --teilen (the model computer) and --mode panel --modelle <host> (the panel computer).
    Read from the scripts; install.sh and uninstall.sh are not part of the app/-only copy (skipped there like
    test_richtlinie does), speech-spark.sh is."""

    def test_model_computer(self):
        sh = repo_file("install.sh")
        self.assertIn("""[ "$TEILEN" = 1 ] && jqi '.asr.host="127.0.0.1" | .tts.host="127.0.0.1" | .llm.host="127.0.0.1"'""", sh)
        self.assertIn('bash "$PREFIX/app/speech-spark.sh" teilen zertifikat', sh)
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "speech-spark.sh")) as f:
            cli = f.read()
        self.assertIn('-newkey ec -pkeyopt ec_paramgen_curve:prime256v1', cli)      # the one place for it
        self.assertIn('-keyout "$ETC/tls/tor-key.pem" -out "$ETC/tls/tor-cert.pem"', cli)
        self.assertNotIn("tor-key.pem\" -out", sh)
        self.assertIn("ConditionPathExists=$VAR/state/waerter.key", sh)
        self.assertIn('ExecStart=/usr/sbin/nft -f $(dirname "$ETC")/speech-spark-teilen.nft', sh)
        self.assertIn("restart_front tlstor", sh)
        self.assertIn("restart_front waerter", sh)
        self.assertEqual(os.path.basename(common.TOR_CERT), "tor-cert.pem")
        self.assertNotEqual(common.TOR_CERT, os.path.join(common.TLS_DIR, "cert.pem"), "the panel's certificate moves")

    def test_panel_computer(self):
        sh = repo_file("install.sh")
        self.assertIn("PANEL_ONLY=1; WITH_ASR=0; WITH_TTS=0; WITH_BILD=0; WITH_LLM=0; WITH_KOLIBRI=0; LLM_ON=0; DOWNLOAD=0", sh)
        self.assertIn("sys.version_info < (3, 11)", sh)
        self.assertIn("aarch64|x86_64", sh)
        # paired before any unit is written or started: the panel never talks to the models without the pin
        self.assertLess(sh.index("teilen koppeln \"$MODELLE_PICK\""), sh.index('say "systemd units"'))
        self.assertIn('die "the pairing needs the code', sh)
        # no GPU on the panel computer (V01.0.626: the Pi stopped at "nvidia-smi not found"), on the first install and
        # on every update (models.host from the pairing)
        self.assertLess(sh.index('[ -n "$MODELLE_PICK" ] && gpu_needed=0'), sh.index("command -v nvidia-smi"))
        self.assertIn('if [ "$gpu_needed" = 1 ]; then', sh)

    def test_panel_computer_talks_to_the_door_not_to_loopback(self):
        """V01.0.637: after the move tars -> Pi the chat still asked http://127.0.0.1:30001/v1 (qwen38 on tars); on a
        panel computer install.sh turns such an address into the model computer's LLM-Tor, as common.model_url does."""
        sh = repo_file("install.sh")
        i = sh.index('.chat.llm_url = "https://')
        self.assertLess(sh.index('teilen koppeln "$MODELLE_PICK"'), i, "after the pairing knows models.host")
        self.assertLess(i, sh.index('say "systemd units"'), "before the panel starts")
        block = sh[sh.rindex("\nif ", 0, i):sh.index("\nfi\n", i)]
        self.assertIn('. == "127.0.0.1" or . == "localhost" or . == "::1"\')" = false ]', block, "only on a panel computer")
        self.assertIn("127[.]0[.]0[.]1|localhost|[[]::1[]]", block, "only an address on this computer is changed")
        self.assertIn(":\\(.llm.port // 31006)/v1", block)
        self.assertIn('.chat.llm_key = ""', block, "the door takes api.key (llm.key)")
        cfg = {"models": {"host": "192.168.178.171"}, "llm": {"port": 31006}}
        self.assertEqual(common.model_url("llm", "/v1", cfg), "https://192.168.178.171:31006/v1")

    def test_speakers_address_moves_with_the_panel(self):
        """V01.0.638: after the move the speakers' address (chat.esp32_url) still named tars; on a panel computer
        install.sh puts this computer's IPv4 address in place of the model computer's, nothing else."""
        sh = repo_file("install.sh")
        i = sh.index(".chat.esp32_url |= sub(")
        self.assertLess(sh.index('teilen koppeln "$MODELLE_PICK"'), i)
        self.assertLess(i, sh.index('say "systemd units"'))
        block = sh[sh.rindex("\nif ", 0, i):sh.index("\nfi\n", i)]
        self.assertIn('test("^https?://" + ($h | gsub("[.]"; "[.]")) + "(:[0-9]+)?/?$")', block,
                      "only an address that names the model computer, the whole host, no path")
        self.assertIn("grep -m1 -E '^[0-9]+([.][0-9]+){3}$'", block)

    def test_cli_finds_the_sbin_tools_with_a_short_path(self):
        """V01.0.631: teilen.py starts "teilen umzug-einspielen" with PATH=/usr/bin:/bin; runuser is in /usr/sbin."""
        import subprocess
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "speech-spark.sh")) as f:
            cli = f.read()
        line = next(x for x in cli.splitlines() if x.startswith("export PATH="))
        self.assertLess(cli.index(line), cli.index("runuser -u"), "set before any use")
        got = subprocess.run(["/bin/bash", "-c", line + '; printf %s "$PATH"'], env={"PATH": "/usr/bin:/bin"},
                             stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10).stdout.split(":")
        self.assertEqual(got[:2], ["/usr/bin", "/bin"], "the caller's order stays first")
        self.assertIn("/usr/sbin", got)
        self.assertIn("/sbin", got)

    def test_uninstall_and_rules_place(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "speech-spark.sh")) as f:
            cli = f.read()
        self.assertNotIn('"$ETC/teilen.nft"', cli, "root never writes into the service user's $ETC")
        self.assertIn('rules="$(dirname "$ETC")/speech-spark-teilen.nft"', cli)
        un = repo_file("uninstall.sh")
        self.assertIn("tlstor waerter teilen-fw", un)
        self.assertIn("nft delete table inet speech_spark_teilen", un)
