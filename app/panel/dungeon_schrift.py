"""KI-Dungeon-Master: Schriftstücke zum Anfassen (D&D idea 3, Dominik 2026-10-25 „1-12 reihenfolge bestimmst du wie du
alles umsetzten kannst.“; handouts for all, some or nobody as in NeonBrasil/DM-Dungeon-Music, BigJk/snd and
Hinnful/Evermist, all MIT, own code).

When the heroes find a letter, a wanted poster, a riddle or a diary page, the narration reports it in „schriftstueck“
(at most one a turn): title, its text as it stands (at most TEXT_MAX characters), its kind (ARTEN) and who wrote it. The
panel takes it by fixed rules (check: plain text, the round's limits and the list „nie“, the lengths) and keeps it in the
round (rd["schrift"], at most SCHRIFT_MAX); the table shows it as a parchment at its turn and in the tab „Schriftstücke“.
Who sees it is the host's choice (set): every seat („alle“, the default), one seat (its pid: a secret note) or nobody
(„niemand“); the one sight filter keeps the text from everyone else (view, GEHEIM["schrift"] in dungeon_sicht).
The model keeps the last SCHRIFT_FAKTEN in its facts, so the story stays consistent; it never decides who sees them.

Off by default: the admin's switch dungeonschrift (features.py, chat.dungeon_schrift) for the round's host.
Journal: fixed words and numbers („dungeon: schrift | …“), Live only counts.
"""
import features
from common import DayCounter

KEY = "dungeonschrift"
ARTEN = ("brief", "steckbrief", "vers", "tagebuch", "notiz", "inschrift")
ZEICHEN = {"brief": "✉", "steckbrief": "📜", "vers": "🪶", "tagebuch": "📖", "notiz": "🗒", "inschrift": "🪨"}
TITEL_MAX = 60
TEXT_MAX = 600
TEXT_MIN = 20
VON_MAX = 40
SCHRIFT_MAX = 40           # writings a round keeps
SCHRIFT_FAKTEN = 3         # the newest ones the model reads in its facts
SICHT = ("alle", "niemand")   # or a seat's pid
# a writing counts only when the narration shows one (Anker-Tabelle, Dominik 2026-10-28 „es kommen zu viele fehler“):
# a word of these (parts of words count: „Briefumschlag“, „Pergamentrolle“) or the writing's title in the narration
WORTE = ("brief", "vers", "gedicht", "tagebuch", "notiz", "inschrift", "schrift", "zettel", "pergament", "rolle", "seite",
         "buch", "geschrieben", "letter", "poster", "verse", "poem", "diary", "journal", "note", "inscription", "writ",
         "scroll", "parchment", "page", "book")

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["titel", "text", "art"], "properties": {
    "titel": {"type": "string", "maxLength": TITEL_MAX + 20}, "text": {"type": "string", "maxLength": TEXT_MAX + 100},
    "art": {"type": "string", "enum": list(ARTEN)}, "von": {"type": "string", "maxLength": VON_MAX + 20}}}
AUFGABE = {
    "de": (" Finden die Helden in deiner Erzählung etwas Geschriebenes (einen Brief, einen Steckbrief, einen Vers, eine "
           "Tagebuchseite, eine Notiz, eine Inschrift), gibst du es in schriftstueck an: titel, den text so, wie er "
           "dasteht (höchstens 600 Zeichen), art und von (wer es schrieb, leer wenn unbekannt); höchstens eines je Zug."),
    "en": (" When the heroes find something written in your narration (a letter, a wanted poster, a verse, a diary page, a "
           "note, an inscription), give it in schriftstueck: titel, the text as it stands (at most 600 characters), art and "
           "von (who wrote it, empty when unknown); at most one a turn."),
}
GEFUNDEN = {"de": " schriftstuecke sind die zuletzt gefundenen; bleib bei dem, was dort steht.",   # only with writings (T20)
            "en": " schriftstuecke are the ones found last; keep to what stands there."}

_day = DayCounter(gefunden=0, verworfen=0, geheim=0)


