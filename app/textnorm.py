"""Text clean-up before speech synthesis.

Chat replies carry emojis, markdown and "haha"; the model reads those as cues and laughs,
speeds up or switches tone (config tts.clean_text). Digits are another weak spot: the model
guesses how to read "05.10.2026", "14:30", "3,5 %" or a phone number and often gets it
wrong, so numbers are written out as words first (config tts.numbers):

  off     leave numbers alone
  words   dates, times, money, percent, decimals, years and ordinals as words; phone
          numbers and long digit strings in blocks of two
  blocks  like words, but every number with 3 or more digits in blocks of two
  digits  like words, but every number with 3 or more digits digit by digit

Dates, times, money and decimals are always read as words unless the mode is off.
German and English are supported; other languages only get the clean-up.
"""
import re

try:
    from num2words import num2words
except ImportError:  # installed by install.sh; without it numbers stay as they are
    num2words = None

NUMBER_MODES = ("off", "words", "blocks", "digits")

EMOJI = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0000FE0F\U0000200D\U00002B00-\U00002BFF]+")
LAUGH = re.compile(r"(?i)(?<!\w)(?:(?:ha|he|hi|hö){2,}h?|lol|lmao|rofl|xd|:-?[)(dp]|;-?\))(?!\w)[!.]*")
ACTION = re.compile(r"(?i)[*(\[](?:lacht|lach|kichert|grinst|schmunzelt|zwinkert|seufzt|laughs?|giggles?|grins?|winks?|smiles?)[^*)\]]{0,30}[*)\]]")
MONTHS_DE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September",
             "Oktober", "November", "Dezember"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
             "October", "November", "December"]
MONTH_DE = r"(?:Jan(?:uar)?|Feb(?:ruar)?|März|Mär|Apr(?:il)?|Mai|Juni?|Juli?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Okt(?:ober)?|Nov(?:ember)?|Dez(?:ember)?)\.?"


# Exclamations and interjections make the model act out emotion; calm mode flattens them.
INTERJECTION = re.compile(r"(?im)(^|(?<=[.!?:]) )(?:oh je|ohje|oje|na ja|oh+|ah+|aha|ach|hach|wow|hm+|uff|juhu|yay|hurra|whoa|ooh|yeah|tja)\b[,!.…]*\s+(?=\w)")


def calm_text(t):
    t = INTERJECTION.sub(r"\1", t)
    t = re.sub(r"(?:!+\?|\?!+)", "?", t)            # "?!" -> "?"
    t = t.replace("!", ".").replace("\u2026", ".")     # "!" and "…" -> "."
    t = re.sub(r"\.(?:\s*\.)+", ".", t)
    return t


MAX_INPUT = 20000  # characters per request; longer texts are refused by the speech services


def clean_text(text, calm=False):
    # runs of white space first: thousands of empty lines would make the patterns below slow
    t = re.sub(r"\s{2,}", lambda m: "\n" if "\n" in m.group() else " ", str(text))
    t = ACTION.sub(" ", t)
    t = EMOJI.sub(" ", t)
    t = LAUGH.sub(" ", t)
    t = re.sub(r"```.*?```", " ", t, flags=re.S)       # code blocks are not speakable
    t = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", t)    # [text](url) -> text
    t = re.sub(r"https?://\S+", " ", t)
    # headings, bullets, quotes, numbered lists (but not "5. Oktober")
    t = re.sub(r"^\s{0,3}(?:#{1,6}|[-*+>]|\d+\.(?!\s*" + MONTH_DE + r"))\s+", "", t, flags=re.M)
    t = re.sub(r"[*_`~#|]+", "", t)
    t = re.sub(r"([!?.])\1+", r"\1", t)                # "!!!" -> "!"
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\s+([,;:.!?])", r"\1", t)             # "witzig ," -> "witzig,"
    t = re.sub(r"(^|\n)[\s,;:.!?]+", r"\1", t)          # leftovers at line starts
    if calm:
        t = calm_text(t)
    t = re.sub(r"\s*\n\s*", "\n", t).strip()
    # A line without a closing mark (list items, headings, the last words of an answer) is spoken
    # with rising pitch, as if more were to come; a full stop lets the voice settle.
    return re.sub(r"(?m)([\w%)\]\"“”»'])$", r"\1.", t)


