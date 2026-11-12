"""The Dungeon-Master's numbers for Zustand → Live (Kritische Prüfung 2026-11-12 point 7): one way in from live.py instead
of forty imports of game modules in live.snapshot. Each part gives only numbers (its own for_live/counts), a part that
fails shows as empty, the game's own switch decides whether the parts are asked at all."""


def for_live():
    """{"on": …, part: numbers} of the game and each of its parts."""
    try:
        import dungeon
        dgn = dungeon.for_live()
    except Exception:
        dgn = {"on": False}
    try:   # Bilder für Ausrüstung und Zauber (dungeon_dingbild.py): numbers on the game's line
        import dungeon_dingbild
        dgn["ding"] = dungeon_dingbild.for_live() if dgn.get("on") else {"on": False}
    except Exception:
        dgn["ding"] = {"on": False}
    try:   # Gesichter für NSCs (dungeon_gesicht.py): numbers on the game's line
        import dungeon_gesicht
        dgn["gesicht"] = dungeon_gesicht.for_live() if dgn.get("on") else {"on": False}
    except Exception:
        dgn["gesicht"] = {"on": False}
    try:   # Wappen für Gruppe und Fraktionen (dungeon_wappen.py): numbers on the game's line
        import dungeon_wappen
        dgn["wappen"] = dungeon_wappen.for_live() if dgn.get("on") else {"on": False}
    except Exception:
        dgn["wappen"] = {"on": False}
    try:   # Heldenlied des Barden (dungeon_lied.py): numbers on the game's line
        import dungeon_lied
        dgn["lied"] = dungeon_lied.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["lied"] = {}
    try:   # Echte Würfel am Tisch (dungeon_echt.py): numbers on the game's line
        import dungeon_echt
        dgn["echt"] = dungeon_echt.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["echt"] = {}
    try:   # Runen und Sockel (dungeon_runen.py): numbers on the game's line
        import dungeon_runen
        dgn["runen"] = dungeon_runen.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["runen"] = {}
    try:   # Spielleiter gibt Dinge (dungeon_geben.py): numbers on the game's line
        import dungeon_geben
        dgn["geben"] = dungeon_geben.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["geben"] = {}
    try:   # Helden kommentieren selbst (dungeon_kommentar.py): numbers on the game's line
        import dungeon_kommentar
        dgn["kommentar"] = dungeon_kommentar.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["kommentar"] = {}
    try:   # Lagerfeuer und Rast (dungeon_rast.py): numbers on the game's line
        import dungeon_rast
        dgn["rast"] = dungeon_rast.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["rast"] = {}
    try:   # Reise-Etappen (dungeon_reise.py): numbers on the game's line
        import dungeon_reise
        dgn["reise"] = dungeon_reise.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["reise"] = {}
    try:   # Sprachen der Völker (dungeon_sprachen.py): numbers on the game's line
        import dungeon_sprachen
        dgn["sprachen"] = dungeon_sprachen.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["sprachen"] = {}
    try:   # Kalender der Welt (dungeon_kalender.py): numbers on the game's line
        import dungeon_kalender
        dgn["kalender"] = dungeon_kalender.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["kalender"] = {}
    try:   # Zeugen-Regel (dungeon_zeugen.py): numbers on the game's line
        import dungeon_zeugen
        dgn["zeugen"] = dungeon_zeugen.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["zeugen"] = {}
    try:   # Wandernde Personen and Kleine Gesten (dungeon_wandern.py): numbers on the game's line
        import dungeon_wandern
        dgn["wandern"] = dungeon_wandern.for_live() if dgn.get("on") else {}
        import dungeon_warten
        dgn["wandern"].update({"gesten_" + k: v for k, v in dungeon_warten.gesten_live().items()} if dgn.get("on") else {})   # the idle time's side
    except Exception:
        dgn["wandern"] = {}
    try:   # Aufträge von Personen (dungeon_auftraege.py): numbers on the game's line
        import dungeon_auftraege
        dgn["auftraege"] = dungeon_auftraege.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["auftraege"] = {}
    try:   # Gedanken lesen (dungeon_gedanken.py): numbers on the game's line
        import dungeon_gedanken
        dgn["gedanken"] = dungeon_gedanken.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["gedanken"] = {}
    try:   # Überreden zum Mitkommen (dungeon_mitkommen.py): numbers on the game's line
        import dungeon_mitkommen
        dgn["mitkommen"] = dungeon_mitkommen.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["mitkommen"] = {}
    try:   # Spieler anleiten and Fortschritt der Geschichte (dungeon_anleiten.py): numbers on the game's line
        import dungeon_anleiten
        c = dungeon_anleiten.for_live() if dgn.get("on") else {}
        dgn["fortschritt"] = {k: c.pop(k, 0) for k in dungeon_anleiten.KERN_ZAEHLER}
        dgn["anleiten"] = c
    except Exception:
        dgn["anleiten"], dgn["fortschritt"] = {}, {}
    try:   # Tageszeit vom Panel (dungeon_tageszeit.py): numbers on the game's line
        import dungeon_tageszeit
        dgn["tageszeit"] = dungeon_tageszeit.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["tageszeit"] = {}
    try:   # Chronikbuch (dungeon_chronik.py): numbers on the game's line
        import dungeon_chronik
        dgn["chronik"] = dungeon_chronik.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["chronik"] = {}
    try:   # Heldenbuch aufs reMarkable (dungeon_buch.py): numbers on the game's line
        import dungeon_buch
        dgn["buch"] = dungeon_buch.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["buch"] = {}
    try:   # Personen-Katalog (dungeon_personen.py): numbers on the game's line
        import dungeon_personen
        dgn["personen"] = dungeon_personen.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["personen"] = {}
    try:   # Gefährten anheuern (dungeon_gefaehrte.py): numbers on the game's line
        import dungeon_gefaehrte
        dgn["gefaehrte"] = dungeon_gefaehrte.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["gefaehrte"] = {}
    try:   # Herzenswunsch (dungeon_wunsch.py): numbers on the game's line
        import dungeon_wunsch
        dgn["wunsch"] = dungeon_wunsch.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["wunsch"] = {}
    try:   # Flüstern mit einer Figur (dungeon_fluestern.py): numbers on the game's line
        import dungeon_fluestern
        dgn["fluestern"] = dungeon_fluestern.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["fluestern"] = {}
    try:   # Alarm und Fackeln (dungeon_alarm.py): numbers on the game's line
        import dungeon_alarm
        dgn["alarm"] = dungeon_alarm.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["alarm"] = {}
    try:   # Umgebung nutzen (dungeon_umgebung.py): numbers on the game's line
        import dungeon_umgebung
        dgn["umgebung"] = dungeon_umgebung.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["umgebung"] = {}
    try:   # Gegner-Ansagen und Haltung (dungeon_haltung.py): numbers on the game's line
        import dungeon_haltung
        dgn["haltung"] = dungeon_haltung.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["haltung"] = {}
    try:   # Eigene Geschichten (dungeon_geschichten.py): numbers on the game's line
        import dungeon_geschichten
        dgn["eigene_g"] = dungeon_geschichten.for_live() if dgn.get("on") else {}   # beside the planner's count „geschichten“
    except Exception:
        dgn["eigene_g"] = {}
    try:   # Rückfrage bei unklaren Aktionen (dungeon_rueckfrage.py): numbers on the game's line
        import dungeon_rueckfrage
        dgn["rueckfrage"] = dungeon_rueckfrage.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["rueckfrage"] = {}
    try:   # Narben (dungeon_narben.py): numbers on the game's line
        import dungeon_narben
        dgn["narben"] = dungeon_narben.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["narben"] = {}
    try:   # Monster-Album (dungeon_album.py): numbers on the game's line
        import dungeon_album
        dgn["album"] = dungeon_album.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["album"] = {}
    try:   # Schriftstücke (dungeon_schrift.py): numbers on the game's line
        import dungeon_schrift
        dgn["schrift"] = dungeon_schrift.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["schrift"] = {}
    try:   # Helfen und Gruppenprobe (dungeon_helfen.py): numbers on the game's line
        import dungeon_helfen
        dgn["helfen"] = dungeon_helfen.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["helfen"] = {}
    try:   # Knapp daneben (dungeon_knapp.py): numbers on the game's line
        import dungeon_knapp
        dgn["knapp"] = dungeon_knapp.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["knapp"] = {}
    try:   # the admin's rules tab (dungeon_regelseite.py): own entries, hidden ones, pictures to choose
        import dungeon_regelseite
        dgn["regeln"] = dungeon_regelseite.counts() if dgn.get("on") else {}
    except Exception:
        dgn["regeln"] = {}
    try:   # Musik am Tisch (dungeon_musik.py): numbers on the game's line
        import dungeon_musik
        dgn["musik"] = dungeon_musik.for_live() if dgn.get("on") else {}
    except Exception:
        dgn["musik"] = {}
    return dgn
