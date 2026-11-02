"""REMIX-01 R1 (2026-10-20): the encounter description Remix works from, and its checker (docs/development/REMIX.md).

  py tools/remix_spec.py FILE.encounters.json [--map MAP_SCRIPT.py]

A description says what each encounter of a map *does* (its locked story job, its creatures and their roles, how hard
the simulator measured it, the terrain, what a remix may change) and the non-combat routes through it. check() returns
a list of problems in plain words (empty: fine). With the map's SPEC it also checks that the room and the creatures are
the ones the map really has. Plain data and plain functions: portable to the Rust engine.
"""
import argparse, importlib.util, json, sys
from pathlib import Path

FORMAT = "remix-encounters/1"
PLAYS_AS = ("below low", "low", "moderate", "high", "above high")
BANDS = ("below Low", "Low", "Moderate", "High", "above High")             # 2024 XP budget bands
APPROACHES = ("parley", "bargain", "deceive", "intimidate", "perform", "distract", "scare off", "sneak past", "avoid",
              "lore", "help")
TALK = ("parley", "bargain", "deceive", "intimidate", "perform")           # need a creature that understands
TONES = ("family", "spooky", "dark", "mature")
SIZES = ("Tiny", "Small", "Medium", "Large", "Huge", "Gargantuan")
# GM 2026-10-23 (DECISIONS: MOUNTS ARE DOMESTIC ANIMALS): the SRD 5.2.1 mounts (Equipment, "Mounts and Other Animals")
# are ordinary animals, never offered as foes; a mounted foe comes from an adventure's story. An encounter that already
# has one keeps it, and simulated fights may still use them.
SRD_MOUNTS = frozenset(("Camel", "Elephant", "Draft Horse", "Riding Horse", "Mastiff", "Mule", "Pony", "Warhorse"))
ABILITIES = ("Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Charisma")
TALK_INT = 6                                                                # an Intelligence that can follow speech
DC_RANGE = (5, 30)                                                          # SRD 5.2.1 Typical Difficulty Classes


def check(desc, map_spec=None):
    out = []
    if desc.get("format") != FORMAT:
        out.append("format: must be %r" % FORMAT)
    encs = desc.get("encounters")
    if not isinstance(encs, list) or not encs:
        out.append("encounters: at least one")
        return out
    for i, e in enumerate(encs):
        out += ["encounter %s: %s" % (e.get("room") or i + 1, p) for p in check_encounter(e, map_spec)]
    return out


def check_encounter(e, map_spec=None):
    out = []
    for key in ("room", "level", "party_size"):
        if not e.get(key):
            out.append("%s: required" % key)
    job = e.get("story_job") or {}
    if not isinstance(job.get("locked"), list) or not job.get("locked") or not all(isinstance(x, str) and x for x in job["locked"]):
        out.append("story_job.locked: the canon lines this encounter serves (at least one)")
    clue_rooms = set(job.get("clue_rooms") or [])

    creatures = e.get("original")
    if not isinstance(creatures, list) or not creatures:
        out.append("original: the creatures in the encounter")
        creatures = []
    by_name = {}
    for c in creatures:
        name = c.get("srd")
        by_name[name] = c
        if not name or not isinstance(c.get("count"), int) or c["count"] < 1:
            out.append("original: each creature needs an srd name and a count")
        if not isinstance(c.get("int"), int):
            out.append("original %s: its Intelligence (int)" % name)
        if not c.get("roles"):
            out.append("original %s: its roles" % name)
        if len(c.get("start") or []) != c.get("count"):
            out.append("original %s: one start square per creature" % name)

    diff = e.get("difficulty") or {}
    if not isinstance(diff.get("xp"), int) or diff.get("band") not in BANDS:
        out.append("difficulty: xp and band (%s)" % ", ".join(BANDS))
    m = diff.get("measured") or {}
    if m.get("plays_as") not in PLAYS_AS or not isinstance(m.get("drops_per_run"), (int, float)) or not m.get("report"):
        out.append("difficulty.measured: plays_as (%s), drops_per_run and the report it came from" % ", ".join(PLAYS_AS))

    rem = e.get("remix") or {}
    if not rem.get("may_change") or not rem.get("must_keep"):
        out.append("remix: may_change and must_keep")
    f = rem.get("filters") or {}
    if f.get("tone_cap") not in TONES:
        out.append("remix.filters.tone_cap: one of %s" % ", ".join(TONES))
    if f.get("max_size") not in SIZES:
        out.append("remix.filters.max_size: one of %s" % ", ".join(SIZES))

    routes = e.get("routes")
    if not isinstance(routes, list) or len(routes) < 2:
        out.append("routes: at least two non-combat ways through")
        routes = []
    seen = set()
    for r in routes:
        rid = r.get("id") or "?"
        if rid in seen:
            out.append("route %s: the id is used twice" % rid)
        seen.add(rid)
        if r.get("approach") not in APPROACHES:
            out.append("route %s: approach must be one of %s" % (rid, ", ".join(APPROACHES)))
        who = r.get("who") or []
        for name in who:
            if name not in by_name:
                out.append("route %s: %s is not in the encounter" % (rid, name))
            elif r.get("approach") in TALK and (by_name[name].get("int", 0) < TALK_INT or not by_name[name].get("languages")):
                out.append("route %s: %s cannot be talked to (Intelligence %s, languages %s): use distract, scare off, "
                           "sneak past or avoid" % (rid, name, by_name[name].get("int"), by_name[name].get("languages") or "none"))
        chk = r.get("check")
        if chk is not None:
            if chk.get("ability") not in ABILITIES:
                out.append("route %s: check.ability one of %s" % (rid, ", ".join(ABILITIES)))
            if not isinstance(chk.get("dc"), int) or not DC_RANGE[0] <= chk["dc"] <= DC_RANGE[1]:
                out.append("route %s: DC between %d and %d (SRD 5.2.1 Typical Difficulty Classes)" % ((rid,) + DC_RANGE))
        elif not r.get("condition"):
            out.append("route %s: a check or a condition" % rid)
        for key in ("success", "failure", "canon"):
            if not r.get(key):
                out.append("route %s: %s (what happens / how it serves the story)" % (rid, key))
        skipped = set(r.get("bypasses") or []) & clue_rooms
        if skipped and not r.get("clue_elsewhere"):
            out.append("route %s: it skips %s, which delivers a locked clue: say where the clue can still be found "
                       "(clue_elsewhere)" % (rid, ", ".join(sorted(skipped))))

    out += check_events(e.get("events") or [])
    if map_spec is not None:
        out += check_against_map(e, map_spec)
    return out


