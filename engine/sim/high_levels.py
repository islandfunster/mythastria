"""GM 2026-10-26 (goal 9, "Test heroes to the full SRD"): the level 9-20 class and subclass features of the seven test
heroes (and of any character the builder makes with them) that fit the engine's building blocks, SRD 5.2.1. The flags
come from the sheet (sim/character_build.py member(), FEATURE_FLAGS); sim/party.py, sim/gm_rules.py and sim/live_play.py
call in here, for Play live and the computer-played heroes alike.

- Tactical Master (Fighter 9): an attack with a weapon whose mastery the Fighter uses swaps that property for Push, Sap
  or Slow (Play live: chosen on the attack; the computer: Sap on a foe that will outlast the turn).
- Studied Attacks (Fighter 13): after a miss, Advantage on the next attack roll against that creature before the end of
  the Fighter's next turn.
- Survivor (Champion 18): Heroic Rally, 5 + the Constitution modifier at the start of each turn while Bloodied (above
  0 HP); Defy Death, Advantage on Death Saving Throws and 18-20 counts as a 20.
- Supreme Sneak (Thief 9): the Stealth Attack option of Cunning Strike (one Sneak Attack die): a hidden Rogue's attack
  leaves the hiding on when the Rogue ends the turn behind Three-Quarters or Total Cover from every enemy that is up.
  Improved Cunning Strike (Rogue 11): two options on one Sneak Attack (Trip and Stealth Attack).
- Relentless Rage (Barbarian 11): dropping to 0 HP while raging, a DC 10 Constitution save (+5 each time, 10 again after
  a rest): Hit Points twice the Barbarian level instead. Improved Brutal Strike 17: 2d10.
- Abjure Foes (Paladin 9): Magic action, a Channel Divinity use: up to the Charisma modifier (1 at least) creatures
  within 60 ft she sees make a Wisdom save or are Frightened for 1 minute or until they take damage; while so
  Frightened a creature does one thing on its turn (move, action or Bonus Action): with no enemy beside it, it holds.
- Aura of Courage (Paladin 10): she and allies in her aura can't be Frightened while she is not Incapacitated.
- Radiant Strikes (Paladin 11): +1d8 Radiant on a melee weapon or Unarmed Strike hit.
- Aura Expansion (Paladin 18): her auras reach 30 ft.
- Empowered Evocation (Evoker 10): + the Intelligence modifier to one damage roll of a Wizard Evocation spell.
- Supreme Healing (Life 17): a spell's healing dice at their highest.
- Superior Inspiration (Bard 18): on rolling Initiative, Bardic Inspiration back to two uses if she has fewer (the
  fight's start, and after the adventure day's carried uses: sim/rests.py apply_to_sim).
- Words of Creation (Bard 20): Power Word Heal and Power Word Kill always prepared (the builder); either takes a second
  creature within 10 ft of the first (Play live's general caster and the referee; the computer-played Bard casts them,
  bard_words).
- CASTER-HIGH (GM 2026-10-28), the casters' level 10-20 features, SRD 5.2.1:
  - Overchannel (Evoker 14): a Wizard spell that deals damage, cast with a level 1-5 slot, deals its maximum damage on
    the turn it is cast (every die at its highest: fight_state._damage, Party.area_spell, the general caster's rolls).
    The first use after a Long Rest costs nothing; each later one: 2d12 Necrotic per slot level, +1d12 per level each
    time again, ignoring Resistance and Immunity. Play live: a choice on the cast; the computer: its free use only, on a
    Fireball or Cone of Cold.
  - Spell Mastery (Wizard 18): its level 1 and level 2 spells (casting time an action) at their lowest level without a
    slot, at will; Signature Spells (Wizard 20): each of its two level 3 spells once at level 3 without a slot until a
    Short or Long Rest (the "free" uses, shared with Ask the GM). A higher slot asked for is spent as usual.
  - Hurl Through Hell (Fiend 14): once per turn on a hit with an attack roll, a Charisma save against the spell save DC
    or 8d10 Psychic (not a Fiend) and gone until the end of the Warlock's next turn (Incapacitated, nobody's target, its
    turns skipped), back in its space. Once per Long Rest, or a Pact Magic slot restores it (no action).
  - Eldritch Master (Warlock 20): Magical Cunning (the adventure day, sim/rests.py) regains all Pact Magic slots.
  - Divine Intervention (Cleric 10): a Magic action, a Cleric spell of level 5 or lower (not a Reaction) without a slot
    or Material components, once per Long Rest: the table's Cleric spells on the sheet cast it from their cards; any
    other is Ask the GM (its use counted here). Greater Divine Intervention (20): Wish through Ask the GM; then no
    Divine Intervention for 2d4 Long Rests (rests.py counts them).

Not played, "Ask the GM" (docs/development/CLASS_FEATURES_AUDIT.md lists them with the reason).
"""
import character_rules as cr

EVOCATION = {s["name"] for s in cr.rules()["spells"] if s.get("school") == "Evocation" and "Wizard" in s["classes"]}
MASTERIES = ("Push", "Sap", "Slow")                               # Tactical Master's swaps
OWN = ("graze", "vex", "sap", "cleave", "nick", "push", "slow", "topple")   # a weapon's own mastery flag
OPS = ("abjure_foes",)
FT = 5


class HighError(ValueError):
    pass


def _state(party, name):
    d = getattr(party, name, None)
    if d is None:
        d = {}
        setattr(party, name, d)
    return d


def mod(score):
    return (int(score or 10) - 10) // 2


# ---------------------------------------------------------------------- Fighter
def tactical_options(c, weapon):
    """Tactical Master's choices for this attack: [] when the character lacks it or the weapon has no mastery it uses."""
    if not c.get("tactical_master") or not isinstance(weapon, dict) or weapon.get("cantrip"):
        return []
    return list(MASTERIES) if any(weapon.get(k) for k in OWN) else []


def own_mastery(weapon):
    for k in OWN:
        if weapon.get(k):
            return k.title()
    return ""


def choose_mastery(party, me, tid, c, weapon):
    """The computer-played Fighter: Sap on a foe whose Hit Points outlast this attack's best damage (it will strike back),
    else the weapon's own mastery (None)."""
    if not tactical_options(c, weapon) or weapon.get("sap") or tid is None:
        return None
    if tid in _state(party, "sapped").get(me, ()):
        return None
    dice, _, bonus = str(weapon.get("dmg", "1d4")).partition("+")
    n, _, sides = dice.partition("d")
    most = int(n or 1) * int(sides or 4) + int(bonus or 0)
    return "Sap" if party.hp_left(tid) > most else None