def on(rd):
    return bool(rd.get("owner")) and features.allowed(KEY, rd["owner"])


def task(rd, lang):
    return AUFGABE[lang] + (GEFUNDEN[lang] if facts(rd) else "") if on(rd) else ""


def check(dm, r, rd, obj, erzaehlung):
    """The narration's writing by fixed rules: None when there is none, it is off, too short, refused or the narration
    shows no writing (WORTE, its title)."""
    if not isinstance(obj, dict) or not on(rd):
        return None
    titel, text, von = dm.plain(obj.get("titel"), TITEL_MAX), dm.plain(obj.get("text"), TEXT_MAX - 2), dm.plain(obj.get("von"), VON_MAX)
    if obj.get("art") not in ARTEN or not titel or len(text) < TEXT_MIN or dm.bad_words(r, rd, " ".join((titel, text, von))):
        _day.bump("verworfen")
        print("dungeon: schrift | verworfen", flush=True)
        return None
    low = str(erzaehlung or "").lower()
    if not any(w in low for w in WORTE) and not dm.erz.foe_named(titel, erzaehlung):
        _day.bump("verworfen")
        print("dungeon: schrift | nicht erzaehlt", flush=True)
        return None
    return {"titel": titel, "text": text, "art": obj["art"], "von": von}


def learn(dm, rd, story):
    """A writing the narration found goes into the round, for every seat (the host may change that, set)."""
    s = (story or {}).get("schrift")
    if not s:
        return
    alle = rd.setdefault("schrift", [])
    sid = f"s{rd.get('zug', 0)}"
    while any(x["id"] == sid for x in alle):
        sid += "x"
    alle.append(dict(s, id=sid, zug=rd.get("zug", 0), sicht="alle"))
    del alle[:-SCHRIFT_MAX]
    dm._log(rd, "schrift", sid=sid)
    _day.bump("gefunden")
    print(f"dungeon: schrift | gefunden | {s['art']}", flush=True)


def set_sight(rd, sid, sicht):
    """The host's choice who sees a writing: alle, niemand or one seat with a hero."""
    x = next((x for x in rd.get("schrift") or [] if x["id"] == sid), None) if isinstance(sid, str) else None
    ok = isinstance(sicht, str) and (sicht in SICHT or (rd["plaetze"].get(sicht) or {}).get("held"))
    if not x or not ok:
        print("dungeon: schrift | sicht | abgelehnt", flush=True)
        raise ValueError("eingabe")
    x["sicht"] = sicht
    if sicht not in SICHT:
        _day.bump("geheim")
    print(f"dungeon: schrift | sicht | {sicht if sicht in SICHT else 'ein platz'}", flush=True)


def view(rd, pid, host):
    """The writings a viewer may see, newest last: the host all of them with who sees them, a seat those for every
    seat and its own (never the others' secret ones); [] without any."""
    names = {p: (x.get("held") or {}).get("name", "") for p, x in rd["plaetze"].items()}
    out = []
    for x in rd.get("schrift") or []:
        if host:
            out.append(dict(x, zeichen=ZEICHEN.get(x["art"], ""), fuer=names.get(x["sicht"], "") if x["sicht"] not in SICHT else ""))
        elif x["sicht"] == "alle" or x["sicht"] == pid:
            out.append({k: x[k] for k in ("id", "zug", "titel", "text", "art", "von")} | {"zeichen": ZEICHEN.get(x["art"], ""), "geheim": x["sicht"] == pid})
    return out


def facts(rd):
    """The newest writings for the model (it wrote them; who sees them is not its business)."""
    s = (rd.get("schrift") or [])[-SCHRIFT_FAKTEN:]
    return {"schriftstuecke": [{k: x[k] for k in ("titel", "text", "von")} for x in s]} if s and on(rd) else {}


def for_live():
    """Numbers only: writings found, refused, made secret today."""
    t = _day.counts()
    return {k: t[k] for k in ("gefunden", "verworfen", "geheim")}
