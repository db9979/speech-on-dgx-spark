"""Chats between the people of this Spark (chats.py, plan plaene/messenger.md): off until the admin and the profile
switch them on, the rules of who may write to whom, groups, ticks, changing and taking back, the event stream and
notifications without text, sealed texts at rest, and Live, journal and events with numbers only."""
import asyncio
import contextlib
import io
import json
import os
import time
import unittest
from unittest import mock

from tests import helpers

helpers.start()
import chats  # noqa: E402
import messages  # noqa: E402
import panel  # noqa: E402
import profiles  # noqa: E402
import push  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = TestClient(panel.app)
ADMIN.post("/api/login", json={"password": "secret-admin"})


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def profile(name, pin="2468", on=True):
    r = ADMIN.post("/api/admin/profiles", json={"name": name, "pin": pin})
    assert r.status_code in (200, 409), r.text
    c = TestClient(panel.app)
    assert c.post("/api/profile/login", json={"name": name, "pin": pin}).status_code == 200
    if on:
        assert c.put("/api/profile/settings", json={"chats_on": True}).status_code == 200
    return c


def uid_of(client):
    return client.get("/api/whoami").json()["profile"]["id"]


def switch(chats_on=True, groups=False):
    helpers.set_config(chats=chats_on, chats_groups=groups)


def open_with(a, b):
    r = a.post("/api/chats/open", json={"to": uid_of(b)})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def say(client, cid, text, **kw):
    return client.post("/api/chats/send", json=dict({"id": cid, "text": text}, **kw))


class Base(unittest.TestCase):
    def setUp(self):
        switch()
        chats._sent.clear()

    def tearDown(self):
        helpers.set_config(chats=False, chats_groups=False, messages_all=False, messages_announce=False)
        chats._subs.clear()


class Off(Base):
    def test_off_until_admin_and_profile_switch_it_on(self):
        a, b = profile("Channa"), profile("Chben")
        switch(chats_on=False)
        self.assertEqual(a.post("/api/chats/open", json={"to": uid_of(b)}).status_code, 403)
        self.assertFalse(a.get("/api/chats").json()["enabled"])
        switch()
        c = profile("Chcarl", on=False)                     # the admin alone is not enough
        self.assertFalse(c.get("/api/chats").json()["on"])
        self.assertEqual(c.post("/api/chats/open", json={"to": uid_of(a)}).status_code, 403)
        g = TestClient(panel.app)                          # guests never
        self.assertIn(g.get("/api/chats").status_code, (401, 403))
        self.assertIn(g.post("/api/chats/send", json={"id": "c" + "0" * 12, "text": "x"}).status_code, (401, 403))

    def test_defaults_are_off(self):
        d = json.loads(read(os.path.join(helpers.APP, "config.default.json")))["chat"]
        self.assertIs(d["chats"], False)
        self.assertIs(d["chats_groups"], False)
        self.assertIs(profiles.SETTINGS["chats_on"][0], False)
        self.assertIs(profiles.SETTINGS["chat_push_text"][0], False)

    def test_only_browser_or_app_keys(self):
        a = profile("Chdora")
        uid = uid_of(a)
        token = profiles.add_device("Chtestgeraet", uid)   # a name no other test writes (Probleme melden checks device names)
        did = next(x["id"] for x in profiles._load()["devices"] if x["name"] == "Chtestgeraet")
        self.addCleanup(profiles.delete_device, did)
        k = TestClient(panel.app)
        r = k.get("/api/chats", headers={profiles.DEVICE_HEADER: token})
        self.assertEqual(r.status_code, 403)


