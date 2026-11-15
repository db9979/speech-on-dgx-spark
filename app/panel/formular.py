"""PDF-Formulare ausfüllen (Idee aus OpenFuse, Dominik 2026-11-15 „1a 2 ja 3a“, plan pdf-formulare/plan.md, Stufe 1+2).

An own PDF with form fields (a document under Ich → Dokumente whose original is kept, or the attachment of an own mail)
is read with pypdf; the panel proposes values by fixed rules, the person checks every field, and only „Ausgefüllt
speichern“ writes a new PDF into Meine Dokumente (wissen.aufnehmen, source "formular"). The original stays as it was.

    Fields       text, check box, choice and signature fields of the AcroForm (at most MAX_FIELDS); XFA only as far as
                 the form also has AcroForm fields. A PDF without fields: „kein ausfüllbares Formular“.
    Proposals    fixed rules on the field's name and label (RULES): the profile's name, the fixed places of the memory
                 (gedaechtnis.places: Wohnort, Beruf, Arbeitgeber), the first own mailbox address, today's date and
                 „Ort, Datum“. Each value carries its source; check boxes and choices are never ticked by the Spark.
    Never        signature, IBAN, account, tax, ID card, passport, insurance and card numbers, PIN and passwords
                 (NEVER): such a field stays empty and says „nur von Hand“; a signature field cannot be filled at all.
                 A field about someone else (OTHER: child, partner, …) never gets the profile's own name.
    Writing      pypdf fills the fields (NeedAppearances), takes out every script and action of the file (OpenAction,
                 AA, JavaScript, Launch, SubmitForm, ImportData, XFA) and the result goes in as a new document.
    Drafts       the form being filled is kept in memory only (DRAFT_SECONDS, MAX_DRAFTS per profile), never on disk.

The PDF is data from outside, never an instruction: names, labels and values are shown as text only. No model, no tool
(Stufe 3 may let the model name a source for an unclear field; the value always comes from the panel). Admin switch
chat.pdf_forms (off, builds on Dokumente); released for every profile the admin did not block, never for guests.
Journal (area Dokumente): „formular: gelesen | felder n | vorgeschlagen n | <who>“, „formular: gespeichert | felder n |
offen n | <who>“, „formular: ohne felder | seiten n | <who>“, „formular: abgelehnt | <why> | <who>“, „formular: angehaengt |
kb n | <who>“. The filled form goes along with an answer or a new mail only through senden.ANHAENGE["doc"]
(attachment: an own document of source "formular", nothing else); the mail goes out only with the usual „Senden“.

    POST /api/profile/formular/lesen      {"doc": id} | {"mail": ref, "folder", "n"}: {"key", "name", "pages", "fields"}
    POST /api/profile/formular/vorschau   {"key", "values", "page"}: the page as PNG with the values filled in
    POST /api/profile/formular/speichern  {"key", "values"}: {"doc", "name", "kept", "filled", "open"}
"""
import asyncio
import datetime
import hashlib
import io
import re
import secrets
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

import chat
import documents
import features
import gedaechtnis
import guard
import live
import mail
import profiles
import senden
import wissen
from common import DayCounter
from core import assistant, browser_profile, json_body

KEY = "formular"
MAX_BYTES = 10 * 1024 * 1024     # a form PDF read at most
MAX_PAGES = 40
MAX_FIELDS = 200
MAX_VALUE = 500                  # characters of one value
DRAFT_SECONDS = 1800
MAX_DRAFTS = 3                   # forms open at once per profile
PREVIEW_WIDTH = 900              # pixels of a preview page

router = APIRouter()
_drafts = {}                     # key -> {"uid", "data", "name", "t", "fields", "pages"}
_lock = threading.Lock()
_count = DayCounter(gelesen=0, gespeichert=0, ohne=0, abgelehnt=0)

