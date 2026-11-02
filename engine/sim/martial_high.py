"""MARTIAL-HIGH (GM 2026-10-28): the Fighter, Rogue (Thief), Barbarian (Berserker) and Paladin (Devotion) features of
levels 2-20 that went to Ask the GM, played in a fight, SRD 5.2.1. A player's choice that comes up on another creature's
roll, or right after the player's own d20 fails, is asked live (sim/live_reactions.py, like Disciplined Survivor and
Uncanny Dodge); the computer-played heroes (and the GM's Auto mode) choose as written below. sim/high_levels.py holds
the other level 9-20 features; its flags come from the sheet the same way (sim/character_build.py FEATURE_FLAGS).

- Tactical Mind (Fighter 2): "When you fail an ability check, you can expend a use of your Second Wind ... roll 1d10 and
  add the number rolled to the ability check ... If the check still fails, this use of Second Wind isn't expended."
  The checks a fight rolls: Hide, Study, Influence. The computer: when the d10 can still make it.
- Tactical Shift (Fighter 5): Second Wind with a Bonus Action: "you can move up to half your Speed without provoking
  Opportunity Attacks" (Play live: half the Speed more movement this turn; a move that fits inside it provokes none).
  The computer-played Fighter does not step away.
- Heroic Warrior (Champion 10): "During combat, you can give yourself Heroic Inspiration whenever you start your turn
  without it." Heroic Inspiration rerolls the d20 of a missed attack roll, a failed saving throw or a failed check, the
  new roll kept (the computer: always).
- Devious Strikes (Rogue 14), new Cunning Strike options: Daze (2 dice; Constitution save; on its next turn it does only
  one of moving, an action or a Bonus Action), Knock Out (6 dice; Constitution save; Unconscious for 1 minute or until
  it takes damage, a save again at the end of each of its turns), Obscure (3 dice; Dexterity save; Blinded until the end
  of its next turn). One Sneak Attack die at least stays; with Improved Cunning Strike two options on one Sneak Attack.
  The computer: Knock Out on a foe its Sneak Attack won't drop.
- Thief's Reflexes (Thief 17): "You can take two turns during the first round of any combat ... your first turn at your
  normal Initiative and your second turn at your Initiative minus 10" (sim/fight_state.py nextActor).
- Stroke of Luck (Rogue 20): "If you fail a D20 Test, you can turn the roll into a 20"; once per Short or Long Rest. On
  an attack roll a 20 is a Critical Hit. The computer: a missed Sneak Attack, or a failed save the 20 turns.
- Retaliation (Berserker 10): "When you take damage from a creature that is within 5 feet of you, you can take a Reaction
  to make one melee attack against that creature."
- Intimidating Presence (Berserker 14): Bonus Action; each creature of its choice in a 30-foot Emanation makes a Wisdom
  save (DC 8 + Strength modifier + Proficiency Bonus) or is Frightened for 1 minute, a save again at the end of each of
  its turns; once per Long Rest, or "expend a use of your Rage (no action required) to restore your use of it". The
  computer: three foes or more within 30 ft, once the Rage is on.
- Restoring Touch (Paladin 14): Lay On Hands also ends Blinded, Charmed, Deafened, Frightened, Paralyzed or Stunned, 5
  points of the pool each (those points heal nothing). The computer: an ally in touch Paralyzed or Stunned.
- Smite of Protection (Devotion 15): "Whenever you cast Divine Smite, you and your allies have Half Cover while in your
  Aura of Protection" until the start of her next turn (Half Cover: +2 AC and Dexterity saves; it doesn't add to other
  cover, the better counts). Play live's Divine Smite is an Ask the GM spell: casting it there turns this on too.
- Holy Nimbus (Devotion 20): Bonus Action, 10 minutes (the fight): Advantage on her saves a Fiend or an Undead forces;
  each enemy that starts its turn in her aura takes Radiant damage of her Charisma modifier + Proficiency Bonus; the
  aura is sunlight; once per Long Rest, or a level 5 slot restores it. The computer: at once, a foe within 60 ft.
Not here: Use Magic Device (Thief 13) stays with the GM: its charges and Spell Scrolls are not items the table uses in a
fight, and Attunement is outside it.
"""
from high_levels import FT, HighError, _state, aura_ft, has, mod, score

OPS = ("intimidating_presence", "holy_nimbus")
DAY_USES = ("stroke_of_luck", "intimidating_presence", "holy_nimbus")    # sim/rests.py USES carries them
DEVIOUS = {"daze": ("Daze", 2, "con"), "knock_out": ("Knock Out", 6, "con"), "obscure": ("Obscure", 3, "dex")}
CUNNING = {"trip": ("Trip", "dex"), "poison": ("Poison", "con"), "withdraw": ("Withdraw", None)}   # Rogue 5: one die each
RESTORE = ("Blinded", "Charmed", "Deafened", "Frightened", "Paralyzed", "Stunned")
HEROIC, STROKE, TMIND = "Heroic Inspiration", "Stroke of Luck", "Tactical Mind"


