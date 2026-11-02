"""v0.7.89 PRACTICE-TWIN-01: a saved fight (mythastria_core/fight_snapshot.py) -> a simulator scenario that continues it
from the saved turn, plus the reviewable report of the practice run.

Everything the fake FG cannot resolve is listed before the run:
- "blocking" (per combatant): the run stops with a "not simulated" message when that combatant's turn comes
  (its spells, save/effect actions, unreadable Multiattack, its own active effects);
- "targets" (per combatant): the run stops when a creature hostile to it takes a turn (its effects, temporary HP);
- "ignored": listed only (traits without rolls, a weapon's second attack form the extension never uses in FG either).
A player character dropping to 0 HP also stops the run (death saving throws are not simulated).
Nothing is written back to Fantasy Grounds."""
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mythastria_core"))
import ai_turn            # noqa: E402
import fight_snapshot     # noqa: E402
import map_walls          # noqa: E402

SIG = "parseNPCPower(nodePower,false)"
BRANCH = re.compile(r"\.(actions|spells|innatespells|traits|bonusactions|reactions|legendaryactions|lairactions)\.[^.]+$")
BRANCH_LABEL = {"traits": "trait", "bonusactions": "bonus action", "reactions": "reaction",
                "legendaryactions": "legendary action", "lairactions": "lair action"}
NO_WRITE_BACK = ("Practice run only: nothing was written back to Fantasy Grounds and the real fight is unchanged. "
                 "Moving these results into FG would be a separate step the GM reviews and approves (not available yet).")


def _num(value, label):
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise ValueError("%s is missing or not a number" % label)
    return int(n) if n.is_integer() else n


def _groups(record):
    groups = {}
    for f in (record.get("attempts", {}).get(SIG) or {}).get("fields", []):
        m = re.fullmatch(r"return1\.(\d+)\.(.+)", f.get("key", ""))
        if m:
            groups.setdefault(int(m[1]), {})[m[2]] = f.get("value")
    return [groups[i] for i in sorted(groups)]


def _attack(name, groups):
    """The first parsed attack and the damage after it (what the extension's PARSED_ATTACK uses in FG).
    Returns (action fields, ignored notes) or raises ValueError with the reason it cannot be simulated."""
    first = next(i for i, g in enumerate(groups) if g.get("type") == "attack")
    attack = groups[first]
    damage = next((g for g in groups[first + 1:] if g.get("type") == "damage"), None)
    extra = sorted({g.get("type") for g in groups} - {"attack", "damage"})
    if extra:
        raise ValueError("%s also has %s parts (riders) the practice run cannot resolve" % (name, ", ".join(extra)))
    if damage is None:
        raise ValueError("%s: FG parsed no damage" % name)
    typ = str(attack.get("atktype") or "").lower()
    if typ not in ("melee", "ranged"):
        raise ValueError("%s: unknown attack type" % name)
    clauses = {m[1] for k in damage for m in [re.match(r"clauses\.(\d+)\.", k)] if m}
    if len(clauses) != 1:
        raise ValueError("%s: damage with %d parts is not simulated" % (name, len(clauses)))
    c = clauses.pop()
    dice = [v for k, v in sorted(damage.items()) if re.fullmatch(r"clauses\.%s\.dice\.\d+" % c, k)]
    if not dice or len(set(dice)) != 1 or not re.fullmatch(r"d\d+", str(dice[0])):
        raise ValueError("%s: mixed damage dice are not simulated" % name)
    mod = _num(attack.get("modifier"), name + " attack bonus")
    bonus = _num(damage.get("clauses.%s.modifier" % c) or 0, name + " damage bonus")
    reach = _num(attack.get("rangedist") or 5, name + " reach")
    notes = []
    if sum(1 for g in groups if g.get("type") == "attack") > 1:
        notes.append("%s: only its first attack form (%s) is used, as the extension does in FG" % (name, typ))
    return ({"atk": int(mod), "atktype": typ, "reach": reach, "dmg": "%d%s%+d" % (len(dice), dice[0], int(bonus)),
             "dmgtype": str(damage.get("clauses.%s.dmgtype" % c) or "")}, notes)


