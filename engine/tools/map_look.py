"""MAP-LOOK-01 (2026-10-15): a local vision model looks at a Seven Isles map picture and answers questions the map's
own source can answer; disagreements are flagged for a human look. Development tool (Ollama on this PC; nothing leaves it).

  py tools\\map_look.py ward_chamber village_harbor ...      # map script names under AI_Adventures/seven_isles/maps
  py tools\\map_look.py --all [--model qwen3.5:9b-q4_K_M]

The picture is the builder's PNG (out/<island>/<base>.png), not FG's screen: FG's own rendering needs a screenshot.
Counts asked: doors drawn on walls, square solid blocks (pillars, crates, rubble), glowing light markers, separate rooms.
A small model miscounts sometimes; a mismatch is a prompt to look, not a verdict. Doors and lights must match exactly,
blocks within one; the room count is only reported (rooms joined without walls are ambiguous).
"""
import os
import argparse, base64, json, sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
MASTER = Path(os.environ.get("MYTHASTRIA_FG_DIR") or Path(os.environ.get("APPDATA", "")) / "SmiteWorks" / "Fantasy Grounds") / "AI_Adventures" / "seven_isles"
sys.path.insert(0, str(MASTER / "tools"))
OLLAMA = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3.5:9b-q4_K_M"

PROMPT = ("This is a top-down tactical battle map on a square grid, drawn plainly: floor areas in light colours, thick "
          "dark lines are walls, the dark area around the rooms is impassable. Count carefully and answer in JSON only.\n"
          "- doors: short coloured bars (orange-brown or blue) set into a wall line\n"
          "- blocks: square solid blocks standing on the floor (grey pillars, brown crates, heaps of rubble)\n"
          "- lights: small glowing round markers (blue rings, orange or yellow flames); ignore large circular floor patterns\n"
          "- rooms: separate floor areas joined by gaps or doors\n"
          "- description: one sentence on the overall layout")
SCHEMA = {"type": "object", "properties": {
    "doors": {"type": "integer"}, "blocks": {"type": "integer"}, "lights": {"type": "integer"},
    "rooms": {"type": "integer"}, "description": {"type": "string"}},
    "required": ["doors", "blocks", "lights", "rooms", "description"]}


def find_maps():
    return {p.stem: p for p in sorted((MASTER / "maps").glob("*/*.py"))}


def load_spec(path):
    import importlib.util
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod.spec(), path.parent.name


def expected(m):
    # glyph decor is drawn as a ring marker too, so it counts as a light marker; daylight lights draw nothing
    drawn_lights = sum(1 for l in m.lights if l.get("kind", "torch") != "daylight")
    glyphs = sum(1 for d in m.decor if d["kind"] in ("glyph", "post"))
    return {"doors": len(m.doors), "blocks": len(m.solid), "lights": drawn_lights + glyphs, "rooms": len(m.rooms)}


def ask(model, png, timeout=300):
    body = json.dumps({"model": model, "stream": False, "format": SCHEMA, "options": {"temperature": 0},
                       "messages": [{"role": "user", "content": PROMPT,
                                     "images": [base64.b64encode(png.read_bytes()).decode()]}]}).encode()
    with urlopen(Request(OLLAMA + "/api/chat", data=body, headers={"Content-Type": "application/json"}), timeout=timeout) as r:
        return json.loads(json.loads(r.read())["message"]["content"])


def check(name, path, model):
    m, island = load_spec(path)
    png = MASTER / "out" / island / (m.base + ".png")
    if not png.exists():
        return {"map": name, "error": "no picture (build the map first): %s" % png}
    got, want = ask(model, png), expected(m)
    # strict where the picture is unambiguous; blocks may be off by one (a glowing block reads as a light); rooms that
    # run into each other without walls (a quay and its plaza) are a matter of opinion: reported, never flagged
    tol = {"doors": 0, "lights": 0, "blocks": 1}
    diffs = {k: (want[k], got.get(k)) for k in tol
             if not isinstance(got.get(k), int) or abs(got.get(k) - want[k]) > tol[k]}
    return {"map": name, "expected": want, "seen": {k: got.get(k) for k in want}, "mismatches": diffs,
            "description": got.get("description", "")}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("maps", nargs="*"); ap.add_argument("--all", action="store_true")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    a = ap.parse_args(argv)
    maps = find_maps()
    names = list(maps) if a.all else a.maps
    if not names:
        ap.error("name one or more maps (%s) or use --all" % ", ".join(maps))
    for n in names:
        if n not in maps:
            print("%s: unknown map" % n); continue
        r = check(n, maps[n], a.model)
        if "error" in r:
            print("%s: %s" % (n, r["error"])); continue
        flag = "OK" if not r["mismatches"] else "LOOK: " + ", ".join(
            "%s expected %s, seen %s" % (k, w, s) for k, (w, s) in r["mismatches"].items())
        print("%s: %s (rooms: %s in the source, %s seen)\n    %s" % (n, flag, r["expected"]["rooms"], r["seen"]["rooms"],
                                                                  r["description"]))


if __name__ == "__main__":
    main()
