"""KI-Dungeon-Master im Auto (CarPlay; Dominik 2026-10-23 „Alles umsetzten“, 2026-10-24 „alles nach Empfehlung“,
Punkte 8 bis 13 der Prüfseite „Dungeon-Master Spieltisch“).

The car shows no text (Apple's rule for voice apps): the iPhone app reads aloud what comes back and listens; what is
said comes back here. Every sentence of the car is built by this file from fixed words and numbers of the round; the
model's words are only the narration itself. The model decides nothing here.

- Without text: the newest narration after the number `nach` (with the round's own voices when its pieces are ready,
  vortrag), then a short summary of what happened: rolls, hits, damage, loot, a new level, who is down, whose turn it is
  (Punkt 8). While nothing is new the app asks again after a while without listening (warten).
- With text: a fixed question about the own hero or the fight (life, bag, fight, ways, merchant, who is missing, again, help)
  is answered at once. Anything that changes the game (an item put on, a spell, a potion, buying, selling, a value
  point, an ability, the host's „jetzt weiter“, and every action of the turn) is said back first: „Uma greift Goblin 1
  an. Passt das?“ (frage). Only the same request again with ok goes through, by the same rules as the buttons at the
  table (hero_act, act, maybe_close). A long sentence is always the action, never a command.
- rid picks one of the own running rounds (CarPlay lists them); without it the newest. neu offers three stories and
  starts the chosen one with the hero played last (Punkt 11); the app sends back only what it got under weiter.
"""
import re
import time

import dungeon_geschichten as geschichten

KURZ = 60                  # characters: only a short sentence is a fixed question or command; a longer one is the action
EREIGNIS_MAX = 8           # sentences of the summary after a narration
DINGE_MAX = 8              # items named for the bag or the merchant
TON_WARTEN = 90            # seconds the car waits for the round's own voices before it reads with the assistant's
WAHL = 3                   # stories offered for a new round

# the fixed questions and commands, the first that matches counts; a command needs the hero's „ja“ (ok)
FRAGEN = (
    ("nochmal", re.compile(r"(?i)^\W*(wiederhol\w*|noch ?mal|nochmal( bitte)?|repeat( that)?|say (it|that) again)\W*$")),
    ("hilfe", re.compile(r"(?i)^\W*(hilfe|was kann ich sagen|welche befehle\w*|help|what can i say)\W*$")),
    ("weiter", re.compile(r"(?i)^\W*(jetzt weiter|weiter jetzt|nächster zug|go on now|next turn( now)?)\W*$")),
    ("kampf", re.compile(r"(?i)\b(wie steht (es um )?(der|den) kampf|kampfstand|wie geht es den gegnern|wie viel leben haben die gegner|"
                         r"how is the fight|how are the foes|fight status)\b")),
    ("haendler", re.compile(r"(?i)\b(was (verkauft|hat|bietet) (der )?h[äa]ndler|was gibt es zu kaufen|h[äa]ndler\W*$|"
                            r"what does the merchant (sell|have)|what is for sale|merchant\W*$)")),
    ("trank_an", re.compile(r"(?i)^\W*(gib|give) (?P<wer>\w+) (einen |den |deinen |meinen |a |my |the )?(\w*trank|potion)\W*$")),
    ("trinken", re.compile(r"(?i)\b(trink\w*|drink\w*)\b.*\b(\w*trank|potion)\b")),
    ("anlegen", re.compile(r"(?i)^\W*(leg|zieh|nimm|rüste) (?P<was>.+?) (an|in die hand|aus)\W*$|^\W*(equip|put on|wear|wield) (?P<was2>.+?)\W*$")),
    ("wirken", re.compile(r"(?i)^\W*(wirke?|zaubere?|sprich) (?P<was>.+?)\W*$|^\W*cast (?P<was2>.+?)\W*$")),
    ("aufheben", re.compile(r"(?i)^\W*(heb|hebe|nimm) (?P<was>.+?) (auf|mit)\W*$|^\W*pick up (?P<was2>.+?)\W*$")),
    ("verkaufen", re.compile(r"(?i)^\W*(verkauf\w*) (?P<was>.+?)\W*$|^\W*sell (?P<was2>.+?)\W*$")),
    ("kaufen", re.compile(r"(?i)^\W*(kauf\w*) (?P<was>.+?)\W*$|^\W*buy (?P<was2>.+?)\W*$")),
    ("punkt", re.compile(r"(?i)\b(wert)?punkt (auf|in|für) (?P<was>\w+)|\bpoint (in|on|to|into) (?P<was2>\w+)")),
    ("faehigkeit", re.compile(r"(?i)^\W*(die |the )?(?P<was>erste|zweite|dritte|eins|zwei|drei|first|second|third|1|2|3)\.?( fähigkeit| ability| one)?\W*$")),
    ("leben", re.compile(r"(?i)\b(wie ?viel\w*\b.*\bleben|lebenspunkte|wie geht es (mir|meinem helden)|how much (life|health)|hit points|my health)\b")),
    ("tasche", re.compile(r"(?i)\b(tasche|inventar|was trage ich|what do i carry|my bag|inventory)\b")),
    ("warten", re.compile(r"(?i)\b(auf wen warten|wer fehlt|who are we waiting for|who is missing)\b")),
    ("kann", re.compile(r"(?i)\b(was (kann ich|können wir|koennen wir) (hier |jetzt )?(tun|machen)|"
                        r"what can (i|we) do( here| now)?)\b")),
    ("wohin", re.compile(r"(?i)\b(wohin (können|koennen|kann) (wir|ich)( gehen)?|welche wege|wo geht es (hin|weiter)|"
                         r"where can (we|i) go|which ways)\b")))
