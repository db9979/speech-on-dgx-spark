"""The fight of the KI-Dungeon-Master (Punkt 2 of the review of 2026-10-24 with the foe points 1 and 2 and the item
points 1 and 9, Dominik „Ja, alles umsetzen“ / „Ja, alles nach Empfehlung umsetzen“): the panel sets the encounter by
a budget, rolls every attack and keeps the foes' life; the model only picks foes from the panel's offer and tells
what the dice say.

    budget     the D&D table of a medium encounter per hero (BUDGET by level) times the heroes, half at the children's table
    offer      up to ANGEBOT foes of the bestiary (dungeon_srd.json „gegner“) of the round's world that fit the budget;
               the same turn always offers the same (a seed of round, turn and group), so check and facts agree
    start      the model's begegnung [{id, allein}] from the offer only, ARTEN kinds at most; the panel sets the counts
               (fill) until the adjusted experience (D&D multiplier by count) is BAND times the budget, GEGNER_MAX at most
    attack     the panel makes the attack from the action (Kampf-Audit 1, Dominik 2026-10-26): ANGRIFF_WORTE, a spell
               with a damage kind, BEZUG_WORTE or magic with a foe named; d20 + the value's bonus + proficiency against
               the foe's armour class (ruestung); a hit costs the weapon's die + the value's bonus + its rarity (a spell
               cast this turn: its die by grade); a natural 20 doubles the dice, a natural 1 misses. The target is the
               foe the action names („Riesenratten“, „die Ratten“: the first of them still standing), else the model's
               ziel, else the first one standing; none standing, the attack lapses. A hero whose class casts and whose
               action is magic (MAGIE_WORTE) without a spell of its own attacks with a cantrip: ZAUBER_W[0] + the better
               of the mind's values, kind energie. Advantage only from fixed sources, never the model's
    foes       every foe still up attacks once: the hero who hit it this turn, else one of the standing heroes by the
               seed; d20 + angriff against the hero's armour class (rk), the bestiary's dice + schaden_plus; Eisenhaut
               and Schildwall work on it as on every hit (dungeon.consequences)
    flight     a foe at a quarter of its life or less flees on a d20 of FLUCHT_W or less (never at the children's table:
               there it gives up)
    end        all foes down or fled, or the model's kampf_ende („frieden“, „flucht“): every hero the fight began with
               gets its level's budget times the share won of the encounter against reference (Review 27.10. B9), the
               finds of the occasion „gegner“ by dungeon.funde

Teil 2 (Kampf-Tiefe, Bestiarium-Punkte 4-6 and item point 2, Dominik 2026-10-24 „alles nach empfehlung umsetzten“):
    weapons    eigenschaften of the catalog, each a fixed rule (EIGENSCHAFT_REGEL): finesse and a throw take the better
               of Stärke and Geschick, vielseitig with a free off hand rolls a die two sides bigger, schwer without
               Stärke 13 attacks at a disadvantage, leicht is critical from 19, reichweite keeps the foe it hit at a
               distance (its attack on that hero this turn at a disadvantage)
    kinds      every hit has a damage kind (the weapon's schaden_art, a spell's, a foe's); a foe's resistenz halves it,
               immun stops it, schwaeche doubles it
    states     a foe's hit may cause one of its zustaende: the hero saves with d20 + Konstitution (Weisheit for the mind)
               against the bestiary's sg (Kampf-Audit N6), else RETTUNG + a quarter of the foe's level; failed, the
               state lasts its runden turns and works by its wirkung (ZUSTAND_WIRKUNG); all end with the fight
    saves      a spell with rettung (Kampf-Audit H4): the foe saves with d20 + its value against ZAUBER_SG + the
               caster's attack bonus (spell_save); failed, the damage and the spell's zustand, passed, half with halb;
               a spell without damage with rettung and zustand (bann: Schlaf …) works on a foe that way
    bosses     a foe with boss: more life per hero (BOSS_LEBEN), a second phase at half life (+BOSS_PHASE to hit, once
               a log line), at least two attacks a turn, its find one rarity better (dungeon.give_loot „boss“)
    multiattack a foe with "angriffe" (2 to 5, Tabletop-Punkt 12, from the SRD's Multiattack) attacks that often a turn
               (blows); its schaden is the mean of its damaging attacks, so the turn is as strong as in the SRD

rd["kampf"] = {"gegner": [{k, id, name, zeichen, leben, max, rk, angriff, schaden, plus, wuerfel, ep, aus, art, resistenz,
               immun, schwaeche, zustaende, boss, phase, angriffe}], "seit": zug, "budget": n, "gefahr": "leicht"|"mittel"|"schwer"};
hero states in h["zust"] = [{"id", "bis": zug}]; dungeon.py owns the round and calls in.
"""
import math
import random
import re

import dungeon_album as album
import dungeon_bestiarium as best
import dungeon_ehre as ehre
import dungeon_gefaehrte as gefaehrte
import dungeon_haltung as haltung
import dungeon_umgebung as umgebung
import dungeon_narben as narben

# D&D 5e: experience of a medium encounter per character by its level (1..20)
# the experience of a medium encounter per hero and level: levels 1 to 10 measured with the balance bench (dungeon_pruefstand,
# Dominik 2026-10-24 Idee 5) so a group wins 70 to 90 per cent at „mittel“, measured anew with heroes raised like at the
# table, every class, gear of the find table (Review 27.10. B6, B11) and abilities only when used, only the strongest
# bonus (B7, B13), with the counts set into BAND (B8), and since Review 27.10. Paket 11.6 counting every foe by its
# measured fight experience (wert, dungeon_bestiarium.ep_kampf); beyond the heroes' top level the D&D table
BUDGET = (119, 169, 279, 341, 492, 605, 694, 1093, 1263, 1455, 1600, 2000, 2200, 2500, 2800, 3200, 3900, 4200, 4900, 5700)
REGLER = 25                # the game master's dial (Idee 6): the next encounters at most this many per cent easier or harder
REGLER_HOCH = 10           # after a fight won with less than REGLER_LEICHT of the group's life lost: this much harder
REGLER_LEICHT = 0.25
REGLER_RUNTER = 15         # after a fight with a hero down, lost or fled from: this much easier
# the budget times this for 1 to 5 heroes (more heroes hit more often), 0.33 more for each further one; measured with
# the balance bench (Review 27.10. B6: every class, alone too, heroes raised like at the table; Paket 11.6 by ep_kampf)
GRUPPE = (0.44, 0.91, 1.36, 1.72, 2.05)
GRUPPE_PLUS = 0.33
MAL = ((11, 3.0), (7, 2.5), (3, 2.0), (2, 1.5), (1, 1.0))   # the multiplier of the experience by the number of foes
GEGNER_MAX = 6             # foes of one encounter
ANZAHL_MAX = 4             # of one kind
ANGEBOT = 5                # foes the panel offers the model
SCHWER = 1.5               # the adjusted experience at most this many times the budget
# Review 27.10. B8 (Dominik 2026-10-27 „ok“): the model picks at most ARTEN kinds, the panel sets how many come until
# the adjusted experience is BAND times the budget; a foe the scene wants alone (allein) comes once for ALLEIN of the reward
ARTEN = 2
BAND = (0.9, 1.1)
ALLEIN = 0.5
KIND = 0.5                 # the children's table: half the budget
FLUCHT = 4                 # a foe at a quarter of its life or less …
FLUCHT_W = 9               # … flees on a d20 of this or less
GEFAHR = ((0.75, "leicht"), (1.25, "mittel"), (99.0, "schwer"))
# Budget-Stufen (Tabletop-Punkt 13 of 2026-10-25): the host chooses how hard the encounters are; the SRD 5.2.1 table
# (the catalog's "budget": experience per hero for levels 1 to 10, leicht, mittel, schwer) gives the ratio to „mittel“,
# the measured BUDGET above stays the medium
STUFEN = {"leicht": ("Leicht", "Easy"), "mittel": ("Mittel", "Medium"), "schwer": ("Schwer", "Hard"), "toedlich": ("Tödlich", "Deadly")}
TOEDLICH = 1.5             # deadly: the hard budget times this (the SRD 5.2.1 table has no deadly)
STUFE_OHNE = {"leicht": 0.67, "schwer": 1.4}   # the ratios when the catalog has no table
FAUST = 2                  # an attack without a weapon: 1W2 + Stärke
ZAUBER_W = (6, 8, 8, 10, 10, 12)   # the die of an attack spell by its grade 0..5
ENDE = ("frieden", "flucht")       # the model may end a fight without a winner
AUS = ("besiegt", "geflohen")
ZIEL_MAX = 40
# Kampf-Audit 1 (Dominik 2026-10-26 „Empfehlung umsetzen“): the panel makes the attack from the action, never from the
# model's check. ANGRIFF_WORTE attack on their own (with no foe named: the first one standing), BEZUG_WORTE only with a
# foe named in the action; a stem may carry a prefix (er-, be-, zu-, nieder-, ab-, ver-), NICHT_ANGRIFF is taken out
# first („greife nach dem Seil“, „treffe mich mit“, „stoße die Tür auf“, „betrete“). New words only with
# test_kampf_angriffswoerter_tabelle.
_VOR = r"(?<!\w)(?:er|be|zu|nieder|ab|ver|drauf|los)?"
ANGRIFF_WORTE = re.compile(r"(?i)" + _VOR + r"(?:greif\w*\s+(?:[\w'-]+\s+){0,4}an(?!\w)|verpass\w*\s+(?:[\w'-]+\s+){0,4}eins(?!\w)|angriff|angreif|attackier|attack|schlag|schläg|schlug|"
                           r"stech|stich|stach|stoß|stoss|schieß|schiess|schoss|schuss|tö?te[nt]?(?!\w)|toete|tötet|erschlag|besieg|"
                           r"zerschmetter|erdolch|kämpf|kaempf|hau(?:e|t|en)?(?!\w)|hieb|prügel|prügl|pruegel|pruegl|dresch|"
                           r"schlitz|ramm|tret|tritt|spieß|spiess|kill|hits?(?!\w)|strike|shoot|stab|slash|smite|blast|fight|battle|"
                           r"punch|kick|swing|bash|cleave)")
BEZUG_WORTE = re.compile(r"(?i)" + _VOR + r"(?:triff|treff|traf|ziel|wirf|werf|wurf|schleuder|feuer|stürm|stuerm|schneid|box|"
                         r"(?:gehe?|geht|renne?|rennt|springe?|springt)\s+(?:[\w'-]+\s+){0,8}los|stürz\w*\s+(?:[\w'-]+\s+){0,8}auf(?!\w)|"
                         r"stuerz\w*\s+(?:[\w'-]+\s+){0,8}auf(?!\w)|lass\w*\s+(?:[\w'-]+\s+){0,8}fliegen|pack|greif\w*\s+[^.!?;]*?(?<!\w)an(?!\w)|aim|throw|hurl|toss|fire|charge|cut|shove)")
NICHT_ANGRIFF = re.compile(r"(?i)greif\w*\s+nach(?!\w)|treff\w*\s+(?:mich|uns|dich|euch|sich)(?!\w)|(?:stoß|stoss)\w*\s+(?:die|eine|das)\s+"
                           r"(?:tür|tuer|tor|fenster|kiste|truhe)|betret|(?<!\w)(?:tür|tuer)\w*\s+auf|(?:greif|attack)\w*\s+(?:ab|aus)(?!\w)|"
                           r"lagerfeuer|feuer\s+(?:machen|entzünd|an)|reach\s+for|meet\s+with|"
                           # Nachprüfung Welle 1 (2026-10-26): stepping, proposing, fleeing, a look, a light are no attack;
                           # Nachprüfung V01.1.130: each ends at a word, so a foe's name („Nachtmahr“, „Sicherheitsdroide“) stays whole
                           r"(?:tret|tritt|trat)\w*\s+(?:den\s+(?:rückzug|rueckzug)|zur\s+seite|zurück|zurueck|beiseite|ein(?=\s*(?:[.,;:!?]|$|und(?!\w)))|vor(?!\w)|"
                           r"näher|naeher|(?:die|eine|das)\s+(?:tür|tuer|tor|fenster|kiste|truhe)\w*\s+ein(?!\w))|"
                           r"(?:schlag|schläg|schlug)\w*\s+(?:vor(?!\w)|(?:mich|uns|dich|euch|sich)(?!\w)(?!\s+nieder)|alarm)|hau\w*\s+ab(?!\w)|"
                           r"(?:werf|wirf|warf)\w*\s+(?:[\w-]+\s+){0,4}blick|(?:gebe?|gib|reich)\w*\s+(?:[\w-]+\s+){0,4}feuer(?!\s*(?:auf|!|$))|"
                           r"(?:werf|wirf|warf)\w*\s+(?:[\w-]+\s+){1,5}zu(?!\w)(?!\s+(?:dem|der|den|boden)(?!\w))|"
                           r"step\s+(?:back|aside|in|forward)|retreat|fall\s+back|(?:throw|cast)\w*\s+(?:[\w-]+\s+){0,3}(?:glance|look)|"
                           r"suggest|propose|hits?\s+the\s+road|strik\w*\s+(?:a\s+)?(?:deal|bargain|match|light)")