# Passwords, code words, one-time codes and keys are never spoken (fixed rule, no switch): a
# speaker in the room, the car or Siri would say them to everyone nearby. The written answer keeps
# them; only the voice says "nur schriftlich sichtbar" instead. Runs in both speech services on
# every request, whatever clean_text says, so every path (chat, speaker, Telegram voice, Wyoming,
# reminders) is covered.
SECRET_HINT = {"de": "nur schriftlich sichtbar", "en": "shown in writing only"}
SECRET_WORD = (r"(?:\w+-)*(?:\w*(?:passw(?:ort|örter|ord)|kennw(?:ort|örter)|codew(?:ort|örter)|zugangsdaten|"
               r"passphrase|passcode|geheimzahl|schlüssel|token|secret)\w*|\w*codes?|(?:pin|tan|otp|key)s?)(?!\w)")
# the value after "Passwort ... ist/lautet/:" (up to six words in between: "für das Gäste-WLAN")
SECRET_SAID = re.compile(r"(?i)(?<!\w)(" + SECRET_WORD + r"(?:[ \t]+[^\s.,;:!?=]+){0,6}?[ \t]*"
                         r"(?:(?<!\w)(ist|lautet|lauten|heißt|heissen|heißen|sind|is|are|reads)(?!\w)[ \t]*:?|[:=]))[ \t]*"
                         r"([^\n]*)")
# "PIN 1234", "Code 482 913", "Token ab12cd34": a value with a digit right after the word
SECRET_NEXT = re.compile(r"(?i)(?<!\w)(" + SECRET_WORD + r"[ \t]+)((?=[^\s]*\d)[^\s,;!?]*[^\s,;!?.:](?:[ -]\d{2,4}(?!\w))*)")
SECRET_TOKEN = re.compile(r"(?<![\w/+=-])(?:"
                          r"(?:sk|pk|rk)-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_\w{20,}|"
                          r"xox[abpr]-[A-Za-z0-9-]{10,}|AKIA[A-Z0-9]{12,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9._-]{10,}|"
                          r"otpauth://\S+|-----BEGIN[^-]{0,40}-----.*?(?:-----END[^-]{0,40}-----|$)|"
                          r"[A-Za-z0-9_+/=]{16,})(?![\w/+=-])", re.S)
# words after "ist" that describe the password instead of being it ("ist falsch", "ist im Tresor")
NOT_A_SECRET = set("""falsch richtig korrekt sicher unsicher schwach stark neu alt leer gültig ungültig bekannt unbekannt
geheim privat noch schon jetzt leider bereits nur auch sehr zu nicht kein keine keiner keinen nie immer gleich
lang kurz abgelaufen erforderlich nötig notwendig optional aktiv inaktiv da weg hier dort dabei drin vorhanden
im in am an auf bei unter über für mit ohne aus von vom zum zur nach vor seit bis ein eine einer einen der die das
dein deine deinen dein mein meine sein seine ihr ihre dasselbe derselbe dieselbe es er sie wie was wo
not no wrong right correct incorrect safe unsafe weak strong new old empty valid invalid known unknown secret
private still already now only also very too never always the a an your my his her its in on at for with without
from of to by under required needed missing set saved stored expired active inactive there here""".split())


def _secret_token(tok):
    if re.match(r"(?:sk|pk|rk)-|gh[pousr]_|github_pat_|xox|AKIA|eyJ|otpauth:|-----BEGIN", tok):
        return True
    digits, letters = sum(c.isdigit() for c in tok), sum(c.isalpha() for c in tok)
    mixed = any(c.islower() for c in tok) and any(c.isupper() for c in tok)
    # keys and hashes: letters and digits mixed; long uppercase numbers (parcels) stay
    return digits >= 3 and letters >= 3 and (mixed or len(tok) >= 24)


def _clause(value):
    """The spoken value up to the end of its clause: ", " "; " or a full stop before a space; a value
    spelled out letter by letter ("S, o, n, n, e") as a whole."""
    spelled = re.match(r"(?:[^\s,;]{1,2}(?:\s*[,-]\s*|\s+)){3,}[^\s,;.!?]{1,2}(?![^\s,;.!?])", value)
    if spelled:
        return value[:spelled.end()], value[spelled.end():], True
    m = re.search(r"[,;!?](?:\s|$)|\.(?:\s|$)", value)
    return (value[:m.start()], value[m.start():], False) if m else (value, "", False)


