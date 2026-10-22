"""Rechnen mit festem Werkzeug (Dominik 2026-10-22): a language model cannot calculate, so the panel does it.

One core, used three ways, never eval, exec, sympy or any foreign calculator (huhabla/calculator-mcp-server was looked
at and turned down: eval with empty builtins, sympify, no limits):

- calc(text): an own small parser (tokens, then recursive descent) for numbers, + - × ÷, powers, brackets, percent
  ("19 % von 249", "249 plus 19 %"), the square root and pi, written with digits or German and English words ("drei
  Komma fünf" stays with the model; "3,5 mal 2", "17 geteilt durch 4", "Klammer auf"). Decimal, not float, so
  0,1 + 0,2 is 0,3. Hard limits: MAX_CHARS, MAX_TOKENS, MAX_DEPTH, MAX_EXP, MAX_ABS; anything else is an error word.
- days(): date arithmetic by fixed rules (days until, days between, the weekday of a day, the date in n days).
- the tool `rechnen` for the model (admin switch chat.rechnen, Funktionen → Rechnen mit festem Werkzeug, off): the
  model only writes the expression or the dates, the panel computes and the result is the panel's own words. Offered
  only when the person's own words ask for a calculation (WORDS), next to whatever the Weiche picked (extras "keep",
  werkzeug_abdeckung.BY_WORD); never guests, never another voice, never over MCP. Reads nothing, changes nothing
  (chat.INSIDE).
- fix(): Antwort-Prüfung for sums, same switch: a sentence the model writes with a calculation and its result
  ("17 mal 23 ist 381") is computed again before it is shown or said, and a wrong result is replaced by the right one.
- sofort.py takes calc() and the date questions for its fixed sentences without the model (switch chat.sofort).

Logs: "rechnen: <art> ok|fehler <word>" and "chat: answer check: rechnung korrigiert", fixed words only.
"""
import datetime
import decimal
import re

import features

MAX_CHARS = 200        # longer expressions are refused
MAX_TOKENS = 80
MAX_DEPTH = 12         # brackets, roots and signs inside each other
MAX_EXP = 100          # the largest power
MAX_ABS = decimal.Decimal(10) ** 15   # no step may grow beyond this
MAX_DAYS = 36600       # about 100 years either way
PLACES = 10            # decimal places in a tool result
D = decimal.Decimal
PI = D("3.14159265358979323846264338327950288")

WORDS = re.compile(r"(?i)\b(rechne\w*|berechne\w*|ausrechn\w*|ausgerechnet|kalkulier\w*|calculat\w*|compute|"
                   r"plus|minus|mal|geteilt|dividiert|multipliziert|hoch|wurzel|prozent|percent|times|divided|"
                   r"summe|differenz|produkt|quotient|ergibt|zinse?n?|rabatt|mehrwertsteuer|mwst|brutto|netto|"
                   r"wie ?viele? tage|how many days|wochentag|day of the week|in \d+ (?:tagen|wochen|days|weeks))\b"
                   r"|\d\s*(?:[-+*/×÷^%]|x\s*\d)")
ARTEN = ("zahl", "tage_bis", "tage_zwischen", "wochentag", "datum_plus")
TOOL = {"type": "function", "function": {
    "name": "rechnen",
    "description": "Exact calculation by the panel. art=zahl: 'ausdruck' with numbers, + - * / ^, brackets, % "
                   "('19 % von 249', '249 + 19 %'), sqrt(), pi; decimal point '.', no thousands separators. "
                   "Dates (YYYY-MM-DD): art=tage_bis ('bis'), tage_zwischen ('von', 'bis'), wochentag ('datum'), "
                   "datum_plus ('von' optional, 'tage'). Say only the result of this tool, never your own figure.",
    "parameters": {"type": "object", "properties": {
        "art": {"type": "string", "enum": list(ARTEN), "description": "default zahl"},
        "ausdruck": {"type": "string", "description": "for zahl, e.g. (1200 - 200) * 19 %"},
        "von": {"type": "string", "description": "start date YYYY-MM-DD (default today)"},
        "bis": {"type": "string", "description": "end date YYYY-MM-DD"},
        "datum": {"type": "string", "description": "a date YYYY-MM-DD"},
        "tage": {"type": "integer", "description": "days to add, negative to go back"}}}}}