def npc_actions(ctpath, name, records):
    """FG's parsed records of one NPC -> (actions for the fake FG, blocking reasons, ignored notes)."""
    actions, blocking, ignored, seen = [], [], [], set()
    mine = sorted((r for r in records.values() if r.get("ctpath") == ctpath),
                  key=lambda r: (not (r.get("node_path") or "").startswith(ctpath + "."), r.get("node_path") or ""))
    for rec in mine:
        path, power = rec.get("node_path") or "", rec.get("power_name") or "(unnamed)"
        m = BRANCH.search(path)
        if not m or power.lower() in seen:
            continue
        seen.add(power.lower())
        branch, groups = m[1], _groups(rec)
        types = {g.get("type") for g in groups if g.get("type")}
        ok = (rec.get("attempts", {}).get(SIG) or {}).get("ok") == "1"
        if branch in ("spells", "innatespells"):
            (blocking if types else ignored).append("%s: spell %s%s" % (
                name, power, " (spells are not simulated yet)" if types else " (no rolls FG can parse)"))
        elif branch != "actions":
            ignored.append("%s: %s %s not applied%s" % (name, BRANCH_LABEL.get(branch, branch), power,
                                                        " (it has rolls)" if types else ""))
        elif power.lower().startswith("multiattack"):
            actions.append({"name": power, "desc": rec.get("description") or ""})
        elif not ok or not types:
            ignored.append("%s: action %s has no rolls FG can parse (the AI cannot use it in FG either)" % (name, power))
        elif "attack" not in types:
            blocking.append("%s: action %s (%s) is not simulated" % (name, power, ", ".join(sorted(types))))
        else:
            try:
                fields, notes = _attack(power, groups)
            except ValueError as error:
                blocking.append("%s: %s" % (name, error)); continue
            actions.append(dict(fields, name=power, desc=""))
            ignored += ["%s: %s" % (name, n) for n in notes]
    for i, a in enumerate(actions):
        a["id"] = "id-%05d" % (i + 1)
    attacks = {a["name"]: a["atktype"] for a in actions if "atk" in a}
    for a in actions:
        if "atk" not in a and ai_turn.parse_multiattack(a["desc"], attacks) is None:
            blocking.append("%s: %s wording needs the model's reading and the GM's approval (not in practice runs yet)"
                            % (name, a["name"]))
    if not attacks and not blocking:
        ignored.append("%s has no attack the AI can use" % name)
    return actions, blocking, ignored


def pc_weapon(name, sheet):
    """A linked PC's equipped melee weapon from the synced sheet, with FG's numbers (ability + proficiency + bonus).
    Raises ValueError when the sheet has nothing this simple adapter supports."""
    if not sheet:
        raise ValueError("%s: sheet not synced" % name)
    core = sheet.get("core", {})
    for w in sheet.get("weapons", {}).values():
        if str(w.get("carried")) != "2" or str(w.get("type")) != "0":
            continue
        f = {k: (v.get("value") if isinstance(v, dict) else v) for k, v in (w.get("fields") or {}).items()}
        props = {p.strip().lower() for p in str(w.get("properties") or "").split(",") if p.strip()}
        clauses = {}
        for k, v in f.items():
            m = re.fullmatch(r"damagelist\.([^.]+)\.([^.]+)", k)
            if m:
                clauses.setdefault(m[1], {})[m[2]] = v
        if len(clauses) != 1 or _num(f.get("bonus") or 0, "weapon bonus") != 0 \
                or _num(f.get("criticalrange") or 20, "critical range") != 20:
            continue
        clause = next(iter(clauses.values()))
        dice = [d.strip() for d in str(clause.get("dice") or "").split(",") if d.strip()]
        if not dice or len(set(dice)) != 1 or not re.fullmatch(r"d\d+", dice[0]) \
                or str(clause.get("statmult") or "1") != "1":
            continue
        stat = lambda s: "dexterity" if s == "dexterity" else "strength"
        mods = {"strength": _num(core.get("strmod"), name + " STR modifier"),
                "dexterity": _num(core.get("dexmod"), name + " DEX modifier")}
        best = max(mods, key=mods.get) if "finesse" in props else "strength"
        atk_stat = best if f.get("attackstat", "") in ("", "base") else stat(f.get("attackstat"))
        dmg_stat = best if clause.get("stat", "") in ("", "base") else stat(clause.get("stat"))
        prof = _num(core.get("profbonus"), name + " proficiency") if str(w.get("prof")) == "1" else 0
        atk = mods[atk_stat] + prof + _num(f.get("attackbonus") or 0, "attack bonus")
        bonus = mods[dmg_stat] + _num(clause.get("bonus") or 0, "damage bonus")
        if bonus < 0:
            continue   # the scripted player attack takes "NdX+B" only
        reach = 10 if "reach" in props else 5
        return {"name": w.get("name") or "weapon", "atk": int(atk), "reach": reach,
                "dmg": "%d%s+%d" % (len(dice), dice[0], int(bonus))}
    raise ValueError("%s: no equipped melee weapon this practice run can roll" % name)