def hide_secrets(text, language=None):
    """The text with passwords, code words, one-time codes and keys replaced by a short hint."""
    t = str(text)
    lang = number_language(language, t) or "de"
    hint = SECRET_HINT.get(lang, SECRET_HINT["de"])

    def said(m):
        lead, conn, rest = m.group(1), m.group(2), m.group(3)
        q = re.match(r"\s*([„“\"'`«»‚‘])", rest)
        if q:  # quoted: everything up to the closing quote
            end = re.search(r"[“”\"'`«»‘’]", rest[q.end():])
            tail = rest[q.end() + end.end():] if end else ""
            return lead.rstrip() + " " + hint + tail
        value, tail, spelled = _clause(rest)
        first = value.strip().split(" ")[0].strip("()[]").lower() if value.strip() else ""
        if not first:
            return m.group(0)
        weak = conn is not None and conn.lower() in ("ist", "sind", "is", "are")
        if weak and not spelled and not re.search(r"\d|[^\w\s]", value.split(" ")[0]) and (
                first in NOT_A_SECRET or re.fullmatch(r"ge\w+(?:t|en)|\w+(?:iert|lich|ig|bar)", first)):
            return m.group(0)
        return lead.rstrip() + " " + hint + tail

    t = SECRET_SAID.sub(said, t)
    t = SECRET_NEXT.sub(lambda m: m.group(1) + hint, t)
    t = SECRET_TOKEN.sub(lambda m: hint if _secret_token(m.group(0)) else m.group(0), t)
    return t


def parse_pronunciations(text):
    """Lines like "DGX = De Ge Ix" (also "->" or "→") -> [(pattern, replacement)], longest first."""
    rules = []
    for line in str(text or "").splitlines():
        m = re.match(r"\s*(.+?)\s*(?:=|->|→)\s*(.*?)\s*$", line)
        if m and m.group(1) and not line.lstrip().startswith("#"):
            rules.append((m.group(1), m.group(2)))
    rules.sort(key=lambda r: -len(r[0]))
    return [(re.compile(r"(?<!\w)" + re.escape(a) + r"(?!\w)", re.I), b) for a, b in rules]


def apply_pronunciations(text, rules):
    for pat, rep in rules:
        text = pat.sub(lambda _: rep, text)
    return text


GERMAN_HINT = re.compile(r"(?i)\b(der|die|das|und|ist|nicht|ich|wir|sie|mit|für|auf|ein|eine|auch|uhr)\b|[äöüß]")
ENGLISH_HINT = re.compile(r"(?i)\b(the|and|is|not|you|we|with|for|on|a|an|also|this|that)\b")


def number_language(language, text):
    """'de', 'en' or None (leave numbers alone) from the request language or the text."""
    lang = str(language or "").strip().lower()
    if lang in ("german", "de", "deutsch"):
        return "de"
    if lang in ("english", "en"):
        return "en"
    if lang not in ("", "auto"):
        return None
    de, en = len(GERMAN_HINT.findall(text)), len(ENGLISH_HINT.findall(text))
    return "de" if de >= en else "en"


def guess_language(text):
    """'German', 'English' or None when the text does not clearly show one of them.
    With language "Auto" the model guesses per request, so one English word ("Feedback")
    can switch accent and tone in the middle of an answer."""
    de, en = len(GERMAN_HINT.findall(text)), len(ENGLISH_HINT.findall(text))
    if de >= 2 and de > 2 * en:
        return "German"
    if en >= 2 and en > 2 * de:
        return "English"
    return None


class Speaker:
    def __init__(self, lang, mode):
        self.lang, self.mode = lang, mode

    def w(self, n, to="cardinal"):
        return num2words(n, lang=self.lang, to=to)

    def year(self, y):
        y = int(y)
        return self.w(y, "year") if 1100 <= y <= 2099 else self.w(y)

    def digits(self, s):
        return " ".join(self.w(int(c)) for c in s)

    def blocks(self, s):
        """'01711234567' -> 'null eins siebzehn elf dreiundzwanzig ...' (leading zeros singly,
        then pairs; an odd length starts with a single digit)."""
        out = []
        zeros = len(s) - len(s.lstrip("0"))
        out += [self.w(0)] * zeros
        rest = s[zeros:]
        if len(rest) % 2:
            out.append(self.w(int(rest[0])))
            rest = rest[1:]
        out += [self.w(int(rest[i:i + 2])) if rest[i] != "0" else self.digits(rest[i:i + 2])
                for i in range(0, len(rest), 2)]
        return " ".join(out)

    def integer(self, s):
        """A plain integer as the mode wants it."""
        s = s.lstrip("+")
        if len(s) >= 3 and self.mode == "digits":
            return self.digits(s)
        if len(s) >= 3 and self.mode == "blocks" or s.startswith("0") and len(s) > 1 or len(s) >= 8:
            return self.blocks(s)
        return self.w(int(s))

    def decimal(self, whole, frac):
        sep = " Komma " if self.lang == "de" else " point "
        return self.w(int(whole)) + sep + self.digits(frac)

    def ordinal(self, n, dative=False):
        o = self.w(int(n), "ordinal")
        return o + "n" if self.lang == "de" and dative and o.endswith("e") else o


