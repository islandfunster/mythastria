"""SPELL-EFFECTS-01 (GM 2026-10-26, goal 4: "the remaining spell effects", in separate tasks): the spell effects that Play
live used to leave to "Ask the GM", each group in its own module, and the one place the rest of the engine calls them:

  haste_slow   Haste and Slow (the extra action, Speed, AC, Dexterity saves, the lethargy; Slow's limits)
  summons      summoned and conjured creatures (Find Steed, Find Familiar, Animate Dead), in their own module so the
               creature turns (FG-EXIT-01) only need the thin hooks below
  spell_zones  lasting areas on the map (Web, Spike Growth, Moonbeam, Silence, Sleet Storm, Entangle, Grease, Cloudkill,
               Conjure Animals' pack) on the map-layers zones (sim/map_layers.py)
  charms       Charm Person, Suggestion, Animal Friendship, Calm Emotions, Command's other words: Charmed creatures
               the game plays leave their charmer alone; the charm ends when the caster's side hurts them
  spell_doors  SPELL-OBJECTS-01: spells cast at the map's doors (Knock, the spell-attack cantrips, Shatter's area), a
               door's AC and Hit Points by SRD 5.2.1 "Breaking Objects", burning doors

Each module has SPELLS (name -> how it is cast), known(c), of(sim) (its state, kept on the simulator so the creatures'
turn hooks reach it too) with offers(me) and cast(me, cmd), and any of the hooks below. Every cast is checked before
anything is spent (sim/requirements.py, with its reason) and goes through the rules referee like every other cast.
"""
import importlib

import requirements as rq

MODULES = ("haste_slow", "summons", "spell_zones", "charms", "spell_doors", "delayed_blast", "fire_storm",
           "battle_spells",                                      # SPELL-BATCH-01: Bane, Aid, Barkskin, Mirror Image, Misty Step, Fly, Revivify
           "spells_4_6",                                         # SPELLS-4-6-FIGHT: the level 4-6 spells that change a fight
           "spells_7_9")                                         # SPELLS-7-9: Arcane Sword, Dominate Monster, Holy Aura, Mind Blank, Time Stop, Storm of Vengeance


class EffectError(ValueError):
    pass


def modules():
    return [importlib.import_module(m) for m in MODULES]


def owner(name):
    """The module that casts this spell, or None."""
    return next((m for m in modules() if name in m.SPELLS), None)


def names():
    return {n for m in modules() for n in m.SPELLS}


def has_spell(c, name, flag=None):
    """On the sheet: in its spell list, or the sheet flag (the pregens' way: "haste": true)."""
    listed = {sp.get("name") for sp in c.get("spell_list") or [] if isinstance(sp, dict)}
    flag = flag or name.lower().replace("'", "").replace(" ", "_").replace("/", "_")
    return name in listed or bool(c.get(flag))


def known(c):
    return {n for m in modules() for n in m.known(c)}


def live(sim):
    return getattr(sim, "live", None)


# ---------------------------------------------------------------------- casting (live_spells.LiveSpells.cast / offers)
def cast(fight, me, cmd):
    m = owner(cmd.get("spell"))
    return m.of(fight.sim).cast(me, cmd)


def offers(fight, me):
    out = []
    for m in modules():
        out += m.of(fight.sim).offers(me)
    return out


