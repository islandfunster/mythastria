"""THREAT-01 (GM 2026-10-20): measure what each SRD creature actually does against the pregens, so Remix can swap and
scale encounters on the fly (docs/development/REMIX.md: CR/XP matched the measured band in only 6 of 16 Seven Isles
encounters).

  py tools/creature_threat.py run [--creatures seven-isles|all-known|NAME,NAME] [--levels 1-8] [--arenas open,corridor]
                                  [--seeds 5] [--rounds 8]          # long: run it in the background; it resumes
  py tools/creature_threat.py report                                # docs/development/THREAT_REPORT.md from the results
  py tools/creature_threat.py run ... --worker 2/4                  # one of 4 workers side by side (its own file)
  py tools/creature_threat.py merge                                 # the workers' files into threat.json

For each creature, at each party level where a group of it fits the 2024 Moderate XP budget for four characters (1 to 8
creatures; one alone when it is above that budget but within High), the group fights Hero 1, Hero 2, Hero 3 and Hero 4 (the
SRD pregens at that level, team tactics) on standard arenas, a few runs each with instant dice (the encounter tuner's
simulate()). Recorded per creature, level and arena: wins, losses, time-outs, characters dropped, deaths, rounds, the
tuner's "plays as" rating, how that compares with the XP band, and a threat number (characters dropped per run for a
Moderate budget's worth of the creature). Results: sim/threat/threat.json (one row per measurement, written as it goes).

Stat blocks: the simulator's own, from the scenarios that already use the creature (sim/scenarios); every other SRD
creature has THREAT-02's basic block (tools/srd_library.py). Only creatures in the SRD 5.2.1 bestiary are measured.
Arenas: open ground and a 10-ft corridor, bright light; creatures that cannot move on land wait for a water arena.
2026-10-27 (GM: "Make temporary arenas proportionate to the creatures based on medium size. Make the arena one size
larger per size increase of the creatures"): the arenas are Medium-sized for Tiny, Small and Medium creatures and grow
one step per size above: x2 for Large, x3 for Huge, x4 for Gargantuan (the corridor 20, 30 or 40 ft wide and 60, 90
or 120 squares long; the open arena's and the water arenas' room and the creatures' starting area the same). The
creatures still start 14 squares from the party at every scale, so a big creature doesn't buy the party extra rounds
of ranged attacks. Each row records its arena_scale.
"""
import argparse, copy, glob, json, re, sys, time, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "sim"), str(ROOT / "mythastria_core")]
import bestiary_catalog as bc
import encounter_tuner as tuner

OUT = ROOT / "sim" / "threat" / "threat.json"
REPORT = ROOT / "docs" / "development" / "THREAT_REPORT.md"
PARTY = ["Hero 1", "Hero 2", "Hero 3", "Hero 4"]
SEVEN_ISLES = ["Animated Armor", "Animated Flying Sword", "Azer Sentinel", "Doppelganger", "Earth Elemental", "Gargoyle",
               "Giant Crab", "Giant Venomous Snake", "Harpy", "Knight", "Mage", "Magma Mephit", "Magmin",
               "Minotaur Skeleton", "Sahuagin Warrior", "Shadow", "Shield Guardian", "Skeleton", "Steam Mephit", "Wight",
               "Zombie"]
ARENAS = ("open", "corridor")
# 2026-10-20 (GM: "underground island rooms and caverns can have traps and events that fill them partially or fully
# with water"): the simulator's water zones (SIM-ENV-01: underwater attacks, swimming, holding breath)
WATER_ARENAS = ("flooded", "half-flooded")
BANDS = ("below low", "low", "moderate", "high", "above high")
KEEP = ("hp", "ac", "dex_save", "str_save", "con_save", "wis_save", "int_save", "cha_save", "speed", "space", "size", "type",
        "int", "senses", "wis_mod", "actions", "damageimmunities", "damageresistances", "damagevulnerabilities", "traits",
        "skills", "srd_name", "fly", "stealth", "multiattack", "spells", "reach", "reactions", "legendary", "conditions")


