"""REMIX-01, attached to Play live (GM 2026-10-20: "We need the remix built"; "As long as the encounters are customizable
and recommendations are offered by Remix then it's okay to attach."). Design: docs/development/REMIX.md.

A remix is a small layer, never an edit of the map: {"changes": [{"from": "Goblin Warrior", "to": "Kobold Warrior",
"count": 3}, ...], "add": [{"name": "Wolf", "count": 2, "at": [x, y] or absent}], "seed": n}. apply() returns a new
scenario for one fight; the map file is untouched.

- encounter(): the map's creatures by kind (count, XP, CR, how they move and fight), the XP total and its band for the
  party (SRD 5.2.1 XP budget per character, bestiary_catalog.XP_BUDGET).
- recommend(): substitutes for one kind from the SRD 5.2.1 library (creature_threat.library: 336 creatures): close in
  XP, the same way of moving where the map needs it (a swimmer for a swimmer, a flier for a flier), a similar fighting
  style (melee or ranged), not bigger than the space it starts in; closer still when the measured threat (THREAT-01)
  at this level is known for both. Each comes with a plain reason.
- suggest(): quick remixes the GM can take as they are or edit: fresh faces (each kind replaced by a recommendation,
  chosen by the seed), one step easier, one step harder.
- apply(): the creatures of each changed kind are replaced by the new kind's stat block, on the old creatures' squares
  first, more near them (whole spaces, clear of walls and others), fewer by dropping the last.
- Added kinds (GM 2026-10-21: "Training doesn't have a way to populate the combat table"): any SRD 5.2.1 creature from
  the library, 1-12 of it, on free floor squares the nearest walk from the map's foe start (its first creature) or from
  a square the GM clicked; never through a wall.
- Lineups (2026-10-21): the GM saves the creatures of a fight as a named list of {name, count} and loads it onto any
  map (the panel replaces the map's creatures with it or adds it). check_lineup() keeps only SRD 5.2.1 library
  creatures, on saving and on loading; the service keeps the lineups in sim/lineups/lineups.json (campaign data).
Estimates only: Remix's background proof (the tuner) is a later step; the GM decides.
"""
import copy, json, math, random, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "sim"), str(ROOT / "mythastria_core")]
from remix_spec import SRD_MOUNTS  # noqa: E402  (GM 2026-10-23: mounts are animals, never offered as foes)

MAX_COUNT, MAX_FOES, MAX_CHANGES = 12, 24, 12
THREAT = ROOT / "sim" / "threat" / "threat.json"
LINEUP_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 '\-]{0,39}$")
MAX_LINEUPS = 100


def base_name(name):
    return re.sub(r"\s+\d+$", "", str(name or "")).strip()


def _speeds(block):
    s = str(block.get("speed") or "").lower()
    return {"swim": "swim" in s, "fly": "fly" in s or bool(block.get("fly")),
            "walk": bool(re.match(r"^\s*([1-9]\d*)\s*ft", s)) and not re.match(r"^\s*5\s*ft", s)}


def _style(block):
    kinds = {a.get("atktype") for a in block.get("actions") or [] if isinstance(a, dict)}
    if block.get("spells"):
        return "caster"
    return "ranged" if kinds == {"ranged"} or ("ranged" in kinds and "melee" not in kinds) else "melee"


def _squares(block):
    return max(1, int(round(float(block.get("space") or 5) / 5)))


def profile(name, block):
    sp = _speeds(block)
    return {"name": name, "xp": int(block.get("xp") or 0), "cr": block.get("cr"), "style": _style(block),
            "squares": _squares(block), "swims": sp["swim"], "flies": sp["fly"], "walks": sp["walk"],
            "fully_played": not block.get("gm_text")}


