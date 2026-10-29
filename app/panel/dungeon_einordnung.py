"""KI-Dungeon-Master: die Einordnung (Dominik 2026-10-28 „es kommen zu viele fehler aktuell … mache mir vorschläge“,
Vorschlag 7, „ok“): the one module of every fixed word list that sorts what a player typed, and one answer for each
action. kind(text) is exactly one of ARTEN by the fixed order below, so no two lists say two things of one sentence
(the Satz-Prüfstand found „Wir schlagen hier unser Lager auf“ as an attack and a rest, „Ich frage den Wirt nach dem
Weg. Dann gehe ich los.“ as an attack and a question). Never the model.

Order   angriff, bezug, flucht, frieden (in a fight an attack wins over running away, Kampf-Audit M6), alltag (every part
        an everyday act), frage, verkauf, kauf, rast, gehen; else "".
fight(text)       what the action does in a fight: one of KAMPF or ""
asks(text)        it only asks or talks: kind frage, or frieden with a word of FRAGT (asking for peace talks too)
typed(text)       the kinds the panel carries out or answers itself (GETIPPT) or ""
everyday(text)    only everyday acts: no check
just_going(wofuer)  a check the model asked for only for going somewhere (GEHEN without RISIKO)
values(text)      the values of a check the action's words name (WERTE), in the table's order

New words only with the Satz-Prüfstand's sentences (tests/dungeon_saetze.py, test_dungeon_saetze checks kind() for
each). Data and pure functions: no journal, no switch, the callers log.
"""
import re

ARTEN = ("angriff", "bezug", "flucht", "frieden", "alltag", "frage", "verkauf", "kauf", "rast", "gehen")
KAMPF = ("angriff", "bezug", "flucht", "frieden")
GETIPPT = ("verkauf", "kauf", "rast", "gehen")

# Kampf-Audit 1 (Dominik 2026-10-26 „Empfehlung umsetzen“): the panel makes the attack from the action, never from the
# model's check. ANGRIFF_WORTE attack on their own (with no foe named: the first one standing), BEZUG_WORTE only with a
# foe named in the action; a stem may carry a prefix (er-, be-, zu-, nieder-, ab-, ver-), NICHT_ANGRIFF is taken out
# first („greife nach dem Seil“, „treffe mich mit“, „stoße die Tür auf“, „betrete“). New words only with
# the Satz-Prüfstand's sentences (tests/dungeon_saetze.py, test_dungeon_saetze).
_VOR = r"(?<!\w)(?:er|be|zu|nieder|ab|ver|drauf|los)?"
ANGRIFF_WORTE = re.compile(r"(?i)" + _VOR + r"(?:greif\w*\s+(?:[\w'-]+\s+){0,4}an(?!\w)|verpass\w*\s+(?:[\w'-]+\s+){0,4}eins(?!\w)|angriff|angreif|attackier|attack|schlag|schläg|schlug|"
                           r"stech|stich|stach|stoß|stoss|schieß|schiess|schoss|schuss|tö?te[nt]?(?!\w)|toete|tötet|erschlag|besieg|"
                           r"zerschmetter|erdolch|kämpf|kaempf|hau(?:e|t|en)?(?!\w)|hieb|prügel|prügl|pruegel|pruegl|dresch|"
                           r"schlitz|ramm|tret|tritt|spieß|spiess|kill|hits?(?!\w)|strike|shoot|stab|slash|smite|blast|fight|battle|"
                           r"punch|kick|swing|bash|cleave)")
BEZUG_WORTE = re.compile(r"(?i)" + _VOR + r"(?:triff|treff|traf|ziel|wirf|werf|wurf|schleuder|feuer|stürm|stuerm|schneid|box|"
                         r"(?:gehe?|geht|renne?|rennt|springe?|springt)\s+(?:[\w'-]+\s+){0,2}auf\s+(?:[\w'-]+\s+){0,6}los|stürz\w*\s+(?:[\w'-]+\s+){0,8}auf(?!\w)|"
                         r"stuerz\w*\s+(?:[\w'-]+\s+){0,8}auf(?!\w)|lass\w*\s+(?:[\w'-]+\s+){0,8}fliegen|pack|greif\w*\s+[^.!?;]*?(?<!\w)an(?!\w)|aim|throw|hurl|toss|fire|charge|cut|shove)")
