"""REGION-01 (GM 2026-10-20: "The outdoor map can simply create a popup of a standard terrain battle map."): a standard
outdoor battle map for a terrain of the region map (plains, road, forest, hills, mountains, swamp, desert, coast, open
water), with the GM's creatures, for Play live. Display and rules: trees and boulders block movement and sight (natural
walls round their squares, drawn as the trees and rocks themselves, never as stone walls); pools and the sea are water
zones (the simulator's swimming and underwater rules); the ground colour is display only. Night is dim light (moon and
stars), not darkness. Seeded: the same terrain and seed give the same map. Written to sim/scenarios/region/.

  py tools/terrain_battle.py forest --creature Wolf --count 4 [--seed 7] [--night]
"""
import argparse, json, random, re, sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools")]
import map_import  # noqa: E402

COLS, ROWS = 24, 18
PARTY_AT, FOES_AT = (4, ROWS // 2), (COLS - 5, ROWS // 2)
OUT = ROOT / "sim" / "scenarios" / "region"

# what each terrain holds: blocking features (squares), loose props (display), water, the ground colour, suggested foes
# 2026-10-21 (GM): only SRD 5.2.1 creatures: Orc -> Hobgoblin Warrior (plains, hills) / Bugbear Warrior (mountains);
# Lizardfolk -> Swarm of Insects, Bullywug Warrior -> Giant Lizard (swamp). The names must be in the creature library.
TERRAINS = {
    "plains": {"label": "Plains", "ground": "grass", "block": ("boulder", 0.02), "props": (("bush", 8), ("rock", 3)),
               "foes": ["Bandit", "Wolf", "Goblin Warrior", "Hobgoblin Warrior", "Scout", "Guard"]},
    "road": {"label": "Road", "ground": "grass", "road": True, "block": ("tree", 0.04), "props": (("bush", 6), ("log", 2)),
             "foes": ["Bandit", "Bandit Captain", "Goblin Warrior", "Wolf"]},
    "forest": {"label": "Forest", "ground": "forest", "block": ("tree", 0.16), "props": (("bush", 10), ("log", 3), ("fern", 6), ("mushrooms", 3)),
               "foes": ["Wolf", "Goblin Warrior", "Brown Bear", "Giant Spider", "Owlbear", "Giant Venomous Snake", "Scout"]},
    "hills": {"label": "Hills", "ground": "dry", "block": ("boulder", 0.07), "props": (("rock", 8), ("bush", 5)),
              "foes": ["Hobgoblin Warrior", "Goblin Warrior", "Hill Giant", "Wolf", "Goblin Boss", "Kobold Warrior"]},
    "mountains": {"label": "Mountains", "ground": "stone", "block": ("boulder", 0.13), "cluster": True, "props": (("rock", 12),),
                  "foes": ["Bugbear Warrior", "Griffon", "Ogre", "Hill Giant", "Harpy", "Gargoyle", "Earth Elemental", "Kobold Warrior"]},
    "swamp": {"label": "Swamp", "ground": "mud", "block": ("dead_tree", 0.05), "pools": 3, "props": (("fern", 8), ("moss", 6), ("log", 3)),
              "foes": ["Swarm of Insects", "Giant Frog", "Crocodile", "Giant Lizard", "Giant Venomous Snake", "Zombie", "Giant Rat"]},
    "desert": {"label": "Desert", "ground": "sand", "block": ("boulder", 0.03), "props": (("rock", 5), ("bones", 2)),
               "foes": ["Giant Scorpion", "Bandit", "Jackal", "Gnoll Warrior", "Skeleton", "Giant Venomous Snake"]},
    "coast": {"label": "Coast", "ground": "sand", "sea": 4, "block": ("boulder", 0.03), "props": (("rock", 6), ("log", 2), ("boat", 1)),
              "foes": ["Giant Crab", "Merfolk Skirmisher", "Bandit", "Harpy", "Sahuagin Warrior"]},
}
TERRAINS["water"] = dict(TERRAINS["coast"], label="Open water (the shore)")


def _reachable(cols, rows, blocked, a, b):
    seen, todo = {a}, deque([a])
    while todo:
        x, y = todo.popleft()
        if (x, y) == b:
            return True
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= n[0] < cols and 0 <= n[1] < rows and n not in blocked and n not in seen:
                seen.add(n); todo.append(n)
    return False


def suggested(terrain, lib):
    """The terrain's usual foes that have a simulator stat block, best first; any creature if none has."""
    names = [n for n in TERRAINS[terrain]["foes"] if n in lib]
    return names or sorted(lib)[:1]


# MAPGEN-01 (GM 2026-10-22: "the design preference seems do-able now for outdoor maps and their corresponding
# battle-maps"): the GM's design preferences for battle maps, and what the region map's hex holds (a road through it,
# a river across it, the sea on one side), so the battle map matches the hex it is fought on.
SIZES = {"small": (18, 14), "normal": (COLS, ROWS), "large": (32, 24)}
DENSITY = {"open": .5, "normal": 1.0, "dense": 1.7}
SIDES = ("north", "east", "south", "west")


def check_design(design, context):
    design, context = dict(design or {}), dict(context or {})
    if set(design) - {"size", "density"} or design.get("size", "normal") not in SIZES or design.get("density", "normal") not in DENSITY:
        raise ValueError("Battle map design: size small, normal or large; density open, normal or dense.")
    if set(context) - {"road", "river", "sea"} or context.get("sea") not in (None,) + SIDES \
            or not all(isinstance(context.get(k, False), bool) for k in ("road", "river")):
        raise ValueError("Hex context: road and river true or false; sea north, east, south, west or none.")
    return design, context


def build(terrain, creature, count, lib, seed=1, night=False, design=None, context=None):
    if terrain not in TERRAINS:
        raise ValueError("Unknown terrain %r (one of %s)." % (terrain, ", ".join(TERRAINS)))
    design, context = check_design(design, context)
    cols, rows = SIZES[design.get("size", "normal")]
    dens, area = DENSITY[design.get("density", "normal")], cols * rows / (COLS * ROWS)
    party_at, foes_at = (4, rows // 2), (cols - 5, rows // 2)
    extra = "" if not design and not context else ":" + json.dumps([design, context], sort_keys=True)
    t, rng = TERRAINS[terrain], random.Random("%s:%s%s" % (terrain, seed, extra))
    keep_clear = {(x, y) for sx, sy in (party_at, foes_at) for x in range(sx - 2, sx + 3) for y in range(sy - 2, sy + 3)}
    zones, ground_cells, water = [], {}, set()
    side = context.get("sea") or ("north" if t.get("sea") else None)
    if side:                                                          # the sea along one edge (the region's water side)
        d = t.get("sea", 4) if side in ("north", "south") else 3
        x0, y0, x1, y1 = {"north": (0, 0, cols - 1, d - 1), "south": (0, rows - d, cols - 1, rows - 1),
                          "west": (0, 0, d - 1, rows - 1), "east": (cols - d, 0, cols - 1, rows - 1)}[side]
        zones.append({"id": "sea", "kind": "water", "rect": [x0, y0, x1, y1]})
        water |= {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}
    road = bool(t.get("road") or context.get("road"))
    ford = set(range(rows // 2 - 1, rows // 2 + 1))
    if context.get("river"):                                          # a river across the field, a ford where the sides meet
        x = cols // 2 - 1
        for y in range(rows):
            x = max(cols // 2 - 3, min(cols // 2 + 1, x + rng.choice((-1, 0, 0, 1))))
            if y in ford:
                continue
            cells = {(x, y), (x + 1, y)} - water
            if cells:
                zones.append({"id": "river %d" % y, "kind": "water", "rect": [min(c[0] for c in cells), y, max(c[0] for c in cells), y]})
                water |= cells
    for i in range(int(round(t.get("pools", 0) * area))):            # swamp pools, away from the start squares
        for _ in range(50):
            w, h = rng.randint(2, 3), rng.randint(2, 3)
            x0, y0 = rng.randint(1, cols - w - 1), rng.randint(1, rows - h - 1)
            cells = {(x, y) for x in range(x0, x0 + w) for y in range(y0, y0 + h)}
            if not cells & keep_clear and not cells & water:
                zones.append({"id": "pool %d" % (i + 1), "kind": "water", "rect": [x0, y0, x0 + w - 1, y0 + h - 1]})
                water |= cells
                break
    if road:                                                          # a road across the map, through both start squares
        ground_cells["road"] = [[x, y] for x in range(cols) for y in (rows // 2 - 1, rows // 2) if (x, y) not in water]
    kind, share = t["block"]
    free = [(x, y) for x in range(cols) for y in range(rows) if (x, y) not in keep_clear and (x, y) not in water
            and not (road and rows // 2 - 1 <= y <= rows // 2)]
    for _ in range(40):                                               # blocking features, never cutting the field in two
        blocked = set()
        want = int(len(free) * min(.4, share * dens))
        while len(blocked) < want:
            c = rng.choice(free)
            blocked.add(c)
            if t.get("cluster") and len(blocked) < want:              # mountains: rock in clumps
                n = (c[0] + rng.choice((-1, 0, 1)), c[1] + rng.choice((-1, 0, 1)))
                if n in free:
                    blocked.add(n)
        if _reachable(cols, rows, blocked | water, party_at, foes_at):
            break
    else:
        blocked = set()
    taken = set(blocked) | water
    props = [{"kind": kind, "x": x, "y": y, "label": kind.replace("_", " ")} for x, y in sorted(blocked)]
    for pk, n in t["props"]:
        for _ in range(int(round(n * dens * area))):
            spots = [c for c in free if c not in taken]
            if not spots:
                break
            c = rng.choice(spots); taken.add(c)
            props.append({"kind": pk, "x": c[0], "y": c[1], "label": pk.replace("_", " ")})
    walls = map_import.cell_walls(cols, rows, blocked, [])
    walls = [dict(w, natural=True) for w in walls if not _on_edge(w, cols, rows)]   # the map's edge is open country
    lighting = {"ambient": "dim" if night else "bright", "lights": []}
    name = "%s battle%s" % (t["label"], " (night)" if night else "")
    # nobody starts inside a tree, a boulder or the water; a Large creature's whole space is clear (THREAT-02)
    sc = map_import._scenario(name, cols, rows, walls, [], lighting, None, party_at, creature, count, foes_at, lib, None,
                              avoid=blocked | water)
    sc.update(name="%s: %d x %s" % (name, count, creature), map_name=name, zones=zones, props=props, ground=t["ground"],
              ground_cells=ground_cells, source="SRD 5.2.1 (CC-BY-4.0) creatures; a standard Mythastria terrain battle map (REGION-01).",
              terrain=terrain, seed=seed, design=design, context=context)
    return sc


def _on_edge(w, cols=COLS, rows=ROWS):
    (x1, y1), (x2, y2) = w["points"]
    return (x1 == x2 and x1 in (-0.5, cols - 0.5)) or (y1 == y2 and y1 in (-0.5, rows - 0.5))


def write(sc, out_dir=OUT):
    out_dir.mkdir(parents=True, exist_ok=True)
    if not (out_dir / ".gitignore").exists():                     # made at the table, not part of the repository
        (out_dir / ".gitignore").write_text("*\n", encoding="utf-8")
    look = "_".join(v for v in (sc.get("design", {}).get("size"), sc.get("design", {}).get("density"),
                                  *(k for k, v in sorted(sc.get("context", {}).items()) if v is True),
                                  sc.get("context", {}).get("sea")) if v and v != "normal")
    slug = re.sub(r"[^a-z0-9]+", "_", "%s_%s_%s_%s" % (sc["terrain"], sc["seed"], look,
                                                      sc["combatants"][-1]["name"].rsplit(" ", 1)[0].lower())).strip("_")
    path = out_dir / (slug + ".json")
    path.write_text(json.dumps(sc, indent=1) + "\n", encoding="utf-8")
    return "region/" + path.name


def main(argv=None):
    import creature_threat
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("terrain", choices=sorted(TERRAINS)); ap.add_argument("--creature"); ap.add_argument("--count", type=int, default=4)
    ap.add_argument("--seed", type=int, default=1); ap.add_argument("--night", action="store_true")
    a = ap.parse_args(argv)
    lib = creature_threat.library()
    sc = build(a.terrain, a.creature or suggested(a.terrain, lib)[0], a.count, lib, a.seed, a.night)
    print("wrote sim/scenarios/" + write(sc))


if __name__ == "__main__":
    main()
