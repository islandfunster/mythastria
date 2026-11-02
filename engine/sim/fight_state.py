"""FG-EXIT-01 step 1 (GM 2026-10-25: "archive the FG-only files listed in FG_EXIT_PLAN.md, then start step 1, the fight
state in Python"): the fight's state and its attack and damage rolls in Python, so Mythastria no longer needs the stand-in
Fantasy Grounds (sim/fake_fg.lua) for them. Nothing uses it yet: step 3 of docs/development/FG_EXIT_PLAN.md switches the
simulator over; until then test_fight_state.py plays the same calls and dice through both and compares every line.

FightState offers the calls Python makes on the Lua SIM table today, under the same names (addCombatant, addAction,
addEffect, removeEffect, effectLabels, startCombat, resumeCombat, nextActor, active, round, state, pcAttack, pcDamage,
setField, getField, setValue, getValue, heal, move, turnSerial, savageRecords), and the same hooks set on it
(say, rand, later, condMode, inspireMiss, reactHit, dodgeHit, onHit, onAttackRoll, fortitude, onDrop, onDamage, onHurt,
onAdjust, extraResist, gmTurnStart, holdStep, tokenMoved). A combatant is named by its id, as in SIM.

The rules, from SRD 5.2.1 (written fresh; behaviour matches the simulator's so recorded fights replay the same):
- turn order: Initiative, then the initiative bonus, then name (a stable order for ties); a new round after the last
  combatant; a creature at 0 HP is skipped (a dying character still takes its turn for death saves); a turn start gives
  the Reaction back;
- an attack roll: d20 + modifier against AC; Advantage and Disadvantage roll two d20s and cancel each other; a 20 (or the
  critical range) is a Critical Hit, a 1 always misses; Advantage against an Unconscious (0 HP) creature, and a hit from
  within 5 ft on a Paralyzed or Unconscious creature is a Critical Hit; a ranged attack with an enemy within 5 ft that is
  not Incapacitated has Disadvantage; Bless adds 1d4; reactions (Shield, Uncanny Dodge) and Bardic Inspiration through
  hooks;
- damage: a Critical Hit doubles the dice; Great Weapon Fighting counts a 1 or 2 as 3; Savage Attacker rerolls the weapon
  dice once a turn and keeps the higher; Immunity, then Resistance (halved, odd amounts rounded so two halved amounts in
  one hit lose no more than one point together), then Vulnerability (doubled), per damage type, untyped damage never
  adjusted; Temporary Hit Points are lost first; Undead Fortitude through a hook; a creature at 0 HP drops.
"""
import math
import re

DAMAGE_TYPES = {"acid", "bludgeoning", "cold", "fire", "force", "lightning", "necrotic", "piercing", "poison", "psychic",
                "radiant", "slashing", "thunder"}
STOPPED = {"incapacitated", "paralyzed", "petrified", "stunned", "unconscious"}   # no threat to a ranged attacker
LIST = "combattracker.list."


def _num(v, default=0):
    """A field read as a number (a text that is not a number reads as the default), as the simulator reads them."""
    if isinstance(v, bool) or v is None:
        return default
    if isinstance(v, (int, float)):
        return v
    try:
        f = float(str(v).strip())
    except ValueError:
        return default
    return int(f) if f.is_integer() else f


def _truthy(v):
    """Lua truth: only nil and false are false (0 and "" count as true)."""
    return v is not None and v is not False


def dice_list(expr):
    """"2d6+3" -> ["d6", "d6"]; every NdM in the text, N dice of M sides."""
    out = []
    for n, sides in re.findall(r"(\d*)d(\d+)", str(expr or "")):
        out += ["d" + sides] * int(n or 1)
    return out


class Combatant:
    def __init__(self, cid):
        self.id, self.fields, self.effects, self.actions = cid, {}, {}, {}
        self.px, self.py = 0, 0          # the token's position in pixels (squares x grid), as the map keeps it

    @property
    def path(self):
        return LIST + self.id


