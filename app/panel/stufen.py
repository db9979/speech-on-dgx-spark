"""Wann fragt der Spark nach dem Code? One list for every change that needs the second step (V01.0.427,
plan plaene/zweiter-faktor-einheitlich.md).

Three levels, nothing in between:
  free     reading and ordinary settings: no code (not listed here)
  confirm  "Bestätigen": a new account, device or key for the Spark, people changed or removed, settings that
           send data elsewhere. A right code (or passkey) counts for core.CONFIRM_WINDOW in the same login.
  protect  "Schutz ändern": the protection itself (password, second step, passkeys, roles, code words), all
           data in or out (backups, offsite, report token), the emergency stop off, a new Spark version,
           Asked every time, also of admins (who skip "Bestätigen": core.admin_login).

core.confirm_code takes the level from here (by method and route), so one place decides. The self-test
tests/test_stufen.py finds every route that asks for a code and fails when it is missing here or listed with
another level than its code says. The page Ich -> Sicherheit -> „Wann fragt der Spark?" is made from this list,
and the 428 answer carries the entry so the dialog can say what the code is for and how long it counts.
"""
import base64
import json

CONFIRM, PROTECT = "confirm", "protect"

# (method, route) -> (level, area, what in German, what in English)
LIST = {
    # ------------------------------------------------------------------ protection itself
    ("POST", "/api/password"): (PROTECT, "Schutz", "Panel-Passwort ändern", "Change the panel password"),
    ("POST", "/api/mfa/setup"): (PROTECT, "Schutz", "Zweiten Schritt des Notzugangs einrichten", "Set up the emergency access's second step"),
    ("POST", "/api/mfa/disable"): (PROTECT, "Schutz", "Zweiten Schritt des Notzugangs ausschalten", "Switch off the emergency access's second step"),
    ("POST", "/api/mfa/recovery"): (PROTECT, "Schutz", "Neue Wiederherstellungscodes (Notzugang)", "New recovery codes (emergency access)"),
    ("POST", "/api/mfa/passkeys/begin"): (PROTECT, "Schutz", "Passkey für den Notzugang anlegen", "Add a passkey for the emergency access"),
    ("POST", "/api/profile/mfa/setup"): (PROTECT, "Schutz", "Zweiten Schritt neu einrichten", "Set up the second step again"),
    ("POST", "/api/profile/mfa/disable"): (PROTECT, "Schutz", "Zweiten Schritt ausschalten", "Switch off the second step"),
    ("POST", "/api/profile/mfa/recovery"): (PROTECT, "Schutz", "Neue Wiederherstellungscodes", "New recovery codes"),
    ("POST", "/api/profile/mfa/passkeys/begin"): (PROTECT, "Schutz", "Passkey anlegen", "Add a passkey"),
    ("PUT", "/api/admin/roles"): (PROTECT, "Schutz", "Haupt-Admin wählen", "Choose the main admin"),
    ("PUT", "/api/admin/roles/{uid}"): (PROTECT, "Schutz", "Admin-Rolle einer Person ändern", "Change a person's admin role"),
    ("DELETE", "/api/admin/profiles/{uid}/mfa"): (PROTECT, "Schutz", "Zweiten Schritt einer Person zurücksetzen", "Reset a person's second step"),
    ("PUT", "/api/profile/homeassistant/code"): (PROTECT, "Schutz", "Codewort für Home Assistant", "Code word for Home Assistant"),
    ("PUT", "/api/profile/speaker-code"): (PROTECT, "Schutz", "Codewort am Lautsprecher", "Code word at the speaker"),
    ("PUT", "/api/profile/telefon/pin"): (PROTECT, "Schutz", "Telefon-PIN", "Phone PIN"),
    ("POST", "/api/admin/notaus/off"): (PROTECT, "Schutz", "Notaus aufheben", "Lift the emergency stop"),
    ("POST", "/api/notaus/mine/off"): (PROTECT, "Schutz", "Eigenen Notaus aufheben", "Lift my own emergency stop"),
    ("POST", "/api/admin/notaus/mine/off"): (PROTECT, "Schutz", "Notaus einer Person aufheben", "Lift a person's emergency stop"),
    ("POST", "/api/admin/notaus/keys"): (PROTECT, "Schutz", "Notaus-Schlüssel für Home Assistant", "Emergency stop key for Home Assistant"),
    ("POST", "/api/iphone/update"): (PROTECT, "Schutz", "Spark-Update aus der App", "Spark update from the app"),
    # ------------------------------------------------------------------ all data in or out
    ("POST", "/api/backups/move"): (PROTECT, "Daten", "Sicherungen umziehen", "Move backups"),
    ("POST", "/api/backups/{name}/ticket"): (PROTECT, "Daten", "Sicherung herunterladen", "Download a backup"),
    ("POST", "/api/backups/{name}/restore"): (PROTECT, "Daten", "Sicherung einspielen", "Restore a backup"),
    ("POST", "/api/backups-upload"): (PROTECT, "Daten", "Sicherung hochladen", "Upload a backup"),
    ("PUT", "/api/admin/offsite"): (PROTECT, "Daten", "Ziel der Sicherung nach außen", "Offsite backup target"),
    ("PUT", "/api/admin/docling"): (PROTECT, "Daten", "Docling-Server für Dokumente", "Docling server for documents"),
    ("PUT", "/api/admin/report/token"): (PROTECT, "Daten", "Token für Problem-Meldungen", "Token for problem reports"),
    ("PUT", "/api/admin/ghtoken"): (PROTECT, "Daten", "GitHub-Token für Updates", "GitHub token for updates"),
    # ------------------------------------------------------------------ accounts, devices, keys (confirm)
    ("POST", "/api/profile/calendar"): (CONFIRM, "Konten", "Kalender verbinden", "Connect a calendar"),
    ("POST", "/api/profile/calserver"): (CONFIRM, "Konten", "App-Passwort für Kalender-Apps erzeugen", "Make an app password for calendar apps"),
    ("PUT", "/api/profile/calendar/{cid}/share"): (CONFIRM, "Konten", "Kalender mit einem anderen Profil teilen", "Share a calendar with another profile"),
    ("POST", "/api/profile/mail"): (CONFIRM, "Konten", "Mail-Konto verbinden", "Connect a mail account"),
    ("POST", "/api/profile/mail/folder/rename"): (CONFIRM, "Konten", "Mail-Ordner umbenennen", "Rename a mail folder"),
    ("POST", "/api/profile/mail/folder/remove"): (CONFIRM, "Konten", "Leeren Mail-Ordner entfernen", "Remove an empty mail folder"),
    ("POST", "/api/profile/mail/rules/{rid}/apply"): (CONFIRM, "Konten", "Mail-Regel auf vorhandene Mails anwenden", "Apply a mail rule to the mails already there"),
    ("POST", "/api/profile/contacts"): (CONFIRM, "Konten", "Adressbuch verbinden", "Connect an address book"),
    ("PUT", "/api/profile/homeassistant"): (CONFIRM, "Konten", "Home Assistant verbinden", "Connect Home Assistant"),
    ("POST", "/api/profile/telegram/link"): (CONFIRM, "Konten", "Telegram verbinden", "Connect Telegram"),
    ("POST", "/api/profile/remarkable/pair"): (CONFIRM, "Konten", "reMarkable verbinden", "Connect reMarkable"),
    ("POST", "/api/profile/feeds/inbox"): (CONFIRM, "Konten", "Reddit-Posteingang verbinden", "Connect the Reddit inbox"),
    ("PUT", "/api/profile/tidy"): (CONFIRM, "Konten", "Postfach aufräumen einstellen", "Set up mailbox tidying"),
    ("POST", "/api/profile/mymcp"): (CONFIRM, "Konten", "Eigenen Dienst verbinden", "Connect an own service"),
    ("PUT", "/api/profile/mymcp/{sid}"): (CONFIRM, "Konten", "Adresse oder Schlüssel eines eigenen Dienstes", "Address or key of an own service"),
    ("POST", "/api/profile/nas"): (CONFIRM, "Konten", "Speicherort verbinden", "Connect a place"),
    ("PUT", "/api/profile/nas/{nid}"): (CONFIRM, "Konten", "Benutzer, Passwort oder Zertifikat eines Speicherorts", "User, password or certificate of a place"),
    ("POST", "/api/profile/speicher"): (CONFIRM, "Konten", "Kopie meiner Daten einschalten", "Switch on the copy of my data"),
    ("PUT", "/api/profile/speicher/{tid}"): (CONFIRM, "Konten", "Ordner, Adresse oder Auslagern einer Kopie", "Folder, address or offloading of a copy"),
    ("POST", "/api/profile/mymcp/{sid}/oauth/start"): (CONFIRM, "Konten", "Eigenen Dienst anmelden", "Sign in an own service"),
    ("PUT", "/api/profile/mcp/conns/{cid}"): (CONFIRM, "Konten", "Rechte eines Programms (MCP)", "Rights of a program (MCP)"),
    ("POST", "/api/profile/mcp/actions/{aid}"): (CONFIRM, "Konten", "Aktion eines Programms erlauben", "Allow a program's action"),
    ("POST", "/api/profile/ha-events/key"): (CONFIRM, "Geräte", "Schlüssel für Home-Assistant-Meldungen", "Key for Home Assistant events"),
    ("POST", "/api/profile/room/ha"): (CONFIRM, "Geräte", "Schlüssel für den Raum-Modus", "Key for room mode"),
    ("POST", "/api/profile/voice"): (CONFIRM, "Geräte", "Stimme anlernen", "Teach my voice"),
    ("POST", "/api/profile/telefon/nummern"): (CONFIRM, "Geräte", "Eigene Rufnummer eintragen", "Add an own phone number"),
    ("POST", "/api/chats/keys"): (CONFIRM, "Geräte", "Gerät für private Chats eintragen", "Add a device for private chats"),
    ("PUT", "/api/admin/telefon/zugang"): (CONFIRM, "Spark", "Zugang zur Telefonanlage", "Access to the telephone system"),
    ("PUT", "/api/admin/naszustand"): (CONFIRM, "Spark", "Zugang zum Zustand der NAS (SNMP)", "Access to the NAS status (SNMP)"),
    ("POST", "/api/admin/gehaeuse/einrichten"): (CONFIRM, "Spark", "Gehäuse einrichten (config.txt)", "Set up the case (config.txt)"),
    ("POST", "/api/admin/gehaeuse/entfernen"): (CONFIRM, "Spark", "Gehäuse entfernen (config.txt)", "Take out the case (config.txt)"),
    ("POST", "/api/admin/gehaeuse/neustart"): (CONFIRM, "Spark", "Panel-Rechner neu starten", "Restart the panel computer"),
    ("POST", "/api/admin/verbund/pair"): (CONFIRM, "Geräte", "Kopplungs-Code für einen anderen Spark", "Pairing code for another Spark"),
    ("POST", "/api/admin/verbund/connect"): (CONFIRM, "Geräte", "Mit einem anderen Spark koppeln", "Pair with another Spark"),
    ("POST", "/api/profile/esp32/{did}/voice"): (CONFIRM, "Geräte", "Stimme am Lautsprecher anlernen", "Teach my voice at a speaker"),
    ("POST", "/api/profile/push"): (CONFIRM, "Geräte", "Meldungen an diesen Browser", "Notifications to this browser"),
    ("POST", "/api/profile/iphone/pair"): (CONFIRM, "Geräte", "iPhone koppeln", "Pair an iPhone"),
    ("POST", "/api/profile/pebble/pair"): (CONFIRM, "Geräte", "Pebble koppeln", "Pair a Pebble"),
    ("POST", "/api/profile/write/pair"): (CONFIRM, "Geräte", "Schreibhilfe koppeln", "Pair a writing help"),
    ("POST", "/api/profile/desk/pair"): (CONFIRM, "Geräte", "Spark-Begleiter koppeln", "Pair the Spark companion"),
    ("POST", "/api/profile/terminal/pair"): (CONFIRM, "Geräte", "Terminal koppeln", "Pair a terminal"),
    ("POST", "/api/profile/esp32/setup"): (CONFIRM, "Geräte", "Lautsprecher einrichten", "Set up a speaker"),
    ("POST", "/api/profile/esp32/pair"): (CONFIRM, "Geräte", "Lautsprecher koppeln", "Pair a speaker"),
    ("POST", "/api/profile/handoff"): (CONFIRM, "Geräte", "Anmeldung aufs Handy geben", "Hand the login to a phone"),
    # ------------------------------------------------------------------ people and the Spark (confirm)
    ("PUT", "/api/admin/profiles/{uid}"): (CONFIRM, "Personen", "PIN einer Person setzen", "Set a person's PIN"),
    ("DELETE", "/api/admin/profiles/{uid}"): (CONFIRM, "Personen", "Person löschen", "Delete a person"),
    ("POST", "/api/admin/devices"): (CONFIRM, "Personen", "Geräte-Schlüssel anlegen", "Add a device key"),
    ("PUT", "/api/admin/devices/{did}"): (CONFIRM, "Personen", "Geräte-Schlüssel ändern", "Change a device key"),
    ("PUT", "/api/admin/join"): (CONFIRM, "Personen", "Einladungen erlauben", "Allow invitations"),
    ("POST", "/api/admin/join/invites"): (CONFIRM, "Personen", "Person einladen", "Invite a person"),
    ("POST", "/api/admin/pruefzugang"): (CONFIRM, "Personen", "Prüfzugang für die iPhone-App erstellen", "Make a review access for the iPhone app"),
    ("POST", "/api/logout-everywhere"): (CONFIRM, "Personen", "Notzugang überall abmelden", "Sign the emergency access out everywhere"),
    ("PUT", "/api/config"): (CONFIRM, "Spark", "Einstellungen, die Daten nach außen schicken oder Anmeldungen ändern", "Settings that send data elsewhere or change logins"),
    ("POST", "/api/hilfe/karte/{cid}"): (CONFIRM, "Spark", "Spark-Schalter aus einer Hilfe-Karte", "Spark switches from a help card"),
    ("POST", "/api/admin/agent/mcp"): (CONFIRM, "Spark", "Dienst für den Agenten verbinden", "Connect a service for the agent"),
    ("PUT", "/api/admin/agent/mcp/{sid}"): (CONFIRM, "Spark", "Dienst des Agenten ändern", "Change an agent service"),
    ("POST", "/api/admin/agent/mcp/{sid}/refresh"): (CONFIRM, "Spark", "Dienst des Agenten neu laden", "Reload an agent service"),
    ("DELETE", "/api/admin/agent/mcp/{sid}"): (CONFIRM, "Spark", "Dienst des Agenten entfernen", "Remove an agent service"),
    ("DELETE", "/api/admin/mcp/{cid}"): (CONFIRM, "Spark", "Programm (MCP) trennen", "Disconnect a program (MCP)"),
    ("PUT", "/api/admin/mymcp/hosts"): (CONFIRM, "Spark", "Erlaubte Adressen für eigene Dienste", "Allowed addresses for own services"),
    ("PUT", "/api/admin/mymcp/{uid}/{sid}"): (CONFIRM, "Spark", "Eigenen Dienst einer Person sperren", "Block a person's own service"),
    ("DELETE", "/api/admin/mymcp/{uid}/{sid}"): (CONFIRM, "Spark", "Eigenen Dienst einer Person entfernen", "Remove a person's own service"),
    ("PUT", "/api/admin/apns"): (CONFIRM, "Spark", "Push an die iPhone-App einrichten", "Set up push to the iPhone app"),
    ("DELETE", "/api/admin/apns"): (CONFIRM, "Spark", "Push an die iPhone-App entfernen", "Remove push to the iPhone app"),
    ("PUT", "/api/admin/iphone-update/{uid}"): (CONFIRM, "Spark", "Update aus der App für eine Person erlauben", "Allow a person the update from the app"),
    ("PUT", "/api/admin/telegram"): (CONFIRM, "Spark", "Telegram-Bot einrichten", "Set up the Telegram bot"),
    ("DELETE", "/api/admin/telegram"): (CONFIRM, "Spark", "Telegram-Bot entfernen", "Remove the Telegram bot"),
    ("POST", "/api/admin/esp32/fetch"): (CONFIRM, "Spark", "Lautsprecher-Firmware holen", "Fetch speaker firmware"),
    ("POST", "/api/admin/offsite/now"): (CONFIRM, "Daten", "Sicherung jetzt nach außen schicken", "Send a backup offsite now"),
    ("POST", "/api/update/rollback"): (CONFIRM, "Spark", "Zurück zur vorigen Version", "Back to the previous version"),
    ("POST", "/api/admin/modelle/wechseln"): (CONFIRM, "Spark", "Ein Modell wechseln", "Switch a model"),
    ("POST", "/api/admin/modelle/platz"): (CONFIRM, "Spark", "Lange Gespräche einstellen", "Set long conversations"),
    ("POST", "/api/admin/modelle/zurueck"): (CONFIRM, "Spark", "Das vorige Modell zurückholen", "Bring back the previous model"),
    ("POST", "/api/admin/werkstatt/auftrag"): (CONFIRM, "Spark", "Werkstatt: Diagnose, Reparatur oder Code-Messung", "Workshop: diagnosis, repair or code measurement"),
    ("POST", "/api/admin/modelle/messen"): (CONFIRM, "Spark", "Ein Modell messen", "Measure a model"),
    ("POST", "/api/admin/modelle/eigen"): (CONFIRM, "Spark", "Ein eigenes Modell hinzufügen", "Add an own model"),
    ("DELETE", "/api/admin/modelle/eigen/{mid}"): (CONFIRM, "Spark", "Ein eigenes Modell löschen", "Delete an own model"),
}


def entry(request):
    """The list entry of this request (method and route), or None (a request the list does not know)."""
    route = getattr(request, "scope", {}).get("route") if hasattr(request, "scope") else None
    path = getattr(route, "path", None)
    return LIST.get((getattr(request, "method", ""), path)) if path else None


def level(request, fresh):
    """PROTECT or CONFIRM for this request: the list decides; unknown requests keep what the caller says."""
    e = entry(request)
    return e[0] if e else (PROTECT if fresh else CONFIRM)


def header(request, lvl, name):
    """X-Speech-Confirm for the 428 answer: whose code, for what, and whether it counts for a while."""
    e = entry(request)
    d = {"level": lvl, "who": str(name or "")[:60], "what": e[2] if e else "", "what_en": e[3] if e else ""}
    return {"X-Speech-Confirm": base64.urlsafe_b64encode(json.dumps(d, separators=(",", ":")).encode()).rstrip(b"=").decode()}


def overview():
    """For Ich -> Sicherheit -> „Wann fragt der Spark?": the entries by level and area (no routes)."""
    out = {CONFIRM: {}, PROTECT: {}}
    for (_m, _p), (lvl, area, de, en) in LIST.items():
        out[lvl].setdefault(area, []).append({"de": de, "en": en})
    return out
