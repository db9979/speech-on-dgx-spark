"""Rückgängig im Admin-Protokoll (undo.py, V01.0.286): saved changes keep their old values, never secrets; undoing
puts back only what is still as that change left it, through the same checks as saving; admins only."""
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
import undo  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def save(**chat):
    cfg = ADMIN.get("/api/config").json()
    cfg["chat"].update(chat)
    r = ADMIN.put("/api/config", json=cfg)
    assert r.status_code == 200, r.text
    return ADMIN.get("/api/admin/undo").json()["items"][0]


class Undo(unittest.TestCase):
    def setUp(self):
        helpers.set_config(weather=False, transit=False)

    def tearDown(self):
        helpers.set_config(weather=False, transit=False)

    def test_change_kept_and_undone(self):
        x = save(weather=True)
        self.assertEqual(x["changes"], [{"k": "chat.weather", "old": False, "new": True}])
        self.assertEqual(x["by"], "main")
        r = ADMIN.post(f"/api/admin/undo/{x['id']}")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["undone"], ["chat.weather"])
        self.assertIs(ADMIN.get("/api/config").json()["chat"]["weather"], False)
        self.assertEqual(ADMIN.post(f"/api/admin/undo/{x['id']}").status_code, 409)     # once
        items = ADMIN.get("/api/admin/undo").json()["items"]
        self.assertTrue(next(i for i in items if i["id"] == x["id"])["undone"])
        self.assertEqual(items[0]["changes"], [{"k": "chat.weather", "old": True, "new": False}])  # the undo itself

    def test_a_value_changed_since_stays(self):
        x = save(weather=True, transit=True)
        save(transit=False)
        r = ADMIN.post(f"/api/admin/undo/{x['id']}").json()
        self.assertEqual((r["undone"], r["kept"]), (["chat.weather"], ["chat.transit"]))
        y = save(weather=True)
        save(weather=False)
        self.assertEqual(ADMIN.post(f"/api/admin/undo/{y['id']}").status_code, 409)     # nothing left to undo

    def test_secrets_and_panel_never_kept(self):
        old = {"chat": {"llm_key": "a", "llm_url": "http://a", "telegram_token": "x", "system_prompt": "kurz", "weather": False},
               "panel": {"port": 31080}, "api": {"key": "k"}}
        new = {"chat": {"llm_key": "b", "llm_url": "http://b", "telegram_token": "y", "system_prompt": "x" * 400, "weather": True},
               "panel": {"port": 31081}, "api": {"key": "j"}}
        sens = [("chat", "llm_url")]
        self.assertEqual(undo.diff(old, new, sens), [{"k": "chat.weather", "old": False, "new": True}])
        item = {"changes": [{"k": "chat.llm_key", "old": "a", "new": "b"}, {"k": "panel.port", "old": 1, "new": 31081}]}
        cfg, done, kept = undo.revert(item, new, sens)
        self.assertEqual((done, cfg["chat"]["llm_key"], cfg["panel"]["port"]), ([], "b", 31081))

    def test_the_app_switches_are_kept_too(self):
        r = ADMIN.put("/api/admin/switches", json={"key": "weather", "on": True})
        self.assertEqual(r.status_code, 200, r.text)
        x = ADMIN.get("/api/admin/undo").json()["items"][0]
        self.assertEqual(x["changes"], [{"k": "chat.weather", "old": False, "new": True}])

    def test_only_admins(self):
        x = save(weather=True)
        guest = TestClient(panel.app)
        self.assertEqual(guest.get("/api/admin/undo").status_code, 401)
        self.assertEqual(guest.post(f"/api/admin/undo/{x['id']}").status_code, 401)
        self.assertEqual(ADMIN.post("/api/admin/undo/../../x").status_code, 404)
        self.assertEqual(ADMIN.post("/api/admin/undo/zzzzzzzzzzzz").status_code, 404)

    def test_keeps_the_last_50(self):
        for i in range(undo.KEEP + 3):
            undo.record({"chat": {"weather": False}}, {"chat": {"weather": True}}, "main")
        self.assertEqual(len(undo.listing()), undo.KEEP)