NEVER = re.compile(r"(?i)unterschrift|signatur|signature|iban|\bbic\b|konto|bankverbindung|steuer|\btax\b|ausweis|reisepass|"
                   r"passport|pass-?nr|passnummer|versicherungsn|sozialversicherung|krankenkasse|versicherten|kartennummer|"
                   r"card ?number|\bpin\b|passwort|kennwort|password|\btan\b")
OTHER = re.compile(r"(?i)\bkind|kindes|sohn|tochter|schüler|teilnehmer|ehegatt|ehepartner|partner|vertreter|bevollmächtig|"
                   r"patient|child|spouse|student")
NOT_TODAY = re.compile(r"(?i)geburt|gültig|ablauf|beginn|ende\b|\bbis\b|\bvon\b|termin|frist|eintritt|austritt|birth|valid|expir")
# (rule, pattern on the label): the first that fits wins; the value comes from _values (never from the PDF)
RULES = (
    ("ort_datum", re.compile(r"(?i)\bort\b.{0,6}\bdatum\b|\bdatum\b.{0,6}\bort\b|place.{0,6}date")),
    ("vorname", re.compile(r"(?i)vorname|first ?name|given ?name")),
    ("nachname", re.compile(r"(?i)nachname|familienname|zuname|surname|last ?name|family ?name")),
    ("name", re.compile(r"(?i)^(ihr |dein |vollständiger )?name$|^name,? vorname$|antragsteller|erziehungsberecht|"
                        r"unterzeichn|^full ?name$|^your name$")),
    ("email", re.compile(r"(?i)e-?mail")),
    ("beruf", re.compile(r"(?i)\bberuf|occupation|profession")),
    ("arbeitgeber", re.compile(r"(?i)arbeitgeber|employer")),
    ("ort", re.compile(r"(?i)^(wohn)?ort$|^stadt$|^city$|^town$|^wohnort\b")),
    ("datum", re.compile(r"(?i)^datum$|^date$|^heute$|^today$|datum der unterschrift|ausstellungsdatum")),
)
SOURCE = {"ort_datum": "regel", "vorname": "profil", "nachname": "profil", "name": "profil", "email": "postfach",
          "beruf": "gedaechtnis", "arbeitgeber": "gedaechtnis", "ort": "gedaechtnis", "datum": "regel"}


def _log(word, prof, **nums):
    extra = "".join(f" | {k} {v}" for k, v in nums.items())
    print(f"formular: {word}{extra} | {profiles.log_name(prof)}", flush=True)


def _clean(text, most):
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", str(text or ""))).strip()[:most]


def _label(name, tu):
    """What the person reads for a field: its tooltip (/TU) or its name with _ . - as blanks."""
    return _clean(tu, 120) or _clean(re.sub(r"[_.\-]+", " ", str(name or "")), 120)


def _reader(data):
    from pypdf import PdfReader
    if len(data) > MAX_BYTES or not data.startswith(b"%PDF-"):
        raise ValueError("Das ist kein PDF oder es ist größer als 10 MB.")
    try:
        r = PdfReader(io.BytesIO(data), strict=False)
        if r.is_encrypted and not r.decrypt(""):
            raise ValueError("Das PDF ist mit einem Kennwort geschützt.")
        if len(r.pages) > MAX_PAGES:
            raise ValueError(f"Das PDF hat mehr als {MAX_PAGES} Seiten.")
        return r
    except ValueError:
        raise
    except Exception:   # noqa: BLE001  (a broken file is no form)
        raise ValueError("Das PDF lässt sich nicht lesen.") from None