# 2026-10-20 (GM: "underground island rooms and caverns can have traps and events that fill them partially or fully with
# water"): events that change the room during the fight; Remix may retune them as a difficulty lever. Depths: shallow
# (wading; whether it slows movement is a GM ruling, proposed for the house rules), deep (swimming), full (underwater:
# holding breath, suffocation; SRD 5.2.1 as the simulator's water zones play it).
EVENT_KINDS = ("flood", "trap", "collapse", "fire", "darkness", "reinforcements")
DEPTHS = ("shallow", "deep", "full")


def check_events(events):
    out = []
    for ev in events:
        eid = ev.get("id") or "?"
        if ev.get("kind") not in EVENT_KINDS:
            out.append("event %s: kind must be one of %s" % (eid, ", ".join(EVENT_KINDS)))
        if not ev.get("trigger"):
            out.append("event %s: its trigger" % eid)
        stages = ev.get("stages") or []
        if ev.get("kind") == "flood":
            if not stages:
                out.append("event %s: a flood needs stages (round, area, depth)" % eid)
            rounds = [s.get("round") for s in stages]
            if any(not isinstance(r, int) or r < 1 for r in rounds) or rounds != sorted(rounds):
                out.append("event %s: stages in order of round (1 or later)" % eid)
            for s in stages:
                if s.get("depth") not in DEPTHS:
                    out.append("event %s: depth must be one of %s" % (eid, ", ".join(DEPTHS)))
                if not s.get("area"):
                    out.append("event %s: each stage names its area" % eid)
        counter = ev.get("counter") or {}
        if not counter.get("how"):
            out.append("event %s: a counter (how the party stops it, escapes it or survives it)" % eid)
        chk = counter.get("check")
        if chk:
            if chk.get("ability") not in ABILITIES:
                out.append("event %s: counter check ability one of %s" % (eid, ", ".join(ABILITIES)))
            if not isinstance(chk.get("dc"), int) or not DC_RANGE[0] <= chk["dc"] <= DC_RANGE[1]:
                out.append("event %s: counter DC between %d and %d" % ((eid,) + DC_RANGE))
    return out


def check_against_map(e, spec):
    """The room is one of the map's room keys, and the creatures are the map's encounter, square for square."""
    out = []
    rooms = [title.split(" ")[0] for title, _ in spec.get("stories", [])]
    if e.get("room") not in rooms:
        out.append("room %s is not a room key on the map (%s)" % (e.get("room"), ", ".join(rooms)))
    enc = next((x for x in spec.get("encounters", []) if str(x.get("name", "")).startswith(str(e.get("room")))), None)
    if not enc:
        out.append("the map has no encounter in %s" % e.get("room"))
        return out
    on_map = {name: (len(spots), [tuple(p) for p in spots]) for name, _, _, spots in enc["npcs"]}
    described = {c.get("srd"): (c.get("count"), [tuple(p) for p in c.get("start") or []]) for c in e.get("original") or []}
    if on_map != described:
        out.append("the creatures and start squares differ from the map's encounter: map %s, description %s" % (
            {k: v[0] for k, v in on_map.items()}, {k: v[0] for k, v in described.items()}))
    if (e.get("difficulty") or {}).get("xp") != enc.get("exp"):
        out.append("difficulty.xp %s differs from the map's %s" % ((e.get("difficulty") or {}).get("xp"), enc.get("exp")))
    return out


def load_map(script):
    script = Path(script)
    sys.path.insert(0, str(script.resolve().parents[2] / "tools"))
    spec = importlib.util.spec_from_file_location(script.stem, script)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod.SPEC


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("file"); ap.add_argument("--map")
    a = ap.parse_args(argv)
    problems = check(json.loads(Path(a.file).read_text(encoding="utf-8")), load_map(a.map) if a.map else None)
    print("\n".join(problems) if problems else "OK: the description is complete.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
