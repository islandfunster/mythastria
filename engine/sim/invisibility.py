"""INVISIBILITY-01 (GM 2026-10-26, goal 5: "the Invisibility spell on the map"): the SRD 5.2.1 Invisibility spell in Play
live, on the Invisible condition MAP-LAYERS-01 step 2 already draws per viewer (sim/map_layers.py sight_parts,
tools/table_seats.py player_view, the page's faded outline).

SRD 5.2.1 Invisibility: level 2 Illusion; Action; Touch; V, S, M (an eyelash in gum arabic); Concentration, up to 1 hour.
"A creature you touch has the Invisible condition until the spell ends. The spell ends early immediately after the
target makes an attack roll, deals damage, or casts a spell." Using a Higher-Level Spell Slot: "You can target one
additional creature for each spell slot level above 2."
The Invisible condition (Rules Glossary): attack rolls against it have Disadvantage and its attack rolls Advantage,
unless the other creature can somehow see it (Truesight or Blindsight within range, See Invisibility, an outline:
GmRules.cond_mode, Sim.sees); Concealed: an effect that requires its target to be seen can't take it ("a creature you
can see": live_spells.check_creature).

Here:
- cast (LiveInvisibility.cast): able to act, the spell on the sheet, the Action free, a slot of level 2 or higher, One
  Spell with a Spell Slot per Turn; each creature within touch (5 ft, no wall between; the caster may touch itself), at
  most 1 + (slot - 2) of them. A new Concentration spell ends the one held. Each creature gets the Invisible condition
  held by the caster (GmRules record spell="Invisibility"; it replaces hiding), and the cast is the caster's
  Concentration spell (Party.control) for 600 rounds.
- it ends on one creature (ends_on): that creature's attack roll (GmRules.attack_rolled), damage it deals
  (GmRules.hurt), a spell it casts (cast_spell: every cast in Play live, the sheet's spells, the zone spells and Ask the
  GM's). With no creature left the spell is over and the caster's Concentration with it. The caster's Concentration
  ending (damage, Incapacitated, another Concentration spell, its hour) ends it on everyone (Party.end_concentration).
- it is not hiding: Perception (passive or a Search) finds a hidden creature (Hide), never this one.
- the creatures the simulator plays: an Invisible enemy they can't perceive and don't hear fighting is not a target
  (mythastria_core/ai_turn.py build_options); with no one else to go for they stay on guard.
"""
import requirements as rq

SPELL = "Invisibility"
LEVEL, TOUCH_FT, ROUNDS = 2, 5, 600                              # Concentration, up to 1 hour


class InvisibilityError(ValueError):
    pass


def held(gm, t):
    """The Invisibility spell's record on t (its caster in "by"), or None."""
    info = (gm.cond.get(t) or {}).get("Invisible") if gm else None
    return info if info and info.get("spell") == SPELL else None


def ends_on(sim, t, why):
    """The spell ends early on t (its attack roll, damage it dealt, a spell it cast). On the last creature it holds, the
    spell is over: the caster's Concentration ends. True when it ended."""
    gm, party = getattr(sim, "gm_rules", None), getattr(sim, "party", None)
    info = held(gm, t)
    if not info:
        return False
    gm.remove(t, "Invisible", "%s ends: %s" % (SPELL, why))
    let_go(sim, info["by"], t)
    return True


def let_go(sim, caster, t):
    """The caster's Invisibility no longer holds t; on its last creature the spell is over."""
    party = getattr(sim, "party", None)
    ctl = (getattr(party, "control", None) or {}).get(caster) if party else None
    if ctl and ctl.get("spell") == SPELL:
        ctl["targets"].discard(t)
        if not ctl["targets"]:
            party.end_concentration(caster)
            sim.say("dice", "%s's %s holds no one now: the spell ends, and %s's Concentration with it" % (
                sim.by_id(caster)["name"], SPELL, sim.by_id(caster)["name"]))


def cast_spell(sim, me, spell):
    """A creature cast a spell: its own Invisibility ends (an Invisibility cast does this itself, before its touch)."""
    if spell != SPELL:
        ends_on(sim, me, "it casts a spell (%s)" % spell)


