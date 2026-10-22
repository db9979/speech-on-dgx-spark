"""Spielprofile „Nur Spiel“ (plan krisenspiel/plan-netzduell.md, Netzduell Schritt 1, Dominik 2026-10-22: „user ohne
den agent auch ein spielprofile zu erstellen, so das diese nur das spiel spielen können“).

A profile the admin marks „Nur Krisenspiel“ (profiles: "nur_spiel") may only play: features.blocked() blocks every
function but the Krisenspiel and its parts (and the second sign-in step), and the panel's middleware lets such a
profile reach only the paths in ALLOW, every other request of it (also with a device key, over MCP, Telegram or the
phone) is refused with 403 before any route runs. Never the assistant, a model, a tool, memory or a device.
The admin turns it into a normal profile or back (Personen und Geräte → the profile); an admin profile never is one.
"""
import re

SPIEL = "krisenspiel"           # the function such a profile keeps, with every function built on it
# what a game-only profile may reach: the page and its files (GET), signing in and out, its own security, the game
ALLOW = ((("GET",), r"/"), (("GET",), r"/static/.+"), (("GET",), r"/(?:favicon\.ico|apple-touch-icon\.png|manifest\.webmanifest|sw\.js)"),
         (("GET",), r"/api/(?:whoami|notaus)"), (("POST",), r"/api/profile/(?:login|logout|logout-all)"),
         (("GET", "POST", "DELETE"), r"/api/profile/(?:mfa|sessions)(?:/[A-Za-z0-9_.-]+)*"),
         (("GET", "POST", "DELETE"), r"/api/profile/krisenspiel(?:/[A-Za-z0-9_.-]+)*"))
_RX = [(m, re.compile(p)) for m, p in ALLOW]
DETAIL = "Dieses Profil ist nur für das Krisenspiel."


def may(method, path):
    """A game-only profile may send this request (fixed list ALLOW, the whole path must match)."""
    return any(method in m and rx.fullmatch(path) for m, rx in _RX)


def gate(request):
    """None, or the refusal for a request of a game-only profile outside ALLOW (panel.py middleware)."""
    import profiles
    prof = profiles.current(request)
    if not prof or not profiles.nur_spiel(prof["id"]) or may(request.method, request.url.path):
        return None
    area = request.url.path.split("/")[2] if request.url.path.startswith("/api/") and request.url.path.count("/") >= 2 else "seite"
    print(f"spiel: nur spiel gesperrt | {re.sub(r'[^a-z]', '', area.lower())[:20] or 'pfad'}", flush=True)
    return 403, DETAIL