def apply_mastery(party, me, tid, mastery):
    """Push (Large or smaller: 10 ft straight away), Sap (Disadvantage on its next attack roll before the start of the
    attacker's next turn) or Slow (Speed -10 ft until the start of the attacker's next turn) on a hit."""
    sim, c = party.sim, party.sim.by_id(me)
    gm = getattr(sim, "gm_rules", None)
    if party.down(tid):
        return
    if mastery == "Push":
        if sim.size_sq(tid) > 2:
            sim.say("dice", "Push (Tactical Master): %s is too big to push" % party.name(tid))
            return
        (ax, ay), (bx, by) = party.pos(me), party.pos(tid)
        d = ((bx > ax) - (bx < ax), (by > ay) - (by < ay))
        sim.say("dice", "Push (Tactical Master): %s is pushed 10 ft away from %s" % (party.name(tid), c["name"]))
        party.push(tid, d, 2)
    elif mastery == "Sap":
        party.s.setField(tid, "sim_sapped", 1)
        party.sapped.setdefault(me, set()).add(tid)
        sim.say("dice", "Sap (Tactical Master): %s has Disadvantage on its next attack roll" % party.name(tid))
    elif mastery == "Slow" and gm:
        slowed = _state(party, "tm_slowed").setdefault(me, set())
        if not gm.has(tid, "Slowed"):
            gm.add(tid, "Slowed", "(%s's Slow mastery: Speed -10 ft until the start of %s's next turn)" % (c["name"], c["name"]),
                   by=me, ft=10, ends=99)
            slowed.add(tid)


def studied_adv(party, me, tid, peek=False):
    """Studied Attacks: the Advantage a miss earned against this creature (used by this attack roll; peek: only asked)."""
    if peek:
        return (me, tid) in _state(party, "studied")
    return bool(_state(party, "studied").pop((me, tid), None) is not None)


def studied_miss(party, me, tid):
    if party.sim.by_id(me).get("studied_attacks") and not party.down(tid):
        _state(party, "studied")[(me, tid)] = party.s.round()
        party.sim.say("dice", "Studied Attacks: %s has Advantage on the next attack roll against %s" % (
            party.name(me), party.name(tid)))


# ---------------------------------------------------------------------- Rogue
def hiding(gm, me):
    info = (gm.cond.get(me, {}) if gm else {}).get("Invisible")
    return bool(info) and not info.get("spell")                  # the Hide action's Invisible (not the spell)


def stealth_ok(party, me, c):
    """Why Stealth Attack can't be used now ("" when it can)."""
    gm = getattr(party.sim, "gm_rules", None)
    if not c.get("supreme_sneak"):
        return "Stealth Attack is Supreme Sneak's (Thief 9)."
    if not hiding(gm, me):
        return "%s is not hidden (the Hide action's Invisible condition)." % c["name"]
    return ""


def keeps_hidden(gm, src):
    """gm_rules.attack_rolled: this attack is a Stealth Attack, so the hiding waits for the end of the turn."""
    p = getattr(gm, "p", None)
    return bool(p) and _state(p, "stealth_attack").get(src) == p.s.turnSerial


def end_turn(party, me):
    """The end of a member's turn: Stealth Attack's hiding stays only behind Three-Quarters or Total Cover from every
    enemy that is up."""
    serial = _state(party, "stealth_attack").pop(me, None)
    gm = getattr(party.sim, "gm_rules", None)
    if serial is None or not gm or not hiding(gm, me):
        return
    env = getattr(party.sim, "env", None)
    open_to = [f for f in party.foes(me) if not party.down(f) and not party.blocked(f, me)
               and (env.cover(f, me) if env else 0) < 5]          # a wall between them: Total Cover
    if open_to:
        gm.remove(me, "Invisible", "the Stealth Attack ends the turn in the open (%s has less than Three-Quarters Cover "
                  "from %s)" % (party.name(me), party.name(open_to[0])))
    else:
        party.sim.say("dice", "Supreme Sneak: %s ends the turn behind cover and stays hidden" % party.name(me))


# ---------------------------------------------------------------------- Barbarian
def relentless(gm, tid):
    """Relentless Rage at 0 HP: True when the Barbarian stays up (gm_rules.fortitude: 1 HP now, the rest healed after)."""
    p = gm.p
    c = gm.sim.by_id(tid)
    if not p or not c.get("relentless_rage") or tid not in getattr(p, "raging", {}):
        return False
    times = _state(p, "relentless")
    dc = 10 + 5 * times.get(tid, 0)
    times[tid] = times.get(tid, 0) + 1
    d20, bonus = gm.sim.rng.randint(1, 20), int(c.get("con_save", 0) or 0)
    ok = d20 + bonus >= dc
    lv = int(c.get("level", 1) or 1)
    gm.sim.say("dice", "%s Relentless Rage: Constitution save d20 %d %+d = %d vs DC %d -> %s" % (
        c["name"], d20, bonus, d20 + bonus, dc, "Hit Points %d instead of 0" % (2 * lv) if ok else "down at 0 HP"))
    if ok:
        gm.sim.later.append(lambda: p.s.heal(tid, 2 * lv - 1))
    return ok


def brutal_dice(c):
    return "2d10" if int(c.get("improved_brutal_strike") or 0) >= 2 else "1d10"


# ---------------------------------------------------------------------- Paladin
def aura_ft(c):
    return int(c.get("aura_ft") or 10)


def courage(gm, t):
    """Aura of Courage: the Paladin keeping t from the Frightened condition, or None."""
    p = gm.p
    for q in getattr(p, "aura_ids", ()) if p else ():
        pal = gm.sim.by_id(q)
        if pal.get("aura_courage") and p.side(q) == p.side(t) and not gm.sim.down(q) and not gm.incapacitated(q) \
                and (q == t or p.dist(q, t) <= aura_ft(pal)):
            return q
    return None


def radiant(c, weapon):
    """Radiant Strikes: the extra die on a melee weapon (or Unarmed Strike) hit."""
    melee = weapon.get("reach", 5) <= 10 and not weapon.get("cantrip") and weapon.get("dmgtype") not in (None, "") \
        or weapon.get("name") == "Unarmed Strike"
    return "1d8:radiant" if c.get("radiant_strikes") and melee else ""


def abjure_count(c):
    return max(1, int(c.get("spell_mod") or mod((c.get("abilities") or {}).get("cha"))))


