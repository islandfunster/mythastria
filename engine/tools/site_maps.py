"""MAPGEN-02 (GM 2026-10-26: goal 19, "Indoor maps and dungeons from your preferences", "in LM Studio"): the sites on a
made region (dungeons, caves, ruins, lairs) drawn as indoor battle maps from the GM's design preferences.

The model designs, the code builds and checks:
  - the local model (LM Studio, OpenAI-compatible, on this PC only) proposes the site as JSON (DESIGN_SCHEMA): rooms with
    their purpose, size, shape, features and a short description, on one or more levels, joined by doors, archways and
    stairs; it works from the GM's preferences and the site's place on the region map (its terrain, a river, the coast);
  - check_design() keeps what is usable and says what it changed (a room with no way in gets a passage, and so on);
    nothing usable (no reply, not JSON, fewer than two rooms) is an error the GM sees: never a scripted map instead;
  - build() lays each level out on a grid (seeded: the same design and number give the same map): every square is floor
    or wall, walls at least one 5-ft square thick (MAP RULE), corridors one square or wider, doors in walls, stone
    fading past the outer walls (the pages draw wall_cells so); check_map() proves it before anything is written.

  py tools/site_maps.py --kind cave --theme "a flooded smugglers' cave" [--size normal --levels 1 --seed 7]
    [--llm-url http://127.0.0.1:1234/v1 --model google/gemma-4-12b-qat] [--design design.json]

Content policy (GM): only Mythastria's own words and SRD 5.2.1 go to the model; it is told to invent original names.
"""
import argparse, heapq, json, random, re, sys, time
from collections import deque
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools")]
import map_import  # noqa: E402

OUT = ROOT / "sim" / "scenarios" / "sites"
LLM_URL, MODEL = "http://127.0.0.1:1234/v1", "google/gemma-4-12b-qat"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

KINDS = ("dungeon", "cave", "ruin", "lair")
SIZES = {"small": (4, 6), "normal": (7, 10), "large": (11, 15)}      # rooms over all levels
LAYOUTS = ("linear", "branching", "looping")
WALLS = ("cut stone", "natural cave", "mixed")
DOORS = ("few", "some", "many")
PURPOSES = ("entrance", "guardroom", "hall", "barracks", "living quarters", "kitchen", "storage", "workshop", "shrine",
            "crypt", "prison", "library", "treasury", "throne room", "lair", "cavern", "pool", "collapsed", "empty")
ROOM_SIZES = {"small": (3, 4), "medium": (5, 7), "large": (8, 10)}   # interior squares each way
LINKS = ("door", "locked door", "archway", "stairs")
# the props the pages draw (isles-table props3d.mjs), the indoor ones; "pool" is a water zone, not a prop
FEATURES = ("table", "bench", "chair", "bed", "shelf", "desk", "lectern", "barrel", "crate", "sacks", "cauldron", "hearth",
            "rug", "lantern", "well", "chest", "statue", "altar", "brazier", "anvil", "weapon_rack", "sarcophagus", "bones",
            "throne", "stalagmite", "crystal", "boulder", "rock", "mushrooms", "moss", "roots", "broken_column",
            "stone_bench", "stone_table", "obelisk", "bell", "pool")
BY_WALL = {"shelf", "bed", "barrel", "crate", "sacks", "weapon_rack", "hearth", "bench", "stone_bench", "anvil", "desk",
           "stalagmite", "moss", "roots", "bones", "lectern"}
# SRD 5.2.1 light: a Torch sheds Bright Light 20 ft and Dim Light 20 ft more; a Hooded Lantern 30 ft and 30 ft more
LIGHTS = {"brazier": (20, 40, "a brazier (as a Torch: Bright 20 ft, Dim 20 ft more)"),
          "hearth": (20, 40, "a hearth fire (as a Torch: Bright 20 ft, Dim 20 ft more)"),
          "lantern": (30, 60, "a lantern (as a Hooded Lantern: Bright 30 ft, Dim 30 ft more)")}
MAX_SIDE = 160                                                         # squares each way (map_import.MAX_SQUARES is 200)
MARGIN = 3                                                             # rock round the outermost rooms' interiors


class SiteMapError(ValueError):
    pass


# ------------------------------------------------------------------ what the GM asks for
DEFAULT_PREFS = {"kind": "dungeon", "size": "normal", "levels": 1, "layout": "branching", "walls": "cut stone",
                 "doors": "some", "theme": "", "seed": 1}


def check_prefs(prefs):
    p = dict(DEFAULT_PREFS, **{k: v for k, v in (prefs or {}).items() if v is not None})
    if set(p) - set(DEFAULT_PREFS):
        raise SiteMapError("Unknown preferences: %s." % ", ".join(sorted(set(p) - set(DEFAULT_PREFS))))
    if p["kind"] not in KINDS or p["size"] not in SIZES or p["layout"] not in LAYOUTS or p["walls"] not in WALLS \
            or p["doors"] not in DOORS:
        raise SiteMapError("Site: kind %s; size %s; layout %s; walls %s; doors %s." % (
            "/".join(KINDS), "/".join(SIZES), "/".join(LAYOUTS), "/".join(WALLS), "/".join(DOORS)))
    if not (isinstance(p["levels"], int) and not isinstance(p["levels"], bool) and 1 <= p["levels"] <= 3):
        raise SiteMapError("Levels: 1, 2 or 3.")
    if not (isinstance(p["seed"], int) and not isinstance(p["seed"], bool) and 1 <= p["seed"] <= 10 ** 9):
        raise SiteMapError("The map number is a whole number from 1.")
    if not isinstance(p["theme"], str) or len(p["theme"]) > 300:
        raise SiteMapError("The theme is up to 300 characters of your own words.")
    p["theme"] = " ".join(p["theme"].split())
    return p