class FightState:
    def __init__(self, grid=50, units=5, diag=1, instant=True, rand=None, say=None, later=None):
        self.grid, self.units, self.diag, self.instant = grid, units, diag, instant
        self.rand = rand or (lambda n: 1)
        self.say = say or (lambda kind, text: None)
        self.later = later or (lambda fn: fn())
        self.combatants = {}                       # id -> Combatant, in the order added
        self.round_n = None                        # the round; unset until the fight starts
        self.turnSerial = 0
        self.pendingRolls, self.advancePending = 0, False
        self.lastAttack = None                     # {src, tgt, res} of the last attack roll (damage reads its crit)
        self.savageUsed, self.savageRecords = {}, []
        self.turnStart, self.attackPostResolve = [], []   # callbacks(id); callbacks(src, tgt, result)
        # creature abilities (sim/creature_abilities.py): callbacks(id) when a combatant's turn has ended (legendary
        # actions come right after it) and when one begins, before anything else (uses regained, Regeneration)
        self.turnEnded, self.turnBegins = [], []
        for hook in ("condMode", "inspireMiss", "reactHit", "dodgeHit", "onHit", "onAttackRoll", "fortitude", "onDrop",
                     "onDamage", "onHurt", "onAdjust", "extraResist", "gmTurnStart", "holdStep", "tokenMoved", "hitRedirect",
                     "cutWords", "deflectHit", "luckMiss"):
            setattr(self, hook, None)
        for hook in ("peerlessAim", "improveFate", "shadowResist"):   # EPIC-BOONS-01 (sim/epic_boons.py)
            setattr(self, hook, None)
        self.damageSrc = None                                    # EPIC-BOONS-01: who deals the damage adjust_damage weighs

    # ------------------------------------------------------------------ fields
    def _c(self, cid):
        return self.combatants[cid]

    def getValue(self, cid, key, default=None):
        v = self._c(cid).fields.get(key)
        return default if v is None else v

    def setValue(self, cid, key, value):
        self._c(cid).fields[key] = value

    def num(self, cid, key, default=0):
        return _num(self._c(cid).fields.get(key), default)

    def ac_now(self, cid):
        """The AC an attack roll is made against now: the AC (Haste, Slow change it), at least Barkskin's 17, plus
        Shield's +5 and Shield of Faith's +2. AC-SHOWN-01: the sheet shows this same number (tools/sim_messages.py)."""
        return max(self.num(cid, "ac", 10), self.num(cid, "sim_ac_floor")) + self.num(cid, "sim_ac_bonus") + \
            self.num(cid, "sim_ac_faith")

    def ac_why(self, cid):
        """What makes ac_now differ from the AC itself, in words: ["Shield +5", "Barkskin: AC 17", ...]."""
        ac, floor = self.num(cid, "ac", 10), self.num(cid, "sim_ac_floor")
        bonus, faith = self.num(cid, "sim_ac_bonus"), self.num(cid, "sim_ac_faith")
        return (["Barkskin: AC %d" % floor] if floor > ac else []) + (["Shield %+d" % bonus] if bonus else []) + \
            (["Shield of Faith %+d" % faith] if faith else [])

    def setField(self, cid, key, value):
        self._c(cid).fields[key] = value

    def getField(self, cid, key):
        return _num(self._c(cid).fields.get(key), 0)

    def name(self, cid):
        return self.getValue(cid, "name", "?")

    def down(self, cid):
        hp = self.num(cid, "hptotal")
        return hp > 0 and self.num(cid, "wounds") >= hp

    # ------------------------------------------------------------------ building a fight
    def addCombatant(self, c):
        c = dict(c)
        n = Combatant(c["id"])
        self.combatants[n.id] = n

        def setv(k, v):
            if v is not None:
                n.fields[k] = v

        def pick(v, default):
            return default if v is None or v is False else v

        setv("name", c.get("name")); setv("friendfoe", pick(c.get("side"), "")); setv("wounds", pick(c.get("wounds"), 0))
        setv("hptotal", c.get("hp")); setv("ac", pick(c.get("ac"), 10)); setv("initresult", pick(c.get("init"), 10))
        setv("init", c.get("init_bonus"))
        setv("speed", pick(c.get("speed"), "30 ft.")); setv("reach", pick(c.get("reach"), 5))
        setv("space", pick(c.get("space"), 5)); setv("reaction", pick(c.get("reaction"), 0)); setv("active", 0)
        setv("sim_savage_attacker", 1 if _truthy(c.get("savage_attacker")) else 0)
        setv("skills", c.get("skills")); setv("sim_wis_mod", c.get("wis_mod")); setv("senses", c.get("senses"))
        setv("type", c.get("type"))
        for k in ("damageimmunities", "damageresistances", "damagevulnerabilities"):
            setv(k, c.get(k))
        if c.get("int") is not None:
            n.fields["abilities.intelligence.score"] = c["int"]
        n.fields["pc"] = _truthy(c.get("pc"))
        if n.fields["pc"]:
            n.fields["level"] = pick(c.get("level"), 1)
        n.px, n.py = c["x"] * self.grid, c["y"] * self.grid
        return n.path

    def addAction(self, cid, a):
        a = dict(a)
        self._c(cid).actions[a["id"]] = a

    def addEffect(self, cid, label, active=True):
        eff = self._c(cid).effects
        i = 1
        while "id-%05d" % i in eff:
            i += 1
        eff["id-%05d" % i] = {"label": label, "isactive": 0 if active is False else 1}

    def removeEffect(self, cid, label):
        eff = self._c(cid).effects
        for k, e in list(eff.items()):
            if e["label"] == label:
                del eff[k]
                return True
        return False

    def effectLabels(self, cid):
        return {k: e["label"] for k, e in self._c(cid).effects.items()}

    def active_labels(self, cid):
        return [e["label"] for e in self._c(cid).effects.values() if _num(e.get("isactive"), 1) != 0]

    # ------------------------------------------------------------------ turn order
    def ordered(self):
        def key(n):
            return (-_num(n.fields.get("initresult"), 0), -_num(n.fields.get("init"), 0), n.fields.get("name", ""), n.path)
        return [n.id for n in sorted(self.combatants.values(), key=key)]

    def active(self):
        for cid in self.ordered():
            if self.num(cid, "active") == 1:
                return cid, self.getValue(cid, "name", "")
        return "", ""

    def round(self):
        return 1 if self.round_n is None else self.round_n

    def _new_round(self):
        self.round_n = (self.round_n or 0) + 1
        self.say("turn", "--- round %s ---" % self.round_n)

    def _gm_turn(self, cid):
        if self.gmTurnStart and self.gmTurnStart(cid):
            self.say("turn", self.name(cid) + " ends the turn (the simulator as GM)")
            self.later(self._advance_from(self.turnSerial))
            return True
        return False

    def _advance_from(self, serial):
        """A queued end of turn: it ends the turn it was queued for, never a later one. GM 2026-10-27 (the threat batch
        hung): a dying character's turn the simulator as GM took was also ended at once by the run loop (its death
        save); the queued end then fired inside the next creature's turn start and skipped that creature, whose turn
        the engine then waited for forever."""
        def go():
            if self.turnSerial == serial:
                self.nextActor()
        return go

    def _start_turn(self, cid):
        for fn in list(self.turnStart):
            try:
                fn(cid)
            except Exception as e:                  # a turn-start handler's error is reported, not swallowed
                self.say("error", "turn start: %s" % e)

    def startCombat(self):
        self.turnSerial += 1
        self.round_n = 1
        order = self.ordered()
        for cid in order:
            self.setValue(cid, "active", 0)
        first = order[0]
        self.setValue(first, "active", 1)
        self.say("turn", "--- round 1 ---")
        self.say("turn", self.name(first) + "'s turn")
        self._hooks(self.turnBegins, first, "turn begins")
        if not self._gm_turn(first):
            self._start_turn(first)

    def resumeCombat(self, cid, round_n, skip_current=False):
        """A saved fight goes on at its round with its active combatant, or with the next one when its turn was already
        under way."""
        self.turnSerial += 1
        self.round_n = round_n
        for c in self.ordered():
            self.setValue(c, "active", 0)
        self.setValue(cid, "active", 1)
        self.say("turn", "--- round %s ---" % round_n)
        if skip_current:
            self.say("turn", self.name(cid) + "'s turn was already under way in FG: continuing with the next combatant")
            self.nextActor()
            return
        self.setValue(cid, "reaction", 0)
        self.say("turn", self.name(cid) + "'s turn")
        self._hooks(self.turnBegins, cid, "turn begins")
        self._start_turn(cid)

    def _skippable(self, cid):
        return self.down(cid) and self.num(cid, "sim_dying") != 1

    def nextActor(self):
        if self.pendingRolls > 0:                  # dice still to land: the next turn waits for them
            if not self.advancePending:
                self.advancePending = True
                then = self._advance_from(self.turnSerial)

                def go():
                    self.advancePending = False
                    then()
                self.later(go)
            return
        order = self.ordered()
        idx = -1
        for i, cid in enumerate(order):
            if self.num(cid, "active") == 1:
                idx = i
        if idx >= 0 and self.turnEnded and getattr(self, "_ended", None) != self.turnSerial:
            self._ended = self.turnSerial               # once per turn, whatever the callbacks do
            self._hooks(self.turnEnded, order[idx], "turn end")
        if idx >= 0 and self.round() == 1 and self.num(order[idx], "sim_reflexes") == 1:
            self._reflexes(order[idx])                  # MARTIAL-HIGH: Thief's Reflexes, a second turn in round 1
            order, idx = self.ordered(), idx - 1        # whoever followed it goes next (itself, if no one is between)
        for cid in order:
            self.setValue(cid, "active", 0)
        nxt = idx + 1
        if nxt >= len(order):
            nxt = 0
            self._new_round()
            order = self._reflexes_back(order)
        for _ in range(len(order)):
            if not self._skippable(order[nxt]):
                break
            self.say("turn", self.name(order[nxt]) + " is down: turn skipped")
            nxt += 1
            if nxt >= len(order):
                nxt = 0
                self._new_round()
                order = self._reflexes_back(order)
        cid = order[nxt]
        if self._skippable(cid):
            return                                  # everyone is down
        self.turnSerial += 1
        self.setValue(cid, "active", 1)
        self.setValue(cid, "reaction", 0)
        self.setValue(cid, "sim_no_oa", 0)                  # GM 2026-10-25 (S2): Shocking Grasp ends at its turn start
        self.say("turn", self.name(cid) + "'s turn")
        self._hooks(self.turnBegins, cid, "turn begins")
        if not self._gm_turn(cid):
            self._start_turn(cid)

    def _reflexes(self, cid):
        """MARTIAL-HIGH (SRD 5.2.1 Thief's Reflexes, Thief 17): "You can take two turns during the first round of any
        combat. You take your first turn at your normal Initiative and your second turn at your Initiative minus 10."
        Its Initiative is lowered for the rest of the first round; the turn order puts it there."""
        init = _num(self.getValue(cid, "initresult"), 0)
        self.setValue(cid, "sim_reflexes", 2)
        self.setValue(cid, "sim_reflexes_init", init)
        self.setValue(cid, "initresult", init - 10)
        self.say("turn", "Thief's Reflexes: %s takes a second turn this round, at Initiative %d" % (self.name(cid), init - 10))

    def _reflexes_back(self, order):
        """The first round is over: Thief's Reflexes' Initiative back (the order of the rounds after it)."""
        moved = [c for c in order if self.num(c, "sim_reflexes") == 2]
        for c in moved:
            self.setValue(c, "initresult", self.getValue(c, "sim_reflexes_init"))
            self.setValue(c, "sim_reflexes", 3)
        return self.ordered() if moved else order

    def _hooks(self, fns, cid, what):
        for fn in list(fns):
            try:
                fn(cid)
            except Exception as e:                  # reported, not swallowed
                self.say("error", "%s: %s: %s" % (what, type(e).__name__, e))

    # ------------------------------------------------------------------ the map
    def state(self, cid):
        n = self._c(cid)
        return (self.getValue(cid, "wounds", 0), self.getValue(cid, "hptotal", 0), n.px / self.grid, n.py / self.grid,
                self.getValue(cid, "reaction", 0))

    def size_squares(self, cid):
        return max(1, math.floor(_num(self.getValue(cid, "space", 5), 5) / self.units + 0.5))

    def distance(self, a, b):
        """Feet between two creatures' nearest squares, by the map's diagonal rule (1: every square 5 ft; 1.5: every
        second diagonal 10 ft; "*": straight line), rounded to the nearest square."""
        ca, cb, g = self._c(a), self._c(b), self.grid
        sa, sb = self.size_squares(a), self.size_squares(b)
        dx = max(0, abs(ca.px - cb.px) / g - (sa - 1) / 2 - (sb - 1) / 2)
        dy = max(0, abs(ca.py - cb.py) / g - (sa - 1) / 2 - (sb - 1) / 2)
        hi, lo = max(dx, dy), min(dx, dy)
        sq = hi
        if self.diag == "*":
            sq = math.sqrt(dx * dx + dy * dy)
        elif self.diag == 1.5:
            sq = hi + math.floor(lo / 2)
        return math.floor(sq + 0.5) * self.units

    def move(self, cid, x, y):
        self.say("turn", "%s moves to (%s, %s)" % (self.name(cid), _g(x), _g(y)))
        self.step(cid, x, y)

    def step(self, cid, x, y):
        """One step of a token to square (x, y), without the move line (a creature's planned route says its feet once)."""
        n = self._c(cid)
        nx, ny = x * self.grid, y * self.grid
        if self.holdStep and self.holdStep(self.name(cid), n.px, n.py, nx, ny):
            return                                  # a creature a trap caught stays put
        ox, oy = n.px, n.py
        n.px, n.py = nx, ny
        if self.tokenMoved:
            self.tokenMoved(self.name(cid), ox, oy, nx, ny)

    def place(self, cid, x, y):
        """Put a token on square (x, y) with no step at all (an undone move goes back): no hooks run."""
        n = self._c(cid)
        n.px, n.py = x * self.grid, y * self.grid

    def heal(self, cid, amount):
        w = max(0, self.num(cid, "wounds") - amount)
        self.setValue(cid, "wounds", w)
        return w

    # ------------------------------------------------------------------ rolls
    def stopped(self, cid):
        """Incapacitated, Paralyzed, Petrified, Stunned or Unconscious (an effect, or 0 HP)."""
        for label in self.active_labels(cid):
            if any(part.strip().lower() in STOPPED for part in str(label).split(";")):
                return True
        return self.down(cid)

    def range_disadvantage(self, src, roll):
        """A ranged attack roll with a hostile creature within 5 ft that is not Incapacitated has Disadvantage."""
        if roll.get("sType") != "attack" or roll.get("sRange") != "R":
            return
        side = self.getValue(src, "friendfoe", "")
        for cid in self.combatants:
            other = self.getValue(cid, "friendfoe", "")
            hostile = cid != src and ((side == "foe" and other == "friend") or (side == "friend" and other == "foe"))
            if hostile and self.distance(src, cid) <= 5 and not self.stopped(cid):
                roll["bDIS"] = True
                roll.setdefault("tNotifications", []).append("[RANGED ATTACK NEXT TO ENEMY]")
                return

    def actionRoll(self, src, tgt, rolls):
        """A creature's rolls (sim/creature_turns.py): the range rule first, then each roll, at once or on the next
        step."""
        for roll in rolls:
            self.range_disadvantage(src, roll)
            if self.instant:
                self.resolve(src, tgt, roll)
            else:
                self.pendingRolls += 1

                def land(roll=roll):
                    self.pendingRolls -= 1
                    self.resolve(src, tgt, roll)
                self.later(land)

    def resolve(self, src, tgt, roll):
        if roll.get("sType") == "attack":
            self._attack(src, tgt, roll)
        elif roll.get("sType") == "damage":
            self._damage(src, tgt, roll)
        else:
            self.say("dice", "unsupported roll type %s (not simulated)" % roll.get("sType"))

    def _labelled(self, cid, labels):
        for e in self._c(cid).effects.values():
            if e["label"] in labels and _num(e.get("isactive"), 1) == 1:
                return True
        return False

    def roll_mode(self, src, tgt, roll, peek=False):
        """Advantage and Disadvantage of one attack roll, before the d20. peek (HINTS-01 H5: the attack hint asks it
        without rolling): nothing is used up (Sap, Vicious Mockery, Stunning Strike, Help).
        -> (adv, dis, notes for the log line, modifier, why): why [(how, note)], how "adv", "dis", "either" (a hook that
        gave both) or "off" (Elusive took the Advantage away)."""
        adv, dis = bool(roll.get("bADV")), bool(roll.get("bDIS"))
        why = []
        if self.down(tgt):
            adv = True                                   # attack rolls against an Unconscious creature
            why.append(("adv", "[target at 0 HP]"))
        notes = roll.setdefault("tNotifications", [])
        if self.num(tgt, "sim_reckless") == 1:
            adv = True; notes.append("[Reckless Attack]"); why.append(("adv", "[Reckless Attack]"))
        if self.num(src, "sim_sapped") == 1:
            dis = True; notes.append("[Sap]"); why.append(("dis", "[Sap]"))
            if not peek:
                self.setValue(src, "sim_sapped", 0)
        if self.num(src, "sim_mocked") == 1:
            dis = True; notes.append("[Vicious Mockery]"); why.append(("dis", "[Vicious Mockery]"))
            if not peek:
                self.setValue(src, "sim_mocked", 0)
        if self.num(tgt, "sim_struck") == 1:                     # MONK-01: Stunning Strike saved: the next attack roll
            adv = True; notes.append("[Stunning Strike]"); why.append(("adv", "[Stunning Strike]"))
            if not peek:
                self.setValue(tgt, "sim_struck", 0)
        mod = _num(roll.get("nMod"), 0)
        if self.condMode:
            out = self.condMode(src, tgt, roll.get("sRange") or "", roll.get("sim_dmgtype") or "", bool(roll.get("sim_spell")),
                                *((True,) if peek else ()))
            out = tuple(out) if isinstance(out, (tuple, list)) else (out,)
            cadv, cdis, cnotes, cmod, cwhy = (tuple(out) + (None, None, None, None, None))[:5]
            if _truthy(cadv):
                adv = True
            if _truthy(cdis):
                dis = True
            if cnotes:
                notes.append(cnotes)
            if _num(cmod, 0) != 0:
                mod = mod + _num(cmod, 0)
            why += list(cwhy or [])
        if adv and self.num(tgt, "sim_elusive") == 1 and not self.down(tgt) and not self._labelled(
                tgt, ("Incapacitated", "Paralyzed", "Petrified", "Stunned", "Unconscious")):
            adv = False; notes.append("[Elusive: no Advantage]")   # group 3: Elusive (Rogue 18)
            why.append(("off", "[Elusive: no Advantage]"))
        return adv, dis, notes, mod, why

    def _attack(self, src, tgt, roll):
        sname, tname = self.name(src), self.name(tgt)
        adv, dis, notes, mod, _ = self.roll_mode(src, tgt, roll)
        d20 = self.rand(20)
        mode = ""
        if adv != dis:
            d2 = self.rand(20)
            mode = " [%s %d/%d]" % ("ADV" if adv else "DIS", d20, d2)
            d20 = max(d20, d2) if adv else min(d20, d2)
        total = d20 + mod
        if _num(roll.get("nBless"), 0) > 0:
            b = self.rand(roll["nBless"])
            total += b
            mode += " +%d Bless" % b
        ac = self.ac_now(tgt)                                    # SPELL-BATCH-01: Barkskin, AC 17 if lower
        crit_min = _num(roll.get("nCritMin"), 20) if roll.get("nCritMin") is not None else 20
        res = "crit" if d20 >= crit_min else ("hit" if d20 != 1 and total >= ac else "miss")
        if res == "miss" and d20 != 1 and self.inspireMiss:
            add = _num(self.inspireMiss(src, total, ac), 0)
            if add > 0:
                total += add
                mode += " +%d Bardic Inspiration" % add
                res = "hit" if total >= ac else "miss"
        if res == "miss" and self.luckMiss:                       # MARTIAL-HIGH: Heroic Inspiration, Stroke of Luck
            new = _num(self.luckMiss(src, tgt, d20, total, ac), 0)
            if new > 0:
                total += new - d20
                mode += " [d20 %d -> %d]" % (d20, new)
                d20 = new
                res = "crit" if d20 >= crit_min else ("hit" if d20 != 1 and total >= ac else "miss")
        if res == "hit" and self.distance(src, tgt) <= 5 and self._labelled(tgt, ("Paralyzed", "Unconscious")):
            res = "crit"; mode += " [CONVERTED TO CRIT]"
        if res == "hit" and self.down(tgt) and self.distance(src, tgt) <= 5:
            res = "crit"; mode += " [UNCONSCIOUS: critical]"
        if res in ("hit", "miss") and d20 != 1 and self.improveFate:   # EPIC-BOONS-01: Boon of Fate, 2d4 on or off
            fate = _num(self.improveFate(src, tgt, total, ac, res), 0)
            if fate:
                total += fate
                mode += " %+d Boon of Fate" % fate
                res = "hit" if total >= ac else "miss"
        if res == "hit" and self.cutWords:                       # CUTTING-WORDS-01: a Bard's die off the roll, first
            cut = _num(self.cutWords(src, tgt, total, ac), 0)
            if cut > 0:
                total -= cut
                mode += " -%d Cutting Words" % cut
                res = "hit" if total >= ac else "miss"
        if res == "hit" and self.reactHit and self.num(tgt, "reaction") == 0:
            out = self.reactHit(tgt, total, ac, False, roll.get("sRange") != "R", src)
            out = tuple(out) if isinstance(out, (tuple, list)) else (out,)
            bonus, lasting = (out + (None, None))[:2]
            bonus = _num(bonus, 0)
            if bonus > 0:
                self.setValue(tgt, "reaction", 1)
                if _truthy(lasting):
                    self.setValue(tgt, "sim_ac_bonus", self.num(tgt, "sim_ac_bonus") + bonus)
                ac += bonus
                res = "hit" if total >= ac else "miss"
        if res == "miss" and self.peerlessAim and self.peerlessAim(src, tgt, total, ac):   # EPIC-BOONS-01: Peerless Aim
            res = "hit"; mode += " [Peerless Aim: a hit]"
        if res in ("hit", "crit") and self.hitRedirect:          # SPELL-BATCH-01: Mirror Image's duplicate
            note = self.hitRedirect(src, tgt)
            if note:
                res = "miss"; notes.append(note)
        for note in notes:
            mode += " " + note
        self.say("dice", "%s attacks %s%s: d20 %d %+d = %d vs AC %d -> %s" % (sname, tname, mode, d20, mod, total, ac, res))
        if res in ("hit", "crit") and self.dodgeHit and self.num(tgt, "reaction") == 0:
            if self.dodgeHit(tgt, src):
                self.setValue(tgt, "reaction", 1)
                self.setValue(tgt, "sim_halve_next", 1)
        self.lastAttack = {"src": src, "tgt": tgt, "res": res, "ranged": roll.get("sRange") == "R", "d20": d20}
        if self.onHit and roll.get("sim_action"):
            self.onHit(src, tgt, roll["sim_action"], res)
        if self.onAttackRoll:
            self.onAttackRoll(src)
        for fn in list(self.attackPostResolve):
            try:
                fn(src, tgt, {"sResult": res, "sType": "attack"})
            except Exception as e:
                self.say("error", "onAttackPostResolve: %s" % e)
        return res

    def _die(self, sides, gwf):
        r = self.rand(sides)
        return 3 if gwf and r < 3 else r

    def _type_set(self, cid, field):
        return {w for w in re.findall(r"[a-z]+", str(self.getValue(cid, field, "") or "").lower()) if w in DAMAGE_TYPES}

    @staticmethod
    def _listed(types, key):
        """A damage type key ("fire", or "bludgeoning, magic") counts only when each basic type in it is in the set."""
        basic = False
        for t in key.split(","):
            t = t.strip()
            if t in DAMAGE_TYPES:
                basic = True
                if t not in types:
                    return False
        return basic

    def adjust_damage(self, tgt, clauses, parts):
        immune, resist, vuln = (self._type_set(tgt, f) for f in ("damageimmunities", "damageresistances", "damagevulnerabilities"))
        rage = self.num(tgt, "sim_resist_bps") == 1
        if self.extraResist:
            resist |= {w for w in re.findall(r"[a-z]+", str(self.extraResist(tgt) or "")) if w in DAMAGE_TYPES}
        own = set(resist)
        if rage:
            resist |= {"bludgeoning", "piercing", "slashing"}
        defense = self.num(tgt, "sim_resist_all") == 1 and not self.down(tgt) and not self._labelled(
            tgt, ("Incapacitated", "Paralyzed", "Petrified", "Stunned", "Unconscious"))
        if defense:                                      # GM 2026-10-28: Superior Defense (Monk 18), all but Force
            resist |= DAMAGE_TYPES - {"force"}
        shadow = self.num(tgt, "sim_shadowy") == 1 and bool(self.shadowResist) and self.shadowResist(tgt)
        if shadow:                                       # EPIC-BOONS-01: Shadowy Form, all but Psychic and Radiant
            resist |= DAMAGE_TYPES - {"psychic", "radiant"}
        src = self.damageSrc                             # EPIC-BOONS-01: Overcome Defenses ignores B/P/S Resistance
        overcome = resist & {"bludgeoning", "piercing", "slashing"} if src and self.num(src, "sim_overcome") == 1 else set()
        resist -= overcome
        sums = {}
        for i, c in enumerate(clauses):
            key = str(c.get("dmgtype") or "").lower().strip()
            sums[key] = sums.get(key, 0) + (parts[i] if i < len(parts) else 0)
        total, carry, seen = 0, False, []

        def note(text):
            if text not in seen:
                seen.append(text)
        for key, v in sums.items():
            if key != "" and v > 0:
                if self._listed(immune, key):
                    v = 0
                    note("Immunity: " + key + ", none")
                    if self.onAdjust:
                        self.onAdjust(tgt, key, "immune")
                else:
                    if self._listed(resist, key):
                        cut = math.ceil(v / 2)
                        if v % 2 == 1:
                            if carry:
                                cut -= 1; carry = False
                            else:
                                carry = True
                        v -= cut
                        note("Shadowy Form: Resistance, halved" if shadow and not defense and not self._listed(own, key) and not rage else
                             "Superior Defense: Resistance, halved" if defense and not self._listed(own, key) and not rage else
                             "Rage: Resistance, halved" if rage and not self._listed(own, key) else "Resistance: " + key + ", halved")
                        if self.onAdjust and self._listed(own, key):
                            self.onAdjust(tgt, key, "resistant")
                    elif overcome and self._listed(overcome, key):
                        note("Overcome Defenses: Resistance ignored")
                    if self._listed(vuln, key):
                        v *= 2
                        note("Vulnerability: " + key + ", doubled")
                        if self.onAdjust:
                            self.onAdjust(tgt, key, "vulnerable")
            total += v
        return total, "".join(" [%s]" % t for t in seen)

    def _damage(self, src, tgt, roll):
        sname, tname = self.name(src), self.name(tgt)
        la = self.lastAttack
        crit = bool(la and la["src"] == src and la["tgt"] == tgt and la["res"] == "crit")
        clauses = roll.get("clauses") or []
        weapon_total, weapon_dice, parts, first_weapon, gwf_used = 0, 0, [], None, False
        top = getattr(self, "maxSrc", None) == src               # CASTER-HIGH: Overchannel, every die at its highest
        faces = []                                               # the attack's own dice as they fell (Sorcerous Burst)
        for i, c in enumerate(clauses):
            part = 0
            for die in c.get("dice") or []:
                sides = int(re.search(r"\d+", str(die)).group()) if re.search(r"\d+", str(die)) else 4
                rolled = sides if top else self._die(sides, c.get("sim_gwf"))
                if c.get("sim_weapon"):
                    faces.append(rolled)
                if crit:
                    again = sides if top else self._die(sides, c.get("sim_gwf"))
                    rolled += again
                    if c.get("sim_weapon"):
                        faces.append(again)
                if c.get("sim_gwf"):
                    gwf_used = True
                part += rolled
                if c.get("sim_weapon"):
                    weapon_total += rolled
                    weapon_dice += 1
            if c.get("sim_weapon") and first_weapon is None:
                first_weapon = i
                self.weaponFaces = faces
            parts.append(part + _num(c.get("modifier"), 0))
        actor, turn = LIST + src, self.turnSerial
        hit = bool(la and la["src"] == src and la["tgt"] == tgt and la["res"] in ("hit", "crit"))
        if hit and weapon_dice > 0 and self.num(src, "sim_savage_attacker") == 1 and self.savageUsed.get(actor) != turn:
            second = 0                                  # Savage Attacker: the weapon's dice again, the higher total kept
            for c in clauses:
                if c.get("sim_weapon"):
                    for die in c.get("dice") or []:
                        sides = int(re.search(r"\d+", str(die)).group()) if re.search(r"\d+", str(die)) else 4
                        second += self._die(sides, c.get("sim_gwf"))
                        if crit:
                            second += self._die(sides, c.get("sim_gwf"))
            chosen = max(weapon_total, second)
            parts[first_weapon] = parts[first_weapon] - weapon_total + chosen
            self.savageUsed[actor] = turn
            self.savageRecords.append({"actor": actor, "turn": turn, "first": weapon_total, "second": second, "chosen": chosen})
            self.say("feat", "Savage Attacker: %s; turn %d; weapon dice %d vs %d -> %d (modifier added once)"
                     % (sname, turn, weapon_total, second, chosen))
        if gwf_used:
            self.say("feat", "Great Weapon Fighting: " + sname + "'s damage dice of 1 or 2 count as 3")
        self.damageSrc = src
        try:
            total, notes = self.adjust_damage(tgt, clauses, parts)
        finally:
            self.damageSrc = None
        total = max(0, total)
        if self.num(tgt, "sim_halve_next") == 1:
            self.setValue(tgt, "sim_halve_next", 0)
            total = total // 2
            notes += " [Uncanny Dodge: halved]"
        if hit and total > 0 and self.deflectHit and self.num(tgt, "reaction") == 0:   # MONK-01: Deflect Attacks
            kinds = ",".join(sorted({str(c.get("dmgtype") or "").lower().strip() for i, c in enumerate(clauses)
                                     if i < len(parts) and parts[i] > 0} - {""}))
            cut = min(total, _num(self.deflectHit(tgt, src, total, kinds, bool(la.get("ranged"))), 0))
            if cut > 0:
                self.setValue(tgt, "reaction", 1)
                total -= cut
                notes += " [Deflect Attacks: -%d]" % cut
        taken = total
        temp = self.num(tgt, "sim_temp_hp")
        if temp > 0 and total > 0:
            soak = min(temp, total)
            self.setValue(tgt, "sim_temp_hp", temp - soak)
            total -= soak
            notes += " [%d taken by Temporary Hit Points, %d left]" % (soak, temp - soak)
        hp, w = self.num(tgt, "hptotal"), self.num(tgt, "wounds")
        if hp > 0 and w < hp and w + total >= hp and self.fortitude:
            radiant = any("radiant" in str(c.get("dmgtype") or "").lower() and parts[i] > 0 for i, c in enumerate(clauses))
            kept = self.fortitude(tgt, taken, radiant, crit)
            if kept:
                total = hp - w - 1
                taken = total
                notes += " [%s: 1 HP]" % (kept if isinstance(kept, str) else "Undead Fortitude")   # SPELLS-4-6: Death Ward
        nw = min(hp, w + total)
        was_down = hp > 0 and w >= hp
        self.say("dice", "%s deals %d damage to %s (%d/%d HP left)%s" % (sname, taken, tname, hp - nw, hp, notes))
        if total > 0:
            self.setValue(tgt, "wounds", nw)
        if nw >= hp and hp > 0 and not was_down:
            self.say("turn", tname + " drops to 0 hit points")
            if self.onDrop:
                self.onDrop(tgt)
        if taken > 0 and self.onDamage:
            self.onDamage(tgt, taken, crit, was_down)
        if taken > 0 and self.onHurt:                   # HAZARDS-01: the damage types that dealt it
            self.onHurt(src, tgt, taken, ",".join(str(c.get("dmgtype") or "").lower()
                                                  for i, c in enumerate(clauses) if parts[i] > 0))

    # ------------------------------------------------------------------ a character's own rolls (party.py, live_play.py)
    def pcAttack(self, cid, tid, atk, crit_min=None, dice="", bonus=0, mode=None, graze=0, bless=0, extra="", dmgtype="",
                 ranged=False, spell=False):
        roll = {"sType": "attack", "nMod": atk, "nCritMin": crit_min, "bADV": mode == "adv", "bDIS": mode == "dis",
                "nBless": bless, "sRange": "R" if _truthy(ranged) else "M", "sim_dmgtype": dmgtype or "", "sim_spell": spell}
        res = self._attack(cid, tid, roll)
        if res in ("hit", "crit"):
            gwf = not _truthy(ranged) and self.num(cid, "sim_gwf") == 1   # Great Weapon Fighting: a two-handed melee weapon
            clauses = [{"dice": dice_list(dice), "modifier": bonus, "sim_weapon": True, "sim_gwf": gwf, "dmgtype": dmgtype or ""}]
            if res == "crit" and (self.lastAttack or {}).get("d20") == 20 and self.num(cid, "sim_overwhelm") > 0:
                more = self.num(cid, "sim_overwhelm")            # EPIC-BOONS-01: Overwhelming Strike, the boon's score
                self.say("feat", "Overwhelming Strike (Boon of Irresistible Offense): a 20 on the d20, %d more %s damage"
                         % (more, dmgtype or "of the attack's type"))
                clauses.append({"dice": [], "modifier": more, "dmgtype": dmgtype or ""})
            for entry in str(extra or "").split(";"):
                if not entry:
                    continue
                m = re.match(r"^\s*(.*?)\s*:\s*(.*?)\s*$", entry)
                clauses.append({"dice": dice_list(m.group(1) if m else entry), "modifier": 0, "dmgtype": (m.group(2) if m else "")})
            self._damage(cid, tid, {"sType": "damage", "clauses": clauses})
        elif _num(graze, 0) > 0:
            self.say("feat", "Graze: the attack missed; %s still deals %s damage" % (self.name(cid), graze))
            self._damage(cid, tid, {"sType": "damage", "clauses": [{"dice": [], "modifier": _num(graze, 0), "dmgtype": dmgtype or ""}]})
        return res

    def pcDamage(self, cid, tid, dice, bonus=0, crit=False, dmgtype=""):
        """Damage with no attack roll (Magic Missile); crit: the extra damage of a Critical Hit that just landed."""
        self.lastAttack = {"src": cid, "tgt": tid, "res": "crit"} if _truthy(crit) else None
        self._damage(cid, tid, {"sType": "damage", "clauses": [{"dice": dice_list(dice), "modifier": bonus, "dmgtype": dmgtype or ""}]})


def _g(v):
    """A coordinate as the move line prints it (2, 9.5)."""
    return "%g" % v
