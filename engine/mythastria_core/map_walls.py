"""v0.7.73 WALLS-01a: walls from a map's FG "Export Image to File" XML.

The GM exports a map once (PNG + matching XML with occluders and lights); FG gives scripts no live wall getter, and
the user decided a one-time export per map is enough. This module reads the XML into a local wall cache
(mythastria_core/cache/walls, never in git, snapshots or reviews: it is module geometry) and draws a calibration page.

The export's coordinates are centred (observed range about -1130..1207 on a 2048-wide map), FG's token positions are
not proven to share that frame. Nothing uses the walls until the GM confirms one alignment on the calibration page:
- center_down: token = export + half the image size (y grows downwards in both)
- center_up:   token x = export x + half width, token y = half height - export y
- identity:    the same frame
- flip_y:      the same origin, y pointing the other way
Field result 2026-10-12 18:36: FG's token positions are centred too (x from -77 to +56 on the Halls map) and FG gave no
image size for that map window, so identity and flip_y are the likely candidates and need no image size.
Flags (closed, toggleable, single_sided, counterclockwise, hidden) are empty elements: presence means set.
Toggleable occluders are doors; their open/closed state is not in the export (treated by later steps)."""
import html as _html
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

TRANSFORMS = ("center_down", "center_up", "identity", "flip_y")
SIZE_FREE = ("identity", "flip_y")


def candidates(image_size):
    """Alignments to offer: all of them when FG reported the image size, else only the size-free ones."""
    return list(TRANSFORMS) if image_size else ["identity", "flip_y"]
FLAGS = ("closed", "toggleable", "single_sided", "counterclockwise", "hidden")


def walls_dir():
    return Path(os.environ.get("MYTHASTRIA_WALLS_DIR") or Path(__file__).resolve().parent / "cache" / "walls")


def _pair(text):
    try:
        a, b = (float(v) for v in str(text or "").split(",")[:2])
        return [a, b]
    except ValueError:
        return None


def parse_export(path):
    """Export XML -> {"gridsize", "gridoffset", "occluders": [...], "lights": [...], "skipped"}."""
    root = ET.parse(str(path)).getroot()
    out = {"version": root.get("version"), "dataversion": root.get("dataversion"),
           "grid": (root.findtext("grid") or "").strip(), "gridsize": _pair(root.findtext("gridsize")),
           "gridoffset": _pair(root.findtext("gridoffset")), "occluders": [], "lights": [], "skipped": 0}
    for o in root.iter("occluder"):
        try:
            nums = [float(v) for v in re.split(r"[,\s]+", (o.findtext("points") or "").strip()) if v]
        except ValueError:
            nums = []
        if len(nums) < 4 or len(nums) % 2:
            out["skipped"] += 1
            continue
        flags = {f: o.find(f) is not None for f in FLAGS}
        out["occluders"].append({"id": (o.findtext("id") or "").strip(), "points": [nums[i:i + 2] for i in range(0, len(nums), 2)],
                                 "closed": flags["closed"], "door": flags["toggleable"], "single_sided": flags["single_sided"],
                                 "counterclockwise": flags["counterclockwise"], "hidden": flags["hidden"]})
    for l in root.iter("light"):
        pos = _pair(l.findtext("position"))
        if pos:
            light = {"position": pos, "on": l.find("on") is not None}
            # v0.7.84: <range>bright,intensity,dim,intensity</range> in grid squares (FG's Torch preset is 4,0.75,8,0.5
            # = Bright 20 ft, Dim to 40 ft, the SRD Torch)
            rng = (l.findtext("range") or "").split(",")
            try:
                light["bright_sq"], light["dim_sq"] = float(rng[0]), float(rng[2])
            except (IndexError, ValueError):
                pass
            out["lights"].append(light)
    return out


def segments(occluder):
    pts = occluder["points"]
    segs = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    if occluder.get("closed") and len(pts) > 2:
        segs.append((pts[-1], pts[0]))
    return segs


def apply(transform, point, image_size):
    x, y = point
    if transform == "identity":
        return (x, y)
    if transform == "flip_y":
        return (x, -y)
    if not image_size:
        raise ValueError("this alignment needs the map's image size")
    w, h = image_size
    if transform == "center_down":
        return (x + w / 2.0, y + h / 2.0)
    if transform == "center_up":
        return (x + w / 2.0, h / 2.0 - y)
    raise ValueError("unknown transform")


