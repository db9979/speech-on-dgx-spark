"""KI-Dungeon-Master: the anchor of every field the model fills (Dominik 2026-10-28 „es kommen zu viele fehler aktuell
… mache mir vorschläge“, proposal 3, „ok“).

Every field of every answer the model gives the game (its JSON schemas) stands here with the fixed rule that holds it,
so no model answer changes the game unless the panel can check it. test_dungeon_anker compares this table with the
schemas: a new field without an anchor turns the test red, and so does an anchor whose check is gone.

ANKER: schema → {field path: (art, the check that holds it)}. A path is the field's way through the JSON („npc[].name“
is the name of each npc). The kinds (ARTEN):
  worte     only words to show or read aloud (plain, the round's refused words); they change no rule of the game
  liste     only one value of a fixed list of the panel (an enum or true/false)
  angebot   only an id or a name the panel offered in this turn (the foes of the offer, the map's places, open threads)
  gruppe    only a name of the heroes at the table
  erzaehlt  counts only when the narration names it (a fixed check of the text: a merchant, a person, a thing, a goal)
  panel     the panel decides by its own rules or dice; the model's value is at most a wish (damage by a failed check,
            loot by the panel's roll, the difficulty by its table, a fight's end by the panel's own check)
"""

ARTEN = ("worte", "liste", "angebot", "gruppe", "erzaehlt", "panel")

_STIMME = {f"npc[].stimme.{k}": ("liste", "dungeon_stimmen.schema") for k in ("alter", "geschlecht", "klang", "wesen", "tempo")}

