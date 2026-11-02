"""v0.7.73 WALLS-01a: import a map's exported walls and confirm how they line up with FG's tokens.

  (in PowerShell, first: cd to the engine folder)
  1. py calibrate_map_walls.py import "Map - My Map.xml" --map "My Map"
  2. In FG: open that map, tokens placed, bridge running; type /aibridge syncspatial and wait for it to finish.
     py calibrate_map_walls.py check --map "My Map"
     -> writes and opens a local page with one drawing per candidate alignment.
  3. py calibrate_map_walls.py confirm --map "My Map" --option center_down   (the option that matches FG)

Everything stays on this PC (mythastria_core/cache/walls). Reads the bridge's /spatial.json, /combat.json and
/maps.json only; changes nothing in FG or the bridge."""
import argparse, json, sys, webbrowser
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "mythastria_core"))
import map_walls  # noqa: E402

BRIDGE = "http://127.0.0.1:8766"


def get(path):
    with urlopen(Request(BRIDGE + path, headers={"Host": "127.0.0.1:8766"}), timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def live_tokens(map_name):
    """Tokens on the named (or the only open) map, with the map's image size, grid and offset from FG."""
    spatial, combat = get("/spatial.json"), get("/combat.json")
    try:
        names = {p: r.get("name", "") for p, r in get("/maps.json").get("records", {}).items()}
    except Exception:
        names = {}
    rows = [r for r in spatial.get("tokens", {}).values() if num(r.get("x")) is not None and num(r.get("y")) is not None]
    named = [r for r in rows if names.get(r.get("image_record"), "").strip().lower() == map_name.strip().lower()]
    if not named:
        # field result 18:36: the map catalog was not synced and FG reported map_open 0; all tokens on one map is enough
        records = {r.get("image_record") for r in rows if r.get("image_record")}
        if len(records) != 1:
            opened = {r.get("image_record") for r in rows if r.get("map_open") == "1"}
            if len(opened) != 1:
                raise SystemExit("Tokens are on %d maps: keep only the %r encounter's tokens placed (or open only that map), "
                                 "then /aibridge syncspatial." % (len(records), map_name))
            records = opened
        named = [r for r in rows if r.get("image_record") in records]
    sizes = [(num(r.get("image_width")), num(r.get("image_height"))) for r in named if num(r.get("image_width"))]
    actors = combat.get("actors", {})
    tokens = [{"name": r.get("name", "?"), "x": num(r["x"]), "y": num(r["y"]),
               "side": "foe" if (actors.get(r.get("ctpath"), {}).get("friend_foe") == "foe") else "friend"} for r in named]
    r0 = named[0]
    grid = (num(r0.get("grid_width")) or num(r0.get("grid_size")), num(r0.get("grid_height")) or num(r0.get("grid_size")))
    offset = (num(r0.get("grid_offset_x")) or 0.0, num(r0.get("grid_offset_y")) or 0.0)
    return tokens, (sizes[0] if sizes else None), grid, offset, named[0].get("container_node")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("import"); a.add_argument("xml"); a.add_argument("--map", required=True)
    c = sub.add_parser("check"); c.add_argument("--map", required=True); c.add_argument("--no-open", action="store_true")
    f = sub.add_parser("confirm"); f.add_argument("--map", required=True); f.add_argument("--option", required=True, choices=map_walls.TRANSFORMS)
    li = sub.add_parser("lights", help="v0.7.84: use the map's own lights (from the export) and set the ambient light")
    li.add_argument("xml"); li.add_argument("--map", required=True)
    li.add_argument("--ambient", default="dark", choices=("dark", "dim", "bright"))
    li.add_argument("--units", type=float, default=5.0, help="feet per grid square (default 5)")
    li.add_argument("--torch", action="append", default=[], help="CT id or path of a creature carrying a lit Torch")
    li.add_argument("--off", action="store_true", help="switch lighting off for this map (everything in Bright Light)")
    args = ap.parse_args(argv)

    if args.cmd == "lights":
        if args.off:
            data = map_walls.load(args.map)
            if not data:
                raise SystemExit("No walls imported for %r yet." % args.map)
            data.pop("lighting", None)
            (map_walls.walls_dir() / (map_walls._key(args.map) + ".json")).write_text(json.dumps(data, indent=1), encoding="utf-8")
            print("Lighting off for %r: everything counts as Bright Light again." % args.map); return 0
        lights = map_walls.parse_export(args.xml)["lights"]
        try:
            block = map_walls.set_lighting(args.map, args.ambient, lights, args.units, args.torch)
        except ValueError as e:
            raise SystemExit(str(e))
        sizes = {}
        for l in block["lights"]:
            if "pos" in l:
                k = "%g/%g ft" % (l["bright_ft"], l["dim_ft"]); sizes[k] = sizes.get(k, 0) + 1
        print("Lighting on for %r: ambient %s, %d map lights (%s)%s. Bridge restart not needed (read on each turn)." % (
            args.map, args.ambient, sum(1 for l in block["lights"] if "pos" in l),
            ", ".join("%d x Bright/Dim %s" % (n, k) for k, n in sorted(sizes.items())),
            (", Torch carried by " + ", ".join(args.torch)) if args.torch else ""))
        return 0

    if args.cmd == "import":
        walls = map_walls.parse_export(args.xml)
        p = map_walls.save(args.map, walls, source=args.xml)
        doors = sum(o["door"] for o in walls["occluders"])
        print("Imported %d walls/doors (%d doors, %d hidden, %d skipped) and %d lights for %r. Saved locally: %s" % (
            len(walls["occluders"]), doors, sum(o["hidden"] for o in walls["occluders"]), walls["skipped"],
            len(walls["lights"]), args.map, p.relative_to(ROOT)))
        print("Not used yet: run the 'check' step to confirm the alignment.")
        return 0

    data = map_walls.load(args.map)
    if not data:
        raise SystemExit("No walls imported for %r yet: run the import step first." % args.map)
    tokens, size, grid, offset, fg_map = live_tokens(args.map)

    if args.cmd == "check":
        page = map_walls.walls_dir() / (map_walls._key(args.map) + "_calibration.html")
        page.write_text(map_walls.calibration_html(args.map, data, tokens, size, grid, offset), encoding="utf-8")
        print("FG: image %s, grid %s x %s, offset %s, %d token(s): %s" % (
            "%g x %g" % size if size else "size not reported", grid[0], grid[1], offset, len(tokens),
            ", ".join(t["name"] for t in tokens)))
        if data.get("gridsize") and grid[0] and abs(data["gridsize"][0] - grid[0]) > 0.5:
            print("Note: the export's grid (%s) differs from FG's current grid; walls are image pixels, so this is fine "
                  "as long as the map image itself did not change." % data["gridsize"])
        print("Calibration page: %s" % page.relative_to(ROOT))
        print("Then, in PowerShell:")
        print('  cd to the engine folder')
        print('  py calibrate_map_walls.py confirm --map "%s" --option <%s>' % (args.map, "|".join(map_walls.candidates(size))))
        if not args.no_open:
            webbrowser.open(page.resolve().as_uri())
        return 0

    confirmed = map_walls.confirm(args.map, args.option, size, fg_map)
    print("Confirmed %r: alignment %s, FG map %s. The bridge uses these walls from v0.7.73 on." % (
        args.map, confirmed["transform"], confirmed.get("fg_map")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
