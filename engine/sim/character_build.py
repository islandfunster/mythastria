"""CHARACTERS-01 phase 3 (GM 2026-10-21: "a first rate character builder that can quickly be tested in live"): the SRD 5.2.1
character builder of the simulator service, the rules authority. The Characters page only collects choices; everything
that matters in a fight is worked out and checked here.

  build(choices)   a "mythastria-build/1" set of choices -> the sheet (isles-character/1 with `derived`), the problems
                   (each one names its level and step), what is left to choose, and the options for the next choices.
                   Levels 1-20, multiclassing (prerequisites, the proficiencies a new class gives, the Multiclass
                   Spellcaster table, Pact Magic apart), the SRD subclass of each class, Ability Score Improvements and
                   feats, Fighting Styles, Expertise, invocations, Metamagic, cantrips and prepared spells (and a Wizard's
                   spellbook), equipment and Armor Class, hit points by the average or rolled dice.
  member(sheet)    any saved sheet (built or imported) -> the simulator party member (the flat build sim/run_sim.py
                   apply_party uses for the pregens) and the list of what the simulator can't play ("GM rules this").

SRD 5.2.1 only (sim/srd_character_rules.json). Plain JSON in and out.
"""
import math, re
import character_rules as cr
import epic_boons

ABILITIES = ("str", "dex", "con", "int", "wis", "cha")
ARRAY = [8, 10, 12, 13, 14, 15]
POINT_COST = {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9}
FIGHTING_STYLES = ["Archery", "Defense", "Great Weapon Fighting", "Two-Weapon Fighting"]
STYLE_LEVEL = {"Fighter": 1, "Paladin": 2, "Ranger": 2}
STYLE_OPTION = {"Paladin": ("Blessed Warrior", "Cleric"), "Ranger": ("Druidic Warrior", "Druid")}
EXPERTISE = {"Rogue": {1: 2, 6: 2}, "Bard": {2: 2, 9: 2}, "Ranger": {2: 1, 9: 2}, "Wizard": {2: 1}}
SCHOLAR = ("Arcana", "History", "Investigation", "Medicine", "Nature", "Religion")   # the Wizard's Expertise (level 2)
METAMAGIC_AT = {2: 2, 10: 2, 17: 2}
METAMAGIC = cr.rules()["metamagic"]
INVOCATIONS = {k: (v["level"], v["needs"], v["repeatable"]) for k, v in cr.rules()["invocations"].items()}   # name: (level, needs, repeatable)
# GM 2026-11-01 ("Change sorcerous burst back to elemental damages"): the SRD 5.2.1 types, chosen at each cast; the first is the default
CANTRIP_CHOICES = {"Sorcerous Burst": ["acid", "cold", "fire", "lightning", "poison", "psychic", "thunder"]}
DAMAGE_CANTRIPS = {  # SRD 5.2.1 cantrips that deal damage: (die, attack roll?, damage type)
    "Acid Splash": (6, False, "acid"), "Chill Touch": (10, True, "necrotic"), "Eldritch Blast": (10, True, "force"),
    "Fire Bolt": (10, True, "fire"), "Poison Spray": (12, True, "poison"), "Produce Flame": (8, True, "fire"),
    "Ray of Frost": (8, True, "cold"), "Sacred Flame": (8, False, "radiant"), "Shocking Grasp": (8, True, "lightning"),
    "Starry Wisp": (8, True, "radiant"), "Vicious Mockery": (6, False, "psychic"), "Sorcerous Burst": (8, True, "acid"),
}
CANTRIP_RANGE = {"Eldritch Blast": 120, "Fire Bolt": 120, "Chill Touch": 5, "Shocking Grasp": 5, "Produce Flame": 60,
                 "Ray of Frost": 60, "Poison Spray": 30, "Starry Wisp": 60, "Sorcerous Burst": 120}
# SPELLS-4-9 (SRD 5.2.1 Warlock): Mystic Arcanum, one Warlock spell of each level (6-9) from these Warlock levels
ARCANUM = ((6, 11), (7, 13), (8, 15), (9, 17))
ALWAYS = {  # spells a class or subclass always has prepared: class -> [(class level, [spells])]
    "Cleric": [(3, ["Aid", "Bless", "Cure Wounds", "Lesser Restoration"]), (5, ["Mass Healing Word", "Revivify"]),
               (7, ["Aura of Life", "Death Ward"]), (9, ["Greater Restoration", "Mass Cure Wounds"])],
    "Paladin": [(2, ["Divine Smite"]), (3, ["Protection from Evil and Good", "Shield of Faith"]),
                (5, ["Aid", "Zone of Truth", "Find Steed"]),        # Find Steed: Faithful Steed (GM 2026-10-26)
                (9, ["Beacon of Hope", "Dispel Magic"]), (13, ["Freedom of Movement", "Guardian of Faith"]),
                (17, ["Commune", "Flame Strike"])],
    "Warlock": [(3, ["Burning Hands", "Command", "Scorching Ray", "Suggestion"]), (5, ["Fireball", "Stinking Cloud"]),
                (7, ["Fire Shield", "Wall of Fire"]), (9, ["Geas", "Insect Plague"])],
    "Sorcerer": [(3, ["Alter Self", "Chromatic Orb", "Command", "Dragon's Breath"]), (5, ["Fear", "Fly"]),
                 (7, ["Arcane Eye", "Charm Monster"]), (9, ["Legend Lore", "Summon Dragon"])],
    "Ranger": [(1, ["Hunter's Mark"])], "Druid": [(1, ["Speak with Animals"])],
    "Bard": [(20, ["Power Word Heal", "Power Word Kill"])],     # Words of Creation (GM 2026-10-28, "heroes 20")
}
SECRETS_LISTS = {"Bard", "Cleric", "Druid", "Wizard"}           # Magical Secrets (Bard 10): prepared from these lists
AFFINITY = ("acid", "cold", "fire", "lightning", "poison")       # Draconic Sorcery 6: Elemental Affinity's damage types
CAPSTONE_SCORES = {"Barbarian": ("str", "con"), "Monk": ("dex", "wis")}   # Primal Champion, Body and Mind (level 20)
ARCANUM_AT = {11: 6, 13: 7, 15: 8, 17: 9}                         # Warlock: Mystic Arcanum, one spell of each level
WIZARD_PICKS = {18: ("spell_mastery", "Spell Mastery", (1, 2)), 20: ("signature_spells", "Signature Spells", (3, 3))}
LAND = {"arid": [(3, ["Blur", "Burning Hands", "Fire Bolt"]), (5, ["Fireball"]), (7, ["Blight"]), (9, ["Wall of Stone"])],
        "polar": [(3, ["Fog Cloud", "Hold Person", "Ray of Frost"]), (5, ["Sleet Storm"]), (7, ["Ice Storm"]), (9, ["Cone of Cold"])],
        "temperate": [(3, ["Misty Step", "Shocking Grasp", "Sleep"]), (5, ["Lightning Bolt"]), (7, ["Freedom of Movement"]),
                      (9, ["Tree Stride"])],
        "tropical": [(3, ["Acid Splash", "Ray of Sickness", "Web"]), (5, ["Stinking Cloud"]), (7, ["Polymorph"]),
                     (9, ["Insect Plague"])]}
LINEAGE_SPELLS = {  # species lineage: [(character level, spell)]
    "Drow": [(1, "Dancing Lights"), (3, "Faerie Fire"), (5, "Darkness")],
    "High Elf": [(1, "Prestidigitation"), (3, "Detect Magic"), (5, "Misty Step")],
    "Wood Elf": [(1, "Druidcraft"), (3, "Longstrider"), (5, "Pass without Trace")],
    "Forest Gnome": [(1, "Minor Illusion"), (1, "Speak with Animals")], "Rock Gnome": [(1, "Mending"), (1, "Prestidigitation")],
    "Abyssal": [(1, "Poison Spray"), (3, "Ray of Sickness"), (5, "Hold Person")],
    "Chthonic": [(1, "Chill Touch"), (3, "False Life"), (5, "Ray of Enfeeblement")],
    "Infernal": [(1, "Fire Bolt"), (3, "Hellish Rebuke"), (5, "Darkness")],
}
TIEFLING_RESIST = {"Abyssal": "Poison", "Chthonic": "Necrotic", "Infernal": "Fire"}
STANDARD_LANGUAGES = ["Common Sign Language", "Draconic", "Dwarvish", "Elvish", "Giant", "Gnomish", "Goblin", "Halfling", "Orc"]
CLASS_GOLD = {"Barbarian": 75, "Bard": 90, "Cleric": 110, "Druid": 50, "Fighter": 155, "Monk": 50, "Paladin": 150,
              "Ranger": 150, "Rogue": 100, "Sorcerer": 50, "Warlock": 100, "Wizard": 55}


def _kit(armor=None, shield=False, weapons=(), focus=False, spellbook=False, items=(), gp=0):
    return {"armor": armor, "shield": shield, "weapons": [list(w) if isinstance(w, tuple) else [w, 1] for w in weapons],
            "focus": focus, "spellbook": spellbook, "items": list(items), "gp": gp}


# KITS-01 (GM 2026-10-26: "Does the class offer the choice of standard adventure kit or gold? Does the background
# offer that equipment pack or gold?" then "yes"): each class's and background's Starting Equipment, SRD 5.2.1 word
# for word. A level 1 character takes one kit (A, B ...) or the gold (the last choice); the background likewise.
# `focus` is the kit's Holy Symbol, Druidic or Arcane Focus; a staff focus is also the Quarterstaff weapon.
CLASS_KITS = {
    "Barbarian": {"A": _kit(weapons=["Greataxe", ("Handaxe", 4)], items=["Explorer's Pack"], gp=15)},
    "Bard": {"A": _kit("Leather Armor", weapons=[("Dagger", 2)], items=["Musical Instrument (your choice)", "Entertainer's Pack"], gp=19)},
    "Cleric": {"A": _kit("Chain Shirt", True, ["Mace"], True, items=["Holy Symbol", "Priest's Pack"], gp=7)},
    "Druid": {"A": _kit("Leather Armor", True, ["Sickle", "Quarterstaff"], True,
                        items=["Druidic Focus (Quarterstaff)", "Explorer's Pack", "Herbalism Kit"], gp=9)},
    "Fighter": {"A": _kit("Chain Mail", weapons=["Greatsword", "Flail", ("Javelin", 8)], items=["Dungeoneer's Pack"], gp=4),
                "B": _kit("Studded Leather Armor", weapons=["Scimitar", "Shortsword", "Longbow"],
                          items=["Arrows ×20", "Quiver", "Dungeoneer's Pack"], gp=11)},
    "Monk": {"A": _kit(weapons=["Spear", ("Dagger", 5)], items=["Artisan's Tools or Musical Instrument (your tool proficiency)",
                                                                "Explorer's Pack"], gp=11)},
    "Paladin": {"A": _kit("Chain Mail", True, ["Longsword", ("Javelin", 6)], True, items=["Holy Symbol", "Priest's Pack"], gp=9)},
    "Ranger": {"A": _kit("Studded Leather Armor", False, ["Scimitar", "Shortsword", "Longbow"], True,
                         items=["Arrows ×20", "Quiver", "Druidic Focus (sprig of mistletoe)", "Explorer's Pack"], gp=7)},
    "Rogue": {"A": _kit("Leather Armor", weapons=[("Dagger", 2), "Shortsword", "Shortbow"],
                        items=["Arrows ×20", "Quiver", "Thieves' Tools", "Burglar's Pack"], gp=8)},
    "Sorcerer": {"A": _kit(weapons=["Spear", ("Dagger", 2)], focus=True, items=["Arcane Focus (crystal)", "Dungeoneer's Pack"], gp=28)},
    "Warlock": {"A": _kit("Leather Armor", weapons=["Sickle", ("Dagger", 2)], focus=True,
                          items=["Arcane Focus (orb)", "Book (occult lore)", "Scholar's Pack"], gp=15)},
    "Wizard": {"A": _kit(weapons=[("Dagger", 2), "Quarterstaff"], focus=True, spellbook=True,
                         items=["Arcane Focus (Quarterstaff)", "Robe", "Scholar's Pack"], gp=5)},
}
BACKGROUND_GOLD = 50
BACKGROUND_KITS = {
    "Acolyte": _kit(items=["Calligrapher's Supplies", "Book (prayers)", "Holy Symbol", "Parchment (10 sheets)", "Robe"], gp=8),
    "Criminal": _kit(weapons=[("Dagger", 2)], items=["Thieves' Tools", "Crowbar", "Pouch ×2", "Traveler's Clothes"], gp=16),
    "Sage": _kit(weapons=["Quarterstaff"], items=["Calligrapher's Supplies", "Book (history)", "Parchment (8 sheets)", "Robe"], gp=8),
    "Soldier": _kit(weapons=["Spear", "Shortbow"], items=["Arrows ×20", "Gaming Set (your tool proficiency)", "Healer's Kit",
                                                         "Quiver", "Traveler's Clothes"], gp=14),
}