NICHT_ANGRIFF = re.compile(r"(?i)greif\w*\s+nach(?!\w)|treff\w*\s+(?:mich|uns|dich|euch|sich)(?!\w)|(?:stoß|stoss)\w*\s+(?:die|eine|das)\s+"
                           r"(?:tür|tuer|tor|fenster|kiste|truhe)|betret|(?<!\w)(?:tür|tuer)\w*\s+auf|(?:greif|attack)\w*\s+(?:ab|aus)(?!\w)|"
                           r"lagerfeuer|feuer\s+(?:machen|entzünd|an)|reach\s+for|meet\s+with|"
                           # Nachprüfung Welle 1 (2026-10-26): stepping, proposing, fleeing, a look, a light are no attack;
                           # Nachprüfung V01.1.130: each ends at a word, so a foe's name („Nachtmahr“, „Sicherheitsdroide“) stays whole
                           r"(?:tret|tritt|trat)\w*\s+in\s+(?:[\w-]+\s+){0,3}(?:ein|hinein)(?!\w)|"   # „trete in die Halle ein“ (2026-10-28)
                           # Satz-Prüfstand 2026-10-28 (tests/dungeon_saetze.py): a staff, a book, a camp, a headline, an idiom
                           r"(?:mein|meine[nmrs]?|dein\w*|sein\w*|ihr\w*|unser\w*|de[nmrs]|die|das|ein\w*|am|im|vom|zum|mit)\s+(?:[\w-]+\s+){0,2}"
                           r"stab(?:es|s|e)?(?!\w)|stichw\w*|stichflamm\w*|schlag(?:zeile|wort|loch|baum|sahne|ader)\w*|"
                           r"(?:schlag|schläg|schlug)\w*\s+(?:(?:hier|dort|da|jetzt|nun|erst)\s+)?(?:das|den|die|ein\w*|mein\w*|dein\w*|sein\w*|ihr\w*|unser\w*)\s+(?:[\w-]+\s+)?"
                           r"(?:buch|tagebuch|folianten?|karte|heft|seite|lager|zelt|nachtlager)\w*|pack\w*\s+(?:[\w-]+\s+){0,3}aus(?!\w)|"
                           r"ramm\w*\s+(?:[\w-]+\s+){1,2}(?:pfahl|pflock|pfosten|stock|speer|spaten)\w*\s+in(?!\w)|"
                           r"besieg\w*\s+(?:meine|seine|ihre|deine|unsere|eure|die|den)\s+(?:angst|furcht|zweifel|müdigkeit|muedigkeit|schwäche|schwaeche|scham|wut)|"
                           r"(?:kämpf|kaempf)\w*\s+(?:mich|uns|dich|euch|sich)\s+durch\s+(?:das|den|die)\s+(?:gestrüpp|gestruepp|dickicht|unterholz|"
                           r"menge|schnee|sturm|wind|dornen|büsche|buesche|sumpf|matsch)|st(?:e|i)ch\w*\s+in\s+see|t(?:ö|oe)?te\w*\s+die\s+zeit|"
                           r"(?:an|ans|am|zum|ins|vom)\s+(?:das\s+)?(?:lager)?feuer(?!\w)|battle\s*(?:map|plan|field|cry|standard|axe)|(?:by|at|around|near|to|from)\s+the\s+(?:camp\s*)?fire(?!\w)|kick\w*\s+off|swing\w*\s+(?:[\w-]+\s+){0,2}open|"
                           r"(?:tret|tritt|trat)\w*\s+(?:den\s+(?:rückzug|rueckzug)|zur\s+seite|zurück|zurueck|beiseite|ein(?=\s*(?:[.,;:!?]|$|und(?!\w)))|vor(?!\w)|"
                           r"näher|naeher|(?:die|eine|das)\s+(?:tür|tuer|tor|fenster|kiste|truhe)\w*\s+ein(?!\w))|"
                           r"(?:schlag|schläg|schlug)\w*\s+(?:vor(?!\w)|(?:mich|uns|dich|euch|sich)(?!\w)(?!\s+nieder)|alarm)|hau\w*\s+ab(?!\w)|"
                           r"(?:werf|wirf|warf)\w*\s+(?:[\w-]+\s+){0,4}blick|(?:gebe?|gib|reich)\w*\s+(?:[\w-]+\s+){0,4}feuer(?!\s*(?:auf|!|$))|"
                           r"(?:werf|wirf|warf)\w*\s+(?:[\w-]+\s+){1,5}zu(?!\w)(?!\s+(?:dem|der|den|boden)(?!\w))|"
                           r"step\s+(?:back|aside|in|forward)|retreat|fall\s+back|(?:throw|cast)\w*\s+(?:[\w-]+\s+){0,3}(?:glance|look)|"
                           r"suggest|propose|hits?\s+the\s+road|strik\w*\s+(?:a\s+)?(?:deal|bargain|match|light)")