def of(fight):
    inv = getattr(fight, "invisibility", None)
    if inv is None:
        inv = fight.invisibility = LiveInvisibility(fight)
    return inv


class LiveInvisibility:
    """The spell in one LiveFight (its turn_state, its simulator)."""

    def __init__(self, fight):
        self.fight = fight

    @property
    def sim(self):
        return self.fight.sim

    @property
    def party(self):
        return self.fight.sim.party

    @staticmethod
    def known(c):
        """On the sheet: in its spell list (the Characters page's prepared spells) or its flag (a pregen, a test)."""
        return c.get("invisibility") or any(isinstance(sp, dict) and sp.get("name") == SPELL for sp in c.get("spell_list") or [])

    @staticmethod
    def most(slot):
        return 1 + max(0, int(slot) - LEVEL)

    def pool(self, me):
        import live_spells
        return live_spells.slots_of(self.party, me)

    # ------------------------------------------------------------------ the checks
    def needs(self, me, slot=None):
        c, t, party = self.sim.by_id(me), self.fight.turn_state, self.party
        needs = [rq.able(self.fight, me)]
        if not t or t["id"] != me:
            needs.append(rq.need("your turn", False, "It is not this character's turn."))
            return needs
        needs.append(rq.need("the spell on the sheet", self.known(c), "%s is not on %s's sheet." % (SPELL, c["name"]),
                             rq.LINKS["characters"]))
        needs.append(rq.action_free(self.fight, me, SPELL))
        lv = max(LEVEL, int(slot or LEVEL))
        needs.append(rq.need("a spell slot", sum(self.pool(me)[lv - 1:]) > 0,
                             "No spell slot of level %d or higher left for %s." % (lv, SPELL)))
        needs.append(rq.need("no other slot this turn", party.slot_turn.get(me) != party.s.turnSerial,
                             "One spell with a spell slot per turn: %s already spent a slot this turn (SRD 5.2.1)." % c["name"]))
        if getattr(party, "quickened_turn", {}).get(me) == party.s.turnSerial:
            needs.append(rq.need("no Quickened Spell this turn", False,
                                 "After a Quickened Spell, no level 1+ spell this turn (SRD 5.2.1 Metamagic)."))
        return needs

    def target_needs(self, me, tid):
        sim, party = self.sim, self.party
        o = next((x for x in sim.sc["combatants"] if x["id"] == tid), None)
        if o is None:
            return [rq.need("a creature", False, "Choose a creature for %s." % SPELL)]
        needs = [rq.need("a creature, not a corpse", not sim.corpse(o), "%s is dead: no longer a creature." % o["name"])]
        if tid != me:
            needs.append(rq.need("within touch", party.dist(me, tid) <= TOUCH_FT + 0.01,
                                 "%s is %d ft away: %s is cast by touch (5 ft)." % (o["name"], round(party.dist(me, tid)), SPELL)))
            needs.append(rq.need("no wall between", not party.blocked(me, tid), "A wall stands between %s and %s." % (
                sim.by_id(me)["name"], o["name"])))
        return needs

    def slot_for(self, me, cmd, n):
        """The slot this cast uses: cmd["slot"], or the lowest one left that takes the creatures chosen."""
        pool = self.pool(me)
        if cmd.get("slot"):
            try:
                return max(LEVEL, int(cmd["slot"]))
            except (TypeError, ValueError):
                raise InvisibilityError("The slot is a level from 2 to 9.")
        for lv in range(LEVEL, len(pool) + 1):
            if pool[lv - 1] > 0 and self.most(lv) >= n:
                return lv
        return LEVEL

    # ------------------------------------------------------------------ casting
    def cast(self, me, cmd):
        if cmd.get("metamagic"):
            raise InvisibilityError("Metamagic on %s is not played yet: ask the GM." % SPELL)
        tids = list(cmd.get("targets") or ([cmd["target"]] if cmd.get("target") is not None else []))
        if not tids:
            raise InvisibilityError("Choose the creature %s touches." % SPELL)
        if len(set(tids)) != len(tids):
            raise InvisibilityError("Each creature once.")
        slot = self.slot_for(me, cmd, len(tids))
        ready, rows = rq.check(self.needs(me, slot))
        if not ready:
            raise InvisibilityError(rq.first_why(rows))
        if len(tids) > self.most(slot):
            raise InvisibilityError("%s takes at most %d creature%s with a level %d slot (one more for each level above 2)." % (
                SPELL, self.most(slot), "" if self.most(slot) == 1 else "s", slot))
        for tid in tids:
            ok, rows = rq.check(self.target_needs(me, tid))
            if not ok:
                raise InvisibilityError(rq.first_why(rows))
        sim, party, gm, c, t = self.sim, self.party, self.sim.gm_rules, self.sim.by_id(me), self.fight.turn_state
        ends_on(sim, me, "it casts a spell (%s)" % SPELL)       # casting it ends its own first
        t["action_used"], t["attacks_left"] = True, 0
        lv = party.spend_slot(me, slot)
        party.start_concentration(me, SPELL)                    # a new Concentration spell ends the one held
        rnd = int(sim.S.round())
        sim.say("dice", "%s casts %s (a level %d slot, Concentration, up to 1 hour), touching %s" % (
            c["name"], SPELL, lv, " and ".join(sim.by_id(x)["name"] for x in tids)))
        for tid in tids:
            why = "(%s's %s)" % (c["name"], SPELL)
            prev = held(gm, tid)
            if gm.has(tid, "Invisible"):                        # hidden, or another's Invisibility: this one holds it now
                gm.cond[tid]["Invisible"] = {"why": why, "by": me, "spell": SPELL}
                sim.say("dice", "%s stays Invisible, now %s" % (sim.by_id(tid)["name"], why))
                if prev:
                    let_go(sim, prev["by"], tid)
            else:
                gm.add(tid, "Invisible", why, by=me, spell=SPELL)
        party.__dict__.setdefault("control", {})[me] = {"spell": SPELL, "targets": set(tids), "ends_round": rnd + ROUNDS}
        x, y = party.pos(tids[0])
        return {"spell": SPELL, "appearance": "arcane", "shape": "circle", "origin": [x, y], "radius_ft": 5,
                "targets": list(tids), "from": list(party.pos(me))}

    def turn_start(self, me):
        """The caster's turn: its hour is over (600 rounds)."""
        ctl = (getattr(self.party, "control", None) or {}).get(me)
        if ctl and ctl.get("spell") == SPELL and int(self.sim.S.round()) >= ctl.get("ends_round", 1 << 30):
            self.party.end_concentration(me)
            self.sim.say("dice", "%s's %s ends: its hour is over" % (self.sim.by_id(me)["name"], SPELL))

    # ------------------------------------------------------------------ what the sheet shows
    def offers(self, me):
        c = self.sim.by_id(me)
        if not self.known(c):
            return []
        pool = self.pool(me)
        ready, rows = rq.check(self.needs(me))
        slots = [lv for lv in range(LEVEL, len(pool) + 1) if pool[lv - 1] > 0]
        most = self.most(max(slots) if slots else LEVEL)
        e = {"name": SPELL, "level": LEVEL, "time": "action", "shape": "creatures" if most > 1 else "creature",
             "general": True, "appearance": "arcane", "range_ft": TOUCH_FT, "touch": True, "concentration": True,
             "ready": ready, "why": "" if ready else rq.first_why(rows), "slots_ok": slots, "upcast": True,
             "kind": "condition", "rider": "Invisible until the spell ends; it ends on a creature that attacks, deals "
                                           "damage or casts a spell"}
        if most > 1:
            e["max_targets"] = most
        held_now = self.party.concentrates(me)
        if held_now:
            e["ends"] = held_now
        link = rq.first_link(rows)
        if link and not ready:
            e["link"] = link
        if ready:
            ok, no = [], {}
            for o in self.sim.sc["combatants"]:
                fine, why = rq.check(self.target_needs(me, o["id"]))
                if fine:
                    ok.append(o["id"])
                else:
                    no[o["id"]] = rq.first_why(why)
            e["targets"], e["refused"] = ok, no
        return [e]
