"""Steckbrief pro Funktion (steckbrief.py, Kritische Prüfung 2026-11-12 point 4): one place per function, the lists read it.

- every Steckbrief is complete and reaches every list it feeds (features, werkzeuge, Live, logs, Werkzeug-Abdeckung,
  Spickzettel, technik, Begleiter);
- no old table names a part of it again (rule 12: one source);
- a new function comes with a Steckbrief: OHNE_ALT, the functions without one, only shrinks (V01.1.397: all but
  „Rechnen“; V01.1.401: the group „Tempo und Genauigkeit“ moved in).

Reads only app/, so it runs in the app/-only copy too. No wall clock dependence.
"""
import ast
import os
import re
import unittest

from tests import helpers

helpers.start()
import features  # noqa: E402
import live  # noqa: E402
import logfilter  # noqa: E402
import spickzettel  # noqa: E402
import steckbrief  # noqa: E402
import technik  # noqa: E402
import werkzeug_abdeckung  # noqa: E402
import werkzeuge  # noqa: E402

PANEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "panel")
OHNE_ALT = ('ablauf', 'agent', 'android', 'androidassist', 'androidlive', 'androidlock', 'androidupdate',
            'angriffsprobe', 'anhalten', 'anrufassistent', 'anrufe', 'anrufeturn', 'appmerken', 'auftragsplan',
            'auswertungen', 'begleiter', 'begleiterbedienen', 'begleitermeeting', 'begleiterschirm', 'begleitertun',
            'beobachten', 'berater', 'beraterana', 'beraterauto', 'beraterchat', 'beratererklaeren',
            'beraterhinweis', 'beraterideen', 'beraterissue', 'beratermich', 'berateru', 'beraterundo',
            'beraterwarum', 'bewerten', 'bewertenzurueck', 'bildaendern', 'bilder', 'calendar', 'calserver',
            'calshare', 'chatgroups', 'chatinvite', 'chatmedia', 'chatprivate', 'chats', 'contacts', 'dienstnutzer',
            'dienstwacht', 'docaudio', 'docbrief', 'docfiles', 'docling', 'doclink', 'docmeaning', 'docnight',
            'docpics', 'docshared', 'documents', 'docyoutube', 'dungeon', 'dungeonbilder', 'dungeonbuecher',
            'dungeongast', 'dungeongeschichten', 'dungeonpruefstand', 'dungeonpruefung', 'eingespraech',
            'einladungen', 'entwickeln', 'entwickelnauftrag', 'entwickelngithub', 'entwickelnterminal', 'erstellen',
            'erstellenbilder', 'erstellenvorlagen', 'esp32', 'espstopp', 'feeds', 'feedsmelden', 'fernals',
            'fernbild', 'fernbildablage', 'ferngross', 'fernnotizen', 'fernordner', 'fernsshtermy', 'fernweb',
            'fernzugang', 'fernzugangalle', 'fernzuganghilfe', 'fernzugangmeldung', 'fixes', 'follow', 'fuerdich',
            'fund', 'fundchats', 'fundkontakte', 'fundlisten', 'fundmail', 'fundmedien', 'fundschlagworte',
            'fundtermine', 'gedfragen', 'gedhinweis', 'gedpruefen', 'gedthemen', 'gehaeuse', 'geraetenacht',
            'geraeteupdate', 'ha', 'hacam', 'haevent', 'halive', 'haloud', 'havoice', 'hilfe', 'hilfeseite',
            'hilfevorschlag', 'history', 'hoerstueck', 'hoerstueckdisk', 'ichweiss', 'images', 'iphone',
            'iphonepanel', 'iphonepruef', 'iphonepush', 'iphoneupdate', 'kartensuche', 'kiwix', 'klaeren',
            'klaerenmerken', 'klaerenweg', 'kontakteaendern', 'kontaktserver', 'kontingent', 'listdav', 'listlink',
            'listnote', 'listshare', 'llmapi', 'llmapiassist', 'llmapiextern', 'lokal', 'mail', 'mailcode',
            'maildelete', 'mailidle', 'maillearn', 'mailmanage', 'mailsend', 'mailstil', 'mailwichtig', 'mappen',
            'mcp', 'mcpact', 'mcpextern', 'mcpserver', 'melden', 'meldenadmin', 'memory', 'messages_all',
            'messages_announce', 'mfa', 'modelleeigen', 'modellwechsel', 'musik', 'musikbearbeiten', 'mymcp',
            'mymcpjobs', 'mymcpoauth', 'mystatus', 'nachsortieren', 'nas', 'nasablage', 'nashaushalt', 'nasquelle',
            'naszustand', 'notbetriebasr', 'notedevice', 'offlinelesen', 'openwebui', 'parcels', 'pebble',
            'pebbleantwort', 'pebblechat', 'pebbleerinnern', 'pebblefern', 'pebblefolge', 'pebblegesund',
            'pebblemeldung', 'pebblemerken', 'pebbleort', 'pebbleschnell', 'pebbletag', 'pebblezifferblatt',
            'proactive', 'remarkable', 'reminders', 'rmask', 'rmaufgaben', 'rmaufraeumen', 'rmfresh', 'rmguide',
            'rminbox', 'rmmeet', 'rmmorning', 'rmordner', 'rmpapier', 'rmsend', 'rmtodo', 'rmweb', 'rmweek', 'roles',
            'room', 'roomfar', 'roomha', 'roomtv', 'rueckgaengig', 'rundlauf', 'satzende', 'schirm', 'schreib',
            'schreibapps', 'search', 'selfecho', 'sparkzustand', 'speaker', 'speicher', 'speicherauslagern',
            'speicherlan', 'speicherordner', 'spkcode', 'spontanhilfe', 'spontansteuern', 'stimmdesign', 'style',
            'suchfragen', 'suchpruefung', 'suchschnell', 'systemnachtmodelle', 'systemnachtpanel', 'systemupdates',
            'tagebuch', 'tasks', 'teilen', 'teilenhinweis', 'telefon', 'telefonalarm', 'telefonanrufen',
            'telefonaussen', 'telefongast', 'telegram', 'terminal', 'tidy', 'tipps', 'tippspush', 'tippssaetze',
            'tippsstimme', 'transit', 'verbrauch', 'verbund', 'verbundgruppen', 'verbundmedia', 'verlaufsync',
            'vorgaenge', 'vorrang', 'wachposten', 'wartung', 'wartungauto', 'weather', 'werkstatt', 'werkstattnacht',
            'wiki', 'wissensbuch', 'wissenskarte', 'wissensknoten', 'wyoming', 'xiaozhihinweis')