def fields_of(data):
    """[{"name", "label", "kind": text|check|choice|sig, "options", "max", "now"}] of the form, in the file's order."""
    r = _reader(data)
    got = r.get_fields() or {}
    out = []
    for name, f in got.items():
        ft = str(f.get("/FT") or "")
        if ft not in ("/Tx", "/Btn", "/Ch", "/Sig"):
            continue
        kind = {"/Tx": "text", "/Btn": "check", "/Ch": "choice", "/Sig": "sig"}[ft]
        flags = int(f.get("/Ff") or 0)
        if kind == "check" and flags & (1 << 16):        # a push button: nothing to fill
            continue
        item = {"name": _clean(name, 200), "label": _label(name, f.get("/TU")), "kind": kind, "now": ""}
        if kind == "text":
            ml = f.get("/MaxLen")
            item["max"] = int(ml) if isinstance(ml, int) and 0 < int(ml) < MAX_VALUE else MAX_VALUE
            item["now"] = _clean(f.get("/V") if isinstance(f.get("/V"), str) else "", item["max"])
        elif kind == "check":
            item["options"] = [_clean(str(s).lstrip("/"), 60) for s in (f.get("/_States_") or []) if str(s) != "/Off"][:10] or ["Yes"]
            item["now"] = _clean(str(f.get("/V") or "").lstrip("/"), 60) if str(f.get("/V") or "") not in ("", "/Off") else ""
        elif kind == "choice":
            opts = []
            for o in f.get("/Opt") or []:
                o = o[-1] if isinstance(o, list) and o else o
                opts.append(_clean(o, 120))
            item["options"] = [o for o in opts if o][:60]
            item["now"] = _clean(f.get("/V") if isinstance(f.get("/V"), str) else "", 120)
        out.append(item)
        if len(out) >= MAX_FIELDS:
            break
    return out, len(r.pages)


def _cased(text, value):
    """The memory keeps places in small letters („musterstadt“); the form gets them as the fact wrote them."""
    words = [re.escape(w) for w in str(value).split()]
    m = re.search(r"(?i)(?<!\w)" + r"[\s\-]+".join(words) + r"(?!\w)", str(text)) if words else None
    return m.group(0) if m else value


def _values(uid):
    """{rule: (value, source)} the panel knows for this profile: name, memory places, mailbox address, today."""
    prof = profiles.by_id(uid) or {}
    name = _clean(prof.get("name"), 80)
    out = {}
    if name:
        out["name"] = name
        parts = name.split()
        out["vorname"] = parts[0]
        if len(parts) > 1:
            out["nachname"] = parts[-1]
    try:
        for row in gedaechtnis.places(uid):
            kv = gedaechtnis.slot_of(row.get("text") or "", name) if row.get("text") else None
            if kv and kv[1]:
                key = {"wohnort:": "ort", "beruf:": "beruf", "arbeit:": "arbeitgeber"}.get(row["place"])
                if key:
                    out[key] = _clean(_cased(row["text"], kv[1]), 80)
    except Exception:   # noqa: BLE001  (no memory: those fields stay open)
        pass
    if features.allowed("mail", uid):
        try:
            accts = mail.get(uid)["accounts"]
            if accts and "@" in str(accts[0].get("user") or ""):
                out["email"] = _clean(accts[0]["user"], 120)
        except Exception:   # noqa: BLE001
            pass
    zone = chat.user_zone(profiles.settings(uid).get("tz", ""))
    today = datetime.datetime.now(zone).strftime("%d.%m.%Y")
    out["datum"] = today
    out["ort_datum"] = f"{out['ort']}, {today}" if out.get("ort") else today
    return out


def propose(uid, fields):
    """The fields with "value", "src" (profil, gedaechtnis, postfach, regel or "") and "lock" (never filled by the
    Spark: signature, IBAN, numbers of ID cards, … and every signature field)."""
    known = _values(uid)
    out = []
    for f in fields:
        f = dict(f, value=f.get("now") or "", src="", lock="")
        text = f["label"] + " " + f["name"]
        if f["kind"] == "sig":
            f["lock"] = "sig"
        elif NEVER.search(text):
            f["lock"] = "hand"
        elif f["kind"] == "text" and not f["value"]:
            for rule, rx in RULES:
                if not (rx.search(f["label"]) or rx.search(re.sub(r"[_.\-]+", " ", f["name"]))):
                    continue
                if rule in ("name", "vorname", "nachname") and OTHER.search(text):
                    break                     # someone else's name: never the profile's own
                if rule == "datum" and NOT_TODAY.search(text):
                    break
                if known.get(rule):
                    f["value"], f["src"] = known[rule][:f.get("max", MAX_VALUE)], SOURCE[rule]
                break
        out.append(f)
    return out