FRIEDEN_WORTE = re.compile(r"(?i)ergebt|ergib|aufgeben|gebt\s+auf|kapitulier|verhandel|verhandl|frieden|waffenstillstand|lasst\s+uns\s+reden|"
                           r"überred|ueberred|ruhig\s+bleiben|surrender|give\s+up|parley|negotiat|truce|peace|stand\s+down")
# Kampf-Audit 5: spells that work on foes but have no damage kind; those with a saving throw and a state work by it
# (bann, Kampf-Audit H4), the others cost no charge in a fight (dungeon.cast_powers) and say so to the seat
KONTROLLE = ("befehl", "farbspray", "furcht", "gegenzauber", "hypnosemuster", "person_beherrschen", "person_festhalten", "schlaf",
             "stinkwolke", "unheil", "verbannung", "verlangsamen", "verstricken", "verwandlung", "verwirrung")
ZAUBER_SG = 10             # Kampf-Audit H4: a spell's save DC is this + proficiency + the caster's value (8 in 5e: a
                           # save has no critical hit and no advantage, with 10 the balance bench keeps its aim)


def bann(c):
    """Kampf-Audit H4: a spell without damage that works on a foe by its saving throw (rettung) with a state (zustand)."""
    return bool(c and c.get("art") == "zauber" and not c.get("schaden_art") and (c.get("rettung") or {}).get("wert") and c.get("zustand"))


FRIEDEN_SG = (12, 10)      # the panel's peace check: Charisma against the higher of 12 and 10 + the strongest foe's level
# Kampf-Audit M6: the group flees only when most heroes who can act say so, then by the panel's Geschick check
FLUCHT_WORTE = re.compile(r"(?i)flieh|flücht|fluecht|(?<!ver)(?<!zu)flucht|(?:rückzug|rueckzug)|(?:renn|lauf|spring)\w*\s+(?:[\w'-]+\s+){0,5}(?:weg|davon|fort)(?!\w)|"
                          r"hau\w*\s+ab(?!\w)|(?:zieh|ziehen)\w*\s+(?:uns|mich|euch)\s+zurück|(?<!\w)flee|run\s+away|retreat|fall\s+back|escape|get\s+away")
FLUCHT_SG = (10, 8)        # the flight check: Geschick against the higher of 10 and 8 + the strongest foe's level


def intent(text):
    """What an action does in a fight by the fixed word lists: "angriff" (attacks on its own), "bezug" (attacks a foe
    it names), "flucht" (runs away, Kampf-Audit M6), "frieden" (asks for peace) or ""."""
    t = NICHT_ANGRIFF.sub(" ", str(text or ""))
    return ("angriff" if ANGRIFF_WORTE.search(t) else "bezug" if BEZUG_WORTE.search(t) else "flucht" if FLUCHT_WORTE.search(str(text or ""))
            else "frieden" if FRIEDEN_WORTE.search(t) else "")


# Review 27.10. Paket 2 (E1): an action that names a foe standing is an attack, unless it heals, protects, talks,
# looks, hides, gives or waits (these words), flees or asks for peace
SANFT_WORTE = re.compile(r"(?i)(?<!\w)(?:heil|versorg|verbind|schütz|schuetz|beschütz|beschuetz|deck|abschirm|rede|red|sprech|sprich|sag|"
                         r"frag|ruf|antwort|überred|ueberred|droh|beobacht|schau|seh|sieh|beäug|lausch|versteck|duck|gib|geb|reich|zeig|"
                         r"wart|bleib|halt\w*\s+(?:mich|uns)|heal|protect|guard|shield|cover|talk|speak|say|ask|call|threaten|watch|look|"
                         r"observe|hide|give|hand|show|wait|stay)\w*")
MAGIE_WORTE = re.compile(r"(?i)zauber|magie|magisch|spell|magic|(?<!\w)cast")   # an action that casts
ZAUBERWERTE = ("intelligenz", "weisheit", "charisma")   # a cantrip's value: the better of these
_FUELL = {"der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem", "einer", "beide", "beiden", "alle", "allen",
          "the", "a", "an", "all", "both", "and", "und", "auf", "mit", "on", "at", "with"}
EIGENSCHAFTEN = ("leicht", "finesse", "reichweite", "wurf", "schwer", "vielseitig")
SCHADEN_ARTEN = ("hieb", "stich", "wucht", "feuer", "kaelte", "blitz", "saeure", "gift", "nekrotisch", "strahlend", "psychisch",
                 "donner", "energie")
ART_NAME = {"hieb": ("Hieb", "slashing"), "stich": ("Stich", "piercing"), "wucht": ("Wucht", "bludgeoning"), "feuer": ("Feuer", "fire"),
            "kaelte": ("Kälte", "cold"), "blitz": ("Blitz", "lightning"), "saeure": ("Säure", "acid"), "gift": ("Gift", "poison"),
            "nekrotisch": ("nekrotisch", "necrotic"), "strahlend": ("strahlend", "radiant"), "psychisch": ("psychisch", "psychic"),
            "donner": ("Donner", "thunder"), "energie": ("Energie", "force")}
ART_ZEICHEN = {"hieb": "🗡️", "stich": "🏹", "wucht": "🔨", "feuer": "🔥", "kaelte": "❄️", "blitz": "⚡", "saeure": "🧪", "gift": "🐍",
               "nekrotisch": "🌑", "strahlend": "☀️", "psychisch": "🧠", "donner": "💥", "energie": "✨"}   # the bestiary's symbols
EIGENSCHAFT_REGEL = {                       # what each property does at the table, as the item's line says it
    "leicht": ("leicht: kritisch schon ab 19", "light: critical from 19"),
    "finesse": ("Finesse: trifft mit Stärke oder Geschick, dem besseren", "finesse: hits with Strength or Dexterity, the better"),
    "reichweite": ("Reichweite: wen du triffst, greift dich mit Nachteil an", "reach: whoever you hit attacks you at a disadvantage"),
    "wurf": ("Wurf: geworfen mit dem besseren von Stärke und Geschick", "thrown: thrown with the better of Strength and Dexterity"),
    "schwer": ("schwer: unter Stärke 13 mit Nachteil", "heavy: at a disadvantage below Strength 13"),
    "vielseitig": ("vielseitig: mit freier zweiter Hand ein größerer Würfel", "versatile: a bigger die with the off hand free")}
KOERPER = ("hieb", "stich", "wucht")
KENNT_MAX = 300            # foes whose weak spots a round remembers   # the weapons' kinds; a resistance against them does not hold against magic
SCHWER_STAERKE = 13        # a heavy weapon wants this Stärke, else its attack is at a disadvantage
LEICHT_KRIT = 19           # a light weapon is critical from this natural roll
WURF_WORTE = ("wirf", "werf", "wurf", "schleuder", "throw", "hurl", "toss")   # an action that throws (eigenschaft wurf)
RETTUNG = 10               # a state's save: this + a quarter of the foe's level
GEIST = ("bezaubert", "veraengstigt")   # states of the mind: saved with Weisheit, the rest with Konstitution
BRENNT = 4                 # schaden_pro_zug: 1W4 at each of the foes' turns
KRIT = "dungeonkrit"       # the switch „Krit- und Patzer-Tabellen“ (D&D idea 2, features.py) for the round's host
BOSS_LEBEN = 0.5           # a boss: its life times 1 + this per hero beyond the first
ANTEIL_MIN = 0.4           # the budget times the group's share of its life, at least this (Review 27.10. B5)
BOSS_PHASE = 2             # a boss at half life: this much more to hit, once

SCHEMA_BEGEGNUNG = {"type": "array", "maxItems": ARTEN, "items": {"type": "object", "additionalProperties": False, "required": ["id"],
                    "properties": {"id": {"type": "string", "maxLength": 40}, "allein": {"type": "boolean"}}}}
SCHEMA_ENDE = {"type": "string", "enum": ["", *ENDE]}

AUFGABE_ANGEBOT = {
    "de": "Liegt ein Kampf in der Luft (ein Hinterhalt, Wachen, ein Ungeheuer), wähle in begegnung höchstens zwei Arten "
          "von Gegnern mit id nur aus der Liste angebot der Fakten und erzähle, wie sie auftauchen, jede mit ihrem Namen "
          "aus angebot, ohne Zahl; nenne keine anderen Gegner. Das Panel bestimmt, wie viele kommen und wie stark sie sind. "
          "Nur wenn die Szene einen einzelnen Gegner verlangt (ein Duell, ein einsamer Wächter), setze bei ihm allein: true.",
    "en": "When a fight is in the air (an ambush, guards, a monster), choose at most two kinds of foes in begegnung with "
          "id only from the list angebot of the facts and tell how they appear, each by its name from angebot, without a "
          "number; name no other foes. The panel decides how many come and how strong they are. Only when the scene "
          "wants a single foe (a duel, a lone guard), set allein: true for it."}
AUFGABE_KAMPF = {
    "de": "Es wird gekämpft (Fakten kampf). Das Panel würfelt jeden Angriff: Greift eine Figur in ihrer Aktion einen "
          "Gegner an, gib ihr eine Probe mit ziel = dem Namen des Gegners genau wie in kampf und dem Wert, mit dem sie "
          "angreift; schwer zählt dabei nicht. Erzähle genau, was die Würfe in proben und gegner_zuege sagen: wer "
          "trifft, wer verfehlt, wer fällt oder flieht. Melde für den Kampf keinen Schaden in folgen und lass keinen "
          "Gegner ohne Wurf fallen. wirkt sagt, ob der Gegner den Schaden halbiert (resistenz), gar nicht nimmt (immun) "
          "oder doppelt (schwaeche); zustand mit gerettet false heißt, die Figur leidet jetzt daran (erzähle es), "
          "kann_nicht, dass sie wegen eines Zustands nicht angreifen konnte. Ein Gegner mit boss und phase 2 wird "
          "jetzt gefährlicher. Ob die Gruppe entkommt, entscheidet das Panel (Probe „Fliehen“ in proben); Frieden gibt es nur, wenn die Probe „Frieden anbieten“ "
          "in proben geschafft ist. Melde im Kampf keine heilung in folgen: geheilt wird nur durch Zauber und Tränke des Panels.",
    "en": "There is a fight (facts kampf). The panel rolls every attack: when a character attacks a foe in its action, "
          "give it a check with ziel = the foe's name exactly as in kampf and the value it attacks with; schwer does "
          "not count then. Tell exactly what the rolls in proben and gegner_zuege say: who hits, who misses, who falls "
          "or flees. Report no damage of the fight in folgen and let no foe fall without a roll. wirkt says whether the "
          "foe halves the damage (resistenz), takes none (immun) or double (schwaeche); zustand with gerettet false means "
          "the character now suffers it (tell it), kann_nicht that a state kept it from attacking. A foe with boss "
          "and phase 2 grows more dangerous now. Whether the group gets away the panel decides (the check \"flee\" in proben); there is peace only when the check "
          "\"offer peace\" in proben is passed. Report no heilung in folgen during a fight: only the panel's spells and "
          "potions heal."}