def check_context(context):
    """The site's place on the region map (region-gen.mjs hexContext and the place): what the model is told about it."""
    c = dict(context or {})
    out = {"terrain": str(c.get("terrain") or "plains")[:20], "climate": str(c.get("climate") or "temperate")[:20],
           "river": bool(c.get("river")), "road": bool(c.get("road")), "sea": c.get("sea") if c.get("sea") in ("north", "east", "south", "west") else None,
           "region": str(c.get("region") or "")[:80], "place": str(c.get("place") or "")[:80],
           "note": str(c.get("note") or "")[:300], "town_miles": c.get("town_miles") if isinstance(c.get("town_miles"), (int, float)) else None}
    return out


# ------------------------------------------------------------------ the model's part: the design, as JSON
DESIGN_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "summary": {"type": "string"},
        "entrance": {"type": "string"},
        "lair": {"type": "string"},
        "rooms": {"type": "array", "minItems": 2, "maxItems": 20, "items": {
            "type": "object",
            "properties": {
                "id": {"type": "string"}, "name": {"type": "string"}, "level": {"type": "integer"},
                "purpose": {"type": "string", "enum": list(PURPOSES)},
                "size": {"type": "string", "enum": list(ROOM_SIZES)},
                "shape": {"type": "string", "enum": ["built", "natural"]},
                "description": {"type": "string"},
                "features": {"type": "array", "maxItems": 6, "items": {"type": "string", "enum": list(FEATURES)}}},
            "required": ["id", "name", "level", "purpose", "size", "shape", "description", "features"]}},
        "connections": {"type": "array", "maxItems": 40, "items": {
            "type": "object",
            "properties": {"from": {"type": "string"}, "to": {"type": "string"},
                           "kind": {"type": "string", "enum": list(LINKS)},
                           "length": {"type": "string", "enum": ["short", "long"]}},
            "required": ["from", "to", "kind", "length"]}}},
    "required": ["name", "summary", "entrance", "lair", "rooms", "connections"]}

SYSTEM = ("You design indoor adventure sites (dungeons, caves, ruins, lairs) for a fantasy tabletop game played on a "
          "5-foot square grid. Invent everything yourself: original names only, never places, people or monsters from "
          "published adventures, novels or settings. Answer with one JSON object that follows the schema, nothing else.")


def prompt(prefs, context):
    p, c = prefs, context
    lo, hi = SIZES[p["size"]]
    where = ["%s terrain" % c["terrain"], "a %s climate" % c["climate"]]
    if c["river"]:
        where.append("a river nearby")
    if c["road"]:
        where.append("a road nearby")
    if c["sea"]:
        where.append("the sea to the %s" % c["sea"])
    if c["town_miles"] is not None:
        where.append("the nearest settlement %s miles away" % round(c["town_miles"]))
    lines = [
        "Design a %s: %d to %d rooms in all, on %d level%s." % (p["kind"], lo, hi, p["levels"], "" if p["levels"] == 1 else "s"),
        "Where it is: %s%s." % (", ".join(where), " (region: %s)" % c["region"] if c["region"] else ""),
        "The game master's theme: %s." % (p["theme"] or "your choice, fitting the place"),
        "Layout: %s (%s)." % (p["layout"], {"linear": "rooms one after another, few side rooms",
                                             "branching": "a main way with side branches and dead ends",
                                             "looping": "at least one loop, so there is more than one way round"}[p["layout"]]),
        "Walls: %s (%s)." % (p["walls"], {"cut stone": "rooms are built, shape \"built\"",
                                          "natural cave": "rooms are natural caverns, shape \"natural\"",
                                          "mixed": "some built rooms and some natural caverns"}[p["walls"]]),
        "Doors: %s (%s)." % (p["doors"], {"few": "mostly archways", "some": "a mix of doors and archways",
                                          "many": "most links are doors, some locked"}[p["doors"]]),
        "Rules for the JSON:",
        "- Room ids are R1, R2, R3 and so on. Levels count down from 1 (the way in).",
        "- \"entrance\" is the id of the level-1 room the party comes in by; \"lair\" is the id of the room where the "
        "main inhabitants wait.",
        "- Every room is joined to the others by connections. A connection between rooms on different levels has kind "
        "\"stairs\"; on the same level it is \"door\", \"locked door\" or \"archway\". \"length\" is the corridor between "
        "them: short or long.",
        "- Each room: a name, its purpose, its size (small, medium, large), its shape, up to 6 different features from the list, "
        "and a description of one or two sentences that a game master reads aloud or uses (what is seen, heard, smelled).",
        "- \"summary\": two sentences on the site's story and who lives there now.",
    ]
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "\n".join(lines)}]


def check_local(url):
    host = (urlparse(url or "").hostname or "").lower()
    if host not in LOCAL_HOSTS:
        raise SiteMapError("Refused: %s is not on this PC. Only a local model server designs sites." % url)
    return url.rstrip("/")