def _clean_values(fields, values):
    """{field name: value} only for fields of this form that may be written, each cut and checked."""
    values = values if isinstance(values, dict) else {}
    out = {}
    for f in fields:
        v = values.get(f["name"])
        if v is None or f["kind"] == "sig":
            continue
        if f["kind"] == "check":
            v = str(v)
            if v and v not in f.get("options", []):
                continue
            out[f["name"]] = ("/" + v) if v else "/Off"
        elif f["kind"] == "choice":
            v = _clean(v, 120)
            if v and f.get("options") and v not in f["options"]:
                continue
            out[f["name"]] = v
        else:
            out[f["name"]] = _clean(v, f.get("max", MAX_VALUE))
    return out


BAD_ACTIONS = ("/JavaScript", "/Launch", "/SubmitForm", "/ImportData", "/ResetForm", "/Rendition", "/Sound", "/Movie",
               "/RichMediaExecute", "/GoToR", "/GoToE")


def _strip(w):
    """Takes every script and action out of the file being written."""
    from pypdf.generic import NameObject
    root = w._root_object
    for k in ("/OpenAction", "/AA"):
        root.pop(NameObject(k), None)
    names = root.get("/Names")
    if names is not None:
        names = names.get_object()
        for k in ("/JavaScript", "/EmbeddedFiles"):
            names.pop(NameObject(k), None)
    form = root.get("/AcroForm")
    if form is not None:
        form.get_object().pop(NameObject("/XFA"), None)

    def clean_dict(d):
        d.pop(NameObject("/AA"), None)
        a = d.get("/A")
        if a is not None and str(a.get_object().get("/S")) in BAD_ACTIONS:
            d.pop(NameObject("/A"), None)
    for page in w.pages:
        clean_dict(page)
        for a in page.get("/Annots") or []:
            clean_dict(a.get_object())
    if form is not None:
        stack = list(form.get_object().get("/Fields") or [])
        while stack:
            d = stack.pop().get_object()
            clean_dict(d)
            stack.extend(d.get("/Kids") or [])


def fill(data, fields, values):
    """The PDF with the values in its fields, every script taken out; (bytes, filled count)."""
    from pypdf import PdfWriter
    from pypdf.generic import NameObject
    r = _reader(data)
    vals = _clean_values(fields, values)
    w = PdfWriter(clone_from=r)
    for page in w.pages:
        if page.get("/Annots") and vals:
            try:
                w.update_page_form_field_values(page, vals, auto_regenerate=False)
            except Exception:   # noqa: BLE001  (a field pypdf cannot write stays as it was)
                pass
    w.set_need_appearances_writer(True)
    _strip(w)
    w._root_object.pop(NameObject("/Perms"), None)
    out = io.BytesIO()
    w.write(out)
    return out.getvalue(), sum(1 for v in vals.values() if v not in ("", "/Off"))


def preview(data, page=0):
    """One page as PNG (PREVIEW_WIDTH wide) with its fields drawn."""
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(data)
    try:
        pdf.init_forms()
        n = max(0, min(int(page), len(pdf) - 1))
        p = pdf[n]
        scale = PREVIEW_WIDTH / max(1.0, p.get_width())
        img = p.render(scale=min(scale, 3.0), may_draw_forms=True).to_pil()
        buf = io.BytesIO()
        img.save(buf, "PNG", optimize=True)
        return buf.getvalue()
    finally:
        pdf.close()


