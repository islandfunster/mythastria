"""MAP RULE (GM 2026-10-24: "There's a problem with the adventure maps. They still have 0ft wide inner walls. They need to
be 5ft wide walls."; "The map may be expanded to make them fit. Doors may be moved."): turn a map's thin inner walls into
wall squares. Where a thin wall stood between two floor squares, a new column (or row) of squares is put in: wall where
the line was, a doorway where its door was, floor elsewhere (the rooms it crosses grow 5 ft); so no room shrinks. A small
closed box no creature starts in (a pillar drawn as four lines) becomes wall squares. Everything with a square moves with
the map: creatures, props, lights, ceilings, zones and an encounters file's start squares. The walls the simulator
uses are then made from the squares (tools/map_import.cell_walls), each door keeping its name.

  py tools/thicken_walls.py ..\\adventures\\my_module            (all its maps; --dry-run to only report)
"""
import argparse, json, math, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import map_import                                                    # noqa: E402  cell_walls, rule_problems, _door_face

PILLAR = 4                                                           # a closed box of at most this many squares, empty


def unit_edges(points):
    """An axis-aligned wall line on the half grid -> its unit edges: ("v", b, y) between (b, y) and (b + 1, y), or
    ("h", x, b) between (x, b) and (x, b + 1)."""
    (ax, ay), (bx, by) = points[0], points[-1]
    if ax == bx and (ax * 2) % 2 == 1:
        b = int(math.floor(ax))
        return [("v", b, y) for y in range(int(round(min(ay, by) + 0.5)), int(round(max(ay, by) + 0.5)))]
    if ay == by and (ay * 2) % 2 == 1:
        b = int(math.floor(ay))
        return [("h", x, b) for x in range(int(round(min(ax, bx) + 0.5)), int(round(max(ax, bx) + 0.5)))]
    raise ValueError("A wall that is not on the grid: %s" % (points,))


class Axis:
    """Old -> new positions along one axis once columns (or rows) are put in after the boundaries `cuts`."""
    def __init__(self, cuts):
        self.cuts = sorted(cuts)

    def cell(self, c):
        return c + sum(1 for b in self.cuts if b < c)

    def inserted(self, b):
        return self.cell(b) + 1

    def point(self, v):                                              # a token, light or prop position (may be x.5)
        v = float(v)
        out = v + sum(1 for b in self.cuts if b + 0.5 < v)
        if any(b + 0.5 == v for b in self.cuts):
            out += 0.5                                               # on the old line: the middle of the new square
        return int(out) if out == int(out) else out


