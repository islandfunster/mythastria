"""LIVE-PLAY-01 slices 3 and 4 (GM 2026-10-20: "start" on the Bonus Actions, Dash, Dodge, Disengage and doors; then "add
Help, Hide, Search, Ready, Second Wind and the other class Bonus Actions, and Grapple and Shove"): the other actions a
player's character can take in a live fight, checked against SRD 5.2.1 (Playing the Game, "Actions"; Rules Glossary; the
class tables) and done through the simulator's own state.

Slice 3:
- Dash: the action; extra movement equal to the character's Speed for the rest of the turn.
- Disengage: the action; the character's movement provokes no Opportunity Attacks for the rest of the turn. The
  extension already skips a mover marked "Note: Disengage" (aibridge.lua isDisengaged); the mark goes at the turn's end.
- Dodge: the action; until the start of the character's next turn, an attack roll against it has Disadvantage if it
  can see the attacker, and it makes Dexterity saving throws with Advantage; no benefit while Incapacitated or at Speed 0
  (GmRules.cond_mode, Party.save_damage read c["dodging"]).
- Cunning Action (Rogue level 2): Dash, Disengage or Hide as a Bonus Action instead.
- A door: opening or closing one the character stands next to (within 5 ft of its middle) is the turn's one free object
  interaction; a locked door does not open. The simulated map changes (Sim.set_door: sight, routes, walls).
Slice 4:
- Help (assist an attack): the action; an enemy within 5 ft; the next attack roll one of the helper's allies makes
  against it before the helper's next turn has Advantage (GmRules.cond_mode reads gm.helped).
- Hide: the action; not while any enemy sees the character without Three-Quarters Cover or better (env.cover); DC 15
  Dexterity (Stealth) (GmRules.hide: Invisible, the total is the DC to find it).
- Search: the action; Wisdom (Perception) against each hidden enemy's Stealth total.
- Ready (an attack): the action; the trigger is an enemy moving within the readied weapon's reach; the attack is the
  Reaction, made right after the triggering step (Sim.token_moved -> on_step -> sim.later); it lapses at the start of
  the character's next turn.
- Second Wind (Fighter), Rage (Barbarian), Lay On Hands (Paladin): Bonus Actions with their uses / pool.
- Grapple and Shove: Unarmed Strike options, each one attack of the Attack action; a creature within 5 ft, at most one
  size larger; it makes a Strength or Dexterity saving throw (its better) against DC 8 + Strength modifier +
  Proficiency Bonus; a Grapple's escape DC is the same; a Shove pushes it 5 ft straight away or knocks it Prone.
- Ready (a spell), GM 2026-10-25: a spell with a casting time of an action, cast at one creature, is cast as normal (the
  action, its slot) and held with Concentration until the start of the caster's next turn; the trigger is an enemy
  coming within the spell's range; the Reaction releases it at that creature. Broken Concentration: it dissipates.
Not here: Study, Influence, Utilize, reactions chosen by a person when another creature acts.
GM 2026-10-23 (the Sorcerer): Innate Sorcery and Font of Magic (sim/live_sorcery.py) are offered and done here too;
and the Study and Influence actions (sim/live_lore.py).
GM 2026-10-24 (SRD Group 2, sim/traps.py): Search and Study of a square (x, y) look for traps there; "trap" is a step on a
trap the party knows (cut, wedge a spike, plug, deface, Thieves' Tools, free a creature, climb out, slow the stone) or
picking a lock.
"""
import live_lore
import live_sorcery


class ActionError(ValueError):
    pass


SIZES = ["tiny", "small", "medium", "large", "huge", "gargantuan"]
CLASS_BONUS = {"second_wind": "fighter", "rage": "barbarian", "lay_on_hands": "paladin"}
NAMES = {"dash": "Dash", "disengage": "Disengage", "dodge": "Dodge", "help": "Help", "hide": "Hide", "search": "Search",
         "ready": "Ready", "second_wind": "Second Wind", "action_surge": "Action Surge", "rage": "Rage", "lay_on_hands": "Lay On Hands",
         "grapple": "Grapple", "shove": "Shove", "innate_sorcery": "Innate Sorcery",
         "font_convert": "Font of Magic (a slot into points)", "font_create": "Font of Magic (points into a slot)",
         "study": "Study", "influence": "Influence", "stand": "Stand up",
         "drop_prone": "Drop prone", "shake": "Shake awake", "stabilize": "Stabilize", "spirit_strike": "Spiritual Weapon: strike",
         "extinguish": "Put out the fire (roll on the ground)"}       # GM 2026-10-26: SRD 5.2.1 Burning


def cunning(c):
    """Cunning Action: a Rogue of level 2 or more (SRD 5.2.1 Rogue)."""
    return c.get("class") == "rogue" and int(c.get("level", 1) or 1) >= 2


def size_rank(c):
    s = str(c.get("size") or "").lower()
    return SIZES.index(s) if s in SIZES else {5: 2, 10: 3, 15: 4, 20: 5}.get(int(c.get("space") or 5), 2)


def proficiency(c):
    return 2 + (int(c.get("level", 1) or 1) - 1) // 4