def pb(c):
    return 2 + (int(c.get("level", 1) or 1) - 1) // 4


def uses_left(party, me, key):
    """A use the day carries (once per Long Rest; Stroke of Luck also a Short Rest): 1 or 0."""
    d = _state(party, "martial_left").setdefault(me, {})
    if key not in d:
        d[key] = 1 if party.sim.by_id(me).get(key) else 0
    return d[key]


def spend_use(party, me, key):
    _state(party, "martial_left").setdefault(me, {})[key] = max(0, uses_left(party, me, key) - 1)


def day_apply(party, i, e):
    """sim/rests.py apply_to_sim: the day's carried uses."""
    for key in DAY_USES:
        if key in e["uses_max"]:
            _state(party, "martial_left").setdefault(i, {})[key] = int(e["uses"].get(key, 0))


def day_capture(party, i, e):
    """sim/rests.py capture: what is left when the fight ends."""
    for key in DAY_USES:
        if key in e["uses_max"]:
            e["uses"][key] = int(uses_left(party, i, key))


def setup(party, pcs):
    """Party.__init__: the fight state's hook on a missed attack roll, and Thief's Reflexes' mark."""
    party.s.luckMiss = lambda src, tgt, d20, total, ac: luck_miss(party, src, tgt, d20, total, ac)
    for c in pcs:
        if has(c, "thiefs_reflexes", "Thief's Reflexes"):
            party.s.setField(c["id"], "sim_reflexes", 1)


def turn_start(party, me):
    """The start of a member's turn: its Smite of Protection ends; Heroic Warrior's Heroic Inspiration."""
    c = party.sim.by_id(me)
    if _state(party, "smite_cover").pop(me, None):
        party.sim.say("dice", "%s's Smite of Protection ends (the start of %s's turn)" % (c["name"], c["name"]))
    heroic = _state(party, "heroic")
    if has(c, "heroic_warrior", "Heroic Warrior") and not party.down(me) and not heroic.get(me):
        heroic[me] = True
        party.sim.say("dice", "%s: Heroic Warrior, Heroic Inspiration at the start of the turn" % c["name"])


# ---------------------------------------------------------------------- d20 Tests
def lucky(party, me):
    """Something that may change a failed check of this member's now."""
    c = party.sim.by_id(me)
    return bool(_state(party, "heroic").get(me) or has(c, "tactical_mind", TMIND) or
                (has(c, "stroke_of_luck", STROKE) and uses_left(party, me, "stroke_of_luck")))


def _ask(party, me, feature, trigger, note, cost):
    """True: the player (or the GM for them) says yes; False: no; None: no one asked (the computer chooses)."""
    asked = party.asked_live(me)
    if not asked:
        return None
    return bool(asked.luck(me, feature, trigger, note, cost))


def luck_miss(party, src, tgt, d20, total, ac):
    """fight_state's luckMiss: src's attack roll missed (d20, total vs ac). -> the new d20 (0: none). Heroic Inspiration
    rolls it again; Stroke of Luck makes it a 20."""
    sim = party.sim
    c = sim.by_id(src)
    if not c or not c.get("pc") or party.down(src) or party.incapacitated(src):
        return 0
    who = sim.S.name(tgt)
    line = "%s's attack roll misses %s (d20 %d, %d vs AC %d)"
    heroic = _state(party, "heroic")
    if heroic.get(src):
        yes = _ask(party, src, HEROIC, line % (c["name"], who, d20, total, ac), "Roll the d20 again; the new roll stands.",
                   "It spends Heroic Inspiration.")
        if yes is not False:
            heroic.pop(src)
            new = sim.rng.randint(1, 20)
            sim.say("dice", "%s uses Heroic Inspiration: the attack's d20 again, %d -> %d" % (c["name"], d20, new))
            total += new - d20
            if new == 1 or (total < ac and new < int((c.get("weapon") or {}).get("crit", 20) or 20)):
                d20 = new                                        # still a miss: Stroke of Luck may follow
                return 20 if _stroke(party, src, c, line % (c["name"], who, d20, total, ac), attack=True) else new
            return new
    return 20 if _stroke(party, src, c, line % (c["name"], who, d20, total, ac), attack=True) else 0


def _stroke(party, me, c, trigger, attack=False, can=True):
    if not has(c, "stroke_of_luck", STROKE) or not uses_left(party, me, "stroke_of_luck"):
        return False
    yes = _ask(party, me, STROKE, trigger, "The d20 becomes a 20%s." % (" (on an attack roll: a Critical Hit)" if attack else ""),
               "It spends Stroke of Luck (once per Short or Long Rest).")
    if yes is None:                                              # the computer: a missed Sneak Attack, a failed save
        yes = can and (not attack or _state(party, "sneak_now").get(me) == party.s.turnSerial)
    if not yes:
        return False
    spend_use(party, me, "stroke_of_luck")
    party.sim.say("dice", "%s uses Stroke of Luck: the d20 becomes a 20" % c["name"])
    return True