def cast_needs(fight, me, name, level, time="action", slot=None, flag=None):
    """The checks every cast here makes before anything is spent (as the general caster's): able to act, the spell on
    the sheet, its casting time free, a slot of its level or the chosen one, One Spell with a Spell Slot per Turn."""
    c, t, party = fight.sim.by_id(me), fight.turn_state, fight.sim.party
    needs = [rq.need("the spell on the sheet", has_spell(c, name, flag), "%s is not on %s's sheet." % (name, c["name"]),
                     rq.LINKS["characters"]),
             rq.need("this character's turn", bool(t) and t.get("id") == me, "It is not %s's turn." % c["name"])]
    if not t or t.get("id") != me:
        return needs
    needs.append(rq.able(fight, me))
    needs.append(rq.bonus_free(fight, me, name) if time == "bonus" else rq.action_free(fight, me, name))
    if level >= 1:
        lv = max(level, int(slot or level))
        pool = party.pools.get(me) or [party.slots.get(me, 0)]
        needs.append(rq.need("a spell slot", sum(pool[lv - 1:]) > 0, "No spell slot of level %d or higher left for %s." % (lv, name)))
        needs.append(rq.need("no other slot this turn", party.slot_turn.get(me) != party.s.turnSerial,
                             "One spell with a spell slot per turn: %s already spent a slot this turn (SRD 5.2.1)." % c["name"]))
        if getattr(party, "quickened_turn", {}).get(me) == party.s.turnSerial:
            needs.append(rq.need("no Quickened Spell this turn", False,
                                 "After a Quickened Spell, no level 1+ spell this turn (SRD 5.2.1 Metamagic)."))
    return needs


def check(needs):
    ready, rows = rq.check(needs)
    if not ready:
        raise EffectError(rq.first_why(rows))


def spend(fight, me, time, level, slot=None):
    """The casting time and the slot (the lowest left of the chosen level or higher). Returns the slot level (0: none)."""
    t, party = fight.turn_state, fight.sim.party
    if time == "bonus":
        party.use_bonus(me)
    else:
        t["action_used"], t["attacks_left"] = True, 0
    return party.spend_slot(me, max(level, int(slot or level))) if level >= 1 else 0


def slots_ok(fight, me, level):
    import live_spells
    pool = live_spells.slots_of(fight.sim.party, me)
    return [lv for lv in range(max(1, level), len(pool) + 1) if pool[lv - 1] > 0] if level else []


def card(fight, me, name, s, needs, **more):
    """A spell card the page draws like the general caster's (general: it asks a choice and the slot first)."""
    ready, rows = rq.check(needs)
    e = {"name": name, "level": s["level"], "time": s.get("time", "action"), "shape": s["shape"], "general": True,
         "appearance": s.get("appearance", "arcane"), "range_ft": s.get("range_ft", 0),
         "concentration": bool(s.get("concentration")), "ready": ready, "why": "" if ready else rq.first_why(rows),
         "slots_ok": slots_ok(fight, me, s["level"]), "upcast": bool(s.get("upcast")), "effects": True}
    for k in ("radius_ft", "size_ft", "length_ft", "max_targets", "choices", "gm_rules", "rider", "touch"):
        if s.get(k) is not None:
            e[k] = s[k]
    held = fight.sim.party.concentrates(me)
    if s.get("concentration") and held:
        e["ends"] = held
    link = rq.first_link(rows)
    if link and not ready:
        e["link"] = link
    e.update(more)
    return e


def targets_of(fight, me, check_one):
    """(ids that pass, {id: why not}) over every creature in the fight."""
    ok, no = [], {}
    for o in fight.sim.sc["combatants"]:
        try:
            check_one(o["id"])
            ok.append(o["id"])
        except (EffectError, ValueError) as e:
            no[o["id"]] = str(e)
    return ok, no


def in_range(fight, me, tid, rng_ft, name, sight=True):
    """A creature within the spell's range, no wall on the way, seen (SRD 5.2.1: "a creature you can see")."""
    sim, party = fight.sim, fight.sim.party
    target = sim.by_id(tid)
    if tid != me:
        d = party.dist(me, tid)
        if d > rng_ft + 0.01:
            raise EffectError("%s is %d ft away: out of %s's range (%d ft)." % (target["name"], round(d), name, rng_ft))
        if party.blocked(me, tid):
            raise EffectError("A wall blocks the line to %s." % target["name"])
        if sight and not sim.sees(me, tid):
            raise EffectError("%s cannot see %s." % (sim.by_id(me)["name"], target["name"]))
    return target