class LiveActions:
    def __init__(self, fight):
        self.fight = fight
        self.readied = {}                                   # ctid -> sheet weapon key (slice 4: Ready)
        self.held = {}                                      # ctid -> a readied spell (GM 2026-10-25), see hold_spell
        self.lore = live_lore.Lore(fight)                    # GM 2026-10-23: Study and Influence

    @property
    def sim(self):
        return self.fight.sim

    @property
    def gm(self):
        return getattr(self.sim, "gm_rules", None)

    def turn_start(self, me):
        """The start of this character's turn: its readied attack, its readied spell and its Help lapse."""
        self.readied.pop(me, None)
        h = self.held.pop(me, None)
        if h:                                                    # SRD 5.2.1 Ready: held up to the start of the next turn
            party = self.sim.party
            if party.concentrates(me) == h["label"]:
                party.end_concentration(me)
            self.sim.say("turn", "%s's readied %s lapses unreleased (its slot stays spent)" % (self.sim.by_id(me)["name"], h["spell"]))
        helped = getattr(self.gm, "helped", None)
        if helped:
            for t in [t for t, h in helped.items() if h == me]:
                helped.pop(t)

    # ------------------------------------------------------------------ checks
    def able(self, me):
        t, c = self.fight.turn_state, self.sim.by_id(me)
        if not t or t["id"] != me:
            raise ActionError("It is not %s's turn." % c["name"])
        if self.sim.down(me):
            raise ActionError("%s is down." % c["name"])
        if self.gm and self.gm.incapacitated(me):
            raise ActionError("%s is Incapacitated: no actions." % c["name"])
        return t, c

    def check(self, me, op, bonus=False):
        """Raises ActionError with the reason, or returns how it is paid: "action", "bonus" or "attack" (one attack of
        the Attack action)."""
        t, c = self.able(me)
        party = self.sim.party
        if op == "drop_prone":                                   # GM 2026-10-24: against ranged attacks; then crawl
            if self.gm and self.gm.cond.get(me, {}).get("Prone"):
                raise ActionError("%s is already Prone." % c["name"])
            return "free"
        if op == "action_surge":                                 # play-test 2026-11-02: only the simulator's Fighters had it
            if self.sim.party.surges.get(me, 0) <= 0:
                raise ActionError("%s has no Action Surge left." % c["name"])
            if t.get("surged"):
                raise ActionError("%s has used Action Surge this turn." % c["name"])
            if not t["action_used"] or t["attacks_left"] > 0:
                raise ActionError("Take your action first: Action Surge gives one more.")
            return "free"
        if op == "stand":                                        # GM 2026-10-24: SRD 5.2.1 Prone, "Stand up"
            if not (self.gm and self.gm.cond.get(me, {}).get("Prone")):
                raise ActionError("%s is not Prone." % c["name"])
            if t.get("speed", 0) <= 0:
                raise ActionError("%s's Speed is 0: no standing up." % c["name"])
            if t["movement"] < t["speed"] // 2:
                raise ActionError("Standing up takes %d ft of movement (half %s's Speed); %d ft left." % (
                    t["speed"] // 2, c["name"], t["movement"]))
            return "free"
        if op == "spirit_strike":                                # GM 2026-10-25: SRD 5.2.1 Spiritual Weapon, later turns
            if me not in getattr(party, "spirit_weapon", {}):
                raise ActionError("%s holds no Spiritual Weapon." % c["name"])
            if not party.bonus_free(me):
                raise ActionError("%s's Bonus Action is used this turn." % c["name"])
            return "bonus"
        if op in CLASS_BONUS:
            if c.get("class") != CLASS_BONUS[op]:
                raise ActionError("%s is a %s feature." % (NAMES[op], CLASS_BONUS[op].title()))
            if op == "second_wind" and self.second_winds_left(me) <= 0:
                raise ActionError("%s has no Second Wind left." % c["name"])
            if op == "second_wind" and party.hp_left(me) >= c["hp"]:
                raise ActionError("%s is unhurt: Second Wind would heal nothing." % c["name"])
            if op == "rage":
                if me in party.raging:
                    raise ActionError("%s is already raging." % c["name"])
                if not party.rages.get(me):
                    raise ActionError("%s has no Rage left." % c["name"])
            if op == "lay_on_hands" and party.loh.get(me, 0) <= 0:
                raise ActionError("%s's Lay On Hands pool is empty." % c["name"])
            if not party.bonus_free(me):
                raise ActionError("%s's Bonus Action is used this turn." % c["name"])
            return "bonus"
        if bonus:
            if op not in ("dash", "disengage", "hide") or not cunning(c):
                raise ActionError("Only a Rogue's Cunning Action (level 2) makes %s a Bonus Action." % NAMES.get(op, op)
                                  if op in ("dash", "disengage", "hide") else "%s is not a Bonus Action." % NAMES.get(op, op))
            if not party.bonus_free(me):
                raise ActionError("%s's Bonus Action is used this turn." % c["name"])
            return "bonus"
        if op in ("grapple", "shove"):
            if t["action_used"] and t["attacks_left"] <= 0:
                raise ActionError("%s's action is used this turn." % c["name"])
            return "attack"
        if op == "extinguish" and not (self.gm and self.gm.has(me, "Burning")):   # GM 2026-10-26
            raise ActionError("%s is not burning." % c["name"])
        if t["action_used"]:
            raise ActionError("%s's action is used this turn." % c["name"])
        return "action"

    def second_winds_left(self, me):
        winds = self.sim.__dict__.setdefault("second_winds", {})
        return winds.setdefault(me, self.sim.by_id(me).get("second_wind", 0) or 0)

    def foe_beside(self, me, tid, what):
        """A creature for Help, Grapple or Shove: another creature, still up, within 5 ft, no wall between."""
        party, c = self.sim.party, self.sim.by_id(me)
        t = next((o for o in self.sim.sc["combatants"] if o["id"] == tid), None)
        if not t or tid == me:
            raise ActionError("%s: choose another creature." % what)
        if self.sim.down(tid):
            raise ActionError("%s is down." % t["name"])
        if what == "Help" and party.side(tid) == party.side(me):
            raise ActionError("Help aids an attack against an enemy: %s is an ally." % t["name"])
        d = party.dist(me, tid)
        if d > 5.01:
            raise ActionError("%s is %d ft away: %s needs a creature within 5 ft." % (t["name"], round(d), what))
        if party.blocked(me, tid):
            raise ActionError("A wall stands between %s and %s." % (c["name"], t["name"]))
        if what in ("Grapple", "Shove") and size_rank(t) > size_rank(c) + 1:
            raise ActionError("%s is too big to %s (more than one size larger)." % (t["name"], what.lower()))
        return t

    def dying_beside(self, me, tid):
        """Play-test 2026-11-02: SRD 5.2.1, the Help action tries to stabilize a character at 0 HP within 5 ft."""
        party = self.sim.party
        t = next((o for o in self.sim.sc["combatants"] if o["id"] == tid), None)
        if not t or tid == me:
            raise ActionError("Stabilize: choose another character.")
        if not self.dying(tid):
            raise ActionError("%s isn't dying." % t["name"])
        if party.dist(me, tid) > 5.01:
            raise ActionError("%s is %d ft away: stabilizing needs them within 5 ft." % (t["name"], round(party.dist(me, tid))))
        return t

    def dying(self, tid):
        c, st = self.sim.by_id(tid), self.sim.party.deaths.get(tid)
        return bool(c.get("pc") and st and self.sim.down(tid) and not st["dead"] and not st["stable"])

    def stabilize(self, me, c, t):
        """A DC 10 Wisdom (Medicine) check: Stable, with its death saves cleared."""
        bonus = self.fight.checks(me)["skills"]["Medicine"]
        d20 = self.sim.rng.randint(1, 20)
        won = d20 + bonus >= 10
        self.sim.say("dice", "%s tries to stabilize %s: Wisdom (Medicine) d20 %d %+d = %d vs DC 10 -> %s" % (
            c["name"], t["name"], d20, bonus, d20 + bonus, "Stable" if won else "failure"))
        if won:
            self.sim.party.deaths[t["id"]].update(successes=0, failures=0, stable=True)
            self.sim.S.setField(t["id"], "sim_dying", 0)

    def sleeper_beside(self, me, tid):
        """GM 2026-10-25 (ruling L4): a creature within 5 ft whose sleep or stupor a shake ends (gm_rules.shakeable)."""
        party, c = self.sim.party, self.sim.by_id(me)
        t = next((o for o in self.sim.sc["combatants"] if o["id"] == tid), None)
        if not t or tid == me:
            raise ActionError("Shake awake: choose another creature.")
        if not (self.gm and self.gm.shakeable(tid)):
            raise ActionError("%s is not asleep from Sleep, Hypnotic Pattern, Spider's Sting or Essence of Ether." % t["name"])
        if party.dist(me, tid) > 5.01:
            raise ActionError("%s is %d ft away: shaking it awake needs it within 5 ft." % (t["name"], round(party.dist(me, tid))))
        return t

    def spirit_target(self, me, tid):
        """GM 2026-10-25 (SRD 5.2.1 Spiritual Weapon): "As a Bonus Action on your later turns, you can move the force up
        to 20 feet and repeat the attack against a creature within 5 feet of it." Walls are not checked for the force
        (as Party.spiritual_strike)."""
        party = self.sim.party
        sw = party.spirit_weapon[me]
        t = next((o for o in self.sim.sc["combatants"] if o["id"] == tid), None)
        if not t or tid == me:
            raise ActionError("Spiritual Weapon: choose another creature.")
        if self.sim.down(tid):
            raise ActionError("%s is down." % t["name"])
        (fx, fy), (ax, ay) = party.pos(tid), sw["at"]
        ft = max(abs(fx - ax), abs(fy - ay)) * self.sim.sc.get("units", 5)
        if ft > 25 + 2.6:
            raise ActionError("%s is %d ft from the spectral force: it moves 20 ft and strikes within 5 ft." % (t["name"], round(ft)))
        return t

    def push_spot(self, me, tid):
        """Where a Shove pushes it: one square straight away from the shover, free and with no wall in between."""
        env, party = getattr(self.sim, "env", None), self.sim.party
        (mx, my), (tx, ty) = party.pos(me), party.pos(tid)
        px, py = tx + (tx > mx) - (tx < mx), ty + (ty > my) - (ty < my)
        if env and (env.square_taken(tid, px, py) or env.walled((tx, ty), (px, py))):
            raise ActionError("No room to push %s: the square behind it is taken or walled." % self.sim.by_id(tid)["name"])
        return px, py

    def ally_in_touch(self, me, tid):
        party = self.sim.party
        a = next((o for o in self.sim.sc["combatants"] if o["id"] == tid), None)
        if not a or (tid != me and party.side(tid) != party.side(me)):
            raise ActionError("Lay On Hands: choose yourself or an ally.")
        if tid != me and party.dist(me, tid) > 5.01:
            raise ActionError("%s is out of touch (5 ft)." % a["name"])
        if party.deaths.get(tid, {}).get("dead"):
            raise ActionError("%s is dead." % a["name"])
        if party.hp_left(tid) >= a["hp"] and not self.sim.down(tid):
            raise ActionError("%s is unhurt." % a["name"])
        return a

    def hide_check(self, me):
        env, c = getattr(self.sim, "env", None), self.sim.by_id(me)
        if self.gm and self.gm.has(me, "Invisible"):             # INVISIBILITY-01: the spell's condition is not hiding
            raise ActionError("%s is already %s." % (c["name"], "Invisible (Invisibility)" if (
                self.gm.cond[me]["Invisible"].get("spell") == "Invisibility") else "hidden"))
        for f in self.sim.party.foes(me):
            if self.sim.sees(f, me) and (not env or env.cover(f, me) < 5):
                raise ActionError("%s can see %s: there is no cover to hide behind." % (self.sim.by_id(f)["name"], c["name"]))

    def spell_to_ready(self, me, cmd):
        """GM 2026-10-25 (SRD 5.2.1 Ready): the spell must have a casting time of an action; the table holds one cast at
        one creature (the trigger brings the creature). Its other checks are the cast's own (slot, components...)."""
        name, c = cmd.get("spell"), self.sim.by_id(me)
        s = next((x for x in self.fight.spells.offers(me) if x["name"] == name), None)
        if s is None:
            raise ActionError("%s is not a spell on %s's sheet the table casts." % (name, c["name"]))
        if s.get("time") != "action":
            raise ActionError("Only a spell with a casting time of an action can be readied (SRD 5.2.1 Ready).")
        if s.get("shape") != "creature":
            raise ActionError("The table readies a spell cast at one creature; %s is not one." % name)
        if s.get("moves"):
            raise ActionError("Moving %s is not casting it." % name)
        if not s.get("ready"):
            raise ActionError(s.get("why") or "%s can't be cast now." % name)
        return s

    def hold_spell(self, me, c, s, cmd):
        """Cast as normal but held: the slot is spent now and Concentration holds it (ending the one held before)."""
        party = self.sim.party
        lv = max(s["level"], int(cmd.get("slot") or 0)) if s["level"] else 0
        if lv and __import__("high_levels").free_how(party, me, s["name"], cmd):
            lv = 0                                               # CASTER-HIGH: Spell Mastery, no slot (at its release too)
        if lv:
            pool = party.pools.get(me) or [party.slots.get(me, 0)]
            lv = next((x for x in range(lv, len(pool) + 1) if pool[x - 1] > 0), lv)
            lv = party.spend_slot(me, lv)
        label = "a readied %s" % s["name"]
        party.start_concentration(me, label)
        party.__dict__.setdefault("gm_concentration", {})[me] = label
        self.held[me] = {"spell": s["name"], "slot": lv, "range_ft": s.get("range_ft", 0), "label": label,
                         "extra": {k: cmd[k] for k in ("choice", "slot") if cmd.get(k) is not None}}
        self.sim.say("turn", "%s readies %s%s, held with Concentration: released with the Reaction when an enemy comes "
                     "within %d ft" % (c["name"], s["name"], " (a level %d slot spent)" % lv if lv else "", s.get("range_ft", 0)))

    def ready_check(self, me, key):
        w = self.sim.by_id(me).get(key) if key in __import__("character_rules").WEAPON_KEYS else None
        if not isinstance(w, dict) or not w.get("name"):
            raise ActionError("Ready which attack? Choose one on the sheet.")
        return w

    # ------------------------------------------------------------------ doing
    def do(self, me, cmd):
        op, bonus = cmd.get("op"), bool(cmd.get("bonus"))
        if op == "door":
            return self.door(me, str(cmd.get("door", "")))
        if op in ("search", "study") and cmd.get("x") is not None:    # GM 2026-10-24: a square, for traps (sim/traps.py)
            return self.examine(me, op, cmd)
        if op == "trap":                                         # GM 2026-10-24: a step on a known trap, or a lock
            import traps
            self.able(me)
            try:
                paid = traps.of(self.sim).do(me, cmd)
            except (traps.TrapError, ValueError) as e:
                raise ActionError(str(e))
            return {"ok": True, "result": "trap", "paid": paid}
        if op in ("study", "influence"):                       # GM 2026-10-23: sim/live_lore.py
            self.able(me)
            try:
                paid = self.lore.do(me, cmd)
            except live_lore.LoreError as e:
                raise ActionError(str(e))
            return {"ok": True, "result": op, "paid": paid}
        import high_levels
        if op in high_levels.OPS:                                # GM 2026-10-26: Abjure Foes (sim/high_levels.py)
            self.able(me)
            try:
                paid, chosen = high_levels.of(self.fight).do(me, cmd)
            except high_levels.HighError as e:
                raise ActionError(str(e))
            return {"ok": True, "result": op, "paid": paid, "targets": chosen}
        import martial_high                                      # MARTIAL-HIGH: Intimidating Presence, Holy Nimbus,
        if op in martial_high.OPS or (op == "lay_on_hands" and cmd.get("mode")):   # Restoring Touch (sim/martial_high.py)
            self.able(me)
            try:
                paid, chosen = martial_high.of(self.fight).do(me, cmd)
            except high_levels.HighError as e:
                raise ActionError(str(e))
            return {"ok": True, "result": op, "paid": paid, "targets": chosen}
        import epic_boons
        if op in epic_boons.OPS:                                 # EPIC-BOONS-01: Merge with Shadows, Blink Steps
            self.able(me)
            try:
                paid = epic_boons.of(self.fight).do(me, cmd)
            except epic_boons.BoonError as e:
                raise ActionError(str(e))
            return {"ok": True, "result": op, "paid": paid}
        import monk
        if op in monk.OPS:                                       # MONK-01: the Monk's Bonus Actions (sim/monk.py)
            self.able(me)
            try:
                paid = monk.of(self.fight).do(me, cmd)
            except monk.MonkError as e:
                raise ActionError(str(e))
            return {"ok": True, "result": op, "paid": paid}
        if op in live_sorcery.OPS:                              # GM 2026-10-23: the Sorcerer (sim/live_sorcery.py)
            self.able(me)
            try:
                paid = live_sorcery.of(self.fight).do(me, cmd)
            except live_sorcery.SorceryError as e:
                raise ActionError(str(e))
            return {"ok": True, "result": op, "paid": paid}
        if op not in NAMES:
            raise ActionError("Not an action here.")
        paid = self.check(me, op, bonus)
        t, c, party = self.fight.turn_state, self.sim.by_id(me), self.sim.party
        tid = cmd.get("target")
        # every check that can refuse comes before anything is spent
        if op in ("help", "grapple", "shove"):
            target = self.foe_beside(me, tid, NAMES[op])
        if op == "shake":
            target = self.sleeper_beside(me, tid)
        if op == "stabilize":
            target = self.dying_beside(me, tid)
        if op == "spirit_strike":
            target = self.spirit_target(me, tid)
        if op == "shove":
            mode = cmd.get("mode")
            if mode not in ("prone", "push"):
                raise ActionError("A Shove knocks the creature Prone or pushes it 5 ft: choose prone or push.")
            spot = self.push_spot(me, tid) if mode == "push" else None
        if op == "hide":
            self.hide_check(me)
        if op == "ready" and cmd.get("spell"):                  # GM 2026-10-25: a readied spell
            spell = self.spell_to_ready(me, cmd)
        elif op == "ready":
            w = self.ready_check(me, cmd.get("weapon"))
        if op == "lay_on_hands":
            a = self.ally_in_touch(me, tid)
        how = " (Cunning Action, Bonus Action)" if paid == "bonus" and op in ("dash", "disengage", "hide") else ""
        if paid == "free":
            pass                                                 # Stand up: movement, not an action
        elif paid == "bonus":
            party.use_bonus(me)
        elif paid == "action":
            t["action_used"], t["attacks_left"] = True, 0
        else:                                                    # one attack of the Attack action
            if not t["action_used"]:
                t["action_used"], t["attacks_left"] = True, c.get("attacks", 1)
                self.sim.say("turn", "%s takes the Attack action (%d attack%s)" % (c["name"], t["attacks_left"],
                                                                                   "" if t["attacks_left"] == 1 else "s"))
            t["attacks_left"] -= 1
            t["attacks_made"] = t.get("attacks_made", 0) + 1
        say = lambda text: self.sim.say("turn", text)
        if op == "drop_prone":
            self.gm.add(me, "Prone", "(drops prone)", by=me)
            say("%s drops prone: ranged attacks from beyond 5 ft have Disadvantage, attacks within 5 ft Advantage; "
                "moving is crawling (double cost) until it stands" % c["name"])
        elif op == "stand":
            cost = t["speed"] // 2
            t["movement"] -= cost
            self.gm.remove(me, "Prone", "stands up, spending %d ft of movement" % cost)
            say("%s stands up (%d ft of movement; %d ft left)" % (c["name"], cost, t["movement"]))
        elif op == "dash":
            speed = t.get("speed", 30)
            t["movement"] += speed
            say("%s Dashes%s: +%d ft of movement (%d ft left)" % (c["name"], how, speed, t["movement"]))
        elif op == "disengage":
            self.sim.S.addEffect(me, "Note: Disengage", True)
            t["disengaged"] = True
            say("%s Disengages%s: no Opportunity Attacks against its movement this turn" % (c["name"], how))
        elif op == "dodge":
            c["dodging"] = True
            say("%s Dodges: attacks against it have Disadvantage, Dexterity saves Advantage, until its next turn" % c["name"])
        elif op == "spirit_strike":                              # GM 2026-10-25: the force moves and strikes again
            party.spirit_weapon[me]["at"] = party.pos(tid)
            self.sim.say("dice", "%s moves the Spiritual Weapon to %s (Bonus Action)" % (c["name"], target["name"]))
            party.spirit_attack(me, c, tid)
            self.sim.settle()
        elif op == "extinguish":                                 # GM 2026-10-26: SRD 5.2.1 Burning
            self.gm.remove(me, "Burning", "rolls on the ground (an action)")
            if not self.gm.cond.get(me, {}).get("Prone"):
                self.gm.add(me, "Prone", "(rolling out the fire)", by=me)
            say("%s rolls on the ground (an action): the fire goes out; %s is Prone" % (c["name"], c["name"]))
        elif op == "shake":                                      # GM 2026-10-25 (ruling L4)
            what = self.gm.shake_awake(tid, me)
            say("%s shakes %s awake (an action): %s ends" % (c["name"], target["name"], what))
        elif op == "stabilize":
            self.stabilize(me, c, target)
        elif op == "help":
            self.gm.__dict__.setdefault("helped", {})[tid] = me
            say("%s Helps: the next attack an ally makes against %s before %s's next turn has Advantage" % (
                c["name"], target["name"], c["name"]))
        elif op == "hide":                                       # STEALTH-01 (GM 2026-10-28): declared stealth, the
            import stealth                                       # player's roll; the GM rolls Perception (sim/stealth.py)
            stealth.of(self.fight).declare(me, how)
        elif op == "search":
            self.search(me, c)
        elif op == "ready" and cmd.get("spell"):
            self.readied.pop(me, None)                           # one readied thing: the spell replaces an attack
            self.hold_spell(me, c, spell, cmd)
        elif op == "ready":
            self.held.pop(me, None)
            self.readied[me] = cmd.get("weapon")
            say("%s Readies an attack with %s (Reaction when an enemy comes within %d ft)" % (c["name"], w["name"], w.get("reach", 5)))
        elif op == "action_surge":                               # SRD 5.2.1: one more action, except the Magic action
            party.surges[me] -= 1
            t["action_used"], t["attacks_left"], t["surged"] = False, 0, True
            self.sim.say("dice", "%s uses Action Surge: one more action (%d use%s left)" % (
                c["name"], party.surges[me], "" if party.surges[me] == 1 else "s"))
        elif op == "second_wind":
            s = self.sim.S
            heal = self.sim.rng.randint(1, 10) + int(c.get("level", 1) or 1)
            self.sim.second_winds[me] -= 1
            wounds = s.heal(me, heal)
            self.sim.say("dice", "%s uses Second Wind (Bonus Action): 1d10 + %d = %d HP (%d/%d HP, %d use%s left)" % (
                c["name"], c.get("level", 1), heal, c["hp"] - int(wounds or 0), c["hp"], self.sim.second_winds[me],
                "" if self.sim.second_winds[me] == 1 else "s"))
            import martial_high
            martial_high.tactical_shift(self.fight, me, c, t)    # MARTIAL-HIGH: Tactical Shift (Fighter 5)
        elif op == "rage":                                       # as Party.turn_barbarian
            party.rages[me] -= 1
            party.raging[me] = party.rage_kept[me] = party.s.turnSerial
            party.s.setField(me, "sim_resist_bps", 1)
            import party as party_mod
            self.sim.say("dice", "%s enters a Rage (Bonus Action): +%d damage with Strength attacks, Resistance to Bludgeoning, "
                         "Piercing and Slashing damage (%d uses left)" % (
                             c["name"], c.get("rage_damage", party_mod.rage_damage(c.get("level", 1))), party.rages[me]))
            party.rage_started(me, c)                            # Mindless Rage (Berserker 6)
            if c.get("instinctive_pounce"):                      # Instinctive Pounce (Barbarian 7): half the Speed
                extra_ft = t.get("speed", 30) // 2
                t["movement"] += extra_ft
                say("%s pounces as the Rage starts (Instinctive Pounce): +%d ft of movement (%d ft left)" % (
                    c["name"], extra_ft, t["movement"]))
        elif op == "lay_on_hands":
            pool, missing = party.loh[me], a["hp"] - party.hp_left(tid)
            want = cmd.get("amount")
            heal = min(pool, int(want) if isinstance(want, int) and want > 0 else missing, missing)
            heal = max(1, heal)
            party.loh[me] -= heal
            who = "herself" if tid == me else a["name"]
            self.sim.say("dice", "%s uses Lay On Hands on %s (Bonus Action): %d HP (%d left in the pool)" % (c["name"], who, heal, party.loh[me]))
            if self.sim.down(tid):
                party.revive(tid, heal)
            else:
                party.s.heal(tid, heal)
        elif op in ("grapple", "shove"):
            self.unarmed(me, c, tid, target, op, cmd.get("mode"), spot if op == "shove" else None)
        return {"ok": True, "result": op, "paid": paid}

    def examine(self, me, op, cmd):
        import requirements as rq, traps
        try:
            x, y = int(cmd["x"]), int(cmd["y"])
        except (KeyError, TypeError, ValueError):
            raise ActionError("%s which square? Give x and y." % NAMES[op])
        tr = traps.of(self.sim)
        ready, rows = rq.check(tr.examine_needs(me, op, x, y))
        if not ready:
            raise ActionError(rq.first_why(rows))
        t = self.fight.turn_state
        t["action_used"], t["attacks_left"] = True, 0
        found = tr.examine(me, op, x, y)
        return {"ok": True, "result": op, "paid": "action", "square": [x, y], "found": [f[0]["id"] for f in found]}

    def search(self, me, c):
        bonus = self.gm.passive_perception(me) - 10
        d20 = self.sim.rng.randint(1, 20)
        total = d20 + bonus
        self.sim.say("dice", "%s Searches: Wisdom (Perception) d20 %d %+d = %d" % (c["name"], d20, bonus, total))
        found, low = [], None
        import light_sources                                     # LIGHTS-01: Dim Light: Disadvantage; Darkness: Blinded
        for f in self.sim.party.foes(me):
            info = self.gm.cond.get(f, {}).get("Invisible") or {}
            look = light_sources.perception(self.sim, me, f) if info and info.get("total") is not None else ""
            if look == "blind":
                continue                                         # it can't see into the Darkness there
            if look == "dis" and total >= info["total"]:
                if low is None:                                  # the second d20, once for the Search
                    second = self.sim.rng.randint(1, 20)
                    low = min(d20, second) + bonus
                    self.sim.say("dice", "Dim Light: Disadvantage where %s looks into it: d20 %d/%d %+d = %d" % (
                        c["name"], d20, second, bonus, low))
                if low < info["total"]:
                    continue
            if info and info.get("total") is not None and total >= info["total"]:
                self.gm.remove(f, "Invisible", "found by %s (Search, Perception %d)" % (c["name"], total))
                found.append(f)
        if not found:
            self.sim.say("turn", "%s finds no one hidden" % c["name"])

    def unarmed(self, me, c, tid, t, op, mode, spot):
        dc = 8 + (int(c.get("str_score", 10) or 10) - 10) // 2 + proficiency(c)
        ability, bonus = max((("Strength", t.get("str_save", 0) or 0), ("Dexterity", t.get("dex_save", 0) or 0)), key=lambda x: x[1])
        d20 = self.sim.rng.randint(1, 20)
        saved = d20 + bonus >= dc
        if self.gm and self.gm.auto_fail(tid, ability.lower()[:3] + "_save"):
            saved = False
        if op == "grapple":
            self.sim.say("dice", "%s tries to Grapple %s (Unarmed Strike): %s save d20 %d %+d = %d vs DC %d -> %s" % (
                c["name"], t["name"], ability, d20, bonus, d20 + bonus, dc, "slips free" if saved else "grappled"))
            if not saved:
                self.gm.add(tid, "Grappled", "(escape DC %d, %s's grapple)" % (dc, c["name"]), by=me, dc=dc, range=5)
            return
        self.sim.say("dice", "%s Shoves %s (Unarmed Strike): %s save d20 %d %+d = %d vs DC %d -> %s" % (
            c["name"], t["name"], ability, d20, bonus, d20 + bonus, dc,
            "holds its ground" if saved else ("pushed 5 ft" if mode == "push" else "knocked Prone")))
        if saved:
            return
        if mode == "push":
            env = getattr(self.sim, "env", None)
            if env:
                env.forced_move(tid, spot[0], spot[1], "shoved by %s" % c["name"])
            else:
                self.sim.S.move(tid, spot[0], spot[1])
            self.sim.settle(0.2)
        else:
            self.gm.add(tid, "Prone", "(%s's Shove)" % c["name"], by=me)

    # ------------------------------------------------------------------ Ready: the trigger and the Reaction
    def on_step(self, name, x0, y0, x1, y1):
        """Sim.token_moved, every token step (pixels): an enemy of a readied character steps from beyond the readied
        weapon's reach to within it -> the readied attack, right after the step (sim.later)."""
        if self.held:
            self.spell_trigger(name, x0, y0, x1, y1)              # GM 2026-10-25: a readied spell
        if not self.readied:
            return
        sim, g = self.sim, self.sim.sc.get("grid", 50)
        mover = next((o for o in sim.sc["combatants"] if o["name"] == name), None)
        if not mover:
            return
        for me, key in list(self.readied.items()):
            if mover.get("side") == sim.by_id(me).get("side"):
                continue
            w = sim.by_id(me).get(key) or {}
            reach = w.get("reach", 5) / sim.sc.get("units", 5)
            mx, my = sim.party.pos(me)
            gap = lambda x, y: max(abs(x / g - mx), abs(y / g - my)) - 1  # squares between two one-square creatures
            if gap(x1, y1) <= reach + 1e-6 < gap(x0, y0):
                sim.later.append(lambda me=me, tid=mover["id"]: self.fire(me, tid))

    def spell_trigger(self, name, x0, y0, x1, y1):
        sim, g, units = self.sim, self.sim.sc.get("grid", 50), self.sim.sc.get("units", 5)
        mover = next((o for o in sim.sc["combatants"] if o["name"] == name), None)
        if not mover:
            return
        for me, h in list(self.held.items()):
            if mover.get("side") == sim.by_id(me).get("side"):
                continue
            mx, my = sim.party.pos(me)
            ft = lambda x, y: max(abs(x / g - mx), abs(y / g - my)) * units
            if ft(x1, y1) <= h["range_ft"] + 1e-6 < ft(x0, y0):
                sim.later.append(lambda me=me, tid=mover["id"]: self.release(me, tid))

    def release(self, me, tid):
        """The trigger came: the Reaction releases the held spell at that creature (no new action or slot). It must still
        be a legal target (sight, range, walls); else the spell stays held. Broken Concentration: it is gone."""
        sim, s = self.sim, self.sim.S
        h = self.held.get(me)
        if not h or sim.down(me) or sim.down(tid) or (self.gm and self.gm.incapacitated(me)):
            return
        if int(s.getField(me, "reaction") or 0):
            return
        party, c = sim.party, sim.by_id(me)
        if party.concentrates(me) != h["label"]:
            self.held.pop(me, None)
            sim.say("turn", "%s's readied %s is gone: its Concentration broke" % (c["name"], h["spell"]))
            return
        lv = h["slot"]
        pool = party.pools.setdefault(me, [party.slots.get(me, 0)])
        if lv:                                                   # the slot spent when readied pays for this cast
            pool[lv - 1] += 1
            party.slots[me] += 1
        was, was_turn = self.fight.turn_state, party.slot_turn.get(me)
        self.fight.turn_state = {"id": me, "movement": 0, "speed": 0, "action_used": False, "attacks_left": 0,
                                 "sneak_used": True, "attacks_made": 0}
        party.slot_turn.pop(me, None)
        import high_levels                                       # CASTER-HIGH: Spell Mastery's cast, no slot
        high_levels.arm(party, me, h["spell"], dict(h["extra"], **({"slot": lv} if lv else {})))
        party.no_recall = me                                     # EPIC-BOONS-01: Spell Recall rolled when it was readied
        try:
            self.fight.spells.cast(me, dict(h["extra"], spell=h["spell"], target=tid, **({"slot": lv} if lv else {})))
        except Exception as e:                                   # not a legal target now: it stays held
            if lv:
                pool[lv - 1] -= 1
                party.slots[me] -= 1
            if was_turn is not None:
                party.slot_turn[me] = was_turn
            sim.say("turn", "%s's readied %s waits: not at %s (%s)" % (c["name"], h["spell"], sim.by_id(tid)["name"], e))
            return
        finally:
            self.fight.turn_state = was
            high_levels.disarm(party, me)
            party.no_recall = None
        self.held.pop(me, None)
        s.setField(me, "reaction", 1)
        if party.concentrates(me) == h["label"]:                 # a spell without Concentration: the holding ends
            party.end_concentration(me)
        sim.say("turn", "%s releases the readied %s at %s (Reaction)" % (c["name"], h["spell"], sim.by_id(tid)["name"]))

    def fire(self, me, tid):
        sim, s = self.sim, self.sim.S
        key = self.readied.get(me)
        if not key or sim.down(me) or sim.down(tid) or (self.gm and self.gm.incapacitated(me)):
            return
        if int(s.getField(me, "reaction") or 0):
            return
        w = sim.by_id(me).get(key) or {}
        party = sim.party
        if party.dist(me, tid) > w.get("reach", 5) + 0.01 or party.blocked(me, tid):
            return
        self.readied.pop(me, None)
        s.setField(me, "reaction", 1)
        sim.say("turn", "%s makes the readied attack against %s (Reaction)" % (sim.by_id(me)["name"], sim.by_id(tid)["name"]))
        party.attack(me, tid, w, retarget_grapple=False)

    def door(self, me, door_id):
        t, c = self.able(me)
        w = self.doors_by_id().get(door_id)
        if not w:
            raise ActionError("No door called %s here." % door_id)
        walls = self.sim.walls
        if door_id in getattr(getattr(self.sim, "_spell_doors", None), "broken", ()):   # SPELL-OBJECTS-01
            raise ActionError("The %s is broken: the doorway can't be closed." % door_id)
        import spell_doors                                       # SPELL-OBJECTS-01: Arcane Lock opens for its party
        if door_id in walls.get("locked_doors", []) and not spell_doors.of(self.sim).opens_freely(door_id, me):
            raise ActionError("The %s is locked." % door_id)
        if not self.near(me, w):
            raise ActionError("%s must stand next to the %s to open or close it." % (c["name"], door_id))
        if t.get("interaction_used"):
            raise ActionError("%s has used the free object interaction this turn." % c["name"])
        import run_sim
        is_open = door_id in walls.get("open_doors", [])
        self.sim.set_door(run_sim.MAP, door_id, not is_open)
        t["interaction_used"] = True
        self.sim.say("turn", "%s %s the %s (free object interaction)" % (c["name"], "closes" if is_open else "opens", door_id))
        return {"ok": True, "result": "door", "door": door_id, "open": not is_open}

    # ------------------------------------------------------------------ for the sheet
    def doors_by_id(self):
        return {str(w["id"]): w for w in self.sim.sc.get("walls") or [] if w.get("door")}

    def near(self, me, w):
        (ax, ay), (bx, by) = w["points"][0], w["points"][-1]
        px, py = self.sim.party.pos(me)
        return max(abs(px - (ax + bx) / 2), abs(py - (ay + by) / 2)) <= 1.0 + 1e-9

    def offers(self, me):
        c, party, out = self.sim.by_id(me), self.sim.party, []
        ops = ["dash", "disengage", "dodge", "help", "hide", "search", "ready"]
        ops += [op for op, cls in CLASS_BONUS.items() if c.get("class") == cls and (op != "second_wind" or c.get("second_wind"))]
        ops += ["action_surge"] if c.get("action_surge") else []
        ops += ["grapple", "shove"]
        if self.gm and any(self.gm.shakeable(o["id"]) for o in self.sim.sc["combatants"] if o["id"] != me):
            ops.append("shake")                                  # GM 2026-10-25 (L4): only when someone sleeps
        if any(self.dying(o["id"]) for o in self.sim.sc["combatants"] if o["id"] != me):
            ops.append("stabilize")                              # play-test 2026-11-02: only when someone is dying
        if me in getattr(party, "spirit_weapon", {}):
            ops.append("spirit_strike")                          # GM 2026-10-25: its Bonus Action on later turns
        if self.gm and self.gm.has(me, "Burning"):
            ops.insert(0, "extinguish")                          # GM 2026-10-26: only while it burns
        ops.insert(0, "stand" if self.gm and self.gm.cond.get(me, {}).get("Prone") else "drop_prone")   # GM 2026-10-24
        others = [o["id"] for o in self.sim.sc["combatants"] if o["id"] != me]
        for op in ops:
            entry = {"op": op, "bonus": False, "label": NAMES[op]}
            try:
                self.check(me, op)
                entry["ready"] = True
            except ActionError as e:
                entry["ready"], entry["why"] = False, str(e)
            if op in ("dash", "disengage", "hide") and cunning(c):
                try:
                    self.check(me, op, bonus=True)
                    entry["bonus"] = True
                except ActionError as e:
                    entry.setdefault("bonus_why", str(e))
            if op in CLASS_BONUS or op == "spirit_strike":
                entry["time"] = "bonus"
            if op == "spirit_strike":
                entry["targets"], entry["refused"] = self.legal(others, lambda o: self.spirit_target(me, o))
            if op in ("help", "grapple", "shove"):
                entry["targets"], entry["refused"] = self.legal(others, lambda o: self.foe_beside(me, o, NAMES[op]))
            if op == "shake":
                entry["targets"], entry["refused"] = self.legal(others, lambda o: self.sleeper_beside(me, o))
            if op == "stabilize":
                entry["targets"], entry["refused"] = self.legal(others, lambda o: self.dying_beside(me, o))
            if op == "lay_on_hands":
                entry["targets"], entry["refused"] = self.legal([me] + party.allies(me), lambda o: self.ally_in_touch(me, o))
                entry["pool"] = party.loh.get(me, 0)
            if op == "second_wind":
                entry["uses"] = self.second_winds_left(me)
            if op == "action_surge":
                entry["uses"] = party.surges.get(me, 0)
            if op == "rage":
                entry["uses"] = party.rages.get(me, 0)
            if op == "ready":
                entry["weapons"] = [{"key": k, "name": c[k]["name"]} for k in __import__("character_rules").WEAPON_KEYS
                                    if isinstance(c.get(k), dict) and c[k].get("name")]
                entry["spells"] = []                             # GM 2026-10-25: spells it could ready now
                for s in self.fight.spells.offers(me):
                    if s.get("time") == "action" and s.get("shape") == "creature":
                        try:
                            self.spell_to_ready(me, {"spell": s["name"]})
                            entry["spells"].append({"name": s["name"], "ready": entry["ready"], "why": entry.get("why", ""),
                                                    "range_ft": s.get("range_ft", 0), "general": bool(s.get("general")),
                                                    "choices": s.get("choices"), "upcast": s.get("upcast"),
                                                    "slots_ok": s.get("slots_ok")})
                        except ActionError as e:
                            entry["spells"].append({"name": s["name"], "ready": False, "why": str(e)})
                if me in self.held:
                    entry["holding"] = self.held[me]["spell"]
            if op == "hide" and entry["ready"]:
                try:
                    self.hide_check(me)
                except ActionError as e:
                    entry["ready"], entry["why"], entry["blocked"] = False, str(e), str(e)   # the Bonus Action one too
            out.append(entry)
        import high_levels
        out += self.lore.offers(me) + live_sorcery.of(self.fight).actions(me)   # GM 2026-10-23
        out += high_levels.of(self.fight).actions(me)            # GM 2026-10-26: Abjure Foes
        import martial_high
        out += martial_high.of(self.fight).actions(me)           # MARTIAL-HIGH: the Berserker's and the Paladin's
        import monk
        out += monk.of(self.fight).actions(me)                   # MONK-01: Martial Arts, Monk's Focus
        import epic_boons
        out += epic_boons.of(self.fight).actions(me)             # EPIC-BOONS-01: Merge with Shadows, Blink Steps
        import traps                                             # GM 2026-10-24: Search or Study a square (traps)
        for op, label in (("search", "Search a square (traps: Perception)"), ("study", "Study a square (traps: Investigation)")):
            entry = {"op": op, "square": True, "bonus": False, "label": label}
            try:
                self.check(me, op if op != "study" else "search")
                entry["ready"] = True
            except ActionError as e:
                entry["ready"], entry["why"] = False, str(e)
            out.append(entry)
        return out + traps.of(self.sim).offers(me)              # GM 2026-10-24: known traps, locks

    def legal(self, ids, check):
        ok, no = [], {}
        for o in ids:
            try:
                check(o)
                ok.append(o)
            except ActionError as e:
                no[o] = str(e)
        return ok, no

    def door_offers(self, me):
        t, walls, out = self.fight.turn_state or {}, self.sim.walls, []
        for door_id, w in self.doors_by_id().items():
            (ax, ay), (bx, by) = w["points"][0], w["points"][-1]
            import spell_doors                                   # SPELL-OBJECTS-01: Arcane Lock opens for its party
            d = {"id": door_id, "open": door_id in walls.get("open_doors", []),
                 "locked": door_id in walls.get("locked_doors", []) and not spell_doors.of(self.sim).opens_freely(door_id, me),
                 "mid": [(ax + bx) / 2, (ay + by) / 2], "near": self.near(me, w)}
            try:
                self.able(me)
                d["ready"] = d["near"] and not d["locked"] and not t.get("interaction_used")
            except ActionError:
                d["ready"] = False
            out.append(d)
        return out