def band(xp, party_size, level, levels=None):
    """levels: each character's own level (a party of mixed levels, saved characters among them): the SRD 5.2.1 budget
    is per character, so their budgets add up; otherwise party_size characters at `level`."""
    import bestiary_catalog as bc
    each = levels or [level] * party_size
    low, mod, high = (sum(bc.XP_BUDGET[max(1, min(20, int(lv)))][i] for lv in each) for i in range(3))
    name = "below Low" if xp < low else "Low" if xp < mod else "Moderate" if xp < high else "High" if xp <= high else "above High"
    return {"xp": xp, "band": name, "budget": {"low": low, "moderate": mod, "high": high}}


def foes(sc):
    return [c for c in sc.get("combatants", []) if c.get("side") == "foe" and not c.get("pc")]


def encounter(sc, lib, party_size, level, levels=None):
    kinds = {}
    for c in foes(sc):
        n = base_name(c["name"])
        k = kinds.setdefault(n, dict(profile(n, lib.get(n) or c), count=0, in_library=n in lib))
        k["count"] += 1
    total = sum(k["xp"] * k["count"] for k in kinds.values())
    return dict(band(total, party_size, level, levels), kinds=list(kinds.values()), party_size=party_size, level=level,
                levels=list(levels) if levels else None)


def _threat(level):
    try:
        rows = json.loads(THREAT.read_text(encoding="utf-8"))["rows"]
    except (OSError, ValueError, KeyError):
        return {}
    out = {}
    for r in rows:
        if r.get("level") == level and r.get("threat") is not None:
            out.setdefault(r["creature"], []).append(r["threat"] / max(1, r.get("count", 1)))
    return {k: sum(v) / len(v) for k, v in out.items()}


def recommend(name, lib, level, n=8, exclude=(), threat=None):
    """Substitutes for `name`, best first: [{name, xp, cr, style, why, measured}]."""
    base = lib.get(name)
    if not base:
        return []
    want, threat = profile(name, base), _threat(level) if threat is None else threat
    out = []
    for other, block in lib.items():
        if other == name or other in exclude or other in SRD_MOUNTS:
            continue
        p = profile(other, block)
        if p["xp"] <= 0 or not want["xp"]:
            continue
        ratio = p["xp"] / want["xp"]
        if not 0.5 <= ratio <= 2.0 or p["squares"] > want["squares"]:
            continue
        if want["swims"] and not want["walks"] and not p["swims"]:
            continue                                            # a sea creature's map needs a swimmer
        if want["flies"] and not want["walks"] and not p["flies"]:
            continue
        score = abs(math.log(ratio)) + (0.6 if p["style"] != want["style"] else 0) + (0.3 if not p["fully_played"] else 0)
        score += (0.2 if p["flies"] != want["flies"] else 0) + (0.25 if want["swims"] and not p["swims"] else 0)
        measured = None
        if name in threat and other in threat:
            measured = threat[other] / max(1e-6, threat[name])
            score += abs(math.log(max(1e-3, measured))) * 0.8
        why = ["XP %d vs %d" % (p["xp"], want["xp"]), p["style"]]
        if p["flies"]:
            why.append("flies")
        if p["swims"]:
            why.append("swims")
        if measured is not None:
            why.append("measured %s" % ("about as dangerous" if 0.8 <= measured <= 1.25 else "more dangerous" if measured > 1.25 else "less dangerous"))
        if not p["fully_played"]:
            why.append("some abilities GM-ruled")
        out.append((score, other, dict(p, why=", ".join(why), measured=None if measured is None else round(measured, 2))))
    out.sort(key=lambda t: (t[0], t[1]))
    return [p for _, _, p in out[:n]]