HINT = ("Für jede Rechnung, Prozent, Summe oder Datumsrechnung ruf rechnen und sag nur dessen Ergebnis, "
        "rechne nie selbst im Kopf.")
PREFIX = "Ergebnis vom Panel: "   # a tool result the answer check knows as the panel's own figure (answercheck.known)
# computes from the person's own words and the model's expression; reads nothing from outside (chat.INSIDE)
INSIDE = {"rechnen"}
WHY = {"leer": ("Da steht keine Rechnung.", "There is no calculation."),
       "lang": ("Die Rechnung ist zu lang.", "The calculation is too long."),
       "zeichen": ("Darin steht etwas, das keine Zahl und kein Rechenzeichen ist.",
                   "It holds something that is neither a number nor an operator."),
       "form": ("Die Rechnung ist nicht vollständig.", "The calculation is incomplete."),
       "null": ("Durch null lässt sich nicht teilen.", "Division by zero is not possible."),
       "gross": ("Das Ergebnis ist zu groß.", "The result is too large."),
       "hoch": ("Die Potenz ist zu groß oder nicht erlaubt.", "The power is too large or not allowed."),
       "wurzel": ("Aus einer negativen Zahl gibt es keine Wurzel.", "No square root of a negative number."),
       "prozent": ("„von“ braucht davor einen Prozentwert.", "\"of\" needs a percentage before it."),
       "datum": ("Das Datum verstehe ich nicht.", "I do not understand the date."),
       "tage": ("So viele Tage rechne ich nicht.", "That is too many days.")}
WEEKDAY = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
WEEKDAY_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTH = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November",
         "Dezember")
MONTH_EN = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
            "November", "December")
MONTHS = {m.lower(): i + 1 for i, m in enumerate(MONTH)}
MONTHS.update({m.lower(): i + 1 for i, m in enumerate(MONTH_EN)})
MONTHS.update({"maerz": 3, "jänner": 1, "jan": 1, "feb": 2, "mär": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
               "sep": 9, "sept": 9, "okt": 10, "oct": 10, "nov": 11, "dez": 12, "dec": 12})
FEAST = {"heiligabend": (12, 24), "weihnachten": (12, 24), "christmas eve": (12, 24), "christmas": (12, 25),
         "silvester": (12, 31), "new year's eve": (12, 31), "neujahr": (1, 1), "new year": (1, 1),
         "new year's day": (1, 1), "valentinstag": (2, 14), "valentine's day": (2, 14), "halloween": (10, 31),
         "nikolaus": (12, 6), "tag der deutschen einheit": (10, 3)}
_MON = "|".join(sorted(MONTHS, key=len, reverse=True))
_FEAST = "|".join(re.escape(f) for f in sorted(FEAST, key=len, reverse=True))
DAY = (r"(\d{4}-\d{2}-\d{2}|\d{1,2}\.\s?\d{1,2}\.(?:\s?\d{4}\b)?|\d{1,2}\.?\s+(?:" + _MON + r")\b(?:\s+\d{4}\b)?"
       r"|(?:" + _FEAST + r")|heute|morgen|today|tomorrow)")


class Fehler(ValueError):
    """A calculation the panel refuses; args[0] is a key of WHY."""


# --- the tokens: numbers, operators and the few words that mean one ---------------------------------------------

# longest first; German and English words a person or a model writes for an operator
_WORDS = [(r"geteilt\s+durch|dividiert\s+durch|divided\s+by|durch", "/"),
          (r"multipliziert\s+mit|multiplied\s+by|mal|times", "*"),
          (r"plus|und", "+"), (r"minus|weniger", "-"),
          (r"to\s+the\s+power\s+of|hoch", "^"), (r"prozent|percent|pct", "%"),
          (r"quadratwurzel\s+(?:aus|von)|wurzel\s+(?:aus|von)|square\s+root\s+of|sqrt|wurzel", "√"),
          (r"klammer\s+auf", "("), (r"klammer\s+zu", ")"), (r"von|of", "v"), (r"pi", "π")]