def abjure_candidates(party, me):
    """Foes within 60 ft that she sees, not Frightened yet and up, the most Hit Points first."""
    gm = getattr(party.sim, "gm_rules", None)
    out = [f for f in party.foes(me) if not party.down(f) and party.dist(me, f) <= 60 and not party.blocked(me, f)
           and party.sim.sees(me, f) and not (gm and gm.has(f, "Frightened"))]
    return sorted(out, key=lambda f: -party.hp_left(f))


def abjure_check(party, me):
    c = party.sim.by_id(me)
    if not c.get("abjure_foes"):
        raise HighError("Abjure Foes is a Paladin's (level 9).")
    if party.channel.get(me, 0) <= 0:
        raise HighError("%s has no Channel Divinity use left." % c["name"])
    if not abjure_candidates(party, me):
        raise HighError("No foe within 60 ft that %s sees (and not Frightened already)." % c["name"])


def abjure(party, me, targets=None):
    """Abjure Foes on the chosen creatures (or the strongest ones in range): spends a Channel Divinity use. The caller
    pays the Magic action."""
    c, gm = party.sim.by_id(me), party.sim.gm_rules
    pool = abjure_candidates(party, me)
    n = abjure_count(c)
    if targets:
        bad = [t for t in targets if t not in pool]
        if bad:
            raise HighError("%s: not a foe within 60 ft that %s sees." % (party.name(bad[0]), c["name"]))
        if len(targets) > n:
            raise HighError("Abjure Foes takes up to %d creature%s (the Charisma modifier)." % (n, "" if n == 1 else "s"))
        chosen = list(dict.fromkeys(targets))
    else:
        chosen = pool[:n]
    party.channel[me] -= 1
    dc = party.spell_dc(c)
    party.sim.say("dice", "%s uses Abjure Foes (Channel Divinity, Magic action): DC %d Wisdom save for %s" % (
        c["name"], dc, ", ".join(party.name(f) for f in chosen)))
    until = int(party.s.round()) + 10
    for f in chosen:
        if gm.cond_immune(f, "frightened"):
            party.sim.say("dice", "%s can't be Frightened" % party.name(f)); continue
        if not gm.condition_save(f, "wis", dc, "Abjure Foes"):
            gm.add(f, "Frightened", "(%s's Abjure Foes: 1 minute or until it takes damage; on its turns it moves, takes an "
                   "action or a Bonus Action, one of them)" % c["name"], by=me, abjure=True, expires=until)
    return chosen


def abjured(gm, t):
    info = gm.cond.get(t, {}).get("Frightened")
    return bool(info and info.get("abjure"))


def abjure_hurt(gm, t):
    """Damage ends Abjure Foes' Frightened."""
    if abjured(gm, t):
        gm.remove(t, "Frightened", "the damage ends Abjure Foes")


def abjure_turn(gm, me):
    """A creature Frightened by Abjure Foes does one thing on its turn. With an enemy beside it, that is its action (it
    stays put); otherwise it would have to move, and Frightened it comes no closer: it holds. True: the turn is over."""
    if not abjured(gm, me) or gm.sim.by_id(me).get("pc"):
        return False
    p = gm.p
    side = p.side(me)
    near = [o["id"] for o in gm.sim.sc["combatants"] if p.side(o["id"]) != side and not gm.sim.down(o["id"])
            and p.dist(me, o["id"]) <= FT]
    if near:
        gm.sim.say("turn", "%s is Frightened (Abjure Foes): it takes its action, and no move or Bonus Action" %
                   gm.sim.by_id(me)["name"])
        return False
    gm.sim.say("turn", "%s is Frightened (Abjure Foes): one thing this turn, and it comes no closer: it holds" %
               gm.sim.by_id(me)["name"])
    return True


def abjure_tactic(party, me, c):
    """The computer-played Paladin: Abjure Foes when three foes or more are in its range (the action) and a Channel
    Divinity use is left."""
    if not c.get("abjure_foes") or party.channel.get(me, 0) <= 0:
        return False
    if len(abjure_candidates(party, me)) < 3:
        return False
    abjure(party, me)
    return True


# ---------------------------------------------------------------------- Wizard, Cleric
def empowered(c, spell):
    """Empowered Evocation: + the Intelligence modifier for a Wizard Evocation spell."""
    base = str(spell or "").split(" (")[0]
    if not c.get("empowered_evocation") or base not in EVOCATION:
        return 0
    return max(1, mod((c.get("abilities") or {}).get("int")) if c.get("abilities") else int(c.get("spell_mod") or 1))


def heal_roll(rng, c, dice):
    """A spell's healing dice ("2d8+5"): Supreme Healing uses the highest number of each die."""
    import party as party_mod
    if not c.get("supreme_healing"):
        return party_mod.roll(rng, dice)
    total = 0
    for part in str(dice).replace("-", "+-").split("+"):
        part = part.strip()
        if not part:
            continue
        if "d" in part:
            n, _, s = part.partition("d")
            total += int(n or 1) * int(s)
        else:
            total += int(part)
    return total


# ---------------------------------------------------------------------- the start of a member's turn
def turn_start(party, me):
    c = party.sim.by_id(me)
    gm = getattr(party.sim, "gm_rules", None)
    for tid in _state(party, "tm_slowed").pop(me, set()):       # Slow (Tactical Master): until the start of this turn
        if gm and gm.has(tid, "Slowed") and (gm.cond[tid]["Slowed"] or {}).get("by") == me:
            gm.remove(tid, "Slowed", "the start of %s's turn" % c["name"])
    for key, r in list(_state(party, "studied").items()):         # Studied Attacks: before the end of the next turn
        if key[0] == me and r < party.s.round() - 1:
            _state(party, "studied").pop(key)
    if c.get("survivor") and not party.down(me):                  # Heroic Rally (Champion 18)
        left = party.hp_left(me)
        if 0 < left <= c["hp"] // 2:
            heal = 5 + mod((c.get("abilities") or {}).get("con"))
            party.s.heal(me, heal)
            party.sim.say("dice", "%s: Heroic Rally (Survivor), Bloodied: regains %d HP" % (c["name"], heal))


def defy_death(c, d20):
    """Defy Death (Champion 18): a Death Saving Throw with Advantage counts 18-20 as a 20 (the caller rolls twice)."""
    return 20 if c.get("survivor") and d20 >= 18 else d20


# ---------------------------------------------------------------------- Bard (GM 2026-10-28, "heroes 20")
WORDS = ("Power Word Heal", "Power Word Kill")                    # Words of Creation's spells
WORDS_FT = 10


