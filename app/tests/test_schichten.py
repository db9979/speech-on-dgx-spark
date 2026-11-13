"""Schichten statt Knäuel (Kritische Prüfung 2026-11-12 point 5, docs/de/richtlinien.md Teil 17): how the panel's
modules may import each other. Measured on V01.1.395: at module level the imports form layers (the only cycles are
the chat family and the dungeon's core, MODUL_KREISE), but imports inside functions tie 296 of the panel's modules into
one big cycle: every one of them reaches every other, so none can be loaded, tested or replaced alone
(intent.py, plain rules, pulls in icalendar).

Three rules, each a ratchet like test_aufraeumen (the lists and numbers only shrink):
- a  GRUND, the bottom layer: these modules import no panel module outside GRUND, not even inside a function. A module
     that became clean may join (the test names it); none leaves.
- b  KNOTEN_ALT: the modules in the big cycle on V01.1.395 (plus KNOTEN_TUEREN, doors with their reason). A new module
     never joins it; one that left must be taken out of the list in the same commit.
- c  LOKAL_MAX: imports of panel modules inside functions (the way around a cycle). Never more; fewer lowers it.
And at module level no cycle beyond MODUL_KREISE.

Reads only app/panel, so it runs in the app/-only copy too. No wall clock dependence.
"""
import ast
import glob
import os
import sys
import unittest

PANEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "panel")
GRUND = ("aktiv", "arbeiter", "ausleiten", "beobachten", "dateien", "docrender", "dungeon_ablage", "dungeon_balance",
         "dungeon_bestiarium", "dungeon_einordnung", "dungeon_legenden", "dungeon_tabellen", "dungeon_vorlesen",
         "embed_worker", "folien", "kalenderspiegel", "kalserie", "kontaktkarte", "kopplung", "latency", "pdftabellen",
         "quellenangabe", "rechenteile", "schwachstellen_stand", "schwer", "signatur", "sse", "steckbrief", "steuer", "stoppwort", "stufen", "symbole", "taten",
         "technik_seiten", "technik_seiten_anfrage", "technik_seiten_daten", "technik_seiten_geraete",
         "technik_seiten_kern", "technik_seiten_modelle", "technik_seiten_netz", "technik_seiten_zugang", "telefon_ton",
         "undo", "vault", "wege", "werkzeug_abdeckung", "werkzeuge")