def _key(map_name):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", map_name.strip())[:80] or "map"


def save(map_name, walls, source=""):
    d = walls_dir(); d.mkdir(parents=True, exist_ok=True)
    data = dict(walls, map=map_name, source=os.path.basename(source), imported=time.strftime("%Y-%m-%d %H:%M"),
                transform=None, image_size=None)
    p = d / (_key(map_name) + ".json")
    p.write_text(json.dumps(data, indent=1), encoding="utf-8")
    _by_map["stamp"] = None                     # writes can land within one mtime tick
    return p


def load(map_name):
    p = walls_dir() / (_key(map_name) + ".json")
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def confirm(map_name, transform, image_size, fg_map=None):
    if transform not in TRANSFORMS:
        raise ValueError("unknown transform")
    if transform not in SIZE_FREE and not image_size:
        raise ValueError("this alignment needs the map's image size")
    data = load(map_name)
    if not data:
        raise ValueError("no walls imported for this map")
    data.update(transform=transform, image_size=[float(image_size[0]), float(image_size[1])] if image_size else None,
                confirmed=time.strftime("%Y-%m-%d %H:%M"))
    if fg_map:
        data["fg_map"] = fg_map                 # v0.7.73: FG's token container path, as the turn notice reports it
    data.setdefault("open_doors", [])
    (walls_dir() / (_key(map_name) + ".json")).write_text(json.dumps(data, indent=1), encoding="utf-8")
    _by_map["stamp"] = None
    return data


def usable(map_name):
    """The map's walls only once the GM confirmed an alignment, else None."""
    data = load(map_name)
    if not data or data.get("transform") not in TRANSFORMS:
        return None
    return data if data["transform"] in SIZE_FREE or data.get("image_size") else None


# ------------------------------------------------------------------ v0.7.73 WALLS-01b: using confirmed walls
_by_map = {"stamp": None, "maps": {}}


def for_map(fg_map):
    """Confirmed walls for FG's map path (token container, e.g. image.id-00028.image@GPFG5ETCOO), or None."""
    if not fg_map:
        return None
    d = walls_dir()
    files = sorted(d.glob("*.json")) if d.exists() else []
    stamp = (str(d), tuple((f.name, f.stat().st_mtime_ns, f.stat().st_size) for f in files))
    if stamp != _by_map["stamp"]:
        maps = {}
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if data.get("fg_map") and usable(data.get("map", "")):
                maps[data["fg_map"]] = data
        _by_map.update(stamp=stamp, maps=maps)
    return _by_map["maps"].get(fg_map)


def set_door(map_name, door_id, is_open):
    """Mark one door open or closed (doors are closed unless the GM opens them)."""
    data = load(map_name)
    if not data or not any(o["door"] and o["id"] == str(door_id) for o in data["occluders"]):
        raise ValueError("no such door")
    opened = [i for i in data.get("open_doors", []) if i != str(door_id)] + ([str(door_id)] if is_open else [])
    data["open_doors"] = opened
    (walls_dir() / (_key(map_name) + ".json")).write_text(json.dumps(data, indent=1), encoding="utf-8")
    _by_map["stamp"] = None
    return data


def placed(data, point):
    """An export point in FG's token frame: the confirmed alignment, then the GM's nudge (pixels, set_offset)."""
    x, y = apply(data["transform"], point, data.get("image_size"))
    dx, dy = data.get("offset") or (0.0, 0.0)
    return (x + dx, y + dy)


def set_offset(map_name, dx, dy):
    """v0.7.73: shift a confirmed map's walls by (dx, dy) pixels in FG's token frame (e.g. one square = grid width)."""
    data = load(map_name)
    if not data or data.get("transform") not in TRANSFORMS:
        raise ValueError("confirm the map's alignment first")
    data["offset"] = [float(dx), float(dy)]
    (walls_dir() / (_key(map_name) + ".json")).write_text(json.dumps(data, indent=1), encoding="utf-8")
    _by_map["stamp"] = None
    return data


def blocking_segments(data):
    """Wall segments in FG's token frame that block sight and movement: walls (hidden ones too, e.g. secret walls)
    and doors the GM has not marked open."""
    if not data:
        return []
    opened = set(data.get("open_doors") or [])
    size = data.get("image_size")
    out = []
    for o in data["occluders"]:
        if o["door"] and o["id"] in opened:
            continue
        for a, b in segments(o):
            out.append((placed(data, a), placed(data, b)))
    return out


