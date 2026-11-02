"""MONK-01 (GM 2026-10-28, "Monk as SRD"): the Monk's fight play, for a Monk played at the table (Play live) and
for the simulator's computer-played party, checked against SRD 5.2.1 (Monk; Warrior of the Open Hand). The pool and the
marks live on the party (sim/party.py), shared by both.

- Martial Arts (1): while unarmed or wielding only Monk weapons (Simple Melee weapons, Martial Melee weapons with the
  Light property) and wearing no armor and no Shield: Dexterity for the attack and damage rolls of Unarmed Strikes and
  Monk weapons, the Martial Arts die in place of their normal damage (d6, d8 at 5, d10 at 11, d12 at 17), and an Unarmed
  Strike as a Bonus Action. The character builder (sim/character_build.py) works out the attacks; a build marks its Monk
  weapons ("monk") and keeps its Unarmed Strike apart ("unarmed").
- Monk's Focus (2): Focus Points equal to the Monk level, all back on a Short or Long Rest (sim/rests.py). Save DC 8 +
  Wisdom modifier + Proficiency Bonus.
  Flurry of Blows: 1 Focus Point, two Unarmed Strikes as a Bonus Action.
  Patient Defense: Disengage as a Bonus Action; or 1 Focus Point, both Disengage and Dodge.
  Step of the Wind: Dash as a Bonus Action; or 1 Focus Point, both Disengage and Dash (the jump distance doubled).
- Unarmored Movement (2): Speed +10 ft and more (the builder adds it to the sheet's Speed).
- Deflect Attacks (3): Reaction when an attack roll hits and its damage includes Bludgeoning, Piercing or Slashing: the
  attack's total damage is reduced by 1d10 + Dexterity modifier + Monk level. Reduced to 0: 1 Focus Point redirects it
  at a creature within 5 ft (a melee attack) or within 60 ft (a ranged one) the Monk can see: Dexterity save or two rolls
  of the Martial Arts die + the Dexterity modifier, of the attack's damage type. Deflect Energy (13): any damage type.
- Open Hand Technique (Warrior of the Open Hand 3): a hit of an attack from Flurry of Blows adds one: Addle (no
  Opportunity Attacks until the start of its next turn), Push (Strength save or pushed up to 15 ft away) or Topple
  (Dexterity save or Prone). Saves against the Monk's Focus save DC.
- Slow Fall (4): Reaction when it falls: the falling damage is reduced by five times the Monk level.
- Extra Attack (5): the builder's two attacks per Attack action.
- Stunning Strike (5): once per turn, a hit with a Monk weapon or an Unarmed Strike; 1 Focus Point: Constitution save, or
  Stunned until the start of the Monk's next turn; on a success its Speed is halved until then and the next attack roll
  against it before then has Advantage.
- Evasion (7): sim/gm_rules.py (Rogue and Monk 7) already plays it.
Played at the table, Deflect Attacks (and its redirect), Slow Fall and Deflect Energy are asked live, the way Shield is
(sim/live_reactions.py); the computer-played Monk always uses them when its Reaction is free.
GM 2026-10-28 ("heroes 20"): the Monk 14-20.
- Disciplined Survivor (14): proficiency in every saving throw (the builder); a failed save rolled again for 1 Focus
  Point, the new roll kept (GmRules.indomitable, the hook every failed save of a character passes). Played at the table
  it is asked (sim/live_reactions.py); the computer-played Monk rerolls whenever a roll could still succeed.
- Perfect Focus (15): rolling Initiative with 3 Focus Points or fewer (Uncanny Metabolism is the GM's), back up to 4
  (sim/rests.py, when the day's points are carried into a fight).
- Superior Defense (18): at the start of its turn, 3 Focus Points: Resistance to all damage but Force for 1 minute (10
  rounds) or until it is Incapacitated (fight_state reads sim_resist_all). A button at the table (no action, before
  anything else that turn); the computer-played Monk uses it when below half its Hit Points with a foe in sight.
- Body and Mind (20): Dexterity and Wisdom +4, up to 25 (the builder).
Not played (the GM rules them): Uncanny Metabolism, Wholeness of Body, Empowered Strikes' Force damage, Acrobatic
Movement, Heightened Focus, Self-Restoration, Fleet Step, Quivering Palm; Martial Arts with armor or a Shield on (the
builder's attacks are kept as they are).
"""
import party as party_mod

