"""KI-Dungeon-Master: Heldenmut (Idee 8 of 2026-10-24, Dominik „alle umsetzen“).

Once a game evening each hero may call on Heldenmut with an action: a failed check is rolled again once, an attack
that hits becomes a critical hit, one that misses is rolled again once. A second charge of the evening comes from the
table: when at least half of the other players give 👍 to one of the hero's actions (LOB_MAX an evening). The panel
counts the charges by fixed rules, the model never gives or takes one.

The charges live in the round (rd["mut"][pid] = {"abend", "genutzt", "lob"}), the 👍 in rd["mut_lob"][zug][pid].
Only while „Heldenmut“ is allowed for the round's host (features "dungeonheldenmut").
"""
import time

LOB_MAX = 1               # charges the table can give a hero per evening, on top of the hero's own one
LOB_ZUEGE = 3             # an action can get 👍 while it is one of the last three turns
clock = time.time


def on(rd):
    import features
    return bool(rd.get("owner")) and features.allowed("dungeonheldenmut", rd["owner"])


def evening():
    return time.strftime("%Y-%m-%d", time.localtime(clock()))


def _mine(rd, pid):
    m = rd.setdefault("mut", {}).get(pid)
    if not m or m.get("abend") != evening():
        m = rd["mut"][pid] = {"abend": evening(), "genutzt": 0, "lob": 0}
    return m


def left(rd, pid):
    """The charges of a seat still free this evening."""
    m = (rd.get("mut") or {}).get(pid)
    if not m or m.get("abend") != evening():
        return 1
    return max(0, 1 + m["lob"] - m["genutzt"])


def ask(rd, pid, want):
    """An action asks for Heldenmut (want is True): marked on the open action while a charge is free; spent only when
    a roll uses it (use)."""
    if want is not True:
        return
    if not on(rd) or not left(rd, pid):
        print("dungeon: heldenmut | keiner frei", flush=True)
        return
    rd["offen"][pid]["mut"] = True
    print("dungeon: heldenmut | bereit", flush=True)


def wants(rd, pid):
    """The open action of the seat calls on Heldenmut and no roll of this turn has used it yet."""
    a = rd["offen"].get(pid) or {}
    return a.get("mut") is True and not a.get("mut_weg") and on(rd) and left(rd, pid) > 0


def spend(rd, pid):
    """A roll of this turn used it (on run_turn's copy): no second roll of the same action uses it."""
    rd["offen"][pid]["mut_weg"] = True


def use(rd, pid):
    """apply: a roll used Heldenmut, the charge is gone."""
    _mine(rd, pid)["genutzt"] += 1
    print("dungeon: heldenmut | genutzt", flush=True)


def need(rd, pid, heroes):
    """How many 👍 of the others give a hero the table's charge: half of the other players, rounded up; 0 alone."""
    others = sum(1 for p in heroes if p != pid)
    return (others + 1) // 2


def praise(rd, voter, zug, pid, heroes):
    """A 👍 of seat voter for the action of seat pid in turn zug. Returns True when it gave pid the table's charge."""
    if not isinstance(zug, int) or isinstance(zug, bool) or not isinstance(pid, str):
        raise ValueError("daumen")
    if not on(rd):
        print("dungeon: heldenmut | aus", flush=True)
        raise PermissionError("heldenmut")
    if pid == voter or pid not in heroes or voter not in heroes:
        print("dungeon: heldenmut | lob nein", flush=True)
        raise ValueError("daumen")
    if not rd["zug"] - LOB_ZUEGE <= zug < rd["zug"] or not any(
            e["art"] == "aktion" and e.get("n") == zug and e.get("pid") == pid for e in rd["log"]):
        print("dungeon: heldenmut | lob alt", flush=True)
        raise LookupError("aktion")
    lob = rd.setdefault("mut_lob", {})
    for k in [k for k in lob if int(k) < rd["zug"] - LOB_ZUEGE]:
        lob.pop(k)
    votes = lob.setdefault(str(zug), {}).setdefault(pid, [])
    if voter not in votes:
        votes.append(voter)
    m = _mine(rd, pid)
    if len(votes) < need(rd, pid, heroes) or m["lob"] >= LOB_MAX:
        print(f"dungeon: heldenmut | lob | {len(votes)} von {need(rd, pid, heroes)}", flush=True)
        return False
    m["lob"] += 1
    print("dungeon: heldenmut | geschenkt", flush=True)
    return True


def given(rd, voter):
    """The 👍 a seat gave for actions, as "zug:pid"."""
    return sorted(f"{z}:{p}" for z, x in (rd.get("mut_lob") or {}).items() for p, v in x.items() if voter in v)


def view(rd, pid):
    """The own seat's Heldenmut for the table: free charges and the 👍 given; None while off."""
    if not on(rd):
        return None
    m = (rd.get("mut") or {}).get(pid) or {}
    return {"frei": left(rd, pid), "lob": given(rd, pid), "geschenkt": m.get("lob", 0) if m.get("abend") == evening() else 0}


def for_live(rs):
    """Numbers only: charges used this evening over all rounds."""
    ev = evening()
    return {"heldenmut": sum(m.get("genutzt", 0) for rd in rs for m in (rd.get("mut") or {}).values() if m.get("abend") == ev)}