def to_scenario(snap, pcs="pass"):
    """A saved fight -> a run_sim scenario that resumes at the saved turn. pcs: "pass" (players stand still and end
    their turn) or "attack" (they attack the nearest foe in reach with their equipped melee weapon, without moving)."""
    if snap.get("kind") != fight_snapshot.KIND:
        raise ValueError("not a saved fight")
    actors = snap.get("combatants") or {}
    if not actors:
        raise ValueError("the saved fight has no combatants")
    maps = {(a.get("raw_fields") or {}).get("pos.map") for a in actors.values()}
    if None in maps or "" in maps:
        raise ValueError("a combatant has no token on a map: place every token, then save again")
    if len(maps) != 1:
        raise ValueError("combatants are on different maps")
    fg_map = maps.pop()
    space, walls = snap.get("space") or {}, snap.get("walls")
    if walls and walls.get("fg_map") != fg_map:
        walls = None
    grid = float(space.get("grid") or 0) if space.get("map") in (None, "", fg_map) else 0
    grid_h = float(space.get("grid_h") or 0) or grid
    if not grid and walls and walls.get("gridsize"):
        grid, grid_h = (float(v) for v in walls["gridsize"])
    if grid <= 0 or grid_h <= 0:
        raise ValueError("the map's grid size is unknown: let FG start one turn on this map, then save again")
    units = float(space.get("units") or 5)
    diag = {"1.5": 1.5, "*": "*"}.get(str(space.get("diag")), 1)
    sim_grid = grid if abs(grid - grid_h) < 1e-6 else 1000   # rectangular cells: square simulator cells
    cells = lambda x, y: (round(x / grid, 4), round(y / grid_h, 4))
    sheets, records = snap.get("sheets") or {}, snap.get("parser") or {}
    practice = {"blocking": {}, "targets": {}, "ignored": [], "map": fg_map}
    sc = {"name": "Practice run from a saved fight", "policy": "local_only", "grid": sim_grid, "units": units,
          "diag": diag, "map_name": (walls or {}).get("map") or space.get("mapname") or "Saved map",
          "approve_plans": False, "combatants": [], "practice": practice,
          "source_grid": {"width": grid, "height": grid_h},
          "aware": [p.rsplit(".", 1)[-1] for p in (snap.get("awareness") or {}).get("aware") or []],
          "perception_dc": (snap.get("awareness") or {}).get("perception_dc") or 15}
    for ctpath, a in actors.items():
        cid, name, raw = ctpath.rsplit(".", 1)[-1], a.get("name") or ctpath, a.get("raw_fields") or {}
        link = a.get("actor_link") or {}
        pc = link.get("class") == "charsheet"
        side = "friend" if pc else a.get("friend_foe")
        if side not in ("friend", "foe"):
            raise ValueError("%s has no faction: set friend or foe in the Combat Tracker, then save again" % name)
        hp = _num(a.get("hp_total"), name + " HP")
        wounds = min(hp, max(0, _num(a.get("wounds") or 0, name + " wounds")))
        x, y = cells(_num(raw.get("pos.x"), name + " x"), _num(raw.get("pos.y"), name + " y"))
        effects = [e.get("label", "") for e in a.get("effects") or [] if str(e.get("active", "1")) != "0"]
        own = ["%s: effect %s is not simulated" % (name, e) for e in effects]
        temp = _num(a.get("temporary_hp") or 0, name + " temporary HP")
        if temp:
            own.append("%s: %s temporary HP are not simulated" % (name, temp))
        if own:
            practice["targets"][cid] = list(own)
            if not pc or pcs == "attack":   # a player character that only passes never uses its own effects
                practice["blocking"].setdefault(cid, []).extend(own)
        try: init_bonus = _num(raw.get("init") or 0, "init")
        except ValueError: init_bonus = 0
        c = {"id": cid, "name": name, "pc": pc, "side": side, "hp": hp, "wounds": wounds,
             "ac": _num(raw.get("ac"), name + " AC"), "init": _num(a.get("initiative") or 0, name + " initiative"),
             "init_bonus": init_bonus, "x": x, "y": y, "speed": str(raw.get("speed") or "30"),
             "space": _num(raw.get("space") or 5, name + " space"), "reach": _num(raw.get("reach") or 5, name + " reach"),
             "reaction": 1 if str(raw.get("reaction") or "0") == "1" else 0, "senses": raw.get("senses") or "",
             "effects": [{"label": e} for e in effects],
             "source_position": {"x": raw.get("pos.x"), "y": raw.get("pos.y"), "map": fg_map}}
        if pc:
            if pcs == "attack":
                try:
                    c["weapon"] = pc_weapon(name, sheets.get(link.get("recordname")))
                    c["script"] = {"*": ["attack"]}
                except ValueError as error:
                    practice["ignored"].append("%s; this player character stands still and passes" % error)
        else:
            c["actions"], blocking, ignored = npc_actions(ctpath, name, records)
            practice["blocking"].setdefault(cid, []).extend(blocking)
            practice["ignored"] += ignored
        sc["combatants"].append(c)
    practice["blocking"] = {k: v for k, v in practice["blocking"].items() if v}
    if walls:
        def pt(p):
            return list(cells(*map_walls.placed(walls, p)))
        sc["walls"] = [{"id": o["id"], "door": bool(o.get("door")), "closed": bool(o.get("closed")),
                        "points": [pt(p) for p in o["points"]]} for o in walls.get("occluders") or []]
        sc["open_doors"] = list(walls.get("open_doors") or [])
        lit = map_walls.lighting(walls)
        if lit:
            lights = []
            for l in lit["lights"]:
                item = {"bright_ft": l["bright_ft"], "dim_ft": l["dim_ft"]}
                if l.get("carrier"):
                    item["carrier"] = l["carrier"].rsplit(".", 1)[-1]
                else:
                    item["x"], item["y"] = cells(*l["pos"])
                lights.append(item)
            sc["lighting"] = {"ambient": lit["ambient"], "lights": lights}
    else:
        practice["ignored"].append("No confirmed walls for this map: the practice run has no walls or lighting")
    active = snap.get("active")
    if active not in actors:
        raise ValueError("no combatant is active in FG: start a turn in the Combat Tracker, then save again")
    prog = snap.get("turn_progress") or {}
    started = prog.get("moved_ft") or prog.get("bonus_used") or prog.get("slot_used") or prog.get("multi_done")
    active_pc = (actors[active].get("actor_link") or {}).get("class") == "charsheet"
    sc["resume"] = {"active": active.rsplit(".", 1)[-1], "round": int(snap.get("round") or 1),
                    "skip_current": bool(started) and not active_pc}
    if sc["resume"]["skip_current"]:
        practice["ignored"].append("%s's turn was already under way in FG; the practice run starts with the next "
                                   "combatant" % actors[active].get("name"))
    return sc


