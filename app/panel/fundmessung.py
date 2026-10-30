"""Finden messen (plan such-index §8 E, since V01.1.285 a part of Wissen messen): how fast the search index stays
with many own data, on synthetic data only, in an index of its own that nobody else sees.

    wissensmessung.MESSTEILE["fund"]: wissensmessung.teil_fund(ordner, anzahl) -> teil(anzahl, ruhe)
    (Zustand → Prüfen → Wissen messen, or sudo speech-spark wissen messen synth 5000)

The shared measurement (wissensmessung.py) does the rest, once for every part: its own measuring process at low
priority, one run at a time (a lock file), the pause between runs from the panel, the stop as soon as somebody speaks
(ruhe, between every two slices here), the throwaway run folder (profiles point there, removed after the run), the
journal line per part, the kept runs and Live. This file only builds and measures; it has no command line, no unit
and no file of its own.

- Synthetic data, made here from a fixed seed (the same numbers each time): per document of the run MAILS_JE_DOKUMENT
  mails (5 000 documents: 50 000 mails), every fifth with an attachment, and the documents as rows of the index
  (fields and tags; their full text stays in wissen.db, whose own search the part „documents“ measures). Words from a
  made-up vocabulary with a Zipf-like spread, a few real ones (Rechnung, Gesamtbetrag …) so the fixed rules give
  amounts, numbers and categories.
- Sealed like real mail: every mail and attachment goes through fundmail.eintraege (the first EINLESEN_MIME as real
  MIME messages: parsing, the fixed rules, the attachment's text) and fundmail.schreiben (AES-GCM, HMAC marks, one
  transaction per slice of fundmail.HAPPEN_N), the rest as ready entries through the same schreiben.
- Measured (numbers only, keys in the form of the other parts): suche_p50_ms, suche_p95_ms, suche_max_ms, suche_n
  (SUCHEN searches of one, two and three words, with a category, a period and a sender), reading in per 1000 mails
  (with MIME) and writing per 1000 (sealing and writing only), the size of fund.db, and the RAM of the measuring
  process (before, after, peak, growth). The plan's goal on the Pi: 95 % of the searches below ZIEL_P95_MS.
- The Spark's key is only read (vorrat.marke and vorrat.seal need it), never made: without it the part gives
  {"schluessel": False} and one journal line. The search runs with fund.suche(…, frei=…) on this index only,
  whatever the switches of the Spark say.
"""
import os
import random
import resource
import time

MAILS = 50_000             # the test's numbers (and what Wissen messen with 5 000 documents builds)
DOKUMENTE = 5_000
MAILS_JE_DOKUMENT = 10     # mails per document of the run (Wissen messen's anzahl)
SUCHEN = 200
EINLESEN_MIME = 1_000      # mails read in as real MIME messages (the rest as ready entries, the same writing)
ANHANG_JEDE = 5            # every fifth mail has an attachment
WORTE_MAIL = 120           # words of a mail's text
WORTSCHATZ = 20_000        # made-up words
ZIEL_P95_MS = 150          # the plan: 95 % of the searches below this on the Pi
KONTO = "m5e55a9e0"        # the made-up mailbox (fund's form m + 8 hex digits)
NOW = 1_800_000_000        # a fixed moment for the data's dates, never the clock
JAHRE = 10                 # the mails spread over these years
UID = "fundmessung"        # the throwaway profile's id inside the run folder
SILBEN = ("ka", "ber", "lin", "stra", "to", "mer", "ga", "len", "rin", "do", "vo", "sen", "hau", "pel", "tor", "fi",
          "mu", "ra", "kel", "wen", "dra", "zu", "lo", "nik", "ster", "bo", "gu", "ne", "sa", "tik", "ver", "mon")
ECHT = ("Rechnung", "Bestellung", "Lieferung", "Termin", "Vertrag", "Kundennummer", "Versicherung", "Konto", "Reise",
        "Hotel", "Werkstatt", "Arzt", "Praxis", "Steuer", "Bescheid", "Garantie", "Gutschein", "Mahnung")
FIRMEN = ("Thomann", "Telekom", "Allianz", "Bahn", "Lufthansa", "Ikea", "Zalando", "Otto", "Vodafone", "Sparkasse",
          "Stadtwerke", "Amazon", "Mediamarkt", "Tchibo", "Rossmann", "Hornbach")


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


def _peak_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024   # kilobytes on Linux