def prof(stufe):
    """The proficiency bonus of D&D by level."""
    return 2 + (max(1, int(stufe)) - 1) // 4


WIRKUNG = ("schaden", "lebensraub", "glueck", "wachsam")   # what an item's effect does by a fixed rule (Gegenstands-Punkt 3)
WIRKUNG_W = 6             # „schaden“: +1d6 of its kind on a hit (twice on a critical)
RAUB_W = 4                # „lebensraub“: the hero heals 1d4 on a hit
OEL_TREFFER = 3           # „oel“ (Wirtschaft Punkt 9): a coated weapon hits with its kind +1d6 for this many hits


def effects(dm, r, h, wirkung, it=None):
    """The known effects with this wirkung the hero wears (or of the one item it); an unknown item counts only by its base."""
    its = [it] if it else dm.worn(h)
    return [e for x in its for e in dm.item_effects(r, x) if e.get("wirkung") == wirkung]


def lucky(dm, r, h, w, rng):
    """„glueck“: a natural 1 is rolled again once. Returns (the roll, rolled again)."""
    if w == 1 and effects(dm, r, h, "glueck"):
        return rng.randint(1, 20), True
    return w, False


def rk(dm, r, h):
    """A hero's armour class (Gegenstands-Punkt 9): 10 + twice the body armour + the other pieces (shield, helmet,
    gauntlets, boots, each with its rarity) + the Geschick bonus, at most 2 in medium (body 2) and none in heavy armour
    (body 3 and more)."""
    body, rest = 0, 0
    for k, it in (h.get("an") or {}).items():
        if not it or dm._c(r, it)["art"] != "ruestung":
            continue
        n = dm._c(r, it).get("schutz", 0) + (0 if it.get("u") else it.get("bonus", 0))
        if k == "koerper":
            body = n
        else:
            rest += n
    g = dm.body(r, h, "geschick") - dm.blessing(h, "geschick")   # Kampf-Audit M5: worn items count, a wound too
    base = dm._c(r, h["an"]["koerper"]).get("schutz", 0) if (h.get("an") or {}).get("koerper") else 0
    g = g if base < 2 else min(g, 2) if base < 3 else min(g, 0)
    # a blessing on Geschick (Schild, Hast, a cat's potion) is magic: it counts past the armour's cap
    return 10 + 2 * body + rest + g + dm.blessing(h, "geschick") + len(effects(dm, r, h, "wachsam")) + dm.runen.armour(dm, r, h)


def _mal(n):
    return next(m for k, m in MAL if n >= k)


def group_factor(n):
    """GRUPPE for n heroes (companions as their share): between two sizes on the line, beyond the table GRUPPE_PLUS more
    for each further hero."""
    n = max(1.0, n)
    if n >= len(GRUPPE):
        return GRUPPE[-1] + GRUPPE_PLUS * (n - len(GRUPPE))
    k = int(n)
    return GRUPPE[k - 1] + (GRUPPE[k] - GRUPPE[k - 1]) * (n - k)


def budget(dm, r, rd, held, stufe=True):
    """The experience an encounter of this group may have: BUDGET per hero, times GRUPPE for the group's size, half at
    the children's table, the dial, and the host's stage (stage_factor; stufe=False: the medium), times the group's
    share of its life (at least ANTEIL_MIN). Every companion up counts as gefaehrte.ANTEIL of a hero (round 2, idea 9)."""
    mehr = gefaehrte.share(rd)
    voll = sum(max(1, h.get("leben_max") or 1) for h in held)    # Review 27.10. B5: a battered group gets less, at least ANTEIL_MIN
    anteil = max(ANTEIL_MIN, min(1, sum(max(0, h.get("leben", h.get("leben_max") or 1)) for h in held) / voll)) if held else 1
    b = anteil * sum(BUDGET[min(len(BUDGET), max(1, h["stufe"])) - 1] for h in held) * (1 + mehr / max(1, len(held))) \
        * group_factor(len(held) + mehr)
    return int(b * (KIND if dm.kids(r, rd) else 1) * (1 + dial(rd) / 100) * (stage_factor(r, rd, held) if stufe else 1))


def reference(dm, r, rd, held):
    """The budget a reward is measured against (Review 27.10. B9): BUDGET per hero times GRUPPE for the group with its
    companions, without the life share, the dial, the host's stage and the children's table, so a harder fight gives
    more and a hero's reward does not hang on how many stand with it."""
    mehr = gefaehrte.share(rd)
    return max(1, int(sum(BUDGET[min(len(BUDGET), max(1, h["stufe"])) - 1] for h in held) * (1 + mehr / max(1, len(held)))
                      * group_factor(len(held) + mehr)))


def reward(k, stufe, anteil=1):
    """A hero's experience from the fight k (Review 27.10. B9): its level's BUDGET times the encounter's adjusted
    experience (k["wert"]) against the reference budget (k["bezug"]), times the share won; rounded down."""
    return int(BUDGET[min(len(BUDGET), max(1, stufe)) - 1] * k["wert"] * anteil / max(1, k["bezug"]))


def stages_on(rd):
    """The host may choose the stage: „Kampfstufen“ allowed for the round's host."""
    import features
    return bool(rd.get("owner")) and features.allowed("dungeonstufen", rd["owner"])


def stage(rd):
    s = rd.get("kampfstufe")
    return s if s in STUFEN and stages_on(rd) else "mittel"


def stage_factor(r, rd, held):
    """The stage against the medium: the mean over the heroes of the SRD 5.2.1 budget of their level (1 to 10), deadly
    the hard one times TOEDLICH; 1 for the medium."""
    s = stage(rd)
    if s == "mittel":
        return 1.0
    key = "schwer" if s == "toedlich" else s
    t = r.get("budget") or {}
    fs = [t[key][min(10, max(1, h["stufe"])) - 1] / t["mittel"][min(10, max(1, h["stufe"])) - 1] for h in held] if t else []
    f = sum(fs) / len(fs) if fs else STUFE_OHNE[key]
    return f * (TOEDLICH if s == "toedlich" else 1)


def check_rules(r):
    """The catalog's budget table by fixed rules (dungeon.check_rules adds the sentences)."""
    t = r.get("budget")
    if t is None:
        return []
    ok = isinstance(t, dict) and set(t) == {"leicht", "mittel", "schwer"} and all(
        isinstance(v, list) and len(v) == 10 and all(isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in v) for v in t.values())
    ok = ok and all(a < b < c for a, b, c in zip(t["leicht"], t["mittel"], t["schwer"]))
    return [] if ok else ["budget: leicht, mittel und schwer mit je 10 Zahlen (Stufe 1 bis 10), leicht < mittel < schwer"]


def dial_on(rd):
    """The game master's dial works for this round: „Spielleiter-Regler“ allowed for its host."""
    import features
    return bool(rd.get("owner")) and features.allowed("dungeonregler", rd["owner"])


def dial(rd):
    """The dial's per cent (-REGLER..REGLER) for the next encounter, 0 while it is off."""
    return max(-REGLER, min(REGLER, int(rd.get("regler", 0)))) if dial_on(rd) else 0


def turn_dial(dm, r, rd):
    """After a fight, once its last hits are in the heroes' life (dungeon.apply after consequences), by fixed numbers: won with little life lost → REGLER_HOCH harder, a hero down, a lost fight or
    a flight → REGLER_RUNTER easier, else as it was; at most ±REGLER, at the children's table never above 0. The
    host can hold it (rd["regler_fest"]). Returns the step (+, - or 0)."""
    k = rd.pop("kampf_aus", None)
    if not k or not dial_on(rd):
        return 0
    held, why = [p["held"] for _, p in dm.seated(rd)], k["why"]
    if rd.get("regler_fest"):
        print("dungeon: regler | fest", flush=True)
        return 0
    voll = k.get("leben0") or 0
    lost = 1 - sum(max(0, h["leben"]) for h in held) / voll if voll else 0
    down = any(dm.zustand(h) for h in held)
    step = -REGLER_RUNTER if down or why == "flucht" else REGLER_HOCH if lost < REGLER_LEICHT else 0
    top = 0 if dm.kids(r, rd) else REGLER
    was = int(rd.get("regler", 0))
    rd["regler"] = max(-REGLER, min(top, was + step))
    step = rd["regler"] - was
    if step > 0:
        dm._day.bump("regler_hoch")
        print(f"dungeon: regler | hoch | {rd['regler']}", flush=True)
    elif step < 0:
        dm._day.bump("regler_runter")
        print(f"dungeon: regler | runter | {rd['regler']}", flush=True)
    else:
        print(f"dungeon: regler | gleich | {rd['regler']}", flush=True)
    return step


def plays_in(r, g, welt):
    """Whether a foe of the bestiary meets heroes in the world: „alle“ everywhere, else its worlds; a world no foe names
    for itself (the own world, a new one of the admin) takes the foes of dungeon_legenden.SONST (Bestiarium-Punkt 3)."""
    from dungeon_legenden import SONST
    w = welt if any(welt in x["welten"] for x in r.get("gegner") or []) else SONST
    return "alle" in g["welten"] or w in g["welten"]


def _foes(dm, r, rd):
    """The foes of the round's world; a peaceful one (dungeon_bestiarium.friedlich, Review 27.10. Paket 11) never."""
    welt = rd.get("welt", "")
    return [g for g in r.get("gegner") or [] if plays_in(r, g, welt) and not best.friedlich(g)]


def _seed(rd, held, *more):
    return random.Random("|".join(map(str, (rd.get("zug", 0), rd.get("welt", ""), len(held), sum(h["stufe"] for h in held), *more))))


def room(r, rd):
    """The foes a room of the map demands (dungeon_karte puts {"raum": its tag, "ids": [bestiary ids]} into
    rd["raum_gegner"] for a guardian or boss room): their catalog entries, [] without one."""
    rg = rd.get("raum_gegner") or {}
    by = {g["id"]: g for g in r.get("gegner") or []}
    return [by[i] for i in rg.get("ids") or [] if i in by][:ANGEBOT]


def offer(dm, r, rd, held):
    """The foes the model may choose from this turn: of the round's world, one of them alone within the budget, the
    nearest to a third of it first, ANGEBOT drawn from the best twelve by the turn's seed; in a room of the map only
    its foes (room). [] in a fight."""
    if rd.get("kampf") or not held:
        return []
    if room(r, rd):
        return room(r, rd)
    b = budget(dm, r, rd, held)
    import dungeon_tageszeit                     # LlamaTale idea 1: at night the foes of the night table
    fit = dungeon_tageszeit.night_foes(rd, [g for g in _foes(dm, r, rd) if 0 < g["ep"] and best.ep_kampf(g) <= b * SCHWER], ANGEBOT)
    fit.sort(key=lambda g: (abs(best.ep_kampf(g) - b / 3), g["id"]))
    top = fit[:12]
    import dungeon_personen                      # people of the scene with a template by occupation (Personen-Katalog 4)
    return sorted(_seed(rd, held).sample(top, min(ANGEBOT, len(top))), key=best.ep_kampf) + dungeon_personen.fighters(dm, r, rd, held, b)


def offer_facts(dm, r, rd, held, li):
    return [{"id": g.get("oid", g["id"]), "name": g["name"][li], "stufe": g["stufe"], "groesse": g.get("groesse", "mittel"),
             **({"person": True} if g.get("person") else {})} for g in offer(dm, r, rd, held)]


def faktor(g, n_held):
    """A boss's life grows by BOSS_LEBEN per hero beyond the first (lineup); every other foe 1."""
    return 1 + BOSS_LEBEN * max(0, n_held - 1) if g.get("boss") else 1


def wert(g, n_held):
    """A foe's experience as the budget and the reward count it (Review 27.10. Paket 4a): its measured fight experience
    (Paket 11.6, dungeon_bestiarium.ep_kampf, else its ep), a boss with its life factor (faktor). Also for the map's
    rooms (dungeon_karte._room_foes)."""
    return int(best.ep_kampf(g) * faktor(g, n_held))


