"""Profiles as admins (V01.0.255, plan plaene/benutzer-als-admin.md).

The main admin (the panel password) can give a profile one of three roles:

    "owner"     Haupt-Admin (V01.0.275, plan „Vereinheitlichen“ Phase 7): the main admin as a profile, so one login
                (PIN, second step, admin mode with a fresh code) is enough. Everything the panel password may
                (core.owner_auth) except the password's own things: the password itself, its second step and
                signing it out everywhere stay the way in when nothing else works. Only the password gives or
                takes this role, and only one profile has it.

    "coadmin"   Mit-Admin: everything the main admin can, except the main admin's own things (core.main_auth:
                roles, admin password and second step, restoring and downloading backups) and changes to
                another admin profile (its PIN, second step, devices, deleting it; admin.py)
    "manager"   Verwalter: only MANAGER below (Zustand, Logs, profiles and devices, feature switches)

A role alone gives nothing. The profile needs its own second step, the main admin needs his, the switch
"Benutzer als Admin" must be on, and the profile opens the admin mode with a fresh code ("Admin-Modus",
like sudo): a cookie that ends after IDLE seconds without use and after LONGEST in any case. It is signed
with the profiles' login key (users/secret, never in a backup) over the profile's PIN, its "log out
everywhere" count, its second step, its role and when the role was given: changing any of these, or
taking the role away, ends every open admin mode of that profile at once. In the browser the admin mode
holds only together with the same profile's login; from the iPhone app ("via" a device id) only while that
app key exists and its profile keeps "Spark verwalten in der App" on.

The role never reaches the assistant: speech, speakers, the watch, Telegram, mail and Siri have no admin
tools, and guests never get a role. Every admin request is logged with who did it (by).

    STATE/admins.json  {"on": bool, "notify": "<profile id>" | "", "users": {uid: {"role", "since", "k", "by"}}}
                       (k: random per role given; signs the admin mode, so a new role ends the old ones)
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time

import guard
import mfa
import profiles

STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
FILE = os.path.join(STATE, "admins.json")
ROLES = ("owner", "coadmin", "manager")
NAMES = {"owner": "Haupt-Admin", "coadmin": "Mit-Admin", "manager": "Verwalter"}
MAX_ADMINS = 5
COOKIE = "speech_spark_elev"
IDLE = 900               # 15 minutes without use end the admin mode
LONGEST = 8 * 3600       # and 8 hours in any case
RENEW = 60               # the cookie is renewed at most once a minute while used
_UID = re.compile(r"u_[0-9a-f]{12}")
_VIA = re.compile(r"b|d_[0-9a-f]{12}")
_lock = threading.Lock()

# What a Verwalter may reach (method, path); everything else stays closed for him.
_P, _D = r"u_[0-9a-f]{12}", r"d_[0-9a-f]{12}"
MANAGER = tuple((frozenset(m), re.compile(p)) for m, p in (
    (("GET",), r"/api/status"), (("GET",), r"/api/languages"), (("GET",), r"/api/logfilter"),
    (("GET",), r"/api/logs/[a-z\-]+"), (("GET",), r"/api/vorrang"), (("GET",), r"/api/livecheck"),
    (("GET",), r"/api/quality"), (("GET",), r"/api/update"), (("GET",), r"/api/update/progress"),
    (("GET",), r"/api/admin/rooms"), (("GET",), r"/api/admin/wissen"), (("GET",), r"/api/admin/protocol"),
    (("GET", "PUT"), r"/api/admin/switches"), (("POST",), r"/api/admin/elevate/keep"),
    (("GET",), r"/api/admin/features"), (("PUT",), rf"/api/admin/features/[a-z0-9_]+/profiles/{_P}"),
    (("PUT",), r"/api/admin/features/[a-z0-9_]+/new"),
    (("GET", "POST"), r"/api/admin/profiles"), (("GET", "PUT", "DELETE"), rf"/api/admin/profiles/{_P}"),
    (("PUT",), rf"/api/admin/profiles/{_P}/call"), (("DELETE",), rf"/api/admin/profiles/{_P}/mfa"),
    (("DELETE",), rf"/api/admin/profiles/{_P}/sessions/[0-9a-f]{{16}}"),
    (("POST",), r"/api/admin/devices"), (("PUT", "DELETE"), rf"/api/admin/devices/{_D}"),
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
    users = {u: x for u, x in users.items() if _UID.fullmatch(str(u)) and isinstance(x, dict) and x.get("role") in ROLES}
    notify = d.get("notify") if _UID.fullmatch(str(d.get("notify") or "")) else ""
    return {"on": d.get("on") is True, "notify": notify, "users": users}


def _write(d):
    os.makedirs(STATE, exist_ok=True)
    tmp = FILE + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "w") as f:
        json.dump(d, f)
    os.replace(tmp, FILE)


def on():
    return _read()["on"]


def role(uid):
    """The role the main admin gave this profile ("" for none; also while the switch is off)."""
    x = _read()["users"].get(uid)
    return x["role"] if x and uid in profiles.user_ids() else ""


def listing():
    d = _read()
    known = {u["id"]: u["name"] for u in profiles.names()}
    return {"on": d["on"], "notify": d["notify"] if d["notify"] in known else "", "max": MAX_ADMINS,
            "main_mfa": mfa.enabled(mfa.ADMIN),
            "users": [{"id": u, "name": known[u], "role": x["role"], "since": x.get("since"), "mfa": mfa.enabled(u)}
                      for u, x in d["users"].items() if u in known]}


def set_on(value):
    if value and not mfa.enabled(mfa.ADMIN):
        raise ValueError("Erst den zweiten Anmeldeschritt für den Hauptadmin einschalten (Einstellungen → Sicherheit).")
    with _lock:
        d = _read()
        d["on"] = bool(value)
        _write(d)


def set_notify(uid):
    if uid and uid not in profiles.user_ids():
        raise LookupError("no such profile")
    with _lock:
        d = _read()
        d["notify"] = uid or ""
        _write(d)


def set_role(uid, new):
    """new: a role, or "" to take it away. A new role (also a changed one) ends the profile's admin mode."""
    if uid not in profiles.user_ids():
        raise LookupError("no such profile")
    if new and new not in ROLES:
        raise ValueError("role must be owner, coadmin, manager or empty")
    with _lock:
        d = _read()
        d["users"] = {u: x for u, x in d["users"].items() if u in profiles.user_ids()}
        if new == "owner" and any(x["role"] == "owner" for u, x in d["users"].items() if u != uid):
            raise ValueError("Es gibt schon einen Haupt-Admin. Dort zuerst die Rolle ändern.")
        if not new:
            d["users"].pop(uid, None)
        else:
            if uid not in d["users"] and len(d["users"]) >= MAX_ADMINS:
                raise ValueError(f"höchstens {MAX_ADMINS} Profile mit Admin-Rolle")
            if d["users"].get(uid, {}).get("role") != new:
                d["users"][uid] = {"role": new, "since": int(time.time()), "k": secrets.token_hex(8), "by": "main"}
        _write(d)


