"""Back in when locked out: sudo speech-spark notzugang (V01.0.439, Dominik 2026-10-12 „wenn ich mich aufgrund eines
updates ausgesperrt habe …“). Only on the Spark itself: the shell command needs root and runs this file as the
service user, the panel has no way to start it.

It sets a new panel password (shown once), moves the emergency access's own second step aside (kept as .bak, set it
up again under Einstellungen → Sicherheit), and unlinks the main admin profile (Haupt-Admin) so the password no longer
asks for its code (mfa.linked); the roles stay, the profile can be made main again. Every login with the password
ends (a new password). It is noted in the change log (notzugang_cli) and the profiles with an admin role get a push."""
import asyncio
import os
import secrets
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coadmin  # noqa: E402
import core  # noqa: E402
import guard  # noqa: E402
import mfa  # noqa: E402
import profiles  # noqa: E402

LETTERS = "abcdefghjkmnpqrstuvwxyz23456789"   # no 0/o, 1/l/i: read off a terminal and typed on a phone
NOTE = "Der Notzugang wurde auf dem Spark zurückgesetzt (neues Panel-Passwort, Haupt-Admin gelöst)."


def new_password():
    return "-".join("".join(secrets.choice(LETTERS) for _ in range(5)) for _ in range(4))


def admins():
    """The profiles that hear about it: every one with an admin role."""
    d = coadmin._read()
    ids = profiles.user_ids()
    return [u for u in d["users"] if u in ids]


async def tell(uids):
    reached = 0
    for uid in uids:
        try:
            import push
            reached += await asyncio.wait_for(push.send(uid, "🔐 Spark", NOTE, tag="admin", private=False), 20)
        except Exception as e:
            print("notzugang: push failed:", type(e).__name__, flush=True)
    return reached


def reset(now=None):
    """Does it; returns the new password and what changed (no secrets besides the password)."""
    now = int(now or time.time())
    password = new_password()
    core.store_password(password)
    own = mfa._own_path(mfa.ADMIN)
    step = os.path.exists(own)
    if step:
        os.replace(own, f"{own}.{now}.bak")
    unlinked = coadmin.unlink_main()
    guard.log("notzugang_cli", second_step_off=step or None, main_unlinked=unlinked or None)
    return password, {"second_step_off": step, "main_unlinked": unlinked, "notify": admins()}


def main():
    password, done = reset()
    reached = asyncio.run(tell(done["notify"])) if done["notify"] else 0
    print("Neues Panel-Passwort (wird nur jetzt gezeigt):")
    print()
    print("    " + password)
    print()
    print("Anmelden: https://<Adresse des Spark>/#admin mit diesem Passwort, ohne Code.")
    if done["second_step_off"]:
        print("Zweiter Schritt des Notzugangs: aus (alte Datei als .bak). Neu einrichten unter Einstellungen → Sicherheit.")
    if done["main_unlinked"]:
        print("Haupt-Admin: gelöst, die Rollen bleiben. Wieder wählen unter Einstellungen → Sicherheit → Admin-Rechte.")
    print(f"Push an Admins: {reached} Gerät(e) erreicht." if done["notify"] else "Push: kein Profil mit Admin-Rolle.")
    print("Steht im Änderungsprotokoll (notzugang_cli).")


if __name__ == "__main__":
    main()
