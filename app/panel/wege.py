"""Ways into the panel in texts that leave it ("Einschalten unter Ich → Telegram"): Telegram messages, push notes.

The panel turns such a way into a Sprung-Link by itself (static/js/way.js). Outside the panel the app, the Begleiter
or Telegram opens `<panel>/#weg=<way>` instead; way.js reads the hash and jumps there. The way here is generous (up to
the end of the clause): the panel follows only the steps it finds on the page, a lower-case word is an action.
Only navigation: nothing in a #weg= link switches, saves or sends anything.
"""
import re
from urllib.parse import quote

ROOTS = ("Einstellungen", "Funktionen", "Zustand", "Personen und Geräte", "Ich",
         "Settings", "Features", "Status", "People and devices", "Me",
         # the pages of their own (way.js WAY_ROOTS, OWN_PAGES): "E-Mail → Für dich", "Kalender → Einstellungen"
         "Kalender", "Calendar", "E-Mail", "E-mail", "Kontakte", "Contacts", "Wissensbuch", "Knowledge book")
# a root followed by an arrow; not "Mein Notaus", not a way inside another program's way ("Open WebUI → Einstellungen")
WAY = re.compile(r"(?<![\w-])(?<!Mein )(?<!My )(?<!→ )(?:" + "|".join(map(re.escape, ROOTS)) + r")\s*→[^\n.;:()!?]{1,160}")
MAX = 200
URL = re.compile(r"https?://[A-Za-z0-9.\-]+(?::\d{1,5})?/?")


def find(text):
    """The first way in a text, or ""."""
    m = WAY.search(str(text or "")[:6000])
    return m.group(0).strip(" ,–-")[:MAX] if m else ""


def link(base, way):
    """`<base>/#weg=<way>` for a checked base address (http(s)://name[:port]), else ""."""
    base = str(base or "").strip()
    if not way or not URL.fullmatch(base):
        return ""
    return base.rstrip("/") + "/#weg=" + quote(way[:MAX], safe="")
