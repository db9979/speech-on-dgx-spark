"""Gruppen über Sparks (Verbund V2 Teil 2, plan plaene/messenger-d-v2.md Teil 3, Dominik 2026-10-14 "3a").

A group always belongs to the Spark it was made on (its home). Its admins there can add people on other Sparks, but
only their own accepted contacts (verbund.py state "ok"): that person already said "Annehmen" to the admin, as a
group on one Spark takes only people who take messages from its admin. Who is in, who is admin and the group's name
are decided on the home Spark alone; another Spark only shows the group.

    home Spark                                  member Spark
    gadd    to one person: you are in (name, the members' names)  -> a group chat kind "group" with "home" and "gid"
    gmsg    every message to every member on another Spark       -> stored like any group message
            <- gmsg of a member there: checked (in the group?), stored, sent on to the other Sparks' members
    gremove to one person: you are out                            -> the person leaves the chat
    gname   the new name                                          -> shown
    gmembers who is in now (to the people already in)            -> the member list shown there
            <- gleave: the person left there

At most MAX_SPARKS other Sparks and chats.MAX_MEMBERS people per group. A Spark that is away gets its part later
(verbund.py queue, 7 days). Text only for now; photos and files in groups across Sparks come with a later step.
Nothing of it goes to the model. Logs: "verbund: group …" with numbers only.
"""
import hashlib

import features

MAX_SPARKS = 10           # other Sparks in one group
TYPES = ("gadd", "gmsg", "gleave", "gremove", "gname", "gmembers")


def admin_on():
    return features.admin_on("verbundgruppen")


def usable(uid):
    """Groups, Verbund and this switch for the person (the admin did not block it)."""
    import chats
    import verbund
    return bool(verbund.usable(uid) and features.allowed("verbundgruppen", uid) and chats.groups_on())


def _log(what, **nums):
    import verbund
    verbund._log("group " + what, **nums)


def _addr(member):
    """The Spark address of a member of a group here: a profile's own, or the one of a person on another Spark."""
    import chats
    import verbund
    if chats.RID.fullmatch(member):
        return verbund.addr_of(member)
    return verbund.address(member)


def _dom(addr):
    return addr.rsplit("@", 1)[-1] if "@" in addr else ""


def far_cid(dom, gid):
    """The chat a member Spark keeps for the group gid of the home Spark dom (one for all its people in it)."""
    return "c" + hashlib.sha256(f"fg|{dom}|{gid}".encode()).hexdigest()[:12]


# ---------------------------------------------------------------- on the home Spark
def can_add(uid, rid):
    import verbund
    c = verbund.contact(uid, rid)
    return bool(admin_on() and usable(uid) and c and c.get("state") == "ok")


def sparks_of(members):
    import chats
    return {_dom(_addr(u)) for u in members if chats.RID.fullmatch(u)} - {""}


def _members_wire(meta):
    import chats
    names = chats._names()
    return [{"addr": a, "name": names.get(u, "")[:40]} for u in meta["members"][:chats.MAX_MEMBERS] if (a := _addr(u))]


def _send(rid, body, cid="", mid=""):
    import verbund
    addr = _addr(rid)
    h, d = verbund.split(addr) if addr else ("", "")
    if not d or not verbund.peer_allowed(d):
        return False
    verbund._enqueue(d, dict(body, to=h), cid, mid)
    return True


def added(cid, meta, admin, rids):
    """New members on other Spark: each hears it is in, with the group's name and who else is."""
    import chats
    import verbund
    name = chats.unseal(meta.get("name"), cid, "name")
    who = _members_wire(meta)
    n = sum(1 for r in rids if _send(r, {"type": "gadd", "from": verbund.handle(admin), "gid": cid, "name": name, "members": who}))
    _log("members added", n=n)


def removed(cid, rids):
    n = sum(1 for r in rids if _send(r, {"type": "gremove", "gid": cid}))
    _log("members removed", n=n)


def _one_each(meta, but=(), skip=""):
    """One member per other Spark (the chat there is one for all its people in the group); but: people left out,
    skip: a Spark left out."""
    import chats
    seen = {}
    for r in meta["members"]:
        if chats.RID.fullmatch(r) and r not in but:
            d = _dom(_addr(r))
            if d and d != skip:
                seen.setdefault(d, r)
    return list(seen.values())


def changed(cid, meta, but=()):
    """Who is in now, to the members on other Sparks (but: the ones that just heard it with gadd)."""
    who = _members_wire(meta)
    for r in _one_each(meta, but):
        _send(r, {"type": "gmembers", "gid": cid, "members": who})


def named(cid, meta, name):
    for r in _one_each(meta):
        _send(r, {"type": "gname", "gid": cid, "name": name})


def out(cid, meta, author, mid, text, reply=""):
    """A message in a group of this Spark to its members on other Sparks (not to the Spark it came from: it has it)."""
    import chats
    names = chats._names()
    by = _addr(author)
    n = 0
    for r in _one_each(meta, skip=_dom(by)):
        n += _send(r, {"type": "gmsg", "gid": cid, "id": mid, "text": text, "reply": reply, "by": by,
                       "byname": names.get(author, "")[:40]}, cid, mid)
    return n


