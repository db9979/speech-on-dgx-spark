"""Was ich über dich weiß (plan persoenlicher-assistent/plan.md, Dominik 2026-10-18 „3a 4a 6a 7a“, stages 3 and 4): one
page under Ich that shows what the Spark knows about the person and lets it be corrected:

    Interessen       proposed as topics (TOPICS, Dominik 2026-10-22 „ok“ to plan interessen-themen: a sender's name is no
                     interest) with their evidence: the senders as chips, the counts of orders, offers and newsletters
                     and up to EXAMPLES subjects (shown as text, kept in memory only); a sender without a topic stays
                     „Thema unklar“ with its subjects and a field for an own topic; the own addresses and service
                     senders (TOPICS rules below) are never proposed; words in Reddit und Feeds; counted only after
                     „Stimmt“ (the topic with its senders); „Nicht so“ is remembered; own words can be added; an older
                     confirmed sender is asked once for its topic
    Wiederkehrendes  bills of the same sender in three or more months, about the same day („um den 15.“), with
                     „Monatlich erinnern“ (a monthly reminder)
    Diese Woche      the weekly review: marked done, still open, deadlines of the next seven days (Von selbst: Sundays
                     at 18 o'clock, kind "rueckblick")
    Diesen Monat     the sum of bills and orders of this month from the checked amounts of Für dich (7a)
    Aus dem Netz     at most one tip a day for a confirmed interest that allows it (4a): a separate run that sends only
                     the interest word to the web search (SearXNG through chat.web_search), never mail text
    Gemerkt          the newest facts of the memory and the mail style, with the ways to their own pages

Fixed rules, the panel decides, no model. Part of „Für dich aus Mails“ (chat.mail_insight, off; needs chat.mail);
released for every profile the admin did not block, guests never. Kept in users/<id>/interessen.json: the confirmed and
refused interests (name, state, time, web tips on or off, topic, senders) and the last web tip; everything else is read
when the page asks and kept in memory only.

    GET    /api/profile/ichweiss                  the page
    POST   /api/profile/ichweiss/interest         {"name", "state": "yes" | "no" | "forget", "web": bool, "topic", "senders"}
                                                  or {"name", "state": "adopt", "topic"} / {"name", "state": "keep"}
                                                  / {"name", "state": "rename", "to"} (a new name or a topic)
                                                  / {"name", "state": "drop", "senders": [one]} (a sender out)
    POST   /api/profile/ichweiss/recurring        {"id"}: a monthly reminder for it
    DELETE /api/profile/ichweiss                  forget every interest and the web tip
"""
import asyncio
import datetime
import hashlib
import imaplib
import json
import os
import re
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import features
import fuerdich
import guard
import mail
import notaus
import profiles
import vorrang
from common import DayCounter, load_config
from core import assistant, browser_profile, json_body, own_profile

router = APIRouter()
NAME_MAX = 40                   # an interest is a short word or name
MAX_INTERESTS = 60
MAX_PROPOSALS = 8
SHOP_MIN = 2                    # mails of a shop (orders, offers, newsletters) before it is proposed
EXAMPLES = 3                    # subjects of a sender shown as evidence (memory only, fuerdich._shop)
EXAMPLE_MAX = 80                # characters of one
TOPIC_MIN = 2                   # mails of a sender with a topic's words before the topic is its one
MAX_SENDERS = 20                # senders kept with a confirmed topic

