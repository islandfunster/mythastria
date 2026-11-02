"""SPELL-BATCH-02 (GM 2026-10-28: Shield and Counterspell as player Reactions in Play live, where "the fight asks the
player live", picked over a standing auto-setting).

When a Reaction spell's trigger happens to a character played at the table (live), the fight stops where it is (the
creature's turn waits on the fight's own thread) and asks: that character's player client, or the GM console for a
character nobody plays or the GM holds (Take over, Hand to the GM). The GM console can always answer for the player
(Answer for them), so a fight never hangs on a slow or absent player. One question at a time; the first answer counts.

SRD 5.2.1 (sim/spells/srd_spells.json):
- Shield (level 1, Reaction "when you are hit by an attack roll or targeted by the Magic Missile spell"): until the start
  of your next turn, +5 AC, including against the triggering attack, and no damage from Magic Missile. A Critical Hit is
  not asked about (the d20's 20 hits whatever the AC: the engine resolves it as before).
- Counterspell (level 3, Reaction "when you see a creature within 60 feet of yourself casting a spell with Verbal,
  Somatic, or Material components"): the caster makes a Constitution save against your spell save DC; on a failed save
  the spell dissipates with no effect and the action, Bonus Action or Reaction used to cast it is wasted; a spell slot is
  not expended. A creature's N/Day use is not a spell slot: it is spent (the SRD keeps only a slot).
Both need the spell on the sheet, the Reaction free (Slow takes it), the character up and not Incapacitated, and a slot
of the spell's level or higher with no other slot spent this turn (One Spell with a Spell Slot per Turn: Party.slot_free).

REACTIONS-LIVE-01 (GM 2026-10-28, "continue": the other Reactions the engine took by itself for a played character):
- Hellish Rebuke (level 1, Reaction "in response to taking damage from a creature that you can see within 60 feet of
  yourself"): the creature makes a Dexterity save, 2d10 Fire on a failure, half on a success; 1d10 more for each slot
  level above 1. The Infernal Legacy's free use (once per Long Rest: Party.rebuke_free, sim/rests.py) goes first, then
  the lowest slot.
- Uncanny Dodge (Rogue 5, Reaction "when an attacker that you can see hits you with an attack roll"): the attack's
  damage is halved.
Not asked: readied actions (automatic, by the GM's choice). Opportunity Attacks: asked since OA-AUTO-01 (below).

CUTTING-WORDS-01 (GM 2026-10-28, "continue"): Cutting Words (Bard 3, College of Lore; Reaction "when a creature that you
can see within 60 feet of yourself makes a damage roll or succeeds on an ability check or attack roll"): one use of
Bardic Inspiration (Party.bi_uses), its die rolled and subtracted from the roll. Asked when a foe's attack roll hits
(not a Critical Hit) and the die could turn it into a miss; its damage rolls and ability checks are not asked (the GM
rules those). Asked before Shield: when the words make it miss, no slot is needed.

OA-AUTO-01 (GM 2026-10-28: "automatic pause to ask players opportunity attacks. Auto mode for monsters and foes is
available for fast live games"):
- Opportunity Attack (SRD 5.2.1: "you can make an Opportunity Attack when a creature that you can see leaves your
  reach"; one melee attack, the Reaction): a played character is asked in Run_sim.reaction_window instead of the
  scenario's reaction_policy.
- Auto mode (the GM's switch, for fast live games): the engine answers every player Reaction itself, as it does for
  monsters and foes: Shield when it turns a hit into a miss, Uncanny Dodge, Hellish Rebuke's free use, every Opportunity
  Attack; Counterspell and Cutting Words aren't used (the engine has no choice of its own for them).

MONK-01 (GM 2026-10-28, "Monk as SRD"; sim/monk.py): the Monk's Reactions, features used like Uncanny Dodge.
- Deflect Attacks (Monk 3, Reaction "when an attack roll hits you and its damage includes Bludgeoning, Piercing, or
  Slashing damage"): asked once the attack's damage is rolled (the question names it), 1d10 + Dexterity modifier + Monk
  level off it. Deflect Energy (Monk 13): any damage type. When that takes it to 0, a second question: 1 Focus Point
  redirects the force (Dexterity save or two Martial Arts dice + the Dexterity modifier).
- Slow Fall (Monk 4, Reaction "when you fall"): five times the Monk level off the falling damage.

MARTIAL-HIGH (GM 2026-10-28; sim/martial_high.py):
- Retaliation (Berserker 10, Reaction "when you take damage from a creature that is within 5 feet of you"): one melee
  attack against that creature.
- Not Reactions, asked the same way when the d20 has failed (asked even with the Reaction used): Heroic Inspiration
  (Champion 10's Heroic Warrior: the d20 again), Stroke of Luck (Rogue 20: the d20 becomes a 20) and Tactical Mind
  (Fighter 2: +1d10 on a failed ability check for a Second Wind use).
"""
import threading