def source(name):
    with open(os.path.join(PANEL, name), encoding="utf-8") as f:
        return f.read()


class Steckbrief(unittest.TestCase):
    def test_every_steckbrief_reaches_its_lists(self):
        for key, s in steckbrief.STECKBRIEFE.items():
            f = features.BY_KEY[key]
            self.assertEqual((f.de, f.en, f.group, f.admin, f.pref, f.parent, f.me, f.guide),
                             (s.de, s.en, s.gruppe, s.schalter, s.pref, s.parent, s.me, s.anleitung), key)
            self.assertIn(s.gruppe, {g[0] for g in features.GROUPS}, key)
            if s.parent:
                self.assertIn(s.parent, features.BY_KEY, key)
            # a tool or the reason why there is none, never both
            self.assertNotEqual(bool(s.werkzeuge), bool(s.ohne_werkzeug), key)
            for tool, names in s.werkzeuge.items():
                self.assertEqual(werkzeuge.NAMES[tool], names, key)
                self.assertEqual(live.TOOLS[tool], s.live[0], key)
            if s.werkzeuge:
                self.assertEqual(werkzeug_abdeckung.TOOLS[key], tuple(s.werkzeuge), key)
            else:
                self.assertNotIn(key, werkzeug_abdeckung.TOOLS, key)
                art, why = s.ohne_werkzeug
                self.assertEqual({"regel": werkzeug_abdeckung.RULES, "ohne": werkzeug_abdeckung.WITHOUT}[art][key], why, key)
            if s.live:
                self.assertEqual(live.TARGETS[s.live[0]], s.live[1:5], key)
                self.assertEqual(live.RETURNS[s.live[0]], s.live[5], key)
            if s.log:
                area = dict(logfilter.AREAS)[s.log[0]]
                self.assertRegex(s.log[1] + ": x", area, key)
            if s.nur_eigenes_wort:
                tool = s.nur_eigenes_wort[1][0]
                self.assertIn(tool, s.werkzeuge, key)
                self.assertEqual(werkzeug_abdeckung.BY_WORD[tool], s.nur_eigenes_wort[0], key)
                self.assertIn(s.nur_eigenes_wort[1], spickzettel.KURZ, key)
            if s.modul:
                self.assertTrue(any(os.path.isfile(os.path.join(d, s.modul[0] + ".py")) for d in (PANEL, os.path.dirname(PANEL))),
                                key)
                self.assertEqual(technik.MODULE[s.modul[0]], s.modul[1:], key)
            if s.begleiter:
                self.assertIn(key, features.DESK_SKIP, key)
                if s.begleiter in ("talk", "voice", "spark", "link", "device", "panel"):
                    self.assertTrue(features.DESK_SKIP[key].startswith(("works", "for speaking", "a setting", "stays",
                                                                        "another")), key)
                else:
                    self.assertEqual(features.DESK_SKIP[key], s.begleiter, key)
            self.assertEqual(key in features.SPARK_ONLY, s.nur_spark, key)

    def test_no_old_table_names_it_again(self):
        """One source: what a Steckbrief holds stands nowhere else as a literal: not as a key or element of the table
        it feeds, not as the first word of an F(...) or of an example sentence."""
        tables = {"features.py": ("FEATURES", "DESK_SKIP", "DESK", "SPARK_ONLY"), "werkzeuge.py": ("NAMES",),
                  "live.py": ("TOOLS", "TARGETS", "RETURNS"), "werkzeug_abdeckung.py": ("TOOLS", "RULES", "WITHOUT", "BY_WORD"),
                  "technik.py": ("MODULE",), "spickzettel.py": ("KURZ",)}
        found = {}
        for name, names in tables.items():
            tree = ast.parse(source(name))
            for node in tree.body:
                targets = [t.id for t in getattr(node, "targets", []) if isinstance(t, ast.Name)]
                if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    targets = [node.target.id]
                if not set(targets) & set(names) or node.value is None:
                    continue
                for n in ast.walk(node.value):
                    lits = []
                    if isinstance(n, ast.Dict):
                        lits = [k for k in n.keys if k is not None]
                    elif isinstance(n, (ast.Set, ast.Tuple, ast.List)):
                        lits = n.elts
                    elif isinstance(n, ast.Call) and n.args and not (isinstance(n.func, ast.Attribute)
                                                                     and getattr(n.func.value, "id", "") == "steckbrief"):
                        lits = n.args[:1]   # F("key", …), dict.fromkeys((…), …) is a tuple above
                    for k in lits:
                        if isinstance(k, ast.Constant) and isinstance(k.value, str):
                            found.setdefault(k.value, set()).add(f"{name} {targets[0]}")
        for key, s in steckbrief.STECKBRIEFE.items():
            words = set(s.werkzeuge) | {key} | ({s.live[0]} if s.live else set()) | ({s.modul[0]} if s.modul else set())
            for w in sorted(words):
                self.assertEqual(sorted(found.get(w, ())), [], f"{w} stands there again: it lives in steckbrief.py")
            if s.log:
                self.assertNotRegex(source("logfilter.py"), r"[|(]%s[|)]" % re.escape(s.log[1]), "logfilter names it again")

    def test_a_new_function_comes_with_a_steckbrief(self):
        ohne = set(features.BY_KEY) - set(steckbrief.STECKBRIEFE)
        self.assertEqual(sorted(ohne - set(OHNE_ALT)), [], "a new function needs its Steckbrief in steckbrief.py")
        self.assertEqual(sorted(set(OHNE_ALT) - ohne), [], "these functions have a Steckbrief now (or are gone): take "
                                                          "them out of OHNE_ALT, the list only shrinks")


if __name__ == "__main__":
    unittest.main()