class OneToOne(Base):
    def test_both_see_the_same_messages_with_ticks(self):
        a, b = profile("Chemil"), profile("Chfrida")
        cid = open_with(a, b)
        self.assertEqual(open_with(b, a), cid)             # the chat of two people is always the same one
        r = say(a, cid, "Hallo Frida\nZweite Zeile")
        self.assertEqual(r.status_code, 200, r.text)
        item = r.json()["item"]
        self.assertEqual(item["text"], "Hallo Frida\nZweite Zeile")
        self.assertEqual(item["tick"], "sent")
        lst = b.get("/api/chats").json()                   # b's device asks: the second tick
        mine = next(x for x in lst["chats"] if x["id"] == cid)
        self.assertEqual(mine["unread"], 1)
        self.assertEqual(mine["last"]["text"], "Hallo Frida\nZweite Zeile")
        self.assertEqual(a.get("/api/chats/items", params={"id": cid}).json()["items"][-1]["tick"], "got")
        self.assertEqual(b.post("/api/chats/read", json={"id": cid}).status_code, 200)
        self.assertEqual(a.get("/api/chats/items", params={"id": cid}).json()["items"][-1]["tick"], "read")
        self.assertEqual(next(x for x in b.get("/api/chats").json()["chats"] if x["id"] == cid)["unread"], 0)
        # "gelesen" off for b: a sees only "got" (both ways)
        b.put("/api/profile/settings", json={"chat_receipts": False})
        say(a, cid, "Noch was")
        b.post("/api/chats/read", json={"id": cid})
        self.assertEqual(a.get("/api/chats/items", params={"id": cid}).json()["items"][-1]["tick"], "got")

    def test_texts_are_sealed_at_rest_and_bound_to_their_message(self):
        a, b = profile("Chgerd"), profile("Chhanna")
        cid = open_with(a, b)
        say(a, cid, "Geheimes Rezept Zimt_Stern-4711")
        raw = read(chats._chat_file(cid)) + read(chats._index_file())
        self.assertNotIn("Geheimes Rezept", raw)
        self.assertNotIn("Zimt_Stern-4711", raw)   # "_" and "-" never occur in base64 or a time stamp
        x = json.loads(read(chats._chat_file(cid)))["items"][-1]
        self.assertEqual(chats.unseal(x["text"], cid, x["id"]), "Geheimes Rezept Zimt_Stern-4711")
        self.assertEqual(chats.unseal(x["text"], cid, "0" * 12), "")          # moved to another message: unreadable
        self.assertEqual(chats.unseal(x["text"], "c" + "1" * 12, x["id"]), "")

    def test_rules_of_messages_apply(self):
        a, b = profile("Chida"), profile("Chjan")
        cid = open_with(a, b)
        ub, ua = uid_of(b), uid_of(a)
        messages.mutate(ub, lambda d: d["block"].append(ua))   # b blocks a: a hears only a neutral sentence
        r = say(a, cid, "Hallo?")
        self.assertEqual(r.status_code, 403)
        self.assertIn("nimmt gerade keine Nachrichten von dir an", r.json()["detail"])
        self.assertNotIn("block", r.json()["detail"].lower())
        self.assertFalse(a.get("/api/chats/items", params={"id": cid}).json()["can_send"])
        messages.mutate(ub, lambda d: d["block"].remove(ua))
        self.assertEqual(say(a, cid, "Jetzt?").status_code, 200)
        c = profile("Chkai")                                 # a stranger is never in someone else's chat
        self.assertEqual(c.get("/api/chats/items", params={"id": cid}).status_code, 404)
        self.assertEqual(say(c, cid, "rein").status_code, 404)

    def test_limits(self):
        a, b = profile("Chlea"), profile("Chmax")
        cid = open_with(a, b)
        self.assertEqual(say(a, cid, "x" * 5000).json()["item"]["text"], "x" * chats.MAX_TEXT)
        self.assertEqual(say(a, cid, "   ").status_code, 400)
        big = a.post("/api/chats/send", content=b'{"id":"' + b"x" * 140000 + b'"}', headers={"Content-Type": "application/json"})
        self.assertEqual(big.status_code, 413)
        with mock.patch.object(chats, "PER_HOUR", 2):
            chats._sent.clear()
            say(a, cid, "1")
            say(a, cid, "2")
            self.assertEqual(say(a, cid, "3").status_code, 429)
        self.assertEqual(a.post("/api/chats/react", json={"id": cid, "mid": "0" * 12, "emoji": "🍕"}).status_code, 400)

    def test_change_take_back_react_reply(self):
        a, b = profile("Chnora"), profile("Cholaf")
        cid = open_with(a, b)
        first = say(b, cid, "Kannst du Brot mitbringen?").json()["item"]
        mine = say(a, cid, "Klar", reply=first["id"]).json()["item"]
        self.assertEqual(mine["reply"]["text"], "Kannst du Brot mitbringen?")
        self.assertEqual(a.post("/api/chats/edit", json={"id": cid, "mid": mine["id"], "text": "Klar, mach ich"}).status_code, 200)
        self.assertEqual(b.post("/api/chats/edit", json={"id": cid, "mid": mine["id"], "text": "fremd"}).status_code, 404)
        self.assertEqual(b.post("/api/chats/react", json={"id": cid, "mid": mine["id"], "emoji": "👍"}).status_code, 200)
        got = b.get("/api/chats/items", params={"id": cid}).json()["items"][-1]
        self.assertEqual((got["text"], got["edited"], got["react"]), ("Klar, mach ich", True, [{"e": "👍", "n": 1, "me": True}]))
        self.assertEqual(a.post("/api/chats/back", json={"id": cid, "mid": mine["id"]}).status_code, 200)
        got = b.get("/api/chats/items", params={"id": cid}).json()["items"][-1]
        self.assertTrue(got["gone"])
        self.assertNotIn("text", got)
        self.assertNotIn("Klar", read(chats._chat_file(cid)))
        later = time.time() + chats.EDIT_SECS + 5        # after 15 minutes no change, after an hour no taking back
        x = say(a, cid, "spät").json()["item"]
        with self.assertRaises(PermissionError):
            chats.edit(uid_of(a), cid, x["id"], "neu", now=later)
        with self.assertRaises(PermissionError):
            chats.take_back(uid_of(a), cid, x["id"], now=time.time() + chats.BACK_SECS + 5)

    def test_clear_for_me_and_vanish(self):
        a, b = profile("Chpia"), profile("Chquinn")
        cid = open_with(a, b)
        say(a, cid, "alt")
        self.assertEqual(b.post("/api/chats/clear", json={"id": cid}).status_code, 200)
        self.assertFalse(any(x["id"] == cid for x in b.get("/api/chats").json()["chats"]))
        self.assertEqual([x["text"] for x in a.get("/api/chats/items", params={"id": cid}).json()["items"]], ["alt"])
        say(a, cid, "neu")
        self.assertEqual([x["text"] for x in b.get("/api/chats/items", params={"id": cid}).json()["items"]], ["neu"])
        self.assertEqual(a.post("/api/chats/opts", json={"id": cid, "vanish": 86400}).status_code, 200)
        self.assertEqual(a.post("/api/chats/opts", json={"id": cid, "vanish": 5}).status_code, 400)
        page = chats.items(uid_of(a), cid, now=time.time() + 2 * 86400)
        self.assertEqual([x for x in page["items"] if x["kind"] == "text"], [])

    def test_search_finds_only_own_chats(self):
        a, b, c = profile("Chrolf"), profile("Chsara"), profile("Chtim")
        cid = open_with(a, b)
        say(a, cid, "Treffpunkt am Brunnen")
        self.assertEqual([x["text"] for x in b.post("/api/chats/find", json={"q": "brunnen"}).json()["hits"]],
                         ["Treffpunkt am Brunnen"])
        self.assertEqual(c.post("/api/chats/find", json={"q": "brunnen"}).json()["hits"], [])