# ---------------------------------------------------------------- drafts in memory
def _put(uid, data, name, fields, pages, src):
    key = secrets.token_hex(12)
    now = time.time()
    with _lock:
        for k in [k for k, v in _drafts.items() if now - v["t"] > DRAFT_SECONDS]:
            _drafts.pop(k, None)
        mine = sorted((v["t"], k) for k, v in _drafts.items() if v["uid"] == uid)
        for _, k in mine[:max(0, len(mine) - MAX_DRAFTS + 1)]:
            _drafts.pop(k, None)
        _drafts[key] = {"uid": uid, "data": data, "name": name, "t": now, "fields": fields, "pages": pages, "src": src}
    return key


def _get(uid, key):
    with _lock:
        d = _drafts.get(str(key or ""))
        if not d or d["uid"] != uid or time.time() - d["t"] > DRAFT_SECONDS:
            return None
        d["t"] = time.time()
        return d


def _pdf_name(name):
    base = re.sub(r"(?i)\.pdf$", "", _clean(re.sub(r"[\\/:*?\"<>|]", "", str(name or "")), 100)) or "Formular"
    return base


async def read(uid, body):
    """The form from an own document or an own mail's attachment: (data, name, src)."""
    if body.get("doc"):
        doc = str(body["doc"])
        got = await asyncio.to_thread(documents.original, uid, doc)
        if not got or not got[1].lower().endswith(".pdf"):
            raise LookupError("Von diesem Dokument ist kein PDF aufbewahrt.")
        path = got[0]
        with open(path, "rb") as fh:
            data = fh.read(MAX_BYTES + 1)
        return data, got[1], {"doc": doc}
    if body.get("mail"):
        if not features.allowed("mail", uid):
            raise PermissionError("E-Mail ist für dich aus.")
        ref, folder = str(body["mail"])[:40], str(body.get("folder") or "INBOX")[:200]
        try:
            n = int(body.get("n"))
        except (TypeError, ValueError):
            raise LookupError("Unbekannter Anhang.") from None
        got = await asyncio.wait_for(asyncio.to_thread(mail.file_of, uid, ref, folder, n), 90)
        if not got:
            raise LookupError("Diesen Anhang gibt es nicht (mehr).")
        return got[1], got[0], {"mail": ref, "folder": folder}
    raise LookupError("Kein Formular genannt.")


def _err(e):
    if isinstance(e, PermissionError):
        return HTTPException(403, str(e))
    if isinstance(e, LookupError):
        return HTTPException(404, str(e))
    if isinstance(e, asyncio.TimeoutError):
        return HTTPException(504, "Das Postfach hat zu lange gebraucht.")
    return HTTPException(400, str(e))


def _on(request: Request, prof=Depends(browser_profile)):
    if not features.allowed(KEY, prof["id"]):
        raise HTTPException(403, ("PDF-Formulare sind für dich aus. " + features.missing_text(KEY, prof["id"])).strip())
    guard.limit(request, "doc", prof["id"], False)
    return prof


@router.post("/api/profile/formular/lesen", dependencies=[Depends(assistant)])
async def api_read(request: Request, prof=Depends(_on)):
    b = await json_body(request, 1024)
    try:
        data, name, src = await read(prof["id"], b)
        fields, pages = await asyncio.to_thread(fields_of, data)
    except (LookupError, PermissionError, ValueError, asyncio.TimeoutError, OSError) as e:
        _count.bump("abgelehnt")
        _log("abgelehnt", prof, why={PermissionError: "aus", LookupError: "fehlt"}.get(type(e), "datei"))
        raise _err(e)
    if not fields:
        _count.bump("ohne")
        _log("ohne felder", prof, seiten=pages)
        raise HTTPException(422, "Das ist kein ausfüllbares Formular: Das PDF hat keine Felder.")
    fields = propose(prof["id"], fields)
    key = _put(prof["id"], data, _pdf_name(name), fields, pages, src)
    _count.bump("gelesen")
    _log("gelesen", prof, felder=len(fields), vorgeschlagen=sum(1 for f in fields if f["src"]))
    return {"key": key, "name": _pdf_name(name) + ".pdf", "pages": pages, "fields": fields, "src": src}


