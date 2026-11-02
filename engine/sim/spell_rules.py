"""REFEREE-01 (GM 2026-10-22): the spell rules every part of Mythastria reads: the SRD 5.2.1 rule sheet
(sim/spells/srd_spells.json, tools/srd_spells.py) with the GM's own clarifications laid over it (GM: "allow ambiguous
descriptions to be modified for clarity for that DM"), and what the engine plays of each spell (the coverage list).

Clarifications (sim/spells/clarifications.json, kept on the GM's PC, never committed or shared: a table's rulings are
its own, like homebrew, and never train the prep engine): per spell, the GM's wording and, when the GM wants it, the
reading the engine and the referee use instead of the parsed one (for example "targets": {"choice": true}). The SRD text
is always kept beside it, and a clarified spell is marked as such wherever it is shown.
"""
import datetime, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHEET = ROOT / "sim" / "spells" / "srd_spells.json"
CLARIFY = ROOT / "sim" / "spells" / "clarifications.json"
EDITABLE = ("casting_time", "range", "area", "targets", "attack", "save", "damage", "healing", "conditions", "duration",
            "lasts", "later")
_SHEET = None


class SpellRuleError(ValueError):
    pass


def sheet():
    """{name: the SRD rule sheet} (read once)."""
    global _SHEET
    if _SHEET is None:
        _SHEET = {s["name"]: s for s in json.loads(SHEET.read_text(encoding="utf-8"))["spells"]}
    return _SHEET


def clarifications(path=None):
    p = Path(path or CLARIFY)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    return data.get("spells", {}) if isinstance(data, dict) else {}


# SPELLS-4-9 (GM 2026-10-26, goal 3: spell levels 4 to 9): what a spell's own words say that the sheet's reading of its
# first paragraph misses, read here once so the engine and the referee share it (the GM's clarification still goes over
# it). Each entry quotes the words it reads. A key ending in "+" adds to the sheet's own reading of that field.
READINGS = {
    # "Three bolts then leap from that target to as many as three other targets of your choice, each of which must be
    # within 30 feet of the first target." / "One additional bolt leaps ... for each spell slot level above 6."
    "Chain Lightning": {"targets": {"choice": True, "max": 4, "kind": "creatures"}, "near": {"ft": 30, "leap": True},
                        "scaling+": {"extra_targets_per_level": 1, "above": 6}},
    # "You launch a green ray at a target you can see within range." (the 10-foot Cube is a Huge object's portion)
    "Disintegrate": {"area": None, "targets": {"choice": False, "max": 1, "kind": "creature"}},
    # "Your touch inflicts a magical contagion. The target must succeed on a Constitution saving throw ..."
    "Contagion": {"targets": {"choice": False, "max": 1, "kind": "creature"}},
    # "You restore up to 700 Hit Points, divided as you choose among any number of creatures that you can see"
    "Mass Heal": {"targets": {"choice": True, "max": None, "kind": "creatures"}},
    # "Choose up to six creatures in a 30-foot-radius Sphere centered on that point."
    "Mass Cure Wounds": {"targets": {"choice": True, "max": 6, "kind": "area"}},
    # "Each creature of your choice in range makes a Charisma saving throw."
    "Divine Word": {"targets": {"choice": True, "max": None, "kind": "creatures"}},
    # "One creature of your choice within 60 feet of you that you can see" (its range is Self)
    "Eyebite": {"range": {"kind": "ranged", "ft": 60}},
    # "You can make the wall up to 60 feet long, 20 feet high, and 1 foot thick" (the straight wall; the ring is the
    # GM's) / "When the wall appears, each creature in its area makes a Dexterity saving throw"
    "Wall of Fire": {"area": {"shape": "line", "size_ft": 60, "width_ft": 1, "origin": "point", "wall": True},
                     "targets": {"choice": False, "max": None, "kind": "area"}},
    # "For each target, roll 1d8 ... 8 Special. The target is struck by two rays." (two rays' damage at most)
    "Prismatic Spray": {"count": {"n": 2, "word": "ray", "per_target": True}},
    # "Blazing orbs of fire plummet to the ground at four different points ... A creature in the area of more than one
    # fiery Sphere is affected only once."
    "Meteor Swarm": {"area+": {"points": 4}},
    # SPELLS-4-6-FIGHT (GM 2026-10-28): "Squirming, ebony tentacles fill a 20-foot square"
    "Black Tentacles": {"area": {"shape": "cube", "size_ft": 20, "origin": "point"},
                        "targets": {"choice": False, "max": None, "kind": "area"}},
    # "Any enemy that moves to a space within 10 feet of the guardian" (the guardian on a point in range)
    "Guardian of Faith": {"area": {"shape": "sphere", "size_ft": 10, "origin": "point"},
                          "targets": {"choice": False, "max": None, "kind": "area"}},
    # "a straight wall up to 100 feet long ... and 5 feet thick" / "up to 60 feet long ... and 5 feet thick" (the ring
    # is the GM's); "wall": a shape the referee doesn't place, so it judges their saves but not who stood in them
    "Blade Barrier": {"area": {"shape": "wall", "size_ft": 100, "width_ft": 5, "origin": "point", "wall": True},
                      "targets": {"choice": False, "max": None, "kind": "area"}},
    "Wall of Thorns": {"area": {"shape": "wall", "size_ft": 60, "width_ft": 5, "origin": "point", "wall": True},
                       "targets": {"choice": False, "max": None, "kind": "area"}},
    # "twelve or fewer creatures you can see within range"
    "Mass Suggestion": {"targets": {"choice": True, "max": 12, "kind": "creatures"}},
}