TUN = ("trank_an", "trinken", "anlegen", "wirken", "aufheben", "verkaufen", "kaufen", "punkt", "faehigkeit", "weiter", "aktion")
_ZAHL = {"erste": 0, "eins": 0, "first": 0, "1": 0, "zweite": 1, "zwei": 1, "second": 1, "2": 1, "dritte": 2, "drei": 2, "third": 2, "3": 2}
_FUELL = re.compile(r"(?i)\b(den|die|das|dem|der|des|einen|eine|ein|meinen|meine|mein|deinen|deine|dein|the|a|an|my)\b")

SAGEN = {
    "keine": ("Du sitzt gerade in keiner laufenden Runde. Sag „Neue Runde“ oder leg im Panel unter Dungeon-Master eine an.",
              "You are not in a running round. Say „new round“ or start one in the panel under Dungeon Master."),
    "dran": ("{name} ist dran. Was tust du?", "It is {name}'s turn. What do you do?"),
    "pause": ("Die Runde ist gerade pausiert. Du kannst deine Aktion schon sagen, es geht weiter, sobald der Spielleiter fortsetzt.",
              "The round is paused right now. You may say your action already, it goes on as soon as the game master continues."),
    "leben": ("{name} hat {leben} von {max} Leben.", "{name} has {leben} of {max} life."),
    "tasche": ("In der Tasche: {dinge}. Dazu {gold} Gold.", "In the bag: {dinge}. And {gold} gold."),
    "leer": ("Die Tasche ist leer. Du hast {gold} Gold.", "The bag is empty. You have {gold} gold."),
    "trinken": ("{name} trinkt {trank}.", "{name} drinks {trank}."),
    "geben": ("{name} gibt {wer} {trank}.", "{name} gives {wer} {trank}."),
    "getrunken": ("{wer} hat jetzt {leben} von {max} Leben.", "{wer} now has {leben} of {max} life."),
    "kein_trank": ("Du hast keinen Trank in der Tasche.", "You have no potion in the bag."),
    "wer_nicht": ("Ich finde niemanden namens {wer} am Tisch.", "I find nobody called {wer} at the table."),
    "noch_nichts": ("Der Dungeon-Master hat noch nichts erzählt.", "The Dungeon Master has not told anything yet."),
    "warten": ("Wir warten noch auf {namen}.", "We are still waiting for {namen}."),
    "wege": ("Von hier aus: {wege}.", "From here: {wege}."),
    "weg": ("{richtung}: {ziel}", "{richtung}: {ziel}"),
    "keine_wege": ("Von hier aus kenne ich keinen Weg.", "I know no way from here."),
    "kann_nichts": ("Gerade habe ich keinen Vorschlag. Sag einfach, was dein Held tut.",
                    "I have no suggestion right now. Just say what your hero does."),
    "alle": ("Alle haben gehandelt, der Dungeon-Master erzählt gleich.", "Everyone has acted, the Dungeon Master tells it shortly."),
    "notiert": ("Notiert. Wir warten noch auf {namen}. Ich melde mich, wenn du dran bist.",
                "Noted. We are still waiting for {namen}. I will speak up when it is your turn."),
    "notiert_alle": ("Notiert. Der Dungeon-Master erzählt. Ich melde mich gleich.", "Noted. The Dungeon Master is telling it. I will speak up shortly."),
    "erzaehlt": ("Der Dungeon-Master erzählt gerade, gleich bist du dran.", "The Dungeon Master is telling it right now, your turn comes shortly."),
    "sagt": ("{name} sagt: {text}", "{name} says: {text}"),
    "passt": ("{was} Passt das?", "{was} Is that right?"),
    "aktion": ("{name}: {text}.", "{name}: {text}."),
    "anlegen": ("{name} legt {ding} an.", "{name} puts on {ding}."),
    "angelegt": ("{name} trägt jetzt {ding}.", "{name} now wears {ding}."),
    "wirken": ("{name} wirkt {ding}.", "{name} casts {ding}."),
    "gewirkt": ("{name} wirkt {ding}. Der Dungeon-Master erzählt die Wirkung.", "{name} casts {ding}. The Dungeon Master tells what it does."),
    "aufheben": ("{name} hebt {ding} auf.", "{name} picks up {ding}."),
    "aufgehoben": ("{ding} ist jetzt in deiner Tasche.", "{ding} is in your bag now."),
    "kaufen": ("{name} kauft {ding} für {gold} Gold.", "{name} buys {ding} for {gold} gold."),
    "gekauft": ("Gekauft: {ding}. Du hast noch {gold} Gold.", "Bought: {ding}. You have {gold} gold left."),
    "verkaufen": ("{name} verkauft {ding} für {gold} Gold.", "{name} sells {ding} for {gold} gold."),
    "verkauft": ("Verkauft: {ding}. Du hast jetzt {gold} Gold.", "Sold: {ding}. You now have {gold} gold."),
    "punkt": ("{name} setzt einen Wertpunkt auf {wert}.", "{name} puts a value point on {wert}."),
    "gesetzt": ("{wert} ist jetzt {zahl}.", "{wert} is {zahl} now."),
    "faehigkeit": ("{name} lernt {ding}.", "{name} learns {ding}."),
    "gelernt": ("{name} kann jetzt {ding}.", "{name} can {ding} now."),
    "weiter": ("Du schließt den Zug jetzt.", "You close the turn now."),
    "weiter_ok": ("Der Zug ist zu. Der Dungeon-Master erzählt.", "The turn is closed. The Dungeon Master is telling it."),
    "nicht_gastgeber": ("Das darf nur der Gastgeber der Runde.", "Only the round's host can do that."),
    "keine_aktion": ("Noch hat niemand gehandelt.", "Nobody has acted yet."),
    "nicht_da": ("Ich finde {was} nicht.", "I cannot find {was}."),
    "kein_zauber": ("{ding} ist kein Zauber aus deiner Tasche. Sag es als Aktion, etwa „Ich wirke {ding} auf den Goblin“.",
                    "{ding} is no spell from your bag. Say it as your action, for example „I cast {ding} on the goblin“."),
    "kein_haendler": ("Hier ist gerade kein Händler.", "There is no merchant here right now."),
    "ware": ("{haendler} verkauft: {dinge}.", "{haendler} sells: {dinge}."),
    "keine_wahl": ("Gerade gibt es keine Fähigkeit zu wählen.", "There is no ability to choose right now."),
    "wahl": ("Du kannst wählen: {dinge}. Sag „die erste“, „die zweite“ oder „die dritte“.",
             "You can choose: {dinge}. Say „the first“, „the second“ or „the third“."),
    "keine_punkte": ("Du hast gerade keinen Wertpunkt.", "You have no value point right now."),
    "kein_kampf": ("Gerade gibt es keinen Kampf.", "There is no fight right now."),
    "gegner": ("{name} hat {leben} von {max} Leben", "{name} has {leben} of {max} life"),
    "gegner_lage": ("{name} ist {lage}", "{name} is {lage}"),
    "gegner_aus": ("{name} ist besiegt", "{name} is defeated"),
    "geht_nicht": ("Das geht gerade nicht.", "That does not work right now."),
    "passt_nicht": ("Das passt deinem Helden gerade nicht.", "That does not fit your hero right now."),
    "tasche_voll": ("Die Tasche ist voll.", "The bag is full."),
    "gold": ("Dafür reicht das Gold nicht.", "There is not enough gold for that."),
    "am_boden": ("{name} liegt am Boden und kann das gerade nicht.", "{name} is down and cannot do that right now."),
    "hilfe": ("Du kannst sagen: wie viel Leben habe ich, was ist in meiner Tasche, wie steht der Kampf, wohin können wir, was kann ich tun, was verkauft der Händler, "
              "trink einen Heiltrank, gib Bela einen Trank, leg den Dolch an, wirke Feuerpfeil, heb den Schlüssel auf, kauf, verkauf, "
              "Punkt auf Stärke, die erste, wer fehlt, nochmal, als Gastgeber jetzt weiter, und Stopp zum Aufhören. Alles andere ist deine Aktion.",
              "You can say: how much life do I have, what is in my bag, how is the fight, where can we go, what can I do, what does the merchant sell, drink a healing "
              "potion, give Bela a potion, put on the dagger, cast fire bolt, pick up the key, buy, sell, point on strength, the first, "
              "who is missing, again, as host go on now, and stop to quit. Anything else is your action."),
    # a new round in the car (Punkt 11)
    "geschichten": ("Drei Geschichten: {liste}. Welche nimmst du?", "Three stories: {liste}. Which one do you take?"),
    "geschichte": ("{nr}: {titel}", "{nr}: {titel}"),
    "keine_geschichte": ("Gerade gibt es keine Geschichte zur Auswahl. Leg die Runde bitte im Panel an.",
                         "There is no story to choose right now. Please start the round in the panel."),
    "welche": ("Welche Geschichte? Sag „die erste“, „die zweite“ oder „die dritte“.", "Which story? Say „the first“, „the second“ or „the third“."),
    "kein_held": ("Du hast keinen freien Helden. Leg im Panel unter Dungeon-Master einen an.",
                  "You have no free hero. Make one in the panel under Dungeon Master."),
    "neu": ("{titel} mit {held}.", "{titel} with {held}."),
    "neu_ok": ("Die Runde {titel} beginnt. Der Dungeon-Master erzählt gleich, ich melde mich dann.",
               "The round {titel} begins. The Dungeon Master tells it shortly, I will speak up then."),
    "runden_voll": ("Du hast schon so viele Runden, wie gehen. Beende eine im Panel.", "You have as many rounds as allowed. End one in the panel."),
    # the summary after a narration (Punkt 8): only names, fixed words and numbers of the round
    "wurf_ok": ("{name} schafft die {wert}-Probe mit {gesamt} gegen {schwer}.", "{name} passes the {wert} check with {gesamt} against {schwer}."),
    "wurf_nein": ("{name} schafft die {wert}-Probe nicht, {gesamt} gegen {schwer}.", "{name} fails the {wert} check, {gesamt} against {schwer}."),
    "trifft": ("{name} trifft {gegner} für {schaden}.", "{name} hits {gegner} for {schaden}."),
    "krit": ("{name} trifft {gegner} kritisch für {schaden}.", "{name} hits {gegner} critically for {schaden}."),
    "verfehlt": ("{name} verfehlt {gegner}.", "{name} misses {gegner}."),
    "schaden": ("{name} verliert {zahl} Leben, noch {leben}.", "{name} loses {zahl} life, {leben} left."),
    "heilung": ("{name} heilt {zahl} Leben, jetzt {leben}.", "{name} heals {zahl} life, now {leben}."),
    "beute": ("Beute für {name}: {ding}.", "Loot for {name}: {ding}."),
    "beute_gold": ("Beute für {name}: {gold} Gold.", "Loot for {name}: {gold} gold."),
    "stufe": ("{name} erreicht Stufe {stufe}.", "{name} reaches level {stufe}."),
    "boden": ("{name} liegt am Boden.", "{name} is down."),
    "ohnmacht": ("{name} ist ohnmächtig.", "{name} is unconscious."),
    "gnade": ("Ein Fremder rettet {name}.", "A stranger saves {name}."),
    "todeswurf": ("{name} würfelt einen Rettungswurf: {wurf}.", "{name} rolls a death save: {wurf}."),
    "tot": ("{name} ist gefallen.", "{name} has fallen."),
    "auf": ("{name} steht wieder.", "{name} is up again."),
    "stabil": ("{name} ist stabil, aber bewusstlos.", "{name} is stable but unconscious."),
    "zauber": ("{name} wirkt {zauber}.", "{name} casts {zauber}."),
    "sieg": ("Der Kampf ist gewonnen.", "The fight is won."),
    "kampf_ende": ("Der Kampf ist vorbei.", "The fight is over."),
    "mehr": ("Und mehr, am Tisch zu sehen.", "And more, to see at the table.")}