_WORD_RX = [(re.compile(r"(?<![a-zäöüß])(?:" + w + r")(?![a-zäöüß])"), s) for w, s in _WORDS]
_DROP = re.compile(r"(?:€|\$|£|eur(?:o|os)?\b|dollar\b|stück\b|gramm\b|kg\b|ist\s*$|ergibt\s*$|=\s*$|\?|!)")
_TOKEN = re.compile(r"\s*(?:(\d+(?:[.,]\d+)*)|(\*\*|[-+*/^%()√vπ×÷·:]))")


def number(s, en=False):
    """Decimal of a number as written: "1.234,5" (de), "1,234.5" (en), "3,5", "3.5"; one separator before exactly
    three digits is a thousands one in the person's language ("1.000" de, "1,000" en)."""
    if len(re.sub(r"\D", "", s)) > 20:
        raise Fehler("gross")
    dots, commas = s.count("."), s.count(",")
    if dots and commas:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
    elif dots + commas == 0:
        return D(s)
    else:
        sep = "." if dots else ","
        groups = s.split(sep)
        if len(groups) > 2 or (len(groups[1]) == 3 and sep == ("," if en else ".")):
            if any(len(g) != 3 for g in groups[1:]):
                raise Fehler("zeichen")
            return D("".join(groups))
        dec = sep
    whole, _, frac = s.rpartition(dec)
    return D(re.sub(r"\D", "", whole) + "." + frac)


def tokens(text, en=False):
    """[(kind, value)] of a calculation; kind "n" (Decimal) or an operator sign."""
    t = str(text or "").strip().lower()
    if not t:
        raise Fehler("leer")
    if len(t) > MAX_CHARS:
        raise Fehler("lang")
    for rx, sign in _WORD_RX:
        t = rx.sub(" " + sign + " ", t)
    t = re.sub(r"(?<=\d)\s*x\s*(?=\d)", " * ", t)
    t = t.replace("²", "^2").replace("³", "^3").replace("−", "-").replace("–", "-")
    t = _DROP.sub(" ", t).strip()
    out, pos = [], 0
    while pos < len(t):
        m = _TOKEN.match(t, pos)
        if not m:
            if t[pos:].strip():
                raise Fehler("zeichen")
            break
        pos = m.end()
        if m.group(1):
            out.append(("n", number(m.group(1), en)))
        else:
            sign = {"**": "^", "×": "*", "·": "*", "÷": "/", ":": "/"}.get(m.group(2), m.group(2))
            out.append((sign, None))
        if len(out) > MAX_TOKENS:
            raise Fehler("lang")
    if not out:
        raise Fehler("leer")
    return out


# --- the parser: recursive descent, every value checked against MAX_ABS ------------------------------------------

def _ctx():
    c = decimal.Context(prec=34, Emax=999999, Emin=-999999)
    c.traps[decimal.Inexact] = False
    return c


