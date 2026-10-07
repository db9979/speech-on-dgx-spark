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


def clean_text(text, calm=False):
    t = ACTION.sub(" ", str(text))
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
    return re.sub(r"\s*\n\s*", "\n", t).strip()


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
