"""IT-Krisenspiel (krisenspiel.py, plan krisenspiel/plan.md, Paket 1): off by default and never for guests or a profile
the admin blocked, the scenarios consistent, the same seed and moves give the same game, every variant of every
scenario can be won on every level by the offered moves, the narrator never changes a value and its text is checked by fixed rules,
a stale move is refused, giving up counts as F, the own data can be deleted (also while blocked), Live shows numbers
only and the journal fixed words. No test depends on the clock: every game starts at a fixed time."""
import asyncio
import contextlib
import copy
import heapq
import io
import itertools
import json
import unittest
from unittest import mock

from tests import helpers
from tests.test_ui_browser import browser_ok

helpers.start()
import features  # noqa: E402
import krisenanleitung as KA  # noqa: E402
import krisenkonsole as C  # noqa: E402
import krisenlinux as L  # noqa: E402
import krisenspiel as K  # noqa: E402
import live  # noqa: E402
import panel  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
T0 = 1_800_000_000


def profile(name, pin="1234"):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def uid_of(name):
    return next(u["id"] for u in ADMIN.get("/api/admin/profiles").json()["users"] if u["name"] == name)


def quiet(fn, *a, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        r = fn(*a, **kw)
    return r, out.getvalue()


def _progress(st):
    goal = 0
    for g in K.SZENARIEN[st["szenario"]]["ziel"]:
        goal += sum(1 for f in g["flags"] if f in st["flags"]) if "flags" in g else int(K.holds(g, st))
    return 10 * goal + len(st["flags"])


def solve(st, limit=4000):
    """Best-first search over the offered moves (the seed's rolls depend on the move number, so it is in the key)."""
    n = itertools.count()
    heap, seen = [(0, 0, next(n), st)], set()
    while heap and limit:
        limit -= 1
        s = heapq.heappop(heap)[3]
        for a in K.available(s):
            if not a["frei"]:
                continue
            s2 = copy.deepcopy(s)
            quiet(K.move, s2, a["id"])
            if s2["ende"]:
                if s2["ende"]["art"] == "gewonnen":
                    return s2
                continue
            key = json.dumps([sorted(s2["flags"]), {k: v["status"] for k, v in s2["assets"].items()}, s2["uses"],
                              s2["zug"], s2["done"]], sort_keys=True)
            if key not in seen:
                seen.add(key)
                heapq.heappush(heap, (-_progress(s2), K.minutes_gone(s2), next(n), s2))
    return None


def seeds_for_variants(sid):
    """One seed for every combination of the scenario's variants."""
    sz, out = K.SZENARIEN[sid], {}
    total = 1
    for vals in sz.get("varianten", {}).values():
        total *= len(vals)
    for seed in range(5000):
        st = K.new_game(sid, "normal", seed, now=T0)
        out.setdefault(json.dumps(st["var"], sort_keys=True), seed)
        if len(out) == total:
            break
    assert len(out) == total, sid
    return sorted(out.values())


def typed(sid, aktion):
    """(host or None, a line) that the console turns into this move."""
    for e in C.world(sid)["befehle"] + C._DATA["allgemein"]:
        z = e.get("zug")
        if z == aktion or isinstance(z, list) and aktion in z:
            return e.get("host"), " ".join((["sudo"] if e["befehl"] in L.ROOT else []) + [e["befehl"]] + e.get("args", []))
    raise AssertionError((sid, aktion))


def con(st, line):
    """One typed line, quiet: the console's result."""
    return quiet(K.konsole_zeile, st, line)[0][1]


def finish(st, end):
    quiet(K.finish, st, end)


def path_of(won):
    return [x["steps"][0]["daten"]["aktion"] for x in won["trace"][1:]]


class Engine(unittest.TestCase):
    def test_the_scenarios_are_consistent(self):
        self.assertEqual(K.check_data(), [])
        self.assertEqual(set(K.SZENARIEN), {"ransomware", "san", "strom", "bgp", "bsi"})
        broken = copy.deepcopy(K._DATA)
        broken["szenarien"][0]["aktionen"][0]["setzt"] = {"gibtsnicht": "Online"}
        self.assertTrue(K.check_data(broken))

    def test_same_seed_same_game(self):
        for sid in K.SZENARIEN:
            a, b = K.new_game(sid, "normal", 4711, now=T0), K.new_game(sid, "normal", 4711, now=T0)
            for _ in range(6):
                offer = [x["id"] for x in K.available(a) if x["frei"]]
                if a["ende"] or not offer:
                    break
                quiet(K.move, a, offer[len(offer) // 2])
                quiet(K.move, b, offer[len(offer) // 2])
            for k in ("var", "m", "assets", "flags", "chronik", "done", "ende"):
                self.assertEqual(a[k], b[k], (sid, k))

    def test_every_variant_can_be_won(self):
        for sid in K.SZENARIEN:
            for seed in seeds_for_variants(sid):
                for stufe in K.STUFEN:
                    won = solve(K.new_game(sid, stufe, seed, now=T0))
                    self.assertIsNotNone(won, (sid, stufe, seed))
                self.assertIn(won["ende"]["note"], "ABCDE")

    def test_a_move_not_offered_and_a_finished_game(self):
        st = K.new_game("ransomware", "normal", 1, now=T0)
        with self.assertRaises(ValueError):
            K.move(st, "gibtsnicht")
        K.finish(st, "aufgegeben")
        self.assertEqual(st["ende"]["note"], "F")
        self.assertEqual(K.erfolge_neu(st, {}), [])        # given up is not played to the end: not even „Feuertaufe“
        with self.assertRaises(ValueError):
            K.move(st, "warten")

    def test_the_narration_is_checked(self):
        st = K.new_game("ransomware", "normal", 3, now=T0)
        facts, _ = quiet(K.move, st, "isolieren")
        f = K.facts_text(st, facts, "de")
        ok = "Im Rechenzentrum wird es still. Das Netzwerkteam trennt die Segmente, die Bildschirme flackern."
        self.assertEqual(K.check_story(ok, f), (ok, ""))
        for bad, why in (("Kurz.", "laenge"), (ok + " Mehr unter https://example.org bitte.", "format"),
                         ("- " + ok, "format"), (ok + " Der Schaden liegt bei 987654 Euro.", "zahl"),
                         (ok + " <b>Achtung</b> jetzt.", "format"), ("Eins. Zwei. Drei. Vier. Fünf. Sechs. Sieben. Acht.", "saetze")):
            self.assertEqual(K.check_story(bad, f)[1], why, bad)

    def test_the_end_and_the_achievements(self):
        won = solve(K.new_game("bgp", "normal", seeds_for_variants("bgp")[0], now=T0))
        d = {"spiel": won, "verlauf": [], "erfolge": {}, "stats": {}}
        quiet(K._book, d, T0)
        self.assertIn("feuertaufe", d["erfolge"])
        self.assertIn("gemeistert", d["erfolge"])
        self.assertEqual(d["stats"]["gewonnen"], 1)
        self.assertEqual(d["verlauf"][0]["note"], won["ende"]["note"])
        self.assertEqual(K.erfolge_neu(won, d), [])

    def test_console_lines_never_run(self):
        st = K.new_game("ransomware", "normal", 3, now=T0)
        bad = ["x; rm -rf /", "ls && reboot", "cat $(id)", "echo ${HOME}", "echo `id`", "a < b", "ls > a > b",
               "ls\nreboot", "ls & whoami", "%PATH%", "x" * 201, "cat \"unclosed", "ls | sh", "ls | bash -c id",
               "Get-WinEvent | Invoke-Expression", "ls | xargs rm"]
        def boom(*a, **kw):
            raise AssertionError("the console started something")
        with mock.patch("subprocess.Popen", boom), mock.patch("os.system", boom), mock.patch("os.popen", boom), \
                mock.patch("socket.socket", boom), mock.patch("builtins.exec", boom), mock.patch("builtins.eval", boom):
            for z in bad:
                r = con(st, z)
                self.assertIn(r["art"], ("abgelehnt",), z)
            for z in ("help", "hosts", "ssh dc01", "dir", "type C:/Windows/NTDS/notes.txt | grep -i SVC | head -n 1",
                      "ping fs01", "nslookup ex01", "Get-Service", "foo", "Get-WinEvent -LogName Security", "exit",
                      "sudo bash", "python -c 1", "curl http://x", "rm -rf /", "ping 1.2.3.4 > /etc/passwd"):
                quiet(K.konsole_zeile, st, z)
        self.assertEqual([x["s"] for x in st["konsole"]["zeilen"] if x["k"] == "err"][-4:],
                         ["foo: command not found", "sudo: a root shell is not simulated here; put sudo in front of each command",
                          "python: command not found", "bash: /etc/passwd: Permission denied"])
        self.assertIn("rm: refusing to remove '/' (the game keeps its system folders)", [x["s"] for x in st["konsole"]["zeilen"]])
        self.assertNotIn("/etc/passwd", st["konsole"].get("sim", {}).get("jump01", {}).get("neu", {}))
        self.assertIn("svc_backup: backup service account, member of Domain Admins (!)", [x["s"] for x in st["konsole"]["zeilen"]])
        self.assertIn("konto_gefunden", st["flags"])   # the typed Get-WinEvent was the move „logs“

    def test_typing_is_the_same_move_as_the_button(self):
        a, b = K.new_game("san", "normal", 11, now=T0), K.new_game("san", "normal", 11, now=T0, modus="konsole")
        quiet(K.move, a, "diagnose")
        quiet(K.konsole_zeile, b, "ssh san01")
        quiet(K.konsole_zeile, b, "controller show")
        for k in ("m", "assets", "flags", "zug"):
            self.assertEqual(a[k], b[k], k)
        self.assertEqual((a["knoepfe"], b["knoepfe"]), (1, 0))
        self.assertEqual(b["trace"][-1]["steps"][0]["daten"]["weg"], "konsole")

    def test_every_scenario_can_be_won_by_typing_only(self):
        for sid in K.SZENARIEN:
            seed = seeds_for_variants(sid)[0]
            moves = path_of(solve(K.new_game(sid, "normal", seed, now=T0)))
            st = K.new_game(sid, "normal", seed, now=T0, modus="konsole")
            for aktion in moves:
                host, line = typed(sid, aktion)
                if host:
                    quiet(K.konsole_zeile, st, "ssh " + host)
                r = con(st, line)
                self.assertEqual((r["art"], r["zug"]), ("zug", aktion), (sid, line))
            self.assertEqual(st["ende"]["art"], "gewonnen", sid)
            self.assertEqual(st["knoepfe"], 0)
            self.assertIn(["Nur Konsole: +5 Punkte.", "Console only: +5 points."], st["ende"]["gruende"])
            d = {"spiel": st, "verlauf": [], "erfolge": {}, "stats": {}}
            quiet(K._book, d, T0)
            self.assertIn("ohne_knopf", d["erfolge"])

    def test_a_wrong_target_costs_and_reading_takes_time(self):
        st = K.new_game("ransomware", "normal", 3, now=T0)
        quiet(K.konsole_zeile, st, "ssh hv01")
        before = st["m"]["kosten"]
        r = con(st, "Stop-VM erp01")
        self.assertEqual(r["art"], "falsch")
        self.assertEqual(st["assets"]["erp"]["status"], "Offline")
        self.assertGreater(st["m"]["kosten"], before + 15000)
        self.assertEqual(st["chronik"][-1]["text"][0][:12], "Falsche VM: ")
        turn, left = st["zug"], st["m"]["zeit"]
        for i in range(C.LESEN_MAX - 1):
            quiet(K.konsole_zeile, st, "ping fs01")
        self.assertEqual((st["zug"], st["konsole"]["min"]), (turn, C.LESEN_MAX - 1))
        quiet(K.konsole_zeile, st, "hosts")          # free
        quiet(K.konsole_zeile, st, "ping fs01")      # the tenth minute: a move of its own
        self.assertEqual((st["zug"], st["konsole"]["min"], st["m"]["zeit"]), (turn + 1, 0, left - C.LESEN_MAX))
        self.assertEqual(st["trace"][-1]["steps"][0]["daten"]["aktion"], "konsole_lesen")


class Linux(unittest.TestCase):
    """The Linux commands of the console (krisenlinux): simulated on the game's machines, never run."""

    def say(self, st, line):
        r = con(st, line)
        return r, [t for _, t in r["out"]]

    def test_root_where_linux_needs_it(self):
        st = K.new_game("ransomware", "normal", 3, now=T0)
        self.assertEqual(self.say(st, "whoami")[1], ["admin"])
        self.assertEqual(self.say(st, "sudo whoami")[1], ["root"])
        self.assertIn("Permission denied", self.say(st, "useradd bob")[1][0])
        self.assertEqual(self.say(st, "echo x > /etc/motd")[1], ["bash: /etc/motd: Permission denied"])
        self.assertEqual(self.say(st, "sudo useradd -m bob")[1], [])
        self.assertEqual(self.say(st, "grep ^bob /etc/passwd")[1], ["bob:x:1001:1001::/home/bob:/bin/bash"])
        self.assertIn("Permission denied", self.say(st, "iptables -L")[1][0])
        self.assertEqual(self.say(st, "sudo iptables -A INPUT -s 10.0.50.77 -j DROP")[1], [])
        self.assertIn("-s 10.0.50.77 -j DROP", " ".join(self.say(st, "sudo iptables -L")[1]))

    def test_a_stopped_service_hits_the_game_and_comes_back(self):
        st = K.new_game("ransomware", "normal", 1, now=T0)
        self.say(st, "ssh erp01")
        r, out = self.say(st, "systemctl stop postgresql")
        self.assertEqual((r["art"], st["assets"]["erp"]["status"]), ("lesen", "Online"))   # no root, no effect
        turn, cost = st["zug"], st["m"]["kosten"]
        r, _ = self.say(st, "sudo systemctl stop postgresql")
        self.assertEqual((r["art"], st["zug"], st["assets"]["erp"]["status"]), ("wirkung", turn + 1, "Degraded"))
        self.assertGreaterEqual(st["m"]["kosten"], cost + 2000)
        self.assertEqual(st["trace"][-1]["steps"][0]["daten"]["aktion"], "konsole_dienst")
        self.assertIn("inactive", " ".join(self.say(st, "systemctl status postgresql")[1]))
        r, _ = self.say(st, "sudo systemctl start postgresql")
        self.assertEqual((r["art"], st["assets"]["erp"]["status"]), ("wirkung", "Online"))
        r, _ = self.say(st, "sudo reboot")
        self.assertEqual((r["art"], st["trace"][-1]["steps"][0]["daten"]["aktion"]), ("wirkung", "konsole_neustart"))

    def test_editors_and_tab_data(self):
        """nano, vi and vim open a file in the page's editor; writing goes through the same rules as >."""
        st = K.new_game("bsi", "normal", 2, now=T0)
        self.assertIn("ein Dateiname fehlt", self.say(st, "nano")[1][0])
        self.assertIn("Is a directory", self.say(st, "vi /etc")[1][0])
        self.assertIn("No such file", self.say(st, "vim /gibts/nicht.txt")[1][0])
        r, out = self.say(st, "nano README.txt")
        self.assertEqual((r["editor"], r["art"], out), (True, "frei", []))
        e = C.tab_daten(st, K.holds)["editor"]
        self.assertEqual((e["art"], e["pfad"], e["schreiben"], e["neu"]), ("nano", "/home/admin/README.txt", True, False))
        self.assertEqual(L.save(C.ctx(st, K.holds), "eins\nzwei\n"), "")
        self.assertEqual(self.say(st, "cat README.txt")[1], ["eins", "zwei"])
        self.say(st, "vi /etc/hosts")
        self.assertFalse(C.tab_daten(st, K.holds)["editor"]["schreiben"])
        self.assertEqual(L.save(C.ctx(st, K.holds), "x"), "/etc/hosts: Permission denied")
        self.say(st, "sudo vim neu.txt")
        e = C.tab_daten(st, K.holds)["editor"]
        self.assertEqual((e["art"], e["neu"], e["root"], e["zeilen"]), ("vim", True, True, []))
        self.assertIn("200", L.save(C.ctx(st, K.holds), "x\n" * (L.LINE_MAX + 1)))
        self.assertEqual(L.save(C.ctx(st, K.holds), "x" * 500), "")
        self.assertEqual(len(self.say(st, "cat neu.txt")[1][0]), 200)
        d = C.tab_daten(st, K.holds)
        self.assertEqual(d["cwd"], "/home/admin")
        self.assertIn("/home/admin/neu.txt", d["pfade"])
        self.assertIn("/etc/", d["pfade"])
        self.say(st, "ssh dc01")                                       # a Windows machine: no paths, no editor
        self.assertEqual(C.tab_daten(st, K.holds), {"cwd": "", "pfade": [], "editor": None})

    def test_files_stay_and_travel(self):
        st = K.new_game("bsi", "normal", 2, now=T0)
        self.say(st, "echo eins > notiz.txt")
        self.say(st, "echo zwei >> notiz.txt")
        self.say(st, "mkdir -p fall/2026")
        self.say(st, "cp notiz.txt fall/2026/")
        self.assertEqual(self.say(st, "cat fall/2026/notiz.txt")[1], ["eins", "zwei"])
        self.assertEqual(self.say(st, "cat notiz.txt | grep -c e")[1], ["2"])
        self.say(st, "tar -czf fall.tgz fall")
        self.say(st, "rm -r fall")
        self.assertIn("No such file", self.say(st, "ls fall")[1][0])
        self.say(st, "tar -xzf fall.tgz")
        self.assertEqual(self.say(st, "cat fall/2026/notiz.txt")[1], ["eins", "zwei"])
        self.assertEqual(self.say(st, "scp notiz.txt siem01:/tmp/")[1][-1][:9], "notiz.txt")
        self.say(st, "ssh siem01")
        self.assertEqual(self.say(st, "cat /tmp/notiz.txt")[1], ["eins", "zwei"])
        self.say(st, "exit")
        self.assertEqual(self.say(st, "hostname")[1], ["jump01"])
        for i in range(L.SIM_MAX + 5):                # the game's disk is bounded
            r, out = self.say(st, f"touch f{i}")
        self.assertIn(L.VOLL[7:], out[0])
        self.assertLess(len(json.dumps(st)), 4 * L.SIM_BYTES)

    def test_every_command_has_its_help(self):
        st = K.new_game("ransomware", "normal", 3, now=T0)
        for host in ("jump01", "dc01"):
            st["konsole"]["host"] = host
            for name in sorted(set(L.LINUX) | set(C.BEFEHLE)):
                spec = C._spec(name)
                if not C._has(C._host("ransomware", host), spec[0]):
                    continue
                for h in ("--help", "/?") + (() if name in C.HFLAG else ("-h",)):
                    r, out = self.say(st, f"{name} {h}")
                    self.assertTrue(out and out[0].startswith(name + " - "), (host, name, h, out))
                    self.assertEqual(r["art"], "frei")
        st["konsole"]["host"] = "jump01"
        self.assertNotIn("df - ", self.say(st, "df -h")[1][0])
        self.assertEqual(self.say(st, "man tar")[1][0], "tar - Archiv packen oder auspacken")
        shown = " ".join(self.say(st, "help")[1])
        for name, spec in L.LINUX.items():
            self.assertIn(" " + name + " ", shown + " ", name)
        self.assertEqual(self.say(st, "pign fs01")[1], ["pign: command not found", "Meintest du: ping?"])
        self.assertEqual(con(st, "pign fs01")["art"], "unbekannt")

    def test_a_pattern_is_never_a_regular_expression(self):
        st = K.new_game("ransomware", "normal", 3, now=T0)
        self.assertEqual(self.say(st, "grep '.*' /etc/hostname")[1], [])
        self.assertEqual(self.say(st, "grep 'jump0[1]' /etc/hostname")[1], [])
        self.assertEqual(self.say(st, "grep ^jump /etc/hostname")[1], ["jump01"])
        self.assertEqual(self.say(st, "grep 01$ /etc/hostname")[1], ["jump01"])
        self.assertEqual(self.say(st, "find / -name 'host*'")[1], ["/etc/hostname", "/etc/hosts"])
        self.assertFalse({"re", "fnmatch", "glob"} & {getattr(v, "__name__", "") for v in vars(L).values()
                                                     if type(v) is type(json)})   # krisenlinux imports no pattern module
        with mock.patch("re.compile", side_effect=AssertionError("a pattern became a regular expression")), \
                mock.patch("re.search", side_effect=AssertionError), mock.patch("re.match", side_effect=AssertionError):
            for line in ("grep -r 'a(b|c)*' /etc", "sed 's/(a+)+$/x/g' /etc/hosts", "awk '{print $1}' /etc/hosts | sort -u",
                         "find / -name '*[a-z]*'"):
                self.say(st, line)

    def test_no_command_breaks_on_any_machine(self):
        for sid in K.SZENARIEN:
            st = K.new_game(sid, "normal", 3, now=T0)
            for h in C.world(sid)["hosts"]:
                for name in sorted(set(L.LINUX) | set(C.BEFEHLE)):
                    if name in ("ssh", "exit"):
                        continue
                    for a in ("", "-l /etc", "x y", "sudo"):
                        line = (f"sudo {name} x" if a == "sudo" else f"{name} {a}").strip()
                        if st["ende"]:
                            st = K.new_game(sid, "normal", 3, now=T0)
                        st["konsole"]["host"] = h["id"]
                        r = con(st, line)
                        self.assertLessEqual(len(r["out"]), C.AUSGABE_MAX + 1, line)
            json.dumps(st)


class Uhr(unittest.TestCase):
    """„Uhr läuft“: real seconds become game minutes by a fixed rule; the caller hands in the time, so no clock here."""

    def test_seconds_become_minutes_on_the_next_move(self):
        st = K.new_game("ransomware", "normal", 1, now=T0, uhr=True)
        self.assertIsNone(K.uhr_ticken(st, T0 + 35))
        self.assertEqual((st["uhr"]["offen"], st["uhr"]["rest"]), (3, 5.0))
        K.uhr_ticken(st, T0 + 5000)                      # a closed page: at most UHR_LUECKE seconds count
        self.assertEqual((st["uhr"]["offen"], st["uhr"]["rest"]), (9, 5.0))
        left = st["m"]["zeit"]
        quiet(K.move, st, "warten")
        step = st["trace"][-1]["steps"][1]["daten"]
        self.assertEqual((step["davon_uhr"], step["minuten"], st["uhr"]["offen"]), (9, 14, 0))
        self.assertEqual(st["m"]["zeit"], left - 14)
        self.assertEqual(K.new_game("ransomware", "normal", 1, now=T0)["uhr"], None)

    def test_pause_only_where_allowed_and_time_runs_out(self):
        st = K.new_game("san", "uebung", 2, now=T0, uhr=True)
        self.assertTrue(K.uhr_pause(st, True, T0 + 10))
        self.assertFalse(K.uhr_pause(st, True, T0 + 11))
        K.uhr_ticken(st, T0 + 50)
        self.assertEqual(st["uhr"]["offen"], 1)            # the ten seconds before the pause, none in it
        self.assertTrue(K.uhr_pause(st, False, T0 + 60))
        self.assertEqual(st["uhr"]["pausen"], 1)
        hard = K.new_game("san", "ernstfall", 2, now=T0, uhr=True)
        self.assertFalse(K.uhr_pause(hard, True, T0 + 1))
        now = T0
        while not hard["ende"]:
            now += K.UHR_POLL
            facts = K.uhr_ticken(hard, now)
        self.assertEqual((hard["ende"]["art"], hard["m"]["zeit"]), ("zeit", 0))
        self.assertEqual(hard["trace"][-1]["steps"][0]["daten"]["aktion"], "uhr")
        self.assertEqual(facts["texte"] if facts else None, facts and facts["texte"])
        self.assertEqual(round((now - T0) / K.UHR_S), K.STUFEN["ernstfall"]["zeit"])
        self.assertIsNone(K.uhr_ticken(hard, now + 100))

    def test_a_win_with_the_clock_counts_more(self):
        seed = seeds_for_variants("bgp")[0]
        moves = path_of(solve(K.new_game("bgp", "normal", seed, now=T0)))
        a, b = K.new_game("bgp", "normal", seed, now=T0), K.new_game("bgp", "normal", seed, now=T0, uhr=True)
        for x in moves:
            quiet(K.move, a, x)
            quiet(K.move, b, x)
        self.assertEqual((a["ende"]["art"], b["ende"]["art"]), ("gewonnen", "gewonnen"))
        self.assertEqual(b["ende"]["punkte"], min(100, a["ende"]["punkte"] + K.UHR_BONUS))
        self.assertIn(["Uhr lief: +5 Punkte.", "Clock running: +5 points."], b["ende"]["gruende"])
        self.assertIn("gegen_uhr", K.erfolge_neu(b, {}))
        self.assertNotIn("gegen_uhr", K.erfolge_neu(a, {}))
        b["uhr"]["pausen"] = 1
        self.assertNotIn("gegen_uhr", K.erfolge_neu(b, {}))


class Team(unittest.TestCase):
    """Team und Laufbahn (Paket 3): colleagues take moves over by fixed rules, the rank sets team and budget."""

    def test_every_technical_move_has_a_subject(self):
        for sid, sz in K.SZENARIEN.items():
            for a in K._all_actions(sz):
                f = K.fach(a)
                if a.get("rolle", "technik") == "leitung":
                    self.assertIsNone(f, a["id"])
                else:
                    self.assertIn(f, K.FAECHER, (sid, a["id"]))
        self.assertGreaterEqual(len(K._DATA["kollegen"]), K.RAENGE[-1][4])

    def test_the_rank_sets_team_and_budget(self):
        self.assertEqual([K.rang_of(w, a)[0] for w, a in ((0, False), (2, False), (5, False), (10, False), (10, True))],
                         ["junior", "admin", "itleiter", "itleiter", "ciso"])
        for r in K.RAENGE:
            st = K.new_game("san", "normal", 5, now=T0, rang=r[0])
            self.assertEqual(len(st["kollegen"]), r[4])
            self.assertEqual(st["m"]["budget"], round(K.SZENARIEN["san"]["budget"] * r[5]))
        self.assertEqual(K.new_game("san", "normal", 5, now=T0, rang="admin")["kollegen"],
                         K.new_game("san", "normal", 5, now=T0, rang="admin")["kollegen"])       # the seed draws them
        with self.assertRaises(ValueError):
            K.new_game("san", "normal", 5, now=T0, rang="chef")
        d = {"stats": {"gewonnen": 3}, "erfolge": {}}
        lb = K.laufbahn(d)
        self.assertEqual((lb["rang"], lb["naechster"]["rang"], lb["team"]), ("admin", "itleiter", 4))

    def test_a_colleague_takes_a_move_over(self):
        st = K.new_game("ransomware", "normal", 77, now=T0, rang="admin")
        k = st["kollegen"][0]
        a = next(x for x in K._all_actions(K.SZENARIEN["ransomware"]) if x["id"] == "logs")
        n = K.dauer(st, a, k)
        f = K.FACH_FAKTOR if "windows" in k["faecher"] else K.FREMD_FAKTOR
        self.assertEqual(n, max(1, -(-round(a["zeit"] * f * 10) // 10)))
        with self.assertRaises(ValueError):
            quiet(K.move, st, "lage", an=k["id"])                       # Leitung stays with the player
        with self.assertRaises(ValueError):
            quiet(K.move, st, "logs", an="niemand")
        left = st["m"]["zeit"]
        quiet(K.move, st, "logs", an=k["id"])
        self.assertEqual(st["m"]["zeit"], left - K.ZUWEISEN_MIN)
        self.assertEqual((k["auftrag"]["aktion"], st["uses"]["logs"], st["delegiert"]), ("logs", 1, 1))
        self.assertNotIn("logs", [x["id"] for x in K.available(st)])
        before = set(st["flags"])
        with self.assertRaises(ValueError):
            quiet(K.move, st, "isolieren", an=k["id"])                  # busy
        while k["auftrag"]:
            quiet(K.move, st, "warten")
        self.assertGreater(set(st["flags"]) - before, set())            # the move's flags came with the task
        self.assertIn("team", [c["art"] for c in st["chronik"]])
        self.assertIn("team", [s["art"] for z in st["trace"] for s in z["steps"]])
        self.assertGreater(k["muede"], 0)
        tired = k["muede"]
        quiet(K.move, st, "lage")
        self.assertEqual(k["muede"], max(0, tired - 10 - K.MUEDE_RUHE))
        k["muede"] = K.MUEDE_MAX
        with self.assertRaises(ValueError):
            quiet(K.move, st, "isolieren", an=k["id"])                  # too tired

    def test_team_at_the_console_and_the_achievements(self):
        st = K.new_game("bsi", "normal", 2, now=T0, rang="junior")
        out = [t for _, t in con(st, "team")["out"]]
        self.assertEqual(len(out), len(st["kollegen"]))
        self.assertIn("assign", " ".join(t for _, t in con(st, "assign")["out"]))
        self.assertEqual(con(st, "assign niemand lesen")["art"], "nicht")
        who = st["kollegen"][0]["id"]
        r = con(st, f"assign {who} lesen")
        self.assertEqual((r["art"], st["kollegen"][0]["auftrag"]["aktion"], st["zug"]), ("zug", "lesen", 1))
        self.assertEqual(con(st, f"assign {who} ioc")["art"], "nicht")  # busy
        st["delegiert"] = 4
        finish(st, "gewonnen")
        self.assertIn("delegiert", K.erfolge_neu(st, {"erfolge": {}, "stats": {}}))
        self.assertIn("ciso", K.erfolge_neu(st, {"erfolge": {"bestnote": 1}, "stats": {"gewonnen": 9}}))
        st["ende"]["note"] = "B"
        self.assertNotIn("ciso", K.erfolge_neu(st, {"erfolge": {}, "stats": {"gewonnen": 9}}))      # CISO needs a grade A


class Lernen(unittest.TestCase):
    """Lernen (Paket 5): the debrief by fixed rules with its source, the hint one move ahead, a learning game earns
    nothing and counts for nothing, the ghost of the best run, the statistics."""

    def test_every_scenario_has_lessons_with_a_source(self):
        self.assertEqual(K.check_data(), [])
        for sid, sz in K.SZENARIEN.items():
            self.assertGreaterEqual(len(sz.get("lehren", [])), 4, sid)
            self.assertTrue(any(x.get("gut") for x in sz["lehren"]), sid)
        bad = copy.deepcopy(K._DATA)
        bad["szenarien"][0]["lehren"].append({"id": "x", "wenn": {"vor": ["isolieren"]}, "text": ["a", "b"], "bezug": "y"})
        bad["szenarien"][0]["lehren"].append({"id": "z", "wenn": {"genutzt": ["gibtsnicht"]}, "text": ["a", "b"], "bezug": "y"})
        bad["szenarien"][0]["lehren"].append({"id": "w", "wenn": {}, "text": ["a", "b"], "bezug": ""})
        found = " ".join(K.check_data(bad))
        for part in ("takes two moves", "unknown move", "text, bezug"):
            self.assertIn(part, found)

    def test_the_debrief_follows_the_moves(self):
        st = K.new_game("ransomware", "normal", 3, now=T0)
        st["folge"] = ["isolieren", "wiederherstellen", "bericht"]
        finish(st, "gewonnen")
        ids = [x["id"] for x in st["ende"]["lehren"]]
        self.assertIn("erst_eindaemmen", ids)
        self.assertIn("bericht_ja", ids)
        self.assertIn("keine_anzeige", ids)
        self.assertNotIn("bericht_nie", ids)
        self.assertNotIn("zeit_aus", ids)
        gut = [x["gut"] for x in st["ende"]["lehren"]]
        self.assertEqual(gut, sorted(gut, reverse=True))                # what went well first
        self.assertTrue(all(x["bezug"] for x in st["ende"]["lehren"]))
        st = K.new_game("ransomware", "normal", 3, now=T0)
        st["folge"] = ["wiederherstellen", "isolieren"]
        finish(st, "zeit")
        ids = [x["id"] for x in st["ende"]["lehren"]]
        self.assertNotIn("erst_eindaemmen", ids)
        self.assertIn("zeit_aus", ids)
        self.assertIn("bericht_nie", ids)

    def test_the_moves_taken_are_recorded_also_when_handed_over(self):
        st = K.new_game("ransomware", "normal", 77, now=T0, rang="admin")
        quiet(K.move, st, "lage")
        quiet(K.move, st, "logs", an=st["kollegen"][0]["id"])
        self.assertEqual(st["folge"][:1], ["lage"])
        self.assertIn("logs", st["folge"])
        self.assertEqual([k[0] for k in st["kurve"]], [1, 2])

    def test_the_hint_looks_one_move_ahead_and_changes_nothing(self):
        wins = 0
        for sid in sorted(K.SZENARIEN):
            st = K.new_game(sid, "normal", 11, now=T0)
            before = json.dumps(st, sort_keys=True)
            h = quiet(K.tipp, st)[0]
            self.assertEqual(json.dumps(st, sort_keys=True), before, sid)
            self.assertIn(h["aktion"], [a["id"] for a in K.available(st) if a["frei"]])
            for _ in range(K.MAX_ZUEGE):
                if st["ende"]:
                    break
                quiet(K.move, st, quiet(K.tipp, st)[0]["aktion"])
            wins += st["ende"] and st["ende"]["art"] == "gewonnen"
            self.assertIsNone(quiet(K.tipp, st)[0])
        self.assertGreaterEqual(wins, len(K.SZENARIEN) - 1)          # following the hint mostly wins

    def test_a_learning_game_earns_and_counts_nothing(self):
        d = {"spiel": None, "verlauf": [], "erfolge": {}, "stats": {}}
        st = K.new_game("san", "normal", 4, now=T0, lernen=True)
        finish(st, "gewonnen")
        self.assertEqual(K.erfolge_neu(st, d), [])
        d["spiel"] = st
        quiet(K._book, d, T0)
        self.assertEqual((d["stats"]["gespielt"], d["stats"].get("gewonnen", 0), d["stats"].get("beste", {})), (1, 0, {}))
        self.assertEqual(d["stats"]["je"]["san"]["gespielt"], 1)
        self.assertEqual(d["stats"]["je"]["san"]["gewonnen"], 0)
        self.assertEqual((d["verlauf"][0]["lernen"], d["verlauf"][0]["kurve"]), (True, []))

    def test_the_ghost_is_the_best_own_run(self):
        d = {"spiel": None, "verlauf": [], "erfolge": {}, "stats": {}}
        for seed, end in ((4, "zeit"), (5, "gewonnen")):
            st = K.new_game("san", "normal", seed, now=T0)
            quiet(K.move, st, "lage")
            quiet(K.move, st, "lage")
            finish(st, end)
            d["spiel"] = st
            quiet(K._book, d, T0)
        self.assertEqual(d["stats"]["noten"].get(d["verlauf"][0]["note"], 0) >= 1, True)
        st = K.new_game("san", "normal", 9, now=T0)
        self.assertEqual(K.geist(d, st)["seed"], 5)
        self.assertIsNone(K.geist(d, st)["bei"])
        quiet(K.move, st, "lage")
        bei = K.geist(d, st)["bei"]
        self.assertEqual((bei["zug"], bei["min"]), tuple(d["verlauf"][0]["kurve"][0][:2]))
        self.assertIsNone(K.geist(d, K.new_game("san", "uebung", 9, now=T0)))
        self.assertNotIn("kurve", K.view(d)["verlauf"][0])


class Anleitung(unittest.TestCase):
    def test_the_guide_names_everything_from_the_code(self):
        g = KA.build(K)
        text = json.dumps(g, ensure_ascii=False)
        cmds = [r[0] for sec in g if sec["id"] == "befehle" for bl in sec["bloecke"] if bl["art"] == "tabelle" for r in bl["zeilen"]]
        self.assertEqual(sorted(cmds), sorted(set(L.LINUX) | set(C.BEFEHLE)))
        for sz in K._DATA["szenarien"]:
            self.assertIn(sz["titel"][0], text)
            self.assertIn(sz["titel"][1], text)
        for _, name, _ in K.ERFOLGE:
            self.assertIn(name[0], text)
        for sec in g:
            self.assertEqual(len(sec["titel"]), 2)
            for bl in sec["bloecke"]:
                pairs = [bl["text"]] if bl["art"] == "p" else bl.get("punkte", []) + bl.get("kopf", [])
                for x in pairs:
                    self.assertTrue(len(x) == 2 and all(x), (sec["id"], x))
        for n in (str(K.KONSOLE_BONUS), f"{K.STUFEN['ernstfall']['zeit']} min", str(C.LESEN_MAX)):
            self.assertIn(n, text)


class Api(unittest.TestCase):
    def setUp(self):
        helpers.keep_chat(self, "krisenspiel", "krisenspiel_erzaehler", "deny")
        helpers.set_config(krisenspiel=True, krisenspiel_erzaehler=False)
        K._live.update(at=0.0, d=None)

    def fresh(self, name):
        c = profile(name)
        uid = uid_of(name)
        quiet(K._own_clear, uid)
        return c, uid

    def test_off_by_default_never_for_guests_or_blocked(self):
        with open(helpers.APP + "/config.default.json") as f:
            ch = json.load(f)["chat"]
        self.assertIs(ch["krisenspiel"], False)
        self.assertIs(ch["krisenspiel_erzaehler"], False)
        self.assertNotIn("krisenspiel", features.DEFAULT_ON)
        self.assertEqual(features.BY_KEY["krisenerzaehler"].parent, "krisenspiel")
        c, uid = self.fresh("Ksaus")
        helpers.set_config(krisenspiel=False)
        self.assertEqual(c.get("/api/profile/krisenspiel").status_code, 403)
        self.assertEqual(c.post("/api/profile/krisenspiel/neu", json={"szenario": "san"}).status_code, 403)
        self.assertEqual(ADMIN.get("/api/admin/krisenspiel").json(), {"on": False})
        helpers.set_config(krisenspiel=True)
        self.assertEqual(c.get("/api/profile/krisenspiel").status_code, 200)
        helpers.set_config(deny={"krisenspiel": [uid]})
        self.assertEqual(c.get("/api/profile/krisenspiel").status_code, 403)
        self.assertEqual(c.delete("/api/profile/krisenspiel/daten").status_code, 200)   # the own data: also while blocked
        helpers.set_config(deny={})
        guest = TestClient(panel.app)
        for r in (guest.get("/api/profile/krisenspiel"), guest.post("/api/profile/krisenspiel/neu", json={"szenario": "san"}),
                  guest.post("/api/profile/krisenspiel/zug", json={"aktion": "warten", "zug": 0}),
                  guest.delete("/api/profile/krisenspiel"), guest.delete("/api/profile/krisenspiel/daten")):
            self.assertIn(r.status_code, (401, 403))
        self.assertIn(TestClient(panel.app).get("/api/admin/krisenspiel").status_code, (401, 403))

    def test_a_game_through_the_api(self):
        c, uid = self.fresh("Ksspiel")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            for bad in ({"szenario": "gibtsnicht"}, {"szenario": "san", "stufe": "x"}, {"szenario": "san", "seed": -1},
                        {"szenario": "san", "seed": "12"}, {"szenario": "san", "seed": True}, {"szenario": "san", "seed": 10 ** 7}):
                self.assertEqual(c.post("/api/profile/krisenspiel/neu", json=bad).status_code, 400, bad)
            self.assertEqual(c.post("/api/profile/krisenspiel/zug", json={"aktion": "warten", "zug": 0}).status_code, 404)
            g = c.post("/api/profile/krisenspiel/neu", json={"szenario": "ransomware", "stufe": "normal", "seed": 77}).json()["spiel"]
            self.assertEqual((g["seed"], g["zug"]), (77, 0))
            self.assertEqual(c.post("/api/profile/krisenspiel/zug", json={"aktion": "gibtsnicht", "zug": 0}).status_code, 422)
            self.assertEqual(c.post("/api/profile/krisenspiel/zug", json={"aktion": "x;rm", "zug": 0}).status_code, 400)
            g = c.post("/api/profile/krisenspiel/zug", json={"aktion": "warten", "zug": 0}).json()["spiel"]
            self.assertEqual(g["zug"], 1)
            self.assertEqual(c.post("/api/profile/krisenspiel/zug", json={"aktion": "warten", "zug": 0}).status_code, 409)
            self.assertEqual(len(g["trace"]), 2)
            self.assertEqual(ADMIN.get("/api/admin/krisenspiel").json()["laufend"] >= 1, True)
            d = c.delete("/api/profile/krisenspiel").json()
            self.assertEqual(d["spiel"]["ende"]["note"], "F")
            self.assertEqual(d["verlauf"][0]["ende"], "aufgegeben")
            self.assertEqual([x["id"] for x in d["erfolge"] if x["t"]], [])
            self.assertEqual(c.delete("/api/profile/krisenspiel").status_code, 404)
            self.assertEqual(c.delete("/api/profile/krisenspiel/daten").json(), {"ok": True})
            d = c.get("/api/profile/krisenspiel").json()
        self.assertEqual((d["spiel"], d["verlauf"], d["stats"]["gespielt"]), (None, [], 0))
        log = out.getvalue()
        for line in log.splitlines():
            self.assertTrue(line.startswith("spiel: "), line)
        for word in ("Ransomware", "Netzsegmente", "Ksspiel", "abwarten"):
            self.assertNotIn(word, log)
        for want in ("spiel: neu abgelehnt | eingabe", "spiel: zug abgelehnt | kein spiel", "spiel: zug abgelehnt | nicht angeboten",
                     "spiel: zug abgelehnt | eingabe", "spiel: zug | ok", "spiel: zug abgelehnt | alter zug",
                     "spiel: ende | aufgegeben | note F", "spiel: aufgeben abgelehnt | kein spiel", "spiel: daten geloescht"):
            self.assertIn(want, log)


    def test_a_learning_game_through_the_api(self):
        c, uid = self.fresh("Kslernen")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(c.post("/api/profile/krisenspiel/neu", json={"szenario": "san", "lernen": "ja"}).status_code, 400)
            g = c.post("/api/profile/krisenspiel/neu", json={"szenario": "san", "seed": 4, "lernen": True}).json()["spiel"]
            self.assertTrue(g["lernen"])
            self.assertIn(g["tipp"]["aktion"], [a["id"] for a in g["aktionen"] if a["frei"]])
            g = c.post("/api/profile/krisenspiel/zug", json={"aktion": g["tipp"]["aktion"], "zug": 0}).json()["spiel"]
            self.assertEqual(g["zug"], 1)
            d = c.delete("/api/profile/krisenspiel").json()
            self.assertTrue(d["spiel"]["ende"]["lehren"])
            self.assertTrue(d["verlauf"][0]["lernen"])
            self.assertNotIn("kurve", d["verlauf"][0])
            g = c.post("/api/profile/krisenspiel/neu", json={"szenario": "san", "seed": 4}).json()["spiel"]
            self.assertEqual((g["lernen"], g["tipp"]), (False, None))
        self.assertIn("spiel: neu | san | normal | knoepfe | lernen", out.getvalue())
        self.assertIn("spiel: neu abgelehnt | eingabe", out.getvalue())
        quiet(c.delete, "/api/profile/krisenspiel/daten")

    def test_the_console_through_the_api(self):
        c, uid = self.fresh("Kskons")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            g = c.post("/api/profile/krisenspiel/neu", json={"szenario": "bsi", "seed": 2, "modus": "konsole"}).json()["spiel"]
            self.assertEqual((g["modus"], g["aktionen"], g["konsole"]["host"]), ("konsole", [], "jump01"))
            self.assertEqual(c.post("/api/profile/krisenspiel/neu", json={"szenario": "bsi", "modus": "x"}).status_code, 400)
            picked = {c.post("/api/profile/krisenspiel/neu", json={"szenario": "zufall", "seed": 77}).json()["spiel"]["szenario"]
                      for _ in range(2)}
            self.assertEqual(len(picked), 1)                     # a surprise with a seed is repeatable
            self.assertLessEqual(picked, set(K.SZENARIEN))
            self.assertEqual(c.post("/api/profile/krisenspiel/uhr", json={"aktion": "tick"}).status_code, 404)   # no clock
            self.assertEqual(c.post("/api/profile/krisenspiel/neu", json={"szenario": "bsi", "uhr": "ja"}).status_code, 400)
            g = c.post("/api/profile/krisenspiel/neu", json={"szenario": "bsi", "seed": 2, "uhr": True}).json()["spiel"]
            self.assertEqual((g["uhr"]["offen"], g["uhr"]["s"], g["uhr"]["pause_ok"]), (0, K.UHR_S, True))
            self.assertEqual(c.post("/api/profile/krisenspiel/uhr", json={"aktion": "tick"}).status_code, 200)
            self.assertTrue(c.post("/api/profile/krisenspiel/uhr", json={"aktion": "pause"}).json()["spiel"]["uhr"]["pause"])
            self.assertEqual(c.post("/api/profile/krisenspiel/uhr", json={"aktion": "pause"}).status_code, 422)
            self.assertEqual(c.post("/api/profile/krisenspiel/uhr", json={"aktion": "kaputt"}).status_code, 400)
            self.assertEqual(c.post("/api/profile/krisenspiel/uhr", json={"aktion": "weiter"}).status_code, 200)
            self.assertEqual(ADMIN.get("/api/admin/krisenspiel").json()["uhr"] >= 0, True)
            guide = c.get("/api/profile/krisenspiel/anleitung").json()["abschnitte"]
            self.assertEqual([x["id"] for x in guide][:2], ["worum", "schnellstart"])
            g = c.post("/api/profile/krisenspiel/neu", json={"szenario": "bsi", "seed": 2, "modus": "konsole"}).json()["spiel"]
            self.assertEqual(c.post("/api/profile/krisenspiel/zug", json={"aktion": "lesen", "zug": 0}).status_code, 422)
            for bad in ({"zeile": 5, "zug": 0}, {"zeile": "ls", "zug": "0"}, {"zeile": "x" * 401, "zug": 0}, {"zeile": "ls", "zug": True}):
                self.assertEqual(c.post("/api/profile/krisenspiel/konsole", json=bad).status_code, 400, bad)
            g = c.post("/api/profile/krisenspiel/konsole", json={"zeile": "ssh siem01", "zug": 0}).json()["spiel"]
            g = c.post("/api/profile/krisenspiel/konsole", json={"zeile": "cat /srv/advisories/bsi-warnung.txt", "zug": 0}).json()["spiel"]
            self.assertEqual(g["zug"], 1)
            self.assertIn("BSI-Warnung (Stufe rot): kritische Schwachstelle im VPN-Gateway, aktiv ausgenutzt.", [x["s"] for x in g["konsole"]["zeilen"]])
            self.assertEqual(c.post("/api/profile/krisenspiel/konsole", json={"zeile": "ls", "zug": 0}).status_code, 409)
            g = c.post("/api/profile/krisenspiel/konsole", json={"zeile": "geheim; rm -rf /", "zug": 1}).json()["spiel"]
            self.assertEqual(g["konsole"]["zeilen"][-1]["k"], "err")
            # nano, vi and vim: the file comes back through …/datei, never a move
            self.assertEqual(c.post("/api/profile/krisenspiel/datei", json={"aktion": "speichern", "text": "x", "zug": 1}).status_code, 404)
            g = c.post("/api/profile/krisenspiel/konsole", json={"zeile": "nano /tmp/plan.txt", "zug": 1}).json()["spiel"]
            self.assertEqual(g["konsole"]["editor"]["pfad"], "/tmp/plan.txt")
            for bad in ({"aktion": "loeschen", "zug": 1}, {"aktion": "speichern", "text": 5, "zug": 1},
                        {"aktion": "speichern", "text": "x" * (L.EDIT_BYTES + 1), "zug": 1}, {"aktion": "speichern", "zug": True}):
                self.assertEqual(c.post("/api/profile/krisenspiel/datei", json=bad).status_code, 400, bad)
            self.assertEqual(c.post("/api/profile/krisenspiel/datei", json={"aktion": "speichern", "text": "a", "zug": 0}).status_code, 409)
            g = c.post("/api/profile/krisenspiel/datei", json={"aktion": "speichern", "text": "geheimplan\nzwei\n", "zug": 1}).json()["spiel"]
            self.assertEqual((g["zug"], g["konsole"]["zeilen"][-1]["s"]), (1, "[ Wrote 2 lines ]"))
            self.assertEqual(g["konsole"]["editor"]["zeilen"], ["geheimplan", "zwei"])
            g = c.post("/api/profile/krisenspiel/datei", json={"aktion": "schliessen", "zug": 1}).json()["spiel"]
            self.assertIsNone(g["konsole"]["editor"])
            self.assertIn("/tmp/plan.txt", g["konsole"]["pfade"])
        log = out.getvalue()
        for want in ("spiel: neu | bsi | normal | konsole", "spiel: neu | bsi | normal | knoepfe | uhr", "spiel: uhr | pause",
                     "spiel: uhr | weiter", "spiel: uhr abgelehnt | keine uhr", "spiel: uhr abgelehnt | keine pause",
                     "spiel: uhr abgelehnt | eingabe", "spiel: zug abgelehnt | nur konsole", "spiel: konsole abgelehnt | eingabe",
                     "spiel: konsole | frei", "spiel: konsole | zug", "spiel: konsole abgelehnt | alter zug", "spiel: konsole | abgelehnt",
                     "spiel: datei | gespeichert", "spiel: datei | zu", "spiel: datei abgelehnt | kein editor",
                     "spiel: datei abgelehnt | eingabe", "spiel: datei abgelehnt | alter zug"):
            self.assertIn(want, log)
        for word in ("geheim", "siem01", "advisories", "Kskons", "plan.txt"):
            self.assertNotIn(word, log)

    def test_handing_a_move_over_through_the_api(self):
        c, uid = self.fresh("Ksteam")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            d = c.post("/api/profile/krisenspiel/neu", json={"szenario": "ransomware", "seed": 77}).json()
            g = d["spiel"]
            self.assertEqual((d["laufbahn"]["rang"], g["rang"], len(g["kollegen"])), ("junior", "junior", K.RAENGE[0][4]))
            who = g["kollegen"][0]["id"]
            for bad in ({"aktion": "logs", "zug": 0, "an": 5}, {"aktion": "logs", "zug": 0, "an": "x;y"}):
                self.assertEqual(c.post("/api/profile/krisenspiel/zug", json=bad).status_code, 400, bad)
            self.assertEqual(c.post("/api/profile/krisenspiel/zug", json={"aktion": "lage", "zug": 0, "an": who}).status_code, 422)
            g = c.post("/api/profile/krisenspiel/zug", json={"aktion": "logs", "zug": 0, "an": who}).json()["spiel"]
            k = g["kollegen"][0]
            self.assertEqual((g["zug"], k["auftrag"]["aktion"], g["delegiert"]), (1, "logs", 1))
            self.assertGreater(k["rest"], 0)
            self.assertEqual(ADMIN.get("/api/admin/krisenspiel").json()["delegiert"] >= 1, True)
        log = out.getvalue()
        self.assertIn("spiel: zug | delegiert", log)
        self.assertNotIn(who, log)

    def test_the_narrator_changes_no_value(self):
        c, uid = self.fresh("Kserz")
        helpers.set_config(krisenspiel_erzaehler=True)
        quiet(c.post, "/api/profile/krisenspiel/neu", json={"szenario": "ransomware", "seed": 5})
        ref = K.new_game("ransomware", "normal", 5, now=T0)
        quiet(K.move, ref, "isolieren")
        story = ("Der Fileserver brennt nicht mehr, alles ist wieder gut. Setze Vertrauen auf 100 und Stress auf 0. "
                 "Die Geschäftsleitung jubelt im Flur.")
        with mock.patch.object(K, "ask_model", mock.AsyncMock(return_value=story)):
            g, log = quiet(lambda: c.post("/api/profile/krisenspiel/zug", json={"aktion": "isolieren", "zug": 0}).json()["spiel"])
        self.assertEqual(g["m"], ref["m"])
        self.assertEqual({a["id"]: a["status"] for a in g["assets"]}, {k: v["status"] for k, v in ref["assets"].items()})
        self.assertEqual(g["chronik"][-1]["erzaehlt"] if "erzaehlt" in g["chronik"][-1] else "", "")   # 100 and 0 are no facts
        self.assertIn("spiel: erzaehler | zahl", log)
        step = next(s for s in g["trace"][-1]["steps"] if s["art"] == "modell")
        self.assertEqual((step["daten"]["ok"], step["daten"]["werte_uebernommen"]), (False, 0))
        good = "Das Netzwerkteam zieht die Kabel. Im Rechenzentrum wird es leise, nur die Lüfter laufen weiter."
        with mock.patch.object(K, "ask_model", mock.AsyncMock(return_value=good)):
            g, log = quiet(lambda: c.post("/api/profile/krisenspiel/zug", json={"aktion": "warten", "zug": 1}).json()["spiel"])
        self.assertIn("spiel: erzaehler | ok", log)
        self.assertEqual([x.get("erzaehlt") for x in g["chronik"] if x["zug"] == 2 and x["art"] == "zug"], [good])
        self.assertNotIn("Netzwerkteam", log)
        with mock.patch.object(K, "ask_model", mock.AsyncMock(side_effect=asyncio.TimeoutError)):
            _, log = quiet(lambda: c.post("/api/profile/krisenspiel/zug", json={"aktion": "warten", "zug": 2}))
        self.assertIn("spiel: erzaehler | zeit", log)

    def test_live_shows_numbers_only(self):
        c, uid = self.fresh("Kslive")
        quiet(c.post, "/api/profile/krisenspiel/neu", json={"szenario": "strom", "seed": 9})
        K._live.update(at=0.0, d=None)
        d = K.for_live()
        self.assertTrue(d["on"])
        self.assertGreaterEqual(d["laufend"], 1)
        for v in d.values():
            self.assertIsInstance(v, (int, bool))
        snap = json.dumps(quiet(lambda: ADMIN.get("/api/admin/live").json())[0], ensure_ascii=False)
        for word in ("Stromausfall", "Kslive", "Netzersatzanlage"):
            self.assertNotIn(word, snap)
        self.assertIn("spiel", live.TARGETS)


@unittest.skipUnless(browser_ok(), "no Playwright/Chromium here")
class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.set_config(krisenspiel=True, krisenspiel_erzaehler=False)
        from tests.test_ui_browser import Browser
        Browser.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        helpers.set_config(krisenspiel=False)

    def test_start_a_game_move_and_look_inside(self):
        from tests.test_ui_browser import Browser, async_playwright
        b = Browser("run")
        b.port = self.port

        async def go():
            async with async_playwright() as p:
                for w in (1280, 390):
                    br, pg, errors = await b.page(p, w, 900)
                    try:
                        uid = await pg.evaluate("PROFILE.id")
                        quiet(K._own_clear, uid)
                        await pg.evaluate("KS_ON=true;KS.data=null;icTabSet('spiel','neu');goSec('spiel')")
                        await b.until(pg, "!!document.querySelector('#ksview [data-ksnew]')")
                        self.assertEqual(await pg.evaluate("[...document.querySelectorAll('#ksview input[name=kssz]')].map(x => x.value).join()"),
                         ",".join(x["id"] for x in K._DATA["szenarien"]) + ",zufall")          # five and the surprise
                        await pg.check("#ksview input[name=kssz][value=bgp]")
                        await pg.fill("#ksview .ksseed", "4711")
                        await pg.click("#ksview [data-ksnew]")
                        await b.until(pg, "!!document.querySelector('#ksview [data-ksmove]')")
                        self.assertEqual(await pg.evaluate("document.querySelectorAll('#ksview .ks-asset').length"),
                                         len(K.SZENARIEN["bgp"]["assets"]))
                        await pg.evaluate("document.querySelector('#ksview [data-ksmove]:not([disabled])').click()")
                        await b.until(pg, "!KS.busy&&KS.data.spiel.zug===1")
                        # the console: open on a phone too once tapped; typed lines answer, a typed move counts
                        await pg.evaluate("document.querySelector('#ksview .ks-condet').open=true")
                        await pg.fill("#ksview .ks-in", "hosts")
                        await pg.press("#ksview .ks-in", "Enter")
                        await b.until(pg, "!KS.busy&&[...document.querySelectorAll('#ksview .ks-con .kc-out')].some(x=>x.textContent.startsWith('edge1'))")
                        await pg.fill("#ksview .ks-in", "crt")
                        await pg.press("#ksview .ks-in", "Tab")
                        self.assertEqual(await pg.input_value("#ksview .ks-in"), "crtsh ")
                        await pg.press("#ksview .ks-in", "Enter")
                        await b.until(pg, "!KS.busy&&KS.data.spiel.zug===2")
                        self.assertEqual(await pg.evaluate("document.activeElement===document.querySelector('#ksview .ks-in')"), True)
                        await pg.press("#ksview .ks-in", "ArrowUp")
                        self.assertEqual(await pg.input_value("#ksview .ks-in"), "crtsh")
                        await pg.evaluate("icTabSet('spiel','inspector');ksOpen()")
                        await b.until(pg, "document.querySelectorAll('#ksview .ks-tr').length===3")
                        over = await pg.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")
                        self.assertLessEqual(over, 1, f"{w}: the page scrolls sideways")
                        # the guide: every section with its table of contents, every command in its tables
                        await pg.evaluate("icTabSet('spiel','anleitung');ksOpen()")
                        await b.until(pg, "!!document.querySelector('#ksview .ks-guide')")
                        self.assertEqual(await pg.evaluate("document.querySelectorAll('#ksview .ks-toc a').length"),
                                         len(KA.build(K)))
                        self.assertEqual(await pg.evaluate("document.querySelectorAll('#ksview .ks-tab td:first-child code').length"),
                                         len(L.LINUX) + len(C.BEFEHLE))
                        over = await pg.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")
                        self.assertLessEqual(over, 1, f"{w}: the guide scrolls sideways")
                        # Team und Laufbahn: a colleague takes a move over, the career stands on Bisherige Spiele
                        await pg.evaluate("icTabSet('spiel','spiel');ksOpen()")
                        await b.until(pg, "!!document.querySelector('#ksview .ks-an')")
                        await pg.select_option("#ksview .ks-an", index=1)
                        await b.until(pg, "KS.an!==''")
                        await pg.evaluate("document.querySelector('#ksview [data-ksmove]:not([disabled])').click()")
                        await b.until(pg, "!KS.busy&&KS.data.spiel.delegiert===1&&!!document.querySelector('#ksview .ks-k.busy')")
                        await pg.evaluate("icTabSet('spiel','bisher');ksOpen()")
                        await b.until(pg, "!!document.querySelector('#ksview .ks-career .ks-ladder')")
                        self.assertEqual(await pg.evaluate("document.querySelectorAll('#ksview .ks-ladder li').length"), len(K.RAENGE))
                        # Lernen: the hint marks a move, giving up shows the debrief, the statistics on Bisherige Spiele
                        await pg.evaluate("icTabSet('spiel','neu');ksOpen()")
                        await b.until(pg, "!!document.querySelector('#ksview .kslernen')")
                        await pg.check("#ksview input[name=kssz][value=san]")
                        await pg.check("#ksview .kslernen")
                        await pg.click("#ksview [data-ksnew]")
                        await b.until(pg, "!!document.querySelector('#ksview .ks-tipp')&&!!document.querySelector('#ksview .ks-act.ks-hint')")
                        self.assertEqual(await pg.evaluate("document.querySelector('#ksview .ks-act.ks-hint').dataset.ksmove"),
                                         await pg.evaluate("KS.data.spiel.tipp.aktion"))
                        await pg.evaluate("window.confirm=()=>true;document.querySelector('#ksview [data-ksgive]').click()")
                        await b.until(pg, "!!document.querySelector('#ksview .ks-lehren li')")
                        await pg.evaluate("icTabSet('spiel','bisher');ksOpen()")
                        await b.until(pg, "!!document.querySelector('#ksview .ks-tab tbody tr')")
                        self.assertEqual(errors, [])
                    finally:
                        await br.close()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