OPS = ("martial_arts", "flurry", "patient_defense", "step_of_the_wind", "superior_defense")
TECHNIQUES = {"addle": "Addle", "push": "Push", "topple": "Topple"}
BPS = {"bludgeoning", "piercing", "slashing"}
NAMES = {"martial_arts": "Martial Arts: Unarmed Strike", "flurry": "Flurry of Blows", "patient_defense": "Patient Defense",
         "step_of_the_wind": "Step of the Wind", "superior_defense": "Superior Defense"}
DEFENSE_ROUNDS = 10


class MonkError(ValueError):
    pass


# ---------------------------------------------------------------------- the sheet
def is_monk(c):
    return bool(c.get("monk_level")) or c.get("class") == "monk"


def level(c):
    return int(c.get("monk_level") or (c.get("level", 1) if c.get("class") == "monk" else 0) or 0)


def ability_mod(c, ab):
    return (int((c.get("abilities") or {}).get(ab, 10) or 10) - 10) // 2


def die(c):
    n = level(c)
    return int(c.get("martial_arts") or (6 if n < 5 else 8 if n < 11 else 10 if n < 17 else 12))


def save_dc(c):
    return int(c.get("focus_dc") or 8 + ability_mod(c, "wis") + party_mod.proficiency_bonus(int(c.get("level", 1) or 1)))


def unarmed(c):
    """The sheet's Unarmed Strike (the builder's, Martial Arts already in it)."""
    for key in ("unarmed", "weapon", "ranged"):
        w = c.get(key)
        if isinstance(w, dict) and w.get("name") == "Unarmed Strike":
            return w
    return None


def monk_weapon(w):
    return bool(w and (w.get("monk") or w.get("name") == "Unarmed Strike"))


def _state(party, name):
    d = getattr(party, name, None)
    if d is None:
        d = {}
        setattr(party, name, d)
    return d


def points(party, me):
    """Focus Points left (the sheet's number when the fight starts; sim/rests.py carries them between fights)."""
    pool = _state(party, "focus_left")
    if me not in pool:
        pool[me] = int(party.sim.by_id(me).get("focus_points", 0) or 0)
    return pool[me]


def spend(party, me, n=1):
    points(party, me)
    party.focus_left[me] -= n
    return party.focus_left[me]


def turn_start(party, me):
    """The start of this Monk's turn: what lasted until now ends (Stunning Strike's marks; its own Dodge)."""
    s = party.s
    for tid in _state(party, "struck").pop(me, set()):
        s.setField(tid, "sim_struck", 0)
    c = party.sim.by_id(me)
    if is_monk(c) and not c.get("live"):
        c.pop("dodging", None)                                   # Patient Defense's Dodge (live_play clears a played one)
    until = _state(party, "defense_until").get(me)
    if until is not None:                                        # Superior Defense: 1 minute, or Incapacitated
        gm = getattr(party.sim, "gm_rules", None)
        if int(party.s.round() or 0) > until or party.down(me) or (gm and gm.incapacitated(me)):
            end_defense(party, me, "1 minute has passed" if int(party.s.round() or 0) > until else "Incapacitated")


# ---------------------------------------------------------------------- GM 2026-10-28: the Monk 14-18
def survivor(gm, t, total, dc, label, bonus):
    """Disciplined Survivor (Monk 14): a failed save (total < dc) rolled again for 1 Focus Point, the new roll kept.
    -> the total."""
    sim = gm.sim
    c, party = sim.by_id(t), sim.party
    if total >= dc or not c.get("disciplined_survivor") or not party or points(party, t) < 1:
        return total
    asked = party.asked_live(t)
    if asked:
        if not asked.survivor(t, total, dc, label, points(party, t)):
            return total
    elif bonus + 20 < dc:
        return total                                             # no roll could make it
    left = spend(party, t)
    d20 = sim.rng.randint(1, 20)
    new = d20 + bonus
    sim.say("dice", "%s uses Disciplined Survivor (1 Focus Point, %d left): the %s save again, d20 %d %+d = %d vs DC %d "
            "-> %s" % (c["name"], left, label, d20, bonus, new, dc, "success" if new >= dc else "failure"))
    return new