def luck_save(gm, t, total, dc, label, bonus):
    """gm_rules.indomitable: a failed save (total < dc; bonus: the save's own) -> the total after Heroic Inspiration (the
    d20 again) and Stroke of Luck (a 20)."""
    p = gm.p
    c = gm.sim.by_id(t)
    if total >= dc or not p or not c.get("pc") or gm.sim.down(t):
        return total
    trigger = "%s fails a %s save (%d vs DC %d)" % (c["name"], label, total, dc)
    heroic = _state(p, "heroic")
    if heroic.get(t) and (bonus + 20 >= dc or p.asked_live(t)):
        if _ask(p, t, HEROIC, trigger, "Roll the save again; the new roll stands.", "It spends Heroic Inspiration.") is not False:
            heroic.pop(t)
            d20 = gm.sim.rng.randint(1, 20)
            total = d20 + bonus
            gm.sim.say("dice", "%s uses Heroic Inspiration: the %s save again, d20 %d %+d = %d vs DC %d -> %s" % (
                c["name"], label, d20, bonus, total, dc, "success" if total >= dc else "failure"))
            if total >= dc:
                return total
            trigger = "%s fails the %s save again (%d vs DC %d)" % (c["name"], label, total, dc)
    if _stroke(p, t, c, trigger, can=bonus + 20 >= dc):
        total = 20 + bonus
    return total


def luck_check(party, me, total, dc, label, bonus):
    """A failed ability check in a fight (Hide, Study, Influence) -> the new total: Heroic Inspiration, then Tactical Mind
    (+1d10 for a Second Wind use, kept when it still fails), then Stroke of Luck."""
    if total >= dc or not party:
        return total
    sim = party.sim
    c = sim.by_id(me)
    trigger = "%s fails the %s check (%d vs DC %d)" % (c["name"], label, total, dc)
    heroic = _state(party, "heroic")
    if heroic.get(me) and (bonus + 20 >= dc or party.asked_live(me)):
        if _ask(party, me, HEROIC, trigger, "Roll the check again; the new roll stands.", "It spends Heroic Inspiration.") is not False:
            heroic.pop(me)
            d20 = sim.rng.randint(1, 20)
            total = d20 + bonus
            sim.say("dice", "%s uses Heroic Inspiration: the %s check again, d20 %d %+d = %d vs DC %d -> %s" % (
                c["name"], label, d20, bonus, total, dc, "success" if total >= dc else "failure"))
            if total >= dc:
                return total
            trigger = "%s fails the %s check again (%d vs DC %d)" % (c["name"], label, total, dc)
    winds = sim.__dict__.setdefault("second_winds", {})
    left = winds.setdefault(me, c.get("second_wind", 0) or 0)
    if has(c, "tactical_mind", TMIND) and left > 0 and (total + 10 >= dc or party.asked_live(me)):
        yes = _ask(party, me, TMIND, trigger, "Add 1d10 to the check; the Second Wind use is kept if it still fails.",
                   "It spends a Second Wind use (%d left), only if the check then succeeds." % left)
        if yes is not False:
            d10 = sim.rng.randint(1, 10)
            ok = total + d10 >= dc
            if ok:
                winds[me] = left - 1
            sim.say("dice", "%s uses Tactical Mind: %d + 1d10 %d = %d vs DC %d -> %s" % (
                c["name"], total, d10, total + d10, dc, "success (a Second Wind use spent, %d left)" % winds[me] if ok
                else "still a failure (the Second Wind use is kept)"))
            if ok:
                return total + d10
    if _stroke(party, me, c, trigger, can=bonus + 20 >= dc):
        total = 20 + bonus
    return total


# ---------------------------------------------------------------------- Tactical Shift
def tactical_shift(fight, me, c, t):
    """Second Wind as a Bonus Action (Play live): half the Speed more movement, which provokes no Opportunity Attacks."""
    if not c.get("tactical_shift") or not t:
        return 0
    ft = int(t.get("speed", 30) or 30) // 2
    if ft <= 0:
        return 0
    t["movement"] += ft
    t["shift_ft"] = int(t.get("shift_ft", 0) or 0) + ft
    fight.sim.say("turn", "%s: Tactical Shift, %d ft of movement that provokes no Opportunity Attacks (%d ft left)" % (
        c["name"], ft, t["movement"]))
    return ft


def shift_left(t):
    return int((t or {}).get("shift_ft", 0) or 0)