SHIELD, COUNTER, REBUKE, DODGE, CUT = "Shield", "Counterspell", "Hellish Rebuke", "Uncanny Dodge", "Cutting Words"
OA = "Opportunity Attack"
LEVEL = {SHIELD: 1, COUNTER: 3, REBUKE: 1, DODGE: None, CUT: None, OA: None}   # None: no spell slot
VERB = {DODGE: "use", CUT: "use", OA: "make"}                                   # the others are cast
FEATURE_FLAG = {DODGE: "uncanny_dodge", CUT: "cutting_words"}           # a build's flag, or the sheet's feature
# the sheet's word for these spells (sim/live_asks.py): not Ask the GM, the fight asks when the trigger happens
ASKED = {SHIELD: "Shield is a Reaction: the fight asks you when an attack roll hits you or Magic Missile targets you.",
         COUNTER: "Counterspell is a Reaction: the fight asks you when a creature you can see within 60 ft casts a spell.",
         REBUKE: "Hellish Rebuke is a Reaction: the fight asks you when a creature you can see within 60 ft damages you.",
         CUT: "Cutting Words is a Reaction: the fight asks you when a foe you can see within 60 ft hits with an attack roll "
              "your Bardic Inspiration die could make miss (the GM rules it against damage rolls and ability checks)."}
ANSWER_WAIT = 5.0       # seconds an answer waits for the fight to resolve it (the reply carries the result)
# MONK-01: the Monk's Reactions (features, used; sim/monk.py)
DEFLECT, ENERGY, REDIRECT, FALL = "Deflect Attacks", "Deflect Energy", "Deflect Attacks: redirect", "Slow Fall"
SURVIVOR = "Disciplined Survivor"                                       # GM 2026-10-28: Monk 14, not a Reaction
LEVEL.update({DEFLECT: None, ENERGY: None, REDIRECT: None, FALL: None})
VERB.update({DEFLECT: "use", ENERGY: "use", REDIRECT: "use", FALL: "use"})
FEATURE_FLAG.update({DEFLECT: "deflect_attacks", ENERGY: "deflect_energy", REDIRECT: "deflect_attacks", FALL: "slow_fall"})
LEVEL[SURVIVOR], VERB[SURVIVOR], FEATURE_FLAG[SURVIVOR] = None, "use", "disciplined_survivor"
# MARTIAL-HIGH: Retaliation (a Reaction); Heroic Inspiration, Stroke of Luck, Tactical Mind (not Reactions)
RETALIATE, HEROIC, STROKE, TMIND = "Retaliation", "Heroic Inspiration", "Stroke of Luck", "Tactical Mind"
LEVEL.update({RETALIATE: None, HEROIC: None, STROKE: None, TMIND: None})
VERB.update({RETALIATE: "use", HEROIC: "use", STROKE: "use", TMIND: "use"})
FEATURE_FLAG.update({RETALIATE: "retaliation", STROKE: "stroke_of_luck", TMIND: "tactical_mind"})
# EPIC-BOONS-01 (GM 2026-10-28; sim/epic_boons.py): Peerless Aim and Improve Fate, asked like Disciplined Survivor (not
# Reactions: asked with the Reaction used too, and using one doesn't end Merge with Shadows)
PEERLESS, FATE = "Peerless Aim", "Improve Fate"
LEVEL.update({PEERLESS: None, FATE: None})
VERB.update({PEERLESS: "use", FATE: "use"})
FEATURE_FLAG.update({PEERLESS: "combat_prowess", FATE: "boon_fate"})
NOT_REACTION = {SURVIVOR, REDIRECT, PEERLESS, FATE, HEROIC, STROKE, TMIND}   # + MARTIAL-HIGH's d20 Tests


