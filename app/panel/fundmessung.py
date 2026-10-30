"""Finden, Stufe E: die Messung (plan such-index §8 E, Dominik 2026-10-29): how fast the search index stays with many
own data, on synthetic data only, in an index of its own that nobody else sees.

    python3 fundmessung.py messen [mails] [dokumente]     (on the Spark: sudo speech-spark finden messen …)

- Synthetic data, made here from a fixed seed (the same numbers each time): 50 000 mails (MAILS), every fifth with
  an attachment, and 5 000 documents (DOKUMENTE) as rows of the index (fields and tags; their full text stays in
  wissen.db, whose own search the documents measure). Words from a made-up vocabulary with a Zipf-like spread, a few
  real ones (Rechnung, Gesamtbetrag …) so the fixed rules give amounts, numbers and categories.
- Sealed like real mail: every mail and attachment goes through fundmail.eintraege (the first EINLESEN_MIME as real
  MIME messages: parsing, the fixed rules, the attachment's text) and fundmail.schreiben (AES-GCM, HMAC marks, one
  transaction per slice of fundmail.HAPPEN_N), the rest as ready entries through the same schreiben.
- Measured: the time per search (p50, p95, the slowest; SUCHEN searches of one, two and three words, with a category,
  a period and a sender), reading in per 1000 mails (with MIME) and writing per 1000 (sealing and writing only), the
  size of fund.db and the RAM of this process (resident now, peak, growth). The plan's goal on the Pi:
  95 % of the searches below ZIEL_P95_MS.
- Never touches a profile: the command line runs in a folder of its own beside users/ (a throw-away profile folder,
  removed at the end, also after an error); the Spark's key is only read (vorrat.marke and vorrat.seal need it).
  The search runs with fund.suche(…, frei=…) on this index only, whatever the switches of the Spark say.
- Results: numbers only, in one journal line (fund: messung | …) and in state/fundmessung.json, which Zustand → Live
  shows in the box Finden (fund.for_live). Never a word of the synthetic data in either.
"""
import math
import os
import random
import re
import resource
import shutil
import statistics
import sys
import tempfile
import time

MAILS = 50_000
DOKUMENTE = 5_000
SUCHEN = 200
EINLESEN_MIME = 1_000      # mails read in as real MIME messages (the rest as ready entries, the same writing)
ANHANG_JEDE = 5            # every fifth mail has an attachment
WORTE_MAIL = 120           # words of a mail's text
WORTSCHATZ = 20_000        # made-up words
ZIEL_P95_MS = 150          # the plan: 95 % of the searches below this on the Pi
KONTO = "m5e55a9e0"        # the made-up mailbox (fund's form m + 8 hex digits)
NOW = 1_800_000_000        # a fixed moment for the data's dates, never the clock
JAHRE = 10                 # the mails spread over these years
MAX_MAILS = 200_000        # the command line's limits (chat.fund_mail_max in the plan: 1 000 to 200 000)
MAX_DOKUMENTE = 20_000
SILBEN = ("ka", "ber", "lin", "stra", "to", "mer", "ga", "len", "rin", "do", "vo", "sen", "hau", "pel", "tor", "fi",
          "mu", "ra", "kel", "wen", "dra", "zu", "lo", "nik", "ster", "bo", "gu", "ne", "sa", "tik", "ver", "mon")
ECHT = ("Rechnung", "Bestellung", "Lieferung", "Termin", "Vertrag", "Kundennummer", "Versicherung", "Konto", "Reise",
        "Hotel", "Werkstatt", "Arzt", "Praxis", "Steuer", "Bescheid", "Garantie", "Gutschein", "Mahnung")
FIRMEN = ("Thomann", "Telekom", "Allianz", "Bahn", "Lufthansa", "Ikea", "Zalando", "Otto", "Vodafone", "Sparkasse",
          "Stadtwerke", "Amazon", "Mediamarkt", "Tchibo", "Rossmann", "Hornbach")


def _file():
    from common import STATE
    return os.path.join(STATE, "fundmessung.json")


