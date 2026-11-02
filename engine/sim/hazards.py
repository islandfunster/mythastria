"""HAZARDS-01 (GM 2026-10-26, the Documents goal "Environment, contagions, fear and travel"): SRD 5.2.1 environmental
effects, magical contagions, fear and mental stress, Exhaustion carried between fights and the travel pace's effects.

Two halves, one set of rules:
- The adventure day (sim/rests.py's day, POST /api/adventures/day): hours pass (Pass time, rests, travel on the region
  map) and each hour of exposure to Extreme Cold, Extreme Heat or swimming in Deep Water asks for its save; a day's end
  checks food and water; dawn and each Long Rest's end fight the contagions; incubation ends after 1d4 days; Extended
  Travel past 8 hours asks for its save; mental stress leaves its short- and long-term effects.
- A fight (Sim.hazards; the GM's Hazards tool in Play live, POST /api/live/hazards, or a map's "hazards"): Slippery Ice,
  Thin Ice and Frigid Water on squares; Strong Wind, a sandstorm and Heavy Precipitation over the map; fear (Frightened
  by a source, a Wisdom save each turn's end) and mental stress (Psychic damage) from the GM; Cackle Fever's laughter
  and its spreading; a creature that carries Sewer Plague infects with its wounds. Exhaustion gained here is kept
  (sim/environment.py add_exhaustion) and written back to the day with everything else when the fight ends.

SRD 5.2.1 text (the rules cache, srd521-player): Gameplay Toolbox "Environmental Effects" (Deep Water, Extreme Cold,
Extreme Heat, Frigid Water, Heavy Precipitation, High Altitude, Slippery Ice, Strong Wind, Thin Ice), "Curses and Magical
Contagions" (Cackle Fever, Sewer Plague, Sight Rot), "Fear and Mental Stress" (Fear Effects, Mental Stress Effects,
Prolonged Effects), "Travel Pace" (Travel Terrain's Maximum Pace, Good Roads, Slower Travelers, Extended Travel); Rules
Glossary "Exhaustion", "Dehydration", "Malnutrition"; Playing the Game "Travel Pace" (each pace's effect).
Readings the SRD leaves to the GM, kept as settings here and said on the page (confirmed by the GM 2026-10-27): dawn is 06:00; a contagion is fought
(dawn saves, Long Rest saves) once its effects have begun; a creature's weight on Thin Ice is the GM's estimate by size.
"""
import math, queue, re

SRD = "SRD 5.2.1"
DAWN_HOUR = 6
ROUNDS_PER_MINUTE = 10
YEAR_HOURS = 365 * 24
ABILITY = {"str": "Strength", "dex": "Dexterity", "con": "Constitution", "int": "Intelligence", "wis": "Wisdom",
           "cha": "Charisma"}


class HazardError(ValueError):
    pass


# ------------------------------------------------------------------ the SRD's environmental effects
# where: "hour" (the adventure day, each hour of exposure), "travel" (the region map's travel), "fight" (a map in Play live)
WEATHER = {
    "extreme_cold": {"name": "Extreme Cold", "where": "hour",
                     "text": "0 °F or lower: a DC 10 Constitution save at the end of each hour or 1 Exhaustion level. "
                             "Resistance or Immunity to Cold damage: automatic success."},
    "extreme_heat": {"name": "Extreme Heat", "where": "hour",
                     "text": "100 °F or higher, without drinkable water: a Constitution save at the end of each hour or 1 "
                             "Exhaustion level; DC 5 the first hour, +1 each hour after. Medium or Heavy armor: "
                             "Disadvantage. Resistance or Immunity to Fire damage: automatic success."},
    "deep_water": {"name": "Swimming in deep water", "where": "hour",
                   "text": "More than 100 feet deep: after each hour of swimming, a creature without a Swim Speed makes a "
                           "DC 10 Constitution save or gains 1 Exhaustion level."},
    "high_altitude": {"name": "High Altitude", "where": "travel",
                      "text": "10,000 feet or higher: each hour of travel counts as 2 hours toward how long the party can "
                              "travel (8 hours a day before Extended Travel)."},
    "strong_wind": {"name": "Strong Wind", "where": "fight",
                    "text": "Disadvantage on ranged weapon attack rolls; open flames go out and fog disperses; a flying "
                            "creature must land at the end of its turn or fall."},
    "sandstorm": {"name": "Sandstorm (strong wind in a desert)", "where": "fight",
                  "text": "Strong Wind's effects, and Disadvantage on Wisdom (Perception) checks."},
    "heavy_precipitation": {"name": "Heavy rain or snow", "where": "fight",
                            "text": "Everything is Lightly Obscured: Disadvantage on Wisdom (Perception) checks; heavy "
                                    "rain puts out open flames."},
}
HOURLY = ("extreme_cold", "extreme_heat", "deep_water")
FIGHT_WEATHER = ("strong_wind", "sandstorm", "heavy_precipitation")

ZONES = {
    "slippery_ice": {"name": "Slippery ice",
                     "text": "Difficult Terrain. Moving onto it for the first time on a turn, or starting a turn there: "
                             "DC 10 Dexterity save or Prone."},
    "thin_ice": {"name": "Thin ice",
                 "text": "Holds 3d10 x 10 pounds on each 10-foot square; more weight breaks it and everyone on it falls "
                         "through into frigid water."},
    "frigid_water": {"name": "Frigid water",
                     "text": "Minutes equal to the Constitution score without harm; then a DC 10 Constitution save each "
                             "minute (10 rounds) or 1 Exhaustion level. Resistance or Immunity to Cold, or a creature "
                             "adapted to ice-cold water: automatic success. Swimming costs 1 extra foot a foot."},
}
# GM's estimates (the SRD gives no creature weights): pounds by size, creature and gear, for Thin Ice
THIN_ICE_WEIGHTS = {"Tiny": 10, "Small": 60, "Medium": 180, "Large": 800, "Huge": 4000, "Gargantuan": 20000}

# ------------------------------------------------------------------ magical contagions (SRD 5.2.1 examples)
CONTAGIONS = {
    "cackle_fever": {
        "name": "Cackle Fever", "dc": 10, "fight_dc": 13, "rest_dc": 13, "incubation": 4,
        "how": "Cheaply made potions and elixirs; any Humanoid (not a gnome) that starts its turn within 10 feet of an "
               "infected creature: DC 10 Constitution save (a success: not from that creature for 24 hours).",
        "effects": "1d4 days after infection: 1 Exhaustion level that lasts until the contagion ends. While it has "
                   "Exhaustion, each time it takes damage other than Psychic: DC 13 Constitution save or 1d10 Psychic "
                   "damage and Incapacitated with laughter (the save again at the end of each of its turns; after 1 "
                   "minute it succeeds).",
        "fight": "At the end of each Long Rest: DC 13 Constitution save; after three successes it ends, and the "
                 "creature is immune for 1 year."},
    "sewer_plague": {
        "name": "Sewer Plague", "dc": 11, "dawn_dc": 11, "incubation": 4,
        "how": "Wounded by a creature that carries it (otyughs, rats), or contact with contaminated filth: DC 11 "
               "Constitution save.",
        "effects": "1d4 days after infection: 1 Exhaustion level. While it has any Exhaustion: half the Hit Points from "
                   "spending Hit Point Dice, and a Long Rest restores no lost Hit Points and removes no Exhaustion.",
        "fight": "Daily at dawn: DC 11 Constitution save; a failure adds 1 Exhaustion level, a success removes one; at "
                 "0 Exhaustion it ends."},
    "sight_rot": {
        "name": "Sight Rot", "dc": 15, "incubation": 0,
        "how": "Drinking tainted water, or skin contact with an infected creature: DC 15 Constitution save (a success: "
               "not from that creature for 24 hours). Beasts and Humanoids.",
        "effects": "Blinded until the contagion ends.",
        "fight": "Heal or Lesser Restoration ends it. Someone proficient with an Herbalism Kit makes one dose of "
                 "ointment in 1 hour: it holds the contagion off for 24 hours; 72 hours of it (three doses) end it."},
}

# ------------------------------------------------------------------ fear and mental stress (SRD 5.2.1)
SHORT_TERM = ("Frightened", "Incapacitated", "Stunned")
STRESS_KINDS = {
    "none": "No lasting effect.",
    "short": "Short-term: Frightened, Incapacitated or Stunned for 1d10 minutes (Lesser Restoration removes it).",
    "long": "Long-term: Disadvantage on some or all ability checks for 1d10 x 10 hours (Lesser Restoration removes it).",
    "indefinite": "Indefinite: a long-term effect that lasts until Greater Restoration removes it.",
}

