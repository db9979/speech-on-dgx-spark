"""Steckbrief pro Funktion (steckbrief.py, Kritische Prüfung 2026-11-12 point 4): one place per function, the lists read it.

- every Steckbrief is complete and reaches every list it feeds (features, werkzeuge, Live, logs, Werkzeug-Abdeckung,
  Spickzettel, technik, Begleiter);
- no old table names a part of it again (rule 12: one source);
- a new function comes with a Steckbrief: OHNE_ALT, the functions without one on V01.1.397, only shrinks.

Reads only app/, so it runs in the app/-only copy too. No wall clock dependence.
"""
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
OHNE_ALT = ('ablauf', 'ack', 'agent', 'android', 'androidassist', 'androidlive', 'androidlock', 'androidupdate',
            'angriffsprobe', 'anhalten', 'anrufassistent', 'anrufe', 'anrufeturn', 'appmerken', 'auftragsplan',
            'auswertungen', 'begleiter', 'begleiterbedienen', 'begleitermeeting', 'begleiterschirm', 'begleitertun',
            'beobachten', 'berater', 'beraterana', 'beraterauto', 'beraterchat', 'beratererklaeren',
            'beraterhinweis', 'beraterideen', 'beraterissue', 'beratermich', 'berateru', 'beraterundo',
            'beraterwarum', 'bewerten', 'bewertenzurueck', 'bildaendern', 'bilder', 'calendar', 'calserver',
            'calshare', 'chatgroups', 'chatinvite', 'chatmedia', 'chatprivate', 'chats', 'contacts', 'dienstnutzer',
            'dienstwacht', 'direct', 'docaudio', 'docbrief', 'docfiles', 'docling', 'doclink', 'docmeaning',
            'docnight', 'docpics', 'docshared', 'documents', 'docyoutube', 'dungeon', 'dungeonbilder',
            'dungeonbuecher', 'dungeongast', 'dungeongeschichten', 'dungeonpruefstand', 'dungeonpruefung',
            'eingespraech', 'einladungen', 'einordnung', 'einordnungcheck', 'einordnungklage', 'einordnungpost',
            'einordnungrat', 'einordnungtest', 'entwickeln', 'entwickelnauftrag', 'entwickelngithub',
            'entwickelnterminal', 'erstellen', 'erstellenbilder', 'erstellenvorlagen', 'esp32', 'espstopp', 'feeds',
            'feedsmelden', 'fernals', 'fernbild', 'fernbildablage', 'ferngross', 'fernnotizen', 'fernordner',
            'fernsshtermy', 'fernweb', 'fernzugang', 'fernzugangalle', 'fernzuganghilfe', 'fernzugangmeldung',
            'fixes', 'follow', 'fuerdich', 'fund', 'fundchats', 'fundkontakte', 'fundlisten', 'fundmail',
            'fundmedien', 'fundschlagworte', 'fundtermine', 'gedfragen', 'gedhinweis', 'gedkurz', 'gedpruefen',
            'gedthemen', 'gehaeuse', 'geraetenacht', 'geraeteupdate', 'ha', 'hacam', 'haevent', 'halive', 'haloud',
            'havoice', 'helfer', 'helferangriff', 'hilfe', 'hilfeseite', 'hilfevorschlag', 'history', 'hoeren',
            'hoerstueck', 'hoerstueckdisk', 'ichweiss', 'images', 'iphone', 'iphonepanel', 'iphonepruef',
            'iphonepush', 'iphoneupdate', 'kartensuche', 'kiwix', 'klaeren', 'klaerenmerken', 'klaerenweg',
            'kontakteaendern', 'kontaktserver', 'kontingent', 'listdav', 'listlink', 'listnote', 'listshare',
            'llmapi', 'llmapiassist', 'llmapiextern', 'lokal', 'mail', 'mailcode', 'maildelete', 'mailidle',
            'maillearn', 'mailmanage', 'mailsend', 'mailstil', 'mailwichtig', 'mappen', 'mcp', 'mcpact',
            'mcpextern', 'mcpserver', 'melden', 'meldenadmin', 'memory', 'messages_all', 'messages_announce', 'mfa',
            'modelleeigen', 'modellwechsel', 'musik', 'musikbearbeiten', 'mymcp', 'mymcpjobs', 'mymcpoauth',
            'mystatus', 'nachsortieren', 'nas', 'nasablage', 'nashaushalt', 'nasquelle', 'naszustand',
            'notbetriebasr', 'notedevice', 'offlinelesen', 'openwebui', 'parcels', 'pebble', 'pebbleantwort',
            'pebblechat', 'pebbleerinnern', 'pebblefern', 'pebblefolge', 'pebblegesund', 'pebblemeldung',
            'pebblemerken', 'pebbleort', 'pebbleschnell', 'pebbletag', 'pebblezifferblatt', 'proactive',
            'remarkable', 'reminders', 'rmask', 'rmaufgaben', 'rmaufraeumen', 'rmfresh', 'rmguide', 'rminbox',
            'rmmeet', 'rmmorning', 'rmordner', 'rmpapier', 'rmsend', 'rmtodo', 'rmweb', 'rmweek', 'roles', 'room',
            'roomfar', 'roomha', 'roomtv', 'routing', 'rueckgaengig', 'rundlauf', 'satzende', 'schirm', 'schreib',
            'schreibapps', 'search', 'selfecho', 'sofort', 'sparkzustand', 'speaker', 'speicher',
            'speicherauslagern', 'speicherlan', 'speicherordner', 'spkcode', 'spontanhilfe', 'spontansteuern',
            'stimmdesign', 'style', 'suchfragen', 'suchpruefung', 'suchschnell', 'systemnachtmodelle',
            'systemnachtpanel', 'systemupdates', 'tagebuch', 'tasks', 'teilen', 'teilenhinweis', 'telefon',
            'telefonalarm', 'telefonanrufen', 'telefonaussen', 'telefongast', 'telegram', 'terminal', 'tidy',
            'tipps', 'tippspush', 'tippssaetze', 'tippsstimme', 'toolthink', 'transit', 'verbrauch', 'verbund',
            'verbundgruppen', 'verbundmedia', 'verlaufsync', 'vorab', 'vorgaenge', 'vorrang', 'wachposten',
            'wartung', 'wartungauto', 'weather', 'weicheabstimmen', 'weicheunklar', 'werkstatt', 'werkstattnacht',
            'wiki', 'wissensbuch', 'wissenskarte', 'wissensknoten', 'wyoming', 'xiaozhihinweis')


