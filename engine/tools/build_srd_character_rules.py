"""CHARACTERS-01 (GM 2026-10-21: "a first rate character builder"): build sim/srd_character_rules.json, the SRD 5.2.1
character rules the simulator service checks characters with (sim/character_rules.py): every class with its features by
level, its one SRD subclass, spell progressions and resources; species, backgrounds, feats, weapons, armor, and all 339
spells with level, school and class lists.

  py tools/build_srd_character_rules.py SRD_CC_v5.2.1-flow.txt

The input is `pdftotext -enc UTF-8 SRD_CC_v5.2.1.pdf flow.txt` of the official SRD 5.2.1 PDF (CC-BY-4.0). Spells and the
"Level N: Feature" headings are read from that text; the class tables below were transcribed from the same PDF's class
feature tables and checked against it. Nothing here comes from any other source: only SRD 5.2.1 ships (content policy).
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "sim" / "srd_character_rules.json"
CLASSES = ["Barbarian", "Bard", "Cleric", "Druid", "Fighter", "Monk", "Paladin", "Ranger", "Rogue", "Sorcerer", "Warlock",
           "Wizard"]
SCHOOLS = "Abjuration|Conjuration|Divination|Enchantment|Evocation|Illusion|Necromancy|Transmutation"
SKILLS = ["Acrobatics", "Animal Handling", "Arcana", "Athletics", "Deception", "History", "Insight", "Intimidation",
          "Investigation", "Medicine", "Nature", "Perception", "Performance", "Persuasion", "Religion", "Sleight of Hand",
          "Stealth", "Survival"]
SKILL_ABILITY = {"Acrobatics": "dex", "Animal Handling": "wis", "Arcana": "int", "Athletics": "str", "Deception": "cha",
                 "History": "int", "Insight": "wis", "Intimidation": "cha", "Investigation": "int", "Medicine": "wis",
                 "Nature": "int", "Perception": "wis", "Performance": "cha", "Persuasion": "cha", "Religion": "int",
                 "Sleight of Hand": "dex", "Stealth": "dex", "Survival": "wis"}


def per_level(spec):
    """'2:1-2,3:3-5' -> 20 values (0 where no range covers the level)."""
    out = [0] * 20
    for part in spec.split(","):
        v, r = part.split(":")
        a, _, b = r.partition("-")
        for lv in range(int(a), int(b or a) + 1):
            out[lv - 1] = int(v) if re.fullmatch(r"-?\d+", v) else v
    return out


def seq(text):
    return [int(v) for v in text.split()]


# hit die, saves, primary (all of / any of), skill count, skill list ('*' = any), armor, weapons, multiclass gains,
# caster kind, casting ability, cantrips by level, prepared spells by level (Core Traits tables + class tables, SRD 5.2.1)
CLASS_ROWS = {
    "Barbarian": dict(hit_die=12, saves=["str", "con"], primary=["str"], primary_any=False, skill_count=2,
                      skills=["Animal Handling", "Athletics", "Intimidation", "Nature", "Perception", "Survival"],
                      armor=["light", "medium", "shield"], weapons=["simple", "martial"],
                      multiclass=dict(armor=["shield"], weapons=["martial"], skills=0, tools=""),
                      caster="none", ability=None, page=28,
                      resources=dict(rages=per_level("2:1-2,3:3-5,4:6-11,5:12-16,6:17-20"),
                                     rage_damage=per_level("2:1-8,3:9-15,4:16-20"),
                                     weapon_mastery=per_level("2:1-3,3:4-9,4:10-20"))),
    "Bard": dict(hit_die=8, saves=["dex", "cha"], primary=["cha"], primary_any=False, skill_count=3, skills="*",
                 armor=["light"], weapons=["simple"], multiclass=dict(armor=["light"], weapons=[], skills=1,
                                                                      tools="one Musical Instrument"),
                 caster="full", ability="cha", page=31,
                 cantrips=seq("2 2 2 3 3 3 3 3 3 4 4 4 4 4 4 4 4 4 4 4"),
                 prepared=seq("4 5 6 7 9 10 11 12 14 15 16 16 17 17 18 18 19 20 21 22"),
                 resources=dict(inspiration_die=per_level("6:1-4,8:5-9,10:10-14,12:15-20"))),
    "Cleric": dict(hit_die=8, saves=["wis", "cha"], primary=["wis"], primary_any=False, skill_count=2,
                   skills=["History", "Insight", "Medicine", "Persuasion", "Religion"], armor=["light", "medium", "shield"],
                   weapons=["simple"], multiclass=dict(armor=["light", "medium", "shield"], weapons=[], skills=0, tools=""),
                   caster="full", ability="wis", page=36,
                   cantrips=seq("3 3 3 4 4 4 4 4 4 5 5 5 5 5 5 5 5 5 5 5"),
                   prepared=seq("4 5 6 7 9 10 11 12 14 15 16 16 17 17 18 18 19 20 21 22"),
                   resources=dict(channel_divinity=per_level("2:2-5,3:6-17,4:18-20"))),
    "Druid": dict(hit_die=8, saves=["int", "wis"], primary=["wis"], primary_any=False, skill_count=2,
                  skills=["Animal Handling", "Arcana", "Insight", "Medicine", "Nature", "Perception", "Religion", "Survival"],
                  armor=["light", "shield"], weapons=["simple"],
                  multiclass=dict(armor=["light", "shield"], weapons=[], skills=0, tools=""),
                  caster="full", ability="wis", page=41,
                  cantrips=seq("2 2 2 3 3 3 3 3 3 4 4 4 4 4 4 4 4 4 4 4"),
                  prepared=seq("4 5 6 7 9 10 11 12 14 15 16 16 17 17 18 18 19 20 21 22"),
                  resources=dict(wild_shape=per_level("2:2-5,3:6-16,4:17-20"))),
    "Fighter": dict(hit_die=10, saves=["str", "con"], primary=["str", "dex"], primary_any=True, skill_count=2,
                    skills=["Acrobatics", "Animal Handling", "Athletics", "History", "Insight", "Intimidation",
                            "Persuasion", "Perception", "Survival"],
                    armor=["light", "medium", "heavy", "shield"], weapons=["simple", "martial"],
                    multiclass=dict(armor=["light", "medium", "shield"], weapons=["martial"], skills=0, tools=""),
                    caster="none", ability=None, page=47,
                    resources=dict(second_wind=per_level("2:1-3,3:4-9,4:10-20"),
                                   weapon_mastery=per_level("3:1-3,4:4-9,5:10-15,6:16-20"),
                                   action_surge=per_level("1:2-16,2:17-20"), indomitable=per_level("1:9-12,2:13-16,3:17-20"),
                                   attacks=per_level("1:1-4,2:5-10,3:11-19,4:20"))),
    "Monk": dict(hit_die=8, saves=["str", "dex"], primary=["dex", "wis"], primary_any=False, skill_count=2,
                 skills=["Acrobatics", "Athletics", "History", "Insight", "Religion", "Stealth"], armor=[],
                 weapons=["simple", "martial light"], multiclass=dict(armor=[], weapons=[], skills=0, tools=""),
                 caster="none", ability=None, page=49,
                 resources=dict(martial_arts_die=per_level("6:1-4,8:5-10,10:11-16,12:17-20"),
                                focus=[0] + list(range(2, 21)),
                                unarmored_movement=per_level("0:1,10:2-5,15:6-9,20:10-13,25:14-17,30:18-20"),
                                attacks=per_level("1:1-4,2:5-20"))),
    "Paladin": dict(hit_die=10, saves=["wis", "cha"], primary=["str", "cha"], primary_any=False, skill_count=2,
                    skills=["Athletics", "Insight", "Intimidation", "Medicine", "Persuasion", "Religion"],
                    armor=["light", "medium", "heavy", "shield"], weapons=["simple", "martial"],
                    multiclass=dict(armor=["light", "medium", "shield"], weapons=["martial"], skills=0, tools=""),
                    caster="half", ability="cha", page=53,
                    cantrips=[0] * 20, prepared=seq("2 3 4 5 6 6 7 7 9 9 10 10 11 11 12 12 14 14 15 15"),
                    resources=dict(channel_divinity=per_level("2:3-10,3:11-20"), lay_on_hands=[5 * n for n in range(1, 21)],
                                   attacks=per_level("1:1-4,2:5-20"))),
    "Ranger": dict(hit_die=10, saves=["str", "dex"], primary=["dex", "wis"], primary_any=False, skill_count=3,
                   skills=["Animal Handling", "Athletics", "Insight", "Investigation", "Nature", "Perception", "Stealth",
                           "Survival"],
                   armor=["light", "medium", "shield"], weapons=["simple", "martial"],
                   multiclass=dict(armor=["light", "medium", "shield"], weapons=["martial"], skills=1, tools=""),
                   caster="half", ability="wis", page=57,
                   cantrips=[0] * 20, prepared=seq("2 3 4 5 6 6 7 7 9 9 10 10 11 11 12 12 14 14 15 15"),
                   resources=dict(favored_enemy=per_level("2:1-4,3:5-8,4:9-12,5:13-16,6:17-20"),
                                  attacks=per_level("1:1-4,2:5-20"))),
    "Rogue": dict(hit_die=8, saves=["dex", "int"], primary=["dex"], primary_any=False, skill_count=4,
                  skills=["Acrobatics", "Athletics", "Deception", "Insight", "Intimidation", "Investigation", "Perception",
                          "Persuasion", "Sleight of Hand", "Stealth"],
                  armor=["light"], weapons=["simple", "martial finesse-or-light"],
                  multiclass=dict(armor=["light"], weapons=[], skills=1, tools="Thieves' Tools"),
                  caster="none", ability=None, page=62,
                  resources=dict(sneak_attack=[(n + 1) // 2 for n in range(1, 21)])),
    "Sorcerer": dict(hit_die=6, saves=["con", "cha"], primary=["cha"], primary_any=False, skill_count=2,
                     skills=["Arcana", "Deception", "Insight", "Intimidation", "Persuasion", "Religion"], armor=[],
                     weapons=["simple"], multiclass=dict(armor=[], weapons=[], skills=0, tools=""),
                     caster="full", ability="cha", page=64,
                     cantrips=seq("4 4 4 5 5 5 5 5 5 6 6 6 6 6 6 6 6 6 6 6"),
                     prepared=seq("2 4 6 7 9 10 11 12 14 15 16 16 17 17 18 18 19 20 21 22"),
                     resources=dict(sorcery_points=[0] + list(range(2, 21)))),
    "Warlock": dict(hit_die=8, saves=["wis", "cha"], primary=["cha"], primary_any=False, skill_count=2,
                    skills=["Arcana", "Deception", "History", "Intimidation", "Investigation", "Nature", "Religion"],
                    armor=["light"], weapons=["simple"], multiclass=dict(armor=["light"], weapons=[], skills=0, tools=""),
                    caster="pact", ability="cha", page=70,
                    cantrips=seq("2 2 2 3 3 3 3 3 3 4 4 4 4 4 4 4 4 4 4 4"),
                    prepared=seq("2 3 4 5 6 7 8 9 10 10 11 11 12 12 13 13 14 14 15 15"),
                    resources=dict(invocations=seq("1 3 3 3 5 5 6 6 7 7 7 8 8 8 9 9 9 10 10 10"),
                                   pact_slots=per_level("1:1,2:2-10,3:11-16,4:17-20"),
                                   pact_level=per_level("1:1-2,2:3-4,3:5-6,4:7-8,5:9-20"))),
    "Wizard": dict(hit_die=6, saves=["int", "wis"], primary=["int"], primary_any=False, skill_count=2,
                   skills=["Arcana", "History", "Insight", "Investigation", "Medicine", "Nature", "Religion"], armor=[],
                   weapons=["simple"], multiclass=dict(armor=[], weapons=[], skills=0, tools=""),
                   caster="full", ability="int", page=77,
                   cantrips=seq("3 3 3 4 4 4 4 4 4 5 5 5 5 5 5 5 5 5 5 5"),
                   prepared=seq("4 5 6 7 9 10 11 12 14 15 16 16 17 18 19 21 22 23 24 25")),
}
ASI = {c: [4, 8, 12, 16] for c in CLASSES}
ASI["Fighter"] = [4, 6, 8, 12, 14, 16]
ASI["Rogue"] = [4, 8, 10, 12, 16]

# Multiclass Spellcaster table (SRD 5.2.1 p. 25): spell slots per spell level for caster levels 1-20
MULTICLASS_SLOTS = [seq(r) for r in (
    "2", "3", "4 2", "4 3", "4 3 2", "4 3 3", "4 3 3 1", "4 3 3 2", "4 3 3 3 1", "4 3 3 3 2", "4 3 3 3 2 1", "4 3 3 3 2 1",
    "4 3 3 3 2 1 1", "4 3 3 3 2 1 1", "4 3 3 3 2 1 1 1", "4 3 3 3 2 1 1 1", "4 3 3 3 2 1 1 1 1", "4 3 3 3 3 1 1 1 1",
    "4 3 3 3 3 2 1 1 1", "4 3 3 3 3 2 2 1 1")]

SPECIES = {
    "Dragonborn": dict(speed=30, sizes=["Medium"], page=84, traits=["Draconic Ancestry", "Breath Weapon", "Damage Resistance",
                                                                    "Darkvision", "Draconic Flight"], darkvision=60,
                       lineages={"Black": "acid", "Blue": "lightning", "Brass": "fire", "Bronze": "lightning",
                                 "Copper": "acid", "Gold": "fire", "Green": "poison", "Red": "fire", "Silver": "cold",
                                 "White": "cold"}),
    "Dwarf": dict(speed=30, sizes=["Medium"], page=84, traits=["Darkvision", "Dwarven Resilience", "Dwarven Toughness",
                                                               "Stonecunning"], darkvision=120, resist="poison"),
    "Elf": dict(speed=30, sizes=["Medium"], page=84, traits=["Darkvision", "Elven Lineage", "Fey Ancestry", "Keen Senses",
                                                             "Trance"], darkvision=60,
                lineages={"Drow": "Dancing Lights", "High Elf": "Prestidigitation", "Wood Elf": "Druidcraft"}),
    "Gnome": dict(speed=30, sizes=["Small"], page=85, traits=["Darkvision", "Gnomish Cunning", "Gnomish Lineage"],
                  darkvision=60, lineages={"Forest Gnome": "Minor Illusion", "Rock Gnome": "Mending, Prestidigitation"}),
    "Goliath": dict(speed=35, sizes=["Medium"], page=85, traits=["Giant Ancestry", "Large Form", "Powerful Build"],
                    lineages={"Cloud": "Cloud's Jaunt", "Fire": "Fire's Burn", "Frost": "Frost's Chill",
                              "Hill": "Hill's Tumble", "Stone": "Stone's Endurance", "Storm": "Storm's Thunder"}),
    "Halfling": dict(speed=30, sizes=["Small"], page=86, traits=["Brave", "Halfling Nimbleness", "Luck", "Naturally Stealthy"]),
    "Human": dict(speed=30, sizes=["Small", "Medium"], page=86, traits=["Resourceful", "Skillful", "Versatile"]),
    "Orc": dict(speed=30, sizes=["Medium"], page=86, traits=["Adrenaline Rush", "Darkvision", "Relentless Endurance"],
                darkvision=120),
    "Tiefling": dict(speed=30, sizes=["Small", "Medium"], page=86, traits=["Darkvision", "Fiendish Legacy",
                                                                           "Otherworldly Presence"], darkvision=60,
                     lineages={"Abyssal": "Poison Spray", "Chthonic": "Chill Touch", "Infernal": "Fire Bolt"}),
}
BACKGROUNDS = {
    "Acolyte": dict(abilities=["int", "wis", "cha"], skills=["Insight", "Religion"], feat="Magic Initiate (Cleric)",
                    tool="Calligrapher's Supplies"),
    "Criminal": dict(abilities=["dex", "con", "int"], skills=["Sleight of Hand", "Stealth"], feat="Alert",
                     tool="Thieves' Tools"),
    "Sage": dict(abilities=["con", "int", "wis"], skills=["Arcana", "History"], feat="Magic Initiate (Wizard)",
                 tool="Calligrapher's Supplies"),
    "Soldier": dict(abilities=["str", "dex", "con"], skills=["Athletics", "Intimidation"], feat="Savage Attacker",
                    tool="Gaming Set"),
}
# Warlock "Eldritch Invocation Options" and Sorcerer "Metamagic Options" (SRD 5.2.1 pp. 66, 72): name -> Warlock level,
# what it needs first, repeatable
INVOCATIONS = {
    "Agonizing Blast": (2, "damage cantrip", True), "Armor of Shadows": (1, None, False), "Ascendant Step": (5, None, False),
    "Devil's Sight": (2, None, False), "Devouring Blade": (12, "Thirsting Blade", False), "Eldritch Mind": (1, None, False),
    "Eldritch Smite": (5, "Pact of the Blade", False), "Eldritch Spear": (2, "damage cantrip", True),
    "Fiendish Vigor": (2, None, False), "Gaze of Two Minds": (5, None, False), "Gift of the Depths": (5, None, False),
    "Gift of the Protectors": (9, "Pact of the Tome", False), "Investment of the Chain Master": (5, "Pact of the Chain", False),
    "Lessons of the First Ones": (2, None, True), "Lifedrinker": (9, "Pact of the Blade", False),
    "Mask of Many Faces": (2, None, False), "Master of Myriad Forms": (5, None, False), "Misty Visions": (2, None, False),
    "One with Shadows": (5, None, False), "Otherworldly Leap": (2, None, False), "Pact of the Blade": (1, None, False),
    "Pact of the Chain": (1, None, False), "Pact of the Tome": (1, None, False),
    "Repelling Blast": (2, "attack cantrip", True), "Thirsting Blade": (5, "Pact of the Blade", False),
    "Visions of Distant Realms": (9, None, False), "Whispers of the Grave": (7, None, False), "Witch Sight": (15, None, False),
}
METAMAGIC = ["Careful Spell", "Distant Spell", "Empowered Spell", "Extended Spell", "Heightened Spell", "Quickened Spell",
             "Seeking Spell", "Subtle Spell", "Transmuted Spell", "Twinned Spell"]
FEATS = {
    "Alert": dict(category="origin"), "Magic Initiate": dict(category="origin", repeatable=True),
    "Savage Attacker": dict(category="origin"), "Skilled": dict(category="origin", repeatable=True),
    "Ability Score Improvement": dict(category="general", level=4, repeatable=True),
    "Grappler": dict(category="general", level=4, needs="str or dex 13"),
    "Archery": dict(category="fighting style"), "Defense": dict(category="fighting style"),
    "Great Weapon Fighting": dict(category="fighting style"), "Two-Weapon Fighting": dict(category="fighting style"),
    "Boon of Combat Prowess": dict(category="epic boon", level=19),
    "Boon of Dimensional Travel": dict(category="epic boon", level=19), "Boon of Fate": dict(category="epic boon", level=19),
    "Boon of Irresistible Offense": dict(category="epic boon", level=19),
    "Boon of Spell Recall": dict(category="epic boon", level=19, needs="spellcasting"),
    "Boon of the Night Spirit": dict(category="epic boon", level=19), "Boon of Truesight": dict(category="epic boon", level=19),
}


def weapon(name, cat, kind, dice, dtype, props, mastery, cost):
    w = dict(name=name, category=cat, kind=kind, dice=dice, type=dtype, mastery=mastery, cost=cost)
    for p in props.split(", ") if props else []:
        m = re.match(r"(Thrown|Ammunition) \((\d+)/(\d+)\)", p)
        if m:
            w[m.group(1).lower()] = [int(m.group(2)), int(m.group(3))]
        elif p.startswith("Versatile"):
            w["versatile"] = p.split()[1]
        else:
            w[p.lower().replace("-", "_").replace(" ", "_")] = True
    return w


W = [  # SRD 5.2.1 Weapons table
    ("Club", "simple", "melee", "1d4", "bludgeoning", "Light", "Slow", 0.1),
    ("Dagger", "simple", "melee", "1d4", "piercing", "Finesse, Light, Thrown (20/60)", "Nick", 2),
    ("Greatclub", "simple", "melee", "1d8", "bludgeoning", "Two-Handed", "Push", 0.2),
    ("Handaxe", "simple", "melee", "1d6", "slashing", "Light, Thrown (20/60)", "Vex", 5),
    ("Javelin", "simple", "melee", "1d6", "piercing", "Thrown (30/120)", "Slow", 0.5),
    ("Light Hammer", "simple", "melee", "1d4", "bludgeoning", "Light, Thrown (20/60)", "Nick", 2),
    ("Mace", "simple", "melee", "1d6", "bludgeoning", "", "Sap", 5),
    ("Quarterstaff", "simple", "melee", "1d6", "bludgeoning", "Versatile 1d8", "Topple", 0.2),
    ("Sickle", "simple", "melee", "1d4", "slashing", "Light", "Nick", 1),
    ("Spear", "simple", "melee", "1d6", "piercing", "Thrown (20/60), Versatile 1d8", "Sap", 1),
    ("Dart", "simple", "ranged", "1d4", "piercing", "Finesse, Thrown (20/60)", "Vex", 0.05),
    ("Light Crossbow", "simple", "ranged", "1d8", "piercing", "Ammunition (80/320), Loading, Two-Handed", "Slow", 25),
    ("Shortbow", "simple", "ranged", "1d6", "piercing", "Ammunition (80/320), Two-Handed", "Vex", 25),
    ("Sling", "simple", "ranged", "1d4", "bludgeoning", "Ammunition (30/120)", "Slow", 0.1),
    ("Battleaxe", "martial", "melee", "1d8", "slashing", "Versatile 1d10", "Topple", 10),
    ("Flail", "martial", "melee", "1d8", "bludgeoning", "", "Sap", 10),
    ("Glaive", "martial", "melee", "1d10", "slashing", "Heavy, Reach, Two-Handed", "Graze", 20),
    ("Greataxe", "martial", "melee", "1d12", "slashing", "Heavy, Two-Handed", "Cleave", 30),
    ("Greatsword", "martial", "melee", "2d6", "slashing", "Heavy, Two-Handed", "Graze", 50),
    ("Halberd", "martial", "melee", "1d10", "slashing", "Heavy, Reach, Two-Handed", "Cleave", 20),
    ("Lance", "martial", "melee", "1d10", "piercing", "Heavy, Reach, Two-Handed", "Topple", 10),
    ("Longsword", "martial", "melee", "1d8", "slashing", "Versatile 1d10", "Sap", 15),
    ("Maul", "martial", "melee", "2d6", "bludgeoning", "Heavy, Two-Handed", "Topple", 10),
    ("Morningstar", "martial", "melee", "1d8", "piercing", "", "Sap", 15),
    ("Pike", "martial", "melee", "1d10", "piercing", "Heavy, Reach, Two-Handed", "Push", 5),
    ("Rapier", "martial", "melee", "1d8", "piercing", "Finesse", "Vex", 25),
    ("Scimitar", "martial", "melee", "1d6", "slashing", "Finesse, Light", "Nick", 25),
    ("Shortsword", "martial", "melee", "1d6", "piercing", "Finesse, Light", "Vex", 10),
    ("Trident", "martial", "melee", "1d8", "piercing", "Thrown (20/60), Versatile 1d10", "Topple", 5),
    ("Warhammer", "martial", "melee", "1d8", "bludgeoning", "Versatile 1d10", "Push", 15),
    ("War Pick", "martial", "melee", "1d8", "piercing", "Versatile 1d10", "Sap", 5),
    ("Whip", "martial", "melee", "1d4", "slashing", "Finesse, Reach", "Slow", 2),
    ("Blowgun", "martial", "ranged", "1", "piercing", "Ammunition (25/100), Loading", "Vex", 10),
    ("Hand Crossbow", "martial", "ranged", "1d6", "piercing", "Ammunition (30/120), Light, Loading", "Vex", 75),
    ("Heavy Crossbow", "martial", "ranged", "1d10", "piercing", "Ammunition (100/400), Heavy, Loading, Two-Handed", "Push", 50),
    ("Longbow", "martial", "ranged", "1d8", "piercing", "Ammunition (150/600), Heavy, Two-Handed", "Slow", 50),
    ("Musket", "martial", "ranged", "1d12", "piercing", "Ammunition (40/120), Loading, Two-Handed", "Slow", 500),
    ("Pistol", "martial", "ranged", "1d10", "piercing", "Ammunition (30/90), Loading", "Vex", 250),
]
ARMOR = [dict(name=n, ac=ac, category=cat, cost=cost, strength=st, stealth_disadvantage=sd) for n, ac, cat, cost, st, sd in [
    ("Padded Armor", 11, "light", 5, 0, True), ("Leather Armor", 11, "light", 10, 0, False),
    ("Studded Leather Armor", 12, "light", 45, 0, False), ("Hide Armor", 12, "medium", 10, 0, False),
    ("Chain Shirt", 13, "medium", 50, 0, False), ("Scale Mail", 14, "medium", 50, 0, True),
    ("Breastplate", 14, "medium", 400, 0, False), ("Half Plate Armor", 15, "medium", 750, 0, True),
    ("Ring Mail", 14, "heavy", 30, 0, True), ("Chain Mail", 16, "heavy", 75, 13, True),
    ("Splint Armor", 17, "heavy", 200, 15, True), ("Plate Armor", 18, "heavy", 1500, 15, True)]]


def spells(text):
    pat = re.compile(r"^(?:Level (\d) (%s)|(%s) Cantrip) \(([^)]+)\)$" % (SCHOOLS, SCHOOLS))
    out = []
    for pi, page in enumerate(text.split("\f")):
        lines = [l.strip() for l in page.split("\n")]
        for i, l in enumerate(lines):
            m = pat.match(l)
            if m:
                j = i - 1
                while j >= 0 and not lines[j]:
                    j -= 1
                out.append(dict(name=lines[j].replace("’", "'"), level=int(m.group(1) or 0),
                                school=m.group(2) or m.group(3), classes=[c.strip() for c in m.group(4).split(",")],
                                page=pi + 1))
    return sorted(out, key=lambda s: s["name"])


def features(text):
    """'Level N: Name' headings per class, then per '<Class> Subclass: <Name>' section, in the SRD's order."""
    order, cur, sub, out, subs = iter(CLASSES), None, None, {}, {}
    for raw in text.split("\n"):
        l = raw.strip().replace("’", "'")
        m = re.match(r"^(\w+) Subclass: (.+)$", l)
        if m and m.group(1) in CLASSES and cur:
            sub = m.group(1)
            subs[sub] = {"name": m.group(2), "features": []}
            continue
        m = re.match(r"^Level (\d+): (.+)$", l)
        if not m:
            continue
        n = int(m.group(1))
        if n == 1 and (cur is None or sub is not None):
            cur, sub = next(order), None
            out[cur] = []
        (subs[sub]["features"] if sub else out[cur]).append([n, m.group(2)])
    return out, subs


