"""Stoppwörter: when a whole sentence ends the talk („Stopp“, „Hör auf“, „Tschüss“, „Danke, das war's“).

One fixed rule for every client (Dominik 2026-11-10, Paket „Abbrechen heißt aus“, decision 2a), never the model:
- stopp: the answer ends, nothing goes to the language model, the microphone closes (STOPP)
- tschuess: a goodbye ends the talk the same way; on a phone call the Spark says „Tschüss!“ and hangs up (BYE)
- no_more: right after the Spark's own „Noch etwas?“ on a call also a plain no (NO_MORE)
- abbruch: „Vergiss es“, „Lass es“ call a wish off (intent.cancel, klaeren): the model answers without any tool

The word lists live only here (Regel 12): chat_turn (web, apps, Begleiter, Telegram, Siri), /api/test/asr and
/api/desk/hear (wake word), esp32 (also while it speaks), telefon, zwischenruf (Ins Wort fallen) and room (Raum-Modus,
as the start of a sentence). Only whole sentences count, so „Stopp die Musik“ or „Halt, wie spät ist es?“ stay
questions. Nothing here logs or keeps the words."""
import re

# the wake word or a listening word may stand in front: „Spark, stopp“, „Okay, hör auf“
_LEAD = r"(?:(?:hey|ok|okay|oh|ach|ja|nein|nee|mhm|danke)\W+)*(?:(?:jarvis|spark|computer)\W+)?"
_TAIL = r"(?:\W+(?:bitte|jetzt|sofort|danke|jarvis|spark|computer|stopp?))*\W*"
# shared with ABBRUCH below: these also call a wish off
_BOTH = r"schon gut|abbrechen|cancel"
STOPP = (r"stopp?|halt|ruhe|still|sei (?:jetzt )?(?:bitte )?still|psst+|pst|hör (?:jetzt )?(?:bitte )?auf|aufhören|abbruch|"
         r"genug|(?:danke,? )?(?:das |es )?(?:reicht|genügt)(?: jetzt)?|nicht jetzt|jetzt nicht|(?:halt die )?klappe|"
         r"stop it|enough|that'?s enough|be quiet|quiet|shut up|" + _BOTH)
_STOP = re.compile(r"(?i)^\W*" + _LEAD + r"(?:" + STOPP + r")" + _TAIL + r"$")
_STARTS = re.compile(r"(?i)^\W*(?:(?:hey\W+)?(?:jarvis|spark|computer)\W+)?(?:" + STOPP + r")\b")
# a goodbye; the greetings only end a phone call („Gute Nacht“ elsewhere may be the smart home's evening wish)
_BYE_LEAD = (r"(?:(?:ok|okay|gut|alles klar|prima|super|perfekt|dann|nein|nee|danke|danke schön|dankeschön|danke dir|"
             r"danke sehr|vielen dank|merci)\W+)*")
BYE = (r"tschüss|tschüs|tschau|ciao|servus|auf wiederhören|auf wiedersehen|bis dann|bis später|bis bald|"
       r"(?:du kannst|ich|ich lege?|ich leg) (?:jetzt )?auf(?:legen)?|leg (?:jetzt )?auf|auflegen|das war'?s|das wars|"
       r"das war es|das war alles|das ist alles|nichts mehr|nichts weiter|ende|schluss|bye|bye bye|goodbye|"
       r"that'?s all|that'?s it")
GREET = r"bis morgen|gute nacht|schönen tag noch|schönen abend noch"
_BYE_TAIL = r"(?:\W+(?:danke|danke schön|dir auch|spark|für heute|erstmal|tschüss|tschüs|ciao|bye))*\W*$"
_BYE = re.compile(r"(?i)^\W*" + _BYE_LEAD + r"(?:" + BYE + r")" + _BYE_TAIL)
_BYE_CALL = re.compile(r"(?i)^\W*" + _BYE_LEAD + r"(?:" + BYE + "|" + GREET + r")" + _BYE_TAIL)
_NO_MORE = re.compile(r"(?i)^\W*(?:nein|nee|ne|nö|nope|no|nichts|danke|passt|passt so|alles gut|das reicht|reicht)"
                      r"(?:\W+(?:danke|danke schön|vielen dank|thanks|passt|alles gut|das reicht|reicht|spark))*\W*$")
# „Vergiss es“: the wish is called off (intent.cancel, klaeren._none); the answer comes without any tool
ABBRUCH = (r"vergiss es|vergiss das( ganze)?|lass es( lieber)?|lass das( lieber)?|lass mal|lass gut sein|"
           r"nein,? doch nicht|doch nicht|egal|nicht so wichtig|never ?mind|forget it|forget about it|"
           r"cancel( that| it)|skip it|" + _BOTH)
KINDS = ("stopp", "tschuess")
MAX = 200   # a longer text is never only a stop word


def _cut(text):
    return str(text or "")[:MAX]


def stop(text):
    """The whole sentence says stop („Stopp“, „Spark, hör auf“, „Danke, das reicht“)."""
    return bool(_STOP.match(_cut(text)))


def starts(text):
    """The sentence begins with a stop word („Stopp, das stimmt nicht“): only for room mode while it speaks."""
    return bool(_STARTS.match(_cut(text)))


def bye(text, call=False):
    """The whole sentence says goodbye („Tschüss“, „Danke, das war's“); call: also „Gute Nacht“ and the like."""
    return bool((_BYE_CALL if call else _BYE).match(_cut(text)))


def no_more(text):
    """Right after „Noch etwas?“: a plain no („Nein danke“, „Passt“)."""
    return bool(_NO_MORE.match(_cut(text)))


def ende(text, call=False):
    """"stopp", "tschuess" or "": whether the whole sentence ends the talk (stop words before goodbyes)."""
    return "stopp" if stop(text) else "tschuess" if bye(text, call) else ""
