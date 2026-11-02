"""REFEREE-01 (GM 2026-10-22: "is there an agent that is expert on spell rules and double checks all aspects of the rules
are followed? It would need to be something built into the game itself."): the rules referee. After every spell a
character casts, it compares what happened with the spell's rules (sim/spell_rules.py: the SRD 5.2.1 rule sheet, with
the GM's clarification over it) and writes a "Referee:" note in the log for anything that doesn't add up, quoting the
rule it relies on. It never changes a result: the GM decides. Parser and arithmetic only, no language model (GM:
"No, parser only").

Where it watches: every spell a player casts in Play live (sim/live_play.py), every spell the scripted party casts in a
simulator run (sim/party.py wraps each cast in Referee.watch), and a creature's spell the same way once creatures cast
spells. In a simulator run a note is also one of the run's problems, so the test that ran it fails like any other rule
break.

Checks (SRD 5.2.1 "Spells", "Casting a Spell", the Rules Glossary, and the spell's own text):
- slot: a levelled spell spends exactly one slot of its level or higher (none when a feature casts it free); a cantrip
  spends none;
- one spell with a spell slot per turn;
- Concentration: a Concentration spell is the one the caster now holds (or ended at once when it held no one), never
  two at a time; a spell without Concentration leaves the caster's Concentration alone;
- casting time: an Action spell uses the Action, a Bonus Action spell the Bonus Action;
- range: the target (from the edge of the caster's space to the edge of its) or the point is within the spell's range;
  no more creatures than it may target;
- who it touches: only creatures inside its area (or the target, and the creatures its text names around the target),
  and for "creatures of your choice" only the ones the caster chose; every creature inside a no-choice area makes its
  save;
- saving throw: the DC is 8 + Proficiency Bonus + the spellcasting ability modifier (the character sheet's DC);
- damage: no more than the spell's dice (a higher slot's, a cantrip's tier, every dart, ray or beam it makes, the extra
  its text names), the caster's modifier when it adds one, a class feature that adds to it (Agonizing Blast) and Hex on
  the target; a Critical Hit doubles the dice, Vulnerability the whole;
- conditions: only the conditions the spell gives (and those they include: Unconscious brings Prone);
- healing: no more than the spell's dice (a higher slot's), the caster's modifier when it adds one, Disciple of Life
  and Blessed Healer (REFEREE-02).
REFEREE-02 (GM 2026-10-26, goal 8: "the later saves of a lasting area, the save of an attack's rider, and healing
amounts"), whoever casts the spell or makes the attack:
- a lasting area's later saves (Spirit Guardians, Stinking Cloud, Moonbeam, Web, Cloudkill...; spell_rules.later reads
  when from the spell's words): each one is asked when the spell says (the area moved into the creature's space, the
  creature entered it, started or ended its turn there), only while the spell lasts, of a creature inside it that it
  affects, at most once per turn when it says so; the right ability and the caster's DC; the damage within its dice
  (half or none on a success, as it says) and only its conditions, none on a success. At each turn's end, a creature
  that ended (or started) its turn inside, or came inside during it, and never saved is called out;
- an attack's save rider (the Ghoul's Claw: "Constitution Saving Throw: DC 10. Failure: The target has the Paralyzed
  condition until the end of its next turn"), read from the stat block's own words: the target rolls it (not a
  creature the rider spares: "isn't an Undead or elf"), the ability and DC the stat block gives, on a failure only the
  conditions and damage its Failure names, nothing on a success, and the condition ends when it says.
Areas are read two ways, as the table's grid can be: a creature the spell may touch is one inside the area by the grid
reading (5-foot diagonals, any square of its space); a creature that had to save is one inside it by the strict reading
(the centre of its space, measured straight). So the referee calls out only what is wrong either way.
Who it touched comes from the engine's own record of damage (its source) and conditions (who gave them), so a Death
Burst the spell sets off is not taken for the spell's own work.
"""
import contextlib, math, re

import spell_rules

CONDITIONS = ("Blinded", "Charmed", "Deafened", "Exhaustion", "Frightened", "Grappled", "Incapacitated", "Invisible",
              "Paralyzed", "Petrified", "Poisoned", "Prone", "Restrained", "Stunned", "Unconscious")
# SRD 5.2.1 Rules Glossary: conditions that bring others with them
INCLUDES = {"Unconscious": ("Incapacitated", "Prone"), "Paralyzed": ("Incapacitated",), "Petrified": ("Incapacitated",),
            "Stunned": ("Incapacitated",)}
# class features that add to a spell's damage (SRD 5.2.1), by the character sheet's key: the spell, and what each of its
# hits gains (Agonizing Blast: the spellcasting ability modifier to each beam)
FEATURES = {"agonizing": "Eldritch Blast"}
ABILITY = {"Strength": "str", "Dexterity": "dex", "Constitution": "con", "Intelligence": "int", "Wisdom": "wis",
           "Charisma": "cha"}
NAMES = {v: k for k, v in ABILITY.items()}
SAVE_LINE = r" (Strength|Dexterity|Constitution|Intelligence|Wisdom|Charisma) save\b"
# REFEREE-02: when a lasting area asks for its save (spell_rules.later)
WHEN = {"moved": "when the area moved into its space", "enter": "when it entered the area",
        "start": "at the start of its turn there", "end": "at the end of its turn there",
        "your_start": "at the start of the caster's turn", "your_end": "at the end of the caster's turn"}
# an attack's rider in a stat block: "Constitution Saving Throw: DC 10. Failure: The target has the Paralyzed ..."
RIDER = re.compile(r"(Strength|Dexterity|Constitution|Intelligence|Wisdom|Charisma) Saving Throw: DC (\d+)\.\s*"
                   r"((?:First )?Failure:.*?)(?=\s(?:Second Failure|Success|Failure by)|$)", re.S)
DAMAGE = re.compile(r"\d+ \((\d+d\d+(?: ?[+-] ?\d+)?)\) \w+ damage")


def _dice_max(expr):
    total = 0
    for n, d in re.findall(r"(\d+)d(\d+)", expr or ""):
        total += int(n) * int(d)
    return total


def _flat(expr):
    return sum(int(k) for k in re.findall(r"\+ ?(\d+)\b(?!d)", expr or ""))


def _first_sentence(text):
    m = re.match(r"(.+?[.!?])(\s|$)", (text or "").strip(), re.S)
    return (m.group(1) if m else (text or "")[:200]).strip()


def proficiency_bonus(level):
    return 2 + (max(1, int(level or 1)) - 1) // 4