def main(argv):
    text = Path(argv[1]).read_text(encoding="utf-8")
    sp = spells(text)
    feats, subs = features(text)
    assert len(sp) == 339 and len({s["name"] for s in sp}) == 339, len(sp)
    assert set(feats) == set(CLASSES) and set(subs) == set(CLASSES)
    classes = {}
    for name in CLASSES:
        c = dict(CLASS_ROWS[name])
        if c["skills"] == "*":
            c["skills"] = SKILLS
        c["features"], c["subclass"], c["asi"] = feats[name], subs[name], ASI[name]
        classes[name] = c
    doc = {"format": "mythastria-srd-character-rules/1", "version": "SRD 5.2.1",
           "about": "SRD 5.2.1 character rules for the simulator service's character checks (sim/character_rules.py). "
                    "Built by tools/build_srd_character_rules.py from the official SRD 5.2.1 PDF; CC-BY-4.0, see "
                    "the SRD's attribution. Only SRD 5.2.1 content: anything else is the user's homebrew.",
           "url": "https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf",
           "skills": SKILL_ABILITY, "classes": classes, "multiclass_slots": MULTICLASS_SLOTS, "species": SPECIES,
           "backgrounds": BACKGROUNDS, "feats": FEATS, "weapons": [weapon(*w) for w in W], "armor": ARMOR,
           "shield": {"name": "Shield", "ac": 2, "cost": 10}, "spells": sp,
           "invocations": {k: {"level": v[0], "needs": v[1], "repeatable": v[2]} for k, v in INVOCATIONS.items()},
           "metamagic": METAMAGIC,
           "languages": ["Common", "Common Sign Language", "Draconic", "Dwarvish", "Elvish", "Giant", "Gnomish", "Goblin",
                         "Halfling", "Orc", "Abyssal", "Celestial", "Deep Speech", "Druidic", "Infernal", "Primordial",
                         "Sylvan", "Thieves' Cant", "Undercommon"]}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("%s: %d classes, %d spells, %d weapons" % (OUT, len(classes), len(sp), len(W)))


if __name__ == "__main__":
    main(sys.argv)
