"""TUNE-01 (2026-10-14): rate and tune a module encounter for a party, with the simulator as the judge.

  py tools/encounter_tuner.py sim/scenarios/watch_temple_interior.json --target moderate [--level 1]
        [--members Hero 1,Hero 2,Hero 3,Hero 4] [--seeds 10] [--rounds 8] [--ollama 0] [--out FILE.md]
        [--llm-url http://127.0.0.1:1234/v1 --model google/gemma-4-12b-qat]   # local-model runs in LM Studio

1. Rate: the encounter's XP (SRD 5.2.1 stat blocks; XP from CR where missing) against the 2024 XP budget for the
   party's size and level: below Low / Low / Moderate / High / above High.
2. Measure: simulator runs (real extension and bridge, scripted monster chooser; --ollama N adds N runs with the local
   model) with the optimized SRD pregens (sim/parties/srd_pregens.json, team tactics, death saves): wins, losses,
   characters dropped, deaths, rounds.
3. Tune: variants that keep the same creatures and stat blocks: one fewer or one more of a creature already there, or
   its hit points at the low or high end of its own hit dice. Each variant is rated and simulated the same way; the one
   closest to the target is recommended.
Targets (SRD 5.2.1 "Combat Encounter Difficulty", read as simulator outcomes for an optimized party):
  low       no character should drop (average under 0.5 drops a run), no deaths, always a win
  moderate  "weaker characters might get taken out": about 0.5-1.5 drops a run, a win at least 9 times in 10, no deaths
  high      "could be lethal for one or more characters": 1.5 drops or more, or a few losses, rare deaths
Nothing is written into the adventure: the report is a proposal for the GM.
--level: 1-8 (PARTY-04 2026-10-15, PARTY-L8 2026-10-18: the pregens' builds; a higher level is refused).
--items: the pregens' magic-item kits up to that level (PARTY-ITEMS, simulator tests only).
"""
import argparse, contextlib, copy, json, math, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "sim")); sys.path.insert(0, str(ROOT / "mythastria_core"))
import bestiary_catalog as bc

TARGETS = {"low": (0.0, 0.5), "moderate": (0.5, 1.5), "high": (1.5, 3.5)}
DEFAULT_MEMBERS = ["Hero 1", "Hero 2", "Hero 3", "Hero 4"]


# ------------------------------------------------------------------ rating
def base_name(name):
    return re.sub(r"\s+\d+$", "", name).strip()


def srd_stats():
    out = {}
    for r in bc.srd_records():
        f = r["fields"]
        crv = bc.cr_value(f.get("cr"))
        stated = str(f.get("xp") or "").strip()
        xp = int(stated) if stated.isdigit() else 0
        # The module's XP is 0 for a few creatures whose SRD 5.2.1 stat block gives more (the wyrmlings: 450, 700): their
        # CR's XP then. A CR 0 creature's 0 is its own (Shrieker Fungus, Seahorse: "CR 0 (XP 0)"), not a missing value.
        out[r["name"]] = {"xp": xp if xp or crv == 0 and stated == "0" else bc.CR_XP.get(crv, 0),
                          "cr": str(f.get("cr") or ""), "hd": str(f.get("hd") or "")}
    return out


def hp_range(hd):
    """'(2d8 + 4)' -> (6, 13, 20): minimum, average, maximum hit points from the stat block's own hit dice."""
    m = re.search(r"(\d+)d(\d+)\s*([+-]\s*\d+)?", hd or "")
    if not m:
        return None
    n, d, b = int(m.group(1)), int(m.group(2)), int((m.group(3) or "0").replace(" ", ""))
    return max(1, n + b), int(n * (d + 1) / 2 + b), n * d + b


def foes(sc):
    return [c for c in sc["combatants"] if c.get("side") == "foe"]


def rate(sc, stats, party_size, level):
    xp = sum(stats.get(base_name(c["name"]), {}).get("xp", 0) for c in foes(sc))
    low, mod, high = (party_size * v for v in bc.XP_BUDGET[level])
    band = ("below Low" if xp < low else "Low" if xp < mod else "Moderate" if xp < high else
            "High" if xp <= high * 1.0 else "above High")
    if xp == high:
        band = "High"
    return {"xp": xp, "budget": {"low": low, "moderate": mod, "high": high}, "band": band}


# ------------------------------------------------------------------ simulating
def max_party_level():
    return 20


