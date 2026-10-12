"""Read-only GitHub token (ghtoken.py): only the main admin sets it with a fresh code, it lies sealed in the vault,
is never shown, goes only to https://api.github.com, and a refused token (401) makes the Spark ask without it
again instead of failing. GitHub is faked here; no test depends on the time of day."""
import asyncio
import json
import os
import unittest

import httpx

from tests import helpers

helpers.start()
import panel  # noqa: E402
import ghtoken  # noqa: E402
import profiles  # noqa: E402
import stufen  # noqa: E402
import vault  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

HOME = ("192.168.178.20", 50000)
TOKEN = "github_pat_" + "Z9y8" * 20
SEEN = []


def gh(request):
    SEEN.append((request.url.host, request.url.path, request.headers.get("authorization")))
    if request.url.path == "/rate_limit":
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={})
        return httpx.Response(200, json={"resources": {"core": {"limit": 5000}}},
                              headers={"github-authentication-token-expiration": "2027-10-12 10:00:00 UTC"})
    return httpx.Response(200, json={})


async def fake_client():
    return httpx.AsyncClient(transport=httpx.MockTransport(gh))


def admin():
    c = TestClient(panel.app, client=HOME)
    assert c.post("/api/login", json={"password": "secret-admin"}).status_code == 200
    return c


class Base(unittest.TestCase):
    def setUp(self):
        self.real = ghtoken._client
        ghtoken._client = fake_client
        ghtoken.drop()
        SEEN.clear()

    def tearDown(self):
        ghtoken._client = self.real
        ghtoken.drop()


class Token(Base):
    def test_only_fine_grained_sealed_and_never_shown(self):
        a = admin()
        self.assertEqual(a.put("/api/admin/ghtoken", json={"token": "ghp_" + "x" * 36}).status_code, 400)
        r = a.put("/api/admin/ghtoken", json={"token": TOKEN})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["ok"], r.json()["limit"], r.json()["until"]), (True, 5000, "2027-10-12"))
        self.assertNotIn(TOKEN, json.dumps(r.json()))
        self.assertNotIn(TOKEN, json.dumps(a.get("/api/admin/ghtoken").json()))
        with open(ghtoken.TOKEN_FILE) as f:
            raw = f.read()
        self.assertNotIn(TOKEN, raw)
        self.assertTrue(json.loads(raw)["token"].startswith(vault.PREFIX))
        self.assertEqual(oct(os.stat(ghtoken.TOKEN_FILE).st_mode & 0o777), "0o600")
        self.assertEqual(a.delete("/api/admin/ghtoken").json()["set"], False)

    def test_not_from_profiles_guests_or_apps(self):
        c = TestClient(panel.app, client=HOME)
        self.assertIn(c.put("/api/admin/ghtoken", json={"token": TOKEN}).status_code, (401, 403))
        self.assertIn(c.get("/api/admin/ghtoken").status_code, (401, 403))
        a = admin()
        uid = a.post("/api/admin/profiles", json={"name": "GhTom", "pin": "1234"}).json().get("id")
        if uid:
            d = TestClient(panel.app, client=HOME)
            d.headers[profiles.DEVICE_HEADER] = profiles.add_device("GhTom App", uid, scope="app")
            self.assertIn(d.put("/api/admin/ghtoken", json={"token": TOKEN}).status_code, (401, 403))
        self.assertFalse(ghtoken._token())
        self.assertIn(("PUT", "/api/admin/ghtoken"), stufen.LIST)

    def test_goes_only_to_the_github_api(self):
        ghtoken.save(TOKEN)
        self.assertEqual(ghtoken.auth_header("https://api.github.com/repos/x/y/releases"), {"Authorization": f"Bearer {TOKEN}"})
        for url in ("https://github.com/x/y/releases/download/a.bin", "https://objects.githubusercontent.com/a",
                    "https://api.github.com.example.org/repos", "http://api.github.com/repos", "http://127.0.0.1:9/repos", ""):
            self.assertEqual(ghtoken.auth_header(url), {}, url)
        ghtoken.drop()
        self.assertEqual(ghtoken.auth_header("https://api.github.com/repos/x/y"), {})
        self.assertEqual(ghtoken.used(), "ohne Token")

    def test_refused_token_asks_without_it(self):
        ghtoken.save(TOKEN)
        asked = []

        class C:
            async def get(self, url, headers=None, **kw):
                asked.append(dict(headers or {}))
                return httpx.Response(401 if "Authorization" in (headers or {}) else 200, json={})
        r = asyncio.run(ghtoken.get(C(), "https://api.github.com/repos/x/y/releases", headers={"Accept": "a"}))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(asked, [{"Accept": "a", "Authorization": f"Bearer {TOKEN}"}, {"Accept": "a"}])
        self.assertEqual(ghtoken.used(), "Token abgelehnt")
        asyncio.run(ghtoken.get(C(), "https://api.github.com/repos/x/y/releases"))
        self.assertEqual(asked[-1], {})          # no more tries with it until a new one is saved
        ghtoken.save(TOKEN)
        self.assertEqual(ghtoken.used(), "mit Token")

    def test_in_the_backup_sealed(self):
        import backup
        self.assertIn("github-token.json", backup.STATE_FILES)


if __name__ == "__main__":
    unittest.main()
