"""GM 2026-10-25 (the optional Social interaction rules pack, sim/rules_packs/social.json; its text in
social_interaction_rules.md): "I really was looking for creature dispositions when encountered. A social creature is
loosely defined as INT 4+"; "Those determinations can signify if a creature is neutral or hostile according to
intelligence and faction".

A creature's disposition when the party meets it, only when the GM switches the pack on for a campaign (the SRD's own
rule stays the default: "Indifferent is the default attitude of a monster"):
1. its faction: written on the creature in the map or adventure ("faction": "broken-ring"), else a faction the pack
   lists it in (the Broken Ring's Bandits, Bandit Captains and Thugs; the Keepers of the Pale Flame's Cultists and Cult
   Fanatics; the Obsidian Scribes' Mages and Acolytes): the faction's attitude;
2. a social creature (Intelligence 4 or higher): its creature type's attitude in the pack's table;
3. a creature of Intelligence 3 or lower goes by instinct: a predator (it bites, claws, stings, constricts or engulfs)
   is Hostile, any other Indifferent; mindless Constructs, Oozes, Plants and Undead keep their type's attitude.
Each answer names the pack item it comes from (an anchor on the pack's page, rules-social.html), so the GM's screen can
link to it.
"""
import json
import re
from pathlib import Path

PACK_FILE = Path(__file__).resolve().parent / "rules_packs" / "social.json"
PREDATOR = re.compile(r"\b(bites?|claws?|talons?|tentacles?|stings?|constricts?|engulfs?|pseudopods?|swallows?|gores?|tusks?|rends?)\b", re.I)
_pack = None


def pack():
    global _pack
    if _pack is None:
        _pack = json.loads(PACK_FILE.read_text(encoding="utf-8"))
    return _pack


def on(optional):
    """True when a campaign's optional rules switch this pack on ({"social": true})."""
    return bool((optional or {}).get("social"))


def creature_type(c):
    """The pack's type key for a creature ("Small Fey (Goblinoid)" -> fey), with the pack's fallbacks."""
    p = pack()
    raw = str(c.get("type") or "").strip()
    name = c.get("srd_name") or re.sub(r"\s+\d+$", "", str(c.get("name") or "")).strip()
    for word in re.findall(r"[A-Za-z]+", raw.split("(")[0].lower()):
        if word in p["types"]:
            return word
    fb = p.get("type_fallback") or {}
    if name in fb:
        return fb[name].get("type")
    if raw.lower().startswith("swarm"):
        return (fb.get("Swarm") or {}).get("type")
    return None


def intelligence(c):
    i = c.get("int", (c.get("abilities") or {}).get("int"))
    if i is None:                                            # the pack's fallback (a library entry without it)
        name = c.get("srd_name") or re.sub(r"\s+\d+$", "", str(c.get("name") or "")).strip()
        i = ((pack().get("type_fallback") or {}).get(name) or {}).get("int")
    try:
        return int(i)
    except (TypeError, ValueError):
        return None


def faction_of(c):
    """(faction key, how) or (None, None): written on the creature first, then the pack's member lists."""
    p = pack()
    written = c.get("faction")
    if written in p["factions"]:
        return written, "written on it"
    name = c.get("srd_name") or re.sub(r"\s+\d+$", "", str(c.get("name") or "")).strip()
    for key, f in p["factions"].items():
        if name in f.get("members") or ():
            return key, "the pack's member list"
    return None, None


def disposition(c):
    """{attitude, why, item, social, type, int} for one creature, by the pack's three steps (module docstring)."""
    p = pack()
    t, i = creature_type(c), intelligence(c)
    social = i is not None and i >= p["social_int"]
    key, how = faction_of(c)
    if key:
        f = p["factions"][key]
        return {"attitude": f["attitude"], "why": "%s (%s)" % (f["name"], how), "item": "faction-" + key,
                "social": social, "type": t, "int": i}
    if social and t:
        row = p["types"][t]
        return {"attitude": row["attitude"], "why": "a social %s (Intelligence %d)" % (t.title(), i),
                "item": "type-" + t, "social": True, "type": t, "int": i}
    if i is not None and not social and t in (p.get("mindless_types") or ()):
        row = p["types"][t]
        return {"attitude": row["attitude"], "why": "a mindless %s (Intelligence %d)" % (t.title(), i),
                "item": "type-" + t, "social": False, "type": t, "int": i}
    if i is not None and not social:
        predator = any(PREDATOR.search(str(a.get("name") or "")) for a in c.get("actions") or [])
        a = p["instinct"]["predator" if predator else "other"]
        return {"attitude": a, "why": "instinct (Intelligence %d%s)" % (i, ", a predator" if predator else ""),
                "item": "instinct", "social": False, "type": t, "int": i}
    return {"attitude": "Indifferent", "why": "nothing to go on: the SRD's default", "item": "types",
            "social": social, "type": t, "int": i}


def influence_refusal(c, mode):
    """With the pack on, why an Influence urge can't work on this creature, or None. Not a social creature
    (Intelligence 3 or lower): only Wisdom (Animal Handling), and only on a Beast or Monstrosity. A type the pack
    marks immune (Constructs, Oozes, Plants): no urge works."""
    d = disposition(c)
    row = pack()["types"].get(d["type"] or "") or {}
    name = c.get("name") or "It"
    if row.get("immune"):
        return "%s is a %s: no urge works on it (Social rules pack)." % (name, d["type"].title())
    if not d["social"] and d["int"] is not None and mode != "animal_handling":
        return ("%s is not a social creature (Intelligence %d): it can't be talked into anything; a Beast or Monstrosity "
                "can be coaxed with Animal Handling (Social rules pack)." % (name, d["int"]))
    return None


def library_rows(library_path=None):
    """Every SRD creature with its disposition, for the pack's page (GET /api/rules/social)."""
    path = library_path or Path(__file__).resolve().parent / "creatures" / "srd_library.json"
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    cs = raw.get("creatures") if isinstance(raw, dict) else raw
    cs = cs if isinstance(cs, list) else list(cs.values())
    out = []
    for c in sorted(cs, key=lambda x: x.get("name") or ""):
        d = disposition(c)
        out.append({"name": c.get("name"), "cr": c.get("cr"), **d})
    return out


def anchor(name):
    """The page anchor of one creature's row ("Bandit Captain" -> c-bandit-captain)."""
    return "c-" + re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")