class _Parser:
    def __init__(self, toks):
        self.t, self.i, self.depth = toks, 0, 0

    def peek(self):
        return self.t[self.i][0] if self.i < len(self.t) else None

    def take(self):
        self.i += 1
        return self.t[self.i - 1]

    def deeper(self):
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise Fehler("lang")

    @staticmethod
    def ok(v):
        if not v.is_finite() or abs(v) > MAX_ABS:
            raise Fehler("gross")
        return v

    def expr(self):
        v, pct = self.term()
        while self.peek() in ("+", "-"):
            op = self.take()[0]
            r, rpct = self.term()
            if rpct and not pct:   # "249 plus 19 %" adds 19 % of 249
                v = v * (1 + r) if op == "+" else v * (1 - r)
            else:
                v, pct = (v + r if op == "+" else v - r), pct and rpct
            self.ok(v)
        return v, pct

    def term(self):
        v, pct = self.unary()
        while self.peek() in ("*", "/", "v"):
            op = self.take()[0]
            r, _ = self.unary()
            if op == "v":
                if not pct:
                    raise Fehler("prozent")
                v = v * r
            elif op == "*":
                v = v * r
            else:
                if r == 0:
                    raise Fehler("null")
                v = v / r
            pct = False
            self.ok(v)
        return v, pct

    def unary(self):
        if self.peek() in ("-", "+"):
            sign = self.take()[0]
            self.deeper()
            v, pct = self.unary()
            self.depth -= 1
            return (-v if sign == "-" else v), pct
        return self.power()

    def power(self):
        v, pct = self.postfix()
        if self.peek() == "^":
            self.take()
            self.deeper()
            e, _ = self.unary()
            self.depth -= 1
            if abs(e) > MAX_EXP or (v == 0 and e < 0) or (v < 0 and e != e.to_integral_value()):
                raise Fehler("hoch")
            v, pct = self.ok(v ** e), False
        return v, pct

    def postfix(self):
        v, pct = self.primary()
        if self.peek() == "%":
            self.take()
            v, pct = v / 100, True
        return v, pct

    def primary(self):
        kind = self.peek()
        if kind is None:
            raise Fehler("form")
        if kind == "n":
            return self.ok(self.take()[1]), False
        if kind == "π":
            self.take()
            return PI, False
        if kind == "(":
            self.take()
            self.deeper()
            v = self.expr()
            self.depth -= 1
            if self.peek() != ")":
                raise Fehler("form")
            self.take()
            return v
        if kind == "√":
            self.take()
            self.deeper()
            v, _ = self.unary()
            self.depth -= 1
            if v < 0:
                raise Fehler("wurzel")
            return v.sqrt(), False
        raise Fehler("form")


def calc(text, en=False):
    """The value (Decimal) of a calculation, else Fehler with a key of WHY. Never eval: an own parser over at most
    MAX_TOKENS tokens."""
    with decimal.localcontext(_ctx()):
        try:
            toks = tokens(text, en)
            p = _Parser(toks)
            v, _ = p.expr()
            if p.i != len(toks):
                raise Fehler("form")
            return +v
        except (decimal.DivisionByZero, decimal.InvalidOperation):
            raise Fehler("hoch")
        except (decimal.Overflow, decimal.Underflow):
            raise Fehler("gross")
        except RecursionError:
            raise Fehler("lang")