class Groups(Base):
    def test_groups_need_their_switch_and_only_take_who_takes_from_the_admin(self):
        a, b, c = profile("Chuwe"), profile("Chvera"), profile("Chwilma")
        ub, uc = uid_of(b), uid_of(c)
        self.assertEqual(a.post("/api/chats/group", json={"name": "Familie", "members": [ub]}).status_code, 403)
        switch(groups=True)
        c.put("/api/profile/settings", json={"msg_from": "chosen"})   # c takes only from picked people
        r = a.post("/api/chats/group", json={"name": "Familie", "members": [ub, uc]})
        self.assertEqual(r.status_code, 200, r.text)
        cid = r.json()["id"]
        self.assertEqual(r.json()["left_out"], ["Chwilma"])
        self.assertEqual(say(b, cid, "Hallo alle").status_code, 200)
        self.assertEqual(c.get("/api/chats/items", params={"id": cid}).status_code, 404)
        self.assertEqual(b.post("/api/chats/members", json={"id": cid, "add": [uc]}).status_code, 403)   # only admins
        self.assertEqual(b.post("/api/chats/opts", json={"id": cid, "name": "Meins"}).status_code, 403)
        self.assertEqual(a.post("/api/chats/opts", json={"id": cid, "name": "Familie Kern"}).status_code, 200)
        self.assertEqual(next(x for x in b.get("/api/chats").json()["chats"] if x["id"] == cid)["title"], "Familie Kern")
        self.assertNotIn("Familie", read(chats._index_file()))   # the group's name is sealed too
        sys_lines = [x["sys"] for x in b.get("/api/chats/items", params={"id": cid}).json()["items"] if x["kind"] == "sys"]
        self.assertEqual(sys_lines, ["made", "name"])

    def test_leaving_and_the_last_one_out(self):
        switch(groups=True)
        a, b = profile("Chxaver"), profile("Chyara")
        cid = a.post("/api/chats/group", json={"name": "Zwei", "members": [uid_of(b)]}).json()["id"]
        self.assertEqual(a.post("/api/chats/leave", json={"id": cid}).status_code, 200)
        page = b.get("/api/chats/items", params={"id": cid}).json()
        self.assertTrue(page["admin"])                     # the last admin left: the longest member is admin now
        self.assertEqual(b.post("/api/chats/leave", json={"id": cid}).status_code, 200)
        self.assertNotIn(cid, chats._index())
        self.assertFalse(os.path.exists(chats._chat_file(cid)))

    def test_a_deleted_profile_leaves_no_words(self):
        switch(groups=True)
        a, b = profile("Chzoe"), profile("Chzack")
        ua = uid_of(a)
        cid = open_with(a, b)
        say(a, cid, "Mein letztes Wort")
        self.assertEqual(ADMIN.delete(f"/api/admin/profiles/{ua}").status_code, 200)
        self.assertNotIn(ua, chats._index()[cid]["members"])
        x = chats._chat(cid)["items"][-1]
        self.assertTrue(x["gone"])
        self.assertNotIn("text", x)


class Delivery(Base):
    def test_events_carry_ids_never_text(self):
        a, b = profile("Chalma"), profile("Chbodo")
        cid = open_with(a, b)
        loop = asyncio.new_event_loop()
        q = asyncio.Queue()
        chats._subs[uid_of(b)] = {"s": (loop, q)}
        try:
            say(a, cid, "Streng geheim")
            a.post("/api/chats/typing", json={"id": cid})
            loop.run_until_complete(asyncio.sleep(0.05))
            evs = [q.get_nowait() for _ in range(q.qsize())]
        finally:
            loop.close()
        self.assertEqual([e["type"] for e in evs], ["chat", "typing"])
        self.assertNotIn("geheim", json.dumps(evs))
        self.assertEqual(a.get("/api/chats/items", params={"id": cid}).json()["items"][-1]["tick"], "got")   # page open

    def test_notification_to_every_device_without_text(self):
        a, b = profile("Chcora"), profile("Chdirk")
        cid = open_with(a, b)
        sent = []

        async def fake(uid, title, body, tag="", private=True, why="", to=""):
            sent.append((uid, title, body, tag, to))
            return 2
        with mock.patch.object(push, "send", fake), mock.patch.object(push, "reachable", lambda u, private=True: True), \
                mock.patch("room.night", lambda u, local=None: False):
            say(a, cid, "Essen ist fertig")
            b.put("/api/profile/settings", json={"chat_push_text": True})
            say(a, cid, "Mit Text")
            b.post("/api/chats/opts", json={"id": cid, "mute": -1})
            say(a, cid, "Stumm")
        self.assertEqual([(x[2], x[3], x[4]) for x in sent], [("Neue Nachricht", "chat-" + cid, "every"),
                                                               ("Mit Text", "chat-" + cid, "every")])
        self.assertEqual(sent[0][1], "💬 Chcora")
        self.assertEqual(push._why("chat-" + cid), "Chat")

    def test_push_every_reaches_each_browser_but_not_telegram(self):
        ways = {}

        async def one(uid, kind, targets, title, body, tag, private, why):
            ways[kind] = len(targets)
            return 1
        with mock.patch.object(push, "_have", lambda u, p: {"app": True, "and": False, "desk": False, "tg": True, "web": True}), \
                mock.patch.object(push, "subs", lambda u: [{"endpoint": "a"}, {"endpoint": "b"}]), \
                mock.patch.object(push, "_send_one", one), mock.patch("begleiter.hold", lambda *a: False), \
                mock.patch("begleiter.lapsed", lambda u: None):
            asyncio.run(push.send("u_000000000000", "t", "b", tag="chat-x", to="every"))
        self.assertEqual(ways, {"app": 0, "web": 2})

    def test_live_and_journal_show_numbers_only(self):
        a, b = profile("Chelke"), profile("Chfinn")
        cid = open_with(a, b)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            say(a, cid, "Wort im Journal?")
        self.assertIn("chats: sent", out.getvalue())
        self.assertNotIn("Wort im Journal", out.getvalue())
        self.assertNotIn("Chelke", out.getvalue())
        lv = chats.for_live()
        self.assertTrue(lv["on"])
        self.assertGreaterEqual(lv["sent"], 1)
        self.assertNotIn("Chelke", json.dumps(lv))
        import live
        self.assertEqual(live.TARGETS["chats"][2], "spark")
        import logfilter
        self.assertEqual(logfilter.parse("chats: sent | kind one | chars 4")["area"], "nachrichten")


