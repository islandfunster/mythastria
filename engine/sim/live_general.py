"""SPELL-CASTER-01 (GM 2026-10-24: players with their own characters "will need full access"): the general spell caster
for Play live. A spell whose rules the referee reads (sim/spell_rules.py spell(): range, area, targets, save, attack,
damage with its scaling, healing, conditions and how long they last, Concentration) is cast by the engine from those
rules, so it is a Cast button instead of "Ask the GM" (sim/live_asks.py). The 14 hand-written spells of
sim/live_spells.py keep their own code; everything here goes through the same checks, the same referee and the same
cards on the page (the offer's shape: creature, creatures, sphere, cone, line, cube, cube_self).

Which spells, and how far the engine plays them, is PLAYS below: read from the SRD 5.2.1 text of every spell of levels
0-3 the rule sheet reads (docs/development/SRD_GAPS_PLAN.md "The general spell caster"). The sheet's reading is the
rule; an entry only adds what the text says and the sheet can't hold (Entangle's 20-foot square, Shatter's Constructs,
Ice Knife's scaling on the Cold damage only, the rider of a cantrip). Two kinds:
- the engine plays all of it in a fight (damage, healing, the save, the conditions and when they end);
- "gm": the engine plays the save, attack, damage and conditions, and the rest goes to the GM as a request (Ask the
  GM's list on the GM's screen), worded from the spell: Dissonant Whispers' flight, Moonbeam on later turns...
Spells not in PLAYS stay Ask the GM: the 155 utility spells, the 67 whose number of targets the sheet can't read, and
the ones whose effect the engine has no way to hold yet (Haste, Slow, summons, lasting zones).
SPELLS-4-9 (GM 2026-10-26, goal 3: spell levels 4 to 9): the same for every level 4-9 spell whose effect fits these
building blocks, with a few more of them, each from the spell's words: damage in two parts at once (Flame Strike), a
straight wall placed on a point (Wall of Fire), several Spheres (Meteor Swarm), bolts that leap from the first target
(Chain Lightning), the power words (by the target's Hit Points), Prismatic Spray's rays, healing by a number or divided
(Heal, Mass Heal, Power Word Heal), a Hit Point maximum cut (Harm), a condition given to a willing creature (Greater
Invisibility). The readings the referee shares are sim/spell_rules.py READINGS. A Warlock's Mystic Arcanum spell is
cast without a slot, once per Long Rest. GM_WHY says why each other level 4-9 spell is still the GM's (Ask the GM shows
it).

Checks before anything is spent (sim/requirements.py, each with its reason): able to act; the spell on the sheet; the
casting time free (the Action or the Bonus Action); a slot of the chosen level or higher; One Spell with a Spell Slot
per Turn; a Material component with a cost in the bag (and taken when the spell consumes it); range, sight and a clear
line to each creature or point; the creature type the spell needs. A new Concentration spell ends the one held
(Party.start_concentration). Upcasting: cmd["slot"] (else the lowest slot that allows the creatures chosen).
"""
import math, re

import requirements as rq
import spell_rules

TIME = {"action": "action", "bonus_action": "bonus"}
ABILITY = {"str": "Strength", "dex": "Dexterity", "con": "Constitution", "int": "Intelligence", "wis": "Wisdom",
           "cha": "Charisma"}
APPEAR = {"fire": "fire", "cold": "frost", "lightning": "lightning", "acid": "acid", "poison": "poison", "thunder": "thunder",
          "radiant": "radiant", "necrotic": "shadow", "psychic": "arcane", "force": "arcane", "piercing": "physical",
          "slashing": "physical", "bludgeoning": "physical"}
ROUNDS = {"round": 1, "minute": 10, "hour": 600}

# What the text adds to the sheet, per spell (see the module notes). Keys:
#   gm: what the GM rules after the engine's part (a request opens with these words)
#   area: the area the text gives where the sheet has none; foe: a creature other than the caster; kind: its type
#   choice: [options] the player picks one (cmd["choice"]); rider: the cantrip's or spell's extra on a hit or failure
#   dis_type: creatures of this type have Disadvantage on the save; scale_part: the damage part the scaling adds to
#   push_ft: pushed away on a failed save; ends_on_hurt: the condition ends when the creature takes damage
#   repeat: the save again at the end of each of its turns, the spell ending on it on a success
PLAYS = {
    # ---- cantrips
    "Acid Splash": {},
    "Chill Touch": {"gm": "it can't regain Hit Points until the end of {caster}'s next turn"},
    "Eldritch Blast": {},
    "Fire Bolt": {},
    "Poison Spray": {},
    "Ray of Frost": {"rider": "slow"},
    "Sacred Flame": {},
    "Shocking Grasp": {"rider": "no_reaction"},
    "Starry Wisp": {"rider": "outlined"},
    "Vicious Mockery": {"rider": "mocked"},
    # ---- level 1
    "Chromatic Orb": {"choice": ["acid", "cold", "fire", "lightning", "poison", "thunder"], "rider": "leap"},
    "Color Spray": {},
    "Command": {"choice": ["Grovel", "Halt", "Approach", "Drop", "Flee"], "rider": "command"},   # SPELL-EFFECTS-01: all played
    "Dissonant Whispers": {"gm": "on a failed save {target} must use its Reaction, if available, to move as far away "
                                 "from {caster} as it can by the safest route"},
    "Entangle": {"area": {"shape": "cube", "size_ft": 20, "origin": "point"}, "targets": "area", "gm_when": "always",
                 "gm": "the 20-foot square is Difficult Terrain; a Restrained creature can take an action for a Strength "
                       "(Athletics) check against DC {dc} to free itself"},
    "Faerie Fire": {"rider": "outlined_adv"},
    "Grease": {"area": {"shape": "cube", "size_ft": 10, "origin": "point"}, "targets": "area",
               "gm_when": "always", "gm": "the 10-foot square is Difficult Terrain for 1 minute; a creature that enters it or ends its turn "
                     "there saves (DC {dc} Dexterity) or falls Prone"},
    "Hideous Laughter": {"foe": True},
    "Hunter's Mark": {"rider": "mark"},
    "Ice Knife": {"scale_part": 1},
    "Inflict Wounds": {},
    "Magic Missile": {},
    "Ray of Sickness": {},
    "Thunderwave": {"push_ft": 10},
    # ---- level 2
    "Acid Arrow": {"rider": "acid_later"},
    "Blindness/Deafness": {"choice": ["Blinded", "Deafened"], "repeat": True},
    "Mind Spike": {"gm": "{caster} knows {target}'s location until the spell ends: it can't hide from {caster}, and "
                         "Invisible gives it no benefit against {caster}"},
    "Moonbeam": {"gm_when": "always", "gm": "the Cylinder stays: a creature saves when it enters it, ends its turn there or the Cylinder moves "
                       "into its space (once a turn); {caster} can move it up to 60 ft as a Magic action"},
    "Scorching Ray": {},
    "Shatter": {"dis_type": "construct"},
    # ---- level 3
    "Fear": {"gm": "a Frightened creature drops what it holds, takes the Dash action and moves away from {caster} by the "
                   "safest route on each of its turns; it saves again only when it ends a turn out of {caster}'s sight"},
    "Hypnotic Pattern": {"ends_on_hurt": True, "sees": True,
                         "gm": "a Charmed creature has Speed 0; someone else can take an action to shake it out of it"},
    "Lightning Bolt": {},
    "Mass Healing Word": {},
    "Vampiric Touch": {"rider": "drain", "gm_when": "always", "gm": "until the spell ends {caster} can make the attack again on each later turn "
                                               "as a Magic action"},
    # ---- level 4 (SPELLS-4-9). More keys: how: word / buff (kind of play the sheet can't tell); wall: a straight wall
    # on a point; points: several Spheres; leap_ft: the later targets within this of the first; auto_fail_type /
    # auto_save_type: creatures of this type fail / succeed the save; later_part: this damage part again at the end of
    # the target's next turn; mark: a mark (not an SRD condition) the failed save gives; choice_cond: the choice's
    # condition; wakes: the choice that ends on damage; saved_speed0: Speed 0 until the start of the caster's next turn
    # on a success; heal_area: the caster's side in the area (at most the spell's number); pool: Hit Points divided;
    # cures: conditions the healing ends; foes_only: "creatures of your choice" (the caster's foes); ends_on_save: the
    # spell ends when every target saved; conditions: the conditions it gives in a fight (the sheet's, unless set)
    "Banishment": {"gm": "{target} is banished to a harmless demiplane while {caster} concentrates (Incapacitated, gone from "
                         "the map) and reappears in the space it left; an Aberration, Celestial, Elemental, Fey or Fiend "
                         "doesn't return if the spell lasts the full minute"},
    "Blight": {"auto_fail_type": "plant"},
    "Confusion": {"mark": "Confused", "repeat": True,
                  "gm": "a Confused creature can't take Bonus Actions or Reactions and rolls 1d10 at the start of each of its "
                        "turns: 1 it moves in a random direction (1d4) and takes no action; 2-6 it doesn't move or act; 7-8 one "
                        "melee attack against a random creature in reach; 9-10 it acts freely"},
    "Greater Invisibility": {"how": "buff"},
    "Ice Storm": {"gm_when": "always", "gm": "hailstones make the ground in the Cylinder Difficult Terrain until the end of "
                                             "{caster}'s next turn"},
    "Phantasmal Killer": {"ends_on_save": True, "gm": "{target} has Disadvantage on ability checks and attack rolls while "
                          "{caster} concentrates, and saves again (DC {dc} Wisdom) at the end of each of its turns: a "
                          "failure deals the Psychic damage again, a success ends the spell"},
    "Vitriolic Sphere": {"later_part": 1},
    # group 2 (GM 2026-10-27): a straight wall or a ring 20 feet across ({choice})
    "Wall of Fire": {"choice": ["Straight", "Ring"],
                     "gm_when": "always", "gm": "the wall ({choice}) stays while {caster} concentrates and is opaque; its hot "
                     "side (the caster picks it; a ring: inside or outside) deals {dice} Fire damage to each creature that "
                     "ends its turn within 10 ft of that side or inside the wall, and to one that enters the wall (the "
                     "first time on a turn)"},
    # ---- level 5
    "Contagion": {"choice": ["Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Charisma"],
                  "gm": "while Poisoned, {target} has Disadvantage on {choice} saving throws; it saves again (DC {dc} "
                        "Constitution) at the end of each of its turns until it has three successes (the spell ends) or "
                        "three failures (it lasts 7 days)"},
    "Flame Strike": {},
    "Mass Cure Wounds": {"heal_area": True},
    # ---- level 6
    "Chain Lightning": {"leap_ft": 30},
    "Circle of Death": {},
    "Disintegrate": {"rider": "dust"},
    "Eyebite": {"choice": ["Asleep", "Panicked", "Sickened"], "wakes": "Asleep",
                "choice_cond": {"Asleep": "Unconscious", "Panicked": "Frightened", "Sickened": "Poisoned"},
                "gm_when": "always", "gm": "on each of {caster}'s turns until the spell ends, a Magic action targets another "
                "creature (never one that saved); Panicked: the target Dashes away from {caster} by the safest route on "
                "each of its turns (it ends 60 ft away out of sight); Asleep: an action shakes it awake"},
    "Flesh to Stone": {"auto_save_type": "construct", "saved_speed0": True, "conditions": ["Restrained"],
                       "gm": "{target} saves again (DC {dc} Constitution) at the end of each of its turns: three failures "
                             "and it is Petrified, three successes and the spell ends (successes and failures needn't be "
                             "consecutive)"},
    "Freezing Sphere": {"conditions": []},                    # Restrained: only creatures swimming in water it freezes
    "Harm": {"rider": "harm"},
    "Heal": {"cures": ["Blinded", "Deafened", "Poisoned"]},
    "Sunbeam": {"gm_when": "always", "gm": "until the spell ends, {caster} can take a Magic action to send a new Line (the "
                                           "GM rolls it as this one)"},
    # ---- level 7
    "Divine Word": {"how": "word", "word": "divine"},
    "Finger of Death": {"gm_when": "killed", "gm": "{target} rises at the start of {caster}'s next turn as a Zombie that "
                                                   "obeys {caster}'s verbal orders"},
    "Prismatic Spray": {"rays": True},
    # ---- level 8
    "Befuddlement": {"mark": "Befuddled", "gm": "{target} can't cast spells or take the Magic action; it saves again every "
                     "30 days, and Greater Restoration, Heal or Wish ends it"},
    "Power Word Stun": {"how": "word", "word": "stun"},
    "Sunburst": {"repeat": True},
    # ---- level 9
    "Mass Heal": {"pool": 700, "cures": ["Blinded", "Deafened", "Poisoned"]},
    "Meteor Swarm": {},
    "Power Word Heal": {"cures": ["Charmed", "Frightened", "Paralyzed", "Poisoned", "Stunned"],
                        "gm_when": "prone", "gm": "{target} can use its Reaction to stand up"},
    "Power Word Kill": {"how": "word", "word": "kill"},
    "Weird": {"foes_only": True, "repeat": True,
              "gm": "a Frightened target that fails its save at the end of its turn takes 5d10 Psychic damage (the GM "
                    "rolls it); a success ends the spell on it"},
}
ANY = 99                                                         # "any number of creatures"

