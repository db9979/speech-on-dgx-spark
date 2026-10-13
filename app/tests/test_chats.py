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


def switch(chats_on=True, groups=False, msgs=True):
    helpers.set_config(messages=msgs, chats=chats_on, chats_groups=groups)


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
        helpers.set_config(messages=False, chats=False, chats_groups=False)
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
        say(a, cid, "Geheimes Rezept 4711")
        raw = read(chats._chat_file(cid)) + read(chats._index_file())
        self.assertNotIn("Geheimes Rezept", raw)
        self.assertNotIn("4711", raw)
        x = json.loads(read(chats._chat_file(cid)))["items"][-1]
        self.assertEqual(chats.unseal(x["text"], cid, x["id"]), "Geheimes Rezept 4711")
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
        big = a.post("/api/chats/send", content=b'{"id":"' + b"x" * 70000 + b'"}', headers={"Content-Type": "application/json"})
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
        self.assertEqual(messages._load(ub)["items"], [])            # not into the mailbox
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
        self._tr = messages._transcribe

        async def tr(pcm):
            return "Bin gleich da"
        messages._transcribe = tr

    def tearDown(self):
        messages._transcribe = self._tr
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
