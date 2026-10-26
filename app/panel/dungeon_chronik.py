"""KI-Dungeon-Master: Chronikbuch zum Blättern (D&D idea 11, Dominik 2026-10-25 „1-12 reihenfolge bestimmst du wie du
alles umsetzten kannst.“; ideas of rpgtex/DND-5e-LaTeX-Template, MIT, and canismarko/dungeon-sheets, GPL-3, only as
ideas; own code and own layout, never the look of the official books).

When the host closes a chapter (dungeon.end_chapter), the panel writes one page of the campaign's book from what the
round already holds (page): the chapter's number and title, its turns, the cover (the chapter's last scene picture,
dungeon.cover), the heroes with people, class, level and their scars (D&D idea 8), the titles of the evening (idea 1)
and the writings every seat could read (idea 3; one for a single seat stays out), the places of the map; „Bisher
geschah“ comes onto the page once the model or the host has written it (story). The model writes nothing new for it.
The book is the host's own: only the owner of the campaign sees it (the profile's campaign file), turns its pages,
gets it as a PDF made on the Spark (pdf, fpdf2 with the panel's own fonts; nothing leaves the LAN) and deletes a page.
At most BUCH_MAX pages a campaign, the oldest goes first.

The log entry „kapitel_ende“ {kapitel} of end_chapter is the one place a chapter's end is told (the bard's song of the
music thread, dungeon_lied, waits for it); it comes with or without this switch.

Off by default: the admin's switch dungeonchronik (features.py, chat.dungeon_chronik) for the campaign's owner.
Journal: fixed words and numbers („dungeon: chronik | …“), Live only counts.

    GET  /api/profile/dungeon/kampagne/{kid}/chronik           the book's pages
    GET  /api/profile/dungeon/kampagne/{kid}/chronik.pdf       the book as a PDF
    POST /api/profile/dungeon/kampagne/{kid}/chronik/loeschen  {kapitel}: one page away
"""
import asyncio
import io

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

import features
import guard
from common import DayCounter
from core import assistant, browser_profile, json_body, own_profile

router = APIRouter()
KEY = "dungeonchronik"
BUCH_MAX = 30
SCHRIFT_MAX = 6            # writings a page keeps
TEXT_MAX = 600
ORTE_MAX = 12
BODY = 256

_day = DayCounter(seiten=0, pdf=0, geloescht=0, abgelehnt=0)


def page(dm, r, rd, c, now):
    """Inside end_chapter: the chapter's page from what the round holds, into the campaign's book c["buch"]."""
    if not rd.get("owner") or not features.allowed(KEY, rd["owner"]):
        return None
    import dungeon_karte
    li = 1 if rd.get("lang") == "en" else 0
    n = rd.get("kapitel", 1)
    helden = []
    for _, p in dm.seated(rd):
        h = p["held"]
        v, k = dm._by(r, "voelker").get(h.get("volk")) or {}, dm._by(r, "klassen").get(h.get("klasse")) or {}
        helden.append({"name": h["name"], "volk": (v.get("name") or ["", ""])[li], "klasse": (k.get("name") or ["", ""])[li],
                       "stufe": h.get("stufe", 1), "narben": [x["t"][li] for x in h.get("narben") or [] if x.get("t")][:8]})
    schrift = [{"titel": x.get("titel", ""), "text": str(x.get("text", ""))[:TEXT_MAX]}
               for x in rd.get("schrift") or [] if x.get("sicht") == "alle"][:SCHRIFT_MAX]
    seite = {"kapitel": n, "titel": rd.get("titel", ""), "zuege": max(0, rd.get("zug", 1) - 1), "t": now, "helden": helden,
             "ehrungen": [{"titel": x["titel"], "name": x["name"]} for x in rd.get("ehrung") or []],
             "schrift": schrift, "orte": dungeon_karte.names(rd)[-ORTE_MAX:], "bisher": ""}
    c["buch"] = ([x for x in c.get("buch") or [] if x.get("kapitel") != n] + [seite])[-BUCH_MAX:]
    _day.bump("seiten")
    print(f"dungeon: chronik | seite | {len(helden)} helden | {len(schrift)} schriften", flush=True)
    return seite


