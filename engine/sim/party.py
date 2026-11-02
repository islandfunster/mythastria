"""PARTY-01 (simulator, 2026-10-14): team tactics for the simulator's player characters (scenario script "team", or --party).

An optimized level-1 party (sim/parties/level1_team.json) plays as a team, not as four individuals:
  - focus fire: the party picks one foe (the one it can finish soonest, near the party) and keeps on it until it drops;
  - the Fighter guards the casters (a foe next to the Wizard or Cleric becomes his target);
  - the Rogue sets up Sneak Attack: a foe an ally is already next to, or one it has Advantage on (Vex, Guiding Bolt,
    unseen), with the Rapier in melee or the Shortbow from range;
  - the Cleric opens with Bless (Concentration) on the attackers, keeps one slot for Healing Word to bring a fallen
    ally back, and uses Guiding Bolt against a lone strong foe so the next attack (often the Rogue's) has Advantage;
  - the Wizard (Mage Armor cast before the day) uses Fire Bolt, spends her slot on Magic Missile only for a sure kill
    and otherwise keeps it for Shield (a Reaction when a hit would miss against AC + 5).
Rules from SRD 5.2.1 (see test_party.py). One Spell with a Spell Slot per Turn is kept. Death saves for every member.

PARTY-02 (simulator, 2026-10-14): the Barbarian, Paladin and Warlock of the SRD pregens (sim/parties/srd_pregens.json):
  - the Barbarian enters a Rage on its first turn with a foe in sight (Bonus Action: +2 damage with Strength attacks,
    Resistance to Bludgeoning, Piercing and Slashing), breathes fire (Breath Weapon, instead of its attack) when a
    15-ft Cone or 30-ft Line catches two or more foes and no ally, otherwise swings the Greataxe (Cleave: a second foe
    next to the first); from level 2 Reckless Attack while above half its hit points;
  - the Paladin uses Lay On Hands (Bonus Action) to bring a fallen ally back or on a Bloodied member (half its hit
    points or fewer), Bless when no one concentrates on it, the Longsword (Sap), and from level 2 Divine Smite on a
    Critical Hit or on the focus target;
  - the Warlock casts Hex on the focus target (Bonus Action, Concentration; moved when the target drops) and Eldritch
    Blast every turn from range (Agonizing Blast from level 2); Armor of Shadows keeps its AC at 14.

PARTY-03 (simulator, 2026-10-14): the Bard:
  - Bonus Action: Shillelagh when it is about to fight in melee and the spell is not running (1 minute), otherwise
    Bardic Inspiration on the ally who attacks most (Bless order) within 60 ft that has no die (SRD 5.2.1: one die at a
    time, uses = Charisma modifier). The holder rolls it after an attack roll misses, when the die can still turn the
    miss into a hit;
  - Action: Cure Wounds (touch, 2d8 + spellcasting modifier, a level 1 slot) on a fallen ally it can reach this turn;
    otherwise the melee weapon (Shillelagh) when it is a front-liner (`front_liner`) and the target is within its move
    and reach; otherwise Vicious Mockery when the target's Wisdom save is known and low (Wisdom save against the spell
    DC, 2d6 Psychic at level 5, Disadvantage on its next attack roll), else Starry Wisp (ranged spell attack, 60 ft).

PARTY-04 (simulator, 2026-10-15): the SRD pregens at levels 3-7 (srd_pregens.json `at_level`; sim/README.md lists what
is and is not modelled): Extra Attack (attack_action), Action Surge, Improved Critical, Steady Aim, Uncanny Dodge, Frenzy,
the Breath Weapon in place of one attack, Sacred Weapon, Aura of Protection, Potent Cantrip, Scorching Ray, Fireball
(never on an ally; Sculpt Spells), Spirit Guardians, Preserve Life, Disciple of Life, Mass Healing Word, Blessed Healer,
Sacred Flame, two Eldritch Blast beams, Dark One's Blessing; spell slots per slot level (init_slots / spend_slot).
REFEREE-01: every cast is wrapped in refereed(), so the rules referee (sim/referee.py) checks it once it has resolved.
"""
import contextlib, math
from character_rules import WEAPON_KEYS
import high_levels as high                                       # GM 2026-10-26: level 9-20 features (sim/high_levels.py)
import martial_high as martial                                   # MARTIAL-HIGH (GM 2026-10-28): sim/martial_high.py

FT = 5


def new_death_state():
    return {"successes": 0, "failures": 0, "stable": False, "dead": False}


def death_save(d20, st):
    """SRD 5.2.1 Death Saving Throws: 'success', 'failure', 'stable', 'dead' or 'revive' (a 20: regain 1 HP)."""
    if d20 == 20:
        st.update(new_death_state())
        return "revive"
    st["failures" if d20 < 10 else "successes"] += 2 if d20 == 1 else 1
    if st["failures"] >= 3:
        st["dead"] = True
        return "dead"
    if st["successes"] >= 3:
        st.update(successes=0, failures=0, stable=True)
        return "stable"
    return "success" if d20 >= 10 else "failure"


def damage_at_zero(st, crit, damage, hp_max):
    """Damage at 0 Hit Points: a failure (two on a Critical Hit); damage >= the HP maximum kills; ends Stable."""
    st["stable"] = False
    if damage >= hp_max:
        st["dead"] = True
        return "dead"
    st["failures"] += 2 if crit else 1
    if st["failures"] >= 3:
        st["dead"] = True
        return "dead"
    return "failure"


OWN_ADVANTAGE = ("Guiding Bolt", "Vex", "Innate Sorcery", "Studied Attacks")   # the attack's own log names them


def sneak_attack_ok(mode, ally_adjacent):
    return mode != "dis" and (mode == "adv" or ally_adjacent)


def combine(advs, diss):
    a, d = any(advs), any(diss)
    return "adv" if a and not d else "dis" if d and not a else ""