class Assistant(Base):
    def test_tell_anna_goes_into_the_chat_and_reading_marks_outside(self):
        a, b = profile("Chgreta"), profile("Chhugo")
        ub, ua = uid_of(b), uid_of(a)
        names, why = asyncio.run(messages.send(ua, [ub], "Das Essen ist fertig"))
        self.assertEqual((names, why), (["Chhugo"], ""))
        self.assertNotIn("items", messages._raw(ub))                 # there is no mailbox any more
        cid = chats.one_id(ua, ub)
        x = b.get("/api/chats/items", params={"id": cid}).json()["items"][-1]
        self.assertEqual((x["text"], x["via"]), ("Das Essen ist fertig", "spark"))
        out = asyncio.run(messages.tool("message_read", {}, {"who": {"id": ub}, "src": "web"}))
        self.assertIn("Chat von Chgreta: Das Essen ist fertig", out)
        self.assertEqual(chats.unread_total(ub), 0)
        offered = messages.offer({"who": {"id": ub}, "own": True, "private": True, "text": "Was gibt es Neues?"})
        self.assertIsNone(offered)    # nothing unread, no words about messages: no tools
        say(a, cid, "Noch eins")
        offered = messages.offer({"who": {"id": ub}, "own": True, "private": True, "text": "Was gibt es Neues?"})
        self.assertIn("message_read", offered["outside"])            # what someone wrote is outside text


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------- Schritt B: photos, files, voice, invitations
def jpeg(w=600, h=400, gps=True):
    from PIL import Image
    im = Image.new("RGB", (w, h), (200, 80, 40))
    out = io.BytesIO()
    if gps:   # a place in the EXIF data, as a phone writes it
        ex = Image.Exif()
        ex[0x010F] = "Kamerafirma"
        ex[0x8825] = {1: "N", 2: (48.0, 8.0, 0.0)}
        im.save(out, "JPEG", exif=ex)
    else:
        im.save(out, "JPEG")
    return out.getvalue()


def wav(secs=1.5):
    import math
    import struct
    import wave
    pcm = b"".join(struct.pack("<h", int(8000 * math.sin(i / 8))) for i in range(int(16000 * secs)))
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm)
    return out.getvalue()


def docx():
    import zipfile
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<w:document/>")
    return out.getvalue()


def up(client, cid, kind, data, name=""):
    from urllib.parse import quote
    head = {"Content-Type": "application/octet-stream"}
    if name:
        head["X-Chat-Name"] = quote(name)
    return client.post("/api/chats/media", params={"id": cid, "kind": kind}, content=data, headers=head)