def superior_inspiration(party, me, c):
    """Superior Inspiration (Bard 18): "When you roll Initiative, you regain expended uses of Bardic Inspiration until
    you have two if you have fewer than that." True when uses came back."""
    if not has(c, "superior_inspiration", "Superior Inspiration"):
        return False
    left = int(party.bi_uses.get(me, 0) or 0)
    if left >= 2:
        return False
    party.bi_uses[me] = 2
    party.sim.say("tactic", "%s: Superior Inspiration, Bardic Inspiration back to 2 uses as the fight starts (had %d)" % (
        c["name"], left))
    return True


def words_extra(c, spell):
    """Words of Creation (Bard 20): Power Word Heal or Power Word Kill "can target a second creature with it if that
    creature is within 10 feet of the first target": 1 more creature for those two spells, else 0."""
    return 1 if str(spell or "").split(" (")[0] in WORDS and has(c, "words_of_creation", "Words of Creation") else 0


def words_second(party, first, tid):
    """Why the second creature of Words of Creation can't be chosen (more than 10 ft from the first), else None."""
    ft = party.dist(first, tid)
    if ft > WORDS_FT + 0.01:
        return "%s is %d ft from %s: Words of Creation's second creature must be within %d ft of the first." % (
            party.name(tid), round(ft), party.name(first), WORDS_FT)
    return None


def words_pair(party, c, spell, cands):
    """The computer-played Bard's choice for a power word: the first of `cands` and, with Words of Creation, the next one
    of them within 10 ft of it."""
    if not cands:
        return []
    first = cands[0]
    if not words_extra(c, spell):
        return [first]
    second = next((t for t in cands[1:] if not words_second(party, first, t)), None)
    return [first] + ([second] if second is not None else [])


def bard_words(party, me, c):
    """The computer-played Bard's Action with the level 9 power words (a level 9 slot, 60 ft, a creature she sees): Power
    Word Heal on fallen allies (all their Hit Points back) when two are down, or one is down and she has no Healing Word;
    else Power Word Kill on a foe with 100 Hit Points or fewer that a cantrip won't finish (more than 30 left). With Words
    of Creation each takes a second creature within 10 ft of the first. True when she cast one."""
    if not party.slot_free(me, 9):
        return False
    names = {s.get("name") for s in c.get("spell_list") or []}

    def seen(t):
        return party.dist(me, t) <= 60 and not party.blocked(me, t) and party.sim.sees(me, t)
    if "Power Word Heal" in names:
        down = sorted((a for a in party.allies(me) if party.down(a) and not party.deaths.get(a, {}).get("dead") and seen(a)),
                      key=lambda a: party.dist(me, a))
        pick = words_pair(party, c, "Power Word Heal", down)
        if len(pick) >= 2 or (pick and not c.get("healing_word")):
            return _word(party, me, c, "Power Word Heal", pick)
    if "Power Word Kill" in names:
        foes = sorted((f for f in party.foes(me) if seen(f) and 30 < party.hp_left(f) <= 100), key=lambda f: -party.hp_left(f))
        pick = words_pair(party, c, "Power Word Kill", foes)
        if pick:
            return _word(party, me, c, "Power Word Kill", pick)
    return False


def _word(party, me, c, spell, targets):
    """A power word cast through the general caster's rules (sim/live_general.py), outside Play live."""
    import live_general
    from creature_abilities import _Fight
    g = live_general.General(getattr(party.sim, "live", None) or _Fight(party.sim))
    p = live_general.plan(spell)
    with party.refereed(me, spell, {"targets": list(targets)}):
        slot = party.spend_slot(me, 9)
        label = "%s (a level %d slot)" % (spell, slot)
        if len(targets) > 1:
            party.sim.say("dice", "%s: Words of Creation, %s takes a second creature within 10 ft of the first" % (
                c["name"], spell))
        if p["kind"] == "heal":
            g.heal(me, c, p, slot, targets, label)
        else:
            g.word(me, c, p, targets, label, party.spell_dc(c))
    return True


# ---------------------------------------------------------------------- group 3, batch 1 (GM 2026-10-27)
def has(c, flag, name):
    """A feature on the sheet: its flag (sim/character_build.py FEATURE_FLAGS) or its name in the feature list (the
    test heroes' later levels list some only by name)."""
    return bool(c.get(flag)) or any(isinstance(f, dict) and f.get("name") == name for f in c.get("feature_list") or [])


def score(c, ability):
    s = (c.get("abilities") or {}).get(ability)
    return int(s) if isinstance(s, (int, float)) else int(c.get("%s_score" % ability) or 10)


def indomitable_might(sim, c, ability, total, what):
    """Indomitable Might (Barbarian 18): a Strength check or Strength saving throw whose total is lower than the
    Strength score uses the score instead."""
    if ability != "str" or not has(c, "indomitable_might", "Indomitable Might"):
        return total
    s = score(c, "str")
    if total < s:
        sim.say("dice", "%s: Indomitable Might, the %s's total %d becomes the Strength score, %d" % (c["name"], what, total, s))
        return s
    return total


def remarkable(c, skill=None, initiative=False):
    """Remarkable Athlete (Champion 3): Advantage on Initiative rolls and Strength (Athletics) checks."""
    return has(c, "remarkable_athlete", "Remarkable Athlete") and (initiative or skill == "Athletics")


def elusive(c):
    """Elusive (Rogue 18): no attack roll has Advantage against the Rogue unless it has the Incapacitated condition
    (the fight state reads its field sim_elusive)."""
    return has(c, "elusive", "Elusive")


def persistent(c):
    """Persistent Rage (Barbarian 15): the Rage lasts 10 minutes without being extended; on rolling Initiative, all
    expended uses of Rage come back (once per Long Rest)."""
    return has(c, "persistent_rage", "Persistent Rage")


def blessed_cantrip(c, p):
    """Blessed Strikes: Potent Spellcasting (Cleric 7): + the Wisdom modifier to a Cleric cantrip's damage."""
    classes = (p.get("rules") or {}).get("classes") or ["Cleric"]
    if not c.get("potent_spellcasting") or p.get("level") != 0 or "Cleric" not in classes:
        return 0
    return int(c.get("spell_mod") or mod((c.get("abilities") or {}).get("wis")))