def point_in_range(fight, me, x, y, rng_ft, name):
    here, u = fight.sim.party.pos(me), fight.sim.sc.get("units", 5)
    far = max(abs(x - here[0]), abs(y - here[1])) * u
    if far > rng_ft + 0.01:
        raise EffectError("That point is %d ft away: out of %s's range (%d ft)." % (far, name, rng_ft))
    if fight.sim.party.walled(here, (x, y)):
        raise EffectError("A wall blocks the way to that point.")


def square(cmd, name):
    try:
        return int(cmd["x"]), int(cmd["y"])
    except (KeyError, TypeError, ValueError):
        raise EffectError("Place %s on a square." % name)


def metamagic(fight, me, name, s, cmd):
    """GM 2026-10-23 (the Sorcerer): the Metamagic plan for this cast (sim/live_sorcery.py), checked with the rest
    before anything is spent: (the spell's entry as Metamagic changes it, the plan or None)."""
    if not cmd.get("metamagic"):
        return s, None
    import live_sorcery
    try:
        return live_sorcery.of(fight).plan(me, name, s, cmd)
    except live_sorcery.SorceryError as e:
        raise EffectError(str(e))


def pay_metamagic(fight, me, name, plan, **kw):
    if plan:
        import live_sorcery
        live_sorcery.of(fight).pay(me, name, plan, **kw)


def extended(fight, me, name, plan):
    """Extended Spell: Advantage on the saves to keep its Concentration (and, here, twice its duration)."""
    party = fight.sim.party
    if plan and "Extended Spell" in plan.get("metas", ()) and party.concentrates(me) == name:
        party.__dict__.setdefault("extended", {})[me] = name
        return True
    return False


# ---------------------------------------------------------------------- the engine's moments (thin hooks)
def _each(hook, *args):
    out = []
    for m in modules():
        fn = getattr(m, hook, None)
        if fn:
            out.append(fn(*args))
    return out


def creature_turn_start(sim, me):
    """gm_rules.turn_start (a creature the game plays): why its turn is over now, or "" (it plays on)."""
    for why in _each("creature_turn_start", sim, me):
        if why:
            return why
    return ""


def concentration_ended(sim, me, spells):
    """Party.end_concentration: a caster's Concentration ended (group 2: Delayed Blast Fireball's bead explodes)."""
    _each("concentration_ended", sim, me, spells)


def creature_extra_action(sim, me):
    """creature_turns.extra_action: the spell that gives a creature the game plays one more action now (Haste), or ""."""
    for label in _each("creature_extra_action", sim, me):
        if label:
            return label
    return ""


def live_turn_start(fight, me):
    """LiveFight.turn: a player's character's turn begins (after its turn state is set)."""
    _each("live_turn_start", fight, me)


def turn_ended(sim, me):
    """gm_rules.turn_ended: the end of any creature's turn (repeat saves, a zone's end-of-turn save)."""
    _each("turn_ended", sim, me)


def condition_changed(sim, t, name):
    """gm_rules.add / remove: a condition came or went (Haste's AC and Speed follow its "Hasted")."""
    if getattr(sim, "_more_spells_busy", False):
        return
    sim._more_spells_busy = True
    try:
        _each("condition_changed", sim, t, name)
    finally:
        sim._more_spells_busy = False


def on_step(sim, name, x0, y0, x1, y1):
    """Sim.token_moved: a creature stepped (Spike Growth's spikes, entering a web or the sleet)."""
    _each("on_step", sim, name, x0, y0, x1, y1)


def on_hurt(sim, src, tid, amount, kinds=""):
    """Sim.on_hurt: damage taken (fire burns a web away; the charm of Charm Person and Suggestion ends)."""
    _each("on_hurt", sim, src, tid, amount, kinds)


def difficult_cells(sim, me=None):
    """Squares of Difficult Terrain from these spells (Web, Spike Growth, Sleet Storm, Entangle, Grease)."""
    out = set()
    for cells in _each("difficult_cells", sim, me):
        out |= cells or set()
    if me is not None and any(_each("ignores_difficult", sim, me)):   # SPELLS-4-6-FIGHT: Freedom of Movement
        return set()
    return out