class Media(Base):
    def setUp(self):
        super().setUp()
        helpers.set_config(chats_media=True)
        self._tr = chats._transcribe

        async def tr(pcm):
            return "Bin gleich da"
        chats._transcribe = tr

    def tearDown(self):
        chats._transcribe = self._tr
        helpers.set_config(chats_media=False)
        super().tearDown()

    def test_off_by_default_and_needs_its_switch(self):
        import features
        self.assertEqual(features.BY_KEY["chatmedia"].parent, "chats")   # the profile's own switch is the one of Chats
        with open(os.path.join(os.path.dirname(chats.__file__), "..", "config.default.json")) as f:
            self.assertIs(json.load(f)["chat"]["chats_media"], False)
        a, b = profile("Chmona"), profile("Chnils")
        cid = open_with(a, b)
        helpers.set_config(chats_media=False)
        self.assertEqual(up(a, cid, "photo", jpeg()).status_code, 403)
        self.assertFalse(a.get("/api/chats").json()["media"])
        helpers.set_config(chats_media=True)
        self.assertTrue(a.get("/api/chats").json()["media"])
        self.assertEqual(up(a, cid, "sticker", jpeg()).status_code, 400)
        g = TestClient(panel.app)                           # guests never
        self.assertIn(up(g, cid, "photo", jpeg()).status_code, (401, 403))

    def test_photo_is_saved_anew_without_place_sealed_and_only_for_members(self):
        a, b, c = profile("Cholga"), profile("Chpaul"), profile("Chquinn")
        cid = open_with(a, b)
        r = up(a, cid, "photo", jpeg(3000, 2000))
        self.assertEqual(r.status_code, 200, r.text)
        mid = r.json()["item"]["id"]
        x = next(x for x in b.get("/api/chats/items", params={"id": cid}).json()["items"] if x["id"] == mid)
        self.assertEqual(x["kind"], "photo")
        self.assertEqual(max(x["media"]["w"], x["media"]["h"]), chats.PHOTO_SIDE)
        full = b.get("/api/chats/media", params={"id": cid, "mid": mid, "part": "f"})
        self.assertEqual(full.status_code, 200)
        self.assertTrue(full.content.startswith(b"\xff\xd8"))
        self.assertNotIn(b"Kamerafirma", full.content)      # no EXIF (camera, place) any more
        self.assertNotIn(b"GPS", full.content)
        self.assertEqual(full.headers["x-content-type-options"], "nosniff")
        self.assertIn("sandbox", full.headers["content-security-policy"])
        thumb = b.get("/api/chats/media", params={"id": cid, "mid": mid, "part": "t"})
        from PIL import Image
        self.assertLessEqual(max(Image.open(io.BytesIO(thumb.content)).size), chats.THUMB_SIDE)
        # on the disk only sealed bytes, bound to chat, message and part
        raw = read_bytes(chats._media_file(cid, mid, "f"))
        self.assertFalse(raw.startswith(b"\xff\xd8"))
        self.assertIsNone(chats.unseal_bytes(raw, cid, mid, "t"))
        self.assertEqual(c.get("/api/chats/media", params={"id": cid, "mid": mid}).status_code, 404)
        self.assertEqual(up(a, cid, "photo", b"kein bild").status_code, 400)
        self.assertEqual(up(a, cid, "photo", docx()).status_code, 400)

    def test_files_by_content_never_by_name_and_only_as_download(self):
        a, b = profile("Chrita"), profile("Chsven")
        cid = open_with(a, b)
        r = up(a, cid, "file", docx(), name="../../Bericht \"Q3\".exe")
        self.assertEqual(r.status_code, 200, r.text)
        x = r.json()["item"]
        self.assertEqual(x["media"]["ext"], "docx")
        self.assertTrue(x["media"]["name"].endswith(".docx"))
        self.assertNotIn("/", x["media"]["name"])
        self.assertNotIn("..", x["media"]["name"])
        got = b.get("/api/chats/media", params={"id": cid, "mid": x["id"]})
        self.assertEqual(got.headers["content-type"], "application/octet-stream")
        self.assertTrue(got.headers["content-disposition"].startswith("attachment;"))
        self.assertEqual(got.content, docx())
        self.assertEqual(up(a, cid, "file", b"%PDF-1.4\n...").json()["item"]["media"]["ext"], "pdf")
        self.assertEqual(up(a, cid, "file", "Liste;1\n".encode(), name="a.csv").json()["item"]["media"]["ext"], "csv")
        self.assertEqual(up(a, cid, "file", b"MZ\x90\x00\x03\x00\x00\x00binary").status_code, 400)   # a program
        self.assertEqual(up(a, cid, "file", jpeg()).status_code, 400)                                 # pictures as photo
        import zipfile
        z = io.BytesIO()
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("evil.js", "x")
        self.assertEqual(up(a, cid, "file", z.getvalue(), name="x.docx").status_code, 400)
        z = io.BytesIO()   # a zip bomb: 200 MB of zeros in a few hundred KB; only its first bytes are read
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as f:
            f.writestr("mimetype", b"\0" * (200 * 1024**2))
        with mock.patch("zipfile.ZipFile.read", side_effect=AssertionError("unpacked a whole entry")):
            with self.assertRaises(ValueError):
                chats.file_kind(z.getvalue(), "x.odt")
        # the name never sits in the index unsealed
        self.assertNotIn("Bericht", read(chats._chat_file(cid)))

    def test_voice_message_with_its_words(self):
        a, b = profile("Chtara"), profile("Chudo")
        cid = open_with(a, b)
        r = up(a, cid, "voice", wav())
        self.assertEqual(r.status_code, 200, r.text)
        x = r.json()["item"]
        self.assertEqual((x["kind"], x["text"]), ("voice", "Bin gleich da"))
        self.assertGreaterEqual(x["media"]["secs"], 1)
        got = b.get("/api/chats/media", params={"id": cid, "mid": x["id"]})
        self.assertEqual(got.headers["content-type"], "audio/aac")
        self.assertEqual(got.content[0], 0xFF)                       # an AAC (ADTS) stream: plays on every phone
        self.assertEqual(got.content[1] & 0xF0, 0xF0)
        self.assertEqual(up(a, cid, "voice", wav(0.2)).status_code, 400)       # too short
        self.assertEqual(up(a, cid, "voice", b"nichts").status_code, 400)
        self.assertEqual(b.get("/api/chats").json()["chats"][0]["last"]["kind"], "voice")

    def test_taken_back_and_vanished_take_their_files_and_bytes(self):
        a, b = profile("Chvalk"), profile("Chwenz")
        cid = open_with(a, b)
        mid = up(a, cid, "photo", jpeg()).json()["item"]["id"]
        ua = uid_of(a)
        self.assertGreater(chats.used(ua), 0)
        self.assertTrue(os.path.exists(chats._media_file(cid, mid, "f")))
        self.assertEqual(a.post("/api/chats/back", json={"id": cid, "mid": mid}).status_code, 200)
        self.assertFalse(os.path.exists(chats._media_file(cid, mid, "f")))
        self.assertFalse(os.path.exists(chats._media_file(cid, mid, "t")))
        self.assertEqual(chats.used(ua), 0)
        self.assertEqual(b.get("/api/chats/media", params={"id": cid, "mid": mid}).status_code, 404)
        mid = up(a, cid, "photo", jpeg()).json()["item"]["id"]
        a.post("/api/chats/opts", json={"id": cid, "vanish": 86400})
        self.assertGreater(chats.used(ua), 0)
        self.assertEqual(chats.tidy(now=time.time() + 2 * 86400, every=0), 1)
        self.assertFalse(os.path.exists(chats._media_file(cid, mid, "f")))
        self.assertEqual(chats.used(ua), 0)

    def test_quota_and_rate(self):
        a, b = profile("Chxaver"), profile("Chyvo")
        cid = open_with(a, b)
        with mock.patch.object(chats, "QUOTA", 1000):
            r = up(a, cid, "photo", jpeg())
            self.assertEqual(r.status_code, 429)
            self.assertIn("voll", r.json()["detail"])
        self.assertEqual(os.listdir(chats._media_dir(cid)) if os.path.isdir(chats._media_dir(cid)) else [], [])

    def test_names_and_search_words_never_in_the_address(self):
        a, b = profile("Chzora"), profile("Chadam")
        cid = open_with(a, b)
        say(a, cid, "Geheimwort Lavendel")
        self.assertEqual(b.get("/api/chats/find", params={"q": "lavendel"}).status_code, 405)   # GET is gone
        self.assertEqual([x["text"] for x in b.post("/api/chats/find", json={"q": "lavendel"}).json()["hits"]],
                         ["Geheimwort Lavendel"])
        js = read(os.path.join(os.path.dirname(chats.__file__), "static", "js", "chats.js"))
        self.assertNotIn("find?q=", js)
        self.assertIn("X-Chat-Name", js)

    def test_live_and_journal_with_numbers_only(self):
        a, b = profile("Chbert"), profile("Chcora")
        cid = open_with(a, b)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            up(a, cid, "file", docx(), name="Steuer Chbert.docx")
        self.assertIn("chats: sent", out.getvalue())
        self.assertNotIn("Steuer", out.getvalue())
        lv = chats.for_live()
        self.assertTrue(lv["media_on"])
        self.assertGreaterEqual(lv["media"], 1)
        self.assertNotIn("Steuer", json.dumps(lv))


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