def kits():
    """The kits for the builder page (character_srd)."""
    return {"classes": CLASS_KITS, "class_gold": CLASS_GOLD, "backgrounds": BACKGROUND_KITS, "background_gold": BACKGROUND_GOLD}


def mod(score):
    return (int(score) - 10) // 2


def prof_bonus(level):
    return 2 + (max(1, level) - 1) // 4


def signed(n):
    return "%+d" % n


class Problems:
    def __init__(self):
        self.errors, self.todo, self.warnings = [], [], []

    def need(self, where, text):
        """Something still to choose: listed, and the sheet is not finished until it is chosen."""
        self.todo.append({"where": where, "text": text})

    def bad(self, where, text):
        """A choice the SRD does not allow."""
        self.errors.append({"where": where, "text": text})

    def warn(self, where, text):
        self.warnings.append({"where": where, "text": text})


def _list(v):
    return [x for x in (v if isinstance(v, list) else []) if isinstance(x, str) and x.strip()]


def _spell(name):
    n = cr.norm(name)
    return next((s for s in cr.rules()["spells"] if cr.norm(s["name"]) == n), None)


def _casting_time(name):
    """CASTER-HIGH: a spell's casting time from its SRD 5.2.1 text ("action", "bonus_action", "reaction"), or None."""
    try:
        import spell_rules
        return (spell_rules.spell(name) or {}).get("casting_time")
    except Exception:
        return None


def _weapon(name):
    n = cr.norm(name)
    return next((w for w in cr.rules()["weapons"] if cr.norm(w["name"]) == n), None)


def _armor(name):
    n = cr.norm(name)
    return next((a for a in cr.rules()["armor"] if cr.norm(a["name"]) == n), None)


def imported_weapon(text):
    """GM 2026-10-28 ("also no weapons"): an imported sheet's equipment line -> (the SRD weapon, its +N), or (None, 0).
    D&D Beyond and other tools name magic and special weapons "Scimitar, +1", "+2 Longsword", "Adamantine War Pick" or
    "Longsword (Silvered)": the longest SRD weapon name among the words, and a +1 to +3 anywhere in the line."""
    t = cr.norm(text)
    plus = re.search(r"\+\s*([1-3])\b", t)
    words = re.findall(r"[a-z']+", re.sub(r"\+\s*[1-3]\b", " ", t))
    best = None
    for w in cr.rules()["weapons"]:
        wn = re.findall(r"[a-z']+", cr.norm(w["name"]))
        if any(words[i:i + len(wn)] == wn for i in range(len(words) - len(wn) + 1)) and (
                best is None or len(wn) > len(re.findall(r"[a-z']+", cr.norm(best["name"])))):
            best = w
    return best, (int(plus.group(1)) if plus and best else 0)


def imported_attacks(s, mods, pb, level):
    """The attacks of an imported sheet in a built sheet's shape: one per SRD weapon in its equipment (proficiency from its
    proficiencies: Simple Weapons, Martial Weapons or the weapon's own name; none listed: proficient) and its damaging
    cantrips (the spellcasting ability of the class that gives them)."""
    profs = [cr.norm(p) for p in (s.get("proficiencies") or []) if isinstance(p, str)]
    listed = [p for p in profs if p.endswith("(weapons)")]
    out, seen = [], set()
    for line in s.get("equipment") or []:
        w, plus = imported_weapon(line) if isinstance(line, str) else (None, 0)
        if not w:
            continue
        name = w["name"] + (" +%d" % plus if plus else "")
        if name in seen:
            continue
        seen.add(name)
        ranged = w["kind"] == "ranged"
        ab = "dex" if ranged else ("dex" if mods["dex"] > mods["str"] else "str") if w.get("finesse") else "str"
        prof = not listed or any(p.startswith(w["category"] + " weapons") or p.startswith(cr.norm(w["name"])) for p in listed)
        dice = re.match(r"(\d+)d(\d+)", w["dice"])
        count, die = (int(dice.group(1)), int(dice.group(2))) if dice else (1, 1)
        out.append({"name": name, "atk": (pb if prof else 0) + mods[ab] + plus, "count": count, "die": die,
                    "bonus": mods[ab] + plus, "type": w["type"], "melee": not ranged, "ability": ab, "proficient": prof,
                    "reach": (w.get("ammunition") or [80])[0] if ranged else (10 if w.get("reach") else 5),
                    "mastery": None, "light": bool(w.get("light")), "finesse": bool(w.get("finesse")),
                    "magic": plus})
    R = cr.rules()["classes"]
    casters = [c for c in s.get("classes") or [] if isinstance(c, dict) and R.get(str(c.get("name")).title(), {}).get("caster", "none") != "none"]
    for sp in s.get("spells") or []:
        nm = sp if isinstance(sp, str) else (sp or {}).get("name", "")
        if nm not in DAMAGE_CANTRIPS or nm in seen:
            continue
        src = (sp.get("source") if isinstance(sp, dict) else "") or ""
        cls = next((c for c in casters if cr.norm(c["name"]) in cr.norm(src)), casters[0] if casters else None)
        ab = R[cls["name"].title()]["ability"] if cls else "cha"
        die, roll, dtype = DAMAGE_CANTRIPS[nm]
        seen.add(nm)
        out.append({"name": nm, "atk": pb + mods[ab] if roll else None, "save_dc": None if roll else 8 + pb + mods[ab],
                    "count": 1 + (level >= 5) + (level >= 11) + (level >= 17), "die": die, "bonus": 0, "type": dtype,
                    "reach": CANTRIP_RANGE.get(nm, 60), "melee": CANTRIP_RANGE.get(nm) == 5, "ability": ab, "cantrip": True,
                    "proficient": True})
    return out


def class_levels(levels):
    out = {}
    for e in levels:
        out[e["class"]] = out.get(e["class"], 0) + 1
    return out