def forget(uid):
    """A deleted profile leaves the list (and is no longer the one told about admin modes)."""
    with _lock:
        d = _read()
        if uid in d["users"] or d["notify"] == uid:
            d["users"].pop(uid, None)
            d["notify"] = "" if d["notify"] == uid else d["notify"]
            _write(d)


# ---------------------------------------------------------------- the admin mode
def _sig(u, entry, start, issued, family, via):
    msg = "|".join(("speech-spark-elev", u["id"], u["pin"], str(u.get("epoch", 0)), entry["role"], str(entry.get("k")),
                    mfa.session_salt(u["id"]), str(start), str(issued), family, via))
    return hmac.new(profiles._secret(), msg.encode(), hashlib.sha256).hexdigest()


def _token(uid, start, family, via, now=None):
    u = next((x for x in profiles._load()["users"] if x["id"] == uid), None)
    entry = _read()["users"].get(uid)
    if not u or not entry:
        return None
    issued = int(now if now is not None else time.time())
    return f"{uid}.{start}.{issued}.{family}.{via}.{_sig(u, entry, start, issued, family, via)}"


def start(uid, via, now=None):
    """A new admin mode for this profile: the cookie value."""
    now = int(now if now is not None else time.time())
    return _token(uid, now, secrets.token_hex(8), via, now)