ANKER = {
    "dungeon.SCHEMA_ERZAEHLEN": {
        "erzaehlung": ("worte", "dungeon.check_story"),
        "npc[].name": ("worte", "dungeon.check_story"),        # „keine“ is no speaker (nsc.LEERWORTE)
        "npc[].sagt": ("worte", "dungeon.check_story"),
        **_STIMME,
        "folgen[].wer": ("gruppe", "dungeon.check_story"),
        "folgen[].art": ("liste", "dungeon.check_story"),     # never healing, never damage in a fight
        "folgen[].zahl": ("panel", "dungeon.grounded"),       # damage only with a failed check of the body as its reason
        "beute[].anlass": ("panel", "dungeon.give_loot"),     # the panel rolls the find, one find a place
        "beute[].name": ("worte", "dungeon.give_loot"),
        "beute[].satz": ("worte", "dungeon.give_loot"),
        "erfolg[].art": ("erzaehlt", "dungeon.goal_told"),    # a goal only with words of the plan's goal in the narration
        "begegnung[].id": ("angebot", "dungeon_kampf.check_encounter"),
        "begegnung[].allein": ("panel", "dungeon_kampf.check_encounter"),   # the counts by fill, never the model's
        "kampf_ende": ("panel", "dungeon_kampf.apply"),       # peace and flight only by the panel's own check
        "szene.ort": ("worte", "dungeon.fund_ort"),           # where a find counts: the map's place first
        "szene.stimmung": ("worte", "dungeon.check_story"),
        "szene.tageszeit": ("liste", "dungeon.tageszeit_ok"),   # only forward, never evening to morning
        "szene.ort_id": ("angebot", "dungeon_karte.ort_id"),
        "haendler.name": ("erzaehlt", "dungeon.check_story"),   # a merchant only when the narration shows one
        "haendler.satz": ("worte", "dungeon.check_story"),
        "frage_an": ("gruppe", "dungeon.check_story"),
        "akt_fertig": ("erzaehlt", "dungeon.step_act"),       # the act's turning point named, AKT_MIN turns run
        "auftrag": ("worte", "dungeon.check_opening"),
        "wege": ("worte", "dungeon.check_opening"),
        "haken[].wer": ("gruppe", "dungeon.check_opening"),
        "haken[].text": ("worte", "dungeon.check_opening"),
        "bild": ("worte", "dungeon.picture_text"),
        "faeden.neu": ("worte", "dungeon_erzaehler.check_threads"),
        "faeden.erledigt": ("angebot", "dungeon_erzaehler.check_threads"),   # only a thread that is open
        "dinge[].name": ("erzaehlt", "dungeon_erzaehler.check_things"),
        "dinge[].merkmale": ("worte", "dungeon_erzaehler.check_things"),
        "nsc[].name": ("erzaehlt", "dungeon_nsc.check"),
        "nsc[].held": ("erzaehlt", "dungeon_nsc.check"),
        "nsc[].haltung": ("liste", "dungeon_nsc.check"),      # one step per hero and turn
        "nsc[].kante": ("liste", "dungeon_nsc.check"),
        "nsc[].ziel": ("erzaehlt", "dungeon_nsc.check"),
        "fraktionen[].name": ("erzaehlt", "dungeon_fraktionen.check"),
        "fraktionen[].wirkung": ("liste", "dungeon_fraktionen.check"),
        "quest_fund[].wer": ("gruppe", "dungeon_quest.check"),
        "quest_fund[].name": ("erzaehlt", "dungeon_quest.check"),
        "quest_fund[].info": ("worte", "dungeon_quest.check"),
        "schriftstueck.titel": ("erzaehlt", "dungeon_schrift.check"),   # a writing only when the narration shows one
        "schriftstueck.text": ("worte", "dungeon_schrift.check"),
        "schriftstueck.art": ("liste", "dungeon_schrift.check"),
        "schriftstueck.von": ("worte", "dungeon_schrift.check"),
        "helden_sagen[].name": ("gruppe", "dungeon_kommentar.check"),
        "helden_sagen[].sagt": ("worte", "dungeon_kommentar.check"),
        "fremd.name": ("worte", "dungeon_sprachen.check"),
        "fremd.volk": ("liste", "dungeon_sprachen.check"),
        "fremd.sagt": ("worte", "dungeon_sprachen.check"),
        "wunsch_erfuellt": ("erzaehlt", "dungeon_wunsch.check"),   # the wish hero acted and is named
        "ooc[].wer": ("gruppe", "dungeon.check_story"),
        "ooc[].text": ("worte", "dungeon.check_story"),
    },
    "dungeon.schema_proben": {
        "proben[].wer": ("gruppe", "dungeon.check_proben"),   # only a seat that acted this turn
        "proben[].wert": ("panel", "dungeon.fitting_value"),
        "proben[].stufe": ("panel", "dungeon.probe_stufe"),   # the model names a level, the panel's table sets the SG
        "proben[].vorteil": ("liste", "dungeon.check_proben"),
        "proben[].ziel": ("angebot", "dungeon.check_proben"),
        "proben[].wofuer": ("worte", "dungeon.check_proben"),
    },
    "dungeon.SCHEMA_PLAN": {
        **{k: ("worte", "dungeon.check_plan") for k in ("titel", "idee", "ziel", "gegner", "orte", "akte[].titel",
                                                         "akte[].inhalt", "akte[].wende", "akte[].ding", "akte[].spuren")},
        "akte[].zuege": ("panel", "dungeon.check_plan"),      # AKT_ZUEGE, the panel moves the act on after AKT_UEBER
    },
    "dungeon.SCHEMA_BISHER": {"bisher": ("worte", "dungeon.check_summary")},
    "dungeon_erzaehler.SCHEMA_KURZ": {"kurz": ("worte", "dungeon_erzaehler.summarize")},
    "dungeon_erzaehler.SCHEMA_WAHRHEIT": {
        "personen[].name": ("panel", "dungeon_nsc.no_person"),   # only names that are people
        **{k: ("worte", "dungeon_erzaehler.check_truth") for k in ("personen[].rolle", "personen[].ziel", "personen[].sprache",
                                                                    "gruppen[].name", "gruppen[].will", "geheimnisse")},
    },
    "dungeon_fluestern.SCHEMA": {
        "antwort": ("worte", "dungeon_fluestern.check"),
        "haltung": ("liste", "dungeon_fluestern.keep"),       # one step a whisper
        "gold": ("panel", "dungeon_fluestern.keep"),          # at most GESCHENK, once a person, only when fond
    },
    "dungeon_grenzen.SCHEMA": {"text": ("worte", "dungeon_grenzen.retell")},   # the X card: told again, the same word lists
    "dungeon_schreiber.SCHEMA": {
        "aenderungen[].art": ("liste", "dungeon_schreiber.take"),
        "aenderungen[].wer": ("erzaehlt", "dungeon_schreiber.take"),   # a hero the narration names
        "aenderungen[].zahl": ("erzaehlt", "dungeon_schreiber.take"),  # the number stands in the narration, within the limits
        "aenderungen[].name": ("erzaehlt", "dungeon_schreiber.take"),  # a thing on the ground, a place, a new person named
    },
}
