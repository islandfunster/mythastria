"""v0.8.6 AUDIT-07 (the AI assistant SRD audit of v0.7.78): a coverage manifest for every simulator run.

A run with no stalls, refusals or wall crossings proves the plumbing and the planner, not full rules fidelity. This
lists what the fake FG resolves, what it never resolves, and the unsupported mechanics this encounter holds (and which
of them were met: the creature took a turn), so a report or a tuning rating is read with its limits."""
import re

SIMULATED = [
    "attack rolls against AC (natural 20 critical, crit range), damage of up to two clauses per hit",
    "Multiattack as FG's parser reads it",
    "movement: walls, doors (DOORS-01), other creatures, squeezing (HR-SQUEEZE), walking and flying speeds",
    "opportunity attacks",
    "Advantage/Disadvantage from sight and light, ranged attacks in close combat, Unconscious targets",
    "player characters' death saving throws; the SRD pregens' team tactics (sim/party.py)",
    "damage Resistance, Immunity and Vulnerability (SIM-MECHANICS-01: the SRD bestiary record or the scenario; Rage; the "
    "pregens' species resistances)",
    "the party's Concentration (Bless, Hex, Spirit Guardians): one at a time, a Constitution save after each damage "
    "(DC 10 or half, up to 30), ends when Incapacitated or dead (SIM-MECHANICS-01 e)",
    "creatures' SRD spells from their Spellcasting (sim/creature_abilities.py, FG-EXIT-01 goal 6): spell attacks, saves "
    "for damage or conditions in the SRD shapes, healing, Magic Missile, Bless, Shield as a Reaction, uses per day; "
    "spells with no effect in a fight or that the engine cannot hold (summons, teleports, Charmed) stay with the GM",
    "monster Concentration: one spell at a time, a Constitution save after each damage (goal 6)",
    "legendary actions after other creatures' turns, and Legendary Resistance (goal 7)",
    "monster traits (goal 7): Pack Tactics, Bloodied Frenzy and Fury, Sunlight and Light Sensitivity, Magic Resistance, "
    "Flyby and Agile, Regeneration, Undead Fortitude, Death Burst, start-of-turn auras, Evasion; the rest are listed "
    "for the GM",
]
NEVER = [
    "monster save effects other than the breath and Death Burst the simulator plays as GM (sim/gm_rules.py)",
    "conditions other than the ones the simulator plays as GM (sim/gm_rules.py: Grappled, Prone, Charmed, Frightened, "
    "Incapacitated, Steam Breath's slow, Burning)",
    "reactions other than opportunity attacks and Shield", "lair actions", "surprise (fixed initiative)",
]
CONDITIONS = ("Blinded", "Charmed", "Deafened", "Frightened", "Grappled", "Incapacitated", "Paralyzed", "Petrified",
              "Poisoned", "Prone", "Restrained", "Stunned", "Unconscious")
SENSES = ("Tremorsense", "Truesight")              # the planner uses sight, darkvision and Blindsight only
SPEEDS = ("Burrow", "Climb", "Swim")               # the planner uses walking and flying speeds only


def encounter_items(c):
    """Unsupported mechanics in one creature's scenario entry (its stat block as the simulator holds it)."""
    name, out = c.get("name", "?"), []
    for a in c.get("actions") or []:
        desc = str(a.get("desc") or "")
        for cond in CONDITIONS:
            if re.search(r"\b%s\b" % cond, desc):
                out.append("%s: %s applies %s (not applied)" % (name, a.get("name", "?"), cond))
        if re.search(r"saving throw", desc, re.I):
            out.append("%s: %s calls for a saving throw (not resolved)" % (name, a.get("name", "?")))
    for s in SENSES:
        if s.lower() in str(c.get("senses") or "").lower():
            out.append("%s: %s (not used by the planner)" % (name, s))
    for s in SPEEDS:
        if s.lower() in str(c.get("speed") or "").lower():
            out.append("%s: %s speed (not used by the planner)" % (name, s))
    return out


def declared(sc):
    """What the scenario itself says is not simulated (its source note: "Not simulated: a, b, c.")."""
    m = re.search(r"Not simulated:\s*(.+?)(?:\.\s|\.$|$)", str(sc.get("source") or ""), re.S | re.I)
    return [p.strip() for p in re.split(r",\s*", m.group(1)) if p.strip()] if m else []


def manifest(sc, lines=None):
    enc = [i for c in sc.get("combatants") or [] if not c.get("pc") for i in encounter_items(c)]
    acted = {c.get("name") for c in sc.get("combatants") or [] if lines is not None
             and any("%s's turn" % c.get("name") in str(l) for l in lines)}
    return {"simulated": SIMULATED, "never": NEVER, "encounter": enc, "declared": declared(sc),
            "met": [i for i in enc if i.split(":", 1)[0] in acted]}


def report_lines(sc, lines):
    m = manifest(sc, lines)
    out = ["## Coverage (what this run did not simulate)", "",
           "Simulated: " + "; ".join(m["simulated"]) + ".", "",
           "Never simulated: " + "; ".join(m["never"]) + ".", ""]
    if m["encounter"] or m["declared"]:
        out.append("In this encounter, not simulated:")
        out += ["- %s%s" % (i, " (met in this run)" if i in m["met"] else "") for i in m["encounter"]]
        out += ["- %s (declared by the scenario)" % d for d in m["declared"]]
    else:
        out.append("In this encounter: nothing beyond the list above was found.")
    return out


def summary_line(sc):
    """One line for the tuner: the encounter's unsupported mechanics, deduplicated by creature kind."""
    m = manifest(sc)
    items = sorted({re.sub(r" \d+:", ":", i) for i in m["encounter"]} | set(m["declared"]))
    return ("Not simulated in this encounter (ratings exclude them): " + "; ".join(items) + ".") if items else ""