def story(c, text):
    """„Bisher geschah“ written for the last chapter (dungeon.summarize, dungeon.edit_summary): onto its page."""
    for x in c.get("buch") or []:
        if x.get("kapitel") == c.get("kapitel"):
            x["bisher"] = text


def view(c, kid):
    """The book's pages, oldest first, each with its cover's address when the campaign still keeps it."""
    have = set(c.get("titelbilder") or [])
    return {"titel": c.get("titel", ""), "seiten": [dict(x, bild=f"/api/profile/dungeon/kampagne/{kid}/bild/{x['kapitel']}"
                                                           if x["kapitel"] in have else "") for x in c.get("buch") or []]}


def drop(c, kapitel):
    if not isinstance(kapitel, int) or isinstance(kapitel, bool) or not any(x.get("kapitel") == kapitel for x in c.get("buch") or []):
        raise LookupError("seite")
    c["buch"] = [x for x in c["buch"] if x.get("kapitel") != kapitel]


def pdf(dm, c, kid, lang):
    """The book as a PDF made on the Spark: a title page, then per chapter its cover, „Bisher geschah“, the heroes, the
    titles, the writings and the places."""
    try:
        from fpdf import FPDF
    except ImportError:
        raise LookupError("pdf")
    import docrender
    en = lang == "en"
    reg, bold = docrender._font_files()
    fam = "DejaVu" if reg else "Helvetica"

    def tx(s):
        s = str(s or "")
        return s if reg else "".join(docrender.LATIN1.get(ch, ch) for ch in s).encode("latin-1", "replace").decode("latin-1")
    doc = FPDF(format="A4")
    doc.set_auto_page_break(True, margin=18)
    doc.set_margins(20, 18, 20)
    if reg:
        doc.add_font("DejaVu", "", reg)
        doc.add_font("DejaVu", "B", bold)
    doc.set_title(tx(c.get("titel"))[:200])
    doc.set_creator("Spark")
    doc.add_page()
    doc.set_font(fam, "B", 26)
    doc.ln(60)
    doc.multi_cell(0, 12, tx(c.get("titel")), align="C", new_x="LMARGIN", new_y="NEXT")
    doc.set_font(fam, "", 13)
    doc.multi_cell(0, 8, tx("Chronik" if not en else "Chronicle"), align="C", new_x="LMARGIN", new_y="NEXT")
    have = set(c.get("titelbilder") or [])

    def head(s):
        doc.ln(3)
        doc.set_font(fam, "B", 12)
        doc.multi_cell(0, 7, tx(s), new_x="LMARGIN", new_y="NEXT")
        doc.set_font(fam, "", 11)
    for x in c.get("buch") or []:
        doc.add_page()
        doc.set_font(fam, "B", 18)
        doc.multi_cell(0, 10, tx(f"{'Kapitel' if not en else 'Chapter'} {x['kapitel']} · {x['titel']}"), new_x="LMARGIN", new_y="NEXT")
        doc.set_font(fam, "", 10)
        doc.multi_cell(0, 6, tx(f"{x['zuege']} {'Züge' if not en else 'turns'}"), new_x="LMARGIN", new_y="NEXT")
        if x["kapitel"] in have:
            try:
                doc.image(io.BytesIO(dm._png(f"{kid}-{x['kapitel']}")), w=doc.epw * 0.8, x=doc.l_margin + doc.epw * 0.1)
            except (LookupError, OSError, ValueError, RuntimeError):
                pass
        if x.get("bisher"):
            head("Bisher geschah" if not en else "The story so far")
            doc.multi_cell(0, 6, tx(x["bisher"]), new_x="LMARGIN", new_y="NEXT")
        head("Helden" if not en else "Heroes")
        for h in x["helden"]:
            narben = f" · {'Narben' if not en else 'scars'}: " + ", ".join(h["narben"]) if h["narben"] else ""
            doc.multi_cell(0, 6, tx(f"{h['name']} · {h['volk']} {h['klasse']}, {'Stufe' if not en else 'level'} {h['stufe']}{narben}"), new_x="LMARGIN", new_y="NEXT")
        if x["ehrungen"]:
            head("Ehrungen des Abends" if not en else "Honours of the evening")
            for e in x["ehrungen"]:
                doc.multi_cell(0, 6, tx(f"{e['titel']}: {e['name']}"), new_x="LMARGIN", new_y="NEXT")
        for s in x["schrift"]:
            head(s["titel"] or ("Schriftstück" if not en else "Writing"))
            doc.multi_cell(0, 6, tx(s["text"]), new_x="LMARGIN", new_y="NEXT")
        if x["orte"]:
            head("Orte" if not en else "Places")
            doc.multi_cell(0, 6, tx(" → ".join(x["orte"])), new_x="LMARGIN", new_y="NEXT")
    return bytes(doc.output())