def closed_door_segments(data):
    """v0.7.93 HEAR-01: the closed doors alone (beyond 60 ft a closed door stops the sound of a fight)."""
    if not data:
        return []
    opened = set(data.get("open_doors") or [])
    return [(placed(data, a), placed(data, b)) for o in data["occluders"] if o["door"] and o["id"] not in opened
            for a, b in segments(o)]


def closed_doors(data):
    """v0.7.95 DOORS-01: the doors still closed, each {"id", "name", "seg" (token frame), "locked"}. A map built for an
    adventure names its doors and lists the locked ones (set_door_info); FG's own ids are numbers."""
    if not data:
        return []
    opened, locked = set(data.get("open_doors") or []), set(str(i) for i in data.get("locked_doors") or [])
    names = data.get("door_names") or {}
    return [{"id": str(o["id"]), "name": names.get(str(o["id"]), ""), "seg": (placed(data, a), placed(data, b)),
             "locked": str(o["id"]) in locked}
            for o in data["occluders"] if o["door"] and o["id"] not in opened for a, b in segments(o)]


def set_door_info(map_name, names, locked=()):
    """v0.7.95: door names ({id: name}) and the locked door ids of a confirmed map (an adventure's builder sets them)."""
    data = load(map_name)
    if not data:
        raise ValueError("no walls imported for that map")
    data["door_names"] = {str(k): str(v) for k, v in names.items()}
    data["locked_doors"] = [str(i) for i in locked]
    (walls_dir() / (_key(map_name) + ".json")).write_text(json.dumps(data, indent=1), encoding="utf-8")
    _by_map["stamp"] = None
    return data


def set_lighting(map_name, ambient, lights, units=5.0, torches=()):
    """v0.7.84: switch lighting on for a confirmed map: the ambient level plus the export's lights (position in the
    export frame, radii in squares -> feet) and optional carried Torches (CT paths). Returns the saved block."""
    if ambient not in ("bright", "dim", "dark"):
        raise ValueError("ambient must be bright, dim or dark")
    data = load(map_name)
    if not data:
        raise ValueError("no walls imported for that map")
    block = {"ambient": ambient, "lights": [
        {"pos": list(l["position"]), "bright_ft": l["bright_sq"] * units, "dim_ft": l["dim_sq"] * units, "on": l.get("on", True)}
        for l in lights if "bright_sq" in l and "dim_sq" in l]}
    block["lights"] += [{"carrier": str(t), "bright_ft": 20.0, "dim_ft": 40.0} for t in torches]   # SRD 5.2.1 Torch
    data["lighting"] = block
    p = walls_dir() / (_key(map_name) + ".json")
    p.write_text(json.dumps(data, indent=1), encoding="utf-8")
    _by_map["stamp"] = None
    return block


def set_water(map_name, rects):
    """SWIM-01 (2026-10-19): the map's water areas, rectangles [x1, y1, x2, y2] in the export frame (any two opposite
    corners); an NPC in them moves at its Swim Speed. A map's builder sets them (Seven Isles tools/fgmap.py zones)."""
    data = load(map_name)
    if not data:
        raise ValueError("no walls imported for that map")
    out = []
    for r in rects:
        if len(r) != 4:
            raise ValueError("a water area needs two corners: x1, y1, x2, y2")
        out.append([float(v) for v in r])
    data["water"] = out
    (walls_dir() / (_key(map_name) + ".json")).write_text(json.dumps(data, indent=1), encoding="utf-8")
    _by_map["stamp"] = None
    return out


def water(data):
    """SWIM-01: the map's water areas in FG's token frame, each (x1, y1, x2, y2) with x1 < x2 and y1 < y2, or None."""
    rects = (data or {}).get("water")
    if not rects:
        return None
    out = []
    for x1, y1, x2, y2 in rects:
        (ax, ay), (bx, by) = placed(data, (x1, y1)), placed(data, (x2, y2))
        out.append((min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)))
    return out