def improved_blessed(party, me, c, p, dealt):
    """Improved Blessed Strikes (Cleric 14), Potent Spellcasting: a cantrip that dealt damage gives the Cleric or a
    creature within 60 ft twice the Wisdom modifier in Temporary Hit Points (the most hurt ally in reach, else itself)."""
    if not dealt or p.get("level") != 0 or not has(c, "improved_blessed_strikes", "Improved Blessed Strikes"):
        return None
    amount = 2 * blessed_cantrip(c, p)
    if amount <= 0:
        return None
    side = [me] + [a for a in party.allies(me) if not party.down(a) and party.dist(me, a) <= 60]
    who = max(side, key=lambda a: (party.sim.by_id(a)["hp"] - party.hp_left(a), a == me))
    if amount > (party.s.getField(who, "sim_temp_hp") or 0):
        party.s.setField(who, "sim_temp_hp", amount)
    party.sim.say("dice", "%s: Improved Blessed Strikes, %s gains %d Temporary Hit Points" % (c["name"], party.name(who), amount))
    return who


# ---------------------------------------------------------------------- Play live: Abjure Foes as an action
def of(fight):
    h = getattr(fight, "high", None)
    if h is None:
        h = fight.high = LiveHigh(fight)
    return h


class LiveHigh:
    def __init__(self, fight):
        self.fight = fight

    @property
    def sim(self):
        return self.fight.sim

    def actions(self, me):
        c, party, out = self.sim.by_id(me), self.sim.party, []
        if c.get("abjure_foes"):
            e = {"op": "abjure_foes", "label": "Abjure Foes (Channel Divinity, up to %d)" % abjure_count(c), "time": "action",
                 "bonus": False, "uses": party.channel.get(me, 0)}
            try:
                self.check(me)
                e["ready"] = True
                e["targets"] = abjure_candidates(party, me)
            except HighError as err:
                e["ready"], e["why"] = False, str(err)
            out.append(e)
        return out

    def check(self, me):
        t = self.fight.turn_state
        c = self.sim.by_id(me)
        if t["action_used"]:
            raise HighError("%s's action is used this turn." % c["name"])
        abjure_check(self.sim.party, me)

    def do(self, me, cmd):
        if cmd.get("op") != "abjure_foes":
            raise HighError("Not an action here.")
        self.check(me)
        targets = [x for x in (cmd.get("targets") or []) if isinstance(x, str)]
        chosen = abjure(self.sim.party, me, targets or None)
        t = self.fight.turn_state
        t["action_used"], t["attacks_left"] = True, 0
        self.sim.settle()
        return "action", chosen



# ---------------------------------------------------------------------- CASTER-HIGH (GM 2026-10-28): Wizard, Warlock, Cleric
OVERCHANNEL, MASTERY, SIGNATURE = "Overchannel", "Spell Mastery", "Signature Spells"
HURL, DIVINE, GREATER = "Hurl Through Hell", "Divine Intervention", "Greater Divine Intervention"
DIVINE_TOP = 5                                                    # "any Cleric spell of level 5 or lower"


def _rules(name):
    import spell_rules
    try:
        return spell_rules.spell(name) or None
    except Exception:
        return None


def _sheet_spell(c, name):
    return next((s for s in c.get("spell_list") or [] if isinstance(s, dict) and s.get("name") == name), None)


def _pool(party, me):
    return list(party.pools.get(me) or [party.slots.get(me, 0)])


def _turn(party, me):
    """Play live's turn state when it is this character's turn, else None."""
    t = getattr(getattr(party.sim, "live", None), "turn_state", None)
    return t if t and t.get("id") == me else None


# ---- Spell Mastery, Signature Spells, Divine Intervention: a cast without a slot
def signature_left(party, me, name):
    """Signature Spells' use of this spell (the sheet's "free" use, in the store Ask the GM uses: sim/live_asks.py)."""
    return party.__dict__.setdefault("ask_uses", {}).setdefault(me, {}).setdefault("free:" + name, 1)


def divine_left(party, me):
    """Divine Intervention's use (1 after a Long Rest; none while Greater Divine Intervention's Long Rests run)."""
    return _state(party, "divine_left").setdefault(me, 1)


def divine_why(party, me, name):
    """Why Divine Intervention can't cast `name` now ("" when it can)."""
    c = party.sim.by_id(me)
    if not has(c, "divine_intervention", DIVINE):
        return "Divine Intervention is a Cleric's (level 10)."
    r = _rules(name)
    if not r or "Cleric" not in r.get("classes", ()) or not 1 <= int(r.get("level") or 0) <= DIVINE_TOP:
        return "Divine Intervention casts a Cleric spell of level 1 to %d; %s is not one." % (DIVINE_TOP, name)
    if r.get("casting_time") == "reaction":
        return "Divine Intervention can't cast a spell that takes a Reaction (%s)." % name
    if divine_left(party, me) <= 0:
        wait = _state(party, "divine_wait").get(me)
        return "%s's Divine Intervention is spent: it comes back with a Long Rest%s." % (
            c["name"], " (Greater Divine Intervention: %d Long Rests to go)" % wait if wait else "")
    t = _turn(party, me)
    if t and t.get("action_used"):
        return "%s's action is used this turn: Divine Intervention is a Magic action." % c["name"]
    return ""


def free_how(party, me, name, cmd=None):
    """The feature that casts `name` now without a spell slot ("" when none): Divine Intervention (cmd["divine"]), Spell
    Mastery (at its lowest level, at will) or Signature Spells (once until a rest). A slot asked for (cmd["use_slot"] or
    a slot above the spell's level) and Overchannel (which needs a slot) take a slot instead."""
    cmd = cmd or {}
    if cmd.get("divine"):
        return "" if divine_why(party, me, name) else DIVINE
    c = party.sim.by_id(me)
    sp = _sheet_spell(c, name)
    lv = int((sp or {}).get("level") or 0)
    if not sp or lv < 1 or cmd.get("use_slot") or cmd.get("overchannel"):
        return ""
    try:
        if cmd.get("slot") and int(cmd["slot"]) != lv:
            return ""
    except (TypeError, ValueError):
        return ""
    if sp.get("mastery") and lv <= 2 and has(c, "spell_mastery", MASTERY):
        return MASTERY
    if sp.get("free") and lv == 3 and has(c, "signature_spells", SIGNATURE) and signature_left(party, me, name) > 0:
        return SIGNATURE
    return ""


def no_slot(party, me, name, slot=None):
    """The cast's checks (sim/live_spells.py, sim/live_general.py): the feature that pays `name` without a slot, "" for a
    slot. During a cast, what was armed for it (the player's choice); else what the sheet allows now."""
    a = _state(party, "armed").get(me) if party else None
    if a and a.get("name") == name:
        return a.get("how", "")
    return free_how(party, me, name, {"slot": slot}) if party else ""