EREIGNIS_ARTEN = ("wurf", "angriff", "folge", "beute", "stufe", "zustand", "todeswurf", "zauber", "kampf")


WORTE_S = 600             # Tabletop-Punkt 14: for so long after the car's last game request its recordings hear the round's names
_im_auto = {}             # uid -> time of the last game request from the car (memory only)


def _dm():
    import dungeon
    return dungeon


def im_auto(uid, now=None):
    """Whether the profile plays from the car now: its last game request from there is at most WORTE_S old (a guest
    without a profile never; the real dice of dungeon_echt never ask a seat in the car)."""
    now = time.time() if now is None else now
    return bool(uid) and now - _im_auto.get(uid, 0) <= WORTE_S


def words(uid, now=None):
    """The names of the profile's round (dungeon.heard_words) for the car's recordings while it plays from the car,
    [] otherwise."""
    if not im_auto(uid, now):
        return []
    dm = _dm()
    rid, pid = _seat(dm, uid, "")
    return dm.heard_words(dm.rules(), dm._read()["runden"][rid], pid) if rid else []


def _say(k, li, **kw):
    return SAGEN[k][li].format(**kw)


def told(e, li):
    """A narration as it is read aloud in the car: the text, then every NPC's line not already in it."""
    dm = _dm()
    return " ".join([e["text"]] + [_say("sagt", li, name=n["name"], text=n["sagt"]) for n in e.get("npc") or []
                                   if not dm.vortrag.in_text(n["sagt"], e["text"])])