# Topics (plan interessen-themen, 1a): key -> (German name, English name, words, sender domains). A word matches as a
# whole word, „wort*“ as the start of a word, in the subject and the sender's name; a domain matches itself and its
# subdomains. Fixed rules, the panel decides, no model; one list (test_ichweiss: no word in two topics).
TOPICS = {
    "musikproduktion": ("Musikproduktion & Samples", "Music production & samples",
                        ("sample*", "synth*", "vst", "plugin*", "plug-in*", "preset*", "daw", "ableton", "cubase", "kontakt",
                         "orchestral", "mixing", "mastering", "sound design", "soundbank*", "loops", "midi", "drum*"),
                        ("sonokinetic.com", "native-instruments.com", "splice.com", "spitfireaudio.com", "plugin-alliance.com",
                         "waves.com", "kvraudio.com", "steinberg.net", "ableton.com", "thomann.de", "bestservice.com")),
    "musik": ("Musik hören", "Listening to music", ("spotify", "album", "vinyl", "schallplatte*", "playlist*", "konzertmitschnitt*"),
              ("spotify.com", "bandcamp.com", "hhv.de", "deezer.com")),
    "smarthome": ("Smart Home & IoT", "Smart home & IoT",
                  ("smart home", "smarthome", "iot*", "esp32", "esp8266", "arduino", "raspberry", "home assistant",
                   "zigbee", "mqtt", "tasmota", "shelly", "sensor*"),
                  ("home-assistant.io", "homeassistant.io", "raspberrypi.com", "espressif.com", "shelly.com", "nabucasa.com")),
    "software": ("Software & Entwicklung", "Software & development",
                 ("python", "javascript", "typescript", "docker", "kubernetes", "developer*", "entwickler*", "open source",
                  "linux", "programming", "programmier*", "coding", "devops"),
                 ("jetbrains.com", "stackoverflow.com", "docker.com", "gitlab.com")),
    "ki": ("KI & Sprachmodelle", "AI & language models",
           ("ki", "künstliche intelligenz", "ai", "llm*", "gpt*", "chatgpt", "openai", "anthropic", "nvidia", "machine learning",
            "deep learning", "hugging face", "huggingface"),
           ("openai.com", "anthropic.com", "huggingface.co", "nvidia.com")),
    "computer": ("Computer & Elektronik", "Computers & electronics",
                 ("laptop*", "notebook*", "monitor", "ssd", "grafikkarte*", "gpu", "prozessor*", "cpu", "mainboard*",
                  "tastatur*", "keyboard*", "gaming pc"),
                 ("alternate.de", "mindfactory.de", "notebooksbilliger.de", "cyberport.de", "conrad.de", "reichelt.de",
                  "caseking.de", "mouser.com", "digikey.de")),
    "maker": ("Basteln & 3D-Druck", "Making & 3D printing",
              ("3d-druck*", "3d print*", "filament*", "prusa", "bambu", "cnc", "lasercutter*", "löten", "soldering", "bastel*"),
              ("prusa3d.com", "bambulab.com", "elegoo.com")),
    "foto": ("Fotografie & Video", "Photography & video",
             ("kamera*", "camera*", "foto*", "photo*", "objektiv*", "lens", "lenses", "lightroom", "drohne*", "drone*"),
             ("canon.de", "nikon.de", "dji.com", "fujifilm.com", "calumetphoto.de")),
    "spiele": ("Spiele", "Games", ("game", "games", "gaming", "spiele", "steam", "playstation", "xbox", "nintendo"),
               ("steampowered.com", "epicgames.com", "nintendo.com", "nintendo.de", "playstation.com", "xbox.com", "gog.com")),
    "filme": ("Filme & Serien", "Films & series", ("film", "filme", "movie*", "serie", "serien", "series", "kino", "streaming"),
              ("netflix.com", "disneyplus.com", "wowtv.de", "paramountplus.com")),
    "buecher": ("Bücher & Hörbücher", "Books & audiobooks", ("buch", "bücher", "book", "books", "ebook*", "hörbuch*", "audiobook*", "roman"),
                ("thalia.de", "hugendubel.de", "audible.de", "audible.com", "tolino.de")),
    "konzerte": ("Konzerte & Events", "Concerts & events", ("konzert*", "concert*", "festival*", "tickets", "tournee"),
                 ("eventim.de", "ticketmaster.de", "reservix.de")),
    "essen": ("Essen bestellen", "Food delivery", ("lieferando", "pizza", "burger", "sushi", "lieferdienst*"),
              ("lieferando.de", "wolt.com", "ubereats.com", "deliveroo.de", "flink.com")),
    "kochen": ("Kochen & Rezepte", "Cooking & recipes", ("rezept*", "recipe*", "kochen", "backen", "thermomix", "kochbox*"),
               ("hellofresh.de", "chefkoch.de", "marleyspoon.de", "vorwerk.com")),
    "reisen": ("Reisen", "Travel", ("reise*", "urlaub*", "flug", "flüge", "flight*", "hotel*", "ferienwohnung*", "kreuzfahrt*", "trip"),
               ("booking.com", "airbnb.com", "airbnb.de", "expedia.de", "lufthansa.com", "eurowings.com", "ryanair.com",
                "tui.com", "holidaycheck.de")),
    "sport": ("Sport & Fitness", "Sports & fitness",
              ("fitness", "workout*", "laufen", "running", "fahrrad*", "bike", "bikes", "radsport", "marathon*", "yoga", "gym"),
              ("strava.com", "garmin.com", "decathlon.de", "rosebikes.de", "bike-discount.de", "runtastic.com")),
    "auto": ("Auto & Mobilität", "Cars & mobility", ("auto", "autos", "elektroauto*", "e-auto*", "tesla", "reifen", "wallbox*"),
             ("tesla.com", "adac.de", "mobile.de", "autoscout24.de")),
    "finanzen": ("Finanzen & Geldanlage", "Finance & investing",
                 ("aktie*", "etf*", "depot*", "börse*", "sparplan*", "krypto*", "bitcoin", "dividende*", "geldanlage"),
                 ("traderepublic.com", "scalable.capital", "finanzfluss.de", "justetf.com")),
    "mode": ("Mode", "Fashion", ("mode", "fashion", "sneaker*", "schuhe", "shoes", "jacke*", "kleid*", "outfit*", "kollektion*"),
             ("zalando.de", "aboutyou.de", "hm.com", "asos.com", "zara.com")),
    "haus": ("Haus & Garten", "Home & garden", ("garten*", "garden*", "heimwerk*", "baumarkt*", "möbel*", "furniture", "deko*"),
             ("obi.de", "hornbach.de", "bauhaus.info", "ikea.com", "home24.de")),
    "gesundheit": ("Gesundheit", "Health", ("gesundheit*", "health", "ernährung*", "nutrition", "apotheke*", "vitamin*", "schlaf"),
                   ("shop-apotheke.com", "docmorris.de")),
    "tiere": ("Haustiere", "Pets", ("hund", "hunde*", "katze*", "dog", "dogs", "tierfutter", "haustier*"),
              ("fressnapf.de", "zooplus.de")),
    "familie": ("Familie & Kinder", "Family & children", ("baby*", "kinder*", "kids", "spielzeug*", "toys", "lego"),
                ("mytoys.de", "jako-o.de", "lego.com")),
    "technews": ("Technik-Nachrichten", "Tech news", ("tech news", "newsticker"),
                 ("heise.de", "golem.de", "t3n.de", "computerbase.de", "theverge.com", "techcrunch.com")),
}
# never an interest (2a): mails of a service about an account (GitHub, an app store, …), machine mail (Auto-Submitted)
SERVICE_DOMAINS = ("github.com", "gitlab.com", "bitbucket.org", "atlassian.net", "apple.com", "icloud.com", "google.com",
                   "accounts.google.com", "microsoft.com", "paypal.com", "paypal.de")