def adjusted(foes, n_held=1):
    return int(sum(wert(g, n_held) for g in foes) * _mal(len(foes)))


def check_encounter(dm, r, rd, held, obj):
    """The model's begegnung by fixed rules: only offered ids, one entry per id, ARTEN kinds at most, the counts by
    fill (Review 27.10. B8; a person comes with its escort, dungeon_personen.escort, B14); one kind with allein: true
    comes once and alone (a copy marked "allein", half the reward in end); in a room of the map each of its foes as
    the map wants it. Returns [(catalog entry, count)] or []."""
    if not isinstance(obj, list) or rd.get("kampf"):
        return []
    have = {g.get("oid", g["id"]): g for g in offer(dm, r, rd, held)}
    out, seen = [], set()
    for x in obj[:ARTEN]:
        if not isinstance(x, dict) or x.get("id") not in have or x["id"] in seen:
            continue
        if have[x["id"]].get("boss") and any(g.get("boss") for g, _ in out):
            continue                             # Review 27.10. Paket 4a: at most one boss an encounter
        seen.add(x["id"])
        out.append([have[x["id"]], 1])
    if room(r, rd):                              # a room's guardian or boss as the map wants it, its count by "anzahl" (Paket 4 B1)
        anz, out_ = (rd.get("raum_gegner") or {}).get("anzahl") or {}, []
        for g, _ in out:
            n = anz.get(g["id"]) if isinstance(anz.get(g["id"]), int) and not isinstance(anz.get(g["id"]), bool) else 1
            n = 1 if g.get("boss") or g.get("person") else max(1, min(ANZAHL_MAX, n, GEGNER_MAX - sum(m for _, m in out_)))
            if sum(m for _, m in out_) < GEGNER_MAX:
                out_.append((g, n))
        return out_
    allein = [x for x in obj[:ARTEN] if isinstance(x, dict) and x.get("allein") is True]
    if len(out) == 1 and allein and allein[0].get("id") == out[0][0].get("oid", out[0][0]["id"]):
        print("dungeon: begegnung | allein", flush=True)
        return [(dict(out[0][0], allein=True), 1)]
    import dungeon_personen
    for g, _ in list(out):
        w = dungeon_personen.escort(dm, r, rd, g) if g.get("person") and len(out) < ARTEN + 1 else None
        if w and all(x["id"] != w["id"] for x, _ in out):
            out.append([w, 1])                   # B14: the person's guards from its row, counted by fill
    return fill(out, len(held), budget(dm, r, rd, held))


def fill(wahl, n_held, b):
    """The counts by fixed rules (Review 27.10. B8): every kind once (a boss and a person always once); then one more
    of the kind that brings the adjusted experience nearest to b while it stays at most BAND[1] times b, GEGNER_MAX
    foes and ANZAHL_MAX of a kind, until it is BAND[0] times b; then, still above BAND[1] times b, the strongest taken
    away, a boss or a person last (one foe always stays). The model's numbers never count. [(entry, count)]."""
    out = [[g, n] for g, n in wahl]
    flat = lambda: [g for g, n in out for _ in range(n)]    # noqa: E731
    while out and adjusted(flat(), n_held) < BAND[0] * b:
        f = flat()
        neu = [(abs(adjusted(f + [g], n_held) - b), i) for i, (g, n) in enumerate(out)
               if not (g.get("boss") or g.get("person")) and n < ANZAHL_MAX and len(f) < GEGNER_MAX
               and adjusted(f + [g], n_held) <= BAND[1] * b]
        if not neu:
            break
        out[min(neu)[1]][1] += 1
    while out and len(flat()) > 1 and adjusted(flat(), n_held) > BAND[1] * b:
        i = max(range(len(out)), key=lambda j: (not (out[j][0].get("boss") or out[j][0].get("person")), wert(out[j][0], n_held), out[j][1]))
        out[i][1] -= 1
        if not out[i][1]:
            out.pop(i)
    return [(g, n) for g, n in out]


def lineup(wahl, li, n_held):
    """The foes of an encounter with their bestiary values, numbered when several of a kind come; a boss has more life
    the more heroes stand against it (start, and the balance bench dungeon_pruefstand)."""
    gegner = []
    for g, n in wahl:
        for j in range(n):
            gegner.append({"k": f"g{len(gegner) + 1}", "id": g["id"], "name": g["name"][li] + (f" {j + 1}" if n > 1 else ""),
                           "zeichen": g.get("zeichen", ""), "leben": g["leben"], "max": g["leben"], "rk": g["ruestung"],
                           "angriff": g["angriff"], "schaden": g["schaden"], "plus": g.get("schaden_plus", 0),
                           "wuerfel": g.get("anzahl_wuerfel", 1), "ep": g["ep"], "aus": "", "art": g.get("schaden_art", ""),
                           **{x: list(g.get(x) or []) for x in ("resistenz", "immun", "schwaeche", "zustaende")},
                           "boss": bool(g.get("boss")), "phase": 1, "angriffe": g.get("angriffe", 1), "ep_kampf": best.ep_kampf(g),
                           **({"person": g["person"]} if g.get("person") else {})})
            if g.get("boss"):
                gegner[-1]["leben"] = gegner[-1]["max"] = int(g["leben"] * faktor(g, n_held))
    return gegner


def danger(adj, b):
    """The danger word of an encounter: its adjusted experience against the medium budget (GEFAHR)."""
    return next(n for m, n in GEFAHR if adj / max(1, b) <= m)


def start(dm, r, rd, held, wahl, li):
    """An encounter into the round: the foes with their bestiary values, numbered when several of a kind come."""
    if not wahl:
        return None
    gegner = lineup(wahl, li, len(held))
    b = budget(dm, r, rd, held)
    rd["kampf"] = {"gegner": gegner, "seit": rd.get("zug", 0), "budget": b, "gefahr": danger(adjusted(gegner, len(held)), budget(dm, r, rd, held, False)),
                   "bezug": reference(dm, r, rd, held), "wert": adjusted(gegner, len(held)),
                   "leben0": sum(max(0, h["leben"]) for h in held),
                   "helden": [pid for pid, p in dm.seated(rd) if not p["held"].get("tot")],   # the group the fight was made for
                   **({"allein": True} if any(g.get("allein") for g, _ in wahl) else {})}
    if room(r, rd) and {g["id"] for g, _ in wahl} <= set(rd["raum_gegner"]["ids"]):
        rd["kampf"]["raum"] = rd["raum_gegner"]["raum"]
    dm._log(rd, "begegnung", gegner=[dict(card(dm, r, rd, g["id"], "en" if li else "de"), anzahl=n,
                                          **({"name": g["name"][li], "person": True} if g.get("person") else {})) for g, n in wahl],
            gefahr=rd["kampf"]["gefahr"])
    dm._day.bump("begegnungen")
    print(f"dungeon: kampf | start | {len(gegner)} gegner | {rd['kampf']['gefahr']}", flush=True)
    return rd["kampf"]


def up(rd):
    return [g for g in (rd.get("kampf") or {}).get("gegner") or [] if not g["aus"]]


def _stems(word):
    yield word
    for suf in ("en", "n", "es", "s", "e"):
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            yield word[:-len(suf)]


def _kind_of(g, text):
    """The text names the foe's kind (its name without the number, as a plural or its last part): „Riesenratten“,
    „die Ratten“, „giant rats“."""
    last = re.sub(r"\s+\d+$", "", g["name"].lower()).split()[-1:] or [""]
    teile = {x for x in re.split(r"[-\s]+", re.sub(r"\s+\d+$", "", g["name"].lower())) if len(x) >= 3}   # Review Paket 2: „Ork“ is the Ork-Krieger
    for w in re.findall(r"\w+", text):
        if w in _FUELL:
            continue
        for s in _stems(w):
            if s == last[0] or len(s) >= 4 and last[0].endswith(s) or s in teile:
                return True
    return False