def ask_model(prefs, context, llm_url=LLM_URL, model=MODEL, timeout=600, max_tokens=8192):
    """One request to the local model; returns (the design it sent, facts about the call). Raises SiteMapError, in plain
    words, when the server is not there or the reply is not a JSON object."""
    base = check_local(llm_url)
    payload = {"model": model, "messages": prompt(prefs, context), "temperature": 0.8, "seed": prefs["seed"],
               "max_tokens": max_tokens, "stream": False,
               "response_format": {"type": "json_schema", "json_schema": {"name": "site_design", "schema": DESIGN_SCHEMA, "strict": False}}}
    req = Request(base + "/chat/completions", data=json.dumps(payload).encode(), method="POST",
                  headers={"Content-Type": "application/json"})
    started = time.time()
    try:
        with urlopen(req, timeout=timeout) as r:
            resp = json.loads(r.read().decode())
    except HTTPError as e:
        raise SiteMapError("The local model server answered HTTP %s: %s" % (e.code, e.read().decode(errors="replace")[:200]))
    except (URLError, TimeoutError, OSError) as e:
        raise SiteMapError("The local model server is not answering at %s (is LM Studio running with %s loaded?): %s"
                           % (base, model, getattr(e, "reason", e)))
    except ValueError:
        raise SiteMapError("The local model server sent something that is not JSON.")
    choice = (resp.get("choices") or [{}])[0]
    usage = resp.get("usage") or {}
    facts = {"model": resp.get("model") or model, "seconds": round(time.time() - started, 1),
             "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
             "finish": choice.get("finish_reason")}
    content = (choice.get("message") or {}).get("content") or ""
    design = _json_object(content)
    if design is None:
        why = " (it ran out of room: %s tokens)" % max_tokens if choice.get("finish_reason") == "length" else ""
        raise SiteMapError("The model gave nothing usable: its reply was not a JSON design%s. Try again, or another map number." % why)
    return design, facts


def _json_object(text):
    text = re.sub(r"^\s*```(?:json)?|```\s*$", "", text.strip())
    for candidate in (text, text[text.find("{"):text.rfind("}") + 1] if "{" in text else ""):
        try:
            out = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(out, dict):
            return out
    return None


# ------------------------------------------------------------------ the design, checked
def _text(v, n):
    return " ".join(str(v or "").split())[:n]


def check_design(raw, prefs):
    """The model's JSON -> (a design the builder can lay out, what was changed, in words). Raises SiteMapError when
    nothing usable is left (no rooms, one room). Never invents rooms; it only joins the ones the model made."""
    if not isinstance(raw, dict):
        raise SiteMapError("The model gave nothing usable: no JSON object.")
    fixes, rooms, ids = [], [], set()
    levels = prefs["levels"]
    natural_default = prefs["walls"] == "natural cave"
    for i, r in enumerate(raw.get("rooms") or []):
        if not isinstance(r, dict):
            continue
        rid = _text(r.get("id"), 12) or "R%d" % (i + 1)
        if rid in ids:
            fixes.append("Two rooms were called %s; the second is now R%d." % (rid, 100 + i))
            rid = "R%d" % (100 + i)
        lv = r.get("level")
        if not (isinstance(lv, int) and not isinstance(lv, bool) and 1 <= lv <= levels):
            fixes.append("Room %s was on level %r; it is on level %d." % (rid, lv, min(levels, max(1, lv if isinstance(lv, int) else 1))))
            lv = min(levels, max(1, lv if isinstance(lv, int) and not isinstance(lv, bool) else 1))
        size = r.get("size") if r.get("size") in ROOM_SIZES else "medium"
        shape = r.get("shape") if r.get("shape") in ("built", "natural") else ("natural" if natural_default else "built")
        listed = [f for f in (r.get("features") or []) if f in FEATURES] if isinstance(r.get("features"), list) else []
        feats = [f for i, f in enumerate(listed) if listed[:i].count(f) < 2][:6]   # Gemma can repeat one kind six times
        if len(feats) < min(6, len(listed)):
            fixes.append("Room %s listed the same feature again and again; each is kept at most twice." % rid)
        if r.get("purpose") == "pool" and "pool" not in feats:
            feats = (feats + ["pool"])[-6:]
            fixes.append("Room %s is a pool: it has one." % rid)
        ids.add(rid)
        rooms.append({"id": rid, "name": _text(r.get("name"), 60) or "Room %s" % rid, "level": lv,
                      "purpose": r.get("purpose") if r.get("purpose") in PURPOSES else "empty", "size": size,
                      "shape": shape, "description": _text(r.get("description"), 400), "features": feats})
    if len(rooms) > 20:
        fixes.append("The model made %d rooms; the first 20 are kept." % len(rooms))
        rooms = rooms[:20]
        ids = {r["id"] for r in rooms}
    if len(rooms) < 2:
        raise SiteMapError("The model gave nothing usable: %s." % ("no rooms" if not rooms else "only one room"))
    by_id = {r["id"]: r for r in rooms}
    links, seen = [], set()
    for c in raw.get("connections") or []:
        if not isinstance(c, dict):
            continue
        a, b = _text(c.get("from"), 12), _text(c.get("to"), 12)
        if a not in by_id or b not in by_id or a == b:
            fixes.append("A connection %s - %s names no room of the design; it is left out." % (a or "?", b or "?"))
            continue
        pair = tuple(sorted((a, b)))
        if pair in seen:
            continue
        seen.add(pair)
        kind = c.get("kind") if c.get("kind") in LINKS else "archway"
        across = by_id[a]["level"] != by_id[b]["level"]
        if across and kind != "stairs":
            fixes.append("%s and %s are on different levels: they are joined by stairs." % (a, b))
            kind = "stairs"
        elif not across and kind == "stairs":
            fixes.append("%s and %s are on the same level: stairs became an archway." % (a, b))
            kind = "archway"
        links.append({"from": a, "to": b, "kind": kind, "length": c.get("length") if c.get("length") in ("short", "long") else "short"})
    used = {r["level"] for r in rooms}
    if used != set(range(1, max(used) + 1)):
        fixes.append("Levels %s had rooms; they are numbered 1 to %d." % (sorted(used), len(used)))
        renum = {lv: i + 1 for i, lv in enumerate(sorted(used))}
        for r in rooms:
            r["level"] = renum[r["level"]]
    nlev = max(r["level"] for r in rooms)
    entrance = _text(raw.get("entrance"), 12)
    if entrance not in by_id or by_id[entrance]["level"] != 1:
        entrance = next((r["id"] for r in rooms if r["level"] == 1 and r["purpose"] == "entrance"), None) \
            or next(r["id"] for r in rooms if r["level"] == 1)
        fixes.append("The way in is %s (%s)." % (entrance, by_id[entrance]["name"]))
    lair = _text(raw.get("lair"), 12)
    if lair not in by_id:
        lair = None
    # every room reachable: a level's rooms joined among themselves, each level below reached by stairs from above
    for lv in range(1, nlev + 1):
        here = [r["id"] for r in rooms if r["level"] == lv]
        groups = _groups(here, [l for l in links if l["kind"] != "stairs"])
        groups.sort(key=lambda g: (entrance not in g, -len(g)))
        main = groups[0]
        for g in groups[1:]:
            a = min(main, key=lambda x: (_degree(x, links), here.index(x)))
            b = g[0]
            links.append({"from": a, "to": b, "kind": "archway", "length": "short"})
            fixes.append("Room %s (%s) had no way in on its level: Mythastria added a passage from %s." % (b, by_id[b]["name"], a))
            main = main + g
        if lv > 1 and not any(l["kind"] == "stairs" and {by_id[l["from"]]["level"], by_id[l["to"]]["level"]} & {lv}
                              and min(by_id[l["from"]]["level"], by_id[l["to"]]["level"]) < lv for l in links):
            above = [r["id"] for r in rooms if r["level"] == lv - 1]
            a = max(above, key=lambda x: (by_id[x]["purpose"] in ("hall", "cavern", "shrine", "crypt"), -_degree(x, links)))
            links.append({"from": a, "to": here[0], "kind": "stairs", "length": "short"})
            fixes.append("Level %d had no stairs down to it: Mythastria added stairs from %s to %s." % (lv, a, here[0]))
    design = {"name": _text(raw.get("name"), 60) or "The %s" % prefs["kind"], "summary": _text(raw.get("summary"), 500),
              "entrance": entrance, "lair": lair, "levels": nlev, "rooms": rooms, "connections": links}
    return design, fixes