def with_party(sc, members, level, items=False, party="srd_pregens", extra=None):
    import run_sim
    # items: PARTY-ITEMS, tests only; party: LEVEL-TESTS-01 clone parties (sim/parties/test/pregens_L<n>)
    # extra: CHARACTERS-01 saved characters {name: member build}, named in members too
    sc = run_sim.apply_party(copy.deepcopy(sc), party, level, items=items, extra=extra)
    keep = set(members)
    sc["combatants"] = [c for c in sc["combatants"] if not c.get("pc") or c["name"] in keep]
    # Dark maps hand the party torch to Hero 1's scenario id; without Hero 1, the first character carries it (the
    # campaign runner did this alone; the tuner crashed on the dangling carrier, 2026-10-18 RECHECK-LARGE-01).
    pc_ids = [c["id"] for c in sc["combatants"] if c.get("pc")]
    for light in (sc.get("lighting") or {}).get("lights") or []:
        if light.get("carrier") and pc_ids and str(light["carrier"]).rsplit(".", 1)[-1] not in pc_ids:
            light["carrier"] = pc_ids[0]
            light["label"] = "Party torch (test fixture)"
    return sc


STUCK = "cannot get closer; it stays put"


def stuck_turns(text, pc_names):
    """v0.8.6: monster turns that "cannot get closer" before any character drops (after that, the last characters
    standing may simply be surrounded: the end of a lost fight, not a creature boxed in at its start square)."""
    drops = [text.find(n + " drops to 0 hit points") for n in pc_names]
    first = min([d for d in drops if d >= 0], default=len(text))
    return text[:first].count(STUCK)


def simulate(sc, seeds, rounds, model="scripted", instant=False, stall=None):
    import run_sim
    res = {"runs": 0, "won": 0, "lost": 0, "timeout": 0, "drops": 0, "dead": 0, "rounds": [], "issues": 0}
    for seed in seeds:
        s = copy.deepcopy(sc)
        sim = run_sim.Sim(s, model, model == "scripted", seed, instant, True)
        try:
            sim.run(rounds, stall or (20 if model == "scripted" else 200))   # LEVEL-TESTS-01: instant rolls, a short stall
        finally:
            sim.close()
        text = "\n".join(t for _, t in sim.lines)
        pcs = [c for c in s["combatants"] if c.get("pc")]
        res["runs"] += 1
        if sim.side_down("foe"):
            res["won"] += 1; res["rounds"].append(sim.S.round())
        elif sim.side_down("friend"):
            res["lost"] += 1
        else:
            res["timeout"] += 1
        res["drops"] += sum(text.count(c["name"] + " drops to 0 hit points") for c in pcs)
        res["dead"] += sum(1 for c in pcs if sim.party and sim.party.deaths.get(c["id"], {}).get("dead"))
        res["issues"] += sim.stalls + len(sim.problems) + sim.wall_crossings
        # 2026-10-15 (tidal archive): a monster boxed in at its start square "cannot get closer; it stays put" every
        # turn and the fights time out with nobody hurt; report it instead of rating the stalemate
        res["stuck"] = res.get("stuck", 0) + stuck_turns(text, [c["name"] for c in pcs])
    res["drops_per_run"] = res["drops"] / max(1, res["runs"])
    res["avg_rounds"] = sum(res["rounds"]) / len(res["rounds"]) if res["rounds"] else None
    return res


@contextlib.contextmanager
def local_model(llm_url=None, model=None, reasoning=None):
    """The model for the local-model runs, as (model, label). Default: Ollama's qwen3.5 (the live game model).
    2026-10-16 (GM: "add the LM Studio option to the encounter tuner and recheck"): with llm_url, that model on a local
    OpenAI-compatible server such as LM Studio (LOCAL-LLM-01 chooser, this PC only) for the duration."""
    import ollama_client
    if not llm_url:
        yield (next((m for m in (ollama_client.list_models() or []) if "qwen3.5" in m), None) or "qwen3.5:9b-q4_K_M",
               "Ollama")
        return
    import local_llm_chooser
    real = ollama_client.choose
    ollama_client.choose = local_llm_chooser.make_choose(llm_url, model, reasoning=reasoning)
    try:
        yield model, "local server %s%s" % (llm_url, ", thinking %s" % reasoning if reasoning else "")
    finally:
        ollama_client.choose = real


def simulate_model(sc, seeds, rounds, model):
    """simulate() with the local model, counting its calls and failures (LOCAL-LLM-01 server). If every call failed the
    batch stops: nothing is rated and the scripted chooser is never used instead (as in GEMMA-GROUPS-01)."""
    import local_llm_chooser
    before = dict(local_llm_chooser.STATS)
    r = simulate(sc, seeds, rounds, model)
    r["calls"] = local_llm_chooser.STATS["calls"] - before["calls"]
    r["failures"] = local_llm_chooser.STATS["failures"] - before["failures"]
    if r["calls"] and r["failures"] == r["calls"]:
        raise SystemExit("Every local-model call failed (%d of %d); stopped, nothing rated." % (r["failures"], r["calls"]))
    return r