# ---------------------------------------------------------------- reading only (Punkt 8, 10, 12)
def events(rd, pid, seit):
    """The entries after the log position seit that the car tells after a narration, as the seat sees them."""
    dm = _dm()
    return [e for e in (rd.get("log") or [])[seit:] if e.get("art") in EREIGNIS_ARTEN and dm.shown(e, pid)]


def summary(r, rd, pid, li, seit):
    """Punkt 8: the fixed sentences of what happened since the previous narration, at most EREIGNIS_MAX."""
    werte = {w["id"]: w["name"][li] for w in r["werte"]}
    out = []
    for e in events(rd, pid, seit):
        n, a = e.get("name", ""), e["art"]
        if a == "wurf" and "ok" in e:
            out.append(_say("wurf_ok" if e["ok"] else "wurf_nein", li, name=n, wert=werte.get(e.get("wert"), e.get("wert", "")),
                            gesamt=e.get("gesamt", 0), schwer=e.get("schwer", 0)))
        elif a == "angriff":
            if e.get("von_gegner"):   # a foe attacks the hero: the damage comes as its own „folge“
                out.append(_say("trifft" if e.get("treffer") else "verfehlt", li, name=e.get("gegner", ""), gegner=n, schaden=e.get("schaden", 0)))
            else:
                k = "verfehlt" if not e.get("treffer") else "krit" if e.get("krit") else "trifft"
                out.append(_say(k, li, name=n, gegner=e.get("gegner", ""), schaden=e.get("schaden", 0)))
        elif a == "folge" and e.get("was") in ("schaden", "heilung"):
            out.append(_say(e["was"], li, name=n, zahl=e.get("zahl", 0), leben=e.get("leben", 0)))
        elif a == "beute":
            if (e.get("item") or {}).get("name"):
                out.append(_say("beute", li, name=n, ding=e["item"]["name"]))
            elif e.get("gold"):
                out.append(_say("beute_gold", li, name=n, gold=e["gold"]))
        elif a == "stufe":
            out.append(_say("stufe", li, name=n, stufe=e.get("stufe", 0)))
        elif a == "zustand" and e.get("was") in ("boden", "ohnmacht", "tot", "auf", "gnade", "stabil"):
            out.append(_say(e["was"], li, name=n, noch=e.get("noch", 0)))
        elif a == "todeswurf":
            out.append(_say("todeswurf", li, name=n, wurf=e.get("wurf", 0)))
        elif a == "zauber":
            out.append(_say("zauber", li, name=n, zauber=e.get("zauber", "")))
        elif a == "kampf":
            out.append(_say("sieg" if e.get("was") == "sieg" else "kampf_ende", li))
    if len(out) > EREIGNIS_MAX:
        out = out[:EREIGNIS_MAX - 1] + [_say("mehr", li)]
    return out