def _degree(rid, links):
    return sum(rid in (l["from"], l["to"]) for l in links)


def _groups(ids, links):
    adj = {i: set() for i in ids}
    for l in links:
        if l["from"] in adj and l["to"] in adj:
            adj[l["from"]].add(l["to"]); adj[l["to"]].add(l["from"])
    out, seen = [], set()
    for i in ids:
        if i in seen:
            continue
        g, todo = [], [i]
        seen.add(i)
        while todo:
            x = todo.pop(0); g.append(x)
            for n in sorted(adj[x], key=ids.index):
                if n not in seen:
                    seen.add(n); todo.append(n)
        out.append(g)
    return out


# ------------------------------------------------------------------ the code's part: a level laid out on the grid
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def _ring(r):
    x0, y0, x1, y1 = r
    return {(x, y) for x in range(x0 - 1, x1 + 2) for y in range(y0 - 1, y1 + 2)} - _inside(r)


def _inside(r):
    x0, y0, x1, y1 = r
    return {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}


def _apart(a, b):
    """Two rooms' walls never touch: at least one square of rock between their rings (interiors 4 apart)."""
    return a[0] - b[2] >= 4 or b[0] - a[2] >= 4 or a[1] - b[3] >= 4 or b[1] - a[3] >= 4


def _centre(r):
    return ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)


def _place(rooms, links, start, rng):
    """Room rectangles (interior squares, inclusive), each beside the room it is reached from, or None."""
    ids = [r["id"] for r in rooms]
    by_id = {r["id"]: r for r in rooms}
    adj = {i: [] for i in ids}
    for l in links:
        if l["from"] in adj and l["to"] in adj:
            adj[l["from"]].append((l["to"], l["length"])); adj[l["to"]].append((l["from"], l["length"]))
    order, parent, todo = [start], {start: (None, "short")}, deque([start])
    while todo:
        x = todo.popleft()
        for n, length in adj[x]:
            if n not in parent:
                parent[n] = (x, length); order.append(n); todo.append(n)
    dims = {}
    for i in ids:
        lo, hi = ROOM_SIZES[by_id[i]["size"]]
        dims[i] = (rng.randint(lo, hi), rng.randint(lo, hi))
    rects = {start: (0, 0, dims[start][0] - 1, dims[start][1] - 1)}
    for rid in order[1:]:
        par, length = parent[rid]
        w, h = dims[rid]
        gap = (1, 2) if length == "short" else (3, 6)
        anchors = [par] + rng.sample([a for a in rects if a != par], len(rects) - 1)
        done = False
        for anchor in anchors:
            P = rects[anchor]
            for dx, dy in rng.sample(DIRS, 4):
                for _ in range(6):
                    g = rng.randint(*gap)
                    if dx:
                        x0 = P[2] + g + 3 if dx > 0 else P[0] - g - 3 - (w - 1)
                        y0 = rng.randint(P[1] - h + 1, P[3])
                    else:
                        y0 = P[3] + g + 3 if dy > 0 else P[1] - g - 3 - (h - 1)
                        x0 = rng.randint(P[0] - w + 1, P[2])
                    r = (x0, y0, x0 + w - 1, y0 + h - 1)
                    if all(_apart(r, o) for o in rects.values()):
                        rects[rid] = r; done = True
                        break
                if done:
                    break
            if done:
                break
        if not done:
            return None
    return rects