# SPELLS-4-9: why each other level 4-9 spell is still the GM's (Ask the GM shows it). "goal 4": the session building the
# remaining spell effects (summons, Haste and Slow, charms, lasting zones and clouds).
GOAL4 = "its lasting effect belongs to the remaining spell effects (goal 4)"
GM_WHY = dict(
    [(n, "a summoned or conjured creature: " + GOAL4) for n in (
        "Conjure Minor Elementals", "Conjure Woodland Beings", "Faithful Hound", "Giant Insect", "Guardian of Faith",
        "Animate Objects", "Arcane Hand", "Conjure Elemental", "Summon Dragon", "Conjure Fey", "Create Undead",
        "Planar Ally", "Arcane Sword", "Conjure Celestial", "Simulacrum", "Gate", "Animal Shapes")]
    + [(n, "a charm or a creature controlled: " + GOAL4) for n in (
        "Charm Monster", "Compulsion", "Dominate Beast", "Dominate Person", "Geas", "Modify Memory", "Mass Suggestion",
        "Irresistible Dance", "Dominate Monster", "Antipathy/Sympathy", "Planar Binding")]
    + [(n, "a lasting zone, cloud or wall: " + GOAL4) for n in (
        "Black Tentacles", "Cloudkill", "Insect Plague", "Blade Barrier", "Wall of Ice", "Wall of Thorns", "Wall of Stone",
        "Wall of Force", "Incendiary Cloud", "Earthquake", "Prismatic Wall", "Storm of Vengeance", "Forcecage",
        "Reverse Gravity", "Antilife Shell", "Antimagic Field", "Globe of Invulnerability",
        "Aura of Life", "Holy Aura", "Control Water", "Tsunami", "Control Weather", "Move Earth")]
    + [(n, "a planar or reality-bending spell: the GM rules it") for n in (
        "Plane Shift", "Etherealness", "Astral Projection", "Maze", "Demiplane", "Wish", "Time Stop",
        "Magic Jar", "Sequester", "Imprisonment", "Contingency", "Clone", "Mirage Arcane", "Magnificent Mansion",
        "Teleportation Circle", "Word of Recall", "Transport via Plants", "Tree Stride", "Project Image")]
    + [(n, "a new form or shape: the engine has no stat-block change yet") for n in (
        "Polymorph", "True Polymorph", "Shapechange")]
    + [(n, "movement or teleportation the engine doesn't play yet") for n in (
        "Dimension Door", "Teleport", "Freedom of Movement", "Wind Walk", "Passwall", "Telekinesis")]
    + [(n, "a protection or buff the engine doesn't hold yet (resistance, a ward, a reaction)") for n in (
        "Death Ward", "Fire Shield", "Stoneskin", "Resilient Sphere", "Dispel Evil and Good", "Mind Blank", "Foresight",
        "Heroes' Feast", "Greater Restoration", "Mislead", "Seeming", "Glibness")]
    + [(n, "a dead creature brought back: outside a fight's turns") for n in (
        "Raise Dead", "Reincarnate", "Resurrection", "True Resurrection")]
)


def gm_why(name):
    """Why a spell of level 4-9 is not a Cast button (None for one the engine plays, or of a lower level)."""
    import live_spells
    r = spell_rules.spell(name)
    if r is None or r["level"] < 4 or plan(name) or name in live_spells.SPELLS:
        return None
    if name in GM_WHY:
        return GM_WHY[name]
    if r["casting_time"] not in TIME:
        return "its casting time is longer than a turn, or a Reaction: the GM rules it"
    return "a utility spell (no attack, save, damage or healing the engine plays): the GM rules it"

# Riders a cantrip or spell adds, for the referee and the page.
RIDER_TEXT = {"slow": "Speed -10 ft until the start of your next turn", "no_reaction": "no Opportunity Attacks until the "
              "start of its next turn", "outlined": "can't benefit from Invisible until the end of your next turn",
              "mocked": "Disadvantage on its next attack roll", "outlined_adv": "outlined: attacks against it have Advantage",
              "mark": "+1d6 Force on each of your hits", "acid_later": "2d4 Acid more at the end of its next turn",
              "drain": "you regain half the Necrotic damage dealt", "leap": "a double on the d8s leaps to another creature",
              "dust": "a creature it drops to 0 Hit Points is turned to dust",
              "harm": "its Hit Point maximum drops by the Necrotic damage taken"}


class GeneralError(ValueError):
    pass


def _ft(text):
    m = re.search(r"(\d+) (round|minute|hour)", text or "")
    return int(m.group(1)) * ROUNDS[m.group(2)] if m else None


def _dice(expr):
    """'3d8' -> (3, 8); '1d4 + 1' -> (1, 4)."""
    m = re.match(r"\s*(\d+)d(\d+)", expr or "")
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def _flat(expr):
    m = re.search(r"\+\s*(\d+)\s*$", expr or "")
    return int(m.group(1)) if m else 0


def plan(name):
    """The rules the engine casts a general spell by (None: not one the engine plays). The SRD sheet (and the GM's
    clarification over it), with PLAYS' additions."""
    extra = PLAYS.get(name)
    r = spell_rules.spell(name)
    if extra is None or r is None or r.get("unread") or r["casting_time"] not in TIME:
        return None
    area = extra.get("area", r["area"])
    t = r["targets"]
    kind = extra.get("how") or (
        "attack" if r["attack"] else "save" if r["save"] else "heal" if r["healing"] and not r["damage"] else
        "auto" if r["damage"] and r.get("count") else "mark" if extra.get("rider") == "mark" else None)
    if kind is None:
        return None
    if area and area.get("wall"):                                # SPELLS-4-9: Wall of Fire
        shape = "wall"
    elif area and area.get("points"):                            # Meteor Swarm
        shape = "spheres"
    elif area and extra.get("targets") == "area" or (area and t["kind"] == "area"):
        shape = {"sphere": "sphere", "cylinder": "sphere", "cone": "cone", "line": "line",
                 "cube": "cube" if area["origin"] == "point" else "cube_self"}.get(area["shape"])
    else:
        shape = "creature"
    if shape is None:
        return None
    rng = r["range"]
    reach = rng["ft"] or (5 if kind == "attack" and r["attack"] == "melee" else 0)
    step = re.search(r"healing increases by (\d+) for each", (r.get("scaling") or {}).get("text") or "")
    most = t.get("max") or (ANY if t["choice"] and t["kind"] == "creatures" else 1)
    return dict(extra, name=name, level=r["level"], time=TIME[r["casting_time"]], kind=kind, shape=shape, area=area,
                range_ft=reach, range_kind=rng["kind"], attack=r["attack"], save=r["save"], damage=r["damage"],
                healing=r["healing"], conditions=list(extra.get("conditions", r["conditions"])), lasts=r.get("lasts") or {},
                concentration=bool(r["duration"]["concentration"]), instant=bool(r["duration"]["instant"]),
                rounds=_ft(r["duration"]["text"]), scaling=r.get("scaling") or {}, count=r.get("count"),
                near=r.get("near"), components=r["components"], max_targets=most, choice_targets=t["choice"],
                clarified=r.get("clarified", False), duration_text=r["duration"]["text"],
                together=spell_rules.together(r), area_max=t.get("max") if t["kind"] == "area" else None,
                scaled=[extra["scale_part"]] if "scale_part" in extra else spell_rules.scaled_parts(r),
                heal_step=int(step.group(1)) if step else 0, rules=r)


def castable():
    """Every spell the general caster plays (for the coverage list and the plan)."""
    return [n for n in PLAYS if plan(n)]