# ------------------------------------------------------------------ creatures
def library():
    """{SRD name: the simulator's stat block, with its XP and CR from the SRD}: sim/creatures/srd_library.json, which holds
    every SRD 5.2.1 creature with the scenarios' hand-made blocks put right from the official PDF (GM 2026-11-01). A
    scenario's own block only for a creature the file lacks: a map can carry numbers set for its encounter."""
    import srd_library
    out = copy.deepcopy(srd_library.load())
    for name, c in hand_made().items():
        out.setdefault(name, c)
    return out


def hand_made():
    """{SRD name: the simulator's stat block from the scenarios that already use the creature, XP and CR from the SRD}."""
    srd = tuner.srd_stats()
    out = {}
    for f in sorted(glob.glob(str(ROOT / "sim" / "scenarios" / "**" / "*.json"), recursive=True)):
        try:
            sc = json.loads(Path(f).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for c in sc.get("combatants", []):
            if c.get("side") != "foe" or c.get("pc"):
                continue
            name = tuner.base_name(c["name"])
            if name in out or name not in srd:
                continue
            block = {k: copy.deepcopy(v) for k, v in c.items() if k not in ("id", "name", "x", "y", "side", "init", "wounds")}
            block.update(name=name, xp=srd[name]["xp"], cr=srd[name]["cr"], source=Path(f).relative_to(ROOT).as_posix(),
                         init=c.get("init", 10))
            out[name] = block
    return out


def walks(c):
    """False for a swimmer that barely moves on land (a shark's 5 ft): it is measured only in the water arenas."""
    m = re.match(r"\s*(\d+)", str(c.get("speed", "30")))
    land = int(m.group(1)) if m else 0
    return land >= 10 or "swim" not in str(c.get("speed", "")).lower()


# ------------------------------------------------------------------ groups and the plan
def budget(level):
    low, mod, high = (4 * v for v in bc.XP_BUDGET[level])
    return low, mod, high


def group_size(xp, level, cap=False):
    """How many of a creature make the 2024 Moderate budget for four characters at this level: 1-8, or None (a swarm
    of more than 8, or one alone beyond the High budget). cap: a swarm is measured as 8, however weak that plays."""
    if not xp:
        return None
    _, mod, high = budget(level)
    n = round(mod / xp)
    if n == 0:
        return 1 if xp <= high else None
    return n if n <= 8 else 8 if cap else None


def plan(lib, names, levels=range(1, 9), arenas=ARENAS, done=(), cap=False):
    done = set(done)
    out = []
    for name in names:
        c = lib.get(name)
        if not c:
            continue
        for lv in levels:
            n = group_size(c["xp"], lv, cap)
            if not n:
                continue
            for arena in arenas:
                if arena not in WATER_ARENAS and not walks(c):
                    continue
                key = (name, lv, arena)
                if key not in done:
                    out.append({"creature": name, "level": lv, "arena": arena, "count": n})
    return out


# ------------------------------------------------------------------ arenas
LENGTH, DEPTH, GAP = 30, 16, 14              # a Medium arena: 30 squares long, 16 deep; the creatures start 14 squares in


def arena_scale(creature):
    """GM 2026-10-27: one arena size per creature size above Medium: Tiny-Medium 1, Large 2, Huge 3, Gargantuan 4."""
    return max(1, int(round(float(creature.get("space") or 5) / 5)))


def arena_walls(arena, k=1):
    if arena in ("open",) + WATER_ARENAS:
        return []
    if arena == "corridor":                          # a 10-ft corridor (x k wide), 30 squares long (x k), from row 6
        n, s, e = 5.5, 5.5 + 2 * k, LENGTH * k - 0.5
        return [{"id": "north", "points": [[-0.5, n], [e, n]]}, {"id": "south", "points": [[-0.5, s], [e, s]]},
                {"id": "west", "points": [[-0.5, n], [-0.5, s]]}, {"id": "east", "points": [[e, n], [e, s]]}]
    raise ValueError("no arena %s" % arena)


def arena_zones(arena, k=1):
    """Flooded: the whole arena is deep water. Half-flooded: the far half (where the creatures start); the party starts
    on dry ground and must go in after them, or make them come out."""
    if arena == "flooded":
        return [{"id": "flood", "kind": "water", "rect": [0, 0, LENGTH * k - 1, DEPTH * k - 1]}]
    if arena == "half-flooded":
        return [{"id": "flood", "kind": "water", "rect": [GAP - 4, 0, LENGTH * k - 1, DEPTH * k - 1]}]
    return []


def squares(arena, side, n, size, k=1):
    """Start squares (top-left of each space) for n creatures of `size` squares on one side of an arena of scale k.
    The party keeps the left edge, at the arena's middle; the creatures' area grows with k from 14 squares out."""
    if arena in ("open",) + WATER_ARENAS:
        mid = DEPTH * k // 2
        cols, rows = ([2, 3], range(mid - 4, mid + 3)) if side == "party" else (
            list(range(GAP, GAP + 12 * k, size)), range(mid - 5 * k, mid + 5 * k - size + 1, size))
    else:
        top, width = 6, 2 * k
        mid = top + k - 1
        cols, rows = ([1, 2, 3, 4], [mid, mid + 1]) if side == "party" else (
            list(range(GAP, LENGTH * k - size + 1, size)), range(top, top + width - size + 1, size))
    spots = [(x, y) for x in cols for y in rows]
    if len(spots) < n:
        raise ValueError("no room for %d on the %s side of %s" % (n, side, arena))
    return spots[:n]


def arena_scenario(arena, creature, n):
    size = k = arena_scale(creature)
    sc = {"name": "THREAT-01 arena %s x%d: %d x %s" % (arena, k, n, creature["name"]), "rounds": 8, "grid": 50, "units": 5,
          "diag": 1, "map_name": "Threat arena (%s, x%d)" % (arena, k), "walls": arena_walls(arena, k), "open_doors": [],
          **({"zones": arena_zones(arena, k)} if arena_zones(arena, k) else {}),
          "source": "SRD 5.2.1 (CC-BY-4.0); synthetic simulator arena (THREAT-01, not adventure content).", "combatants": []}
    for i, (name, (x, y)) in enumerate(zip(PARTY, squares(arena, "party", 4, 1, k)), 1):
        sc["combatants"].append({"id": "id-%05d" % i, "name": name, "side": "friend", "pc": True, "hp": 10, "ac": 10,
                                 "init": 20 - i, "x": x, "y": y})
    foes = []
    for i, (x, y) in enumerate(squares(arena, "foe", n, size, k), 1):
        x, y = x + (size - 1) / 2, y + (size - 1) / 2       # THREAT-02: a Large token on its grid corner (map_import.spaces)
        c = {k: copy.deepcopy(v) for k, v in creature.items() if k in KEEP}
        c.update(id="id-%05d" % (20 + i), name="%s %d" % (creature["name"], i), side="foe", x=x, y=y,
                 init=creature.get("init", 10))
        foes.append(c)
    sc["combatants"] += foes
    sc["aware"] = [c["id"] for c in foes]
    return sc


# ------------------------------------------------------------------ measuring
def summarize(r, moderate):
    runs = max(1, r["runs"])
    d = r["drops"] / runs
    res = dict(r, drops_per_run=round(d, 3), avg_rounds=round(sum(r["rounds"]) / len(r["rounds"]), 2) if r["rounds"] else None)
    res["plays_as"] = tuner.verdict(dict(r, drops_per_run=d))
    if r["timeout"] * 2 >= runs and d < 0.5:
        # the encounter tuner's warning: fights that time out with nobody down are a stalemate, not a difficulty
        res.update(plays_as="not rated", vs_xp="ran out of rounds: not rated", threat=None)
        return res
    res["threat"] = round(d * moderate / max(1, r["xp"]), 4)
    xp_band = {"below Low": "below low", "Low": "low", "Moderate": "moderate", "High": "high", "above High": "above high"}.get(r["band"], r["band"])
    gap = BANDS.index(res["plays_as"]) - BANDS.index(xp_band)
    res["vs_xp"] = "as XP says" if gap == 0 else "%s than XP says (%d band%s)" % ("harder" if gap > 0 else "easier", abs(gap), "" if abs(gap) == 1 else "s")
    return res


def measure(item, lib, seeds=(1, 2, 3, 4, 5), rounds=8):
    c, lv, n = lib[item["creature"]], item["level"], item["count"]
    sc = tuner.with_party(arena_scenario(item["arena"], c, n), PARTY, lv)
    low, mod, high = budget(lv)
    rating = tuner.rate(sc, tuner.srd_stats(), 4, lv)
    t0 = time.monotonic()
    r = tuner.simulate(sc, list(seeds), rounds, instant=True)
    row = {"creature": item["creature"], "level": lv, "arena": item["arena"], "count": n, "xp": rating["xp"],
           "band": rating["band"], "runs": r["runs"], "won": r["won"], "lost": r["lost"], "timeout": r["timeout"],
           "drops": r["drops"], "dead": r["dead"], "rounds": r["rounds"], "issues": r["issues"], "stuck": r.get("stuck", 0),
           "seconds": round(time.monotonic() - t0, 1), "stat_block": c["source"], "arena_scale": arena_scale(c)}
    return summarize(row, mod)


# ------------------------------------------------------------------ the batch
def load_results():
    return json.loads(OUT.read_text(encoding="utf-8")) if OUT.is_file() else {"format": "creature-threat/1", "rows": []}


def save_results(data):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tmp.replace(OUT)


# 2026-10-27 (GM: "How to reduce that time in half"; chose 4 workers): workers run side by side, each in its own process
# with its own results file; a measurement belongs to one worker by a fixed rule on its creature, level and arena, so the
# shares never overlap and a restarted worker takes up its own share where it stopped. `merge` folds the files in.
def worker_file(k):
    return OUT.with_name("threat_worker%d.json" % k)


def worker_rows():
    rows = []
    for f in sorted(OUT.parent.glob("threat_worker*.json")):
        rows += json.loads(f.read_text(encoding="utf-8"))["rows"]
    return rows


def mine(item, k, n):
    return zlib.crc32(("%s|%d|%s" % (item["creature"], item["level"], item["arena"])).encode("utf-8")) % n == k - 1


def merge():
    data = load_results()
    have = {(r["creature"], r["level"], r["arena"]) for r in data["rows"]}
    added = 0
    for r in worker_rows():
        key = (r["creature"], r["level"], r["arena"])
        if key not in have:
            data["rows"].append(r)
            have.add(key)
            added += 1
    save_results(data)
    for f in OUT.parent.glob("threat_worker*.json"):
        f.unlink()
    return added


def run(names, levels, arenas, seeds, rounds, log=print, cap=False, worker=None):
    lib = library()
    main_data = load_results()
    done = {(r["creature"], r["level"], r["arena"]) for r in main_data["rows"] + worker_rows()}
    todo = plan(lib, names, levels, arenas, done, cap)
    if worker:
        k, n = worker
        todo = [item for item in todo if mine(item, k, n)]
        path = worker_file(k)
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"format": "creature-threat/1", "rows": []}
        save = lambda d: (path.with_suffix(".tmp").write_text(json.dumps(d, indent=1), encoding="utf-8"),
                          path.with_suffix(".tmp").replace(path))
    else:
        data, save = main_data, save_results
    skipped = [n for n in names if n in lib and not walks(lib[n])] + [n for n in names if n not in lib]
    log("THREAT-01: %d measurements to run (%d done before); skipped: %s" % (len(todo), len(done), ", ".join(skipped) or "none"))
    for i, item in enumerate(todo, 1):
        try:
            row = measure(item, lib, seeds, rounds)
        except ValueError as e:                  # 2026-10-27: a group too big for the arena (7 Huge in the corridor)
            log("[%d/%d] %s x%d, level %d, %s: skipped, %s (not recorded: measure it in a bigger arena)" % (
                i, len(todo), item["creature"], item["count"], item["level"], item["arena"], e))
            continue
        data["rows"].append(row)
        save(data)
        log("[%d/%d] %s x%d, level %d, %s: %s (%s), %.2f drops/run, %d/%d won, %.0f s" % (
            i, len(todo), item["creature"], item["count"], item["level"], item["arena"], row["plays_as"], row["vs_xp"],
            row["drops_per_run"], row["won"], row["runs"], row["seconds"]))
    return data


