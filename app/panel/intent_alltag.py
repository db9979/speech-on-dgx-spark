"""The Weiche's everyday check (plan weiche-intelligenter.md, 4): sentences as people say them, never used to set
the rules up. intent_bench.BENCH holds every reported wrong turn and passes in full by design; this list measures how
well the rules do on questions nobody tuned them for.

Each line: sentence -> the group it belongs to ("" = no group, a knowledge question or small talk the model answers
alone). Rules may be improved because of a group of misses here, never by copying one of these sentences into a rule;
a sentence that should always land right goes into intent_bench.BENCH instead.

measure() sorts every sentence into
    richtig    the rules name the right group (the tools are narrowed to it)
    geschuetzt nothing recognized for sure, but a hint word names the right group: its tools stay with „lean“ and a
               model pick (intent.Route.hints)
    offen      nothing recognized and no hint (or no hint for the right group): with „lean“ the tool is missing
    falsch     the rules name another group (the right tools are cut away)
tests/test_intent_alltag.py holds the numbers: right + protected may not go down, wrong may not go up.
Funktionen → Weiche shows them („Alltagsquote“).
"""

ALLTAG = [
    # smarthome
    ("Mach mal das Licht im Bad an", "smarthome"),
    ("Wie warm ist es im Wohnzimmer?", "smarthome"),
    ("Ist die Waschmaschine fertig?", "smarthome"),
    ("Dreh die Heizung im Büro hoch", "smarthome"),
    ("Wie warm ist das Wasser im Pool?", "smarthome"),
    ("Sind alle Fenster zu?", "smarthome"),
    ("Mach die Rollos im Schlafzimmer zu", "smarthome"),
    ("Wie viel Strom verbrauchen wir gerade?", "smarthome"),
    ("Schalte den Ventilator aus", "smarthome"),
    ("Ist die Haustür abgeschlossen?", "smarthome"),
    ("Mach es im Wohnzimmer etwas heller", "smarthome"),
    ("Dimm das Licht in der Küche auf 30 Prozent", "smarthome"),
    ("Lass den Saugroboter im Flur saugen", "smarthome"),
    ("Wie voll ist der Akku vom Auto?", "smarthome"),
    ("Mach die Lampe auf der Terrasse aus", "smarthome"),
    # kalender
    ("Wann muss ich morgen los?", "kalender"),
    ("Hab ich am Freitag Zeit?", "kalender"),
    ("Verschieb mein Meeting mit Peter auf 15 Uhr", "kalender"),
    ("Was hab ich nächste Woche vor?", "kalender"),
    ("Bin ich am Samstag schon verplant?", "kalender"),
    ("Wann ist mein nächster Arzttermin?", "kalender"),
    ("Trag für Mittwoch Elternabend um 19 Uhr ein", "kalender"),
    ("Wie sieht mein Tag aus?", "kalender"),
    ("Habe ich übermorgen etwas vor?", "kalender"),
    ("Sag das Treffen mit Jonas am Donnerstag ab", "kalender"),
    ("Wann treffe ich mich mit Sabine?", "kalender"),
    # mail
    ("Hat mir die Bank geschrieben?", "mail"),
    ("Was wollte Herr Meier von mir?", "mail"),
    ("Gibt es was Wichtiges im Postfach?", "mail"),
    ("Lies mir die Mail von der Schule vor", "mail"),
    ("Hab ich Post vom Finanzamt bekommen?", "mail"),
    ("Schreib einen Entwurf für eine Antwort an Frau Weber", "mail"),
    ("Such die Mail mit der Buchungsbestätigung", "mail"),
    ("Ist die Antwort vom Vermieter schon da?", "mail"),
    # nachricht
    ("Antworte Anna, dass ich später komme", "nachricht"),
    ("Sag Papa, dass das Essen fertig ist", "nachricht"),
    ("Schick Lena eine Nachricht, dass sie Brot mitbringen soll", "nachricht"),
    ("Hat mir jemand im Haus geschrieben?", "nachricht"),
    ("Ruf alle zum Essen", "nachricht"),
    # wetter
    ("Brauche ich morgen einen Schirm?", "wetter"),
    ("Muss ich die Pflanzen gießen?", "wetter"),
    ("Wird es heute noch sonnig?", "wetter"),
    ("Wie kalt wird es heute Nacht?", "wetter"),
    ("Soll ich eine Jacke mitnehmen?", "wetter"),
    ("Gibt es heute Gewitter?", "wetter"),
    ("Wie viel Grad hat es draußen?", "wetter"),
    ("Wird es am Wochenende schön?", "wetter"),
    # bahn
    ("Wann fährt der nächste Bus in die Stadt?", "bahn"),
    ("Hat mein Zug Verspätung?", "bahn"),
    ("Wie komme ich mit der Bahn nach Stuttgart?", "bahn"),
    ("Wann fährt die letzte Straßenbahn heute?", "bahn"),
    ("Fällt der ICE nach Berlin aus?", "bahn"),
    # paket
    ("Wo ist meine Amazon-Lieferung?", "paket"),
    ("Kommt heute DHL?", "paket"),
    ("Wann wird mein Päckchen von Hermes zugestellt?", "paket"),
    ("Ist die Sendung schon da?", "paket"),
    ("Wo steckt meine Zalando-Bestellung?", "paket"),
    # erinnerung
    ("Weck mich um sieben", "erinnerung"),
    ("Stell einen Timer auf 10 Minuten", "erinnerung"),
    ("Sag mir in einer Stunde, dass ich die Wäsche aufhänge", "erinnerung"),
    ("Erinner mich heute Abend an den Müll", "erinnerung"),
    ("Wie lange läuft der Timer noch?", "erinnerung"),
    ("Stell einen Wecker für morgen früh um halb sechs", "erinnerung"),
    ("Mach den Timer aus", "erinnerung"),
    # liste
    ("Wir brauchen Milch", "liste"),
    ("Schreib Eier auf", "liste"),
    ("Was muss ich noch einkaufen?", "liste"),
    ("Pack Klopapier auf den Einkaufszettel", "liste"),
    ("Was steht noch auf der Liste?", "liste"),
    ("Streich die Tomaten von der Liste", "liste"),
    ("Setz Rasen mähen auf meine Aufgaben", "liste"),
    ("Wir haben keinen Kaffee mehr", "liste"),
    # kontakt
    ("Wann hat Oma Geburtstag?", "kontakt"),
    ("Wie ist die Nummer vom Klempner?", "kontakt"),
    ("Wo wohnt Tante Gerda?", "kontakt"),
    ("Hast du die Handynummer von Markus?", "kontakt"),
    ("Wer hat diesen Monat Geburtstag?", "kontakt"),
    # dokument
    ("Wann läuft mein Handyvertrag aus?", "dokument"),
    ("Was steht in meinem Mietvertrag zur Kündigung?", "dokument"),
    ("Wie hoch ist die Selbstbeteiligung bei meiner Hausratversicherung?", "dokument"),
    ("Such die Garantie vom Fernseher raus", "dokument"),
    ("Was hat der Arzt im letzten Befund geschrieben?", "dokument"),
    ("Wie viel Nebenkosten haben wir letztes Jahr bezahlt?", "dokument"),
    # websuche
    ("Wer hat gestern die Bundesliga gewonnen?", "websuche"),
    ("Was kostet ein Liter Diesel gerade?", "websuche"),
    ("Hat der Baumarkt heute offen?", "websuche"),
    ("Was gibt es Neues?", "websuche"),
    ("Wie steht der DAX?", "websuche"),
    ("Wie hat der KSC gespielt?", "websuche"),
    ("Was läuft heute Abend im Fernsehen?", "websuche"),
    ("Gibt es Stau auf der A5?", "websuche"),
    ("Wann ist der nächste Flohmarkt in Karlsruhe?", "websuche"),
    ("Was ist heute in der Welt passiert?", "websuche"),
    ("Wie viel kostet ein Bitcoin?", "websuche"),
    ("Wer ist der neue Trainer vom VfB?", "websuche"),
    # gedaechtnis
    ("Ich mag keine Pilze", "gedaechtnis"),
    ("Worüber haben wir gestern geredet?", "gedaechtnis"),
    ("Mein Lieblingsessen ist Lasagne", "gedaechtnis"),
    ("Was hab ich dir letzte Woche über das Auto erzählt?", "gedaechtnis"),
    ("Merk dir bitte meine Schuhgröße: 44", "gedaechtnis"),
    ("Ich bin allergisch gegen Nüsse", "gedaechtnis"),
    # agent
    ("Schick mir jeden Morgen um sieben die Schlagzeilen", "agent"),
    ("Welche Aufgaben laufen bei dir automatisch?", "agent"),
    ("Pass auf, wann die neue iPhone-Generation erscheint", "agent"),
    # iphone
    ("Ruf meine Schwester an", "iphone"),
    ("Bring mich nach Hause", "iphone"),
    ("Starte den Kurzbefehl Feierabend", "iphone"),
    ("Navigier mich zum nächsten Supermarkt", "iphone"),
    # erstellen
    ("Erstell mir eine Excel mit meinen Ausgaben", "erstellen"),
    ("Schreib eine Kündigung für mein Fitnessstudio", "erstellen"),
    ("Mach mir eine Präsentation über Solaranlagen", "erstellen"),
    ("Schreib einen Brief an die Versicherung", "erstellen"),
    ("Erstelle eine Tabelle mit den Geburtstagen der Familie", "erstellen+kontakt"),   # the birthdays are in the contacts
    ("Mach ein Word-Dokument mit dem Protokoll von heute", "erstellen"),
    # zustand
    ("Läuft alles?", "zustand"),
    ("Wann wurde zuletzt gesichert?", "zustand"),
    ("Gibt es ein Update für dich?", "zustand"),
    ("Ist der Notaus an?", "zustand"),
    # spark (questions about the Spark itself)
    ("Wie schalte ich die Websuche ein?", "spark"),
    ("Was kann ich beim Spark noch einstellen?", "spark"),
    ("Wo finde ich die Einstellung für die Stimme?", "spark"),
    # archiv / wikipedia (only when named)
    ("Schau in Wikipedia nach Marie Curie", "wikipedia"),
    ("Was sagt mein Archiv über den Dreißigjährigen Krieg?", "archiv"),
    # no group: knowledge, small talk, sums
    ("Wie hoch ist der Eiffelturm?", ""),
    ("Erklär mir Quantenphysik einfach", ""),
    ("Erzähl einen Witz", ""),
    ("Wie spät ist es?", ""),
    ("Rechne 17 mal 23", ""),
    ("Was ist der Unterschied zwischen Wetter und Klima?", ""),
    ("Wie koche ich ein weiches Ei?", ""),
    ("Wer hat die Relativitätstheorie erfunden?", ""),
    ("Was bedeutet das Wort Melancholie?", ""),
    ("Schreib mir ein Gedicht über den Herbst", ""),
    ("Wie viele Einwohner hat Kanada?", ""),
    ("Gib mir ein Rezept für Pfannkuchen", ""),
    ("Was ist ein Schaltjahr?", ""),
    ("Warum ist der Himmel blau?", ""),
    ("Wie lange braucht Licht von der Sonne zur Erde?", ""),
    ("Hilf mir bei einer Geburtstagsrede für meinen Vater", ""),
    ("Was heißt Fenster auf Englisch?", ""),
    ("Wie viel Uhr ist es in New York?", ""),
    # a second batch, written after the rules above were improved and never used for them (honest check, 14.10.)
    ("Ist im Kinderzimmer noch Licht?", "smarthome"),
    ("Stell die Heizung im Gästezimmer auf 19", "smarthome"),
    ("Läuft der Trockner noch?", "smarthome"),
    ("Mach den Fernseher leiser", "smarthome"),
    ("Ist das Garagentor offen?", "smarthome"),
    ("Was mache ich am Sonntag?", "kalender"),
    ("Hab ich heute Nachmittag noch was?", "kalender"),
    ("Wann ist das nächste Elterngespräch?", "kalender"),
    ("Leg mir für Freitag 18 Uhr Kino an", "kalender"),
    ("Sind neue Mails von Amazon da?", "mail"),
    ("Hat die Schule geantwortet?", "mail"),
    ("Lösch die Werbemails", "mail"),
    ("Schreib Max, dass er den Schlüssel mitnehmen soll", "nachricht"),
    ("Sag allen im Haus Gute Nacht", "nachricht"),
    ("Wie wird das Wetter in Hamburg am Freitag?", "wetter"),
    ("Kann ich heute Wäsche draußen aufhängen?", "wetter"),
    ("Wie viel Regen kommt heute?", "wetter"),
    ("Wann kommt die nächste Bahn nach Heidelberg?", "bahn"),
    ("Komme ich mit dem Bus noch rechtzeitig zum Bahnhof?", "bahn"),
    ("Kommt mein Paket heute noch?", "paket"),
    ("Wo ist die Bestellung von Otto?", "paket"),
    ("Erinner mich morgen früh an die Medikamente", "erinnerung"),
    ("Stell einen Timer für die Nudeln, 9 Minuten", "erinnerung"),
    ("Kauf noch Zwiebeln", "liste"),
    ("Was fehlt noch im Kühlschrank?", "liste"),
    ("Setz Waschmittel auf die Liste", "liste"),
    ("Wie ist die Adresse von Peter?", "kontakt"),
    ("Wann hat mein Bruder Geburtstag?", "kontakt"),
    ("Bis wann kann ich meinen Stromvertrag kündigen?", "dokument"),
    ("Zeig mir die letzte Gasrechnung", "dokument"),
    ("Wie ist das Spiel Bayern gegen Dortmund ausgegangen?", "websuche"),
    ("Was kostet ein neues iPhone?", "websuche"),
    ("Gibt es heute Streik bei der Bahn?", "websuche"),
    ("Was weißt du noch über meinen Urlaub?", "gedaechtnis"),
    ("Ich trinke keinen Alkohol", "gedaechtnis"),
    ("Mach mir eine Liste der Hauptstädte als Excel", "erstellen"),
    ("Schreib einen Widerspruch gegen den Bußgeldbescheid", "erstellen"),
    ("Wie groß ist der Mount Everest?", ""),
    ("Was ist ein Primzahl?", ""),
    ("Erklär mir, wie Photosynthese funktioniert", ""),
    ("Wie viele Tage hat der Februar?", ""),
    ("Welche Farbe hat ein Flamingo?", ""),
    # a third batch for the functions added since (16.10.): telephone, chats, pictures, the Spark's state, and tools
    # the Weiche keeps by their own word („@tool“: the module's fixed word rule offers it, whatever the group)
    ("Kannst du mich heute Abend um acht anrufen?", "erinnerung"),
    ("Ruf mich in einer Stunde an", "erinnerung"),
    ("Ruf Oma an", "iphone"),
    ("Schreib im Familienchat, dass ich später komme", "nachricht"),
    ("Hat jemand im Chat geschrieben?", "nachricht"),
    ("Was hat Anna im Chat geschrieben?", "nachricht"),
    ("Starte einen Videoanruf mit Anna", ""),
    ("Zeichne mir ein Einhorn", "bild"),
    ("Mal ein Ausmalbild mit Dinos", "bild"),
    ("Male ein Bild von unserem Hund am Strand", "bild"),
    ("Läuft alles?", "zustand"),
    ("Welche Version läuft gerade?", "zustand"),
    ("Ist der Spark erreichbar?", "spark+zustand"),
    ("Was hast du heute für mich erledigt?", "erstellen"),
    ("Wie richte ich den Terminal-Client ein?", "spark"),
    ("Starte das Terminal", ""),
    ("Mach leiser", "@speaker_volume"),
    ("Lautstärke auf 40", "@speaker_volume"),
    ("Sprich lauter", "@speaker_volume"),
    ("Mach das rückgängig", "@undo_last"),
    ("Nimm das zurück", "@undo_last"),
    ("Meld dich heute nicht mehr", "@proactive_pause"),
    ("Keine Meldungen bis morgen", "@proactive_pause"),
    ("Ist die Synology voll?", "@nas_zustand"),
    ("Wie viel Platz ist noch auf dem NAS?", "@nas_zustand"),
    ("Was ist noch offen?", "@offen_zeigen"),
    ("Gibt es noch offene Sachen?", "@offen_zeigen"),
    ("Leg die Rechnung auf der NAS ab", "dokument+@nas_ablegen"),
    ("Schick den Artikel aufs reMarkable", "@remarkable_page"),
    ("Was liegt auf meinem reMarkable?", "@remarkable_library"),
    ("Rechne 19 Prozent von 249 Euro aus", "@rechnen"),
    ("Wie viele Tage sind es noch bis Weihnachten?", "@rechnen"),
    ("Was sind 3,5 Prozent Zinsen auf 12000 Euro im Jahr?", "@rechnen"),
]