def keep_off_cells(sim, me):
    """Squares a creature the game plays keeps off on its routes: the lasting areas that would harm or hold it."""
    out = set()
    for cells in _each("keep_off_cells", sim, me):
        out |= cells or set()
    return out


def save_mod(sim, t, ability):
    """(bonus, Advantage reason or "") on a saving throw: Slow's -2 and Haste's Advantage on Dexterity saves."""
    bonus, adv = 0, ""
    for b, a in _each("save_mod", sim, t, ability):
        bonus += b
        adv = adv or a
    return bonus, adv


def attack_mod(sim, src, tgt):
    """gm_rules.cond_mode: (modifier, note) on an attack roll from these spells (Bane: -1d4)."""
    mod, notes = 0, []
    for m, n in _each("attack_mod", sim, src, tgt):
        mod += m
        if n:
            notes.append(n)
    return mod, " ".join(notes)


def attack_mode(sim, src, tgt):
    """(Advantage, Disadvantage, notes) on an attack roll from these spells: SPELLS-4-6-FIGHT (Irresistible Dance's
    dancer, Dispel Evil and Good) and SPELLS-7-9 (Holy Aura). A module's note is a list or a line of text."""
    adv = dis = False
    notes = []
    for a, d, n in _each("attack_mode", sim, src, tgt):
        adv, dis = adv or a, dis or d
        notes += [n] if isinstance(n, str) and n else list(n or []) if not isinstance(n, str) else []
    return adv, dis, notes


def save_dis(sim, t, ability):
    """SPELLS-4-6-FIGHT: Disadvantage on a saving throw from these spells (Irresistible Dance: Dexterity saves)."""
    return any(_each("save_dis", sim, t, ability))


def rule_immune(sim, t, name):
    """gm_rules.rule_immune: the spell that keeps a condition off this creature now (SPELLS-7-9: Mind Blank), or ""."""
    for why in _each("rule_immune", sim, t, name):
        if why:
            return why
    return ""


def hit_redirect(sim, src, tgt):
    """FightState: a hit that strikes something else instead (Mirror Image's duplicate): its note, or ""."""
    for note in _each("hit_redirect", sim, src, tgt):
        if note:
            return note
    return ""


def choose(fight, me, cmd, do):
    """LiveFight._choose: a player's choice, through Haste's extra action and Slow's limits (haste_slow.choose)."""
    import charms, haste_slow
    charms.of(fight.sim).refuse(me, cmd)                         # a Charmed character and its charmer
    return haste_slow.choose(fight, me, cmd, do)


def before_cast(fight, me, cmd):
    """LiveFight._cast, before anything else: a cast that can't happen (Silence: a Verbal component) raises; one that
    fails anyway (Slow: 25 percent with a Somatic component) returns the reply, its time and slot spent. None: go on."""
    for out in _each("before_cast", fight, me, cmd):
        if out:
            return out
    return None


def adjust_offers(fight, me, out):
    """LiveFight.offers: what Haste's extra action and Slow change on the sheet, and these modules' own actions."""
    _each("adjust_offers", fight, me, out)


OPS = {}                                                         # op -> module name (actions besides casting)


def ops():
    if not OPS:
        for m in modules():
            for op in getattr(m, "OPS", ()):
                OPS[op] = m.__name__
    return OPS


def act(fight, me, cmd):
    m = importlib.import_module(ops()[cmd["op"]])
    return m.of(fight.sim).act(me, cmd)


ACTIVE = None                    # the simulator these modules last played for (the planner gets only its combatants)


def plan_filter(source, me, opponents, combatants):
    """ai_turn.build_options: the targets a creature the game plays may not choose (its charmer; for a summoned
    creature, all but the one it was ordered to attack). Returns the opponents left."""
    sim = ACTIVE
    if sim is None:
        return opponents
    for m in modules():
        fn = getattr(m, "plan_filter", None)
        if fn:
            opponents = fn(sim, source, me, opponents, combatants)
    return opponents