def report(data=None):
    data = data or load_results()
    rows = [summarize(r, budget(r["level"])[1]) for r in data["rows"]]   # re-rated with the current rules
    lines = ["# THREAT-01 — measured creature threat (generated by tools/creature_threat.py report)", "",
             "Each row: a group of the creature sized to the 2024 Moderate XP budget for four characters at that level, "
             "against Hero 1, Hero 2, Hero 3 and Hero 4 (SRD pregens, team tactics), %s runs each with instant dice. Threat: "
             "characters dropped per run for a Moderate budget's worth of the creature (higher is deadlier for its XP)."
             % (rows[0]["runs"] if rows else "-"), ""]
    rated = [r for r in rows if r["plays_as"] != "not rated"]
    off = [r for r in rated if r["vs_xp"] != "as XP says"]
    lines += ["Measurements: %d (%d not rated: they ran out of rounds with nobody down). Of the rated: as XP says %d, "
              "harder than XP %d, easier than XP %d." % (
        len(rows), len(rows) - len(rated), len(rated) - len(off), sum(1 for r in off if r["vs_xp"].startswith("harder")),
        sum(1 for r in off if r["vs_xp"].startswith("easier"))), ""]
    lines += ["| Creature | Level | Arena | Group | XP (band) | Plays as | vs XP | Drops/run | Won | Rounds | Threat |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["creature"], r["level"], r["arena"])):
        lines.append("| %s | %d | %s | %d | %d (%s) | %s | %s | %.2f | %d/%d | %s | %.2f |" % (
            r["creature"], r["level"], r["arena"], r["count"], r["xp"], r["band"], r["plays_as"], r["vs_xp"],
            r["drops_per_run"], r["won"], r["runs"], r["avg_rounds"] if r["avg_rounds"] is not None else "-",
            r["threat"] if r["threat"] is not None else float("nan")))
    lines += ["", "Limits: bright light and two arenas only; no water arena yet (creatures without a land speed wait); "
              "only creatures with a simulator stat block (THREAT-02 converts the rest of the SRD bestiary); features the "
              "simulator does not play are not counted (see each map's tuning report)."]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return REPORT


def parse_levels(text):
    a, _, b = text.partition("-")
    return range(int(a), int(b or a) + 1)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--creatures", default="seven-isles"); r.add_argument("--levels", default="1-8")
    r.add_argument("--arenas", default=",".join(ARENAS), help="open, corridor, flooded, half-flooded"); r.add_argument("--seeds", type=int, default=5)
    r.add_argument("--rounds", type=int, default=8)
    # 2026-10-21 (GM: "remix doesn't have qualifying arena samples"): weak creatures (Giant Crab, Flying Snake) never
    # fill a Moderate budget with 8, so Remix had no sample for them at any level. This measures them 8 at a time.
    r.add_argument("--cap-at-8", action="store_true", help="measure a group of 8 when the budget needs more")
    r.add_argument("--worker", help="K/N: run worker K of N side by side (its own results file; merge afterwards)")
    sub.add_parser("report")
    sub.add_parser("merge")
    a = ap.parse_args(argv)
    if a.cmd == "report":
        print(report()); return 0
    if a.cmd == "merge":
        print("merged %d rows from the workers into %s" % (merge(), OUT)); print(report()); return 0
    worker = tuple(int(x) for x in a.worker.split("/")) if a.worker else None
    names = (SEVEN_ISLES if a.creatures == "seven-isles" else sorted(library()) if a.creatures == "all-known"
             else [n.strip() for n in a.creatures.split(",")])
    run(names, parse_levels(a.levels), a.arenas.split(","), list(range(1, a.seeds + 1)), a.rounds,
        log=lambda s: print(s, flush=True), cap=a.cap_at_8, worker=worker)
    if not worker:
        print(report())
    return 0


if __name__ == "__main__":
    sys.exit(main())
