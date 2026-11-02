"""HINTS-01 step H1 (GM 2026-10-22: "I liked the idea of suggested turns, but not sure if they can be reassuring to
experienced players"; then "Hints are opt-in"): the reminders a player can switch on for their own screen.
Design: docs/development/LLM_PLAYTESTER_AND_HINTS.md part 2, "Reminders". No language model.

Always right or silent: every reminder is read from the offers the sheet already gets, which the same checks act()
makes have built (attack_check, LiveSpells.check_common / check_creature, LiveActions.check). So a reminder shows
exactly when the engine would accept the matching choice now, and says nothing otherwise. Reminders name what is
possible, never which one to take.

- action: the Action is unused and some Action choice is legal now (or attacks of the Attack action are left);
- bonus: the Bonus Action is free, with the names of its legal choices (the class resources go under `resources`);
- movement: feet of movement left while a square can be reached;
- slot: a spell slot was spent this turn and a levelled spell is refused for that alone (One Spell with a Spell Slot
  per Turn);
- resources: Second Wind, Rage, Lay On Hands usable right now, with their uses or pool;
- concentration: on each Concentration spell's card while one is held: casting it ends the held one;
- sneak (H6): Sneak Attack not used this turn while an attack in reach would add it.

Facts (H4, H5, H6; GM 2026-10-29: Advantage and Disadvantage and why, never a chance to hit, an attack bonus or an
Armor Class), shown on hover:
- attacks: for each attack and legal target, Advantage or Disadvantage and why, from the roll's own checks asked
  without rolling (Party.mode_parts and FightState.roll_mode with peek), and whether Sneak Attack applies;
- reach: the squares a move can end on inside a foe's reach, and the foes that may make an Opportunity Attack on the
  way there (creature_turns.on_step's own test at each step of the route the move takes);
- area_inside: who an area spell aimed at a square would catch now (the cast's own shape code), asked while aiming
  (tools/sim_service.py /api/live/aim).

Who sees them: only the seat that plays the acting character, and only at the Reminders level (tools/table_seats.py
player_view cuts `hints` for every other seat and for a seat at Off; every seat starts at Off; seen_offers keeps only
the creatures that seat sees).
"""
import math

KINDS = ("action", "bonus", "movement", "slot", "resources", "concentration", "sneak", "attack", "reach", "area")
RESOURCES = ("second_wind", "rage", "lay_on_hands", "innate_sorcery")