def card(party, me, e, recheck=None):
    """A Cast card (Play live) of a spell the table casts: Spell Mastery's or Signature Spells' cast without a slot
    (no_slot), Overchannel's and Divine Intervention's choices. recheck(e): a card greyed for want of a slot or a
    Material component, checked again as Divine Intervention casts it -> the fields to change (ready, creatures) or
    None; such a card is cast only that way (divine_only)."""
    name = e.get("name")
    free = no_slot_offer(party, me, name)
    if free:
        e["no_slot"] = free
    over = overchannel_offer(party, me, name)
    if over:
        e["overchannel"] = over
    divine = divine_offer(party, me, name)
    if divine:
        e["divine"] = divine
        if divine["ready"] and not e.get("ready") and recheck:
            state = _state(party, "armed")
            before = state.get(me)
            state[me] = {"how": DIVINE, "name": name}
            try:
                more = recheck(e)
            finally:
                if before is None:
                    state.pop(me, None)
                else:
                    state[me] = before
            if more:
                e.update(more, divine_only=True)
    return e


def no_slot_offer(party, me, name):
    """A Cast card's line for a spell its feature casts without a slot now: {"by", "note"} or None."""
    how = free_how(party, me, name)
    if not how:
        return None
    return {"by": how, "note": {MASTERY: "no slot at its lowest level (at will); a higher slot casts it higher",
                                SIGNATURE: "once without a slot until a Short or Long Rest; a higher slot casts it higher"}[how]}


def arm(party, me, name, cmd=None):
    """Before a cast resolves: the feature that pays it instead of a slot is armed (Party.spend_slot takes it), and an
    Overchannel cast turns every damage die to its highest. Returns the feature ("" for none). Raises HighError."""
    cmd = cmd or {}
    sim = party.sim
    if cmd.get("divine"):
        why = divine_why(party, me, name)
        if why:
            raise HighError(why)
    how = free_how(party, me, name, cmd)
    over = overchannel_check(party, me, name, cmd) if cmd.get("overchannel") else None
    _state(party, "armed")[me] = {"how": how, "name": name, "over": over, "bonus_free": party.bonus_free(me),
                                  "pool": _pool(party, me)}
    if over:
        sim.S.maxSrc = me
    return how


def armed(party, me):
    """The feature armed for this caster's cast now ("" when none): the cast's checks skip the slot (and, for Divine
    Intervention, the Material components)."""
    return (_state(party, "armed").get(me) or {}).get("how", "") if party else ""


def take_free(party, me, level):
    """Party.spend_slot: the armed feature pays the cast (once). Returns the slot level the spell is cast at, or None."""
    a = _state(party, "armed").get(me)
    if not a or not a.get("how") or a.get("paid"):
        return None
    a["paid"] = True
    c = party.sim.by_id(me)
    if a["how"] == SIGNATURE:
        party.ask_uses[me]["free:" + a["name"]] -= 1
    elif a["how"] == DIVINE:
        _state(party, "divine_left")[me] = 0
    party.sim.say("dice", "%s casts %s with %s: no spell slot%s" % (c["name"], a["name"], a["how"], {
        MASTERY: " (at its lowest level, at will)", SIGNATURE: " (once until a Short or Long Rest)",
        DIVINE: " and no Material components, as a Magic action (once per Long Rest)"}[a["how"]]))
    return int(level)


def disarm(party, me):
    """After the cast (or its refusal): Divine Intervention's Magic action; Overchannel's Necrotic damage."""
    a = _state(party, "armed").pop(me, None)
    sim = party.sim
    if getattr(sim.S, "maxSrc", None) == me:
        sim.S.maxSrc = None
    if not a:
        return
    if a.get("how") == DIVINE and a.get("paid"):
        t = _turn(party, me)
        if t:
            t["action_used"], t["attacks_left"] = True, 0
        if a["bonus_free"]:
            party.bonus_turn.pop(me, None)                        # a Bonus Action spell: cast with the Magic action
    if a.get("over"):
        spent = [b - n for b, n in zip(a["pool"], _pool(party, me))]
        slot = next((k + 1 for k, d in enumerate(spent) if d > 0), None)
        if slot:
            overchannel_cost(party, me, slot)


def pay(party, me, name, level, highest=False):
    """The computer-played caster's slot for `name`: Spell Mastery or Signature Spells when they cast it, else a slot."""
    arm(party, me, name)
    try:
        return party.spend_slot(me, level, highest)
    finally:
        disarm(party, me)


# ---- Overchannel
def overchannel_check(party, me, name, cmd=None):
    """Overchannel's needs for this cast; returns the slot level it will use. Raises HighError."""
    c = party.sim.by_id(me)
    if not has(c, "overchannel", OVERCHANNEL):
        raise HighError("Overchannel is an Evoker's (Wizard 14).")
    r = _rules(name)
    if not r or "Wizard" not in r.get("classes", ()) or not r.get("damage"):
        raise HighError("Overchannel is for a Wizard spell that deals damage; %s is not one." % name)
    lv = int(r.get("level") or 0)
    pool = _pool(party, me)
    try:
        want = int((cmd or {}).get("slot") or 0)
    except (TypeError, ValueError):
        want = 0
    want = want or next((k for k in range(max(lv, 1), len(pool) + 1) if pool[k - 1] > 0), 0)
    if lv < 1 or not 1 <= want <= 5:
        raise HighError("Overchannel needs a spell slot of level 1 to 5 (%s would use %s)." % (
            name, "no slot" if not want else "a level %d slot" % want))
    return want


def overchannel_cost(party, me, slot):
    """After an Overchannel cast: the first use since a Long Rest is free; the k-th one deals k d12 Necrotic per slot
    level to the Wizard, ignoring Resistance and Immunity."""
    used = _state(party, "overchannel_n")
    k = used.get(me, 0) + 1
    used[me] = k
    c = party.sim.by_id(me)
    if k == 1:
        party.sim.say("dice", "%s: Overchannel, the spell's maximum damage; the first use since a Long Rest has no "
                      "adverse effect" % c["name"])
        return 0
    dice = "%dd12" % (k * slot)
    party.sim.say("dice", "%s: Overchannel again (use %d since a Long Rest): %s Necrotic, ignoring Resistance and "
                  "Immunity" % (c["name"], k, dice))
    party.s.pcDamage(me, me, dice, 0, False, "")                  # no type: nothing resists or ignores it
    party.sim.settle()
    return k


def maxed(sim, me=None):
    """Overchannel is on for this cast (the damage dice roll their highest)."""
    src = getattr(getattr(sim, "S", None), "maxSrc", None)
    return src is not None and (me is None or src == me)