SERVICE_ADDR = re.compile(r"(?i)^(notifications?|notify|alerts?|security|account|accounts|konto|no-?reply-?(?:account|security)|"
                          r"verify|verification)[@.+-]")


def _word_re(words):
    return re.compile("|".join(r"\b" + re.escape(w[:-1]) if w.endswith("*") else r"\b" + re.escape(w) + r"\b" for w in words), re.I)


_TOPIC_RE = {k: _word_re(v[2]) for k, v in TOPICS.items()}


def _dom_in(dom, domains):
    return any(dom == d or dom.endswith("." + d) for d in domains)


def topics_in(text, dom):
    """The topic keys whose words stand in text (a subject and a sender's name) or whose domains send it."""
    dom = (dom or "").lower()
    return [k for k, v in TOPICS.items() if (dom and _dom_in(dom, v[3])) or _TOPIC_RE[k].search(text or "")]


def service(addr):
    """A service or machine sender (2a): never proposed as an interest."""
    addr = (addr or "").lower()
    return bool(SERVICE_ADDR.match(addr)) or _dom_in(addr.rpartition("@")[2], SERVICE_DOMAINS)


def topic_name(key, en=False):
    t = TOPICS.get(key)
    return (t[1] if en else t[0]) if t else ""


def topic_by_name(name):
    """The key of a topic named so (German or English, any case), else "" (an own topic picked or typed, 4a)."""
    n = norm(clean(name))
    return next((k for k, v in TOPICS.items() if n and n in (norm(v[0]), norm(v[1]))), "")


def choices(uid):
    """[{"name", "en", "topic"}] to pick an own topic from (Dominik 2026-10-22 „Themen auswählen von den vorhandenen“):
    the confirmed interests first, then the topics of TOPICS not confirmed yet."""
    yes = [v for v in load(uid)["items"].values() if v["state"] == "yes"]
    # an older confirmed sender (no topic) is no topic to pick; it gets one with rename() (Dominik 2026-10-22)
    out = [{"name": v["name"], "en": topic_name(v["topic"], True) or v["name"], "topic": v["topic"]}
           for v in sorted(yes, key=lambda v: v["name"].lower()) if not _old_sender(v)]
    have = {v["topic"] for v in yes} | {norm(v["name"]) for v in yes}
    out += [{"name": v[0], "en": v[1], "topic": k} for k, v in TOPICS.items() if k not in have and norm(v[0]) not in have]
    return out


def topic_of(c):
    """The topic of a sender's counts (fuerdich._shop): the one with most mails, TOPIC_MIN or more and at least a third
    of its mails; a sender domain of a topic counts for each of its mails. "" when none fits."""
    n = sum(c.get(w, 0) for w in ("orders", "offers", "news"))
    best = max(((v, k) for k, v in (c.get("topics") or {}).items() if k in TOPICS), default=(0, ""), key=lambda x: x[0])
    return best[1] if best[0] >= TOPIC_MIN and best[0] * 3 >= n else ""
REC_DAYS = 200                  # days of headers read for Wiederkehrendes
REC_SCAN = 1500                 # newest headers per folder
REC_MONTHS = 3                  # bills of a sender in this many months make it recurring
REC_SPREAD = 6                  # their days of the month lie within this many days
REC_SECONDS = 24 * 3600         # Wiederkehrendes is read at most once a day
REMIND_HOUR = 9
WEEK_DAYS = 7
TIP_HOURS = (10, 19)            # the web tip is looked for in the day only, once a day
TIP_KEEP = 3 * 86400

_lock = threading.Lock()
_rec = {}                       # uid -> (time, [recurring])
_day = DayCounter(angesehen=0, bestaetigt=0, abgelehnt=0, erinnerung=0, netztipp=0, thema=0)   # Zustand → Live, numbers only


def _file(uid):
    return profiles._path(uid, "interessen.json")


def norm(name):
    return re.sub(r"\s+", " ", str(name or "").strip().lower())[:NAME_MAX]


def clean(name):
    """An interest's name as the page shows it: one line, letters, digits, spaces and a few signs."""
    v = re.sub(r"[^\w .&+'-]", " ", str(name or ""))
    return re.sub(r"\s+", " ", v).strip()[:NAME_MAX]


def load(uid):
    try:
        with open(_file(uid)) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d = d if isinstance(d, dict) else {}
    items = {}
    for k, v in (d.get("items") or {}).items():
        if isinstance(v, dict) and v.get("state") in ("yes", "no") and isinstance(v.get("name"), str) and norm(k) == k:
            items[k] = {"name": clean(v["name"]) or k, "state": v["state"], "t": int(v.get("t") or 0),
                        "web": v.get("web") is True, "src": v.get("src") if v.get("src") in SOURCES else "hand",
                        "topic": v.get("topic") if v.get("topic") in TOPICS else "",
                        "senders": [clean(x) for x in v.get("senders") or [] if isinstance(x, str) and clean(x)][:MAX_SENDERS],
                        "kept": v.get("kept") is True}
    tip = d.get("tip") if isinstance(d.get("tip"), dict) else None
    return {"items": items, "tip": tip}