def _parse(raw):
    p = (raw or "").split(".")
    if len(p) != 6 or not _UID.fullmatch(p[0]) or not p[1].isdigit() or not p[2].isdigit() \
            or not re.fullmatch(r"[0-9a-f]{16}", p[3]) or not _VIA.fullmatch(p[4]):
        return None
    return {"uid": p[0], "start": int(p[1]), "issued": int(p[2]), "family": p[3], "via": p[4], "sig": p[5]}


def session(request, now=None):
    """{"id", "name", "role", "via", "start", "issued", "family"} of a valid admin mode in this request, else None."""
    raw = request.cookies.get(COOKIE, "")
    t = _parse(raw)
    if not t:
        return None
    now = now if now is not None else time.time()
    d = _read()
    entry = d["users"].get(t["uid"])
    if not d["on"] or not entry or not mfa.enabled(mfa.ADMIN) or not mfa.enabled(t["uid"]):
        return None
    if now - t["issued"] > IDLE or now - t["start"] > LONGEST or t["issued"] < t["start"] or t["issued"] > now + 60:
        return None
    u = next((x for x in profiles._load()["users"] if x["id"] == t["uid"]), None)
    if not u or not secrets.compare_digest(t["sig"], _sig(u, entry, t["start"], t["issued"], t["family"], t["via"])):
        return None
    if guard.revoked("elev-family:" + t["family"]):
        return None
    if t["via"] == "b":
        # only together with the same profile's own browser login
        cu, _ = profiles._cookie_user(profiles._load(), request.cookies.get(profiles.COOKIE, ""))
        if not cu or cu["id"] != t["uid"]:
            return None
    elif not app_ok(t["uid"], t["via"]):
        return None
    return {"id": u["id"], "name": u["name"], "role": entry["role"], "via": t["via"], "start": t["start"],
            "issued": t["issued"], "family": t["family"]}


def app_ok(uid, did):
    """The iPhone app's key `did` still exists, belongs to `uid` and may open "Spark verwalten"."""
    dev = next((x for x in profiles._load()["devices"] if x["id"] == did), None)
    if not dev or dev.get("user") != uid or dev.get("scope") != "app":
        return False
    import iphone
    return iphone.allowed(uid) and iphone.area_on(uid, "app_admin")


def manager_may(request):
    path, method = request.scope.get("path") or "", request.method
    return any(method in m and p.fullmatch(path) for m, p in MANAGER)


def allows(request):
    """True when this request comes with a valid admin mode whose role reaches it. Marks the request."""
    s = session(request)
    if not s or (s["role"] == "manager" and not manager_may(request)):
        return False
    request.scope["speech_coadmin"] = s
    return True


def renewed(request, now=None):
    """A fresh cookie value for an admin mode in use (same start and family), else None."""
    now = int(now if now is not None else time.time())
    s = session(request, now)
    if not s or now - s["issued"] < RENEW:
        return None
    return _token(s["id"], s["start"], s["family"], s["via"], now)


def end(request):
    """Ends the admin mode of this request (every copy of it)."""
    t = _parse(request.cookies.get(COOKIE, ""))
    if t:
        guard.revoke("elev-family:" + t["family"], LONGEST + 120)
    return t


def expires(s, now=None):
    """When the admin mode ends without further use (unix time)."""
    return min(s["issued"] + IDLE, s["start"] + LONGEST)


async def tell_main(name, role_name, via):
    """Optional note to the profile the main admin chose (push, as that profile set it up)."""
    uid = _read()["notify"]
    if not uid or uid not in profiles.user_ids():
        return 0
    import push
    where = "in der iPhone-App" if via != "b" else "im Browser"
    try:
        return await push.send(uid, "🔐 Spark", f"{name} hat den Admin-Modus geöffnet ({role_name}, {where}).",
                               tag="admin", private=False)
    except Exception as e:
        print("coadmin: note failed:", type(e).__name__, flush=True)
        return 0