class Daten:
    """The synthetic data from a fixed seed: words, subjects, senders and texts."""
    def __init__(self, seed=7):
        self.rnd = random.Random(seed)
        r = self.rnd
        words = set()
        while len(words) < WORTSCHATZ:
            words.add("".join(r.choice(SILBEN) for _ in range(r.randint(2, 4))))
        self.worte = sorted(words)
        r.shuffle(self.worte)
        # Zipf-like: the word of rank k comes about 1/k as often
        acc, self.cum = 0.0, []
        for k in range(len(self.worte)):
            acc += 1.0 / (k + 1)
            self.cum.append(acc)

    def text(self, n):
        r = self.rnd
        out = r.choices(self.worte, cum_weights=self.cum, k=n)
        for _ in range(max(1, n // 30)):
            out[r.randrange(n)] = r.choice(ECHT)
        return " ".join(out)

    def mail(self, i):
        """(subject, sender, text, attachment text or "", unix time) of mail i."""
        r = self.rnd
        firma = r.choice(FIRMEN)
        rechnung = i % 7 == 0
        subject = (f"Ihre Rechnung {firma} {r.randint(1000, 99999)}" if rechnung else
                   " ".join(r.choices(self.worte, cum_weights=self.cum, k=r.randint(2, 6))).capitalize())
        sender = f"{firma} Service <service@{firma.lower()}.example>" if r.random() < 0.6 else \
            f"{r.choice(self.worte).capitalize()} {r.choice(self.worte).capitalize()} <{r.choice(self.worte)}@post.example>"
        text = self.text(WORTE_MAIL)
        if rechnung:
            text += f"\nRechnungsnummer: RE-{r.randint(10000, 99999)} Gesamtbetrag {r.randint(5, 900)},{r.randint(10, 99)} EUR"
        anhang = ""
        if i % ANHANG_JEDE == 0:
            anhang = self.text(200) + (f"\nRechnungsbetrag {r.randint(5, 900)},{r.randint(10, 99)} EUR" if rechnung else "")
        when = NOW - int(r.random() * JAHRE * 365 * 86400)
        return subject, sender, text, anhang, when

    def frage(self):
        """One search as the page would send it: (words, filters)."""
        r = self.rnd
        k = r.random()
        if k < 0.3:
            return r.choice(self.worte[:3000]), {}
        if k < 0.55:
            return " ".join(r.choices(self.worte[:5000], k=2)), {}
        if k < 0.7:
            return " ".join(r.choices(self.worte, cum_weights=self.cum, k=3)), {}
        if k < 0.8:
            return "Rechnung " + r.choice(FIRMEN), {"kategorie": "Rechnung"}
        if k < 0.9:
            y = 2026 - r.randint(1, JAHRE - 1)
            return r.choice(ECHT), {"von": f"{y}-01-01", "bis": f"{y}-12-31"}
        return r.choice(self.worte[:2000]), {"firma": r.choice(FIRMEN)}


def _raw(subject, sender, text, anhang, when):
    import email.message
    import email.policy
    import email.utils
    m = email.message.EmailMessage(policy=email.policy.SMTP)
    m["From"], m["To"], m["Subject"] = sender, "ich@post.example", subject
    m["Date"] = email.utils.formatdate(when, usegmt=True)
    m.set_content(text)
    if anhang:
        m.add_attachment(anhang.encode(), maintype="text", subtype="plain", filename="beleg.txt")
    return m.as_bytes(policy=email.policy.SMTP)


def _eintrag(uid, fkey, u, subject, sender, text, anhang, when):
    """(mail, [attachments]) like fundmail.eintraege makes them, without a MIME message (the fixed rules too)."""
    import fund
    ext = f"{KONTO}:{fkey}:{u}"
    felder, tags = fund.regeln(subject + "\n" + text, {"sender": sender.split("<")[0].strip()})
    felder.update(absender=sender, ordner="inbox")
    anh = []
    if anhang:
        af, at = fund.regeln(anhang, {"sender": sender.split("<")[0].strip()})
        af.pop("absender", None)
        af.update(name="beleg.txt", kb=max(1, len(anhang) // 1024))
        anh.append({"ext": f"{ext}:0", "wann": when, "titel": "beleg.txt", "auszug": anhang, "felder": af, "tags": at,
                    "worte": "beleg.txt\n" + anhang, "absender": sender})
        felder["anhaenge"] = ["beleg.txt"]
    return {"ext": ext, "wann": when, "titel": subject, "auszug": text, "felder": felder, "tags": tags,
            "worte": "\n".join([subject, sender, text] + [a["titel"] for a in anh]), "absender": sender}, anh


def _rss_mb():
    try:
        with open("/proc/self/status", encoding="ascii") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except OSError:
        pass
    return 0.0


def _peak_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024   # kilobytes on Linux


def _pct(ms, p):
    """The nearest-rank percentile: the smallest value at least p % of the values are not above."""
    s = sorted(ms)
    return s[min(len(s) - 1, max(0, math.ceil(p / 100 * len(s)) - 1))] if s else 0.0


def messen(uid, mails=MAILS, dokumente=DOKUMENTE, suchen=SUCHEN, seed=7, schritt=None):
    """Fills the index of `uid` (a throw-away one: its fund.db is made anew) with the synthetic data and measures.
    schritt(text): progress for the command line. Returns the numbers (also what for_live shows)."""
    import fund
    import fundmail
    import vorrat
    if not vorrat.marke(uid, "x"):
        raise RuntimeError("no key")
    path = fund.db_path(uid)
    for x in (path, path + "-wal", path + "-shm"):
        if os.path.exists(x):
            os.remove(x)
    d = Daten(seed)
    rss0 = _rss_mb()
    fkey = fundmail._fkey(uid, KONTO, "INBOX")
    with fund._Db(uid) as con:
        fundmail._put_state(con, KONTO, fkey, {"validity": "1", "rolle": "inbox",
                                               "name": fund.siegel(uid, "ordner", KONTO, fkey, "INBOX")})
    # documents (and NAS) as rows of the index: fields and tags, like fund._doc_entries makes them
    t0 = time.perf_counter()
    with fund._Db(uid) as con:
        for i in range(dokumente):
            src = fund.BY_NAME["dokument" if i < 200 else "nas"]
            titel = " ".join(d.rnd.choices(d.worte, cum_weights=d.cum, k=d.rnd.randint(2, 5))).capitalize()
            text = d.text(80)
            felder, tags = fund.regeln(text, {"art": d.rnd.choice(fund.ARTEN), "sender": d.rnd.choice(FIRMEN)})
            fund._put(con, uid, src, {"ext": f"{i:012x}", "wann": NOW - int(d.rnd.random() * JAHRE * 365 * 86400),
                                      "geaendert": NOW - 86400, "titel": titel, "auszug": text[:fund.AUSZUG],
                                      "felder": dict(felder, name=f"datei-{i}.pdf", tags=[]), "stand": str(i),
                                      "tags": tags, "worte": " ".join([titel, felder.get("nr", "")])}, NOW)
    dok_s = time.perf_counter() - t0
    if schritt:
        schritt(f"{dokumente} dokumente | {dok_s:.1f} s")
    # the first mails as real MIME messages (parsing, rules, the attachment's text), the rest as ready entries
    import email
    import email.policy
    mime_n = min(EINLESEN_MIME, mails)
    raws = [_raw(*d.mail(i)) for i in range(mime_n)]
    t0 = time.perf_counter()
    for at in range(0, mime_n, fundmail.HAPPEN_N):
        batch = []
        for u in range(at, min(mime_n, at + fundmail.HAPPEN_N)):
            msg = email.message_from_bytes(raws[u], policy=email.policy.default)
            batch.append(fundmail.eintraege(KONTO, fkey, "inbox", u + 1, msg))
        fundmail.schreiben(uid, batch, NOW, zaehlen=False)
    mime_s = time.perf_counter() - t0
    del raws
    rest_s, n = 0.0, 0
    for at in range(mime_n, mails, fundmail.HAPPEN_N):
        made = [d.mail(u) for u in range(at, min(mails, at + fundmail.HAPPEN_N))]   # making the data is not measured
        t0 = time.perf_counter()
        batch = [_eintrag(uid, fkey, at + k + 1, *m) for k, m in enumerate(made)]
        fundmail.schreiben(uid, batch, NOW, zaehlen=False)
        rest_s += time.perf_counter() - t0
        n += len(batch)
        if schritt and n % 10_000 < fundmail.HAPPEN_N:
            schritt(f"{mime_n + n} mails")
    with fund._Db(uid) as con:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        anhaenge = con.execute("SELECT COUNT(*) FROM fund_item WHERE quelle='anhang'").fetchone()[0]
    size = sum(os.path.getsize(x) for x in (path, path + "-wal") if os.path.exists(x))
    rss_full = _rss_mb()
    # the searches: like the page, only this index (frei), the newest date as now
    frei = (("dokument", "nas", "mail", "anhang"), [KONTO], None)
    ms, treffer = [], 0
    fund.suche(uid, d.frage()[0], now=NOW, frei=frei)   # the first one opens the file (not counted)
    for _ in range(suchen):
        worte, flt = d.frage()
        t0 = time.perf_counter()
        hits = fund.suche(uid, worte, now=NOW, frei=frei, **flt)
        ms.append((time.perf_counter() - t0) * 1000)
        treffer += bool(hits)
    p95 = _pct(ms, 95)
    return {"at": int(time.time()), "mails": mails, "anhaenge": anhaenge, "dokumente": dokumente, "suchen": suchen,
            "mit_treffer": treffer, "p50_ms": round(statistics.median(ms), 1), "p95_ms": round(p95, 1),
            "max_ms": round(max(ms), 1), "ziel_ms": ZIEL_P95_MS, "unter_ziel": round(sum(1 for x in ms if x < ZIEL_P95_MS) * 100 / len(ms)),
            "einlesen_1000_s": round(mime_s * 1000 / max(1, mime_n), 2),
            "schreiben_1000_s": round(rest_s * 1000 / max(1, mails - mime_n), 2) if mails > mime_n else None,
            "dokumente_1000_s": round(dok_s * 1000 / max(1, dokumente), 2) if dokumente else None,
            "db_mb": round(size / 1024 / 1024, 1), "kb_je_mail": round(size / 1024 / max(1, mails + anhaenge + dokumente), 2),
            "ram_mb": round(_rss_mb(), 1), "ram_spitze_mb": round(_peak_mb(), 1),
            "ram_zuwachs_mb": round(max(0.0, rss_full - rss0), 1)}


def zeile(r):
    """The journal line: fixed words and numbers only."""
    return "fund: messung | " + _werte(r)


def _werte(r):
    return (f"{r['mails']} mails | {r['anhaenge']} anhaenge | {r['dokumente']} dokumente | "
            f"p50 {r['p50_ms']} ms | p95 {r['p95_ms']} ms | max {r['max_ms']} ms | {r['unter_ziel']} % unter {r['ziel_ms']} ms | "
            f"einlesen {r['einlesen_1000_s']} s je 1000 | db {r['db_mb']} mb | ram {r['ram_mb']} mb spitze {r['ram_spitze_mb']} mb")


LIVE_KEYS = ("at", "mails", "anhaenge", "dokumente", "suchen", "p50_ms", "p95_ms", "max_ms", "ziel_ms", "unter_ziel",
             "einlesen_1000_s", "schreiben_1000_s", "dokumente_1000_s", "db_mb", "ram_mb", "ram_spitze_mb", "ram_zuwachs_mb")


def behalten(r):
    """The last result into state/fundmessung.json (numbers only), for Zustand → Live."""
    from common import write_json
    write_json(_file(), {k: r[k] for k in LIVE_KEYS if isinstance(r.get(k), (int, float)) and not isinstance(r.get(k), bool)},
               mode=0o600)


def letzte():
    """The last measurement's numbers, or None (Live: fund.for_live)."""
    from common import read_json
    got = read_json(_file(), None)
    if not isinstance(got, dict):
        return None
    return {k: got[k] for k in LIVE_KEYS if isinstance(got.get(k), (int, float)) and not isinstance(got.get(k), bool)} or None


def _zahl(v, default, most):
    if v is None:
        return default
    if not re.fullmatch(r"\d{1,7}", str(v)):
        raise SystemExit("fundmessung: only whole numbers")
    return max(0, min(int(v), most))


def main(argv):
    """The command line: messen [mails] [dokumente] in a throw-away folder beside users/ (removed at the end)."""
    if not argv or argv[0] != "messen":
        print("fund: messung abgelehnt | aufruf: fundmessung.py messen [mails] [dokumente]")
        return 2
    mails = _zahl(argv[1] if len(argv) > 1 else None, MAILS, MAX_MAILS)
    docs = _zahl(argv[2] if len(argv) > 2 else None, DOKUMENTE, MAX_DOKUMENTE)
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import vault
    if not os.path.exists(vault.KEY_FILE):   # only read, never made here: without it nothing can be sealed
        print("fund: messung abgelehnt | kein schluessel", flush=True)
        return 1
    users = os.environ.get("SPEECH_SPARK_USERS", "/var/lib/speech-spark/users")
    # on the same disk as the profiles (the SD card or the SSD is what is measured), never inside users/
    tmp = tempfile.mkdtemp(prefix="fundmessung-", dir=os.path.dirname(os.path.abspath(users)))
    os.chmod(tmp, 0o700)
    os.environ["SPEECH_SPARK_USERS"] = tmp
    try:
        r = messen("fundmessung", mails, docs, schritt=lambda s: print(f"fund: messung schritt | {s}", flush=True))
        print("fund: messung | " + _werte(r), flush=True)
        behalten(r)
        print(f"fund: messung ziel | 95 % unter {r['ziel_ms']} ms | erreicht {r['unter_ziel']} % | "
              f"{'ja' if r['p95_ms'] < r['ziel_ms'] else 'nein'}", flush=True)
        return 0
    except Exception as e:
        print(f"fund: messung fehler | {type(e).__name__}", flush=True)
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