def stand(rd, li, host=True):
    """Punkt 10: every foe of the fight with its life, or None without a fight; only the host hears the numbers, every
    other seat its state as a word (Tabletop-Punkt 11)."""
    import dungeon_kampf as kampf
    k = rd.get("kampf")
    if not k:
        return None
    return [_say("gegner_aus", li, name=g["name"]) if g.get("aus") or g.get("leben", 0) <= 0
            else _say("gegner", li, name=g["name"], leben=max(0, g["leben"]), max=g["max"]) if host
            else _say("gegner_lage", li, name=g["name"], lage=kampf.lage(g)[1][li]) for g in k.get("gegner") or []]


def ton_ready(rd, e):
    """Punkt 12: the round's own pieces of this narration ({"n", "k"} once all are made), "wait" while they are being
    made (at most TON_WARTEN after the reading began), else None: the car reads it with the assistant's voice."""
    le = rd.get("lesung") or {}
    if not rd.get("vorlesen") or le.get("n") != e.get("n"):
        return None
    if le.get("fertig"):
        return {"n": le["n"], "k": le.get("k", 0)} if le.get("k") else None
    if rd.get("spricht") and time.time() - rd["spricht"] < TON_WARTEN:
        return "wait"
    return None


# ---------------------------------------------------------------- matching what was said
def _words(s):
    return [w for w in re.findall(r"\w+", _FUELL.sub(" ", s.lower())) if len(w) > 1]


def find(items, said):
    """The item whose name fits the spoken words best: every word said is in its name (or its name in what was said)."""
    ws = _words(said)
    if not ws:
        return None
    for x in items:
        name = x["name"].lower()
        if all(w in name for w in ws) or name in said.lower():
            return x
    for x in items:   # a single word that fits („den Dolch“ for „Dolch des Wanderers“)
        if any(w in _words(x["name"]) for w in ws):
            return x
    return None


def _what(m):
    return (m.groupdict().get("was") or m.groupdict().get("was2") or "").strip()


# ---------------------------------------------------------------- the round
def _seat(dm, uid, rid):
    """(rid, pid) of the own seat with a hero in a running round: the one asked for, else the newest."""
    seats = sorted(((rd.get("made", 0), k, pid) for k, rd in dm._read()["runden"].items() if rd.get("status") == "laeuft"
                    for pid, p in rd["plaetze"].items() if p.get("uid") == uid and p.get("held")), reverse=True)
    pick = [s for s in seats if s[1] == rid] if rid else seats
    return (pick[0][1], pick[0][2]) if pick else (None, None)