FRIEDEN_WORTE = re.compile(r"(?i)ergebt|ergib|ergeben\s+uns|ergebe\s+mich|aufgeben|gebt\s+auf|kapitulier|verhandel|verhandl|frieden|waffenstillstand|lasst\s+uns\s+reden|"
                           r"überred|ueberred|ruhig\s+bleiben|surrender|give\s+up|parley|negotiat|truce|peace|stand\s+down")

# Kampf-Audit M6: the group flees only when most heroes who can act say so, then by the panel's Geschick check
FLUCHT_WORTE = re.compile(r"(?i)flieh|flücht|fluecht|(?<!ver)(?<!zu)flucht|(?:rückzug|rueckzug)|(?:renn|lauf|spring)\w*\s+(?:[\w'-]+\s+){0,5}(?:weg|davon|fort)(?!\w)|"
                          r"hau\w*\s+ab(?!\w)|(?:zieh|ziehen)\w*\s+(?:uns|mich|euch)\s+zurück|(?<!\w)flee|run\s+away|retreat|fall\s+back|escape|get\s+away")

# Review 27.10. Paket 2 (E1): an action that names a foe standing is an attack, unless it heals, protects, talks,
# looks, hides, gives or waits (these words), flees or asks for peace
SANFT_WORTE = re.compile(r"(?i)(?<!\w)(?:heil|versorg|verbind|schütz|schuetz|beschütz|beschuetz|deck|abschirm|rede|red|sprech|sprich|sag|"
                         r"frag|ruf|antwort|überred|ueberred|droh|beobacht|schau|seh|sieh|beäug|lausch|versteck|duck|gib|geb|reich|zeig|"
                         r"wart|bleib|halt\w*\s+(?:mich|uns)|heal|protect|guard|shield|cover|talk|speak|say|ask|call|threaten|watch|look|"
                         r"observe|hide|give|hand|show|wait|stay)\w*")
MAGIE_WORTE = re.compile(r"(?i)zauber|magie|magisch|spell|magic|(?<!\w)cast")   # an action that casts
WERFEN = ("wirf", "werf", "wurf", "schleuder", "throw", "hurl", "toss")   # an action that throws (eigenschaft wurf)

# going somewhere needs no check (Dominik 2026-10-25, „gehe nach wolfshafen“ got „Sich durch die Gassen von Wolfshafen
# bewegen“ on Geschick): a check whose wofuer has a word of GEHEN and none of RISIKO is dropped; the map moves the group
GEHEN = re.compile(r"(?i)\b(geh(e|en|t|st)?|lauf(e|en|t)?|läufs?t|reis(e|en|t)|beweg\w*|wander\w*|marschier\w*|"
                   r"betr(e|i)t\w*|eintret\w*|tr(e|i)tt?(e|st|en|et)?\s+(in\s+(\w+\s+){0,3}?)?ein(?=\s*(?:[.,;:!?]|$|und(?!\w)))|"   # „betrete die Bibliothek“ (Dominik 2026-10-28)
                   r"walk\w*|go(es|ing)?|travel\w*|mov(e|es|ing)|head(s|ing)?|enter(s|ing|ed)?)\b")
