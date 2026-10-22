"""Anleitung des IT-Krisenspiels (Dominik 2026-10-22: „eine gute Dokumentation für das Spiel … wie das Ganze
funktioniert, welche Befehle man nehmen kann und gut strukturiert … um einen guten Spieleinstieg zu haben“, „1“ = own
tab „Anleitung“ in the game). The texts are fixed here in German and English; every number, every command, every
scenario and every achievement comes from the code itself (krisenspiel, krisenkonsole, krisenlinux), so the guide is
complete and never out of date. build() returns sections of blocks the page shows (static/js/krisenspiel.js, each
text through esc, never markup):
    {"id", "titel": [de, en], "bloecke": [{"art": "p"|"liste"|"tabelle"|"code", ...}]}
p: "text" [de, en]; liste: "punkte" [[de, en]]; tabelle: "kopf" [[de, en]], "zeilen" [[cell]] where a cell is a
string or [de, en]; code: "zeilen" [str]."""
import krisenkonsole
import krisenlinux


def _p(de, en):
    return {"art": "p", "text": [de, en]}


def _liste(*punkte):
    return {"art": "liste", "punkte": [list(x) for x in punkte]}


def _tabelle(kopf, zeilen):
    return {"art": "tabelle", "kopf": [list(x) for x in kopf], "zeilen": zeilen}


def _code(*zeilen):
    return {"art": "code", "zeilen": list(zeilen)}


def _sek(i, de, en, *bloecke):
    return {"id": i, "titel": [de, en], "bloecke": list(bloecke)}


def _beispiel(name, spec):
    """The example of a command: its usage without [optional parts] (the same rule as krisenlinux.help_lines)."""
    return next(x for x in krisenlinux.help_lines(name, False, spec) if x.startswith("Beispiel: "))[len("Beispiel: "):]


def befehle():
    """Every command by group: (key, [de, en], [(name, [de, en], example)]). From LINUX and BEFEHLE, nothing by hand."""
    out = []
    for key, (de, en) in krisenlinux.GRUPPEN.items():
        rows = [(n, [s[3], s[4]], _beispiel(n, s)) for n, s in sorted(krisenlinux.LINUX.items()) if s[1] == key]
        out.append((key, [de, en], rows))
    eigene = {"konsole": lambda s: s[1] != "spiel" and s[0] is None,
              "windows": lambda s: s[1] != "spiel" and s[0] == krisenkonsole.WIN,
              "spiel": lambda s: s[1] == "spiel"}
    for key, keep in eigene.items():
        rows = [(n, [s[2], s[3]], _beispiel(n, s)) for n, s in sorted(krisenkonsole.BEFEHLE.items()) if keep(s)]
        out.append((key, list(krisenkonsole.EIGENE[key]), rows))
    return out