def car(uid, text="", nach=0, lang="de", rid="", ok=False, neu=False, wahl=None, rf=False):
    """The game in the car. Returns {"sagen", "n", "warten", "aus", "rid"} and, when it fits, "danach" (the summary
    after the narration), "ton" (the round's pieces to play before danach), "frage" (said back, ok goes through),
    "weiter" (fields for the next request), "prolog" (a new round whose opening the endpoint starts), "vorschlaege"
    (an unclear action's suggestions as CarPlay buttons, dungeon_rueckfrage, or „Das kannst du hier“ of
    dungeon_anleiten with "vorschlaege_titel"; rf: the next text answers it)."""
    dm = _dm()
    r = dm.rules()
    li = 1 if lang == "en" else 0
    _im_auto[uid] = time.time()
    text = dm._clean(text, dm.TEXT_MAX)
    if neu:
        return new_round(dm, r, uid, text, lang, li, wahl, ok)
    rid, pid = _seat(dm, uid, rid)
    if not rid:
        return {"sagen": _say("keine", li), "n": 0, "warten": False, "aus": True, "rid": ""}
    dm.maybe_close(rid)
    rd = dm._read()["runden"][rid]
    li = 1 if rd["lang"] == "en" else 0
    h = rd["plaetze"][pid]["held"]
    log = rd.get("log") or []
    erz = [i for i, e in enumerate(log) if e["art"] == "dm"]
    last = log[erz[-1]] if erz else None
    n = last.get("k", 0) if last else 0
    names = [p["held"]["name"] for q, p in dm.seated(rd) if q not in rd["offen"]]

    def out(k, warten=False, **kw):
        return {"sagen": _say(k, li, **kw), "n": n, "warten": warten, "aus": False, "rid": rid}
    if not text:
        if last and n > nach:
            tr = ton_ready(rd, last)
            if tr == "wait":
                return {"sagen": "", "n": nach, "warten": True, "aus": False, "rid": rid}
            after = summary(r, rd, pid, li, erz[-2] + 1 if len(erz) > 1 else 0)
            if not rd.get("dm") and pid not in rd["offen"] and not dm.zustand(h):
                after.append(_say("pause", li) if rd.get("pause") else _say("dran", li, name=h["name"]))
            import dungeon_anleiten
            k = dungeon_anleiten.car(dm, r, rd, pid, li) if dungeon_anleiten.stufe(rd) == "einsteiger" and not rd.get("pause") else None
            if k:                                # Einsteiger: the buttons said after the narration, as the CarPlay list too
                after.append(k["sagen"])
            return {"sagen": told(last, li), "danach": " ".join(after), "n": n, "warten": False, "aus": False, "rid": rid,
                    **({"ton": dict(tr, rid=rid)} if tr else {}),
                    **({"vorschlaege": k["vorschlaege"], "vorschlaege_titel": k["titel"], "weiter": {"rf": True}} if k else {})}
        if rd.get("dm") or pid in rd["offen"]:
            return {"sagen": "", "n": n, "warten": True, "aus": False, "rid": rid}
        return out("pause") if rd.get("pause") else out("dran", name=h["name"])   # paused by the host: said, not „dran“
    import dungeon_anleiten
    import dungeon_rueckfrage
    if rf and dungeon_rueckfrage.on(rd):         # the answer to the Rückfrage: a suggestion, „so lassen“, else a new action
        pick = dungeon_rueckfrage.answer(rd, pid, text)
        if pick:
            return _act_car(dm, r, rid, pid, pick, li, n, True)
    if rf and dungeon_anleiten.on(rd) and not dungeon_rueckfrage.waiting(rd, pid):   # a pick of „Das kannst du hier“
        if dungeon_rueckfrage.SO_LASSEN.match(text):
            return out("dran", name=h["name"])
        pick = dungeon_anleiten.answer(dm, r, rd, pid, text)
        if pick:
            return _act_car(dm, r, rid, pid, pick, li, n, True)
    kind = next((k for k, rx in FRAGEN if rx.search(text)), "aktion") if len(text) <= KURZ else "aktion"
    if kind == "aktion" and not ok and dungeon_rueckfrage.on(rd) and dungeon_rueckfrage.unclear(dm, r, rd, pid, text):
        return _act_car(dm, r, rid, pid, text, li, n, False)   # kept as written and asked: the turn never waits on the car
    dm._day.bump("auto")
    print(f"dungeon: auto | {kind}{' | ok' if ok and kind in TUN else ''}", flush=True)
    if kind == "nochmal":
        return {"sagen": told(last, li), "n": n, "warten": False, "aus": False, "rid": rid} if last else out("noch_nichts")
    if kind == "hilfe":
        return out("hilfe")
    if kind == "leben":
        return out("leben", name=h["name"], leben=h["leben"], max=h["leben_max"])
    if kind == "tasche":
        dinge = [(f"{x['n']} " if x.get("n", 1) > 1 else "") + dm.item_view(r, x, rd["lang"])["name"] for x in h["tasche"]]
        return out("tasche", dinge=", ".join(dinge[:DINGE_MAX]), gold=h["gold"]) if dinge else out("leer", gold=h["gold"])
    if kind == "warten":
        return out("warten", namen=", ".join(names)) if names else out("alle")
    if kind == "wohin":   # the ways of the map, only what a seat may see (dungeon_karte.wege, the same as „Von hier aus“)
        import dungeon_karte
        w = dungeon_karte.wege(rd, rd["lang"])[:DINGE_MAX]
        return out("wege", wege=", ".join(_say("weg", li, **x) for x in w)) if w else out("keine_wege")
    if kind == "kann":   # Spieler anleiten: the seat's buttons, said and as the CarPlay list (dungeon_anleiten.car)
        k = dungeon_anleiten.car(dm, r, rd, pid, li)
        if not k:
            return out("kann_nichts")
        return {"sagen": k["sagen"], "vorschlaege": k["vorschlaege"], "vorschlaege_titel": k["titel"], "weiter": {"rf": True},
                "n": n, "warten": False, "aus": False, "rid": rid}
    if kind == "kampf":
        s = stand(rd, li, rd.get("owner") == uid)
        return {"sagen": ". ".join(s) + "." if s else _say("kein_kampf", li), "n": n, "warten": False, "aus": False, "rid": rid}
    if kind == "haendler":
        m = dm.market_view(r, rd, h, rd["lang"])
        if not m:
            return out("kein_haendler")
        dinge = [f"{x['name']} für {x['preis']}" if not li else f"{x['name']} for {x['preis']}" for x in m["ware"][:DINGE_MAX]]
        return out("ware", haendler=m["name"], dinge=", ".join(dinge))
    if kind == "faehigkeit" and not h.get("wahl"):
        return out("keine_wahl")
    return do(dm, r, rd, rid, pid, h, kind, text, ok, li, n, names, out, uid)