def convert(sc, starts=None):
    """One scenario (a dict) -> (new scenario, report lines). starts: encounter start lists to move in place."""
    report = []
    cells = {tuple(c) for c in sc.get("wall_cells") or []}
    xs = [c[0] for c in cells] + [c["x"] for c in sc["combatants"]]
    ys = [c[1] for c in cells] + [c["y"] for c in sc["combatants"]]
    cols, rows = int(math.ceil(max(xs))) + 1, int(math.ceil(max(ys))) + 1
    solid = lambda x, y: not (0 <= x < cols and 0 <= y < rows) or (x, y) in cells
    edges, doors, faces = set(), {}, []                              # doors: edge -> the wall entry (its id, its fields)
    for w in sc["walls"]:
        for e in unit_edges(w["points"]):
            a, b = ((e[1], e[2]), (e[1] + 1, e[2])) if e[0] == "v" else ((e[1], e[2]), (e[1], e[2] + 1))
            if solid(*a) and solid(*b):
                continue
            if solid(*a) or solid(*b):                               # against a wall square already: nothing to do,
                if w.get("door"):                                    # but a door there stays on the floor's face
                    faces.append((b if solid(*a) else a, ("W" if e[0] == "v" else "N") if solid(*a) else ("E" if e[0] == "v" else "S"), w))
                continue
            if w.get("door"):
                doors[e] = w
            else:
                edges.add(e)
    # a door already at the mouth of a passage through a thick wall (one or more doors wide) stays where it is
    at_passage = []
    for e in doors:
        step = (0, 1) if e[0] == "v" else (1, 0)                     # along the door's line
        run = [e]
        for sign in (-1, 1):
            n = (e[0], e[1] + sign * step[0], e[2] + sign * step[1])
            while n in doors:
                run.append(n)
                n = (n[0], n[1] + sign * step[0], n[2] + sign * step[1])
        for side in (0, 1):                                          # the squares on one side of the doors
            cs = sorted((r[1], r[2]) if side == 0 else ((r[1] + 1, r[2]) if r[0] == "v" else (r[1], r[2] + 1)) for r in run)
            if solid(cs[0][0] - step[0], cs[0][1] - step[1]) and solid(cs[-1][0] + step[0], cs[-1][1] + step[1]):
                at_passage.append(e)
                break
    for e in at_passage:
        faces.append(((e[1], e[2]), "E" if e[0] == "v" else "S", doors.pop(e)))
    # pillars: small closed boxes no creature starts in become wall squares (a glowing obelisk's light stays where it is)
    used = {(int(round(c["x"])), int(round(c["y"]))) for c in sc["combatants"]}
    shut = edges | set(doors)
    seen = set()
    for y in range(rows):
        for x in range(cols):
            if (x, y) in seen or solid(x, y):
                continue
            region, todo = [], [(x, y)]
            seen.add((x, y))
            while todo:
                cx, cy = todo.pop()
                region.append((cx, cy))
                for e, n in ((("v", cx - 1, cy), (cx - 1, cy)), (("v", cx, cy), (cx + 1, cy)),
                             (("h", cx, cy - 1), (cx, cy - 1)), (("h", cx, cy), (cx, cy + 1))):
                    if not solid(*n) and e not in shut and n not in seen:
                        seen.add(n); todo.append(n)
            sides = lambda e: {(e[1], e[2]), (e[1] + 1, e[2]) if e[0] == "v" else (e[1], e[2] + 1)}
            if len(region) <= PILLAR and not set(region) & used and not set(region) & {f[0] for f in faces}                     and not any(sides(e) & set(region) for e in doors):
                cells |= set(region)
                report.append("A closed box of %d square%s at %s (a pillar) is now wall." % (len(region), "" if len(region) == 1 else "s", region[0]))
    keep = lambda e: not (solid(e[1], e[2]) or (solid(e[1] + 1, e[2]) if e[0] == "v" else solid(e[1], e[2] + 1)))
    edges = {e for e in edges if keep(e)}
    doors = {e: w for e, w in doors.items() if keep(e)}

    # columns first: a new column after each boundary that has a thin wall or door between floor squares
    vcuts = sorted({e[1] for e in edges | set(doors) if e[0] == "v"})
    X = Axis(vcuts)
    ncols = cols + len(vcuts)
    wall2, door2, hedges2, hdoors2 = set(), {}, set(), {}
    for (x, y) in cells:
        wall2.add((X.cell(x), y))
    for b in vcuts:
        nx = X.inserted(b)
        for y in range(rows):
            left, right = (b, y), (b + 1, y)
            if solid(*left) or solid(*right) or ("v", b, y) in edges:
                wall2.add((nx, y))
            elif ("v", b, y) in doors:
                door2[(nx, y)] = (doors[("v", b, y)], "v")
    for e in edges:
        if e[0] == "h":
            hedges2.add((X.cell(e[1]), e[2]))
    for e, w in doors.items():
        if e[0] == "h":
            hdoors2[(X.cell(e[1]), e[2])] = w
    for b in vcuts:                                                  # a thin wall crossing the new column carries on
        nx = X.inserted(b)
        for y in range(rows):
            if (nx, y) in wall2 or (nx, y) in door2:
                continue
            if (X.cell(b), y) in hedges2 and (X.cell(b + 1), y) in hedges2:
                hedges2.add((nx, y))
    # then rows, the same way
    hcuts = sorted({y for (_, y) in hedges2 | set(hdoors2)})
    Y = Axis(hcuts)
    nrows = rows + len(hcuts)
    wall3, door3 = set(), {}
    for (x, y) in wall2:
        wall3.add((x, Y.cell(y)))
    for (x, y), w in door2.items():
        door3[(x, Y.cell(y))] = w
    faces3 = [((X.cell(f[0][0]), Y.cell(f[0][1])), f[1], f[2]) for f in faces]
    is_wall2 = lambda x, y: not (0 <= x < ncols and 0 <= y < rows) or (x, y) in wall2
    for b in hcuts:
        ny = Y.inserted(b)
        for x in range(ncols):
            above, below = (x, b), (x, b + 1)
            if is_wall2(*above) or is_wall2(*below) or (x, b) in hedges2:
                wall3.add((x, ny))
            elif (x, b) in hdoors2:
                door3[(x, ny)] = (hdoors2[(x, b)], "h")
    # walls from the squares; each door on a face: a doorway's west (or north) face, or the floor's face on the wall
    report += map_import.rule_problems(ncols, nrows, wall3, [])
    segs = set()
    for w in map_import.cell_walls(ncols, nrows, wall3, []):
        segs |= unit_segments(w["points"])
    by_door = {}
    for (x, y), (w, kind) in door3.items():
        s = ((x - .5, y - .5), (x - .5, y + .5)) if kind == "v" else ((x - .5, y - .5), (x + .5, y - .5))
        by_door.setdefault(w["id"], (w, set()))[1].add(s)
    for (x, y), side, w in faces3:
        s = {"E": ((x + .5, y - .5), (x + .5, y + .5)), "W": ((x - .5, y - .5), (x - .5, y + .5)),
             "S": ((x - .5, y + .5), (x + .5, y + .5)), "N": ((x - .5, y - .5), (x + .5, y - .5))}[side]
        segs.discard(s)
        by_door.setdefault(w["id"], (w, set()))[1].add(s)
    walls = [{"id": "w%d" % i, "points": pts} for i, pts in enumerate(runs(segs))]
    for name, (w, ss) in by_door.items():
        for k, pts in enumerate(runs(ss)):
            walls.append(dict({key: v for key, v in w.items() if key != "points"}, id=name if k == 0 else "%s %d" % (name, k + 1), points=pts))
    out = dict(sc)
    out["walls"] = walls
    out["wall_cells"] = [list(c) for c in sorted(wall3, key=lambda c: (c[1], c[0]))]
    pt = lambda x, y: (X.point(x), Y.point(y))

    def move(o):
        o["x"], o["y"] = pt(o["x"], o["y"])
    out["combatants"] = [dict(c) for c in sc["combatants"]]
    for c in out["combatants"]:
        move(c)
    out["props"] = [dict(p) for p in sc.get("props") or []]
    for p in out["props"]:
        move(p)
    if sc.get("lighting"):
        out["lighting"] = dict(sc["lighting"], lights=[dict(l) for l in sc["lighting"].get("lights", [])])
        for l in out["lighting"]["lights"]:
            if "x" in l:
                move(l)

    def rect(r):
        return [X.cell(r[0]), Y.cell(r[1]), X.cell(r[2]), Y.cell(r[3])]
    out["ceilings"] = [dict(c, rect=rect(c["rect"])) if "rect" in c else dict(c) for c in sc.get("ceilings") or []]
    out["zones"] = [dict(z, rect=rect(z["rect"])) if "rect" in z else dict(z) for z in sc.get("zones") or []]
    for s in starts or []:
        for i, (x, y) in enumerate(s):
            s[i] = list(pt(x, y))
    for c in out["combatants"]:
        n = map_import.size_squares(c)
        x0, y0 = c["x"] - (n - 1) / 2, c["y"] - (n - 1) / 2
        block = {(int(round(x0 + i)), int(round(y0 + j))) for i in range(n) for j in range(n)}
        if block & wall3:
            report.append("%s starts in a wall at (%s, %s): move it." % (c["name"], c["x"], c["y"]))
    report.insert(0, "%d x %d -> %d x %d squares; %d column%s and %d row%s put in; %d door%s." % (
        cols, rows, ncols, nrows, len(vcuts), "" if len(vcuts) == 1 else "s", len(hcuts), "" if len(hcuts) == 1 else "s",
        len(by_door), "" if len(by_door) == 1 else "s"))
    return out, report