def lighting(data):
    """v0.7.81 LIGHT-01: the map's lighting in FG's token frame, or None (everything in Bright Light).
    data["lighting"] = {"ambient": "bright" | "dim" | "dark", "lights": [{"pos": [x, y] (export frame) or
    "carrier": CT path, "bright_ft", "dim_ft"}]}. The GM sets it; FG's own light radii are not read yet."""
    lit = (data or {}).get("lighting")
    if not lit:
        return None
    lights = []
    for l in lit.get("lights") or []:
        if l.get("on") is False:
            continue
        item = {"bright_ft": float(l.get("bright_ft") or 0), "dim_ft": float(l.get("dim_ft") or 0)}
        if l.get("dir") is not None:
            item["dir"] = float(l["dir"])                        # LIGHTS-01: a Bullseye Lantern's Cone
        if l.get("carrier"):
            item["carrier"] = str(l["carrier"])
        elif l.get("pos"):
            item["pos"] = placed(data, l["pos"])
        else:
            continue
        lights.append(item)
    return {"ambient": str(lit.get("ambient") or "bright"), "lights": lights}


def doors_svg(data, tokens):
    """v0.7.73 WALLS-01c: the confirmed walls in FG's token frame with the combat's tokens, for the bridge page. Doors
    are drawn dashed (amber closed, green open) with a wide clickable band carrying data-door / data-open.
    tokens: [(name, x, y, is_foe)]."""
    opened = set(data.get("open_doors") or [])
    size = data.get("image_size")
    walls, doors, pts = [], [], []
    for o in data["occluders"]:
        for a, b in segments(o):
            a, b = placed(data, a), placed(data, b)
            pts += [a, b]
            (doors if o["door"] else walls).append((o, a, b))
    pts += [(x, y) for _, x, y, _ in tokens]
    if not pts:
        return ""
    x0, y0 = min(p[0] for p in pts) - 40, min(p[1] for p in pts) - 40
    w, h = max(p[0] for p in pts) + 40 - x0, max(p[1] for p in pts) + 40 - y0
    sw = max(w, h) / 300                                   # stroke width that reads at page size
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="%.1f %.1f %.1f %.1f" style="width:100%%;max-height:520px;'
           'background:#f8fafc;border:1px solid #cbd5e1">' % (x0, y0, w, h)]
    for o, a, b in walls:
        out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="%.1f"/>'
                   % (a[0], a[1], b[0], b[1], "#64748b" if o["hidden"] else "#111", sw))
    for o, a, b in doors:
        is_open = o["id"] in opened
        out.append('<g class=wall-door data-door="%s" data-open="%d" style="cursor:pointer"><title>Door %s: %s. Click to %s.</title>'
                   '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="%.1f" stroke-dasharray="%.1f %.1f"/>'
                   '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="transparent" stroke-width="%.1f"/></g>'
                   % (_html.escape(o["id"], quote=True), is_open, _html.escape(o["id"]), "open" if is_open else "closed",
                      "close it" if is_open else "open it", a[0], a[1], b[0], b[1], "#16a34a" if is_open else "#d97706",
                      sw * 1.6, sw * 3, sw * 2, a[0], a[1], b[0], b[1], sw * 8))
    for name, x, y, foe in tokens:
        out.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s"><title>%s</title></circle>'
                   '<text x="%.1f" y="%.1f" font-size="%.1f" fill="#0f172a">%s</text>'
                   % (x, y, sw * 4, "#dc2626" if foe else "#2563eb", _html.escape(name), x + sw * 5, y + sw * 2, sw * 9,
                      _html.escape(name)))
    out.append("</svg>")
    return "".join(out)


def _orient(a, b, c):
    v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return 0 if abs(v) < 1e-9 else (1 if v > 0 else -1)


def _on(a, b, c):
    return min(a[0], b[0]) - 1e-9 <= c[0] <= max(a[0], b[0]) + 1e-9 and min(a[1], b[1]) - 1e-9 <= c[1] <= max(a[1], b[1]) + 1e-9


def crosses(p, q, a, b):
    """Does segment p-q cross wall a-b? Touching a wall's end exactly counts (conservative at corners)."""
    o1, o2, o3, o4 = _orient(p, q, a), _orient(p, q, b), _orient(a, b, p), _orient(a, b, q)
    if o1 != o2 and o3 != o4:
        return True
    return (o1 == 0 and _on(p, q, a)) or (o2 == 0 and _on(p, q, b)) or (o3 == 0 and _on(a, b, p)) or (o4 == 0 and _on(a, b, q))


def near(p, segs, dist):
    """v0.7.79: is a wall or closed door within `dist` of point p (a square's centre)? Used to keep NPCs out of squares
    a wall cuts through (field: a Gobliez ended its move with a wall across its square)."""
    for a, b in segs:
        if min(a[0], b[0]) - dist > p[0] or max(a[0], b[0]) + dist < p[0] or                 min(a[1], b[1]) - dist > p[1] or max(a[1], b[1]) + dist < p[1]:
            continue
        dx, dy = b[0] - a[0], b[1] - a[1]
        length2 = dx * dx + dy * dy
        t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2))
        if (p[0] - a[0] - t * dx) ** 2 + (p[1] - a[1] - t * dy) ** 2 < dist * dist:
            return True
    return False


