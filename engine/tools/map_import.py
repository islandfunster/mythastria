"""VIEW-01 (GM 2026-10-20: map imports "from Dungeondraft and similar tools"; "not their code, of course"): our own reader
for the published Universal VTT format (.dd2vtt, .uvtt: JSON with the grid, wall lines, doors, lights and the picture),
making a Mythastria map the simulator plays and the table draws.

  py tools/map_import.py FILE.dd2vtt --name "The Old Mill" --party 3,5 --creature Goblin --count 4 --foes 18,7

What it reads (grid units, from the map's origin): resolution (map_origin, map_size, pixels_per_grid); line_of_sight and
objects_line_of_sight (polylines: walls that block sight and movement); portals (bounds, closed: doors); lights
(position, range: dim light to its range, bright to half); environment (ambient_light: a dark colour makes a dark map
unless baked_lighting); image (base64 PNG, WebP or JPEG). A Universal VTT square n spans n..n+1 grid units; ours has its
centre at n, so a grid line at g is our g - 0.5. The file says nothing about where the floor is, so the GM gives the
party's and the creatures' start squares. Writes sim/scenarios/imported/<slug>.json and the picture into the table's
dist/maps/imported/<slug>.<ext>.

MAP RULE (GM 2026-10-20: walls "a minimum of 5 feet wide"; "this is a rule for map building") and the grid tools (GM:
"maps will need a grid aligment tool ... the grid will need to be created by hand by a survey tool"): on Play live the
GM's squares decide the walls. draft() turns a file's thin wall lines into wall squares (rock outside the outer wall, a
line inside becomes the square east or south of it, a door its doorway square); the GM corrects them by hand; a picture
with no file (convert_picture) gets its grid from the GM's alignment or survey and its squares drafted from the
picture's light in the browser. cell_walls() makes the wall lines the simulator uses from the squares; rule_problems()
refuses floor on the map's edge and a door that is not in a wall. (The command line keeps the file's own lines.)
"""
import argparse, base64, binascii, copy, json, math, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARTY = ["Hero 1", "Hero 2", "Hero 3", "Hero 4"]
MAX_SQUARES = 200
TABLE = ROOT.parent / "isles-table" / "dist"
KEEP = ("hp", "ac", "dex_save", "str_save", "con_save", "wis_save", "int_save", "cha_save", "speed", "space", "size", "type",
        "int", "senses", "wis_mod", "actions", "damageimmunities", "damageresistances", "damagevulnerabilities", "traits",
        "skills", "srd_name", "fly", "stealth", "multiattack", "spells", "reach", "reactions", "legendary", "conditions")


class ImportError_(ValueError):
    pass


def slug(name):
    s = re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")[:50]
    return s or "map"


def picture(data):
    try:
        raw = base64.b64decode(data or "", validate=False)
    except (binascii.Error, ValueError):
        raw = b""
    if raw.startswith(b"\x89PNG"):
        return raw, "png"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return raw, "webp"
    if raw.startswith(b"\xff\xd8"):
        return raw, "jpg"
    raise ImportError_("The file has no PNG, WebP or JPEG picture.")