# ---------------------------------------------------------------------- Devious Strikes
def devious_offer(party, me, c, weapon, sneak_used):
    """Play live: the attack row's Devious Strikes choices, or None."""
    if not has(c, "devious_strikes", "Devious Strikes") or not c.get("sneak") or not (
            weapon.get("finesse") or weapon.get("reach", 5) > 10) or weapon.get("cantrip"):   # Finesse or ranged (party.ranged)
        return None
    n = int(str(c["sneak"]).partition("d")[0] or 0)
    out = []
    for key, (name, cost, save) in DEVIOUS.items():
        why = "Sneak Attack is used this turn." if sneak_used else "" if n > cost else \
            "%s costs %d Sneak Attack dice; %s has %d (one stays)." % (name, cost, c["name"], n)
        out.append({"key": key, "name": name, "dice": cost, "save": save, "ready": not why, "why": why})
    return {"options": out, "dc": int(c.get("cunning_strike") or 0), "two": bool(c.get("improved_cunning_strike"))}


def cunning_offer(party, me, c, weapon, sneak_used):
    """Play live: the attack row's Cunning Strike choices (Rogue 5), or None. One Sneak Attack die each, and one stays."""
    if not c.get("cunning_strike") or not c.get("sneak") or not (weapon.get("finesse") or weapon.get("reach", 5) > 10) \
            or weapon.get("cantrip"):                            # Finesse or ranged (party.ranged)
        return None
    n = int(str(c["sneak"]).partition("d")[0] or 0)
    why = "Sneak Attack is used this turn." if sneak_used else "" if n > 1 else \
        "Cunning Strike costs a Sneak Attack die; %s has %d (one stays)." % (c["name"], n)
    return {"options": [{"key": key, "name": name, "dice": 1, "save": save, "ready": not why, "why": why}
                        for key, (name, save) in CUNNING.items()],
            "dc": int(c["cunning_strike"]), "two": bool(c.get("improved_cunning_strike"))}


def cunning_why(party, me, tid, c, weapon, strikes, stealth, devious, sneak_used):
    """Why this attack can't carry these Cunning Strike options, or "". The dice and the count of options are checked
    together: Stealth Attack and a Devious Strike are options of the same Sneak Attack."""
    offer = cunning_offer(party, me, c, weapon, sneak_used)
    if not offer:
        return "Cunning Strike (Rogue 5) needs a Sneak Attack weapon: not this attack."
    if any(not o["ready"] for o in offer["options"]):
        return offer["options"][0]["why"]
    if len(strikes) + bool(stealth) + bool(devious) > (2 if offer["two"] else 1):
        return "One Cunning Strike option per Sneak Attack: two need Improved Cunning Strike (Rogue 11)."
    n = int(str(c["sneak"]).partition("d")[0] or 0)
    if len(strikes) + bool(stealth) + (DEVIOUS[devious][1] if devious else 0) >= n:
        return "%s has %d Sneak Attack dice, and one stays." % (c["name"], n)
    gm = getattr(party.sim, "gm_rules", None)
    if "trip" in strikes and (party.sim.size_sq(tid) > 2 or (gm and gm.has(tid, "Prone"))):
        return "Trip takes a Large or smaller creature that isn't Prone yet."
    return ""


def poison_strike(party, me, tid):
    """Cunning Strike, Poison: Constitution save or Poisoned for 1 minute, the save again at the end of each of its turns.
    The Poisoner's Kit is presumed at hand (GM ruling on presumed equipment)."""
    sim, gm = party.sim, getattr(party.sim, "gm_rules", None)
    c = sim.by_id(me)
    if party.down(tid) or not gm:
        return
    if gm.cond_immune(tid, "poisoned"):
        sim.say("dice", "%s can't be Poisoned (Cunning Strike: Poison)" % party.name(tid))
        return
    dc = int(c["cunning_strike"])
    if gm.condition_save(tid, "con", dc, "Cunning Strike (Poison)", adv=gm.antitoxin(tid, "Poisoned")):
        return
    gm.add(tid, "Poisoned", "(%s's Cunning Strike: 1 minute; a Constitution save again at the end of each of its turns)" % c["name"],
           by=me, lib=True, save="con", dc=dc, repeat="end", expires=int(party.s.round() or 1) + 10)


def withdraw(fight, me, c, t):
    """Cunning Strike, Withdraw: right after the attack, up to half the Speed that provokes no Opportunity Attacks."""
    ft = int(t.get("speed", 30) or 30) // 2
    t["movement"] += ft
    t["shift_ft"], t["shift_name"] = int(t.get("shift_ft", 0) or 0) + ft, "Withdraw"
    fight.sim.say("turn", "%s: Withdraw, %d ft of movement that provokes no Opportunity Attacks (%d ft left)" % (
        c["name"], ft, t["movement"]))