def verdict(r):
    d = r["drops_per_run"]
    win = r["won"] / max(1, r["runs"])
    if r["dead"] == 0 and win == 1 and d < 0.5:
        return "low"
    if r["dead"] == 0 and win >= 0.9 and d < 1.5:
        return "moderate"
    return "high" if win >= 0.6 else "above high"


def distance(r, target):
    lo, hi = TARGETS[target]
    d = r["drops_per_run"]
    miss = 0 if lo <= d < hi else min(abs(d - lo), abs(d - hi))
    win = r["won"] / max(1, r["runs"])
    need_win = 1.0 if target == "low" else 0.9 if target == "moderate" else 0.6
    return miss + max(0.0, need_win - win) * 3 + r["dead"] * (2 if target != "high" else 0.5)


# ------------------------------------------------------------------ variants
def free_square(sc, near):
    """A place next to `near` (same creature type) for one more of it: its whole space free of other creatures and of
    walls (the scenario's own walls), reachable from `near` without crossing one. v0.8.4 (the AI assistant review R083-01): by
    the creature's space (a Large one steps 2 squares and fills 2 x 2 around its token; it once overlapped the first)."""
    import map_walls, ai_turn
    g = sc.get("grid", 50)
    segs = [((w["points"][0][0] * g, w["points"][0][1] * g), (w["points"][1][0] * g, w["points"][1][1] * g))
            for w in sc.get("walls", []) if not (w.get("door") and str(w["id"]) in set(map(str, sc.get("open_doors", []))))]
    size = lambda c: max(1, int(round(float(c.get("space") or 5) / 5)))
    s = size(near)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, 1), (1, -1), (-1, -1), (2, 0), (0, 2), (-2, 0), (0, -2)):
        x, y = near["x"] + dx * s, near["y"] + dy * s
        if any(abs(c["x"] - x) < (size(c) + s) / 2 - 0.02 and abs(c["y"] - y) < (size(c) + s) / 2 - 0.02
               for c in sc["combatants"]):
            continue
        a, b = (near["x"] * g, near["y"] * g), (x * g, y * g)
        if segs and (map_walls.blocked(a, b, segs) or not ai_turn._space_clear(b, s, g, segs)
                     or (s == 1 and map_walls.near(b, segs, 0.3 * g))):
            continue
        return x, y
    return None


def variants(sc, stats):
    out = []
    kinds = {}
    for c in foes(sc):
        kinds.setdefault(base_name(c["name"]), []).append(c)
    for kind, group in kinds.items():
        if len(group) > 1 or len(kinds) > 1:
            v = copy.deepcopy(sc)
            drop = group[-1]["id"]
            v["combatants"] = [c for c in v["combatants"] if c["id"] != drop]
            out.append(("one fewer %s" % kind, v))
        spot = free_square(sc, group[0])
        if spot:
            v = copy.deepcopy(sc)
            new = copy.deepcopy(group[0])
            used = {c["id"] for c in v["combatants"]}
            n = len(v["combatants"]) + 1
            while "id-%05d" % n in used:
                n += 1
            new.update(id="id-%05d" % n, name="%s %d" % (kind, len(group) + 1), x=spot[0], y=spot[1])
            v["combatants"].append(new)
            out.append(("one more %s (at %g,%g)" % (kind, spot[0], spot[1]), v))
        rng = hp_range(stats.get(kind, {}).get("hd"))
        if rng:
            for label, hp in (("low", rng[0]), ("high", rng[2])):
                if hp != group[0].get("hp"):
                    v = copy.deepcopy(sc)
                    for c in v["combatants"]:
                        if c.get("side") == "foe" and base_name(c["name"]) == kind:
                            c["hp"] = hp
                    out.append(("%s at %s hit points (%d, hit dice %s)" % (kind, label, hp, stats[kind]["hd"]), v))
    return out