CHAT_KREIS = {"chat", "chat_modell", "chat_ton", "chat_tools", "chat_turn"}
DUNGEON_KREIS = {"dungeon", "dungeon_auto", "dungeon_geschichten", "dungeon_gesicht"}
MODUL_KREISE = (CHAT_KREIS, DUNGEON_KREIS)   # the cycles at module level on V01.1.395: they may only shrink
LOKAL_MAX = 2942
KNOTEN_ALT = ('ablauf', 'abschrift', 'account', 'ack', 'admin', 'aendern', 'agent', 'android', 'angriffsprobe', 'anrufe',
    'answercheck', 'antwortvorschlag', 'apns', 'appmerken', 'appupdate', 'auftragsplan', 'auslassen', 'auswertung',
    'backup', 'bedienen', 'befund', 'begleiter', 'berater', 'berater_katalog', 'bilder', 'calendars', 'chat',
    'chat_modell', 'chat_ton', 'chat_tools', 'chat_turn', 'chats', 'chatsec', 'coadmin', 'codeauftrag', 'contacts',
    'core', 'dienstwacht', 'docembed', 'doclingdienst', 'docmake', 'documents', 'doklink', 'dungeon', 'dungeon_alarm',
    'dungeon_album', 'dungeon_anleiten', 'dungeon_auftraege', 'dungeon_auto', 'dungeon_buch', 'dungeon_chronik',
    'dungeon_dingbild', 'dungeon_echt', 'dungeon_ehre', 'dungeon_erzaehler', 'dungeon_erzaehlstand',
    'dungeon_fluestern', 'dungeon_fraktionen', 'dungeon_gast', 'dungeon_geben', 'dungeon_gedanken',
    'dungeon_gefaehrte', 'dungeon_geschichten', 'dungeon_gesicht', 'dungeon_gold', 'dungeon_grenzen',
    'dungeon_haltung', 'dungeon_helfen', 'dungeon_ideen', 'dungeon_import', 'dungeon_kalender', 'dungeon_kampf',
    'dungeon_karte', 'dungeon_knapp', 'dungeon_kommentar', 'dungeon_lied', 'dungeon_mitkommen', 'dungeon_musik',
    'dungeon_mut', 'dungeon_narben', 'dungeon_nsc', 'dungeon_orakel', 'dungeon_personen', 'dungeon_protokoll',
    'dungeon_pruefstand', 'dungeon_quest', 'dungeon_rast', 'dungeon_regelseite', 'dungeon_reise',
    'dungeon_rueckfrage', 'dungeon_runen', 'dungeon_schreiber', 'dungeon_schrift', 'dungeon_sicht',
    'dungeon_sprachen', 'dungeon_stimmen', 'dungeon_tageszeit', 'dungeon_tiefe', 'dungeon_umgebung',
    'dungeon_wandern', 'dungeon_wappen', 'dungeon_warten', 'dungeon_wunsch', 'dungeon_zeugen', 'dungeon_zufall',
    'echo', 'einladung', 'einordnen', 'entwickelnseite', 'esp32', 'extras', 'faelle', 'features', 'feeds', 'fernals',
    'fernanker', 'fernbild', 'ferndateien', 'ferngross', 'fernnotiz', 'fernordner', 'fernsicht', 'fernsshtermy',
    'fernweb', 'fernwindows', 'fernzugang', 'fixes', 'fremdstimme', 'frisch', 'fuerdich', 'fund', 'fundmail',
    'fundmessung', 'fundquellen', 'gedaechtnis', 'gehaeuse', 'gemerkt', 'geraetebild', 'geraeteupdate', 'geteilt',
    'ghtoken', 'guard', 'halive', 'hamelden', 'health', 'hilfe', 'hintergrund', 'hoerstueck', 'hoerstueck_diskussion',
    'hoerwoerter', 'homeassistant', 'ichweiss', 'images', 'intent', 'intent_alltag', 'intent_bench', 'iphone', 'join',
    'kalenderserver', 'kiwix', 'klaeren', 'klartext', 'kontaktserver', 'laufend', 'listendav', 'live', 'llm',
    'llmapi', 'logfilter', 'lokal', 'loopwacht', 'mail', 'mailansicht', 'mailcode', 'mailidle', 'mailregeln',
    'mailstil', 'mailvorrat', 'mappen', 'mcp', 'mcpserver', 'meinedaten', 'meinmcp', 'meldung', 'memtidy', 'messages',
    'mfa', 'mitschreiblink', 'mitteilungen', 'modellseite', 'monitor', 'musik', 'nachsortieren', 'nas', 'nasablage',
    'nashilfe', 'nasquelle', 'naszustand', 'netguard', 'netproxy', 'notaus', 'notbetrieb', 'offline', 'offsite',
    'onboard', 'openwebui', 'parcels', 'passkey', 'pebblewatch', 'postfach', 'praxistest', 'proactive', 'profiles',
    'pruefzugang', 'push', 'quality', 'quellen', 'recall', 'rechnen', 'rechnerblick', 'remarkable', 'rmaufgaben',
    'rmliste', 'rmpapier', 'rmplus', 'roles', 'room', 'roomfar', 'roomlive', 'rufen', 'rundlauf', 'saetze',
    'satzende', 'schirm', 'schreib', 'senden', 'siegel', 'sofort', 'sparkkalender', 'speakers', 'speicher', 'spkcode',
    'spontanhilfe', 'spontansteuern', 'stille', 'stimmdesign', 'stufe', 'suchpruefung', 'system', 'systemone',
    'systemupdates', 'tagebuch', 'tasks', 'technik', 'technik_knoten', 'telefon', 'telefon_anruf', 'telefon_ich',
    'telegram', 'terminal', 'tidy', 'tipps', 'today', 'tonteile', 'tracelog', 'transit', 'umziehen', 'update',
    'verbrauch', 'verbund', 'verbundgruppe', 'verlauf', 'vorab', 'vorgaenge', 'vorrang', 'vorrat', 'vorwaermen',
    'wachposten', 'wartung', 'watch', 'weather', 'weiche', 'weiche_unklar', 'werkstattseite', 'wiki', 'wissen',
    'wissensbuch', 'wissensdoppelt', 'wissenskarte', 'wissensmessung', 'wyoming', 'ytquelle', 'zertpin', 'zustand_wz',
    'zustellung', 'zwischenruf')