def _route(a, b, cols, rows, blocked, floor):
    """A corridor from square a to square b: through rock only, never on the map's edge, never touching a room's wall
    ring; joining an existing corridor costs less, turning costs a little (straight passages)."""
    inside = lambda x, y: 1 <= x <= cols - 2 and 1 <= y <= rows - 2 and (x, y) not in blocked
    if not inside(*a) or not inside(*b):
        return None
    h = lambda p: abs(p[0] - b[0]) + abs(p[1] - b[1])
    best, came, heap, n = {(a, None): 0}, {}, [(h(a), 0, 0, a, None)], 0
    while heap:
        _, g, _, p, d = heapq.heappop(heap)
        if p == b:
            path, k = [p], (p, d)
            while k in came:
                k = came[k]; path.append(k[0])
            return path[::-1]
        if g > best.get((p, d), 1e9):
            continue
        for nd in DIRS:
            q = (p[0] + nd[0], p[1] + nd[1])
            if not inside(*q):
                continue
            ng = g + (0.4 if q in floor else 1.0) + (0.5 if d is not None and nd != d else 0)
            if ng < best.get((q, nd), 1e9):
                best[(q, nd)] = ng; came[(q, nd)] = (p, d); n += 1
                heapq.heappush(heap, (ng + h(q), ng, n, q, nd))
    return None


def _door_spots(r, side, doors):
    """The wall squares on one side of room r that can take a doorway (not a corner, not beside another doorway), with
    the square just outside it."""
    x0, y0, x1, y1 = r
    dx, dy = side
    if dx:
        x = x1 + 1 if dx > 0 else x0 - 1
        spots = [((x, y), (x + dx, y), (x - dx, y)) for y in range(y0, y1 + 1)]
    else:
        y = y1 + 1 if dy > 0 else y0 - 1
        spots = [((x, y), (x, y + dy), (x, y - dy)) for x in range(x0, x1 + 1)]
    taken = set(doors)
    return [s for s in spots if not any((s[0][0] + i, s[0][1] + j) in taken for i, j in ((0, 0),) + DIRS)]


def _layout_level(design, lv, start, seed, attempt):
    rng = random.Random("site:%s:%d:%d" % (seed, lv, attempt))
    rooms = [r for r in design["rooms"] if r["level"] == lv]
    links = [l for l in design["connections"] if l["kind"] != "stairs"
             and {l["from"], l["to"]} <= {r["id"] for r in rooms}]
    rects = _place(rooms, links, start, rng)
    if rects is None:
        return None
    minx, miny = min(r[0] for r in rects.values()), min(r[1] for r in rects.values())
    rects = {k: (r[0] - minx + MARGIN, r[1] - miny + MARGIN, r[2] - minx + MARGIN, r[3] - miny + MARGIN) for k, r in rects.items()}
    cols, rows = max(r[2] for r in rects.values()) + MARGIN + 1, max(r[3] for r in rects.values()) + MARGIN + 1
    if cols > MAX_SIDE or rows > MAX_SIDE:
        return None
    blocked = set()
    for r in rects.values():
        blocked |= _inside(r) | _ring(r)
    floor = set()
    for r in rects.values():
        floor |= _inside(r)
    doors, corridors, door_list = {}, set(), []          # doorway square -> (kind, room id)
    for l in links:
        A, B = rects[l["from"]], rects[l["to"]]
        (ax, ay), (bx, by) = _centre(A), _centre(B)
        sides_a = sorted(DIRS, key=lambda d: -(d[0] * (bx - ax) + d[1] * (by - ay)))[:3]
        sides_b = sorted(DIRS, key=lambda d: -(d[0] * (ax - bx) + d[1] * (ay - by)))[:3]
        path = None
        for sa in sides_a:
            for sb in sides_b:
                ca = sorted(_door_spots(A, sa, doors), key=lambda s: abs(s[0][0] - bx) + abs(s[0][1] - by))
                cb = sorted(_door_spots(B, sb, doors), key=lambda s: abs(s[0][0] - ax) + abs(s[0][1] - ay))
                for da in ca[:2]:
                    for db in cb[:2]:
                        if da[1] == db[1] or da[1] in doors or db[1] in doors:
                            continue
                        path = _route(da[1], db[1], cols, rows, blocked, corridors)
                        if path:
                            break
                    if path:
                        break
                if path:
                    break
            if path:
                break
        if not path:
            return None
        for d in (da, db):
            doors[d[0]] = l["kind"]
            door_list.append((d[0], l["kind"], d[2]))
        corridors |= set(path)
    floor |= corridors | set(doors)
    return {"cols": cols, "rows": rows, "rects": rects, "floor": floor, "doors": door_list, "rng": rng}