def choose_devious(party, me, tid, c, count):
    """The computer-played Rogue: Knock Out on a foe its Sneak Attack won't drop (7 dice or more)."""
    if not has(c, "devious_strikes", "Devious Strikes") or count < 7 or party.down(tid):
        return None
    gm = getattr(party.sim, "gm_rules", None)
    if gm and (gm.cond_immune(tid, "unconscious") or gm.incapacitated(tid)):
        return None
    dice, _, bonus = str((c.get("weapon") or {}).get("dmg", "1d4")).partition("+")
    n, _, sides = dice.partition("d")
    most = int(n or 1) * int(sides or 4) + int(bonus or 0) + count * 6
    return "knock_out" if party.hp_left(tid) > most else None


def devious_effect(party, me, tid, key):
    """After the hit's damage: the Devious Strike's save and effect."""
    sim, gm = party.sim, getattr(party.sim, "gm_rules", None)
    c = sim.by_id(me)
    name, _, save = DEVIOUS[key]
    if party.down(tid) or not gm:
        return
    dc = int(c.get("cunning_strike") or 8 + mod((c.get("abilities") or {}).get("dex")) + pb(c))
    cond = {"knock_out": "Unconscious", "obscure": "Blinded"}.get(key)
    if cond and gm.cond_immune(tid, cond.lower()):
        sim.say("dice", "%s can't be %s (Cunning Strike: %s)" % (party.name(tid), cond, name))
        return
    if gm.condition_save(tid, save, dc, "Cunning Strike (%s)" % name):
        return
    if key == "daze":
        _state(party, "dazed")[tid] = me
        sim.say("dice", "%s is Dazed (%s's Cunning Strike): on its next turn it moves, or takes an action, or a Bonus "
                "Action, only one of them" % (party.name(tid), c["name"]))
    elif key == "knock_out":
        gm.add(tid, "Unconscious", "(%s's Cunning Strike: Knock Out, 1 minute or until it takes damage; a Constitution save "
               "again at the end of each of its turns)" % c["name"], by=me, lib=True, save="con", dc=dc, repeat="end",
               expires=int(party.s.round() or 1) + 10, knockout=True)
        if gm.has(tid, "Unconscious"):
            gm.add(tid, "Prone", "(falls Unconscious)", by=me)
    elif key == "obscure":
        gm.add(tid, "Blinded", "(%s's Cunning Strike: Obscure, until the end of its next turn)" % c["name"], by=me, lib=True,
               until={"who": "target", "when": "end"}, skip=1 if party.s.active()[0] == tid else 0)


def knockout_hurt(gm, t):
    """gm_rules.hurt: damage ends Knock Out's Unconscious."""
    info = gm.cond.get(t, {}).get("Unconscious")
    if info and info.get("knockout"):
        gm.remove(t, "Unconscious", "the damage wakes it (Knock Out ends)")


def daze_turn(gm, me):
    """gm_rules.turn_start: a Dazed creature's turn now is limited (creature_turns.py reads daze_choices)."""
    p = gm.p
    if not p or _state(p, "dazed").pop(me, None) is None:
        return
    gm.sim.by_id(me)["_dazed"] = p.s.turnSerial
    gm.sim.say("turn", "%s is Dazed: this turn it moves, or takes an action, or a Bonus Action (one of them)" %
               gm.sim.by_id(me)["name"])


def dazed(sim, cid):
    return sim.by_id(cid).get("_dazed") == sim.S.turnSerial


def daze_choices(sim, cid, choices):
    """A Dazed creature's choices this turn: an action where it stands, else a move only; never a Bonus Action."""
    if not dazed(sim, cid):
        return choices
    here = [ch for ch in choices if not ch.get("bonus") and not ch.get("move") and not ch.get("move_only")]
    return here or [ch for ch in choices if ch.get("move_only")] or here


# ---------------------------------------------------------------------- Retaliation, Intimidating Presence
def retaliate(party, me, src):
    """gm_rules.hurt (after the damage settles): Retaliation's melee attack against src, the Reaction. True: made."""
    if party is None or src is None or me == src:
        return False
    sim = party.sim
    c = sim.by_id(me)
    if not c or not has(c, "retaliation", "Retaliation") or party.side(src) == party.side(me) or party.down(me) or party.down(src):
        return False
    if party.incapacitated(me) or party.s.getField(me, "reaction") or party.dist(me, src) > FT + 0.01 or party.blocked(me, src):
        return False
    w = c.get("weapon") or {}
    if not w.get("name") or w.get("reach", 5) > 10 or w.get("cantrip"):
        return False
    asked = party.asked_live(me)
    if asked and not asked.retaliation(me, src, w):
        return False
    party.s.setField(me, "reaction", 1)
    sim.say("dice", "%s uses Retaliation (Reaction): one melee attack against %s" % (c["name"], party.name(src)))
    party.attack(me, src, party.rage_weapon(me, c, w), note="Retaliation", retarget_grapple=False)
    sim.settle()
    return True