def unit_segments(points):
    """A straight wall line -> its one-square pieces ((x0, y0), (x1, y1)), each from its smaller end."""
    (ax, ay), (bx, by) = points[0], points[-1]
    out = set()
    if ax == bx:
        for i in range(int(round(abs(by - ay)))):
            y = min(ay, by) + i
            out.add(((ax, y), (ax, y + 1)))
    else:
        for i in range(int(round(abs(bx - ax)))):
            x = min(ax, bx) + i
            out.add(((x, ay), (x + 1, ay)))
    return out


def runs(segs):
    """One-square pieces -> straight lines, joined end to end."""
    out = []
    vert = sorted(s for s in segs if s[0][0] == s[1][0])
    horiz = sorted((s for s in segs if s[0][1] == s[1][1] and s[0][0] != s[1][0]), key=lambda s: (s[0][1], s[0][0]))
    for group in (vert, horiz):
        cur = None
        for a, b in group:
            if cur and cur[1] == a:
                cur = (cur[0], b)
            else:
                if cur:
                    out.append([list(cur[0]), list(cur[1])])
                cur = (a, b)
        if cur:
            out.append([list(cur[0]), list(cur[1])])
    return out


def thin_edges(sc):
    """The thin walls left between two floor squares (0 for a map that passes)."""
    cells = {tuple(c) for c in sc.get("wall_cells") or []}
    n = 0
    for w in sc["walls"]:
        if w.get("door"):
            continue
        for e in unit_edges(w["points"]):
            a, b = ((e[1], e[2]), (e[1] + 1, e[2])) if e[0] == "v" else ((e[1], e[2]), (e[1], e[2] + 1))
            n += a not in cells and b not in cells
    return n