def _read(name, base):
    r = READINGS.get(name)
    if not r:
        return base
    out = dict(base)
    for k, v in r.items():
        if k.endswith("+"):
            out[k[:-1]] = dict(out.get(k[:-1]) or {}, **v)
        else:
            out[k] = v
    if "targets" in r:
        out["unread"] = [u for u in out.get("unread") or [] if u != "targets"]
    return out


def together(rules):
    """Are the spell's damage parts dealt together ("5d6 Fire damage and 5d6 Radiant damage": Flame Strike, Ice Storm,
    Meteor Swarm), not one or the other ("3d8 Radiant damage ... or 3d8 Necrotic": Spirit Guardians)?"""
    return len((rules or {}).get("damage") or []) > 1 and bool(re.search(
        r"\d+d\d+(?: \+ \d+)? \w+ damage and \d+d\d+ \w+ damage(?! at the end)", (rules or {}).get("text") or ""))


def scaled_parts(rules):
    """The damage parts a higher slot adds its dice to: the ones its words name ("The Bludgeoning damage increases",
    "The Fire damage and the Radiant damage increase"), all of them for "both", else the first."""
    dmg, text = rules.get("damage") or [], ((rules.get("scaling") or {}).get("text") or "")
    if not dmg:
        return []
    if re.search(r"\bboth\b", text, re.I):                     # "Both types of damage", "(both initial and later)"
        return list(range(len(dmg)))
    named = [k for k, d in enumerate(dmg) if re.search(r"\b%s damage\b" % d["type"], text, re.I)]
    return named or [0]


def area_at(rules, slot_level=None):
    """The spell's area as cast with a slot: "The Sphere's radius increases by 5 feet for each spell slot level above
    4" (Confusion)."""
    area = rules.get("area")
    m = re.search(r"radius increases by (\d+) feet for each (?:spell )?slot level above (\d)",
                  (rules.get("scaling") or {}).get("text") or "")
    if not area or not m or not slot_level:
        return area
    return dict(area, size_ft=area["size_ft"] + int(m.group(1)) * max(0, slot_level - int(m.group(2))))


def spell(name, path=None):
    """The rules the engine and the referee use for a spell: the SRD sheet (with READINGS), the GM's clarification
    over it."""
    base = sheet().get(name)
    if base is None:
        return None
    base = _read(name, base)
    c = clarifications(path).get(name)
    if not c:
        return dict(base, clarified=False)
    out = dict(base, clarified=True, srd_text=base["text"], text=c.get("text") or base["text"], clarification=c)
    for k, v in (c.get("fields") or {}).items():
        if k in EDITABLE:
            out[k] = v
    return out


# ------------------------------------------------------------------ a lasting area's later saves
# REFEREE-02 (GM 2026-10-26, goal 8): when a spell's area asks for its save again after the cast, read from the spell's
# own words (or the GM's): "whenever the Emanation enters a creature's space and whenever a creature enters the
# Emanation or ends its turn there" (Spirit Guardians); "Each creature that starts its turn in the Sphere" (Stinking
# Cloud). moved: the area moves into a creature's space; enter: a creature enters it; start / end: of the creature's
# turn there; your_start / your_end: of the caster's turn (Earthquake).
_ABILITY = {"Strength": "str", "Dexterity": "dex", "Constitution": "con", "Intelligence": "int", "Wisdom": "wis",
            "Charisma": "cha"}
_LATER_WHEN = (
    ("moved", r"\b(?:area|Emanation|Sphere|Cylinder|pack) (?:moves into|enters|moves within \d+ feet of a creature)"
              r"|space the wall enters|move the sphere into a creature's space"),
    ("enter", r"\b(?:creature|it|enemy)(?: you can see| that| who| also)* (?:enters?|moves to a space within|moving through)\b"
              r"|\bmoves within \d+ feet of it\b"),
    ("start", r"\bstarts? (?:its|their) turn"),
    ("end", r"\bends? (?:its|it|their) turn"),
    ("your_start", r"\bstart of each of your (?:later )?turns"),
    ("your_end", r"\bend of each of your (?:later )?turns"))