def perfect_focus(party, me):
    """Perfect Focus (Monk 15): rolling Initiative with 3 Focus Points or fewer, back up to 4."""
    c = party.sim.by_id(me)
    if not c.get("perfect_focus") or points(party, me) > 3:
        return
    most = min(4, int(c.get("focus_points", 0) or 0))
    if points(party, me) < most:
        party.sim.say("dice", "%s: Perfect Focus, Focus Points %d -> %d as Initiative is rolled" % (
            c["name"], points(party, me), most))
        party.focus_left[me] = most


def defense_why(party, me, fresh=True):
    """None when Superior Defense can start now; else why not. fresh: the turn has only just started."""
    c = party.sim.by_id(me)
    if not c.get("superior_defense"):
        return "Superior Defense is a Monk feature of level 18."
    if me in _state(party, "defense_until"):
        n = defense_rounds(party, me)
        return "Superior Defense is already on (%d round%s left)." % (n, "" if n == 1 else "s")
    if not fresh:
        return "Superior Defense starts at the start of the turn, before anything else."
    if points(party, me) < 3:
        return "Superior Defense needs 3 Focus Points (%d left)." % points(party, me)
    return None


def defense_rounds(party, me):
    until = _state(party, "defense_until").get(me)
    return max(0, until - int(party.s.round() or 0) + 1) if until is not None else 0


def superior_defense(party, me):
    """Superior Defense (checked by the caller): 3 Focus Points, Resistance to all damage but Force for 1 minute."""
    c = party.sim.by_id(me)
    left = spend(party, me, 3)
    _state(party, "defense_until")[me] = int(party.s.round() or 0) + DEFENSE_ROUNDS - 1
    party.s.setField(me, "sim_resist_all", 1)
    party.sim.say("dice", "%s uses Superior Defense (3 Focus Points, %d left): Resistance to all damage but Force for 1 "
                  "minute or until Incapacitated" % (c["name"], left))


def end_defense(party, me, why):
    _state(party, "defense_until").pop(me, None)
    party.s.setField(me, "sim_resist_all", 0)
    party.sim.say("dice", "%s's Superior Defense ends (%s)" % (party.name(me), why))


# ---------------------------------------------------------------------- after a hit: Stunning Strike, Open Hand
def save(party, tid, ability, dc, label):
    """A saving throw against the Monk's DC; Paralyzed, Petrified, Stunned and Unconscious fail Strength and Dexterity
    saves on their own (SRD 5.2.1)."""
    gm = party.sim.gm_rules
    if gm.auto_fail(tid, ability):
        party.sim.say("dice", "%s fails the %s save against %s automatically (%s)" % (
            party.name(tid), {"str": "Strength", "dex": "Dexterity"}[ability], label,
            next(n for n in ("Paralyzed", "Petrified", "Stunned", "Unconscious") if gm.has(tid, n))))
        return False
    return gm.condition_save(tid, ability, dc, label)


def stun_why(party, me, w, tid=None):
    """None when Stunning Strike can go with a hit of this attack now; else why not."""
    c = party.sim.by_id(me)
    if not c.get("stunning_strike"):
        return "Stunning Strike is a Monk feature of level 5."
    if not monk_weapon(w):
        return "Stunning Strike needs a Monk weapon or an Unarmed Strike."
    if _state(party, "stun_turn").get(me) == party.s.turnSerial:
        return "Stunning Strike is used this turn (once per turn)."
    if points(party, me) < 1:
        return "No Focus Point left."
    return None


