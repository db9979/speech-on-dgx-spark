"""Bus und Bahn (transit.py) against a fake transport.rest service; times are relative to now."""
import asyncio
import datetime
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import chat  # noqa: E402
import transit  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})
PORT = helpers._port()
ZONE = datetime.timezone(datetime.timedelta(hours=2))
NOW = datetime.datetime.now(ZONE).replace(second=0, microsecond=0)
LATE = {"value": 0, "cancelled": False}


def iso(minutes):
    return (NOW + datetime.timedelta(minutes=minutes)).isoformat()


def fake():
    app = FastAPI()

    @app.get("/locations")
    def locations(query: str = ""):
        stops = {"karlsbad": ("8003204", "Karlsbad-Langensteinbach Bahnhof"), "karlsruhe": ("8000191", "Karlsruhe Hbf")}
        if query.lower() == "bahnhof":   # two stations, neither named exactly so (Rückfrage, klaeren.py)
            return [{"type": "station", "id": "8001", "name": "Ettlingen Bahnhof"},
                    {"type": "station", "id": "8002", "name": "Durlach Bahnhof"}]
        return [{"type": "stop", "id": i, "name": n} for k, (i, n) in stops.items() if k in query.lower()] + \
            [{"type": "address", "id": "x", "name": "Adresse"}]

    @app.get("/stops/{sid}/departures")
    def deps(sid: str):
        return {"departures": [
            {"plannedWhen": iso(4), "when": iso(7), "delay": 180, "platform": "2", "direction": "Karlsruhe Marktplatz",
             "line": {"name": "S11"}},
            {"plannedWhen": iso(12), "delay": 0, "direction": "Ittersbach", "line": {"name": "Bus 106"}, "cancelled": True}]}

    @app.get("/journeys")
    def journeys(departure: str = ""):
        start = datetime.datetime.fromisoformat(departure) if departure else NOW
        dep = start + datetime.timedelta(minutes=12)
        return {"journeys": [{"legs": [
            {"plannedDeparture": dep.isoformat(), "departureDelay": LATE["value"], "line": {"name": "S11"},
             "plannedArrival": (dep + datetime.timedelta(minutes=27)).isoformat(), "arrivalDelay": 0,
             "cancelled": LATE["cancelled"]}]}]}
    return app


helpers._serve(fake(), PORT)


def profile(name):
    ADMIN.post("/api/admin/profiles", json={"name": name, "pin": "1234"})
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": "1234"}).status_code == 200
    return c


def ask(c, text):
    r = c.post("/api/chat", json={"messages": [{"role": "user", "content": text}]})
    return "".join(e.get("delta", "") for e in helpers.events(r) if e["type"] == "text")