class Referee:
    def __init__(self, fight=None, sim=None):
        self.fight, self._sim = fight, sim
        self.notes = []                      # every note this fight, for the tests and the table
        self.checked = []                    # (caster id, spell) of every cast checked
        self.open = []                       # casters whose cast is resolving (a watch inside it is the same cast)
        self.hurts = []                      # (source, target, damage taken) as the engine deals it
        self.used = {}                       # (caster, turn number) -> the casting times its spells took that turn
        self.spans = []                      # (first, last + 1) log lines of every cast or action watched
        self.given = []                      # conditions a spell or an action gave, watched until they should end
        self.timed = 0                       # how many were watched
        self.turn = None                     # (creature, turn number) whose turn runs
        self.areas = {}                      # (caster, spell) -> a lasting area: its slot level, its point, its round
        self.area_saves = []                 # its later saves: creature, spell, caster, turn (window), when
        self.area_checked = []               # (caster, spell, creature, when) of every later save checked
        self.rider_checked = []              # (attacker, action, target) of every rider save checked
        self.window, self.window_at = 0, None   # the referee's own turn count; where all stood when this turn began
        self.lag = 0                         # how many turns the run loop is behind the engine's own count
        self.judged = 0                      # turns judged for a lasting area's missed saves

    @property
    def sim(self):
        return self.fight.sim if self.fight is not None else self._sim

    def units(self):
        return self.sim.sc.get("units", 5)

    def serial(self):
        return int(self.sim.S.turnSerial or 0)

    def note(self, spell, text, rule):
        msg = "Referee: %s %s (Rule: %s)" % (spell, text, rule)
        self.notes.append(msg)
        self.sim.say("referee", msg)
        self.sim.problems.append(msg)        # a rule break: the run's test fails on it like on any other problem
        return msg

    def hurt(self, src, tgt, amount):
        """The engine dealt damage (the fake FG's onHurt): who dealt it to whom."""
        self.hurts.append((src, tgt, amount))

    def own_lines(self, start):
        """The log lines since `start`, without those of a cast or action watched inside (a Hellish Rebuke a Fireball's
        damage set off is the Rebuke's), and records this span for an outer watch."""
        end = len(self.sim.lines)
        inner = [(s, e) for s, e in self.spans if s >= start]
        self.spans = [sp for sp in self.spans if sp[0] < start][-50:] + [(start, end)]
        return [t for k, (_, t) in enumerate(self.sim.lines[start:end], start) if not any(s <= k < e for s, e in inner)]

    # ------------------------------------------------------------------ before and after
    def snapshot(self, me):
        import live_spells, sim_messages
        sim, party = self.sim, self.sim.party
        state = sim_messages.state(sim, 0, None)
        gm = sim.gm_rules
        t = self.fight.turn_state if self.fight is not None else None
        serial = self.serial()
        own = bool(t) and t.get("id") == me                     # a live player's turn: its own record of the Action
        return {"slots": list(live_spells.slots_of(party, me)) if party else [0],
                "conc": party.concentrates(me) if party else None,
                "action_used": bool(t.get("action_used")) if own else "action" in self.used.get((me, serial), ()),
                "bonus_free": bool(party.bonus_free(me)) if party else True,
                "slot_spent": bool(party and party.slot_turn.get(me) == serial),
                "hex": (getattr(party, "hex", None) or {}).get(me),     # Hex's creature (None once it dropped)
                "mark": (getattr(party, "marked", None) or {}).get(me) if party and party.concentrates(me) == "Hunter's Mark" else None,
                "serial": serial, "hurt_n": len(self.hurts),
                "hp": {c["id"]: c["hp"] for c in state["combatants"]},
                "cond": {c["id"]: dict((gm.cond.get(c["id"]) or {}) if gm else {}) for c in state["combatants"]},
                "pos": {c["id"]: (c["x"], c["y"]) for c in state["combatants"]},
                "down": {c["id"]: c["down"] for c in state["combatants"]},
                "doors": self.doors()}                          # SPELL-OBJECTS-01: each door's Hit Points and lock

    def doors(self):
        try:
            import spell_doors
            return spell_doors.of(self.sim).view() if (self.sim.sc.get("walls") and self.sim.walls is not None) else {}
        except Exception:
            return {}

    @contextlib.contextmanager
    def watch(self, me, spell, cmd=None, effect=None):
        """A cast while the engine resolves it: the state before, the check after. A watch inside one of the same
        caster's is that cast (the scripted party's code a live cast calls). The with-block may add to w["cmd"] and
        w["effect"] as the cast finds its targets; w["notes"] holds the notes once it is over."""
        w = {"cmd": dict(cmd or {}, spell=spell), "effect": dict(effect or {}), "notes": []}
        if me in self.open or spell_rules.spell(spell) is None:
            yield w
            return
        before = self.snapshot(me)
        start = len(self.sim.lines)
        self.open.append(me)
        try:
            yield w
        finally:
            self.open.remove(me)
        w["notes"] = self.check_cast(me, w["cmd"], before, w["effect"], self.own_lines(start))

    def touched(self, me, before, after):
        """{creature: conditions the caster gave it} for every creature the cast changed: those it damaged (the engine
        names the source of all damage), those it healed, those it gave a condition."""
        out = {}
        for s, t, _ in self.hurts[before["hurt_n"]:]:
            if s == me:
                out.setdefault(t, set())
        for i, hp in after["hp"].items():
            if hp > before["hp"].get(i, hp):
                out.setdefault(i, set())
        for i, conds in after["cond"].items():
            for n, info in conds.items():
                if n not in before["cond"].get(i, {}) and (info or {}).get("by") == me:
                    out.setdefault(i, set()).add(n)
        out.pop(me, None)
        return out

    def check_cast(self, me, cmd, before, effect, lines):
        """Compare one cast with its rules. Returns the notes it wrote."""
        name = cmd.get("spell")
        rules = spell_rules.spell(name)
        if rules is None:
            return []
        start = len(self.notes)
        self.checked.append((me, name))
        after = self.snapshot(me)
        caster = self.sim.by_id(me)
        text = " ".join(lines)
        rule_text = _first_sentence(rules["text"])
        level = rules["level"]
        free = cmd.get("free")                   # a feature casts it without a slot (Infernal Legacy, Paladin's Smite)

        # -- the slot, and one per turn
        spent = [b - a for b, a in zip(before["slots"], after["slots"])]
        used = sum(spent)
        slot_level = next((i + 1 for i, d in enumerate(spent) if d > 0), None)
        if level == 0 and used:
            self.note(name, "is a cantrip but spent a spell slot.", "a cantrip needs no slot")
        if level > 0 and free:
            if used:
                self.note(name, "spent a spell slot, though %s casts it without one." % free, free)
        elif level > 0:
            if used != 1:
                self.note(name, "spent %d spell slots; a spell spends exactly one." % used, "Casting a Spell: Spell Slots")
            elif slot_level < level:
                self.note(name, "used a level %d slot; it needs level %d or higher." % (slot_level, level),
                          "Casting a Spell: Spell Slots")
            if before["slot_spent"]:
                self.note(name, "was cast after a slot was already spent this turn.", "One Spell with a Spell Slot per Turn")
        # a free casting at a higher level ("Fireball (level 5 version)" in a creature's Spellcasting) names its level
        slot_level = slot_level or (max(level, int(cmd["slot"])) if free and cmd.get("slot") else level)
        if rules["area"]:                                        # SPELLS-4-9: Confusion's Sphere grows with the slot
            rules = dict(rules, area=spell_rules.area_at(rules, slot_level))

        # -- Concentration
        conc = rules["duration"]["concentration"]
        # The caster may lose it by itself during the cast, and the log says so: Sleep ends on a creature this spell
        # damages; a failed Concentration save after damage the cast set off (2026-10-23: Hero 6's Divine Smite dropped a
        # Magmin, its Death Burst burned her, "Hero 6 Concentration save: ... -> Bless ends").
        lost = "concentration ends" in text.lower() or any(
            line.startswith("%s Concentration save:" % caster["name"]) and not line.endswith("-> kept") for line in lines)
        if conc and after["conc"] not in (name, None):
            self.note(name, "needs Concentration, but %s now holds %s." % (caster["name"], after["conc"]), "Concentration")
        if conc and after["conc"] is None and not lost:
            self.note(name, "needs Concentration, but %s holds nothing." % caster["name"], "Concentration")
        if not conc and before["conc"] and after["conc"] != before["conc"] and (
                ("to cast %s" % name) in text or not lost):
            self.note(name, "has no Concentration, yet %s's %s ended." % (caster["name"], before["conc"]), "Concentration")

        # -- casting time
        ct = rules["casting_time"]
        if cmd.get("legendary"):            # a legendary action casts it on another creature's turn: not its Action
            ct = "legendary"
        if ct == "action" and "Quickened Spell" in ((cmd or {}).get("metamagic") or ()):
            ct = "bonus_action"             # SRD 5.2.1 Quickened Spell: a Bonus Action instead of the Action
        if cmd.get("free") and cmd.get("time") in ("bonus", "reaction"):
            ct = {"bonus": "bonus_action", "reaction": "reaction"}[cmd["time"]]   # a creature's Spellcasting says so
            # (group 1, GM 2026-10-27: the Priest's "3/Day: Bless ... (all bonus actions)")
        if ct == "action" and before["action_used"]:
            self.note(name, "takes an Action; the Action was already used.", "Casting Time: Action")
        if ct == "bonus_action" and not before["bonus_free"]:
            self.note(name, "takes a Bonus Action; it was already used.", "Casting Time: Bonus Action")
        self.used.setdefault((me, before["serial"]), []).append(ct)

        # -- range, and how many it may target (GM 2026-10-23: the Sorcerer's Distant and Twinned Spell change both)
        rng, u = rules["range"], self.units()
        metas = (cmd or {}).get("metamagic") or []
        metas = {metas} if isinstance(metas, str) else set(metas)
        reach_ft = rng["ft"]
        if "Distant Spell" in metas and reach_ft:
            reach_ft = 30 if rng["kind"] == "touch" or reach_ft <= 5 else reach_ft * 2
        aims = [t for t in ([cmd["target"]] if cmd.get("target") is not None else []) + list(cmd.get("targets") or [])
                if t != me and t in before["pos"]]
        near = rules.get("near") or {}
        if rng["kind"] in ("ranged", "touch") and rng["ft"]:
            for t in dict.fromkeys(aims):
                if near.get("leap") and aims and t != aims[0] and self.gap_ft(aims[0], t, before) <= near["ft"] + 0.01:
                    continue                                     # SPELLS-4-9: Chain Lightning's bolt leaps from the first
                ft = self.gap_ft(me, t, before)
                if ft > reach_ft + 0.01:
                    self.note(name, "reached %s at %d ft; its range is %d ft." % (self.sim.by_id(t)["name"], ft, reach_ft),
                              "Range: %s ft" % rng["ft"])
            if not aims and "x" in cmd and "y" in cmd and rules["area"] and rules["area"]["origin"] == "point":
                here = before["pos"][me]
                ft = (max(abs(cmd["x"] - here[0]), abs(cmd["y"] - here[1])) - (self.span(me) - 1) / 2) * u
                if ft > reach_ft + 0.01:
                    self.note(name, "was placed %d ft away; its range is %d ft." % (ft, reach_ft), "Range: %s ft" % rng["ft"])
        most_targets = self.target_limit(rules, slot_level, caster)
        if most_targets and "Twinned Spell" in metas:
            most_targets += 1
        words = __import__("high_levels").words_extra(caster, name)   # Words of Creation (Bard 20): a second creature
        if most_targets and words:
            most_targets += words
            for t in aims[1:2]:
                if self.gap_ft(aims[0], t, before) > 10.01:
                    self.note(name, "took %s, %d ft from %s; Words of Creation's second creature is within 10 ft of the first." % (
                        self.sim.by_id(t)["name"], self.gap_ft(aims[0], t, before), self.sim.by_id(aims[0])["name"]),
                        "Words of Creation (Bard 20)")
        chosen = set(cmd.get("targets") or [])
        if most_targets and len(chosen) > most_targets:
            self.note(name, "took %d creatures; it takes at most %d." % (len(chosen), most_targets), rule_text)
        for t in (aims[1:] if near.get("leap") else []):
            if self.gap_ft(aims[0], t, before) > near["ft"] + 0.01:
                self.note(name, "leapt to %s, %d ft from %s; it leaps only within %d ft of the first target." % (
                    self.sim.by_id(t)["name"], self.gap_ft(aims[0], t, before), self.sim.by_id(aims[0])["name"], near["ft"]),
                    rule_text)

        # -- who it touched
        if rules["area"] and rules["area"]["shape"] == "cube" and effect.get("cube"):
            self.check_cube(name, rules["area"], me, before, effect)
        touched = self.touched(me, before, after)
        t_rules = rules["targets"]
        if t_rules.get("kind") == "area" and t_rules.get("max") and len(touched) > t_rules["max"]:
            self.note(name, "affected %d creatures in its area; it takes at most %d." % (len(touched), t_rules["max"]),
                      rule_text)                                 # SPELLS-4-9: Mass Cure Wounds' six
        allowed = self.allowed(me, cmd, rules, before, effect, lenient=True)
        if allowed is not None:
            for i in sorted(set(touched) - allowed):
                self.note(name, "affected %s, outside what it may touch." % self.sim.by_id(i)["name"], rule_text)
        # every creature inside an instant area saves at once (a lasting area, like Spirit Guardians, asks later: when a
        # creature enters it or ends its turn there)
        if rules["area"] and not rules["targets"]["choice"] and rules["save"] and rules["duration"]["instant"]:
            inside = self.allowed(me, cmd, rules, before, effect, lenient=False) or set()
            sculpt = set(self.sim.party.allies(me)) if caster.get("sculpt_spells") else set()   # Sculpt Spells: no save
            for i in sorted(inside - sculpt - {me}):
                nm = self.sim.by_id(i)["name"]
                if not before["down"].get(i) and not re.search(re.escape(nm) + r"(?!\d)", text):
                    self.note(name, "never gave %s its saving throw, though it was inside." % nm, rule_text)

        # -- the save DC
        want = None
        if rules["save"]:
            # the cast's own DC, not a Concentration save its damage set off (a creature that concentrates, too)
            m = re.search(r"DC (\d+)", " ".join(l for l in lines if " Concentration" not in l))
            want = self.spell_dc(caster)
            party = getattr(self.sim, "party", None)
            if want is not None and party is not None and hasattr(party, "innate_on"):
                want += party.innate_on(me)                      # GM 2026-10-23: Innate Sorcery, +1 while active
            if m and want is not None and int(m.group(1)) != want:
                self.note(name, "used DC %s; %s's spell save DC is %d (8 + Proficiency Bonus + spellcasting ability)."
                          % (m.group(1), caster["name"], want), "Spell Save DC")

        # -- damage within the dice
        if rules["damage"]:
            crit = bool(re.search(r"-> crit\b|critical|CRIT", text, re.I))     # the attack line: "... -> crit"
            for i in sorted(touched):
                dealt = sum(a for s, t, a in self.hurts[before["hurt_n"]:] if s == me and t == i)
                most = self.most_damage(caster, rules, slot_level, i, crit, hexed=i in (before["hex"], after["hex"]),
                                        marked=i in (before["mark"], after["mark"]))
                if dealt > most:
                    self.note(name, "dealt %d damage to %s; the most it can deal is %d." % (dealt, self.sim.by_id(i)["name"], most),
                              rule_text)

        # -- healing within the dice (REFEREE-02); the caster too when it is one of the spell's creatures
        if (rules.get("healing") or {}).get("dice"):
            aimed = set(cmd.get("targets") or []) | ({cmd["target"]} if cmd.get("target") is not None else set())
            others = any(after["hp"].get(i, 0) > before["hp"].get(i, 0) for i in touched)
            for i in sorted(set(touched) | ({me} & aimed)):
                gained = after["hp"].get(i, 0) - before["hp"].get(i, 0)
                most = self.most_healing(caster, rules, slot_level, i == me and others)
                if most is not None and gained > most:
                    self.note(name, "healed %s %d Hit Points; the most it can heal is %d." % (self.sim.by_id(i)["name"],
                                                                                            gained, most), rule_text)

        # -- conditions
        allowed_conds = set(rules["conditions"])
        allowed_conds |= {x for c in allowed_conds for x in INCLUDES.get(c, ())}
        for i, given in sorted(touched.items()):
            for cnd in sorted(given):
                if cnd in CONDITIONS and cnd not in allowed_conds:     # the engine's own marks (Blessed ...) are not conditions
                    self.note(name, "gave %s the %s condition, which it doesn't give." % (self.sim.by_id(i)["name"], cnd), rule_text)
                elif cnd in (rules.get("lasts") or {}):                 # watched until it should end
                    self.time_condition(i, cnd, me, name, rules["lasts"][cnd], before["serial"], rules)

        # -- doors (SPELL-OBJECTS-01)
        self.check_doors(me, name, cmd, rules, before, after, slot_level, caster, text, effect)

        # -- a lasting area (REFEREE-02): its later saves are checked as they come (watch_area, area_turn)
        if spell_rules.later(rules) and (not conc or after["conc"] == name):
            point = rules["area"] and rules["area"]["origin"] == "point"
            origin = effect.get("origin") or ([cmd["x"], cmd["y"]] if "x" in cmd and "y" in cmd else None)
            self.areas[(me, name)] = {"slot": slot_level, "origin": list(origin) if point and origin else None,
                                      "round": self.round(), "dc": want}
        return self.notes[start:]

    def check_doors(self, me, name, cmd, rules, before, after, slot_level, caster, text, effect):
        """SPELL-OBJECTS-01: only a spell that may target an object (sim/spell_objects.py) changes a door; a door it
        was cast at is within its range; the damage within its dice (objects immune to Poison and Psychic); Knock
        unlocks one lock; an area reaches only the doors inside it."""
        import spell_objects, spell_doors
        b, a = before.get("doors") or {}, after.get("doors") or {}
        changed = {d: (b[d], a[d]) for d in b if d in a and (a[d]["hp"] < b[d]["hp"] or a[d]["broken"] != b[d]["broken"]
                                                               or a[d]["locked"] != b[d]["locked"])}
        rule_text = _first_sentence(rules["text"])
        if spell_objects.objects(name) == "no":
            for d in changed:
                self.note(name, "changed the %s, though it targets only creatures." % d, rule_text)
            return
        aimed = cmd.get("door")
        doors = spell_doors.of(self.sim)
        if aimed is not None:
            aimed = str(aimed)
            if aimed in doors.walls():
                ft, _ = doors.ft_to(me, doors.walls()[aimed])
                reach = max(rules["range"]["ft"] or 0, 5)
                if ft > reach + 0.01:
                    self.note(name, "reached the %s at %d ft; its range is %d ft." % (aimed, ft, reach), "Range: %s ft" % reach)
            for d in changed:
                if d != aimed:
                    self.note(name, "changed the %s too; it was cast at the %s." % (d, aimed), rule_text)
        unlocked = [d for d, (x, y) in changed.items() if x["locked"] and not y["locked"] and not y["broken"]]
        locked = [d for d, (x, y) in changed.items() if y["locked"] and not x["locked"]]
        if locked and name not in ("Arcane Lock", "Stone Shape"):
            self.note(name, "locked the %s; it locks nothing." % ", ".join(locked), rule_text)
        for d in b:                                              # only a spell whose text lights flammable objects
            if d in a and a[d]["burning"] and not b[d]["burning"] and not spell_doors.IGNITE.search(rules["text"]):
                self.note(name, "set the %s alight; it lights nothing." % d, rule_text)
        for d, (x, y) in changed.items():
            if y["broken"] and not x["broken"] and y["hp"] > 0 and name not in ("Disintegrate", "Stone Shape"):
                self.note(name, "destroyed the %s without bringing it to 0 Hit Points." % d, rule_text)
        if unlocked and name not in ("Knock", "Dispel Magic"):
            self.note(name, "unlocked the %s; it opens no lock." % ", ".join(unlocked), rule_text)
        if len(unlocked) > 1:
            self.note(name, "unlocked %d locks; it unlocks one." % len(unlocked), "If the object has multiple locks, only "
                      "one of them is unlocked.")
        crit = bool(re.search(r"-> crit\b", text))
        types = {x["type"] for x in rules["damage"] or []}
        for d, (x, y) in changed.items():
            lost = x["hp"] - y["hp"]
            if lost <= 0:
                continue
            if not rules["damage"]:
                self.note(name, "damaged the %s; it deals no damage." % d, rule_text)
                continue
            if types and types <= spell_doors.IMMUNE:
                self.note(name, "damaged the %s with %s; objects are immune to it." % (d, " and ".join(sorted(types))),
                          "Breaking Objects")
            most = self.most_damage(caster, rules, slot_level, me, crit)
            if lost > most:
                self.note(name, "dealt %d damage to the %s; the most it can deal is %d." % (lost, d, most), rule_text)
            if aimed is None and rules["area"] and effect.get("origin") and not y["broken"] \
                    and d not in doors.in_area(effect):
                self.note(name, "damaged the %s, outside its area." % d, rule_text)

    # ------------------------------------------------------------------ a lasting area's later saves (REFEREE-02)
    @contextlib.contextmanager
    def watch_area(self, me, spell, t, when, slot_level=None, origin=None):
        """A lasting area's later save while the engine resolves it, whoever cast the spell (Spirit Guardians when its
        Emanation reaches a creature or one ends its turn in it; Stinking Cloud at the start of a turn in it): the state
        before, the check after. when: a key of WHEN; slot_level: the slot it was cast with; origin: its point (a
        Sphere's or a Cylinder's centre, in squares)."""
        w = {"notes": []}
        if spell_rules.spell(spell) is None:
            yield w
            return
        before = dict(self.snapshot(me), holds=self.holds(me, spell), window=(self.window, self.serial()))
        start = len(self.sim.lines)
        yield w
        w["notes"] = self.check_area_save(me, spell, t, when, slot_level, origin, before, self.own_lines(start))

    def area_of(self, me, spell, rules, slot_level=None, origin=None):
        """The record of a caster's lasting area (made at its cast, or at its first later save)."""
        a = self.areas.setdefault((me, spell), {"slot": slot_level or rules["level"], "origin": None, "round": self.round(),
                                                "dc": None})
        if origin is not None and rules["area"] and rules["area"]["origin"] == "point":
            a["origin"] = list(origin)
        return a

    def holds(self, me, spell):
        """Does the caster's lasting spell still last? True / False, or None when the referee can't tell."""
        rules = spell_rules.spell(spell)
        if rules["duration"]["concentration"]:
            party = self.sim.party
            held = party.concentrates(me) if party else None
            if held == spell:
                return True
            return False if held or self.sim.by_id(me).get("pc") else None
        a, m = self.areas.get((me, spell)), re.search(r"(\d+) (round|minute|hour)", rules["duration"].get("text") or "")
        if not a or not m:
            return None
        return self.round() <= a["round"] + int(m.group(1)) * {"round": 1, "minute": 10, "hour": 600}[m.group(2)]

    def affects(self, later, me, i, area, must=False):
        """May the area ask creature i for its save (must: has to)? The caster is not inside its own Emanation; "Any
        enemy" only the caster's foes. A spell whose caster spares creatures when casting it (Spirit Guardians) must ask
        the caster's foes (the engine spares the caster's side); one whose caster may force a save each time (Conjure
        Animals) never has to."""
        if i == me and (later["who"] != "all" or (area or {}).get("shape") == "emanation"):
            return False
        foe = self.sim.by_id(i).get("side") != self.sim.by_id(me).get("side")
        if later["who"] == "enemy":
            return foe
        if must and later["who"] in ("designate", "choice"):
            return foe and later["who"] == "designate"
        return True

    def check_area_save(self, me, spell, t, when, slot_level, origin, before, lines):
        """Compare one later save of a lasting area with the spell's words. Returns the notes it wrote."""
        rules = spell_rules.spell(spell)
        later = spell_rules.later(rules)
        start = len(self.notes)
        self.area_checked.append((me, spell, t, when))
        after = self.snapshot(me)
        caster, nm = self.sim.by_id(me), self.sim.by_id(t)["name"]
        if not later:
            self.note(spell, "gave %s a save after it was cast; its area asks for none later." % nm,
                      _first_sentence(rules["text"]))
            return self.notes[start:]
        rule = _first_sentence(later["text"])
        a = self.area_of(me, spell, rules, slot_level, origin)
        slot = slot_level or a["slot"]

        # -- when, how often, while it lasts, of whom
        if when not in later["when"]:
            self.note(spell, "gave %s its save %s; it asks for it only %s." % (
                nm, WHEN[when], " or ".join(WHEN[x] for x in later["when"])), rule)
        turn = before["window"]                                  # the referee's turn and the engine's
        prior = [s for s in self.area_saves if (s["t"], s["spell"], s["by"], s["turn"]) == (t, spell, me, turn)]
        if later["once"] and prior:
            self.note(spell, "gave %s its save twice in one turn; a creature makes it only once per turn." % nm, rule)
        elif when == "enter" and later["first"] and any(s["when"] == "enter" for s in prior):
            self.note(spell, "gave %s its save twice in one turn for entering; only the first time on a turn." % nm, rule)
        self.area_saves.append({"t": t, "spell": spell, "by": me, "window": turn[0], "turn": turn, "when": when})
        if before["holds"] is False:
            self.note(spell, "gave %s its save after the spell ended." % nm, "Duration: %s" % rules["duration"].get("text"))
        if not self.affects(later, me, t, rules["area"]):
            self.note(spell, "gave %s its save; %s." % (nm, "the caster is not inside its own Emanation" if t == me
                                                        else "it asks only the caster's foes"), rule)
        area = rules["area"]
        if area and (area["origin"] != "point" or a["origin"]):
            inside = self.in_area(area, me, t, before, {"origin": a["origin"]} if area["origin"] == "point" else {}, True)
            if inside is False:
                self.note(spell, "gave %s its save, but %s is outside its %s." % (nm, nm, area["shape"].capitalize()), rule)

        # -- the roll: the target's, the right ability, the caster's DC
        roll = next((ln for ln in lines if re.match(re.escape(nm) + SAVE_LINE, ln)), None)
        saved = None
        if roll is None:
            self.note(spell, "never rolled %s's %s save." % (nm, NAMES.get(later["ability"], "")), rule)
        else:
            ab = ABILITY[re.match(re.escape(nm) + SAVE_LINE, roll).group(1)]
            if later["ability"] and ab != later["ability"]:
                self.note(spell, "asked %s for a %s save; it asks for %s." % (nm, NAMES[ab], NAMES[later["ability"]]), rule)
            m = re.search(r"vs DC (\d+)", roll)
            want = self.spell_dc(caster)
            party = getattr(self.sim, "party", None)
            ok = {want, a.get("dc")}                             # the DC now, or the one it was cast with (Innate Sorcery)
            if want is not None and party is not None and hasattr(party, "innate_on"):
                ok.add(want + party.innate_on(me))
            if m and want is not None and int(m.group(1)) not in ok:
                self.note(spell, "used DC %s; %s's spell save DC is %d (8 + Proficiency Bonus + spellcasting ability)."
                          % (m.group(1), caster["name"], want), "Spell Save DC")
            saved = bool(re.search(r"-> success", roll))

        # -- damage within its dice: half or none on a success
        dealt = sum(x for s, i, x in self.hurts[before["hurt_n"]:] if s == me and i == t)
        if dealt:
            if later["dice"]:
                scale = rules.get("scaling") or {}
                most = _dice_max(later["dice"]) + _dice_max(scale.get("dice_per_level")) * max(0, slot - scale.get("above", slot))
            else:
                most = self.most_damage(caster, rules, slot, t, False) if rules["damage"] else 0
            limit = most if not saved else most // 2 if later["half"] else 0
            if dealt > limit:
                self.note(spell, "dealt %d damage to %s%s; the most it can deal is %d." % (
                    dealt, nm, " on a successful save" if saved else "", limit), rule)

        # -- its conditions only, none on a success
        allowed = set(rules["conditions"]) | {x for c in rules["conditions"] for x in INCLUDES.get(c, ())}
        for cnd, info in sorted((after["cond"].get(t) or {}).items()):
            if cnd in (before["cond"].get(t) or {}) or (info or {}).get("by") != me or cnd not in CONDITIONS:
                continue
            if saved:
                self.note(spell, "gave %s the %s condition, though it saved." % (nm, cnd), rule)
            elif cnd not in allowed:
                self.note(spell, "gave %s the %s condition, which it doesn't give." % (nm, cnd), rule)
            elif cnd in (rules.get("lasts") or {}):
                self.time_condition(t, cnd, me, spell, rules["lasts"][cnd], before["serial"], rules)
        return self.notes[start:]

    def where(self):
        """Where every creature stands, and who is down."""
        import sim_messages
        state = sim_messages.state(self.sim, 0, None)
        return {"pos": {c["id"]: (c["x"], c["y"]) for c in state["combatants"]},
                "down": {c["id"]: c["down"] for c in state["combatants"]}}

    def area_turn(self, ended):
        """A turn ended (`ended`'s; None at the fight's start): a creature a lasting area should have asked for its save
        during it and didn't is called out: it ended its turn inside, started it inside, or came inside (by its own
        move or the area's). The strict reading of the area, a creature not down; then a new turn begins.
        Only a turn the referee saw alone, in step with the engine, is judged: in a simulator run the fake FG can play
        the next creatures' turns while a turn-end rule settles its dice (the engine's turn count then moves by more
        than one), and the run loop's turns lag behind the engine's until it catches up (the count stands still)."""
        was, now = self.window_at, self.where()
        held = {k for k in self.areas if self.holds(*k)}
        moved = self.serial() - was["serial"] - 1 if was is not None else 0
        alone = was is not None and moved == 0 and self.lag == 0
        self.lag += moved
        self.judged += int(alone and bool(held))
        for (me, spell) in sorted(held & set((was or {}).get("held") or {}) if alone else (), key=str):
            if now["down"].get(me) or was["down"].get(me):
                continue                                         # an Unconscious caster loses its Concentration
            rules = spell_rules.spell(spell)
            later, area, a = spell_rules.later(rules), rules["area"], self.areas[(me, spell)]
            if not later or not area or (area["origin"] == "point" and not a["origin"]):
                continue
            effect, then = ({"origin": a["origin"]}, {"origin": was["held"][(me, spell)] or a["origin"]}) \
                if area["origin"] == "point" else ({}, {})
            saved = {s["t"] for s in self.area_saves if (s["spell"], s["by"], s["window"]) == (spell, me, self.window)}
            # SPELL-EFFECTS-01: a turn-start save is rolled as the engine starts the turn (the stand-in FG's nextActor),
            # before the run loop opens that turn's window: it is in the window before
            began = {s["t"] for s in self.area_saves if (s["spell"], s["by"], s["window"], s["when"]) ==
                     (spell, me, self.window - 1, "start")}
            for i in sorted(now["pos"]):
                if i in saved or now["down"].get(i) or was["down"].get(i) or i not in was["pos"] \
                        or not self.affects(later, me, i, area, must=True) or self.spared(i, rules):
                    continue
                inside = self.in_area(area, me, i, now, effect, False)
                if inside is None:
                    break                                        # a shape the referee doesn't read
                why = None
                if inside and i == ended and "end" in later["when"]:
                    why = "it ended its turn inside"
                elif inside and me == ended and "your_end" in later["when"]:
                    why = "it was inside at the end of %s's turn" % self.sim.by_id(me)["name"]
                elif i == ended and "start" in later["when"] and i not in began and self.in_area(area, me, i, was, then, False):
                    why = "it started its turn inside"
                elif inside and not self.in_area(area, me, i, was, then, True):
                    if "enter" in later["when"] and was["pos"][i] != now["pos"][i]:
                        why = "it entered it"
                    elif "moved" in later["when"] and (was["pos"].get(me) != now["pos"].get(me) if area["origin"] != "point"
                                                       else then.get("origin") != effect.get("origin")):
                        why = "the %s moved onto it" % area["shape"].capitalize()
                if why:
                    self.note(spell, "never gave %s its save, though %s." % (self.sim.by_id(i)["name"], why),
                              _first_sentence(later["text"]))
        self.window += 1
        self.area_saves = [s for s in self.area_saves if s["window"] >= self.window - 2]
        self.window_at = dict(now, held={k: list(self.areas[k]["origin"] or []) or None for k in held}, serial=self.serial())

    def spared(self, i, rules):
        """A creature the area can't hurt: immune to every condition it gives, and it deals no damage."""
        gm = self.sim.gm_rules
        return bool(rules["conditions"]) and not rules["damage"] and gm is not None and \
            all(gm.cond_immune(i, c) for c in rules["conditions"])

    # ------------------------------------------------------------------ an attack's save rider (REFEREE-02)
    @contextlib.contextmanager
    def watch_rider(self, src, tgt, action):
        """An attack's save rider, after the hit, while the engine resolves it (sim/gm_rules.py save_rider; a
        character's rider the same way, its action written like a stat block's): the state before, the check after."""
        w = {"notes": []}
        if not RIDER.search((action or {}).get("desc") or ""):
            yield w
            return
        before = self.snapshot(src)
        start = len(self.sim.lines)
        yield w
        w["notes"] = self.check_rider(src, tgt, action, before, self.own_lines(start))

    def rider_spares(self, desc, tgt):
        """Who the rider leaves alone, in the stat block's words: "If the target is a creature that isn't an Undead or
        elf"; "a non-Undead creature"; "If the target is a Humanoid" (only them). Returns why, or None."""
        tc = self.sim.by_id(tgt)
        kind = (re.findall(r"\w+", str(tc.get("type") or ("humanoid" if tc.get("pc") else ""))) or [""])[0].lower()
        elf = bool(tc.get("fey_ancestry") or "elf" in str(tc.get("species", "")).lower())
        m = re.search(r"If the target is (?:an? )?(.+?), (?:it|the target)\b", desc)
        if not m:
            return None
        who = m.group(1)
        named = re.search(r"isn't an? (.+)", who) or re.search(r"non-(\w+)", who)
        spared = [w for w in re.findall(r"\w+", named.group(1)) if w not in ("or", "and", "a", "an")] if named else []
        for k in (s.lower() for s in spared):
            if k == kind or (k == "elf" and elf):
                return "it is %s %s" % ("an" if k[0] in "aeiou" else "a", k.capitalize() if k != "elf" else k)
        only = re.fullmatch(r"(Aberration|Beast|Celestial|Construct|Dragon|Elemental|Fey|Fiend|Giant|Humanoid|"
                            r"Monstrosity|Ooze|Plant|Undead)", who)
        if only and kind and only.group(1).lower() != kind:
            return "it is not a %s" % only.group(1)
        return None

    def check_rider(self, src, tgt, action, before, lines):
        """Compare one rider save with the stat block's words. Returns the notes it wrote."""
        desc, sp = action.get("desc") or "", action.get("save") or {}
        m = RIDER.search(desc)
        start = len(self.notes)
        self.rider_checked.append((src, action["name"], tgt))
        after = self.snapshot(src)
        nm = self.sim.by_id(tgt)["name"]
        name = "%s's %s" % (self.sim.by_id(src)["name"], action["name"])
        ability, dc, failure = ABILITY[m.group(1)], int(m.group(2)), m.group(3)
        rule = "%s Saving Throw: DC %d. %s" % (m.group(1), dc, _first_sentence(failure))
        if sp and (sp.get("save") != ability or sp.get("dc") != dc):
            self.note(name, "was read as DC %s %s; its stat block says DC %d %s." % (
                sp.get("dc"), NAMES.get(sp.get("save"), sp.get("save")), dc, m.group(1)), rule)

        # -- who rolls: the target, unless the rider spares it
        rolls = [(r.group(1), ABILITY[r.group(2)], ln) for ln in lines
                 for r in [re.match(r"(.+?)" + SAVE_LINE + r" against " + re.escape(action["name"]) + r"\b", ln)] if r]
        spare = self.rider_spares(desc, tgt)
        mine = [x for x in rolls if x[0] == nm]
        for who, _, _ in rolls:
            if who != nm:
                self.note(name, "had %s roll the save; the target, %s, makes it." % (who, nm), rule)
        gained = {c: info for c, info in (after["cond"].get(tgt) or {}).items()
                  if c not in (before["cond"].get(tgt) or {}) and (info or {}).get("by") == src}
        dealt = sum(x for s, i, x in self.hurts[before["hurt_n"]:] if s == src and i == tgt)
        if spare:
            if mine or gained or dealt:
                self.note(name, "affected %s, though %s: the rider spares it." % (nm, spare), rule)
            return self.notes[start:]
        if not mine:
            self.note(name, "hit %s but never gave it its %s save." % (nm, m.group(1)), rule)
            saved = None
        else:
            _, ab, roll = mine[0]
            if ab != ability:
                self.note(name, "asked %s for a %s save; its stat block says %s." % (nm, NAMES[ab], m.group(1)), rule)
            used = re.search(r"vs DC (\d+)", roll)
            if used and int(used.group(1)) != dc:
                self.note(name, "used DC %s; its stat block says DC %d." % (used.group(1), dc), rule)
            saved = bool(re.search(r"-> success", roll))

        # -- the effect: its Failure's conditions and damage, nothing on a success
        named = [c for c in CONDITIONS if re.search(r"\b%s\b" % c, failure)]
        allowed = set(named) | {x for c in named for x in INCLUDES.get(c, ())}
        most = sum(_dice_max(d) + _flat(d) for d in DAMAGE.findall(failure))
        if dealt > (0 if saved else most):
            self.note(name, "dealt %d damage to %s%s; the most it can deal is %d." % (
                dealt, nm, " on a successful save" if saved else "", 0 if saved else most), rule)
        gm = self.sim.gm_rules
        for cnd in sorted(gained):
            if cnd not in CONDITIONS:
                continue
            if saved:
                self.note(name, "gave %s the %s condition, though it saved." % (nm, cnd), rule)
            elif cnd not in allowed:
                self.note(name, "gave %s the %s condition, which it doesn't give." % (nm, cnd), rule)
            else:
                lasts = self.rider_lasts(failure)
                if lasts:
                    self.time_condition(tgt, cnd, src, name, lasts, before["serial"])
        if saved is False and not re.search(r"\b(?:Tiny|Small|Medium|Large|Huge) or smaller\b", desc):
            for cnd in named:
                if cnd not in gained and not (gm and (gm.cond_immune(tgt, cnd) or gm.cond.get(tgt, {}).get(cnd))):
                    self.note(name, "%s failed its save but doesn't have the %s condition." % (nm, cnd), rule)
        return self.notes[start:]

    @staticmethod
    def rider_lasts(failure):
        """How long the Failure's condition lasts, in the timing's terms: "until the end of its next turn"; "until the
        end of the homunculus's next turn"; "for 1 minute"."""
        m = re.search(r"until the (start|end) of (its|the [\w ]+?'s) next turn", failure)
        if m:
            return {"until": {"who": "target" if m.group(2) == "its" else "caster", "when": m.group(1)}}
        m = re.search(r"for (\d+) (round|minute)", failure)
        return {"rounds": int(m.group(1)) * (10 if m.group(2) == "minute" else 1)} if m else None

    # ------------------------------------------------------------------ creatures' saving-throw actions
    @contextlib.contextmanager
    def watch_action(self, me, action, aim=None):
        """A creature's saving-throw action (THREAT-02: its stat block, read by tools/srd_library.py into
        action["save"]; or the simulator's own Recharge breath and Death Burst tables) while the simulator, as GM,
        resolves it: the state before, the check after. aim: where it was aimed (origin, toward; the target of a
        one-creature action)."""
        w = {"effect": dict(aim or {}), "notes": []}
        if me in self.open or not (action or {}).get("save"):
            yield w
            return
        before = self.snapshot(me)
        start = len(self.sim.lines)
        self.open.append(me)
        try:
            yield w
        finally:
            self.open.remove(me)
        w["notes"] = self.check_action(me, action, before, w["effect"], self.own_lines(start))

    def action_area(self, sp):
        """The stat block's area in the referee's terms (None: one creature)."""
        ar = sp["area"]
        return {"cone": lambda: {"shape": "cone", "size_ft": ar["size"], "origin": "self"},
                "line": lambda: {"shape": "line", "size_ft": ar["length"], "width_ft": ar["width"], "origin": "self"},
                "emanation": lambda: {"shape": "emanation", "size_ft": ar["size"], "origin": "self"},
                "sphere": lambda: {"shape": "sphere", "size_ft": ar["radius"], "origin": "point"},
                }.get(ar["shape"], lambda: None)()

    def check_action(self, me, action, before, effect, lines):
        """Compare one saving-throw action with its stat block: the DC, the area and who was in it, every creature
        inside saving, the damage within its dice, its conditions. Returns the notes it wrote."""
        name, sp = action["name"], action["save"]
        start = len(self.notes)
        self.checked.append((me, name))
        after = self.snapshot(me)
        rule = _first_sentence(action.get("desc") or "") or "%s's %s" % (self.sim.by_id(me)["name"], name)
        text = " ".join(lines)
        side = self.sim.by_id(me).get("side")
        enemies = sp["area"].get("enemies")

        # -- the save DC: the stat block's own number
        said = re.search(r"\bDC (\d+)", action.get("desc") or "")
        want = int(said.group(1)) if said else sp["dc"]
        if said and want != sp["dc"]:
            self.note(name, "was read as DC %d; its stat block says DC %d." % (sp["dc"], want), rule)
        used = set()
        for line in lines:          # its own lines; the simulator's own tables write their saves without the name
            if name in line or (not action.get("desc") and "Concentration" not in line and re.search(
                    r" (Strength|Dexterity|Constitution|Intelligence|Wisdom|Charisma) save: ", line)):
                # a grapple's "escape DC 14" (the Salamander's Constrict) is not the save DC (GM 2026-10-27)
                used |= {int(x) for x in re.findall(r"(?<!escape )\bDC (\d+)", line)}
        for dc in sorted(used - {want}):
            self.note(name, "used DC %d; its stat block says DC %d." % (dc, want), rule)

        # -- the area, and who was in it
        touched = self.touched(me, before, after)
        area = self.action_area(sp)
        if area is None:                                      # one creature within range
            allowed = {effect["target"]} if effect.get("target") is not None else None
            for t in allowed or ():
                ft = self.gap_ft(me, t, before)
                if ft > sp["area"]["range"] + 0.01:
                    self.note(name, "reached %s at %d ft; its range is %d ft." % (self.sim.by_id(t)["name"], ft,
                                                                                   sp["area"]["range"]), rule)
            inside = set()
        else:
            if area["origin"] == "point" and effect.get("origin"):
                here, o = before["pos"][me], effect["origin"]
                ft = (max(abs(o[0] - here[0]), abs(o[1] - here[1])) - (self.span(me) - 1) / 2) * self.units()
                if ft > sp["area"]["range"] + 0.01:
                    self.note(name, "was placed %d ft away; its range is %d ft." % (ft, sp["area"]["range"]), rule)
            allowed, inside = set(), set()
            for i in before["pos"]:
                if i == me:
                    continue
                if enemies and self.sim.by_id(i).get("side") == side:
                    continue
                lenient = self.in_area(area, me, i, before, effect, True)
                if lenient is None:
                    allowed = inside = None              # a shape the referee doesn't read: it says nothing
                    break
                if lenient:
                    allowed.add(i)
                if not before["down"].get(i) and self.in_area(area, me, i, before, effect, False):
                    inside.add(i)
        if allowed is not None:
            for i in sorted(set(touched) - allowed):
                self.note(name, "affected %s, outside its area." % self.sim.by_id(i)["name"], rule)
        for i in sorted(inside or ()):
            nm = self.sim.by_id(i)["name"]
            if not re.search(re.escape(nm) + r"(?!\d) \w+ save", text):
                self.note(name, "never gave %s its saving throw, though it was inside." % nm, rule)

        # -- damage within the dice
        most = sum(_dice_max(sp.get(k)) + _flat(sp.get(k)) for k in ("dmg", "dmg2") if sp.get(k))
        for i in sorted(touched):
            dealt = sum(a for s, t, a in self.hurts[before["hurt_n"]:] if s == me and t == i)
            vulnerable = str(self.sim.by_id(i).get("damagevulnerabilities") or "").split(";")[0].lower()
            limit = most * (2 if any(sp.get(k) and sp[k] in vulnerable for k in ("type", "type2")) else 1)
            if dealt > limit:
                self.note(name, "dealt %d damage to %s; the most it can deal is %d." % (dealt, self.sim.by_id(i)["name"], limit),
                          rule)

        # -- conditions
        allowed_conds = {k["name"] for k in sp.get("conditions") or []}
        allowed_conds |= {x for c in allowed_conds for x in INCLUDES.get(c, ())}
        until = {k["name"]: k["until"] for k in sp.get("conditions") or [] if k.get("until")}
        for i, given in sorted(touched.items()):
            for cnd in sorted(given):
                if cnd in CONDITIONS and cnd not in allowed_conds:
                    self.note(name, "gave %s the %s condition, which it doesn't give." % (self.sim.by_id(i)["name"], cnd), rule)
                elif cnd in until:                                     # "until the start of the lion's next turn"
                    u = dict(until[cnd], who="caster" if until[cnd]["who"] == "self" else until[cnd]["who"])
                    self.time_condition(i, cnd, me, name, {"until": u}, before["serial"])
        return self.notes[start:]

    # ------------------------------------------------------------------ how long conditions last
    def time_condition(self, t, cond, by, source, lasts, serial, rules=None):
        """Watch a condition a spell or an action gave until its words say it ends."""
        gm = self.sim.gm_rules
        info = ((gm.cond.get(t) or {}).get(cond)) if gm else None
        if info is None or any(g["info"] is info for g in self.given):
            return
        dur = (rules or {}).get("duration") or {}
        m = re.search(r"(\d+) (round|minute|hour)", dur.get("text") or "")
        self.given.append({"t": t, "cond": cond, "info": info, "by": by, "source": source, "lasts": lasts, "serial": serial,
                           "round": self.round(), "conc": bool(dur.get("concentration")),
                           "rounds": int(m.group(1)) * {"round": 1, "minute": 10, "hour": 600}[m.group(2)] if m else None})
        self.timed += 1

    def round(self):
        return int(self.sim.S.round() or 0)

    def adopt(self, serial):
        """Conditions given outside a watched cast or action: a spell's later stage (Sleep's Unconscious, given when
        its target fails the second save) and an attack's save rider (the Ghoul's Paralysis), from the engine's record of
        who gave them and why."""
        for t, conds in list(self.sim.gm_rules.cond.items()):
            for name, info in list(conds.items()):
                if not info or info.get("by") is None or any(g["info"] is info for g in self.given):
                    continue
                rules = spell_rules.spell(info["spell"]) if info.get("spell") else None
                if rules and name in (rules.get("lasts") or {}):
                    self.time_condition(t, name, info["by"], info["spell"], rules["lasts"][name], serial, rules)
                elif info.get("lib") and info.get("until"):
                    u = dict(info["until"], who="caster" if info["until"]["who"] == "self" else info["until"]["who"])
                    self.time_condition(t, name, info["by"], "%s's %s" % (self.sim.by_id(info["by"])["name"], name),
                                        {"until": u}, serial)

    def turn_changed(self, ended, started):
        """The run loop moved on to `started`'s turn, after the engine's turn-end rules for `ended` (None: none ran)
        and its turn-start rules for `started`: every condition past its time must be gone by now."""
        if self.sim.gm_rules is None:
            return
        now = self.serial()
        prev = self.turn if self.turn and ended is not None and self.turn[0] == ended else (ended, None)
        self.area_turn(ended)                                # REFEREE-02: the saves a lasting area asked this turn
        self.adopt(prev[1] if prev[1] is not None else now)
        for g in list(self.given):
            if (self.sim.gm_rules.cond.get(g["t"]) or {}).get(g["cond"]) is not g["info"]:
                self.given.remove(g)                         # it ended (a new one is another record)
                continue
            why = self.overdue(g, prev, started, now)
            if why and not self.covered(g):
                self.given.remove(g)
                self.note(g["source"], "%s still has the %s condition after %s." % (self.sim.by_id(g["t"])["name"], g["cond"], why),
                          "%s %s" % (g["cond"], self.lasts_text(g)))
        self.turn = (started, now)

    def overdue(self, g, prev, started, now):
        """Why the condition should have ended by now, or None."""
        lasts, party = g["lasts"], self.sim.party
        if lasts.get("spell"):
            if g["conc"]:                                    # a Concentration spell: while its caster holds it
                caster = self.sim.by_id(g["by"])
                if party and caster.get("pc") and party.concentrates(g["by"]) != g["source"]:
                    return "%s ended" % g["source"]
                return None
            if g["rounds"] and self.round() > g["round"] + g["rounds"]:
                return "%s's duration ran out" % g["source"]
            return None
        if lasts.get("rounds"):
            return "%d rounds" % lasts["rounds"] if self.round() > g["round"] + lasts["rounds"] else None
        u = lasts.get("until")
        if not u:
            return None
        if u["who"] == "current":
            return "the end of the turn it was given" if prev[1] is not None and prev[1] >= g["serial"] else None
        x = g["t"] if u["who"] == "target" else g["by"]
        if u["when"] == "end" and prev[0] == x and prev[1] is not None and prev[1] > g["serial"]:
            return "the end of %s's turn" % self.sim.by_id(x)["name"]
        if u["when"] == "start" and started == x and now > g["serial"]:
            return "the start of %s's turn" % self.sim.by_id(x)["name"]
        return None

    def covered(self, g):
        """Another condition from the same giver brings this one with it (Sleep's Unconscious keeps Incapacitated)."""
        conds = self.sim.gm_rules.cond.get(g["t"]) or {}
        return any(g["cond"] in INCLUDES.get(n, ()) and (info or {}).get("by") == g["by"] for n, info in conds.items()
                   if n != g["cond"])

    @staticmethod
    def lasts_text(g):
        lasts = g["lasts"]
        if lasts.get("spell"):
            return "for the duration (until %s ends)" % g["source"]
        if lasts.get("rounds"):
            return "for %d rounds" % lasts["rounds"]
        u = lasts["until"]
        if u["who"] == "current":
            return "until the end of the current turn"
        return "until the %s of %s next turn" % (u["when"], "its" if u["who"] == "target" else "the giver's")

    # ------------------------------------------------------------------ the numbers
    def spell_dc(self, c):
        """The character sheet's spell save DC, or 8 + Proficiency Bonus + the spellcasting ability modifier."""
        if c.get("spell_dc") is not None:
            return int(c["spell_dc"])
        if c.get("spell_mod") is None:
            return None
        return 8 + proficiency_bonus(c.get("level")) + int(c["spell_mod"])

    def most_healing(self, caster, rules, slot_level, blessed=False):
        """REFEREE-02: the most Hit Points the spell restores to one creature: its dice (and a higher slot's) or its
        number (Heal's 70, +10 a slot level), the caster's modifier when it adds one, Disciple of Life (Life 3: 2 + the
        slot's level); blessed: the caster also regains Blessed Healer's (Life 6). None: no limit read (Power Word Heal)."""
        h, scale = rules["healing"], rules.get("scaling") or {}
        expr = str(h.get("dice") or "")
        if not re.match(r"\d", expr):
            return None
        above = max(0, slot_level - scale.get("above", rules["level"]))
        most = _dice_max(expr) + _flat(expr) if "d" in expr else int(re.match(r"\d+", expr).group())
        most += _dice_max(scale.get("dice_per_level")) * above
        flat = re.search(r"healing increases by (\d+) for each", scale.get("text") or "")
        if flat and "d" not in expr:
            most += int(flat.group(1)) * max(0, slot_level - rules["level"])
        if h.get("plus_mod"):
            most += int(caster.get("spell_mod", 5))
        if caster.get("disciple_of_life") and rules["level"] > 0:
            most += 2 + slot_level
        if blessed and caster.get("blessed_healer"):
            most += 2 + slot_level
        return most

    def target_limit(self, rules, slot_level, caster):
        t, scale = rules["targets"], rules.get("scaling") or {}
        if not t.get("max") or t.get("kind") not in ("creature", "creatures"):
            return None
        most = t["max"] + (scale.get("extra_targets_per_level", 0) * max(0, slot_level - scale.get("above", slot_level)))
        return max(most, self.strikes(rules, slot_level, caster))

    def strikes(self, rules, slot_level, caster):
        """How many darts, rays or beams it makes (1 for a spell that strikes once)."""
        n = rules.get("count")
        if not n:
            return 1
        if n.get("levels"):
            lvl = int(caster.get("level") or 1)
            return n["levels"][2] if lvl >= 17 else n["levels"][1] if lvl >= 11 else n["levels"][0] if lvl >= 5 else n["n"]
        return n["n"] + n.get("per_level", 0) * max(0, slot_level - n.get("above", slot_level))

    def most_damage(self, caster, rules, slot_level, target, crit, hexed=False, marked=False):
        level, scale, dmg = rules["level"], rules.get("scaling") or {}, rules["damage"]
        first = dmg[0]["dice"]
        if level == 0 and scale.get("levels"):
            lvl = int(caster.get("level") or 1)
            first = scale["levels"][2] if lvl >= 17 else scale["levels"][1] if lvl >= 11 else scale["levels"][0] if lvl >= 5 else first
        dice = _dice_max(first)
        if len({d["dice"] for d in dmg}) > 1 or spell_rules.together(rules):   # Ice Knife, Flame Strike: both;
            dice += sum(_dice_max(d["dice"]) for d in dmg[1:])                 # Spirit Guardians: one or the other
        if scale.get("dice_per_level"):                          # SPELLS-4-9: on each part its words name
            dice += _dice_max(scale["dice_per_level"]) * max(0, slot_level - scale.get("above", level)) *                 max(1, len(spell_rules.scaled_parts(rules)))
        dice += sum(_dice_max(x["dice"]) for x in rules.get("extra") or [])
        flat = _flat(first) + (int(caster.get("spell_mod", 5)) if any(d.get("plus_mod") for d in dmg) else 0)
        if any(caster.get(k) and spell == rules["name"] for k, spell in FEATURES.items()):
            flat += int(caster.get("spell_mod", 5))
        if caster.get("elemental_affinity"):                     # GM 2026-10-23: Draconic Sorcery's Elemental Affinity
            flat += max(1, int(caster.get("cha_mod", caster.get("spell_mod", 1)) or 1))
        if hexed:                                                # Hex: its 1d6 on every hit the caster lands
            hx = spell_rules.spell("Hex")
            dice += _dice_max(hx["damage"][0]["dice"]) if hx and hx["damage"] else 6
        if marked:                                               # Hunter's Mark: its 1d6 Force on every hit
            hm = spell_rules.spell("Hunter's Mark")
            dice += _dice_max(hm["damage"][0]["dice"]) if hm and hm["damage"] else 6
        most = self.strikes(rules, slot_level, caster) * (dice * (2 if crit else 1) + flat)
        vulnerable = str(self.sim.by_id(target).get("damagevulnerabilities") or "").split(";")[0].lower()
        if any(d["type"] in vulnerable for d in dmg):
            most *= 2
        return most

    # ------------------------------------------------------------------ geometry (squares; feet = squares x units)
    def span(self, i):
        return self.sim.size_sq(i)

    def gap_ft(self, a, b, before):
        """Feet from the edge of a's space to the edge of b's (5-foot diagonals; adjacent = 5)."""
        (ax, ay), (bx, by) = before["pos"][a], before["pos"][b]
        gap = max(abs(ax - bx), abs(ay - by)) - ((self.span(a) + self.span(b)) / 2 - 1)
        return max(0, gap) * self.units()

    def cells(self, p, span):
        """The centres of the squares a creature's space covers."""
        k = [(j - (span - 1) / 2) for j in range(span)]
        return [(p[0] + dx, p[1] + dy) for dx in k for dy in k]

    def allowed(self, me, cmd, rules, before, effect, lenient=True):
        """The creatures the spell may touch: the target(s) (and the creatures its text names around the target), or
        those inside its area (the chosen ones when it says "of your choice"). None when the referee can't tell (a
        spell it has no shape for). lenient: the grid reading (who it may touch); else the strict one (who must save)."""
        if cmd.get("target") is not None or cmd.get("targets"):
            out = set(cmd.get("targets") or []) | ({cmd["target"]} if cmd.get("target") is not None else set())
            near = rules.get("near")
            if near:                                              # Ice Knife: each creature within 5 ft of the target
                out |= {i for t in list(out) for i in before["pos"] if i != t and self.gap_ft(t, i, before) <= near["ft"]}
            return out
        area = rules["area"]
        if not area:
            return None
        inside = set()
        for i in before["pos"]:
            if not lenient and before["down"].get(i):
                continue
            at = self.in_area(area, me, i, before, effect, lenient)
            if at is None:
                return None                      # a shape the referee doesn't read: it says nothing rather than guess
            if at:
                inside.add(i)
        if area["origin"] == "self" and area["shape"] != "emanation":
            inside.discard(me)
        if rules["targets"]["choice"] and effect.get("targets") is not None:
            return inside & set(effect["targets"])
        return inside

    def in_area(self, area, me, i, before, effect, lenient):
        """Is creature i inside the area? True / False, or None for a shape not read."""
        u, here, p = self.units(), before["pos"][me], before["pos"][i]
        if len(effect.get("origins") or []) > 1:                 # SPELLS-4-9: Meteor Swarm's Spheres, each creature once
            found = [self.in_area(area, me, i, before, dict(effect, origins=None, origin=o), lenient) for o in effect["origins"]]
            return None if None in found else any(found)
        origin = tuple(effect.get("cube_origin") or effect.get("origin") or here)   # a Cube drawn from its edge
        size = area["size_ft"]
        party = self.sim.party
        froms = [origin] + ([here] if tuple(here) != origin else [])
        walled = [party.walled(o, p) for o in froms]     # a wall shields a creature, as in the engine
        if (all(walled) if lenient else any(walled)):
            return False
        if effect.get("ring"):                                   # group 2: Wall of Fire's ring: the squares it stands on
            ring = {tuple(q) for q in effect.get("wall") or []}
            return any((int(round(q[0])), int(round(q[1]))) in ring for q in self.cells(p, self.span(i)))
        pts = self.cells(p, self.span(i)) if lenient else [p]
        shape = area["shape"]
        if shape in ("sphere", "cylinder"):
            if lenient:                                              # 5-foot diagonals: a square box
                return any(max(abs(q[0] - origin[0]), abs(q[1] - origin[1])) * u <= size + 0.01 for q in pts)
            return math.hypot(p[0] - origin[0], p[1] - origin[1]) * u <= size + 0.01
        if shape == "emanation":                                     # from the edge of the caster's space
            if lenient:
                return self.gap_ft(me, i, before) <= size + 0.01
            return (math.hypot(p[0] - here[0], p[1] - here[1]) - (self.span(me) - 1) / 2) * u <= size + 0.01
        if shape in ("cone", "line"):
            toward = effect.get("toward")
            if toward is None:
                a = math.radians(effect.get("angle_deg", 0))
                toward = (math.cos(a), math.sin(a))
            n = math.hypot(*toward) or 1.0
            ux, uy = toward[0] / n, toward[1] / n
            # a Line runs from the edge of the caster's space: from its centre, as far again as half its space
            reach = size + (self.span(me) / 2 if lenient else (self.span(me) - 1) / 2) * u if shape == "line" else size
            half = area.get("width_ft", 5) / 2
            for q in pts:
                vx, vy = q[0] - origin[0], q[1] - origin[1]
                along, across = (vx * ux + vy * uy) * u, abs(vx * uy - vy * ux) * u
                if not 0 < along <= reach + 0.01:
                    continue
                if shape == "cone" and across <= along / 2 + 0.01:
                    return True
                if shape == "line" and (across <= half + 0.01 if lenient else across < half - 0.01):
                    return True
            return False
        if shape == "cube":                                          # its squares' edges: [x0, y0, x1, y1]
            box = effect.get("cube")
            if not box:
                return None
            x0, y0, x1, y1 = box
            if lenient:
                return any(x0 - 0.01 <= q[0] <= x1 + 0.01 and y0 - 0.01 <= q[1] <= y1 + 0.01 for q in pts)
            return x0 + 0.01 < p[0] < x1 - 0.01 and y0 + 0.01 < p[1] < y1 - 0.01
        return None                    # a shape the referee doesn't read: it says nothing rather than guess

    def check_cube(self, name, area, me, before, effect):
        """A Cube is as big as the spell says, and one "from you" starts at the caster's space."""
        x0, y0, x1, y1 = effect["cube"]
        u, caster = self.units(), self.sim.by_id(me)
        w, h = (x1 - x0) * u, (y1 - y0) * u
        if abs(w - area["size_ft"]) > 0.01 or abs(h - area["size_ft"]) > 0.01:
            self.note(name, "its Cube is %g by %g ft; the spell's is %d ft." % (w, h, area["size_ft"]), "Cube")
        if area["origin"] == "self":
            (hx, hy), half = before["pos"][me], self.span(me) / 2
            gap = max(x0 - (hx + half), (hx - half) - x1, y0 - (hy + half), (hy - half) - y1)
            if abs(gap) > 0.01:
                self.note(name, "its Cube doesn't start at %s; a Cube from the caster touches the caster's space."
                          % caster["name"], "Cube: its point of origin lies on a face of the Cube")