def stunning_strike(party, me, tid, w, res, want=True):
    """A hit (res) of w at tid: Stunning Strike when wanted and allowed. True when it was used."""
    sim, gm = party.sim, getattr(party.sim, "gm_rules", None)
    if res not in ("hit", "crit") or not want or not gm or party.down(tid) or stun_why(party, me, w, tid):
        return False
    c = sim.by_id(me)
    _state(party, "stun_turn")[me] = party.s.turnSerial
    left = spend(party, me)
    dc = save_dc(c)
    sim.say("dice", "%s uses Stunning Strike (1 Focus Point, %d left): %s makes a DC %d Constitution save" % (
        c["name"], left, party.name(tid), dc))
    if not gm.condition_save(tid, "con", dc, "Stunning Strike"):
        gm.add(tid, "Stunned", "(%s's Stunning Strike, until the start of %s's next turn)" % (c["name"], c["name"]),
               by=me, lib=True, until={"who": "caster", "when": "start"}, save="con", dc=dc)
        return True
    speed = int(str(sim.by_id(tid).get("speed", "30")).split()[0] or 30)
    if not gm.has(tid, "Slowed"):
        gm.add(tid, "Slowed", "(%s's Stunning Strike: Speed halved until the start of %s's next turn)" % (c["name"], c["name"]),
               by=me, ft=speed - speed // 2, lib=True, until={"who": "caster", "when": "start"})
    party.s.setField(tid, "sim_struck", 1)                        # fight_state: the next attack roll has Advantage
    _state(party, "struck").setdefault(me, set()).add(tid)
    sim.say("dice", "%s's Speed is halved and the next attack roll against it has Advantage, until the start of %s's next "
            "turn" % (party.name(tid), c["name"]))
    return True


def technique(party, me, tid, how):
    """Open Hand Technique on a Flurry of Blows hit: Addle, Push or Topple (how)."""
    sim, gm, c = party.sim, getattr(party.sim, "gm_rules", None), party.sim.by_id(me)
    if how not in TECHNIQUES or not c.get("open_hand") or party.down(tid) or not gm:
        return
    dc, name = save_dc(c), party.name(tid)
    if how == "addle":
        party.s.setField(tid, "sim_no_oa", 1)                    # cleared at the start of its turn (fight_state)
        sim.say("dice", "Open Hand Technique (Addle): %s can't make Opportunity Attacks until the start of its next turn" % name)
    elif how == "push":
        if not save(party, tid, "str", dc, "Open Hand Technique (Push)"):
            (mx, my), (tx, ty) = party.pos(me), party.pos(tid)
            d = ((tx > mx) - (tx < mx), (ty > my) - (ty < my))
            sim.say("dice", "Open Hand Technique (Push): %s is pushed up to 15 ft away from %s" % (name, c["name"]))
            party.push(tid, d, 3)
    elif how == "topple" and not gm.has(tid, "Prone"):
        if not save(party, tid, "dex", dc, "Open Hand Technique (Topple)"):
            gm.add(tid, "Prone", "(%s's Open Hand Technique: Topple)" % c["name"], by=me)


def strike(party, me, tid, how=None, label="", stun=False):
    """One Unarmed Strike (Martial Arts' Bonus Action or one of Flurry of Blows'). Returns its result (None: refused)."""
    c, w = party.sim.by_id(me), unarmed(party.sim.by_id(me))
    if label:
        party.sim.say("turn", "%s: %s" % (c["name"], label))
    res = party.attack(me, tid, w, retarget_grapple=False)
    party.sim.settle()
    if res in ("hit", "crit"):
        stunning_strike(party, me, tid, w, res, want=stun)
        if how:
            technique(party, me, tid, how)
            party.sim.settle()
    return res


def flurry(party, me, tid, how=None, stun=False, other=None):
    """Flurry of Blows (paid by the caller): two Unarmed Strikes; the second at the same creature while it is up, else at
    `other` or another foe within 5 ft. Returns [(target, result)]."""
    out = []
    for k in range(2):
        if party.down(me):
            break
        if k and (party.down(tid) or party.dist(me, tid) > 5.01 or party.blocked(me, tid)):
            near = [f for f in ([other] if other is not None else []) + party.foes(me)
                    if f is not None and not party.down(f) and party.dist(me, f) <= 5.01 and not party.blocked(me, f)]
            if not near:
                break
            tid = near[0]
        res = strike(party, me, tid, how, "Flurry of Blows, strike %d of 2" % (k + 1), stun)
        if res is None:
            break
        out.append((tid, res))
    return out


# ---------------------------------------------------------------------- Reactions: Deflect Attacks, Slow Fall
def deflect_hit(party, tgt, src, total, kinds, ranged):
    """fight_state's deflectHit (an attack roll hit tgt for `total` damage of `kinds`, the Reaction free): the amount
    Deflect Attacks takes off (0: not used). A redirect (1 Focus Point) is dealt once the attack has settled."""
    sim = party.sim
    c = sim.by_id(tgt)
    if not c or not c.get("deflect_attacks") or total <= 0 or party.incapacitated(tgt) or party.down(tgt):
        return 0
    kinds = {k.strip() for k in str(kinds or "").split(",") if k.strip()}
    if not (kinds & BPS) and not c.get("deflect_energy"):
        return 0
    feature = "Deflect Energy" if c.get("deflect_energy") and not (kinds & BPS) else "Deflect Attacks"
    dex, n = ability_mod(c, "dex"), level(c)
    asked = party.asked_live(tgt)
    if asked and not asked.deflect(tgt, src, total, dex + n, feature):
        return 0
    r = sim.rng.randint(1, 10)
    cut = r + dex + n
    sim.say("dice", "%s uses %s (Reaction): 1d10 %d %+d Dex %+d Monk level = %d off the attack's %d damage" % (
        c["name"], feature, r, dex, n, cut, total))
    if cut >= total:
        _redirect(party, tgt, src, kinds, ranged, asked)
    return cut


def redirect_targets(party, me, src, ranged):
    """Creatures the force can go at: within 5 ft (a melee attack) or 60 ft (a ranged one), seen, no Total Cover; the
    attacker first, then the nearest foes. A wall between them is Total Cover."""
    sim = party.sim
    reach = 60 if ranged else 5
    out = []
    for f in ([src] if src is not None else []) + sorted(party.foes(me), key=lambda f: party.dist(me, f)):
        if f in out or f == me or party.down(f) or party.dist(me, f) > reach + 0.01 or not sim.sees(me, f):
            continue
        if party.blocked(me, f):
            continue
        out.append(f)
    return out


def _redirect(party, me, src, kinds, ranged, asked):
    sim, c = party.sim, party.sim.by_id(me)
    if points(party, me) < 1:
        return
    targets = redirect_targets(party, me, src, ranged)
    targets = [t for t in targets if party.side(t) != party.side(me)] or targets
    if not targets:
        return
    tid = targets[0]
    kind = sorted(kinds)[0] if len(kinds) == 1 else next((k for k in ("bludgeoning", "piercing", "slashing") if k in kinds),
                                                          sorted(kinds)[0] if kinds else "bludgeoning")
    if asked and not asked.redirect(me, tid, kind, die(c), ability_mod(c, "dex")):
        return
    left = spend(party, me)
    dc, d = save_dc(c), die(c)

    def land():
        if party.down(tid):
            return
        gm = sim.gm_rules
        sim.say("dice", "%s spends 1 Focus Point (%d left) to redirect the attack's force at %s: DC %d Dexterity save" % (
            c["name"], left, party.name(tid), dc))
        saved = save(party, tid, "dex", dc, "Deflect Attacks") if gm else False
        if saved:
            sim.say("dice", "%s avoids the redirected force" % party.name(tid))
            return
        sim.S.pcDamage(me, tid, "2d%d" % d, ability_mod(c, "dex"), False, kind)
    sim.later.append(land)


def slow_fall(sim, i, dmg, why="the fall"):
    """Slow Fall (Monk 4): a falling creature's Reaction takes five times its Monk level off the falling damage. Returns
    the damage left (dmg when not used)."""
    c, party = sim.by_id(i), getattr(sim, "party", None)
    if not c or not c.get("slow_fall") or dmg <= 0 or not party or party.incapacitated(i) or sim.down(i) \
            or int(sim.S.getField(i, "reaction") or 0):
        return dmg
    cut = 5 * level(c)
    asked = party.asked_live(i)
    if asked and not asked.slow_fall(i, dmg, cut, why):
        return dmg
    sim.S.setField(i, "reaction", 1)
    left = max(0, dmg - cut)
    sim.say("dice", "%s uses Slow Fall (Reaction): %d less falling damage (%d -> %d)" % (c["name"], cut, dmg, left))
    return left


# ---------------------------------------------------------------------- the computer-played Monk
def turn(party, me, c):
    """Party.turn_monk: close in (Step of the Wind's free Dash when the foe is farther than its Speed), the Attack action
    with Stunning Strike on the first hit, then the Bonus Action: Patient Defense (Disengage and Dodge) when hurt and
    held in melee, else Flurry of Blows (Topple, or Addle on a Prone foe), else the Martial Arts Unarmed Strike."""
    sim = party.sim
    tid = party.front_target(me, c)
    if tid is None:
        party.say(c["name"] + " sees no foe and holds position"); return
    if party.hp_left(me) < c["hp"] / 2 and not defense_why(party, me):   # Superior Defense (Monk 18)
        superior_defense(party, me)
    speed = c["_speed_now"] if "_speed_now" in c else int(str(c.get("speed", "30")).split()[0])
    if party.bonus_free(me) and speed > 0 and party.dist(me, tid) > speed + 5.01 and level(c) >= 1:
        party.use_bonus(me)                                      # Step of the Wind without a Focus Point: Dash
        c["_speed_now"] = speed * 2
        sim.say("turn", "%s uses Step of the Wind (Bonus Action): Dash, %d ft of movement" % (c["name"], speed * 2))
    w = c["weapon"]
    party.attack_action(me, c, tid, lambda k: w, rider=lambda t, res: stunning_strike(
        party, me, t, w, res, want=_stun_worth(party, me, t)))
    if not party.bonus_free(me) or party.down(me) or not unarmed(c):
        return
    near = [f for f in party.foes(me) if party.dist(me, f) <= 5.01 and not party.blocked(me, f)]
    if not near:
        return
    hurt = party.hp_left(me) <= c["hp"] // 3
    keep = 1 if c.get("stunning_strike") else 0                  # a point kept for next turn's Stunning Strike
    if hurt and points(party, me) >= 1 and level(c) >= 2:
        party.use_bonus(me)
        spend(party, me)
        party.s.addEffect(me, "Note: Disengage", True)
        c["dodging"] = True
        sim.say("turn", "%s uses Patient Defense (Bonus Action, 1 Focus Point, %d left): Disengage and Dodge" % (
            c["name"], points(party, me)))
        return
    target = tid if tid in near else min(near, key=lambda f: (f != party.focus, party.hp_left(f)))
    gm = getattr(sim, "gm_rules", None)
    if level(c) >= 2 and points(party, me) >= 1 + keep:
        party.use_bonus(me)
        spend(party, me)
        how = ("addle" if gm and gm.has(target, "Prone") else "topple") if c.get("open_hand") else None
        sim.say("turn", "%s uses Flurry of Blows (Bonus Action, 1 Focus Point, %d left)%s" % (
            c["name"], points(party, me), ": Open Hand Technique, %s on a hit" % TECHNIQUES[how] if how else ""))
        flurry(party, me, target, how, stun=_stun_worth(party, me, target))
        return
    party.use_bonus(me)
    sim.say("turn", "%s makes an Unarmed Strike (Martial Arts, Bonus Action)" % c["name"])
    strike(party, me, target, stun=_stun_worth(party, me, target))


def _stun_worth(party, me, tid):
    gm = getattr(party.sim, "gm_rules", None)
    return bool(gm) and not party.down(tid) and not gm.incapacitated(tid) and not gm.cond_immune(tid, "Stunned")


# ---------------------------------------------------------------------- Play live
def of(fight):
    m = getattr(fight, "monk", None)
    if m is None:
        m = fight.monk = LiveMonk(fight)
    return m


class LiveMonk:
    def __init__(self, fight):
        self.fight = fight

    @property
    def sim(self):
        return self.fight.sim

    @property
    def party(self):
        return self.sim.party

    def summary(self, me):
        """For the sheet: Focus Points, the Martial Arts die, the save DC."""
        c = self.sim.by_id(me)
        if not is_monk(c):
            return None
        return {"points": points(self.party, me), "max": int(c.get("focus_points", 0) or 0), "die": die(c),
                "dc": save_dc(c), "level": level(c), "open_hand": bool(c.get("open_hand")),
                "reactions": [n for n, on in (("Deflect Attacks", c.get("deflect_attacks")), ("Slow Fall", c.get("slow_fall")),
                                              ("Deflect Energy", c.get("deflect_energy")),
                                              ("Disciplined Survivor", c.get("disciplined_survivor"))) if on],
                "superior_defense": defense_rounds(self.party, me)}

    def _able(self, me):
        import live_actions
        try:
            return self.fight.actions.able(me)
        except live_actions.ActionError as e:
            raise MonkError(str(e))

    def check(self, me, op, focus=False):
        t, c = self._able(me)
        party = self.party
        if not is_monk(c):
            raise MonkError("%s is a Monk feature." % NAMES[op])
        if op == "superior_defense":                             # no action, at the start of the turn
            fresh = not t["action_used"] and not t.get("attacks_made") and party.bonus_free(me) and \
                t["movement"] >= t.get("speed", 0)
            why = defense_why(party, me, fresh)
            if why:
                raise MonkError(why)
            return t, c
        if op in ("flurry", "patient_defense", "step_of_the_wind") and level(c) < 2 and (focus or op == "flurry"):
            raise MonkError("Monk's Focus comes at Monk level 2.")
        if op in ("martial_arts", "flurry") and not unarmed(c):
            raise MonkError("No Unarmed Strike on %s's sheet." % c["name"])
        if not party.bonus_free(me):
            raise MonkError("%s's Bonus Action is used this turn." % c["name"])
        if (focus or op == "flurry") and points(party, me) < 1:
            raise MonkError("No Focus Point left (%d of %d)." % (points(party, me), int(c.get("focus_points", 0) or 0)))
        if op == "step_of_the_wind" and t.get("speed", 0) <= 0:
            raise MonkError("%s's Speed is 0: a Dash adds nothing." % c["name"])
        return t, c

    def target_ok(self, me, tid):
        party, sim = self.party, self.sim
        o = next((x for x in sim.sc["combatants"] if x["id"] == tid), None)
        if not o or tid == me:
            raise MonkError("Choose another creature.")
        if sim.down(tid):
            raise MonkError("%s is down." % o["name"])
        if party.dist(me, tid) > 5.01:
            raise MonkError("%s is %d ft away: an Unarmed Strike reaches 5 ft." % (o["name"], round(party.dist(me, tid))))
        if party.blocked(me, tid):
            raise MonkError("A wall stands between them.")
        return o

    def actions(self, me):
        """The Monk's buttons, with the other actions (sim/live_actions.py offers)."""
        c, out = self.sim.by_id(me), []
        if not is_monk(c):
            return out
        others = [o["id"] for o in self.sim.sc["combatants"] if o["id"] != me]

        def entry(e, check, pick=False):
            try:
                check()
                e["ready"] = True
            except MonkError as err:
                e["ready"], e["why"] = False, str(err)
            if pick:
                e["targets"], e["refused"] = [], {}
                for o in others:
                    try:
                        self.target_ok(me, o)
                        e["targets"].append(o)
                    except MonkError as err:
                        e["refused"][o] = str(err)
            out.append(e)
        if unarmed(c):
            entry({"op": "martial_arts", "label": NAMES["martial_arts"], "time": "bonus", "bonus": False},
                  lambda: self.check(me, "martial_arts"), pick=True)
        if level(c) >= 2:
            modes = [("strikes", "two Unarmed Strikes")] + ([(k, "%s on a hit" % v) for k, v in TECHNIQUES.items()]
                                                             if c.get("open_hand") else [])
            for mode, text in modes:
                entry({"op": "flurry", "mode": mode, "label": "Flurry of Blows: %s" % text, "time": "bonus", "bonus": False,
                       "points": points(self.party, me)}, lambda: self.check(me, "flurry"), pick=True)
        for op, free, paid in (("patient_defense", "Disengage", "Disengage + Dodge (1 Focus)"),
                               ("step_of_the_wind", "Dash", "Disengage + Dash (1 Focus)")):
            entry({"op": op, "mode": "free", "label": "%s: %s" % (NAMES[op], free), "time": "bonus", "bonus": False},
                  lambda op=op: self.check(me, op))
            if level(c) >= 2:
                entry({"op": op, "mode": "focus", "label": "%s: %s" % (NAMES[op], paid), "time": "bonus", "bonus": False},
                      lambda op=op: self.check(me, op, focus=True))
        if c.get("superior_defense"):
            entry({"op": "superior_defense", "label": "Superior Defense (3 Focus, Resistance for 1 minute)", "time": "free",
                   "bonus": False, "rounds": defense_rounds(self.party, me)}, lambda: self.check(me, "superior_defense"))
        return out

    def do(self, me, cmd):
        """Checked, then done; returns how it was paid ("bonus")."""
        op, party, sim = cmd.get("op"), self.party, self.sim
        mode = cmd.get("mode") or ("strikes" if op == "flurry" else "free")
        focus = op == "flurry" or mode == "focus"
        t, c = self.check(me, op, focus=focus)
        if op == "superior_defense":
            superior_defense(party, me)
            return "free"
        if op in ("martial_arts", "flurry"):
            tid = cmd.get("target")
            self.target_ok(me, tid)
            how = mode if mode in TECHNIQUES else None
            if how and not c.get("open_hand"):
                raise MonkError("Open Hand Technique is a Warrior of the Open Hand feature (Monk 3).")
            stun = bool(cmd.get("stun"))
            if stun and stun_why(party, me, unarmed(c)):
                raise MonkError(stun_why(party, me, unarmed(c)))
            party.use_bonus(me)
            if op == "martial_arts":
                sim.say("turn", "%s makes an Unarmed Strike (Martial Arts, Bonus Action)" % c["name"])
                if strike(party, me, tid, stun=stun) is None:
                    raise MonkError("The simulator refused that strike (out of reach or blocked).")
                return "bonus"
            spend(party, me)
            sim.say("turn", "%s uses Flurry of Blows (Bonus Action, 1 Focus Point, %d left)%s" % (
                c["name"], points(party, me), ": Open Hand Technique, %s on a hit" % TECHNIQUES[how] if how else ""))
            flurry(party, me, tid, how, stun=stun, other=cmd.get("target2"))
            return "bonus"
        party.use_bonus(me)
        paid = " (Bonus Action, 1 Focus Point, %d left)" % spend(party, me) if focus else " (Bonus Action)"
        if op == "patient_defense" or focus:                     # Disengage (Patient Defense; Step of the Wind with Focus)
            sim.S.addEffect(me, "Note: Disengage", True)
            t["disengaged"] = True
        if op == "patient_defense":
            if focus:
                c["dodging"] = True
            sim.say("turn", "%s uses Patient Defense%s: %s" % (c["name"], paid, "Disengage and Dodge: no Opportunity Attacks "
                    "against its movement this turn; attacks against it have Disadvantage and Dexterity saves Advantage "
                    "until its next turn" if focus else "Disengage: no Opportunity Attacks against its movement this turn"))
        else:
            speed = t.get("speed", 30)
            t["movement"] += speed
            sim.say("turn", "%s uses Step of the Wind%s: %s +%d ft of movement (%d ft left)%s" % (
                c["name"], paid, "Disengage and Dash:" if focus else "Dash:", speed, t["movement"],
                "; its jump distance is doubled this turn" if focus else ""))
        return "bonus"

    def attack_offer(self, me, w):
        """The Stunning Strike choice beside an attack on the sheet (a Monk of level 5, a Monk weapon)."""
        c = self.sim.by_id(me)
        if not c.get("stunning_strike") or not monk_weapon(w):
            return None
        why = stun_why(self.party, me, w)
        return {"ready": not why, "why": why or "", "points": points(self.party, me), "dc": save_dc(c)}