# ------------------------------------------------------------------ travel pace (SRD 5.2.1)
PACES = {
    "fast": {"label": "Fast", "mph": 4, "per_day": 30,
             "effect": "Disadvantage on Wisdom (Perception or Survival) and Dexterity (Stealth) checks"},
    "normal": {"label": "Normal", "mph": 3, "per_day": 24, "effect": "Disadvantage on Dexterity (Stealth) checks"},
    "slow": {"label": "Slow", "mph": 2, "per_day": 18, "effect": "Advantage on Wisdom (Perception or Survival) checks"},
}
TRAVEL_HOURS = 8

# ------------------------------------------------------------------ who a character is, for these rules
ARMOR_NAMES = [("Half Plate", "medium"), ("Studded Leather", "light"), ("Chain Shirt", "medium"), ("Chain Mail", "heavy"),
               ("Ring Mail", "heavy"), ("Splint", "heavy"), ("Plate", "heavy"), ("Scale Mail", "medium"),
               ("Breastplate", "medium"), ("Hide", "medium"), ("Leather", "light"), ("Padded", "light")]
SPECIES = ("Dragonborn", "Dwarf", "Elf", "Gnome", "Goliath", "Halfling", "Human", "Orc", "Tiefling")
DRACONIC = {"Black": "acid", "Blue": "lightning", "Brass": "fire", "Bronze": "lightning", "Copper": "acid", "Gold": "fire",
            "Green": "poison", "Red": "fire", "Silver": "cold", "White": "cold"}
FIENDISH = {"Abyssal": "poison", "Chthonic": "necrotic", "Infernal": "fire"}


def _types(text):
    return sorted({w for w in re.findall(r"[a-z]+", str(text or "").lower().split(";")[0])
                   if w in ("acid", "bludgeoning", "cold", "fire", "force", "lightning", "necrotic", "piercing", "poison",
                            "psychic", "radiant", "slashing", "thunder")})


def traits_of(b):
    """Species, armor weight, damage Resistances and Immunities and a Swim Speed, from a build (a pregen's note, a saved
    character's sheet extras rest_traits, a combatant's stat block)."""
    t = b.get("rest_traits") if isinstance(b.get("rest_traits"), dict) else {}
    note = " ".join([str(b.get("note") or "")] + [str(x) for x in t.get("equipment") or []])
    species = t.get("species") or next((s for s in SPECIES if re.search(r"\b%s\b" % s, note)), "")
    armor = next((w for n, w in ARMOR_NAMES if re.search(r"\b%s\b" % n, note)), "")
    resist = set(_types(b.get("damageresistances")))
    m = re.search(r"\b(%s) Dragonborn\b" % "|".join(DRACONIC), note)
    if m:
        resist.add(DRACONIC[m.group(1)])
    m = re.search(r"\b(%s) Tiefling\b" % "|".join(FIENDISH), note)
    if m:
        resist.add(FIENDISH[m.group(1)])
    if species == "Dwarf":
        resist.add("poison")
    swim = bool(b.get("swim_ft")) or bool(re.search(r"Swim \d+", str(b.get("speed") or "")))
    return {"species": species, "armor": armor, "resist": sorted(resist), "immune": _types(b.get("damageimmunities")),
            "swim": swim, "type": str(b.get("type") or "humanoid").lower(),
            "tools": [str(x) for x in b.get("tools") or [] if isinstance(x, str)]}