class Invite(Base):
    BASE = "https://spark.example"

    def setUp(self):
        super().setUp()
        import guard
        for k in [k for k in guard._rate if k[0] in ("chatsinvite",)]:
            guard._rate.pop(k, None)

    def tearDown(self):
        helpers.set_config(chats_invite=False)
        ADMIN.put("/api/admin/join", json={"mode": "off"})
        super().tearDown()

    def test_needs_the_switch_and_new_people_by_invitation(self):
        a = profile("Chdora")
        body = {"base": self.BASE, "name": "Oma"}
        self.assertEqual(a.post("/api/chats/invite", json=body).status_code, 403)
        helpers.set_config(chats_invite=True)
        self.assertEqual(a.post("/api/chats/invite", json=body).status_code, 403)   # Neue Personen still off
        self.assertFalse(a.get("/api/chats/invites").json()["on"])
        self.assertTrue(a.get("/api/chats").json()["invite_switch"])
        ADMIN.put("/api/admin/join", json={"mode": "invite"})
        self.assertTrue(a.get("/api/chats/invites").json()["on"])
        self.assertEqual(a.post("/api/chats/invite", json={"base": "http://spark.example"}).status_code, 400)
        g = TestClient(panel.app)
        self.assertIn(g.post("/api/chats/invite", json=body).status_code, (401, 403))

    def test_the_invited_person_lands_in_the_chat(self):
        import join
        helpers.set_config(chats_invite=True)
        ADMIN.put("/api/admin/join", json={"mode": "invite"})
        a = profile("Chemil")
        r = a.post("/api/chats/invite", json={"base": self.BASE, "name": "Chfrieda"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("<svg", r.json()["qr"])
        code = r.json()["link"].split("#join=", 1)[1]
        self.assertTrue(any(i["chat"] for i in ADMIN.get("/api/admin/join").json().get("invites", [])))
        n = TestClient(panel.app)
        j = n.post("/api/join", json={"code": code, "name": "Chfrieda", "pin": "135791"})
        self.assertEqual(j.status_code, 200, j.text)
        cid = j.json()["chat"]
        self.assertEqual(cid, chats.one_id(uid_of(a), n.get("/api/whoami").json()["profile"]["id"]))
        self.assertTrue(n.get("/api/whoami").json()["chats_use"])
        d = n.get("/api/chats/items", params={"id": cid}).json()
        self.assertTrue(d["can_send"])
        self.assertEqual([x["sys"] for x in d["items"] if x["kind"] == "sys"], ["joined"])
        self.assertEqual(say(n, cid, "Hallo!").status_code, 200)
        self.assertEqual(a.get("/api/chats").json()["chats"][0]["last"]["text"], "Hallo!")
        self.assertEqual(n.post("/api/join", json={"code": code, "name": "Chzweit", "pin": "135791"}).status_code, 400)
        self.assertEqual(join.chat_of(n.get("/api/whoami").json()["profile"]["id"]), cid)

    def test_at_most_three_open_withdraw_and_switch_off_ends_them(self):
        helpers.set_config(chats_invite=True)
        ADMIN.put("/api/admin/join", json={"mode": "invite"})
        a, b = profile("Chgerd"), profile("Chhanna")
        codes = []
        for i in range(3):
            r = a.post("/api/chats/invite", json={"base": self.BASE})
            self.assertEqual(r.status_code, 200, r.text)
            codes.append((r.json()["id"], r.json()["link"].split("#join=", 1)[1]))
        self.assertEqual(a.post("/api/chats/invite", json={"base": self.BASE}).status_code, 409)
        self.assertEqual(len(a.get("/api/chats/invites").json()["open"]), 3)
        self.assertEqual(b.get("/api/chats/invites").json()["open"], [])
        self.assertEqual(b.post("/api/chats/invite/back", json={"id": codes[0][0]}).status_code, 404)  # not hers
        self.assertEqual(a.post("/api/chats/invite/back", json={"id": codes[0][0]}).status_code, 200)
        n = TestClient(panel.app)
        self.assertEqual(n.post("/api/join", json={"code": codes[0][1], "name": "Chweg", "pin": "135791"}).status_code, 400)
        helpers.set_config(chats_invite=False)
        self.assertEqual(n.post("/api/join", json={"code": codes[1][1], "name": "Chweg", "pin": "135791"}).status_code, 400)
        helpers.set_config(chats_invite=True)
        a.put("/api/profile/settings", json={"chats_on": False})   # the inviter turned chats off: the link ends
        self.assertEqual(n.post("/api/join", json={"code": codes[1][1], "name": "Chweg", "pin": "135791"}).status_code, 400)
        self.assertFalse(any(u["name"] == "Chweg" for u in profiles._load()["users"]))


# ---------------------------------------------------------------- private chats (Schritt C, chatsec.py)
# The same box the page makes in chatsec.js, made here with the cryptography package: so the Spark is tested
# with real encryption and a text the test reads back only with the receiving device's private key.
import base64  # noqa: E402

from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: E402
from cryptography.hazmat.primitives.kdf.hkdf import HKDF  # noqa: E402

import chatsec  # noqa: E402

b64 = lambda b: base64.b64encode(b).decode()   # noqa: E731


class Device:
    def __init__(self, client):
        self.c, self.priv = client, ec.generate_private_key(ec.SECP256R1())
        self.pub = b64(self.priv.public_key().public_bytes(serialization.Encoding.X962,
                                                           serialization.PublicFormat.UncompressedPoint))
        r = client.post("/api/chats/keys", json={"pub": self.pub, "kind": "browser"})
        assert r.status_code == 200, r.text
        self.kid = r.json()["id"]

    def _wrap_key(self, other_pub, cid, frm, to, salt):
        peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), base64.b64decode(other_pub))
        shared = self.priv.exchange(ec.ECDH(), peer)
        return HKDF(hashes.SHA256(), 32, salt, f"spark-e2e-v1|{cid}|{frm}|{to}".encode()).derive(shared)

    def box(self, cid, payload, keys):
        k, iv = os.urandom(32), os.urandom(12)
        out = {"v": 1, "f": self.kid, "iv": b64(iv), "ct": b64(AESGCM(k).encrypt(iv, json.dumps(payload).encode(), cid.encode())), "k": {}}
        for x in keys:
            salt, wi = os.urandom(16), os.urandom(12)
            wk = self._wrap_key(x["pub"], cid, self.kid, x["id"], salt)
            out["k"][x["id"]] = {"s": b64(salt), "i": b64(wi), "w": b64(AESGCM(wk).encrypt(wi, k, None))}
        return out, k

    def open(self, cid, box, keys):
        w = box["k"][self.kid]
        sender = next(x for x in keys if x["id"] == box["f"])
        wk = self._wrap_key(sender["pub"], cid, box["f"], self.kid, base64.b64decode(w["s"]))
        k = AESGCM(wk).decrypt(base64.b64decode(w["i"]), base64.b64decode(w["w"]), None)
        return json.loads(AESGCM(k).decrypt(base64.b64decode(box["iv"]), base64.b64decode(box["ct"]), cid.encode()))


def keys_of(client, cid):
    r = client.get("/api/chats/keys", params={"id": cid})
    assert r.status_code == 200, r.text
    return [x for x in r.json()["keys"] if not x.get("gone")]


