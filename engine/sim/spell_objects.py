"""SPELL-OBJECTS-01 (GM 2026-10-27: "Some spells only target creatures, some objects also"; asked, chose "Mark spells
now": every SRD spell marked from its own text, the checks and messages saying so; casting at doors and other objects
comes next).

Each of the 339 SRD 5.2.1 spells (sim/spells/srd_spells.json) is one of:
- "no": it never targets an object (a creature, yourself, or an area of creatures);
- "also": a creature or an object ("a creature or an object within range": Fire Bolt), or an area whose own text has
  objects in it affected too ("A nonmagical object that isn't being worn or carried also takes the damage": Shatter);
- "only": an object, not a creature ("Choose an object that you can see within range": Knock; a weapon, a rope, a
  corpse).
Read by hand from each spell's text on 2026-10-27 (every spell naming an object, a weapon, a corpse, bones, a rope,
food, water or a door in its first sentences); every other spell is "no". tools/srd_spells.py writes the mark into each
spell's "targets" as "objects"; `py sim/spell_objects.py` marks the file in place.
"""
import json, sys
from pathlib import Path

ALSO = {"Eldritch Blast", "Fire Bolt", "Produce Flame", "Sorcerous Burst", "Starry Wisp", "Arcanist's Magic Aura",
        "Enlarge/Reduce", "Levitate", "Dispel Magic", "Nondetection", "Remove Curse", "Resilient Sphere", "Telekinesis",
        "Chain Lightning", "Disintegrate", "Sequester", "Teleport", "Antipathy/Sympathy", "True Polymorph",
        "Darkness", "Daylight",                                   # a point, or an object the light or dark comes from
        # areas whose text affects objects in them too
        "Elementalism", "Burning Hands", "Faerie Fire", "Thunderwave", "Flaming Sphere", "Shatter", "Silence", "Fireball",
        "Delayed Blast Fireball", "Fire Storm", "Reverse Gravity", "Meteor Swarm", "Storm of Vengeance"}
ONLY = {"Light", "Mending", "Prestidigitation", "Identify", "Arcane Lock", "Continual Flame", "Heat Metal", "Knock",
        "Locate Object", "Magic Mouth", "Glyph of Warding", "Fabricate", "Stone Shape", "Animate Objects", "Instant Summons",
        "Symbol", "Shillelagh", "Magic Weapon", "Rope Trick", "Gentle Repose", "Animate Dead", "Speak with Dead", "Alarm",
        "Purify Food and Drink", "Create or Destroy Water"}
WORDS = {"no": "a creature", "also": "a creature or an object", "only": "an object, not a creature"}
FILE = Path(__file__).resolve().parent / "spells" / "srd_spells.json"


def objects(name):
    """"only", "also" or "no" for an SRD spell's name."""
    return "only" if name in ONLY else "also" if name in ALSO else "no"


def mark(path=FILE):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    names = {s["name"] for s in data["spells"]}
    missing = sorted((ALSO | ONLY) - names)
    if missing:
        raise SystemExit("Not in the spell file: %s" % ", ".join(missing))
    for s in data["spells"]:
        s["targets"]["objects"] = objects(s["name"])
    Path(path).write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    return {k: sum(1 for s in data["spells"] if s["targets"]["objects"] == k) for k in WORDS}


if __name__ == "__main__":
    print(mark(sys.argv[1] if len(sys.argv) > 1 else FILE))