def concentration_dc(damage):
    return min(30, max(10, damage // 2))


def rage_damage(level):
    """SRD 5.2.1 Barbarian table, Rage Damage column."""
    return 2 if level < 9 else 3 if level < 16 else 4


def breath_dc(con_mod, pb):
    return 8 + con_mod + pb


def breath_dice(char_level):
    return "%dd10" % (1 + (char_level >= 5) + (char_level >= 11) + (char_level >= 17))


def save_for_half(damage, saved):
    return damage // 2 if saved else damage


# SIM-MECHANICS-01 (a), 2026-10-18: damage types for the attack cantrips and spells the builds carry as weapons (SRD 5.2.1
# spell descriptions), so the target's Resistance, Immunity and Vulnerability apply; a weapon names its own ("dmgtype")
SPELL_DAMAGE_TYPES = {"Fire Bolt": "fire", "Eldritch Blast": "force", "Scorching Ray": "fire", "Ray of Frost": "cold",
                      "Guiding Bolt": "radiant", "Sacred Flame": "radiant", "Magic Missile": "force",
                      "Vicious Mockery": "psychic", "Divine Smite": "radiant", "Hex": "necrotic", "Fireball": "fire"}


def damage_type(weapon):
    return str(weapon.get("dmgtype") or SPELL_DAMAGE_TYPES.get(weapon.get("name"), "")).lower()


# GM 2026-10-23 (the Sorcerer): the attack cantrips and spell attacks a sheet carries as a weapon; Innate Sorcery gives
# Advantage on them, and Metamagic can change them (sim/live_sorcery.py)
SPELL_ATTACKS = {"Fire Bolt", "Ray of Frost", "Chill Touch", "Shocking Grasp", "Eldritch Blast", "Sorcerous Burst",
                 "Produce Flame", "Starry Wisp", "Scorching Ray", "Guiding Bolt", "Chromatic Orb",
                 "Inflict Wounds", "Spiritual Weapon"}


def spell_attack(weapon):
    return bool(weapon.get("cantrip") or weapon.get("name") in SPELL_ATTACKS)


def ranged(weapon):
    """A ranged attack: a range beyond 10 ft (the sheet's ranged attacks; a Reach weapon's 10 ft is still melee)."""
    return weapon.get("reach", 5) > 10


def empowered_roll(rng, expr, n):
    """Empowered Spell (SRD 5.2.1 Metamagic): the damage dice rolled one by one, then up to n of them rolled again (the
    lowest ones, when they are below the die's average: the choice a player makes), the new rolls kept.
    Returns (total, the rolls before, the rolls after, how many were rolled again)."""
    dice, _, bonus = expr.partition("+")
    count, _, sides = dice.partition("d")
    sides = int(sides)
    rolls = [rng.randint(1, sides) for _ in range(int(count or 1))]
    before = list(rolls)
    again = [k for k in sorted(range(len(rolls)), key=lambda k: rolls[k])[:max(1, n)] if rolls[k] < (sides + 1) / 2]
    for k in again:
        rolls[k] = rng.randint(1, sides)
    return sum(rolls) + int(bonus or 0), before, rolls, len(again)


def _along_across(origin, toward, point):
    ux, uy = toward
    n = math.hypot(ux, uy) or 1.0
    dx, dy = point[0] - origin[0], point[1] - origin[1]
    return (dx * ux + dy * uy) / n, abs(dx * uy - dy * ux) / n


def in_cone(origin, toward, point, length):
    """A Cone as wide as it is long at its far end (feet; creature centers)."""
    along, across = _along_across(origin, toward, point)
    return 0 < along <= length + 0.01 and across <= along / 2 + 0.01


def in_line(origin, toward, point, length, width):
    along, across = _along_across(origin, toward, point)
    return 0 < along <= length + 0.01 and across * 2 < width


def smite_dice(slot_level, fiend_or_undead):
    return "%dd8" % (1 + slot_level + (1 if fiend_or_undead else 0))


def lay_on_hands_pool(level):
    return 5 * level


def bardic_die(level):
    """SRD 5.2.1 Bard: d6, d8 at level 5, d10 at 10, d12 at 15."""
    return 6 if level < 5 else 8 if level < 10 else 10 if level < 15 else 12


def cantrip_dice(level, die):
    """SRD 5.2.1 Cantrip Upgrade: one more die at character levels 5, 11 and 17."""
    return "%dd%d" % (1 + (level >= 5) + (level >= 11) + (level >= 17), die)


def inspiration_helps(total, target, sides):
    """Worth rolling the die: a miss that a roll of 1..sides could still turn into a success."""
    return total < target <= total + sides


# ---------------------------------------------------------------- PARTY-04: levels 3-7 (SRD 5.2.1 class tables)
def hit_points(die, level, con_mod):
    """The die's maximum + Con at level 1, then its average (d6 4, d8 5, d10 6, d12 7) + Con per level; a higher
    Constitution modifier counts for every level."""
    return die + con_mod + (level - 1) * (die // 2 + 1 + con_mod)


def proficiency_bonus(level):
    return 2 + (level - 1) // 4


FULL_CASTER_SLOTS = {1: [2], 2: [3], 3: [4, 2], 4: [4, 3], 5: [4, 3, 2], 6: [4, 3, 3], 7: [4, 3, 3, 1],
                     8: [4, 3, 3, 2], 9: [4, 3, 3, 3, 1]}
HALF_CASTER_SLOTS = {1: [2], 2: [2], 3: [3], 4: [3], 5: [4, 2], 6: [4, 2], 7: [4, 3], 8: [4, 3], 9: [4, 3, 2]}
PACT_SLOTS = {1: (1, 1), 2: (2, 1), 3: (2, 2), 4: (2, 2), 5: (2, 3), 6: (2, 3), 7: (2, 4), 8: (2, 4), 9: (2, 5)}


def spell_slots(kind, level):
    """Slots per slot level (index 0 = level 1): 'full' (Wizard, Cleric), 'half' (Paladin), 'pact' (Warlock)."""
    if kind == "pact":
        n, lv = PACT_SLOTS[level]
        return [0] * (lv - 1) + [n]
    return list((FULL_CASTER_SLOTS if kind == "full" else HALF_CASTER_SLOTS)[level])


def sneak_dice(level):
    return "%dd6" % ((level + 1) // 2)


def rages(level):
    """SRD 5.2.1 Barbarian table, Rages column."""
    return 2 if level < 3 else 3 if level < 6 else 4 if level < 12 else 5 if level < 17 else 6


def eldritch_beams(level):
    return 1 + (level >= 5) + (level >= 11) + (level >= 17)


def fireball_dice(slot_level):
    return "%dd6" % (8 + slot_level - 3)


def scorching_rays(slot_level):
    return 3 + slot_level - 2


def guardians_dice(slot_level):
    return "%dd8" % (3 + slot_level - 3)


def in_sphere(center, point, radius):
    """Feet; a creature counts when the center of its square is within the radius."""
    return math.hypot(point[0] - center[0], point[1] - center[1]) <= radius + 0.01


NUMBERS = {1: "one", 2: "two", 3: "three", 4: "four"}
BLESS_ORDER = ("fighter", "barbarian", "paladin", "rogue", "warlock", "cleric", "wizard")
GUARDED = ("wizard", "cleric", "warlock", "sorcerer")          # GM 2026-10-23: the Sorcerer too


def roll(rng, expr):
    """'2d4+3' -> total."""
    dice, _, bonus = expr.partition("+")
    n, _, sides = dice.partition("d")
    return sum(rng.randint(1, int(sides)) for _ in range(int(n or 1))) + int(bonus or 0)


def average_damage(expr):
    """'2d6+3' -> 10: one ordinary hit of this weapon on average (what a player expects it to do)."""
    dice, _, bonus = str(expr).partition("+")
    n, _, sides = dice.partition("d")
    return int(n or 1) * (int(sides or 0) + 1) // 2 + int(bonus or 0)


def speed_ft(c):
    if "_speed_now" in c:                                        # SIM-MECHANICS-01 (c): this turn's Speed (conditions)
        return c["_speed_now"]
    return int(str(c.get("speed", "30")).split()[0])


class Party:
    def __init__(self, sim):
        self.sim, self.s = sim, sim.S
        pcs = [c for c in sim.sc["combatants"] if c.get("pc")]
        self.slots, self.pools = {}, {}                  # PARTY-04: slots left in all, and per slot level
        for c in pcs:
            self.init_slots(c["id"], c.get("slots", 0))
        self.deaths = {c["id"]: new_death_state() for c in pcs}
        self.slot_turn = {}          # ctid -> turn serial a slot was spent (One Spell with a Spell Slot per Turn)
        self.blessed, self.concentrating = set(), None
        self.guided = {}             # foe id -> (caster, round cast)
        self.vexed = {}              # (attacker, foe) -> round
        self.shielded = set()
        self.focus = None
        # PARTY-02
        self.bonus_turn = {}         # ctid -> turn serial its Bonus Action was taken
        self.rages = {c["id"]: c.get("rages", 0) for c in pcs}
        self.raging, self.rage_kept = {}, {}   # ctid -> turn serial the Rage started / was last extended
        self.breaths = {c["id"]: c.get("breath", 0) for c in pcs}
        self.reckless, self.sapped = set(), {}
        self.loh = {c["id"]: c.get("lay_on_hands", 0) for c in pcs}
        self.free_smite = {c["id"]: bool(c.get("smite")) for c in pcs}
        self.hex = {}                # warlock -> cursed creature (None after it dropped) while concentrating
        # SIM-MECHANICS-01 (f), 2026-10-19
        self.faith = {}              # caster -> the creature its Shield of Faith protects (+2 AC: sim_ac_faith)
        self.spirit_weapon = {}      # cleric -> {"level": slot level, "at": (x, y) of the spectral force}
        self.control = {}            # caster -> {"spell": Sleep / Hideous Laughter / Hold Person, "targets": set}
        self.rebuke_free = {}        # Infernal Legacy: Hellish Rebuke once a day without a slot (False: used)
        self.seared = set()          # (paladin, target): Searing Smite used on it
        # PARTY-03
        self.inspiration = {}        # holder -> (bard, sides): one Bardic Inspiration die at a time
        self.bi_uses = {c["id"]: c.get("inspiration", 0) for c in pcs}
        self.shillelagh = {}         # bard -> round the spell ends (1 minute = 10 rounds)
        self.mocked = {}             # bard -> creatures with Vicious Mockery's Disadvantage
        # PARTY-04
        self.surges = {c["id"]: c.get("action_surge", 0) for c in pcs}
        self.channel = {c["id"]: c.get("channel", 0) for c in pcs}
        self.sacred = set()          # paladins whose Sacred Weapon is on (10 minutes: the whole fight)
        self.guardians = {}          # cleric -> slot level of its Spirit Guardians while concentrating
        self.guardian_saved = set()  # (creature, turn serial): Spirit Guardians' save, once per turn
        # SIM-MECHANICS-01 (a), GM 2026-10-18 ("ilsa should be able to tell if a creature is immune after one action"):
        # what the party has seen a kind of creature do with a damage type: (kind, type) -> immune/resistant/vulnerable
        self.known = {}
        self.bursts = {}             # GM 2026-10-18: kinds seen exploding at 0 HP -> burst range in feet
        self.actor = None            # the member whose turn it is (Dark One's Blessing: "when you reduce")
        self.turn_pos = {}           # member -> square at the start of its turn (Steady Aim: not moved)
        self.aura_ids = [c["id"] for c in pcs if c.get("aura")]
        # GM 2026-10-23 (the Sorcerer; sim/live_sorcery.py): Sorcery Points left, Innate Sorcery's uses and the last round
        # it lasts, the spell an Extended Spell keeps (Advantage on its Concentration saves), a Quickened Spell's turn
        self.sorcery = {c["id"]: c.get("sorcery_points", 0) for c in pcs}
        self.innate_left = {c["id"]: c.get("innate_sorcery", 0) for c in pcs}
        self.innate_until, self.extended, self.quickened_turn = {}, {}, {}
        for c in pcs:
            if c.get("class") == "wizard" and c.get("shield"):
                sim.say("tactic", "%s cast Mage Armor before the day (AC %d)" % (c["name"], c["ac"]))
            # GM 2026-10-23 (the test heroes to the full SRD 5.2.1): Fiendish Vigor (Warlock invocation): False Life
            # without a slot and without rolling (2d4 + 4: 12 Temporary Hit Points), cast before the fight
            if c.get("fiendish_vigor"):
                self.s.setField(c["id"], "sim_temp_hp", 12)
                sim.say("tactic", "%s cast False Life before the fight (Fiendish Vigor): 12 Temporary Hit Points" % c["name"])
            if c.get("deflect_attacks"):                         # MONK-01: Deflect Attacks (sim/monk.py)
                import monk
                self.s.deflectHit = lambda tid, src, total, kinds, ranged: monk.deflect_hit(self, tid, src, total, kinds, ranged)
            if c.get("gwf"):                                     # Great Weapon Fighting (a two-handed melee weapon)
                self.s.setField(c["id"], "sim_gwf", 1)
            if c.get("fiendish_resilience"):                     # group 3: Fiendish Resilience (Warlock 10)
                had = str(self.s.getValue(c["id"], "damageresistances", "") or "")
                self.s.setField(c["id"], "damageresistances", ", ".join(x for x in (had, c["fiendish_resilience"]) if x))
                sim.say("tactic", "%s: Fiendish Resilience, Resistance to %s damage" % (c["name"], c["fiendish_resilience"].title()))
            if high.elusive(c):                                  # group 3: Elusive (Rogue 18), read by the fight state
                self.s.setField(c["id"], "sim_elusive", 1)
            most = rages(c.get("level", 1)) if high.persistent(c) else 0
            if most and self.rages.get(c["id"], 0) < most:      # Persistent Rage: every use back on rolling Initiative
                self.rages[c["id"]] = most
                sim.say("tactic", "%s: Persistent Rage, all %d uses of Rage back as the fight starts" % (c["name"], most))
            high.superior_inspiration(self, c["id"], c)          # Bard 18 (GM 2026-10-28, "heroes 20"): two uses at least
            import epic_boons
            epic_boons.fight_start(self, c)                      # EPIC-BOONS-01: the Epic Boons' fields and hooks
        martial.setup(self, pcs)                                 # MARTIAL-HIGH: a missed attack's luck, Thief's Reflexes

    # ---------------------------------------------------------------- state
    def st(self, i):
        return self.s.state(i)

    def pos(self, i):
        st = self.st(i)
        return st[2], st[3]

    def hp_left(self, i):
        w, hp = self.st(i)[0], self.st(i)[1]
        return hp - w

    def down(self, i):
        return self.sim.down(i)

    def dist(self, a, b):
        """Feet from the edge of a's space to the edge of b's (2026-10-16: a Large creature measured centre to centre
        was never in a character's 5-foot reach; see Sim.gap)."""
        return self.sim.gap(a, b) * self.sim.sc.get("units", 5)

    def side(self, i):
        return self.sim.by_id(i).get("side")

    def foes(self, i):
        # GM 2026-10-24: a creature out of the fight (side "neutral": Indifferent, surrendered, fled) is nobody's foe
        return [o["id"] for o in self.sim.sc["combatants"] if o.get("side") not in (self.side(i), "neutral")
                and not self.down(o["id"]) and not high.gone(self, o["id"])]   # CASTER-HIGH: Hurl Through Hell

    def allies(self, i):
        return [o["id"] for o in self.sim.sc["combatants"] if o.get("side") == self.side(i) and o["id"] != i]

    def blocked(self, a, b):
        g = self.sim.sc.get("grid", 50)
        (ax, ay), (bx, by) = self.pos(a), self.pos(b)
        return bool(self.sim.wall_segs) and self.sim.map_walls.blocked((ax * g, ay * g), (bx * g, by * g), self.sim.wall_segs)

    def ally_next_to(self, tid, me):
        return any(not self.down(a) and self.dist(a, tid) <= FT for a in self.allies(me))

    def enemy_next_to(self, me):
        return any(self.dist(f, me) <= FT for f in self.foes(me))

    def init_slots(self, i, slots):
        """PARTY-04: `slots` is a count of level 1 slots (levels 1-2) or a list per slot level ([4, 3, 2])."""
        pool = list(slots) if isinstance(slots, list) else [int(slots or 0)]
        self.pools[i], self.slots[i] = pool, sum(pool)

    def slot_free(self, i, level=1):
        """A slot of `level` or higher left, and no slot spent this turn (One Spell with a Spell Slot per Turn)."""
        pool = self.pools.get(i) or [self.slots.get(i, 0)]
        return sum(pool[level - 1:]) > 0 and self.slot_turn.get(i) != self.s.turnSerial

    def slot_wanted(self, i, base):
        """GM 2026-10-28 ("also many spells like bless can be upcast"): the slot level the player chose (Cast at) for a
        spell of level `base`, while such a slot is left; else `base`."""
        want = (self.__dict__.get("upcast") or {}).get(i)
        pool = self.pools.get(i) or []
        return want if isinstance(want, int) and base < want <= len(pool) and pool[want - 1] > 0 else base

    def spend_slot(self, i, level=1, highest=False):
        """Spend the lowest slot of `level` or higher (highest=True: the highest one). Returns the slot level. A slot the
        player chose to upcast with (self.upcast, set by sim/live_spells.py) is spent instead, once."""
        level = self.slot_wanted(i, level)
        self.__dict__.get("upcast", {}).pop(i, None)
        free = high.take_free(self, i, level)                    # CASTER-HIGH: Spell Mastery, Signature Spells, Divine
        if free:                                                 # Intervention cast it without a slot
            return free
        pool = self.pools.setdefault(i, [self.slots.get(i, 0)])
        levels = [lv for lv in range(level, len(pool) + 1) if pool[lv - 1] > 0]
        lv = (max if highest else min)(levels) if levels else level
        if levels:
            pool[lv - 1] -= 1
        self.slots[i] -= 1
        self.slot_turn[i] = self.s.turnSerial
        if levels:                                               # EPIC-BOONS-01: Boon of Spell Recall (levels 1-4)
            import epic_boons
            epic_boons.spell_recall(self, i, lv)
            epic_boons._state(self, "acted")[i] = self.s.turnSerial
        return lv

    def top_slot(self, i):
        pool = self.pools.get(i) or [self.slots.get(i, 0)]
        return max([lv for lv in range(1, len(pool) + 1) if pool[lv - 1] > 0] or [0])

    def concentrates(self, i):
        """PARTY-04: what this member concentrates on (Bless, Hex, Spirit Guardians), or None."""
        if self.concentrating == i:
            return "Bless"
        if self.hex.get(i, False) is not False:
            return "Hex"
        if i in self.guardians:
            return "Spirit Guardians"
        if i in getattr(self, "faith", ()):                       # parties built without __init__ (tests) have none
            return "Shield of Faith"
        if i in getattr(self, "spirit_weapon", ()):
            return "Spiritual Weapon"
        if i in getattr(self, "control", ()):
            return self.control[i]["spell"]
        return getattr(self, "gm_concentration", {}).get(i)   # GM 2026-10-24: a spell the GM rules (sim/live_asks.py)

    def aura(self, i):
        """PARTY-04: Aura of Protection (Paladin 6): + the Paladin's Charisma modifier to saving throws within 10 ft,
        while the Paladin is not Incapacitated."""
        best = 0
        for p in getattr(self, "aura_ids", ()):
            if self.side(p) == self.side(i) and not self.incapacitated(p) and \
                    (p == i or self.dist(p, i) <= high.aura_ft(self.sim.by_id(p))):      # Aura Expansion: 30 ft
                best = max(best, self.sim.by_id(p)["aura"])
        return best

    def say(self, text):
        self.sim.say("tactic", text)

    def refereed(self, me, spell, cmd=None, effect=None):
        """REFEREE-01: the rules referee checks this cast once the with-block has resolved it (sim/referee.py watch);
        cmd: target / targets / x, y / free (a feature casts it without a slot); effect: origin, angle_deg, the chosen
        targets. Without a referee (a party built for a test) nothing is checked."""
        ref = getattr(self.sim, "referee", None)
        if ref is None:
            return contextlib.nullcontext({"cmd": dict(cmd or {}), "effect": dict(effect or {}), "notes": []})
        return ref.watch(me, spell, cmd, effect)

    def bonus_free(self, i):
        return self.bonus_turn.get(i) != self.s.turnSerial

    def use_bonus(self, i):
        self.bonus_turn[i] = self.s.turnSerial

    def name(self, i):
        return self.sim.by_id(i)["name"]

    def bless_targets(self, me, cands):
        """Bless: up to three creatures; the attackers first (Fighter, Barbarian, Paladin, Rogue, Warlock), the caster last."""
        def rank(i):
            cls = self.sim.by_id(i).get("class")
            return BLESS_ORDER.index(cls) if cls in BLESS_ORDER else 99
        return (sorted([i for i in cands if i != me], key=rank) + ([me] if me in cands else []))[:3]

    # ---------------------------------------------------------------- choosing
    def heard(self):
        """Foes that attacked or were attacked this round or last: not hidden (SRD 5.2.1 Hide), so the party knows
        their squares and can attack them unseen with Disadvantage (the creatures' own noise record, v0.7.93)."""
        return {p.rsplit(".", 1)[-1] for p in self.sim.recent_noise()}

    def located(self, me):
        """Foes the party can point at: seen by any member who is up (allies call out positions), or heard."""
        heard = self.heard()
        return [f for f in self.foes(me)
                if f in heard or any(self.sim.sees(p, f) for p in [me] + self.allies(me) if not self.down(p))]

    def pick_focus(self, me):
        seen = self.located(me)
        if self.focus in seen:
            return self.focus
        if not seen:
            return None
        party = [me] + [a for a in self.allies(me) if not self.down(a)]
        self.focus = min(seen, key=lambda f: (self.hp_left(f), min(self.dist(f, p) for p in party)))
        self.say("focus: the party concentrates on %s (%d HP left)" % (self.sim.by_id(self.focus)["name"], self.hp_left(self.focus)))
        return self.focus

    def nearest_seen(self, me):
        seen = [f for f in self.foes(me) if self.sim.sees(me, f)] or self.located(me)
        return min(seen, key=lambda f: self.dist(me, f)) if seen else None

    # ---------------------------------------------------------------- SIM-MECHANICS-01 (a): defenses seen
    def kind(self, tid):
        """A creature's kind: its name without the number ("Magmin 2" -> Magmin)."""
        return self.sim.by_id(tid)["name"].rstrip("0123456789").strip()

    def learn(self, tid, dmgtype, what):
        """A hit showed the party that this kind of creature is immune, resistant or vulnerable to a damage type; the
        whole party saw it, and the same kind is taken to share it."""
        if tid in self.foes_all() and (self.kind(tid), dmgtype) not in self.known:
            self.known[(self.kind(tid), dmgtype)] = what
            self.say("the party notes: %s is %s to %s" % (self.kind(tid), what, dmgtype))

    def foes_all(self):
        return {c["id"] for c in self.sim.sc["combatants"] if (c.get("side") or "") == "foe"}

    def wasted(self, tid, dmgtype):
        """The party has seen this kind of creature take no damage of this type."""
        return self.known.get((self.kind(tid), str(dmgtype).lower())) == "immune"

    def unwasted_attack(self, me, tid, c, weapon, sneak):
        """A computer-played character's other attacks: when the party has seen this kind of foe ignore the attack its tactics
        chose, the first of the same sort (a spell for a spell, a weapon for a weapon) that reaches it and can harm it,
        Sorcerous Burst in a type that can."""
        if c.get("live") or not self.wasted(tid, damage_type(weapon)) or not any(weapon is c.get(k) for k in WEAPON_KEYS):
            return weapon
        for w in (c.get(k) for k in WEAPON_KEYS):
            if not isinstance(w, dict) or not w.get("name") or spell_attack(w) != spell_attack(weapon) \
                    or self.dist(me, tid) > w.get("reach", 5) + 0.01 or (sneak and not (w.get("finesse") or ranged(w))):
                continue
            kind = next((k for k in w.get("dmg_choices") or [damage_type(w)] if not self.wasted(tid, k)), None)
            if kind:
                self.say("%s: %s won't harm %s, so %s (%s)" % (c["name"], weapon.get("name"), self.name(tid), w["name"], kind))
                return dict(w, dmgtype=kind)
        return weapon

    def useful_target(self, me, tid, weapon):
        """The target if the weapon's damage is not known to be wasted on it, else the nearest other foe the party has
        located that the weapon can harm (None when there is none)."""
        kind = damage_type(weapon)
        if tid is None or not self.wasted(tid, kind):
            return tid
        others = [f for f in self.located(me) if not self.wasted(f, kind)]
        alt = min(others, key=lambda f: self.dist(me, f)) if others else None
        if alt is not None:
            self.say("%s turns from %s (immune to %s) to %s" % (self.name(me), self.name(tid), kind, self.name(alt)))
        return alt

    # ---------------------------------------------------------------- acting
    def mode_parts(self, me, tid, weapon, spell=False, peek=False):
        """The Advantage and Disadvantage attack() adds to a roll, by name: sight, Guiding Bolt, Vex, Innate Sorcery,
        Studied Attacks, close-range Disadvantage. peek (HINTS-01 H5: the attack hint, no roll): Studied Attacks' Advantage
        is not used up. -> ([Advantage names], [Disadvantage names])."""
        base = self.sim.attack_mode_for(me, tid)
        advs = [n for n, on in (("unseen attacker", base == "adv"), ("Guiding Bolt", tid in self.guided),
                                ("Vex", (me, tid) in self.vexed),
                                ("Innate Sorcery", bool(self.innate_on(me)) and (spell or spell_attack(weapon))),
                                ("Studied Attacks", high.studied_adv(self, me, tid, peek))) if on]   # Fighter 13
        diss = [n for n, on in (("unseen target", base == "dis"),   # a ranged attack with an enemy within 5 ft
                                ("an enemy within 5 ft", ranged(weapon) and self.enemy_next_to(me))) if on]
        return advs, diss

    def final_mode(self, me, tid, weapon, mode, spell=False):
        """'adv', 'dis' or '': the mode the d20 is rolled with, this attack's own `mode` with the conditions' and
        effects' (FightState.roll_mode, asked without rolling: nothing used up). SRD 5.2.1 Sneak Attack: no Disadvantage
        on the roll, whatever gives it."""
        adv, dis, _, _, _ = self.s.roll_mode(me, tid, {"bADV": mode == "adv", "bDIS": mode == "dis",
                                                       "sRange": "R" if spell or ranged(weapon) else "M",
                                                       "sim_dmgtype": damage_type(weapon), "sim_spell": bool(spell)}, peek=True)
        return "adv" if adv and not dis else "dis" if dis and not adv else ""

    def attack(self, me, tid, weapon, extra_adv=(), spell=False, sneak=False, bonus_dice="", note="", retarget_grapple=True,
               brutal=False, mastery=None, stealth=False, devious=None, strikes=()):
        """One attack roll through the fake FG, with sight, Guiding Bolt, Vex, Bless and close-range Disadvantage.
        brutal: Brutal Strike (Barbarian 9; SRD 5.2.1): with Reckless Attack, any Advantage on this Strength attack is
        given up (not when it has Disadvantage); a hit deals 1d10 more of the weapon's type and Hamstring Blow (Speed
        -15 ft until the start of the Barbarian's next turn).
        GM 2026-10-26 (sim/high_levels.py): mastery, Tactical Master's Push, Sap or Slow in place of the weapon's own
        (the computer-played Fighter chooses it here); stealth, Supreme Sneak's Stealth Attack (Cunning Strike, one Sneak
        Attack die; the computer-played Rogue uses it whenever it is hidden); Studied Attacks, Radiant Strikes, Improved
        Brutal Strike and Empowered Evocation on their own. strikes: the Cunning Strike options a player chose (Rogue 5:
        trip, poison, withdraw; live_play checks them first)."""
        c = self.sim.by_id(me)
        weapon = self.unwasted_attack(me, tid, c, weapon, sneak)
        if mastery is None and not c.get("live") and not spell:
            mastery = high.choose_mastery(self, me, tid, c, weapon)
        gm = getattr(self.sim, "gm_rules", None)
        grappler = gm.by(me, "Grappled") if gm and gm.has(me, "Grappled") else None
        if retarget_grapple and grappler and grappler != tid and not self.down(grappler) and not self.blocked(me, grappler) \
                and self.dist(me, grappler) <= weapon.get("reach", 5) + 0.01:
            self.say("%s is Grappled: attacks %s instead" % (c["name"], self.name(grappler)))
            tid = grappler                                       # SIM-MECHANICS-01 (c): no Disadvantage against it
        if self.dist(me, tid) > weapon.get("reach", 5) + 0.01 or self.blocked(me, tid):
            return None
        advs, diss = self.mode_parts(me, tid, weapon, spell)
        mode = combine([bool(advs)] + list(extra_adv), [bool(diss)])
        brutal = brutal and mode != "dis" and not diss
        if brutal:
            mode = ""                                            # Brutal Strike: the Advantage given up
        notes = [n for n in advs if n in OWN_ADVANTAGE] + ([note] if note else [])
        if mastery:
            notes.append("Tactical Master: %s instead of %s" % (mastery, high.own_mastery(weapon) or "its mastery"))
        kind = damage_type(weapon)
        extra = [bonus_dice] if bonus_dice else []              # PARTY-02: Hex's 1d6 on a hit ("1d6:necrotic")
        if brutal:
            extra.append("%s:%s" % (high.brutal_dice(c), kind))
            notes.append("Brutal Strike (no Advantage; +%s and Hamstring Blow on a hit)" % high.brutal_dice(c))
        shining = high.radiant(c, weapon) if not spell else ""
        if shining:                                              # Radiant Strikes (Paladin 11)
            extra.append(shining)
            notes.append("Radiant Strikes (+1d8 Radiant)")
        coat_extra, coat_label = ("", "") if c.get("live") else self.coat_dice(me, weapon)   # live: live_play adds it
        if coat_extra:
            extra.append(coat_extra)
        if coat_label:
            notes.append(coat_label)
        trip, dev, poison = 0, None, False
        if sneak and c.get("sneak") and (weapon.get("finesse") or ranged(weapon)) \
                and sneak_attack_ok(self.final_mode(me, tid, weapon, mode, spell), self.ally_next_to(tid, me)):
            sneak_dice_now = c["sneak"]
            count, _, sides = str(sneak_dice_now).partition("d")
            # Supreme Sneak (Thief 9): Stealth Attack, one die; Improved Cunning Strike (11): Trip may come with it
            sly = int(count or 0) > 1 and not high.stealth_ok(self, me, c) and (stealth or not c.get("live"))
            # MARTIAL-HIGH: Devious Strikes (Rogue 14): Daze, Knock Out, Obscure (the player's choice; the computer's)
            room = (2 if c.get("improved_cunning_strike") else 1) - bool(sly)    # options left on this Sneak Attack
            dev = devious if c.get("live") else martial.choose_devious(self, me, tid, c, int(count or 0) - bool(sly))
            if dev not in martial.DEVIOUS or room < 1 or int(count or 0) <= martial.DEVIOUS[dev][1] + bool(sly):
                dev = None
            dev_dice = martial.DEVIOUS[dev][1] if dev else 0
            # play-test 2026-11-02: Trip costs a die, so a character played at the table never spends it unasked
            if c.get("cunning_strike") and not c.get("live") and room - bool(dev) > 0 and int(count or 0) > 1 + bool(sly) + dev_dice \
                    and self.trip_worth(me, tid):
                trip = int(c["cunning_strike"])
            if "trip" in strikes:
                trip = int(c["cunning_strike"])
            chosen = [martial.CUNNING[k][0] for k in strikes if k != "trip"]    # Poison, Withdraw
            forgone = bool(trip) + bool(sly) + dev_dice + len(chosen)
            poison = "poison" in strikes
            if forgone:
                sneak_dice_now = "%dd%s" % (int(count) - forgone, sides)
            if sly:
                high._state(self, "stealth_attack")[me] = self.s.turnSerial
            extra.append("%s:%s" % (sneak_dice_now, kind))      # Sneak Attack: the weapon's damage type
            high._state(self, "sneak_now")[me] = self.s.turnSerial   # MARTIAL-HIGH: Stroke of Luck on a missed one
            options = [n for n, on in (("Trip", trip), ("Stealth Attack", sly)) if on] + chosen + ([martial.DEVIOUS[dev][0]] if dev else [])
            notes.append("Sneak Attack" + (" (Cunning Strike: %s, %s forgone)" % (
                " and ".join(options), "one die" if forgone == 1 else "%d dice" % forgone) if options else ""))
        elif strikes:
            notes.append("Cunning Strike unused: no Sneak dice on this attack")
        if notes:
            self.say("%s: %s" % (c["name"], ", ".join(notes)))
        dice, _, bonus = weapon.get("dmg", "1d4").partition("+")
        self.guided.pop(tid, None)                              # the next attack roll against it used the Advantage
        with (self.refereed(me, weapon.get("name"), {"target": tid}) if spell else contextlib.nullcontext()):
            # Elemental Affinity (Draconic Sorcery 6): one damage roll of the spell (a ray that already hit took it)
            affinity = self.affinity(c, kind) if (spell or spell_attack(weapon)) and not weapon.get("_affinity_hit") else 0
            if affinity:
                self.say("%s: Elemental Affinity, +%d %s damage on a hit" % (c["name"], affinity, kind.capitalize()))
            evoke = high.empowered(c, weapon.get("name")) if (spell or spell_attack(weapon)) and not weapon.get("_affinity_hit") else 0
            if evoke:                                            # Empowered Evocation (Evoker 10): one damage roll
                self.say("%s: Empowered Evocation, +%d damage on a hit" % (c["name"], evoke))
                affinity += evoke
            res = self.s.pcAttack(me, tid, weapon.get("atk", 0), weapon.get("crit", 20), dice, int(bonus or 0) + affinity, mode,
                                  0 if mastery else weapon.get("graze", 0), 4 if me in self.blessed else 0, ";".join(extra), kind,
                                  spell or weapon.get("reach", 5) > 10, bool(spell))
            faces = list(getattr(self.s, "weaponFaces", ()))     # before anything else in the fight rolls
            self.sim.settle()
            if res in ("hit", "crit") and weapon.get("name") == "Sorcerous Burst":
                self.burst_dice(me, tid, c, kind, faces)
            if affinity and weapon.get("one_affinity") and res in ("hit", "crit"):   # (Empowered Evocation too)
                weapon["_affinity_hit"] = True                   # this cast's other rays roll without it
            if coat_label:
                self.coat_after(me, weapon, res, tid)            # GM 2026-10-23: the poison on the weapon
            if brutal and res in ("hit", "crit") and gm and not self.down(tid):     # Hamstring Blow
                gm.add(tid, "Slowed", "(%s's Hamstring Blow: Speed -15 ft until the start of its next turn)" % c["name"],
                       by=me, ft=15, ends=1)
            if res in ("hit", "crit") and weapon.get("vex") and not mastery and not self.down(tid):
                self.vexed[(me, tid)] = self.s.round()
            if res in ("hit", "crit") and mastery:
                high.apply_mastery(self, me, tid, mastery)          # Tactical Master (Fighter 9)
            if res == "miss" and not spell:
                high.studied_miss(self, me, tid)                    # Studied Attacks (Fighter 13)
            if trip and res in ("hit", "crit") and gm and not self.down(tid) and not gm.has(tid, "Prone") \
                    and not gm.condition_save(tid, "dex", trip, "Cunning Strike (Trip)"):
                gm.add(tid, "Prone", "(%s's Cunning Strike)" % c["name"], by=me)
            if dev and res in ("hit", "crit"):
                martial.devious_effect(self, me, tid, dev)          # MARTIAL-HIGH: Devious Strikes
            if poison and res in ("hit", "crit"):
                martial.poison_strike(self, me, tid)                # Cunning Strike (Rogue 5)
            if res == "miss" and weapon.get("potent") and not self.down(tid):
                half = roll(self.sim.rng, weapon.get("dmg", "1d4")) // 2   # PARTY-04: Potent Cantrip (Evoker 3)
                self.sim.say("dice", "Potent Cantrip: %s takes half the %s damage on the miss (%d)" % (
                    self.name(tid), weapon.get("name", "cantrip"), half))
                if half:
                    self.s.pcDamage(me, tid, "", half, False, kind)
                    self.sim.settle()
        return res

    # ---------------------------------------------------------------- GM 2026-10-23: a poisoned weapon and the bag
    def coat_on(self, me, weapon):
        """The poison coating this weapon now (sim/live_items.py coats it), or None: Basic Poison lasts 1 minute."""
        coat = getattr(self, "coated", {}).get(me)
        if not coat or coat["name"] != weapon.get("name"):
            return None
        if coat["until"] is not None and int(self.s.round()) > coat["until"]:
            self.coated.pop(me, None)
            return None
        return coat

    def coat_dice(self, me, weapon):
        """(extra damage dice, its name): Basic Poison's 1d4 Poison with Piercing or Slashing damage; an injury poison
        has no dice (its save comes after a wound)."""
        coat = self.coat_on(me, weapon)
        if not coat or damage_type(weapon) not in ("piercing", "slashing"):
            return "", ""
        return ("" if coat.get("poison") else "1d4:poison"), coat.get("label", "Basic Poison")

    def coat_after(self, me, weapon, res, tid):
        """After an attack with the coated weapon: an injury poison's save on a wound; ammunition spends a piece per
        shot; on a weapon the poison is gone once its damage is dealt."""
        coat = self.coat_on(me, weapon)
        if not coat:
            return
        if coat.get("poison") and res in ("hit", "crit") and tid is not None and not self.down(tid):
            import srd_poisons
            srd_poisons.apply(self.sim, me, tid, coat["poison"])
        if coat.get("pieces"):
            coat["pieces"] -= 1
            if coat["pieces"] <= 0:
                self.coated.pop(me, None)
                self.sim.say("dice", "%s's last poisoned piece of ammunition is spent" % self.name(me))
        elif res in ("hit", "crit"):
            self.coated.pop(me, None)
            self.sim.say("dice", "The %s on %s's %s is spent" % (coat.get("label", "Basic Poison"), self.name(me), coat["name"]))

    def bag(self, me):
        """The character's Market bag in a live fight (sim/requirements.py Bag), or its own "bag" lines; None without."""
        c = self.sim.by_id(me)
        market = getattr(getattr(self.sim, "live", None), "market", None)
        if market is None and not c.get("bag"):
            return None
        import requirements
        return requirements.Bag(c["name"], market, c.get("bag"))

    def bag_potion(self, me, c):
        """A computer-played hero at a third of its Hit Points or fewer drinks a Potion of Healing from its bag (a Bonus
        Action)."""
        if self.hp_left(me) > c["hp"] // 3 or not self.bonus_free(me):
            return False
        bag = self.bag(me)
        if bag is None:
            return False
        import live_items
        pid = next((p for p in live_items.POTIONS if bag.count(p)), None)
        if not pid:
            return False
        name, dice = live_items.POTIONS[pid]
        bag.take(pid, 1, "drunk in a fight")
        self.use_bonus(me)
        heal = roll(self.sim.rng, dice)
        self.s.heal(me, heal)
        self.sim.say("dice", "%s drinks a %s from the bag (Bonus Action): %s = %d HP" % (c["name"], name, dice, heal))
        return True

    def bag_coat(self, me, c):
        """At the end of its turn, with the Bonus Action still free and a foe in sight, a computer-played hero coats its
        Piercing or Slashing weapon with Basic Poison from its bag (the dearer SRD poisons stay the player's choice)."""
        if not self.bonus_free(me) or self.down(me) or getattr(self, "coated", {}).get(me):
            return False
        if not any(self.sim.sees(me, f) for f in self.foes(me)):
            return False
        bag = self.bag(me)
        if bag is None or not bag.count("poison-basic"):
            return False
        w = next((w for w in (c.get("weapon"), c.get("ranged")) if isinstance(w, dict) and w.get("name")
                  and not w.get("cantrip") and damage_type(w) in ("piercing", "slashing")), None)
        if not w:
            return False
        import live_items
        bag.take("poison-basic", 1, "on the %s in a fight" % w["name"])
        self.use_bonus(me)
        pieces = 3 if w["name"] in live_items.AMMO_WEAPONS else None
        self.__dict__.setdefault("coated", {})[me] = {"key": "weapon" if w is c.get("weapon") else "ranged", "name": w["name"],
                                                       "until": int(self.s.round()) + live_items.MINUTE - 1,
                                                       "pieces": pieces, "label": "Basic Poison"}
        self.sim.say("dice", "%s coats the %s with Basic Poison from the bag (Bonus Action): +1d4 Poison with its next "
                     "wound, for 1 minute" % (c["name"], w["name"]))
        return True

    def trip_worth(self, me, tid):
        """Cunning Strike (Rogue 5; SRD 5.2.1): Trip (one Sneak Attack die) when the target is Large or smaller, not
        Prone yet, and an ally stands next to it (Prone gives that ally's melee attacks Advantage)."""
        gm = getattr(self.sim, "gm_rules", None)
        return bool(gm) and self.sim.size_sq(tid) <= 2 and not gm.has(tid, "Prone") and \
            any(a != me and not self.down(a) and self.dist(a, tid) <= 5 for a in self.allies(me))

    def approach(self, me, tid, reach):
        if self.dist(me, tid) > reach + 0.01 or self.blocked(me, tid):
            self.sim.pc_advance(me, tid, reach)

    def turn(self, me):
        c = self.sim.by_id(me)
        if me in self.shielded:                                  # Shield lasts until the start of her turn
            self.shielded.discard(me); self.s.setField(me, "sim_ac_bonus", 0)
        self.turn_start(me)
        self.actor, self.turn_pos[me] = me, self.pos(me)
        gm = getattr(self.sim, "gm_rules", None)
        harpy = gm.pc_turn_start(me) if gm else None             # SIM-MECHANICS-01 (c): conditions
        if not self.down(me) and not (gm and gm.incapacitated(me)):
            self.drink_potion(me, c) or self.bag_potion(me, c)   # PARTY-ITEMS; GM 2026-10-23: the Market bag
        if self.down(me):
            pass                                                 # dropped by burning at the start of its turn
        elif gm and gm.extinguish_if_needed(me):                 # SIM-MECHANICS-01 (d): Burning
            self.say("%s puts out the fire: that is its action" % c["name"])
        elif harpy:                                                # Charmed by a Luring Song: Incapacitated, walks to it
            self.say("%s is Charmed and Incapacitated: walks toward %s" % (c["name"], self.name(harpy)))
            if self.dist(me, harpy) > 5:
                self.sim.pc_advance(me, harpy, 5)
        elif gm and gm.incapacitated(me):
            self.say("%s is Incapacitated: no action" % c["name"])
        elif gm and gm.break_free(me):                           # THREAT-02 step 2: a web holds it (its action)
            pass
        elif getattr(self.sim, "escape", None) and self.sim.escape.active and self.escape_turn(me, c):
            pass                                                 # SIM-ESC-02: escape choices used the turn
        else:
            role = c.get("class")
            getattr(self, "turn_" + role, self.turn_fighter)(me, c)
            import epic_boons                                    # EPIC-BOONS-01: Blink Steps, Merge with Shadows
            epic_boons.after_action(self, me, c)
            if role == "rogue" and c.get("level", 1) >= 2 and self.bonus_free(me) and not self.down(me) \
                    and self.try_hide(me):                       # SIM-ENV-03: Cunning Action, Hide
                self.use_bonus(me)
            if not (gm and gm.incapacitated(me)):
                self.bag_coat(me, c)                             # GM 2026-10-23: Basic Poison from the bag
        self.end_turn(me)
        if gm:
            gm.pc_turn_end(me)
        self.actor = None

    def drink_potion(self, me, c):
        """PARTY-ITEMS (tests only): a Potion of Healing (2d4 + 2, a Bonus Action in 2024) at a third of its hit points or
        fewer."""
        if c.get("potions", 0) <= 0 or self.hp_left(me) > c["hp"] // 3 or not self.bonus_free(me):
            return False
        self.use_bonus(me)
        c["potions"] -= 1
        heal = roll(self.sim.rng, "2d4+2")
        self.s.heal(me, heal)
        self.sim.say("dice", "%s drinks a Potion of Healing (Bonus Action): 2d4 + 2 = %d HP (%d left)" % (
            c["name"], heal, c["potions"]))
        return True

    def try_hide(self, me):
        """SIM-ENV-03: Hide when every enemy that could see this character has Three-Quarters Cover against it (or none
        sees it). True when hidden."""
        env, gm = getattr(self.sim, "env", None), getattr(self.sim, "gm_rules", None)
        c = self.sim.by_id(me)
        if not env or not gm or gm.has(me, "Invisible") or "stealth" not in c:
            return False
        for f in self.foes(me):
            if self.sim.sees(f, me) and env.cover(f, me) < 5:
                return False
        return gm.hide(me, c["stealth"], adv=bool(c.get("stealth_boots")), reliable=bool(c.get("reliable_talent")),
                       why=" (Cunning Action, Bonus Action)")

    # ---------------------------------------------------------------- SIM-ESC-02: the escape (Drowned Way test)
    def escape_turn(self, me, c):
        """The scripted choices in an escape (docs/development/DROWNED_WAY_TEST_DESIGN.md). True: the turn is used."""
        esc, env = self.sim.escape, self.sim.env
        if esc.status.get(me) != "inside":
            self.say("%s is out of the passage (%s)" % (c["name"], esc.status.get(me)))
            return True
        gm = self.sim.gm_rules
        if gm and gm.whelmed(me):                                # SIM-ESC-04: get out of the elemental (an action)
            gm.escape_grapple(me)
            return True
        held = [a for a in self.allies(me) if gm and gm.whelmed(a) and gm.ft_between(me, gm.by(a, "Grappled")) <= 5]
        if held:
            gm.pull_out(me, held[0])                             # pull a friend out (an action)
            return True
        if esc.separated(me) and ("separated", me) not in esc.flags:
            esc.flags.add(("separated", me))
            esc.note("%s is separated from the party (no ally in sight within 30 ft)" % c["name"])
        near = [f for f in self.foes(me) if self.dist(me, f) <= 5.01 and not esc.dormant(f)]
        if near and not esc.carried_by(me):
            spot, here = self.exit_point(me), self.pos(me)       # SIM-ESC-06: the way out in reach: break away
            if spot and max(abs(spot[0] - here[0]), abs(spot[1] - here[1])) * self.sim.sc.get("units", 5) <= speed_ft(c):
                self.say("%s breaks away for the way out (Opportunity Attacks allowed)" % c["name"])
                self.head_out(me)
                return True
            return False                                         # fight: the class turn
        g = esc.guardian
        if esc.cfg.get("fight_guardian") and g and esc.awake and not self.down(g) and not esc.carried_by(me):
            return False                                         # SIM-ESC-03 coverage: the party fights it
        if esc.carried_by(me):                                   # SIM-ESC-05: the action is a Dash (double movement)
            self.say("%s carries %s toward the way out (Dash)" % (c["name"], self.name(esc.carried_by(me))))
            c["_speed_now"] = 2 * speed_ft(c)
            self.head_out(me)
            return True
        down = [a for a in self.allies(me) if self.down(a) and esc.status.get(a) == "inside"
                and not self.deaths.get(a, {}).get("dead") and a not in esc.carrying.values() and self.dist(me, a) <= 35]
        if down:
            a = min(down, key=lambda a: self.dist(me, a))
            if self.dist(me, a) > 5.01:
                self.sim.pc_advance(me, a, 5)
            if self.dist(me, a) <= 5.01:
                esc.pick_up(me, a)
            return True
        if self.needs_air(me):
            return True
        if self.sluice_turn(me, c):
            return True
        if self.lever_turn(me, c):
            return True
        self.head_out(me)
        return True

    def exit_point(self, me):
        """The nearest square of the way out: an exit zone, or a sluice channel."""
        esc = self.sim.escape
        squares = [(x, y) for z in esc.zones("exit") + esc.zones("channel")
                   for x in range(z["rect"][0], z["rect"][2] + 1) for y in range(z["rect"][1], z["rect"][3] + 1)]
        if not squares:
            return None
        here = self.pos(me)
        free = [s for s in squares if not self.sim.env.square_taken(me, s[0], s[1])] or squares
        return min(free, key=lambda s: max(abs(s[0] - here[0]), abs(s[1] - here[1])))

    def head_out(self, me):
        spot = self.exit_point(me)
        if spot:
            self.sim.pc_move_toward(me, spot[0], spot[1])

    def needs_air(self, me):
        """Breath left would not last to the way out (plus two rounds): the nearest working air station, or repair the
        damaged one it stands in."""
        esc, env = self.sim.escape, self.sim.env
        if env.breathes(me) or not env.of_kind("water"):
            return False
        spot = self.exit_point(me)
        here = self.pos(me)
        speed = max(5, env.speed(me, speed_ft(self.sim.by_id(me))))
        rounds_out = (max(abs(spot[0] - here[0]), abs(spot[1] - here[1])) * 5 / speed) if spot else 99
        left = env.breath.get(me, env.max_breath(me))
        if left > rounds_out + 2 or not env.of_kind("air"):
            return False
        for z in env.of_kind("air"):
            if env.inside(z, here):
                if z.get("state", "working") != "working":
                    esc.repair(me, z["id"])
                else:
                    self.say("%s breathes in the air pocket %s" % (self.name(me), z["id"]))
                return True
        stations = sorted(env.of_kind("air"), key=lambda z: (z.get("state", "working") != "working",
                          max(abs((z["rect"][0] + z["rect"][2]) / 2 - here[0]), abs((z["rect"][1] + z["rect"][3]) / 2 - here[1]))))
        z = stations[0]
        target = min(((x, y) for x in range(z["rect"][0], z["rect"][2] + 1) for y in range(z["rect"][1], z["rect"][3] + 1)
                      if not env.square_taken(me, x, y)), key=lambda s: max(abs(s[0] - here[0]), abs(s[1] - here[1])),
                     default=None)
        if target:
            self.say("%s is running out of breath (%d rounds): heads for the air station %s" % (self.name(me), left, z["id"]))
            self.sim.pc_move_toward(me, target[0], target[1])
        return True

    def lever_turn(self, me, c):
        """A running current between it and the way out that it cannot swim: work the lever (or go to it). A strong
        swimmer (Swim Speed 30+) does not need it."""
        esc, env = self.sim.escape, self.sim.env
        if env.swim_speed(me) >= 30:
            return False
        here, spot = self.pos(me), self.exit_point(me)
        for z in esc.zones("lever"):
            cur = esc.zone(z.get("current")) if z.get("current") else None
            if z.get("done") or cur is None or not cur.get("on", True) or not spot:
                continue
            x1, x2 = cur["rect"][0], cur["rect"][2]
            if not (min(here[0], spot[0]) <= x2 and max(here[0], spot[0]) >= x1):
                continue                                         # the current is not on its way
            rails = esc.zones("rail")
            if rails and z.get("fails", 0) >= 2:                 # SIM-ESC-03: the lever jammed twice: the chains
                r = rails[0]
                end = (r["rect"][2] + 1, r["rect"][1]) if here[0] <= r["rect"][2] else spot
                if not env.zone_at(here, "rail") and here[0] < r["rect"][0]:
                    end = (r["rect"][0], r["rect"][1])
                self.say("%s takes the guide chains across the %s" % (c["name"], cur["id"]))
                self.sim.pc_move_toward(me, end[0], end[1])
                return True
            lx, ly = z["rect"][0], z["rect"][1]
            if max(abs(here[0] - lx), abs(here[1] - ly)) <= 1:
                esc.operate(me, z["id"])
            else:
                self.say("%s cannot swim the current %s: goes to the lever %s" % (c["name"], cur["id"], z["id"]))
                self.sim.pc_move_toward(me, lx, ly + 1)
            return True
        return False

    def operator(self):
        """Who works the sluice: the nearest character inside who is up and not carrying anyone."""
        esc = self.sim.escape
        z = (esc.zones("sluice_lever") or [None])[0]
        if not z:
            return None
        lx, ly = z["rect"][0], z["rect"][1]
        cands = [i for i, s in esc.status.items() if s == "inside" and not self.down(i) and not esc.carried_by(i)]
        if not cands:
            return None
        return min(cands, key=lambda i: (max(abs(self.pos(i)[0] - lx), abs(self.pos(i)[1] - ly)), i))

    def sluice_turn(self, me, c):
        """The last chamber: wait in the channel; the nearest character works the sluice and goes in last."""
        esc = self.sim.escape
        levers = esc.zones("sluice_lever")
        if not levers:
            return False
        z = levers[0]
        chan = esc.zone(z.get("channel"))
        if any(s in ("escaped", "rescued") for s in esc.status.values()):
            if not esc.inside(chan, me):
                self.head_out(me)
            else:
                self.say("%s waits in the channel for the outer winch" % c["name"])
            return True
        inside = [i for i, s in esc.status.items() if s == "inside" and not self.down(i)]
        lx, ly = z["rect"][0], z["rect"][1]
        operator = self.operator()
        if me != operator:
            if not esc.inside(chan, me):
                self.head_out(me)
            else:
                self.say("%s waits in the channel" % c["name"])
            return True
        here = self.pos(me)
        if max(abs(here[0] - lx), abs(here[1] - ly)) <= 1:
            others = [i for i in inside if i != me]
            ready = [i for i in others if esc.inside(chan, i)]
            held = esc.held.get(me, 0)
            # SIM-ESC-05: wait for everyone up (carriers too); after 3 rounds held, send whoever is in the channel
            if not others or len(ready) == len(others) or (ready and held >= 3):
                esc.run_sluice(me, z["id"])
            else:
                esc.held[me] = held + 1
                self.say("%s holds the sluice lever until the others reach the channel" % c["name"])
        else:
            self.sim.pc_move_toward(me, lx, ly + 1)
        return True

    def incapacitated(self, i):
        """At 0 HP or Incapacitated (SIM-MECHANICS-01 c): no Reaction, no Concentration, no aura."""
        gm = getattr(self.sim, "gm_rules", None)
        return self.down(i) or bool(gm and gm.incapacitated(i))

    def start_concentration(self, me, spell):
        """SIM-MECHANICS-01 (e): starting a Concentration spell ends the one this member holds (SRD 5.2.1 Concentration).
        The caller then records the new spell (blessed/concentrating, hex, guardians)."""
        held = self.concentrates(me)
        getattr(self, "extended", {}).pop(me, None)              # an Extended Spell's Advantage ends with its spell
        if held:
            self.sim.say("dice", "%s ends its Concentration on %s to cast %s" % (self.sim.by_id(me)["name"], held, spell))
            self.end_concentration(me)

    def drop_concentration(self, me, why):
        """SRD 5.2.1: "The creator can end Concentration at any time (no action required)." Returns the spells ended.
        The scripted party only needs it as part of starting another Concentration spell (start_concentration)."""
        ended = self.end_concentration(me)
        if ended:
            self.sim.say("dice", "%s ends its Concentration on %s (no action: %s)" % (
                self.sim.by_id(me)["name"], ", ".join(ended), why))
        return ended

    def end_concentration(self, tid):
        """Drop whatever this member concentrates on, silently; returns the spell names ended."""
        out = []
        held = getattr(self, "gm_concentration", {}).pop(tid, None)
        if held:
            out.append(held)
        if self.concentrating == tid:
            self.blessed, self.concentrating = set(), None
            out.append("Bless")
        if tid in self.hex:
            self.hex.pop(tid)
            out.append("Hex")
        if tid in self.guardians:
            self.guardians.pop(tid)
            out.append("Spirit Guardians")
        if tid in getattr(self, "faith", ()):
            self.s.setField(self.faith.pop(tid), "sim_ac_faith", 0)
            out.append("Shield of Faith")
        if tid in getattr(self, "spirit_weapon", ()):
            self.spirit_weapon.pop(tid)
            out.append("Spiritual Weapon")
        if tid in getattr(self, "control", ()):
            out.append(self.control.pop(tid)["spell"])
            gm = getattr(self.sim, "gm_rules", None)
            if gm:
                gm.end_spell(tid, "%s's Concentration ends" % self.sim.by_id(tid)["name"], spell=out[-1])
        if out and getattr(self.sim, "_delayed_blast", None):    # group 2: the bead explodes when its spell ends
            import more_spells
            more_spells.concentration_ended(self.sim, tid, out)
        layers = getattr(self.sim, "layers", None)
        if out and layers is not None and getattr(self.sim, "_spell_zones", None):
            layers.sweep()                                       # SPELL-EFFECTS-01: its zone (Web, Entangle) ends now
        return out

    def lose_concentration(self, tid, why):
        """SIM-MECHANICS-01 (c): Incapacitated breaks Concentration (Bless, Hex, Spirit Guardians); (e): so does
        dying (SRD 5.2.1 Concentration: "Incapacitated or Dead")."""
        c = self.sim.by_id(tid)
        for spell in self.end_concentration(tid):
            self.sim.say("dice", "%s is %s: Concentration ends, %s ends" % (c["name"], why, spell))

    def turn_start(self, me):
        """PARTY-02: effects that last until the start of this member's next turn (also when it is at 0 HP)."""
        if me in self.reckless:                                  # Reckless Attack
            self.reckless.discard(me); self.s.setField(me, "sim_reckless", 0)
        for tid in self.sapped.pop(me, ()):                      # Sap: before the start of the Paladin's next turn
            self.s.setField(tid, "sim_sapped", 0)
        for tid in self.mocked.pop(me, ()):                      # Vicious Mockery: its next turn is over by now
            self.s.setField(tid, "sim_mocked", 0)
        if self.sim.by_id(me).get("uncanny_dodge"):              # PARTY-04: an unused Uncanny Dodge does not carry over
            self.s.setField(me, "sim_halve_next", 0)
        high.turn_start(self, me)                                # GM 2026-10-26: Slow, Studied Attacks, Heroic Rally
        martial.turn_start(self, me)                             # MARTIAL-HIGH: Heroic Warrior, Smite of Protection
        import monk
        monk.turn_start(self, me)                                # MONK-01: Stunning Strike's marks, Patient Defense
        import epic_boons
        epic_boons.turn_start(self, me)                          # EPIC-BOONS-01: Peerless Aim comes back

    def end_turn(self, me):
        high.end_turn(self, me)                                  # GM 2026-10-26: Supreme Sneak's cover check
        rnd = self.s.round()
        for tid, (caster, r) in list(self.guided.items()):
            if caster == me and r < rnd:
                self.guided.pop(tid)
        for key, r in list(self.vexed.items()):
            if key[0] == me and r < rnd:
                self.vexed.pop(key)
        if self.focus and self.down(self.focus):
            self.focus = None
        serial = self.s.turnSerial
        if me in self.raging and self.raging[me] != serial and self.rage_kept.get(me) != serial and                 not high.persistent(self.sim.by_id(me)):                # group 3: Persistent Rage needs no extending
            if self.bonus_free(me) and self.foes(me):
                self.use_bonus(me); self.rage_kept[me] = serial
                self.sim.say("dice", "%s extends the Rage (Bonus Action)" % self.name(me))
            else:
                self.end_rage(me, "no attack, no saving throw forced, no Bonus Action")

    def front_target(self, me, c):
        """The Fighter's choice: a foe next to a caster, else the party's focus, else the nearest foe in sight."""
        guard = [f for f in self.foes(me) for a in self.allies(me)
                 if self.sim.by_id(a).get("class") in GUARDED and not self.down(a) and self.dist(f, a) <= FT]
        if guard:
            self.say("%s moves to guard %s" % (c["name"], ", ".join(self.name(a) for a in self.allies(me)
                     if self.dist(guard[0], a) <= FT and self.sim.by_id(a).get("class") in GUARDED)))
            return guard[0]
        return self.pick_focus(me) or self.nearest_seen(me)

    def saw_burst(self, tid, feet):
        """GM 2026-10-18: the party saw this kind of creature explode when it dropped (Death Burst)."""
        kind = self.kind(tid)
        if kind not in self.bursts:
            self.bursts[kind] = feet
            self.say("the party notes: %s explodes when it drops (%d ft)" % (kind, feet))

    def burst_risky(self, me, tid, weapon, at=None):
        """Finishing this foe with this hit would catch the attacker in a burst the party has seen: its kind explodes,
        an average hit would drop it, and the attacker stands (or will stand) within the burst range."""
        feet = self.bursts.get(self.kind(tid))
        if feet is None or self.hp_left(tid) > average_damage(weapon.get("dmg", "1d4")):
            return False
        return (self.dist(me, tid) if at is None else at) <= feet + 0.01

    def burst_safe(self, me, tid, weapon, reach_now=False):
        """GM 2026-10-18 ("melee characters should avoid finishing that kind of creature while standing in its burst
        range when they can"): another foe this hit cannot turn into a burst on us, the nearest one this turn's move
        (or only the current reach) can get to; else the chosen foe."""
        if not self.burst_risky(me, tid, weapon, at=weapon.get("reach", 5)):
            return tid
        limit = weapon.get("reach", 5) + (0 if reach_now else speed_ft(self.sim.by_id(me))) + 0.01
        others = [f for f in self.foes(me) if f != tid and self.dist(me, f) <= limit and not self.blocked(me, f)
                  and not self.burst_risky(me, f, weapon, at=weapon.get("reach", 5))]
        if not others:
            return tid
        alt = min(others, key=lambda f: (self.dist(me, f), self.hp_left(f)))
        self.say("%s leaves %s (it would burst on %s) for %s" % (self.name(me), self.name(tid), self.name(me), self.name(alt)))
        return alt

    def shove_spot(self, me, tid):
        """SIM-ENV-02: where a Shove pushes this foe (one square straight away from us) when that square is a drop it
        would fall into: (x, y), or None."""
        env = getattr(self.sim, "env", None)
        c, t = self.sim.by_id(me), self.sim.by_id(tid)
        if not env or "str_score" not in c or self.dist(me, tid) > 5.01 or self.down(tid) or env.can_fly_now(tid):
            return None
        sizes = ["tiny", "small", "medium", "large", "huge", "gargantuan"]
        def rank(x):
            s = str(x.get("size") or "").lower()
            return sizes.index(s) if s in sizes else {5: 2, 10: 3, 15: 4}.get(int(x.get("space") or 5), 2)
        if rank(t) > rank(c) + 1:
            return None
        (mx, my), (tx, ty) = self.pos(me), self.pos(tid)
        px, py = tx + (tx > mx) - (tx < mx), ty + (ty > my) - (ty < my)
        here, there = env.drop_at((tx, ty)), env.drop_at((px, py))
        if not there or there is here or env.square_taken(tid, px, py) or env.walled((tx, ty), (px, py)):
            return None
        return px, py

    def try_shove(self, me, tid):
        """SIM-ENV-02: Shove (an Unarmed Strike option, one attack of the Attack action) when it pushes the foe off a
        ledge: the foe saves with Strength or Dexterity (the better) against 8 + Strength modifier + Proficiency Bonus.
        True when the attempt was made (it used the attack)."""
        spot = self.shove_spot(me, tid)
        if not spot:
            return False
        c, t = self.sim.by_id(me), self.sim.by_id(tid)
        dc = 8 + (c["str_score"] - 10) // 2 + (2 if (c.get("level") or 1) <= 4 else 3)
        ability, bonus = max((("Strength", t.get("str_save", 0)), ("Dexterity", t.get("dex_save", 0))), key=lambda a: a[1])
        d20 = self.sim.rng.randint(1, 20)
        ok = d20 + bonus >= dc
        self.sim.say("dice", "%s Shoves %s toward the drop (Unarmed Strike): %s save d20 %d %+d = %d vs DC %d -> %s" % (
            c["name"], t["name"], ability, d20, bonus, d20 + bonus, dc, "holds its ground" if ok else "pushed 5 ft"))
        if not ok:
            self.sim.env.forced_move(tid, spot[0], spot[1], "shoved off the ledge by %s" % c["name"])
            self.sim.settle(0.2)
        return True

    def melee(self, me, tid, weapon, move=True, **kw):
        """Close in (once a turn) and attack; a foe already next to us when the chosen one cannot be reached.
        Returns (target, result)."""
        tid = self.burst_safe(me, tid, weapon, reach_now=not move)
        if move:
            self.approach(me, tid, 5)
        if self.try_shove(me, tid):                              # SIM-ENV-02: off the ledge instead of a hit
            return tid, "shove"
        res = self.attack(me, tid, weapon, **kw)
        if res is None:
            near = [f for f in self.foes(me) if self.dist(me, f) <= FT and not self.blocked(me, f)]
            if near:
                tid = near[0]
                res = self.attack(me, tid, weapon, **kw)
        return tid, res

    def attack_action(self, me, c, tid, weapon, move=True, kw_for=None, rider=None):
        """PARTY-04: the Attack action: `attacks` attacks (Extra Attack from level 5). The move comes before the first
        attack; a later one goes to the same foe while it is up and in reach, else to another foe already in reach (no
        movement between attacks). weapon(k) / kw_for(k): the k-th attack's weapon and attack() options; rider(target,
        result) runs after each attack (Sap, Divine Smite, Cleave). Returns [(target, result)]."""
        out = []
        for k in range(c.get("attacks", 1)):
            w, kw = weapon(k), (kw_for(k) if kw_for else {})
            if k == 0 and not self.down(tid):
                tid, res = self.melee(me, tid, w, move=move, **kw)
            else:
                reach = w.get("reach", 5) + 0.01
                if self.down(tid) or self.dist(me, tid) > reach or self.blocked(me, tid):
                    near = [f for f in self.foes(me) if self.dist(me, f) <= reach and not self.blocked(me, f)]
                    if not near:
                        break
                    tid = min(near, key=lambda f: (f != self.focus, self.hp_left(f)))
                tid = self.burst_safe(me, tid, w, reach_now=True)
                res = "shove" if self.try_shove(me, tid) else self.attack(me, tid, w, **kw)
            if res is None:
                break
            out.append((tid, res))
            if rider:
                rider(tid, res)
        return out

    def surge_worth(self, me):
        """Action Surge on the turn a foe in reach is the toughest one left (the leader), or three or more foes remain."""
        foes = self.foes(me)
        near = [f for f in foes if self.dist(me, f) <= FT and not self.blocked(me, f)]
        if not near:
            return False
        toughest = max(foes, key=lambda f: self.sim.by_id(f).get("hp", 0))
        return toughest in near or len(foes) >= 3

    def turn_monk(self, me, c):
        import monk                                              # MONK-01 (GM 2026-10-28, "Monk as SRD")
        monk.turn(self, me, c)

    def turn_fighter(self, me, c):
        tid = self.front_target(me, c)
        if tid is None:
            self.say(c["name"] + " sees no foe and holds position"); return
        done = self.attack_action(me, c, tid, lambda k: c["weapon"])
        if done and self.surges.get(me) and self.surge_worth(me):   # PARTY-04: Action Surge (Fighter 2)
            self.surges[me] -= 1
            self.sim.say("dice", "%s uses Action Surge: one more action (Attack)" % c["name"])
            self.attack_action(me, c, done[-1][0], lambda k: c["weapon"], move=False)

    # ---------------------------------------------------------------- PARTY-02: Barbarian
    def end_rage(self, me, why):
        if self.raging.pop(me, None) is not None:
            self.s.setField(me, "sim_resist_bps", 0)
            self.sim.say("dice", "%s's Rage ends (%s)" % (self.name(me), why))

    def rage_weapon(self, me, c, w, cleave=False):
        """The weapon with Rage Damage on a Strength attack; Cleave's damage leaves out the ability modifier."""
        dice, _, bonus = w["dmg"].partition("+")
        add = (0 if cleave else int(bonus or 0)) + (
            c.get("rage_damage", rage_damage(c.get("level", 1))) if me in self.raging and w.get("str") else 0)
        return dict(w, dmg=dice + ("+%d" % add if add else ""), graze=0 if cleave else w.get("graze", 0))

    def breath_area(self, me, at=None):
        """The best 15-ft Cone or 30-ft Line (5 ft wide) from the breather: (shape, foes caught), never catching an ally."""
        # SRD 5.2.1: a Cone or Line extends from a point of origin (not itself in the area) in a direction its creator
        # chooses; here the origin is a corner or edge midpoint of the breather's square, and a creature counts when the
        # center of its square is in the area
        # (at: evaluate it from another square, for choosing where to step first)
        u, g = self.sim.sc.get("units", 5), self.sim.sc.get("grid", 50)
        here = at or self.pos(me)
        feet = lambda p: (p[0] * u, p[1] * u)
        cx, cy = feet(here)
        segs = self.sim.wall_segs
        kind = self.sim.by_id(me).get("breath_type", "fire")   # SIM-MECHANICS-01 (a): not the kinds seen ignoring it
        foes = [(f, feet(self.pos(f))) for f in self.foes(me) if not self.wasted(f, kind)
                and max(abs(self.pos(f)[0] - here[0]), abs(self.pos(f)[1] - here[1])) * u <= 30
                and not (segs and self.sim.map_walls.blocked((here[0] * g, here[1] * g),
                                                             (self.pos(f)[0] * g, self.pos(f)[1] * g), segs))]
        if len(foes) < 2:
            return (None, [])
        friends = [feet(self.pos(a)) for a in self.allies(me) if not self.deaths.get(a, {}).get("dead")]
        best = (None, [])
        for ox, oy in [(x, y) for x in (-2.5, 0, 2.5) for y in (-2.5, 0, 2.5) if (x, y) != (0, 0)]:
            o = (cx + ox, cy + oy)
            aims = [(q[0] - o[0], q[1] - o[1]) for _, q in foes]
            aims += [(a[0] / (math.hypot(*a) or 1) + b[0] / (math.hypot(*b) or 1),
                      a[1] / (math.hypot(*a) or 1) + b[1] / (math.hypot(*b) or 1)) for i, a in enumerate(aims) for b in aims[i + 1:]]
            for toward in aims:
                if toward[0] * ox + toward[1] * oy <= 0:
                    continue                                  # breathed outward, away from its own square
                for shape, inside in (("15-ft Cone", lambda q: in_cone(o, toward, q, 15)),
                                      ("30-ft Line", lambda q: in_line(o, toward, q, 30, 5))):
                    hit = [f for f, q in foes if inside(q)]
                    if len(hit) > len(best[1]) and not any(inside(q) for q in friends):
                        best = (shape, hit)
        return best

    def breath_spot(self, me, c):
        """A free square within this turn's move from which the Breath Weapon catches two or more foes (and no ally);
        not taken while a foe is next to the barbarian (leaving would provoke an Opportunity Attack)."""
        if not self.breaths.get(me) or self.enemy_next_to(me):
            return None
        u = self.sim.sc.get("units", 5)
        steps = int(str(c.get("speed", "30")).split()[0]) // u
        x0, y0 = self.pos(me)
        taken = {self.pos(o["id"]) for o in self.sim.sc["combatants"] if not self.down(o["id"])}
        near = [f for f in self.foes(me) if self.dist(me, f) <= (steps * u) + 30]
        if len(near) < 2:
            return None
        best = None
        for dx in range(-steps, steps + 1):
            for dy in range(-steps, steps + 1):
                spot = (x0 + dx, y0 + dy)
                if spot in taken or (dx, dy) == (0, 0):
                    continue
                n = len(self.breath_area(me, spot)[1])
                if n >= 2 and (best is None or (n, -max(abs(dx), abs(dy))) > best[0]):
                    best = ((n, -max(abs(dx), abs(dy))), spot)
        return best and best[1]

    def breathe(self, me, c):
        """Breath Weapon in place of the attack when two or more foes are in the area."""
        if not self.breaths.get(me):
            return False
        shape, hit = self.breath_area(me)
        if len(hit) < 2:
            return False
        self.breaths[me] -= 1
        dice = c.get("breath_dice", breath_dice(c.get("level", 1)))
        dmg, dc, kind = roll(self.sim.rng, dice), c.get("breath_dc", 12), c.get("breath_type", "fire")
        self.sim.say("dice", "%s uses Breath Weapon (%s, %s, in place of the attack): DC %d Dexterity save, %s = %d (%d uses left)" % (
            c["name"], shape, kind, dc, dice, dmg, self.breaths[me]))
        for f in hit:
            self.save_damage(me, f, "Dexterity", "dex_save", dc, dmg, kind)
        self.rage_kept[me] = self.s.turnSerial                  # forcing a saving throw extends the Rage
        return True

    def rage_started(self, me, c):
        """Mindless Rage (Berserker 6; SRD 5.2.1): a Charmed or Frightened condition on the Barbarian ends when the Rage
        starts (and gm_rules keeps both off while it lasts). Also called by Play live's Rage."""
        gm = getattr(self.sim, "gm_rules", None)
        if gm and c.get("mindless_rage"):
            for n in ("Charmed", "Frightened"):
                if gm.has(me, n):
                    gm.remove(me, n, "Mindless Rage")

    def pounce(self, me, c, tid):
        """Instinctive Pounce (Barbarian 7; SRD 5.2.1): as part of the Bonus Action that starts the Rage, move up to half
        the Speed (toward the foe it means to hit, when it is out of reach)."""
        reach = (c.get("weapon") or {}).get("reach", 5)
        if not c.get("instinctive_pounce") or tid is None or (self.dist(me, tid) <= reach + 0.01 and not self.blocked(me, tid)):
            return
        had = c.get("_speed_now")
        speed = had if had is not None else int(str(c.get("speed", "30")).split()[0])
        if speed <= 0:
            return
        c["_speed_now"] = speed // 2
        self.say("%s pounces as the Rage starts (Instinctive Pounce: up to %d ft)" % (c["name"], speed // 2))
        try:
            self.sim.pc_advance(me, tid, reach)
        finally:
            if had is None:
                c.pop("_speed_now", None)
            else:
                c["_speed_now"] = had

    def turn_barbarian(self, me, c):
        tid = self.front_target(me, c)
        if tid is None:
            self.say(c["name"] + " sees no foe and holds position"); return
        if me not in self.raging and self.rages.get(me) and self.bonus_free(me):
            self.rages[me] -= 1
            self.use_bonus(me)
            self.raging[me] = self.rage_kept[me] = self.s.turnSerial
            self.s.setField(me, "sim_resist_bps", 1)
            self.sim.say("dice", "%s enters a Rage (Bonus Action): +%d damage with Strength attacks, Resistance to Bludgeoning, "
                         "Piercing and Slashing damage (%d uses left)" % (
                             c["name"], c.get("rage_damage", rage_damage(c.get("level", 1))), self.rages[me]))
            self.rage_started(me, c)
            self.pounce(me, c, tid)
        martial.intimidate_tactic(self, me, c)                   # MARTIAL-HIGH: Intimidating Presence (Berserker 14)
        # PARTY-04: the Breath Weapon replaces one attack of the Attack action (two attacks from level 5)
        attacks = c.get("attacks", 1)
        if self.breathe(me, c):
            attacks -= 1
            if attacks <= 0:
                return
            self.approach(me, tid, 5)
        else:
            breathed = False
            spot = self.breath_spot(me, c)
            if spot and self.sim.pc_move_to(me, *spot):
                self.say("%s steps where its breath catches the most foes" % c["name"])
                breathed = self.breathe(me, c)
            if not breathed:
                self.approach(me, tid, 5)
                breathed = self.breathe(me, c)
            if breathed:
                attacks -= 1
                if attacks <= 0:
                    return
        w = self.rage_weapon(me, c, c["weapon"])
        in_reach = any(self.dist(me, f) <= FT and not self.blocked(me, f) for f in self.foes(me))
        reckless = bool(c.get("reckless") and w.get("str")) and in_reach and self.hp_left(me) * 2 > c["hp"]
        if reckless:   # decided with the first attack roll of the turn
            self.reckless.add(me); self.s.setField(me, "sim_reckless", 1)
            self.sim.say("dice", "%s uses Reckless Attack: Advantage on Strength attack rolls, attack rolls against it have "
                         "Advantage until its next turn" % c["name"])
        # PARTY-04: Frenzy (Berserker 3): Reckless while raging: the first target hit this turn takes Rage Damage d6s
        state = {"frenzy": reckless and me in self.raging and bool(c.get("frenzy")), "cleaved": False}
        frenzy_dice = "%dd6" % c.get("rage_damage", rage_damage(c.get("level", 1)))

        def kw_for(k):
            return {"extra_adv": [reckless], "bonus_dice": frenzy_dice if state["frenzy"] else "",
                    "note": "Frenzy (%s)" % frenzy_dice if state["frenzy"] else "",
                    "brutal": bool(reckless and c.get("brutal_strike") and k == 0)}    # Barbarian 9: the first attack

        def rider(t, res):
            self.rage_kept[me] = self.s.turnSerial              # an attack roll extends the Rage
            if res not in ("hit", "crit"):
                return
            state["frenzy"] = False
            if c["weapon"].get("cleave") and not state["cleaved"]:   # Cleave: once per turn
                second = [f for f in self.foes(me) if f != t and self.dist(f, t) <= FT and self.dist(me, f) <= FT
                          and not self.blocked(me, f)]
                if second:
                    state["cleaved"] = True
                    self.attack(me, second[0], self.rage_weapon(me, c, c["weapon"], cleave=True), extra_adv=[reckless],
                                note="Cleave (a second creature, no ability modifier)")

        self.attack_action(me, dict(c, attacks=attacks), tid, lambda k: w, move=False, kw_for=kw_for, rider=rider)

    # ---------------------------------------------------------------- PARTY-02: Paladin
    def lay_on_hands(self, me, c):
        """Bonus Action, touch: a fallen ally back on its feet (half its hit points), else a Bloodied member next to
        the Paladin or herself (SRD 5.2.1 Bloodied: half its hit points or fewer)."""
        pool = self.loh.get(me, 0)
        if not pool or not self.bonus_free(me):
            return False
        speed = int(str(c.get("speed", "30")).split()[0])
        fallen = [a for a in self.allies(me) if self.down(a) and not self.deaths.get(a, {}).get("dead")
                  and self.dist(me, a) <= speed + FT]
        if fallen:
            a = min(fallen, key=lambda a: self.dist(me, a))
            if self.dist(me, a) > FT:
                self.say("%s moves to reach %s" % (c["name"], self.name(a)))
                self.sim.pc_advance(me, a, 5)
            if self.dist(me, a) <= FT:
                heal = min(pool, max(1, self.sim.by_id(a)["hp"] // 2))
                self.loh[me] -= heal; self.use_bonus(me)
                self.sim.say("dice", "%s uses Lay On Hands on %s (Bonus Action): %d HP (%d left in the pool)" % (
                    c["name"], self.name(a), heal, self.loh[me]))
                self.revive(a, heal)
                return True
        if martial.restoring_tactic(self, me, c):               # MARTIAL-HIGH: Restoring Touch (Paladin 14)
            return True
        hurt = [a for a in [me] + self.allies(me) if not self.down(a) and (a == me or self.dist(me, a) <= FT)
                and self.hp_left(a) * 2 <= self.sim.by_id(a)["hp"]]
        if hurt:
            a = min(hurt, key=self.hp_left)
            heal = min(pool, self.sim.by_id(a)["hp"] - self.hp_left(a))
            self.loh[me] -= heal; self.use_bonus(me)
            self.s.heal(a, heal)
            self.sim.say("dice", "%s uses Lay On Hands on %s (Bonus Action): %d HP (%d left in the pool)" % (
                c["name"], "herself" if a == me else self.name(a), heal, self.loh[me]))
            return True
        return False

    def cast_bless(self, me, c, reserve):
        """Bless (Action, Concentration) when no one concentrates on it, on up to three attackers within 30 ft."""
        attackers = [me] + [a for a in self.allies(me) if not self.down(a)
                            and self.sim.by_id(a).get("class") in BLESS_ORDER[:5]]
        in_range = [a for a in attackers if a == me or self.dist(me, a) <= 30]
        if (self.concentrating is None and self.concentrates(me) is None and self.slot_free(me)
                and self.slots[me] > reserve and len(in_range) >= 2
                and self.pick_focus(me) is not None):
            targets = self.bless_targets(me, in_range)
            with self.refereed(me, "Bless", {"targets": targets}):
                self.spend_slot(me)
                self.resolve_bless(me, c, targets)
            return True
        return False

    def resolve_bless(self, me, c, targets):
        """Bless on these creatures (the slot is already spent): Concentration, +1d4 to their attacks and saves.
        LIVE-PLAY-01: shared with a player's own choice (sim/live_spells.py)."""
        self.start_concentration(me, "Bless")
        self.blessed, self.concentrating = set(targets), me
        self.sim.say("dice", "%s casts Bless on %s (Concentration)" % (c["name"], ", ".join(self.name(a) for a in targets)))

    # ---------------------------------------------------------------- SIM-MECHANICS-01 (f): Concentration spells
    def cast_shield_of_faith(self, me, c, keep):
        """Shield of Faith (SRD 5.2.1: Bonus Action, 60 ft, Concentration, +2 AC) when this member holds no Concentration
        and has a slot beyond the `keep` it saves. The Paladin protects herself when a foe is within her move; the
        Cleric the ally (or herself) the most foes are next to, one not already protected."""
        if not c.get("shield_of_faith") or self.concentrates(me) or not self.bonus_free(me) or not self.slot_free(me) \
                or self.slots[me] <= keep or self.incapacitated(me):
            return False
        foes = [f for f in self.foes(me) if self.sim.sees(me, f) or f in self.located(me)]
        if c.get("class") == "paladin":
            if not [f for f in foes if self.dist(me, f) <= speed_ft(c) + 5]:
                return False
            t = me
        else:
            taken = set(self.faith.values())
            cands = [a for a in [me] + self.allies(me) if not self.down(a) and a not in taken
                     and (a == me or (self.dist(me, a) <= 60 and not self.blocked(me, a) and self.sim.sees(me, a)))]
            near = lambda a: len([f for f in foes if self.dist(a, f) <= FT])
            if not cands:
                return False
            t = max(cands, key=lambda a: (near(a), -self.sim.by_id(a).get("ac", 10), a == me))
            if near(t) == 0:
                return False
        with self.refereed(me, "Shield of Faith", {"target": t}):
            self.resolve_shield_of_faith(me, c, t)
        return True

    def resolve_shield_of_faith(self, me, c, t):
        """Shield of Faith on t: Concentration, a Bonus Action, a slot, +2 AC. LIVE-PLAY-01: shared with live play."""
        self.start_concentration(me, "Shield of Faith")
        self.use_bonus(me)
        self.spend_slot(me)
        self.faith[me] = t
        self.s.setField(t, "sim_ac_faith", 2)
        self.sim.say("dice", "%s casts Shield of Faith on %s (Bonus Action, Concentration): +2 AC" % (c["name"], self.name(t)))

    def cast_spiritual_weapon(self, me, c, tid, keep):
        """Spiritual Weapon (SRD 5.2.1: Bonus Action, a level 2 slot, 60 ft, Concentration): the force appears beside a
        foe she sees within 60 ft and strikes at once (melee spell attack, 1d8 + her modifier Force, +1d8 per slot level
        above 2)."""
        if not c.get("spiritual_weapon") or tid is None or self.concentrates(me) or not self.bonus_free(me) \
                or not self.slot_free(me, 2) or self.slots[me] <= keep or self.incapacitated(me):
            return False
        if self.down(tid) or self.dist(me, tid) > 60 or self.blocked(me, tid) or not self.sim.sees(me, tid):
            return False
        with self.refereed(me, "Spiritual Weapon", {"target": tid}):
            self.resolve_spiritual_weapon(me, c, tid)
        return True

    def resolve_spiritual_weapon(self, me, c, tid):
        """Resolve a validated choice; scripted preferences above must not reject a live player's cast."""
        self.start_concentration(me, "Spiritual Weapon")
        self.use_bonus(me)
        level = self.spend_slot(me, 2)
        self.spirit_weapon[me] = {"level": level, "at": self.pos(tid)}
        self.sim.say("dice", "%s casts Spiritual Weapon (Bonus Action, a level %d slot, Concentration): a spectral force "
                     "beside %s" % (c["name"], level, self.name(tid)))
        self.spirit_attack(me, c, tid)
        return True

    def spiritual_strike(self, me, c):
        """The Spiritual Weapon she holds: a Bonus Action on a later turn, the force moves up to 20 ft and strikes a foe
        within 5 ft of it (the focus first, else the weakest). Walls are not checked for the force."""
        sw = self.spirit_weapon.get(me)
        if not sw or not self.bonus_free(me) or self.incapacitated(me):
            return False
        def reach(f):
            (fx, fy), (ax, ay) = self.pos(f), sw["at"]
            return max(abs(fx - ax), abs(fy - ay)) * self.sim.sc.get("units", 5) <= 25 + 2.6   # 20 ft move + 5 ft reach
        near = [f for f in self.foes(me) if reach(f)]
        if not near:
            return False
        tid = self.focus if self.focus in near else min(near, key=self.hp_left)
        self.use_bonus(me)
        sw["at"] = self.pos(tid)
        self.sim.say("dice", "%s moves the Spiritual Weapon to %s (Bonus Action)" % (c["name"], self.name(tid)))
        self.spirit_attack(me, c, tid)
        return True

    def spirit_attack(self, me, c, tid):
        lv = self.spirit_weapon[me]["level"]
        base = self.sim.attack_mode_for(me, tid)
        guided = tid in self.guided
        mode = combine([base == "adv", guided], [base == "dis"])
        self.guided.pop(tid, None)
        res = self.s.pcAttack(me, tid, c.get("spell_atk", 5), 20, "%dd8" % (lv - 1), c.get("spell_mod", 3), mode, 0,
                              4 if me in self.blessed else 0, "", "force", False, True)
        self.sim.settle()
        return res

    # ---------------------------------------------------------------- SIM-MECHANICS-01 (f): spells that disable foes
    def spell_dc(self, c):
        # 8 + Proficiency Bonus + modifier. REFEREE-01 (2026-10-22): was 10 + modifier, a level 5 Paladin's Command at
        # DC 13 instead of 14. GM 2026-10-23: +1 while the Sorcerer's Innate Sorcery is active
        return c.get("spell_dc", 8 + proficiency_bonus(c.get("level", 1)) + c.get("spell_mod", 3)) + self.innate_on(c.get("id"))

    def burst_dice(self, me, tid, c, kind, faces):
        """Sorcerous Burst (SRD 5.2.1): each 8 on a d8 rolls another d8 into the damage, at most the spellcasting ability
        modifier's worth of these d8s in a cast. The "can" is always taken: it only adds damage."""
        left = max(0, self.spell_dc(c) - self.innate_on(c.get("id")) - 8 - proficiency_bonus(c.get("level", 1)))
        eights, more = sum(1 for f in faces if f == 8), []
        while eights and len(more) < left:
            more.append(self.sim.rng.randint(1, 8))
            eights += (more[-1] == 8) - 1
        if more:
            self.sim.say("dice", "Sorcerous Burst: an 8 on the d8, %d more d8 (%s) = %d %s (at most %d in a cast)" % (
                len(more), ", ".join(map(str, more)), sum(more), kind.capitalize(), left))
            self.s.pcDamage(me, tid, "", sum(more), False, kind)
            self.sim.settle()

    def innate_on(self, i):
        """Innate Sorcery (Sorcerer 1; SRD 5.2.1): active for 1 minute (10 rounds) after its Bonus Action."""
        until = getattr(self, "innate_until", {}).get(i)
        return int(until is not None and self.s.round() <= until)

    def affinity(self, c, kind):
        """Elemental Affinity (Draconic Sorcery 6; SRD 5.2.1): + the Charisma modifier to one damage roll of a spell that
        deals the chosen type."""
        return max(1, c.get("cha_mod", 1)) if c.get("elemental_affinity") and c["elemental_affinity"] == kind else 0

    def holds_no_one(self, caster, spell, why="holds no one"):
        """GM 2026-10-25 (ruling S3; SRD 5.2.1 Concentration: "The creator can end Concentration at any time"): a spell
        whose every creature saved (or is free again) leaves a player's character concentrating on it, held as itself, until
        the player casts another Concentration spell or it is broken; the computer-played heroes drop it (their tactic)."""
        c = self.sim.by_id(caster)
        if c.get("pc") and c.get("live"):
            self.__dict__.setdefault("gm_concentration", {})[caster] = spell
            self.sim.say("dice", "%s's %s %s; %s keeps concentrating (another Concentration spell ends it)" % (
                c["name"], spell, why, c["name"]))
        else:
            self.sim.say("dice", "%s's %s %s: its Concentration ends" % (c["name"], spell, why))

    def spell_target_gone(self, caster, t):
        """A creature saved or woke: the spell ends on it; with no creature left the caster drops the Concentration."""
        ctl = getattr(self, "control", {}).get(caster)
        if ctl:
            ctl["targets"].discard(t)
            if not ctl["targets"]:
                self.control.pop(caster)
                self.holds_no_one(caster, ctl["spell"])

    def control_ok(self, me, c, flag, level=1):
        return (c.get(flag) and self.concentrates(me) is None and self.slot_free(me, level) and not self.incapacitated(me)
                and getattr(self.sim, "gm_rules", None) is not None)

    def control_target_ok(self, me, t, rng, *conds):
        gm = self.sim.gm_rules
        return (not self.down(t) and self.dist(me, t) <= rng and not self.blocked(me, t) and self.sim.sees(me, t)
                and not gm.incapacitated(t) and not any(gm.cond_immune(t, n) for n in conds))

    def cast_sleep(self, me, c, keep=1):
        """Sleep (Wizard 1; SRD 5.2.1: Action, 60 ft, Concentration, 5-ft-radius Sphere, Wisdom save or Incapacitated,
        then Unconscious on a second failure). The point (a square's center or corner within 60 ft, no wall on the way)
        whose Sphere holds the most foes she sees (centers within 5 ft), two at least; not those immune to Exhaustion
        (they don't sleep) or already Incapacitated. One slot stays for Shield."""
        if not self.control_ok(me, c, "sleep") or self.slots[me] <= keep:
            return False
        gm, u = self.sim.gm_rules, self.sim.sc.get("units", 5)
        here = self.pos(me)
        cands = [f for f in self.foes(me) if self.control_target_ok(me, f, 65, "exhaustion")
                 and "elf" not in gm.kind(f).lower()]
        best = None
        for f in cands:
            fx, fy = self.pos(f)
            for pt in ((fx, fy), (fx - .5, fy - .5), (fx + .5, fy - .5), (fx - .5, fy + .5), (fx + .5, fy + .5)):
                if max(abs(pt[0] - here[0]), abs(pt[1] - here[1])) * u > 60 or self.walled(here, pt):
                    continue
                inside = [o for o in cands if ((self.pos(o)[0] - pt[0]) ** 2 + (self.pos(o)[1] - pt[1]) ** 2) ** .5 * u <= 5.01]
                if best is None or len(inside) > len(best[1]):
                    best = (pt, inside)
        if not best or len(best[1]) < 2:
            return False
        pt, targets = best
        with self.refereed(me, "Sleep", {"x": pt[0], "y": pt[1]}, {"origin": list(pt), "targets": list(targets)}):
            self.resolve_sleep(me, c, targets)
        return True

    def resolve_sleep(self, me, c, targets, dis=()):
        """Sleep on these creatures: Concentration, a slot, Wisdom saves or Incapacitated. LIVE-PLAY-01: shared.
        dis: the creatures with Disadvantage on the saves against it (GM 2026-10-23: Heightened Spell)."""
        gm = self.sim.gm_rules
        self.start_concentration(me, "Sleep")
        self.spend_slot(me)
        dc = self.spell_dc(c)
        self.sim.say("dice", "%s casts Sleep (Concentration): DC %d Wisdom save for %s" % (
            c["name"], dc, ", ".join(self.name(t) for t in targets)))
        held = set()
        for t in targets:
            hd = "Heightened Spell" if t in dis else False
            if not gm.condition_save(t, "wis", dc, "Sleep", dis=hd):
                gm.add(t, "Incapacitated", "(%s's Sleep, until the end of its next turn)" % c["name"], by=me,
                       spell="Sleep", stage=1, save="wis", dc=dc, **({"dis": hd} if hd else {}))
                held.add(t)
        if held:
            self.control[me] = {"spell": "Sleep", "targets": held}
        else:
            self.holds_no_one(me, "Sleep")

    def cast_laughter(self, me, c, tid):
        """Hideous Laughter (Warlock 1; SRD 5.2.1: Action, 30 ft, Concentration; Wisdom save or Prone and Incapacitated,
        repeats the save at the end of each of its turns and when damaged) on a strong foe (20 HP or more left)."""
        if tid is None or not self.control_ok(me, c, "hideous_laughter") or self.hp_left(tid) < 20:
            return False
        if not self.control_target_ok(me, tid, 30, "prone", "incapacitated"):
            return False
        gm, dc = self.sim.gm_rules, self.spell_dc(c)
        with self.refereed(me, "Hideous Laughter", {"target": tid}):
            self.start_concentration(me, "Hideous Laughter")
            self.spend_slot(me)
            self.sim.say("dice", "%s casts Hideous Laughter on %s (Concentration): DC %d Wisdom save" % (c["name"], self.name(tid), dc))
            if gm.condition_save(tid, "wis", dc, "Hideous Laughter"):
                self.sim.say("dice", "%s's Hideous Laughter fails: its Concentration ends" % c["name"])
                return True
            for n in ("Prone", "Incapacitated"):
                gm.add(tid, n, "(%s's Hideous Laughter)" % c["name"], by=me, spell="Hideous Laughter", save="wis", dc=dc)
            self.control[me] = {"spell": "Hideous Laughter", "targets": {tid}}
        return True

    def resolve_guiding_bolt(self, me, c, focus, level=1):
        """Guiding Bolt at focus (the slot is already spent): a ranged spell attack, 4d6 Radiant (+1d6 for each slot level
        above 1); on a hit the next attack roll against it has Advantage. LIVE-PLAY-01: shared."""
        self.sim.say("dice", "%s casts Guiding Bolt at %s%s" % (c["name"], self.sim.by_id(focus)["name"],
                                                               " (a level %d slot)" % level if level > 1 else ""))
        res = self.s.pcAttack(me, focus, c.get("spell_atk", 5), 20, "%dd6" % (3 + level), 0,
                              combine([self.sim.attack_mode_for(me, focus) == "adv"],
                                      [self.sim.attack_mode_for(me, focus) == "dis", self.enemy_next_to(me)]), 0, 0, "", "radiant", True, True)
        self.sim.settle()
        if res in ("hit", "crit") and not self.down(focus):
            self.guided[focus] = (me, self.s.round())
        return res

    def resolve_hex(self, me, c, tid):
        """Hex on tid (the Bonus Action is the caller's): Concentration, a slot, +1d6 Necrotic on each hit; the caller
        records self.hex[me] = tid. LIVE-PLAY-01: shared."""
        self.start_concentration(me, "Hex")
        self.spend_slot(me)
        self.sim.say("dice", "%s casts Hex on %s (Bonus Action, Concentration): +1d6 Necrotic on each hit" % (
            c["name"], self.name(tid)))

    def cast_hold_person(self, me, c, tid):
        """Hold Person (Fiend 5; SRD 5.2.1: Action, a level 2+ slot, 60 ft, Concentration; a Humanoid; Wisdom save or
        Paralyzed, repeating the save at the end of each of its turns) on a strong Humanoid foe (20 HP or more left).
        One target (a higher slot would add more: not used)."""
        if tid is None or not self.control_ok(me, c, "hold_person", 2) or self.hp_left(tid) < 20:
            return False
        if "humanoid" not in str(self.sim.by_id(tid).get("type", "")).lower():
            return False
        if not self.control_target_ok(me, tid, 60, "paralyzed"):
            return False
        with self.refereed(me, "Hold Person", {"target": tid}):
            self.resolve_hold_person(me, c, tid)
        return True

    def cast_hold_monster(self, me, c, tid, least_hp=30):
        """Hold Monster (SRD 5.2.1: Action, a level 5+ slot, 90 ft, Concentration; any creature; Wisdom save or
        Paralyzed, repeating the save at the end of each of its turns) on a strong foe (30 Hit Points or more left) that
        Hold Person can't take (not a Humanoid, or no level 2 slot plan for it)."""
        if tid is None or not self.control_ok(me, c, "hold_monster", 5) or self.hp_left(tid) < least_hp:
            return False
        if not self.control_target_ok(me, tid, 90, "paralyzed"):
            return False
        with self.refereed(me, "Hold Monster", {"target": tid}):
            self.resolve_hold_person(me, c, tid, spell="Hold Monster")
        return True

    def resolve_hold_person(self, me, c, tid, more=(), dis=(), spell="Hold Person"):
        """Hold Person on tid: Concentration, a level 2+ slot, a Wisdom save or Paralyzed. LIVE-PLAY-01: shared.
        GM 2026-10-23 (the Sorcerer): more = other Humanoids (Twinned Spell: one more), dis = the creatures with
        Disadvantage on the saves against it (Heightened Spell)."""
        gm, dc = self.sim.gm_rules, self.spell_dc(c)
        self.start_concentration(me, spell)
        level = self.spend_slot(me, 5 if spell == "Hold Monster" else 2)
        self.sim.say("dice", "%s casts %s on %s (a level %d slot, Concentration): DC %d Wisdom save" % (
            c["name"], spell, " and ".join(self.name(t) for t in [tid] + list(more)), level, dc))
        held = set()
        for t in [tid] + list(more):
            hd = "Heightened Spell" if t in dis else False
            if not gm.condition_save(t, "wis", dc, spell, dis=hd):
                gm.add(t, "Paralyzed", "(%s's %s)" % (c["name"], spell), by=me, spell=spell, save="wis", dc=dc,
                       **({"dis": hd} if hd else {}))
                held.add(t)
        if not held:
            self.holds_no_one(me, spell, "fails")
            return
        self.control[me] = {"spell": spell, "targets": held}

    def cast_command(self, me, c, tid, keep=0):
        """Command (Cleric, Paladin 1; SRD 5.2.1: Action, 60 ft, instantaneous; Wisdom save or it obeys on its next
        turn): Grovel (Prone, then its turn ends)."""
        gm = getattr(self.sim, "gm_rules", None)
        if tid is None or not gm or not c.get("command") or not self.slot_free(me) or self.slots[me] <= keep \
                or self.incapacitated(me) or gm.has(tid, "Prone"):
            return False
        if not self.control_target_ok(me, tid, 60, "prone"):
            return False
        dc = self.spell_dc(c)
        with self.refereed(me, "Command", {"target": tid}):
            self.spend_slot(me)
            self.sim.say("dice", "%s casts Command (Grovel) on %s: DC %d Wisdom save" % (c["name"], self.name(tid), dc))
            if not gm.condition_save(tid, "wis", dc, "Command"):
                gm.add(tid, "Prone", "(%s's Command: Grovel)" % c["name"], by=me, command=True)
        return True

    # ---------------------------------------------------------------- SIM-MECHANICS-01 (f) slice 3: damage spells
    def slot_spare(self, me, keep, level=1):
        return self.slot_free(me, level) and self.slots[me] > keep

    def area_spell(self, me, c, name, targets, ability, key, dice, kind, note, dis=(), empower=0):
        """GM 2026-10-23 (the Sorcerer): empower = Empowered Spell's dice to roll again (the Charisma modifier); the
        Draconic Sorcerer's Elemental Affinity adds the Charisma modifier when the damage type is its own."""
        if empower:
            dmg, before, after, n = empowered_roll(self.sim.rng, dice, empower)
            self.sim.say("dice", "Empowered Spell: %s rolls %s, %d of the lowest rolled again -> %s" % (
                c["name"], before, n, after))
        else:
            dmg = roll(self.sim.rng, dice)
        if high.maxed(self.sim, me):                             # CASTER-HIGH: Overchannel, the dice at their highest
            dmg = high.max_total(dice)
            self.sim.say("dice", "Overchannel: %s at its maximum, %d" % (dice, dmg))
        dc, plus = self.spell_dc(c), self.affinity(c, kind)
        if plus:
            dice, dmg = "%s+%d (Elemental Affinity)" % (dice, plus), dmg + plus
        evoke = high.empowered(c, name)                          # GM 2026-10-26: Empowered Evocation (Evoker 10)
        if evoke:
            dice, dmg = "%s+%d (Empowered Evocation)" % (dice, evoke), dmg + evoke
        self.sim.say("dice", "%s casts %s: %s, DC %d %s save, %s = %d %s, half on a success (%s)" % (
            c["name"], name, note, dc, ability, dice, dmg, kind.capitalize(), ", ".join(self.name(f) for f in targets)))
        for f in targets:
            if not self.down(f):
                self.save_damage(me, f, ability, key, dc, dmg, kind, dis=f in dis)
        return dmg

    def cone_foes(self, me, feet_long):
        """The direction (of eight) whose Cone from the caster holds the most located foes and no ally: a creature counts
        when its square's center is within the Cone's length and inside its width (as wide as it is far). Returns
        (foes, (dx, dy)); ([], None) when no direction fits."""
        u, (hx, hy) = self.sim.sc.get("units", 5), self.pos(me)
        located = set(self.located(me))
        best = None
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            n = math.hypot(dx, dy)
            def inside(i):
                x, y = self.pos(i)
                vx, vy = x - hx, y - hy
                along = (vx * dx + vy * dy) / n
                across = abs(vx * dy - vy * dx) / n
                return 0 < along * u <= feet_long + 0.01 and across <= along / 2 + 0.01 and not self.walled((hx, hy), (x, y))
            foes = [f for f in self.foes(me) if f in located and inside(f)]
            allies = [a for a in self.allies(me) if not self.deaths.get(a, {}).get("dead") and inside(a)]
            if not allies and (best is None or len(foes) > len(best[0])):
                best = (foes, (dx, dy))
        return best or ([], None)

    def cast_burning_hands(self, me, c, keep):
        """Burning Hands (SRD 5.2.1: Action, 15-ft Cone, Dexterity save, 3d6 Fire, +1d6 per slot level above 1) when the
        Cone holds two located foes or more and no ally."""
        if not c.get("burning_hands") or not self.slot_spare(me, keep):
            return False
        found, way = self.cone_foes(me, 15)
        foes = [f for f in found if not self.wasted(f, "fire")]
        if len(foes) < 2:
            return False
        with self.refereed(me, "Burning Hands", None, {"origin": list(self.pos(me)),
                                                       "angle_deg": math.degrees(math.atan2(way[1], way[0]))}):
            level = self.spend_slot(me)
            self.area_spell(me, c, "Burning Hands (a level %d slot)" % level, foes, "Dexterity", "dex_save",
                            "%dd6" % (2 + level), "fire", "15-ft Cone")
        return True

    def cast_cone_of_cold(self, me, c):
        """Cone of Cold (SRD 5.2.1: Action, a level 5+ slot, 60-ft Cone, Constitution save, 8d8 Cold, +1d8 per slot
        level above 5, half on a success) when the Cone holds two located foes or more and no ally."""
        if not c.get("cone_of_cold") or not self.slot_free(me, 5):
            return False
        found, way = self.cone_foes(me, 60)
        foes = [f for f in found if not self.wasted(f, "cold")]
        if len(foes) < 2:
            return False
        if high.overchannel_tactic(self, me, c, "Cone of Cold"):  # CASTER-HIGH: Overchannel's free use
            high.overchannel_on(self, me)
        with self.refereed(me, "Cone of Cold", None, {"origin": list(self.pos(me)),
                                                      "angle_deg": math.degrees(math.atan2(way[1], way[0]))}):
            try:
                level = self.spend_slot(me, 5)
                self.area_spell(me, c, "Cone of Cold (a level %d slot)" % level, foes, "Constitution", "con_save",
                                "%dd8" % (3 + level), "cold", "60-ft Cone")
            finally:
                high.disarm(self, me)
        return True

    def cast_thunderwave(self, me, c, keep):
        """Thunderwave (SRD 5.2.1: Action, 15-ft Cube from the caster, Constitution save, 2d8 Thunder and pushed 10 ft on
        a failure, half only on a success) when a Cube beside her holds two located foes or more and no ally."""
        if not c.get("thunderwave") or not self.slot_spare(me, keep):
            return False
        hx, hy = self.pos(me)
        located = set(self.located(me))
        best = None
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            xs = (hx + 1, hx + 3) if dx > 0 else (hx - 3, hx - 1) if dx < 0 else (hx - 1, hx + 1)
            ys = (hy + 1, hy + 3) if dy > 0 else (hy - 3, hy - 1) if dy < 0 else (hy - 1, hy + 1)
            inside = lambda i: xs[0] - .5 <= self.pos(i)[0] <= xs[1] + .5 and ys[0] - .5 <= self.pos(i)[1] <= ys[1] + .5 \
                and not self.walled((hx, hy), self.pos(i))
            foes = [f for f in self.foes(me) if f in located and inside(f) and not self.wasted(f, "thunder")]
            if not [a for a in self.allies(me) if not self.deaths.get(a, {}).get("dead") and inside(a)] \
                    and len(foes) >= 2 and (best is None or len(foes) > len(best[0])):
                best = (foes, (dx, dy), xs, ys)
        if not best:
            return False
        xs, ys = best[2], best[3]                                # the Cube's squares; its edges half a square out
        with self.refereed(me, "Thunderwave", None, {"origin": [hx + best[1][0] * .5, hy + best[1][1] * .5],
                                                     "cube": [xs[0] - .5, ys[0] - .5, xs[1] + .5, ys[1] + .5]}):
            level = self.spend_slot(me)
            dc = self.spell_dc(c)
            dmg = roll(self.sim.rng, "%dd8" % (1 + level))
            self.sim.say("dice", "%s casts Thunderwave (a level %d slot): 15-ft Cube, DC %d Constitution save, %dd8 = %d "
                         "Thunder and pushed 10 ft on a failure, half on a success (%s)" % (
                             c["name"], level, dc, 1 + level, dmg, ", ".join(self.name(f) for f in best[0])))
            for f in best[0]:
                mod = self.sim.by_id(f).get("con_save", 0)
                d20 = self.sim.rng.randint(1, 20)
                saved = d20 + mod >= dc
                amount = save_for_half(dmg, saved)
                self.sim.say("dice", "%s Constitution save: d20 %d %+d = %d vs DC %d -> %s" % (
                    self.name(f), d20, mod, d20 + mod, dc, "success (half)" if saved else "failure"))
                if amount:
                    self.s.pcDamage(me, f, "", amount, False, "thunder")
                    self.sim.settle()
                if not saved and not self.down(f):
                    self.push(f, best[1], 2)
        return True

    def push(self, f, d, squares):
        """Move a creature up to `squares` away along d, square by square, stopping at walls and creatures."""
        x, y = self.pos(f)
        taken = {self.pos(o["id"]) for o in self.sim.sc["combatants"] if o["id"] != f and not self.down(o["id"])}
        to = (x, y)
        for _ in range(squares):
            nxt = (to[0] + d[0], to[1] + d[1])
            if nxt in taken or self.walled(to, nxt):
                break
            to = nxt
        if to != (x, y):
            self.s.move(f, to[0], to[1])
            self.sim.say("dice", "%s is pushed to (%g, %g)" % (self.name(f), to[0], to[1]))

    def cast_shatter(self, me, c, keep):
        """Shatter (SRD 5.2.1: Action, a level 2 slot, 60 ft, 10-ft-radius Sphere, Constitution save, 3d8 Thunder, half on
        a success; a Construct has Disadvantage) at the point holding two located foes or more and no ally."""
        if not c.get("shatter") or not self.slot_spare(me, keep, 2):
            return False
        pool = self.pools.get(me) or []
        if c.get("class") == "wizard" and not (len(pool) > 1 and pool[1] > 0):
            return False                                         # higher slots stay for Fireball
        found = self.fireball_point(me, c, 2, radius=10, kind="thunder", reach=60)
        if not found:
            return False
        pt, inside, spared = found
        if spared:
            return False
        with self.refereed(me, "Shatter", {"x": pt[0], "y": pt[1]}, {"origin": list(pt)}):
            level = self.spend_slot(me, 2)
            constructs = [f for f in inside if "construct" in str(self.sim.by_id(f).get("type", "")).lower()]
            self.area_spell(me, c, "Shatter (a level %d slot)" % level, inside, "Constitution", "con_save",
                            "%dd8" % (1 + level), "thunder", "10-ft-radius Sphere at (%g, %g)" % pt, dis=constructs)
        return True

    def cast_ice_knife(self, me, c, tid, keep):
        """Ice Knife (SRD 5.2.1: Action, 60 ft, ranged spell attack 1d10 Piercing; hit or miss, the target and each
        creature within 5 ft make a Dexterity save or take 2d6 Cold) when another foe is next to the target and no ally."""
        if not c.get("ice_knife") or tid is None or not self.slot_spare(me, keep):
            return False
        if self.dist(me, tid) > 60 or self.blocked(me, tid) or not self.sim.sees(me, tid):
            return False
        near = lambda i: i != tid and self.dist(i, tid) <= FT
        others = [f for f in self.foes(me) if near(f)]
        if not others or [a for a in [me] + self.allies(me) if not self.deaths.get(a, {}).get("dead") and near(a)]:
            return False
        with self.refereed(me, "Ice Knife", {"target": tid}):
            level = self.spend_slot(me)
            self.sim.say("dice", "%s casts Ice Knife at %s (a level %d slot)" % (c["name"], self.name(tid), level))
            knife = {"name": "Ice Knife", "atk": c.get("spell_atk", 5), "reach": 60, "dmg": "1d10", "crit": 20,
                     "dmgtype": "piercing"}
            self.attack(me, tid, knife, spell=True)
            dmg, dc = roll(self.sim.rng, "%dd6" % (1 + level)), self.spell_dc(c)
            self.sim.say("dice", "The shard explodes: DC %d Dexterity save, %dd6 = %d Cold (no damage on a success)" % (
                dc, 1 + level, dmg))
            for f in [tid] + others:
                if self.down(f):
                    continue
                mod = self.sim.by_id(f).get("dex_save", 0)
                d20 = self.sim.rng.randint(1, 20)
                gm = getattr(self.sim, "gm_rules", None)
                ok = d20 + mod >= dc and not (gm and gm.auto_fail(f, "dex"))
                self.sim.say("dice", "%s Dexterity save: d20 %d %+d = %d vs DC %d -> %s" % (
                    self.name(f), d20, mod, d20 + mod, dc, "success" if ok else "failure"))
                if not ok:
                    self.s.pcDamage(me, f, "", dmg, False, "cold")
                    self.sim.settle()
        return True

    def frost_weapon(self, c):
        """Ray of Frost in Fire Bolt's place (same dice count: 1d8, 2d8 from level 5; Potent Cantrip too)."""
        n = (c["weapon"].get("dmg", "1d10").split("d")[0] or "1")
        return dict(c["weapon"], name="Ray of Frost", reach=60, dmg="%sd8" % n, dmgtype="cold")

    def hellish_rebuke(self, me, src):
        """Hellish Rebuke (SRD 5.2.1: Reaction to damage from a creature it sees within 60 ft; Dexterity save, 2d10 Fire,
        half on a success): the Infernal legacy's free casting, once a day (the slots stay for Shield and the rest)."""
        asked = self.asked_live(me)
        if asked:                                                # REACTIONS-LIVE-01: its player is asked instead
            return asked.rebuke(me, src)
        c = self.sim.by_id(me)
        if not c.get("hellish_rebuke") or src is None or self.side(src) == self.side(me) or self.down(me) or self.down(src):
            return False
        if self.incapacitated(me) or self.s.getField(me, "reaction") or not self.rebuke_free.setdefault(me, True):
            return False
        if self.dist(me, src) > 60 or not self.sim.sees(me, src) or self.wasted(src, "fire"):
            return False
        with self.refereed(me, "Hellish Rebuke", {"target": src, "free": "Infernal Legacy"}):
            self.rebuke_free[me] = False
            self.s.setField(me, "reaction", 1)
            self.area_spell(me, c, "Hellish Rebuke (Reaction, Infernal Legacy: once a day without a slot)", [src],
                            "Dexterity", "dex_save", "2d10", "fire", "at %s" % self.name(src))
        return True

    def searing_smite(self, me, c, t, res):
        """Searing Smite (SRD 5.2.1: Bonus Action after a melee hit, +1d6 Fire; at the start of each of its turns the
        target takes 1d6 Fire, then a Constitution save ends it) on a sturdy target (25 HP or more left) not already
        searing; Divine Smite stays for the rest."""
        gm = getattr(self.sim, "gm_rules", None)
        if not gm or not c.get("searing_smite") or not self.bonus_free(me) or not self.slot_free(me) \
                or self.down(t) or self.hp_left(t) < 25 or gm.has(t, "Searing Smite") or self.wasted(t, "fire")                 or (me, t) in self.seared:
            return False
        self.seared.add((me, t))                                 # once per target: Divine Smite for the later hits
        with self.refereed(me, "Searing Smite", {"target": t}):
            self.use_bonus(me)
            level = self.spend_slot(me)
            self.sim.say("dice", "%s casts Searing Smite (Bonus Action, a level %d slot): +%dd6 Fire%s" % (
                c["name"], level, level, ", doubled on the Critical Hit" if res == "crit" else ""))
            self.s.pcDamage(me, t, "%dd6" % level, 0, res == "crit", "fire")
            self.sim.settle()
            if not self.down(t):
                gm.add(t, "Searing Smite", "(%s: %dd6 Fire at the start of its turns until a Constitution save)" % (
                    c["name"], level), by=me, dice="%dd6" % level, save="con", dc=self.spell_dc(c))
        return True

    # ---------------------------------------------------------------- SIM-MECHANICS-01 (f) slice 4: features
    def keep_channel(self, c):
        return 1 if c.get("preserve_life") else 0                # one use stays for Preserve Life (Life 3)

    def turn_undead(self, me, c):
        """Turn Undead (Cleric 2, Channel Divinity, Magic action; SRD 5.2.1): each Undead within 30 ft makes a Wisdom
        save or is Frightened and Incapacitated for 1 minute (ends early if it takes damage or the Cleric is
        Incapacitated or dies). Used when two Undead or more are within 30 ft."""
        gm = getattr(self.sim, "gm_rules", None)
        if not gm or not c.get("turn_undead") or self.channel.get(me, 0) <= self.keep_channel(c):
            return False
        undead = [f for f in self.foes(me) if "undead" in str(self.sim.by_id(f).get("type", "")).lower()
                  and self.dist(me, f) <= 30 and not self.blocked(me, f) and not gm.incapacitated(f)]
        if len(undead) < 2:
            return False
        self.channel[me] -= 1
        dc = self.spell_dc(c)
        self.sim.say("dice", "%s uses Turn Undead (Channel Divinity, Magic action): DC %d Wisdom save for %s" % (
            c["name"], dc, ", ".join(self.name(f) for f in undead)))
        sear = 0
        if c.get("sear_undead"):                                 # Sear Undead (Cleric 5): Wisdom-modifier d8s (1d8 at least)
            dice = "%dd8" % max(1, c.get("spell_mod", 1))
            sear = roll(self.sim.rng, dice)
            self.sim.say("dice", "Sear Undead: %s = %d Radiant damage to each Undead that fails the save" % (dice, sear))
        for f in undead:
            if not gm.condition_save(f, "wis", dc, "Turn Undead"):
                if sear:                                         # the damage does not end the turn effect: dealt first
                    self.s.pcDamage(me, f, "", sear, False, "radiant")
                    self.sim.settle()
                    if self.down(f):
                        continue
                for n in ("Frightened", "Incapacitated"):
                    if not gm.cond_immune(f, n.lower()):
                        gm.add(f, n, "(%s's Turn Undead)" % c["name"], by=me, spell="Turn Undead")
        return True

    def divine_spark(self, me, c, tid):
        """Divine Spark (Cleric 2, Channel Divinity, Magic action; SRD 5.2.1): a creature within 30 ft makes a
        Constitution save against 1d8 (2d8 from 7) + Wisdom modifier Radiant, half on a success. Used on the focus when
        a use is spare (one stays for Preserve Life from 3)."""
        if tid is None or not c.get("divine_spark") or self.channel.get(me, 0) <= self.keep_channel(c):
            return False
        if self.down(tid) or self.dist(me, tid) > 30 or self.blocked(me, tid) or not self.sim.sees(me, tid) \
                or self.wasted(tid, "radiant"):
            return False
        self.channel[me] -= 1
        dice = "%dd8+%d" % (2 if c.get("level", 1) >= 7 else 1, c.get("spell_mod", 3))
        self.area_spell(me, c, "Divine Spark (Channel Divinity, Magic action)", [tid], "Constitution", "con_save",
                        dice, "radiant", "at %s" % self.name(tid))
        return True

    def cure_ally(self, me, c, reserve):
        """Cure Wounds (SRD 5.2.1: Action, touch, 2d8 + modifier) on an ally next to her (or herself) at a third of its
        hit points or less, not fallen (Healing Word brings the fallen back); a slot beyond the reserve."""
        if not c.get("cure_wounds") or not self.slot_spare(me, reserve):
            return False
        hurt = [a for a in [me] + self.allies(me) if not self.down(a) and (a == me or self.dist(me, a) <= FT)
                and self.hp_left(a) * 3 <= self.sim.by_id(a)["hp"]]
        if not hurt:
            return False
        a = min(hurt, key=self.hp_left)
        with self.refereed(me, "Cure Wounds", {"target": a}):
            level = self.spend_slot(me)
            heal = high.heal_roll(self.sim.rng, c, "2d8+%d" % c.get("spell_mod", 3)) + self.healing_bonus(me, c, level, a != me)
            self.sim.say("dice", "%s casts Cure Wounds on %s (a level %d slot): %d HP" % (c["name"], self.name(a), level, heal))
            self.s.heal(a, heal)
        return True

    def misty_step(self, me, c, keep):
        """Misty Step (SRD 5.2.1: Bonus Action, a level 2 slot, teleport 30 ft to a free space it can see): away from a
        foe next to it, to the free square within 30 ft farthest from the foes (no opportunity attack: a teleport)."""
        if not c.get("misty_step") or not self.bonus_free(me) or not self.slot_spare(me, keep, 2):
            return False
        foes = [f for f in self.foes(me) if not self.down(f)]
        if not [f for f in foes if self.dist(me, f) <= FT]:
            return False
        hx, hy = self.pos(me)
        taken = {self.pos(o["id"]) for o in self.sim.sc["combatants"] if o["id"] != me and not self.down(o["id"])}
        best = None
        for dx in range(-6, 7):
            for dy in range(-6, 7):
                to = (hx + dx, hy + dy)
                if (dx, dy) == (0, 0) or to in taken or self.walled((hx, hy), to):
                    continue
                gap = min(max(abs(self.pos(f)[0] - to[0]), abs(self.pos(f)[1] - to[1])) for f in foes)
                if best is None or gap > best[0]:
                    best = (gap, to)
        if not best or best[0] <= 1:
            return False
        with self.refereed(me, "Misty Step"):
            self.use_bonus(me)
            level = self.spend_slot(me, 2)
            # a teleport provokes no opportunity attack: the extension skips a mover marked Disengage (aibridge.lua
            # isDisengaged), as a GM would mark it in FG
            self.s.addEffect(me, "Note: Disengage", True)
            self.s.move(me, best[1][0], best[1][1])
            self.s.removeEffect(me, "Note: Disengage")
            self.sim.say("dice", "%s casts Misty Step (Bonus Action, a level %d slot): teleports to (%g, %g)" % (
                c["name"], level, best[1][0], best[1][1]))
        return True

    def repel(self, me, c, tid):
        """Repelling Blast (Warlock 2; SRD 5.2.1): an Eldritch Blast hit pushes a Large or smaller creature 10 ft
        straight away; used to push a foe off a fallen ally or off the Warlock."""
        if not c.get("repelling_blast") or self.down(tid) or self.span(tid) > 2:
            return
        if not (self.dist(me, tid) <= FT or any(self.down(a) and self.dist(a, tid) <= FT for a in self.allies(me))):
            return
        (hx, hy), (x, y) = self.pos(me), self.pos(tid)
        d = ((x > hx) - (x < hx), (y > hy) - (y < hy))
        if d != (0, 0):
            self.sim.say("dice", "Repelling Blast: %s is pushed 10 ft away from %s" % (self.name(tid), c["name"]))
            self.push(tid, d, 2)

    def span(self, i):
        return max(1, int(round(float(self.sim.by_id(i).get("space") or 5) / 5)))

    def turn_paladin(self, me, c):
        martial.nimbus_tactic(self, me, c)                       # MARTIAL-HIGH: Holy Nimbus (Devotion 20)
        self.lay_on_hands(me, c)
        if high.abjure_tactic(self, me, c):                      # GM 2026-10-26: Abjure Foes (Paladin 9) on three foes
            return
        if self.cast_bless(me, c, 1 if c.get("smite") else 0):  # from level 2 one slot stays for Divine Smite
            return
        self.cast_shield_of_faith(me, c, 1)                      # SIM-MECHANICS-01 (f): Devotion 3, on herself
        tid = self.front_target(me, c)
        if tid is None:
            self.say(c["name"] + " sees no foe and holds position"); return
        # SIM-MECHANICS-01 (f): no foe within her move and reach this turn: Command (Grovel) instead of only walking
        if not [f for f in self.foes(me) if self.dist(me, f) <= speed_ft(c) + 5 and not self.blocked(me, f)] \
                and self.cast_command(me, c, tid, 1 if c.get("smite") else 0):
            self.approach(me, tid, 5)
            return
        move = True
        if c.get("sacred_weapon") and me not in self.sacred and self.channel.get(me):
            # PARTY-04: Sacred Weapon (Devotion 3): Channel Divinity when she takes the Attack action, 10 minutes
            self.approach(me, tid, 5); move = False
            if any(self.dist(me, f) <= FT and not self.blocked(me, f) for f in self.foes(me)):
                self.channel[me] -= 1; self.sacred.add(me)
                self.sim.say("dice", "%s uses Sacred Weapon (Channel Divinity): +%d to attack rolls with the %s for 10 minutes" % (
                    c["name"], c["sacred_weapon"], c["weapon"]["name"]))
        w = dict(c["weapon"], atk=c["weapon"]["atk"] + (c["sacred_weapon"] if me in self.sacred else 0))

        def rider(t, res):
            if res not in ("hit", "crit"):
                return
            if c["weapon"].get("sap") and not self.down(t):
                self.s.setField(t, "sim_sapped", 1)
                self.sapped.setdefault(me, set()).add(t)
                self.sim.say("dice", "Sap: %s has Disadvantage on its next attack roll" % self.name(t))
            if self.searing_smite(me, c, t, res):                # SIM-MECHANICS-01 (f) slice 3
                return
            free = self.free_smite.get(me)
            if (c.get("smite") and self.bonus_free(me) and not self.down(t) and (free or self.slot_free(me))
                    and (res == "crit" or (t == self.focus and self.hp_left(t) >= 4))):
                undead = str(self.sim.by_id(t).get("type", "")).lower() in ("undead", "fiend")
                with self.refereed(me, "Divine Smite", dict({"target": t}, **({"free": "Paladin's Smite"} if free else {}))):
                    self.use_bonus(me)                           # a Bonus Action: once per turn
                    if free:
                        self.free_smite[me], level = False, 1
                    else:
                        level = self.spend_slot(me, 1, highest=True)   # PARTY-04: the highest slot left
                    dice = smite_dice(level, undead)
                    self.sim.say("dice", "%s casts Divine Smite (Bonus Action, %s): %s Radiant%s%s" % (
                        c["name"], "Paladin's Smite, no slot" if free else "a level %d slot" % level, dice,
                        " (Undead or Fiend: +1d8)" if undead else "", ", doubled on the Critical Hit" if res == "crit" else ""))
                    self.s.pcDamage(me, t, dice, 0, res == "crit", "radiant")
                    self.sim.settle()
                martial.smite_protection(self, me)              # MARTIAL-HIGH: Smite of Protection (Devotion 15)

        self.attack_action(me, c, tid, lambda k: w, move=move, rider=rider)

    # ---------------------------------------------------------------- PARTY-02: Warlock
    def turn_warlock(self, me, c):
        focus = self.pick_focus(me)
        tid = focus if focus is not None and (self.sim.sees(me, focus) or focus in self.heard()) else self.nearest_seen(me)
        if tid is None and focus is not None:
            self.sim.pc_advance(me, focus, 120)
            tid = focus if self.sim.sees(me, focus) else None
        if tid is None:
            self.say(c["name"] + " sees no foe and holds position"); return
        if self.hex.get(me, False) is False:                    # SIM-MECHANICS-01 (f) slice 4 (Hex needs the Bonus Action)
            self.misty_step(me, c, 1 if c.get("fireball") else 0)
        if self.cast_hold_person(me, c, tid) or self.cast_hold_monster(me, c, tid) or self.cast_laughter(me, c, tid):
            return
        if not c.get("fireball") and self.cast_burning_hands(me, c, 0):          # SIM-MECHANICS-01 (f) slice 3
            return
        if self.cast_fireball(me, c):                            # PARTY-04: Fiend Spells (Warlock 5)
            return
        cursed = self.hex.get(me, False)                         # False: not concentrating on Hex
        move_hex = cursed is not False and (cursed is None or self.down(cursed))
        new_hex = cursed is False and c.get("hex") and self.slot_free(me) and self.hp_left(tid) > 5
        want_hex = self.bonus_free(me) and self.sim.sees(me, tid) and (move_hex or new_hex)
        self.approach(me, tid, 90 if want_hex else c["weapon"]["reach"])
        if want_hex and self.dist(me, tid) <= 90 and not self.blocked(me, tid):
            if new_hex:
                with self.refereed(me, "Hex", {"target": tid}):
                    self.use_bonus(me)
                    self.resolve_hex(me, c, tid)
                    self.hex[me] = tid
            else:
                self.use_bonus(me)
                self.sim.say("dice", "%s moves Hex to %s (Bonus Action)" % (c["name"], self.name(tid)))
                self.hex[me] = tid
        reach = c["weapon"]["reach"]
        if self.dist(me, tid) > reach or self.blocked(me, tid):
            clear = [f for f in self.foes(me) if self.dist(me, f) <= reach and not self.blocked(me, f)
                     and (self.sim.sees(me, f) or f in self.heard())]
            if not clear:
                self.say(c["name"] + " has no clear shot and holds position"); return
            tid = min(clear, key=lambda f: (self.hex.get(me) != f, self.hp_left(f)))
        # PARTY-04: Scorching Ray (Fiend Spells, Warlock 3) with a Pact slot; one stays for Fireball from level 5
        if self.scorching_ray(me, c, tid, keep=1 if c.get("fireball") else 0):
            return
        beams = c.get("beams", 1)
        with self.refereed(me, c["weapon"]["name"], {"targets": [tid]}) as w:
            self.sim.say("dice", "%s casts Eldritch Blast at %s%s%s" % (c["name"], self.name(tid),
                         " (Agonizing Blast: +%d)" % c.get("spell_mod", 3) if c.get("agonizing") else "",
                         " (%s beams, an attack roll each)" % NUMBERS[beams] if beams > 1 else ""))
            for k in range(beams):                               # PARTY-04: two beams at level 5
                if k and (self.down(tid) or self.dist(me, tid) > reach or self.blocked(me, tid) or high.gone(self, tid)):
                    clear = [f for f in self.foes(me) if self.dist(me, f) <= reach and not self.blocked(me, f)
                             and (self.sim.sees(me, f) or f in self.heard())]
                    if not clear:
                        break
                    tid = min(clear, key=lambda f: (self.hex.get(me) != f, self.hp_left(f)))
                    w["cmd"]["targets"].append(tid)
                hexed = self.hex.get(me) == tid
                res = self.attack(me, tid, c["weapon"], spell=True, bonus_dice="1d6:necrotic" if hexed else "",
                                  note="Hex" if hexed else "")
                if res in ("hit", "crit"):
                    self.repel(me, c, tid)                       # SIM-MECHANICS-01 (f) slice 4
                    high.hurl_tactic(self, me, c, tid)           # CASTER-HIGH: Hurl Through Hell (Fiend 14)

    # ---------------------------------------------------------------- PARTY-04: area and multi-attack spells
    def save_damage(self, me, f, ability, key, dc, dmg, kind, dis=False, origin=None):
        """One creature's saving throw against an area: full damage on a failure, half on a success (dis: Disadvantage).
        GM 2026-10-25 (ruling S4): cover against the origin (the caster, or a Sphere's point) on a Dexterity save, and
        Evasion."""
        mod = self.sim.by_id(f).get(key, 0)
        env = getattr(self.sim, "env", None)
        cover = env.cover_from(tuple(origin or self.pos(me)), f, me) if (env and key == "dex_save" and f != me) else 0
        d20 = self.sim.rng.randint(1, 20)
        gm = getattr(self.sim, "gm_rules", None)
        adv = key == "dex_save" and self.sim.by_id(f).get("dodging") and not (gm and gm.incapacitated(f))   # Dodge
        trait = self.sim.save_tweak(f, key[:3]) if hasattr(self.sim, "save_tweak") else {}   # Magic Resistance ...
        adv = adv or bool(trait.get("adv"))
        import more_spells                                       # SPELL-EFFECTS-01: Slow -2, Haste Advantage
        spell_bonus, spell_adv = more_spells.save_mod(self.sim, f, key)
        mod += spell_bonus
        adv = adv or bool(spell_adv)
        if dis and not adv:
            d20 = min(d20, self.sim.rng.randint(1, 20))
        elif adv and not dis:
            d20 = max(d20, self.sim.rng.randint(1, 20))
        saved = d20 + mod + cover >= dc and not (gm and gm.auto_fail(f, key))   # SIM-MECHANICS-01 (f): Paralyzed, Unconscious
        if hasattr(self.sim, "save_result"):
            saved = self.sim.save_result(f, saved, ability)                     # Legendary Resistance
        amount = save_for_half(dmg, saved)
        evade = key == "dex_save" and gm is not None and gm.has_evasion(f)
        if evade:
            amount = 0 if saved else dmg // 2
        self.sim.say("dice", "%s %s save: d20 %d %+d%s = %d vs DC %d -> %s, %d %s damage" % (
            self.name(f), ability, d20, mod, " (cover +%d)" % cover if cover else "", d20 + mod + cover, dc,
            ("success" + (" (Evasion: none)" if evade else " (half)")) if saved else ("failure" + (" (Evasion: half)" if evade else "")),
            amount, kind))
        if amount:
            if kind == "fire":                                   # GM 2026-10-26 (and T10): oil on it or under it burns
                import traps
                traps.of(self.sim).ignite_creatures([f], me, "%s's fire" % self.sim.by_id(me)["name"])
            self.s.pcDamage(me, f, "", amount, False, kind)
            self.sim.settle()

    def walled(self, a, b):
        """Squares a and b with a wall between them."""
        g = self.sim.sc.get("grid", 50)
        return bool(self.sim.wall_segs) and self.sim.map_walls.blocked((a[0] * g, a[1] * g), (b[0] * g, b[1] * g),
                                                                        self.sim.wall_segs)

    def fireball_point(self, me, c, slot_level, radius=20, kind="fire", reach=150, spare=None):
        """Fireball: the point within 150 ft (a square's center or corner, no wall on the way) whose 20-ft-radius Sphere
        holds the most foes the party has located, two at least. Foes count when the center of their square is within
        20 ft; an ally (the caster too, a fallen one too) must be outside the 9x9-square box around the point, the
        stricter grid reading, unless Sculpt Spells (Evoker 6) spares it: 1 + the spell's level allies she can see.
        GM 2026-10-23: spare = how many creatures Careful Spell protects (the Sorcerer's Charisma modifier; the caster
        may be one of them, seen or not). Returns (point, foes inside, allies spared) or None."""
        u = self.sim.sc.get("units", 5)
        feet = lambda p: (p[0] * u, p[1] * u)
        here, located = self.pos(me), set(self.located(me))
        foes = [(f, self.pos(f)) for f in self.foes(me) if not self.wasted(f, kind)]     # SIM-MECHANICS-01 (a)
        if sum(1 for f, _ in foes if f in located) < 2:
            return None
        friends = [(a, self.pos(a)) for a in [me] + self.allies(me) if not self.deaths.get(a, {}).get("dead")]
        sculpt = spare if spare is not None else 1 + slot_level if c.get("sculpt_spells") else 0
        points = set()
        for f, (x, y) in foes:
            if f in located:
                points |= {(x, y)} | {(x + dx, y + dy) for dx in (-0.5, 0.5) for dy in (-0.5, 0.5)}
        for i, (f, p) in enumerate(foes):
            for g2, q in foes[i + 1:]:
                if f in located and g2 in located:
                    points.add((round(p[0] + q[0]) / 2.0, round(p[1] + q[1]) / 2.0))
        best = None
        for pt in sorted(points):
            if max(abs(pt[0] - here[0]), abs(pt[1] - here[1])) * u > reach or self.walled(here, pt):
                continue
            inside = [f for f, q in foes if in_sphere(feet(pt), feet(q), radius) and not self.walled(pt, q)]
            n = sum(1 for f in inside if f in located)
            if n < 2:
                continue
            caught = [a for a, q in friends if max(abs(q[0] - pt[0]), abs(q[1] - pt[1])) * u <= radius + 0.01
                      and not self.walled(pt, q)]
            if caught and ((me in caught and spare is None) or len(caught) > sculpt
                           or (spare is None and not all(self.sim.sees(me, a) for a in caught))):
                continue
            score = (n, -len(caught), self.focus in inside, sum(self.hp_left(f) for f in inside))
            if best is None or score > best[0]:
                best = (score, pt, inside, caught)
        return best and best[1:]

    def cast_fireball(self, me, c):
        if not c.get("fireball") or not (self.slot_free(me, 3) or high.free_how(self, me, "Fireball")):   # Signature Spells
            return False
        pool = self.pools.get(me) or []
        level = min([lv for lv in range(3, len(pool) + 1) if pool[lv - 1] > 0] or [3])
        found = self.fireball_point(me, c, level)
        if not found:
            return False
        pt = found[0]
        free = high.arm(self, me, "Fireball")                    # CASTER-HIGH: Signature Spells (no slot), Overchannel
        if not free and high.overchannel_tactic(self, me, c, "Fireball"):
            high.overchannel_on(self, me)
        with self.refereed(me, "Fireball", dict({"x": pt[0], "y": pt[1]}, **({"free": free} if free else {})), {"origin": list(pt)}):
            try:
                self.resolve_fireball(me, c, *found)
            finally:
                high.disarm(self, me)
        return True

    def resolve_fireball(self, me, c, pt, inside, spared, kind="fire", dis=(), empower=0, spare_why="Sculpt Spells"):
        """Fireball at pt: a level 3+ slot, a Dexterity save for each creature inside, Sculpt Spells sparing `spared`.
        LIVE-PLAY-01: shared with live play. GM 2026-10-23 (the Sorcerer's Metamagic): kind (Transmuted Spell), dis (the
        creatures with Disadvantage on the save: Heightened Spell), empower (Empowered Spell's dice), spare_why (Careful
        Spell spares creatures too); Elemental Affinity adds the Charisma modifier."""
        level = self.spend_slot(me, 3)
        dice = fireball_dice(level)
        if empower:
            dmg, before, after, n = empowered_roll(self.sim.rng, dice, empower)
            self.sim.say("dice", "Empowered Spell: %s rolls %s, %d of the lowest rolled again -> %s" % (c["name"], before, n, after))
        else:
            dmg = roll(self.sim.rng, dice)
        if high.maxed(self.sim, me):                             # CASTER-HIGH: Overchannel, the dice at their highest
            dmg = high.max_total(dice)
            self.sim.say("dice", "Overchannel: %s at its maximum, %d" % (dice, dmg))
        dc, plus = self.spell_dc(c), self.affinity(c, kind)
        if plus:
            dice, dmg = "%s+%d (Elemental Affinity)" % (dice, plus), dmg + plus
        evoke = high.empowered(c, "Fireball")                    # GM 2026-10-26: Empowered Evocation (Evoker 10)
        if evoke:
            dice, dmg = "%s+%d (Empowered Evocation)" % (dice, evoke), dmg + evoke
        self.sim.say("dice", "%s casts Fireball (a level %d slot) at (%g, %g): 20-ft-radius Sphere, DC %d Dexterity save, "
                     "%s = %d %s, half on a success (%d foes inside%s)" % (
                         c["name"], level, pt[0], pt[1], dc, dice, dmg, kind.capitalize(), len(inside), "" if spared else ", no ally"))
        if spared:
            self.sim.say("dice", "%s: %s succeed%s on the save and take no damage" % (
                spare_why, ", ".join(self.name(a) for a in spared), "s" if len(spared) == 1 else ""))
        for f in inside:
            if not self.down(f):
                self.save_damage(me, f, "Dexterity", "dex_save", dc, dmg, kind, dis=f in dis, origin=pt)

    def scorching_ray(self, me, c, tid, keep=0):
        """Scorching Ray at a foe with 10 HP or more (three rays, +1 per slot level above 2; a ranged spell attack
        each, 2d6 Fire; a ray goes to another foe in sight within 120 ft once the target drops). The Wizard uses a level
        2 slot only (higher ones stay for Fireball); keep = slots that must remain."""
        free = high.free_how(self, me, "Scorching Ray")          # CASTER-HIGH: Spell Mastery, no slot
        if not c.get("scorching_ray") or not (free or self.slot_free(me, 2) and self.slots[me] > keep) or self.wasted(tid, "fire"):
            return False
        pool = self.pools.get(me) or []
        if not free and c.get("class") == "wizard" and not (len(pool) > 1 and pool[1] > 0):
            return False
        if self.hp_left(tid) < 10 or self.dist(me, tid) > 120 or self.blocked(me, tid) or not self.sim.sees(me, tid):
            return False
        with self.refereed(me, "Scorching Ray", dict({"targets": [tid]}, **({"free": free} if free else {}))) as w:
            level = high.pay(self, me, "Scorching Ray", 2)
            n = scorching_rays(level)
            ray = {"name": "Scorching Ray", "atk": c.get("spell_atk", 5), "reach": 120, "dmg": "2d6", "crit": 20, "dmgtype": "fire",
                   "one_affinity": True}
            self.sim.say("dice", "%s casts Scorching Ray (a level %d slot) at %s: %d rays, a ranged spell attack each, 2d6 Fire" % (
                c["name"], level, self.name(tid), n))
            for k in range(n):
                if self.down(tid):
                    clear = [f for f in self.foes(me) if self.dist(me, f) <= 120 and not self.blocked(me, f)
                             and self.sim.sees(me, f)]
                    if not clear:
                        break
                    tid = min(clear, key=lambda f: (f != self.focus, self.hp_left(f)))
                    w["cmd"]["targets"].append(tid)
                hexed = self.hex.get(me) == tid
                self.attack(me, tid, ray, spell=True, bonus_dice="1d6:necrotic" if hexed else "", note="Hex" if hexed else "")
        return True

    def turn_rogue(self, me, c):
        focus = self.pick_focus(me)
        seen = [f for f in self.foes(me) if self.sim.sees(me, f)] or self.located(me)
        if not seen:
            self.say(c["name"] + " sees no foe and holds position"); return
        def setup(f):
            return self.ally_next_to(f, me) or f in self.guided or (me, f) in self.vexed
        tid = min(seen, key=lambda f: (not setup(f), f != focus, self.hp_left(f), self.dist(me, f)))
        melee, bow = c["weapon"], c.get("ranged")
        if c.get("steady_aim") and self.bonus_free(me) and not setup(tid) and self.pos(me) == self.turn_pos.get(me):
            # PARTY-04: Steady Aim (Rogue 3): not moved this turn: Advantage on the next attack roll, Speed 0
            here = None
            if self.dist(me, tid) <= FT and not self.blocked(me, tid):
                here = melee
            elif bow and not self.enemy_next_to(me) and self.dist(me, tid) <= bow["reach"] \
                    and not self.blocked(me, tid) and self.sim.sees(me, tid):
                here = bow
            if here is not None and self.sim.attack_mode_for(me, tid) != "dis":
                self.use_bonus(me)
                self.sim.say("dice", "%s uses Steady Aim (Bonus Action, has not moved): Advantage on the next attack "
                             "roll, Speed 0 this turn" % c["name"])
                self.attack(me, tid, here, sneak=True, extra_adv=[True])
                return
        if self.ally_next_to(tid, me) or not bow:
            self.approach(me, tid, 5)
            if self.attack(me, tid, melee, sneak=True) is not None:
                return
        if bow and not self.enemy_next_to(me):
            self.approach(me, tid, bow["reach"])
            if self.attack(me, tid, bow, sneak=True) is not None:
                return
        self.approach(me, tid, 5)
        self.attack(me, tid, melee, sneak=True)

    # ---------------------------------------------------------------- PARTY-04: Life Domain and Spirit Guardians
    def preserve_life(self, me, c):
        """Preserve Life (Life 3; Channel Divinity, Magic action): 5 x Cleric level hit points shared among Bloodied
        creatures within 30 ft (her too), none above half its hit point maximum. Used for a fallen ally, or when two or
        more Bloodied creatures would get 8 hit points or more together. Fallen allies first, then the lowest."""
        if not c.get("preserve_life") or not self.channel.get(me):
            return False
        cands = [a for a in [me] + self.allies(me) if not self.deaths.get(a, {}).get("dead")
                 and (a == me or (self.dist(me, a) <= 30 and not self.blocked(me, a)))
                 and self.hp_left(a) * 2 <= self.sim.by_id(a)["hp"]]
        room = {a: self.sim.by_id(a)["hp"] // 2 - self.hp_left(a) for a in cands}
        cands = [a for a in cands if room[a] > 0]
        fallen = [a for a in cands if self.down(a)]
        if not fallen and (len(cands) < 2 or sum(room[a] for a in cands) < 8):
            return False
        left, heals = 5 * c.get("level", 1), []
        for a in sorted(cands, key=lambda a: (not self.down(a), self.hp_left(a))):
            if left <= 0:
                break
            heals.append((a, min(room[a], left)))
            left -= heals[-1][1]
        self.channel[me] -= 1
        self.sim.say("dice", "%s uses Preserve Life (Channel Divinity, Magic action): %s" % (
            c["name"], ", ".join("%s %d HP" % ("herself" if a == me else self.name(a), h) for a, h in heals)))
        for a, h in heals:
            if self.down(a):
                self.revive(a, h)
            else:
                self.s.heal(a, h)
        return True

    def healing_bonus(self, me, c, level, others):
        """Disciple of Life (Life 3): + 2 + slot level to each creature; Blessed Healer (Life 6): she regains 2 + slot
        level when the spell heals someone else."""
        if c.get("blessed_healer") and others and not self.down(me):
            self.s.heal(me, 2 + level)
            self.sim.say("dice", "%s regains %d HP (Blessed Healer)" % (c["name"], 2 + level))
        return 2 + level if c.get("disciple_of_life") else 0

    def mass_cure(self, me, c):
        """Mass Cure Wounds (Life Domain spell at Cleric 9; SRD 5.2.1: Action, a level 5+ slot, a point within 60 ft,
        30-ft-radius Sphere, up to 6 creatures, 5d8 + the spellcasting modifier each, +1d8 per slot level above 5) when
        three allies or more (she counts) at half their Hit Points or fewer are inside, one of them at 0 HP or two at
        a quarter or fewer. The center is one of them (no wall to her, in sight)."""
        divine = high.armed(self, me) == high.DIVINE              # CASTER-HIGH: Divine Intervention casts it, no slot
        if not (c.get("mass_cure_wounds") or divine) or not (divine or self.slot_free(me, 5)) or self.incapacitated(me):
            return False
        hurt = [a for a in [me] + self.allies(me) if not self.deaths.get(a, {}).get("dead")
                and self.hp_left(a) * 2 <= self.sim.by_id(a)["hp"]]
        best = None
        for p in hurt:
            if self.dist(me, p) > 60 or self.blocked(me, p) or not (p == me or self.sim.sees(me, p)):
                continue
            inside = [a for a in hurt if a == p or (self.dist(p, a) <= 30 and not self.walled(self.pos(p), self.pos(a)))][:6]
            low = sum(1 for a in inside if self.down(a) or self.hp_left(a) * 4 <= self.sim.by_id(a)["hp"])
            if len(inside) >= 3 and (any(self.down(a) for a in inside) or low >= 2) and (best is None or len(inside) > len(best[1])):
                best = (p, inside)
        if not best:
            return False
        p, inside = best
        with self.refereed(me, "Mass Cure Wounds", dict({"targets": list(inside)}, **({"free": high.DIVINE} if divine else {}))):
            level = self.spend_slot(me, 5)
            extra = self.healing_bonus(me, c, level, any(a != me for a in inside))
            dice = "%dd8+%d" % (level, c.get("spell_mod", 3))
            for a in inside:
                heal = high.heal_roll(self.sim.rng, c, dice) + extra
                self.sim.say("dice", "%s casts Mass Cure Wounds (a level %d slot) on %s: %s%s = %d HP" % (
                    c["name"], level, self.name(a), dice, " + %d Disciple of Life" % extra if extra else "", heal))
                if self.down(a):
                    self.revive(a, heal)
                else:
                    self.s.heal(a, heal)
        return True

    def healing_word(self, me, c, dying):
        """Healing Word (Bonus Action) on a fallen ally; Mass Healing Word (Life 5, a level 3 slot) for two or more."""
        if len(dying) >= 2 and c.get("mass_healing_word") and self.slot_free(me, 3):
            with self.refereed(me, "Mass Healing Word", {"targets": dying[:6]}):
                level = self.spend_slot(me, 3)
                extra = self.healing_bonus(me, c, level, any(a != me for a in dying[:6]))
                self.use_bonus(me)                               # SIM-MECHANICS-01 (f): a Bonus Action
                for a in dying[:6]:
                    heal = high.heal_roll(self.sim.rng, c, "2d4+%d" % c.get("spell_mod", 3)) + extra
                    self.sim.say("dice", "%s casts Mass Healing Word (Bonus Action, a level %d slot) on %s: 2d4 + %d%s = %d HP" % (
                        c["name"], level, self.name(a), c.get("spell_mod", 3), " + %d Disciple of Life" % extra if extra else "", heal))
                    self.revive(a, heal)
            return
        a = dying[0]
        with self.refereed(me, "Healing Word", {"target": a}):
            n = 2 * self.slot_wanted(me, 1)                      # +2d4 for each slot level above 1 (SRD 5.2.1)
            heal = high.heal_roll(self.sim.rng, c, "%dd4+%d" % (n, c.get("spell_mod", 3)))
            level = self.spend_slot(me)
            self.use_bonus(me)                                   # SIM-MECHANICS-01 (f): a Bonus Action
            extra = self.healing_bonus(me, c, level, a != me)    # play-test 2026-11-02: Blessed Healer heals others only
            self.sim.say("dice", "%s casts Healing Word on %s (Bonus Action%s): %dd4 + %d%s = %d HP" % (
                c["name"], self.sim.by_id(a)["name"], ", a level %d slot" % level if level > 1 else "", n,
                c.get("spell_mod", 3), " + %d Disciple of Life" % extra if extra else "",
                heal + extra))
            self.revive(a, heal + extra)

    def in_guardians(self, me, f):
        return not self.down(me) and self.dist(me, f) <= 15 and not self.blocked(me, f)

    def guardian_save(self, me, f, once_key=None, when="end"):
        """A Wisdom save against Spirit Guardians (3d8 Radiant, half on a success; a creature saves once per turn).
        when (REFEREE-02, the referee checks it): "end" of its turn in the Emanation, "moved": the Emanation reached it."""
        if self.down(f) or me not in self.guardians:
            return
        if once_key is not None:
            if (f, once_key) in self.guardian_saved:
                return
            self.guardian_saved.add((f, once_key))
        c, level = self.sim.by_id(me), self.guardians[me]
        ref = getattr(self.sim, "referee", None)
        with ref.watch_area(me, "Spirit Guardians", f, when, level) if ref else contextlib.nullcontext():
            dice = guardians_dice(level)
            dmg = roll(self.sim.rng, dice)
            kind = self.guardian_kind(c)
            self.sim.say("dice", "Spirit Guardians (%s): %s = %d %s on %s" % (c["name"], dice, dmg, kind.capitalize(), self.name(f)))
            actor, self.actor = self.actor, me
            self.save_damage(me, f, "Wisdom", "wis_save", c.get("spell_dc", 13), dmg, kind)
            self.actor = actor

    def guardian_kind(self, c):
        """Radiant. BY-THE-SRD-01: with the GM's By the SRD switch on, Necrotic for an evil caster, as the spell says."""
        live = getattr(self.sim, "live", None)
        return "necrotic" if live and live.by_srd and "evil" in str(c.get("alignment") or "").lower() else "radiant"

    def guardian_move(self, me, tid):
        """Walk toward the target with Spirit Guardians up: a foe the Emanation now reaches makes its save."""
        before = self.guardian_foes(me)
        self.approach(me, tid, 5)
        self.guardians_reach(me, before)

    def guardian_foes(self, me):
        return {f for f in self.foes(me) if self.in_guardians(me, f)}

    def guardians_reach(self, me, before):
        """Spirit Guardians moved with its cleric (REFEREE-02: also each step of a live walk): a foe the Emanation now
        reaches that it didn't (`before`) makes its save, once a turn. Returns the foes it reaches now."""
        now = self.guardian_foes(me)
        for f in sorted(now - before):
            self.guardian_save(me, f, self.s.turnSerial, when="moved")
        return now

    def cast_guardians(self, me, c, focus):
        """Spirit Guardians (Cleric 5, a level 3 slot, Concentration) when a foe the party located is within her move
        plus 15 ft; then she walks toward the focus target. Bless she concentrated on ends."""
        if not c.get("spirit_guardians") or me in self.guardians or not self.slot_free(me, 3) or focus is None:
            return False
        if not [f for f in self.located(me) if self.dist(me, f) <= speed_ft(c) + 15]:
            return False
        with self.refereed(me, "Spirit Guardians"):
            self.resolve_guardians(me, c)
        self.guardian_move(me, focus)
        return True

    def resolve_guardians(self, me, c):
        """Spirit Guardians: Concentration, a level 3+ slot, the 15-ft Emanation. LIVE-PLAY-01: shared."""
        self.start_concentration(me, "Spirit Guardians")         # SIM-MECHANICS-01 (e): Bless she held ends
        level = self.spend_slot(me, 3)
        self.guardians[me] = level
        self.sim.say("dice", "%s casts Spirit Guardians (a level %d slot, Concentration): 15-ft Emanation, DC %d Wisdom "
                     "save, %s Radiant, half on a success" % (c["name"], level, c.get("spell_dc", 13), guardians_dice(level)))

    def turn_ended(self, ctid):
        """Hook from the run loop when a combatant's turn ends: Spirit Guardians' save for a foe that ends its turn in
        the Emanation."""
        for me in list(self.guardians):
            if self.side(ctid) != self.side(me) and self.in_guardians(me, ctid):
                self.guardian_save(me, ctid)
        if self.__dict__.get("acid_later"):                      # SPELL-CASTER-01: Acid Arrow's later damage
            import live_general
            live_general.turn_ended(self, ctid)
        high.hurl_return(self, ctid)                             # CASTER-HIGH: back from the Lower Planes

    def sacred_flame(self, me, c, tid):
        """Sacred Flame (cantrip, 60 ft, a creature she can see): Dexterity save or 2d8 Radiant at level 5."""
        if me in self.guardians:
            self.guardian_move(me, tid)
        else:
            self.approach(me, tid, 60)
        if self.dist(me, tid) > 60 or self.blocked(me, tid) or not self.sim.sees(me, tid):
            clear = [f for f in self.foes(me) if self.dist(me, f) <= 60 and not self.blocked(me, f) and self.sim.sees(me, f)]
            if not clear:
                self.say(c["name"] + " has no foe in sight for Sacred Flame"); return
            tid = min(clear, key=lambda f: (f != self.focus, self.hp_left(f)))
        t = self.sim.by_id(tid)
        with self.refereed(me, "Sacred Flame", {"target": tid}):
            d20 = self.sim.rng.randint(1, 20)
            total, dc = d20 + t.get("dex_save", 0), c.get("spell_dc", 13)
            saved = total >= dc
            self.sim.say("dice", "%s casts Sacred Flame at %s: Dexterity save d20 %d %+d = %d vs DC %d -> %s" % (
                c["name"], t["name"], d20, t.get("dex_save", 0), total, dc, "saved" if saved else "failed"))
            if not saved:
                potent = c.get("spell_mod", 0) if c.get("potent_spellcasting") else 0   # Blessed Strikes (Cleric 7)
                if potent:
                    self.sim.say("dice", "Potent Spellcasting: +%d to Sacred Flame's damage" % potent)
                self.s.pcDamage(me, tid, c["sacred_flame"], potent, False, "radiant")
                self.sim.settle()
                high.improved_blessed(self, me, c, {"level": 0, "name": "Sacred Flame"}, True)   # group 3

    def turn_cleric(self, me, c):
        dying = [a for a in self.allies(me) if self.down(a) and not self.deaths.get(a, {}).get("dead")]
        def can_heal(a):   # Healing Word: a creature you can see within 60 ft
            return self.dist(me, a) <= 60 and not self.blocked(me, a) and self.sim.sees(me, a)
        if self.preserve_life(me, c):                            # PARTY-04: a Magic action
            rest = [a for a in self.allies(me) if self.down(a) and not self.deaths.get(a, {}).get("dead") and can_heal(a)]
            if rest and self.slot_free(me):
                self.healing_word(me, c, rest)
            return
        if high.divine_tactic(self, me, c):                      # CASTER-HIGH: Divine Intervention, no level 5 slot
            return
        if self.mass_cure(me, c):                                # level 9: Mass Cure Wounds (her Action and slot)
            return
        if dying and self.slot_free(me) and not any(can_heal(a) for a in dying):
            a = min(dying, key=lambda a: self.dist(me, a))
            self.say("%s moves to see %s" % (c["name"], self.sim.by_id(a)["name"]))
            self.sim.pc_advance(me, a, 5)
        dying = [a for a in dying if can_heal(a)]
        if dying and self.slot_free(me):
            self.healing_word(me, c, dying)
        elif [a for a in self.allies(me) if self.down(a) and not self.deaths[a]["dead"] and not self.deaths[a]["stable"]]:
            # no slot left: the Help action stabilizes a creature at 0 HP (DC 10 Wisdom (Medicine), SRD 5.2.1)
            a = min([a for a in self.allies(me) if self.down(a) and not self.deaths[a]["dead"] and not self.deaths[a]["stable"]],
                    key=lambda a: self.dist(me, a))
            self.approach(me, a, 5)
            if self.dist(me, a) <= FT:
                d20 = self.sim.rng.randint(1, 20)
                total = d20 + c.get("medicine", 0)
                ok = total >= 10
                self.sim.say("dice", "%s takes the Help action to stabilize %s: Wisdom (Medicine) d20 %d %+d = %d vs DC 10 -> %s" % (
                    c["name"], self.sim.by_id(a)["name"], d20, c.get("medicine", 0), total, "Stable" if ok else "failure"))
                if ok:
                    self.deaths[a].update(successes=0, failures=0, stable=True)
                    self.s.setField(a, "sim_dying", 0)
                return
        focus = self.pick_focus(me) or self.nearest_seen(me)
        if self.cast_guardians(me, c, focus):                    # PARTY-04: Spirit Guardians before Bless (5)
            return
        reserve = 1                                               # one slot kept for Healing Word
        if self.turn_undead(me, c):                              # SIM-MECHANICS-01 (f) slice 4: a Magic action
            return
        if focus is not None and self.cast_bless(me, c, reserve):
            return
        if self.cure_ally(me, c, reserve):                     # an ally next to her at a third of its HP or less
            return
        # SIM-MECHANICS-01 (f): the Bonus Action: the Spiritual Weapon she holds strikes, else Spiritual Weapon (3) or
        # Shield of Faith when she holds no Concentration (someone else holds Bless); then her action as before
        if focus is not None and not self.spiritual_strike(me, c) \
                and not self.cast_spiritual_weapon(me, c, focus, reserve):
            self.cast_shield_of_faith(me, c, reserve)
        lone = focus is not None and (len(self.foes(me)) == 1 or self.hp_left(focus) >= 25)
        if lone and self.slot_free(me) and self.slots[me] > reserve and self.dist(me, focus) <= 120 \
                and self.sim.sees(me, focus) and not self.blocked(me, focus):
            with self.refereed(me, "Guiding Bolt", {"target": focus}):
                self.spend_slot(me)
                self.resolve_guiding_bolt(me, c, focus)
            return
        if focus is None:
            self.say(c["name"] + " sees no foe and holds position"); return
        # SIM-MECHANICS-01 (f): Command (Grovel) on the focus when two allies or more are next to it (they get Advantage
        # while it lies Prone, and it loses its turn); one slot stays for Healing Word
        if len([a for a in self.allies(me) if not self.down(a) and self.dist(a, focus) <= FT]) >= 2 \
                and self.hp_left(focus) >= 15 and self.cast_command(me, c, focus, reserve):
            return
        if self.divine_spark(me, c, focus):                      # SIM-MECHANICS-01 (f) slice 4: a spare Channel Divinity
            return
        if c.get("sacred_flame"):                                # PARTY-04: 2d8 from level 5 beats the Warhammer
            self.sacred_flame(me, c, focus)
            return
        self.approach(me, focus, 5)
        if self.attack(me, focus, c["weapon"]) is None:
            near = [f for f in self.foes(me) if self.dist(me, f) <= FT and not self.blocked(me, f)]
            if near:
                self.attack(me, near[0], c["weapon"])

    # ---------------------------------------------------------------- GM 2026-10-23: Sorcerer
    def turn_sorcerer(self, me, c):
        """The computer-played Sorcerer (the test hero Hero 10, sim/parties/srd_sorcerer.json; a built Sorcerer): its own
        tools first (sim/live_sorcery.py), then the Wizard's spell choices (Sleep, the areas, Fireball, Scorching Ray,
        Fire Bolt; a slot kept for Shield).
        - Bonus Action: Innate Sorcery once a foe is in sight; or Font of Magic (a slot from Sorcery Points) when no
          slot is left; or a Quickened Fireball (2 points) when Innate Sorcery is already running.
        - Careful Spell (1 point): a Fireball that would catch allies, sparing up to the Charisma modifier of them,
          when it catches more foes than any point without allies."""
        if not self.sorcery_bonus(me, c) and self.quickened_fireball(me, c):
            pass                                                 # the Action follows: a cantrip (no other levelled spell)
        focus = self.pick_focus(me)
        if focus is not None and self.sim.sees(me, focus) and self.cast_hold_monster(me, c, focus, least_hp=40):
            pass                                                 # level 9: Hold Monster on a strong foe
        elif not self.careful_fireball(me, c):
            self.turn_wizard(me, c)
        if not self.down(me):
            self.sorcery_bonus(me, c)                            # a foe came in sight after moving: for the next turns

    def sorcery_bonus(self, me, c):
        """The Bonus Action, once a foe is in sight: Innate Sorcery; or Font of Magic (a slot of level 3 at most from
        Sorcery Points) when no slot is left."""
        import live_sorcery as ls
        if not self.bonus_free(me) or self.incapacitated(me) or \
                not any(self.sim.sees(me, f) and self.dist(me, f) <= 150 for f in self.located(me)):
            return False
        if not self.innate_on(me) and ls.innate_left(self, me) > 0:
            ls.unleash(self, me, c)
            return True
        if not sum(self.pools.get(me) or [self.slots.get(me, 0)]):
            lv = max([lv for lv, cost in ls.CREATE_COST.items() if cost <= ls.points(self, me)
                      and ls.sorcerer_level(c) >= ls.CREATE_LEVEL[lv] and lv <= 3] or [0])
            if lv:
                self.use_bonus(me)
                ls.create_slot(self, me, c, lv)
                return True
        return False

    def fireball_level(self, me):
        pool = self.pools.get(me) or []
        return min([lv for lv in range(3, len(pool) + 1) if pool[lv - 1] > 0] or [3])

    def quickened_fireball(self, me, c):
        import live_sorcery as ls
        if "Quickened Spell" not in (c.get("metamagic") or []) or (ls.points(self, me) < 2 and not ls.apotheosis_free(self, me)) \
                or not self.bonus_free(me) \
                or not c.get("fireball") or not self.slot_free(me, 3):
            return False
        found = self.fireball_point(me, c, self.fireball_level(me))
        if not found:
            return False
        pt = found[0]
        with self.refereed(me, "Fireball", {"x": pt[0], "y": pt[1]}, {"origin": list(pt)}):
            how = ls.charge(self, me, 2)                         # SORCERER-20: Arcane Apotheosis may pay it
            self.use_bonus(me)
            self.quickened_turn[me] = self.s.turnSerial
            self.sim.say("dice", "%s uses Quickened Spell on Fireball (%s): cast as a Bonus Action" % (c["name"], how))
            self.resolve_fireball(me, c, *found)
        return True

    def careful_fireball(self, me, c):
        import live_sorcery as ls
        if "Careful Spell" not in (c.get("metamagic") or []) or (ls.points(self, me) < 1 and not ls.apotheosis_free(self, me)) \
                or not c.get("fireball") \
                or not self.slot_free(me, 3) or getattr(self, "quickened_turn", {}).get(me) == self.s.turnSerial:
            return False
        level = self.fireball_level(me)
        plain, careful = self.fireball_point(me, c, level), self.fireball_point(me, c, level, spare=ls.cha_mod(c))
        if not careful or not careful[2] or (plain and len(plain[1]) >= len(careful[1])):
            return False
        pt, inside, spared = careful
        with self.refereed(me, "Fireball", {"x": pt[0], "y": pt[1]}, {"origin": list(pt)}):
            self.sim.say("dice", "%s uses Careful Spell on Fireball (%s)" % (c["name"], ls.charge(self, me, 1)))
            self.resolve_fireball(me, c, pt, inside, spared, spare_why="Careful Spell")
        return True

    def turn_wizard(self, me, c):
        focus = self.pick_focus(me)
        tid = focus if focus is not None and (self.sim.sees(me, focus) or focus in self.heard()) else self.nearest_seen(me)
        if tid is None:
            seen_any = self.nearest_seen(me)
            if focus is not None:
                self.sim.pc_advance(me, focus, 120)
                tid = focus if self.sim.sees(me, focus) else None
            if tid is None:
                self.say(c["name"] + " sees no foe and holds position"); return
        # her one slot is Shield's unless Magic Missile surely removes a foe that is on her or on a fallen ally
        def pressing(f):
            return self.dist(f, me) <= FT or any(self.down(a) and self.dist(f, a) <= FT for a in self.allies(me))
        missile = c.get("class") == "wizard" or c.get("magic_missile")     # GM 2026-10-23: a Sorcerer prepares it
        sure = [f for f in self.foes(me) if self.hp_left(f) <= 6 and pressing(f) and self.sim.sees(me, f)
                and self.dist(me, f) <= 120 and not self.blocked(me, f)] if missile else []
        free = high.free_how(self, me, "Magic Missile")          # CASTER-HIGH: Spell Mastery, no slot
        if sure and (free or self.slot_free(me)):
            f = sure[0]
            with self.refereed(me, "Magic Missile", dict({"target": f}, **({"free": free} if free else {}))):
                high.pay(self, me, "Magic Missile", 1)
                self.sim.say("dice", "%s casts Magic Missile at %s (three darts, no attack roll)" % (c["name"], self.sim.by_id(f)["name"]))
                self.s.pcDamage(me, f, "3d4", 3, False, "force")
                self.sim.settle()
            return
        self.misty_step(me, c, 1)                                # SIM-MECHANICS-01 (f) slice 4: away from a foe beside her
        if self.cast_sleep(me, c):                               # SIM-MECHANICS-01 (f): two foes or more
            return
        # SIM-MECHANICS-01 (f) slice 3: areas when two foes or more are caught and no ally (one slot stays for Shield)
        if self.cast_thunderwave(me, c, 1) or self.cast_burning_hands(me, c, 1):
            return
        if not c.get("fireball") and self.cast_shatter(me, c, 1):
            return
        if self.cast_cone_of_cold(me, c):                        # level 9: Cone of Cold before Fireball
            return
        if self.cast_fireball(me, c):                            # PARTY-04: Fireball (5), Scorching Ray (3)
            return
        if self.cast_ice_knife(me, c, tid, 1):                   # SIM-MECHANICS-01 (f) slice 3
            return
        if c.get("ray_of_frost") and tid is not None and self.known.get((self.kind(tid), "fire")) in ("immune", "resistant") \
                and not self.wasted(tid, "cold"):
            ray = self.frost_weapon(c)                           # the target ignores or resists Fire: Ray of Frost
            self.approach(me, tid, ray["reach"])
            self.say("%s uses Ray of Frost at %s (its kind %s Fire)" % (
                c["name"], self.name(tid), "ignores" if self.wasted(tid, "fire") else "resists"))
            if self.attack(me, tid, ray, spell=True) is not None:
                return
        tid = self.useful_target(me, tid, c["weapon"])           # SIM-MECHANICS-01 (a): not at a kind seen ignoring fire
        if tid is None:
            hurt = [f for f in self.located(me) if not self.wasted(f, "force") and self.dist(me, f) <= 120
                    and self.sim.sees(me, f) and not self.blocked(me, f)]
            if hurt and (free or self.slot_free(me)) and missile:
                f = min(hurt, key=lambda f: self.hp_left(f))
                with self.refereed(me, "Magic Missile", dict({"target": f}, **({"free": free} if free else {}))):
                    high.pay(self, me, "Magic Missile", 1)
                    self.sim.say("dice", "%s casts Magic Missile at %s (three darts, no attack roll)" % (c["name"], self.name(f)))
                    self.s.pcDamage(me, f, "3d4", 3, False, "force")
                    self.sim.settle()
            else:
                self.say("%s has no damage the foes do not ignore and holds her action" % c["name"])
            return
        self.approach(me, tid, c["weapon"]["reach"])
        if self.scorching_ray(me, c, tid, keep=1):               # a slot stays for Shield
            return
        self.attack(me, tid, c["weapon"], spell=True)

    # ---------------------------------------------------------------- PARTY-03: Bard
    def bard_weapon(self, me, c):
        """The melee weapon: Shillelagh's while the spell runs, the plain weapon otherwise."""
        on = self.shillelagh.get(me, 0) >= self.s.round()
        return (c.get("shillelagh") if on and c.get("shillelagh") else c["weapon"]), on

    def inspire(self, me, c):
        """Bonus Action: a Bardic Inspiration die to the ally within 60 ft who attacks most and has none."""
        if not self.bi_uses.get(me) or not self.bonus_free(me):
            return False
        def rank(i):
            cls = self.sim.by_id(i).get("class")
            return BLESS_ORDER.index(cls) if cls in BLESS_ORDER else 99
        cands = [a for a in self.allies(me) if not self.down(a) and a not in self.inspiration
                 and self.dist(me, a) <= 60 and not self.blocked(me, a)]
        if not cands or not self.foes(me):
            return False
        a = min(cands, key=lambda a: (rank(a), self.dist(me, a)))
        sides = bardic_die(c.get("level", 1))
        self.inspiration[a] = (me, sides)
        self.bi_uses[me] -= 1; self.use_bonus(me)
        self.sim.say("dice", "%s gives %s Bardic Inspiration (Bonus Action): a d%d (%d uses left)" % (
            c["name"], self.name(a), sides, self.bi_uses[me]))
        return True

    def cast_shillelagh(self, me, c):
        if not self.bonus_free(me) or not c.get("shillelagh") or self.shillelagh.get(me, 0) >= self.s.round():
            return False
        with self.refereed(me, "Shillelagh"):
            self.use_bonus(me)
            self.shillelagh[me] = self.s.round() + 9
            self.sim.say("dice", "%s casts Shillelagh (Bonus Action, 1 minute): %s, %+d to hit" % (
                c["name"], c["shillelagh"]["dmg"], c["shillelagh"]["atk"]))
        return True

    def cure_wounds(self, me, c):
        """Action, touch: Cure Wounds on a fallen ally it can reach this turn (a level 1 slot)."""
        if not self.slot_free(me) or not c.get("cure_wounds"):
            return False
        speed = int(str(c.get("speed", "30")).split()[0])
        fallen = [a for a in self.allies(me) if self.down(a) and not self.deaths.get(a, {}).get("dead")
                  and self.dist(me, a) <= speed + FT]
        if not fallen:
            return False
        a = min(fallen, key=lambda a: self.dist(me, a))
        if self.dist(me, a) > FT:
            self.say("%s moves to reach %s" % (c["name"], self.name(a)))
            self.sim.pc_advance(me, a, 5)
        if self.dist(me, a) > FT:
            return False
        with self.refereed(me, "Cure Wounds", {"target": a}):
            self.resolve_cure_wounds(me, c, a)
        return True

    def resolve_cure_wounds(self, me, c, a):
        """Cure Wounds on a (touch): a slot, 2d8 + the spellcasting modifier. LIVE-PLAY-01: shared."""
        n = 2 * self.slot_wanted(me, 1)                          # +2d8 for each slot level above 1 (SRD 5.2.1)
        heal = high.heal_roll(self.sim.rng, c, "%dd8+%d" % (n, c.get("spell_mod", 0)))
        level = self.spend_slot(me)
        extra = self.healing_bonus(me, c, level, a != me)        # play-test 2026-11-02: Healing Word had it, this didn't
        self.sim.say("dice", "%s casts Cure Wounds on %s%s: %dd8 + %d%s = %d HP" % (c["name"], self.name(a),
                     " (a level %d slot)" % level if level > 1 else "", n, c.get("spell_mod", 0),
                     " + %d Disciple of Life" % extra if extra else "", heal + extra))
        self.revive(a, heal + extra)

    def vicious_mockery(self, me, c, tid):
        """Wisdom save against the spell DC: 2d6 Psychic (level 5) and Disadvantage on its next attack roll."""
        t = self.sim.by_id(tid)
        with self.refereed(me, "Vicious Mockery", {"target": tid}):
            d20 = self.sim.rng.randint(1, 20)
            total, dc = d20 + t.get("wis_save", 0), c.get("spell_dc", 8 + c.get("spell_mod", 0) + 2)
            saved = total >= dc
            dice = cantrip_dice(c.get("level", 1), 6)
            self.sim.say("dice", "%s casts Vicious Mockery at %s: Wisdom save d20 %d %+d = %d vs DC %d -> %s" % (
                c["name"], t["name"], d20, t.get("wis_save", 0), total, dc, "saved" if saved else "failed"))
            if not saved:
                self.s.pcDamage(me, tid, dice, 0, False, "psychic")
                self.sim.settle()
                if not self.down(tid):
                    self.s.setField(tid, "sim_mocked", 1)
                    self.mocked.setdefault(me, set()).add(tid)
                    self.sim.say("dice", "Vicious Mockery: %s has Disadvantage on its next attack roll" % t["name"])

    def bard_healing_word(self, me, c):
        """2026-10-15 (the optimized SRD bard): Healing Word (Bonus Action, 60 ft, a creature it can see) on a fallen ally;
        the Action stays free for a cantrip (One Spell with a Spell Slot per Turn: cantrips are allowed)."""
        if not c.get("healing_word") or not self.slot_free(me):
            return False
        dying = [a for a in self.allies(me) if self.down(a) and not self.deaths.get(a, {}).get("dead")
                 and self.dist(me, a) <= 60 and not self.blocked(me, a) and self.sim.sees(me, a)]
        if not dying:
            return False
        self.healing_word(me, c, [min(dying, key=lambda a: self.dist(me, a))])
        return True

    def turn_bard(self, me, c):
        if high.bard_words(self, me, c):                         # GM 2026-10-28 ("heroes 20"): the power words
            self.inspire(me, c)
            return
        if self.bard_healing_word(me, c):
            tid = self.pick_focus(me) or self.nearest_seen(me)
            if tid is not None:
                self.bard_ranged(me, c, tid)
            return
        if self.cure_wounds(me, c):
            self.inspire(me, c)
            return
        tid = (self.front_target(me, c) if c.get("front_liner") else None) or self.pick_focus(me) or self.nearest_seen(me)
        if tid is None:
            self.say(c["name"] + " sees no foe and holds position"); return
        speed = int(str(c.get("speed", "30")).split()[0])
        if c.get("front_liner") and self.dist(me, tid) <= speed + FT:
            if not self.cast_shillelagh(me, c):
                self.inspire(me, c)
            w, on = self.bard_weapon(me, c)
            if self.melee(me, tid, w, note="Shillelagh" if on else "")[1] is not None:
                return
            self.say("%s cannot reach a foe in melee this turn: a ranged cantrip instead" % c["name"])
            self.bard_ranged(me, c, tid, move=False)   # its move is spent
            return
        self.inspire(me, c)
        self.bard_ranged(me, c, tid)

    def bard_ranged(self, me, c, tid, move=True):
        ranged = c.get("ranged")
        if not ranged:
            if move:
                self.approach(me, tid, 5)
            self.attack(me, tid, c["weapon"]); return
        if move:
            self.approach(me, tid, ranged["reach"])
        if self.dist(me, tid) > ranged["reach"] or self.blocked(me, tid) or not self.sim.sees(me, tid):
            clear = [f for f in self.foes(me) if self.dist(me, f) <= ranged["reach"] and not self.blocked(me, f)
                     and self.sim.sees(me, f)]
            if not clear:
                self.say(c["name"] + " has no clear shot and holds position"); return
            tid = min(clear, key=self.hp_left)
        t = self.sim.by_id(tid)
        # REFEREE-01 (2026-10-22, the referee's first catch): Vicious Mockery's range is 60 ft, the ranged cantrip's
        # may be longer (Fire Bolt 120 ft): beyond 60 ft the cantrip goes instead
        if c.get("vicious_mockery") and "wis_save" in t and t["wis_save"] <= 1 and not self.wasted(tid, "psychic") \
                and self.dist(me, tid) <= 60:
            self.vicious_mockery(me, c, tid)                    # not at a kind seen ignoring Psychic (SIM-MECHANICS-01)
            return
        self.sim.say("dice", "%s casts %s at %s" % (c["name"], ranged["name"], t["name"]))
        self.attack(me, tid, ranged, spell=True)

    def inspire_miss(self, attacker, total, ac):
        """Hook from the fake FG: a holder rolls its die on a missed attack roll the die could still turn."""
        held = self.inspiration.get(attacker)
        if not held or not inspiration_helps(total, ac, held[1]):
            return 0
        self.inspiration.pop(attacker)
        r = self.sim.rng.randint(1, held[1])
        self.sim.say("dice", "%s rolls %s's Bardic Inspiration on the miss: +%d" % (self.name(attacker), self.name(held[0]), r))
        return r

    def react_hit(self, tid, total, ac, crit):
        """Hook from the fake FG (a hit, the target's Reaction free): Shield. Returns (AC bonus, lasting)."""
        bonus = self.shield(tid, total, ac, crit)
        if bonus:
            return bonus, True
        return 0, False

    # ---------------------------------------------------------------- hooks from the fake FG and the run loop
    def asked_live(self, i):
        """SPELL-BATCH-02: the live fight's Reactions (sim/live_reactions.py) when this character's player is asked
        instead of the simulator choosing: a character played at the table, in a fight with a screen to ask, and the
        GM's Auto mode off (OA-AUTO-01: in Auto mode the simulator chooses, as for monsters and foes)."""
        r = getattr(getattr(self.sim, "live", None), "reactions", None)
        return r if r and r.asks() and self.sim.by_id(i).get("live") else None

    def shield(self, tid, total, ac, crit):
        """A Reaction: Shield when a non-critical hit would miss against AC + 5. Returns the AC bonus (0: not cast)."""
        c = self.sim.by_id(tid)
        if not c.get("shield") or crit or total >= ac + 5 or not self.slot_free(tid) or self.incapacitated(tid):
            return 0
        if self.asked_live(tid):                                 # SPELL-BATCH-02: its player is asked instead
            return 0
        with self.refereed(tid, "Shield"):
            self.spend_slot(tid)   # One Spell with a Spell Slot per Turn counts a Reaction too (review of v0.7.97)
            self.shielded.add(tid)
            self.sim.say("dice", "%s casts Shield (Reaction): +5 AC until the start of her turn" % c["name"])
        __import__("epic_boons").reacted(self.sim, tid)          # EPIC-BOONS-01: Merge with Shadows ends
        return 5

    def dodge_hit(self, tid, src):
        """Hook from the fake FG (a hit, the target's Reaction free): Uncanny Dodge (Rogue 5) halves the attack's damage
        when the target can see the attacker."""
        asked = self.asked_live(tid)
        if asked:                                                # REACTIONS-LIVE-01: its player is asked instead
            return asked.dodge(tid, src)
        c = self.sim.by_id(tid)
        if not c.get("uncanny_dodge") or self.incapacitated(tid) or not self.sim.sees(tid, src):
            return False
        self.sim.say("dice", "%s uses Uncanny Dodge (Reaction): the attack's damage is halved" % c["name"])
        __import__("epic_boons").reacted(self.sim, tid)          # EPIC-BOONS-01: Merge with Shadows ends
        return True

    def enemy_dropped(self, tid):
        """Dark One's Blessing (Fiend 3): the Warlock reduced an enemy to 0 HP, or someone did within 10 ft of it:
        Temporary Hit Points = Charisma modifier + Warlock level (they do not add up: the higher number stays)."""
        for w in [o["id"] for o in self.sim.sc["combatants"] if o.get("dark_ones_blessing")]:
            c = self.sim.by_id(w)
            if self.side(w) == self.side(tid) or self.down(w) or not (self.actor == w or self.dist(w, tid) <= 10):
                continue
            temp = c.get("spell_mod", 0) + c.get("level", 1)
            if temp > (self.s.getField(w, "sim_temp_hp") or 0):
                self.s.setField(w, "sim_temp_hp", temp)
                self.sim.say("dice", "%s gains %d Temporary Hit Points (Dark One's Blessing)" % (c["name"], temp))

    def concentration_save(self, tid, c, amount, spell):
        """A Concentration save after damage (Bless 1d4 while it lasts, Aura of Protection). True: kept."""
        dc = concentration_dc(amount)
        d20 = self.sim.rng.randint(1, 20)
        rolled = "d20 %d" % d20
        extended = getattr(self, "extended", {}).get(tid) == spell   # GM 2026-10-23: Extended Spell (Metamagic)
        if c.get("eldritch_mind") or extended:                   # Eldritch Mind (invocation): Advantage
            second = self.sim.rng.randint(1, 20)
            rolled = "d20 %d/%d (%s: Advantage)" % (d20, second, "Eldritch Mind" if c.get("eldritch_mind") else "Extended Spell")
            d20 = max(d20, second)
        b = self.sim.rng.randint(1, 4) if tid in self.blessed and self.concentrating else 0
        aura = self.aura(tid)
        total = d20 + c.get("con_save", 0) + b + aura
        gm = getattr(self.sim, "gm_rules", None)
        if gm:
            total += gm.own_luck(tid, total, dc, "Concentration")
            total = gm.indomitable(tid, total, dc, "Concentration", c.get("con_save", 0) + b + aura)
        self.sim.say("dice", "%s Concentration save: %s %+d%s%s = %d vs DC %d -> %s" % (
            c["name"], rolled, c.get("con_save", 0), " +%d Bless" % b if b else "", " +%d Aura of Protection" % aura if aura else "",
            total, dc, "kept" if total >= dc else spell + " ends"))
        return total >= dc

    def damaged(self, tid, amount, crit, was_down):
        c = self.sim.by_id(tid)
        if not c.get("pc"):
            if not was_down and self.down(tid):
                self.enemy_dropped(tid)                          # PARTY-04
            return
        if was_down:
            out = damage_at_zero(self.deaths[tid], crit, amount, c["hp"])
            self.sim.say("dice", "%s takes damage at 0 HP: death saving throw %s" % (c["name"], out))
            if out == "dead":
                self.s.setField(tid, "sim_dying", 0)
            return
        if self.down(tid):
            # Bless stays on a fallen member while the caster concentrates (review of v0.7.97, finding 3)
            self.deaths[tid] = new_death_state()
            self.s.setField(tid, "sim_dying", 1)
        if self.down(tid):
            self.end_rage(tid, "Incapacitated at 0 HP")
        # PARTY-02/04, SIM-MECHANICS-01 (e): one Concentration at a time; at 0 HP it ends, else a save after the damage
        held = self.concentrates(tid)
        if held and self.down(tid):
            self.lose_concentration(tid, "Unconscious")
        elif held and not self.concentration_save(tid, c, amount, held):
            self.end_concentration(tid)

    def revive(self, tid, amount):
        # Ordinary healing is not resurrection. Live spell validation refuses before spending;
        # this backstop also protects scripted and future callers of the shared helper.
        if self.deaths.get(tid, {}).get("dead"):
            return False
        self.s.heal(tid, amount)
        self.deaths[tid] = new_death_state()
        self.s.setField(tid, "sim_dying", 0)
        return True

    def dying_turn(self, me):
        """A member at 0 HP: a Death Saving Throw at the start of its turn (SRD 5.2.1), then the turn ends."""
        c, st = self.sim.by_id(me), self.deaths[me]
        self.turn_start(me)
        if c.get("periapt") and not st["dead"] and not st["stable"]:   # PARTY-ITEMS: Periapt of Wound Closure
            st["stable"] = True
            self.s.setField(me, "sim_dying", 0)
            self.sim.say("dice", "%s is Stable at the start of the turn (Periapt of Wound Closure)" % c["name"])
        if st["dead"] or st["stable"]:
            self.sim.say("turn", "%s is %s: turn skipped" % (c["name"], "dead" if st["dead"] else "Stable at 0 HP"))
            return
        d20 = self.sim.rng.randint(1, 20)
        if c.get("survivor"):                                    # Defy Death (Champion 18): Advantage, 18-20 is a 20
            d20 = high.defy_death(c, max(d20, self.sim.rng.randint(1, 20)))
        # a Death Saving Throw is a saving throw: Bless adds 1d4 (SRD 5.2.1). A natural 1 or 20 stays what it is.
        b = self.sim.rng.randint(1, 4) if me in self.blessed and self.concentrating else 0
        aura = self.aura(me)                                     # PARTY-04: Aura of Protection
        out = death_save(d20 if d20 in (1, 20) else min(19, d20 + b + aura), st)
        self.sim.say("dice", "%s death saving throw: d20 %d%s%s -> %s (%d successes, %d failures)" % (
            c["name"], d20, " +%d Bless" % b if b else "", " +%d Aura of Protection" % aura if aura else "", out,
            st["successes"], st["failures"]))
        if out == "revive":
            self.revive(me, 1)
        elif out in ("dead", "stable"):
            self.s.setField(me, "sim_dying", 0)