# Doors (Kritische Prüfung point 7): a module that takes many imports of the knot onto one way in. It sits in the knot
# only because the modules behind it still import their callers; it leaves with them. Each with its reason.
KNOTEN_TUEREN = {
    "dungeon_live": "V01.1.399: replaces live.snapshot's 41 imports of game modules by one",
}


def graph():
    """module -> (panel modules it imports anywhere, those at module level), and the count of imports in functions."""
    files = {os.path.basename(p)[:-3]: p for p in glob.glob(os.path.join(PANEL, "*.py"))}
    out, local = {}, 0
    for mod, path in files.items():
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        top = {id(n) for n in tree.body}
        every, upper = set(), set()
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module] if isinstance(node, ast.ImportFrom) and node.level == 0 else []
            for name in names:
                if name in files and name != mod:
                    every.add(name)
                    if id(node) in top:
                        upper.add(name)
                    else:
                        local += 1
        out[mod] = (every, upper)
    return out, local


def cycles(edges):
    """The strongly connected parts with more than one module (Tarjan, iterative)."""
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 10000))
    idx, low, stack, on, found, n = {}, {}, [], set(), [], [0]

    def visit(v):
        idx[v] = low[v] = n[0]
        n[0] += 1
        stack.append(v)
        on.add(v)
        for w in edges[v]:
            if w not in idx:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], idx[w])
        if low[v] == idx[v]:
            part = set()
            while True:
                w = stack.pop()
                on.discard(w)
                part.add(w)
                if w == v:
                    break
            if len(part) > 1:
                found.append(part)
    for v in sorted(edges):
        if v not in idx:
            visit(v)
    return found


G, LOCAL = graph()


class Schichten(unittest.TestCase):
    def test_a_the_bottom_layer_imports_only_itself(self):
        grund = set(GRUND)
        bad = {m: sorted(G[m][0] - grund) for m in GRUND if m in G and G[m][0] - grund}
        self.assertEqual(bad, {}, "a module of GRUND imports one above it: move the shared part down, never the import "
                                  "into a function")
        gone = sorted(m for m in GRUND if m not in G)
        self.assertEqual(gone, [], "a module of GRUND no longer exists: take it out of GRUND")
        joins = sorted(m for m in G if m not in grund and G[m][0] <= grund)
        self.assertEqual(joins, [], "these modules import only GRUND now: add them to GRUND (the layer only grows)")

    def test_b_no_new_module_joins_the_big_cycle(self):
        big = max(cycles({m: e for m, (e, _) in G.items()}), key=len, default=set())
        known = set(KNOTEN_ALT) | set(KNOTEN_TUEREN)
        self.assertEqual(sorted(big - known), [], "these modules joined the big import cycle: import only "
                                                             "downwards (GRUND, then the abilities, then the flow)")
        self.assertEqual(sorted(known - big), [], "these modules left the big cycle: take them out of KNOTEN_ALT "
                                                   "or KNOTEN_TUEREN")

    def test_c_imports_inside_functions_only_get_fewer(self):
        self.assertLessEqual(LOCAL, LOKAL_MAX, "a new import of a panel module inside a function hides a cycle: put the "
                                               "shared part into a lower module instead")
        self.assertEqual(LOCAL, LOKAL_MAX, f"fewer imports inside functions: lower LOKAL_MAX to {LOCAL}")

    def test_d_no_new_cycle_at_module_level(self):
        parts = cycles({m: u for m, (_, u) in G.items()})
        self.assertEqual([sorted(p) for p in parts if not any(p <= k for k in MODUL_KREISE)], [],
                         "a new import cycle at module level")


if __name__ == "__main__":
    unittest.main()