def _save(uid, d):
    with _lock:
        if len(d["items"]) > MAX_INTERESTS:      # the oldest refusals go first
            keep = sorted(d["items"].items(), key=lambda kv: (kv[1]["state"] == "yes", kv[1]["t"]))[-MAX_INTERESTS:]
            d["items"] = dict(keep)
        profiles._write(_file(uid), d)


def count(uid):
    return len(load(uid)["items"])


def forget(uid):
    try:
        os.remove(_file(uid))
    except OSError:
        pass
    _rec.pop(uid, None)


features.OWN["ichweiss"] = (count, forget)
SOURCES = {"thema": ("Thema aus deinen Mails", "Topic from your mails"),
           "shop": ("Mails eines Shops", "Mails of a shop"), "feeds": ("Stichwort in Reddit und Feeds", "Keyword in Reddit and feeds"),
           "karte": ("„Mehr davon“ an einer Karte", "\"More of this\" on a card"), "hand": ("selbst eingetragen", "added by you")}


def usable(uid):
    return bool(features.allowed("ichweiss", uid) and mail.get(uid)["accounts"])


def confirmed(uid):
    return [v for v in load(uid)["items"].values() if v["state"] == "yes"]


def known(uid, who):
    """Said yes or no to already, as an interest or as a sender of a topic („Mehr davon“ only for a shop not known yet)."""
    n = norm(clean(who))
    return any(k == n or n in map(norm, v["senders"]) for k, v in load(uid)["items"].items())


def fits(uid, who, subject="", addr=""):
    """The confirmed interest an offer fits, or "" (Für dich sorts and marks it): its sender's name, a sender of a
    confirmed topic, or the topic of its subject and sender domain."""
    n = norm(who)
    mine = topics_in(f"{who} {subject}", addr.rpartition("@")[2]) if subject or addr else []
    for k, v in load(uid)["items"].items():
        if v["state"] == "yes" and k and (k == n or k in n or n in map(norm, v["senders"]) or (v["topic"] and v["topic"] in mine)):
            return v["name"]
    return ""


def set_state(uid, name, state, src="hand", web=None, topic=None, senders=None):
    """yes / no / forget one interest by its name; returns the item or None (forgotten). topic and senders: a topic of
    TOPICS confirmed with its senders (3a, 5a); a sender said no to in it stays out of it."""
    if not topic and topic_by_name(name):     # a topic of the list typed or picked by its name: that topic
        topic = topic_by_name(name)
        name = topic_name(topic)
    k, nm = norm(clean(name)), clean(name)
    if not k or len(k) < 2:
        raise ValueError("name")
    d = load(uid)
    if state == "forget":
        d["items"].pop(k, None)
        _save(uid, d)
        return None
    old = d["items"].get(k, {})
    names = list(old.get("senders") or [])
    for x in senders or []:
        if clean(x) and norm(x) not in map(norm, names) and len(names) < MAX_SENDERS:
            names.append(clean(x))
    d["items"][k] = {"name": old.get("name") or nm, "state": state, "t": int(time.time()),
                     "web": (old.get("web", False) if web is None else bool(web)) and state == "yes",
                     "src": src if src in SOURCES else "hand", "topic": topic if topic in TOPICS else old.get("topic", ""),
                     "senders": names, "kept": old.get("kept", False)}
    _save(uid, d)
    _day.bump("bestaetigt" if state == "yes" else "abgelehnt")
    return d["items"][k]


def more(uid, who):
    """„Mehr davon“ at a card (Für dich, Offen): the sender's topic with the sender when the last reading knows one,
    else the sender itself as before; returns the item."""
    k = topic_of(fuerdich.shops(uid).get(who) or {})
    if k:
        return set_state(uid, topic_name(k), "yes", "karte", topic=k, senders=[who])
    return set_state(uid, who, "yes", "karte")


def adopt(uid, name, topic):
    """6a: an older confirmed sender goes into its topic (the topic confirmed with it), the sender's own item goes."""
    d = load(uid)
    k = norm(clean(name))
    old = d["items"].get(k)
    if not old or old["state"] != "yes" or topic not in TOPICS:
        raise KeyError(name)
    item = set_state(uid, topic_name(topic), "yes", "thema", web=old["web"] or None, topic=topic, senders=[old["name"]])
    d = load(uid)
    d["items"].pop(k, None)
    _save(uid, d)
    _day.bump("thema")
    return item


def _old_sender(v):
    """A sender confirmed before the topics (V01.0.922): a shop or „Mehr davon“ without a topic."""
    return v["src"] in ("shop", "karte") and not v["topic"]


def drop(uid, name, sender):
    """✕ at a sender in the details of a confirmed interest (Dominik 2026-10-22 „ok“ to the tidy page): the sender
    leaves it and stays out (a „Nicht so“ for its name); returns the item."""
    d = load(uid); k = norm(clean(name)); item = d["items"].get(k)
    if not item or norm(sender) not in map(norm, item["senders"]):
        raise KeyError(name)
    item["senders"] = [x for x in item["senders"] if norm(x) != norm(sender)]
    _save(uid, d)
    set_state(uid, sender, "no", "shop")
    return load(uid)["items"][k]