def max_total(expr):
    """'8d6+5' at its highest: 53."""
    import re
    total = 0
    for part in str(expr).replace(" ", "").replace("-", "+-").split("+"):
        m = re.fullmatch(r"(-?\d*)d(\d+)", part)
        if m:
            total += int(m.group(1) or 1) * int(m.group(2))
        elif re.fullmatch(r"-?\d+", part):
            total += int(part)
    return total


def overchannel_offer(party, me, name):
    """The Cast card's Overchannel choice: {"ready", "why", "uses", "cost"} or None (not the character's, or not a spell
    it fits)."""
    c = party.sim.by_id(me)
    if not has(c, "overchannel", OVERCHANNEL):
        return None
    r = _rules(name)
    if not r or "Wizard" not in r.get("classes", ()) or not r.get("damage") or not 1 <= int(r.get("level") or 0) <= 5:
        return None
    k = _state(party, "overchannel_n").get(me, 0)
    try:
        overchannel_check(party, me, name)
        why = ""
    except HighError as e:
        why = str(e)
    return {"ready": not why, "why": why, "uses": k,
            "cost": "none (the first use since a Long Rest)" if k == 0 else "%dd12 Necrotic per slot level" % (k + 1)}


def overchannel_tactic(party, me, c, name):
    """The computer-played Evoker: Overchannel on this Fireball or Cone of Cold while the use is still free."""
    if not has(c, "overchannel", OVERCHANNEL) or _state(party, "overchannel_n").get(me, 0):
        return False
    try:
        overchannel_check(party, me, name)
    except HighError:
        return False
    return True


def overchannel_on(party, me):
    """The computer-played Evoker's Overchannel for the cast that follows (overchannel_done after it)."""
    _state(party, "armed")[me] = {"how": "", "name": "", "over": 1, "bonus_free": True, "pool": _pool(party, me)}
    party.sim.S.maxSrc = me


# ---- Hurl Through Hell
def hurl_why(party, me):
    """Why Hurl Through Hell can't go on this hit ("" when it can)."""
    c = party.sim.by_id(me)
    if not has(c, "hurl_through_hell", HURL):
        return "Hurl Through Hell is a Fiend Warlock's (level 14)."
    if _state(party, "hurl_turn").get(me) == party.s.turnSerial:
        return "Hurl Through Hell is once per turn."
    if _state(party, "hurl_left").setdefault(me, 1) <= 0 and not any(_pool(party, me)):
        return "Hurl Through Hell is spent and no Pact Magic slot is left to restore it (a Long Rest)."
    return ""


def hurl_offer(party, me, c):
    """An attack's Hurl Through Hell choice (Play live), or None."""
    if not has(c, "hurl_through_hell", HURL):
        return None
    why = hurl_why(party, me)
    left = _state(party, "hurl_left").setdefault(me, 1)
    return {"ready": not why, "why": why, "dc": party.spell_dc(c),
            "pays": "its use (once per Long Rest)" if left > 0 else "a Pact Magic slot to restore it"}


def hurl(party, me, tid):
    """Hurl Through Hell on a hit: the use (or a Pact Magic slot restores it first); a Charisma save against the spell
    save DC; on a failure 8d10 Psychic (not a Fiend) and gone until the end of the Warlock's next turn. True: hurled."""
    if hurl_why(party, me) or party.down(tid):
        return False
    sim, c = party.sim, party.sim.by_id(me)
    gm = sim.gm_rules
    left = _state(party, "hurl_left")
    if left.get(me, 1) <= 0:                                     # a Pact Magic slot restores the use (no action)
        pool = party.pools.setdefault(me, _pool(party, me))
        lv = max(k + 1 for k, n in enumerate(pool) if n > 0)
        pool[lv - 1] -= 1
        party.slots[me] = party.slots.get(me, 1) - 1
        sim.say("dice", "%s expends a level %d Pact Magic slot to restore Hurl Through Hell" % (c["name"], lv))
    left[me] = 0
    _state(party, "hurl_turn")[me] = party.s.turnSerial
    dc = party.spell_dc(c)
    sim.say("dice", "%s uses Hurl Through Hell on %s: DC %d Charisma save" % (c["name"], party.name(tid), dc))
    if gm.condition_save(tid, "cha", dc, HURL):
        return False
    fiend = "fiend" in str(sim.by_id(tid).get("type", "")).lower()
    sim.say("dice", "%s disappears and hurtles through a nightmare landscape%s" % (
        party.name(tid), " (a Fiend: no damage)" if fiend else ""))
    if not fiend:
        party.s.pcDamage(me, tid, "8d10", 0, False, "psychic")
        sim.settle()
    if party.down(tid):
        return True
    _state(party, "hurled")[tid] = {"by": me, "serial": party.s.turnSerial}
    gm.add(tid, "Incapacitated", "(%s's Hurl Through Hell: gone through the Lower Planes until the end of %s's next "
           "turn)" % (c["name"], c["name"]), by=me, hurled=True)
    return True


def gone(party, tid):
    """Hurled through the Lower Planes: not in the fight until it returns."""
    return bool(party) and tid in (getattr(party, "hurled", None) or {})


def gone_why(party, tid):
    return "%s is hurtling through the Lower Planes (Hurl Through Hell) until it returns." % party.name(tid) \
        if gone(party, tid) else ""


def hurled_turn(gm, me):
    """A hurled creature's turn: it is not here. True: the turn is over."""
    if not gone(gm.p, me):
        return False
    gm.sim.say("turn", "%s is hurtling through the Lower Planes (Hurl Through Hell): no turn here" % gm.sim.by_id(me)["name"])
    return True


def hurl_return(party, ender):
    """The end of a turn: a creature the ender hurled on an earlier turn comes back to the space it left."""
    hurled = getattr(party, "hurled", None) or {}
    gm = getattr(party.sim, "gm_rules", None)
    for tid, h in list(hurled.items()):
        if h["by"] != ender or h["serial"] == party.s.turnSerial:
            continue
        hurled.pop(tid)
        if gm and (gm.cond.get(tid, {}).get("Incapacitated") or {}).get("hurled"):
            gm.remove(tid, "Incapacitated", "back from the Lower Planes")
        party.sim.say("turn", "%s returns from the Lower Planes to the space it left (Hurl Through Hell ends)" % party.name(tid))


def hurl_tactic(party, me, c, tid):
    """The computer-played Fiend Warlock: Hurl Through Hell on a hit while its free use is left (no slot spent), at a
    foe with more than 20 Hit Points left."""
    if hurl_why(party, me) or _state(party, "hurl_left").get(me, 1) <= 0 or party.down(tid) or party.hp_left(tid) <= 20:
        return False
    return hurl(party, me, tid)


