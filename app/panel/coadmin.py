"""Profiles as admins (V01.0.255, plan plaene/benutzer-als-admin.md; since V01.0.541 without the admin mode,
plan plaene/admin-ohne-zweite-stufe.md, Dominik 2026-10-14 „A2 B1 C1“).

The admin gives a profile one of two roles:

    "admin"     Admin: everything the panel password may, except the password's own things (core.main_auth: the
                password itself, its second step, signing it out everywhere). It stays the way in when nothing else
                works (Notzugang: the address with #admin, `sudo speech-spark notzugang`).
    "manager"   Verwalter: only MANAGER below (Zustand, Logs, profiles and devices, feature switches)

There is no second stage: a profile with a role IS admin in its own browser login and in its own iPhone app,
as long as
  - its second login step is on (a role is only given then; switched off, the rights rest until it is on again),
  - the browser login was made with that second step (code, passkey or a browser the profile trusts:
    profiles.second_step_of), not with the PIN alone, not by "Am Handy weitermachen", not before the second step
    was set up (the mark is the second step's "since"),
  - the app key was made after the second step was set up and the profile may use the iPhone app.
Speakers, the watch, Telegram, Siri, MCP and own programs never act as admin; guests never get a role.

One admin profile is the "main" one (Haupt-Admin): its code also counts for the panel password (mfa.OWNER), only
it or the panel password changes it (its profile, its role, who is main). The first admin role the panel password
gives makes that profile main. The last admin role cannot be taken away by a profile, only by the password.
Every admin request is logged with who did it (by); admin profiles hear of new admin logins and role changes.

    STATE/admins.json  {"main": "<profile id>" | "", "users": {uid: {"role", "since", "by"}}}
                       (before V01.0.541: "on", "notify", roles owner/coadmin/manager: read as below)
"""
import json
import os
import re
import threading
import time

import mfa
import profiles

STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
FILE = os.path.join(STATE, "admins.json")
ROLES = ("admin", "manager")
NAMES = {"admin": "Admin", "manager": "Verwalter"}
MAX_ADMINS = 5
_UID = re.compile(r"u_[0-9a-f]{12}")
_OLD = {"owner": "admin", "coadmin": "admin", "manager": "manager"}   # roles before V01.0.541
_lock = threading.Lock()

# What a Verwalter may reach (method, path); everything else stays closed for him.
_P, _D = r"u_[0-9a-f]{12}", r"d_[0-9a-f]{12}"
MANAGER = tuple((frozenset(m), re.compile(p)) for m, p in (
    (("GET",), r"/api/status"), (("GET",), r"/api/languages"), (("GET",), r"/api/logfilter"),
    (("GET",), r"/api/logs/[a-z\-]+"), (("GET",), r"/api/vorrang"), (("GET",), r"/api/livecheck"),
    (("GET",), r"/api/quality"), (("GET",), r"/api/update"), (("GET",), r"/api/update/progress"),
    (("GET",), r"/api/admin/rooms"), (("GET",), r"/api/admin/wissen"), (("GET",), r"/api/admin/protocol"),
    (("GET", "PUT"), r"/api/admin/switches"), (("GET",), r"/api/admin/features"), (("PUT",), rf"/api/admin/features/[a-z0-9_]+/profiles/{_P}"),
    (("GET", "POST"), r"/api/admin/profiles"), (("GET", "PUT", "DELETE"), rf"/api/admin/profiles/{_P}"),
    (("PUT",), rf"/api/admin/profiles/{_P}/call"), (("DELETE",), rf"/api/admin/profiles/{_P}/mfa"),
    (("DELETE",), rf"/api/admin/profiles/{_P}/sessions/[0-9a-f]{{16}}"),
    (("DELETE",), rf"/api/admin/profiles/{_P}/trusted/[0-9a-f]{{16}}"),
    (("POST",), r"/api/admin/devices"), (("PUT", "DELETE"), rf"/api/admin/devices/{_D}"),
    (("GET",), r"/api/admin/join"), (("POST",), r"/api/admin/join/invites"), (("DELETE",), r"/api/admin/join/invites/i_[0-9a-f]{12}"),
    (("POST",), rf"/api/admin/profiles/{_P}/remind"),
))