def build(k):
    """The guide. k: the krisenspiel module (its constants, scenarios and achievements; passed in, no import cycle)."""
    st = k.STUFEN
    ue, no, er = st["uebung"], st["normal"], st["ernstfall"]
    noten = ", ".join(f"{n} ab {p}" for p, n in k.NOTEN if p)
    noten_en = ", ".join(f"{n} from {p}" for p, n in k.NOTEN if p)
    n_cmd = len(krisenlinux.LINUX)
    S = []
    S.append(_sek("worum", "Worum es geht", "What it is about",
                  _p(f"Du leitest den IT-Notfall eines Unternehmens, {len(k.SZENARIEN)} Szenarien von Ransomware über "
                     "Stromausfall, DDoS und Datenleck bis zum Chef-Betrug. Jede Minute kostet Geld, die Geschäftsleitung "
                     "will Antworten und das Team wird müde. Du entscheidest, was als Nächstes passiert: mit Knöpfen oder "
                     "an einer Konsole wie ein echter Admin.",
                     f"You lead a company's IT emergency, {len(k.SZENARIEN)} scenarios from ransomware via power cut, DDoS "
                     "and data leak to CEO fraud. Every minute costs money, the management wants answers and the team gets "
                     "tired. You decide what happens next: with buttons or at a console like a real admin."),
                  _p("Alles ist simuliert. Das Panel rechnet jeden Wert mit festen Regeln aus den Szenario-Daten, der Zufall "
                     "kommt nur aus dem Seed. Gleicher Seed und gleiche Züge ergeben dasselbe Spiel, so könnt ihr euch "
                     "vergleichen. Kein Befehl der Konsole läuft wirklich, nichts verlässt das Spiel.",
                     "Everything is simulated. The panel works out every value by fixed rules from the scenario data, "
                     "chance comes only from the seed. The same seed and the same moves give the same game, so you can "
                     "compare. No command of the console really runs, nothing leaves the game.")))
    S.append(_sek("schnellstart", "Schnellstart in fünf Schritten", "Quick start in five steps",
                  _liste(("Reiter „Neues Spiel“: ein Szenario wählen (oder 🎲 Überraschung), Stufe Normal, Spielweise "
                          "„Knöpfe und Konsole“, Spiel starten.",
                          "Tab \"New game\": pick a scenario (or 🎲 Surprise), level Normal, how to play \"Buttons and "
                          "console\", start the game."),
                         ("Oben die Lage lesen: Zeit, Stress, Vertrauen, Moral, Budget, Schaden. Darunter die Systeme mit "
                          "Ampel und die Chronik mit dem, was gerade passiert.",
                          "Read the situation on top: time, stress, trust, morale, budget, damage. Below the systems with "
                          "traffic lights and the chronicle with what just happened."),
                         ("Zuerst eindämmen, dann verstehen, dann wiederherstellen: Ein Zug, der den Schaden stoppt, ist "
                          "fast immer der erste.",
                          "Contain first, then understand, then restore: a move that stops the damage is almost always the "
                          "first."),
                         ("Die Geschäftsleitung nicht vergessen: Ein Lagebericht hält das Vertrauen oben, eine "
                          "Lagebesprechung oder Essen die Moral.",
                          "Do not forget the management: a status report keeps trust up, a team meeting or food keeps morale up."),
                         ("Neugierig? Unten in der Konsole „help“ tippen, dann „hosts“ und „ssh <rechner>“. Jeder Befehl "
                          "erklärt sich mit „-h“.",
                          "Curious? Type \"help\" in the console below, then \"hosts\" and \"ssh <machine>\". Every command "
                          "explains itself with \"-h\"."))))
    S.append(_sek("werte", "Die Werte oben", "The values on top",
                  _tabelle([("Wert", "Value"), ("Was er bedeutet", "What it means"), ("Wann es endet", "When it ends")], [
                      [["Zeit", "Time"], ["Spielminuten bis zur Frist. Jeder Zug kostet Minuten.",
                                          "Game minutes up to the deadline. Every move costs minutes."],
                       ["bei 0: „Die Zeit ist abgelaufen“", "at 0: \"Time ran out\""]],
                      [["Stress", "Stress"], ["Steigt mit jedem ausgefallenen System. Ab 75 % sinkt die Moral bei jedem Zug.",
                                              "Rises with every system down. From 75 % morale drops with every move."],
                       ["–", "–"]],
                      [["Vertrauen", "Trust"], ["Wie sehr die Geschäftsleitung dir den Fall lässt. Sinkt, wenn der Schaden "
                                                "den Richtwert überschreitet.",
                                                "How far the management leaves you the case. Drops when the damage passes "
                                                "the benchmark."],
                       ["bei 0: der Fall wird dir entzogen", "at 0: the case is taken from you"]],
                      [["Moral", "Morale"], ["Kraft des Teams. Hoher Stress zehrt daran, Lagebesprechung und Essen helfen.",
                                             "The team's strength. High stress eats it, team meetings and food help."],
                       ["bei 0: „Das Team kann nicht mehr“", "at 0: \"The team cannot go on\""]],
                      [["Budget", "Budget"], ["Notfall-Geld für Dienstleister, Ersatzteile, Forensik. Ein Zug, den es nicht "
                                              "deckt, ist grau.",
                                              "Emergency money for contractors, spare parts, forensics. A move it does not "
                                              "cover is grey."],
                       ["kein Zug mehr möglich: Sackgasse", "no move left: dead end"]],
                      [["Schaden", "Damage"], ["Was der Ausfall kostet: jedes gestörte oder ausgefallene System pro Minute.",
                                               "What the outage costs: every degraded or failed system per minute."],
                       ["–", "–"]]]),
                  _p(f"Die Systeme haben fünf Zustände: läuft, gestört (kostet {round(k.FAKTOR['Degraded'] * 100)} % "
                     f"seines Schadens pro Minute), kritisch und aus (100 %), isoliert ({round(k.FAKTOR['Isolated'] * 100)} %, "
                     "dafür breitet sich nichts mehr aus).",
                     f"The systems have five states: running, degraded (costs {round(k.FAKTOR['Degraded'] * 100)} % of its "
                     f"damage per minute), critical and off (100 %), isolated ({round(k.FAKTOR['Isolated'] * 100)} %, but "
                     "nothing spreads any more).")))
    S.append(_sek("zuege", "Züge, Ereignisse und Zufall", "Moves, events and chance",
                  _p("Ein Zug hat feste Folgen: Er kostet Minuten und oft Budget, ändert Systeme, Stress, Vertrauen oder "
                     "Moral und schaltet neue Züge frei. Manche Züge gehen nur einmal, manche erst, wenn etwas anderes "
                     "erledigt ist. Unter jedem Knopf stehen seine Kosten.",
                     "A move has fixed effects: it costs minutes and often budget, changes systems, stress, trust or morale "
                     "and unlocks new moves. Some moves work only once, some only after something else is done. Under every "
                     "button stand its costs."),
                  _p("Nach jedem Zug läuft die Zeit: Ausgefallene Systeme kosten Schaden, und Ereignisse können eintreten "
                     "(die Ransomware erreicht den nächsten Server, der Diesel wird knapp). Dazu kommen Nebenschauplätze wie "
                     "ein Anruf der Presse. Ob sie eintreten, würfelt das Panel aus dem Seed; hoher Druck macht sie "
                     "wahrscheinlicher.",
                     "After every move time passes: failed systems cost damage, and events can happen (the ransomware "
                     "reaches the next server, the diesel runs low). On top come side issues like a call from the press. "
                     "Whether they happen the panel rolls from the seed; high pressure makes them likelier."),
                  _p("Jedes Szenario hat Varianten (wo es anfing, ob die Sicherung sauber ist …), die der Seed beim Start "
                     "wählt. Wer genau hinsieht, findet in Logs und Dateien, welche Variante gerade läuft.",
                     "Every scenario has variants (where it started, whether the backup is clean …) that the seed picks at "
                     "the start. Who looks closely finds in logs and files which variant is running.")))
    S.append(_sek("ende", "Spielende, Punkte und Noten", "End, points and grades",
                  _p("Gewonnen ist, wenn das Ziel des Szenarios erreicht ist (etwa: eingedämmt und sauber wiederhergestellt). "
                     f"Verloren ist es bei Zeit 0, Vertrauen 0, Moral 0, nach {k.MAX_ZUEGE} Zügen oder wenn kein Zug mehr "
                     "möglich ist. Aufgeben zählt als F und bringt keinen Erfolg.",
                     "You win when the scenario's goal is reached (such as: contained and cleanly restored). You lose at "
                     f"time 0, trust 0, morale 0, after {k.MAX_ZUEGE} moves or when no move is left. Giving up counts as F "
                     "and earns no achievement."),
                  _liste(("50 Punkte für den Sieg, bis zu 20 für übrige Zeit, bis zu 15 für wenig Schaden, bis zu 10 für "
                          "Vertrauen, bis zu 5 für Moral, 10 weniger bei Datenverlust.",
                          "50 points for the win, up to 20 for time left, up to 15 for little damage, up to 10 for trust, "
                          "up to 5 for morale, 10 less with data loss."),
                         (f"Nur Konsole: +{k.KONSOLE_BONUS} Punkte beim Sieg, Uhr läuft: +{k.UHR_BONUS}.",
                          f"Console only: +{k.KONSOLE_BONUS} points when won, clock running: +{k.UHR_BONUS}."),
                         (f"Noten: {noten}, darunter F.", f"Grades: {noten_en}, below that F.")),
                  _p("Die Auswertung am Ende sagt, woran es lag. „Nochmal mit diesem Seed“ spielt denselben Lauf, so "
                     "lernst du aus jedem Versuch.",
                     "The evaluation at the end says why. \"Again with this seed\" plays the same run, so you learn from "
                     "every try.")))
    S.append(_sek("stufen", "Stufen, Spielweisen und Uhr", "Levels, ways to play and clock",
                  _tabelle([("Stufe", "Level"), ("Zeit", "Time"), ("Budget", "Budget"), ("Schaden", "Damage"),
                            ("Druck", "Pressure")],
                           [[list(s["name"]), f"{s['zeit']} min", f"{round(s['budget'] * 100)} %",
                             f"{round(s['schaden'] * 100)} %", f"{round(s['druck'] * 100)} %"] for s in (ue, no, er)]),
                  _liste(("Knöpfe und Konsole: Die Züge stehen als Knöpfe da, die Konsole kann dasselbe.",
                          "Buttons and console: the moves stand as buttons, the console can do the same."),
                         (f"Nur Konsole: keine Knöpfe, jeder Zug wird getippt; +{k.KONSOLE_BONUS} Punkte beim Sieg.",
                          f"Console only: no buttons, every move is typed; +{k.KONSOLE_BONUS} points when won."),
                         (f"Uhr läuft: {k.UHR_S} echte Sekunden sind eine Spielminute, solange die Seite offen ist. Pause "
                          "nur in Übung und Normal. Sieg: +5 Punkte, ohne Pause der Erfolg „Gegen die Uhr“.",
                          f"Clock running: {k.UHR_S} real seconds are a game minute while the page is open. Pause only in "
                          "practice and normal. Win: +5 points, without a pause the achievement \"Against the clock\"."),
                         ("🎲 Überraschung: Das Panel wählt das Szenario, was passiert, siehst du erst im Spiel.",
                          "🎲 Surprise: the panel picks the scenario, what happens you see only in the game."))))
    S.append(_sek("team", "Team und Laufbahn", "Team and career",
                  _p("Du hast Kollegen. Jeder kann zwei Fächer besonders gut (Netz, Windows, Storage, Forensik, "
                     "Rechenzentrum, Kommunikation). Wähle über den Zügen „Wer übernimmt?“ einen Kollegen und dann einen "
                     "Zug: Er arbeitet ihn in Spielzeit ab, während du weiterspielst. Züge der Leitung (Budget, "
                     "Lagebesprechung, Essen) bleiben bei dir. An der Konsole: team zeigt das Team, assign <kollege> "
                     "<aufgabe> gibt eine Aufgabe ab.",
                     "You have colleagues. Each is especially good at two subjects (network, Windows, storage, forensics, "
                     "data centre, communication). Pick a colleague under \"Who takes it?\" above the moves and then a move: "
                     "they work on it in game time while you play on. Moves of the lead (budget, status meeting, food) stay "
                     "with you. At the console: team shows the team, assign <colleague> <task> hands a task over."),
                  _liste((f"Abgeben kostet dich {k.ZUWEISEN_MIN} Minuten. Im eigenen Fach braucht der Kollege "
                          f"{round(k.FACH_FAKTOR * 100)} % der Zeit des Zugs, sonst {round(k.FREMD_FAKTOR * 100)} %; ab "
                          f"{k.MUEDE_LANGSAM} % Müdigkeit {round(k.MUEDE_FAKTOR * 100)} % davon.",
                          f"Handing over costs you {k.ZUWEISEN_MIN} minutes. In their own subject the colleague needs "
                          f"{round(k.FACH_FAKTOR * 100)} % of the move's time, else {round(k.FREMD_FAKTOR * 100)} %; from "
                          f"{k.MUEDE_LANGSAM} % tiredness {round(k.MUEDE_FAKTOR * 100)} % of that."),
                         (f"Jede Aufgabe macht müde (+{k.MUEDE_FACH} % im Fach, +{k.MUEDE_FREMD} % fremd), wer frei ist, erholt "
                          f"sich je Zug um {k.MUEDE_RUHE} %, Lagebesprechung und Essen helfen allen. Bei {k.MUEDE_MAX} % "
                          "nimmt niemand mehr etwas an.",
                          f"Every task makes tired (+{k.MUEDE_FACH} % in the subject, +{k.MUEDE_FREMD} % outside), who is free "
                          f"rests {k.MUEDE_RUHE} % per move, status meeting and food help everyone. At {k.MUEDE_MAX} % nobody "
                          "takes anything any more."),
                         ("Ist die Aufgabe fertig, wirkt der Zug wie selbst gemacht (das Budget geht schon beim Abgeben weg); "
                          "die Chronik meldet es unter „Team“.",
                          "When the task is done, the move works as if done yourself (the budget goes when handing over); the "
                          "chronicle reports it under \"Team\".")),
                  _p("Laufbahn: Dein Rang kommt aus deinen gewonnenen Spielen. Höhere Ränge bringen mehr Kollegen und mehr "
                     "Notfall-Budget.",
                     "Career: your rank comes from the games you won. Higher ranks bring more colleagues and more emergency "
                     "budget."),
                  _tabelle([("Rang", "Rank"), ("Siege", "Wins"), ("Kollegen", "Colleagues"), ("Budget", "Budget")],
                           [[list(r[1]), f"{r[2]}" + (" + A" if r[3] else ""), f"{r[4]}", f"{round(r[5] * 100)} %"]
                            for r in k.RAENGE])))
    S.append(_sek("lernen", "Lernen: Tipp, Nachbesprechung, Geist", "Learning: hint, debrief, ghost",
                  _p("Nach jedem Spiel kommt die Nachbesprechung: was gut lief und was besser geht, mit der Quelle "
                     "dahinter (NIST SP 800-61, BSI-Standard 200-4, DSGVO und andere). Feste Regeln prüfen deine Züge "
                     "und ihre Reihenfolge, kein Modell.",
                     "After every game comes the debrief: what went well and what could be better, with the source behind "
                     "it (NIST SP 800-61, BSI standard 200-4, GDPR and others). Fixed rules check your moves and their "
                     "order, no model."),
                  _liste(("Lernmodus (Häkchen bei „Neues Spiel“): vor jedem Zug ein Tipp, der Knopf ist markiert. Das Panel "
                          "rechnet dafür einen Zug voraus. Ein Spiel mit Tipps bringt keine Erfolge und zählt nicht für "
                          "Laufbahn und Bestwert.",
                          "Learning mode (tick at \"New game\"): a hint before every move, its button is marked. The panel "
                          "calculates one move ahead for it. A game with hints earns no achievements and does not count "
                          "for career and best score."),
                         ("Geist: Hast du dasselbe Szenario auf derselben Stufe schon gespielt, zeigt eine Zeile, wo dein "
                          "bester Lauf nach gleich vielen Zügen stand (Minute und Schaden).",
                          "Ghost: if you played the same scenario on the same level before, a line shows where your best run "
                          "stood after as many moves (minute and damage)."),
                         ("Statistik unter „Bisherige Spiele“: je Szenario gespielt, gewonnen, Schnitt, Bestwert, "
                          "Minuten, dazu deine Noten.",
                          "Statistics under \"Past games\": per scenario played, won, average, best, minutes, and your "
                          "grades."))))
    S.append(_sek("herausforderungen", "Herausforderungen und Mutatoren", "Challenges and mutators",
                  _p("Unter „Neues Spiel“ stehen die Tages- und die Wochen-Herausforderung: dasselbe Spiel für jedes Profil "
                     "dieses Spark, gezogen aus dem Datum (Szenario, Seed, Stufe Normal, Team wie beim Rang Admin). Der erste "
                     "Versuch zählt für die Bestenliste, weitere Versuche nicht, ein Lernspiel nie. In der Liste stehst du ohne "
                     "Namen, mit deinem Namen oder gar nicht, wie du es wählst.",
                     "Under \"New game\" are the daily and the weekly challenge: the same game for every profile of this "
                     "Spark, drawn from the date (scenario, seed, level Normal, team as at the rank Admin). The first try "
                     "counts for the board, later tries do not, a learning game never. On the board you stand without a "
                     "name, with your name or not at all, as you choose."),
                  _p(f"Mutatoren sind Zusatzregeln; die Tages-Herausforderung hat {k.HERAUS['tag'][0]}, die Wochen-Herausforderung "
                     f"{k.HERAUS['woche'][0]}, im freien Spiel wählst du sie selbst. Ein Sieg bringt ihre Punkte dazu.",
                     f"Mutators are extra rules; the daily challenge has {k.HERAUS['tag'][0]}, the weekly challenge "
                     f"{k.HERAUS['woche'][0]}, in free play you pick them yourself. A win adds their points."),
                  _tabelle([("Mutator", "Mutator"), ("Regel", "Rule"), ("Punkte", "Points")],
                           [[list(n), list(t), [f"+{b}", f"+{b}"]] for _, n, t, b in k.MUTATOREN])))
    S.append(_sek("konsole", "Die Konsole", "The console",
                  _p("Unter der Chronik steht ein Terminal. Du startest auf jump01, dem Linux-Sprungrechner des Admins. "
                     "Von dort erreichst du jeden Rechner des Szenarios mit ssh. Getippte Befehle sind dieselben Züge wie "
                     "die Knöpfe, mit denselben Folgen.",
                     "Under the chronicle there is a terminal. You start on jump01, the admin's Linux jump host. From there "
                     "you reach every machine of the scenario with ssh. Typed commands are the same moves as the buttons, "
                     "with the same effects."),
                  _liste(("help zeigt alle Befehle nach Gruppen, help netz eine Gruppe mit Erklärung.",
                          "help shows all commands by group, help netz one group with explanations."),
                         ("<befehl> -h, --help, /? oder man <befehl> erklärt Aufruf, Optionen und ein Beispiel. Bei df, du, "
                          "free, ls und sort heißt -h „lesbar“, dort hilft --help.",
                          "<command> -h, --help, /? or man <command> explains usage, options and an example. With df, du, "
                          "free, ls and sort -h means \"readable\", there --help helps."),
                         ("hosts zeigt die Rechner mit Adresse, System und Zustand; ssh dc01 wechselt, exit geht zurück.",
                          "hosts shows the machines with address, system and state; ssh dc01 switches, exit goes back."),
                         ("Schaltest du einen Rechner mit sudo shutdown, poweroff oder halt aus, trennt er die Verbindung: "
                          "du bist wieder auf jump01. reboot und shutdown -r halten die Verbindung.",
                          "If you switch a machine off with sudo shutdown, poweroff or halt, it closes the connection: you "
                          "are back on jump01. reboot and shutdown -r keep the connection."),
                         ("sudo <befehl> führt einen Befehl als root aus. Ohne sudo sagt Linux „Permission denied“, wie im "
                          "echten Leben.",
                          "sudo <command> runs a command as root. Without sudo Linux says \"Permission denied\", as in real "
                          "life."),
                         ("Pipes (| grep, | head, | sort, | wc …), > und >> in Dateien, tee. Tab ergänzt Befehle, Rechner, "
                          "Dateien und Ordner (am Handy der Knopf ⇥), ↑ und ↓ holen frühere Eingaben, ein Tippfehler bekommt "
                          "„Meintest du …?“. Der Knopf „Groß“ lässt die Konsole das Fenster füllen, Esc setzt sie zurück.",
                          "Pipes (| grep, | head, | sort, | wc …), > and >> into files, tee. Tab completes commands, machines, "
                          "files and folders (the button ⇥ on a phone), ↑ and ↓ bring back earlier inputs, a typo gets "
                          "\"Did you mean …?\". The button \"Large\" lets the console fill the window, Esc puts it back."),
                         ("nano, vi und vim öffnen eine Datei im Editor. nano: Strg+O speichert, Strg+X beendet. vi: i, a "
                          "oder o zum Schreiben, Esc zurück, x und dd löschen, :w speichert, :q beendet, :wq beides, :q! "
                          "ohne Speichern. Außerhalb von /home/admin und /tmp nur mit sudo davor.",
                          "nano, vi and vim open a file in the editor. nano: Ctrl+O writes, Ctrl+X exits. vi: i, a or o to "
                          "write, Esc back, x and dd delete, :w writes, :q quits, :wq both, :q! without saving. Outside "
                          "/home/admin and /tmp only with sudo in front."),
                         ("Windows-Rechner kennen ihre eigenen Befehle (dir, type, ipconfig, Get-Service, Get-WinEvent …), "
                          "Linux-Befehle nur auf Linux und Netzgeräten.",
                          "Windows machines know their own commands (dir, type, ipconfig, Get-Service, Get-WinEvent …), "
                          "Linux commands only Linux and network devices.")),
                  _p(f"Was es kostet: Lesende Befehle (ping, ps, journalctl, type …) kosten eine Spielminute; "
                     f"{krisenkonsole.LESEN_MAX} Minuten Lesen sind ein eigener Zug „Analyse an der Konsole“. Dateien "
                     "ansehen, wechseln und Hilfe sind frei. Ein falsches Ziel (die falsche VM, das eigene Admin-Konto) "
                     "ist ein eigener Zug mit festen Folgen. Wer mit sudo systemctl stop einen Dienst eines Systems "
                     "anhält (auch kill, pkill), stört das System: 2 Minuten, Stress und 2.000 € Schaden; systemctl "
                     "start gibt es zurück, sudo reboot kostet 5 Minuten.",
                     f"What it costs: reading commands (ping, ps, journalctl, type …) cost a game minute; "
                     f"{krisenkonsole.LESEN_MAX} minutes of reading are a move of their own \"Analysis at the console\". "
                     "Looking at files, switching and help are free. A wrong target (the wrong VM, the own admin account) "
                     "is a move of its own with fixed effects. Who stops a service of a system with sudo systemctl stop "
                     "(also kill, pkill) degrades the system: 2 minutes, stress and 2,000 € damage; systemctl start gives "
                     "it back, sudo reboot costs 5 minutes."),
                  _p(f"Was du anlegst, bleibt im Spiel: Dateien, Verzeichnisse, Benutzer, Gruppen, Mounts und "
                     f"Firewall-Regeln je Rechner (höchstens {krisenlinux.SIM_MAX} Dateien je Rechner und "
                     f"{krisenlinux.SIM_BYTES // 1000} KB je Spiel). Muster bei grep, sed und find sind nur Text mit ^ und $ "
                     "beziehungsweise * und ?, keine regulären Ausdrücke.",
                     f"What you make stays in the game: files, folders, users, groups, mounts and firewall rules per machine "
                     f"(at most {krisenlinux.SIM_MAX} files per machine and {krisenlinux.SIM_BYTES // 1000} KB per game). "
                     "Patterns of grep, sed and find are plain text with ^ and $ or * and ?, no regular expressions.")))
    S.append(_sek("probieren", "Zum Ausprobieren", "To try",
                  _p("Ein kleiner Rundgang auf jump01, der nichts im Spiel kostet:",
                     "A small tour on jump01 that costs nothing in the game:"),
                  _code("help", "cat README.txt", "ls -la /etc", "grep ^admin /etc/passwd", "echo 'Lage um 9:41' > notiz.txt",
                        "echo 'ERP prüfen' >> notiz.txt", "cat notiz.txt | wc -l", "sudo useradd -m forensik",
                        "id forensik", "tar -czf fall.tgz notiz.txt", "tar -tzf fall.tgz", "awk '{print $2}' /etc/hosts | sort",
                        "find / -name 'host*'", "tar --help"),
                  _p("Und dann in die Krise: hosts, ssh auf einen Rechner, Dienste und Logs ansehen (systemctl status, "
                     "journalctl -n 20, tail /var/log/…). Die Befehle der Gruppe „Im Spiel“ sind die Züge.",
                     "And then into the crisis: hosts, ssh to a machine, look at services and logs (systemctl status, "
                     "journalctl -n 20, tail /var/log/…). The commands of the group \"In the game\" are the moves.")))
    rows = []
    for key, name, cmds in befehle():
        rows.append({"art": "p", "text": [f"**{name[0]}** (help {key}, {len(cmds)})", f"**{name[1]}** (help {key}, {len(cmds)})"]})
        rows.append(_tabelle([("Befehl", "Command"), ("Was er tut", "What it does"), ("Beispiel", "Example")],
                             [[n, what, ex] for n, what, ex in cmds]))
    S.append(_sek("befehle", "Alle Befehle", "All commands",
                  _p(f"{n_cmd} Linux-Befehle und die Befehle der Konsole, von Windows und des Spiels. Alle simuliert; "
                     "„(root)“ heißt: nur mit sudo.",
                     f"{n_cmd} Linux commands and the commands of the console, of Windows and of the game. All simulated; "
                     "\"(root)\" means: only with sudo."), *rows))
    sz = []
    for s in k._DATA["szenarien"]:
        hosts = krisenkonsole.world(s["id"])["hosts"]
        sz.append(_p(f"**{s['titel'][0]}**: {s['kurz'][0]} {len(s['assets'])} Systeme: "
                     + ", ".join(a["name"] for a in s["assets"]) + ". Rechner an der Konsole: "
                     + ", ".join(f"{h['id']} ({krisenkonsole.OS_NAMES[h['os']]})" for h in hosts) + ".",
                     f"**{s['titel'][1]}**: {s['kurz'][1]} {len(s['assets'])} systems: "
                     + ", ".join(a["name"] for a in s["assets"]) + ". Machines at the console: "
                     + ", ".join(f"{h['id']} ({krisenkonsole.OS_NAMES[h['os']]})" for h in hosts) + "."))
    S.append(_sek("szenarien", "Die Szenarien", "The scenarios", *sz))
    S.append(_sek("erfolge", "Erfolge", "Achievements",
                  _tabelle([("Erfolg", "Achievement"), ("Was es braucht", "What it takes")],
                           [[list(n), list(t)] for _, n, t in k.ERFOLGE])))
    S.append(_sek("inspector", "Inspector und Erzähler", "Inspector and narrator",
                  _p("Der Reiter „Inspector“ zeigt jeden Zug Schritt für Schritt: was du gewählt hast (Knopf, Konsole oder "
                     "Uhr), welche feste Regel mit welchen Werten gegriffen hat, wie viele Minuten Lesen und Uhr darin "
                     "stecken und welche Würfe aus dem Seed kamen.",
                     "The tab \"Inspector\" shows every move step by step: what you chose (button, console or clock), which "
                     "fixed rule applied with which values, how many minutes of reading and clock are in it and which "
                     "rolls came from the seed."),
                  _p("Mit dem Schalter „Krisenspiel mit Erzähler“ erzählt das Sprachmodell jeden Zug in zwei bis vier "
                     "Sätzen nach. Es ändert nie einen Wert; „Feste Fakten“ zeigt den Originaltext.",
                     "With the switch \"Crisis game with narrator\" the language model retells every move in two to four "
                     "sentences. It never changes a value; \"Fixed facts\" shows the original text.")))
    S.append(_sek("tipps", "Tipps für den Einstieg", "Tips for getting started",
                  _liste(("Erst die Ausbreitung stoppen: isolieren kostet wenig im Vergleich zu jedem weiteren befallenen "
                          "System.",
                          "Stop the spread first: isolating costs little compared with every further system hit."),
                         ("Vor dem Wiederherstellen prüfen, ob die Sicherung sauber ist. Ein Restore aus befallenem Backup "
                          "ist teuer.",
                          "Before restoring, check whether the backup is clean. A restore from an infected backup is "
                          "expensive."),
                         ("Reihenfolge zählt: beim SAN erst die Ursache, beim Strom erst Notstrom und Kühlung, "
                          "nach dem Strom in Reihenfolge hochfahren (Storage, Netz, Cluster).",
                          "Order matters: with the SAN the cause first, with power backup power and cooling first, "
                          "after the power start up in order (storage, network, cluster)."),
                         ("Lagebericht an die Geschäftsleitung, bevor das Vertrauen kippt, und Pizza, bevor die Moral "
                          "kippt.",
                          "A status report to the management before trust tips, and pizza before morale tips."),
                         ("An der Konsole erst lesen, dann handeln: Logs verraten die Variante. Aber Lesen kostet Zeit.",
                          "At the console read first, then act: logs give away the variant. But reading costs time."),
                         ("Ein Seed, mehrere Versuche: Mit „Nochmal mit diesem Seed“ siehst du, was ein anderer Zug "
                          "geändert hätte.",
                          "One seed, several tries: with \"Again with this seed\" you see what another move would have "
                          "changed."))))
    S.append(_sek("fragen", "Wenn etwas hakt", "When something is stuck",
                  _liste(("„command not found“: Den Befehl gibt es auf diesem Rechner nicht (Windows-Befehle nur auf "
                          "Windows). help zeigt, was hier geht.",
                          "\"command not found\": the command does not exist on this machine (Windows commands only on "
                          "Windows). help shows what works here."),
                         ("„Permission denied“: Der Befehl braucht root, sudo davor.",
                          "\"Permission denied\": the command needs root, put sudo in front."),
                         ("„refused“: Die Konsole nimmt keine ; & < ` und kein ${ oder $(.",
                          "\"refused\": the console takes no ; & < ` and no ${ or $(."),
                         ("„nothing to do right now“: Der Zug ist schon erledigt oder noch nicht möglich.",
                          "\"nothing to do right now\": the move is done already or not possible yet."),
                         ("Ein Knopf ist grau: Das Budget reicht nicht.", "A button is grey: the budget is not enough."),
                         ("„Das Spiel war schon einen Zug weiter“: Es lief auf einem anderen Gerät weiter, die Seite lädt "
                          "den neuen Stand.",
                          "\"The game was a move further already\": it went on on another device, the page loads the new "
                          "state."))))
    return S