RISIKO = ("unbemerkt", "unauffällig", "ablenk", "leise", "heimlich", "schleich", "versteck", "kletter", "spring", "schwimm", "flieh", "flucht", "vorbei",
          "verfolg", "balancier", "sneak", "quiet", "unseen", "hidden", "climb", "jump", "swim", "flee", "past", "chase", "balanc")

# Erzähler-Prüfstand 28.10. („Harmlose Aktion ohne Probe“ 0 points): everyday acts need no check by a fixed rule, never
# the model's: an action whose every part (split at „und“, „dann“, commas and sentence ends) is one of these
ALLTAG = re.compile(r"(?i)(?<!\w)(?:(?:be)?grü(?:ß|ss)\w*|gr(?:ue|ü)sse?n?|wünsch\w*|wuensch\w*|bedank\w*|danke\w*|lächel\w*|laechel\w*|lächl\w*|laechl\w*|"
                    r"lach\w*|nick\w*|wink\w*|umarm\w*|ess(?:e|en)|iss|isst|trink\w*|frühstück\w*|fruehstueck\w*|"
                    r"pack\w*\s+(?:\w+\s+){0,3}aus|setz\w*\s+(?:\w+\s+){0,2}(?:hin|nieder|ans|an\s+den|auf\s+die)|streck\w*|gähn\w*|"
                    r"gaehn\w*|hallo|guten\s+(?:morgen|tag|abend)|gute\s+nacht|greet\w*|good\s+(?:morning|evening|night)|hello|"
                    r"wish\w*|thank\w*|smil\w*|laugh\w*|nod\w*|wav(?:e|es|ing)|hug\w*|eat\w*|drink\w*|breakfast\w*|unpack\w*|"
                    r"sit\s+down|sits\s+down|stretch\w*|yawn\w*)(?!\w)")
ALLTAG_NICHT = ("trank", "pilz", "beere", "brunnen", "quelle", "flasche", "phiole", "gift", "fremd", "unbekannt", "seltsam",
                "potion", "mushroom", "berr", "well", "vial", "flask", "poison", "strange", "unknown")   # what one eats or drinks at a risk
TEILE = re.compile(r"(?i)\s*(?:,|;|\.|!|\?|\bund\b|\bdann\b|\band\b|\bthen\b)\s*")

# Review 27.10. Paket 6 (E2, E13): what the player typed, by fixed word lists, never the model's words. Buying, selling
# and resting go only over the panel's buttons: a fixed line to the seat and the fact nicht_erfolgt for the narrator;
# gold typed to a person of the scene goes over for real (typed_seen, typed_apply); plain going, buying and resting
# need no check. Since Vorschlag 7 they stand here (one module, one order).
KAUF = re.compile(r"(?i)(?<!\w)(?:(?:ein|ab)?kauf(?:e|en|st|t|te|ten)?|erwerb(?:e|en)?|bezahl(?:e|en|st|t)?|buy|buys|buying|bought|purchas\w*|pay|pays|paying|paid)(?!\w)")
VERKAUF = re.compile(r"(?i)(?<!\w)(?:verkauf(?:e|en|st|t|te|ten)?|sell|sells|selling|sold)(?!\w)")
RAST = re.compile(r"(?i)(?<!\w)(?:rast(?:e|en|et|est)?|ruh(?:e|en|t)\s+(?:\w+\s+){0,2}aus|ausruh\w*|schlaf(?:e|en|t)?|übernacht\w*|uebernacht\w*|"
                  r"schlag(?:e|en|t)?\s+(?:\w+\s+){0,2}lager|rest|rests|resting|sleep|sleeps|make\s+camp|camp)(?!\w)")
MEHR_ALS_GEHEN = re.compile(r"(?i)(?<!\w)(?:such|durchsuch|untersuch|öffn|oeffn|nimm|nehm|greif|pack|heb|lies|les|prüf|pruef|knack|brech|"
                            r"stiehl|stehl|klau|schlag|hau|kämpf|kaempf|wirk|zauber|frag|sprech|sprich|red|beobacht|lausch|horch|spür|spuer|"
                            r"search|open|take|grab|read|examine|steal|attack|fight|cast|ask|talk|listen|watch|track)")