# ---------------------------------------------------------------- the list
def _read():
    try:
        with open(FILE) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d = d if isinstance(d, dict) else {}
    users = d.get("users") if isinstance(d.get("users"), dict) else {}
    users = {u: x for u, x in users.items() if _UID.fullmatch(str(u)) and isinstance(x, dict) and x.get("role") in ROLES + tuple(_OLD)}
    if "on" in d:
        # the old file (before V01.0.541): the switch "Benutzer als Admin" off meant no role counted, so none counts
        # now either; the old Haupt-Admin profile (owner) stays the main one, its code is the password's
        owner = next((u for u, x in users.items() if x.get("role") == "owner"), "")
        users = {u: {"role": _OLD[x["role"]], "since": x.get("since"), "by": x.get("by", "main")}
                 for u, x in users.items()} if d.get("on") is True else {}
        main = owner if d.get("on") is True else ""
    else:
        main = d.get("main") if _UID.fullmatch(str(d.get("main") or "")) else ""
    main = main if users.get(main, {}).get("role") == "admin" else ""
    return {"main": main, "users": users}


def _write(d):
    os.makedirs(STATE, exist_ok=True)
    tmp = FILE + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "w") as f:
        json.dump(d, f)
    os.replace(tmp, FILE)


def role(uid):
    """The role this profile was given ("" for none). It acts only with its second step on (session)."""
    x = _read()["users"].get(uid)
    return x["role"] if x and uid in profiles.user_ids() else ""


def acts(uid):
    """The role while it counts: given and the profile's second step on, else ""."""
    r = role(uid)
    return r if r and mfa.enabled(uid) else ""


def main_uid():
    """The main admin profile (Haupt-Admin): hears of admin things, its code is also the password's; "" for none."""
    m = _read()["main"]
    return m if m in profiles.user_ids() else ""


def _owner():
    return main_uid() or None


mfa.OWNER[0] = _owner


def admin_uids():
    """Every profile whose role "admin" counts now, the main one first."""
    d, ids = _read(), profiles.user_ids()
    out = [u for u, x in d["users"].items() if x["role"] == "admin" and u in ids and mfa.enabled(u)]
    return sorted(out, key=lambda u: u != d["main"])


def listing():
    d = _read()
    known = {u["id"]: u["name"] for u in profiles.names()}
    return {"main": d["main"] if d["main"] in known else "", "max": MAX_ADMINS,
            "users": [{"id": u, "name": known[u], "role": x["role"], "since": x.get("since"), "mfa": mfa.enabled(u),
                       "main": u == d["main"]}
                      for u, x in d["users"].items() if u in known]}


def set_role(uid, new, by="main"):
    """new: a role, or "" to take it away. by: "main" (the panel password) or the acting profile's id."""
    if uid not in profiles.user_ids():
        raise LookupError("no such profile")
    if new and new not in ROLES:
        raise ValueError("role must be admin, manager or empty")
    if new and not mfa.enabled(uid):
        raise ValueError("Erst braucht das Profil seinen zweiten Anmeldeschritt (Ich → Sicherheit).")
    with _lock:
        d = _read()
        d["users"] = {u: x for u, x in d["users"].items() if u in profiles.user_ids()}
        if by != "main" and uid == d["main"] and by != uid:
            raise PermissionError("Den Haupt-Admin ändert nur er selbst oder das Panel-Passwort.")
        admins = [u for u, x in d["users"].items() if x["role"] == "admin"]
        if by != "main" and new != "admin" and admins == [uid]:
            raise ValueError("Das ist die letzte Admin-Rolle. Erst einem anderen Profil Admin geben.")
        if not new:
            d["users"].pop(uid, None)
        else:
            if uid not in d["users"] and len(d["users"]) >= MAX_ADMINS:
                raise ValueError(f"höchstens {MAX_ADMINS} Profile mit Admin-Rolle")
            if d["users"].get(uid, {}).get("role") != new:
                d["users"][uid] = {"role": new, "since": int(time.time()), "by": by}
        if d["users"].get(d["main"], {}).get("role") != "admin":
            d["main"] = ""
        if not d["main"] and by == "main" and new == "admin":
            d["main"] = uid   # the first admin the password gives is the main one
        _write(d)


