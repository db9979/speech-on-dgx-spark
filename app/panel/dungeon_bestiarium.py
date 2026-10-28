"""KI-Dungeon-Master: what a foe of the Bestiarium is (Dungeon-Prüfbericht 2026-10-27 Z11, Dominik „ok“): the field
„wesen“ of every foe in dungeon_srd.json (thread „DnDAppFiles für den Dungeon-Master“) instead of id lists by hand, one
source for the picture (dungeon_dingbild), the people rules and the rules page.

WESEN in a few words: mensch = an ordinary human person; humanoid = another folk of human shape (elf, dwarf, goblin,
orc, lizard folk, merfolk, a lycanthrope); riese = giants, ogres, trolls; tier = an animal, also a giant or
prehistoric one; untot = the walking and the bodiless dead; konstrukt = anything built (golem, animated object, robot,
drone, AI); drache; unhold = devils and demons; elementar = a being of fire, water, earth, air or storm; fee = fey and
hags; himmlisch = heavenly beings; pflanze; schleim = oozes; aberration = alien and mind-bending beings; monstrum =
every other creature of the myths. The panel reads the field, never the model.

„friedlich“: true (review T24a) marks people and beasts that do not want a fight (the commoner, the unicorn): the
encounter offer never draws them as foes.

„ep_kampf“ (review B4 option a, Paket 11.6): the experience a foe is worth in a fight as the main thread's bench measured
it (ep / x80, the ratio with 80 % wins for a group of four, at most a quarter to four times ep); „ep“ stays for the
display and the D&D reference. A foe the bench could not measure has none and counts with its ep.
"""
WESEN = ("mensch", "humanoid", "riese", "tier", "untot", "konstrukt", "drache", "unhold", "elementar", "fee", "himmlisch",
         "pflanze", "schleim", "aberration", "monstrum")

EP_KAMPF = (0.25, 4)       # ep_kampf lies between these times ep


def wesen(g):
    """What a foe is (one of WESEN), "" for an admin's own foe without the field."""
    w = g.get("wesen") if isinstance(g, dict) else None
    return w if w in WESEN else ""


def friedlich(g):
    """A foe that does not want a fight: never drawn as a foe of an encounter."""
    return isinstance(g, dict) and g.get("friedlich") is True


def ep_kampf(g):
    """The experience a foe is worth in a fight: the measured ep_kampf, else its ep."""
    return int(g.get("ep_kampf") or g.get("ep") or 0)


def _ep_ok(x):
    if "ep_kampf" not in x:
        return True
    v, ep = x["ep_kampf"], x.get("ep")
    return isinstance(v, int) and not isinstance(v, bool) and isinstance(ep, int) and ep > 0 \
        and EP_KAMPF[0] * ep - 1 <= v <= EP_KAMPF[1] * ep + 1


def check_rules(r):
    """„wesen“, „friedlich“ and „ep_kampf“ of the foes by fixed rules: German sentences of what is wrong
    (dungeon.check_rules adds them). Every shipped foe has „wesen“ (test_dungeon_srd); an admin's own foe may leave it
    out, what stands there is one of WESEN."""
    return [f"gegner {x.get('id')}: wesen eines von {', '.join(WESEN)}, friedlich true oder false, ep_kampf eine ganze Zahl "
            f"vom {EP_KAMPF[0]:g}- bis {EP_KAMPF[1]:g}-Fachen von ep" for x in r.get("gegner") or []
            if isinstance(x, dict) and ("wesen" in x and x["wesen"] not in WESEN or x.get("friedlich", False) not in (True, False)
                                        or not _ep_ok(x))]