def not_simulated_lines(sc):
    p = sc.get("practice") or {}
    names = {c["id"]: c["name"] for c in sc["combatants"]}
    out = []
    for cid, reasons in sorted(p.get("blocking", {}).items()):
        out += ["STOPS the run at %s's turn: %s" % (names.get(cid, cid), r.split(": ", 1)[-1]) for r in reasons]
    for cid, reasons in sorted(p.get("targets", {}).items()):
        out += ["STOPS the run when a creature hostile to %s takes its turn: %s" % (names.get(cid, cid), r.split(": ", 1)[-1])
                for r in reasons]
    out += ["Ignored: " + r for r in p.get("ignored", [])]
    out.append("STOPS the run if a player character drops to 0 HP (death saving throws are not simulated)")
    return out


def report(sim, snap_name, snap, rounds, model):
    """The reviewable markdown report of a practice run."""
    sc, s = sim.sc, sim.S
    res = sc["resume"]
    first = next(c["name"] for c in sc["combatants"] if c["id"] == res["active"])
    g = sc["source_grid"]
    out = ["# Practice run: %s" % sc.get("map_name"), "", "> " + NO_WRITE_BACK, "",
           "- Saved fight: `%s` (taken %s, bridge v%s)" % (snap_name, snap.get("taken"), snap.get("bridge_version")),
           "- Continued from round %d, %s's turn%s; up to %d full round(s), back to that turn." % (
               res["round"], first, " (already under way in FG: started with the next combatant)" if res["skip_current"]
               else "", rounds),
           "- NPCs: the AI in Autopilot (%s). Player characters: %s." % (
               "scripted chooser" if model == "scripted" else model,
               "attack the nearest foe in reach without moving" if any(c.get("script") for c in sc["combatants"])
               else "stand still and pass"),
           "- Seed %s; dice by the simulator, not FG." % sc.get("_seed"), ""]
    if sim.stopped:
        out += ["**Stopped: not simulated.** %s" % sim.stopped, ""]
    elif sim.side_down("foe") or sim.side_down("friend"):
        out += ["**Finished:** one side is down.", ""]
    else:
        out += ["**Finished:** the round limit was reached.", ""]
    out += ["## Not simulated (listed before the run)", ""] + ["- " + l for l in not_simulated_lines(sc)] + [""]
    out += ["## Turns", ""]
    keep = ("dice", "turn", "feat", "stop", "error", "players", "move")
    last, rnd = res["round"] + rounds, res["round"]
    for kind, text in sim.lines:
        if kind == "chat" and re.search(r" moves \d+ ft\.$|searches for enemies|notices", text):
            kind = "turn"
        if kind not in keep or text.startswith("startup sync done"):
            continue
        if kind == "turn" and rnd == last and text == first + "'s turn":
            break       # back to the saved combatant: N full rotations played
        if kind == "turn" and text.startswith("--- round"):
            rnd = int(re.sub(r"\D", "", text) or 0)
            if rnd > last:
                break   # the round limit: the next round is not played
            out += ["", "### " + text.strip("- ").capitalize(), ""]
        elif kind == "turn" and text.endswith("'s turn"):
            out.append("- **%s**" % text)
        elif kind == "players":
            out.append("  - narration posted to the players: %s" % text)
        else:
            out.append("  - %s%s" % ("" if kind in ("dice", "turn", "move") else kind.upper() + ": ", text))
    out += ["", "## Final state", "",
            "| Combatant | HP left | Square (x, y) | FG token position | Moved |", "|---|---|---|---|---|"]
    for c in sc["combatants"]:
        w, hp, x, y, _ = s.state(c["id"])
        moved = "yes" if (round(x, 3), round(y, 3)) != (round(c["x"], 3), round(c["y"], 3)) else "no"
        out.append("| %s | %d/%d | (%g, %g) | (%g, %g) | %s |" % (c["name"], hp - w, hp, x, y,
                                                               round(x * g["width"], 1), round(y * g["height"], 1), moved))
    out += ["", "Stalls: %d. Problems: %d." % (sim.stalls, len(sim.problems))] + ["- " + p for p in sim.problems[:20]]
    if sim.walls:
        out.append("Wall crossings (steps or attacks): %d." % sim.wall_crossings)
    out += ["", NO_WRITE_BACK, ""]
    return "\n".join(out)