def rename(uid, name, to):
    """Renames an interest or gives it a topic (Dominik 2026-10-22 „nicht löschbar oder bearbeitbar“): to is a topic of
    the list (German or English name: that topic), a confirmed interest (joined with it) or a new name. An older
    confirmed sender becomes a sender of the new one; web tips and senders go along. Returns the item."""
    d = load(uid)
    k = norm(clean(name))
    old = d["items"].get(k)
    if not old:
        raise KeyError(name)
    t = topic_by_name(to)
    new = topic_name(t) if t else clean(to)
    if len(norm(new)) < 2:
        raise ValueError("name")
    if norm(new) == k and (t or "") == old["topic"]:
        return old
    senders = old["senders"] + ([old["name"]] if _old_sender(old) else [])
    d["items"].pop(k)
    _save(uid, d)
    target = load(uid)["items"].get(norm(new), {})
    item = set_state(uid, new, old["state"], "thema" if t else target.get("src") or "hand",
                     web=(old["web"] or target.get("web", False)) and old["state"] == "yes", topic=t or None, senders=senders)
    _day.bump("thema")
    return item


def keep(uid, name):
    """6a „So lassen“: the older sender stays as it is and is not asked again."""
    d = load(uid)
    k = norm(clean(name))
    if k not in d["items"]:
        raise KeyError(name)
    d["items"][k]["kept"] = True
    _save(uid, d)


def asks(uid):
    """6a: older confirmed senders (no topic, not „So lassen“) whose topic the last reading knows, once each."""
    shops = {norm(clean(w)): c for w, c in fuerdich.shops(uid).items()}
    out = []
    for k, v in load(uid)["items"].items():
        if v["state"] == "yes" and not v["topic"] and not v["kept"] and v["src"] in ("shop", "karte"):
            t = topic_of(shops.get(k) or {})
            if t:
                out.append({"name": v["name"], "topic": t, "label": topic_name(t), "en": topic_name(t, True)})
    return out[:MAX_PROPOSALS]


# ---------------------------------------------------------------- proposals (3a)
def _counts_line(o, f, n):
    parts = [f"{o} {'Bestellung' if o == 1 else 'Bestellungen'}" if o else "",
             f"{f} {'Angebot' if f == 1 else 'Angebote'}" if f else "", f"{n} Newsletter" if n else ""]
    return ", ".join(x for x in parts if x)


def _own(uid):
    """The profile's own addresses, their names before the @ and the profile's name (2a: never an interest)."""
    own = set()
    for a in mail.get(uid)["accounts"]:
        u = str(a.get("user") or "").lower()
        own |= {u, u.partition("@")[0]}
    p = profiles.by_id(uid) or {}
    own.add(norm(p.get("name", "")))
    return {x for x in own if x}


def proposals(uid):
    """[{"name", "en", "src", "why", "topic", "senders", "ex", "unclear"}]: topics found in the senders of the last
    reading of Für dich with SHOP_MIN or more mails (3a), a sender without a topic as „Thema unklar“ when it sent offers or
    newsletters (4a), words of Reddit und Feeds; never the own addresses or a service (2a), never what was said yes or no
    to. Only counts and up to EXAMPLES subjects as evidence (memory only)."""
    d = load(uid)["items"]
    told = set(d) | {norm(x) for v in d.values() for x in v["senders"]}
    own = _own(uid)
    topics, unclear = {}, []
    for who, c in fuerdich.shops(uid).items():
        o, f, n = (c.get(w, 0) for w in ("orders", "offers", "news"))
        addr = str(c.get("addr") or "").lower()
        if norm(who) in told or o + f + n < SHOP_MIN or c.get("svc") or service(addr) \
                or {norm(who), addr, addr.partition("@")[0]} & own:
            continue
        k = topic_of(c)
        if k and norm(topic_name(k)) not in d:
            t = topics.setdefault(k, {"o": 0, "f": 0, "n": 0, "senders": [], "ex": []})
            t["o"], t["f"], t["n"] = t["o"] + o, t["f"] + f, t["n"] + n
            t["senders"].append(clean(who))
            t["ex"] += c.get("ex") or []
        elif not k and f + n:
            unclear.append({"name": clean(who), "en": clean(who), "src": "shop", "topic": "", "senders": [clean(who)],
                            "why": _counts_line(o, f, n) + f" in {fuerdich.DAYS} Tagen", "ex": (c.get("ex") or [])[:EXAMPLES],
                            "unclear": True, "_n": o + f + n})
    out = []
    for k, t in sorted(topics.items(), key=lambda kv: -(kv[1]["o"] + kv[1]["f"] + kv[1]["n"])):
        many = len(t["senders"])
        out.append({"name": topic_name(k), "en": topic_name(k, True), "src": "thema", "topic": k, "senders": t["senders"],
                    "why": _counts_line(t["o"], t["f"], t["n"]) + (f" von {many} Absendern" if many > 1 else "")
                    + f" in {fuerdich.DAYS} Tagen", "ex": t["ex"][:EXAMPLES], "unclear": False})
    out += [{k: v for k, v in x.items() if k != "_n"} for x in sorted(unclear, key=lambda x: -x["_n"])]
    try:
        import feeds
        if features.allowed("feeds", uid):
            for w in feeds.get(uid).get("words", [])[:20]:
                if norm(w) not in d and clean(w):
                    out.append({"name": clean(w), "en": clean(w), "src": "feeds", "why": "Stichwort in Reddit und Feeds",
                                "topic": "", "senders": [], "ex": [], "unclear": False})
    except Exception:
        pass
    seen, res = set(), []
    for x in out:
        if norm(x["name"]) not in seen:
            seen.add(norm(x["name"]))
            res.append(x)
    return res[:MAX_PROPOSALS]


