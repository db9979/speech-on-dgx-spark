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
"""
WESEN = ("mensch", "humanoid", "riese", "tier", "untot", "konstrukt", "drache", "unhold", "elementar", "fee", "himmlisch",
         "pflanze", "schleim", "aberration", "monstrum")


def wesen(g):
    """What a foe is (one of WESEN), "" for an admin's own foe without the field."""
    w = g.get("wesen") if isinstance(g, dict) else None
    return w if w in WESEN else ""


def friedlich(g):
    """A foe that does not want a fight: never drawn as a foe of an encounter."""
    return isinstance(g, dict) and g.get("friedlich") is True


def check_rules(r):
    """„wesen“ and „friedlich“ of the foes by fixed rules: German sentences of what is wrong (dungeon.check_rules adds
    them). Every shipped foe has „wesen“ (test_dungeon_srd); an admin's own foe may leave it out, what stands there is
    one of WESEN."""
    return [f"gegner {x.get('id')}: wesen eines von {', '.join(WESEN)}, friedlich true oder false" for x in r.get("gegner") or []
            if isinstance(x, dict) and ("wesen" in x and x["wesen"] not in WESEN or x.get("friedlich", False) not in (True, False))]