def intimidate_dc(c):
    return 8 + mod(score(c, "str")) + pb(c)


def intimidate_targets(party, me):
    return [f for f in party.foes(me) if not party.down(f) and party.dist(me, f) <= 30 + 0.01 and not party.blocked(me, f)]


def intimidate_check(party, me, bonus_free=True):
    c = party.sim.by_id(me)
    if not has(c, "intimidating_presence", "Intimidating Presence"):
        raise HighError("Intimidating Presence is a Berserker's (Barbarian 14).")
    if not uses_left(party, me, "intimidating_presence") and party.rages.get(me, 0) <= 0:
        raise HighError("%s used Intimidating Presence and has no Rage use to restore it." % c["name"])
    if not bonus_free:
        raise HighError("%s's Bonus Action is used this turn." % c["name"])
    if not intimidate_targets(party, me):
        raise HighError("No foe within 30 ft of %s." % c["name"])


def intimidate(party, me, targets=None):
    """The Bonus Action (the caller pays it); a Rage use restores a spent use first. -> the creatures chosen."""
    sim, gm = party.sim, party.sim.gm_rules
    c = sim.by_id(me)
    pool = intimidate_targets(party, me)
    chosen = [t for t in (targets or pool) if t in pool] or pool
    if not uses_left(party, me, "intimidating_presence"):
        party.rages[me] -= 1
        _state(party, "martial_left").setdefault(me, {})["intimidating_presence"] = 1
        sim.say("dice", "%s spends a use of Rage to restore Intimidating Presence (%d Rage left)" % (c["name"], party.rages[me]))
    spend_use(party, me, "intimidating_presence")
    dc = intimidate_dc(c)
    sim.say("dice", "%s uses Intimidating Presence (Bonus Action): DC %d Wisdom save for %s" % (
        c["name"], dc, ", ".join(party.name(f) for f in chosen)))
    until = int(party.s.round() or 1) + 10
    for f in chosen:
        if gm.cond_immune(f, "frightened"):
            sim.say("dice", "%s can't be Frightened" % party.name(f))
            continue
        if not gm.condition_save(f, "wis", dc, "Intimidating Presence"):
            gm.add(f, "Frightened", "(%s's Intimidating Presence: 1 minute, a Wisdom save again at the end of each of its "
                   "turns)" % c["name"], by=me, lib=True, save="wis", dc=dc, repeat="end", expires=until)
    return chosen


def intimidate_tactic(party, me, c):
    """The computer-played Berserker: with its Rage on and the Bonus Action free, on three foes or more within 30 ft."""
    if me not in party.raging or not party.bonus_free(me):
        return False
    try:
        intimidate_check(party, me)
    except HighError:
        return False
    gm = party.sim.gm_rules
    fresh = [f for f in intimidate_targets(party, me) if not gm.has(f, "Frightened")]
    if len(fresh) < 3 or (not uses_left(party, me, "intimidating_presence") and party.rages.get(me, 0) < 2):
        return False
    party.use_bonus(me)
    intimidate(party, me, fresh)
    return True


# ---------------------------------------------------------------------- Restoring Touch, Smite of Protection, Holy Nimbus
def restorable(gm, t):
    return [n for n in RESTORE if gm.has(t, n)]


def restore_touch(party, me, tid, names):
    """Lay On Hands with Restoring Touch (the caller pays the Bonus Action): 5 points of the pool for each condition."""
    sim, gm = party.sim, party.sim.gm_rules
    c = sim.by_id(me)
    names = [n for n in names if gm.has(tid, n)]
    party.loh[me] -= 5 * len(names)
    sim.say("dice", "%s uses Lay On Hands on %s (Bonus Action), Restoring Touch: %d points of the pool end %s (%d left)" % (
        c["name"], "herself" if tid == me else party.name(tid), 5 * len(names), " and ".join(names), party.loh[me]))
    for n in names:
        gm.remove(tid, n, "%s's Restoring Touch" % c["name"])
    return names