def set_main(uid, by="main"):
    """Makes an admin profile the main one (its code then also counts for the panel password)."""
    with _lock:
        d = _read()
        if by != "main" and by != d["main"]:
            raise PermissionError("Den Haupt-Admin wählt nur der Haupt-Admin oder das Panel-Passwort.")
        if uid and (d["users"].get(uid, {}).get("role") != "admin" or not mfa.enabled(uid)):
            raise ValueError("Haupt-Admin kann nur ein Profil mit der Rolle Admin und zweitem Anmeldeschritt sein.")
        d["main"] = uid or ""
        _write(d)


def unlink_main():
    """The emergency access (notzugang.py): the password no longer asks the main profile's code."""
    with _lock:
        d = _read()
        was = d["main"]
        d["main"] = ""
        _write(d)
    return bool(was)


def forget(uid):
    """A deleted profile leaves the list."""
    with _lock:
        d = _read()
        if uid in d["users"] or d["main"] == uid:
            d["users"].pop(uid, None)
            d["main"] = "" if d["main"] == uid else d["main"]
            _write(d)


# ---------------------------------------------------------------- who acts as admin
def session(request):
    """{"id", "name", "role", "via"} of the profile behind this request when it acts as admin, else None.
    via: "b" (its own browser login) or the iPhone app key's id."""
    if request.scope.get("speech_profile") or request.scope.get("speech_mcp"):
        return None
    d = profiles._load()
    if request.headers.get(profiles.DEVICE_HEADER):
        dev = profiles._device(d, request)
        if not dev or dev.get("scope") != "app":
            return None
        uid, via = dev["user"], dev["id"]
    else:
        raw = request.cookies.get(profiles.COOKIE, "")
        u, _ = profiles._cookie_user(d, raw)
        if not u:
            return None
        uid, via = u["id"], "b"
    entry = _read()["users"].get(uid)
    mark = mfa.mark(uid)
    if not entry or not mark or not mfa.enabled(uid) or uid not in profiles.user_ids():
        return None
    if via == "b":
        if profiles.second_step_of(raw) != mark:
            return None   # signed in with the PIN alone, by "Am Handy weitermachen" or before the second step
    else:
        import iphone
        import notaus
        # an app key made before the second step was set up does not count (unknown "since" in very old files: it does)
        if int(dev.get("created") or 0) < int(mfa.status(uid)["since"] or 0) or not iphone.allowed(uid) or notaus.own(uid):
            return None
    u = next(x for x in d["users"] if x["id"] == uid)
    return {"id": uid, "name": u["name"], "role": entry["role"], "via": via}


def manager_may(request):
    path, method = request.scope.get("path") or "", request.method
    return any(method in m and p.fullmatch(path) for m, p in MANAGER)


def allows(request):
    """True when this request comes from an admin profile whose role reaches it. Marks the request."""
    s = session(request)
    if not s or (s["role"] == "manager" and not manager_may(request)):
        return False
    request.scope["speech_coadmin"] = s
    return True


async def tell(text, skip=""):
    """A note (push) to every admin profile but `skip`, as each set it up. Returns how many devices it reached."""
    import push
    reached = 0
    for uid in admin_uids():
        if uid == skip:
            continue
        try:
            reached += await push.send(uid, "🔐 Spark", text, tag="admin", private=False)
        except Exception as e:
            print("coadmin: note failed:", type(e).__name__, flush=True)
    return reached
