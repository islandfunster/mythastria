"""THREAT-02 step 1 (GM 2026-10-20: how long to make all the SRD creatures' stat blocks): a basic simulator stat block
for every creature of the SRD 5.2.1 bestiary (DNDSRD521BESTIARY, through bestiary_catalog), in one library file the
region map's battle popup, Import map, Remix and the threat batch read (creature_threat.library()). Plain JSON, apart
from the FG code, so the Mythastria engine can read it too.

  py tools/srd_library.py            # writes sim/creatures/srd_library.json
  py tools/srd_library.py show Wolf  # prints one block

Each block: hit points, AC, speed, size, senses, type, Int, skills (build_test_lab.creature()), its XP and CR, and its
actions. An attack roll with damage is played (attack bonus, reach or range, damage dice and type, a second damage
clause); a Multiattack is played when the simulator's own parser (ai_turn.parse_multiattack) understands it with the
played attacks. Everything else (saving-throw actions, Recharge, Spellcasting, an attack's rider such as Prone, Bonus
Actions, Reactions, Legendary Actions) stays as its SRD text labelled "GM rules this", never dropped: "played" and
"text" list the action names per creature. The creatures that already have a hand-made block in a scenario keep it
("made": "hand"), put right where the official PDF differs (official()), and this file wins over the scenarios. Later
THREAT-02 steps play the text parts.

  py tools/srd_library.py official   # official() alone on the file; the rest is left as it is
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "sim"), str(ROOT / "mythastria_core")]
import build_test_lab  # noqa: E402

LIBRARY = ROOT / "sim" / "creatures" / "srd_library.json"
FORMAT = "srd-library/1"
GM = "GM rules this"
GM_REST = GM + ": the rest: "
SOURCE = build_test_lab.SRD + " Converted by tools/srd_library.py (THREAT-02); hand-made blocks from sim/scenarios."
# build_test_lab.ATTACK, widened: "feet" as well as "ft.", flat damage ("Hit: 1 Piercing damage"), minus modifiers
# ("1d4 - 1") and the odd spacing of "(3d6 +4)"
ATTACK = re.compile(r"(Melee or Ranged|Melee|Ranged) Attack Roll: \+(\d+)[^,]*, (?:reach|range) (\d+)(?:/\d+)? (?:ft\.|feet)"
                    r".*?Hit: (\d+)(?: \((\d+d\d+)(?: ?([+-]) ?(\d+))?\))? (\w+) damage"
                    r"(?: plus \d+ \((\d+d\d+)(?: ?([+-]) ?(\d+))?\) (\w+) damage)?", re.S)
# THREAT-02 step 2 (GM 2026-10-21: "creatures' saving-throw actions and Recharge breath weapons")
ABILITIES = {"Strength": "str", "Dexterity": "dex", "Constitution": "con", "Intelligence": "int", "Wisdom": "wis",
             "Charisma": "cha"}
SAVE = re.compile(r"(Strength|Dexterity|Constitution|Intelligence|Wisdom|Charisma) Saving Throw: DC (\d+)(?:, ([^.]*))?\. ?(.*)", re.S)
# conditions the simulator plays (sim/gm_rules.py); Grappled needs its escape DC
CONDITIONS = ("Blinded", "Frightened", "Incapacitated", "Paralyzed", "Petrified", "Poisoned", "Prone", "Restrained",
              "Stunned", "Unconscious", "Grappled")
SIZES = ("Tiny", "Small", "Medium", "Large", "Huge", "Gargantuan")
DAMAGE = re.compile(r"(\d+) \((\d+d\d+)(?: ?([+-]) ?(\d+))?\) (\w+) damage(?: plus (\d+) \((\d+d\d+)(?: ?([+-]) ?(\d+))?\) (\w+) damage)?")
# SRD-EDITION-01: FG's module goes beyond the official SRD 5.2.1 PDF: these and its lair effects stay out
NOT_IN_SRD = {"Barlgura", "Berserker Commander", "Poltergeist"}
# GM 2026-11-01 ("those are relics from the earliest version"): the official PDF's numbers over the earliest hand-made blocks
HIT_POINTS = {"Earth Elemental": 147, "Animated Flying Sword": 14}
INIT_ADVANTAGE = {"Gray Ooze", "Invisible Stalker"}              # the PDF prints their scores 5 past the bonus: Advantage on Initiative
PARTS = (("bonusactions", "Bonus Action"), ("reactions", "Reaction"), ("legendaryactions", "Legendary Action"),
         ("traits", "Trait"))


def _dice(flat, dice, sign, add):
    if not dice:
        return "0d1+%s" % flat                       # fake_fg's "NdM+K" with no dice: the flat number
    return dice + ("%s%s" % (sign, add) if add else "")


def parse_attack(desc):
    """An attack roll with damage -> {atk, atktype, reach, dmg, dmgtype[, dmg2, dmgtype2], rest}, or None."""
    m = ATTACK.search(desc or "")
    if not m:
        return None
    kind, atk, reach, flat, dice, sign, add, dtype, dice2, sign2, add2, dtype2 = m.groups()
    a = {"atk": int(atk), "atktype": "ranged" if kind == "Ranged" else "melee",
         "reach": int(reach) if kind != "Melee or Ranged" else 5, "dmg": _dice(flat, dice, sign, add), "dmgtype": dtype.lower()}
    if dice2:
        a.update(dmg2=_dice(0, dice2, sign2, add2), dmgtype2=dtype2.lower())
    a["rest"] = desc[m.end():].strip(" .,")
    return a


def _area(who, before):
    """The targets of a save: an area from the creature, a Sphere at a point in range, or one creature; None when the
    wording is not one the simulator plays (a creature's space, Grappled targets, a Cylinder ...)."""
    who = " ".join((who or "").split())
    enemies = {"enemies": True} if who.startswith("each enemy") else {}
    m = re.fullmatch(r"each (?:creature|enemy) in an? (\d+)-foot Cone", who)
    if m:
        return dict({"shape": "cone", "size": int(m.group(1))}, **enemies)
    m = re.fullmatch(r"each (?:creature|enemy) in an? (\d+)-foot-long, (\d+)-foot-wide Line", who)
    if m:
        return dict({"shape": "line", "length": int(m.group(1)), "width": int(m.group(2))}, **enemies)
    m = re.fullmatch(r"each (?:creature|enemy) in an? (\d+)-foot Emanation(?: originating from the [\w ]+)?", who)
    if m:
        return dict({"shape": "emanation", "size": int(m.group(1))}, **enemies)
    m = re.fullmatch(r"each (?:creature|enemy) in an? (\d+)-foot-radius Sphere centered on (?:that point|a point (?:the [\w ]+ "
                     r"can see )?within (\d+) feet)", who)
    if m:
        rng = m.group(2)
        if not rng:
            at = re.search(r"at a point (?:it|the [\w ]+) can see within (\d+) feet", before or "")
            rng = at and at.group(1)
        if rng:
            return dict({"shape": "sphere", "radius": int(m.group(1)), "range": int(rng)}, **enemies)
        return None
    m = re.fullmatch(r"one (?:(\w+) or smaller )?creature (the [\w ]+ can see )?within (\d+) feet( that the [\w ]+ can see)?", who)
    if m and (m.group(1) is None or m.group(1) in SIZES):
        a = {"shape": "one", "range": int(m.group(3))}
        if m.group(1):
            a["max_size"] = m.group(1).lower()
        if m.group(2) or m.group(4):
            a["sees"] = True
        return a
    return None


def _until(text):
    """How long a condition lasts: {"who": "target" or "self", "when": "start" or "end"}, or None."""
    m = re.match(r" until the (start|end) of (its|the [\w ]+?'s) next turn", text)
    if not m:
        return None, text
    return {"who": "target" if m.group(2) == "its" else "self", "when": m.group(1)}, text[m.end():]


REPEAT = re.compile(r"(?: for 1 minute)?\.? ?(?:It|The target|, and it|and)? ?repeats the save at the end of each of its turns, "
                    r"ending the effect on itself on a success\.?$")


def _failure(text):
    """A Failure clause -> (damage, conditions, the sentences not played)."""
    out, conds, rest = {}, [], []
    sentences = re.split(r"(?<=\.)\s+", text.strip())
    i = 0
    while i < len(sentences):
        s = sentences[i].strip()
        i += 1
        d = DAMAGE.match(s)
        if d and not out:
            _, dice, sign, add, dtype, _, dice2, sign2, add2, dtype2 = d.groups()
            out.update(dmg=_dice(0, dice, sign, add), type=dtype.lower())
            if dice2:
                out.update(dmg2=_dice(0, dice2, sign2, add2), type2=dtype2.lower())
            tail = s[d.end():].strip()
            if tail.startswith(", and the target has the"):     # "... damage, and the target has the X condition"
                sentences.insert(i, tail[len(", and "):])
            elif tail.strip(" ."):
                rest.append(tail.strip(" ,."))
            continue
        m = re.match(r"(?:If the target is an? (\w+) or smaller creature, )?(?:The target|it|the target) has the (\w+)"
                     r"(?: and (\w+))? conditions?(?: \(escape DC (\d+)\))?", s)
        names = [n for n in (m.groups()[1:3] if m else ()) if n]
        if m and names and all(n in CONDITIONS for n in names) and (m.group(1) is None or m.group(1) in SIZES):
            if len(names) == 2:                                  # "the Frightened and Incapacitated conditions"
                one = _failure("The target has the %s condition%s" % (names[0], s[m.end():]))
                two = _failure("The target has the %s condition%s" % (names[1], s[m.end():]))
                if one[0].get("conditions") and two[0].get("conditions") and not one[1]:
                    conds += one[0]["conditions"] + two[0]["conditions"]
                else:
                    rest.append(s)
                continue
            name, tail = names[0], s[m.end():]
            m = re.match(r"(?:If the target is an? (\w+) or smaller creature, )?.*? \(escape DC (\d+)\)", s) if name == "Grappled" else m
            c = {"name": name}
            if m.group(1):
                c["max_size"] = m.group(1).lower()
            if name == "Grappled":
                if not m:
                    rest.append(s); continue
                c["escape"] = int(m.group(2))
                tail = s[m.end():]
            until, tail = _until(tail)
            if until:
                c["until"] = until
            o = re.match(r" until the \w+ is destroyed \(AC (\d+); HP (\d+)", tail)
            if o:
                c["object"] = {"ac": int(o.group(1)), "hp": int(o.group(2))}
                tail = ""
            if name not in ("Prone", "Grappled") and not until and not c.get("object"):
                nxt = sentences[i].strip() if i < len(sentences) else ""
                if REPEAT.match(tail):
                    c["repeat"] = "end"; tail = ""
                elif tail.strip() in ("", ".", " for 1 minute.") and REPEAT.match(" " + nxt):
                    c["repeat"] = "end"; tail = ""; i += 1
                else:
                    rest.append(s); continue
            conds.append(c)
            if tail.strip(" ,."):
                rest.append(tail.strip(" ,."))
            continue
        rest.append(s)
    if conds:
        out["conditions"] = conds
    return out, rest


def parse_save(desc, rider=False):
    """A saving-throw action (or an attack's rider) -> (spec, the text the GM still rules), or (None, "")."""
    m = SAVE.search(desc or "")
    if not m:
        return None, ""
    before = desc[:m.start()]
    ability, dc, who, rest = m.groups()
    spec = {"save": ABILITIES[ability], "dc": int(dc)}
    if rider:
        if who:
            return None, ""
        spec["rider"] = True
        cond = re.search(r"If the target is an? (?:non-(\w+) )?creature(?: that isn't an? (\w+)(?: or (\w+))?)?, it is "
                         r"subjected to the following effect\.\s*$", before)
        if not cond or before[:cond.start()].strip():
            return None, ""
        excluded = [x for x in cond.groups() if x]
        if excluded:
            spec["not"] = excluded
    else:
        area = _area(who, before)
        if not area:
            return None, ""
        spec["area"] = area
    f = re.search(r"(?:First )?Failure: (.*?)(?=\s*(?:Success:|Second Failure:|Failure or Success:|$))", rest, re.S)
    if not f:
        return None, ""
    eff, unplayed = _failure(f.group(1))
    if not eff:
        return None, ""
    spec.update(eff)
    succ = re.search(r"(?<!or )Success: (.*?)(?=\s*(?:Failure or Success:|Second Failure:|$))", rest, re.S)
    if "dmg" in spec:
        spec["half"] = bool(succ and succ.group(1).startswith("Half damage"))
        if succ and spec["half"] and succ.group(1).strip(" .") not in ("Half damage", "Half damage only"):
            unplayed.append("Success: " + succ.group(1).strip())
    elif succ:
        unplayed.append("Success: " + succ.group(1).strip())
    for extra in re.findall(r"((?:Second Failure|Failure or Success): .*?)(?=\s*(?:Second Failure:|Failure or Success:|$))", rest, re.S):
        unplayed.append(extra.strip())
    lead = before.strip()
    if lead and not rider and not re.fullmatch(r"The [\w ]+ hurls an? [\w ]+ at a point it can see within \d+ feet\.", lead):
        unplayed.insert(0, lead)
    return spec, " ".join(u.strip() for u in unplayed if u.strip())


def _uses(name):
    """Recharge 5-6 -> {"recharge": 5}; "(2/Day)" -> {"uses": 2}."""
    m = re.search(r"\(Recharge (\d)(?:-6)?\)", name)
    if m:
        return {"recharge": int(m.group(1))}
    m = re.search(r"\((\d+)/Day\)", name)
    return {"uses": int(m.group(1))} if m else {}


def _clean(e):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", build_test_lab.text(e.get("desc", "")))).strip()


def _entries(v):
    return [e for e in v.values() if isinstance(e, dict)] if isinstance(v, dict) else []


def label(c):
    """Mark the actions the engine plays and the ones the GM rules; record both lists on the block."""
    import ai_turn
    played = {a["name"]: a.get("atktype", "") for a in c.get("actions", []) if "atk" in a}
    names = []
    for a in c.get("actions", []):
        if a["name"] == "Multiattack" and ai_turn.parse_multiattack(a.get("desc", ""), played):
            names.append(a["name"])
        elif "atk" in a or "save" in a:            # THREAT-02 step 2: saving-throw actions are played too
            names.append(a["name"])
        else:
            a["gm"] = GM
    c["played"] = names
    c["text"] = [a["name"] for a in c.get("actions", []) if a["name"] not in names]
    return c


def srd_block(name, rec, srd_stats):
    """The basic block converted from the SRD record."""
    c = build_test_lab.creature(name, 1, 0, 0, id="-")
    for k in ("id", "name", "side", "x", "y", "init"):
        c.pop(k, None)
    for a in c["actions"]:
        for k in ("atk", "atktype", "reach", "dmg", "dmgtype", "dmg2", "dmgtype2"):
            a.pop(k, None)
        p = parse_attack(a["desc"]) if a["name"] != "Multiattack" else None
        if p:
            rest = p.pop("rest")
            a.update(p)
            if rest:
                spec, left = parse_save(rest, rider=True)
                if spec:
                    a["save"] = spec
                    rest = left
            if rest:
                a["gm"] = GM_REST + rest
        elif a["name"] != "Multiattack":
            spec, left = parse_save(a["desc"])
            if spec:
                spec.update(_uses(a["name"]))
                a["save"] = spec
                if left:
                    a["gm"] = GM_REST + left
    ab = rec.get("abilities") or {}
    c.update(name=name, made="srd", source="SRD 5.2.1", init=initiative(rec),
             wis_mod=int((ab.get("wisdom") or {}).get("bonus") or 0), xp=srd_stats[name]["xp"], cr=srd_stats[name]["cr"])
    return label(c)


def initiative(rec):
    """The stat block's Initiative score: 10, its Dexterity modifier, and the record's bonus on top."""
    try:
        return 10 + int(((rec.get("abilities") or {}).get("dexterity") or {}).get("bonus") or 0) + int((rec.get("initiative") or {}).get("misc") or 0)
    except (ValueError, AttributeError):
        return 10


def official(lib, recs):
    """GM 2026-11-01: what the official SRD 5.2.1 PDF prints, over what the first versions and FG's module left in the blocks."""
    for name, c in lib.items():
        c["hp"] = HIT_POINTS.get(name, c["hp"])
        if name in recs:
            c["init"] = initiative(recs[name]) + (5 if name in INIT_ADVANTAGE else 0)
    for a in lib["Priest"]["actions"]:
        if a["name"] == "Radiant Flame":
            a.update(atk=5, desc=a["desc"].replace("+4,", "+5,", 1))
    for a in lib["Green Hag"]["actions"]:
        if a["name"] == "Spellcasting":                          # the PDF has these as Coven Magic, a trait kept in gm_text
            a["desc"] = re.split(r"(?:\\n|\n)1/Day:", a["desc"])[0]
    text = json.dumps(lib, ensure_ascii=False).replace("SRD 5.2.1 bestiary (DNDSRD521BESTIARY)", "SRD 5.2.1")
    return json.loads(re.sub(r"\bDM\b", "GM", text).replace("\\\\n", "\\n"))    # FG's literal \n: a line break


def build():
    """{format, source, creatures: {SRD name: block}} for every SRD 5.2.1 creature; hand-made blocks win, then official()."""
    import copy, creature_threat, encounter_tuner
    stats = encounter_tuner.srd_stats()
    hand = creature_threat.hand_made()
    recs = build_test_lab.records()
    out = {}
    for name, rec in sorted(recs.items()):
        if name in NOT_IN_SRD:
            continue
        if name in hand:
            c = copy.deepcopy(hand[name])
            c.update(made="hand")
            label(c)
        else:
            c = srd_block(name, rec, stats)
        c["gm_text"] = srd_text(c, rec)
        out[name] = c
    out = json.loads(json.dumps(out).replace("Melf's Acid Arrow", "Acid Arrow"))      # the PDF's name for the spell
    return {"format": FORMAT, "source": SOURCE, "creatures": official(out, recs)}


def srd_text(c, rec):
    """The parts of the SRD record the block does not play, as text: bonus actions, reactions, legendary actions,
    traits; for a hand-made block also the SRD actions it lacks (FG-EXIT-01 goal 6: a Mage's Spellcasting)."""
    out = [{"part": part, "name": str(e.get("name", "")), "desc": _clean(e), "gm": GM}
           for key, part in PARTS for e in _entries(rec.get(key))]
    if c.get("made") == "hand":
        have = {a.get("name") for a in c.get("actions") or []}
        out = [{"part": "Action", "name": str(e.get("name", "")), "desc": _clean(e), "gm": GM}
               for e in _entries(rec.get("actions")) if str(e.get("name", "")) not in have] + out
    return out


def add_srd_text():
    """Only the hand-made blocks of the library file get srd_text() again (the rest of the file is left as it is)."""
    data = json.loads(LIBRARY.read_text(encoding="utf-8"))
    recs = build_test_lab.records()
    n = 0
    for name, c in data["creatures"].items():
        if c.get("made") == "hand" and name in recs:
            c["gm_text"] = srd_text(c, recs[name])
            n += 1
    write(data)
    return n


def load():
    """The library file's blocks ({} when it is missing)."""
    if not LIBRARY.is_file():
        return {}
    return json.loads(LIBRARY.read_text(encoding="utf-8"))["creatures"]


def write(data=None):
    data = data or build()
    LIBRARY.parent.mkdir(parents=True, exist_ok=True)
    LIBRARY.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return data


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["show"]:
        print(json.dumps(build()["creatures"][" ".join(argv[1:])], indent=1, ensure_ascii=False))
        return 0
    if argv[:1] == ["add-srd-text"]:                          # FG-EXIT-01 goal 6: only the hand-made blocks change
        print("hand-made blocks given their SRD text again: %d" % add_srd_text())
        return 0
    if argv[:1] == ["official"]:                              # GM 2026-11-01: only official() changes the file
        data = json.loads(LIBRARY.read_text(encoding="utf-8"))
        data["creatures"] = official(data["creatures"], build_test_lab.records())
        write(data)
        print("official(): %d creatures" % len(data["creatures"]))
        return 0
    lib = write()["creatures"]
    every = sum(1 for c in lib.values() if not c["text"])
    none = sorted(n for n, c in lib.items() if not c["played"])
    print("wrote %s: %d creatures (%d hand-made); every action played: %d; some as GM text: %d; none played: %d (%s)" % (
        LIBRARY.relative_to(ROOT).as_posix(), len(lib), sum(1 for c in lib.values() if c["made"] == "hand"), every,
        len(lib) - every - len(none), len(none), ", ".join(none)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
