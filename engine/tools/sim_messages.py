"""SIM-MSG-01 (2026-10-18): state / action / result messages from a real simulator run, for the visual prototype
(GM: "can I get a current, fresh snapshot and sample state, action and result messages. We can start the visual
prototype now; integration should use the current engine"). Read-only: it runs the current engine and records what
happens; the format is described in docs/development/SIM_MESSAGES.md.

  py tools\\sim_messages.py sim\\scenarios\\test\\lab_underwater.json --level 8 --items --members Hero 1,Hero 5,Hero 6,Hero 2
        [--rounds 2] [--seed 1] [--out docs\\development\\sim_messages_sample.json]
"""
import argparse, copy, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "sim"), str(ROOT / "mythastria_core")]
FORMAT = "sim-messages/1"
RESULT_KINDS = ("dice", "turn", "feat", "tactic", "stop", "error", "chat", "players")


def map_part(sc):
    """The static map: size, walls and doors (squares; walls on square edges), zones, lighting."""
    pts = [p for w in sc.get("walls") or [] for p in w["points"]]
    zx = [v for z in sc.get("zones") or [] for v in (z["rect"][0], z["rect"][2])]
    zy = [v for z in sc.get("zones") or [] for v in (z["rect"][1], z["rect"][3])]
    cx = [c["x"] for c in sc["combatants"]] + [w[0] for w in sc.get("wall_cells") or []]
    cy = [c["y"] for c in sc["combatants"]] + [w[1] for w in sc.get("wall_cells") or []]
    cols = int(max([p[0] + 0.5 for p in pts] + [v + 1 for v in zx + cx] + [1]))
    rows = int(max([p[1] + 0.5 for p in pts] + [v + 1 for v in zy + cy] + [1]))
    return {"name": sc.get("map_name", sc.get("name", "")), "cols": cols, "rows": rows, "square_ft": sc.get("units", 5),
            "walls": [dict({"id": str(w["id"]), "points": w["points"], "door": bool(w.get("door")),
                       "open": str(w["id"]) in [str(d) for d in sc.get("open_doors") or []]},
                           **({"natural": True} if w.get("natural") else {})) for w in sc.get("walls") or []],   # REGION-01: trees, rocks
            "zones": copy.deepcopy(sc.get("zones") or []),
            "lighting": copy.deepcopy(sc.get("lighting") or {"ambient": "bright", "lights": []}),
            # 2026-10-19 (GM): each room's ceiling (feet, None = open sky) and its description, from the map spec
            "ceilings": copy.deepcopy(sc.get("ceilings") or []),
            # 2026-10-19 (GM: decor "made to fit the story"): props drawn only (kind, x, y squares, rot, label)
            "props": copy.deepcopy(sc.get("props") or []),
            # VIEW-01 (2026-10-20): an imported map's picture, drawn under the grid ({"src", "cols", "rows"})
            "background": copy.deepcopy(sc.get("background")),
            # MAP RULE (GM 2026-10-20): walls at least one square thick; these squares are drawn as stone (display only:
            # the wall lines still decide movement and sight)
            "wall_cells": copy.deepcopy(sc.get("wall_cells") or []),
            # REGION-01 (GM 2026-10-20): a terrain battle's ground (grass, forest, dry, stone, mud, sand) and its road squares
            "ground": sc.get("ground"), "ground_cells": copy.deepcopy(sc.get("ground_cells") or {})}


def space_of(c):
    """The creature's space in feet as the rules count it (lighting.space_ft: the 2024 size table; FG's 3.75 counts as
    5). 2026-10-20: was int(space), which made a Small goblin 3 ft, so the table refused its 5-ft art."""
    import lighting
    ft = lighting.space_ft(c.get("size"), c.get("space"))
    return int(ft) if ft == int(ft) else ft


def state(sim, round_no, active):
    """Everything that can change during a fight, for every combatant."""
    g, env, gm = sim.S, sim.env, sim.gm_rules
    out = []
    for c in sim.sc["combatants"]:
        i = c["id"]
        x, y = env.pos(i)
        wounds = int(g.getField(i, "wounds"))
        conds = sorted((gm.cond.get(i) or {}).keys()) if gm else []
        entry = {"id": i, "name": c["name"], "side": c.get("side"), "pc": bool(c.get("pc")), "x": x, "y": y,
                 "space_ft": space_of(c), "hp": max(0, int(c["hp"]) - wounds), "hp_max": int(c["hp"]),
                 "ac": g.ac_now(i) if hasattr(g, "ac_now") else c.get("ac"),   # AC-SHOWN-01: Shield, Barkskin too
                 "down": bool(sim.down(i)), "conditions": conds,
                 "underwater": env.underwater(i), "aloft": env.aloft(i), "mount": env.mount_of(i) if c.get("mount") else None,
                 # 2026-10-19 (GM: "flying creatures should appear elevated"): a Fly Speed it can use right now
                 "fly_ft": env.fly_speed(i), "flying": bool(env.can_fly_now(i))}
        why = g.ac_why(i) if hasattr(g, "ac_why") else []
        if why:
            entry["ac_why"] = why                                # AC-SHOWN-01: why it differs from the sheet's AC
        if c.get("pc"):
            st = (sim.party.deaths.get(i) if sim.party else None) or {}
            entry.update(level=c.get("level"), dead=bool(st.get("dead")), stable=bool(st.get("stable")),
                         death_saves={"successes": st.get("successes", 0), "failures": st.get("failures", 0)},
                         breath_rounds=env.breath.get(i), exhaustion=env.exhaustion.get(i, 0),
                         temp_hp=int(g.getField(i, "sim_temp_hp")))
            if getattr(sim, "hazards", None):                    # HAZARDS-01: Exhaustion's effects, contagions, stress
                entry["afflictions"] = sim.hazards.afflictions(i)
        out.append(entry)
    st = {"type": "state", "round": round_no, "active": active, "combatants": out}
    if sim.walls:                                                # 2026-10-18: doors opened during play
        st["open_doors"] = sorted(str(d) for d in sim.walls.get("open_doors", []))
    return st