def _erode(lay, design, lv):
    """Natural rooms: the rock bites into a cavern's edges; the squares inside a doorway stay, the cavern stays whole."""
    rng, floor = lay["rng"], lay["floor"]
    keep = {inner for _, _, inner in lay["doors"]}
    for r in design["rooms"]:
        if r["level"] != lv or r["shape"] != "natural":
            continue
        R = lay["rects"][r["id"]]
        room = set(_inside(R))
        rim = sorted(c for c in room if c[0] in (R[0], R[2]) or c[1] in (R[1], R[3]))
        for c in rim:
            corner = c[0] in (R[0], R[2]) and c[1] in (R[1], R[3])
            if c in keep or rng.random() > (0.7 if corner else 0.3) or len(room) <= 9:
                continue
            room.discard(c)
            if _connected(room):
                floor.discard(c)
            else:
                room.add(c)
        lay.setdefault("cave", {})[r["id"]] = room


def _connected(cells):
    cells = set(cells)
    if not cells:
        return False
    first = next(iter(cells))
    seen, todo = {first}, [first]
    while todo:
        x, y = todo.pop()
        for dx, dy in DIRS:
            n = (x + dx, y + dy)
            if n in cells and n not in seen:
                seen.add(n); todo.append(n)
    return len(seen) == len(cells)


def build(design, prefs, creature, count, lib, model=None, where=""):
    """The design -> one scenario per level (the simulator's format, Play live's map), each passing check_map()."""
    by_id = {r["id"]: r for r in design["rooms"]}
    stairs = [l for l in design["connections"] if l["kind"] == "stairs"]
    lair = design["lair"]
    out = []
    for lv in range(1, design["levels"] + 1):
        here = [r["id"] for r in design["rooms"] if r["level"] == lv]
        if lv == 1:
            start = design["entrance"]
        else:
            start = next((l[k] for l in stairs for k in ("from", "to") if l[k] in here
                          and by_id[l["to" if k == "from" else "from"]]["level"] < lv), here[0])
        lay = None
        for attempt in range(40):
            lay = _layout_level(design, lv, start, prefs["seed"], attempt)
            if lay:
                break
        if not lay:
            raise SiteMapError("Mythastria could not lay out level %d of this design on the grid (%d rooms). Try another "
                               "map number." % (lv, len(here)))
        _erode(lay, design, lv)
        sc = _scenario(design, prefs, lv, lay, start, here, stairs, by_id, creature, count, lib, lair, model, where)
        problems = check_map(sc)
        if problems:
            raise SiteMapError("Level %d failed the map check: %s" % (lv, " ".join(problems[:4])))
        out.append(sc)
    return out


def _farthest(lay, start_cell, here):
    """The room farthest from the start by walking (doors and all), for creatures when the lair is elsewhere."""
    dist = _walk(lay["floor"], start_cell, lay["floor"])
    return max(here, key=lambda r: min((dist.get(c, -1) for c in _inside(lay["rects"][r]) if c in lay["floor"]), default=-1))


def _walk(cells, start, _floor):
    dist, todo = {start: 0}, deque([start])
    while todo:
        x, y = todo.popleft()
        for dx, dy in DIRS:
            n = (x + dx, y + dy)
            if n in cells and n not in dist:
                dist[n] = dist[(x, y)] + 1; todo.append(n)
    return dist


def _free(room_cells, taken, by_wall, floor):
    cells = sorted(c for c in room_cells if c not in taken)
    if by_wall:
        cells.sort(key=lambda c: -sum((c[0] + dx, c[1] + dy) not in floor for dx, dy in DIRS))
    else:
        cells.sort(key=lambda c: sum((c[0] + dx, c[1] + dy) not in floor for dx, dy in DIRS))
    return cells