def do(dm, r, rd, rid, pid, h, kind, text, ok, li, n, names, out, uid):
    """Everything that changes the game: said back first (frage), done only with ok, by the rules of the table."""
    lang = rd["lang"]
    m = next((rx.search(text) for k, rx in FRAGEN if k == kind), None)
    view = lambda x: dm.item_view(r, x, lang)
    b, ding, gold, zid = None, "", 0, None
    if kind == "aktion":
        if rd.get("dm"):
            return out("erzaehlt", warten=True)
        back = _say("aktion", li, name=h["name"], text=text.rstrip(".!?"))
    elif kind == "weiter":
        if rd["owner"] != uid:
            return out("nicht_gastgeber")
        if not rd["offen"]:
            return out("keine_aktion")
        back = _say("weiter", li)
    elif dm.zustand(h):
        return out("am_boden", name=h["name"])
    elif kind in ("trinken", "trank_an"):
        tr = sorted((x for x in h["tasche"] if dm._c(r, x)["art"] == "trank" and not dm._c(r, x).get("oel")), key=lambda x: not dm._c(r, x).get("heilung"))
        if not tr:
            return out("kein_trank")
        b, ding = {"was": "trinken", "i": tr[0]["i"]}, view(tr[0])["name"]
        if kind == "trank_an":
            wer = m.group("wer").lower()
            zid = next((q for q, p in dm.seated(rd) if q != pid and p["held"]["name"].lower().startswith(wer)), None)
            if not zid:
                return out("wer_nicht", wer=m.group("wer"))
            b["an"] = zid
            back = _say("geben", li, name=h["name"], wer=rd["plaetze"][zid]["held"]["name"], trank=ding)
        else:
            back = _say("trinken", li, name=h["name"], trank=ding)
    elif kind in ("anlegen", "wirken", "verkaufen", "aufheben", "kaufen"):
        mv = dm.market_view(r, rd, h, lang) if kind in ("kaufen", "verkaufen") else None
        if kind in ("kaufen", "verkaufen") and not mv:
            return out("kein_haendler")
        pool = mv["ware"] if kind == "kaufen" else [view(y) for y in (rd.get("boden") or [] if kind == "aufheben" else h["tasche"])]
        x = find(pool, _what(m))
        if kind == "wirken" and (not x or x["art"] != "zauber"):   # a spell of the class is cast in the action itself
            return out("kein_zauber", ding=_what(m))
        if not x:
            return out("nicht_da", was=_what(m))
        b, ding = {"was": kind, "i": x["i"]}, x["name"]
        gold = x.get("preis", 0) if kind == "kaufen" else mv["verkauf"].get(x["i"], 0) if kind == "verkaufen" else 0
        back = _say(kind, li, name=h["name"], ding=ding, gold=gold)
    elif kind == "punkt":
        if h.get("punkte", 0) < 1:
            return out("keine_punkte")
        w = next((w for w in r["werte"] if w["name"][li].lower().startswith(_what(m).lower()[:3])), None)
        if not w:
            return out("nicht_da", was=_what(m))
        b, ding = {"was": "punkt", "wert": w["id"]}, w["name"][li]
        back = _say("punkt", li, name=h["name"], wert=ding)
    else:   # faehigkeit: one of the abilities offered at a new level, by its place
        fa = {x["id"]: x for x in dm._by(r, "klassen")[h["klasse"]]["faehigkeiten"]}
        wahl = [x for x in h["wahl"] if x in fa]
        i = _ZAHL.get(_what(m).lower())
        if i is None or i >= len(wahl):
            return out("wahl", dinge=", ".join(fa[x]["name"][li] for x in wahl))
        b, ding = {"was": "faehigkeit", "id": wahl[i]}, fa[wahl[i]]["name"][li]
        back = _say("faehigkeit", li, name=h["name"], ding=ding)
    if not ok:
        return {"sagen": _say("passt", li, was=back), "frage": True, "n": n, "warten": False, "aus": False, "rid": rid}
    try:
        if kind == "aktion":
            with dm._lock:
                d = dm._read()
                cur = dm._round(d, rid)
                dm.act(cur, pid, text, cur["zug"], time.time())
                dm._write(d)
            dm.maybe_close(rid)
            rd = dm._read()["runden"][rid]
            names = [p["held"]["name"] for q, p in dm.seated(rd) if q not in rd["offen"]]
            return out("notiert", warten=True, namen=", ".join(names)) if names and not rd.get("dm") else out("notiert_alle", warten=True)
        if kind == "weiter":
            dm._host(rid, uid)
            if not dm.maybe_close(rid, force=True):
                return out("keine_aktion")
            print("dungeon: weiter | gastgeber | auto", flush=True)
            return out("weiter_ok", warten=True)
        dm.hero_act(rid, pid, b)
    except dm.KNOWN as e:
        why = e.args[0] if e.args and isinstance(e.args[0], str) else ""
        print(f"dungeon: auto | {kind} | abgelehnt", flush=True)
        return out(NEIN.get(why, "gold" if "gold" in why else "geht_nicht"))
    rd = dm._read()["runden"][rid]
    h = rd["plaetze"][pid]["held"]
    z = rd["plaetze"][zid]["held"] if zid else h
    k = {"trinken": "getrunken", "anlegen": "angelegt", "wirken": "gewirkt", "aufheben": "aufgehoben", "kaufen": "gekauft",
         "verkaufen": "verkauft", "punkt": "gesetzt", "faehigkeit": "gelernt"}[b["was"]]
    return out(k, name=h["name"], wer=z["name"], ding=ding, trank=ding, gold=h["gold"], leben=z["leben"], max=z["leben_max"],
               wert=ding, zahl=h["werte"].get(b.get("wert"), 0))