class ReactionError(ValueError):
    pass


class Reactions:
    def __init__(self, fight):
        self.fight = fight
        self.open, self.n, self.answer = None, 0, None
        self.answered = threading.Event()
        self.thread = None                                       # the thread that may wait (None: the fight's own)
        # asked only where a screen can answer (LiveFight(ask_reactions=True): the service); a fight with no screen (a
        # test) never waits: its characters keep the simulator's automatic Shield (Party.shield) as before
        self.asking = False
        self.auto = False                                        # OA-AUTO-01: the GM's Auto mode (fast live games)

    @property
    def sim(self):
        return self.fight.sim

    def asks(self):
        """A player is asked now: a screen to ask and Auto mode off."""
        return self.asking and not self.auto

    def set_auto(self, auto):
        """OA-AUTO-01: the GM's Auto mode on or off (every screen redraws its switch)."""
        f = self.fight
        with f.lock:
            self.auto = bool(auto)
            f.revision += 1
            f._publish_locked()
        self.sim.say("note", "Auto mode on: the engine answers the players' Reactions." if self.auto else
                     "Auto mode off: each player is asked for a Reaction again.")

    # ------------------------------------------------------------------ who may be asked
    def knows(self, pc, spell):
        c = self.sim.by_id(pc)
        if spell == OA:
            return True                                          # every creature may (reaction_window checks the rest)
        if spell in FEATURE_FLAG:                                # the build's flag (Rogue 5), or the sheet's feature
            return bool(c.get(FEATURE_FLAG[spell])) or any(f.get("name") == spell for f in c.get("feature_list") or [])
        import more_spells                                       # the spell list, or the pregens' flag ("shield": true)
        return more_spells.has_spell(c, spell)

    def free_shield(self, pc):
        """Play-test 2026-11-02: Magic Initiate's Shield, once a Long Rest without a slot, is still there."""
        sp = next((x for x in self.sim.by_id(pc).get("spell_list") or [] if x.get("name") == SHIELD and x.get("free")), None)
        return bool(sp) and self.sim.party.__dict__.setdefault("ask_uses", {}).setdefault(pc, {}).setdefault("free:" + SHIELD, int(sp["free"])) > 0

    def free_rebuke(self, pc):
        """The Infernal Legacy's free Hellish Rebuke is still there (once per Long Rest; the engine's rule)."""
        return self.sim.party.rebuke_free.setdefault(pc, True)

    def verb(self, spell):
        return VERB.get(spell, "cast")

    def why_not(self, pc, spell):
        """None when this character may cast this Reaction spell now; else why not."""
        sim, party = self.sim, self.sim.party
        c = sim.by_id(pc)
        if not self.asking:
            return "no screen to ask (a fight run without the service)"
        if self.auto:
            return "Auto mode: the engine answers"
        if not c or not c.get("live") or not party:
            return "not played at the table"
        if threading.current_thread() is not (self.thread or self.fight.thread):
            return "not on the fight's own thread"               # only the fight may wait for an answer
        if not self.knows(pc, spell):
            return "%s is not on the sheet" % spell
        if sim.down(pc) or party.deaths.get(pc, {}).get("dead") or party.incapacitated(pc):
            return "down or Incapacitated"
        if int(sim.S.getField(pc, "reaction") or 0):
            return "the Reaction is used"
        if spell == REBUKE and self.free_rebuke(pc):
            return None                                          # the free use needs no slot
        if spell == SHIELD and self.free_shield(pc):
            return None                                          # no slot needed
        if spell == CUT and party.bi_uses.get(pc, 0) <= 0:
            return "no Bardic Inspiration left"
        if spell == COUNTER and __import__("high_levels").free_how(party, pc, COUNTER):
            return None                                          # CASTER-HIGH: Signature Spells, no slot
        if LEVEL[spell] and not party.slot_free(pc, LEVEL[spell]):
            return "no level %d+ slot free this turn" % LEVEL[spell]
        return None

    # ------------------------------------------------------------------ the question
    def ask(self, pc, spell, trigger, note="", free=False, cost=""):
        """Ask and wait (the fight's thread) until the player or the GM answers. Returns {"cast": bool, "by": ...}.
        free: cast without a slot (the question names none). cost: what it spends, when not the Reaction (MONK-01)."""
        import live_play
        f, name, verb = self.fight, self.sim.by_id(pc)["name"], self.verb(spell)
        self.sim.say("turn", "%s: %s may %s %s (Reaction). Waiting for the answer." % (trigger, name, verb, spell))
        with f.lock:
            self.n += 1
            level = None if free else LEVEL[spell]
            self.open = {"n": self.n, "pc": pc, "name": name, "spell": spell, "level": level, "trigger": trigger,
                         "note": note, "slots": self._slots(pc) if level else {}, "verb": verb, **({"cost": cost} if cost else {})}
            self.answer = None
            self.answered.clear()
            f.revision += 1
            f._publish_locked()
        try:
            while not self.answered.wait(0.25):
                if f.stopping:
                    raise live_play.Quit()
        finally:
            with f.lock:
                got, self.open = self.answer or {"cast": False, "by": "nobody"}, None
                f.revision += 1
                f._publish_locked()
        if got["cast"] and spell not in NOT_REACTION:            # EPIC-BOONS-01: a Reaction ends Merge with Shadows
            __import__("epic_boons").reacted(self.sim, pc)
        if got["by"] == "gm":
            self.sim.say("gm", "The GM answers for %s: %s" % (name, "%s %s" % (verb, spell) if got["cast"] else "no %s" % spell))
        elif not got["cast"]:
            self.sim.say("turn", "%s does not %s %s" % (name, verb, spell))
        return got

    def _slots(self, pc):
        party = self.sim.party
        pool = party.pools.get(pc) or [party.slots.get(pc, 0)]
        return {str(lv + 1): n for lv, n in enumerate(pool) if n}

    def respond(self, n, cast, by):
        """From the service: the player's (by "player") or the GM's (by "gm") answer to question n."""
        f = self.fight
        with f.lock:
            q = self.open
            if not q or q["n"] != n:
                raise ReactionError("That Reaction question is no longer open.")
            if self.answer is not None:
                raise ReactionError("%s's Reaction is already answered." % q["name"])
            self.answer = {"cast": bool(cast), "by": by}
            self.answered.set()
            f.changed.wait_for(lambda: self.open is None or self.open["n"] != n, ANSWER_WAIT)
        return {"ok": True, "n": n, "cast": bool(cast), "by": by}

    def view(self):
        return dict(self.open) if self.open else None

    # ------------------------------------------------------------------ Shield
    def turn_start(self, pc):
        """Shield lasts until the start of the character's next turn."""
        party = self.sim.party
        if party and pc in party.shielded:
            party.shielded.discard(pc)
            s = self.sim.S
            s.setField(pc, "sim_ac_bonus", max(0, int(s.getField(pc, "sim_ac_bonus") or 0) - 5))

    def _cast_shield(self, pc):
        import invisibility
        party = self.sim.party
        free = self.free_shield(pc)
        with party.refereed(pc, SHIELD, {"free": "Magic Initiate"} if free else None):
            if free:
                party.ask_uses[pc]["free:" + SHIELD] -= 1
            how = "once a Long Rest, no slot" if free else "a level %d slot" % party.spend_slot(pc, 1)
            party.shielded.add(pc)
            self.sim.say("dice", "%s casts Shield (Reaction, %s): +5 AC until the start of %s's next turn, "
                         "and no damage from Magic Missile" % (party.name(pc), how, party.name(pc)))
        invisibility.cast_spell(self.sim, pc, SHIELD)

    def shield_hit(self, pc, total, ac, crit, src=None):
        """An attack roll hit a live character (the fake FG's reactHit, the Reaction free): (5, True) when it casts
        Shield (fight_state adds +5 AC for this attack and keeps it), else None."""
        if crit or self.why_not(pc, SHIELD):
            return None
        who = self.sim.S.name(src) if src else "An attack"
        trigger = "%s hits %s (%d vs AC %d)" % ("%s's attack" % who if src else who, self.sim.by_id(pc)["name"], total, ac)
        note = ("With Shield (AC %d) this attack misses." % (ac + 5) if total < ac + 5 else
                "Even with Shield (AC %d) this attack hits; the +5 AC lasts until the start of your next turn." % (ac + 5))
        if not self.ask(pc, SHIELD, trigger, note, free=self.free_shield(pc))["cast"]:
            return None
        self._cast_shield(pc)
        return 5, True

    def shield_missile(self, pc, src):
        """Magic Missile targets pc: True when pc takes none of its damage (Shield up already, or cast now)."""
        party = self.sim.party
        ab = getattr(self.sim, "abilities", None)
        if (party and pc in party.shielded) or (ab and pc in ab.shielded):
            return True
        if self.why_not(pc, SHIELD):
            return False
        trigger = "%s's Magic Missile targets %s" % (self.sim.S.name(src), self.sim.by_id(pc)["name"])
        if not self.ask(pc, SHIELD, trigger, "With Shield you take no damage from Magic Missile, and +5 AC until the "
                                             "start of your next turn.", free=self.free_shield(pc))["cast"]:
            return False
        self._cast_shield(pc)
        s = self.sim.S
        s.setField(pc, "reaction", 1)
        s.setField(pc, "sim_ac_bonus", int(s.getField(pc, "sim_ac_bonus") or 0) + 5)
        return True

    # ------------------------------------------------------------------ Counterspell
    def counter(self, caster, spell, label, components, target=None):
        """A creature casts `spell`: each live character that may Counterspell it is asked (nearest first) until the
        spell dissipates. True: the spell has no effect (the caster's action is wasted)."""
        if not any((components or {}).get(k) for k in ("v", "s", "m")):
            return False
        sim, party = self.sim, self.sim.party
        if not party:
            return False
        live = [c["id"] for c in sim.sc["combatants"] if c.get("live") and c.get("pc")]
        live.sort(key=lambda i: party.dist(i, caster))
        for pc in live:
            if party.side(pc) == party.side(caster) or self.why_not(pc, COUNTER):
                continue
            if party.dist(pc, caster) > 60 + 0.01 or not sim.sees(pc, caster):
                continue
            at = " at %s" % sim.S.name(target) if target is not None and target != caster else ""
            trigger = "%s casts %s%s (%d ft from %s)" % (sim.S.name(caster), label, at, round(party.dist(pc, caster)),
                                                         sim.by_id(pc)["name"])
            c = sim.by_id(pc)
            dc = party.spell_dc(c)
            note = "%s makes a Constitution save against your DC %d; on a failure the spell has no effect." % (
                sim.S.name(caster), dc)
            import high_levels                                   # CASTER-HIGH: Signature Spells, no slot
            free = high_levels.free_how(party, pc, COUNTER)
            if not self.ask(pc, COUNTER, trigger, note + (" %s: no spell slot." % free if free else ""), free=bool(free))["cast"]:
                continue
            if self.why_not(pc, COUNTER):                         # changed while asking (nothing should, but never twice)
                continue
            with party.refereed(pc, COUNTER, dict({"target": caster}, **({"free": free} if free else {}))):
                lv = high_levels.pay(party, pc, COUNTER, 3)
                sim.S.setField(pc, "reaction", 1)
                sim.say("dice", "%s casts Counterspell (Reaction, a level %d slot) on %s's %s: DC %d Constitution save" % (
                    c["name"], lv, sim.S.name(caster), label, dc))
                saved = self._save(caster, dc, pc)
            import invisibility
            invisibility.cast_spell(sim, pc, COUNTER)
            if saved:
                sim.say("dice", "%s succeeds: %s goes on" % (sim.S.name(caster), label))
                continue
            sim.say("dice", "%s fails: %s dissipates with no effect; its action is wasted" % (sim.S.name(caster), label))
            return True
        return False

    def _save(self, caster, dc, pc):
        ab = getattr(self.sim, "abilities", None)
        if ab:                                                   # Magic Resistance, Legendary Resistance, Bane ...
            return ab.general.save_roll(caster, "con", dc, COUNTER, me=pc)
        return self.sim.gm_rules.condition_save(caster, "con", dc, COUNTER)

    # ------------------------------------------------------------------ REACTIONS-LIVE-01: Hellish Rebuke, Uncanny Dodge
    def rebuke(self, pc, src):
        """pc took damage from src (Party.hellish_rebuke, once the damage settled): True when it casts Hellish Rebuke."""
        import invisibility
        sim, party = self.sim, self.sim.party
        if src is None or src == pc or party.side(src) == party.side(pc) or sim.down(src) or self.why_not(pc, REBUKE):
            return False
        if party.dist(pc, src) > 60 + 0.01 or not sim.sees(pc, src):
            return False
        c, free, who = sim.by_id(pc), self.free_rebuke(pc), sim.S.name(src)
        note = "%s makes a DC %d Dexterity save: 2d10 Fire, half on a success. It uses %s." % (
            who, party.spell_dc(c), "the free use of your Infernal Legacy (once per Long Rest)" if free else
            "your lowest spell slot (1d10 more for each level above 1)")
        if not self.ask(pc, REBUKE, "%s damages %s" % (who, c["name"]), note, free=free)["cast"]:
            return False
        with party.refereed(pc, REBUKE, dict({"target": src}, **({"free": "Infernal Legacy"} if free else {}))) as w:
            if free:
                lv, label = 1, "Hellish Rebuke (Reaction, Infernal Legacy: once a day without a slot)"
                party.rebuke_free[pc] = False
            else:
                lv = party.spend_slot(pc, 1)
                label = "Hellish Rebuke (Reaction, a level %d slot)" % lv
                w["cmd"]["slot"] = lv
            sim.S.setField(pc, "reaction", 1)
            party.area_spell(pc, c, label, [src], "Dexterity", "dex_save", "%dd10" % (lv + 1), "fire", "at %s" % who)
        invisibility.cast_spell(sim, pc, REBUKE)
        return True

    def dodge(self, pc, src):
        """An attack roll from src hit pc (fight_state's dodgeHit, the Reaction free): True when it uses Uncanny Dodge
        (fight_state then halves the attack's damage)."""
        sim = self.sim
        if self.why_not(pc, DODGE) or src is None or not sim.sees(pc, src):
            return False
        trigger = "%s's attack hits %s" % (sim.S.name(src), sim.by_id(pc)["name"])
        if not self.ask(pc, DODGE, trigger, "Uncanny Dodge halves this attack's damage.")["cast"]:
            return False
        sim.say("dice", "%s uses Uncanny Dodge (Reaction): the attack's damage is halved" % sim.by_id(pc)["name"])
        return True

    # ------------------------------------------------------------------ CUTTING-WORDS-01
    def cutting_words(self, src, tgt, total, ac):
        """src's attack roll hit tgt (total vs ac; fight_state, before Shield): the number a played Bard's Cutting Words
        takes off the roll, or 0. Each Bard who could make it miss is asked, nearest first, until one says yes."""
        import party as party_mod
        sim, party = self.sim, self.sim.party
        if not self.asks() or not party:
            return 0
        bards = [c["id"] for c in sim.sc["combatants"] if c.get("live") and c.get("pc")]
        bards.sort(key=lambda i: party.dist(i, src))
        for pc in bards:
            if party.side(pc) == party.side(src) or self.why_not(pc, CUT):
                continue
            if party.dist(pc, src) > 60 + 0.01 or not sim.sees(pc, src):
                continue
            c = sim.by_id(pc)
            sides = party_mod.bardic_die(int(c.get("level") or 1))
            need = total - ac + 1                                # the least roll that makes it miss
            if need > sides:
                continue                                         # no roll of the die could: not asked
            trigger = "%s's attack roll hits %s (%d vs AC %d)" % (sim.S.name(src), sim.by_id(tgt)["name"], total, ac)
            note = "Roll your d%d and take it off the attack roll: %d or more makes it miss. It spends one use of " \
                   "Bardic Inspiration (%d left)." % (sides, need, party.bi_uses.get(pc, 0))
            if not self.ask(pc, CUT, trigger, note)["cast"]:
                continue
            party.bi_uses[pc] -= 1
            sim.S.setField(pc, "reaction", 1)
            r = sim.rng.randint(1, sides)
            sim.say("dice", "%s uses Cutting Words (Reaction, Bardic Inspiration, %d left): d%d = %d off %s's attack roll "
                    "(%d -> %d vs AC %d: %s)" % (c["name"], party.bi_uses[pc], sides, r, sim.S.name(src), total, total - r,
                                                 ac, "a miss" if total - r < ac else "still a hit"))
            return r
        return 0

    # ------------------------------------------------------------------ OA-AUTO-01: Opportunity Attacks
    def opportunity(self, pc, mover):
        """mover left pc's reach (Run_sim.reaction_window, which checked the rest): True when its player makes the
        Opportunity Attack."""
        if self.why_not(pc, OA):
            return False
        sim, c = self.sim, self.sim.by_id(pc)
        w = c.get("weapon") or {}
        trigger = "%s leaves %s's reach" % (sim.S.name(mover), c["name"])
        note = "One melee attack with %s (%+d to hit, %s) against %s." % (w.get("name", "your weapon"), int(w.get("atk", 0)),
                                                                         w.get("dmg", "?"), sim.S.name(mover))
        return bool(self.ask(pc, OA, trigger, note)["cast"])

    # ------------------------------------------------------------------ MONK-01: Deflect Attacks, Slow Fall
    def deflect(self, pc, src, total, cut_more, feature=DEFLECT):
        """An attack roll from src hit pc for `total` damage (fight_state's deflectHit, the Reaction free): True when
        it uses Deflect Attacks (or Deflect Energy)."""
        sim = self.sim
        if self.why_not(pc, feature):
            return False
        who = sim.S.name(src) if src is not None else "An attack"
        trigger = "%s's attack hits %s for %d damage" % (who, sim.by_id(pc)["name"], total)
        note = "%s takes 1d10 %+d off this attack's damage (%d to %d: %s)." % (
            feature, cut_more, 1 + cut_more, 10 + cut_more,
            "always to 0" if 1 + cut_more >= total else "to 0 on %d or more" % (total - cut_more) if 10 + cut_more >= total
            else "it can't reach 0")
        if 10 + cut_more >= total:
            note += " At 0 you may spend 1 Focus Point to redirect the force."
        return bool(self.ask(pc, feature, trigger, note)["cast"])

    def redirect(self, pc, tid, kind, die, dex):
        """Deflect Attacks took the damage to 0: True when pc spends 1 Focus Point to redirect it at tid."""
        import monk
        sim, party = self.sim, self.sim.party
        if not self.asks() or threading.current_thread() is not (self.thread or self.fight.thread):   # OA-AUTO-01
            return False
        n = monk.points(party, pc)
        trigger = "%s's Deflect Attacks took the damage to 0" % sim.by_id(pc)["name"]
        note = "Redirect the force at %s: a DC %d Dexterity save, or 2d%d %+d %s damage." % (
            sim.S.name(tid), monk.save_dc(sim.by_id(pc)), die, dex, kind.title())
        return bool(self.ask(pc, REDIRECT, trigger, note, cost="It spends 1 Focus Point (%d left); the Reaction is "
                                                               "already Deflect Attacks'." % n)["cast"])

    def slow_fall(self, pc, dmg, cut, why):
        """pc falls (sim/environment.py, sim/traps.py), the Reaction free: True when it uses Slow Fall."""
        if self.why_not(pc, FALL):
            return False
        trigger = "%s falls (%s): %d falling damage" % (self.sim.by_id(pc)["name"], why, dmg)
        return bool(self.ask(pc, FALL, trigger, "Slow Fall takes %d off it (5 x your Monk level): %d left." % (
            cut, max(0, dmg - cut)))["cast"])

    def survivor(self, pc, total, dc, label, n):
        """GM 2026-10-28 (Disciplined Survivor, Monk 14): pc failed a save (total vs dc): True when it spends 1 Focus
        Point to roll it again (not a Reaction: asked even with the Reaction used)."""
        import monk
        sim = self.sim
        if not self.asks() or threading.current_thread() is not (self.thread or self.fight.thread):
            return False
        c = sim.by_id(pc)
        if sim.down(pc) or not c.get("disciplined_survivor"):
            return False
        trigger = "%s fails a %s save (%d vs DC %d)" % (c["name"], label, total, dc)
        return bool(self.ask(pc, SURVIVOR, trigger, "Roll the save again; the new roll stands.",
                             cost="It spends 1 Focus Point (%d left), not the Reaction." % n)["cast"])

    # ------------------------------------------------------------------ MARTIAL-HIGH: Retaliation, the d20 Tests
    def retaliation(self, pc, src, w):
        """src damaged pc from within 5 ft (sim/martial_high.py retaliate, the Reaction free): True when pc attacks it."""
        if self.why_not(pc, RETALIATE):
            return False
        sim = self.sim
        trigger = "%s damages %s from within 5 ft" % (sim.S.name(src), sim.by_id(pc)["name"])
        note = "One melee attack with %s (%+d to hit, %s) against %s." % (w.get("name", "your weapon"), int(w.get("atk", 0)),
                                                                         w.get("dmg", "?"), sim.S.name(src))
        return bool(self.ask(pc, RETALIATE, trigger, note)["cast"])

    def luck(self, pc, feature, trigger, note, cost):
        """A d20 of pc's failed (sim/martial_high.py): True when it uses `feature` (not a Reaction: asked even with the
        Reaction used)."""
        if not self.asks() or threading.current_thread() is not (self.thread or self.fight.thread):
            return False
        if self.sim.down(pc):
            return False
        return bool(self.ask(pc, feature, trigger, note, cost=cost)["cast"])
    # ------------------------------------------------------------------ EPIC-BOONS-01: Peerless Aim, Improve Fate
    def _boon_asks(self, pc):
        c = self.sim.by_id(pc)
        return self.asks() and threading.current_thread() is (self.thread or self.fight.thread) and c and c.get("live")             and not self.sim.down(pc)

    def peerless(self, pc, tid, total, ac):
        """Boon of Combat Prowess: pc's attack roll missed tid: True when it hits instead (not a Reaction)."""
        if not self._boon_asks(pc):
            return False
        trigger = "%s's attack roll misses %s (%d vs AC %d)" % (self.sim.by_id(pc)["name"], self.sim.S.name(tid), total, ac)
        return bool(self.ask(pc, PEERLESS, trigger, "Peerless Aim (Boon of Combat Prowess): the miss is a hit instead.",
                             cost="Once until the start of your next turn; not the Reaction.")["cast"])

    def fate(self, pc, trigger, note):
        """Boon of Fate: a D20 Test within 60 ft that 2d4 could turn: True when pc uses Improve Fate (not a Reaction)."""
        if not self._boon_asks(pc):
            return False
        return bool(self.ask(pc, FATE, trigger, note, cost="Once this fight (until Initiative or a rest); not the Reaction.")["cast"])