def later(rules):
    """The later saves of a lasting area, or None: {"when": [...], "once": a creature saves only once per turn,
    "first": entering asks only the first time on a turn, "who": "all" / "other" (not the caster) / "enemy" /
    "designate" (all but those the caster spared when casting: the engine spares the caster's side) / "choice" (each
    time the caster may force it or not), "ability", "dice" (when the later damage is its own: Wall of Ice's 5d6
    Cold), "half", "text": the words read}. The GM's wording (a clarification's "later" field) wins."""
    if not rules or rules["duration"].get("instant"):
        return None
    if rules.get("later") is not None:
        return rules["later"] or None
    text = rules.get("text") or ""
    when, said = [], []
    for s in re.split(r"(?<=[.!?])\s+", text):
        if not re.search(r"\bsav(?:e|ing)\b|affected|targeted|bathe", s) or re.search(
                r"line of sight|more than \d+ feet away|takes the same damage", s):
            continue
        found = [w for w, pat in _LATER_WHEN if re.search(pat, s)]
        if found:
            when += [w for w in found if w not in when]
            said.append(s)
    if not when:
        return None
    words = " ".join(said)
    ab = re.search(r"(Strength|Dexterity|Constitution|Intelligence|Wisdom|Charisma) saving throw", words)
    dice = re.search(r"\btak(?:e|ing) (\d+d\d+) \w+ damage", words)
    half = "half as much" in words if dice else bool((rules.get("save") or {}).get("half"))
    who = ("enemy" if re.search(r"\benemy\b", words) else
           "designate" if re.search(r"designate creatures to be unaffected", text) else
           "choice" if re.search(r"you can force|you can bathe|of your choice", text)
           else "other" if re.search(r"\bAny other creature|other than you", text) else "all")
    return {"when": when, "once": bool(re.search(r"only once per turn", text)),
            "first": bool(re.search(r"first time", words)), "who": who,
            "ability": _ABILITY[ab.group(1)] if ab else (rules.get("save") or {}).get("ability"),
            "dice": dice.group(1) if dice else None, "half": half, "text": words}


def clarify(name, text=None, fields=None, note="", path=None, clear=False):
    """Save (or clear) the GM's clarification of a spell. Only the readable fields may be changed; the SRD text stays."""
    if name not in sheet():
        raise SpellRuleError("No SRD 5.2.1 spell named %r." % name)
    fields = fields or {}
    bad = [k for k in fields if k not in EDITABLE]
    if bad:
        raise SpellRuleError("These can't be changed: %s (only %s)." % (", ".join(bad), ", ".join(EDITABLE)))
    if text is not None and (not isinstance(text, str) or len(text) > 6000):
        raise SpellRuleError("The wording is text, up to 6000 characters.")
    p = Path(path or CLARIFY)
    data = {"format": "spell-clarifications/1", "note": "The GM's own rulings: kept on this PC, never shared or committed.",
            "spells": clarifications(p)}
    if clear:
        data["spells"].pop(name, None)
    else:
        data["spells"][name] = {"text": (text or "").strip() or None, "fields": fields, "note": note.strip()[:500],
                                "when": datetime.date.today().isoformat()}
    p.parent.mkdir(parents=True, exist_ok=True)
    ignore = p.parent / ".gitignore"
    if not ignore.exists():
        ignore.write_text("clarifications.json\n", encoding="utf-8")
    p.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    return spell(name, p)


# ------------------------------------------------------------------ coverage: what the engine plays of each spell
def _engine_names():
    import live_spells, live_general, map_layers, invisibility, more_spells
    src ="".join((ROOT / "sim" / f).read_text(encoding="utf-8") for f in ("party.py", "gm_rules.py", "live_spells.py", "live_actions.py"))
    simulated = {n for n in sheet() if re.search(r'["\' ]%s["\' ,:)]' % re.escape(n), src)}
    return (set(live_spells.SPELLS) | set(live_general.castable()) | set(map_layers.ZONE_SPELLS) | {invisibility.SPELL}
            | more_spells.names()), simulated                       # SPELL-CASTER-01; SPELL-EFFECTS-01: and the rest


def coverage(path=None):
    """[{name, level, live, simulated, status, unread, clarified}]: live = a player can cast it in Play live; simulated =
    the simulator plays it (the scripted party or a creature); status: "played in Play live", "simulator only",
    "not yet (the GM rules it)"."""
    live, simulated = _engine_names()
    clar = clarifications(path)
    out = []
    for name, s in sorted(sheet().items(), key=lambda kv: (kv[1]["level"], kv[0])):
        status = ("played in Play live" if name in live else "simulator only" if name in simulated
                  else "not yet (the GM rules it)")
        out.append({"name": name, "level": s["level"], "live": name in live, "simulated": name in simulated or name in live,
                    "status": status, "unread": s["unread"], "clarified": name in clar})
    return out