class Private(Base):
    def setUp(self):
        super().setUp()
        helpers.set_config(chats_private=True)

    def tearDown(self):
        helpers.set_config(chats_private=False, chats_media=False)
        super().tearDown()

    def pair(self, n1, n2):
        a, b = profile(n1), profile(n2)
        da, db = Device(a), Device(b)
        r = a.post("/api/chats/private", json={"to": uid_of(b)})
        self.assertEqual(r.status_code, 200, r.text)
        return a, b, da, db, r.json()["id"]

    def test_off_until_the_admin_switch(self):
        import features
        self.assertEqual(features.BY_KEY["chatprivate"].parent, "chats")
        with open(os.path.join(helpers.APP, "config.default.json")) as f:
            self.assertIs(json.load(f)["chat"]["chats_private"], False)
        a, b = profile("Chpaula"), profile("Chpeter")
        helpers.set_config(chats_private=False)
        pub = b64(ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
        self.assertEqual(a.post("/api/chats/keys", json={"pub": pub}).status_code, 403)
        self.assertEqual(a.post("/api/chats/private", json={"to": uid_of(b)}).status_code, 403)
        self.assertFalse(a.get("/api/chats").json()["private"])
        helpers.set_config(chats_private=True)
        self.assertTrue(a.get("/api/chats").json()["private"])
        g = TestClient(panel.app)                           # guests never
        self.assertIn(g.post("/api/chats/keys", json={"pub": pub}).status_code, (401, 403))
        # the iPhone app's key (a device key) cannot add a key: the private half has to live in that browser
        token = profiles.add_device("Chtestapp", uid_of(a), scope="app")
        did = next(x["id"] for x in profiles._load()["devices"] if x["name"] == "Chtestapp")
        self.addCleanup(profiles.delete_device, did)
        k = TestClient(panel.app)
        self.assertIn(k.post("/api/chats/keys", json={"pub": pub}, headers={profiles.DEVICE_HEADER: token}).status_code, (401, 403))

    def test_a_key_is_a_real_point_and_counted(self):
        a = profile("Chquinn")
        self.assertEqual(a.post("/api/chats/keys", json={"pub": b64(b"\x04" + b"\x01" * 64)}).status_code, 400)   # not on the curve
        self.assertEqual(a.post("/api/chats/keys", json={"pub": "nicht base64!"}).status_code, 400)
        d = Device(a)
        self.assertEqual(a.post("/api/chats/keys", json={"pub": d.pub}).json()["id"], d.kid)   # the same key once
        for _ in range(chatsec.MAX_KEYS - 1):
            Device(a)
        pub = b64(ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
        self.assertEqual(a.post("/api/chats/keys", json={"pub": pub}).status_code, 429)
        self.assertEqual(len(a.get("/api/chats/keys").json()["keys"]), chatsec.MAX_KEYS)
        import stufen
        self.assertEqual(stufen.LIST[("POST", "/api/chats/keys")][0], stufen.CONFIRM)   # a new device asks for the code

    def test_both_need_a_device_first(self):
        a, b = profile("Chrolf"), profile("Chsina")
        Device(a)
        r = a.post("/api/chats/private", json={"to": uid_of(b)})
        self.assertEqual(r.status_code, 403)
        self.assertIn("noch kein Gerät", r.json()["detail"])
        Device(b)
        r = a.post("/api/chats/private", json={"to": uid_of(b)})
        self.assertEqual(r.status_code, 200, r.text)
        cid = r.json()["id"]
        self.assertNotEqual(cid, chats.one_id(uid_of(a), uid_of(b)))   # its own chat beside the ordinary one
        self.assertEqual(b.post("/api/chats/private", json={"to": uid_of(a)}).json()["id"], cid)
        it = a.get("/api/chats/items", params={"id": cid}).json()
        self.assertTrue(it["private"])
        self.assertTrue(it["can_send"])

    def test_the_spark_keeps_only_the_box_and_the_other_device_opens_it(self):
        a, b, da, db, cid = self.pair("Chtara", "Chtimo")
        sent = []

        async def fake(uid, title, body, tag="", private=True, why="", to=""):
            sent.append(body)
            return 1
        b.put("/api/profile/settings", json={"chat_push_text": True})   # even so: never the text of a private chat
        box, _ = da.box(cid, {"t": "Streng geheim 4711"}, keys_of(a, cid))
        with mock.patch.object(push, "send", fake), mock.patch.object(push, "reachable", lambda u, private=True: True), \
                mock.patch("room.night", lambda u, local=None: False):
            r = a.post("/api/chats/send", json={"id": cid, "box": box})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(sent, ["🔒 Neue Nachricht"])
        raw = read(chats._chat_file(cid)) + read(chats._index_file())
        self.assertNotIn("Streng geheim", raw)
        items = b.get("/api/chats/items", params={"id": cid}).json()["items"]
        self.assertEqual(items[-1]["kind"], "box")
        self.assertNotIn("text", items[-1])
        self.assertEqual(db.open(cid, items[-1]["box"], keys_of(b, cid))["t"], "Streng geheim 4711")
        self.assertEqual(da.open(cid, items[-1]["box"], keys_of(a, cid))["t"], "Streng geheim 4711")   # and the sender's own
        lst = next(x for x in b.get("/api/chats").json()["chats"] if x["id"] == cid)
        self.assertTrue(lst["private"])
        self.assertEqual(lst["unread"], 1)
        self.assertEqual(lst["last"]["text"], "")
        # the assistant knows only that it is there; the search on the Spark finds nothing
        lines = chats.for_model(uid_of(b))
        self.assertIn("🔒 private Nachricht", lines[-1][2])
        self.assertNotIn("geheim", json.dumps(lines))
        self.assertEqual(chats.find(uid_of(a), "geheim"), [])
        # reactions and taking back work as everywhere; changing cannot (the Spark has no text to change)
        mid = items[-1]["id"]
        self.assertEqual(b.post("/api/chats/react", json={"id": cid, "mid": mid, "emoji": "👍"}).status_code, 200)
        self.assertEqual(a.post("/api/chats/edit", json={"id": cid, "mid": mid, "text": "x"}).status_code, 403)
        self.assertEqual(a.post("/api/chats/back", json={"id": cid, "mid": mid}).status_code, 200)
        self.assertNotIn('"box": {', read(chats._chat_file(cid)).split(mid)[1][:400])

    def test_plain_text_only_outside_and_a_box_only_inside(self):
        a, b, da, db, cid = self.pair("Chulla", "Chveit")
        self.assertEqual(say(a, cid, "unverschlüsselt").status_code, 400)
        one = open_with(a, b)
        box, _ = da.box(one, {"t": "x"}, keys_of(a, cid))
        self.assertEqual(a.post("/api/chats/send", json={"id": one, "box": box}).status_code, 400)
        bad, _ = da.box(cid, {"t": "x"}, keys_of(a, cid))
        bad["k"][da.kid]["w"] = b64(b"x" * 10)                 # a wrapped key of the wrong size
        self.assertEqual(a.post("/api/chats/send", json={"id": cid, "box": bad}).status_code, 400)
        bad, _ = da.box(cid, {"t": "x"}, keys_of(a, cid))
        bad["more"] = "x"                                       # nothing else rides along
        self.assertEqual(a.post("/api/chats/send", json={"id": cid, "box": bad}).status_code, 400)
        c = profile("Chwanda")                                  # an outsider sees neither keys nor messages
        self.assertEqual(c.get("/api/chats/keys", params={"id": cid}).status_code, 404)
        self.assertEqual(c.get("/api/chats/items", params={"id": cid}).status_code, 404)

    def test_a_new_device_of_the_other_must_be_in_the_box(self):
        a, b, da, db, cid = self.pair("Chxaver", "Chyara")
        old_keys = keys_of(a, cid)
        db2 = Device(b)                                         # Yara's second device
        box, _ = da.box(cid, {"t": "Hallo"}, old_keys)
        r = a.post("/api/chats/send", json={"id": cid, "box": box})
        self.assertEqual(r.status_code, 403)
        self.assertIn("neues Gerät", r.json()["detail"])
        items = a.get("/api/chats/items", params={"id": cid}).json()["items"]
        self.assertEqual(items[-1]["sys"], "newkey")            # the chat says so: compare the Sicherheitsnummer again
        box, _ = da.box(cid, {"t": "Hallo"}, keys_of(a, cid))
        self.assertEqual(a.post("/api/chats/send", json={"id": cid, "box": box}).status_code, 200)
        last = b.get("/api/chats/items", params={"id": cid}).json()["items"][-1]
        self.assertEqual(db2.open(cid, last["box"], keys_of(b, cid))["t"], "Hallo")
        # a removed device: its key stays for older messages, new ones are not made for it, it cannot send
        self.assertEqual(b.post("/api/chats/keys/remove", json={"id": db2.kid}).status_code, 200)
        allk = a.get("/api/chats/keys", params={"id": cid}).json()["keys"]
        self.assertTrue(next(x for x in allk if x["id"] == db2.kid).get("gone"))
        bx, _ = db2.box(cid, {"t": "von weg"}, keys_of(b, cid))
        self.assertEqual(b.post("/api/chats/send", json={"id": cid, "box": bx}).status_code, 403)
        self.assertEqual(a.get("/api/chats/items", params={"id": cid}).json()["items"][-1]["sys"], "keygone")

    def test_a_photo_or_file_travels_as_the_device_encrypted_it(self):
        helpers.set_config(chats_media=True)
        a, b, da, db, cid = self.pair("Chzora", "Chalba")
        fk, fiv = os.urandom(32), os.urandom(12)
        blob = fiv + AESGCM(fk).encrypt(fiv, b"%PDF-1.4 geheimer Inhalt", None)
        box, _ = da.box(cid, {"t": "", "a": {"kind": "file", "name": "geheim.pdf", "k": b64(fk)}}, keys_of(a, cid))
        r = a.post(f"/api/chats/media?id={cid}&kind=box", content=json.dumps(box).encode() + b"\n" + blob)
        self.assertEqual(r.status_code, 200, r.text)
        mid = r.json()["item"]["id"]
        self.assertEqual(r.json()["item"]["blob"]["bytes"], len(blob))
        stored = open(chats._media_file(cid, mid, "f"), "rb").read()
        self.assertNotIn(b"geheim", stored)
        self.assertNotIn(b"geheim", read(chats._chat_file(cid)).encode())
        got = b.get("/api/chats/media", params={"id": cid, "mid": mid})
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.content, blob)
        self.assertIn("attachment", got.headers["content-disposition"])
        pl = db.open(cid, b.get("/api/chats/items", params={"id": cid}).json()["items"][-1]["box"], keys_of(b, cid))
        k = base64.b64decode(pl["a"]["k"])
        self.assertEqual(AESGCM(k).decrypt(got.content[:12], got.content[12:], None), b"%PDF-1.4 geheimer Inhalt")
        self.assertGreater(chats.used(uid_of(a)), 0)
        self.assertEqual(a.post("/api/chats/back", json={"id": cid, "mid": mid}).status_code, 200)
        self.assertFalse(os.path.exists(chats._media_file(cid, mid, "f")))
        helpers.set_config(chats_media=False)                   # attachments need the media switch here too
        box, _ = da.box(cid, {"t": ""}, keys_of(a, cid))
        r = a.post(f"/api/chats/media?id={cid}&kind=box", content=json.dumps(box).encode() + b"\n" + blob)
        self.assertEqual(r.status_code, 403)

    def test_live_and_journal_numbers_only_and_a_deleted_profile_takes_its_keys(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            a, b, da, db, cid = self.pair("Chbea", "Chcosmo")
            box, _ = da.box(cid, {"t": "Journalprobe"}, keys_of(a, cid))
            a.post("/api/chats/send", json={"id": cid, "box": box})
        self.assertIn("chats: private key added", out.getvalue())
        self.assertIn("kind priv", out.getvalue())
        self.assertNotIn("Journalprobe", out.getvalue())
        self.assertNotIn("Chbea", out.getvalue())
        lv = chats.for_live()
        self.assertTrue(lv["private_on"])
        self.assertGreaterEqual(lv["private"], 1)
        self.assertGreaterEqual(lv["devices"], 2)
        self.assertGreaterEqual(lv["private_sent"], 1)
        import live
        snap = json.dumps(live.snapshot("admin"))
        self.assertIn("privat", snap)
        self.assertNotIn("Chbea", snap)
        uid = uid_of(b)
        self.assertEqual(ADMIN.delete(f"/api/admin/profiles/{uid}").status_code, 200)
        self.assertEqual(chatsec._load(uid), [])