def dark(env):
    """A dark ambient colour (RRGGBB[AA]) makes a dark map, unless the picture has its lighting baked in."""
    env = env or {}
    if env.get("baked_lighting"):
        return False
    m = re.match(r"^#?([0-9a-fA-F]{6})", str(env.get("ambient_light") or "ffffff"))
    if not m:
        return False
    r, g, b = (int(m.group(1)[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.5


def spots(start, n, cols, rows, taken):
    """n free squares from start outwards (a square spiral), on the map."""
    x0, y0 = start
    out, r = [], 0
    while len(out) < n and r <= max(cols, rows):
        ring = [(x0 + dx, y0 + dy) for dx in range(-r, r + 1) for dy in range(-r, r + 1) if max(abs(dx), abs(dy)) == r]
        for p in ring:
            if 0 <= p[0] < cols and 0 <= p[1] < rows and p not in taken and p not in out:
                out.append(p)
                if len(out) == n:
                    break
        r += 1
    return out


def size_squares(c):
    """Squares per side of a stat block's space (Large 2, Huge 3; space in feet)."""
    return max(1, int(round(float(c.get("space") or 5) / 5)))


def spaces(start, n, cols, rows, taken, size=1):
    """THREAT-02 (2026-10-20): token centres for n creatures of size x size squares from start outwards, each space whole
    on the map, clear of `taken` and of the others. The simulator's convention: a square's centre is its whole number, so
    a Large token sits on a grid corner (x.5) and a Huge one on its middle square."""
    if size <= 1:
        return spots(start, n, cols, rows, taken)
    used, out = set(taken), []
    for x, y in spots(start, cols * rows, cols - size + 1, rows - size + 1, set()):
        block = {(x + i, y + j) for i in range(size) for j in range(size)}
        if not block & used:
            used |= block
            out.append((x + (size - 1) / 2, y + (size - 1) / 2))
            if len(out) == n:
                break
    return out


def frame(u):
    """The file's grid: (origin x, origin y, cols, rows)."""
    if not isinstance(u, dict):
        raise ImportError_("This is not a Universal VTT file (a JSON object).")
    res = u.get("resolution") or {}
    try:
        ox, oy = float(res["map_origin"]["x"]), float(res["map_origin"]["y"])
        cols, rows = int(res["map_size"]["x"]), int(res["map_size"]["y"])
    except (KeyError, TypeError, ValueError):
        raise ImportError_("The file has no resolution (map_origin, map_size).")
    if not (1 <= cols <= MAX_SQUARES and 1 <= rows <= MAX_SQUARES):
        raise ImportError_("The map size %s x %s is outside 1-%d squares." % (cols, rows, MAX_SQUARES))
    return ox, oy, cols, rows


# ------------------------------------------------------------------ squares (MAP RULE)
def _cells(cells, cols, rows, what):
    out = []
    for c in cells or []:
        if not (isinstance(c, (list, tuple)) and len(c) == 2 and all(isinstance(v, int) and not isinstance(v, bool) for v in c)
                and 0 <= c[0] < cols and 0 <= c[1] < rows):
            raise ImportError_("A %s square %s is not a square of the map (%d x %d)." % (what, c, cols, rows))
        out.append((c[0], c[1]))
    return out


def _door_face(d, wall, cols, rows):
    """The doorway square's face that carries the door: across the passage, on its west or north side."""
    solid = lambda x, y: not (0 <= x < cols and 0 <= y < rows) or (x, y) in wall
    x, y = d
    if solid(x, y - 1) and solid(x, y + 1) and not solid(x - 1, y) and not solid(x + 1, y):
        return ("v", x, y)
    if solid(x - 1, y) and solid(x + 1, y) and not solid(x, y - 1) and not solid(x, y + 1):
        return ("h", x, y)
    return None


def rule_problems(cols, rows, wall, door):
    """What breaks the map rule, in words (empty: the map passes)."""
    wall, door = set(map(tuple, wall)), [tuple(d) for d in door]
    floor = [(x, y) for y in range(rows) for x in range(cols) if (x, y) not in wall]
    out = []
    if not floor:
        out.append("There is no floor: paint some floor squares.")
    edge = [c for c in floor if c[0] in (0, cols - 1) or c[1] in (0, rows - 1)]
    if edge:
        out.append("%d squares of floor on the map's edge (e.g. %s): the map needs a wall round it." % (len(edge), edge[0]))
    for d in door:
        if d in wall or _door_face(d, wall, cols, rows) is None:
            out.append("The door at %s is not in a wall (a wall square on two opposite sides, floor on the others)." % (d,))
    return out


def cell_walls(cols, rows, wall, door):
    """Wall squares and doorway squares -> the simulator's walls: every edge between floor and wall (or the map's edge),
    joined into straight runs, and a door across each doorway (ids "door 1", ...)."""
    wall = set(map(tuple, wall))
    faces = {}
    for i, d in enumerate(door or []):
        f = _door_face(tuple(d), wall, cols, rows)
        if f:
            faces[f] = "door %d" % (i + 1)
    solid = lambda x, y: not (0 <= x < cols and 0 <= y < rows) or (x, y) in wall
    edges = set()
    for y in range(rows):
        for x in range(cols):
            if (x, y) in wall:
                continue
            for e, other in ((("v", x, y), (x - 1, y)), (("v", x + 1, y), (x + 1, y)),
                             (("h", x, y), (x, y - 1)), (("h", x, y + 1), (x, y + 1))):
                if solid(*other) and e not in faces:
                    edges.add(e)
    out = []
    for kind in ("v", "h"):
        line = {}
        for k, a, b in edges:
            if k == kind:
                line.setdefault(a if kind == "v" else b, []).append(b if kind == "v" else a)
        for fixed, pos in sorted(line.items()):
            pos.sort()
            start = prev = pos[0]
            for q in pos[1:] + [None]:
                if q is not None and q == prev + 1:
                    prev = q
                    continue
                a, b = ((fixed, start), (fixed, prev + 1)) if kind == "v" else ((start, fixed), (prev + 1, fixed))
                out.append({"id": "w%d" % len(out), "points": [[a[0] - 0.5, a[1] - 0.5], [b[0] - 0.5, b[1] - 0.5]]})
                if q is not None:
                    start = prev = q
    for (kind, x, y), name in sorted(faces.items(), key=lambda kv: int(kv[1].split()[1])):
        a, b = ((x, y), (x, y + 1)) if kind == "v" else ((x, y), (x + 1, y))
        out.append({"id": name, "door": True, "points": [[a[0] - 0.5, a[1] - 0.5], [b[0] - 0.5, b[1] - 0.5]]})
    return out


def draft(u):
    """A Universal VTT file's thin walls -> a first draft of wall and doorway squares for the GM to correct."""
    ox, oy, cols, rows = frame(u)
    blocked, portal, wall = set(), set(), set()

    def unit_edges(a, b):
        (ax, ay), (bx, by) = a, b
        if ax == bx and ax == int(ax):
            return [("v", int(ax), y) for y in range(math.floor(min(ay, by)), math.ceil(max(ay, by)))]
        if ay == by and ay == int(ay):
            return [("h", x, int(ay)) for x in range(math.floor(min(ax, bx)), math.ceil(max(ax, bx)))]
        return None

    def mark(a, b):
        es = unit_edges(a, b)
        if es is not None:
            return es
        n = max(1, int(4 * max(abs(b[0] - a[0]), abs(b[1] - a[1]))))      # a slanted wall: the squares it crosses
        for i in range(n + 1):
            x, y = a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n
            if 0 <= x < cols and 0 <= y < rows:
                wall.add((int(x), int(y)))
        return []

    gp = lambda p: (round(float(p["x"]) - ox, 3), round(float(p["y"]) - oy, 3))
    for line in (u.get("line_of_sight") or []) + (u.get("objects_line_of_sight") or []):
        pts = [gp(p) for p in line if isinstance(p, dict)]
        for a, b in zip(pts, pts[1:]):
            blocked.update(mark(a, b))
    for d in u.get("portals") or []:
        b = d.get("bounds") or []
        if len(b) >= 2:
            portal.update(mark(gp(b[0]), gp(b[1])))
    shut = blocked | portal
    edge_open = lambda x, y: not ((x == 0 and ("v", 0, y) in shut) or (x == cols - 1 and ("v", cols, y) in shut)
                                  or (y == 0 and ("h", x, 0) in shut) or (y == rows - 1 and ("h", x, rows) in shut))
    rim = {(x, y) for x in range(cols) for y in range(rows) if x in (0, cols - 1) or y in (0, rows - 1)}
    seen, todo = set(), [c for c in rim if edge_open(*c)]
    while todo:                                                          # rock: reached from beyond the edge
        c = todo.pop()
        if c in seen:
            continue
        seen.add(c)
        x, y = c
        for e, n in ((("v", x, y), (x - 1, y)), (("v", x + 1, y), (x + 1, y)), (("h", x, y), (x, y - 1)), (("h", x, y + 1), (x, y + 1))):
            if 0 <= n[0] < cols and 0 <= n[1] < rows and e not in shut and n not in seen:
                todo.append(n)
    notes = ["Drafted from the file's thin walls: check every wall square against the picture and paint what is wrong."]
    if len(seen) > cols * rows / 2:
        notes.append("Most of the map is open to its edge (an outdoor map?): only the edge and the wall lines became wall squares.")
        seen = rim
    wall |= seen
    door = []
    for e in sorted(shut, key=lambda e: (e[2], e[1], e[0])):
        kind, x, y = e
        a, b = ((x - 1, y), (x, y)) if kind == "v" else ((x, y - 1), (x, y))
        inside = lambda c: 0 <= c[0] < cols and 0 <= c[1] < rows and c not in wall
        if not (inside(a) and inside(b)):
            continue
        if e in portal:
            door.append(b)
        else:
            wall.add(b)
    door = [d for d in door if d not in wall]
    return {"cols": cols, "rows": rows, "wall": sorted([list(c) for c in wall], key=lambda c: (c[1], c[0])),
            "door": [list(d) for d in door], "notes": notes}


def _scenario(name, cols, rows, walls, open_doors, lighting, background, party_at, creature, count, foes_at, lib, wall_cells,
              avoid=None):
    # avoid: squares nobody starts on that are not wall squares (REGION-01: trees, boulders and water)
    c = lib.get(creature)
    if not c:
        raise ImportError_("%s has no simulator stat block yet." % creature)
    if not (isinstance(count, int) and 1 <= count <= 12):
        raise ImportError_("Between 1 and 12 creatures.")
    for p, what in ((party_at, "party"), (foes_at, "creatures")):
        if not (0 <= p[0] < cols and 0 <= p[1] < rows):
            raise ImportError_("The %s' start square %s is off the map (%d x %d)." % (what, tuple(p), cols, rows))
    rock = set(map(tuple, wall_cells or [])) | set(map(tuple, avoid or ()))
    party = spots(tuple(party_at), len(PARTY), cols, rows, rock)
    foes = spaces(tuple(foes_at), count, cols, rows, rock | set(party), size_squares(c))
    if len(party) < len(PARTY) or len(foes) < count:
        raise ImportError_("Not enough room on the map for everyone.")
    combatants = [{"id": "id-%05d" % (i + 1), "name": n, "side": "friend", "pc": True, "hp": 10, "ac": 10, "init": 20 - i,
                   "x": x, "y": y} for i, (n, (x, y)) in enumerate(zip(PARTY, party))]
    foe_ids = []
    for i, (x, y) in enumerate(foes, 1):
        f = {k: copy.deepcopy(v) for k, v in c.items() if k in KEEP}
        f.update(id="id-%05d" % (20 + i), name="%s %d" % (creature, i), side="foe", x=x, y=y, init=c.get("init", 10))
        combatants.append(f)
        foe_ids.append(f["id"])
    sc = {"name": "%s (imported map)" % name, "map_name": str(name)[:80],
          "source": "SRD 5.2.1 (CC-BY-4.0) creatures; map imported by the GM (its licence is the GM's to respect).",
          "rounds": 8, "grid": 50, "units": 5, "diag": 1, "walls": walls, "open_doors": open_doors, "locked_doors": [],
          "lighting": lighting, "background": background, "aware": foe_ids, "combatants": combatants}
    if wall_cells is not None:
        sc["wall_cells"] = [list(c) for c in sorted(rock, key=lambda c: (c[1], c[0]))]
    return sc


def _from_cells(cells, cols, rows):
    if not isinstance(cells, dict):
        raise ImportError_("The squares are missing (wall, door).")
    wall, door = _cells(cells.get("wall"), cols, rows, "wall"), _cells(cells.get("door"), cols, rows, "door")
    problems = rule_problems(cols, rows, wall, door)
    if problems:
        raise ImportError_("The map breaks the map rule: " + " ".join(problems))
    return cell_walls(cols, rows, wall, door), wall


def convert_picture(image, grid, cells, name, party_at, creature, count, foes_at, lib, ambient="dark"):
    """A picture with no file: the GM's grid ({px, ox, oy: pixels; width, height: the picture's pixels}) and squares."""
    image, ext = picture(base64.b64encode(image).decode() if isinstance(image, bytes) else image)
    try:
        px, gx, gy, w, h = (float(grid[k]) for k in ("px", "ox", "oy", "width", "height"))
    except (KeyError, TypeError, ValueError):
        raise ImportError_("The grid is missing (square size and offset).")
    if not (8 <= px <= 2000 and 0 <= gx < px and 0 <= gy < px and 0 < w <= 40000 and 0 < h <= 40000):
        raise ImportError_("The grid does not fit the picture (squares of 8-2000 pixels, offset within one square).")
    cols, rows = int((w - gx) // px), int((h - gy) // px)
    if not (1 <= cols <= MAX_SQUARES and 1 <= rows <= MAX_SQUARES):
        raise ImportError_("The grid makes %s x %s squares; 1-%d each way." % (cols, rows, MAX_SQUARES))
    walls, wall = _from_cells(cells, cols, rows)
    bg = {"src": "maps/imported/%s.%s" % (slug(name), ext), "cols": cols, "rows": rows,
          "x": -gx / px, "y": -gy / px, "w": w / px, "h": h / px}
    lighting = {"ambient": "bright" if ambient == "bright" else "dark", "lights": []}
    return _scenario(name, cols, rows, walls, [], lighting, bg, party_at, creature, count, foes_at, lib, wall), image, ext


def convert(u, name, party_at, creature, count, foes_at, lib, cells=None):
    """Universal VTT (a dict) -> (scenario, picture bytes, extension). With the GM's squares (cells: {wall, door}) the
    walls follow them (MAP RULE); without, the file's own thin lines."""
    ox, oy, cols, rows = frame(u)
    image, ext = picture(u.get("image"))
    pt = lambda p: [round(float(p["x"]) - ox - 0.5, 3), round(float(p["y"]) - oy - 0.5, 3)]
    walls = []
    for line in (u.get("line_of_sight") or []) + (u.get("objects_line_of_sight") or []):
        pts = [pt(p) for p in line if isinstance(p, dict)]
        for a, b in zip(pts, pts[1:]):
            if a != b:
                walls.append({"id": "w%d" % len(walls), "points": [a, b]})
    open_doors = []
    for i, d in enumerate(u.get("portals") or []):
        b = d.get("bounds") or []
        if len(b) >= 2:
            walls.append({"id": "door %d" % (i + 1), "door": True, "points": [pt(b[0]), pt(b[1])]})
            if not d.get("closed", True):
                open_doors.append("door %d" % (i + 1))
    lights = []
    for i, l in enumerate(u.get("lights") or []):
        try:
            x, y = pt(l["position"])
            rng = float(l.get("range") or 0)
        except (KeyError, TypeError, ValueError):
            continue
        if rng > 0:
            lights.append({"x": x, "y": y, "dim_ft": int(round(rng * 5)), "bright_ft": int(round(rng * 5 / 2)), "label": "light %d" % (i + 1)})
    wall = None
    if cells is not None:
        walls, wall = _from_cells(cells, cols, rows)
        open_doors = []
    lighting = {"ambient": "dark" if dark(u.get("environment")) else "bright", "lights": lights}
    bg = {"src": "maps/imported/%s.%s" % (slug(name), ext), "cols": cols, "rows": rows}
    return _scenario(name, cols, rows, walls, open_doors, lighting, bg, party_at, creature, count, foes_at, lib, wall), image, ext


def write(sc, image, ext, scenarios_dir=ROOT / "sim" / "scenarios", table_dir=TABLE):
    s = Path(sc["background"]["src"]).stem
    (Path(scenarios_dir) / "imported").mkdir(parents=True, exist_ok=True)
    (Path(table_dir) / "maps" / "imported").mkdir(parents=True, exist_ok=True)
    (Path(scenarios_dir) / "imported" / (s + ".json")).write_text(json.dumps(sc, indent=1), encoding="utf-8")
    (Path(table_dir) / "maps" / "imported" / ("%s.%s" % (s, ext))).write_bytes(image)
    return "imported/%s.json" % s


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("file"); ap.add_argument("--name", required=True)
    ap.add_argument("--party", required=True, help="x,y"); ap.add_argument("--foes", required=True, help="x,y")
    ap.add_argument("--creature", default="Goblin Warrior"); ap.add_argument("--count", type=int, default=4)
    a = ap.parse_args(argv)
    sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "sim"), str(ROOT / "mythastria_core")]
    import creature_threat
    xy = lambda t: tuple(int(v) for v in t.split(","))
    try:
        sc, image, ext = convert(json.loads(Path(a.file).read_text(encoding="utf-8")), a.name, xy(a.party), a.creature,
                                 a.count, xy(a.foes), creature_threat.library())
    except (ImportError_, ValueError) as e:
        print("Not imported: %s" % e); return 1
    print("Imported as %s" % write(sc, image, ext))
    return 0


if __name__ == "__main__":
    sys.exit(main())