def for_live():
    """Numbers only: pages written, PDFs made, pages deleted, refused requests today."""
    t = _day.counts()
    return {k: t[k] for k in ("seiten", "pdf", "geloescht", "abgelehnt")}


# ---------------------------------------------------------------- routes
def _book(dm, uid, kid):
    if not features.allowed(KEY, uid):
        raise LookupError("chronik aus")
    return dm._campaign(uid, kid)


async def _run(go):
    import dungeon as dm
    try:
        return await asyncio.to_thread(go)
    except dm.KNOWN as e:
        _day.bump("abgelehnt")
        print(f"dungeon: chronik | abgelehnt | {type(e).__name__}", flush=True)
        raise dm._http(e)


@router.get("/api/profile/dungeon/kampagne/{kid}/chronik", dependencies=[Depends(assistant)])
async def chronik(kid: str, request: Request, prof=Depends(own_profile)):
    """The campaign's book: {titel, seiten}."""
    import dungeon as dm
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeon", uid)
    out = await _run(lambda: view(_book(dm, uid, kid)[1], kid))
    print(f"dungeon: chronik | ansehen | {len(out['seiten'])} seiten", flush=True)
    return out


@router.get("/api/profile/dungeon/kampagne/{kid}/chronik.pdf", dependencies=[Depends(assistant)])
async def chronik_pdf(kid: str, request: Request, prof=Depends(own_profile)):
    """The campaign's book as a PDF, made on the Spark."""
    import dungeon as dm
    uid = prof["id"]
    dm._need(uid)
    guard.limit(request, "dungeonpdf", uid)
    lang = "en" if request.query_params.get("lang") == "en" else "de"
    data = await _run(lambda: pdf(dm, _book(dm, uid, kid)[1], kid, lang))
    _day.bump("pdf")
    print(f"dungeon: chronik | pdf | {len(data) // 1024} kb", flush=True)
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="chronik.pdf"',
                                                                 "Cache-Control": "no-store"})


@router.post("/api/profile/dungeon/kampagne/{kid}/chronik/loeschen", dependencies=[Depends(assistant)])
async def chronik_loeschen(kid: str, request: Request, prof=Depends(browser_profile)):
    """{kapitel}: one page of the book away."""
    import dungeon as dm
    uid = prof["id"]
    guard.limit(request, "dungeon", uid)
    b = await json_body(request, BODY)

    def go():
        with dm._lock:
            ks, c = _book(dm, uid, kid)
            drop(c, b.get("kapitel"))
            dm._save_campaigns(uid, ks)
            return view(c, kid)
    out = await _run(go)
    _day.bump("geloescht")
    print("dungeon: chronik | geloescht", flush=True)
    return out