def blocked(p, q, segs):
    """Is the straight line p-q blocked by any wall segment? (sight/attack lines and single movement steps)"""
    minx, maxx, miny, maxy = min(p[0], q[0]), max(p[0], q[0]), min(p[1], q[1]), max(p[1], q[1])
    for a, b in segs:
        if max(a[0], b[0]) < minx or min(a[0], b[0]) > maxx or max(a[1], b[1]) < miny or min(a[1], b[1]) > maxy:
            continue
        if crosses(p, q, a, b):
            return True
    return False


def calibration_html(map_name, walls, tokens, image_size, grid=None, offset=None):
    """A local page with one drawing per candidate alignment: walls (doors dashed), FG's token positions and grid."""
    esc = _html.escape
    panels = []
    for t in candidates(image_size):
        pts = [apply(t, p, image_size) for o in walls["occluders"] for p in o["points"]] + [(k["x"], k["y"]) for k in tokens]
        if image_size:
            x0, y0, x1b, y1b = 0.0, 0.0, float(image_size[0]), float(image_size[1])
        else:   # no image size from FG: fit the drawing to the walls and tokens
            x0, y0 = min(p[0] for p in pts) - 60, min(p[1] for p in pts) - 60
            x1b, y1b = max(p[0] for p in pts) + 60, max(p[1] for p in pts) + 60
        w, h = x1b - x0, y1b - y0
        lines = []
        for o in walls["occluders"]:
            for a, b in segments(o):
                (x1, y1), (x2, y2) = apply(t, a, image_size), apply(t, b, image_size)
                style = 'stroke="#b45309" stroke-dasharray="12 8"' if o["door"] else ('stroke="#64748b"' if o["hidden"] else 'stroke="#111"')
                lines.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" %s stroke-width="6"/>' % (x1, y1, x2, y2, style))
        grid_lines = []
        if grid and grid[0] > 4 and grid[1] > 4:
            ox, oy = (offset or (0, 0))
            x = x0 + ((ox - x0) % grid[0])
            while x < x1b:
                grid_lines.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#cbd5e1" stroke-width="1"/>' % (x, y0, x, y1b)); x += grid[0]
            y = y0 + ((oy - y0) % grid[1])
            while y < y1b:
                grid_lines.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#cbd5e1" stroke-width="1"/>' % (x0, y, x1b, y)); y += grid[1]
        marks = []
        for tok in tokens:
            color = "#dc2626" if tok.get("side") == "foe" else "#2563eb"
            marks.append('<circle cx="%.1f" cy="%.1f" r="16" fill="%s"/><text x="%.1f" y="%.1f" font-size="34" fill="%s">%s</text>'
                         % (tok["x"], tok["y"], color, tok["x"] + 20, tok["y"] - 20, color, esc(tok["name"])))
        frame = ('<rect x="0" y="0" width="%.0f" height="%.0f" fill="none" stroke="#16a34a" stroke-width="4"/>' % (w, h)
                 if image_size else "")
        panels.append('<figure data-transform="%s"><figcaption><b>Option %s</b></figcaption>'
                      '<svg viewBox="%.0f %.0f %.0f %.0f" xmlns="http://www.w3.org/2000/svg" style="width:100%%;background:#fff;border:1px solid #999">'
                      '%s%s%s%s</svg></figure>'
                      % (t, t, x0, y0, w, h, frame, "".join(grid_lines), "".join(lines), "".join(marks)))
    return ("<!doctype html><meta charset=utf-8><title>Wall alignment: %s</title>"
            "<body style='font-family:sans-serif;margin:16px;background:#f8fafc'>"
            "<h1>Wall alignment for %s</h1><p>Each drawing places the exported walls (black; doors dashed orange; hidden grey) "
            "differently over FG's current token positions (red foes, blue friends) and grid. Pick the one where every token "
            "stands where it does in FG (in the right room, not inside a wall), then run the confirm command printed in the "
            "console with that option's name. Stays on this PC.</p>"
            "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px'>%s</div></body>"
            % (esc(map_name), esc(map_name), "".join(panels)))