def _scenario(design, prefs, lv, lay, start, here, stairs, by_id, creature, count, lib, lair, model, where):
    cols, rows, rects, floor, rng = lay["cols"], lay["rows"], lay["rects"], lay["floor"], lay["rng"]
    cave = lay.get("cave", {})
    cells_of = lambda rid: sorted(cave.get(rid) or _inside(rects[rid]))
    wall = {(x, y) for x in range(cols) for y in range(rows)} - floor
    door_squares = [d for d, kind, _ in lay["doors"] if kind in ("door", "locked door")]
    walls = map_import.cell_walls(cols, rows, wall, door_squares)
    locked = []
    door_ids = {tuple(d): "door %d" % (i + 1) for i, d in enumerate(door_squares)}
    for d, kind, _ in lay["doors"]:
        if kind == "locked door":
            locked.append(door_ids[d])
    keep = {inner for _, _, inner in lay["doors"]}
    props, zones, lights, ceilings, taken = [], [], [], [], set(keep)
    for rid in here:
        r, room = by_id[rid], cells_of(rid)
        for l in stairs:
            if rid in (l["from"], l["to"]):
                other = by_id[l["to"] if l["from"] == rid else l["from"]]
                way = "down" if other["level"] > lv else "up"
                c = _free(room, taken, True, floor)[0]
                taken.add(c)
                props.append({"kind": "stairs", "x": c[0], "y": c[1],
                              "label": "Stairs %s to level %d: %s" % (way, other["level"], other["name"])})
        if lv == 1 and rid == design["entrance"]:
            c = _free(room, taken, True, floor)[0]
            taken.add(c)
            props.append({"kind": "stairs", "x": c[0], "y": c[1], "label": "The way in, from outside"})
        for f in r["features"]:
            if f == "pool":
                spots = [c for c in _free(room, taken, False, floor)
                         if all(((c[0] + i, c[1] + j) in room and (c[0] + i, c[1] + j) not in taken) for i in (0, 1) for j in (0, 1))]
                if spots:
                    x, y = spots[0]
                    zones.append({"id": "pool %s" % rid, "kind": "water", "rect": [x, y, x + 1, y + 1]})
                    taken |= {(x + i, y + j) for i in (0, 1) for j in (0, 1)}
                continue
            spots = _free(room, taken, f in BY_WALL, floor)
            if not spots:
                continue
            c = spots[0] if f in BY_WALL else spots[min(len(spots) - 1, rng.randint(0, 2))]
            taken.add(c)
            props.append({"kind": f, "x": c[0], "y": c[1], "label": "%s (%s)" % (f.replace("_", " "), r["name"])})
            if f in LIGHTS:
                bright, dim, what = LIGHTS[f]
                lights.append({"x": c[0], "y": c[1], "bright_ft": bright, "dim_ft": dim, "label": "%s, %s" % (what, r["name"])})
        R = rects[rid]
        ceilings.append({"room": r["name"], "rect": list(R), "ft": 20 if r["size"] == "large" else 15 if r["shape"] == "natural" else 10,
                         "description": r["description"]})
    water = {(x, y) for z in zones for x in range(z["rect"][0], z["rect"][2] + 1) for y in range(z["rect"][1], z["rect"][3] + 1)}
    party_at = _centre_cell(cells_of(start), water | taken)
    foes_room = lair if lair in here and lair != start else _farthest(lay, party_at, here)
    foes_at = _centre_cell(cells_of(foes_room), water | taken | {party_at})
    level_name = design["name"] if design["levels"] == 1 else "%s, level %d" % (design["name"], lv)
    map_name = ("%s, map %d: %s" % (where, prefs["seed"], level_name) if where else level_name)[:80]   # notes are kept by it
    # a level of small rooms holds fewer creatures (the GM adds more in Play live): the same search _scenario makes
    party = map_import.spots(party_at, len(map_import.PARTY), cols, rows, wall | water)
    room_for = map_import.spaces(foes_at, count, cols, rows, wall | water | set(party), map_import.size_squares(lib.get(creature) or {}))
    if not room_for:
        raise SiteMapError("Level %d has no room for one %s: choose a smaller creature or another map number." % (lv, creature))
    count = len(room_for)
    try:
        sc = map_import._scenario(map_name, cols, rows, walls, [], {"ambient": "dark", "lights": lights}, None,
                                  party_at, creature, count, foes_at, lib, wall, avoid=water)
    except map_import.ImportError_ as e:
        raise SiteMapError(str(e))
    natural = all(by_id[rid]["shape"] == "natural" for rid in here)
    # _scenario folds the squares nobody starts on (the pools) into wall_cells: here they are water, never stone
    sc["wall_cells"] = [list(c) for c in sorted(wall, key=lambda c: (c[1], c[0]))]
    sc.update(name="%s: %d x %s" % (level_name, count, creature), map_name=map_name, locked_doors=locked, zones=zones,
              props=props, ground="dry" if natural else "stone", ceilings=ceilings,
              source="SRD 5.2.1 (CC-BY-4.0) creatures; a Mythastria site map (MAPGEN-02): designed by the local model %s "
                     "from the GM's preferences, laid out and checked by Mythastria." % (model or "(none)"),
              rooms=[{"id": rid, "name": by_id[rid]["name"], "purpose": by_id[rid]["purpose"], "rect": list(rects[rid]),
                      "description": by_id[rid]["description"]} for rid in here],
              site={"name": design["name"], "summary": design["summary"], "kind": prefs["kind"], "level": lv,
                    "levels": design["levels"], "start": start, "creatures_in": foes_room},
              design=prefs, doorways=[{"square": list(d), "kind": k} for d, k, _ in lay["doors"]])
    sc["notes"] = [{"id": "room-%s" % rid, "x": int(_centre(rects[rid])[0]), "y": int(_centre(rects[rid])[1]),
                    "text": "%s %s (%s)%s: %s" % (rid, by_id[rid]["name"], by_id[rid]["purpose"],
                                                 ", the creatures wait here" if rid == foes_room else "",
                                                 by_id[rid]["description"])[:2000], "show_players": False} for rid in here]
    return sc


def _centre_cell(cells, avoid):
    cells = [c for c in cells if c not in avoid] or list(cells)
    cx, cy = sum(c[0] for c in cells) / len(cells), sum(c[1] for c in cells) / len(cells)
    return min(cells, key=lambda c: (abs(c[0] - cx) + abs(c[1] - cy), c))


