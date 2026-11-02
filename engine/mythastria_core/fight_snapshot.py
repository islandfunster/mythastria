"""v0.7.89 PRACTICE-TWIN-01: "save this fight, continue it in the simulator".

A fight snapshot is the bridge's live picture of the current fight, saved as one local JSON file: the Combat Tracker
(HP, wounds, effects, initiative, round, whose turn), token positions, the map's confirmed walls/doors and lighting,
FG's parsed NPC actions, the linked PCs' synced sheets (weapons, AC) and which NPCs noticed the party.
`py sim/run_sim.py --from-snapshot <file>` continues the fight from the saved turn (sim/practice.py).

The file holds campaign/module data: it stays in mythastria_core/cache (never committed, shared or sent for review).
Nothing is ever written back to Fantasy Grounds from a snapshot or a practice run."""
import copy, json, re, time
from pathlib import Path

KIND = "aibridge-fight-snapshot"
FORMAT = 1


def snapshot_dir():
    return Path(__file__).resolve().parent / "cache" / "fight_snapshots"


def take(combat, combatants, parser_records, sheets, aware, perception_dc, walls, version):
    """The bridge's state -> a snapshot dict (copies only; the live state is not changed).
    combat: the bridge's combat dict (round, space, multi_done, bonus_used, slot_used); combatants: {ctpath: normalized
    combatant} as /combat.json shows them; parser_records: powparse records; sheets: {charsheet path: synced sheet};
    aware: CT paths of NPCs that noticed the party; walls: map_walls.for_map(map) or None."""
    combatants = copy.deepcopy(combatants)
    active = next((p for p, a in combatants.items() if str(a.get("active")) == "1"), None)
    done = combat.get("multi_done") or (None, [], [])
    progress = {"moved_ft": float((combat.get("space") or {}).get("moved") or 0),
                "bonus_used": bool(active) and combat.get("bonus_used") == active,
                "slot_used": bool(active) and combat.get("slot_used") == active,
                "multi_done": list(done[1]) if done and done[0] == active else []}
    linked = {(a.get("actor_link") or {}).get("recordname") for a in combatants.values()
              if (a.get("actor_link") or {}).get("class") == "charsheet"}
    return {
        "kind": KIND, "format": FORMAT, "taken": time.strftime("%Y-%m-%d %H:%M:%S"), "bridge_version": version,
        "policy": "local_only",
        "note": "Local practice data (campaign and module content): keep on this PC. Nothing in this file is sent "
                "back to Fantasy Grounds.",
        "round": combat.get("round"), "active": active, "turn_progress": progress,
        "space": copy.deepcopy(combat.get("space") or {}),
        "combatants": combatants,
        "parser": {k: copy.deepcopy(r) for k, r in (parser_records or {}).items() if r.get("ctpath") in combatants},
        "sheets": {p: copy.deepcopy(s) for p, s in (sheets or {}).items() if p in linked},
        "awareness": {"aware": sorted(a for a in aware if a in combatants), "perception_dc": perception_dc},
        "walls": copy.deepcopy(walls) if walls else None,
    }


def save(snap, directory=None):
    """Write the snapshot under mythastria_core/cache/fight_snapshots (or `directory`); returns the path."""
    d = Path(directory) if directory else snapshot_dir()
    d.mkdir(parents=True, exist_ok=True)
    mapname = (snap.get("walls") or {}).get("map") or (snap.get("space") or {}).get("mapname") or "fight"
    stem = "%s_%s" % (re.sub(r"[^A-Za-z0-9_-]+", "_", mapname).strip("_")[:40] or "fight", time.strftime("%Y%m%d_%H%M%S"))
    path, n = d / (stem + ".json"), 1
    while path.exists():
        n += 1; path = d / ("%s_%d.json" % (stem, n))
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return path


def load(path):
    snap = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(snap, dict) or snap.get("kind") != KIND:
        raise ValueError("%s is not a saved fight (make one with the bridge page's Save button or save_fight.py)" % path)
    if snap.get("format") != FORMAT:
        raise ValueError("saved fight format %s is not supported by this version" % snap.get("format"))
    return snap


def summary(snap):
    """Plain lines for the bridge page and the command line."""
    actors = snap.get("combatants") or {}
    active = actors.get(snap.get("active") or "", {}).get("name") or "nobody"
    walls = snap.get("walls")
    out = ["Round %s, %s's turn; %d combatants." % (snap.get("round") or "?", active, len(actors))]
    for a in actors.values():
        try: left = int(float(a.get("hp_total") or 0)) - int(float(a.get("wounds") or 0))
        except ValueError: left = "?"
        effects = [e.get("label", "") for e in a.get("effects") or [] if str(e.get("active", "1")) != "0"]
        out.append("%s: %s/%s HP%s" % (a.get("name", "?"), left, a.get("hp_total") or "?",
                                       ("; effects: " + ", ".join(effects)) if effects else ""))
    if walls:
        out.append("Map %s: confirmed walls (%d), doors open: %s; lighting: %s." % (
            walls.get("map"), len(walls.get("occluders") or []), ", ".join(walls.get("open_doors") or []) or "none",
            (walls.get("lighting") or {}).get("ambient") or "bright (not set)"))
    else:
        out.append("No confirmed walls for this map: the practice run has no walls.")
    return out