# ------------------------------------------------------------------ report
def line(label, rating, r):
    return "| %s | %d XP (%s) | %d/%d won, %d lost, %d out of rounds | %.1f | %d | %s | %s |" % (
        label, rating["xp"], rating["band"], r["won"], r["runs"], r["lost"], r["timeout"], r["drops_per_run"], r["dead"],
        "%.1f" % r["avg_rounds"] if r["avg_rounds"] else "-", verdict(r))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("scenario"); ap.add_argument("--target", choices=list(TARGETS), default="moderate")
    ap.add_argument("--level", type=int, default=1); ap.add_argument("--members", default=",".join(DEFAULT_MEMBERS))
    ap.add_argument("--seeds", type=int, default=10); ap.add_argument("--rounds", type=int, default=8)
    ap.add_argument("--ollama", type=int, default=0, help="extra runs of the base and the recommended variant with the local model")
    ap.add_argument("--llm-url", metavar="URL", help="local-model runs on this local OpenAI-compatible server instead of "
                    "Ollama (LM Studio: http://127.0.0.1:1234/v1); needs --model")
    ap.add_argument("--model", help="the model's name on the --llm-url server")
    ap.add_argument("--reasoning", choices=["none", "low", "medium", "high"], help="thinking for an LM Studio model (2026-10-16): none = off, like the live bridge on Ollama; omitted = the model's own default (Gemma 4 thinks first)")
    ap.add_argument("--out")
    ap.add_argument("--items", action="store_true", help="PARTY-ITEMS: the members' magic-item kits (simulator tests only)")
    a = ap.parse_args(argv)
    if a.llm_url and not a.model:
        ap.error("--llm-url needs --model (the model's name on that server)")
    if not 1 <= a.level <= max_party_level():
        ap.error("--level %d: the SRD pregens have builds for levels 1-%d only" % (a.level, max_party_level()))
    stats = srd_stats()
    raw = json.loads(Path(a.scenario).read_text(encoding="utf-8"))
    members = [m.strip() for m in a.members.split(",") if m.strip()]
    sc = with_party(raw, members, a.level, items=a.items)
    seeds = list(range(1, a.seeds + 1))
    rows = []
    base_rating = rate(sc, stats, len(members), a.level)
    base = simulate(sc, seeds, a.rounds)
    rows.append(("as built", sc, base_rating, base))
    print(line("as built", base_rating, base))
    for label, v in variants(sc, stats):
        rt, r = rate(v, stats, len(members), a.level), simulate(v, seeds, a.rounds)
        rows.append((label, v, rt, r)); print(line(label, rt, r))
    best = min(rows, key=lambda x: (distance(x[3], a.target), x[0] != "as built"))
    lines = ["# Encounter tuning: %s" % (raw.get("map_name") or Path(a.scenario).stem), "",
             "Party: %s (SRD pregens, level %d, team tactics). Target: **%s**. %d scripted runs per variant, %d rounds max." % (
                 ", ".join(members), a.level, a.target, len(seeds), a.rounds), "",
             "Budget for %d characters at level %d: Low %d, Moderate %d, High %d XP." % (
                 len(members), a.level, base_rating["budget"]["low"], base_rating["budget"]["moderate"], base_rating["budget"]["high"]), "",
             "| Variant | XP (2024 budget) | Outcome | Drops/run | Deaths | Rounds to win | Plays as |", "|---|---|---|---|---|---|---|"]
    lines += [line(l, rt, r) for l, _, rt, r in rows]
    lines += ["", "**Recommended:** %s (plays as %s)." % (best[0], verdict(best[3]))]
    if a.ollama:
        with local_model(a.llm_url, a.model, a.reasoning) as (model, server):
            for label, v in (("as built", sc), (best[0], best[1])) if best[0] != "as built" else (("as built", sc),):
                r = simulate_model(v, list(range(1, a.ollama + 1)), a.rounds, model)
                rows.append(("%s, %s" % (label, model), v, rate(v, stats, len(members), a.level), r))
                calls = "; model calls %d (%d failed)" % (r["calls"], r["failures"]) if a.llm_url else ""
                lines.append("Local model (%s, %s), %d runs, %s: %d won, %d lost, %d out of rounds; %.1f drops/run, "
                             "%d deaths%s. Plays as %s." % (model, server, r["runs"], label, r["won"], r["lost"],
                                                          r["timeout"], r["drops_per_run"], r["dead"], calls, verdict(r)))
    issues = sum(r["issues"] for *_, r in rows)
    stuck = sum(r.get("stuck", 0) for *_, r in rows)
    if stuck:   # 2026-10-15: a monster that never moves makes every fight a stalemate; the ratings above are not real
        lines += ["", "**Warning:** a monster could not get closer on %d turns (boxed in at its start square?); fights "
                      "that time out with no drops are a stalemate, not a difficulty. Check the start squares." % stuck]
    import sim_coverage   # v0.8.6 AUDIT-07: the ratings exclude what the simulator does not resolve
    cov = sim_coverage.summary_line(sc)
    if cov:
        lines += ["", cov]
    lines += ["", "Simulator problems across all runs: %d (stalls, refused actions, wall crossings)." % issues,
              "Proposal only: nothing is changed in the adventure until the GM approves."]
    text = "\n".join(lines) + "\n"
    print("\n" + text)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