# ------------------------------------------------------------------ the map check (MAP RULE and the goal's rules)
def check_map(sc):
    """What a site map breaks, in words (empty: it passes): floor on the map's edge, a wall line with floor on both sides
    (a line wall, not a square), a door not in a wall, a floor square nobody can walk to (diagonal touching does not
    count: every passage is at least one 5-ft square wide), a creature in the rock, a room with no floor."""
    cols, rows = max(w[0] for w in sc["wall_cells"]) + 1, max(w[1] for w in sc["wall_cells"]) + 1
    wall = set(map(tuple, sc["wall_cells"]))
    floor = {(x, y) for x in range(cols) for y in range(rows)} - wall
    doorways = [tuple(d["square"]) for d in sc.get("doorways", []) if d["kind"] in ("door", "locked door")]
    out = list(map_import.rule_problems(cols, rows, wall, doorways))
    solid = lambda x, y: not (0 <= x < cols and 0 <= y < rows) or (x, y) in wall
    for w in sc["walls"]:
        if w.get("door"):
            continue
        (ax, ay), (bx, by) = [[p + 0.5 for p in q] for q in w["points"]]
        if ax == bx:
            sides = [((int(ax) - 1, y), (int(ax), y)) for y in range(int(min(ay, by)), int(max(ay, by)))]
        else:
            sides = [((x, int(ay) - 1), (x, int(ay))) for x in range(int(min(ax, bx)), int(max(ax, bx)))]
        if any(not solid(*a) and not solid(*b) for a, b in sides):
            out.append("Wall %s is a line between two floor squares: walls are whole squares." % w["id"])
    pcs = [c for c in sc["combatants"] if c.get("side") == "friend"]
    if floor and pcs:
        start = (int(pcs[0]["x"]), int(pcs[0]["y"]))
        reach = _walk(floor, start, floor)
        lost = sorted(floor - set(reach))
        if lost:
            out.append("%d floor squares cannot be walked to from the start (e.g. %s)." % (len(lost), lost[0]))
    for c in sc["combatants"]:
        if (int(c["x"]), int(c["y"])) in wall:
            out.append("%s starts inside the rock." % c["name"])
    for r in sc.get("rooms", []):
        if not _inside(r["rect"]) & floor:
            out.append("Room %s has no floor." % r["id"])
    return out


# ------------------------------------------------------------------ written into the maps folder tree
def slug(text, n=40):
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")[:n] or "map"


def write(levels, project, region, place, out_dir=OUT):
    """Each level as sites/<project>/<region>/<place>_<site>_<map number>_level_<n>.json (the pickers' folders: Region
    sites > project > region). Returns the scenario names, level 1 first."""
    folder = Path(out_dir) / slug(project or "spare maps") / slug(region or "region")
    folder.mkdir(parents=True, exist_ok=True)
    top = Path(out_dir)
    if not (top / ".gitignore").exists():                              # made at the table, not part of the repository
        (top / ".gitignore").write_text("*\n", encoding="utf-8")
    names = []
    for sc in levels:
        stem = "%s_%s_%d_level_%d" % (slug(place or "site", 30), slug(sc["site"]["name"], 30), sc["design"]["seed"], sc["site"]["level"])
        path = folder / (stem + ".json")
        path.write_text(json.dumps(sc, indent=1) + "\n", encoding="utf-8")
        names.append("sites/" + path.relative_to(top).as_posix())
    return names


def make(prefs, context, creature, count, lib, llm_url=LLM_URL, model=MODEL, raw=None, where=""):
    """The whole goal: ask the model (unless a design is given), check the design, build and check every level.
    Returns (levels, design, fixes, facts)."""
    prefs, context = check_prefs(prefs), check_context(context)
    facts = {"model": "(design given)"}
    if raw is None:
        raw, facts = ask_model(prefs, context, llm_url, model)
    design, fixes = check_design(raw, prefs)
    levels = build(design, prefs, creature, count, lib, model=facts.get("model"), where=where)
    return levels, design, fixes, facts


def main(argv=None):
    import creature_threat
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--kind", choices=KINDS, default="dungeon"); ap.add_argument("--size", choices=sorted(SIZES), default="normal")
    ap.add_argument("--levels", type=int, default=1); ap.add_argument("--layout", choices=LAYOUTS, default="branching")
    ap.add_argument("--walls", choices=WALLS, default="cut stone"); ap.add_argument("--doors", choices=DOORS, default="some")
    ap.add_argument("--theme", default=""); ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--terrain", default="hills"); ap.add_argument("--climate", default="temperate")
    ap.add_argument("--creature", default="Goblin Warrior"); ap.add_argument("--count", type=int, default=4)
    ap.add_argument("--llm-url", default=LLM_URL); ap.add_argument("--model", default=MODEL)
    ap.add_argument("--design", help="a design JSON file instead of asking the model")
    ap.add_argument("--project", default="Spare maps"); ap.add_argument("--region", default="Command line")
    ap.add_argument("--place", default="site"); ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    prefs = {k: getattr(a, k) for k in ("kind", "size", "levels", "layout", "walls", "doors", "theme", "seed")}
    raw = json.loads(Path(a.design).read_text(encoding="utf-8")) if a.design else None
    try:
        levels, design, fixes, facts = make(prefs, {"terrain": a.terrain, "climate": a.climate}, a.creature, a.count,
                                            creature_threat.library(), a.llm_url, a.model, raw=raw, where=a.place)
    except SiteMapError as e:
        raise SystemExit(str(e))
    for name in write(levels, a.project, a.region, a.place, Path(a.out)):
        print("wrote sim/scenarios/" + name)
    print("%s: %d rooms, %d levels; model %s, %s s" % (design["name"], len(design["rooms"]), design["levels"],
                                                       facts.get("model"), facts.get("seconds", "-")))
    for f in fixes:
        print("  changed: " + f)


if __name__ == "__main__":
    main()