def source(name):
    with open(os.path.join(PANEL, name), encoding="utf-8") as f:
        return f.read()


class Steckbrief(unittest.TestCase):
    def test_every_steckbrief_reaches_its_lists(self):
        for key, s in steckbrief.STECKBRIEFE.items():
            f = features.BY_KEY[key]
            self.assertEqual((f.de, f.en, f.group, f.admin, f.guide), (s.de, s.en, s.gruppe, s.schalter, s.anleitung), key)
            self.assertIn(s.gruppe, {g[0] for g in features.GROUPS}, key)
            self.assertTrue(s.werkzeuge, key)
            for tool, names in s.werkzeuge.items():
                self.assertEqual(werkzeuge.NAMES[tool], names, key)
                self.assertEqual(live.TOOLS[tool], s.live[0], key)
            self.assertEqual(live.TARGETS[s.live[0]], s.live[1:5], key)
            self.assertEqual(live.RETURNS[s.live[0]], s.live[5], key)
            area = dict(logfilter.AREAS)[s.log[0]]
            self.assertRegex(s.log[1] + ": x", area, key)
            self.assertEqual(werkzeug_abdeckung.TOOLS[key], tuple(s.werkzeuge), key)
            if s.nur_eigenes_wort:
                tool = s.nur_eigenes_wort[1][0]
                self.assertIn(tool, s.werkzeuge, key)
                self.assertEqual(werkzeug_abdeckung.BY_WORD[tool], s.nur_eigenes_wort[0], key)
                self.assertIn(s.nur_eigenes_wort[1], spickzettel.KURZ, key)
            self.assertTrue(os.path.isfile(os.path.join(PANEL, s.modul[0] + ".py")), key)
            self.assertEqual(technik.MODULE[s.modul[0]], s.modul[1:], key)
            self.assertIn(s.begleiter, ("talk", "voice", "spark", "link", "device"), key)
            self.assertIn(key, features.DESK_SKIP, key)

    def test_no_old_table_names_it_again(self):
        """One source: what a Steckbrief holds stands nowhere else as a literal."""
        files = {n: source(n) for n in ("werkzeuge.py", "live.py", "werkzeug_abdeckung.py", "technik.py", "features.py",
                                        "spickzettel.py", "logfilter.py")}
        for key, s in steckbrief.STECKBRIEFE.items():
            words = set(s.werkzeuge) | {key, s.live[0], s.modul[0]}
            for name, src in files.items():
                for w in sorted(words):
                    self.assertNotRegex(src, r'"%s"\s*:' % re.escape(w), f"{name} names {w} again: it lives in steckbrief.py")
                    self.assertNotRegex(src, r'F\(\s*"%s"' % re.escape(w), f"{name} names {w} again")
                    self.assertNotRegex(src, r'\(\s*"%s",\s*"[^"]*",\s*"[^"]*"\)' % re.escape(w),
                                        f"{name} has an example for {w}: it lives in steckbrief.py")
            self.assertNotRegex(files["logfilter.py"], r"[|(]%s[|)]" % re.escape(s.log[1]), "logfilter names it again")

    def test_a_new_function_comes_with_a_steckbrief(self):
        ohne = set(features.BY_KEY) - set(steckbrief.STECKBRIEFE)
        self.assertEqual(sorted(ohne - set(OHNE_ALT)), [], "a new function needs its Steckbrief in steckbrief.py")
        self.assertEqual(sorted(set(OHNE_ALT) - ohne), [], "these functions have a Steckbrief now (or are gone): take "
                                                          "them out of OHNE_ALT, the list only shrinks")


if __name__ == "__main__":
    unittest.main()