def messen(uid, mails=MAILS, dokumente=DOKUMENTE, suchen=SUCHEN, seed=7, wm=None):
    """Fills the index of `uid` (a throw-away one: its fund.db is made anew) with the synthetic data and measures.
    wm: the module wissensmessung of the measuring process (its ruhe, zeiten and rss_mb). Returns numbers only."""
    import fund
    import fundmail
    import vorrat
    if wm is None:
        import wissensmessung as wm
    if not vorrat.marke(uid, "x"):
        raise RuntimeError("no key")
    path = fund.db_path(uid)
    for x in (path, path + "-wal", path + "-shm"):
        if os.path.exists(x):
            os.remove(x)
    d = Daten(seed)
    rss0 = wm.rss_mb()
    fkey = fundmail._fkey(uid, KONTO, "INBOX")
    with fund._Db(uid) as con:
        fundmail._put_state(con, KONTO, fkey, {"validity": "1", "rolle": "inbox",
                                               "name": fund.siegel(uid, "ordner", KONTO, fkey, "INBOX")})
    # documents (and NAS) as rows of the index: fields and tags, like fund._doc_entries makes them
    dok_s = 0.0
    for at in range(0, dokumente, fundmail.HAPPEN_N):
        wm.ruhe()
        t0 = time.perf_counter()
        with fund._Db(uid) as con:
            for i in range(at, min(dokumente, at + fundmail.HAPPEN_N)):
                src = fund.BY_NAME["dokument" if i < 200 else "nas"]
                titel = " ".join(d.rnd.choices(d.worte, cum_weights=d.cum, k=d.rnd.randint(2, 5))).capitalize()
                text = d.text(80)
                felder, tags = fund.regeln(text, {"art": d.rnd.choice(fund.ARTEN), "sender": d.rnd.choice(FIRMEN)})
                fund._put(con, uid, src, {"ext": f"{i:012x}", "wann": NOW - int(d.rnd.random() * JAHRE * 365 * 86400),
                                          "geaendert": NOW - 86400, "titel": titel, "auszug": text[:fund.AUSZUG],
                                          "felder": dict(felder, name=f"datei-{i}.pdf", tags=[]), "stand": str(i),
                                          "tags": tags, "worte": " ".join([titel, felder.get("nr", "")])}, NOW)
        dok_s += time.perf_counter() - t0
    # the first mails as real MIME messages (parsing, rules, the attachment's text), the rest as ready entries
    import email
    import email.policy
    mime_n = min(EINLESEN_MIME, mails)
    raws = [_raw(*d.mail(i)) for i in range(mime_n)]
    mime_s = 0.0
    for at in range(0, mime_n, fundmail.HAPPEN_N):
        wm.ruhe()
        t0 = time.perf_counter()
        batch = []
        for u in range(at, min(mime_n, at + fundmail.HAPPEN_N)):
            msg = email.message_from_bytes(raws[u], policy=email.policy.default)
            batch.append(fundmail.eintraege(KONTO, fkey, "inbox", u + 1, msg))
        fundmail.schreiben(uid, batch, NOW, zaehlen=False)
        mime_s += time.perf_counter() - t0
    del raws
    rest_s = 0.0
    for at in range(mime_n, mails, fundmail.HAPPEN_N):
        wm.ruhe()
        made = [d.mail(u) for u in range(at, min(mails, at + fundmail.HAPPEN_N))]   # making the data is not measured
        t0 = time.perf_counter()
        batch = [_eintrag(uid, fkey, at + k + 1, *m) for k, m in enumerate(made)]
        fundmail.schreiben(uid, batch, NOW, zaehlen=False)
        rest_s += time.perf_counter() - t0
    with fund._Db(uid) as con:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        anhaenge = con.execute("SELECT COUNT(*) FROM fund_item WHERE quelle='anhang'").fetchone()[0]
    size = sum(os.path.getsize(x) for x in (path, path + "-wal") if os.path.exists(x))
    rss_full = wm.rss_mb()
    # the searches: like the page, only this index (frei), the newest date as now; the first one opens the file
    frei = (("dokument", "nas", "mail", "anhang"), [KONTO], None)
    fund.suche(uid, d.frage()[0], now=NOW, frei=frei)
    ms, treffer = [], [0]

    def eine(worte, flt):
        t0 = time.perf_counter()
        hits = fund.suche(uid, worte, now=NOW, frei=frei, **flt)
        ms.append((time.perf_counter() - t0) * 1000)
        treffer[0] += bool(hits)
    out = {"schluessel": True, "mails": mails, "anhaenge": anhaenge, "dokumente": dokumente}
    out.update(wm.zeiten("suche", eine, [d.frage() for _ in range(suchen)]))
    out.update({"mit_treffer": treffer[0], "ziel_ms": ZIEL_P95_MS,
                "unter_ziel": round(sum(1 for x in ms if x < ZIEL_P95_MS) * 100 / max(1, len(ms))),
                "einlesen_1000_s": round(mime_s * 1000 / max(1, mime_n), 2),
                "db_mb": round(size / 1024 / 1024, 1),
                "kb_je_eintrag": round(size / 1024 / max(1, mails + anhaenge + dokumente), 2),
                "ram_vorher_mb": rss0, "ram_mb": wm.rss_mb(), "ram_spitze_mb": round(_peak_mb(), 1),
                "ram_zuwachs_mb": round(max(0.0, rss_full - rss0), 1)})
    if mails > mime_n:
        out["schreiben_1000_s"] = round(rest_s * 1000 / (mails - mime_n), 2)
    if dokumente:
        out["dokumente_1000_s"] = round(dok_s * 1000 / dokumente, 2)
    return out


def teil(anzahl, wm):
    """The part „fund“ of Wissen messen (wissensmessung.teil_fund, after it pointed the profiles at the run folder):
    `anzahl` documents and MAILS_JE_DOKUMENT mails per document. wm: the measuring process's wissensmessung."""
    import vault
    if not os.path.exists(vault.KEY_FILE):   # only read, never made here: without it nothing can be sealed
        print("fund: messung abgelehnt | kein schluessel", flush=True)
        return {"schluessel": False}
    return messen(UID, anzahl * MAILS_JE_DOKUMENT, anzahl, wm=wm)