# ---------------------------------------------------------------- on a member Spark
def member_out(uid, meta, mid, text, reply=""):
    """A message of a person here in a group of another Spark: to its home Spark, which sends it on."""
    import verbund
    verbund._enqueue(meta["home"], {"type": "gmsg", "from": verbund.handle(uid), "to": "", "gid": meta["gid"], "id": mid,
                                    "text": text, "reply": reply})


def member_left(uid, meta):
    import verbund
    verbund._enqueue(meta["home"], {"type": "gleave", "from": verbund.handle(uid), "to": "", "gid": meta["gid"]})
    _log("left there")


# ---------------------------------------------------------------- what comes in (verbund._handle after its checks)
def handle(dom, b, now):
    """One group request of an allowed Spark whose signature was checked. Anything that does not fit is dropped."""
    import chats
    import verbund
    kind, gid = b["type"], str(b.get("gid") or "")
    if not chats.CID.fullmatch(gid) or not admin_on():
        _log("dropped", why=1)
        return
    if kind in ("gmsg", "gleave") and not b.get("to"):
        return _at_home(dom, b, gid, now)
    cid = far_cid(dom, gid)
    if kind == "gmsg":       # one for all people here in the group, whoever it names
        by = str(b.get("by") or "").lower()
        mid = str(b.get("id") or "")
        try:
            d = verbund.split(by)[1]
        except ValueError:
            d = ""
        if not d or d == verbund.domain() or not verbund.MID.fullmatch(mid):
            _log("dropped", why=5)       # one of the own people's messages coming back, or no sender
            return
        r = verbund.remember(by, verbund._clean_name(b.get("byname")))
        reply = str(b.get("reply") or "")
        if not chats.far_group_msg(cid, r, mid, str(b.get("text") or ""),
                                   reply if verbund.MID.fullmatch(reply) else "", now):
            _log("dropped", why=6)
        return
    to = verbund.uid_of_handle(str(b.get("to") or ""))
    if not to or not usable(to):
        _log("dropped", why=2)
        return
    if kind == "gadd":
        frm = str(b.get("from") or "").lower()
        adder = verbund.rid_of(f"{frm}@{dom}") if verbund.HANDLE.fullmatch(frm) else ""
        c = verbund.contact(to, adder) if adder else None
        if not c or c.get("state") != "ok":
            _log("dropped", why=3)      # only an accepted contact can put someone into a group
            return
        members = _people(b)
        chats.far_group_in(to, cid, dom, gid, chats.clean_name(str(b.get("name") or "")) or "Gruppe",
                           [adder] + [r for r in members if r != adder], adder, now)
        _log("joined there")
        return
    if kind == "gmembers":
        chats.far_group_members(to, cid, _people(b), now)
        return
    if kind == "gremove":
        chats.far_group_out(to, cid, now)
        _log("removed there")
        return
    if kind == "gname":
        chats.far_group_name(to, cid, chats.clean_name(str(b.get("name") or "")), now)


def _people(b):
    """The members on other Sparks a home Spark names (its own people and those of a third Spark), remembered with
    their shown name; the people of this Spark are in by their own gadd and left out here."""
    import chats
    import verbund
    out = []
    for m in (b.get("members") if isinstance(b.get("members"), list) else [])[:chats.MAX_MEMBERS]:
        if not isinstance(m, dict):
            continue
        a = str(m.get("addr") or "").lower()
        try:
            d = verbund.split(a)[1]
        except ValueError:
            continue
        if d != verbund.domain():
            out.append(verbund.remember(a, verbund._clean_name(m.get("name"))))
    return [r for r in out if r]


def _at_home(dom, b, gid, now):
    """A member on another Spark writes into or leaves a group of this Spark."""
    import chats
    import verbund
    frm = str(b.get("from") or "").lower()
    if not verbund.HANDLE.fullmatch(frm):
        _log("dropped", why=7)
        return
    rid = verbund.rid_of(f"{frm}@{dom}")
    meta = chats._index().get(gid)
    if not meta or meta.get("kind") != "group" or meta.get("home") or rid not in meta["members"]:
        _log("dropped", why=4)
        return
    if b["type"] == "gleave":
        chats.far_member_left(gid, rid, now)
        return
    mid = str(b.get("id") or "")
    if not verbund.MID.fullmatch(mid):
        _log("dropped", why=8)
        return
    reply = str(b.get("reply") or "")
    meta = chats.home_group_in(gid, rid, mid, str(b.get("text") or ""), reply if verbund.MID.fullmatch(reply) else "", now)
    if meta:
        out(gid, meta, rid, mid, chats.clean(str(b.get("text") or "")), reply)


def for_live():
    import chats
    if not admin_on():
        return {"on": False}
    idx = chats._index()
    return {"on": True, "home": sum(1 for c in idx.values() if chats.spans(c) and not c.get("home")),
            "there": sum(1 for c in idx.values() if c.get("home"))}
