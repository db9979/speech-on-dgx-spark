"""Roles: each profile keeps a few ways the assistant should answer ("Butler: höflich und trocken",
"Erklärbär: erklär alles wie für Kinder") and switches between them by voice ("Sei jetzt der
Butler", "Wechsle zur Rolle Erklärbär", "Sei wieder normal", "Welche Rollen hast du?").

The panel recognizes these sentences with fixed rules in the person's own latest message (never in
outside text or in what the model wrote) and only for a name the profile saved itself; the model
then only says the result. A role changes the tone like the own style, never the rules for tools,
smart home, code word and data. Off until the admin allows it (chat.roles) and the profile switches
it on (setting roles_on). Guests and a voice that is not the profile's own never.

    settings "roles"  text, one role per line "Name: what it should be like" (at most MAX_ROLES)
    settings "role"   the name of the active role ("" = none)
"""
import re

import profiles

MAX_ROLES = 8
MAX_NAME = 30
MAX_TEXT = 300
INTRO = ("Rolle, die der Nutzer selbst gewählt hat. Sie ändert nur, wie du antwortest (Ton, Blickwinkel, "
         "Schwerpunkt), nie die Regeln für Werkzeuge, Smart Home, Codewort und Daten:\n")

_FILL = r"(?:(?:jetzt|ab jetzt|mal|wieder|bitte|bitte mal|nun|doch)\s+)*"
_ART = r"(?:(?:der|die|das|den|dem|ein|eine|einen|mein|meine|meinen|meinem)\s+)?"
SET = [re.compile(r"^(?:bitte\s+)?(?:sei|werde|spiel|spiele)\s+" + _FILL + _ART + r"(?P<n>.+?)(?:\s+bitte)?$"),
       re.compile(r"^(?:bitte\s+)?(?:wechsle|wechsel|schalte|schalt|geh|gehe)\s+" + _FILL
                  + r"(?:zur|zum|zu|in\s+die|in\s+den|auf\s+die|auf\s+den|auf)\s+(?:rolle\s+|persona\s+)?" + _ART
                  + r"(?P<n>.+?)(?:\s+um)?(?:\s+bitte)?$"),
       re.compile(r"^(?:rolle|persona)\s*:?\s+(?P<n>.+)$")]
RESET = re.compile(r"^(?:bitte\s+)?(?:(?:sei|werde|antworte|sprich|rede)\s+" + _FILL + r"(?:wieder\s+)?normal"
                   r"|(?:zurück\s+)?(?:zur|zum)\s+(?:normalen\s+rolle|normalen|normal|standard)"
                   r"|(?:keine|ohne|normale)\s+rolle(?:\s+mehr)?"
                   r"|rolle\s+(?:aus|beenden|ablegen|zurücksetzen|weg)"
                   r"|(?:beende|beend|verlass|verlasse|leg|lege)\s+(?:die\s+|deine\s+)?rolle(?:\s+ab)?)(?:\s+bitte)?$")
LIST = re.compile(r"^(?:(?:welche|was\s+für)\s+rollen\s+(?:hast|kennst|gibt|kannst)"
                  r"|(?:nenn|nenne|zeig|zeige|sag|sage)\s+(?:mir\s+)?(?:mal\s+)?(?:meine|deine|die)?\s*rollen)\b")


def admin_on(ccfg):
    return bool(ccfg.get("roles", False))


def _key(name):
    """Names compared without case, umlauts written out, only letters and digits."""
    s = str(name or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]", "", s)


def parse(text):
    """[(name, description)] from the profile's text: one "Name: ..." per line, the first MAX_ROLES."""
    out, seen = [], set()
    for line in str(text or "").splitlines():
        if ":" not in line:
            continue
        name, desc = line.split(":", 1)
        name = re.sub(r"[^\w äöüÄÖÜß\-]", "", name).strip()[:MAX_NAME]
        desc = re.sub(r"[\x00-\x1f\x7f]|<<<|>>>", "", desc).strip()[:MAX_TEXT]
        if not name or not desc or _key(name) in seen or not _key(name):
            continue
        seen.add(_key(name))
        out.append((name, desc))
        if len(out) >= MAX_ROLES:
            break
    return out


def valid_text(v):
    return isinstance(v, str) and len(v) <= 1500 and not re.search(r"[\x00-\x09\x0b-\x1f\x7f]|<<<|>>>", v)


def _clean_ask(text):
    s = re.sub(r"\s+", " ", str(text or "")).strip().lower()
    s = re.sub(r"^(?:hey|hallo|ok|okay)?\s*spark\b[\s,:]*", "", s)
    return s.strip(" .!?,;:\"'„“")


def command(text, roles):
    """What the person's own message asks for: ("set", name), ("reset", ""), ("list", "") or None.
    "set" only for a name in roles (so "Sei leise" stays a normal question unless a role is called so)."""
    s = _clean_ask(text)[:200]
    if not s:
        return None
    if LIST.search(s):
        return ("list", "")
    if RESET.fullmatch(s):
        return ("reset", "")
    names = {_key(n): n for n, _ in roles}
    for rx in SET:
        m = rx.fullmatch(s)
        if not m:
            continue
        n = re.sub(r"[-\s]*(?:rolle|persona)$", "", m.group("n")).strip()
        if _key(n) in names:
            return ("set", names[_key(n)])
    return None


def on(ccfg, who, pset, own_browser):
    """Roles may be used in this turn: admin switch, a profile's own voice and browser, its own switch."""
    return bool(admin_on(ccfg) and who and own_browser and pset.get("roles_on"))


def active(pset):
    """(name, description) of the active role, or None."""
    want = _key(pset.get("role"))
    if not want:
        return None
    return next(((n, d) for n, d in parse(pset.get("roles")) if _key(n) == want), None)


def prompt(pset):
    a = active(pset)
    return INTRO + f"„{a[0]}“: {a[1]}" if a else ""


def carry_out(uid, cmd, pset):
    """Does what the command asks (only the profile's own setting "role") and returns the fixed note
    for the model. pset is updated, so the new role already applies to this answer."""
    kind, name = cmd
    roles = parse(pset.get("roles"))
    if kind == "set":
        profiles.save_settings(uid, {"role": name})
        pset["role"] = name
        return f"Rolle gewechselt: Ab jetzt antwortest du als „{name}“. Sag das in einem kurzen Satz, schon in dieser Rolle."
    if kind == "reset":
        was = active(pset)
        profiles.save_settings(uid, {"role": ""})
        pset["role"] = ""
        return ("Rolle beendet: Du antwortest wieder normal." if was else "Es war keine Rolle aktiv; du antwortest normal.") \
            + " Sag das in einem kurzen Satz."
    now = active(pset)
    if not roles:
        return ("Der Nutzer hat noch keine Rollen gespeichert. Sag ihm in einem Satz, dass er sie unter Ich → Gespräch → "
                "Antwort → „Meine Rollen“ anlegt, eine pro Zeile wie „Butler: höflich und trocken“.")
    return ("Gespeicherte Rollen: " + ", ".join(f"„{n}“" for n, _ in roles) + ". Gerade aktiv: "
            + (f"„{now[0]}“" if now else "keine") + ". Nenn sie kurz und sag, dass man mit „Sei jetzt …“ wechselt "
            "und mit „Sei wieder normal“ zurückkommt.")