# ---- Divine Intervention: the Cast cards, Ask the GM (any other Cleric spell; Greater: Wish), the computer
def divine_offer(party, me, name):
    """A Cast card's Divine Intervention choice, or None (not a Cleric 10, or not a spell it can cast)."""
    c = party.sim.by_id(me)
    if not has(c, "divine_intervention", DIVINE):
        return None
    r = _rules(name)
    if not r or "Cleric" not in r.get("classes", ()) or not 1 <= int(r.get("level") or 0) <= DIVINE_TOP \
            or r.get("casting_time") == "reaction":
        return None
    why = divine_why(party, me, name)
    return {"ready": not why, "why": why}


def ask_entry(party, me, name):
    """Ask the GM's Divine Intervention and Greater Divine Intervention: a Magic action and the engine's use."""
    if name not in (DIVINE, GREATER) or not has(party.sim.by_id(me), "divine_intervention", DIVINE):
        return {}
    note = ("Name the Cleric spell (level %d or lower, not a Reaction) in the note: the GM rules it. A Cleric spell the "
            "table casts has Divine Intervention on its Cast card." % DIVINE_TOP) if name == DIVINE else \
        "Wish through Divine Intervention: the GM rules it; then no Divine Intervention until 2d4 Long Rests are finished."
    return {"time": "action", "uses": divine_left(party, me), "note": note}


def ask_why(party, me, name):
    """Why Ask the GM can't take Divine Intervention now ("" when it can, or for any other feature)."""
    if name not in (DIVINE, GREATER) or not has(party.sim.by_id(me), "divine_intervention", DIVINE):
        return ""
    return divine_why(party, me, "Bless")                         # a Cleric spell it may always pick


def ask_spend(party, me, name):
    """Ask the GM used Divine Intervention (or Greater Divine Intervention's Wish): the use, and for Wish 2d4 Long Rests.
    Returns what it spent ("" for any other feature)."""
    if name not in (DIVINE, GREATER) or not has(party.sim.by_id(me), "divine_intervention", DIVINE):
        return ""
    _state(party, "divine_left")[me] = 0
    if name == GREATER:
        n = party.sim.rng.randint(1, 4) + party.sim.rng.randint(1, 4)
        _state(party, "divine_wait")[me] = n
        party.sim.say("dice", "%s: Greater Divine Intervention (Wish): 2d4 = %d, no Divine Intervention until %d Long "
                      "Rests are finished" % (party.name(me), n, n))
        return "Divine Intervention, then %d Long Rests" % n
    return "Divine Intervention (once per Long Rest)"


def divine_tactic(party, me, c):
    """The computer-played Cleric's Action: with no level 5+ slot to spend this turn, Divine Intervention casts Mass Cure
    Wounds (Party.mass_cure: three hurt allies or more inside, one down or two at a quarter of their Hit Points). True
    when it cast."""
    if divine_why(party, me, "Mass Cure Wounds") or party.slot_free(me, 5):
        return False
    arm(party, me, "Mass Cure Wounds", {"divine": True})
    try:
        return party.mass_cure(me, c)
    finally:
        disarm(party, me)


# ---- the adventure day (sim/rests.py): what a rest keeps
def to_day(party, i, e):
    """capture: the uses these features spent, into the day's entry ("once": a Long Rest clears it)."""
    once = e.setdefault("once", {})
    n = _state(party, "overchannel_n").get(i)
    if n:
        once["overchannel"] = n
    if _state(party, "hurl_left").get(i, 1) <= 0:
        once["hurl_through_hell"] = True
    if _state(party, "divine_left").get(i, 1) <= 0:
        once["divine_intervention"] = True
    if _state(party, "divine_wait").get(i):
        e["divine_wait"] = _state(party, "divine_wait")[i]
    spent = sorted(k[5:] for k, v in ((getattr(party, "ask_uses", None) or {}).get(i) or {}).items()
                   if k.startswith("free:") and v <= 0)
    if spent:
        once["free_casts"] = spent
    c = party.sim.by_id(i)
    if has(c, "signature_spells", SIGNATURE):                     # what a Short Rest gives back (short_rest)
        e["signature"] = [x["name"] for x in c.get("spell_list") or [] if x.get("free") and int(x.get("level") or 0) == 3]


def from_day(party, i, e):
    """apply_to_sim: the carried uses back into the fight."""
    once = e.get("once") or {}
    if once.get("overchannel"):
        _state(party, "overchannel_n")[i] = int(once["overchannel"])
    if once.get("hurl_through_hell"):
        _state(party, "hurl_left")[i] = 0
    if once.get("divine_intervention") or e.get("divine_wait"):
        _state(party, "divine_left")[i] = 0
    if e.get("divine_wait"):
        _state(party, "divine_wait")[i] = int(e["divine_wait"])
    for name in once.get("free_casts") or []:
        party.__dict__.setdefault("ask_uses", {}).setdefault(i, {})["free:" + name] = 0


def long_rest(e):
    """A Long Rest finished (rests._long_benefits, after "once" is cleared): Greater Divine Intervention's count."""
    if e.get("divine_wait"):
        e["divine_wait"] -= 1
        if e["divine_wait"] > 0:
            e["once"]["divine_intervention"] = True
        else:
            e.pop("divine_wait")


def short_rest(e):
    """A Short Rest finished: Signature Spells' casts come back (Magic Initiate's stay: once per Long Rest)."""
    once = e.get("once") or {}
    if once.get("free_casts"):
        sig = set(e.get("signature") or ())
        once["free_casts"] = [n for n in once["free_casts"] if n not in sig]
        if not once["free_casts"]:
            once.pop("free_casts")


def magical_cunning(e, eldritch_master):
    """Magical Cunning (Warlock 2; SRD 5.2.1), a 1-minute rite once per Long Rest: expended Pact Magic slots back, up to
    half the maximum (rounded up); Eldritch Master (Warlock 20): all of them. Returns how many came back."""
    pact = e.get("pact") or {}
    lv = int(pact.get("level") or 0)
    if not lv or lv > len(e["slots"]):
        return 0
    most = e["slots_max"][lv - 1]
    missing = most - e["slots"][lv - 1]
    back = missing if eldritch_master else min(missing, -(-most // 2))
    e["slots"][lv - 1] += back
    return back


def day_powers(b):
    """rests.entry_from_build: Magical Cunning (Warlock 2) and Eldritch Master (Warlock 20) for the day's rite."""
    out = {}
    if has(b, "magical_cunning", "Magical Cunning"):
        out["magical_cunning"] = True
        if has(b, "eldritch_master", "Eldritch Master"):
            out["eldritch_master"] = True
    return out