def diff(before, after):
    """What changed for each combatant between two states."""
    old = {c["id"]: c for c in before["combatants"]}
    changes = []
    for c in after["combatants"]:
        o = old.get(c["id"], {})
        d = {k: [o.get(k), v] for k, v in c.items() if k not in ("name", "side", "pc") and o.get(k) != v}
        if d:
            changes.append({"id": c["id"], "name": c["name"], "changed": d})
    return changes


def plain(v):
    """JSON-safe copy of a bridge decision record."""
    if isinstance(v, dict):
        return {str(k): plain(x) for k, x in v.items() if not str(k).startswith("_")}
    if isinstance(v, (list, tuple)):
        return [plain(x) for x in v]
    return v if isinstance(v, (str, int, float, bool)) or v is None else str(v)


def record(scenario, members, level, items, rounds, seed, extra=None):
    """members empty: the scenario's own characters (no pregens swapped in). extra: saved characters' builds (GM
    2026-10-28: the Simulator fights page fights with the Saved characters tab), each at its own level."""
    import encounter_tuner, run_sim
    raw = json.loads(Path(scenario).read_text(encoding="utf-8"))
    party = list(members) + list(extra or {})
    sc = encounter_tuner.with_party(raw, party, level, items=items, extra=extra or None) if party else copy.deepcopy(raw)
    sim = run_sim.Sim(sc, "scripted", True, seed, True, True)
    by_name = {c["name"]: c["id"] for c in sim.sc["combatants"]}
    turns, lines, seen_dec = [], [], set()
    real_say = sim.say

    def say(kind, text):
        real_say(kind, text)
        text = str(text)
        if kind == "turn" and text.endswith("'s turn") and text[:-7] in by_name:
            g = sim.S
            turns.append({"actor": by_name[text[:-7]], "round": int(g.round()), "at": len(lines),
                          "state": state(sim, int(g.round()), by_name[text[:-7]]), "decisions": []})
        lines.append((kind, text))
        pending = sim.decision()
        if turns and isinstance(pending, dict) and pending.get("status") in ("ready", "running", "error"):
            key = (pending.get("seq"), pending.get("summary"), pending.get("choice"), pending.get("target"))
            if key not in seen_dec and pending.get("source", "").endswith(turns[-1]["actor"]):
                seen_dec.add(key)
                turns[-1]["decisions"].append(plain(pending))

    sim.say = say
    sim.S.say = say          # the fake FG keeps its own reference (set when the Sim starts)
    try:
        sim.run(rounds, 20)
        g = sim.S
        final = state(sim, int(g.round()), None)
    finally:
        sim.close()
    msgs = [{"type": "scenario", "format": FORMAT, "source_scenario": Path(scenario).name,
             "party": members or [c["name"] for c in sim.sc["combatants"] if c.get("pc")],
             "level": level if members else None, "items": items, "seed": seed, "rounds": rounds, "map": map_part(sim.sc)}]
    for k, t in enumerate(turns):
        nxt = turns[k + 1] if k + 1 < len(turns) else None
        end = nxt["at"] if nxt else len(lines)
        after = nxt["state"] if nxt else final
        c = sim.by_id(t["actor"])
        gm_said = ("the simulator as GM", "is a controlled mount", "lies dormant")
        controller = ("party script" if c.get("pc") and sim.party else
                      "player script" if c.get("pc") else
                      "simulator GM" if any(any(p in x for p in gm_said) for _, x in lines[t["at"]:end]) else "bridge AI")
        msgs.append(t["state"])
        msgs.append({"type": "action", "round": t["round"], "actor": t["actor"], "actor_name": c["name"],
                     "controller": controller, "decisions": t["decisions"],
                     "intent": [x for kd, x in lines[t["at"] + 1:end] if kd == "tactic"]})
        res = {"type": "result", "round": t["round"], "actor": t["actor"],
               "log": [{"kind": kd, "text": x} for kd, x in lines[t["at"] + 1:end] if kd in RESULT_KINDS],
               "changes": diff(t["state"], after)}
        if t["state"].get("open_doors") != after.get("open_doors"):
            res["map_changes"] = {"open_doors": [t["state"].get("open_doors"), after.get("open_doors")]}
        msgs.append(res)
    msgs.append(final)
    return msgs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("scenario"); ap.add_argument("--level", type=int, default=5)
    ap.add_argument("--members", default="Hero 1,Hero 3,Hero 2,Hero 4"); ap.add_argument("--items", action="store_true")
    ap.add_argument("--rounds", type=int, default=2); ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default=str(ROOT / "docs" / "development" / "sim_messages_sample.json"))
    ap.add_argument("--note", default="", help="a line for the scenario message: how the recording was set up")
    ap.add_argument("--extra", help="a JSON file of saved characters' builds ({name: build}) that join the party")
    a = ap.parse_args(argv)
    extra = json.loads(Path(a.extra).read_text(encoding="utf-8")) if a.extra else None
    msgs = record(a.scenario, [m for m in a.members.split(",") if m], a.level, a.items, a.rounds, a.seed, extra)
    if a.note:
        msgs[0]["note"] = a.note
    Path(a.out).write_text(json.dumps(msgs, indent=1) + "\n", encoding="utf-8")
    print("wrote %s: %d messages (%d turns)" % (a.out, len(msgs), sum(m["type"] == "action" for m in msgs)))


if __name__ == "__main__":
    main()
