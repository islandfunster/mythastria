"""SPELL-EFFECTS-01 group 4 (GM 2026-10-26): charms in Play live, by SRD 5.2.1, and the Charmed condition read by the
creatures the game plays (it "can't attack the charmer or target the charmer with damaging abilities or magical
effects").

- Charm Person (level 1, Action, 30 ft, one Humanoid you can see, one more a slot level above 1; 1 hour, no
  Concentration): a Wisdom save, with Advantage when the caster or its allies are fighting it; Charmed until the spell
  ends or until the caster or its allies damage it. The Charmed creature is Friendly to the caster.
- Animal Friendship (level 1, Action, 30 ft, a Beast you can see, one more a slot level above 1; 24 hours): Wisdom
  save or Charmed; the spell ends if the caster or one of its allies damages it.
- Suggestion (level 2, Action, 30 ft, one creature you can see that can hear you; Concentration up to 8 hours): Wisdom
  save or Charmed, pursuing the suggestion, until the spell ends or the caster or its allies damage it. The engine
  plays two suggestions: "Stop fighting and leave" (it stops fighting and leaves: the Dash toward the map's edge each
  turn, as a fled creature does) and "Stop fighting" (it keeps out of the fight: Indifferent); any other is the GM's.
- Calm Emotions (level 2, Action, 60 ft, a 20-foot-radius Sphere; Concentration up to 1 minute): each Humanoid foe in
  it makes a Charisma save or becomes Indifferent toward the caster's side; it ends if the creature takes damage or
  witnesses its allies taking damage (the attitudes, sim/attitude.py), and the attitude returns when the spell ends.
  (The other option, suppressing Charmed and Frightened on the caster's side, is the GM's.)
- Command (sim/live_general.py casts it): besides Grovel and Halt, the creatures the game plays now obey Approach (it
  moves toward the caster by the shortest route, ending its turn within 5 feet), Drop (it drops what it holds and its
  turn ends) and Flee (it spends its turn moving away from the caster, the Dash with its movement).
A player's character that is Charmed can't attack its charmer or aim a spell at it (refused with the reason).
"""
import re

import more_spells as ms
import requirements as rq

SUGGEST = ("Stop fighting and leave", "Stop fighting", "Something else (the GM rules)")
SPELLS = {
    "Charm Person": dict(level=1, time="action", shape="creature", range_ft=30, appearance="arcane", kind="humanoid",
                         per_level=1, upcast=True, ends_if_hurt=True, rounds=600,
                         rider="Charmed (Friendly to you) until the spell ends or you or your allies damage it"),
    "Animal Friendship": dict(level=1, time="action", shape="creature", range_ft=30, appearance="arcane", kind="beast",
                              per_level=1, upcast=True, ends_if_hurt=True, rounds=14400,
                              rider="Charmed until you or your allies damage it"),
    "Suggestion": dict(level=2, time="action", shape="creature", range_ft=30, appearance="arcane", concentration=True,
                       hears=True, ends_if_hurt=True, choices=list(SUGGEST),
                       rider="Charmed: it pursues the suggestion until the spell ends or you or your allies damage it"),
    "Calm Emotions": dict(level=2, time="action", shape="sphere", radius_ft=20, range_ft=60, appearance="radiant",
                          concentration=True, kind="humanoid",
                          rider="each Humanoid foe in it: Charisma save or Indifferent toward your side"),
}
OPS = ()
CALMED = "Calmed"


def known(c):
    return [n for n in SPELLS if ms.has_spell(c, n)]


def of(sim):
    st = getattr(sim, "_charms", None)
    if st is None:
        st = sim._charms = Charms(sim)
    ms.ACTIVE = sim
    return st