def show(v, en=False, places=PLACES, group=0):
    """A Decimal as written: German comma (English point), at most `places` decimals, no trailing zeros; a thousands
    separator when the whole part has at least `group` digits (0: never)."""
    with decimal.localcontext(_ctx()):
        q = v.quantize(D(1).scaleb(-places), rounding=decimal.ROUND_HALF_UP) if places else \
            v.quantize(D(1), rounding=decimal.ROUND_HALF_UP)
    s = format(q, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    if s in ("-0", ""):
        s = "0"
    whole, _, frac = s.partition(".")
    if group and len(whole.lstrip("-")) >= group:
        neg, digits = whole.startswith("-"), whole.lstrip("-")
        digits = f"{int(digits):,}".replace(",", "," if en else ".")
        whole = ("-" if neg else "") + digits
    return whole + ((("." if en else ",") + frac) if frac else "")


def say(v, en=False):
    """A result as it is spoken: whole numbers plain, else two places, "etwa" when that rounded it."""
    s = show(v, en, 2, group=5)
    exact = v == v.quantize(D("0.01"), rounding=decimal.ROUND_HALF_UP) if abs(v) < MAX_ABS else True
    return s if exact else ("about " if en else "etwa ") + s


def why(key, en=False):
    return WHY.get(key, WHY["form"])[1 if en else 0]


# --- dates ------------------------------------------------------------------------------------------------------

def day(text, today):
    """A date from "2026-12-24", "24.12.", "24.12.2026", "24. Dezember", "Weihnachten", "morgen"; a day without year
    is the next one from today on. Else Fehler("datum")."""
    t = re.sub(r"\s+", " ", str(text or "").strip().lower()).removeprefix("der ").removeprefix("den ")
    t = t.removeprefix("zum ").removeprefix("zu ").removeprefix("am ").strip(" ?.!")
    year = None
    try:
        if t in ("heute", "today"):
            return today
        if t in ("morgen", "tomorrow"):
            return today + datetime.timedelta(days=1)
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", t)
        if m:
            d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if not 1900 <= d.year <= 2200:
                raise Fehler("datum")
            return d
        m = re.fullmatch(r"(\d{1,2})\.\s?(\d{1,2})\.(?:\s?(\d{4}))?", t) or \
            re.fullmatch(r"(\d{1,2})\.?\s+(" + _MON + r")(?:\s+(\d{4}))?", t)
        if m:
            mon = int(m.group(2)) if m.group(2).isdigit() else MONTHS[m.group(2)]
            dd, year = int(m.group(1)), int(m.group(3)) if m.group(3) else None
        elif t in FEAST:
            mon, dd = FEAST[t]
        else:
            raise Fehler("datum")
        if year is not None:
            if not 1900 <= year <= 2200:
                raise Fehler("datum")
            return datetime.date(year, mon, dd)
        d = datetime.date(today.year, mon, dd)
        return d if d >= today else datetime.date(today.year + 1, mon, dd)
    except ValueError as e:
        raise e if isinstance(e, Fehler) else Fehler("datum")


def long_day(d, en=False, case="der"):
    """"Freitag, der 16. Oktober 2026" (case "dem" after "vom"/"bis"), "Friday, October 16, 2026"."""
    if en:
        return f"{WEEKDAY_EN[d.weekday()]}, {MONTH_EN[d.month - 1]} {d.day}, {d.year}"
    return f"{WEEKDAY[d.weekday()]}, {case} {d.day}. {MONTH[d.month - 1]} {d.year}"


def days(art, today, von=None, bis=None, datum=None, tage=None, en=False):
    """The fixed sentence for one date calculation; Fehler on anything not understood."""
    if art == "tage_bis":
        a, b = today, day(bis, today)
    elif art == "tage_zwischen":
        a, b = day(von, today) if von else today, day(bis, today)
    elif art == "wochentag":
        d = day(datum or bis or von, today)
        return (f"{d.strftime('%m/%d/%Y')} is a {WEEKDAY_EN[d.weekday()]}." if en else
                f"Der {d.day}.{d.month}.{d.year} ist ein {WEEKDAY[d.weekday()]}.")
    elif art == "datum_plus":
        try:
            n = int(tage)
        except (TypeError, ValueError):
            raise Fehler("tage")
        if abs(n) > MAX_DAYS:
            raise Fehler("tage")
        a = day(von, today) if von else today
        b = a + datetime.timedelta(days=n)
        if en:
            return f"{abs(n)} days {'after' if n >= 0 else 'before'} {a.isoformat()} is {long_day(b, True)}."
        return f"{abs(n)} Tage {'nach' if n >= 0 else 'vor'} dem {a.day}.{a.month}.{a.year} ist {long_day(b)}."
    else:
        raise Fehler("form")
    n = (b - a).days
    if abs(n) > MAX_DAYS:
        raise Fehler("tage")
    w, rest = divmod(abs(n), 7)
    weeks = (f" ({w} weeks" + (f" and {rest} days" if rest else "") + ")" if en else
             f" ({w} Wochen" + (f" und {rest} Tage" if rest else "") + ")") if abs(n) >= 14 else ""
    if en:
        return f"From {long_day(a, True)} to {long_day(b, True)}: {n} days{weeks}."
    return f"Vom {long_day(a, case='dem')} bis {long_day(b, case='dem')} sind es {n} Tage{weeks}."


# --- the tool ---------------------------------------------------------------------------------------------------

def offer(ctx):
    who = ctx.get("who")
    if not who or not ctx.get("own") or ctx.get("client") == "mcp" or not features.allowed("rechnen", who["id"]):
        return None
    if not WORDS.search(str(ctx.get("text") or "")):
        return None
    return {"tools": [TOOL], "hint": HINT, "keep": {"rechnen"},
            "filler": {"rechnen": ("Ich rechne nach.", "Let me calculate.")}}


def run(args, today):
    """(art, result text) of one tool call; the text starts with "Fehler" when it did not work (taten.FAILED)."""
    args = args if isinstance(args, dict) else {}
    art = args.get("art") if args.get("art") in ARTEN else "zahl"
    try:
        if art == "zahl":
            expr = str(args.get("ausdruck") or "")
            v = calc(expr, en=True)
            exact = show(v)
            short = say(v)
            return art, (f"{PREFIX}{exact}" + (f" (gesprochen: {short})" if short != exact else "")
                         + ". Sag genau diese Zahl.")
        return art, days(art, today, *(str(args[k])[:40] if args.get(k) is not None else None
                                       for k in ("von", "bis", "datum")), tage=args.get("tage"))
    except Fehler as e:
        return art, "Fehler beim Rechnen: " + why(e.args[0]) + " Rechne es nicht selbst; sag, dass es so nicht ging."


async def tool(name, args, ctx):
    who = ctx.get("who") or {}
    if name != "rechnen" or not features.allowed("rechnen", who.get("id")):
        return "Fehler: Rechnen mit festem Werkzeug ist für dieses Profil aus."
    import chat
    art, out = run(args, chat.local_now(ctx.get("tz")).date())
    print(f"rechnen: {art} {'fehler' if out.startswith('Fehler') else 'ok'}", flush=True)
    return out


# --- the answer check: a stated result is computed again ---------------------------------------------------------

_N = r"\d+(?:[.,]\d+)*"
_UNIT_AFTER = r"(?:\s*(?:€|euro\b|%|prozent\b|percent\b))?"
_OPW = (r"\s+(?:plus|minus|mal|times|geteilt\s+durch|dividiert\s+durch|divided\s+by|durch|hoch|x|-|–)\s+"
        r"|\s*(?:[+×·÷*/^])\s*|\s*(?:%|prozent|percent)\s+(?:von|of)\s+")
SUM = re.compile(r"(?<![\w.,:/-])(\(?" + _N + _UNIT_AFTER + r"(?:(?:" + _OPW + r")\(?" + _N + r"\)?" + _UNIT_AFTER
                 + r"){1,6})\s*(=|ist gleich|ist|sind|ergibt|ergeben|macht|makes|equals|is|are)\s+"
                 r"((?:etwa|ungefähr|rund|circa|ca\.|about|approximately|roughly)\s+)?(-?" + _N + r")(?![\d]|[.,]\d)",
                 re.I)


def value(text):
    """The figure of a tool result of rechnen ("Ergebnis vom Panel: 47,31 …"), else None."""
    m = re.match(re.escape(PREFIX) + r"(-?\d+(?:,\d+)?)", str(text or ""))
    return D(m.group(1).replace(",", ".")) if m else None


def fix(sentence, en=False):
    """(sentence, n, values): every "a op b ist c" whose c is wrong gets the panel's result instead (with as many
    places as the model wrote, at least two when it is not whole); values are the panel's results of every
    calculation found, right or corrected. Only figures with digits; a range like "10-12" (no spaces) or a date, a
    time or a phone number is never taken for a calculation."""
    n, values = 0, []

    def one(m):
        nonlocal n
        try:
            true = calc(m.group(1), en)
            said = number(m.group(4), en)
        except Fehler:
            return m.group(0)
        values.append(true)
        stated = m.group(4)
        sep = "." if en else ","
        places = len(stated.rsplit(sep, 1)[1]) if sep in stated and len(stated.rsplit(sep, 1)[1]) != 3 else 0
        slack = D(1).scaleb(-places) / 2 + D("1e-12")
        if m.group(3):   # "etwa": one percent room
            slack = max(slack, abs(true) / 100)
        if abs(true - said) <= slack:
            return m.group(0)
        n += 1
        whole = true == true.to_integral_value()
        grouped = re.search(r"\d[.,]\d{3}(?!\d)", stated) and not places
        right = show(true, en, places if places else (0 if whole else 2), group=4 if grouped else 0)
        if not whole and not m.group(3) and true != true.quantize(D(1).scaleb(-max(places, 2))):
            right = ("about " if en else "etwa ") + right
        return m.group(0)[:m.start(4) - m.start(0)] + right
    out = SUM.sub(one, sentence)
    return out, n, values