def _act_car(dm, r, rid, pid, text, li, n, chosen):
    """An action from the car with the Rückfrage (dungeon_rueckfrage): chosen (a suggestion or „so lassen“) goes in as
    it is; else it goes in as written and the question with its suggestions is said, the CarPlay list shows them."""
    import dungeon_rueckfrage
    try:
        with dm._lock:
            d = dm._read()
            cur = dm._round(d, rid)
            dm.act(cur, pid, text, cur["zug"], time.time())
            dungeon_rueckfrage.check(dm, r, cur, pid, chosen)
            dm._write(d)
    except dm.KNOWN as e:
        why = e.args[0] if e.args and isinstance(e.args[0], str) else ""
        print("dungeon: auto | aktion | abgelehnt", flush=True)
        return {"sagen": _say(NEIN.get(why, "geht_nicht"), li), "n": n, "warten": False, "aus": False, "rid": rid}
    dm.maybe_close(rid)
    rd = dm._read()["runden"][rid]
    f = dungeon_rueckfrage.view(rd, pid)
    if f:
        return {"sagen": dungeon_rueckfrage.car(rd, pid, li), "vorschlaege": f["vorschlaege"], "weiter": {"rf": True},
                "n": n, "warten": False, "aus": False, "rid": rid}
    names = [p["held"]["name"] for q, p in dm.seated(rd) if q not in rd["offen"]]
    k = "notiert" if names and not rd.get("dm") else "notiert_alle"
    return {"sagen": _say(k, li, namen=", ".join(names)), "n": n, "warten": True, "aus": False, "rid": rid}


NEIN = {"tasche voll": "tasche_voll", "passt nicht": "passt_nicht", "platz falsch": "passt_nicht"}


# ---------------------------------------------------------------- a new round in the car (Punkt 11)
def offer(dm, r, uid, lang):
    """WAHL stories to choose from: the host's own first (Eigene Geschichten), then the admin's and the shipped ones, those
    the profile played lately last."""
    played = {v.get("plan", {}).get("titel") for v in dm._read()["runden"].values() if v.get("owner") == uid and v.get("plan")}
    pool = [(k, g) for k, g, _ in geschichten.visible(r, uid, lang)]   # the own, the admin's, the Spark's (dungeon_geschichten)
    pool = [x for x in pool if x[1].get("titel") not in played] + [x for x in pool if x[1].get("titel") in played]
    return pool[:WAHL]


def hero_for(dm, uid):
    """The hero played last that is free (alive, in no running round), else the first free one."""
    d = dm._read()
    free = [x for x in dm.heroes(uid) if not x.get("tot") and not dm._in_play(d, x["hid"])]
    last = [p["held"]["hid"] for _, v in sorted(((v.get("made", 0), v) for v in d["runden"].values()), key=lambda x: -x[0])
            for p in v["plaetze"].values() if p.get("uid") == uid and p.get("held")]
    return next((x for hid in last for x in free if x["hid"] == hid), free[0] if free else None)


def new_round(dm, r, uid, text, lang, li, wahl, ok):
    out = lambda k, **kw: {"sagen": _say(k, li, **kw), "n": 0, "warten": False, "aus": False, "rid": ""}
    h = hero_for(dm, uid)
    if not h:
        return dict(out("kein_held"), aus=True)
    pool = offer(dm, r, uid, lang)
    gids = [k for k, _ in pool]
    if not gids:
        return dict(out("keine_geschichte"), aus=True)
    if not text:
        dm._day.bump("auto")
        print("dungeon: auto | neue runde | angeboten", flush=True)
        liste = "; ".join(_say("geschichte", li, nr=i + 1, titel=g["titel"]) for i, (_, g) in enumerate(pool))
        return dict(out("geschichten", liste=liste), weiter={"neu": True, "wahl": gids})
    wahl = [g for g in (wahl or []) if g in gids]       # only what this file offered, never a story the app names
    m = FRAGEN[[k for k, _ in FRAGEN].index("faehigkeit")][1].search(text)
    i = _ZAHL.get((_what(m) if m else "").lower())
    if i is None:
        i = next((j for j, g in enumerate(wahl) if find([{"name": geschichten.find(r, uid, g, lang)[0]["titel"]}], text)), None)
    if i is None or i >= len(wahl):
        return dict(out("welche"), weiter={"neu": True, "wahl": wahl or gids})
    g = geschichten.find(r, uid, wahl[i], lang)[0]
    if not ok:
        return dict(out("passt", was=_say("neu", li, titel=g["titel"], held=h["name"])), frage=True, weiter={"neu": True, "wahl": wahl})
    try:
        rid = dm.make_round(uid, {"geschichte": wahl[i], "titel": g["titel"], "held": h["hid"]}, lang)
    except OverflowError:
        return dict(out("runden_voll"), aus=True)
    except dm.KNOWN:
        print("dungeon: auto | neue runde | abgelehnt", flush=True)
        return dict(out("geht_nicht"), aus=True)
    dm._day.bump("auto")
    print("dungeon: auto | neue runde | ok", flush=True)
    return {"sagen": _say("neu_ok", li, titel=g["titel"]), "n": 0, "warten": True, "aus": False, "rid": rid, "prolog": rid}