def _named(rd, ziel, life=None, text=False):
    """The foe a ziel (or with text=True an attacking action) names, still standing (life: the life left this turn):
    its whole name, then its kind (the end of its name: „Ratte“ is the Riesenratte, never the Rattenschwarm), then the
    start of it (Kampf-Audit N2); among several of the same kind the one with the least life left, else the first."""
    z = str(ziel or "").strip().lower()
    z = z if text else z[:ZIEL_MAX]
    if not z:
        return None
    gs = [g for g in up(rd) if life is None or life.get(g["k"], 0) > 0]
    whole = (lambda n: re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", z)) if text else (lambda n: n == z)
    left = (lambda g: life.get(g["k"], 0)) if life is not None else (lambda g: g.get("leben", 0))
    for fits in (lambda g: whole(g["name"].lower()), lambda g: _kind_of(g, z), lambda g: not text and g["name"].lower().startswith(z)):
        xs = [g for g in gs if fits(g)]
        if xs:
            return min(xs, key=left)
    return None


def _weapon(dm, r, h):
    it = (h.get("an") or {}).get("haupthand")
    return it if it and dm._c(r, it)["art"] == "waffe" else None


def _dice(rng, n, w):
    return sum(rng.randint(1, w) for _ in range(n))


def attackers(dm, r, rd, proben, skip=()):
    """[(check, foe or None, by the model)]: the heroes whose action attacks this fight turn by the fixed rules, in the
    order of the seats (attacks; dungeon_echt asks the seats with own dice for these attacks before the roll, T14).
    Reads only: no foe's life, no journal."""
    if not rd.get("kampf"):
        return []
    life = {g["k"]: g["leben"] for g in up(rd)}
    cat = dm._by(r, "gegenstaende")
    model = {}
    for p in proben:
        model.setdefault(p["pid"], p)
    out = []
    offen = rd.get("offen") or {}
    for pid in list(offen) + [q for q in model if q not in offen]:
        a = offen.get(pid) or {}
        h = (rd["plaetze"].get(pid) or {}).get("held")
        if pid in skip or not h or dm.zustand(h) or (rd["plaetze"][pid].get("wartet")):   # down or dead: no attack
            continue
        spell = cat.get(a.get("kraft") or "")
        was = intent(a.get("text"))
        named = _named(rd, NICHT_ANGRIFF.sub(" ", str(a.get("text") or "")), life, text=True)
        m = model.get(pid) or {}
        by_model = _named(rd, m.get("ziel"), life) if m.get("ziel") else None
        dmg = bool(spell and spell.get("art") == "zauber" and spell.get("schaden_art")) or bann(spell)   # H4: a spell on a foe too
        magie = not spell and bool(MAGIE_WORTE.search(str(a.get("text") or "")))   # magic at a foe: a cantrip (below)
        sanft = was in ("flucht", "frieden") or bool(spell) or bool(SANFT_WORTE.search(str(a.get("text") or "")) or NICHT_ANGRIFF.search(str(a.get("text") or "")))
        if not (was == "angriff" or dmg or (was == "bezug" or magie) and named or named and not sanft):   # the model's ziel only picks the target
            continue                             # Review 27.10. Paket 2: a foe standing named and no gentle word is an attack
        out.append((dict(m or {"pid": pid, "wert": "staerke", "schwer": 10, "wofuer": ""}, pid=pid), named or by_model, bool(m)))
    return out


def attacks(dm, r, rd, proben, rng=None, hand=None, skip=()):
    """The attacks of a fight turn, made by the panel from the actions (Kampf-Audit 1, Dominik 2026-10-26): a hero whose
    action attacks (intent), or who casts a spell with a damage kind (Kampf-Audit 2), attacks whether the model asked a
    check for it or not; the model's checks for that hero are dropped. The target: the foe the action names, else the
    one the model's ziel names, else the first still standing (a target fallen this turn: the next one); with none
    standing the attack lapses, no check, no experience. The model's ziel alone never makes an attack (Nachprüfung
    Welle 1); a hero casting a spell on foes (KONTROLLE) has no check of the model in a fight either. skip: heroes a prop of the fight already took (dungeon_umgebung). Returns (the other checks, the attack
    results); every number from here: the foe's life is only changed in apply (hit). hand (dungeon_echt.Hand): the
    d20 a seat threw at the real table come first, the attack says "echt"."""
    rng = rng or random
    if not rd.get("kampf"):
        return [{k: v for k, v in p.items() if k != "ziel"} for p in proben], []
    rest, out, life = [], [], {g["k"]: g["leben"] for g in up(rd)}
    li = 1 if rd["lang"] == "en" else 0
    cat = dm._by(r, "gegenstaende")
    los = []                                     # (check, foe) in the order of the seats
    offen = rd.get("offen") or {}
    for p, g, m in attackers(dm, r, rd, proben, skip):
        los.append((p, g))
        print(f"dungeon: kampf | angriff | {'aus aktion' if m else 'modell ohne probe'}", flush=True)
    angreifer = {p["pid"] for p, _ in los}
    for p in proben:
        if p["pid"] in angreifer:
            continue
        if (offen.get(p["pid"]) or {}).get("kraft") in KONTROLLE:   # a spell on foes: no effect yet, so no check and no EP
            print("dungeon: probe | kampf | kontrolle verworfen", flush=True)
            continue
        a = rd["offen"].get(p["pid"]) or {}
        g = next((g for g in (_named(rd, x, life, text=True) for x in (a.get("text"), p.get("wofuer")) if x) if g), None)
        if g:
            print("dungeon: probe | kampf | kein angriff", flush=True)   # a foe named, still a check: shows in the journal
        rest.append(dict({k: v for k, v in p.items() if k != "ziel"}, **({"kein_angriff": g["name"]} if g else {})))
    for p, g in los:
        a = rd["offen"].get(p["pid"]) or {}
        if g and life.get(g["k"], 0) <= 0:
            g = None
        if not g:                                # none named, or it fell this turn: the next one standing
            g = next((x for x in up(rd) if life.get(x["k"], 0) > 0), None)
            print(f"dungeon: kampf | angriff | {'ziel neu' if g else 'verfaellt'}", flush=True)
            if not g:
                continue
        h = rd["plaetze"][p["pid"]]["held"]
        spell = cat.get(a.get("kraft") or "")
        gebannt = spell if bann(spell) else None  # Kampf-Audit H4: Schlaf, Person festhalten … on this foe
        if spell and spell.get("art") == "zauber" and not spell.get("schaden_art"):
            spell = None                          # Schild, Segnen … beside an attack: the attack is the weapon's
        ro = h.get("rolle")
        if not spell and ro and ro.get("bis", -1) >= rd.get("zug", 0) and (cat.get(ro.get("id")) or {}).get("art") == "zauber" \
                and cat[ro["id"]].get("schaden_art"):
            spell = cat[ro["id"]]                 # Kampf-Audit M4: the scroll read makes this attack its spell, once
            h.pop("rolle")
            print("dungeon: kampf | rolle | angriff", flush=True)
        wp = _weapon(dm, r, h)
        eig = ()
        geist = [x for x in ZAUBERWERTE if x in h["werte"]]
        trick = not spell and bool(geist) and bool(MAGIE_WORTE.search(str(a.get("text", "")))) and \
            bool(dm._by(r, "klassen").get(h["klasse"], {}).get("zauber"))
        if spell and spell.get("segen"):
            wert, wuerfel, plus, mit = spell["segen"]["wert"], ZAUBER_W[min(5, spell.get("grad", 0))], spell["segen"]["bonus"], spell["name"][li].split(": ", 1)[-1]
            art = spell.get("schaden_art") or "energie"      # a scroll or ability without its own kind: force
        elif trick:                                           # magic of a caster without a spell named: a cantrip
            wert = max(geist, key=lambda x: (dm.total(r, h, x), x == p.get("wert")))
            wuerfel, plus, mit, art = ZAUBER_W[0], 0, ("Zauber" if not li else "spell"), "energie"
            spell = {"grad": 0}
        elif wp:
            c = dm._c(r, wp)
            wert, wuerfel, plus, mit = c["wert"], c["schaden"], 0 if wp.get("u") else wp.get("bonus", 0), wp.get("eigen") or c["name"][li]
            art, eig = c.get("schaden_art", ""), tuple(c.get("eigenschaften") or ())
        else:
            wert, wuerfel, plus, mit, art = "staerke", FAUST, 0, ("Fäuste" if not li else "fists"), "wucht"
        wirft = "wurf" in eig and any(x in str(a.get("text", "")).lower() for x in WURF_WORTE)
        if "finesse" in eig or wirft:            # the better of Stärke and Geschick
            wert = max(("staerke", "geschick"), key=lambda x: (dm.total(r, h, x), x == wert))
        if "vielseitig" in eig and not (h.get("an") or {}).get("nebenhand"):
            wuerfel += 2                          # both hands on it
        vt = ""                                   # Kampf-Audit: an attack's advantage only from the fixed sources below
        if "schwer" in eig and h["werte"].get("staerke", 10) < SCHWER_STAERKE:
            vt = "" if vt == "vorteil" else "nachteil"
        vt = _state_vt(r, h, vt, "angriff")
        if umgebung.edge(rd):                    # a prop gave the group an opening this turn (round 2, idea 3)
            vt = "" if vt == "nachteil" else "vorteil"
        if haltung.stance(rd, p["pid"]) == "abwehr":   # on guard: the own attack at a disadvantage (round 2, idea 2)
            vt = "" if vt == "vorteil" else "nachteil"
        if foe_has(r, rd, g, "vorteil_gegen"):   # a foe on the ground, blinded … by a critical hit (D&D idea 2)
            vt = "" if vt == "nachteil" else "vorteil"
        if blocked(r, h):                     # a state that takes the turn (gelähmt, betäubt …): no attack
            out.append({"pid": p["pid"], "name": h["name"], "ziel": g["k"], "gegner": g["name"], "mit": mit, "wert": wert, "w": 0,
                        "ws": [], "vt": "", "bonus": 0, "gesamt": 0, "rk": g["rk"], "treffer": False, "krit": False, "schaden": 0,
                        "faellt": False, "kann_nicht": blocked(r, h)})
            continue
        if gebannt or (spell and (spell.get("rettung") or {}).get("wert")):   # Kampf-Audit H4: the foe saves, no attack roll
            c = gebannt or spell
            cw = max(geist, key=lambda x: (dm.body(r, h, x, dinge=False), x == (c.get("segen") or {}).get("wert"))) if gebannt and geist else wert
            out.append(spell_save(dm, r, rd, h, p["pid"], g, c, cw, wuerfel, art, c["name"][li].split(": ", 1)[-1] if gebannt else mit, life, rng))
            continue
        # Kampf-Audit M3: a spell's own bonus does not stack with the blessing already on the value (the higher counts)
        bonus = dm.total(r, h, wert) + prof(h["stufe"]) + (max(0, plus - dm.blessing(h, wert)) if spell else 0) \
            + (dm.runen.hit(dm, r, wp) if wp and not spell else 0)      # a weapon's runes only for its attack (dungeon_runen)
        mut = False
        gl = False
        for _ in range(2):
            ws = [hand.d20(p["pid"], rng) if hand else rng.randint(1, 20) for _ in range(2 if vt else 1)]
            w = max(ws) if vt == "vorteil" else min(ws)
            if not gl:
                w, gl = lucky(dm, r, h, w, rng)
            krit = w >= (LEICHT_KRIT if "leicht" in eig else 20)
            hit = krit or (w != 1 and w + bonus >= g["rk"])
            if krit or mut or not dm.mut.wants(rd, p["pid"]):
                break
            dm.mut.spend(rd, p["pid"])            # Heldenmut (Idee 8): a hit becomes critical, a miss is rolled again once
            mut = True
            if hit:
                krit = True
                break
        n, wirkt, extra, raub = 0, "", [], 0
        if hit:
            n = max(1, _dice(rng, 2 if krit else 1, wuerfel) + dm.body(r, h, wert, dinge=False) + (0 if spell else plus)   # M5: with blessing
                    + (dm.KRAFT["schaden_plus"] * len(dm.kraft(r, h, "schaden_plus")) + dm.runen.damage(dm, r, wp) if wp and not spell else 0))   # Waffenmeister (B7), runes
            n, wirkt = against(g, art, n, magisch=bool(spell) or bool(wp and not wp.get("u") and wp.get("bonus", 0) >= 1))
            for e in effects(dm, r, h, "schaden", wp) if wp and not spell else ():   # a burning blade: its own kind, its own resistances
                m, _ = against(g, e["art"], _dice(rng, 2 if krit else 1, WIRKUNG_W))
                extra.append({"art": e["art"], "schaden": m})
                n += m
            if wp and not spell and (wp.get("oel") or {}).get("n", 0) > 0:     # an oil on the blade: one hit of its kind
                m, _ = against(g, wp["oel"]["art"], _dice(rng, 2 if krit else 1, WIRKUNG_W))
                extra.append({"art": wp["oel"]["art"], "schaden": m, "oel": True})
                n += m
            if wp and not spell and effects(dm, r, h, "lebensraub", wp):
                raub = rng.randint(1, RAUB_W)
            life[g["k"]] -= n
        out.append({"pid": p["pid"], "name": h["name"], "ziel": g["k"], "gegner": g["name"], "mit": mit, "wert": wert, "w": w,
                    "ws": ws, "vt": vt, "bonus": bonus, "gesamt": w + bonus, "rk": g["rk"], "treffer": hit, "krit": krit,
                    "schaden": n, "faellt": hit and life[g["k"]] <= 0, "art": art, "wirkt": wirkt,
                    "eig": [x for x in eig if x != "wurf" or wirft], **({"mut": True} if mut else {}),
                    **({"extra": extra} if extra else {}), **({"raub": raub} if raub else {}), **({"glueck": True} if gl else {}),
                    **({"echt": True} if hand and hand.used(p["pid"]) else {}),
                    **table(dm, r, rd, krit and hit, w == 1 and not krit, art, bool(spell), wirft or wert == "geschick" and "finesse" not in eig, rng)})
    return rest, out


def spell_save(dm, r, rd, h, pid, g, c, wert, wuerfel, art, mit, life, rng):
    """Kampf-Audit H4: a spell with a saving throw on a foe. The panel rolls the foe's d20 + the bonus of its value of
    the bestiary against ZAUBER_SG + the bonus the spell's attack roll would have (proficiency, the caster's value for
    a check, dungeon.total, and the spell's own bonus above the blessing on it, M3). Failed: the damage
    (if the spell has a kind) and the spell's state for the state's turns; passed: half the damage with halb, else
    nothing. A natural 20 always passes, a 1 always fails."""
    by = dm._by(r, "gegner").get(g["id"]) or {}
    rw = c["rettung"]["wert"]
    sg = (c.get("segen") or {}).get("bonus", 0) if (c.get("segen") or {}).get("wert") == wert else 0
    dc = ZAUBER_SG + prof(h["stufe"]) + dm.total(r, h, wert) + max(0, sg - dm.blessing(h, wert))   # 10 + the attack's bonus
    w = rng.randint(1, 20)
    mod = dm.mod((by.get("werte") or {}).get(rw, 10))
    ok = w == 20 or (w != 1 and w + mod >= dc)
    n, wirkt = 0, ""
    if c.get("schaden_art"):
        n = max(1, _dice(rng, 1, wuerfel) + dm.body(r, h, wert, dinge=False))
        n = (n // 2 if c.get("halb") else 0) if ok else n
        if n:
            n, wirkt = against(g, art, n, magisch=True)
    zs = {z["id"]: z for z in r.get("zustaende") or []}
    z = zs.get(c.get("zustand")) if not ok else None
    life[g["k"]] -= n
    print(f"dungeon: kampf | rettung gegner | {'geschafft' if ok else 'nicht geschafft'}", flush=True)
    return {"pid": pid, "name": h["name"], "ziel": g["k"], "gegner": g["name"], "mit": mit, "wert": wert, "w": 0, "ws": [], "vt": "",
            "bonus": 0, "gesamt": 0, "rk": g["rk"], "treffer": bool(n or z), "krit": False, "schaden": n, "faellt": bool(n) and life[g["k"]] <= 0,
            "art": art if n else "", "wirkt": wirkt, "eig": [], "gegner_rettung": {"wert": rw, "w": w, "gesamt": w + mod, "gegen": dc, "ok": ok},
            **({"zauber_zustand": {"id": z["id"], "zuege": z["runden"]}} if z else {})}


def tables_on(rd):
    """The host's admin switch for the critical and fumble tables (D&D idea 2)."""
    import features
    return bool(rd.get("owner")) and features.allowed(KRIT, rd["owner"])


def table(dm, r, rd, krit, patzer, art, spell, fern, rng):
    """D&D idea 2: a critical hit rolls a d12 on the table of its kind of damage (krit), a natural 1 on the fumble table
    of melee, ranged or spell (patzer, mild); the line as data for the narration, a state of the catalog for its turns:
    on the foe (krit_zustand, apply) or on the hero (patzer_zustand). Nothing without the switch or a table."""
    i = r.get("ideen") or {}
    if not (krit or patzer) or not tables_on(rd):
        return {}
    rows = (i.get("krit") or {}).get(art or "wucht") if krit else (i.get("patzer") or {}).get("zauber" if spell else "fernkampf" if fern else "nahkampf")
    if not rows:
        return {}
    import dungeon_ideen                 # the table's die (dungeon_ideen imports this module)
    w = rng.randint(1, dungeon_ideen.KRIT_W)
    e = next((x for x in rows if x["w"] == w), None)
    if not e:
        return {}
    li = 1 if rd.get("lang") == "en" else 0
    k = "krit" if krit else "patzer"
    dm._day.bump(k + "_gewuerfelt")
    print(f"dungeon: kampf | {k} tabelle | {w}", flush=True)
    return {k + "_tabelle": e["t"][li], "tabelle_w": w, **({k + "_zustand": {"id": e["zustand"], "zuege": e["zuege"]}} if e.get("zustand") else {})}


def st(rd, who, z):
    """A state from the tables (D&D idea 2) on a foe or a hero for its turns; one of a kind at a time."""
    if not who or not z or z["id"] in {x["id"] for x in who.get("zust") or []}:
        return
    who.setdefault("zust", []).append({"id": z["id"], "bis": rd.get("zug", 0) + z["zuege"]})


def foe_has(r, rd, g, wirkung):
    """Whether a foe has a state in force with this wirkung (from a critical hit, D&D idea 2)."""
    zs = {z["id"]: z for z in r.get("zustaende") or []}
    return any(wirkung in zs.get(x["id"], {}).get("wirkung", ()) for x in g.get("zust") or [] if x.get("bis", 0) >= rd.get("zug", 0))


def oil(dm, r, rd, pid, h, c):
    """Wirtschaft Punkt 9: an oil from the bag on the weapon in the main hand: its kind for OEL_TREFFER hits, a new oil
    replaces the old. Returns False without a weapon (nothing used up)."""
    wp = _weapon(dm, r, h)
    if not wp:
        print("dungeon: oel | keine waffe", flush=True)
        return False
    wp["oel"] = {"art": c["oel"], "n": OEL_TREFFER}
    a = ART_NAME[c["oel"]]
    dm._log(rd, "system", text=[f"{h['name']} reibt die Waffe ein: {OEL_TREFFER} Treffer mit {a[0]}.",
                                f"{h['name']} coats the weapon: {OEL_TREFFER} hits with {a[1]}."])
    dm._day.bump("oel")
    print("dungeon: oel | aufgetragen", flush=True)
    return True


def used_oil(dm, r, rd, pid, h):
    """One hit of the oil is spent; the last one leaves the blade clean."""
    wp = _weapon(dm, r, h)
    if not wp or not wp.get("oel"):
        return
    wp["oel"]["n"] -= 1
    if wp["oel"]["n"] <= 0:
        del wp["oel"]
        dm._log(rd, "system", text=[f"Das Öl auf der Waffe von {h['name']} ist verbraucht.", f"The oil on {h['name']}'s weapon is spent."])
        print("dungeon: oel | verbraucht", flush=True)
    else:
        print("dungeon: oel | treffer", flush=True)


def against(g, art, n, magisch=False):
    """A hit's damage after the foe's resistances: (damage, "immun"|"resistenz"|"schwaeche"|""). A magic weapon (bonus
    +1 or more) or a spell goes through a resistance against hieb, stich and wucht (Dominik 2026-10-25, Punkt 2)."""
    if art and art in g.get("immun", ()):
        return 0, "immun"
    if art and art in g.get("resistenz", ()) and not (magisch and art in KOERPER):
        return max(1, n // 2), "resistenz"
    if art and art in g.get("schwaeche", ()):
        return n * 2, "schwaeche"
    return n, ""


def _states(r, h):
    """A hero's states in force: their catalog entries."""
    return [z for _, z in states_with(r, h)]


def states_with(r, h):
    """A hero's states in force as (its entry in h["zust"], its catalog entry)."""
    by = {z["id"]: z for z in r.get("zustaende") or []}
    return [(x, by[x["id"]]) for x in h.get("zust") or [] if x.get("id") in by]


def left(x, zug):
    """The turns a hero's state still lasts (expire keeps it while bis >= the round's turn), at least 1."""
    return max(1, int(x.get("bis", 0)) - int(zug) + 1)


def has(r, h, wirkung):
    return any(wirkung in z["wirkung"] for z in _states(r, h))


def blocked(r, h):
    """The state that takes a hero's turn (kein_zug), "" for none."""
    return next((z["id"] for z in _states(r, h) if "kein_zug" in z["wirkung"]), "")


def _state_vt(r, h, vt, wofuer):
    """Advantage or disadvantage by the hero's states: wofuer "angriff" (own attack), "gegen" (a foe's attack on it),
    "probe" (a check); for "gegen" the advantage is the foe's. Both cancel to a plain roll, like the burden (dungeon.roll)."""
    up_, down = {"angriff": ("vorteil_angriff", "nachteil_angriff"), "gegen": ("vorteil_gegen", "nachteil_gegen"),
                 "probe": ("", "nachteil_proben")}[wofuer]
    plus, minus = up_ and has(r, h, up_), has(r, h, down)
    if plus and not minus:
        return "" if vt == "nachteil" else "vorteil"
    if minus and not plus:
        return "" if vt == "vorteil" else "nachteil"
    return vt


def blows(g):
    """How often a foe of the encounter attacks in one turn: its multiattack, a boss at least twice."""
    return max(int(g.get("angriffe") or 1), 2 if g.get("boss") else 1)


def foes_turn(dm, r, rd, hits, rng=None):
    """Every foe still up after the heroes' attacks attacks: as often as its multiattack says (Tabletop-Punkt 12,
    "angriffe" 2 to 5, missing 1), a boss at least twice; the first blow at the last who hit it, the others at a standing
    hero by the seed. A hit may cause one of the foe's states (save), a state that burns or bleeds costs
    BRENNT at each turn. [{k, gegner, pid, name, w, ws, vt, gesamt, rk, treffer, schaden, art, zustand, rettung}]."""
    rng = rng or random
    if not rd.get("kampf"):
        return []
    down = {x["ziel"] for x in hits if x["faellt"]}
    standing = [(pid, p["held"]) for pid, p in dm.seated(rd) if not dm.zustand(p["held"])]
    if not standing:
        return []
    out = []
    zs = {z["id"]: z for z in r.get("zustaende") or []}
    reach = [(pid, h) for pid, h in standing if not umgebung.away(rd, pid)]   # a way out of a prop (round 2, idea 3)
    reach += gefaehrte.targets(rd)                # the companions may be struck like a hero (round 2, idea 9)
    for g in up(rd):
        if g["k"] in down or not reach:
            continue
        if foe_has(r, rd, g, "kein_zug"):          # stunned, unconscious … by a critical hit: no blow (D&D idea 2)
            print("dungeon: kampf | gegner setzt aus", flush=True)
            continue
        sagt = haltung.blow(rd, g, reach)      # the blow it announced last turn (round 2, idea 2)
        for zug in range(blows(g)):
            by = [x["pid"] for x in hits if x["ziel"] == g["k"] and x["treffer"]]
            art = sagt[2] if sagt and not zug else ""
            pid, h = (sagt[:2] if art else None) or (next(((q, hh) for q, hh in reach if by and q == by[-1]), None) if not zug else None) \
                or reach[rng.randrange(len(reach))]
            vt = "" if h.get("gefaehrte") else _state_vt(r, h, "", "gegen")
            if art == "lauert":
                vt = "" if vt == "nachteil" else "vorteil"
            steht = haltung.stance(rd, pid)
            if foe_has(r, rd, g, "nachteil_angriff"):
                vt = "" if vt == "vorteil" else "nachteil"
            if any(x["ziel"] == g["k"] and x["pid"] == pid and x["treffer"] and "reichweite" in x.get("eig", ()) for x in hits):
                vt = "" if vt == "vorteil" else "nachteil"    # kept at a distance by a reach weapon
            ws = [rng.randint(1, 20) for _ in range(2 if vt else 1)]
            w = max(ws) if vt == "vorteil" else min(ws)
            ac = (h["ruestung"] if h.get("gefaehrte") else rk(dm, r, h)) + (haltung.ABWEHR if steht == "abwehr" else 0) + umgebung.cover(rd, pid)
            plus = (BOSS_PHASE if g.get("phase") == 2 else 0) + (haltung.ZIELT if art == "zielt" else -haltung.HOLT if art == "holt_aus" else 0)
            hit = w == 20 or (w != 1 and w + g["angriff"] + plus >= ac)
            n = max(1, _dice(rng, g["wuerfel"] * (2 if w == 20 else 1) * (2 if art == "holt_aus" else 1), g["schaden"]) + g["plus"]) if hit else 0
            x = {"k": g["k"], "gegner": g["name"], "pid": pid, "name": h["name"], "w": w, "ws": ws, "vt": vt, "bonus": g["angriff"] + plus,
                 "gesamt": w + g["angriff"] + plus, "rk": ac, "treffer": hit, "krit": w == 20, "schaden": n, "art": g.get("art", ""),
                 **({"ansage": art} if art else {}), **({"haltung": steht} if steht else {})}
            frei = [z for z in g.get("zustaende") or [] if z in zs and z not in {y["id"] for y in h.get("zust") or []}]
            if hit and frei and not h.get("gefaehrte"):   # the hit may cause a state: the hero saves
                z = frei[rng.randrange(len(frei))]
                wert = "weisheit" if z in GEIST else "konstitution"
                c = dm._by(r, "gegner").get(g["id"], {})      # Kampf-Audit N6: the bestiary's DC, else 10 + a quarter of its level
                dc = c["sg"] if isinstance(c.get("sg"), int) and not isinstance(c.get("sg"), bool) else RETTUNG + int(c.get("stufe", 0) // 4)
                rw = max(rng.randint(1, 20), rng.randint(1, 20)) if steht == "ausweichen" else rng.randint(1, 20)
                x["rettung"] = {"zustand": z, "wert": wert, "w": rw, "gesamt": rw + dm.total(r, h, wert), "gegen": dc,
                                "ok": rw + dm.total(r, h, wert) >= dc}
            out.append(x)
    for g in up(rd):                              # a foe bleeding or burning from a critical hit (D&D idea 2)
        if g["k"] not in down and foe_has(r, rd, g, "schaden_pro_zug"):
            zid = next(x["id"] for x in g["zust"] if "schaden_pro_zug" in zs.get(x["id"], {}).get("wirkung", ()))
            out.append({"k": g["k"], "gegner_schaden": zid, "gegner": g["name"], "pid": "", "name": "", "schaden": rng.randint(1, BRENNT)})
    for pid, h in standing:                       # burning, bleeding: every turn of the foes
        for z in _states(r, h):
            if "schaden_pro_zug" in z["wirkung"]:
                out.append({"k": "", "zustand_schaden": z["id"], "pid": pid, "name": h["name"], "schaden": rng.randint(1, BRENNT)})
    return out


def zug_facts(r, rd, x):
    """One of the foes' turn for the model: an attack (with a state's save), or a state's damage."""
    if x.get("zustand_schaden"):
        return {"zustand": _zname(r, rd, x["zustand_schaden"]), "trifft": x["name"], "schaden": x["schaden"]}
    if x.get("gegner_schaden"):
        return {"zustand": _zname(r, rd, x["gegner_schaden"]), "trifft": x["gegner"], "schaden": x["schaden"]}
    rw = x.get("rettung")
    return {"gegner": x["gegner"], "greift_an": x["name"], "trifft": x["treffer"], "schaden": x["schaden"],
            **({"wie_angesagt": x["ansage"]} if x.get("ansage") else {}), **({"haltung": x["haltung"]} if x.get("haltung") else {}),
            **({"zustand": _zname(r, rd, rw["zustand"]), "gerettet": rw["ok"]} if rw else {})}


def facts(dm, r, rd, held, li):
    """The fight for the model: every foe with its life, or the offer when there is none."""
    k = rd.get("kampf")
    if k:
        return {"kampf": {"gefahr": k["gefahr"], "gegner": [{"name": g["name"], "leben": f"{max(0, g['leben'])}/{g['max']}",
                                                              **({"aus": g["aus"]} if g["aus"] else {}),
                                                              **({"boss": True, "phase": g.get("phase", 1)} if g.get("boss") else {})}
                                                             for g in k["gegner"]]}}
    o = offer_facts(dm, r, rd, held, li)
    return {"angebot": o} if o else {}


def task(rd, lang):
    return " " + (AUFGABE_KAMPF if rd.get("kampf") else AUFGABE_ANGEBOT)[lang]


def apply(dm, r, rd, hits, zuege, ende, ep, rng=None):
    """The rolled fight into the round: the heroes' hits on the foes, flight, the foes' attacks as consequences for
    dungeon.consequences, the end. Returns the foes' hits as folgen [{pid, art, zahl, gegner}]."""
    rng = rng or random
    k = rd.get("kampf")
    if not k:
        return []
    by = {g["k"]: g for g in k["gegner"]}
    folgen = []
    expire(dm, rd)
    for x in hits:
        g = by.get(x["ziel"])
        if not g or g["aus"]:
            continue
        if x.get("kann_nicht"):
            dm._log(rd, "angriff", pid=x["pid"], name=x["name"], gegner=g["name"], mit=x["mit"], kann_nicht=_zname(r, rd, x["kann_nicht"]),
                    treffer=False, schaden=0)
            print("dungeon: kampf | kann nicht", flush=True)
            continue
        dm._log(rd, "angriff", pid=x["pid"], name=x["name"], gegner=g["name"], mit=x["mit"], w=x["w"], ws=x["ws"], vt=x["vt"],
                bonus=x["bonus"], gesamt=x["gesamt"], rk=x["rk"], treffer=x["treffer"], krit=x["krit"], schaden=x["schaden"],
                sart=x.get("art", ""), wirkt=x.get("wirkt", ""), eig=x.get("eig", []),
                **{k: x[k] for k in ("mut", "extra", "raub", "glueck", "echt", "krit_tabelle", "patzer_tabelle", "beleg", "gegner_rettung") if x.get(k)},
                **({"zustand": _zname(r, rd, x["zauber_zustand"]["id"])} if x.get("zauber_zustand") else {}))
        dm._day.bump("treffer" if x["treffer"] else "daneben")
        ehre.count(rd, "" if gefaehrte.is_one(x["pid"]) else x["pid"], treffer=int(x["treffer"]), krit=int(x["treffer"] and x["krit"]), schaden=x["schaden"] if x["treffer"] else 0,
                   zwanzig=int(x["w"] == 20), eins=int(x["w"] == 1))     # Ehrungen des Abends (D&D idea 1), the panel's own numbers
        if x.get("wirkt") and x.get("art"):    # Punkt 6: a hit shows how the foe takes this kind
            learn(rd, g["id"], [x["art"]])
        held = (dict(dm.seated(rd)).get(x["pid"]) or {}).get("held")
        if x.get("raub") and held and not dm.zustand(held):     # life drain: the hero heals by the panel's die
            dm.heal(held, x["raub"])
            print("dungeon: kampf | lebensraub", flush=True)
        if any(e.get("oel") for e in x.get("extra") or ()) and held:
            used_oil(dm, r, rd, x["pid"], held)
        was = hurt(g, x["schaden"]) if x["treffer"] else ""
        st(rd, g, x.get("krit_zustand") if x["treffer"] and not was == "besiegt" else None)   # D&D idea 2: the critical hit's state
        st(rd, g, x.get("zauber_zustand") if not was == "besiegt" else None)     # Kampf-Audit H4: the spell's state
        st(rd, held, x.get("patzer_zustand") if held and not dm.zustand(held) else None)    # the fumble's, on the hero
        if was == "besiegt":
            dm._log(rd, "gegner", gegner=g["name"], was="besiegt")
            dm._day.bump("besiegt")
            if not g.get("person"):              # a person is met on the page „Personen“, never a monster (Paket 8, Z8)
                album.win(dm, rd, g["id"])       # the Monster-Album (D&D idea 12): one more win for the fight's heroes
        elif was == "phase2":
            dm._log(rd, "gegner", gegner=g["name"], was="phase2")
            print("dungeon: kampf | boss | phase2", flush=True)
    seats = dict(dm.seated(rd))
    for x in zuege:
        if x.get("zustand_schaden") and x["pid"] in seats and not dm.zustand(seats[x["pid"]]["held"]):
            dm._log(rd, "zustand", pid=x["pid"], name=x["name"], zustand=_zname(r, rd, x["zustand_schaden"]), schaden=x["schaden"])
            folgen.append({"pid": x["pid"], "art": "schaden", "zahl": x["schaden"], "gegner": _zname(r, rd, x["zustand_schaden"])})
            continue
        if x.get("gegner_schaden"):              # a foe bleeds or burns from a critical hit (D&D idea 2)
            g = by.get(x["k"])
            if g and not g["aus"]:
                dm._log(rd, "zustand", name=g["name"], gegner=g["name"], zustand=_zname(r, rd, x["gegner_schaden"]), schaden=x["schaden"])
                if hurt(g, x["schaden"]) == "besiegt":
                    dm._log(rd, "gegner", gegner=g["name"], was="besiegt")
                    dm._day.bump("besiegt")
                    if not g.get("person"):
                        album.win(dm, rd, g["id"])
                print("dungeon: kampf | gegner zustand", flush=True)
            continue
        g = by.get(x["k"])
        if g and not g["aus"] and gefaehrte.is_one(x["pid"]):   # a blow at a companion (round 2, idea 9)
            gefaehrte.struck(dm, rd, x, rng)
            continue
        if not g or g["aus"] or x["pid"] not in seats or dm.zustand(seats[x["pid"]]["held"]):
            continue
        dm._log(rd, "angriff", gegner=g["name"], pid=x["pid"], name=x["name"], w=x["w"], ws=x.get("ws", [x["w"]]), vt=x.get("vt", ""),
                bonus=x["bonus"], gesamt=x["gesamt"], rk=x["rk"], treffer=x["treffer"], krit=x["krit"], schaden=x["schaden"], von_gegner=True,
                **({"beleg": x["beleg"]} if x.get("beleg") else {}))
        if x["treffer"]:
            folgen.append({"pid": x["pid"], "art": "schaden", "zahl": x["schaden"], "gegner": g["name"], "sart": x.get("art", "")})
            if x["krit"]:
                narben.wound(dm, r, rd, x["pid"], seats[x["pid"]]["held"], "krit")   # a foe's critical hit leaves a wound (D&D idea 8)
        rw = x.get("rettung")
        if rw:
            suffers(r, rd, seats[x["pid"]]["held"], rw)
            dm._log(rd, "rettung", pid=x["pid"], name=x["name"], gegner=g["name"], zustand=_zname(r, rd, rw["zustand"]), wert=rw["wert"],
                    w=rw["w"], gesamt=rw["gesamt"], gegen=rw["gegen"], ok=rw["ok"])
            if rw["ok"]:
                print("dungeon: kampf | rettung | ok", flush=True)
            else:
                print("dungeon: kampf | rettung | zustand", flush=True)
    for g in up(rd):
        if flees(g, rng):
            dm._log(rd, "gegner", gegner=g["name"], was="aufgegeben" if dm.kids(r, rd) else "geflohen")
            dm._day.bump("geflohen")
    # Kampf-Audit 3 (Dominik 2026-10-26): peace only after the panel's own peace check passed (peace), never because
    # the model says so; then the fight ends in peace whatever the model wrote. M6: flight the same way (escape)
    if rd["kampf"].get("geschafft"):
        ende = "frieden"
    elif rd["kampf"].pop("entkommen", False):
        ende = "flucht"
    elif ende in ENDE:
        print(f"dungeon: kampf | {ende} | ohne probe", flush=True)
        ende = ""
    if not up(rd) or ende in ENDE:
        end(dm, r, rd, ep, ende)
    return folgen


def peace(dm, r, rd, proben, hits):
    """Kampf-Audit 3: a hero whose action asks for peace (FRIEDEN_WORTE, intent) and who does not attack rolls the
    panel's Charisma check against the higher of FRIEDEN_SG[0] and FRIEDEN_SG[1] + the strongest foe's level, in place
    of the model's checks for it; once a fight (rd["kampf"]["frieden"], set in dungeon.apply), and the check gives no
    check's experience. Passed (apply), the fight ends in peace with half the experience of the foes still up (end)."""
    if not rd.get("kampf") or not up(rd):
        return proben
    by = dm._by(r, "gegner")
    hit = {x["pid"] for x in hits}
    if rd["kampf"].get("frieden"):               # tried once already this fight: words of peace are only words now
        for pid, a in (rd.get("offen") or {}).items():
            if pid not in hit and intent(a.get("text")) == "frieden":
                print("dungeon: kampf | frieden | schon versucht", flush=True)
                return [p for p in proben if p["pid"] != pid]
        return proben
    for pid, a in (rd.get("offen") or {}).items():
        h = (rd["plaetze"].get(pid) or {}).get("held")
        if pid in hit or not h or dm.zustand(h) or intent(a.get("text")) != "frieden":
            continue
        sg = max(FRIEDEN_SG[0], FRIEDEN_SG[1] + max(math.ceil((by.get(g["id"]) or {}).get("stufe", 0)) for g in up(rd)))
        li = 1 if rd.get("lang") == "en" else 0
        print("dungeon: kampf | frieden | probe", flush=True)
        return [p for p in proben if p["pid"] != pid] + [{"pid": pid, "wert": "charisma", "schwer": sg, "vt": "", "frieden": True,
                                                            "wofuer": ("Frieden anbieten", "offer peace")[li]}]
    return proben


def escape(dm, r, rd, proben, hits):
    """Kampf-Audit M6: when most heroes who can act flee (intent "flucht", no attack), each of them rolls the panel's
    Geschick check against the higher of FLUCHT_SG[0] and FLUCHT_SG[1] + the strongest foe's level in place of the
    model's checks for it; at least half passed (dungeon.apply), the fight ends in flight (apply). The check gives no
    check's experience. Fewer: the words stay words and the fight goes on."""
    if not rd.get("kampf") or not up(rd):
        return proben
    hit = {x["pid"] for x in hits}
    offen = rd.get("offen") or {}
    frei = [pid for pid, p in dm.seated(rd) if not dm.zustand(p["held"])]
    weg = [pid for pid in frei if pid not in hit and intent((offen.get(pid) or {}).get("text")) == "flucht"]
    if not weg:
        return proben
    if 2 * len(weg) <= len(frei):
        print(f"dungeon: kampf | flucht | keine mehrheit | {len(weg)} von {len(frei)}", flush=True)
        return proben
    by = dm._by(r, "gegner")
    sg = max(FLUCHT_SG[0], FLUCHT_SG[1] + max(math.ceil((by.get(g["id"]) or {}).get("stufe", 0)) for g in up(rd)))
    li = 1 if rd.get("lang") == "en" else 0
    print(f"dungeon: kampf | flucht | probe | {len(weg)} helden", flush=True)
    return [p for p in proben if p["pid"] not in weg] + [{"pid": pid, "wert": "geschick", "schwer": sg, "vt": "", "flucht": True,
                                                          "wofuer": ("Fliehen", "flee")[li]} for pid in weg]


def hurt(g, n):
    """A hero's hit on a foe: its life down; "besiegt" at 0, "phase2" when a boss comes to half its life (its second
    phase), else ""."""
    g["leben"] = max(0, g["leben"] - n)
    if g["leben"] <= 0:
        g["aus"] = "besiegt"
        return "besiegt"
    if g.get("boss") and g.get("phase") == 1 and g["leben"] * 2 <= g["max"]:
        g["phase"] = 2
        return "phase2"
    return ""


def suffers(r, rd, h, rw):
    """A failed save puts its state on the hero for the state's turns (once)."""
    z = next((z for z in r.get("zustaende") or [] if z["id"] == rw["zustand"]), None)
    if z and not rw["ok"] and z["id"] not in {y["id"] for y in h.get("zust") or []}:
        h.setdefault("zust", []).append({"id": z["id"], "bis": rd.get("zug", 0) + z["runden"]})


def flees(g, rng):
    """A foe at a quarter of its life or less flees on a d20 of FLUCHT_W or less."""
    if 0 < g["leben"] * FLUCHT <= g["max"] and rng.randint(1, 20) <= FLUCHT_W:
        g["aus"] = "geflohen"
        return True
    return False


def _zname(r, rd, zid):
    z = next((z for z in r.get("zustaende") or [] if z["id"] == zid), None)
    return z["name"][1 if rd.get("lang") == "en" else 0] if z else zid


def expire(dm, rd, all_=False):
    """The heroes' and the foes' states whose turns are over go (all of them when the fight ends)."""
    for g in (rd.get("kampf") or {}).get("gegner") or []:
        if g.get("zust"):
            g["zust"] = [] if all_ else [x for x in g["zust"] if x.get("bis", 0) >= rd.get("zug", 0)]
            if not g["zust"]:
                g.pop("zust")
    for _, p in dm.seated(rd):
        h = p["held"]
        if h.get("zust"):
            h["zust"] = [] if all_ else [x for x in h["zust"] if x.get("bis", 0) >= rd.get("zug", 0)]
            if not h["zust"]:
                h.pop("zust")


def end(dm, r, rd, ep, why=""):
    """The fight is over: the share of the foes' experience won (all for the defeated, half for the fled ones; Idee 7:
    all of the foes still up when it ends in peace in a turn with a check passed, k["geschafft"], dungeon.apply) gives
    every hero it began with (k["helden"], never one who came later) its own reward (Review 27.10. B9): BUDGET of its
    level times the encounter's adjusted experience against the reference budget (reference), so it does not hang on
    the group's size; into ep (pid -> number, apply gives it to the table), a line for the log. A won fight of a room
    of the map leaves rd["sieg"] = the room's tag for dungeon_karte (the way is free)."""
    k = rd.pop("kampf", None)
    if not k:
        return
    expire(dm, rd, all_=True)
    gefaehrte.after_fight(rd)                    # the companions stand with the group again (round 2, idea 9)
    import dungeon_personen
    dungeon_personen.after_fight(dm, rd, k)      # a person beaten or fled into the chronicle (Personen-Katalog 4)
    besiegt = [g for g in k["gegner"] if g["aus"] == "besiegt"]
    flohen = [g for g in k["gegner"] if g["aus"] == "geflohen"]
    frieden = [g for g in k["gegner"] if not g["aus"]] if why == "frieden" and k.get("geschafft") else []   # Idee 7
    alle = sum(g["ep"] for g in besiegt) + sum(g["ep"] // 2 for g in flohen + frieden)   # Kampf-Audit 3: peace gives half
    alle = int(alle * ALLEIN) if k.get("allein") else alle      # a lone foe the scene asked for (Review 27.10. B8)
    # divided by the group the fight was made for (Dominik 2026-10-25, Punkt 3): a hero who left has fled and its share
    # stays out, one who arrived later (dungeon.arrive) gets none; one who died in it is no longer in ep: its share goes
    # to the living (Kampf-Audit N4)
    start = k.get("helden")
    teil = [pid for pid in ep if start is None or pid in start]
    zahl = len(teil) if start is None else len([pid for pid in start if pid in ep or pid not in rd["plaetze"]])   # the fallen out
    anteil = alle / max(1, sum(g["ep"] for g in k["gegner"]))
    got = []
    for pid in teil:
        h = (rd["plaetze"].get(pid) or {}).get("held") or {}
        if k.get("bezug"):                      # B9: the hero's level's budget times the encounter against the reference
            got.append(reward(k, h.get("stufe", 1), anteil))
        else:                                   # a fight begun before B9: divided (Kampf-Audit N4: rounded down)
            got.append(alle // max(1, zahl))
        ep[pid] += got[-1]
    each = sum(got) // max(1, len(got))
    if k.get("raum") and not why:
        rd["sieg"] = k["raum"]
        rd.pop("raum_gegner", None)
    if not why:
        dm.breather(rd)                          # Verschnaufen after a won fight (Review 27.10. B5)
    dm._log(rd, "kampf", was=why or "sieg", besiegt=len(besiegt), geflohen=len(flohen), ep=each, boss=any(g.get("boss") for g in besiegt),
            frieden=len(frieden))
    rd["kampf_aus"] = {"leben0": k.get("leben0", 0), "why": why}      # for the dial, after the last hits are in (turn_dial)
    dm._day.bump("kaempfe")
    print(f"dungeon: kampf | ende | {why or 'sieg'} | {len(besiegt)} besiegt | {len(flohen)} geflohen", flush=True)
    return besiegt


LAGE = (("unverletzt", ("unverletzt", "unhurt")), ("angeschlagen", ("angeschlagen", "bruised")),
        ("schwer", ("schwer verletzt", "badly hurt")), ("fast", ("fast besiegt", "nearly beaten")))   # Tabletop-Punkt 11


def lage(g):
    """A foe's life as a word for the players (Tabletop-Punkt 11, from improved-initiative): unverletzt at full life,
    angeschlagen above half, schwer verletzt above a quarter, else fast besiegt."""
    n, m = max(0, g["leben"]), max(1, g["max"])
    return LAGE[0 if n >= m else 1 if 2 * n > m else 2 if 4 * n > m else 3]


def view(dm, r, rd, host=True):
    """The fight bar: every foe with its sign, picture, life and whether it is out. None without a fight. Only the host
    sees the numbers of a foe's life; every other seat (and the TV, the app, the car) sees its state as a word (lage)."""
    k = rd.get("kampf")
    if not k:
        return None
    import dungeon_dingbild as db
    have = db.files() if db.on() else frozenset()
    lang, cat = "en" if rd.get("lang") == "en" else "de", dm._by(r, "gegner")
    out = [dict(card(dm, r, rd, g["id"], lang) if g["id"] in cat else {}, k=g["k"], id=g["id"], name=g["name"], zeichen=g["zeichen"],
                leben=max(0, g["leben"]), max=g["max"], aus=g["aus"], phase=g.get("phase", 1), bild=_picture(r, rd, g["id"], have, g.get("person", "")),
                lage=lage(g)[0], lage_name=lage(g)[1][1 if lang == "en" else 0],
                **({"zust": [_zname(r, rd, x["id"]) for x in g["zust"] if x.get("bis", 0) >= rd.get("zug", 0)]} if g.get("zust") else {})) for g in k["gegner"]]
    if not host:
        out = [{k_: v for k_, v in x.items() if k_ not in ("leben", "max")} for x in out]
    return {"gegner": out, "gefahr": k["gefahr"], "stehen": len(up(rd))}


def _picture(r, rd, gid, have, person=""):
    """A foe's picture: a person who fights shows its own portrait (Review 27.10. Paket 8, Z8), any other its bestiary
    picture; "" while there is none."""
    import dungeon_dingbild as db
    g = ((rd.get("nsc") or {}).get(person) or {}).get("gesicht") if person else None
    if isinstance(g, dict) and g.get("st") == "ok" and g.get("n") in have:
        return g["n"]
    c = next((x for x in r.get("gegner") or [] if x["id"] == gid), None)
    n = db.picture_of(r, c, rd.get("welt", ""))[0] if c and have else ""
    return n if n in have else ""


def pictures(dm, r, rd, out, host=True):
    """view's step for the log: every foe of an encounter card gets "bild" (its bestiary picture, "" while none); its
    life stays the host's (Tabletop-Punkt 11)."""
    import dungeon_dingbild as db
    have = db.files() if db.on() else frozenset()
    out["log"] = [dict(e, gegner=[{k_: v for k_, v in dict(g, bild=_picture(r, rd, g["id"], have, g.get("person", ""))).items() if host or k_ != "leben"}
                                  for g in e["gegner"]]) if e.get("art") == "begegnung" else e
                  for e in out.get("log") or []]


def card(dm, r, rd, gid, lang):
    """One foe of the bestiary for its window at the table: picture, text and values; what hurts it more or less only as
    far as the group found out (known)."""
    li = 1 if lang == "en" else 0
    c = dm._by(r, "gegner")[gid]
    kennt = known(rd, gid)
    return {"id": c["id"], "name": c["name"][li], "info": c["info"][li], "zeichen": c.get("zeichen", ""), "stufe": c["stufe"],
            "leben": c["leben"], "rk": c["ruestung"], "angriff": c["angriff"], "groesse": c.get("groesse", "mittel"),
            "schaden": f"{c.get('anzahl_wuerfel', 1)}{'W' if not li else 'd'}{c['schaden']}" + (f"+{c['schaden_plus']}" if c.get("schaden_plus", 0) > 0 else
                                                                                               f"{c['schaden_plus']}" if c.get("schaden_plus", 0) < 0 else ""),
            "ep": c["ep"],
            # for the big window (Dominik 2026-10-24 „click auf beute etc. sollte ein fenster aufgehen lassen um es genauer zu
            # betrachten - auch gegener“, 1a): the six scores with their bonus and what its blows can cause
            "werte": [{"kurz": w["name"][li][:3].upper(), "name": w["name"][li], "wert": (c.get("werte") or {}).get(w["id"], 10),
                       "mod": dm.mod((c.get("werte") or {}).get(w["id"], 10))} for w in r["werte"]],
            "zustaende": [{"name": z["name"][li], "info": z["info"][li]} for z in r.get("zustaende") or [] if z["id"] in (c.get("zustaende") or [])],
            # Kampf Teil 2: its damage kind, what hurts it more or less, a boss
            "art": ART_NAME[c["schaden_art"]][li] if c.get("schaden_art") in ART_NAME else "",
            # Schadensarten Punkt 6: at the table only what the group found out (known), the rest counted as unknown
            **{x: [ART_NAME[a][li] for a in c.get(x) or [] if a in ART_NAME and a in kennt] for x in ("resistenz", "immun", "schwaeche")},
            "unbekannt": sum(1 for x in ("resistenz", "immun", "schwaeche") for a in c.get(x) or [] if a in ART_NAME and a not in kennt),
            "boss": bool(c.get("boss")), "angriffe": blows(c)}


def known(rd, gid):
    """The damage kinds the group knows of a foe: found out by a hit (wirkt) or a passed Intelligenz check in a fight."""
    return set((rd.get("kennt") or {}).get(gid) or [])


def learn(rd, gid, arten):
    """The group finds out how a foe takes these kinds (kept for the round, at most KENNT_MAX foes)."""
    k = rd.setdefault("kennt", {})
    neu = [a for a in arten if a in ART_NAME and a not in (k.get(gid) or [])]
    if not neu:
        return
    k[gid] = (k.get(gid) or []) + neu
    if len(k) > KENNT_MAX:
        k.pop(next(iter(k)))
    print(f"dungeon: kampf | erkannt | {len(neu)} arten", flush=True)


def for_live(rs):
    return {"kaempfe_laufen": sum(1 for v in rs if v.get("kampf")), "gegner_stehen": sum(len(up(v)) for v in rs),
            "gegner_erkannt": sum(len(v.get("kennt") or {}) for v in rs),
            "gegner_mehrfach": sum(1 for v in rs for g in up(v) if blows(g) > 1)}