class Transit(unittest.TestCase):
    def setUp(self):
        helpers.set_config(transit=True, transit_url=f"http://127.0.0.1:{PORT}")
        transit._cache.clear()

    def tearDown(self):
        helpers.set_config(transit=False, transit_url="")

    def test_stop_departures_and_connections(self):
        a = profile("Pendler")
        stops = a.post("/api/profile/transit/find", json={"q": "Karlsbad"}).json()["stops"]
        self.assertEqual(stops, [{"id": "8003204", "name": "Karlsbad-Langensteinbach Bahnhof"}])
        self.assertEqual(a.put("/api/profile/transit", json={"home": {"id": "../x", "name": "x"}}).status_code, 400)
        a.put("/api/profile/transit", json={"home": stops[0]})
        self.assertIn("NO TOOL transit", ask(a, "TOOL transit {}"))       # not switched on by the profile yet
        a.put("/api/profile/settings", json={"transit_on": True})
        out = ask(a, "TOOL transit {}")
        self.assertIn(f"Abfahrten ab Karlsbad-Langensteinbach Bahnhof: {(NOW + datetime.timedelta(minutes=4)).astimezone(chat.user_zone('')):%H:%M} (+3) "
                      "S11 nach Karlsruhe Marktplatz, Gleis 2", out)
        self.assertIn("Abfahrten ab Karlsbad-Langensteinbach Bahnhof:", out)
        self.assertIn("Bus 106 nach Ittersbach, fällt aus", out)
        out = ask(a, 'TOOL transit {"to": "Karlsruhe"}')
        self.assertIn("Von Karlsbad-Langensteinbach Bahnhof nach Karlsruhe Hbf: ab ", out)
        self.assertIn("mit S11", out)
        self.assertIn("ohne Umstieg", out)
        # timetable text is outside text: nothing that changes things in the same answer
        helpers.LLM_CALLS.clear()
        ask(a, "TOOL transit {}")
        self.assertNotIn("memory_save", [t["function"]["name"] for t in helpers.LLM_CALLS[-1].get("tools", [])])

    def test_commute_note_only_when_late(self):
        a = profile("Pendlerin")
        a.put("/api/profile/settings", json={"transit_on": True})
        home = {"id": "8003204", "name": "Karlsbad-Langensteinbach Bahnhof"}
        to = {"id": "8000191", "name": "Karlsruhe Hbf"}
        at = (NOW + datetime.timedelta(minutes=20)).strftime("%H:%M")
        self.assertEqual(a.put("/api/profile/transit", json={"commute": {"to": to, "at": "7:30"}}).status_code, 400)
        a.put("/api/profile/transit", json={"home": home, "commute": {"to": to, "at": at, "days": [0, 1, 2, 3, 4, 5, 6]}})
        uid = next(u["id"] for u in ADMIN.get("/api/admin/profiles").json()["users"] if u["name"] == "Pendlerin")
        self.assertIsNone(asyncio.run(transit.commute_note(uid, NOW)))
        LATE["value"] = 480
        transit._cache.clear()
        try:
            text, _ = asyncio.run(transit.commute_note(uid, NOW))
            self.assertIn("nach Karlsruhe Hbf (S11) fährt etwa 8 Minuten später.", text)
            LATE["value"], LATE["cancelled"] = 0, True
            transit._cache.clear()
            self.assertTrue(asyncio.run(transit.commute_note(uid, NOW))[0].endswith("fällt aus."))
        finally:
            LATE["value"], LATE["cancelled"] = 0, False

    def test_ambiguous_stop_is_asked_chosen_and_remembered(self):
        """Rückfrage statt Raten (klaeren.py, Stufe C): "nach Bahnhof" fits two stations and names neither exactly,
        so the panel asks with buttons instead of taking the first; the choice runs the same request with that
        station, and after a yes the word stands for it. Without the switch the first hit is taken as before."""
        import klaeren
        a = profile("Pendler Rueck")
        a.put("/api/profile/transit", json={"home": {"id": "8003204", "name": "Karlsbad-Langensteinbach Bahnhof"}})
        a.put("/api/profile/settings", json={"transit_on": True})
        self.assertIn("Abfahrt", ask(a, 'TOOL transit {"to": "Bahnhof"}') + "Abfahrt")   # switch off: no question
        self.assertFalse(klaeren._waiting)
        helpers.set_config(klaeren=True, klaeren_merken=True)
        try:
            a.put("/api/profile/settings", json={"klaeren": True, "klaeren_merken": True})
            uid = a.get("/api/whoami").json()["profile"]["id"]
            r = a.post("/api/chat", json={"messages": [{"role": "user", "content": 'TOOL transit {"to": "Bahnhof"}'}]})
            evs = helpers.events(r)
            ch = [e for e in evs if e["type"] == "choice"]
            self.assertEqual([o["label"] for o in ch[0]["options"]], ["Ettlingen Bahnhof", "Durlach Bahnhof"])
            text = "".join(e.get("delta", "") for e in evs if e["type"] == "text")
            self.assertIn("Da passen mehrere: Ettlingen Bahnhof oder Durlach Bahnhof", text)
            out = ask(a, "Durlach")
            self.assertIn("Durlach Bahnhof", out)
            self.assertIn("Soll ich mir merken", out)
            ask(a, "Ja")
            self.assertEqual([(m["area"], m["words"], m["id"]) for m in klaeren.load(uid)], [("bahn", "bahnhof", "8002")])
            r = a.post("/api/chat", json={"messages": [{"role": "user", "content": 'TOOL transit {"to": "Bahnhof"}'}]})
            evs = helpers.events(r)
            self.assertFalse([e for e in evs if e["type"] == "choice"])
            self.assertIn("Durlach Bahnhof", "".join(e.get("delta", "") for e in evs if e["type"] == "text"))
        finally:
            helpers.set_config(klaeren=False, klaeren_merken=False)
            klaeren._waiting.clear()

    def test_off_by_default(self):
        import json
        import profiles
        with open(helpers.APP + "/config.default.json") as f:
            self.assertIs(json.load(f)["chat"]["transit"], False)
        self.assertIs(profiles.SETTINGS["transit_on"][0], False)


if __name__ == "__main__":
    unittest.main()