def max_spell_level(cls, level):
    """The highest spell level a class's own Spellcasting lets it prepare at a class level."""
    kind = cr.rules()["classes"][cls]["caster"]
    if kind == "full":
        return min(9, (level + 1) // 2)
    if kind == "half":
        return min(5, (level + 3) // 4)
    if kind == "pact":
        return cr.rules()["classes"]["Warlock"]["resources"]["pact_level"][level - 1]
    return 0


def spell_slots(counts):
    """Spell slots per spell level from the Spellcasting classes (Multiclass Spellcaster table), and Pact Magic apart."""
    R = cr.rules()["classes"]
    full = sum(n for c, n in counts.items() if R[c]["caster"] == "full")
    half = sum(n for c, n in counts.items() if R[c]["caster"] == "half")
    caster_level = full + (half + 1) // 2 if half else full
    slots = list(cr.rules()["multiclass_slots"][caster_level - 1]) if caster_level else []
    pact = None
    if counts.get("Warlock"):
        w = R["Warlock"]["resources"]
        pact = {"slots": w["pact_slots"][counts["Warlock"] - 1], "level": w["pact_level"][counts["Warlock"] - 1]}
    return slots, pact, caster_level


# ------------------------------------------------------------------ the build
def build(ch):
    """The choices -> {ok, done, sheet, errors, todo, warnings, options}. `done` is True when nothing is left to choose and
    nothing is wrong; the sheet is returned either way, so the page shows the numbers as they stand."""
    R = cr.rules()
    P = Problems()
    ch = ch if isinstance(ch, dict) else {}
    levels = [e for e in (ch.get("levels") if isinstance(ch.get("levels"), list) else []) if isinstance(e, dict)]
    if not levels:
        P.need("Level 1", "Choose a class.")
        levels = []
    if len(levels) > 20:
        P.bad("Levels", "A character has at most 20 levels.")
        levels = levels[:20]
    for i, e in enumerate(levels):
        if e.get("class") not in R["classes"]:
            P.bad("Level %d" % (i + 1), "Choose an SRD 5.2.1 class.")
    levels = [e for e in levels if e.get("class") in R["classes"]]
    total = len(levels)
    pb = prof_bonus(total)
    first = levels[0]["class"] if levels else None
    counts = class_levels(levels)

    # ---- species, background, scores
    species, sp = ch.get("species"), R["species"].get(ch.get("species"))
    if not sp:
        P.need("Species", "Choose a species.")
    lineage = ch.get("lineage") or ""
    if sp and sp.get("lineages") and lineage not in sp["lineages"]:
        P.need("Species", "Choose the %s %s." % (species, "ancestry" if species in ("Dragonborn", "Goliath") else "lineage"))
    size = ch.get("size") or (sp["sizes"][-1] if sp else "Medium")
    if sp and size not in sp["sizes"]:
        P.bad("Species", "%s can be %s." % (species, " or ".join(sp["sizes"])))
    bgname, bg = ch.get("background"), R["backgrounds"].get(ch.get("background"))
    if not bg:
        P.need("Background", "Choose a background.")

    base = {a: ch.get("base", {}).get(a) for a in ABILITIES}
    method = ch.get("method") or "array"
    if any(not isinstance(base[a], int) or not 3 <= base[a] <= 18 for a in ABILITIES):
        P.bad("Ability scores", "Each score is a whole number from 3 to 18 before increases.")
        base = {a: base[a] if isinstance(base[a], int) and 3 <= base[a] <= 18 else 10 for a in ABILITIES}
    if method == "array" and sorted(base.values()) != ARRAY:
        P.bad("Ability scores", "Use each Standard Array score once: 15, 14, 13, 12, 10, 8.")
    elif method == "point":
        # GM 2026-10-21: "for point buy make options with 27 as shaded as default but +- options are available for survival
        # or heroic modes": 27 is SRD 5.2.1; another budget is a table option (house rule), said on the sheet
        budget = ch.get("point_budget", 27)
        if not isinstance(budget, int) or isinstance(budget, bool) or not 10 <= budget <= 45:
            P.bad("Ability scores", "A point buy budget is 10 to 45 points (27 is the SRD's).")
            budget = 27
        elif budget != 27:
            P.warn("Ability scores", "Point buy with %d points: a %s table option (house rule); the SRD's is 27." % (
                budget, "survival" if budget < 27 else "heroic"))
        if any(v not in POINT_COST for v in base.values()):
            P.bad("Ability scores", "Point buy scores are 8 to 15.")
        elif sum(POINT_COST[v] for v in base.values()) > budget:
            P.bad("Ability scores", "Point buy spends at most %d points (%d now)." % (budget, sum(POINT_COST[v] for v in base.values())))
    elif method == "rolled":
        P.warn("Ability scores", "Rolled scores: the GM approves the rolls.")
    elif method not in ("array", "point"):
        P.bad("Ability scores", "Choose how the scores were made.")
    boosts = {a: int(ch.get("boosts", {}).get(a) or 0) for a in ABILITIES}
    nonzero = sorted(v for v in boosts.values() if v)
    if bg and (nonzero not in ([1, 2], [1, 1, 1]) or any(boosts[a] and a not in bg["abilities"] for a in ABILITIES)):
        P.need("Background", "Raise %s: +2 to one and +1 to another, or +1 to all three." %
               ", ".join(a.upper() for a in bg["abilities"]))
    scores = {a: base[a] + boosts[a] for a in ABILITIES}
    if any(v > 20 for v in scores.values()):
        P.bad("Background", "No score above 20.")

    # ---- feats, skills, proficiencies gathered level by level
    feats, feat_sources = [], []
    skills, expertise, tools, langs = [], [], [], ["Common"]
    armor_train, weapon_train = set(), set()
    features = []                                                 # (character level, source, name)
    fighting_styles, invocations, metamagic = [], [], []
    style_cantrips = {}
    origin = bg["feat"] if bg else None
    if origin:
        feats.append(origin); feat_sources.append(("Background", origin))
    if species == "Human":
        hf = ch.get("human_feat")
        if hf not in ("Alert", "Magic Initiate (Cleric)", "Magic Initiate (Druid)", "Magic Initiate (Wizard)",
                      "Savage Attacker", "Skilled"):
            P.need("Species", "Choose the Human's Origin feat (Versatile).")
        else:
            if hf == origin and not (hf == "Skilled"):
                P.bad("Species", "%s can't be taken twice (Magic Initiate: a different spell list)." % hf)
            feats.append(hf); feat_sources.append(("Human", hf))

    def add_skill(where, s, allowed=None):
        if s not in R["skills"] or (allowed and s not in allowed):
            P.bad(where, "%s is not a skill you can choose here." % s)
        elif s in skills:
            P.bad(where, "Already proficient in %s: choose another skill." % s)
        else:
            skills.append(s)

    if bg:
        for s in bg["skills"]:
            skills.append(s)
        tools.append(ch.get("background_tool") or bg["tool"])
    if species == "Human":
        s = ch.get("species_skill")
        if s:
            add_skill("Species", s)
        else:
            P.need("Species", "Choose the Human's skill (Skillful).")
    if species == "Elf":
        s = ch.get("species_skill")
        if s:
            add_skill("Species", s, ["Insight", "Perception", "Survival"])
        else:
            P.need("Species", "Choose the Elf's Keen Senses skill: Insight, Perception or Survival.")

    # ability score increases and feats over the levels; abilities as they stand at each level (multiclass prerequisites)
    seen = {}
    asi_feats = []
    boon_up = {}                                                 # EPIC-BOONS-01: the score each Epic Boon raised
    for i, e in enumerate(levels):
        lv, cls = i + 1, e["class"]
        C = R["classes"][cls]
        seen[cls] = seen.get(cls, 0) + 1
        n = seen[cls]
        where = "Level %d (%s %d)" % (lv, cls, n)
        if n == 1:
            if lv == 1:
                armor_train |= set(C["armor"]); weapon_train |= set(C["weapons"])
                for s in _list(e.get("skills")):
                    add_skill(where, s, C["skills"])
                if len(_list(e.get("skills"))) != C["skill_count"]:
                    P.need(where, "Choose %d %s skills." % (C["skill_count"], cls))
            else:                                                 # multiclassing into a new class
                need = [cls] + [c for c in seen if c != cls]
                for c in need:
                    prim = R["classes"][c]["primary"]
                    ok = any(scores[a] >= 13 for a in prim) if R["classes"][c]["primary_any"] else all(scores[a] >= 13 for a in prim)
                    if not ok:
                        P.bad(where, "Multiclassing needs %s 13+ for %s." % (
                            (" or " if R["classes"][c]["primary_any"] else " and ").join(a.upper() for a in prim), c))
                mc = C["multiclass"]
                armor_train |= set(mc["armor"]); weapon_train |= set(mc["weapons"])
                if mc["skills"]:
                    picked = _list(e.get("skills"))
                    for s in picked:
                        add_skill(where, s, C["skills"])
                    if len(picked) != mc["skills"]:
                        P.need(where, "Choose %d skill from the %s list." % (mc["skills"], cls))
                if mc["tools"]:
                    tools.append(mc["tools"])
        for flv, fname in C["features"]:
            if flv == n and fname not in ("Ability Score Improvement", "Epic Boon"):
                features.append((lv, cls, C["subclass"]["name"] if fname == cls + " Subclass" else fname))
        if n >= 3:
            for flv, fname in C["subclass"]["features"]:
                if flv == n:
                    features.append((lv, C["subclass"]["name"], fname))
        if n == 3 and e.get("subclass", C["subclass"]["name"]) != C["subclass"]["name"]:
            P.bad(where, "The SRD subclass of the %s is %s." % (cls, C["subclass"]["name"]))
        # Ability Score Improvement / Epic Boon
        if n in C["asi"] or n == 19:
            a = e.get("asi") if isinstance(e.get("asi"), dict) else {}
            feat = a.get("feat")
            label = "Epic Boon" if n == 19 else "Ability Score Improvement"
            if not feat:
                P.need(where, "%s: choose %s." % (label, "an Epic Boon feat (or another feat)" if n == 19 else
                                                  "Ability Score Improvement or a feat"))
            else:
                _feat_choice(P, where, feat, a, scores, lv, cls, n, fighting_styles, feats, feat_sources, asi_feats, seen)
                if str(feat).startswith("Boon of") and isinstance(a.get("abilities"), dict) and a["abilities"]:
                    boon_up[feat] = next(iter(a["abilities"]))
        # Fighting Style
        style_at = STYLE_LEVEL.get(cls)
        if (style_at and n == style_at) or (cls == "Fighter" and n == 7):
            st = e.get("fighting_style")
            opt = STYLE_OPTION.get(cls)
            if opt and st == opt[0]:
                cans = _list(e.get("style_cantrips"))
                style_cantrips[cls] = (opt[1], cans)
                if len(cans) != 2 or any(not (_spell(x) and _spell(x)["level"] == 0 and opt[1] in _spell(x)["classes"]) for x in cans):
                    P.need(where, "%s: choose two %s cantrips." % (opt[0], opt[1]))
                features.append((lv, cls, opt[0]))
            elif st in FIGHTING_STYLES and st not in fighting_styles:
                fighting_styles.append(st); feats.append(st); feat_sources.append((where, st))
            elif st in fighting_styles:
                P.bad(where, "%s is already one of your Fighting Styles." % st)
            else:
                P.need(where, "Choose a Fighting Style%s." % (" (or %s)" % opt[0] if opt else ""))
        # Expertise
        ex_n = EXPERTISE.get(cls, {}).get(n)
        if ex_n:
            picked = _list(e.get("expertise"))
            if len(picked) != ex_n:
                P.need(where, "Expertise: choose %d of your skill proficiencies." % ex_n)
            for s in picked:
                if cls == "Wizard" and s not in SCHOLAR:
                    P.bad(where, "Scholar: choose %s." % ", ".join(SCHOLAR))
                elif s in expertise:
                    P.bad(where, "Expertise in %s already." % s)
                else:
                    expertise.append(s)
        # Divine Order / Primal Order
        if n == 1 and cls in ("Cleric", "Druid"):
            o = e.get("order")
            allowed = ["Protector", "Thaumaturge"] if cls == "Cleric" else ["Magician", "Warden"]
            if o not in allowed:
                P.need(where, "%s: choose %s." % ("Divine Order" if cls == "Cleric" else "Primal Order", " or ".join(allowed)))
            elif o in ("Protector", "Warden"):
                weapon_train.add("martial")
                armor_train.add("heavy" if o == "Protector" else "medium")
            if o:
                features.append((lv, cls, "%s: %s" % ("Divine Order" if cls == "Cleric" else "Primal Order", o)))
        # Warlock invocations
        if cls == "Warlock":
            table = C["resources"]["invocations"]
            gain = table[n - 1] - (table[n - 2] if n > 1 else 0)
            picked = _list(e.get("invocations"))
            if len(picked) != gain:
                P.need(where, "Eldritch Invocations: choose %d." % gain) if gain else P.bad(where, "No new invocation at this level.")
            for inv in picked:
                spec = INVOCATIONS.get(inv)
                if not spec:
                    P.bad(where, "%s is not an SRD 5.2.1 invocation." % inv); continue
                need_lv, needs, rep = spec
                if n < need_lv:
                    P.bad(where, "%s needs Warlock level %d." % (inv, need_lv))
                if needs and needs in INVOCATIONS and needs not in invocations:
                    P.bad(where, "%s needs %s first." % (inv, needs))
                if inv in invocations and not rep:
                    P.bad(where, "%s is already chosen." % inv)
                invocations.append(inv)
        # Metamagic
        if cls == "Sorcerer" and n in METAMAGIC_AT:
            picked = _list(e.get("metamagic"))
            if len(picked) != METAMAGIC_AT[n] or any(m not in METAMAGIC or m in metamagic for m in picked):
                P.need(where, "Metamagic: choose %d new options." % METAMAGIC_AT[n])
            metamagic += [m for m in picked if m in METAMAGIC and m not in metamagic]
        # College of Lore: three skills
        if cls == "Bard" and n == 3:
            picked = _list(e.get("skills"))
            for s in picked:
                add_skill(where, s)
            if len(picked) != 3:
                P.need(where, "Bonus Proficiencies: choose three skills.")
        # Circle of the Land
        if cls == "Druid" and n == 3 and e.get("land") not in LAND:
            P.need(where, "Circle of the Land: choose the land (arid, polar, temperate, tropical).")
        # Draconic Sorcery: Elemental Affinity (GM 2026-10-23, the Sorcerer: its damage type)
        if cls == "Sorcerer" and n == 6 and e.get("affinity") not in AFFINITY:
            P.need(where, "Elemental Affinity: choose the damage type (acid, cold, fire, lightning, poison).")
        # hit points rolled
        if lv > 1 and e.get("hp") is not None:
            die = C["hit_die"]
            if not isinstance(e["hp"], int) or not 1 <= e["hp"] <= die:
                P.bad(where, "A rolled hit die is 1 to %d." % die)

    for s in expertise:
        if s not in skills and s != "Thieves' Tools":
            P.bad("Expertise", "Expertise needs proficiency in %s first." % s)
    # GM 2026-10-26 (levels 10-20): the level 20 features that raise two scores by 4, to a maximum of 25
    champion = []
    for cls, (a, b) in CAPSTONE_SCORES.items():
        if counts.get(cls, 0) >= 20:
            for k in (a, b):
                scores[k] = max(scores[k], min(25, scores[k] + 4))
            champion += [a, b]
    if any(v > 20 and k not in champion for k, v in scores.items()) and not any(f.startswith("Boon of") for f in feats):
        P.bad("Ability scores", "No score above 20 (an Epic Boon raises one to 30).")

    # Skilled and Magic Initiate choices
    fc = ch.get("feat_choices") if isinstance(ch.get("feat_choices"), dict) else {}
    skilled_n = sum(1 for f in feats if f == "Skilled")
    if skilled_n:
        picked = _list(fc.get("Skilled"))
        for s in picked:
            if s in R["skills"]:
                add_skill("Skilled", s)
            else:
                tools.append(s)
        if len(picked) != 3 * skilled_n:
            P.need("Skilled", "Choose %d skills or tools." % (3 * skilled_n))
    spells_out = []                                               # {name, level, source, ability, always?}
    for f in [f for f in feats if f.startswith("Magic Initiate")]:
        lst = re.search(r"\((\w+)\)", f).group(1)
        m = fc.get(f) if isinstance(fc.get(f), dict) else {}
        cans, one, ab = _list(m.get("cantrips")), m.get("spell"), m.get("ability")
        if len(cans) != 2 or any(not (_spell(x) and _spell(x)["level"] == 0 and lst in _spell(x)["classes"]) for x in cans):
            P.need(f, "Choose two %s cantrips." % lst)
        if not (one and _spell(one) and _spell(one)["level"] == 1 and lst in _spell(one)["classes"]):
            P.need(f, "Choose one level 1 %s spell." % lst)
        if ab not in ("int", "wis", "cha"):
            P.need(f, "Choose its spellcasting ability (INT, WIS or CHA).")
        for x in cans:
            spells_out.append({"name": x, "level": 0, "source": f, "ability": ab or "wis"})
        if one:
            spells_out.append({"name": one, "level": 1, "source": f, "ability": ab or "wis", "always": True,
                               "note": "once a Long Rest without a slot"})

    # languages
    picked = _list(ch.get("languages"))
    if len(picked) != 2 or len(set(picked)) != 2 or any(l not in STANDARD_LANGUAGES for l in picked):
        P.need("Languages", "Choose two standard languages besides Common.")
    langs += [l for l in picked if l not in langs]
    if counts.get("Rogue"):
        langs.append("Thieves' Cant"); tools.append("Thieves' Tools")
    if counts.get("Druid"):
        langs.append("Druidic")

    mods = {a: mod(scores[a]) for a in ABILITIES}

    # ---- species spells and traits
    lineage_ability = ch.get("lineage_ability") or "int"
    if species in ("Elf", "Gnome", "Tiefling") and lineage_ability not in ("int", "wis", "cha"):
        P.need("Species", "Choose the lineage's spellcasting ability.")
    for slv, name in LINEAGE_SPELLS.get(lineage, []):
        if total >= slv:
            if lineage == "High Elf" and slv == 1 and ch.get("high_elf_cantrip"):
                hc = ch["high_elf_cantrip"]
                if not (_spell(hc) and _spell(hc)["level"] == 0 and "Wizard" in _spell(hc)["classes"]):
                    P.bad("Species", "The High Elf cantrip is a Wizard cantrip.")
                name = hc
            spells_out.append({"name": name, "level": (_spell(name) or {}).get("level", 0), "source": lineage,
                               "ability": lineage_ability, "always": True})
    if species == "Tiefling":
        spells_out.append({"name": "Thaumaturgy", "level": 0, "source": "Tiefling", "ability": lineage_ability, "always": True})

    # ---- class spells
    sp_choice = ch.get("spells") if isinstance(ch.get("spells"), dict) else {}
    casting = []
    for cls, n in counts.items():
        C = R["classes"][cls]
        if C["caster"] == "none":
            continue
        ab = C["ability"]
        top = max_spell_level(cls, n)
        mine = sp_choice.get(cls) if isinstance(sp_choice.get(cls), dict) else {}
        orders = [e.get("order") for e in levels if e["class"] == cls]
        can_n = C["cantrips"][n - 1] + (1 if cls in ("Cleric", "Druid") and orders and orders[0] in ("Thaumaturge", "Magician") else 0)
        prep_n = C["prepared"][n - 1]
        cans, prep, book = _list(mine.get("cantrips")), _list(mine.get("prepared")), _list(mine.get("book"))
        where = "%s spells" % cls
        if can_n and len(cans) != can_n:
            P.need(where, "Choose %d %s cantrips (%d now)." % (can_n, cls, len(cans)))
        for x in cans:
            s = _spell(x)
            if not s:
                P.bad(where, "%s is not in SRD 5.2.1." % x)
            elif s["level"] != 0 or cls not in s["classes"]:
                P.bad(where, "%s is not a %s cantrip." % (x, cls))
            spells_out.append({"name": x, "level": 0, "source": cls, "ability": ab})
        always = [x for lvl, names in ALWAYS.get(cls, []) if n >= lvl for x in names]
        if cls == "Druid" and n >= 3:
            land = next((e.get("land") for e in levels if e["class"] == "Druid" and e.get("land")), None)
            always += [x for lvl, names in LAND.get(land, []) if n >= lvl for x in names]
        if cls == "Wizard":
            book_n = 6 + 2 * (n - 1)
            if len(book) < book_n:
                P.need(where, "Spellbook: choose %d level 1+ Wizard spells (%d now)." % (book_n, len(book)))
            elif len(book) > book_n + (2 + max(0, max_spell_level(cls, n) - 2) if n >= 3 else 0):
                P.bad(where, "The spellbook holds %d spells at Wizard level %d (Evocation Savant adds evocations)." % (book_n, n))
            for x in book:
                s = _spell(x)
                if not s or s["level"] < 1 or "Wizard" not in s["classes"] or s["level"] > top:
                    P.bad(where, "%s can't go in the spellbook (a Wizard spell of level 1-%d)." % (x, top))
            for x in prep:
                if x not in book:
                    P.bad(where, "%s must be in the spellbook to be prepared." % x)
        if prep_n and len(prep) != prep_n:
            P.need(where, "Prepare %d spells (%d now)." % (prep_n, len(prep)))
        for x in prep:
            s = _spell(x)
            if not s:
                P.bad(where, "%s is not in SRD 5.2.1." % x)
            elif s["level"] < 1 or (cls not in s["classes"] and not (cls == "Bard" and n >= 10 and set(s["classes"]) & SECRETS_LISTS))                     or s["level"] > top:
                P.bad(where, "%s is not a %s spell of level 1-%d%s." % (x, cls, top, " (Magical Secrets: Bard, Cleric, Druid or "
                                                                          "Wizard)" if cls == "Bard" and n >= 10 else ""))
            spells_out.append({"name": x, "level": s["level"] if s else 1, "source": cls, "ability": ab})
        for x in always:
            if not any(cr.norm(o["name"]) == cr.norm(x) and o["source"] == cls for o in spells_out):
                s = _spell(x)
                spells_out.append({"name": x, "level": s["level"] if s else 1, "source": cls, "ability": ab, "always": True})
        if cls in style_cantrips:
            for x in style_cantrips[cls][1]:
                spells_out.append({"name": x, "level": 0, "source": cls + " (Fighting Style)", "ability": ab})
        if cls == "Bard" and n >= 6:
            md = _list(mine.get("discoveries"))
            if len(md) != 2:
                P.need(where, "Magical Discoveries: choose two Cleric, Druid or Wizard spells.")
            for x in md:
                s = _spell(x)
                if not s or not set(s["classes"]) & {"Cleric", "Druid", "Wizard"} or s["level"] > top:
                    P.bad(where, "%s can't be a Magical Discovery." % x)
                spells_out.append({"name": x, "level": s["level"] if s else 1, "source": "Magical Discoveries", "ability": ab,
                                   "always": True})
        # GM 2026-10-26 (levels 10-20): Mystic Arcanum (Warlock 11/13/15/17), one Warlock spell of level 6/7/8/9 each,
        # cast once a Long Rest without a slot
        if cls == "Warlock" and n >= 11:
            arc = _list(mine.get("arcanum"))
            want = [lv for at, lv in sorted(ARCANUM_AT.items()) if n >= at]
            got = sorted((_spell(x) or {}).get("level", 0) for x in arc)
            if got != want:
                P.need(where, "Mystic Arcanum: choose one Warlock spell of %s %s." % ("each level" if len(want) > 1 else "level", ", ".join(map(str, want))))
            for x in arc:
                s = _spell(x)
                if not s or "Warlock" not in s["classes"] or s["level"] not in want:
                    P.bad(where, "%s can't be a Mystic Arcanum (a Warlock spell of level %s)." % (x, ", ".join(map(str, want))))
                spells_out.append({"name": x, "level": s["level"] if s else 6, "source": "Mystic Arcanum", "ability": ab,
                                   "always": True, "note": "once a Long Rest without a slot",
                                   "arcanum": True})   # SPELLS-4-9: cast from its rules without a slot
        # Wizard 18 Spell Mastery (a level 1 and a level 2 spell), 20 Signature Spells (two level 3 spells): spellbook
        # spells always prepared, cast without a slot (Spell Mastery at its lowest level; Signature Spells once a rest)
        if cls == "Wizard":
            for at, (key, label, lvls) in sorted(WIZARD_PICKS.items()):
                if n < at:
                    continue
                e = next((e for i, e in enumerate([e for e in levels if e["class"] == "Wizard"]) if i + 1 == at), {})
                picked = _list(e.get(key))
                if sorted((_spell(x) or {}).get("level", 0) for x in picked) != list(lvls) or len(set(picked)) != 2:
                    P.need(where, "%s: choose %s from the spellbook." % (label, "a level 1 and a level 2 spell" if lvls == (1, 2)
                                                                        else "two level 3 spells"))
                for x in picked:
                    if x not in book:
                        P.bad(where, "%s: %s is not in the spellbook." % (label, x))
                    if lvls == (1, 2) and _casting_time(x) not in (None, "action"):   # CASTER-HIGH: SRD 5.2.1
                        P.bad(where, "Spell Mastery: %s does not have a casting time of an action." % x)
                    old = next((o for o in spells_out if o["name"] == x and o["source"] == cls), None)
                    note = "%s: without a slot%s" % (label, " (at its lowest level)" if lvls == (1, 2) else ", once a Short or Long Rest")
                    if old:
                        old.update(always=True, note=note)
                    else:
                        spells_out.append({"name": x, "level": (_spell(x) or {}).get("level", 1), "source": cls, "ability": ab,
                                           "always": True, "note": note})
        casting.append({"class": cls, "ability": ab, "dc": 8 + pb + mods[ab], "attack": pb + mods[ab], "cantrips": can_n,
                        "prepared": prep_n, "max_level": top})
    slots, pact, caster_level = spell_slots(counts)

    # ---- equipment, Armor Class, attacks
    eq = ch.get("equipment") if isinstance(ch.get("equipment"), dict) else {}
    armor = _armor(eq.get("armor")) if eq.get("armor") and eq.get("armor") != "None" else None
    if eq.get("armor") and eq.get("armor") != "None" and not armor:
        P.bad("Equipment", "%s is not SRD armor." % eq["armor"])
    shield = bool(eq.get("shield"))
    weapons = [w for w in (_weapon(x) for x in _list(eq.get("weapons"))) if w]
    for x in _list(eq.get("weapons")):
        if not _weapon(x):
            P.bad("Equipment", "%s is not an SRD weapon." % x)
    if armor and armor["category"] not in armor_train:
        P.bad("Equipment", "No training with %s armor (%s)." % (armor["category"], armor["name"]))
    if shield and "shield" not in armor_train:
        P.bad("Equipment", "No Shield training.")

    def proficient(w):
        if w["category"] == "simple" and "simple" in weapon_train:
            return True
        if w["category"] == "martial":
            if "martial" in weapon_train:
                return True
            if "martial finesse-or-light" in weapon_train and (w.get("finesse") or w.get("light")):
                return True
            if "martial light" in weapon_train and w.get("light"):
                return True
        return False

    acs = []
    dex = mods["dex"]
    if armor:
        cat = armor["category"]
        acs.append((armor["ac"] + (0 if cat == "heavy" else min(2, dex) if cat == "medium" else dex), armor["name"]))
    else:
        acs.append((10 + dex, "no armor: 10 + DEX"))
        if counts.get("Barbarian"):
            acs.append((10 + dex + mods["con"], "Unarmored Defense: 10 + DEX + CON"))
        if counts.get("Monk") and not shield:
            acs.append((10 + dex + mods["wis"], "Unarmored Defense: 10 + DEX + WIS"))
        if counts.get("Sorcerer", 0) >= 3:
            acs.append((10 + dex + mods["cha"], "Draconic Resilience: 10 + DEX + CHA"))
        if "Armor of Shadows" in invocations:
            acs.append((13 + dex, "Armor of Shadows (Mage Armor): 13 + DEX"))
    ac, ac_how = max(acs)
    if shield:
        ac += 2; ac_how += " + Shield"
    if "Defense" in fighting_styles and armor:
        ac += 1; ac_how += " + Defense"
    speed = sp["speed"] if sp else 30
    if lineage == "Wood Elf":
        speed = 35
    speed_how = "%s %d ft" % (species or "species", speed)
    if armor and armor["strength"] and scores["str"] < armor["strength"]:
        speed -= 10; speed_how += ", -10 (STR below %d for %s)" % (armor["strength"], armor["name"])
    if counts.get("Barbarian", 0) >= 5 and not (armor and armor["category"] == "heavy"):
        speed += 10; speed_how += ", +10 Fast Movement"
    if counts.get("Monk", 0) >= 2 and not armor and not shield:
        um = R["classes"]["Monk"]["resources"]["unarmored_movement"][counts["Monk"] - 1]
        speed += um; speed_how += ", +%d Unarmored Movement" % um

    masteries = _list(ch.get("masteries"))
    mastery_n = 0
    for cls, n in counts.items():
        res = R["classes"][cls].get("resources", {})
        if "weapon_mastery" in res:
            mastery_n = max(mastery_n, res["weapon_mastery"][n - 1])
        elif cls in ("Paladin", "Ranger", "Rogue"):                # Weapon Mastery is a level 1 feature: two kinds
            mastery_n = max(mastery_n, 2)
    if mastery_n and len(masteries) != mastery_n:
        P.need("Weapon Mastery", "Choose %d kinds of weapons for Weapon Mastery (%d now)." % (mastery_n, len(masteries)))
    for m in masteries:
        w = _weapon(m)
        if not w or not proficient(w):
            P.bad("Weapon Mastery", "%s: a weapon kind you are proficient with." % m)
    attacks_n = 1
    for cls, n in counts.items():
        res = R["classes"][cls].get("resources", {})
        if "attacks" in res:
            attacks_n = max(attacks_n, res["attacks"][n - 1])
    if counts.get("Barbarian", 0) >= 5:
        attacks_n = max(attacks_n, 2)
    crit = 20
    if counts.get("Fighter", 0) >= 15:
        crit = 18
    elif counts.get("Fighter", 0) >= 3:
        crit = 19
    monk = counts.get("Monk", 0)
    ma_die = R["classes"]["Monk"]["resources"]["martial_arts_die"][monk - 1] if monk else 0

    attacks = []
    for w in weapons + [None]:
        if w is None:                                             # Unarmed Strike
            if weapons and not monk:
                continue
            ab = "dex" if monk and mods["dex"] > mods["str"] else "str"
            die = ma_die or 1
            attacks.append({"name": "Unarmed Strike", "atk": pb + mods[ab], "count": 1, "die": die, "bonus": mods[ab],
                            "type": "bludgeoning", "reach": 5, "melee": True, "ability": ab, "mastery": None, "proficient": True})
            continue
        ranged = w["kind"] == "ranged"
        use_dex = ranged or w.get("finesse") or (monk and not armor and not shield and (w["category"] == "simple" and not ranged or w.get("light")))
        ab = ("dex" if mods["dex"] >= mods["str"] else "str") if (w.get("finesse") or (use_dex and not ranged)) else ("dex" if ranged else "str")
        if ranged:
            ab = "dex"
        is_prof = proficient(w)
        atk = (pb if is_prof else 0) + mods[ab] + (2 if ranged and "Archery" in fighting_styles else 0)
        dice = re.match(r"(\d+)d(\d+)", w["dice"])
        count, die = (int(dice.group(1)), int(dice.group(2))) if dice else (1, 1)
        if monk and not armor and not shield and not ranged and (w["category"] == "simple" or w.get("light")) and die * count < ma_die:
            count, die = 1, ma_die
        reach = (w.get("ammunition") or [0])[0] if ranged else (10 if w.get("reach") else 5)
        attacks.append({"name": w["name"], "atk": atk, "count": count, "die": die, "bonus": mods[ab], "type": w["type"],
                        "reach": reach, "melee": not ranged, "ability": ab, "proficient": is_prof,
                        "mastery": w["mastery"] if w["name"] in masteries else None,
                        "thrown": w.get("thrown"), "two_handed": bool(w.get("two_handed")), "light": bool(w.get("light")),
                        "finesse": bool(w.get("finesse")), "heavy": bool(w.get("heavy"))})
        if not is_prof:
            P.warn("Equipment", "Not proficient with %s: no proficiency bonus to hit." % w["name"])
        if shield and w.get("two_handed"):
            P.warn("Equipment", "%s needs two hands: not with the Shield at the same time." % w["name"])
    # damaging cantrips as attacks
    char_dice = 1 + (total >= 5) + (total >= 11) + (total >= 17)
    for s in spells_out:
        if s["level"] == 0 and s["name"] in DAMAGE_CANTRIPS:
            die, roll, dtype = DAMAGE_CANTRIPS[s["name"]]
            ab = s.get("ability") or "int"
            count, bonus = char_dice, 0
            if s["name"] == "Eldritch Blast":
                count = 1
                if "Agonizing Blast" in invocations:
                    bonus = mods[ab]
            if not any(a["name"] == s["name"] for a in attacks):
                attacks.append({"name": s["name"], "atk": pb + mods[ab] if roll else None, "save_dc": None if roll else 8 + pb + mods[ab],
                                "count": count, "die": die, "bonus": bonus, "type": dtype, "reach": CANTRIP_RANGE.get(s["name"], 60),
                                "melee": CANTRIP_RANGE.get(s["name"]) == 5, "ability": ab, "cantrip": True, "proficient": True,
                                "beams": (1 + (total >= 5) + (total >= 11) + (total >= 17)) if s["name"] == "Eldritch Blast" else None})

    # ---- hit points
    hp, hp_how = 0, []
    con = mods["con"]
    for i, e in enumerate(levels):
        die = R["classes"][e["class"]]["hit_die"]
        if i == 0:
            hp += die; hp_how.append("d%d max %d" % (die, die))
        else:
            v = e["hp"] if isinstance(e.get("hp"), int) and 1 <= e["hp"] <= die else die // 2 + 1
            hp += v
    hp += con * total
    if total:
        hp_how.append("CON %s x %d" % (signed(con), total))
        if len(levels) > 1:
            rolled = sum(1 for e in levels[1:] if isinstance(e.get("hp"), int))
            hp_how.insert(1, "%d level%s by %s" % (total - 1, "s" if total > 2 else "", "average" if not rolled else
                                                     "average and rolled dice"))
    if species == "Dwarf":
        hp += total; hp_how.append("Dwarven Toughness +%d" % total)
    if counts.get("Sorcerer", 0) >= 3:
        hp += 3 + counts["Sorcerer"] - 3; hp_how.append("Draconic Resilience +%d" % counts["Sorcerer"])
    hp = max(1, hp)

    # ---- saves, skills, initiative
    save_profs = list(R["classes"][first]["saves"]) if first else []
    if counts.get("Rogue", 0) >= 15:                              # Slippery Mind (Rogue 15): Wisdom and Charisma saves
        save_profs += [a for a in ("wis", "cha") if a not in save_profs]
    if counts.get("Monk", 0) >= 14:                               # Disciplined Survivor (Monk 14): every saving throw
        save_profs += [a for a in ABILITIES if a not in save_profs]
    saves = {a: mods[a] + (pb if a in save_profs else 0) for a in ABILITIES}
    skill_bonus = {}
    jack = counts.get("Bard", 0) >= 2
    for s, a in R["skills"].items():
        b = mods[a]
        if s in expertise:
            b += 2 * pb
        elif s in skills:
            b += pb
        elif jack:
            b += pb // 2
        skill_bonus[s] = b
    for e in levels:
        if e.get("order") == "Thaumaturge":
            for s in ("Arcana", "Religion"):
                skill_bonus[s] += max(1, mods["wis"])
        if e.get("order") == "Magician":
            for s in ("Arcana", "Nature"):
                skill_bonus[s] += max(1, mods["wis"])
    initiative = dex + (pb if "Alert" in feats else 0)

    # ---- resources
    res = []
    for cls, n in counts.items():
        r = R["classes"][cls].get("resources", {})
        if cls == "Barbarian":
            res += [("Rage", "%d a day, +%d damage" % (r["rages"][n - 1], r["rage_damage"][n - 1]))]
        if cls == "Bard":
            res += [("Bardic Inspiration", "d%d, %d uses" % (r["inspiration_die"][n - 1], max(1, mods["cha"])))]
        if cls == "Cleric" and n >= 2:
            res += [("Channel Divinity", r["channel_divinity"][n - 1])]
        if cls == "Druid" and n >= 2:
            res += [("Wild Shape", r["wild_shape"][n - 1])]
        if cls == "Fighter":
            res += [("Second Wind", r["second_wind"][n - 1])]
            if n >= 2:
                res += [("Action Surge", r["action_surge"][n - 1])]
            if n >= 9:
                res += [("Indomitable", r["indomitable"][n - 1])]
        if cls == "Monk":
            res += [("Martial Arts die", "d%d" % r["martial_arts_die"][n - 1])]
            if n >= 2:
                res += [("Focus Points", r["focus"][n - 1])]
        if cls == "Paladin":
            res += [("Lay On Hands", "%d HP" % r["lay_on_hands"][n - 1])]
            if n >= 3:
                res += [("Channel Divinity", r["channel_divinity"][n - 1])]
        if cls == "Ranger":
            res += [("Favored Enemy (free Hunter's Mark)", r["favored_enemy"][n - 1])]
        if cls == "Rogue":
            res += [("Sneak Attack", "%dd6" % r["sneak_attack"][n - 1])]
        if cls == "Sorcerer" and n >= 2:
            res += [("Sorcery Points", r["sorcery_points"][n - 1])]
    if species == "Dragonborn":
        res += [("Breath Weapon", "%d a day, %dd10 %s, DC %d" % (pb, char_dice, (sp.get("lineages") or {}).get(lineage, "?"),
                                                              8 + mods["con"] + pb))]
    if species in ("Goliath", "Orc"):
        res += [("Giant Ancestry" if species == "Goliath" else "Adrenaline Rush", "%d a day" % pb)]
    if species == "Human":
        res += [("Heroic Inspiration", "after each Long Rest")]

    # ---- the sheet
    class_list = []
    for cls in counts:
        k = {"name": cls, "level": counts[cls]}
        if counts[cls] >= 3:
            k["subclass"] = R["classes"][cls]["subclass"]["name"]
        class_list.append(k)
    main = _main_attack(attacks)
    feature_names = [f"{n}" for _, _, n in features]
    if species and sp:
        feature_names += [t for t in sp["traits"]]
        if lineage:
            feature_names.append("%s: %s" % ("Ancestry" if species in ("Dragonborn", "Goliath") else "Lineage", lineage))
    feature_names += ["Eldritch Invocation: " + x for x in invocations] + ["Metamagic: " + x for x in metamagic]
    resist = []
    if species == "Dragonborn" and lineage:
        resist.append(sp["lineages"][lineage].title())
    if species == "Dwarf":
        resist.append("Poison")
    if species == "Tiefling" and lineage in TIEFLING_RESIST:
        resist.append(TIEFLING_RESIST[lineage])
    affinity = next((e["affinity"] for e in levels if e.get("class") == "Sorcerer" and e.get("affinity") in AFFINITY), None) \
        if counts.get("Sorcerer", 0) >= 6 else None
    if affinity and affinity.title() not in resist:              # Elemental Affinity: Resistance to its type
        resist.append(affinity.title())
    dv = sp.get("darkvision") if sp else None
    if lineage == "Drow":
        dv = 120
    gold, kit_items, kit_count, gold_how = None, [], {}, ""
    if total == 1 and first:
        # KITS-01: a kit's gear is free and brings its own coins; anything else is bought from the gold
        ck = CLASS_KITS.get(first, {}).get(eq.get("class_kit")) if eq.get("class_kit") not in (None, "", "gold") else None
        bk = BACKGROUND_KITS.get(bgname) if eq.get("background_kit") == "kit" else None
        if eq.get("class_kit") not in (None, "", "gold") and not ck:
            P.bad("Equipment", "%s has no kit %s." % (first, eq["class_kit"]))
        if eq.get("background_kit") == "kit" and not bk:
            P.bad("Equipment", "The %s background has no equipment kit." % (bgname or "chosen"))
        kits_taken = [k for k in (ck, bk) if k]
        free_weapons = {}
        for k in kits_taken:
            for name, n in k["weapons"]:
                free_weapons[name] = free_weapons.get(name, 0) + n
            kit_items += k["items"]
        kit_count = {n: c for n, c in free_weapons.items() if c > 1}
        free = lambda part: any(k.get(part) for k in kits_taken)
        cost = (armor["cost"] if armor and not (ck and ck["armor"] == armor["name"]) else 0) + \
            sum(w["cost"] for w in weapons if w["name"] not in free_weapons) + (10 if shield and not free("shield") else 0) + \
            (25 if eq.get("focus") and not free("focus") else 0) + (50 if eq.get("spellbook") and not free("spellbook") else 0)
        cls_money, bg_money = (ck["gp"] if ck else CLASS_GOLD[first]), (bk["gp"] if bk else BACKGROUND_GOLD)
        gold = round(cls_money + bg_money - cost, 2)
        gold_how = "%s: %s (%s GP) + background: %s (%s GP)%s" % (
            first, ("kit %s" % eq["class_kit"]) if ck else "gold", cls_money, "kit" if bk else "gold", bg_money,
            (" - %s GP of other gear" % round(cost, 2)) if cost else "")
        if gold < 0:
            P.warn("Equipment", "This gear costs more than the starting gold (%s GP over)." % -gold)
    if counts.get("Wizard") and not eq.get("spellbook"):
        P.warn("Equipment", "A Wizard needs a Spellbook.")
    feats_out = list(feats)
    sheet = {
        "format": "isles-character/1", "id": ch.get("id") or "", "name": str(ch.get("name") or "").strip(), "kind": "pc",
        "ruleset": "SRD 5.2.1", "species": species or "", "lineage": lineage, "size": size, "background": bgname or "", "alignment": str(ch.get("alignment") or "")[:20],
        "classes": class_list, "abilities": scores, "proficiencies": skills + ["%s (expertise)" % s for s in expertise if s in skills],
        "saves": save_profs, "feats": feats_out, "features": feature_names, "spells": spells_out,
        "equipment": ([armor["name"]] if armor else []) + (["Shield"] if shield else []) +
        [w["name"] + (" ×%d" % kit_count[w["name"]] if w["name"] in kit_count else "") for w in weapons] +
        (["Component Pouch"] if eq.get("focus") and not any("Focus" in x or "Holy Symbol" in x for x in kit_items) else []) +
        (["Spellbook"] if eq.get("spellbook") else []) + kit_items +
        [x.strip() for x in str(eq.get("other") or "").split("\n") if x.strip()],
        "languages": list(dict.fromkeys(langs)), "tools": list(dict.fromkeys(tools)), "senses": "Darkvision %d ft." % dv if dv else "",
        "damage_resistances": resist, "notes": str(ch.get("notes") or ""), "token_id": ch.get("token_id") or "",
        "space_ft": 5, **({"boon_abilities": boon_up} if boon_up else {}),
        "combat": {"hp_max": hp, "ac": ac, "speed": speed, "attack_bonus": main["atk"] if main and main.get("atk") is not None else pb + mods["str"],
                   "damage_count": main["count"] if main else 1, "damage_die": main["die"] if main else 1,
                   "damage_bonus": main["bonus"] if main else mods["str"], "reach": min(15, main["reach"]) if main and main.get("melee") else 5},
        "derived": {"level": total, "proficiency_bonus": pb, "initiative": initiative, "hp": hp, "hp_how": ", ".join(hp_how),
                    "ac": ac, "ac_how": ac_how, "speed": speed, "speed_how": speed_how, "saves": saves, "skills": skill_bonus,
                    "passive_perception": 10 + skill_bonus["Perception"], "casting": casting, "slots": slots, "pact": pact,
                    "caster_level": caster_level, "attacks": attacks, "attacks_per_action": attacks_n, "crit": crit,
                    "resources": [[a, b] for a, b in res], "hit_dice": {("d%d" % R["classes"][c]["hit_die"]): n for c, n in counts.items()},
                    "masteries": masteries, "fighting_styles": fighting_styles, "invocations": invocations,
                    "metamagic": metamagic, "elemental_affinity": affinity,
                    "features_by_level": [[lv, src, n] for lv, src, n in features],
                    "gold_remaining": gold, "gold_how": gold_how},
        "build": ch,
    }
    if not sheet["name"]:
        P.need("Name", "Give the character a name.")
    sheet["gm_rules"] = member(sheet)["gm_rules"]
    done = not P.errors and not P.todo
    return {"ok": True, "done": done, "sheet": sheet, "errors": P.errors, "todo": P.todo, "warnings": P.warnings,
            "options": options(ch, counts, total, scores, feats, invocations)}


def _feat_choice(P, where, feat, a, scores, lv, cls, n, styles, feats, sources, asi_feats, seen):
    R = cr.rules()
    inc = {k: int(v) for k, v in (a.get("abilities") or {}).items() if k in ABILITIES and isinstance(v, int) and v}
    base = re.sub(r"\s*\(.*\)$", "", feat)
    spec = R["feats"].get(base)
    if not spec:
        P.bad(where, "%s is not an SRD 5.2.1 feat." % feat); return
    if spec.get("level", 0) > lv:
        P.bad(where, "%s needs character level %d." % (feat, spec["level"])); return
    if spec["category"] == "fighting style" and cls not in ("Fighter", "Paladin", "Ranger") and not any(c in seen for c in ("Fighter", "Paladin", "Ranger")):
        P.bad(where, "%s needs the Fighting Style feature." % feat); return
    if spec["category"] == "fighting style" and feat in styles:
        P.bad(where, "%s is already a Fighting Style of yours." % feat); return
    if feat in feats and not spec.get("repeatable"):
        P.bad(where, "%s can't be taken twice." % feat); return
    if base == "Ability Score Improvement":
        if sorted(inc.values()) not in ([2], [1, 1]):
            P.need(where, "Ability Score Improvement: +2 to one score or +1 to two.")
    elif base == "Grappler":
        if not (scores["str"] >= 13 or scores["dex"] >= 13):
            P.bad(where, "Grappler needs STR or DEX 13+.")
        if list(inc.values()) != [1] or list(inc)[0] not in ("str", "dex"):
            P.need(where, "Grappler: +1 to STR or DEX.")
    elif spec["category"] == "epic boon":
        allowed = ("str", "dex") if base == "Boon of Irresistible Offense" else ("int", "wis", "cha") if base == "Boon of Spell Recall" else ABILITIES
        if list(inc.values()) != [1] or list(inc)[0] not in allowed:
            P.need(where, "%s: +1 to %s." % (feat, " or ".join(x.upper() for x in allowed)))
    elif inc:
        P.bad(where, "%s gives no ability score increase." % feat)
    cap = 30 if spec["category"] == "epic boon" else 20
    for k, v in inc.items():
        if scores[k] + v > cap:
            P.bad(where, "%s can't go above %d." % (k.upper(), cap))
        scores[k] = min(cap, scores[k] + v)
    feats.append(feat); sources.append((where, feat)); asi_feats.append(feat)
    if spec["category"] == "fighting style":
        styles.append(feat)


def _main_attack(attacks):
    """The attack the sheet's combat profile shows: the best weapon attack (melee first), else a cantrip."""
    def avg(a):
        return a["count"] * (a["die"] + 1) / 2 + a["bonus"] + (a.get("atk") or 0) * 0.5
    weapons = [a for a in attacks if not a.get("cantrip") and a.get("atk") is not None]
    melee = [a for a in weapons if a["melee"]]
    pool = melee or weapons or [a for a in attacks if a.get("atk") is not None]
    return max(pool, key=avg) if pool else None


def options(ch, counts, total, scores, feats, invocations):
    """What the page offers for the next choices (all SRD 5.2.1)."""
    R = cr.rules()
    nxt = total + 1
    can_take = []
    for cls, C in R["classes"].items():
        if total and cls not in counts:
            prim = C["primary"]
            ok = any(scores[a] >= 13 for a in prim) if C["primary_any"] else all(scores[a] >= 13 for a in prim)
            mine = all((any(scores[a] >= 13 for a in R["classes"][c]["primary"]) if R["classes"][c]["primary_any"]
                        else all(scores[a] >= 13 for a in R["classes"][c]["primary"])) for c in counts)
            can_take.append([cls, ok and mine, "" if ok and mine else "needs %s 13+" % "/".join(a.upper() for a in prim)])
        else:
            can_take.append([cls, True, ""])
    return {"next_level": nxt if nxt <= 20 else None, "classes": can_take,
            "feats": {k: v for k, v in R["feats"].items()}, "fighting_styles": FIGHTING_STYLES,
            "invocations": {k: {"level": v[0], "needs": v[1], "repeatable": v[2]} for k, v in INVOCATIONS.items()},
            "metamagic": METAMAGIC, "languages": STANDARD_LANGUAGES, "lands": list(LAND), "affinities": list(AFFINITY)}


# ------------------------------------------------------------------ the simulator party member
SIM_SPELL_FLAGS = {  # SRD spell -> the simulator's flag (sim/party.py tactics, sim/live_spells.py)
    "Sleep": "sleep", "Burning Hands": "burning_hands", "Ray of Frost": "ray_of_frost", "Shield": "shield",
    "Cure Wounds": "cure_wounds", "Healing Word": "healing_word", "Shield of Faith": "shield_of_faith", "Command": "command",
    "Hex": "hex", "Hideous Laughter": "hideous_laughter", "Fireball": "fireball", "Scorching Ray": "scorching_ray",
    "Misty Step": "misty_step", "Ice Knife": "ice_knife", "Thunderwave": "thunderwave", "Shatter": "shatter",
    "Hellish Rebuke": "hellish_rebuke", "Hold Person": "hold_person", "Spiritual Weapon": "spiritual_weapon",
    "Spirit Guardians": "spirit_guardians", "Mass Healing Word": "mass_healing_word", "Searing Smite": "searing_smite",
    "Vicious Mockery": "vicious_mockery", "Shillelagh": "shillelagh",
    "Magic Missile": "magic_missile",                            # GM 2026-10-23: a Sorcerer's (a Wizard's by class too)
    "Cone of Cold": "cone_of_cold", "Hold Monster": "hold_monster", "Mass Cure Wounds": "mass_cure_wounds",   # level 9
}
SIM_BY_CLASS = {"cleric": ("Bless", "Guiding Bolt", "Healing Word"), "paladin": ("Bless", "Divine Smite"),
                "wizard": ("Magic Missile",)}
SIM_FEATURES = {"Second Wind", "Action Surge", "Extra Attack", "Two Extra Attacks", "Three Extra Attacks", "Rage",
                "Reckless Attack", "Frenzy", "Sneak Attack", "Steady Aim", "Uncanny Dodge", "Reliable Talent",
                "Cunning Action", "Improved Critical", "Superior Critical", "Lay On Hands", "Paladin's Smite",
                "Channel Divinity", "Sacred Weapon", "Aura of Protection", "Bardic Inspiration", "Divine Spark",
                "Turn Undead", "Disciple of Life", "Preserve Life", "Blessed Healer", "Potent Cantrip", "Sculpt Spells",
                "Dark One's Blessing", "Spellcasting", "Pact Magic", "Unarmored Defense", "Fast Movement", "Weapon Mastery",
                "Fighting Style", "Expertise", "Breath Weapon", "Damage Resistance", "Darkvision", "Fey Ancestry",
                "Dwarven Toughness", "Draconic Resilience", "Martial Arts", "Unarmored Movement", "Draconic Ancestry",
                "Dwarven Resilience", "Keen Senses", "Skillful", "Versatile", "Elven Lineage", "Fiendish Legacy",
                "Divine Order: Protector", "Primal Order: Warden", "Druidic", "Thieves' Cant", "Hunter's Lore",
                # GM 2026-10-23: the Sorcerer (sim/live_sorcery.py; Play live and the simulator)
                "Innate Sorcery", "Font of Magic", "Sorcery Incarnate", "Elemental Affinity", "Careful Spell",
                "Distant Spell", "Empowered Spell", "Extended Spell", "Heightened Spell", "Quickened Spell",
                "Seeking Spell", "Subtle Spell", "Transmuted Spell", "Twinned Spell"}
SHEET_HEADINGS = {"Eldritch Invocations", "Metamagic", "Spellcasting", "Pact Magic",   # the chosen ones are listed apart
                  # GM 2026-10-26: spells the sheet lists already, and choices made on the sheet (not things to do)
                  "Fiend Spells", "Life Domain Spells", "Oath of Devotion Spells", "Divine Order", "Evocation Savant",
                  "Faithful Steed", "Otherworldly Presence", "Additional Fighting Style", "Fighting Style",
                  "Draconic Spells", "Circle Spells", "Land's Aid"}
SIM_FEATS = {"Savage Attacker", "Alert", "Archery", "Defense", "Ability Score Improvement", "Skilled", "Magic Initiate",
             "Great Weapon Fighting"}                            # gwf (GM 2026-10-23, in the damage roll)
# GM 2026-10-26 (goal 9, the test heroes to level 20): class and subclass features -> the member's flag the simulator
# reads (sim/party.py, sim/live_play.py, sim/high_levels.py). PLAYED ones count as played (not "Ask the GM"); the others
# are recorded on the member but still listed for the GM (no fight effect yet).
FEATURE_FLAGS = {
    "Indomitable": "indomitable", "Tactical Master": "tactical_master", "Tactical Shift": "tactical_shift",
    "Remarkable Athlete": "remarkable_athlete", "Studied Attacks": "studied_attacks", "Survivor": "survivor",
    "Cunning Strike": "cunning_strike", "Supreme Sneak": "supreme_sneak", "Evasion": "evasion",
    "Improved Cunning Strike": "improved_cunning_strike",
    "Brutal Strike": "brutal_strike", "Improved Brutal Strike": "improved_brutal_strike", "Mindless Rage": "mindless_rage",
    "Instinctive Pounce": "instinctive_pounce", "Feral Instinct": "feral_instinct", "Relentless Rage": "relentless_rage",
    "Aura of Devotion": "aura_devotion", "Abjure Foes": "abjure_foes", "Aura of Courage": "aura_courage",
    "Radiant Strikes": "radiant_strikes", "Aura Expansion": "aura_ft",
    "Sear Undead": "sear_undead", "Blessed Strikes": "potent_spellcasting", "Supreme Healing": "supreme_healing",
    "Empowered Evocation": "empowered_evocation",
    "Eldritch Mind": "eldritch_mind", "Fiendish Vigor": "fiendish_vigor", "Dark One's Own Luck": "own_luck",
    # group 3, batch 1 (GM 2026-10-27; sim/high_levels.py)
    "Elusive": "elusive", "Indomitable Might": "indomitable_might", "Persistent Rage": "persistent_rage",
    "Improved Blessed Strikes": "improved_blessed_strikes",
    # MONK-01 (GM 2026-10-28, "Monk as SRD"; sim/monk.py)
    "Deflect Attacks": "deflect_attacks", "Slow Fall": "slow_fall", "Stunning Strike": "stunning_strike",
    "Deflect Energy": "deflect_energy", "Open Hand Technique": "open_hand",
    # GM 2026-10-28 ("heroes 20"): the Monk 14-18 (sim/monk.py)
    "Disciplined Survivor": "disciplined_survivor", "Perfect Focus": "perfect_focus", "Superior Defense": "superior_defense",
    # Bard 18, 20 (GM 2026-10-28, "heroes 20"; sim/high_levels.py)
    "Superior Inspiration": "superior_inspiration", "Words of Creation": "words_of_creation",
    # SORCERER-20 (GM 2026-10-28, "heroes 20"; sim/live_sorcery.py)
    "Dragon Wings": "dragon_wings", "Arcane Apotheosis": "arcane_apotheosis",
    # CASTER-HIGH (GM 2026-10-28; sim/high_levels.py)
    "Overchannel": "overchannel", "Spell Mastery": "spell_mastery", "Signature Spells": "signature_spells",
    "Hurl Through Hell": "hurl_through_hell", "Eldritch Master": "eldritch_master",
    # MARTIAL-HIGH (GM 2026-10-28; sim/martial_high.py): Fighter, Thief, Berserker, Devotion Paladin
    "Tactical Mind": "tactical_mind", "Heroic Warrior": "heroic_warrior", "Devious Strikes": "devious_strikes",
    "Thief's Reflexes": "thiefs_reflexes", "Stroke of Luck": "stroke_of_luck", "Retaliation": "retaliation",
    "Intimidating Presence": "intimidating_presence", "Restoring Touch": "restoring_touch",
    "Smite of Protection": "smite_protection", "Holy Nimbus": "holy_nimbus",
    # EPIC-BOONS-01 (GM 2026-10-28): the Epic Boon feats (sim/epic_boons.py)
    **epic_boons.FLAGS,
}
PLAYED = {"Indomitable", "Tactical Master", "Studied Attacks", "Survivor", "Cunning Strike", "Supreme Sneak", "Evasion",
          "Improved Cunning Strike",
          "Brutal Strike", "Mindless Rage", "Instinctive Pounce", "Relentless Rage", "Aura of Devotion", "Abjure Foes",
          "Aura of Courage", "Radiant Strikes", "Aura Expansion", "Sear Undead", "Blessed Strikes", "Supreme Healing",
          "Empowered Evocation", "Eldritch Mind", "Fiendish Vigor", "Dark One's Own Luck", "Danger Sense", "Slippery Mind",
          "Primal Champion", "Body and Mind", "Two Extra Attacks", "Mystic Arcanum",
          "Elusive", "Indomitable Might", "Persistent Rage", "Improved Blessed Strikes", "Remarkable Athlete",
          "Monk's Focus", "Deflect Attacks", "Slow Fall", "Stunning Strike", "Deflect Energy", "Open Hand Technique",
          "Disciplined Survivor", "Perfect Focus", "Superior Defense",
          "Superior Inspiration", "Words of Creation",
          "Dragon Wings", "Arcane Apotheosis",                   # SORCERER-20 (GM 2026-10-28)
          "Overchannel", "Spell Mastery", "Signature Spells", "Hurl Through Hell", "Eldritch Master",   # CASTER-HIGH
          "Tactical Mind", "Tactical Shift", "Heroic Warrior", "Devious Strikes", "Thief's Reflexes", "Stroke of Luck",
          "Retaliation", "Intimidating Presence", "Restoring Touch", "Smite of Protection", "Holy Nimbus"}   # MARTIAL-HIGH
SIM_FEATURES |= PLAYED
# Choices a player makes that no control offers yet: they stay on Ask the GM, so nothing on a sheet is ever unusable
NOT_AT_THE_TABLE = {"Channel Divinity", "Divine Spark", "Turn Undead", "Preserve Life", "Sacred Weapon", "Reckless Attack", "Frenzy",
                    "Steady Aim", "Breath Weapon", "Paladin's Smite"}
MASTERY_FLAGS = {"Graze", "Vex", "Sap", "Cleave", "Nick"}       # Nick: GM 2026-10-25 (live play's Light extra attack)


def _dmg(count, die, bonus):
    return "%dd%d%s" % (count, die, ("%+d" % bonus) if bonus else "")


def member(sheet, prefer=None):
    """Any isles-character/1 sheet -> {build, gm_rules, problems}. A built sheet uses its worked-out `derived` values; an
    imported one uses its combat profile and scores, and its features and spells by name. Nothing is guessed: what the
    sheet lacks is a problem, and everything the simulator can't play is listed for the GM to rule.
    prefer: the name of the attack that comes first (the member's `weapon`), when the sheet has it."""
    s = sheet if isinstance(sheet, dict) else {}
    d = s.get("derived") if isinstance(s.get("derived"), dict) and "attacks" in s.get("derived", {}) else None
    k = s.get("combat") or {}
    problems, gm = [], []
    abil = {a: (s.get("abilities") or {}).get(a) for a in ABILITIES}
    if any(not isinstance(v, int) for v in abil.values()):
        problems.append("Fill in all six ability scores.")
        abil = {a: v if isinstance(v, int) else 10 for a, v in abil.items()}
    mods = {a: mod(v) for a, v in abil.items()}
    classes = [c for c in (s.get("classes") or []) if isinstance(c, dict) and c.get("name")]
    level = sum(int(c.get("level") or 0) for c in classes) or 1
    level = max(1, min(20, level))
    pb = prof_bonus(level)
    names = {cr.norm(c["name"]): int(c.get("level") or 0) for c in classes}
    main_cls = max(classes, key=lambda c: int(c.get("level") or 0))["name"] if classes else "fighter"
    for f in ("hp_max", "ac", "speed"):
        if not isinstance(k.get(f), int):
            problems.append("Fill in %s." % {"hp_max": "hit points", "ac": "Armor Class", "speed": "Speed"}[f])
    save_profs = s.get("saves") if isinstance(s.get("saves"), list) else []
    saves = (d or {}).get("saves") or {a: mods[a] + (pb if a in save_profs else 0) for a in ABILITIES}
    b = {"class": cr.norm(main_cls), "level": level, "abilities": abil, "str_score": abil["str"], "dex_score": abil["dex"], "alignment": str(s.get("alignment") or ""),
         "hp": k.get("hp_max") or 1, "ac": k.get("ac") or 10, "speed": "%d ft." % (k.get("speed") or 30),
         "senses": s.get("senses") or "", "skills": [p.replace(" (expertise)", "") for p in (s.get("proficiencies") or [])
                                                  if isinstance(p, str) and p.replace(" (expertise)", "") in cr.rules()["skills"]]}
    for a in ABILITIES:
        b[a + "_save"] = saves.get(a, mods[a])
    b["init"] = 10 + ((d or {}).get("initiative", mods["dex"]))
    exp = [p.replace(" (expertise)", "") for p in (s.get("proficiencies") or []) if isinstance(p, str) and p.endswith("(expertise)")]
    if exp:
        b["expertise"] = exp
    skills = (d or {}).get("skills") or {}
    if "Stealth" in skills:
        b["stealth"] = skills["Stealth"]
    if any((_armor(x) or {}).get("stealth_disadvantage") for x in s.get("equipment") or [] if isinstance(x, str)):
        b["stealth_disadvantage"] = True                             # play-test 2026-11-02: Chain Mail and the like, as the SRD's armor table
    if "Medicine" in skills:
        b["medicine"] = skills["Medicine"]
    if s.get("damage_resistances"):
        b["damageresistances"] = ", ".join(s["damage_resistances"])
    tools = [x for x in (s.get("tools") or []) if isinstance(x, str)]
    if tools:
        b["tools"] = tools                                       # GM 2026-10-23: tool proficiencies (sim/requirements.py)

    # attacks: the sheet's weapon attacks and damaging cantrips (built), or the combat profile (imported)
    def weapon_of(a):
        w = {"name": a["name"], "dmgtype": a.get("type") or "", "atk": a["atk"], "reach": a["reach"],
             "dmg": _dmg(a["count"], a["die"], a["bonus"]), "crit": (d or {}).get("crit", 20) if not a.get("cantrip") else 20}
        if a.get("finesse"):
            w["finesse"] = True
        if a.get("light"):
            w["light"] = True                                   # GM 2026-10-25: the Light property's extra attack
        if a.get("cantrip"):
            w["cantrip"] = True                                 # GM 2026-10-23: a spell (Innate Sorcery, Metamagic)
        if a["name"] in CANTRIP_CHOICES:
            w["dmg_choices"] = list(CANTRIP_CHOICES[a["name"]])
        if a.get("ability") == "str" and a.get("melee") and not a.get("cantrip"):
            w["str"] = True
        m = a.get("mastery")
        if m in MASTERY_FLAGS:
            w[m.lower()] = mods[a.get("ability") or "str"] if m == "Graze" else True
        elif m:
            gm.append("Weapon Mastery %s (%s)" % (m, a["name"]))
        return w
    extra_attacks = 2 if any(names.get(c, 0) >= 5 for c in ("fighter", "barbarian", "paladin", "ranger", "monk")) else 1
    if names.get("fighter", 0) >= 11:
        extra_attacks = 3 if names["fighter"] < 20 else 4
    # GM 2026-10-28 ("also no weapons"): an imported sheet's SRD weapons (and damaging cantrips) are its attacks, as a built
    # sheet's are; the combat profile stays the fallback for a sheet without them
    imp = None if d else imported_attacks(s, mods, pb, level)
    src = d or ({"attacks": imp, "attacks_per_action": extra_attacks} if imp and any(a["atk"] is not None for a in imp) else None)
    if src:
        atks = [a for a in src["attacks"] if a.get("atk") is not None]
        melee = sorted([a for a in atks if a.get("melee") and not a.get("cantrip")], key=lambda a: -(a["count"] * (a["die"] + 1) / 2 + a["bonus"]))
        ranged = sorted([a for a in atks if not a.get("melee") and not a.get("cantrip")], key=lambda a: -(a["count"] * (a["die"] + 1) / 2 + a["bonus"]))
        cants = sorted([a for a in atks if a.get("cantrip")], key=lambda a: -(a["count"] * (a["die"] + 1) / 2 + a["bonus"]))
        caster = cr.norm(main_cls) in ("wizard", "sorcerer", "warlock")
        first = (cants or melee or ranged) if caster else (melee or ranged or cants)
        if prefer and any(a["name"] == prefer for a in first or []):
            first = sorted(first, key=lambda a: a["name"] != prefer)
        elif prefer and any(a["name"] == prefer for a in atks):
            first = [next(a for a in atks if a["name"] == prefer)] + (first or [])
        if first:
            b["weapon"] = weapon_of(first[0])
            reach = ranged + cants
            if imp:                                              # an imported sheet: its best reach, a bow or a cantrip
                reach = sorted(reach, key=lambda a: -(a["count"] * (a["die"] + 1) / 2 + a["bonus"]))
            other = [a for a in (reach + melee) if a is not first[0]]
            if other:
                b["ranged"] = weapon_of(other[0])
            # GM 2026-10-25 (SRD 5.2.1 Light): after an Attack action attack with a Light weapon, one extra attack as a
            # Bonus Action with a different Light weapon, without the ability modifier to damage unless it is negative
            # (Two-Weapon Fighting adds it)
            off = next((a for a in melee if a is not first[0] and a.get("light")), None) if first[0].get("light") \
                and first[0].get("melee") and not first[0].get("cantrip") else None
            if off:
                ow = weapon_of(off)
                if "Two-Weapon Fighting" not in (src.get("fighting_styles") or []) and off["bonus"] > 0:
                    ow["dmg"] = _dmg(off["count"], off["die"], 0)
                b["offhand"] = ow
            taken = {(b.get(k) or {}).get("name") for k in ("weapon", "ranged")}   # NOTES 7.8: the rest of the sheet's attacks
            rest = [a for a in reach + melee if a["name"] not in taken and not (a["name"] == "Unarmed Strike" and names.get("monk"))]
            for key, a in zip(cr.MORE_ATTACKS, rest):
                b[key] = weapon_of(a)
        b["attacks"] = src.get("attacks_per_action", 1)
        for a in src["attacks"]:
            if a.get("cantrip") and a["name"] == "Eldritch Blast" and a.get("beams", 1) > 1:
                b["beams"] = a["beams"]
            if a.get("atk") is None:
                gm.append("%s (a saving-throw cantrip)" % a["name"])
        for a in (b.get(k) for k in cr.WEAPON_KEYS):            # Evoker's Potent Cantrip
            if a and a["name"] in DAMAGE_CANTRIPS and names.get("wizard", 0) >= 3:
                a["potent"] = True
    elif all(isinstance(k.get(f), int) for f in ("attack_bonus", "damage_die", "damage_bonus")):
        b["weapon"] = {"name": next((e for e in (s.get("equipment") or []) if isinstance(e, str) and _weapon(e)), "Attack"),
                       "dmgtype": "", "atk": k["attack_bonus"], "reach": k.get("reach") or 5,
                       "dmg": _dmg(k.get("damage_count") or 1, k["damage_die"], k["damage_bonus"]), "crit": 20}
        if _weapon(b["weapon"]["name"]):
            b["weapon"]["dmgtype"] = _weapon(b["weapon"]["name"])["type"]
        b["attacks"] = extra_attacks
    else:
        problems.append("Fill in the attack (attack bonus and damage) under In a fight.")

    # class features the simulator plays
    feats = [cr.norm(f) for f in (s.get("feats") or []) if isinstance(f, str)]
    feats_raw = [f for f in (s.get("feats") or []) if isinstance(f, str)]
    feature_names = [f if isinstance(f, str) else (f or {}).get("name", "") for f in (s.get("features") or [])]
    fnorm = {cr.bare(f) for f in feature_names}
    if "savage attacker" in feats:
        b["savage_attacker"] = True
    lv = names.get
    R = cr.rules()["classes"]
    if lv("fighter"):
        n = lv("fighter")
        b["second_wind"] = R["Fighter"]["resources"]["second_wind"][n - 1]
        if n >= 2:
            b["action_surge"] = R["Fighter"]["resources"]["action_surge"][n - 1]
    if lv("barbarian"):
        n = lv("barbarian")
        b["rages"], b["rage_damage"] = R["Barbarian"]["resources"]["rages"][n - 1], R["Barbarian"]["resources"]["rage_damage"][n - 1]
        if n >= 2:
            b["reckless"] = True
        if n >= 3:
            b["frenzy"] = True
    if lv("rogue"):
        n = lv("rogue")
        b["sneak"] = "%dd6" % ((n + 1) // 2)
        if n >= 3:
            b["steady_aim"] = True
        if n >= 5:
            b["uncanny_dodge"] = True
        if n >= 7:
            b["reliable_talent"] = True
    if lv("paladin"):
        n = lv("paladin")
        b["lay_on_hands"] = 5 * n
        if n >= 2:
            b["smite"] = True
        if n >= 3:
            b["channel"] = R["Paladin"]["resources"]["channel_divinity"][n - 1]
            b["sacred_weapon"] = max(1, mods["cha"])
        if n >= 6:
            b["aura"] = max(1, mods["cha"])
    if lv("cleric"):
        n = lv("cleric")
        if n >= 2:
            b["channel"] = max(b.get("channel", 0), R["Cleric"]["resources"]["channel_divinity"][n - 1])
            b["divine_spark"] = True; b["turn_undead"] = True
        if n >= 3:
            b["disciple_of_life"] = True; b["preserve_life"] = True
        if n >= 6:
            b["blessed_healer"] = True
    if lv("bard"):
        b["inspiration"] = max(1, mods["cha"])
    if lv("sorcerer"):                                           # GM 2026-10-23: the Sorcerer (sim/live_sorcery.py)
        n = lv("sorcerer")
        b["sorcerer_level"], b["innate_sorcery"], b["cha_mod"] = n, 2, mods["cha"]
        if n >= 2:
            b["sorcery_points"] = R["Sorcerer"]["resources"]["sorcery_points"][n - 1]
            mm = (d or {}).get("metamagic") or [x[len("Metamagic: "):] for x in feature_names if x.startswith("Metamagic: ")]
            if [m for m in mm if m in METAMAGIC]:
                b["metamagic"] = [m for m in mm if m in METAMAGIC]
        if n >= 6:
            aff = (d or {}).get("elemental_affinity") or next(
                (e.get("affinity") for e in ((s.get("build") or {}).get("levels") or []) if isinstance(e, dict)
                 and e.get("class") == "Sorcerer" and e.get("affinity") in AFFINITY), None)
            if aff:
                b["elemental_affinity"] = aff
            else:
                gm.append("Elemental Affinity (its damage type is not on the sheet)")
    if lv("monk"):                                               # MONK-01 (GM 2026-10-28; sim/monk.py)
        n = lv("monk")
        b["monk_level"] = n
        b["martial_arts"] = R["Monk"]["resources"]["martial_arts_die"][n - 1]
        b["focus_dc"] = 8 + mods["wis"] + pb
        if n >= 2:
            b["focus_points"] = R["Monk"]["resources"]["focus"][n - 1]
        for key in cr.WEAPON_KEYS + ("offhand",):                # Monk weapons: Simple melee, Martial melee Light
            w = b.get(key)
            kind = _weapon(w["name"]) if w else None
            if w and w.get("reach", 5) <= 10 and (w["name"] == "Unarmed Strike" or (kind and kind["kind"] == "melee" and (
                    kind["category"] == "simple" or kind.get("light")))):
                w["monk"] = True
        if (b.get("ranged") or {}).get("name") == "Unarmed Strike":   # the Unarmed Strike gets its own place
            b["unarmed"] = b.pop("ranged")
        elif (b.get("weapon") or {}).get("name") != "Unarmed Strike":
            ua = next((a for a in (d or {}).get("attacks") or [] if a["name"] == "Unarmed Strike"), None)
            if ua:
                b["unarmed"] = dict(weapon_of(ua), monk=True)
    if lv("warlock"):
        inv = set((d or {}).get("invocations") or [x[len("Eldritch Invocation: "):] for x in feature_names if x.startswith("Eldritch Invocation: ")]
                  + [x for x in feature_names if x in INVOCATIONS])
        if "Agonizing Blast" in inv:
            b["agonizing"] = True
        if "Repelling Blast" in inv:
            b["repelling_blast"] = True
        if lv("warlock") >= 3:
            b["dark_ones_blessing"] = True
    if lv("wizard", 0) >= 6:
        b["sculpt_spells"] = True
    # GM 2026-10-26: the class and subclass features the simulator reads by flag (FEATURE_FLAGS)
    have = {re.sub(r"^Eldritch Invocation: ", "", f) for f in feature_names} | set(feats_raw)
    res_n = {str(r[0]): r[1] for r in ((d or {}).get("resources") or []) if isinstance(r, (list, tuple)) and len(r) == 2}
    for fname, flag in FEATURE_FLAGS.items():
        if fname in have:
            b[flag] = True
    if b.get("indomitable"):
        b["indomitable"] = res_n.get("Indomitable") if isinstance(res_n.get("Indomitable"), int) else \
            R["Fighter"]["resources"]["indomitable"][max(1, lv("fighter") or 9) - 1]
    if b.get("cunning_strike"):                                   # its saving throw DC: 8 + Dexterity + Proficiency Bonus
        b["cunning_strike"] = 8 + mods["dex"] + pb
    if b.get("own_luck"):                                         # uses: the Charisma modifier (at least 1)
        b["own_luck"] = max(1, mods["cha"])
    if b.get("aura_ft"):                                          # Aura Expansion (Paladin 18): 30 ft
        b["aura_ft"] = 30
    if b.get("improved_brutal_strike"):                           # Barbarian 17: 2d10 and two effects
        b["improved_brutal_strike"] = 2 if (lv("barbarian") or 0) >= 17 else 1
    if "Great Weapon Fighting" in feats_raw and not any(str(x).startswith("Shield") for x in s.get("equipment") or []):
        b["gwf"] = True                                          # play-test 2026-11-02: it needs both hands on the weapon
    epic_boons.build(b, abil, s.get("boon_abilities"))           # EPIC-BOONS-01: Overwhelming Strike's score, Truesight
    species = cr.norm(s.get("species"))
    if "elf" in species.split() or "drow" in species:
        b["fey_ancestry"] = True
    if "dragonborn" in species:
        anc = s.get("lineage") or next((w for w in species.split() if w.title() in cr.rules()["species"]["Dragonborn"]["lineages"]), None)
        dtype = cr.rules()["species"]["Dragonborn"]["lineages"].get((anc or "").title())
        if dtype:
            b["breath"], b["breath_dc"] = pb, 8 + mods["con"] + pb
            b["breath_dice"], b["breath_type"] = "%dd10" % (1 + (level >= 5) + (level >= 11) + (level >= 17)), dtype
        else:
            gm.append("Breath Weapon (the ancestry is not on the sheet)")

    # spells
    spells = s.get("spells") or []
    spell_names = [x if isinstance(x, str) else (x or {}).get("name", "") for x in spells]
    casting = (d or {}).get("casting") or []
    if d:
        slots = list(d.get("slots") or [])
        pact = d.get("pact")
        if pact:
            while len(slots) < pact["level"]:
                slots.append(0)
            slots[pact["level"] - 1] += pact["slots"]
        if slots:
            b["slots"] = slots
        if casting:
            best = max(casting, key=lambda c: c["attack"])
            b["spell_atk"], b["spell_mod"], b["spell_dc"] = best["attack"], mods[best["ability"]], best["dc"]
    else:
        caster = next((c for c in classes if R.get(c["name"].title(), {}).get("caster", "none") != "none"), None)
        if caster and spell_names:
            ab = R[caster["name"].title()]["ability"]
            b["spell_atk"], b["spell_mod"], b["spell_dc"] = pb + mods[ab], mods[ab], 8 + pb + mods[ab]
            # GM 2026-10-28 ("and no spell slots"): an imported sheet's slots from its classes and levels (SRD 5.2.1
            # Multiclass Spellcaster table; Pact Magic added at its own level), as a built sheet's
            counts = {c["name"].title(): int(c.get("level") or 0) for c in classes
                      if R.get(c["name"].title(), {}).get("caster", "none") != "none" and int(c.get("level") or 0) > 0}
            slots, pact, _ = spell_slots(counts)
            slots = list(slots)
            if pact:
                while len(slots) < pact["level"]:
                    slots.append(0)
                slots[pact["level"] - 1] += pact["slots"]
            if any(slots):
                b["slots"] = slots
            else:
                gm.append("Spell slots (an imported sheet: the GM sets them)")
    for nm in spell_names:
        flag = SIM_SPELL_FLAGS.get(nm) or SIM_SPELL_FLAGS.get(next((k2 for k2 in SIM_SPELL_FLAGS if cr.norm(k2) == cr.norm(nm)), ""))
        if flag:
            b[flag] = True
        elif nm and not any(cr.norm(nm) == cr.norm(x) for x in SIM_BY_CLASS.get(b["class"], ())) and \
                not any((b.get(k) or {}).get("name") == nm for k in cr.WEAPON_KEYS):
            gm.append(nm + " (spell)")
    if "sacred flame" in [cr.norm(x) for x in spell_names] and lv("cleric"):
        b["sacred_flame"] = "%dd8" % (1 + (level >= 5) + (level >= 11) + (level >= 17))

    # what the simulator can't play: the GM rules it
    subclasses = {c["subclass"]["name"] for c in cr.rules()["classes"].values()}
    for f in feature_names:
        if f in subclasses:
            continue
        bare_f = re.sub(r"^(Eldritch Invocation|Metamagic|Lineage|Ancestry|Divine Order|Primal Order): ", "", f)
        if bare_f in NOT_AT_THE_TABLE:                               # play-test 2026-11-02: the simulator plays these, a seat has no control
            gm.append(bare_f)
            continue
        if f and f not in SHEET_HEADINGS and bare_f not in SIM_FEATURES and f not in SIM_FEATURES and cr.bare(f) not in {cr.norm(x) for x in SIM_FEATURES} \
                and bare_f not in ("Agonizing Blast", "Repelling Blast") and not f.startswith(("Lineage:", "Ancestry:")):
            gm.append(f)
    for f in feats_raw:
        base_f = re.sub(r"\s*\(.*\)$", "", f)
        if base_f not in SIM_FEATS and base_f not in epic_boons.PLAYED:   # EPIC-BOONS-01: the Epic Boons play
            gm.append(f if base_f.startswith("Boon of") else f + " (feat)")
    if b["class"] not in ("fighter", "barbarian", "paladin", "warlock", "rogue", "cleric", "wizard", "bard", "sorcerer", "monk"):
        gm.append("%s tactics: in simulated turns it fights with its attacks (the players choose in Play live)" % main_cls)
    if len(classes) > 1:
        gm.append("Multiclass: the simulator plays it as a %s %d with all its features listed here" % (main_cls, level))
    seen, out = set(), []
    for g in gm:
        if g not in seen:
            seen.add(g); out.append(g)
    # GM 2026-10-24 ("they will need full access"): every spell and every feature the engine does not play, for Play
    # live's "Ask the GM" (sim/live_asks.py); a feature's uses from the sheet's resources
    # GM 2026-10-26: "free": the uses a rest gives of a spell cast without a slot (Mystic Arcanum, Magic Initiate,
    # Signature Spells), for Ask the GM
    b["spell_list"] = [dict({"name": x.get("name"), "level": int(x.get("level") or 0), "always": bool(x.get("always"))},
                            **({"free": 1} if "without a slot" in str(x.get("note") or "") and "once a" in str(x.get("note") or "")
                               and int(x.get("level") or 0) >= 1 else {}),
                            **({"arcanum": True} if x.get("arcanum") else {}),   # SPELLS-4-9
                            **({"mastery": True} if str(x.get("note") or "").startswith("Spell Mastery") else {}))   # CASTER-HIGH
                       for x in spells if isinstance(x, dict) and x.get("name")] or \
        [{"name": x, "level": 0, "always": False} for x in spell_names if x]
    for x in b["spell_list"]:                                        # SPELLS-4-9: a use of each Mystic Arcanum
        if x.get("arcanum"):
            b["arcanum_%d" % x["level"]] = 1
    uses = {str(r[0]): r[1] for r in ((d or {}).get("resources") or []) if isinstance(r, (list, tuple)) and len(r) == 2
            and isinstance(r[1], int)}
    if isinstance((d or {}).get("initiative"), int):                 # play-test 2026-11-02: Alert, which a fight's roll left out
        b["init_bonus"] = d["initiative"]
    b["feature_list"] = [dict({"name": g}, **({"uses": uses[g]} if g in uses else {})) for g in out
                         if not g.endswith((" (spell)", " (feat)", " (a saving-throw cantrip)")) and "tactics:" not in g
                         and not g.startswith("Multiclass")]
    return {"build": b, "gm_rules": out, "problems": problems}