def entry_fields(b):
    """The hazard state of a new adventure-day character (sim/rests.py entry_from_build)."""
    return {"saves": {a: int(b.get(a + "_save", (int((b.get("abilities") or {}).get(a, 10)) - 10) // 2) or 0)
                      for a in ABILITY},
            "con_score": int((b.get("abilities") or {}).get("con", 10) or 10),
            "speed": int(str(b.get("speed") or "30").split()[0] or 30), "traits": traits_of(b),
            "contagions": [], "immune_until": {}, "locks": {}, "stress": [],
            "rations": {"water": "full", "food": "full", "no_food_days": 0}}


KEEP = ("contagions", "immune_until", "locks", "stress", "rations")       # kept when the sheet changes (rests.ensure)


def fill(e):
    """An entry from a day file made before HAZARDS-01: the fields it lacks, with neutral values."""
    for k, v in entry_fields({}).items():
        e.setdefault(k, v)
    return e


# ------------------------------------------------------------------ dice and saves on the day
def _clock(hour):
    import rests
    return rests.clock_text(hour)


def _log(day, hour, text):
    import rests
    day["log"] = (day["log"] + [{"hour": hour, "when": _clock(hour), "text": text}])[-rests.MAX_LOG:]


def roll_dice(roll, expr):
    """'2d10+3' with roll(sides) -> int."""
    m = re.fullmatch(r"\s*(\d{1,2})d(4|6|8|10|12|20)\s*(?:([+-])\s*(\d{1,3}))?\s*", str(expr or ""))
    if not m:
        raise HazardError("Damage is dice like 2d10 or 1d6+2.")
    n, sides = int(m.group(1)), int(m.group(2))
    if not 1 <= n <= 20:
        raise HazardError("1 to 20 dice.")
    total = sum(roll(sides) for _ in range(n))
    return total + (int(m.group(4)) * (1 if m.group(3) == "+" else -1) if m.group(4) else 0)


def day_save(e, ability, dc, roll, adv=False, dis=False, auto=""):
    """A save on the adventure day: d20 + the sheet's save bonus - 2 per Exhaustion level (SRD 5.2.1 Exhaustion).
    -> (success, the line in words)."""
    if auto:
        return True, "%s %s save DC %d: automatic success (%s)" % (e["name"], ABILITY[ability], dc, auto)
    d = roll(20)
    rolls = "d20 %d" % d
    if adv and not dis:
        d2 = roll(20); rolls = "d20 %d/%d (Advantage)" % (d, d2); d = max(d, d2)
    elif dis and not adv:
        d2 = roll(20); rolls = "d20 %d/%d (Disadvantage%s)" % (d, d2, ": " + dis if isinstance(dis, str) else ""); d = min(d, d2)
    bonus = int((e.get("saves") or {}).get(ability, 0)) - 2 * int(e.get("exhaustion", 0))
    ok = d + bonus >= dc
    return ok, "%s %s save DC %d: %s %+d = %d -> %s" % (e["name"], ABILITY[ability], dc, rolls, bonus, d + bonus,
                                                       "success" if ok else "failure")


# ------------------------------------------------------------------ Exhaustion on the day
def locked(e):
    return sum(int(v) for v in (e.get("locks") or {}).values())


def gain_exhaustion(day, e, n, why, hour, lock=None):
    """n Exhaustion levels (at most 6: death). lock: the source that keeps them from a Long Rest (Cackle Fever's level
    until it ends; dehydration and malnutrition until the creature eats or drinks its fill)."""
    if e["status"] == "dead" or n <= 0:
        return
    old = int(e["exhaustion"])
    e["exhaustion"] = min(6, old + n)
    if lock:
        e["locks"][lock] = e["locks"].get(lock, 0) + e["exhaustion"] - old
    text = "%s: Exhaustion %d -> %d (%s)" % (e["name"], old, e["exhaustion"], why)
    if e["exhaustion"] >= 6:
        e["status"], e["hp"] = "dead", 0
        text += ": Exhaustion level 6 is death"
    _log(day, hour, text + ".")


def lose_exhaustion(e, n=1):
    """Remove up to n levels, never the ones a source still holds."""
    e["exhaustion"] = max(min(int(e["exhaustion"]), locked(e)), int(e["exhaustion"]) - n)


def lift_lock(e, source, end_levels=False):
    n = int((e.get("locks") or {}).pop(source, 0))
    if end_levels and n:
        e["exhaustion"] = max(0, int(e["exhaustion"]) - n)
    return n


def effects_text(e):
    """Exhaustion's effects in words (SRD 5.2.1): -2 per level to D20 Tests, -5 ft per level of Speed; 6 is death."""
    n = int(e.get("exhaustion") or 0)
    if not n:
        return ""
    speed = int(e.get("speed") or 30)
    return "Exhaustion %d: D20 Tests -%d, Speed -%d ft (%d ft)%s" % (n, 2 * n, 5 * n, max(0, speed - 5 * n),
                                                                     "; level 6 is death" if n < 6 else ": dead")


# ------------------------------------------------------------------ contagions on the day
def _infection(e, key):
    return next((c for c in e.get("contagions") or [] if c["key"] == key), None)


def started(c, hour):
    return c["onset"] is not None and hour + 1e-9 >= c["onset"]


def restless(e, hour):
    """Sewer Plague's Weakness and Restlessness: an infected creature (its effects begun) with any Exhaustion."""
    c = _infection(e, "sewer_plague")
    return bool(c and started(c, hour) and int(e.get("exhaustion") or 0) > 0)


def blinded(e, hour):
    c = _infection(e, "sight_rot")
    return bool(c and not (c.get("suppressed_until") and hour < c["suppressed_until"]))


def susceptible(e, key):
    """-> the reason it can't catch it, or ''."""
    t = e.get("traits") or {}
    kind = t.get("type", "humanoid")
    if key == "cackle_fever" and (kind != "humanoid" or t.get("species") == "Gnome"):
        return "Cackle Fever affects Humanoids only, and gnomes are immune"
    if key == "sight_rot" and kind not in ("humanoid", "beast"):
        return "Sight Rot affects Beasts and Humanoids only"
    if key == "sewer_plague" and kind != "humanoid":
        return "Sewer Plague infects Humanoids"
    return ""


def infect(day, name, key, roll, save=True, why="", hour=None):
    """The GM gives a contagion to a character: with its save (expose) or without (infect). -> the line in words."""
    if key not in CONTAGIONS:
        raise HazardError("A contagion is one of %s." % ", ".join(c["name"] for c in CONTAGIONS.values()))
    e = day["party"].get(name)
    if not e:
        raise HazardError("%s is not in the party." % name)
    fill(e)
    spec, hour = CONTAGIONS[key], day["hour"] if hour is None else hour
    why = str(why or "").strip()[:120]
    if e["status"] == "dead":
        raise HazardError("%s is dead." % name)
    if _infection(e, key):
        raise HazardError("%s already has %s." % (name, spec["name"]))
    no = susceptible(e, key)
    if no or (e["immune_until"].get(key) or 0) > hour:
        text = "%s can't catch %s: %s." % (name, spec["name"], no or "immune until %s" % _clock(e["immune_until"][key]))
        _log(day, hour, text)
        return text
    if save:
        ok, line = day_save(e, "con", spec["dc"], roll)
        if ok:
            text = "%s is exposed to %s%s: %s; not infected." % (name, spec["name"], " (%s)" % why if why else "", line)
            _log(day, hour, text)
            return text
    days = roll(spec["incubation"]) if spec["incubation"] else 0
    c = {"key": key, "since": hour, "onset": hour + 24 * days, "successes": 0, "why": why}
    e["contagions"].append(c)
    text = "%s is infected with %s%s%s. %s" % (
        name, spec["name"], " (%s)" % why if why else "", (": " + line) if save else " (the GM)",
        "Its effects begin in %d day%s (%s)." % (days, "" if days == 1 else "s", _clock(c["onset"])) if days else
        "Blinded until the contagion ends.")
    _log(day, hour, text)
    if not days:
        _onset(day, e, c, hour)
    return text


def _onset(day, e, c, hour):
    if c.get("begun"):
        return
    c["begun"] = True
    if c["key"] == "cackle_fever":
        gain_exhaustion(day, e, 1, "Cackle Fever: the fever begins; this level lasts until the contagion ends", hour,
                        lock="cackle_fever")
    elif c["key"] == "sewer_plague":
        gain_exhaustion(day, e, 1, "Sewer Plague: the fatigue begins", hour)
    elif c["key"] == "sight_rot":
        _log(day, hour, "%s is Blinded by Sight Rot until the contagion ends." % e["name"])


def end_contagion(day, e, key, why, hour):
    c = _infection(e, key)
    if not c:
        raise HazardError("%s does not have %s." % (e["name"], CONTAGIONS[key]["name"]))
    e["contagions"].remove(c)
    if key == "cackle_fever":
        lift_lock(e, "cackle_fever", end_levels=True)
        e["immune_until"][key] = hour + YEAR_HOURS
    _log(day, hour, "%s's %s ends (%s)%s." % (e["name"], CONTAGIONS[key]["name"], why,
                                              "; immune to it for 1 year" if key == "cackle_fever" else ""))


def cure(day, name, key, how):
    """how: 'magic' (Heal or Lesser Restoration: Sight Rot), 'gm' (the GM ends it, a cure the SRD leaves to the GM)."""
    e = day["party"].get(name)
    if not e:
        raise HazardError("%s is not in the party." % name)
    fill(e)
    if key not in CONTAGIONS:
        raise HazardError("Name the contagion.")
    if how == "magic" and key != "sight_rot":
        raise HazardError("Heal and Lesser Restoration end Sight Rot; %s ends by its own rule (or the GM's ruling)."
                          % CONTAGIONS[key]["name"])
    if how not in ("magic", "gm"):
        raise HazardError("A cure is magic (Heal or Lesser Restoration) or the GM's.")
    end_contagion(day, e, key, "Heal or Lesser Restoration" if how == "magic" else "the GM ends it", day["hour"])


def ointment_needs(day, maker, patient, bag=None):
    """Sight Rot ointment (SRD 5.2.1): made by someone proficient with an Herbalism Kit, with the kit, in 1 hour."""
    import requirements as rq
    m, p = day["party"].get(maker), day["party"].get(patient)
    needs = [rq.need("the maker", m is not None, "%s is not in the party." % maker),
             rq.need("Sight Rot", bool(p and _infection(p, "sight_rot")), "%s does not have Sight Rot." % patient)]
    if m is not None:
        tools = (m.get("traits") or {}).get("tools") or []
        needs.append(rq.need("Herbalism Kit proficiency", "Herbalism Kit" in tools,
                             "%s is not proficient with an Herbalism Kit." % maker, rq.LINKS["characters"]))
        if bag is not None:
            needs.append(rq.in_bag(bag, "herbalism-kit", "Herbalism Kit"))
    needs.append(rq.need("no rest under way", not day.get("rest"), "A rest is under way: the ointment takes 1 hour of work."))
    return needs


def apply_ointment(day, maker, patient, hour):
    p = day["party"][patient]
    c = _infection(p, "sight_rot")
    c["suppressed_until"] = hour + 24
    _log(day, hour, "%s makes Sight Rot ointment (1 hour, Herbalism Kit) and applies it to %s's eyes: the contagion is held "
         "off for 24 hours (%d of 72 hours so far)." % (maker, patient, int(c.get("suppressed_hours", 0))))


# ------------------------------------------------------------------ time passing on the day
def environment(day):
    env = day.setdefault("environment", {})
    env.setdefault("weather", [])
    env.setdefault("shelter", False)
    env.setdefault("water", True)
    env.setdefault("exposure", 0.0)                         # hours toward the next hourly save
    env.setdefault("heat_hours", 0)                         # hours of Extreme Heat so far (its DC climbs)
    return env


def set_environment(day, weather=None, shelter=None, water=None):
    env = environment(day)
    if weather is not None:
        if not isinstance(weather, list) or any(w not in WEATHER for w in weather):
            raise HazardError("Weather is a list of %s." % ", ".join(sorted(WEATHER)))
        if "extreme_heat" in env["weather"] and "extreme_heat" not in weather:
            env["heat_hours"] = 0
        env["weather"] = sorted(set(weather))
    if shelter is not None:
        env["shelter"] = bool(shelter)
    if water is not None:
        env["water"] = bool(water)
    _log(day, day["hour"], "The environment: %s%s%s." % (
        ", ".join(WEATHER[w]["name"] for w in env["weather"]) or "nothing harsh",
        "; the party is sheltered" if env["shelter"] else "", "" if env["water"] else "; no drinkable water at hand"))
    return env


def _hourly(day, names, roll, hour, weather, water):
    """The saves at the end of one hour of exposure."""
    env = environment(day)
    for key in weather:
        if key not in HOURLY:
            continue
        if key == "extreme_heat":
            if water:
                continue
            env["heat_hours"] += 1
        for n in names:
            e = day["party"].get(n)
            if not e or e["status"] == "dead":
                continue
            fill(e)
            t = e["traits"]
            if key == "deep_water" and t.get("swim"):
                continue
            auto = ""
            if key == "extreme_cold" and ("cold" in t["resist"] or "cold" in t["immune"]):
                auto = "Resistance or Immunity to Cold"
            if key == "extreme_heat" and ("fire" in t["resist"] or "fire" in t["immune"]):
                auto = "Resistance or Immunity to Fire"
            dc = 5 + env["heat_hours"] - 1 if key == "extreme_heat" else 10
            dis = "Medium or Heavy armor" if key == "extreme_heat" and t.get("armor") in ("medium", "heavy") else False
            ok, line = day_save(e, "con", dc, roll, dis=dis, auto=auto)
            if ok:
                _log(day, hour, "%s, an hour: %s." % (WEATHER[key]["name"], line))
            else:
                gain_exhaustion(day, e, 1, "%s, an hour: %s" % (WEATHER[key]["name"], line), hour)


def _day_end(day, names, roll, hour):
    """The end of a day (midnight): water and food (SRD 5.2.1 Dehydration, Malnutrition)."""
    for n in names:
        e = day["party"].get(n)
        if not e or e["status"] == "dead":
            continue
        fill(e)
        r = e["rations"]
        if r["water"] == "short":
            gain_exhaustion(day, e, 1, "Dehydration: less than half the water it needs today", hour, lock="dehydration")
        elif e["locks"].get("dehydration"):
            lift_lock(e, "dehydration")
            _log(day, hour, "%s drank its fill today: its Exhaustion from dehydration can be removed again." % n)
        if r["food"] == "none":
            r["no_food_days"] = int(r.get("no_food_days", 0)) + 1
            if r["no_food_days"] >= 5:
                gain_exhaustion(day, e, 1, "Malnutrition: day %d without food" % r["no_food_days"], hour, lock="malnutrition")
            else:
                _log(day, hour, "%s has eaten nothing for %d day%s (at 5 days: Exhaustion each day)." % (
                    n, r["no_food_days"], "" if r["no_food_days"] == 1 else "s"))
        else:
            r["no_food_days"] = 0
            if r["food"] == "short":
                ok, line = day_save(e, "con", 10, roll)
                if ok:
                    _log(day, hour, "Malnutrition (less than half its food today): %s." % line)
                else:
                    gain_exhaustion(day, e, 1, "Malnutrition, less than half its food today: %s" % line, hour,
                                    lock="malnutrition")
            elif e["locks"].get("malnutrition"):
                lift_lock(e, "malnutrition")
                _log(day, hour, "%s ate its fill today: its Exhaustion from malnutrition can be removed again." % n)


def _dawn(day, names, roll, hour):
    """Daily at dawn: Sewer Plague's save."""
    for n in names:
        e = day["party"].get(n)
        c = e and _infection(e, "sewer_plague")
        if not c or e["status"] == "dead" or not started(c, hour):
            continue
        ok, line = day_save(e, "con", CONTAGIONS["sewer_plague"]["dawn_dc"], roll)
        if ok:
            lose_exhaustion(e, 1)
            _log(day, hour, "Dawn: %s fights Sewer Plague: %s; Exhaustion %d." % (n, line, e["exhaustion"]))
            if e["exhaustion"] == 0:
                end_contagion(day, e, "sewer_plague", "its Exhaustion is gone", hour)
        else:
            gain_exhaustion(day, e, 1, "Sewer Plague at dawn: %s" % line, hour)


def advance(day, names, frm, to, roll, travel=False, weather=None, water=None):
    """Hours pass on the day from frm to to: each event in order (an hour of exposure ends, a contagion's effects begin,
    dawn, a day's end, a suppression or an effect runs out). The clock itself is the caller's (sim/rests.py)."""
    if to <= frm + 1e-9:
        return
    env = environment(day)
    weather = env["weather"] if weather is None else weather
    water = env["water"] if water is None else water
    exposed = (travel or not env["shelter"]) and any(w in HOURLY for w in weather)
    for e in day["party"].values():
        fill(e)
    import rests
    rests.settle_dying(day, names, roll, frm)                   # RESTS-02: the dying settle within the first minute
    events = []
    if exposed:
        t = frm + (1 - env["exposure"])
        while t <= to + 1e-9:
            events.append((t, 0, "hour", None))
            t += 1
        env["exposure"] = round((env["exposure"] + (to - frm)) % 1, 6)
    else:
        env["exposure"], env["heat_hours"] = 0.0, 0                # out of it: the next exposure starts afresh
    first_day = int(frm // 24)
    for d in range(first_day, int(to // 24) + 2):
        if frm < d * 24 + DAWN_HOUR <= to:
            events.append((d * 24 + DAWN_HOUR, 2, "dawn", None))
        if d and frm < d * 24 <= to:
            events.append((d * 24, 3, "midnight", None))
    for n in names:
        e = day["party"].get(n)
        for c in (e or {}).get("contagions") or []:
            if not c.get("begun") and frm < c["onset"] <= to:
                events.append((c["onset"], 1, "onset", (n, c["key"])))
        if e and e["status"] == "stable" and e.get("wake_at") is not None and e["wake_at"] <= to + 1e-9:
            events.append((max(frm, e["wake_at"]), 1, "wake", n))           # RESTS-02: 1 HP after 1d4 hours
    for t, _, kind, what in sorted(events, key=lambda ev: (ev[0], ev[1])):
        if kind == "hour":
            _hourly(day, names, roll, t, weather, water)
        elif kind == "onset":
            e = day["party"][what[0]]
            c = _infection(e, what[1])
            if c:
                _onset(day, e, c, t)
        elif kind == "wake":
            if day["party"][what]["status"] == "stable":
                rests.wake(day, day["party"][what], t)
        elif kind == "dawn":
            _dawn(day, names, roll, t)
        elif kind == "midnight":
            _day_end(day, names, roll, t)
    for n in names:                                            # what runs out by the new hour
        e = day["party"].get(n)
        if not e:
            continue
        c = _infection(e, "sight_rot")
        if c and c.get("suppressed_until"):
            held = max(0.0, min(to, c["suppressed_until"]) - max(frm, c["suppressed_until"] - 24))
            c["suppressed_hours"] = round(c.get("suppressed_hours", 0) + held, 6)
            if c["suppressed_hours"] >= 72 - 1e-6:
                end_contagion(day, e, "sight_rot", "72 hours held off by ointment", min(to, c["suppressed_until"]))
            elif to >= c["suppressed_until"]:
                c.pop("suppressed_until")
                _log(day, to, "%s's Sight Rot ointment wears off: Blinded again (%d of 72 hours held off)." % (
                    n, int(c["suppressed_hours"])))
        for s in list(e["stress"]):
            if s.get("until") is not None and to >= s["until"]:
                e["stress"].remove(s)
                _log(day, s["until"], "%s: %s ends." % (n, stress_text(s)))
        for key, until in list(e["immune_until"].items()):
            if to >= until:
                e["immune_until"].pop(key)


def after_long_rest(day, names, roll, hour):
    """The end of a Long Rest: Cackle Fever's save (sim/rests.py finish_rest has already given the rest's benefits)."""
    for n in names:
        e = day["party"].get(n)
        c = e and _infection(e, "cackle_fever")
        if not c or e["status"] == "dead" or not started(c, hour):
            continue
        ok, line = day_save(e, "con", CONTAGIONS["cackle_fever"]["rest_dc"], roll)
        if ok:
            c["successes"] += 1
        _log(day, hour, "After the Long Rest %s fights Cackle Fever: %s (%d of 3 successes)." % (n, line, c["successes"]))
        if c["successes"] >= 3:
            end_contagion(day, e, "cackle_fever", "three successful saves", hour)


# ------------------------------------------------------------------ mental stress on the day
def stress_text(s):
    if s["kind"] == "short":
        return "%s (short-term mental stress)" % s["condition"]
    what = "all ability checks" if s.get("ability") in (None, "", "all") else "%s checks" % ABILITY[s["ability"]]
    return "Disadvantage on %s (%s mental stress%s)" % (what, "long-term" if s["kind"] == "long" else "indefinite",
                                                       ": until Greater Restoration" if s["kind"] == "indefinite" else "")


def check_stress(save, dc, dice, effect, condition, ability):
    if save not in ("wis", "int", "cha"):
        raise HazardError("Mental stress is resisted with a Wisdom, Intelligence or Charisma save.")
    if not isinstance(dc, int) or isinstance(dc, bool) or not 5 <= dc <= 30:
        raise HazardError("The DC is 5 to 30.")
    if dice:
        roll_dice(lambda s: 1, dice)                             # the form only
    if effect not in STRESS_KINDS:
        raise HazardError("The lasting effect is none, short, long or indefinite.")
    if effect == "short" and condition not in SHORT_TERM:
        raise HazardError("A short-term effect is Frightened, Incapacitated or Stunned.")
    if effect in ("long", "indefinite") and ability not in (None, "", "all") and ability not in ABILITY:
        raise HazardError("A long-term effect names an ability (or all of them).")


def mental_stress(day, names, roll, save="wis", dc=10, dice="", half=False, effect="none", condition=None, ability=None,
                  why=""):
    """The GM subjects characters to mental stress (SRD 5.2.1): a save; Psychic damage on a failure (half on a success
    when the GM says so); the lasting effect on a failure."""
    check_stress(save, dc, dice, effect, condition, ability)
    why, hour, lines = str(why or "mental stress").strip()[:120], day["hour"], []
    for n in names:
        e = day["party"].get(n)
        if not e or e["status"] == "dead":
            continue
        fill(e)
        ok, line = day_save(e, save, dc, roll)
        dmg = roll_dice(roll, dice) if dice else 0
        dealt = dmg // 2 if ok and half else 0 if ok else dmg
        text = "%s (%s): %s" % (n, why, line)
        got = {}
        if dealt:                                                # RESTS-02: damage on the day interrupts a rest
            import rests
            text += "; " + rests.hurt(day, n, dealt, "psychic", hour=hour, interrupt=False, out=got)
        if not ok and effect != "none":
            s = {"kind": effect, "why": why, "since": hour}
            if effect == "short":
                s.update(condition=condition, until=hour + roll(10) / 60)
            else:
                s.update(ability=ability or "all", until=hour + 10 * roll(10) if effect == "long" else None)
            e["stress"].append(s)
            text += "; %s%s" % (stress_text(s), " until %s" % _clock(s["until"]) if s["until"] is not None else "")
        _log(day, hour, text + ".")
        if got.get("taken") and day.get("rest"):
            import rests
            rests.interrupt_one(day, n, "%s: Psychic damage" % why)
        lines.append(text)
    return lines


def end_stress(day, name, n, how):
    e = day["party"].get(name)
    if not e or not isinstance(n, int) or not 0 <= n < len(e.get("stress") or []):
        raise HazardError("Name the character and the effect.")
    s = e["stress"][n]
    if s["kind"] == "indefinite" and how != "greater":
        raise HazardError("An indefinite effect ends only with Greater Restoration.")
    e["stress"].pop(n)
    _log(day, day["hour"], "%s: %s ends (%s)." % (name, stress_text(s), {"lesser": "Lesser Restoration",
                                                                        "greater": "Greater Restoration"}.get(how, "the GM")))


# ------------------------------------------------------------------ rations
def set_rations(day, name, water=None, food=None):
    e = day["party"].get(name)
    if not e:
        raise HazardError("%s is not in the party." % name)
    fill(e)
    if water is not None:
        if water not in ("full", "short"):
            raise HazardError("Water is full or short (less than half).")
        e["rations"]["water"] = water
    if food is not None:
        if food not in ("full", "short", "none"):
            raise HazardError("Food is full, short (less than half) or none.")
        e["rations"]["food"] = food
    _log(day, day["hour"], "%s: water %s, food %s (checked at the day's end)." % (
        name, {"full": "enough", "short": "less than half"}[e["rations"]["water"]],
        {"full": "enough", "short": "less than half", "none": "nothing"}[e["rations"]["food"]]))


# ------------------------------------------------------------------ travel on the region map
def pace_rule(day, names):
    """Slower Travelers (SRD 5.2.1): the group must move at a Slow pace if any member's Speed is reduced to half or less."""
    for n in names:
        e = day["party"].get(n)
        if not e or e["status"] == "dead":
            continue
        fill(e)
        now = max(0, e["speed"] - 5 * int(e["exhaustion"]))
        if now * 2 <= e["speed"]:
            return {"forced": "slow", "why": "%s's Speed is %d ft (half or less of %d ft, Exhaustion %d): the group must "
                                             "move at a Slow pace." % (n, now, e["speed"], e["exhaustion"])}
    return {"forced": None, "why": ""}


def travel(day, names, roll, hours, pace, today_before, today_after, weather=None, water=None, fast=False, where=""):
    """A leg of travel on the region map: the clock runs `hours`; every hour exposed to the region's weather asks for its
    save; past 8 hours of travel today (today_before -> today_after, High Altitude counted double by the page), each
    character makes the Extended Travel save at the end of each extra hour. -> lines in words."""
    if pace not in PACES:
        raise HazardError("A pace is fast, normal or slow.")
    for v in (hours, today_before, today_after):
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not 0 <= v <= 24 * 30:
            raise HazardError("Travel hours are numbers.")
    if day.get("rest"):
        raise HazardError("A rest is under way: finish or stop it before travelling.")
    rule = pace_rule(day, names)
    if rule["forced"] and pace != "slow" and not fast:
        raise HazardError(rule["why"])
    frm = day["hour"]
    env = environment(day)
    if weather is not None and sorted(set(weather)) != env["weather"]:
        set_environment(day, weather)                            # the party is in the region's weather now
    if water is not None and water != env["water"]:
        env["water"] = bool(water)
    _log(day, frm, "The party travels%s at a %s pace for %g hour%s%s: %s." % (
        " (fast travel)" if fast else "", PACES[pace]["label"], round(hours, 2), "" if hours == 1 else "s",
        " to %s" % str(where)[:80] if where else "", PACES[pace]["effect"]))
    # fast travel: the nights on the way are camps (the environment's shelter says whether they are exposed)
    advance(day, names, frm, frm + hours, roll, travel=not fast)
    for k in range(int(math.floor(max(TRAVEL_HOURS, today_before) - TRAVEL_HOURS + 1e-9)) + 1,
                   int(math.floor(today_after - TRAVEL_HOURS + 1e-9)) + 1):
        for n in names:
            e = day["party"].get(n)
            if not e or e["status"] == "dead":
                continue
            ok, line = day_save(e, "con", 10 + k, roll)
            if ok:
                _log(day, frm + hours, "Extended Travel, hour %d past 8: %s." % (k, line))
            else:
                gain_exhaustion(day, e, 1, "Extended Travel, hour %d past 8: %s" % (k, line), frm + hours)
    day["hour"] = frm + hours
    day["travel"] = {"pace": pace, "effect": PACES[pace]["effect"], "at": day["hour"]}


# ------------------------------------------------------------------ the day page's view
def entry_view(e, hour):
    fill(e)
    cont = []
    for c in e["contagions"]:
        spec = CONTAGIONS[c["key"]]
        row = {"key": c["key"], "name": spec["name"], "since": _clock(c["since"]), "begun": started(c, hour)}
        if not started(c, hour):
            row["state"] = "incubating: its effects begin %s" % _clock(c["onset"])
        elif c["key"] == "cackle_fever":
            row["state"] = "fever (1 Exhaustion level until it ends); Long Rest saves %d of 3" % c["successes"]
        elif c["key"] == "sewer_plague":
            row["state"] = "a DC 11 Constitution save each dawn" + (
                "; half HP from Hit Point Dice, no HP or Exhaustion back from a Long Rest" if restless(e, hour) else "")
        else:
            held = c.get("suppressed_until")
            row["state"] = ("held off by ointment until %s" % _clock(held) if held and hour < held else "Blinded") + \
                " (%d of 72 hours of ointment)" % int(c.get("suppressed_hours", 0))
        row["text"] = spec["effects"]
        cont.append(row)
    return {"effects": effects_text(e), "locked": locked(e), "locks": dict(e["locks"]), "contagions": cont,
            "stress": [dict(s, text=stress_text(s), until_text=_clock(s["until"]) if s.get("until") is not None else None)
                       for s in e["stress"]],
            "rations": dict(e["rations"]), "speed": e["speed"], "speed_now": max(0, e["speed"] - 5 * int(e["exhaustion"])),
            "traits": e["traits"], "blinded": blinded(e, hour)}


def catalog():
    return {"weather": {k: dict(v) for k, v in WEATHER.items()}, "zones": {k: dict(v) for k, v in ZONES.items()},
            "contagions": {k: dict(v) for k, v in CONTAGIONS.items()}, "paces": PACES, "stress": STRESS_KINDS,
            "short_term": list(SHORT_TERM), "thin_ice_weights": THIN_ICE_WEIGHTS, "dawn_hour": DAWN_HOUR}


# ====================================================================== a fight (Sim.hazards)
class Hazards:
    """The hazards of one fight. Inert without weather, zones, contagions or carriers."""

    def __init__(self, sim):
        self.sim = sim
        spec = sim.sc.get("hazards") or {}
        self.weather = {w for w in spec.get("weather") or [] if w in FIGHT_WEATHER}
        self.zones, self.n, self.problems = [], 0, []
        self.infected = {}       # ctid -> {key: {"begun": bool}} (from the day, or caught in this fight)
        self.carriers = {}       # ctid -> {keys}: a creature the GM says carries a contagion
        self.no_catch = set()    # (ctid, source, key): saved against that creature (24 hours)
        self.laughing = {}       # ctid -> rounds laughed (Cackle Fever: at most 1 minute)
        self.iced = {}           # ctid -> the turn it last saved against slippery ice
        self.immersed = {}       # ctid -> rounds in frigid water
        self.timed = {}          # (ctid, condition) -> the round it ends (short-term mental stress)
        self.caught, self.stress_new = [], []
        self.gmq = queue.Queue()  # the GM's commands, run on the fight's thread (drain)
        for z in spec.get("zones") or []:
            try:
                self.place(z, quiet=True)
            except HazardError as e:
                self.problems.append("Hazard %s left off the map: %s" % (z.get("kind"), e))

    # ------------------------------------------------------------ the map
    @property
    def g(self):
        return self.sim.sc.get("grid", 50)

    def say(self, text, kind="dice"):
        self.sim.say(kind, text)

    def serial(self):
        return int(self.sim.S.turnSerial or 0)

    def round(self):
        return int(self.sim.S.round() or 0)

    def square(self, i):
        x, y = self.sim.env.pos(i)
        return int(round(x)), int(round(y))

    def footprint(self, i, at=None):
        x, y = at or self.sim.env.pos(i)
        span = max(1, int(round(float(self.sim.by_id(i).get("space") or 5) / self.sim.sc.get("units", 5))))
        x0, y0 = int(round(x - (span - 1) / 2)), int(round(y - (span - 1) / 2))
        return {(x0 + a, y0 + b) for a in range(span) for b in range(span)}

    def zone_at(self, cell, kind):
        return next((z for z in self.zones if z["kind"] == kind and tuple(cell) in z["cells"]), None)

    def in_kind(self, i, kind):
        return any(self.zone_at(c, kind) for c in self.footprint(i))

    def place(self, spec, quiet=False):
        kind = str(spec.get("kind") or "")
        if kind not in ZONES:
            raise HazardError("A hazard on the map is one of %s." % ", ".join(z["name"] for z in ZONES.values()))
        squares = spec.get("squares")
        if not isinstance(squares, list) or not 1 <= len(squares) <= 400:
            raise HazardError("A hazard covers 1 to 400 squares.")
        cells = set()
        for s in squares:
            if not (isinstance(s, (list, tuple)) and len(s) == 2 and all(isinstance(v, (int, float)) for v in s)):
                raise HazardError("A square is [x, y].")
            c = (int(round(s[0])), int(round(s[1])))
            traps = getattr(self.sim, "traps", None)
            if traps and not traps.enterable(*c):
                raise HazardError("Square %d, %d is a wall or off the map." % c)
            if any(c in z["cells"] for z in self.zones):
                raise HazardError("Square %d, %d already has a hazard." % c)
            cells.add(c)
        self.n += 1
        z = {"id": str(spec.get("id") or "hz-%d" % self.n), "kind": kind, "cells": cells, "name": ZONES[kind]["name"]}
        if kind == "thin_ice":
            w = spec.get("weights") if isinstance(spec.get("weights"), dict) else {}
            z["weights"] = {k: int(w.get(k, v)) if isinstance(w.get(k, v), int) and 0 < w.get(k, v) <= 100000 else v
                            for k, v in THIN_ICE_WEIGHTS.items()}
            z["tolerance"] = {}
            for c in cells:
                a = (c[0] // 2, c[1] // 2)                       # each 10-foot square: 3d10 x 10 pounds
                if a not in z["tolerance"]:
                    z["tolerance"][a] = 10 * sum(self.sim.rng.randint(1, 10) for _ in range(3))
        self.zones.append(z)
        if not quiet:
            self.say("%s on %d square%s" % (z["name"], len(cells), "" if len(cells) == 1 else "s"), "turn")
        return z

    def remove(self, zid):
        z = next((z for z in self.zones if z["id"] == zid), None)
        if not z:
            raise HazardError("No hazard %s on the map." % zid)
        self.zones.remove(z)

    def set_weather(self, weather):
        if not isinstance(weather, list) or any(w not in FIGHT_WEATHER for w in weather):
            raise HazardError("A fight's weather is a list of %s." % ", ".join(FIGHT_WEATHER))
        new = set(weather) - self.weather
        self.weather = set(weather)
        for w in sorted(new):
            self.say("%s: %s" % (WEATHER[w]["name"], WEATHER[w]["text"]), "turn")
        if self.windy():
            self.blow_fog()
        if self.windy() or "heavy_precipitation" in self.weather:
            self.douse()

    def windy(self):
        return bool(self.weather & {"strong_wind", "sandstorm"})

    def perception_dis(self):
        """Heavy Precipitation (Lightly Obscured) and a sandstorm: Disadvantage on Wisdom (Perception) checks."""
        return next((WEATHER[w]["name"] for w in ("heavy_precipitation", "sandstorm") if w in self.weather), "")

    def difficult_cells(self, i=None):
        """Squares that cost 1 extra foot a foot: slippery ice (Difficult Terrain), and frigid water for a creature
        without a Swim Speed (swimming)."""
        swim = i is not None and self.sim.env.swim_speed(i)
        return {c for z in self.zones if z["kind"] == "slippery_ice" or (z["kind"] == "frigid_water" and not swim)
                for c in z["cells"]}

    def blow_fog(self):
        """Strong Wind disperses fog (Fog Cloud: "A strong wind disperses it")."""
        env = self.sim.env
        fogs = [z for z in env.zones if z.get("spell") == "Fog Cloud"]
        for z in fogs:
            env.zones.remove(z)
        if fogs:
            self.say("The strong wind disperses the Fog Cloud", "turn")

    def douse(self):
        """Open flames go out: burning Oil on the ground (sim/traps.py)."""
        traps = getattr(self.sim, "traps", None)
        for t in (traps.traps if traps else []):
            if t.get("gear") and t.get("lit") is not None:
                t["lit"] = None
                self.say("The %s puts out the burning %s" % ("wind" if self.windy() else "rain", t["name"]), "turn")

    # ------------------------------------------------------------ who is affected
    def traits(self, i):
        return traits_of(self.sim.by_id(i))

    def resists(self, i, kind):
        t = self.traits(i)
        return kind in t["resist"] or kind in t["immune"]

    def creature(self, i):
        return next((c for c in self.sim.sc["combatants"] if c["id"] == i), None)

    def save(self, i, ability, dc, label):
        gm = self.sim.gm_rules
        if gm:                                                   # Danger Sense, Bless, Exhaustion, Paralyzed...
            return gm.roll_save(i, i, {"save": ability, "dc": dc}, label)[0]
        d = self.sim.rng.randint(1, 20)
        bonus = int(self.sim.by_id(i).get(ability + "_save", 0) or 0) + self.sim.env.d20_penalty(i)
        self.say("%s %s save against %s: d20 %d %+d = %d vs DC %d -> %s" % (
            self.sim.by_id(i)["name"], ABILITY[ability], label, d, bonus, d + bonus, dc, "success" if d + bonus >= dc else "failure"))
        return d + bonus >= dc

    def humanoid_pc(self, i, key):
        c = self.sim.by_id(i)
        if not c.get("pc") or self.sim.down(i):
            return False
        t = self.traits(i)
        return not (key == "cackle_fever" and t.get("species") == "Gnome")

    def infect(self, i, key, why):
        """Caught in this fight: its effects begin 1d4 days later (on the day); Sight Rot blinds now."""
        self.infected.setdefault(i, {})[key] = {"begun": key == "sight_rot", "new": True}
        self.caught.append((i, key, why))
        self.say("%s is infected with %s (%s)%s" % (self.sim.by_id(i)["name"], CONTAGIONS[key]["name"], why,
                 ": Blinded until the contagion ends" if key == "sight_rot" else
                 ": its effects begin 1d4 days from now"))
        if key == "sight_rot" and self.sim.gm_rules:
            self.sim.gm_rules.add(i, "Blinded", "(Sight Rot)", by=i, contagion="sight_rot")

    def expose(self, i, key, save=True, why="the GM"):
        if key not in CONTAGIONS:
            raise HazardError("Name the contagion.")
        c = self.creature(i)
        if not c or not c.get("pc"):
            raise HazardError("Contagions are kept for the player characters.")
        if key in self.infected.get(i, {}):
            raise HazardError("%s already has %s." % (c["name"], CONTAGIONS[key]["name"]))
        if key == "cackle_fever" and self.traits(i).get("species") == "Gnome":
            self.say("%s is a gnome: immune to Cackle Fever" % c["name"])
            return False
        if save and self.save(i, "con", CONTAGIONS[key]["dc"], CONTAGIONS[key]["name"]):
            return False
        self.infect(i, key, why)
        return True

    # ------------------------------------------------------------ the fight's hooks
    def turn_start(self, me):
        """Start of a creature's turn: slippery ice under it, Cackle Fever in the air, short-term stress running out."""
        if self.sim.down(me):
            return
        gm = self.sim.gm_rules
        for (t, cond), end in list(self.timed.items()):
            if t == me and self.round() >= end:
                self.timed.pop((t, cond))
                if gm:
                    gm.remove(me, cond, "its 1d10 minutes of mental stress end")
        if self.windy():
            self.blow_fog()
        if self.in_kind(me, "slippery_ice") and not self.sim.env.aloft(me):
            self.slip(me, "starts its turn on slippery ice")
        if self.humanoid_pc(me, "cackle_fever") and "cackle_fever" not in self.infected.get(me, {}):
            for src in self.cackle_sources():
                if src == me or (me, src, "cackle_fever") in self.no_catch or self.sim.down(src):
                    continue
                if gm and gm.ft_between(src, me) <= 10:
                    if self.save(me, "con", CONTAGIONS["cackle_fever"]["dc"], "Cackle Fever from %s" % self.sim.by_id(src)["name"]):
                        self.no_catch.add((me, src, "cackle_fever"))
                    else:
                        self.infect(me, "cackle_fever", "within 10 feet of %s at the start of its turn" % self.sim.by_id(src)["name"])
                        break

    def cackle_sources(self):
        return [i for i, k in self.infected.items() if "cackle_fever" in k] + \
               [i for i, k in self.carriers.items() if "cackle_fever" in k]

    def slip(self, me, why):
        gm = self.sim.gm_rules
        self.iced[me] = self.serial()
        if gm and gm.has(me, "Prone"):
            return
        if not self.save(me, "dex", 10, "slippery ice (%s)" % why) and gm:
            gm.add(me, "Prone", "(slipped on the ice)", by=me)

    def on_step(self, name, x0, y0, x1, y1):
        mover = next((c for c in self.sim.sc["combatants"] if c["name"] == name), None)
        if not mover or not self.zones or self.sim.down(mover["id"]):
            return
        me, g = mover["id"], self.g
        new, old = self.footprint(me, (x1 / g, y1 / g)), self.footprint(me, (x0 / g, y0 / g))
        entered = new - old
        if entered and any(self.zone_at(c, "slippery_ice") for c in entered) and self.iced.get(me) != self.serial() \
                and not self.sim.env.aloft(me):
            self.slip(me, "moves onto slippery ice")
        if any(self.zone_at(c, "thin_ice") for c in new):
            self.sim.later.append(self.check_ice)

    def weight(self, i, z):
        c = self.sim.by_id(i)
        if isinstance(c.get("weight_lb"), (int, float)):
            return float(c["weight_lb"])
        import gm_rules
        return float(z["weights"].get(gm_rules.size_of(c), 180))

    def check_ice(self):
        """Thin Ice breaks where the weight on a 10-foot square passes what it holds; everyone on it falls through."""
        for z in [z for z in self.zones if z["kind"] == "thin_ice"]:
            load = {}
            for c in self.sim.sc["combatants"]:
                i = c["id"]
                if self.sim.env.aloft(i) or c.get("_offstage"):
                    continue
                on = {(x // 2, y // 2) for x, y in self.footprint(i) if (x, y) in z["cells"]}
                for a in on:
                    load.setdefault(a, []).append(i)
            for a, who in load.items():
                total = sum(self.weight(i, z) for i in who)
                if total <= z["tolerance"].get(a, 0):
                    continue
                broken = {c for c in z["cells"] if (c[0] // 2, c[1] // 2) == a}
                z["cells"] -= broken
                water = self.place({"kind": "frigid_water", "squares": [list(c) for c in sorted(broken)]}, quiet=True)
                water["name"] = "Broken ice (frigid water)"
                self.say("The thin ice breaks under %s (about %d lb on ice that holds %d): %s fall%s through into frigid "
                         "water" % (", ".join(self.sim.by_id(i)["name"] for i in who), total, z["tolerance"][a],
                                    ", ".join(self.sim.by_id(i)["name"] for i in who), "s" if len(who) == 1 else ""), "turn")
            if not z["cells"]:
                self.zones.remove(z)

    def turn_ended(self, i):
        """End of a creature's turn: a flier in a strong wind lands or falls; frigid water's minutes; the laughter's save."""
        env, gm = self.sim.env, self.sim.gm_rules
        if self.sim.down(i):
            return
        if self.windy() and env.aloft(i):
            z = env.drop_at(env.pos(i))
            env.fall(i, int(z.get("height", 10)), "the strong wind: a flier must land at the end of its turn or fall")
        if self.in_kind(i, "frigid_water"):
            n = self.immersed[i] = self.immersed.get(i, 0) + 1
            c = self.sim.by_id(i)
            score = int((c.get("abilities") or {}).get("con") or 10)
            free = score * ROUNDS_PER_MINUTE
            if n > free and (n - free) % ROUNDS_PER_MINUTE == 0:
                if self.resists(i, "cold") or c.get("cold_adapted"):
                    self.say("%s: frigid water, a minute past %d: automatic success (%s)" % (
                        c["name"], score, "adapted to ice-cold water" if c.get("cold_adapted") else "Resistance or Immunity to Cold"))
                elif not self.save(i, "con", 10, "frigid water (minute %d)" % (n // ROUNDS_PER_MINUTE)):
                    env.add_exhaustion(i, 1, "frigid water")
        else:
            self.immersed.pop(i, None)
        if i in self.laughing and gm and gm.has(i, "Incapacitated"):
            self.laughing[i] += 1
            if self.laughing[i] >= ROUNDS_PER_MINUTE:
                self.stop_laughing(i, "a minute has passed: it succeeds automatically")
            elif self.save(i, "con", CONTAGIONS["cackle_fever"]["fight_dc"], "Cackle Fever's laughter (end of its turn)"):
                self.stop_laughing(i, "saved")

    def stop_laughing(self, i, why):
        self.laughing.pop(i, None)
        gm = self.sim.gm_rules
        if gm and (gm.cond.get(i, {}).get("Incapacitated") or {}).get("laugh"):
            gm.remove(i, "Incapacitated", "stops laughing: " + why)

    def hurt(self, src, tid, amount, kinds=""):
        """Damage taken: Cackle Fever's laughter (any damage but Psychic, while it has Exhaustion); a carrier's wound."""
        if not amount or self.sim.down(tid):
            return
        types = [k for k in str(kinds or "").split(",") if k]
        info = self.infected.get(tid, {}).get("cackle_fever")
        if info and info.get("begun") and self.sim.env.exhaustion.get(tid, 0) > 0 and tid not in self.laughing \
                and any(k != "psychic" for k in (types or ["?"])):
            self.sim.later.append(lambda: self.laugh(tid))
        if src and "sewer_plague" in self.carriers.get(src, set()) and self.humanoid_pc(tid, "sewer_plague") \
                and "sewer_plague" not in self.infected.get(tid, {}):
            self.sim.later.append(lambda: self.expose(tid, "sewer_plague", True,
                                                      "wounded by %s, a carrier" % self.sim.by_id(src)["name"]))

    def laugh(self, i):
        if self.sim.down(i) or i in self.laughing:
            return
        if self.save(i, "con", CONTAGIONS["cackle_fever"]["fight_dc"], "Cackle Fever (damage taken)"):
            return
        self.laughing[i] = 0
        self.say("%s laughs uncontrollably (Cackle Fever): 1d10 Psychic" % self.sim.by_id(i)["name"])
        self.sim.S.pcDamage(i, i, "1d10", 0, False, "psychic")
        self.sim.settle(0.2)
        if self.sim.gm_rules and not self.sim.down(i):
            self.sim.gm_rules.add(i, "Incapacitated", "(laughing: Cackle Fever)", by=i, laugh=True)

    def attack_mode(self, src, rng, spell):
        """Strong Wind: Disadvantage on ranged weapon attack rolls."""
        if self.windy() and rng == "R" and not spell:
            return True, "[strong wind: ranged weapon]"
        return False, ""

    # ------------------------------------------------------------ the GM's fear and mental stress
    def fear(self, targets, dc, source, why=""):
        gm = self.sim.gm_rules
        if not gm:
            raise HazardError("Conditions need the party's rules (a party fight).")
        if not isinstance(dc, int) or isinstance(dc, bool) or not 5 <= dc <= 30:
            raise HazardError("The DC is 5 to 30.")
        if self.creature(source) is None:
            raise HazardError("Fear needs its source: a creature or object on the map the targets fear.")
        why = str(why or "a fear effect").strip()[:80]
        out = []
        for t in targets:
            c = self.creature(t)
            if c is None or self.sim.down(t) or t == source:
                continue
            if gm.cond_immune(t, "frightened"):
                self.say("%s is immune to the Frightened condition" % c["name"]); continue
            if gm.condition_save(t, "wis", dc, why):
                out.append((t, False)); continue
            gm.add(t, "Frightened", "(%s, of %s)" % (why, self.sim.by_id(source)["name"]), by=source, save="wis", dc=dc,
                   lib=True, repeat=True)
            out.append((t, True))
        return out

    def stress(self, targets, save, dc, dice, half, effect, condition, ability, why=""):
        check_stress(save, dc, dice, effect, condition, ability)
        gm = self.sim.gm_rules
        if not gm:
            raise HazardError("Mental stress needs the party's rules (a party fight).")
        why = str(why or "mental stress").strip()[:80]
        for t in targets:
            c = self.creature(t)
            if c is None or self.sim.down(t):
                continue
            saved, _ = gm.roll_save(t, t, {"save": save, "dc": dc}, why)
            dmg = roll_dice(lambda sides: self.sim.rng.randint(1, sides), dice) if dice else 0
            dealt = dmg // 2 if saved and half else 0 if saved else dmg
            if dealt:
                self.sim.S.pcDamage(t, t, "", dealt, False, "psychic")
                self.sim.settle(0.2)
            if saved or effect == "none" or self.sim.down(t):
                continue
            if effect == "short":
                minutes = self.sim.rng.randint(1, 10)
                gm.add(t, condition, "(%s: %d minutes)" % (why, minutes), by=t, stress=True)
                self.timed[(t, condition)] = self.round() + minutes * ROUNDS_PER_MINUTE
            else:
                hours = 10 * self.sim.rng.randint(1, 10) if effect == "long" else None
                s = {"kind": effect, "ability": ability or "all", "why": why, "hours": hours}
                self.stress_new.append((t, s))
                self.say("%s: %s%s" % (c["name"], stress_text(s), " for %d hours" % hours if hours else ""))

    def set_carrier(self, i, key, on):
        if key not in CONTAGIONS or self.creature(i) is None:
            raise HazardError("Name the creature and the contagion.")
        if on:
            self.carriers.setdefault(i, set()).add(key)
        else:
            self.carriers.get(i, set()).discard(key)
        self.say("%s %s %s (its wounds or nearness can pass it on)" % (
            self.creature(i)["name"], "carries" if on else "no longer carries", CONTAGIONS[key]["name"]), "turn")

    # ------------------------------------------------------------ the GM's commands (POST /api/live/hazards)
    def submit(self, cmd, timeout=30):
        """From the service's thread: hand a GM command to the fight (its saves and damage run on the fight's thread)."""
        reply = queue.Queue()
        self.gmq.put((cmd, reply))
        try:
            return reply.get(timeout=timeout)
        except queue.Empty:
            return {"ok": False, "refused": "The fight did not answer (frozen, or between turns): try again."}

    def drain(self):
        """On the simulator's thread: the GM's waiting commands. True when one was applied."""
        did = False
        while True:
            try:
                cmd, reply = self.gmq.get_nowait()
            except queue.Empty:
                return did
            try:
                out = dict(self.do(cmd) or {}, ok=True)
                did = True
            except HazardError as e:
                out = {"ok": False, "refused": str(e)}
            except Exception as e:                              # shown to the GM, never hidden
                out = {"ok": False, "refused": "%s: %s" % (type(e).__name__, e)}
            reply.put(out)

    def refuse_waiting(self):
        while True:
            try:
                _, reply = self.gmq.get_nowait()
            except queue.Empty:
                return
            reply.put({"ok": False, "refused": "The fight is over."})

    def do(self, cmd):
        op = cmd.get("op")
        if op == "weather":
            self.set_weather(cmd.get("weather"))
        elif op == "place":
            return {"zone": self.place(cmd)["id"]}
        elif op == "remove":
            self.remove(str(cmd.get("zone", "")))
        elif op == "fear":
            got = self.fear(cmd.get("targets") or [], cmd.get("dc"), cmd.get("source"), cmd.get("why", ""))
            return {"frightened": [t for t, hit in got if hit]}
        elif op == "stress":
            self.stress(cmd.get("targets") or [], cmd.get("save", "wis"), cmd.get("dc"), cmd.get("dice", ""),
                        bool(cmd.get("half")), cmd.get("effect", "none"), cmd.get("condition"), cmd.get("ability"),
                        cmd.get("why", ""))
        elif op == "contagion":
            return {"infected": self.expose(cmd.get("target"), cmd.get("key"), cmd.get("mode", "expose") == "expose",
                                            "the GM: " + str(cmd.get("why") or "exposed")[:80])}
        elif op == "carrier":
            self.set_carrier(cmd.get("creature"), cmd.get("key"), bool(cmd.get("on", True)))
        else:
            raise HazardError("A hazards op is weather, place, remove, fear, stress, contagion or carrier.")
        return {}

    # ------------------------------------------------------------ the day: in and out
    def from_day(self, day):
        """A fight on the adventure's maps: each character's contagions, Sight Rot's blindness, short-term stress still
        running, the day's weather over the map (sim/rests.py apply_to_sim)."""
        hour, gm = day["hour"], self.sim.gm_rules
        env = environment(day)
        self.weather |= {w for w in env["weather"] if w in FIGHT_WEATHER}
        for c in self.sim.sc["combatants"]:
            e = day["party"].get(c["name"]) if c.get("pc") else None
            if not e:
                continue
            fill(e)
            i = c["id"]
            for inf in e["contagions"]:
                self.infected.setdefault(i, {})[inf["key"]] = {"begun": started(inf, hour)}
            if gm and blinded(e, hour):
                gm.add(i, "Blinded", "(Sight Rot)", by=i, contagion="sight_rot")
            for s in e["stress"]:
                if s["kind"] == "short" and s.get("until") and s["until"] > hour and gm:
                    gm.add(i, s["condition"], "(%s)" % s["why"], by=i, stress=True)
                    self.timed[(i, s["condition"])] = self.round() + max(1, int((s["until"] - hour) * 60)) * ROUNDS_PER_MINUTE

    def to_day(self, day):
        """When the fight ends: contagions caught and lasting mental stress, into the day (sim/rests.py capture)."""
        hour, lines = day["hour"], []
        for i, key, why in self.caught:
            c = self.sim.by_id(i)
            e = day["party"].get(c["name"])
            if not e or _infection(e, key):
                continue
            fill(e)
            days = self.sim.rng.randint(1, 4) if CONTAGIONS[key]["incubation"] else 0
            inf = {"key": key, "since": hour, "onset": hour + 24 * days, "successes": 0, "why": why}
            if key == "sight_rot":
                inf["begun"] = True
            e["contagions"].append(inf)
            lines.append("%s caught %s (%s)%s" % (c["name"], CONTAGIONS[key]["name"], why,
                                                   ": its effects begin %s" % _clock(inf["onset"]) if days else ""))
        for i, s in self.stress_new:
            e = day["party"].get(self.sim.by_id(i)["name"])
            if e:
                fill(e)
                e["stress"].append({"kind": s["kind"], "ability": s["ability"], "why": s["why"], "since": hour,
                                    "until": hour + s["hours"] if s["hours"] else None})
        return lines

    # ------------------------------------------------------------ what the screens show
    def view(self, gm=True):
        out = {"weather": sorted(self.weather), "zones": []}
        for z in self.zones:
            row = {"id": z["id"], "kind": z["kind"], "name": z["name"], "squares": sorted([list(c) for c in z["cells"]])}
            if gm and z["kind"] == "thin_ice":
                row["holds"] = {"%d,%d" % a: v for a, v in z["tolerance"].items()}
            out["zones"].append(row)
        if gm:
            out["carriers"] = {i: sorted(k) for i, k in self.carriers.items() if k}
        return out

    def afflictions(self, i):
        """The sheet's lines for a character: Exhaustion's effects, contagions, laughter, mental stress."""
        out = []
        n = int(self.sim.env.exhaustion.get(i, 0))
        if n:
            speed = int(str(self.sim.by_id(i).get("speed", "30")).split()[0])
            out.append("Exhaustion %d: D20 Tests -%d, Speed -%d ft (%d ft)" % (n, 2 * n, 5 * n, max(0, speed - 5 * n)))
        for key, info in self.infected.get(i, {}).items():
            out.append("%s%s" % (CONTAGIONS[key]["name"], {
                "cackle_fever": ": damage other than Psychic, DC 13 Constitution save or laugh (Incapacitated)" if info.get("begun")
                else " (incubating)",
                "sewer_plague": ": half HP from Hit Point Dice; a Long Rest gives back no HP or Exhaustion" if info.get("begun")
                else " (incubating)", "sight_rot": ": Blinded"}[key]))
        if i in self.laughing:
            out.append("Laughing uncontrollably (Cackle Fever): Incapacitated, a DC 13 Constitution save at the end of each turn")
        for t, s in self.stress_new:
            if t == i:
                out.append(stress_text(s))
        return out


def of(sim):
    h = getattr(sim, "hazards", None)
    if h is None:
        h = sim.hazards = Hazards(sim)
    return h