def _plural(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


def _legal(entry):
    """An offered choice the engine accepts now: ready, and with a creature to aim at when it needs one."""
    return bool(entry.get("ready")) and ("targets" not in entry or bool(entry["targets"]))


def _names(names):
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _able(fight, me):
    import live_actions
    try:
        fight.actions.able(me)                                   # its turn, not down, not Incapacitated
        return True
    except live_actions.ActionError:
        return False


def _can_hide(fight, me):
    """Hide's own check (no enemy sees the character without cover), which the offers run only for the Action."""
    import live_actions
    try:
        fight.actions.hide_check(me)
        return True
    except live_actions.ActionError:
        return False


def reminders(fight, offers):
    """The `hints` block for the waiting character's offers: {"line": [{kind, text, ...}], "spells": {name: [...]}}.
    `line` is what the End turn line shows, in this order; `spells` the warnings on spell cards."""
    me, t, party = offers["actor"], fight.turn_state, fight.sim.party
    line, cards = [], {}
    spells = offers.get("spells") or []
    acts = {a["op"]: a for a in offers.get("actions") or []}

    # the Action: unused, and something legal to spend it on now
    if not offers["action_used"]:
        legal = [a["name"] for a in offers["attacks"] if a["targets"]]
        legal += [s["name"] for s in spells if s["time"] == "action" and _legal(s)]
        legal += [a["label"] for op, a in acts.items() if op not in RESOURCES and _legal(a)
                  and a.get("time", "action") == "action" and (op != "ready" or a.get("weapons"))]
        if legal:
            line.append({"kind": "action", "text": "Your Action is still unused."})
    elif offers["attacks_left"] > 0 and (any(a["targets"] for a in offers["attacks"])
                                         or any(_legal(acts[op]) for op in ("grapple", "shove") if op in acts)):
        n = offers["attacks_left"]
        line.append({"kind": "action", "text": "%s of your Attack action left." % ("1 attack" if n == 1 else "%d attacks" % n)})

    # the Bonus Action: its legal choices by name (Cunning Action grouped), class resources separately
    cunning = [a["label"] for op, a in acts.items() if op in ("dash", "disengage", "hide") and a.get("bonus")
               and (op != "hide" or _can_hide(fight, me))]
    names = (["Cunning Action (%s)" % ", ".join(cunning)] if cunning else [])
    names += [s["name"] for s in spells if s["time"] == "bonus" and _legal(s)]
    if names:
        line.append({"kind": "bonus", "text": "Bonus Action free: %s." % ", ".join(names), "names": names})

    if offers["movement"] > 0 and offers.get("reach"):
        line.append({"kind": "movement", "text": "%d ft of movement left." % offers["movement"], "ft": offers["movement"]})

    # One Spell with a Spell Slot per Turn: the spells refused for that reason alone (LiveSpells.check_common checks
    # it last: the caster is able, the spell's casting time is free and a slot of its level is left)
    if spells and party.slot_turn.get(me) == party.s.turnSerial and _able(fight, me):
        pool = offers.get("slots") or []
        waiting = [s["name"] for s in spells if not s["ready"]
                   and (not t["action_used"] if s["time"] == "action" else party.bonus_free(me))
                   and sum(pool[s["level"] - 1:]) > 0]
        if waiting:
            line.append({"kind": "slot", "text": "You cast a levelled spell this turn: %s %s until your next turn." % (
                _names(waiting), "waits" if len(waiting) == 1 else "wait"), "spells": waiting})

    # class resources usable now (each a Bonus Action)
    free = []
    for op in RESOURCES:
        a = acts.get(op)
        if a and _legal(a):
            free.append(a["label"] + (" (%d HP in the pool)" % a["pool"] if op == "lay_on_hands"
                                      else " (%s)" % _plural(a.get("uses", 0), "use")))
    if free:
        line.append({"kind": "resources", "text": "Still free (Bonus Action): %s." % ", ".join(free)})

    # Concentration: casting another Concentration spell ends the one held
    held = offers.get("concentrating")
    if held:
        for s in spells:
            if s.get("moves") and s.get("ready"):                    # Hex / Hunter's Mark: its creature dropped
                cards[s["name"]] = [{"kind": "concentration", "text": "Moving it keeps your Concentration."}]
            elif s.get("concentration") and s.get("ready"):
                text = ("Casting %s again ends your current %s." % (s["name"], held) if s["name"] == held
                        else "Casting %s ends your %s." % (s["name"], held))
                cards[s["name"]] = [{"kind": "concentration", "text": text}]

    facts = attack_facts(fight, offers)
    if any(f.get("sneak") for row in facts.values() for f in row.values()):   # H6: Sneak Attack, once per turn
        line.append({"kind": "sneak", "text": "Sneak Attack not used this turn."})
    return {"line": line, "spells": cards, "attacks": facts, "reach": reach_facts(fight, offers)}


def _plain(note):
    return note.strip().strip("[]")


def attack_facts(fight, offers):
    """H5, H6: {attack key: {target: {"mode": "adv" / "dis" / "", "text": ..., "sneak": ...}}} for the legal targets
    with something to say. The same parts Party.attack and FightState._attack combine (live play passes no extra
    Advantage, no Brutal Strike, no grapple retarget), so the hint says what the roll will use."""
    import party as party_mod
    sim, me, t = fight.sim, offers["actor"], fight.turn_state
    p, c = sim.party, sim.by_id(me)
    out, foes = {}, set(p.foes(me))                              # Sneak Attack is named on foes only
    for a in offers.get("attacks") or []:
        w = c.get(a["key"])
        if not isinstance(w, dict):
            continue
        row = {}
        for tid in a["targets"]:
            advs, diss = p.mode_parts(me, tid, w, peek=True)
            roll = {"bADV": bool(advs), "bDIS": bool(diss), "sRange": "R" if w.get("reach", 5) > 10 else "M",
                    "sim_dmgtype": party_mod.damage_type(w), "sim_spell": False}
            adv, dis, _, _, why = sim.S.roll_mode(me, tid, roll, peek=True)
            ya = advs + [_plain(n) for how, n in why if how == "adv"]
            yd = diss + [_plain(n) for how, n in why if how == "dis"]
            both = [_plain(n) for how, n in why if how == "either"]
            off = [_plain(n) for how, n in why if how == "off"]
            mode = "adv" if adv and not dis else "dis" if dis and not adv else ""
            text = ""
            if mode == "adv":
                text = "Advantage: %s." % "; ".join(ya) if ya else "Advantage."      # a note may hold a comma
            elif mode == "dis":
                text = "Disadvantage: %s." % "; ".join(yd) if yd else "Disadvantage."
            elif adv and dis:
                parts = (["Advantage: " + "; ".join(ya)] if ya else []) + (["Disadvantage: " + "; ".join(yd)] if yd else []) \
                    + (["both: " + "; ".join(both)] if both else [])
                text = "Advantage and Disadvantage cancel%s: a plain roll." % (" (%s)" % " / ".join(parts) if parts else "")
            elif off:
                text = "No Advantage: %s." % "; ".join(n.replace(": no Advantage", "") for n in off)
            entry = {"mode": mode, "text": text} if text else {}
            # Sneak Attack as Party.attack adds it: a Finesse or ranged weapon, once per turn, and Advantage on the roll
            # or an ally beside the target, with no Disadvantage on the roll (Party.final_mode: this same mode)
            if c.get("sneak") and not t["sneak_used"] and (w.get("finesse") or party_mod.ranged(w)) and not party_mod.spell_attack(w) and tid in foes:
                if party_mod.sneak_attack_ok(mode, p.ally_next_to(tid, me)):
                    entry["sneak"] = "Sneak Attack applies: %s." % (
                        "Advantage (%s)" % "; ".join(ya) if mode == "adv" and ya else "Advantage" if mode == "adv"
                        else "an ally is beside it")
            if entry:
                row[tid] = entry
        if row:
            out[a["key"]] = row
    return out


def reach_facts(fight, offers):
    """H4: {"foes": {id: reach ft}, "squares": {"x,y": {"near": [ids], "oa": [ids]}}}: for each square a move can end on,
    the foes whose reach it is in (near) and, along the route the move takes there (offers' reach tree, the same
    cheapest-route search the move makes), the foes whose reach a step leaves while they may make an Opportunity Attack
    (oa): creature_turns.on_step's test (a hostile creature the simulator plays, not stopped, its Reaction free, not
    already asked this turn). No oa after Disengage, nor within Tactical Shift's movement. Dash squares get near only.
    None without the simulator's creatures or a foe."""
    import ai_turn, martial_high
    sim, me, t = fight.sim, offers["actor"], fight.turn_state
    ct = getattr(sim, "creatures", None)
    reach, dash = offers.get("reach") or [], offers.get("dash_reach") or []
    if ct is None or not (reach or dash):
        return None
    fs, units = sim.S, sim.sc.get("units", 5)
    g, diag = sim.sc.get("grid", 50), str(sim.sc.get("diag", 1))
    side, msq = ct.side(me), fs.size_squares(me)
    foes = {}
    for r in fs.combatants:
        rside = ct.side(r)
        if r == me or fs.getValue(r, "pc") or not ((rside == "foe" and side == "friend") or (rside == "friend" and side == "foe")):
            continue
        if fs.stopped(r):
            continue
        n = fs._c(r)
        free = fs.num(r, "reaction") == 0 and fs.num(r, "sim_no_oa") == 0 and ct.oa_asked.get((r, me)) != fs.turnSerial
        foes[r] = (n.px, n.py, max(1, math.floor(fs.num(r, "reach", 5) / units + 0.5)), fs.size_squares(r), free)
    if not foes:
        return None

    def near(sq, f):
        return ct._apart(sq[0] * g, sq[1] * g, f[0], f[1], g, msq, f[3], diag) <= f[2]

    calm = ai_turn.disengaged(ct.normalized(sim.by_id(me)))
    crawl = 2 if fight.prone(me) else 1
    shift = martial_high.shift_left(t)
    shifted = min(shift, t["movement"]) // crawl if shift and not t.get("disengaged") else -1
    prev = {(r[0], r[1]): (r[3], r[4]) for r in reach}
    left = {tuple(int(round(v)) for v in sim.party.pos(me)): frozenset()}

    def oa_on(sq):                                               # the foes a step on the way there leaves
        if sq not in left:
            back = prev.get(sq)
            before = oa_on(back) if back is not None else None
            left[sq] = None if before is None else before | {r for r, f in foes.items() if f[4] and near(back, f) and not near(sq, f)}
        return left[sq]

    squares, mine = {}, {(r[0], r[1]) for r in reach}
    for r in reach + dash:
        sq = (r[0], r[1])
        close = sorted(i for i, f in foes.items() if near(sq, f))
        oa = sorted(oa_on(sq) or ()) if sq in mine and not calm and r[2] // crawl > shifted else []
        if close or oa:
            squares["%d,%d" % sq] = {"near": close, "oa": oa}
    return {"foes": {i: f[2] * units for i, f in foes.items()}, "squares": squares}


def area_inside(fight, me, name, x, y, slot=None):
    """H4: the creatures the spell's area aimed at square (x, y) would catch now, by the cast's own shape code
    (LiveSpells.cone_targets and sphere_targets, LiveGeneral.area): {"inside": [ids], "spared": [ids], "why": ...};
    None when it can't be aimed there or is not one area aimed at one square here (the page then says nothing)."""
    import live_spells, live_general, more_spells, invisibility
    spells, p = fight.spells, fight.sim.party
    pt = (int(x), int(y))
    if name == invisibility.SPELL or more_spells.owner(name):
        return None
    try:
        if name in live_spells.SPELLS:
            s = live_spells.SPELLS[name]
            if s["shape"] == "cone":
                return {"inside": spells.cone_targets(me, pt, s["length_ft"])[0], "spared": []}
            if s["shape"] != "sphere":
                return None
            spells.check_point(me, name, s, *pt)
            inside = spells.sphere_targets(pt, s["radius_ft"])
            if name == "Sleep":                                  # LiveSpells._cast_old's own choice
                gm, foes = fight.sim.gm_rules, set(p.foes(me))
                return {"inside": [i for i in inside if i in foes and not gm.incapacitated(i) and "elf" not in gm.kind(i).lower()
                                   and not gm.cond_immune(i, "exhaustion")], "spared": []}
            allies = [i for i in inside if i in set([me] + p.allies(me))]
            spare = allies[:1 + s["level"]] if fight.sim.by_id(me).get("sculpt_spells") and me not in allies else []
            return {"inside": [i for i in inside if i not in spare], "spared": spare, "why": "Sculpt Spells"}
        plan = live_general.plan(name)
        if not plan or plan["shape"] not in ("sphere", "cone", "line", "cube", "cube_self", "wall"):
            return None
        return {"inside": live_general.of(fight).area(me, plan, pt, slot, [pt], {})[0], "spared": []}
    except (live_spells.SpellError, live_general.GeneralError):
        return None