@router.post("/api/profile/formular/vorschau", dependencies=[Depends(assistant)])
async def api_preview(request: Request, prof=Depends(_on)):
    b = await json_body(request, 128 * 1024)
    d = _get(prof["id"], b.get("key"))
    if not d:
        raise HTTPException(404, "Das Formular ist nicht mehr offen. Bitte noch einmal öffnen.")
    try:
        filled, _ = await asyncio.to_thread(fill, d["data"], d["fields"], b.get("values"))
        png = await asyncio.to_thread(preview, filled, int(b.get("page") or 0))
    except (ValueError, TypeError) as e:
        raise HTTPException(400, str(e) or "Die Vorschau ging nicht.")
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/api/profile/formular/speichern", dependencies=[Depends(assistant)])
async def api_save(request: Request, prof=Depends(_on)):
    b = await json_body(request, 128 * 1024)
    d = _get(prof["id"], b.get("key"))
    if not d:
        raise HTTPException(404, "Das Formular ist nicht mehr offen. Bitte noch einmal öffnen.")
    try:
        out, n = await asyncio.to_thread(fill, d["data"], d["fields"], b.get("values"))
        name = d["name"] + " (ausgefüllt).pdf"
        got = await asyncio.to_thread(wissen.aufnehmen, prof["id"], name, out, "formular",
                                      "formular:" + hashlib.sha256(out).hexdigest()[:40])
    except (ValueError, documents.QueueFull) as e:
        _count.bump("abgelehnt")
        _log("abgelehnt", prof, why="speichern")
        raise HTTPException(400, str(e) or "Speichern ging nicht.")
    kept = bool(await asyncio.to_thread(documents.original, prof["id"], got["id"]))
    total = sum(1 for f in d["fields"] if f["kind"] != "sig")
    _count.bump("gespeichert")
    _log("gespeichert", prof, felder=n, offen=max(0, total - n))
    return {"doc": got["id"], "name": got.get("name") or name, "kept": kept, "filled": n, "open": max(0, total - n),
            "src": d["src"]}


def attachment(uid, doc):
    """(name, "application/pdf", bytes) of a form this profile filled (source "formular", its own document with the
    kept original) for the mail answer (senden._preview, body "doc"); every other document is refused."""
    if not features.allowed(KEY, uid):
        raise ValueError("PDF-Formulare sind für dich aus.")
    doc = str(doc or "")[:40]
    d = next((x for x in documents.list_docs(uid) if x["id"] == doc), None)
    got = documents.original(uid, doc) if d and d.get("source") == KEY else None
    if not got or not got[1].lower().endswith(".pdf"):
        raise LookupError("Nur ein eigenes ausgefülltes Formular geht als Anhang mit.")
    with open(got[0], "rb") as fh:
        data = fh.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Das Formular ist zu groß für eine Mail.")
    _log("angehaengt", prof=profiles.by_id(uid) or {"id": uid}, kb=max(1, len(data) // 1024))
    return got[1], "application/pdf", data


def for_live(now=None):
    """{"on", "gelesen", "gespeichert", "ohne", "abgelehnt", "offen"}: today's counts and forms open now (numbers)."""
    if not features.admin_on(KEY):
        return {"on": False}
    c = _count.today(now)
    with _lock:
        open_ = sum(1 for v in _drafts.values() if time.time() - v["t"] <= DRAFT_SECONDS)
    return {"on": True, "gelesen": c["gelesen"], "gespeichert": c["gespeichert"], "ohne": c["ohne"],
            "abgelehnt": c["abgelehnt"], "offen": open_}


# the hooks into lower modules, so none of them imports this one (test_schichten): the line of Spark-Speicher in the
# Live-Übersicht (live.TEILE) and the filled form as the attachment of a mail (senden.ANHAENGE)
live.TEILE["formular"] = lambda: for_live()
senden.ANHAENGE["doc"] = attachment