class Charms:
    def __init__(self, sim):
        self.sim = sim
        self.cast_round = {}            # (caster, spell) -> (round, rounds) of a charm without Concentration

    @property
    def fight(self):
        return self.sim.live

    @property
    def party(self):
        return self.sim.party

    @property
    def gm(self):
        return self.sim.gm_rules

    def name(self, i):
        return self.sim.by_id(i)["name"]

    def round(self):
        return int(self.sim.S.round() or 0)

    # ------------------------------------------------------------------ the cards
    def most(self, name, slot, twin=False):
        s = SPELLS[name]
        return 1 + s.get("per_level", 0) * max(0, slot - s["level"]) + (1 if twin else 0)

    def needs(self, me, name, slot=None):
        s = SPELLS[name]
        return ms.cast_needs(self.fight, me, name, s["level"], s["time"], slot)

    def check_target(self, me, name, tid, rng=None):
        s, sim = SPELLS[name], self.sim
        o = sim.by_id(tid)
        if tid == me:
            raise ms.EffectError("%s takes another creature." % name)
        if sim.down(tid):
            raise ms.EffectError("%s is down." % o["name"])
        if s.get("kind") and s["kind"] not in str(o.get("type", "")).lower():
            raise ms.EffectError("%s takes a %s; %s is not one." % (name, s["kind"].capitalize(), o["name"]))
        if s.get("hears") and (self.gm.cond.get(tid) or {}).get("Deafened"):
            raise ms.EffectError("%s can't hear %s (Deafened): Suggestion needs a creature that can hear you." % (
                o["name"], self.name(me)))
        if (self.gm.cond.get(tid) or {}).get("Charmed") and self.gm.by(tid, "Charmed") == me:
            raise ms.EffectError("%s is already Charmed by %s." % (o["name"], self.name(me)))
        ms.in_range(self.fight, me, tid, rng or s["range_ft"], name)
        return o

    def offers(self, me):
        import live_spells
        c, out = self.sim.by_id(me), []
        pool = live_spells.slots_of(self.party, me)
        for name in known(c):
            s = dict(SPELLS[name])
            top = max([lv for lv in range(s["level"], len(pool) + 1) if pool[lv - 1] > 0] or [s["level"]])
            most = self.most(name, top)
            if s["shape"] == "creature" and most > 1:
                s.update(shape="creatures", max_targets=most)
            e = ms.card(self.fight, me, name, s, self.needs(me, name))
            if e["ready"] and SPELLS[name]["shape"] == "creature":
                e["targets"], e["refused"] = ms.targets_of(self.fight, me, lambda t: self.check_target(me, name, t))
            if c.get("metamagic"):
                import live_sorcery
                e["metamagic"] = live_sorcery.of(self.fight).options(me, name, self.meta_entry(name))
            out.append(e)
        return out

    @staticmethod
    def meta_entry(name):
        s = SPELLS[name]
        return dict(s, save=True, twin=bool(s.get("per_level")))

    # ------------------------------------------------------------------ casting
    def cast(self, me, cmd):
        name = cmd["spell"]
        fight, sim, party, gm = self.fight, self.sim, self.party, self.gm
        s, plan = ms.metamagic(fight, me, name, self.meta_entry(name), cmd)   # Quickened Spell: the Bonus Action
        ms.check(ms.cast_needs(fight, me, name, s["level"], s["time"], cmd.get("slot")))
        c = sim.by_id(me)
        if name == "Calm Emotions":
            return self.calm(me, c, cmd, s, plan)
        tids = cmd.get("targets") or ([cmd["target"]] if cmd.get("target") is not None else [])
        if not tids:
            raise ms.EffectError("Choose a creature for %s." % name)
        if len(set(tids)) != len(tids):
            raise ms.EffectError("Each creature once.")
        slot = int(cmd.get("slot") or 0) or self.lowest_slot(me, name, len(tids), plan)
        most = self.most(name, slot, twin=bool(plan and plan.get("twin")))
        if len(tids) > most:
            raise ms.EffectError("%s takes at most %d creature%s with a level %d slot." % (name, most, "" if most == 1 else "s", slot))
        for t in tids:
            self.check_target(me, name, t, s["range_ft"])         # Distant Spell: its range doubled
        choice = cmd.get("choice") or (SPELLS[name].get("choices") or [None])[0]
        if SPELLS[name].get("choices") and choice not in SPELLS[name]["choices"]:
            raise ms.EffectError("%s: choose one of %s." % (name, ", ".join(SPELLS[name]["choices"])))
        dis = []
        if plan and plan.get("heighten"):
            import live_sorcery
            dis = live_sorcery.of(fight).heightened(me, tids, cmd)
        lv = ms.spend(fight, me, s["time"], SPELLS[name]["level"], slot)
        ms.pay_metamagic(fight, me, name, plan, heightened=dis)
        if SPELLS[name].get("concentration"):
            party.start_concentration(me, name)
        dc = party.spell_dc(c)
        sim.say("dice", "%s casts %s (a level %d slot%s): DC %d Wisdom save for %s%s" % (
            c["name"], name, lv, ", Concentration" if SPELLS[name].get("concentration") else "", dc,
            ", ".join(self.name(t) for t in tids), ": \"%s\"" % choice if choice else ""))
        held = []
        for t in tids:
            adv = name == "Charm Person" and party.side(t) != party.side(me)      # "fighting it": a foe in this fight
            hd = "Heightened Spell" if t in dis else False
            if gm.cond_immune(t, "Charmed"):
                sim.say("dice", "%s is immune to the Charmed condition" % self.name(t))
                continue
            if gm.condition_save(t, "wis", dc, name, charm=True, adv="you are fighting it" if adv else False, dis=hd):
                continue
            info = {"by": me, "spell": name, "save": "wis", "dc": dc, "ends_if_hurt_by": party.side(me)}
            if choice:
                info["suggestion"] = choice
            gm.add(t, "Charmed", "(%s's %s%s)" % (c["name"], name, ": \"%s\"" % choice if choice else ""), **info)
            held.append(t)
            if name == "Suggestion":
                self.suggest(me, t, choice)
        if SPELLS[name].get("concentration"):
            if held:
                party.control[me] = {"spell": name, "targets": set(held)}
            else:
                party.holds_no_one(me, name, "fails")
        else:
            twice = 2 if plan and "Extended Spell" in plan["metas"] else 1          # Extended Spell: its duration doubled
            self.cast_round[(me, name)] = (self.round(), SPELLS[name]["rounds"] * twice)
        ms.extended(fight, me, name, plan)
        x, y = party.pos(tids[0])
        e = {"spell": name, "appearance": "arcane", "shape": "circle", "origin": [x, y], "radius_ft": 5,
             "targets": list(tids), "from": list(party.pos(me))}
        if len(tids) > 1:
            e["_cmd"] = {"targets": list(tids)}
        return e

    def lowest_slot(self, me, name, n, plan):
        import live_spells
        pool = live_spells.slots_of(self.party, me)
        for lv in range(SPELLS[name]["level"], len(pool) + 1):
            if pool[lv - 1] > 0 and self.most(name, lv, twin=bool(plan and plan.get("twin"))) >= n:
                return lv
        return SPELLS[name]["level"]

    def suggest(self, me, t, choice):
        """Suggestion's course of activity: the two the engine plays (from the creature's next turn: pursue), else the
        GM's ruling."""
        if choice in SUGGEST[:2]:
            self.sim.say("turn", "%s is Charmed: on its turn it will %s" % (self.name(t), choice.lower()))
        elif self.fight is not None:
            n = self.fight.add_ask(me, self.name(me), "spell", "Suggestion", [t], "the GM rules the suggestion the Charmed "
                                   "%s pursues" % self.name(t))
            self.sim.say("turn", "Suggestion: the GM rules the course of activity %s pursues (request %d)" % (self.name(t), n))

    def calm(self, me, c, cmd, s, plan):
        fight, sim, party, gm = self.fight, self.sim, self.party, self.gm
        x, y = ms.square(cmd, "Calm Emotions")
        ms.point_in_range(fight, me, x, y, s["range_ft"], "Calm Emotions")
        u = sim.sc.get("units", 5)
        inside = [o["id"] for o in sim.sc["combatants"] if not sim.down(o["id"]) and
                  ((party.pos(o["id"])[0] - x) ** 2 + (party.pos(o["id"])[1] - y) ** 2) ** 0.5 * u <= 20.01
                  and not party.walled((x, y), party.pos(o["id"]))]
        foes = [t for t in inside if party.side(t) != party.side(me) and "humanoid" in str(sim.by_id(t).get("type", "")).lower()]
        dis = []
        if plan and plan.get("heighten"):
            import live_sorcery
            dis = live_sorcery.of(fight).heightened(me, foes, cmd)
        lv = ms.spend(fight, me, s["time"], 2, cmd.get("slot"))
        ms.pay_metamagic(fight, me, "Calm Emotions", plan, heightened=dis)
        party.start_concentration(me, "Calm Emotions")
        dc = party.spell_dc(c)
        sim.say("dice", "%s casts Calm Emotions (a level %d slot, Concentration): 20-ft-radius Sphere on (%d, %d), DC %d Charisma "
                "save for %s" % (c["name"], lv, x, y, dc, ", ".join(self.name(t) for t in foes) or "no Humanoid foe inside"))
        att, held = getattr(sim, "attitudes", None), []
        for t in foes:
            if gm.condition_save(t, "cha", dc, "Calm Emotions", dis="Heightened Spell" if t in dis else False):
                continue
            gm.add(t, CALMED, "(%s's Calm Emotions: Indifferent toward %s's side)" % (c["name"], c["name"]), by=me,
                   spell="Calm Emotions", was=att.attitude(t) if att else None)
            if att and t in att.rows:
                att.set(t, "Indifferent", "%s's Calm Emotions" % c["name"])
            held.append(t)
        if held:
            party.control[me] = {"spell": "Calm Emotions", "targets": set(held)}
        else:
            party.holds_no_one(me, "Calm Emotions", "calms no one")
        ms.extended(fight, me, "Calm Emotions", plan)
        return {"spell": "Calm Emotions", "appearance": "radiant", "shape": "circle", "origin": [x, y], "radius_ft": 20,
                "targets": list(foes), "from": list(party.pos(me))}

    # ------------------------------------------------------------------ the engine's moments
    def condition_changed(self, t, name):
        """Calm Emotions and Suggestion: when the spell ends on a creature, its attitude returns."""
        if name == "Charmed" and not (self.gm.cond.get(t) or {}).get("Charmed"):
            att = getattr(self.sim, "attitudes", None)
            r = att.rows.get(t) if att else None
            if r and not self.sim.down(t) and (r["status"] == "fled" and not r.get("gone") or r["attitude"] == "Indifferent")                     and any("Suggestion" in str(x.get("why")) for x in att.log if x["id"] == t):
                if r["status"] == "fled":
                    att.set_status(t, None, "the Suggestion ends")
                if r["attitude"] != "Hostile":
                    att.set(t, "Hostile", "the Suggestion ends")
        if name == CALMED and not (self.gm.cond.get(t) or {}).get(CALMED):
            att = getattr(self.sim, "attitudes", None)
            if att and t in att.rows and att.attitude(t) == "Indifferent" and not self.sim.down(t):
                att.set(t, "Hostile", "Calm Emotions ends: its attitude returns")

    def on_hurt(self, src, tid, amount, kinds=""):
        """Charm Person, Animal Friendship, Suggestion end on a creature the caster or its allies damage; Calm Emotions
        on one that takes damage (the attitudes make it and its group Hostile: it witnessed it)."""
        gm = self.gm
        if not amount or gm is None:
            return
        info = (gm.cond.get(tid) or {}).get("Charmed") or {}
        if info.get("ends_if_hurt_by") and src and self.party.side(src) == info["ends_if_hurt_by"]:
            gm.end_one_spell_on(tid, info["by"], info["spell"], "%s damaged it" % self.name(src))
        for t, conds in list(gm.cond.items()):
            calm = conds.get(CALMED)
            if not calm or self.sim.down(t):
                continue
            att = getattr(self.sim, "attitudes", None)
            if t == tid or (att and att.attitude(t) == "Hostile"):
                gm.end_one_spell_on(t, calm["by"], "Calm Emotions", "it took damage" if t == tid else "it saw an ally hurt")

    def expire(self, me):
        """The caster's turn: Charm Person's hour, Animal Friendship's day (they outlast any fight, but not a long one)."""
        for (caster, name), (rnd, rounds) in list(self.cast_round.items()):
            if caster == me and self.round() >= rnd + rounds:
                self.cast_round.pop((caster, name))
                self.gm.end_spell(me, "%s's duration ends" % name, spell=name)

    def pursue(self, me):
        """Suggestion: the Charmed creature pursues the suggestion the engine plays (its attitude, sim/attitude.py)."""
        info = (self.gm.cond.get(me) or {}).get("Charmed") or {}
        att = getattr(self.sim, "attitudes", None)
        want = info.get("suggestion")
        if not att or me not in att.rows or want not in SUGGEST[:2]:
            return
        why = "%s's Suggestion: %s" % (self.name(info["by"]), want.lower())
        if want == SUGGEST[0] and att.rows[me]["status"] != "fled":
            att.set_status(me, "fled", why)
        elif want == SUGGEST[1] and att.attitude(me) != "Indifferent":
            att.set(me, "Indifferent", why)

    def creature_turn_start(self, me):
        """Suggestion pursued; Command's other words, obeyed by a creature the game plays: Approach, Drop, Flee."""
        self.expire(me)
        self.pursue(me)
        gm, sim = self.gm, self.sim
        info = (gm.cond.get(me) or {}).get("Commanded") if gm else None
        word = (info or {}).get("command")
        if not info or word not in ("Approach", "Drop", "Flee") or sim.by_id(me).get("pc"):
            return ""
        caster = info["by"]
        gm.remove(me, "Commanded", "it obeys")
        if word == "Drop":
            return "it obeys the Command (Drop): it drops what it holds"
        if word == "Approach":
            import summons
            summons.of(sim).walk_to(me, caster, near=5)
            return "it obeys the Command (Approach): it moves toward %s by the shortest route" % self.name(caster)
        self.flee(me, caster)
        return "it obeys the Command (Flee): it spends its turn moving away from %s" % self.name(caster)

    def flee(self, me, caster):
        """Command (Flee): away from the caster by the fastest means: the Dash, its whole movement."""
        sim, party = self.sim, self.party
        c = sim.by_id(me)
        speed = int((re.findall(r"\d+", str(c.get("speed", "30"))) or [30])[0])
        best, _, _ = sim._route_search(me, 2 * speed)
        occupied = sim.occupied_cells(me)
        cx, cy = party.pos(caster)
        spots = [q for q in best if q not in occupied]
        if not spots:
            return
        goal = max(spots, key=lambda q: ((q[0] - cx) ** 2 + (q[1] - cy) ** 2, -best[q][0]))
        sim.npc_walk(me, best[goal][1])

    def live_turn_start(self, me):
        self.expire(me)

    def refuse(self, me, cmd):
        """A player's character Charmed by a creature can't attack it or aim a spell at it."""
        gm = self.gm
        info = (gm.cond.get(me) or {}).get("Charmed") if gm else None
        if not info or cmd.get("op") not in ("attack", "cast", "grapple", "shove"):
            return
        aimed = [t for t in [cmd.get("target")] + list(cmd.get("targets") or []) if t is not None]
        if info.get("by") in aimed:
            import live_play
            raise live_play.LiveError("%s is Charmed by %s: it can't attack its charmer or target it with harmful "
                                      "abilities or magical effects (SRD 5.2.1 Charmed)." % (self.name(me), self.name(info["by"])))

    def plan_filter(self, source, opponents, combatants):
        """A creature the game plays, Charmed: its charmer is not a target."""
        cid = str(source).split(".")[-1]
        info = (self.gm.cond.get(cid) or {}).get("Charmed") if self.gm else None
        if not info or not info.get("by"):
            return opponents
        return [p for p in opponents if str(p).split(".")[-1] != info["by"]]


# ---------------------------------------------------------------------- the hooks (sim/more_spells.py)
def _st(sim):
    return getattr(sim, "_charms", None)


def condition_changed(sim, t, name):
    if name in (CALMED, "Charmed") and _st(sim):
        _st(sim).condition_changed(t, name)


def on_hurt(sim, src, tid, amount, kinds=""):
    if _st(sim):
        _st(sim).on_hurt(src, tid, amount, kinds)


def creature_turn_start(sim, me):
    gm = getattr(sim, "gm_rules", None)
    if _st(sim) or (gm and (gm.cond.get(me) or {}).get("Commanded")):
        return of(sim).creature_turn_start(me)
    return ""


def live_turn_start(fight, me):
    if _st(fight.sim):
        _st(fight.sim).live_turn_start(me)


def plan_filter(sim, source, me, opponents, combatants):
    gm = getattr(sim, "gm_rules", None)
    if gm is None:
        return opponents
    return of(sim).plan_filter(source, opponents, combatants)