# ---------------------------------------------------------------- Wiederkehrendes (6a)
def _rec_account(acct, uid):
    import tidy
    found = {}
    with tidy.Box(acct) as b:               # no tidying state: nothing can be changed
        boxes = ["INBOX"]
        try:
            f = tidy.folder_of(tidy.state(uid), "rechnungen")
            if f and b.name(f) in b.boxes:
                boxes.append(b.name(f))
        except Exception:
            pass
        for box in boxes:
            notaus.stop("gespraech")
            b.select(box)                   # EXAMINE
            uids = sorted(b.search("SINCE", tidy._since(REC_DAYS)))[-REC_SCAN:]
            for m in b.headers(uids, "FROM SUBJECT DATE").values():
                subj = mail._hdr(m.get("Subject", ""))
                if not fuerdich.BILL.search(subj):
                    continue
                frm = mail._addr(m.get("From", ""))
                dom = fuerdich.domain(frm)
                if dom:
                    d = mail.local(mail._date(m.get("Date"))).date()
                    found.setdefault(dom, {"who": fuerdich.who(frm), "days": set()})["days"].add(d)
    print(f"ichweiss: kopfzeilen gelesen ordner={len(boxes)} absender={len(found)}", flush=True)
    return found


def recurring_scan(uid):
    """[{"id", "who", "day", "months"}]: senders whose bills came in REC_MONTHS or more months, about the same day."""
    hit = _rec.get(uid)
    if hit and time.time() - hit[0] < REC_SECONDS:
        return hit[1]
    groups = {}
    for a in mail.get(uid)["accounts"]:
        try:
            for dom, g in _rec_account(a, uid).items():
                x = groups.setdefault(dom, {"who": g["who"], "days": set()})
                x["days"] |= g["days"]
        except (ValueError, OSError, imaplib.IMAP4.error) as e:
            print(f"ichweiss: wiederkehrend fehler={type(e).__name__}", flush=True)
    out = []
    for dom, g in groups.items():
        by_month = {}
        for d in sorted(g["days"]):
            by_month.setdefault((d.year, d.month), d.day)     # the first bill of a month
        days = sorted(by_month.values())
        if len(by_month) < REC_MONTHS or days[-1] - days[0] > REC_SPREAD:
            continue
        out.append({"id": hashlib.sha256(f"rec:{dom}".encode()).hexdigest()[:12], "who": g["who"],
                    "day": days[len(days) // 2], "months": len(by_month)})
    out.sort(key=lambda x: x["day"])
    if len(_rec) > 200:
        _rec.clear()
    _rec[uid] = (time.time(), out)
    print(f"ichweiss: wiederkehrend gelesen funde={len(out)}", flush=True)
    return out


def next_monthly(day, now):
    """The next time a monthly reminder for this day of the month rings (9 o'clock, at most the 28th)."""
    day = min(max(int(day), 1), 28)
    at = now.replace(day=day, hour=REMIND_HOUR, minute=0, second=0, microsecond=0)
    if at <= now:
        y, m = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
        at = at.replace(year=y, month=m)
    return at


def rec_text(x):
    return f"Rechnung {fuerdich._one(x['who'], 40)} kommt um den {x['day']}."


# ---------------------------------------------------------------- Diese Woche and Diesen Monat (stage 4)
def cents(amount):
    """84,20 € -> 8420; "" or anything else -> 0."""
    m = re.search(r"(\d{1,3}(?:\.\d{3})*|\d+),(\d{2})", str(amount or ""))
    return int(m.group(1).replace(".", "")) * 100 + int(m.group(2)) if m else 0


def euro(c):
    return f"{c // 100:,}".replace(",", ".") + f",{c % 100:02d} €"


def month_sum(items, today):
    """{"bills", "orders", "total", "n"} in cents from the checked amounts of this month's mails (7a); a bill that is
    debited counts too. Only what the last reading of Für dich holds."""
    ym = today.strftime("%Y-%m")
    out = {"bills": 0, "orders": 0, "n": 0}
    for x in items:
        if x["kind"] in ("rechnung", "bestellung") and str(x.get("sent", "")).startswith(ym) and cents(x.get("amount")):
            out["bills" if x["kind"] == "rechnung" else "orders"] += cents(x["amount"])
            out["n"] += 1
    out["total"] = out["bills"] + out["orders"]
    return out


def week(uid, items, today):
    """The weekly review: {"done", "open", "next": [(day, title)]} from the marks of the last seven days, the cards
    that need the person and the deadlines of the next seven days."""
    since = time.time() - WEEK_DAYS * 86400
    done = sum(1 for v in fuerdich.marks(uid).values() if v[0] == "done" and v[1] >= since)
    soon = [(fuerdich.deadline(x), fuerdich.sentence(x, today)[0]) for x in items if fuerdich.deadline(x)]
    end = (today + datetime.timedelta(days=WEEK_DAYS)).isoformat()
    nxt = sorted((d, t) for d, t in soon if today.isoformat() <= d <= end)
    return {"done": done, "open": sum(1 for x in items if x["kind"] in fuerdich.URGENT), "next": nxt[:5]}


def week_sentence(w, today):
    head = f"Deine Woche: {w['done']} erledigt, {w['open']} offen."
    if not w["next"]:
        return head + " Nächste Woche keine Fristen aus deinen Mails."
    return head + " Nächste Woche: " + "; ".join(f"{fuerdich.day_word(d, today)} {t}" for d, t in w["next"][:3]) + "."


# ---------------------------------------------------------------- Aus dem Netz (4a)
def tip_of(uid):
    """The last web tip while it is fresh ({"name", "title", "url", "domain", "day"}), else None."""
    t = load(uid)["tip"]
    if not t or time.time() - int(t.get("t") or 0) > TIP_KEEP:
        return None
    return {k: t.get(k, "") for k in ("name", "title", "url", "domain", "day")}


def _ccfg():
    return load_config().get("chat", {})


def tip_allowed(uid):
    """The web tip needs the web search released for this profile and an address of the search (SearXNG)."""
    return bool(features.allowed("ichweiss", uid) and features.allowed("search", uid)
                and str(_ccfg().get("search_url") or "").strip())


def _tip_word(uid, today):
    web = sorted((v for v in load(uid)["items"].values() if v["state"] == "yes" and v["web"]), key=lambda v: v["name"])
    return web[today.toordinal() % len(web)]["name"] if web else ""


def _safe_url(u):
    u = str(u or "").strip()
    if not re.fullmatch(r"https://[A-Za-z0-9.\-]{3,253}(?::\d{1,5})?(?:/[^\s<>\"']{0,500})?", u):
        return "", ""
    return u, u.split("/")[2].split(":")[0].lower()


async def tip_run(uid, now):
    """At most once a day: one search with only the interest word (never mail text, never more than the word); the
    first result with a safe https address becomes the tip. Returns the tip or None."""
    import chat
    import httpx
    d = load(uid)
    day = now.date().isoformat()
    if (d["tip"] or {}).get("day") == day:
        return None
    word = _tip_word(uid, now.date())
    if not word:
        return None
    cc = _ccfg()
    d["tip"] = {"day": day, "t": int(time.time()), "name": word, "title": "", "url": "", "domain": ""}
    _save(uid, d)                        # tried today, whatever comes back
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=5)) as c:
            _, sources = await chat.web_search(c, dict(cc, search_pages=0, search_results=5), word)
    except Exception as e:
        print(f"ichweiss: netztipp fehler={type(e).__name__}", flush=True)
        return None
    for s in sources:
        url, dom = _safe_url(s.get("url"))
        if url:
            d = load(uid)
            d["tip"] = dict(d["tip"] or {}, title=fuerdich._one(s.get("title") or dom, 120), url=url, domain=dom)
            _save(uid, d)
            _day.bump("netztipp")
            _live("Netz-Tipp gefunden")
            print("ichweiss: netztipp gefunden", flush=True)
            return tip_of(uid)
    print("ichweiss: netztipp ohne treffer", flush=True)
    return None


async def due_once(now=None):
    """Called once a minute (extras.due_once): the web tip of the day for every profile that allows it."""
    import chat
    for uid in profiles.user_ids():
        if not tip_allowed(uid) or notaus.refuse("auto", uid):
            continue
        local = now.astimezone(chat.user_zone(profiles.effective(uid).get("tz", ""))) if now else \
            datetime.datetime.now(chat.user_zone(profiles.effective(uid).get("tz", "")))
        if not TIP_HOURS[0] <= local.hour < TIP_HOURS[1] or (load(uid)["tip"] or {}).get("day") == local.date().isoformat():
            continue
        try:
            await vorrang.quiet("Netz-Tipp")
            await tip_run(uid, local)
        except Exception as e:
            print(f"ichweiss: netztipp fehler={type(e).__name__}", flush=True)


# ---------------------------------------------------------------- the page
VIEW_BUDGET = 6.0
_tasks = {}


def _rec_reading(uid):
    t = _tasks.get(uid)
    if t is None or t.done():
        t = _tasks[uid] = asyncio.ensure_future(vorrang.in_thread("Für dich", recurring_scan, uid))
        t.add_done_callback(lambda f: f.cancelled() or f.exception())
    return t


async def view(prof):
    uid = prof["id"]
    import chat
    zone = chat.user_zone(profiles.effective(uid).get("tz", ""))
    today = datetime.datetime.now(zone).date()
    loading = []
    try:
        items, _ = await asyncio.wait_for(asyncio.shield(fuerdich._reading(uid)), VIEW_BUDGET) if mail.get(uid)["accounts"] else ([], [])
    except Exception:
        items = []
        loading.append("fuerdich")
    rec = []
    if mail.get(uid)["accounts"]:
        hit = _rec.get(uid)
        if hit:
            rec = hit[1]
            if time.time() - hit[0] >= REC_SECONDS:
                _rec_reading(uid)
        else:
            try:
                rec = await asyncio.wait_for(asyncio.shield(_rec_reading(uid)), VIEW_BUDGET)
            except Exception:
                loading.append("wiederkehrend")
    texts = {x["text"] for x in profiles.reminders(uid)}
    d = load(uid)
    w = week(uid, items, today)
    m = month_sum(items, today)
    facts = profiles.memory(uid)
    style = {}
    if features.allowed("mailstil", uid):
        import mailstil
        s = mailstil.public(uid)
        style = {"mails": s["mails"], "learned": s["learned"]}
    return {"interests": sorted(({"name": v["name"], "state": v["state"], "web": v["web"], "src": v["src"], "t": v["t"],
                                  "topic": v["topic"], "en": topic_name(v["topic"], True) or v["name"], "senders": v["senders"],
                                  "old": _old_sender(v)}
                                 for v in d["items"].values()), key=lambda v: (v["state"] != "yes", v["name"].lower())),
            "proposals": proposals(uid), "asks": asks(uid), "choices": choices(uid), "sources": SOURCES,
            "recurring": [dict(x, set=rec_text(x) in texts) for x in rec],
            "week": dict(w, sentence=week_sentence(w, today)),
            "month": dict(m, line=month_line(m)),
            "tip": tip_of(uid), "tips": tip_allowed(uid),
            "facts": {"count": len(facts), "items": [str(x.get("text", ""))[:200] for x in facts[-5:]][::-1]},
            "style": style, "loading": loading}


def month_line(m):
    if not m["n"]:
        return "Diesen Monat noch keine Beträge aus deinen Mails."
    return (f"Diesen Monat aus Mails: {euro(m['total'])} (Rechnungen {euro(m['bills'])}, Bestellungen {euro(m['orders'])}), "
            f"aus {m['n']} Mails.")


# ---------------------------------------------------------------- endpoints
def _mine(request, prof):
    if not features.allowed("ichweiss", prof["id"]):
        raise HTTPException(403, features.missing_text("ichweiss", prof["id"]) or "„Was ich über dich weiß“ ist aus.")
    guard.limit(request, "fuerdich", prof["id"])


@router.get("/api/profile/ichweiss", dependencies=[Depends(assistant)])
async def api_get(request: Request, prof=Depends(own_profile)):
    _mine(request, prof)
    out = await view(prof)
    _day.bump("angesehen")
    print(f"ichweiss: angesehen vorschlaege={len(out['proposals'])} interessen={len(out['interests'])} "
          f"wiederkehrend={len(out['recurring'])} {profiles.log_name(prof)}", flush=True)
    return out


@router.post("/api/profile/ichweiss/interest", dependencies=[Depends(assistant)])
async def api_interest(request: Request, prof=Depends(own_profile)):
    _mine(request, prof)
    b = await json_body(request, 2 * 1024)
    name, state, src, web = b.get("name"), b.get("state"), b.get("src", "hand"), b.get("web")
    topic, senders, to = b.get("topic", ""), b.get("senders", []), b.get("to", "")
    if not isinstance(name, str) or state not in ("yes", "no", "forget", "adopt", "keep", "rename", "drop") \
            or not isinstance(to, str) or (state == "rename" and len(to.strip()) < 2) \
            or (web is not None and not isinstance(web, bool)) or src not in SOURCES \
            or not isinstance(topic, str) or (topic and topic not in TOPICS) or (state == "adopt" and not topic) \
            or not isinstance(senders, list) or len(senders) > MAX_SENDERS or not all(isinstance(x, str) for x in senders) \
            or (state == "drop" and len(senders) != 1):
        print("ichweiss: interesse abgelehnt grund=eingabe", flush=True)
        raise HTTPException(400, "name, state (yes, no, forget, adopt, keep, rename, drop), web (true/false), topic, senders, to")
    try:
        if state == "adopt":
            item = adopt(prof["id"], name, topic)
        elif state == "keep":
            keep(prof["id"], name)
            item = None
        elif state == "rename":
            item = rename(prof["id"], name, to)
        elif state == "drop":
            item = drop(prof["id"], name, senders[0])
        else:
            item = set_state(prof["id"], name, state, src, web, topic or None, senders)
    except KeyError:
        print(f"ichweiss: interesse abgelehnt grund=fehlt {profiles.log_name(prof)}", flush=True)
        raise HTTPException(404, "Das gibt es nicht mehr. Bitte neu laden.")
    except ValueError:
        print("ichweiss: interesse abgelehnt grund=name", flush=True)
        raise HTTPException(400, "Ein Interesse braucht mindestens zwei Zeichen.")
    print(f"ichweiss: interesse als={state} {profiles.log_name(prof)}", flush=True)
    return {"ok": True, "item": item}


@router.post("/api/profile/ichweiss/recurring", dependencies=[Depends(assistant)])
async def api_recurring(request: Request, prof=Depends(own_profile)):
    _mine(request, prof)
    b = await json_body(request, 1024)
    rid, uid = b.get("id"), prof["id"]
    x = next((r for r in (_rec.get(uid) or (0, []))[1] if r["id"] == rid), None) if isinstance(rid, str) else None
    if x is None:
        print(f"ichweiss: erinnerung abgelehnt grund=fehlt {profiles.log_name(prof)}", flush=True)
        raise HTTPException(404, "Das gibt es nicht mehr. Bitte neu laden.")
    if not features.allowed("reminders", uid):
        print(f"ichweiss: erinnerung abgelehnt grund=aus {profiles.log_name(prof)}", flush=True)
        raise HTTPException(403, features.missing_text("reminders", uid) or "Timer und Erinnerungen sind aus.")
    if rec_text(x) in {r["text"] for r in profiles.reminders(uid)}:
        print(f"ichweiss: erinnerung schon da {profiles.log_name(prof)}", flush=True)
        return {"ok": True, "again": True}
    import chat
    now = datetime.datetime.now(chat.user_zone(profiles.effective(uid).get("tz", "")))
    item = profiles.add_reminder(uid, rec_text(x), int(next_monthly(x["day"], now).timestamp() * 1000), "monthly")
    _day.bump("erinnerung")
    print(f"ichweiss: erinnerung monatlich gesetzt {profiles.log_name(prof)}", flush=True)
    return {"ok": True, "text": item["text"], "due": item["due"]}


@router.delete("/api/profile/ichweiss", dependencies=[Depends(assistant)])
def api_forget(request: Request, prof=Depends(browser_profile)):
    _mine(request, prof)
    forget(prof["id"])
    print(f"ichweiss: geloescht {profiles.log_name(prof)}", flush=True)
    return {"ok": True}


def today_counts():
    return _day.counts()


def _live(what):
    try:
        import live
        live.event("Was ich über dich weiß", what)
    except Exception:
        pass