def restoring_tactic(party, me, c):
    """The computer-played Paladin's Lay On Hands: herself or an ally in touch who is Paralyzed or Stunned."""
    gm = getattr(party.sim, "gm_rules", None)
    if not gm or not has(c, "restoring_touch", "Restoring Touch") or party.loh.get(me, 0) < 5 or not party.bonus_free(me):
        return False
    near = [a for a in [me] + party.allies(me) if not party.down(a) and (a == me or party.dist(me, a) <= FT + 0.01)
            and (gm.has(a, "Paralyzed") or gm.has(a, "Stunned"))]
    if not near:
        return False
    party.use_bonus(me)
    restore_touch(party, me, near[0], restorable(gm, near[0])[:party.loh[me] // 5])
    return True


def smite_protection(party, me):
    """A Divine Smite was cast (the computer's rider, or Ask the GM in Play live): Half Cover in her aura."""
    c = party.sim.by_id(me)
    if not has(c, "smite_protection", "Smite of Protection"):
        return
    _state(party, "smite_cover")[me] = True
    party.sim.say("dice", "%s: Smite of Protection, she and her allies in her %d-ft aura have Half Cover until the start of "
                  "her next turn" % (c["name"], aura_ft(c)))


def smite_cover(gm, src, t):
    """The cover Smite of Protection adds for t against src: Half Cover, 2, less the cover it has already."""
    p = gm.p
    on = _state(p, "smite_cover") if p else {}
    for q in on:
        if p.side(q) == p.side(t) and not gm.sim.down(q) and not gm.incapacitated(q) and (
                q == t or p.dist(q, t) <= aura_ft(gm.sim.by_id(q))):
            env = getattr(gm.sim, "env", None)
            have = env.cover(src, t) if env and src is not None and src != t else 0
            return max(0, 2 - have)
    return 0


def save_aid(gm, src, t, ability, parts):
    """roll_save / save_and_damage (a creature's effect): Smite of Protection's Half Cover on a Dexterity save; Holy
    Nimbus's Advantage on a save a Fiend or an Undead forces."""
    if not gm.p:
        return
    if ability == "dex":
        parts["bonus"] += smite_cover(gm, src, t)
    if src is not None and t in _state(gm.p, "nimbus"):
        kind = str(gm.sim.by_id(src).get("type") or "").lower()
        if "fiend" in kind or "undead" in kind:
            parts["adv"], parts["adv_why"] = True, "Holy Nimbus"


def nimbus_check(party, me, bonus_free=True):
    c = party.sim.by_id(me)
    if not has(c, "holy_nimbus", "Holy Nimbus"):
        raise HighError("Holy Nimbus is a Devotion Paladin's (level 20).")
    if me in _state(party, "nimbus"):
        raise HighError("%s's Holy Nimbus is already on." % c["name"])
    if not uses_left(party, me, "holy_nimbus") and not party.slot_free(me, 5):
        raise HighError("%s used Holy Nimbus and has no level 5 slot free to restore it." % c["name"])
    if not bonus_free:
        raise HighError("%s's Bonus Action is used this turn." % c["name"])


def nimbus_damage(c):
    return max(1, int(c.get("spell_mod") or mod(score(c, "cha")))) + pb(c)


def nimbus(party, me):
    """The Bonus Action (the caller pays it); a level 5 slot restores a spent use first."""
    sim = party.sim
    c = sim.by_id(me)
    if not uses_left(party, me, "holy_nimbus"):
        lv = party.spend_slot(me, 5)
        _state(party, "martial_left").setdefault(me, {})["holy_nimbus"] = 1
        sim.say("dice", "%s spends a level %d slot to restore Holy Nimbus" % (c["name"], lv))
    spend_use(party, me, "holy_nimbus")
    _state(party, "nimbus")[me] = True
    sim.say("dice", "%s uses Holy Nimbus (Bonus Action): for 10 minutes her %d-ft aura is sunlight, an enemy starting its "
            "turn in it takes %d Radiant, and she has Advantage on saves a Fiend or an Undead forces" % (
                c["name"], aura_ft(c), nimbus_damage(c)))
    nimbus_light(party)


def nimbus_light(party):
    """The aura's sunlight (Sunlight Sensitivity and the like), where each Paladin stands now."""
    env = getattr(party.sim, "env", None)
    if env is None:
        return
    env.zones[:] = [z for z in env.zones if not z.get("nimbus")]
    u = party.sim.sc.get("units", 5)
    for q in _state(party, "nimbus"):
        if party.down(q) or party.incapacitated(q):
            continue
        x, y = party.pos(q)
        r = aura_ft(party.sim.by_id(q)) / u
        env.zones.append({"id": "nimbus-%s" % q, "kind": "sunlit", "nimbus": q, "circle": [x, y, r],
                          "rect": [int(x - r), int(y - r), int(x + r + 1), int(y + r + 1)]})


def nimbus_turn(gm, me):
    """gm_rules.turn_start: an enemy that starts its turn in a Holy Nimbus takes the Radiant damage. True: it dropped."""
    p = gm.p
    on = _state(p, "nimbus") if p else {}
    if not on:
        return False
    nimbus_light(p)
    for q in list(on):
        pal = gm.sim.by_id(q)
        if p.side(q) == p.side(me) or gm.sim.down(q) or gm.incapacitated(q) or gm.sim.down(me) or p.dist(q, me) > aura_ft(pal):
            continue
        n = nimbus_damage(pal)
        gm.sim.say("dice", "%s starts its turn in %s's Holy Nimbus: %d Radiant damage" % (gm.sim.by_id(me)["name"], pal["name"], n))
        p.s.pcDamage(q, me, "", n, False, "radiant")
        gm.sim.settle(0.2)
    return gm.sim.down(me)


def nimbus_tactic(party, me, c):
    """The computer-played Paladin: Holy Nimbus (its use, not a slot) as soon as a foe is within 60 ft."""
    if not has(c, "holy_nimbus", "Holy Nimbus") or not uses_left(party, me, "holy_nimbus") or me in _state(party, "nimbus") \
            or not party.bonus_free(me):
        return False
    if not any(party.dist(me, f) <= 60 for f in party.foes(me) if not party.down(f)):
        return False
    party.use_bonus(me)
    nimbus(party, me)
    return True


# ---------------------------------------------------------------------- Play live: the Bonus Actions, Restoring Touch
def of(fight):
    m = getattr(fight, "martial", None)
    if m is None:
        m = fight.martial = LiveMartial(fight)
    return m


class LiveMartial:
    def __init__(self, fight):
        self.fight = fight

    @property
    def sim(self):
        return self.fight.sim

    def actions(self, me):
        c, party, out = self.sim.by_id(me), self.sim.party, []
        free = party.bonus_free(me)
        if has(c, "intimidating_presence", "Intimidating Presence"):
            left = uses_left(party, me, "intimidating_presence")
            e = {"op": "intimidating_presence", "time": "bonus", "bonus": False, "uses": left,
                 "label": "Intimidating Presence (DC %d%s)" % (intimidate_dc(c), "" if left else ", a Rage use restores it")}
            self._ready(e, lambda: intimidate_check(party, me, free))
            out.append(e)
        if has(c, "holy_nimbus", "Holy Nimbus") and me not in _state(party, "nimbus"):
            left = uses_left(party, me, "holy_nimbus")
            e = {"op": "holy_nimbus", "time": "bonus", "bonus": False, "uses": left,
                 "label": "Holy Nimbus" + ("" if left else " (a level 5 slot restores it)")}
            self._ready(e, lambda: nimbus_check(party, me, free))
            out.append(e)
        gm = self.sim.gm_rules
        if has(c, "restoring_touch", "Restoring Touch") and gm:
            touch = [a for a in [me] + party.allies(me) if not party.down(a) and (a == me or party.dist(me, a) <= 5.01)]
            for n in RESTORE:
                who = [a for a in touch if gm.has(a, n)]
                if who:
                    e = {"op": "lay_on_hands", "mode": n, "time": "bonus", "bonus": False, "targets": who, "refused": {},
                         "pool": party.loh.get(me, 0), "label": "Restoring Touch: end %s (Lay On Hands, 5 points)" % n}
                    self._ready(e, lambda: self.restore_check(me, None, [n]))
                    out.append(e)
        return out

    def _ready(self, e, check):
        try:
            check()
            e["ready"] = True
        except HighError as err:
            e["ready"], e["why"] = False, str(err)

    def restore_check(self, me, tid, names):
        c, party, gm = self.sim.by_id(me), self.sim.party, self.sim.gm_rules
        if not has(c, "restoring_touch", "Restoring Touch"):
            raise HighError("Restoring Touch is a Paladin's (level 14).")
        if not party.bonus_free(me):
            raise HighError("%s's Bonus Action is used this turn." % c["name"])
        if party.loh.get(me, 0) < 5 * len(names):
            raise HighError("Restoring Touch takes 5 points of the Lay On Hands pool for each condition; %d left." %
                            party.loh.get(me, 0))
        if tid is None:
            return
        a = next((o for o in self.sim.sc["combatants"] if o["id"] == tid), None)
        if not a or (tid != me and party.side(tid) != party.side(me)):
            raise HighError("Lay On Hands: choose yourself or an ally.")
        if tid != me and party.dist(me, tid) > 5.01:
            raise HighError("%s is out of touch (5 ft)." % a["name"])
        if not any(gm.has(tid, n) for n in names):
            raise HighError("%s is not %s." % (a["name"], " or ".join(names)))

    def do(self, me, cmd):
        party, op = self.sim.party, cmd.get("op")
        if op == "lay_on_hands":
            mode = cmd.get("mode")
            if mode not in RESTORE:
                raise HighError("Restoring Touch ends Blinded, Charmed, Deafened, Frightened, Paralyzed or Stunned.")
            tid = cmd.get("target")
            self.restore_check(me, tid, [mode])
            party.use_bonus(me)
            restore_touch(party, me, tid, [mode])
            return "bonus", [tid]
        if op == "intimidating_presence":
            intimidate_check(party, me, party.bonus_free(me))
            party.use_bonus(me)
            chosen = intimidate(party, me, [x for x in (cmd.get("targets") or []) if isinstance(x, str)] or None)
            self.sim.settle()
            return "bonus", chosen
        if op == "holy_nimbus":
            nimbus_check(party, me, party.bonus_free(me))
            party.use_bonus(me)
            nimbus(party, me)
            return "bonus", []
        raise HighError("Not an action here.")