def with_rock(sc):
    """GM 2026-10-24 ("test/live_keep.json" still had 0-ft walls): a map drawn only with wall lines (no wall_cells) gets
    its rock: every square reached from outside without crossing a wall line is a wall square, and a one-square stone
    frame goes round the map (everything moves one square right and down), so no floor touches the map's edge."""
    sc = json.loads(json.dumps(sc))
    edges = set()
    for w in sc["walls"]:
        edges |= set(unit_edges(w["points"]))
    xs = [p[0] for w in sc["walls"] for p in w["points"]] + [c["x"] for c in sc["combatants"]]
    ys = [p[1] for w in sc["walls"] for p in w["points"]] + [c["y"] for c in sc["combatants"]]
    cols, rows = int(math.floor(max(xs) + 0.5)) + 1, int(math.floor(max(ys) + 0.5)) + 1
    seen, todo = set(), [(-1, -1)]
    while todo:                                                  # outside, flooding in up to the wall lines
        x, y = todo.pop()
        if (x, y) in seen:
            continue
        seen.add((x, y))
        for (nx, ny), e in (((x + 1, y), ("v", x, y)), ((x - 1, y), ("v", x - 1, y)),
                            ((x, y + 1), ("h", x, y)), ((x, y - 1), ("h", x, y - 1))):
            if -1 <= nx <= cols and -1 <= ny <= rows and e not in edges and (nx, ny) not in seen:
                todo.append((nx, ny))
    rock = {(x + 1, y + 1) for x, y in seen if 0 <= x < cols and 0 <= y < rows}
    rock |= {(x, y) for x in range(cols + 2) for y in range(rows + 2) if x in (0, cols + 1) or y in (0, rows + 1)}
    for w in sc["walls"]:
        w["points"] = [[p[0] + 1, p[1] + 1] for p in w["points"]]
    for c in sc["combatants"] + list(sc.get("props") or []) + [l for l in (sc.get("lighting") or {}).get("lights", []) if "x" in l]:
        c["x"], c["y"] = c["x"] + 1, c["y"] + 1
    for z in list(sc.get("ceilings") or []) + list(sc.get("zones") or []):
        if "rect" in z:
            z["rect"] = [v + 1 for v in z["rect"]]
    sc["wall_cells"] = [list(c) for c in sorted(rock, key=lambda c: (c[1], c[0]))]
    return sc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pack", help="an adventure pack folder (its scenarios/*.json and encounters/*.json), or one map's .json")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.pack.endswith(".json"):                                 # one map (a simulator test map, say)
        f = Path(a.pack)
        raw = f.read_bytes().decode("utf-8")
        sc = json.loads(raw)
        if not sc.get("wall_cells"):
            sc = with_rock(sc)
        new, report = convert(sc)
        print("%s: %s" % (f.name, " ".join(report)))
        if not a.dry_run:
            write(f, new, raw)
        return 0
    pack = Path(a.pack)
    enc_files = {}
    for f in sorted((pack / "encounters").glob("*.encounters.json")):
        enc_files[f.name.split(".")[0]] = (f, json.loads(f.read_text(encoding="utf-8")))
    for f in sorted((pack / "scenarios").glob("*.json")):
        raw = f.read_bytes().decode("utf-8")
        sc = json.loads(raw)
        if not sc.get("wall_cells"):
            print("%s: no wall squares (a placeholder): left as it is." % f.name)
            continue
        if not thin_edges(sc):
            print("%s: already passes the map rule." % f.name)
            continue
        enc = enc_files.get(f.stem)
        starts = [o["start"] for e in (enc[1]["encounters"] if enc else []) for o in e.get("original", []) if "start" in o]
        new, report = convert(sc, starts)
        print("%s: %s" % (f.name, " ".join(report)))
        if not a.dry_run:
            write(f, new, raw)
            if enc and starts:
                write(enc[0], enc[1], enc[0].read_bytes().decode("utf-8"))
    return 0


def write(f, data, before):
    """The file's own layout: one-space indent, its line endings."""
    text = json.dumps(data, indent=1, ensure_ascii=False) + ("\n" if before.endswith("\n") else "")
    if "\r\n" in before:
        text = text.replace("\n", "\r\n")
    f.write_bytes(text.encode("utf-8"))


if __name__ == "__main__":
    sys.exit(main())