def suggest(sc, lib, party_size, level, seed=1, levels=None):
    """Quick remixes: fresh faces, one step easier, one step harder. Each: {label, changes, xp, band}."""
    enc, rng, threat = encounter(sc, lib, party_size, level, levels), random.Random(seed), _threat(level)
    kinds = [k for k in enc["kinds"] if k["in_library"]]
    if not kinds:
        return []
    fresh = []
    for k in kinds:
        recs = recommend(k["name"], lib, level, n=3, threat=threat)
        fresh.append({"from": k["name"], "to": rng.choice(recs)["name"] if recs else k["name"], "count": k["count"]})
    big = max(kinds, key=lambda k: (k["count"], k["xp"]))
    keep = [{"from": k["name"], "to": k["name"], "count": k["count"]} for k in kinds if k is not big]
    easier = keep + [{"from": big["name"], "to": big["name"], "count": max(1 if len(kinds) == 1 else 0, big["count"] - 1)}]
    harder = keep + [{"from": big["name"], "to": big["name"], "count": min(MAX_COUNT, big["count"] + 1)}]
    out = []
    for label, changes in (("Fresh faces", fresh), ("One step easier", easier), ("One step harder", harder)):
        xp = sum(lib[c["to"]].get("xp", 0) * c["count"] for c in changes if c["to"] in lib)
        out.append(dict(band(xp, party_size, level, levels), label=label, changes=changes))
    return out


def _extent(sc):
    xs, ys = [0], [0]
    for w in sc.get("walls") or []:
        for p in w.get("points") or []:
            xs.append(p[0]); ys.append(p[1])
    for c in sc.get("combatants", []):
        xs.append(c.get("x", 0)); ys.append(c.get("y", 0))
    for x, y in sc.get("wall_cells") or []:
        xs.append(x); ys.append(y)
    return int(math.floor(max(xs))) + 1, int(math.floor(max(ys))) + 1


def _square(c):
    return int(round(c["x"])), int(round(c["y"]))


def _wall_lines(sc):
    """The map's line walls as segments in squares (square centres are whole numbers), open doors left out."""
    open_ = {str(i) for i in sc.get("open_doors") or []}
    out = []
    for w in sc.get("walls") or []:
        if str(w.get("id")) in open_ and not w.get("closed"):
            continue
        pts = w.get("points") or []
        out += [(tuple(a), tuple(b)) for a, b in zip(pts, pts[1:])]
    return out