# the action's words that ask or talk (Dominik 2026-10-25 „ich frage nach dem keller - es geht nach oben!?“), not „frage mich“
FRAGT = re.compile(r"(?i)\b(frag(e|en|t|st)?|bitte(n|t|st)?|sag(e|en|t|st)?|erzähl(e|en|t|st)?|rede(n|t)?|sprech(e|en)|sprich(st|t)?|"
                   r"überred\w*|verhandl\w*|verhandel\w*|erkundig\w*|ask(s|ed)?|tell(s)?|talk(s|ed)?|speak(s)?|persuad\w*|enquir\w*|inquir\w*)\b")
SICH = re.compile(r"(?i)\b(frag(e|t|st)\s+(mich|sich|dich)|wonder)")

# the value of a check by the player's own words (Review 27.10. Paket 9, G23: „ich klettere“ is never a check on Charisma)
WERTE = (("charisma", r"sprech|sprich|frag|überred|ueberred|bitt|verhandel|talk|ask|persuade|bargain|beg"),
         ("geschick", r"schleich|kletter|versteck|knack|spring|sneak|climb|hide|pick|jump"),
         ("intelligenz", r"untersuch|such|prüf|pruef|lies|les|entziffer|examine|search|inspect|read|study"),
         ("weisheit", r"lausch|beobacht|späh|spaeh|spür|spuer|listen|watch|track|spot"),
         ("staerke", r"brech|heb|stemm|drück|drueck|zieh|break|lift|force|push|pull"))


def _fragt(low):
    return bool(FRAGT.search(low)) and not SICH.search(low) and not any(x in low for x in RISIKO)


def _alltag(low):
    teile = [x for x in TEILE.split(low) if x.strip()]
    return bool(teile) and all(ALLTAG.search(x) for x in teile) and not any(x in low for x in RISIKO + ALLTAG_NICHT)


def kind(text):
    """The one kind of an action by the fixed order (ARTEN), "" for none: NICHT_ANGRIFF is taken out first."""
    raw = str(text or "")
    low = raw.lower()
    if not low.strip():
        return ""
    t = NICHT_ANGRIFF.sub(" ", raw)
    for k, rx, s in (("angriff", ANGRIFF_WORTE, t), ("bezug", BEZUG_WORTE, t), ("flucht", FLUCHT_WORTE, raw), ("frieden", FRIEDEN_WORTE, t)):
        if rx.search(s):
            return k
    if _alltag(low):
        return "alltag"
    if _fragt(low):
        return "frage"
    for k, rx in (("verkauf", VERKAUF), ("kauf", KAUF), ("rast", RAST)):
        if rx.search(low):
            return k
    if GEHEN.search(low) and not any(x in low for x in RISIKO) and not MEHR_ALS_GEHEN.search(low):
        return "gehen"
    return ""


def fight(text):
    """What an action does in a fight: "angriff" (attacks on its own), "bezug" (attacks a foe it names), "flucht"
    (runs away), "frieden" (asks for peace) or ""."""
    k = kind(text)
    return k if k in KAMPF else ""


def asks(text):
    """An action that only asks or talks (kind frage), or asks for peace in words of FRAGT („Lasst uns verhandeln“)."""
    k = kind(text)
    return k == "frage" or k == "frieden" and _fragt(str(text or "").lower())


def typed(text):
    """What a typed action does that the panel carries out or answers itself: "verkauf", "kauf", "rast", "gehen" or ""."""
    k = kind(text)
    return k if k in GETIPPT else ""


def everyday(text):
    """Whether an action is only everyday acts (ALLTAG, every part of it) without a word of RISIKO: no check."""
    return kind(text) == "alltag"


def just_going(wofuer):
    """A check the model asked for only for going somewhere (its wofuer: GEHEN without RISIKO): no roll."""
    low = (wofuer or "").lower()
    return bool(GEHEN.search(low)) and not any(x in low for x in RISIKO)


def values(text):
    """The values of a check the action's words name (WERTE), in the table's order; [] for none."""
    low = str(text or "").lower()
    return [w for w, rx in WERTE if re.search(r"(?<!\w)(?:" + rx + r")", low)]