def byword(tool, text):
    """True when the module that offers `tool` only by the person's own word would offer it for `text` (its fixed
    word rule; werkzeug_abdeckung.BY_WORD). Rights and set-up are not part of the measure."""
    import aendern
    import nasablage
    import naszustand
    import rechnen
    import remarkable
    import vorgaenge
    words = {"speaker_volume": aendern.VOLUME_WORDS, "undo_last": aendern.UNDO_WORDS,
             "proactive_pause": aendern.PAUSE_WORDS, "nas_ablegen": nasablage.WORDS, "nas_zustand": naszustand.WORDS,
             "remarkable_page": remarkable.WORDS, "remarkable_library": remarkable.WORDS,
             "offen_zeigen": vorgaenge.WORDS, "rechnen": rechnen.WORDS}
    return bool(words[tool].search(text))


def _groups(want):
    return {w for w in want.split("+") if w and not w.startswith("@")}


def _ok(names, want, q=""):
    return set(names) == _groups(want) and all(byword(w[1:], q) for w in want.split("+") if w.startswith("@"))


def measure(classify, rows=None):
    """Every sentence through `classify` (text -> intent.Route): the counts per kind and the sentences that are
    open or wrong (for the Weiche page)."""
    out = {"n": 0, "richtig": 0, "geschuetzt": 0, "offen": 0, "falsch": 0, "rows": []}
    for q, want in (ALLTAG if rows is None else rows):
        r = classify(q)
        names = [] if r.names == ["plaudern"] else r.names
        hints = getattr(r, "hints", {}) or {}
        if _ok(names, want, q):
            kind = "richtig"
        elif names and set(names) != _groups(want):
            kind = "falsch"
        elif _groups(want) and _groups(want) <= set(hints):
            kind = "geschuetzt"
        else:
            kind = "offen"
        out["n"] += 1
        out[kind] += 1
        if kind != "richtig":
            out["rows"].append({"q": q, "want": want, "got": "+".join(names), "hint": "+".join(hints), "kind": kind})
    return out