class General:
    """The general caster for one LiveFight (its turn_state, its simulator, its referee)."""

    def __init__(self, fight):
        self.fight = fight

    @property
    def sim(self):
        return self.fight.sim

    @property
    def party(self):
        return self.sim.party

    # ------------------------------------------------------------------ what a character has
    def known(self, c):
        """The general spells on this character's sheet (spell_list), not the ones it already has as a sheet attack."""
        import live_spells, more_spells
        attacks = {str((c.get(k) or {}).get("name")) for k in __import__("character_rules").WEAPON_KEYS}
        names = [sp.get("name") for sp in c.get("spell_list") or []]
        return [n for n in names if n and n not in live_spells.SPELLS and n not in attacks and plan(n)
                and not more_spells.owner(n)]                        # SPELL-EFFECTS-01: Moonbeam, Entangle, Grease

    # ------------------------------------------------------------------ Mystic Arcanum (SPELLS-4-9)
    def arcanum(self, me, name):
        """A Warlock's Mystic Arcanum spell (SRD 5.2.1 Warlock 11, 13, 15, 17: "You can cast your arcanum spell once
        without expending a spell slot, and you must finish a Long Rest before you can cast it in this way again"):
        its level when `name` is one, else None."""
        c = self.sim.by_id(me)
        sp = next((s for s in c.get("spell_list") or [] if s.get("name") == name and s.get("arcanum")), None)
        return int(sp["level"]) if sp else None

    def arcanum_left(self, me, level):
        """Uses left of the arcanum of this level (1 after a Long Rest; the day's carried state: rests.py)."""
        left = self.party.__dict__.setdefault("arcanum_left", {}).setdefault(me, {})
        if level not in left:
            left[level] = int(self.sim.by_id(me).get("arcanum_%d" % level, 1) or 0)
        return left[level]

    def by_arcanum(self, me, name, slot=None):
        """This cast uses the Mystic Arcanum (no slot): the spell is one, a use is left and no slot was chosen."""
        lv = self.arcanum(me, name)
        return bool(lv) and not slot and self.arcanum_left(me, lv) > 0

    # ------------------------------------------------------------------ the numbers, from the rules
    def strikes(self, p, slot, c):
        """Darts, rays or beams (1 for a spell that strikes once)."""
        n = p["count"]
        if not n:
            return 1
        if n.get("levels"):
            lvl = int(c.get("level") or 1)
            return n["levels"][2] if lvl >= 17 else n["levels"][1] if lvl >= 11 else n["levels"][0] if lvl >= 5 else n["n"]
        return n["n"] + n.get("per_level", 0) * max(0, slot - n.get("above", slot))

    def most_targets(self, p, slot, c):
        if p["shape"] != "creature":
            return None
        s = p["scaling"]
        most = p["max_targets"] + s.get("extra_targets_per_level", 0) * max(0, slot - s.get("above", slot))
        most += __import__("high_levels").words_extra(c, p["name"])   # Words of Creation (Bard 20): a second creature
        return max(most, self.strikes(p, slot, c))

    def dice(self, p, slot, c, part=0):
        """The damage (or healing) dice of one strike as 'NdM' (+ 'NdM' when the scaling's die differs), the flat part."""
        if p["kind"] == "heal":
            base = p["healing"]["dice"]
            if re.fullmatch(r"\d+", str(base)):                  # Heal's 70 (+10 a slot level above 6)
                return "", int(base) + p["heal_step"] * max(0, slot - p["level"])
        else:
            base = p["damage"][min(part, len(p["damage"]) - 1)]["dice"]
        n, d = _dice(base)
        flat = _flat(base)
        s = p["scaling"]
        if p["level"] == 0 and s.get("levels"):
            lvl = int(c.get("level") or 1)
            n, d = _dice(s["levels"][2] if lvl >= 17 else s["levels"][1] if lvl >= 11 else s["levels"][0] if lvl >= 5 else base)
        more = ""
        if s.get("dice_per_level") and part in p["scaled"]:
            k = max(0, slot - s.get("above", p["level"]))
            sn, sd = _dice(s["dice_per_level"])
            if sd == d:
                n += sn * k
            elif k:
                more = "%dd%d" % (sn * k, sd)
        out = "%dd%d" % (n, d) + ("+" + more if more else "")
        return out, flat

    def mod_bonus(self, p, c):
        dmg = p["healing"] if p["kind"] == "heal" else (p["damage"][0] if p["damage"] else {})
        bonus = int(c.get("spell_mod", 0)) if (dmg or {}).get("plus_mod") else 0
        if c.get("agonizing") and p["name"] == "Eldritch Blast":
            bonus += int(c.get("spell_mod", 0))
        import high_levels                                           # group 3: Blessed Strikes, Potent Spellcasting
        return bonus + high_levels.blessed_cantrip(c, p)

    def roll(self, expr):
        if __import__("high_levels").maxed(self.sim):                # CASTER-HIGH: Overchannel, the dice at their highest
            return sum(int(n) * int(d) for n, d in re.findall(r"(\d+)d(\d+)", expr))
        rng, total = self.sim.rng, 0
        for n, d in re.findall(r"(\d+)d(\d+)", expr):
            total += sum(rng.randint(1, int(d)) for _ in range(int(n)))
        return total

    # ------------------------------------------------------------------ the checks
    def slot_for(self, me, p, cmd, n_targets=1):
        """The slot this cast uses: cmd["slot"], or the lowest one left that allows the creatures chosen."""
        import live_spells
        if p["level"] == 0:
            return 0
        if __import__("high_levels").no_slot(self.party, me, p["name"], cmd.get("slot")):
            return p["level"]                                        # CASTER-HIGH: no slot, at its own level
        pool = live_spells.slots_of(self.party, me)
        if cmd.get("slot"):
            try:
                return max(p["level"], int(cmd["slot"]))
            except (TypeError, ValueError):
                raise GeneralError("The slot is a level from %d to 9." % p["level"])
        c = self.sim.by_id(me)
        for lv in range(p["level"], len(pool) + 1):
            if pool[lv - 1] > 0 and (self.most_targets(p, lv, c) or 1) >= n_targets:
                return lv
        return p["level"]

    def component(self, me, p):
        """A Material component with a cost (SRD 5.2.1 Components: a focus can't stand in for it) must be at hand: an item
        in the bag that is that thing (sim/requirements.py Bag)."""
        m = p["components"]
        if not m.get("m") or not m.get("cost_gp"):
            return None
        bag = self.fight.items.bag(me)
        noun = re.sub(r"^(a|an|some)\s+", "", m.get("material") or "").split(" worth")[0].strip().lower()
        def fits(b):                                                 # "Diamond (50 GP)"; "Black Pearl" for "the powder of
            name = str(b.get("name") or b.get("item")).lower()       # a crushed black pearl" (SPELLS-4-9)
            core = re.sub(r"\s*\(.*\)\s*$", "", name).strip()
            return bool(noun) and (noun in name or len(core) > 3 and re.search(r"\b%s\b" % re.escape(core), noun))
        have = [b for b in bag.entries() if int(b.get("qty", 0)) > 0 and fits(b)]
        return rq.need("%s (%d+ GP) at hand" % (m["material"], m["cost_gp"]), bool(have),
                       "%s needs %s; %s has none in the bag (a spellcasting focus can't stand in for a component with a cost)."
                       % (p["name"], m["material"], self.sim.by_id(me)["name"]), rq.LINKS["market"]), (bag, have)

    def needs(self, me, name, slot=None, time=None):
        """time: the casting time Metamagic gives it (Quickened Spell: "bonus")."""
        import live_spells
        c, t, party = self.sim.by_id(me), self.fight.turn_state, self.party
        p = plan(name)
        needs = [rq.able(self.fight, me)]
        if not t or t["id"] != me:
            needs.append(rq.need("your turn", False, "It is not this character's turn."))
            return needs, p
        listed = any(isinstance(sp, dict) and sp.get("name") == name for sp in c.get("spell_list") or [])   # play-test 2026-11-02
        needs.append(rq.need("the spell on the sheet", name in self.known(c), ("The table doesn't play %s by itself: use Ask the GM." % name) if listed else "%s is not on %s's sheet." % (name, c["name"]),
                             rq.LINKS["characters"]))
        if p is None:
            return needs, p
        needs.append(rq.bonus_free(self.fight, me, name) if (time or p["time"]) == "bonus" else rq.action_free(self.fight, me, name))
        if self.moves_mark(me, name):                                # moving the mark spends no slot
            return needs, p
        lv = self.arcanum(me, name)
        free = __import__("high_levels").no_slot(party, me, name, slot)   # CASTER-HIGH: Spell Mastery, Signature
        if free:                                                     # Spells, Divine Intervention: no slot
            pass
        elif lv and not slot and not any(live_spells.slots_of(party, me)[lv - 1:]):
            needs.append(rq.need("a Mystic Arcanum use", self.arcanum_left(me, lv) > 0,
                                 "%s's Mystic Arcanum (%s) is spent: it comes back with a Long Rest." % (c["name"], name)))
        elif lv and not slot and self.arcanum_left(me, lv) > 0:
            pass                                                     # SPELLS-4-9: the arcanum needs no slot
        elif p["level"] >= 1:
            lv = max(p["level"], int(slot or p["level"]))
            pool = live_spells.slots_of(party, me)
            needs.append(rq.need("a spell slot", sum(pool[lv - 1:]) > 0,
                                 "No spell slot of level %d or higher left for %s." % (lv, name)))
            needs.append(rq.need("no other slot this turn", party.slot_turn.get(me) != party.s.turnSerial,
                                 "One spell with a spell slot per turn: %s already spent a slot this turn (SRD 5.2.1)." % c["name"]))
            if getattr(party, "quickened_turn", {}).get(me) == party.s.turnSerial:
                needs.append(rq.need("no Quickened Spell this turn", False,
                                     "After a Quickened Spell, no level 1+ spell this turn (SRD 5.2.1 Metamagic)."))
        comp = self.component(me, p)
        if comp and free != "Divine Intervention":                  # CASTER-HIGH: "without ... Material components"
            needs.append(comp[0])
        return needs, p

    def spell_entry(self, p):
        """The fields live_spells.check_creature reads."""
        harmful = p["kind"] not in ("heal", "buff") and p.get("rider") != "mark" or p.get("foe")
        return {"range_ft": p["range_ft"], "heal": p["kind"] == "heal", "foe": bool(harmful and p["range_kind"] != "self"),
                "humanoid": False}

    def check_target(self, me, p, tid):
        import live_spells
        spells = self.fight.spells
        try:
            target = spells.check_creature(me, p["name"], self.spell_entry(p), tid)
        except live_spells.SpellError as e:
            raise GeneralError(str(e))
        if tid == me and p["kind"] not in ("heal", "buff") and p["shape"] == "creature":
            import spell_objects                                     # SPELL-OBJECTS-01, the playtester's finding 3
            raise GeneralError("%s targets %s other than you." % (p["name"], spell_objects.WORDS[spell_objects.objects(p["name"])]))
        if tid != me and p["range_ft"] <= 5 and self.party.dist(me, tid) > 5.01:
            raise GeneralError("%s is out of reach (touch: 5 ft)." % target["name"])
        return target

    # ------------------------------------------------------------------ Metamagic (group 2, GM 2026-10-27)
    @staticmethod
    def meta_entry(p):
        """The fields Metamagic reads (sim/live_sorcery.py plan): the casting time, range, Concentration and duration,
        the damage type, whether it forces a save or damages an area, and whether a higher slot adds a creature
        (Twinned Spell)."""
        import live_sorcery                                          # the type Transmuted Spell may change (Ice Storm: Cold)
        kinds = [d["type"] for d in p["damage"]]
        return {"time": p["time"], "range_ft": p["range_ft"], "concentration": p["concentration"],
                "rounds": p.get("rounds") or 0,
                "kind": next((k for k in kinds if k in live_sorcery.TRANSMUTE), kinds[0] if kinds else None),
                "save": bool(p["save"]), "area_damage": bool(p["damage"]) and p["shape"] != "creature",
                "twin": p["level"] >= 1 and p["shape"] == "creature" and bool(p["scaling"].get("extra_targets_per_level"))}

    def empowered_roll(self, dice, n):
        """Empowered Spell: up to n of the lowest damage dice rolled again (once)."""
        rng = self.sim.rng
        rolled = [(int(d), rng.randint(1, int(d))) for k, d in re.findall(r"(\d+)d(\d+)", dice) for _ in range(int(k))]
        low = sorted(range(len(rolled)), key=lambda k: rolled[k][1])[:n]
        again = [(rolled[k][0], rng.randint(1, rolled[k][0])) if k in low else rolled[k] for k in range(len(rolled))]
        self.sim.say("dice", "Empowered Spell: %s rolled again -> %s" % (
            ", ".join(str(rolled[k][1]) for k in low), ", ".join(str(again[k][1]) for k in low)))
        return sum(v for _, v in again)

    # ------------------------------------------------------------------ casting
    def cast(self, me, cmd):
        name = cmd.get("spell")
        p = plan(name)
        meta, mplan = (self.meta_entry(p), None) if p else ({}, None)
        if p and cmd.get("metamagic"):                               # group 2: checked with the rest, nothing spent
            import live_sorcery
            try:
                meta, mplan = live_sorcery.of(self.fight).plan(me, name, meta, cmd)
            except live_sorcery.SorceryError as e:
                raise GeneralError(str(e))
        ready, rows = rq.check(self.needs(me, name, cmd.get("slot"), meta.get("time"))[0])
        if not ready:
            raise GeneralError(rq.first_why(rows))
        self._meta = {"plan": mplan or {}, "careful": [], "heighten": []}
        try:
            return self._cast(me, cmd, dict(p, range_ft=meta["range_ft"]), meta, mplan)
        finally:
            self._meta = None

    def _cast(self, me, cmd, p, meta, mplan):
        name = p["name"]
        twin = 1 if (mplan or {}).get("twin") else 0               # Twinned Spell: as if a slot one level higher
        c, party = self.sim.by_id(me), self.party
        moving = self.moves_mark(me, name)
        choice = cmd.get("choice")
        if p.get("choice"):
            choice = choice or p["choice"][0]
            if choice not in p["choice"]:
                raise GeneralError("%s: choose one of %s." % (name, ", ".join(p["choice"])))
        # where it goes: every check before anything is spent
        shape, targets, aim = p["shape"], [], {}
        if shape == "creature":
            tids = [x for x in (cmd.get("targets") or ([cmd["target"]] if cmd.get("target") is not None else []))]
            if not tids:
                raise GeneralError("Choose a creature for %s." % name)
            slot = self.slot_for(me, p, cmd, max(1, len(set(tids)) - twin))
            most = self.most_targets(p, slot + twin, c)
            if p["count"]:                                            # darts, rays, beams: one creature or several
                if len(set(tids)) > most:
                    raise GeneralError("%s makes %d %ss: at most %d creatures." % (name, most, p["count"]["word"], most))
            elif len(tids) > most:
                raise GeneralError("%s takes at most %d creature%s with a level %d slot." % (
                    name, most, "" if most == 1 else "s", slot) if slot else "%s takes one creature." % name)
            elif len(set(tids)) != len(tids):
                raise GeneralError("Each creature once.")
            for k, tid in enumerate(dict.fromkeys(tids)):
                if k and p.get("leap_ft"):                            # Chain Lightning: a bolt leaps from the first
                    self.check_leap(me, p, tids[0], tid)
                else:
                    self.check_target(me, p, tid)
                if k and __import__("high_levels").words_extra(c, name):  # Words of Creation: within 10 ft of the first
                    why = __import__("high_levels").words_second(party, tids[0], tid)
                    if why:
                        raise GeneralError(why)
            targets = tids
        else:
            slot = self.slot_for(me, p, cmd)
            try:
                pts = [(int(q[0]), int(q[1])) for q in cmd.get("points") or []] if shape == "spheres" else []
                pt = pts[0] if pts else (int(cmd["x"]), int(cmd["y"]))
            except (KeyError, TypeError, ValueError, IndexError):
                raise GeneralError("Aim %s at a square." % name)
            targets, aim = self.area(me, p, pt, slot, pts or [pt], cmd)
        comp = self.component(me, p)
        if __import__("high_levels").armed(party, me) == "Divine Intervention":
            comp = None                                              # CASTER-HIGH: no Material components
        free = self.by_arcanum(me, name, cmd.get("slot"))           # SPELLS-4-9: the Mystic Arcanum, no slot
        # ---- spend: the casting time, the slot, Concentration, a consumed component
        if mplan:                                                    # who Careful and Heightened Spell pick, now
            import live_sorcery                                      # the creatures inside are known
            sorc = live_sorcery.of(self.fight)
            self._meta["careful"] = sorc.careful(me, list(dict.fromkeys(targets)), cmd) if mplan.get("careful") else []
            self._meta["heighten"] = sorc.heightened(me, list(dict.fromkeys(targets)), cmd) if mplan.get("heighten") else []
        t = self.fight.turn_state
        if meta["time"] == "action":
            t["action_used"], t["attacks_left"] = True, 0
        else:
            party.use_bonus(me)
        if moving:                                                   # Hunter's Mark: the Bonus Action moves the mark
            party.marked[me] = targets[0]
            self.sim.say("dice", "%s moves Hunter's Mark to %s (Bonus Action, no spell slot): +1d6 Force on each hit" % (
                c["name"], party.name(targets[0])))
            effect = self.effect(me, p, list(targets), aim, choice)
            effect["_cmd"] = {"free": "moving Hunter's Mark to a new creature"}
            return effect
        if free:
            slot = p["level"]
            party.arcanum_left[me][slot] -= 1
            self.sim.say("dice", "%s casts %s with the Mystic Arcanum (no spell slot; it comes back with a Long Rest)" % (
                c["name"], name))
        elif p["level"] >= 1:
            slot = party.spend_slot(me, slot)
        if comp and p["components"].get("consumed"):
            bag, have = comp[1]
            bag.take(have[0]["item"], 1, "%s's %s" % (c["name"], name))
        if p["concentration"]:
            party.start_concentration(me, name)
        if mplan:
            import live_sorcery
            live_sorcery.of(self.fight).pay(me, name, mplan, careful=self._meta["careful"], heightened=self._meta["heighten"])
            if "Extended Spell" in mplan["metas"] and party.concentrates(me) == name:
                party.__dict__.setdefault("extended", {})[me] = name
        dc = party.spell_dc(c)
        label = name + (" (a level %d slot)" % slot if p["level"] >= 1 and not free else
                        " (Mystic Arcanum)" if free else "")
        ctx = {"caster": c["name"], "dc": dc, "choice": choice or "", "target": ", ".join(self.sim.by_id(x)["name"] for x in
               dict.fromkeys(targets)) or "no one", "dice": self.dice(p, slot, c, 0)[0] if p["damage"] else ""}
        held, failed = set(), set()
        out_targets = list(dict.fromkeys(targets))
        if p["kind"] == "attack":
            out_targets = self.attacks(me, c, p, slot, targets, choice, label, held, failed)
        elif p.get("rays"):
            failed = self.rays(me, c, p, targets, label, dc, aim)
        elif p["kind"] == "save":
            held, failed = self.saves(me, c, p, slot, targets, choice, label, dc, aim)
        elif p["kind"] == "heal":
            self.heal(me, c, p, slot, targets, label)
        elif p["kind"] == "auto":
            self.darts(me, c, p, slot, targets, label)
        elif p["kind"] == "mark":
            self.mark(me, c, p, targets[0], label)
        elif p["kind"] == "word":
            failed = self.word(me, c, p, targets, label, dc)
        elif p["kind"] == "buff":
            held = self.buff(me, c, p, targets, label)
        if p["level"] == 0 and failed and p["damage"]:                # group 3: Improved Blessed Strikes
            import high_levels
            high_levels.improved_blessed(party, me, c, p, bool(failed))
        if p["concentration"]:
            if p.get("ends_on_save") and not failed:             # Phantasmal Killer: a success ends the spell
                party.end_concentration(me)
                self.sim.say("dice", "%s: every target saved and the spell ends: %s's Concentration ends" % (name, c["name"]))
            else:
                self.hold(me, c, p, held)
        when = p.get("gm_when", "failed")              # failed: a creature failed its save (or was hit); always
        if when == "killed":                           # Finger of Death: a Humanoid it killed
            failed = {x for x in failed if self.sim.down(x) and "humanoid" in str(self.sim.by_id(x).get("type", "")).lower()}
        elif when == "prone":                          # Power Word Heal: a Prone creature may stand
            failed = {x for x in out_targets if self.sim.gm_rules.has(x, "Prone")}
        if p.get("gm") and (when == "always" or failed):
            if failed:
                ctx["target"] = ", ".join(self.sim.by_id(x)["name"] for x in out_targets if x in failed)
            text = p["gm"].format(**ctx)
            n = self.fight.add_ask(me, c["name"], "spell", name, out_targets, "the GM rules the rest: " + text)
            self.sim.say("turn", "%s: the GM rules the rest (request %d): %s" % (name, n, text))
        effect = self.effect(me, p, out_targets, aim, choice)
        if free:
            effect["_cmd"] = dict(effect.get("_cmd") or {}, free="the Mystic Arcanum")
        return effect

    def check_leap(self, me, p, first, tid):
        """Chain Lightning (SRD 5.2.1): a later target is another creature "within 30 feet of the first target", each
        targeted by only one bolt (the bolt leaps from the first: no wall between them)."""
        target = next((o for o in self.sim.sc["combatants"] if o["id"] == tid), None)
        party = self.party
        if target is None or tid in (me, first):
            raise GeneralError("Choose another creature for each of %s's bolts." % p["name"])
        if self.sim.down(tid):
            raise GeneralError("%s is down." % target["name"])
        if party.dist(first, tid) > p["leap_ft"] + 0.01:
            raise GeneralError("%s is %d ft from %s: the bolts leap only %d ft from the first target." % (
                target["name"], round(party.dist(first, tid)), party.name(first), p["leap_ft"]))
        if party.blocked(first, tid):
            raise GeneralError("A wall stands between %s and %s." % (party.name(first), target["name"]))
        return target

    # ------------------------------------------------------------------ areas
    def units(self):
        return self.sim.sc.get("units", 5)

    def area(self, me, p, pt, slot=None, pts=(), cmd=None):
        """The creatures inside the area aimed at pt (pts: Meteor Swarm's points), and where it was aimed (the referee
        and the page read it)."""
        spells, party, u = self.fight.spells, self.party, self.units()
        size, shape = p["area"]["size_ft"], p["shape"]
        here = party.pos(me)
        if shape == "sphere":
            size = spell_rules.area_at(dict(p["rules"], area=p["area"]), slot)["size_ft"]   # Confusion's grows
            spells.check_point(me, p["name"], {"range_ft": p["range_ft"]}, *pt)
            inside = [i for i in spells.sphere_targets(pt, size) if self.may_catch(me, p, i)]
            if p.get("heal_area"):                                    # Mass Cure Wounds: up to six of the caster's side
                inside = self.healed_in(me, p, inside, pt, cmd)
            return inside, {"origin": list(pt), "radius_ft": size}
        if shape == "spheres":                                        # Meteor Swarm: each creature once
            if not 1 <= len(pts) <= p["area"]["points"] or len(set(pts)) != len(pts):
                raise GeneralError("%s falls on 1 to %d different points." % (p["name"], p["area"]["points"]))
            inside = []
            for q in pts:
                spells.check_point(me, p["name"], {"range_ft": p["range_ft"]}, *q)
                inside += [i for i in spells.sphere_targets(q, size) if i not in inside and self.may_catch(me, p, i)]
            return inside, {"origin": list(pts[0]), "origins": [list(q) for q in pts], "radius_ft": size}
        if shape == "wall":
            if (cmd or {}).get("choice") == "Ring":                   # group 2: Wall of Fire's ring
                return self.ring(me, p, pt)
            return self.wall(me, p, pt)
        if shape == "cone":
            inside, angle = spells.cone_targets(me, pt, size)
            return [i for i in inside if self.may_catch(me, p, i)], {"origin": list(here), "angle_deg": angle, "length_ft": size}
        if shape == "line":
            dx, dy = pt[0] - here[0], pt[1] - here[1]
            n = math.hypot(dx, dy)
            if n < 1e-9:
                raise GeneralError("Aim the Line away from the caster.")
            ux, uy = dx / n, dy / n
            half, reach = p["area"].get("width_ft", 5) / 2, size + (self.sim.size_sq(me) - 1) / 2 * u
            out = []
            for i in spells.creatures():
                if i == me:
                    continue
                x, y = party.pos(i)
                vx, vy = x - here[0], y - here[1]
                along, across = (vx * ux + vy * uy) * u, abs(vx * uy - vy * ux) * u
                if 0 < along <= reach + 0.01 and across <= half - 0.01 and not party.walled(here, (x, y)):
                    out.append(i)
            return [i for i in out if self.may_catch(me, p, i)], {"origin": list(here), "angle_deg": math.degrees(math.atan2(uy, ux)),
                                                                  "length_ft": size, "width_ft": p["area"].get("width_ft", 5),
                                                                  "toward": [ux, uy]}
        n = int(round(size / u))
        if shape == "cube":
            spells.check_point(me, p["name"], {"range_ft": p["range_ft"]}, *pt)
            x0, y0 = pt[0] + 0.5 - math.ceil(n / 2), pt[1] + 0.5 - math.ceil(n / 2)
            box = [x0, y0, x0 + n, y0 + n]
            origin = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
        else:                                                         # a Cube from the caster: beside its space
            dx = (pt[0] > here[0]) - (pt[0] < here[0])
            dy = (pt[1] > here[1]) - (pt[1] < here[1])
            if not dx and not dy:
                raise GeneralError("Aim %s beside the caster." % p["name"])
            half = self.sim.size_sq(me) / 2
            def span(h, d):
                if d > 0:
                    return h + half, h + half + n
                if d < 0:
                    return h - half - n, h - half
                return h - n / 2, h + n / 2
            (bx0, bx1), (by0, by1) = span(here[0], dx), span(here[1], dy)
            box = [bx0, by0, bx1, by1]
            origin = (here[0] + dx * half, here[1] + dy * half)
            aim_dir = (dx, dy)
        out = []
        for i in spells.creatures():
            if i == me:
                continue
            x, y = party.pos(i)
            if box[0] < x < box[2] and box[1] < y < box[3] and not party.walled(origin, (x, y)):
                out.append(i)
        aim = {"origin": list(origin), "cube": box, "size_ft": size}
        if shape == "cube_self":
            aim["push"] = aim_dir
        return [i for i in out if self.may_catch(me, p, i)], aim

    def wall(self, me, p, pt):
        """Wall of Fire (SRD 5.2.1): "up to 60 feet long ... and 1 foot thick" on a point in range. Here a straight wall
        centred on that square, across the caster's view of it (the nearest of the eight directions), through the
        squares' centres: 12 squares when it runs along the grid, 8 on a diagonal (measured straight, 60 ft). Each
        creature in a square it crosses is in its area (no wall of the map between it and the wall's end or the
        caster)."""
        spells, party, u = self.fight.spells, self.party, self.units()
        spells.check_point(me, p["name"], {"range_ft": p["range_ft"]}, *pt)
        here = party.pos(me)
        k = round((math.atan2(pt[1] - here[1], pt[0] - here[0]) + math.pi / 2) / (math.pi / 4)) if pt != tuple(here) else 0
        sx, sy = round(math.cos(k * math.pi / 4)), round(math.sin(k * math.pi / 4))
        step = math.hypot(sx, sy)
        n = int(p["area"]["size_ft"] // (u * step))
        squares = [(pt[0] + (j - n // 2) * sx, pt[1] + (j - n // 2) * sy) for j in range(n)]
        ux, uy = sx / step, sy / step
        origin = (squares[0][0] - ux * step / 2, squares[0][1] - uy * step / 2)
        cells, out = set(squares), []
        for i in spells.creatures():
            x, y = party.pos(i)
            span = self.sim.size_sq(i)
            mine = {(round(x + a - (span - 1) / 2), round(y + b - (span - 1) / 2)) for a in range(span) for b in range(span)}
            if mine & cells and not party.walled(origin, (x, y)) and not party.walled(here, (x, y)):
                out.append(i)
        return out, {"origin": [origin[0], origin[1]], "angle_deg": math.degrees(math.atan2(uy, ux)),
                     "length_ft": p["area"]["size_ft"], "width_ft": 5, "toward": [ux, uy], "wall": [list(q) for q in squares]}

    def ring(self, me, p, pt):
        """Wall of Fire's other shape (SRD 5.2.1): "a ringed wall up to 20 feet in diameter, 20 feet high, and 1 foot
        thick", centred on a point in range: here the squares whose centres lie 10 ft (2 squares, rounded) from that
        square's centre. A creature with a square on the ring is in its area."""
        spells, party, u = self.fight.spells, self.party, self.units()
        spells.check_point(me, p["name"], {"range_ft": p["range_ft"]}, *pt)
        r = 10 / u
        cells = {(pt[0] + i, pt[1] + j) for i in range(-3, 4) for j in range(-3, 4) if round(math.hypot(i, j)) == round(r)}
        out = []
        for i in spells.creatures():
            x, y = party.pos(i)
            span = self.sim.size_sq(i)
            mine = {(round(x + a - (span - 1) / 2), round(y + b - (span - 1) / 2)) for a in range(span) for b in range(span)}
            if mine & cells:
                out.append(i)
        return out, {"origin": list(pt), "radius_ft": 10, "ring": True, "wall": sorted([list(q) for q in cells])}

    def healed_in(self, me, p, inside, pt, cmd):
        """Mass Cure Wounds: "Choose up to six creatures in a 30-foot-radius Sphere": the ones the player listed
        (cmd["targets"]), else the caster's side inside, the nearest the point first; never the dead."""
        party = self.party
        side = set([me] + party.allies(me))
        chosen = [x for x in (cmd or {}).get("targets") or [] if x in inside]
        pool = chosen or sorted([i for i in inside if i in side], key=lambda i: math.hypot(
            party.pos(i)[0] - pt[0], party.pos(i)[1] - pt[1]))
        return [i for i in pool if not party.deaths.get(i, {}).get("dead")][:p["area_max"] or ANY]

    def may_catch(self, me, p, i):
        """Every creature inside unless the text says otherwise: Hypnotic Pattern only those who can see the pattern;
        Weird "each creature of your choice" (the caster's foes)."""
        if p.get("sees"):
            gm = self.sim.gm_rules
            return not gm.has(i, "Blinded") and not gm.incapacitated(i)
        if p.get("foes_only"):
            return i in set(self.party.foes(me))
        return True

    # ------------------------------------------------------------------ resolving
    def save_roll(self, t, ability, dc, label, dis=False, origin=None, me=None):
        """GM 2026-10-25 (ruling S4): a Dexterity save adds cover against the effect's origin (SRD 5.2.1 Cover)."""
        gm, c = self.sim.gm_rules, self.sim.by_id(t)
        if gm.auto_fail(t, ability):
            cond = next((n for n in ("Paralyzed", "Petrified", "Stunned", "Unconscious") if gm.has(t, n)), "")
            self.sim.say("dice", "%s %s save against %s: fails automatically (%s)" % (c["name"], ABILITY[ability], label, cond))
            return False
        adv = ability == "dex" and c.get("dodging") and not gm.incapacitated(t)
        env = getattr(self.sim, "env", None)
        cover = env.cover_from(tuple(origin), t, me) if (env and ability == "dex" and origin and t != me) else 0
        return gm.condition_save(t, ability, dc, label, dis=dis, adv="Dodge" if adv else False, cover=cover)

    def saves(self, me, c, p, slot, targets, choice, label, dc, aim):
        """Each target saves; damage on a failure (half on a success when the spell says so), the conditions on a failure.
        Ice Knife: the attack first, then the shard's save for the target and each creature within 5 ft."""
        ab, half = p["save"]["ability"], p["save"]["half"]
        party, gm = self.party, self.sim.gm_rules
        if p["attack"]:                                              # Ice Knife
            tid = targets[0]
            dice, flat = self.dice(p, slot, c, 0)
            knife = {"name": p["name"], "atk": c.get("spell_atk", 5), "reach": p["range_ft"], "dmg": dice + ("+%d" % flat if flat else ""),
                     "crit": 20, "dmgtype": p["damage"][0]["type"]}
            self.sim.say("dice", "%s casts %s at %s" % (c["name"], label, party.name(tid)))
            party.attack(me, tid, knife, spell=True)
            near = (p.get("near") or {}).get("ft", 5)
            targets = [tid] + [i for i in self.fight.spells.creatures() if i != tid and party.dist(tid, i) <= near + 0.01]
            part = 1
        else:
            part = 0
        held, failed, hits = set(), set(), []                        # hits: [damage, type] of each part it deals
        meta = (getattr(self, "_meta", None) or {}).get("plan") or {}   # group 2: Metamagic on this cast
        careful, heighten = (getattr(self, "_meta", None) or {}).get("careful") or [], (getattr(self, "_meta", None) or {}).get("heighten") or []
        if p["damage"]:
            for k in (range(len(p["damage"])) if p["together"] else [part]):     # SPELLS-4-9: Flame Strike's two parts
                dice, flat = self.dice(p, slot, c, k)
                rolled = self.empowered_roll(dice, meta["empower"]) if meta.get("empower") and not hits else self.roll(dice)
                kind = meta["kind"] if meta.get("kind") and p["damage"][k]["type"] == meta.get("was") else p["damage"][k]["type"]
                hits.append([rolled + flat + (self.mod_bonus(p, c) if not hits else 0), kind, dice])
            for h in hits:                                          # Elemental Affinity: one damage roll
                plus = party.affinity(c, h[1])
                if plus:
                    self.sim.say("dice", "%s: Elemental Affinity, +%d %s damage" % (c["name"], plus, h[1].capitalize()))
                    h[0] += plus
                    break
            self.last_hits = [(n, k) for n, k, _ in hits]            # SPELL-OBJECTS-01: an object in the area takes it
            what = "%s%s" % (" and ".join("%s = %d %s" % (d, n, k.capitalize()) for n, k, d in hits),
                             ", half on a success" if half else ", none on a success")
        else:
            what = "or %s" % ("%s (%s)" % (choice, p["choice_cond"][choice]) if p.get("choice_cond") else
                              choice if p.get("choice") and choice in p["conditions"] + ["Blinded", "Deafened"]
                              else " and ".join(p["conditions"] + ([p["mark"]] if p.get("mark") else [])) or "affected")
        where = {"sphere": "%d-ft-radius Sphere" % p["area"]["size_ft"] if p["area"] else "",
                 "cone": "%d-ft Cone" % p["area"]["size_ft"] if p["area"] else "",
                 "line": "%d-ft Line" % p["area"]["size_ft"] if p["area"] else "",
                 "cube": "%d-ft Cube" % p["area"]["size_ft"] if p["area"] else "",
                 "cube_self": "%d-ft Cube" % p["area"]["size_ft"] if p["area"] else ""}.get(p["shape"], "")
        self.sim.say("dice", "%s casts %s%s: DC %d %s save, %s (%s)" % (
            c["name"], label, " (" + where + ")" if where else "", dc, ABILITY[ab], what,
            ", ".join(party.name(t) for t in dict.fromkeys(targets)) or "no creature inside"))
        for t in dict.fromkeys(targets):
            if self.sim.down(t):
                continue
            if t in careful:                                         # Careful Spell: it succeeds and takes no damage
                self.sim.say("dice", "%s succeeds on its save against %s and takes no damage (Careful Spell)" % (
                    party.name(t), p["name"]))
                continue
            dis = bool(p.get("dis_type") and p["dis_type"] in str(self.sim.by_id(t).get("type", "")).lower())
            origin = aim.get("origin") or (list(party.pos(me)) if p["shape"] != "creature" else None)
            if p["shape"] == "wall":                                 # a wall appears in the creature's own space: no
                origin = None                                        # point of origin to take cover from (SRD 5.2.1 Cover)
            kind_t = str(self.sim.by_id(t).get("type", "")).lower()
            if p.get("auto_fail_type") and p["auto_fail_type"] in kind_t:     # Blight: "A Plant creature automatically fails"
                self.sim.say("dice", "%s %s save against %s: fails automatically (a %s)" % (
                    party.name(t), ABILITY[ab], p["name"], p["auto_fail_type"].capitalize()))
                saved = False
            elif p.get("auto_save_type") and p["auto_save_type"] in kind_t:  # Flesh to Stone: Constructs succeed
                self.sim.say("dice", "%s %s save against %s: succeeds automatically (a %s)" % (
                    party.name(t), ABILITY[ab], p["name"], p["auto_save_type"].capitalize()))
                saved = True
            else:
                dis = "%s: Disadvantage" % p["dis_type"].capitalize() if dis else False
                if t in heighten:                                    # Heightened Spell: Disadvantage on this save
                    dis = "Heightened Spell"
                saved = self.save_roll(t, ab, dc, p["name"], dis=dis, origin=origin, me=me)
            if any(k == "fire" for _, k, _ in hits) and (not saved or half):   # GM 2026-10-25 (T10): fire lights oil
                import traps as oil_traps
                oil_traps.of(self.sim).ignite_creatures([t], me, "%s's %s" % (c["name"], p["name"]))
            evasion = bool(hits) and half and ab == "dex" and gm.has_evasion(t)
            if evasion:                                              # GM 2026-10-25 (S4): Evasion
                self.sim.say("dice", "%s: Evasion, %s" % (party.name(t), "no damage" if saved else "half damage"))
            wounds = self.sim.S.state(t)[0]
            for dmg, kind, _ in hits:
                amount = (dmg // 2 if half else 0) if saved else dmg
                if evasion:
                    amount = 0 if saved else dmg // 2
                    self.sim.say("dice", "%s: Evasion, %s" % (party.name(t), "no damage" if saved else "half damage"))
                if amount and not self.sim.down(t):
                    self.sim.S.pcDamage(me, t, "", amount, False, kind)
                    self.sim.settle()
            if not saved and p.get("rider") in ("dust", "harm"):     # Disintegrate, Harm
                self.after_damage(me, c, p, t, int(self.sim.S.state(t)[0] or 0) - int(wounds or 0))
            if saved and p.get("saved_speed0") and not self.sim.down(t):
                self.speed0(me, c, p, t)
            if saved or self.sim.down(t):
                continue
            if p.get("later_part"):                                  # Vitriolic Sphere: more acid at the end of its next turn
                later, _ = self.dice(p, slot, c, p["later_part"])
                party.__dict__.setdefault("acid_later", []).append({"by": me, "t": t, "dice": later, "spell": p["name"],
                                                                    "serial": int(self.sim.S.turnSerial or 0)})
                self.sim.say("dice", "%s: %s takes %s Acid more at the end of its next turn" % (p["name"], party.name(t), later))
            if p.get("rider") != "command" or choice not in ("Grovel", "Halt"):
                failed.add(t)                                         # the GM's part, when there is one
            if p.get("push_ft") and aim.get("push"):
                hx, hy = party.pos(me)
                x, y = party.pos(t)
                d = ((x > hx) - (x < hx), (y > hy) - (y < hy))
                party.push(t, d if d != (0, 0) else aim["push"], int(p["push_ft"] // 5))
            if self.conditions(me, c, p, t, choice, dc):
                held.add(t)
            if p.get("rider") == "mocked":
                self.rider(me, c, p, t)
            if p.get("rider") == "outlined_adv":
                gm.add(t, "Outlined", "(%s's %s: attacks against it have Advantage, no benefit from Invisible)" % (
                    c["name"], p["name"]), by=me, spell=p["name"], advantage=True)
                held.add(t)
            if p.get("rider") == "command":
                self.command(me, c, t, choice)
        return held, failed

    def conditions(self, me, c, p, t, choice, dc):
        """The spell's conditions on a creature that failed its save (or was hit): how long each lasts, from the rules.
        Returns True when a condition the spell holds was given."""
        gm, given = self.sim.gm_rules, False
        conds = [choice] if p.get("choice") and choice in p["conditions"] else list(p["conditions"])
        if p.get("choice_cond"):                                     # Eyebite: Asleep, Panicked or Sickened
            conds = [p["choice_cond"][choice]]
        if p.get("rider") == "command":
            conds = ["Prone"] if choice == "Grovel" else []
        if p.get("mark"):                                            # Confusion, Befuddlement: the engine's own mark
            conds = conds + [p["mark"]]
        for name in conds:
            if gm.cond_immune(t, name):
                self.sim.say("dice", "%s is immune to the %s condition" % (self.sim.by_id(t)["name"], name))
                continue
            lasts = p["lasts"].get(name) or ({"spell": True} if not p["instant"] or p["concentration"] else None)
            info = {"by": me, "spell": p["name"], "save": p["save"]["ability"] if p["save"] else None, "dc": dc}
            why = "(%s's %s" % (c["name"], p["name"])
            if lasts and lasts.get("rounds"):                        # Sunburst: "the Blinded condition for 1 minute"
                info["expires"] = int(self.sim.S.round() or 0) + lasts["rounds"]
                why += ", for %d rounds" % lasts["rounds"]
            elif lasts and lasts.get("until"):
                u = lasts["until"]
                info.update(lib=True, until=dict(u), skip=1 if u["who"] == "caster" and u["when"] == "end" else 0)
                why += ", until the %s of %s next turn" % (u["when"], "its" if u["who"] == "target" else c["name"] + "'s")
            elif lasts and lasts.get("spell") and not p["concentration"] and p["rounds"]:
                info["expires"] = int(self.sim.S.round() or 0) + p["rounds"]
                why += ", %s" % p["duration_text"].lower()
            elif p["concentration"]:
                why += ", while %s concentrates" % c["name"]
            if p.get("repeat"):
                info["repeat_spell"] = True
                why += ", saving again at the end of each of its turns"
            if p.get("ends_on_hurt") or (p.get("wakes") and choice == p["wakes"]):
                info["ends_on_hurt"] = True
                why += ", until it takes damage"
            if name == "Prone" and p.get("rider") == "command":
                info["command"] = True
            gm.add(t, name, why + ")", **info)
            given = given or bool(lasts) and name in (gm.cond.get(t) or {})
        return given

    # ------------------------------------------------------------------ SPELLS-4-9: what levels 4-9 add
    def after_damage(self, me, c, p, t, dealt):
        """Disintegrate: "If this damage reduces it to 0 Hit Points, it ... is disintegrated into gray dust" (a character
        can be revived only by True Resurrection or Wish). Harm: "its Hit Point maximum is reduced by an amount equal to
        the Necrotic damage it took ... can't reduce a target's Hit Point maximum below 1"."""
        s, party = self.sim.S, self.party
        if p["rider"] == "dust" and self.sim.down(t):
            self.sim.say("dice", "%s is disintegrated into gray dust (only True Resurrection or Wish can revive it)" % party.name(t))
            if self.sim.by_id(t).get("pc"):
                party.deaths.setdefault(t, {})["dead"] = True
                s.setField(t, "sim_dying", 0)
        elif p["rider"] == "harm" and dealt > 0:
            wounds, total = int(s.state(t)[0] or 0), int(s.state(t)[1] or 0)
            new = max(1, total - dealt)
            if self.sim.by_id(t).get("pc"):                          # a character's sheet keeps its maximum: the GM's
                n = self.fight.add_ask(me, c["name"], "spell", p["name"], [t], "the GM rules the rest: %s's Hit Point "
                                       "maximum is %d lower (%d), until the GM says it ends" % (party.name(t), total - new, new))
                self.sim.say("turn", "%s: %s's Hit Point maximum drops by %d to %d (request %d: the GM keeps it on the sheet)" % (
                    p["name"], party.name(t), total - new, new, n))
                return
            s.setField(t, "hptotal", new)                           # the same Hit Points left, a lower maximum
            s.setField(t, "wounds", max(0, wounds - (total - new)))
            self.sim.say("dice", "%s: %s's Hit Point maximum drops by %d to %d" % (p["name"], party.name(t), total - new, new))

    def speed0(self, me, c, p, t):
        """Speed 0 until the start of the caster's next turn (Flesh to Stone on a success; Power Word Stun above 150 HP)."""
        self.sim.gm_rules.add(t, "Slowed", "(%s's %s: Speed 0 until the start of %s's next turn)" % (c["name"], p["name"], c["name"]),
                              by=me, ft=999, ends=2, lib=True, until={"who": "caster", "when": "start"})

    def hp(self, t):
        s = self.sim.S
        return int(s.state(t)[1] or 0) - int(s.state(t)[0] or 0)

    def kill(self, me, c, p, t, why):
        """The power words' and Divine Word's "it dies": its Hit Points (and Temporary ones) to 0, a character dead."""
        s, party = self.sim.S, self.party
        self.sim.say("dice", "%s: %s dies (%s)" % (p["name"], party.name(t), why))
        s.pcDamage(me, t, "", self.hp(t) + int(s.getField(t, "sim_temp_hp") or 0), False, "")
        self.sim.settle()
        if self.sim.by_id(t).get("pc"):
            party.deaths.setdefault(t, {})["dead"] = True
            s.setField(t, "sim_dying", 0)

    def word(self, me, c, p, targets, label, dc):
        """The words of power (SRD 5.2.1), by the target's Hit Points now. Power Word Kill: 100 or fewer, it dies; else
        12d12 Psychic. Power Word Stun: 150 or fewer, Stunned (a Constitution save at the end of each of its turns ends
        it); else Speed 0 until the start of the caster's next turn. Divine Word: each creature of the caster's choice
        makes a Charisma save; on a failure, 0-20 HP it dies, 21-30 Blinded, Deafened and Stunned for 1 hour, 31-40
        Blinded and Deafened for 10 minutes, 41-50 Deafened for 1 minute; a Celestial, Elemental, Fey or Fiend that
        fails goes back to its plane (the GM's). Returns the creatures it affected."""
        gm, party, done = self.sim.gm_rules, self.party, set()
        rnd = int(self.sim.S.round() or 0)
        self.sim.say("dice", "%s casts %s on %s" % (c["name"], label, ", ".join(party.name(t) for t in dict.fromkeys(targets))))
        for t in dict.fromkeys(targets):
            if self.sim.down(t):
                continue
            hp = self.hp(t)
            if p["word"] == "kill":
                if hp <= 100:
                    self.kill(me, c, p, t, "%d Hit Points, 100 or fewer" % hp)
                else:
                    dice = p["damage"][0]["dice"]
                    self.sim.say("dice", "%s: %s has %d Hit Points (more than 100): %s Psychic" % (p["name"], party.name(t), hp, dice))
                    self.sim.S.pcDamage(me, t, dice, 0, False, p["damage"][0]["type"])
                    self.sim.settle()
                done.add(t)
            elif p["word"] == "stun":
                if hp <= 150:
                    gm.add(t, "Stunned", "(%s's %s: %d Hit Points, 150 or fewer; a Constitution save at the end of each of "
                           "its turns ends it)" % (c["name"], p["name"], hp), by=me, spell=p["name"], save="con", dc=dc,
                           repeat_spell=True)
                else:
                    self.sim.say("dice", "%s: %s has %d Hit Points (more than 150)" % (p["name"], party.name(t), hp))
                    self.speed0(me, c, p, t)
                done.add(t)
            else:                                                     # Divine Word
                if self.save_roll(t, "cha", dc, p["name"]) or self.sim.down(t):
                    continue
                done.add(t)
                tiers = ((20, None, 0), (30, ("Blinded", "Deafened", "Stunned"), 600), (40, ("Blinded", "Deafened"), 100),
                         (50, ("Deafened",), 10))
                tier = next((x for x in tiers if hp <= x[0]), None)
                if tier and tier[1] is None:
                    self.kill(me, c, p, t, "%d Hit Points, 20 or fewer" % hp)
                elif tier:
                    for cond in tier[1]:
                        if not gm.cond_immune(t, cond):
                            gm.add(t, cond, "(%s's %s: %d Hit Points, for %d rounds)" % (c["name"], p["name"], hp, tier[2]),
                                   by=me, spell=p["name"], expires=rnd + tier[2])
                else:
                    self.sim.say("dice", "%s: %s has %d Hit Points (more than 50): no effect" % (p["name"], party.name(t), hp))
                kind = str(self.sim.by_id(t).get("type", "")).lower()
                if any(k in kind for k in ("celestial", "elemental", "fey", "fiend")) and not self.sim.down(t):
                    n = self.fight.add_ask(me, c["name"], "spell", p["name"], [t], "the GM rules the rest: %s is forced back "
                                           "to its plane of origin and can't return for 24 hours" % party.name(t))
                    self.sim.say("turn", "%s: %s goes back to its plane (request %d: the GM removes it)" % (p["name"], party.name(t), n))
        return done

    def buff(self, me, c, p, targets, label):
        """A condition given to a creature the caster touches, for as long as it concentrates (Greater Invisibility:
        "A creature you touch has the Invisible condition until the spell ends"; unlike Invisibility it doesn't end on an
        attack or a spell). Returns the creatures that have it."""
        gm, held = self.sim.gm_rules, set()
        self.sim.say("dice", "%s casts %s on %s" % (c["name"], label, ", ".join(self.party.name(t) for t in targets)))
        for t in dict.fromkeys(targets):
            for cond in p["conditions"]:
                gm.add(t, cond, "(%s's %s, while %s concentrates)" % (c["name"], p["name"], c["name"]), by=me, spell=p["name"])
                if gm.has(t, cond):
                    held.add(t)
        return held

    RAYS = {1: ("Red", "fire"), 2: ("Orange", "acid"), 3: ("Yellow", "lightning"), 4: ("Green", "poison"), 5: ("Blue", "cold"),
            6: ("Indigo", "Restrained"), 7: ("Violet", "Blinded")}

    def rays(self, me, c, p, targets, label, dc, aim):
        """Prismatic Spray (SRD 5.2.1): each creature in the Cone makes a Dexterity save, and 1d8 says its ray: 1-5 12d6
        Fire, Acid, Lightning, Poison or Cold (half on a success); 6 Indigo, Restrained on a failure (then Constitution
        saves at the end of its turns: three failures Petrified, the GM counts); 7 Violet, Blinded on a failure (then a
        Wisdom save at the start of the caster's next turn, the GM's); 8 two rays (rolled again, rerolling 8s).
        Returns the creatures whose Indigo or Violet ray took hold."""
        gm, party, s = self.sim.gm_rules, self.party, self.sim.S
        dice = p["damage"][0]["dice"]
        self.sim.say("dice", "%s casts %s (%d-ft Cone): DC %d Dexterity save, a ray (1d8) for each creature (%s)" % (
            c["name"], label, p["area"]["size_ft"], dc, ", ".join(party.name(t) for t in targets) or "no creature inside"))
        held = {}
        for t in dict.fromkeys(targets):
            if self.sim.down(t):
                continue
            roll = self.sim.rng.randint(1, 8)
            rays = [roll] if roll < 8 else [self.reroll8(), self.reroll8()]
            self.sim.say("dice", "%s: 1d8 = %d -> %s" % (party.name(t), roll, " and ".join(self.RAYS[r][0] for r in rays)))
            saved = self.save_roll(t, "dex", dc, p["name"], origin=aim.get("origin"), me=me)
            evasion = gm.has_evasion(t)
            for r in rays:
                color, what = self.RAYS[r]
                if r <= 5:
                    dmg = self.roll(dice)
                    amount = (0 if saved else dmg // 2) if evasion else dmg // 2 if saved else dmg
                    self.sim.say("dice", "%s ray: %s = %d %s%s" % (color, dice, dmg, what.capitalize(),
                                                                ", %d taken" % amount if amount != dmg else ""))
                    if amount and not self.sim.down(t):
                        s.pcDamage(me, t, "", amount, False, what)
                        self.sim.settle()
                elif not saved and not self.sim.down(t) and not gm.cond_immune(t, what):
                    gm.add(t, what, "(%s's Prismatic Spray, the %s ray)" % (c["name"], color), by=me, spell=p["name"])
                    held.setdefault(t, []).append(color)
        if held:
            words = {"Indigo": "Restrained: a Constitution save (DC %d) at the end of each of its turns, three successes end it, "
                               "three failures turn it to stone (Petrified)" % dc,
                     "Violet": "Blinded: a Wisdom save (DC %d) at the start of %s's next turn; a success ends it, a failure "
                               "sends it to another plane (the GM's choice)" % (dc, c["name"])}
            for t, colors in held.items():
                text = "; ".join("%s, %s" % (party.name(t), words[k]) for k in colors)
                n = self.fight.add_ask(me, c["name"], "spell", p["name"], [t], "the GM rules the rest: " + text)
                self.sim.say("turn", "%s: the GM rules the rest (request %d): %s" % (p["name"], n, text))
        return set()

    def reroll8(self):
        while True:
            r = self.sim.rng.randint(1, 8)
            if r < 8:
                return r

    def command(self, me, c, t, word):
        """Command (SRD 5.2.1): the engine plays Grovel (Prone, then its turn ends: gm_rules turn_start), Halt (on its
        turn it doesn't move and takes no action or Bonus Action: its turn ends) and, SPELL-EFFECTS-01, Approach, Drop and
        Flee (sim/charms.py: a creature the game plays obeys them on its next turn)."""
        if word in ("Halt", "Approach", "Drop", "Flee"):
            gm = self.sim.gm_rules
            gm.add(t, "Commanded", "(%s's Command: %s on its next turn)" % (c["name"], word), by=me, command=word)

    def attacks(self, me, c, p, slot, targets, choice, label, held, failed):
        """A spell attack for each strike (beams, rays: in the order chosen, around again when fewer creatures than
        strikes); the damage of its dice (a cantrip's tier, the slot's), Hex's die on its creature, the riders."""
        party, n = self.party, self.strikes(p, slot, c)
        order = [targets[k % len(targets)] for k in range(n)]
        kind = choice if p.get("choice") and choice not in ("",) and p.get("rider") == "leap" else p["damage"][0]["type"]
        meta = (getattr(self, "_meta", None) or {}).get("plan") or {}
        if meta.get("kind") and kind == meta.get("was"):             # group 2: Transmuted Spell
            kind = meta["kind"]
        dice, flat = self.dice(p, slot, c, 0)
        flat += self.mod_bonus(p, c)
        what = "%d %ss" % (n, p["count"]["word"]) if p["count"] and n > 1 else "a %s spell attack" % p["attack"]
        self.sim.say("dice", "%s casts %s at %s: %s, %s%s %s" % (
            c["name"], label, ", ".join(party.name(t) for t in dict.fromkeys(order)), what, dice, "+%d" % flat if flat else "",
            kind.capitalize()))
        hit_list = []
        weapon = {"name": p["name"], "atk": c.get("spell_atk", 5), "reach": p["range_ft"] or 5, "dmg": dice + ("+%d" % flat if flat else ""),
                  "crit": 20, "dmgtype": kind, "one_affinity": n > 1}
        if p.get("rider") == "leap":
            return self.orb(me, c, p, slot, order[0], weapon, targets)
        for tid in order:
            if self.sim.down(tid):
                continue
            hexed = party.hex.get(me) == tid
            marked = self.marked(me) == tid
            extra = ";".join(x for x in ("1d6:necrotic" if hexed else "", "1d6:force" if marked else "") if x)
            note = ", ".join(x for x in ("Hex" if hexed else "", "Hunter's Mark" if marked else "") if x)
            before = self.sim.S.state(tid)[0]
            res = party.attack(me, tid, weapon, spell=True, bonus_dice=extra, note=note, retarget_grapple=False)
            self.sim.settle()
            if res in ("hit", "crit"):
                hit_list.append(tid)
                failed.add(tid)
                dealt = max(0, int(self.sim.S.state(tid)[0] or 0) - int(before or 0))
                self.on_hit(me, c, p, tid, slot, dealt, held)
            elif p.get("rider") == "acid_later" and res == "miss":
                half = self.roll(dice) // 2
                self.sim.say("dice", "%s misses: the acid splashes %s for half the initial damage (%d)" % (p["name"], party.name(tid), half))
                if half:
                    self.sim.S.pcDamage(me, tid, "", half, False, kind)
                    self.sim.settle()
        return list(dict.fromkeys(order))

    def card_hit(self, me, c, name, tid):
        """A spell attack from the sheet's attack cards hit: what the spell does beyond its damage, as when it is cast here."""
        p = PLAYS.get(name) or {}
        if p.get("rider"):
            self.rider(me, c, {"rider": p["rider"], "name": name}, tid)
        if p.get("gm"):
            text = p["gm"].format(caster=c["name"], target=self.party.name(tid))
            n = self.fight.add_ask(me, c["name"], "spell", name, [tid], "the GM rules the rest: " + text)
            self.sim.say("turn", "%s: the GM rules the rest (request %d): %s" % (name, n, text))

    def on_hit(self, me, c, p, tid, slot, dealt, held):
        party, gm = self.party, self.sim.gm_rules
        if p["conditions"] and not self.sim.down(tid):
            if self.conditions(me, c, p, tid, None, party.spell_dc(c)):
                held.add(tid)
        if self.sim.down(tid):
            return
        r = p.get("rider")
        if r:
            self.rider(me, c, p, tid, slot=slot, dealt=dealt)

    def rider(self, me, c, p, tid, slot=0, dealt=0):
        """The extra a cantrip or spell gives on a hit (or a failed save), read from its text."""
        party, gm, s, r = self.party, self.sim.gm_rules, self.sim.S, p.get("rider")
        name = party.name(tid)
        if r == "slow":
            gm.add(tid, "Slowed", "(%s's Ray of Frost: Speed -10 ft until the start of %s's next turn)" % (c["name"], c["name"]),
                   by=me, ft=10, ends=2, lib=True, until={"who": "caster", "when": "start"})
        elif r == "no_reaction":                         # GM 2026-10-25 (S2): only Opportunity Attacks (SRD 5.2.1)
            s.setField(tid, "sim_no_oa", 1)
            self.sim.say("dice", "Shocking Grasp: %s can't make Opportunity Attacks until the start of its next turn" % name)
        elif r == "outlined":
            gm.add(tid, "Outlined", "(%s's Starry Wisp: no benefit from Invisible until the end of %s's next turn)" % (
                c["name"], c["name"]), by=me, lib=True, until={"who": "caster", "when": "end"}, skip=1)
        elif r == "mocked":
            s.setField(tid, "sim_mocked", 1)
            party.mocked.setdefault(me, set()).add(tid)
            self.sim.say("dice", "Vicious Mockery: %s has Disadvantage on its next attack roll" % name)
        elif r == "acid_later":
            later, _ = self.dice(p, slot, c, 1)
            party.__dict__.setdefault("acid_later", []).append({"by": me, "t": tid, "dice": later, "serial": int(s.turnSerial or 0),
                                                                "spell": p["name"]})
            self.sim.say("dice", "%s: %s takes %s Acid more at the end of its next turn" % (p["name"], name, later))
        elif r == "drain" and dealt:
            heal = dealt // 2
            if heal:
                party.revive(me, heal) if self.sim.down(me) else s.heal(me, heal)
                self.sim.say("dice", "%s regains %d HP (Vampiric Touch: half the Necrotic damage)" % (c["name"], heal))

    def orb(self, me, c, p, slot, first, weapon, chosen):
        """Chromatic Orb (SRD 5.2.1): the attack, then 3d8 of the chosen type (+1d8 a slot level above 1); when two or
        more d8s match, the orb leaps to another creature within 30 ft of the target (the next one the player chose, else
        the nearest foe), up to the slot's level in leaps, each creature once."""
        party, s = self.party, self.sim.S
        n, d = _dice(weapon["dmg"])
        kind, done, tid, leaps = weapon["dmgtype"], [], first, 0
        while tid is not None:
            done.append(tid)
            res = party.attack(me, tid, dict(weapon, dmg="0d8"), spell=True, retarget_grapple=False)
            self.sim.settle()
            dup = False
            if res in ("hit", "crit"):
                rolls = [self.sim.rng.randint(1, d) for _ in range(n * (2 if res == "crit" else 1))]
                dup = len(set(rolls[:n])) < n
                self.sim.say("dice", "Chromatic Orb: %s = %d %s%s" % ("+".join(map(str, rolls)), sum(rolls), kind.capitalize(),
                                                                      ", a double: the orb leaps" if dup else ""))
                s.pcDamage(me, tid, "", sum(rolls), False, kind)
                self.sim.settle()
            if not dup or leaps >= max(1, slot):
                break
            leaps += 1
            here = tid
            near = [x for x in list(chosen) + party.foes(me) if x not in done and not self.sim.down(x)
                    and party.dist(here, x) <= 30.01 and self._can_target(me, p, x)]
            tid = near[0] if near else None
        return done

    def _can_target(self, me, p, tid):
        try:
            self.check_target(me, p, tid)
            return True
        except GeneralError:
            return False

    def darts(self, me, c, p, slot, targets, label):
        """Magic Missile: each dart hits (no roll), 1d4 + 1 Force, at the creatures chosen (around again when fewer)."""
        n = self.strikes(p, slot, c)
        order = [targets[k % len(targets)] for k in range(n)]
        dice, flat = self.dice(p, slot, c, 0)
        kind = p["damage"][0]["type"]
        self.sim.say("dice", "%s casts %s: %d %ss, %s+%d %s each (%s)" % (c["name"], label, n, p["count"]["word"], dice, flat,
                                                                         kind.capitalize(), ", ".join(self.party.name(t) for t in order)))
        shielded = set()                                             # SPELL-BATCH-02: Shield, no Magic Missile damage
        if p["name"] == "Magic Missile":
            live = getattr(self.sim, "live", None)
            reactions = getattr(live, "reactions", None)
            ab = getattr(self.sim, "abilities", None)
            for tid in dict.fromkeys(order):
                if reactions.shield_missile(tid, me) if reactions else (
                        tid in self.party.shielded or bool(ab and tid in ab.shielded)):
                    shielded.add(tid)
                    self.sim.say("dice", "%s's Shield: no damage from %s" % (self.party.name(tid), label))
        for tid in order:
            if tid in shielded:
                continue
            if not self.sim.down(tid):
                self.sim.S.pcDamage(me, tid, dice, flat, False, kind)
                self.sim.settle()

    def heal(self, me, c, p, slot, targets, label):
        """Healing dice (and the modifier, Disciple of Life), or a number (Heal's 70), or all the Hit Points lost (Power
        Word Heal), or a pool divided in the order the creatures were chosen, each healed up to its maximum (Mass Heal's
        700); then the conditions the spell ends (cures)."""
        party, gm, s = self.party, self.sim.gm_rules, self.sim.S
        dice, flat = ("", 0) if p["healing"]["dice"] == "all" else self.dice(p, slot, c, 0)
        bonus = flat + self.mod_bonus(p, c)
        extra = party.healing_bonus(me, c, slot, any(a != me for a in targets)) if slot else 0
        pool = p.get("pool")
        for a in dict.fromkeys(targets):
            lost = int(s.state(a)[0] or 0)
            if p["healing"]["dice"] == "all":
                amount, how = lost, "all its lost Hit Points"
            elif pool is not None:
                amount, how = min(pool, lost), "%d of %d left" % (min(pool, lost), pool)
                pool -= amount
            else:
                amount = self.roll(dice) + bonus + extra
                how = "%s%s%s" % (dice or "", (" + %d" if dice else "%d") % bonus if bonus else "",
                                  " + %d Disciple of Life" % extra if extra else "")
            self.sim.say("dice", "%s casts %s on %s: %s = %d HP" % (c["name"], label, party.name(a), how, amount))
            if amount:
                party.revive(a, amount)
            for cond in p.get("cures") or ():                         # Mass Heal: "Creatures healed by this spell"
                if gm.has(a, cond) and (amount or p.get("pool") is None):
                    gm.remove(a, cond, "%s ends it" % p["name"])

    def mark(self, me, c, p, tid, label):
        """Hunter's Mark (SRD 5.2.1): +1d6 Force whenever the caster hits the creature with an attack roll, while the
        caster concentrates (live_play adds the die to its attacks)."""
        self.party.__dict__.setdefault("marked", {})[me] = tid
        self.sim.say("dice", "%s casts %s on %s (Bonus Action, Concentration): +1d6 Force on each hit" % (c["name"], label, self.party.name(tid)))

    def marked(self, me):
        party = self.party
        tid = getattr(party, "marked", {}).get(me)
        return tid if tid is not None and party.concentrates(me) == "Hunter's Mark" else None

    def moves_mark(self, me, name):
        """Hunter's Mark (SRD 5.2.1): "If the target drops to 0 Hit Points before this spell ends, you can take a Bonus
        Action to move the mark to a new creature you can see within range" (GM 2026-10-24: on any turn it is held)."""
        party = self.party
        tid = getattr(party, "marked", {}).get(me)
        return (name == "Hunter's Mark" and tid is not None and party.concentrates(me) == "Hunter's Mark"
                and self.sim.down(tid))

    def hold(self, me, c, p, held):
        """Concentration: a spell that holds conditions is held while one creature still has them (Party.control, as Hold
        Person); one with none to hold (Mind Spike, Moonbeam, Hunter's Mark) is held as itself."""
        party = self.party
        if p["conditions"] or p.get("rider") == "outlined_adv" or p.get("mark"):
            if held:
                party.control[me] = {"spell": p["name"], "targets": set(held)}
            elif p.get("gm_when") == "always":                       # Entangle: the plants stay while it concentrates
                party.__dict__.setdefault("gm_concentration", {})[me] = p["name"]
            else:
                party.holds_no_one(me, p["name"])            # GM 2026-10-25 (S3): a player keeps concentrating
            return
        party.__dict__.setdefault("gm_concentration", {})[me] = p["name"]

    # ------------------------------------------------------------------ what the table draws
    def effect(self, me, p, targets, aim, choice):
        party = self.party
        dmg = (p["damage"][0]["type"] if p["damage"] else "")
        appearance = "healing" if p["kind"] == "heal" else APPEAR.get(choice if p.get("rider") == "leap" else dmg, "arcane")
        e = {"spell": p["name"], "appearance": appearance, "from": list(party.pos(me))}
        shape = p["shape"]
        if shape == "creature":
            first = targets[0] if targets else me
            x, y = party.pos(first)
            e.update(shape="circle", origin=[x, y], radius_ft=5, targets=list(targets))
            if len(set(targets)) > 1:
                e["_cmd"] = {"targets": list(targets)}
        elif shape in ("sphere", "spheres"):                         # Meteor Swarm: origins, one circle each
            e.update(shape="circle", origin=aim["origin"], radius_ft=aim["radius_ft"], targets=list(targets))
            if len(aim.get("origins") or []) > 1:
                e["origins"] = aim["origins"]
        elif shape == "wall" and aim.get("ring"):                     # group 2: the ring, drawn as its circle
            e.update(shape="circle", origin=aim["origin"], radius_ft=aim["radius_ft"], targets=list(targets), wall=aim["wall"],
                     ring=True)
        elif shape == "wall":                                         # Wall of Fire: the table draws it as a Line
            e.update(shape="line", origin=aim["origin"], angle_deg=aim["angle_deg"], length_ft=aim["length_ft"],
                     width_ft=aim["width_ft"], toward=aim["toward"], targets=list(targets), wall=aim["wall"])
        elif shape == "cone":
            e.update(shape="cone", origin=aim["origin"], angle_deg=aim["angle_deg"], length_ft=aim["length_ft"],
                     width_ft=aim["length_ft"], targets=list(targets))
        elif shape == "line":
            e.update(shape="line", origin=aim["origin"], angle_deg=aim["angle_deg"], length_ft=aim["length_ft"],
                     width_ft=aim["width_ft"], toward=aim["toward"], targets=list(targets))
        else:                                                         # a Cube: the table draws a rectangle
            x0, y0, x1, y1 = aim["cube"]
            e.update(shape="rectangle", origin=[x0, (y0 + y1) / 2], angle_deg=0, length_ft=aim["size_ft"],
                     width_ft=aim["size_ft"], cube=list(aim["cube"]), targets=list(targets))
            e["cube_origin"] = aim["origin"]
        if p.get("rider") == "leap" and targets:
            e["_cmd"] = {"targets": list(targets)}
        return e

    # ------------------------------------------------------------------ the sheet's cards
    def offers(self, me):
        import live_spells
        c, out = self.sim.by_id(me), []
        pool = live_spells.slots_of(self.party, me)
        for name in self.known(c):
            p = plan(name)
            ready, rows = rq.check(self.needs(me, name)[0])
            slots = [lv for lv in range(max(1, p["level"]), len(pool) + 1) if pool[lv - 1] > 0] if p["level"] else []
            top = max(slots) if slots else p["level"]
            most = min(self.most_targets(p, top, c) or 1, len(self.sim.sc["combatants"]))   # "any number": all here
            shape = "creatures" if p["shape"] == "creature" and most > 1 else p["shape"]
            dmg = (p["damage"][0]["type"] if p["damage"] else "")
            e = {"name": name, "level": p["level"], "time": p["time"], "shape": shape, "general": True,
                 "appearance": "healing" if p["kind"] == "heal" else APPEAR.get(dmg, "arcane"),
                 "range_ft": p["range_ft"], "concentration": p["concentration"], "ready": ready,
                 "why": "" if ready else rq.first_why(rows), "slots_ok": slots, "kind": p["kind"],
                 "objects": __import__("spell_objects").objects(name),   # SPELL-OBJECTS-01: no, also or only
                 "upcast": bool(p["scaling"].get("dice_per_level") or p["scaling"].get("extra_targets_per_level")
                                or (p["count"] or {}).get("per_level") or p["heal_step"])}
            if p["shape"] == "creature" and most > 1:
                e["max_targets"] = most
                if p["count"]:
                    e["strikes"] = most
            if p["area"]:
                key = {"sphere": "radius_ft", "spheres": "radius_ft", "cone": "length_ft", "line": "length_ft",
                       "wall": "length_ft"}.get(p["shape"], "size_ft")
                e[key] = p["area"]["size_ft"]
                if p["shape"] == "line":
                    e["width_ft"] = p["area"].get("width_ft", 5)
                if p["shape"] == "spheres":
                    e["points"] = p["area"]["points"]
                if p["shape"] == "sphere" and spell_rules.area_at(p["rules"], top) != p["area"]:
                    e["grows"] = True                                  # Confusion: a higher slot, a bigger Sphere
                    e["upcast"] = True
            lv = self.arcanum(me, name)
            if lv:                                                   # SPELLS-4-9: the Mystic Arcanum
                e["arcanum"] = {"level": lv, "left": self.arcanum_left(me, lv)}
                if self.by_arcanum(me, name):
                    e["slots_ok"], e["upcast"] = [], False
            if p.get("choice"):
                e["choices"] = list(p["choice"])
            if p.get("gm"):
                e["gm_rules"] = p["gm"].format(caster=c["name"], target="the target", dc=self.party.spell_dc(c),
                                               choice="the command" if name == "Command" else "the chosen ability", dice=self.dice(p, top, c, 0)[0] if p["damage"] else "")
            if p.get("rider"):
                e["rider"] = RIDER_TEXT.get(p["rider"], "")
            if c.get("metamagic"):                                   # group 2 (GM 2026-10-27): the Sorcerer's options
                import live_sorcery
                e["metamagic"] = live_sorcery.of(self.fight).options(me, name, self.meta_entry(p))
            held = self.party.concentrates(me)
            if self.moves_mark(me, name):
                e["moves"] = "Move Hunter's Mark to a new creature (Bonus Action, no spell slot)"
            elif p["concentration"] and held:
                e["ends"] = held
            link = rq.first_link(rows)
            if link and not ready:
                e["link"] = link
            if p["shape"] == "creature" and ready:
                ok, no = [], {}
                for o in self.sim.sc["combatants"]:
                    try:
                        self.check_target(me, p, o["id"])
                        ok.append(o["id"])
                    except GeneralError as err:
                        no[o["id"]] = str(err)
                e["targets"], e["refused"] = ok, no
            out.append(e)
        return out


def of(fight):
    g = getattr(fight, "_general", None)
    if g is None:
        g = fight._general = General(fight)
    return g


# ------------------------------------------------------------------ the engine's later moments (party.py hooks)
def turn_ended(party, ctid):
    """End of a creature's turn: Acid Arrow's later damage (at the end of the target's next turn)."""
    later = party.__dict__.get("acid_later") or []
    s = party.s
    for a in list(later):
        if a["t"] == ctid and int(s.turnSerial or 0) > a["serial"]:
            later.remove(a)
            if party.sim.down(ctid):
                continue
            party.sim.say("dice", "%s: the acid burns %s at the end of its turn: %s Acid" % (a["spell"], party.name(ctid), a["dice"]))
            s.pcDamage(a["by"], ctid, a["dice"], 0, False, "acid")
            party.sim.settle(0.2)