def _crosses(a, b, seg):
    def side(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    c, d = seg
    return side(a, b, c) * side(a, b, d) < 0 and side(c, d, a) * side(c, d, b) < 0


def _near(start, n, cols, rows, taken, rock, lines, size=1):
    """Token centres for n creatures of size x size squares, the nearest walk from start first: through floor (not
    `rock`, never across a line wall), each space whole on the map and clear of `taken` and of the others."""
    from collections import deque
    seen, queue, used, out = {start}, deque([start]), set(taken) | set(rock), []
    while queue and len(out) < n:
        x, y = queue.popleft()
        block = {(x + i, y + j) for i in range(size) for j in range(size)}
        if x + size <= cols and y + size <= rows and not block & used:
            used |= block
            out.append((x + (size - 1) / 2, y + (size - 1) / 2) if size > 1 else (x, y))
        for q in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if q in seen or not (0 <= q[0] < cols and 0 <= q[1] < rows) or q in rock:
                continue
            if any(_crosses((x, y), q, s) for s in lines):
                continue
            seen.add(q)
            queue.append(q)
    return out


def _foe_start(sc, cols, rows, rock):
    """The map's foe start: its first creature's square; with none, the middle of the map (the nearest floor)."""
    import map_import
    f = foes(sc)
    start = _square(f[0]) if f else (cols // 2, rows // 2)
    if start in rock:
        start = (map_import.spots(start, 1, cols, rows, rock) or [start])[0]
    return start


def foe_start(sc):
    """The square added creatures start from when the GM picks none (for the Remix panel)."""
    cols, rows = _extent(sc)
    return list(_foe_start(sc, cols, rows, {tuple(p) for p in sc.get("wall_cells") or []}))


def _next_number(sc, name):
    nums = [int(m.group(1)) for c in sc.get("combatants", []) if base_name(c["name"]) == name
            for m in [re.search(r"\s(\d+)$", str(c["name"]))] if m]
    return max(nums, default=0) + 1


def check(remix, lib, sc):
    if not isinstance(remix, dict):
        raise ValueError("A remix lists its changes (from, to, count) or the creatures it adds (name, count).")
    changes, add = remix.get("changes", []), remix.get("add", [])
    if not isinstance(changes, list) or not isinstance(add, list) or not (changes or add):
        raise ValueError("A remix lists its changes (from, to, count) or the creatures it adds (name, count).")
    if len(changes) > MAX_CHANGES:
        raise ValueError("At most %d changes in one remix." % MAX_CHANGES)
    if len(add) > MAX_CHANGES:
        raise ValueError("At most %d added kinds in one remix." % MAX_CHANGES)
    present = {base_name(c["name"]) for c in foes(sc)}
    seen, total = set(), 0
    for ch in changes:
        if not isinstance(ch, dict):
            raise ValueError("Each change is from, to and count.")
        frm, to, n = ch.get("from"), ch.get("to"), ch.get("count")
        if frm not in present and frm is not None:
            raise ValueError("%s is not in this encounter." % frm)
        if frm in seen and frm is not None:
            raise ValueError("%s is changed twice." % frm)
        seen.add(frm)
        if not isinstance(to, str) or to not in lib:
            raise ValueError("%s has no simulator stat block." % to)
        if not isinstance(n, int) or isinstance(n, bool) or not 0 <= n <= MAX_COUNT:
            raise ValueError("A count is 0-%d." % MAX_COUNT)
        total += n
    cols, rows = _extent(sc)
    rock = {tuple(p) for p in sc.get("wall_cells") or []}
    for a in add:
        if not isinstance(a, dict):
            raise ValueError("Each added kind is a name and a count.")
        name, n, at = a.get("name"), a.get("count"), a.get("at")
        if not isinstance(name, str) or name not in lib:
            raise ValueError("%s is not in the SRD 5.2.1 creature library." % name)
        if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= MAX_COUNT:
            raise ValueError("An added count is 1-%d." % MAX_COUNT)
        if at is not None:
            if not (isinstance(at, list) and len(at) == 2 and all(isinstance(v, int) and not isinstance(v, bool) for v in at)):
                raise ValueError("A square is [x, y] in whole squares.")
            if not (0 <= at[0] < cols and 0 <= at[1] < rows):
                raise ValueError("The square %s is off the map (%d x %d)." % (tuple(at), cols, rows))
            if tuple(at) in rock:
                raise ValueError("The square %s is a wall; pick a floor square." % (tuple(at),))
        total += n
    kept = sum(1 for c in foes(sc) if base_name(c["name"]) not in seen)
    if not 1 <= total + kept <= MAX_FOES:
        raise ValueError("An encounter has 1-%d creatures." % MAX_FOES)


def lineup_name(name):
    if not isinstance(name, str) or not LINEUP_NAME.match(name.strip()):
        raise ValueError("A lineup's name is 1-40 letters, digits, spaces, ' or -, e.g. Wolf pack.")
    return name.strip()


def check_lineup(creatures, lib):
    """A lineup's creatures as [{name, count}], the same kind once (counts added up): each an SRD 5.2.1 creature from
    the library, 1-12 of a kind, 1-24 in all, at most 12 kinds. Raises ValueError, plainly, for anything else."""
    if not isinstance(creatures, list) or not creatures:
        raise ValueError("A lineup lists its creatures (name and count).")
    out = {}
    for c in creatures:
        if not isinstance(c, dict):
            raise ValueError("Each creature in a lineup is a name and a count.")
        name, n = c.get("name"), c.get("count")
        if not isinstance(name, str) or name not in lib:
            raise ValueError("%s is not in the SRD 5.2.1 creature library." % name)
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            raise ValueError("A count in a lineup is 1-%d." % MAX_COUNT)
        out[name] = out.get(name, 0) + n
    if any(n > MAX_COUNT for n in out.values()):
        raise ValueError("At most %d of one kind in a lineup (%s)." % (MAX_COUNT, ", ".join(k for k, n in out.items() if n > MAX_COUNT)))
    if len(out) > MAX_CHANGES:
        raise ValueError("At most %d kinds in a lineup." % MAX_CHANGES)
    if sum(out.values()) > MAX_FOES:
        raise ValueError("A lineup has 1-%d creatures." % MAX_FOES)
    return [{"name": k, "count": n} for k, n in out.items()]


def apply(sc, remix, lib):
    """A new scenario with the remix applied (the given one is not changed). Raises ValueError for a bad remix."""
    import map_import
    check(remix, lib, sc)
    out = copy.deepcopy(sc)
    cols, rows = _extent(out)
    aware = set(out.get("aware") or [])
    taken = {(int(round(c["x"])), int(round(c["y"]))) for c in out["combatants"]} | {tuple(p) for p in out.get("wall_cells") or []}
    rock = {tuple(p) for p in out.get("wall_cells") or []}
    foe_start = _foe_start(sc, cols, rows, rock)                # before any change moves the map's first creature
    n_id = 0

    def place(block, name, x, y, init, is_aware):
        nonlocal n_id
        n_id += 1
        f = {k: copy.deepcopy(v) for k, v in block.items() if k in map_import.KEEP}
        f.update(id="id-remix-%03d" % n_id, name="%s %d" % (name, _next_number(out, name)), side="foe", x=x, y=y, init=init)
        out["combatants"].append(f)
        if is_aware and out.get("aware") is not None:
            aware.add(f["id"])

    for ch in remix.get("changes") or []:
        old = [c for c in foes(out) if base_name(c["name"]) == ch.get("from")]
        block = lib[ch["to"]]
        size = _squares(block)
        old_sq = {(int(round(c["x"])), int(round(c["y"]))) for c in old}
        spots = [(c["x"], c["y"]) for c in old][:ch["count"]] if size == 1 else []   # same squares first
        taken = (taken - old_sq) | {(int(round(x)), int(round(y))) for x, y in spots}
        if len(spots) < ch["count"]:                          # more, or bigger: whole clear spaces near them
            start = (int(round(old[0]["x"])), int(round(old[0]["y"]))) if old else (cols // 2, rows // 2)
            more = map_import.spaces(start, ch["count"] - len(spots), cols, rows, taken, size)
            for x, y in more:
                h = (size - 1) / 2
                taken |= {(int(round(x - h)) + i, int(round(y - h)) + j) for i in range(size) for j in range(size)}
            spots += more
        if len(spots) < ch["count"]:
            raise ValueError("Not enough room on this map for %d %s." % (ch["count"], ch["to"]))
        was_aware = any(c["id"] in aware for c in old) or not out.get("aware")
        init = old[0].get("init", block.get("init", 10)) if old else block.get("init", 10)
        for c in old:
            out["combatants"].remove(c)
            aware.discard(c["id"])
        for x, y in spots:
            place(block, ch["to"], x, y, init, was_aware)
    lines, first = _wall_lines(out), (foes(sc) or [None])[0]
    for a in remix.get("add") or []:                           # added kinds: the nearest floor from the start or the GM's square
        block = lib[a["name"]]
        size = _squares(block)
        spots = _near(tuple(a["at"]) if a.get("at") is not None else foe_start, a["count"], cols, rows, taken, rock, lines, size)
        if len(spots) < a["count"]:
            raise ValueError("Not enough floor near there for %d %s." % (a["count"], a["name"]))
        for x, y in spots:
            h = (size - 1) / 2
            taken |= {(int(round(x - h)) + i, int(round(y - h)) + j) for i in range(size) for j in range(size)}
            place(block, a["name"], x, y, block.get("init", 10), first is not None and first["id"] in (sc.get("aware") or []))
    if out.get("aware") is not None:
        out["aware"] = sorted(aware)
    out["remix"] = copy.deepcopy(remix)
    out["name"] = "%s (remixed)" % out.get("name", "Encounter")
    return out