def speak_numbers(text, language, mode="words"):
    """Write numbers out as words in German or English, see the module docstring."""
    if mode not in NUMBER_MODES or mode == "off" or num2words is None or not re.search(r"\d", text):
        return text
    lang = number_language(language, text)
    if lang is None:
        return text
    sp = Speaker(lang, mode)
    de = lang == "de"
    t = text
    THOU, DEC = (r"\.", ",") if de else (",", r"\.")

    def sub(pattern, fn, flags=0):
        """Replace matches with fn(match) padded by spaces; fn returns None to keep a match."""
        nonlocal t

        def repl(m):
            out = fn(m)
            return m.group(0) if out is None else f" {out} "
        t = re.sub(pattern, repl, t, flags=flags)

    dative_before = r"(?:\b(?i:am|vom|zum|beim|im|ab|bis|seit|dem|den)\s+)"

    # Phone numbers: +49 171 1234567, 0171/1234567, (030) 123 456-78 -> blocks with pauses
    def phone(m):
        raw = m.group(0)
        if len(re.sub(r"\D", "", raw)) < 7:
            return None
        parts = re.findall(r"\d+", raw)
        head = ("plus " if de else "plus ") if raw.lstrip().startswith("+") else ""
        return head + ", ".join(sp.digits(p) if mode == "digits" else sp.blocks(p) for p in parts)
    sub(r"(?<![\w.,])(?:\+\d{1,3}[\s/-]?)?\(?0\d{1,5}\)?(?:[\s/-]?\d{2,}){1,4}(?![\w.,]\d)", phone)
    sub(r"(?<![\w.,])\+\d{1,3}(?:[\s/-]?\d{2,}){2,5}(?![\w.,]\d)", phone)

    # ISO dates 2026-10-05
    def iso(m):
        y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
        if not (1 <= mo <= 12 and 1 <= d <= 31):
            return None
        if de:
            return f"{sp.ordinal(d, True)} {MONTHS_DE[mo - 1]} {sp.year(y)}"
        return f"{MONTHS_EN[mo - 1]} {sp.ordinal(d)}, {sp.year(y)}"
    sub(r"\b(\d{4})-(\d{2})-(\d{2})\b", iso)

    if de:
        # 05.10.2026 / 5.10. / 5. Oktober 2026
        def dmy(m):
            d, mo, y = int(m.group(2)), int(m.group(3)), m.group(4)
            if not (1 <= mo <= 12 and 1 <= d <= 31):
                return None
            pre = m.group(1) or ""
            out = f"{pre}{sp.ordinal(d, bool(pre))} {MONTHS_DE[mo - 1]}"
            return out + (f" {sp.year(y if len(y) == 4 else '20' + y)}" if y else "")
        sub(r"(" + dative_before + r")?\b(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2}(?!\d))?(?![\d,])", dmy)

        def dmonth(m):
            pre = m.group(1) or ""
            name = next(x for x in MONTHS_DE if x.lower().startswith(m.group(3).rstrip(".").lower()[:3]))
            y = m.group(4)
            return f"{pre}{sp.ordinal(m.group(2), bool(pre))} {name}" + (f" {sp.year(y)}" if y else "")
        sub(r"(" + dative_before + r")?\b(\d{1,2})\.\s*(" + MONTH_DE + r")(?:\s+(\d{4}))?", dmonth)
        # "der 3. Platz", "am 2. Tag": ordinals after an article or preposition
        sub(r"(\b(?i:der|die|das|den|dem|des|am|im|zum|zur|vom|beim)\s+)(\d{1,3})\.(?=\s+[A-ZÄÖÜ])",
            lambda m: m.group(1) + sp.ordinal(m.group(2), m.group(1).strip().lower() in
                                               ("den", "dem", "des", "am", "im", "zum", "zur", "vom", "beim")))
    else:
        # October 5, 2026 / 5 October 2026 keep their words; 1st, 2nd -> first, second
        sub(r"\b(\d+)(?:st|nd|rd|th)\b", lambda m: sp.ordinal(m.group(1)))

    # Times 14:30, 9:05 Uhr, 14.30 Uhr
    def clock(m):
        h, mi = int(m.group(1)), int(m.group(2))
        if h > 24 or mi > 59:
            return None
        if de:
            return f"{sp.w(h)} Uhr" + (f" {sp.w(mi)}" if mi else "")
        if mi == 0:
            return f"{sp.w(h)} o'clock"
        return f"{sp.w(h)} " + (f"oh {sp.w(mi)}" if mi < 10 else sp.w(mi))
    sub(r"\b(\d{1,2}):(\d{2})(?:\s*(?:Uhr|h)\b)?(?!:\d)", clock)
    if de:
        sub(r"\b(\d{1,2})\.(\d{2})\s*Uhr\b", clock)

    # Money: 12,50 €, €12.50, 12 EUR, $5, 1.200 Euro
    CUR = {"€": "EUR", "eur": "EUR", "euro": "EUR", "$": "USD", "usd": "USD", "dollar": "USD",
           "£": "GBP", "gbp": "GBP", "chf": "CHF"}
    amount = r"(?P<whole>\d{1,3}(?:" + THOU + r"\d{3})+|\d+)(?:" + DEC + r"(?P<cents>\d{1,2}))?(?!\d)"

    NAMES = {"EUR": ("Euro", "euro", "euros"), "USD": ("Dollar", "dollar", "dollars"),
             "GBP": ("Pfund", "pound", "pounds"), "CHF": ("Franken", "franc", "francs")}

    def money(m):
        """'12,50 €' -> 'zwölf Euro fünfzig' / 'twelve euros fifty'."""
        g = m.groupdict()
        cur = CUR.get((g.get("pre") or g.get("post") or "").lower().rstrip("s"), "EUR")
        whole = int(re.sub(r"\D", "", g["whole"]))
        cents = int((g["cents"] or "0").ljust(2, "0"))
        de_name, one, many = NAMES[cur]
        name = de_name if de else (one if whole == 1 else many)
        return f"{sp.w(whole)} {name}" + (f" {sp.w(cents)}" if cents else "")
    sub(r"(?<![\w.,])(?P<pre>€|\$|£|EUR|USD|GBP|CHF)\s?" + amount, money, re.I)
    sub(r"(?<![\w.,])" + amount + r"\s?(?P<post>€|\$|£|EUR\b|USD\b|GBP\b|CHF\b|Euro\b|Dollars?\b)", money, re.I)

    # Version numbers and other dotted numbers that are no thousands: 3.14 -> drei Punkt vierzehn
    if de:
        sub(r"(?<![\w.,])\d+(?:\.\d+)+(?![\w,]|\.\d)",
            lambda m: None if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", m.group(0))
            else " Punkt ".join(sp.integer(p) for p in m.group(0).split(".")))
    else:
        sub(r"(?<![\w.,])\d+(?:\.\d+){2,}(?![\w,]|\.\d)",
            lambda m: " point ".join(sp.integer(p) for p in m.group(0).split(".")))

    # Percent, degrees, ranges, signs, decimals, thousands, years, plain integers
    def number(m):
        sign, whole, frac = m.group(1) or "", m.group(2), m.group(3)
        digits = re.sub(r"\D", "", whole)
        if frac is not None:
            out = sp.decimal(digits, frac)
        elif not re.search(THOU, whole) and len(digits) == 4 and 1100 <= int(digits) <= 2099 and mode == "words":
            out = sp.year(digits)
        elif re.search(THOU, whole):
            out = sp.w(int(digits))  # 1.000.000 is clearly an amount, never blocks
        else:
            out = sp.integer(digits)
        return ("minus " if sign in ("-", "−") else "") + out
    unit = {"%": (" Prozent", " percent"), "‰": (" Promille", " per mille"),
            "°C": (" Grad Celsius", " degrees Celsius"), "°F": (" Grad Fahrenheit", " degrees Fahrenheit"),
            "°": (" Grad", " degrees")}
    n_re = r"(?<![\w.,])([-−]?)(\d{1,3}(?:" + THOU + r"\d{3})+|\d+)(?:" + DEC + r"(\d+))?"
    for u, (ude, uen) in unit.items():
        sub(n_re + r"\s?" + re.escape(u), lambda m, s=(ude if de else uen): number(m) + s)
    # ranges 3-5, 10–12 Uhr
    sub(r"(?<![\w.,-])(\d+)\s?[-–]\s?(\d+)(?![\w.,]?\d)",
        lambda m: f"{sp.integer(m.group(1))} {'bis' if de else 'to'} {sp.integer(m.group(2))}")
    sub(n_re + r"(?![\d])", number)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\s+([,;:.!?])", r"\1", t)
    return t.strip()
