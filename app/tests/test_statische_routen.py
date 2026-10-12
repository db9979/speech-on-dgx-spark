"""Every static route of the panel answers (V01.0.442). Since .406 /manifest.webmanifest, /apple-touch-icon.png and
/favicon.ico called static_file() without the request and failed with 500 on every fetch; nothing noticed it.

Run:  python -m unittest discover -s app/tests -t app     (from the repository root)
"""
import os
import unittest

from tests import helpers

helpers.start()
import panel  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


class StaticRoutes(unittest.TestCase):
    def setUp(self):
        helpers.set_config(public=True)
        self.guest = TestClient(panel.app, raise_server_exceptions=False)

    def test_aliases_of_public_files(self):
        for path, media in (("/manifest.webmanifest", "application/manifest+json"),
                            ("/apple-touch-icon.png", "image/png"), ("/favicon.ico", "image/png")):
            r = self.guest.get(path)
            self.assertEqual(r.status_code, 200, path)
            self.assertTrue(r.headers["content-type"].startswith(media), path)
            self.assertTrue(r.content, path)

    def test_every_public_file_styles_and_scripts(self):
        names = list(panel.PUBLIC_FILES) + [n for n in os.listdir(panel.STATIC) if n.endswith(".css")]
        for name in names:
            self.assertEqual(self.guest.get("/static/" + name).status_code, 200, name)
        for name in os.listdir(os.path.join(panel.STATIC, "js")):
            if name.endswith(".js"):
                self.assertEqual(self.guest.get("/static/js/" + name).status_code, 200, name)

    def test_page_links_resolve(self):
        page = self.guest.get("/").text
        for href in ("/manifest.webmanifest", "/apple-touch-icon.png"):
            if href in page:
                self.assertEqual(self.guest.get(href).status_code, 200, href)

    def test_no_route_without_parameters_crashes(self):
        """Every GET route without a path parameter: as a guest it may say no (401/403/404), never fail (500)."""
        for route in panel.app.routes:
            path = getattr(route, "path", "")
            if "GET" not in (getattr(route, "methods", None) or ()) or "{" in path or path.startswith("/api/"):
                continue
            with self.subTest(path=path):
                self.assertLess(self.guest.get(path).status_code, 500, path)


if __name__ == "__main__":
    unittest.main()
