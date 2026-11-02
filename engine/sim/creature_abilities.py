"""Documents page goals 6 and 7 (GM 2026-10-26: "6 (creature spellcasting) and 7 (legendary actions and special
traits)"): the rest of an SRD 5.2.1 creature's stat block, played by the engine on the Python creature turns
(sim/creature_turns.py) and checked by the rules referee (sim/referee.py) from the start.

Each creature's abilities come from its block in sim/creatures/srd_library.json (by its srd_name, else its name without
the number), the block its attacks come from:

- Spellcasting: the spell list with its DC, attack bonus and uses (At Will, N/Day, N/Day Each, "(level N version)").
  A spell is cast from its rules (sim/spell_rules.py: the SRD 5.2.1 rule sheet the referee reads): spell attacks (rays
  too), saving throws for damage or conditions (one creature, a Sphere, Cylinder, Cone, Line or Emanation), healing,
  Magic Missile's darts, Bless, and Shield as a Reaction. A spell that is an Action is one more choice on the
  creature's list (the model, or the scripted chooser by its expected effect, picks it); a Bonus Action spell heals an
  ally that needs it; a Concentration spell is held until the creature's Concentration ends (a save when it takes
  damage, DC 10 or half the damage). Spells with no effect in a fight (Detect Magic, Light, Scrying ...) and the ones
  the engine has no way to hold (walls such as Wall of Fire, summons, Charmed, teleports) stay text for the GM, each
  listed with the reason (ruled()). Group 1 (GM 2026-10-27): the lasting areas of sim/spell_zones.py (Entangle,
  Moonbeam, Insect Plague ...) are cast there at the spot with the most foes and none of the caster's side, and Spirit
  Guardians around the caster as the Cleric's (sim/party.py); a creature holding one doesn't cast another over it, and
  waits with Bless when its area spell would end it. A Spellcasting with no DC in its text (the Priest) uses 8 + its
  Proficiency Bonus + its spellcasting modifier.
- Legendary actions: the uses (regained at the start of its turn), taken one at a time right after another creature's
  turn: an attack (with a move first when the text says so), a saving-throw effect, or a spell through Spellcasting;
  "can't take this action again until the start of its next turn" is kept; the Lair numbers are not used (no lairs).
- Traits: Pack Tactics, Bloodied Frenzy and Fury, Sunlight and Light Sensitivity, Magic Resistance, Legendary
  Resistance (N/Day), Flyby and Agile (no Opportunity Attacks), Regeneration (and what stops it), Undead Fortitude,
  Death Burst and other "explodes when it dies" saves, auras that work at the start of a creature's turn (Stench),
  Evasion. Traits about travel, senses, climbing, breathing, rebirth elsewhere or the GM's choices change nothing in a
  fight here and are listed as such.

Choices the engine makes for the creature (the scripted policy; GM 2026-10-26: the creatures play without being asked):
a limited spell when it does clearly more than its best attack, a heal on an ally at a third of its Hit Points or
fewer, Legendary Resistance on any failed save while uses remain, one legendary action after each other creature's
turn while uses remain.
"""
import contextlib, json, math, re, sys
from fractions import Fraction
from pathlib import Path

import ai_turn
import invisibility
import spell_rules

ROOT = Path(__file__).resolve().parent.parent
LIBRARY = ROOT / "sim" / "creatures" / "srd_library.json"
LIST = "combattracker.list."
_LIB = None


def proficiency(cr):
    """SRD 5.2.1 Proficiency Bonus by Challenge Rating: +2 up to CR 4, +3 for 5-8, +4 for 9-12 ... +9 for 29-30."""
    try:
        v = Fraction(str(cr or "0"))
    except (ValueError, ZeroDivisionError):
        v = Fraction(0)
    return 2 + (math.ceil(v) - 1) // 4 if v >= 1 else 2


TRAIT_ATTACK = ("Pack Tactics", "Bloodied Frenzy", "Bloodied Fury", "Sunlight Sensitivity", "Light Sensitivity")
NO_PROVOKE = ("Flyby", "Agile")
# traits that change nothing in a fight on Mythastria's maps (travel, senses, breathing, climbing, rebirth elsewhere)
NOT_IN_FIGHTS = ("Amphibious", "Spider Climb", "Water Breathing", "Hold Breath", "Web Walker", "Ice Walk", "Amorphous",
                 "Immutable Form", "Siege Monster", "Standing Leap", "Running Leap", "Jumper", "Divine Awareness",
                 "Inscrutable", "Mimicry", "Shielded Mind", "Speak with Beasts and Plants", "Probing Telepathy",
                 "Ethereal Sight", "Sense Magic", "Forbiddance", "Training", "Tunneler", "Earth Glide", "Illumination",
                 "Limited Telepathy", "Keen Senses", "Echolocation", "Beast of Burden", "Trampling Charge")
RESTORATION = re.compile(r"Restoration$|^Spirit Jar$|^Rejuvenation$")
# creature, trait the hand-made rules already play (sim/gm_rules.py): never twice
HAND_PLAYED = {("Shield Guardian", "Regeneration"), ("Azer Sentinel", "Fire Aura"), ("Zombie", "Undead Fortitude")}
CONDITION_VALUE = {"Paralyzed": 30, "Stunned": 30, "Unconscious": 30, "Incapacitated": 20, "Restrained": 12,
                   "Frightened": 10, "Blinded": 12, "Poisoned": 6, "Prone": 6}
# what a creature's cast of these spells adds to the rule sheet (keys as sim/live_general.py PLAYS)
CASTS = {
    "Command": {"choice": ["Grovel"], "rider": "command"},
    "Hold Person": {"repeat": True},
    "Hold Monster": {"repeat": True},
    "Fear": {"gm": "a Frightened creature takes the Dash action and moves away from {caster} by the safest route on each "
                   "of its turns; it saves again only when it ends its turn out of {caster}'s line of sight"},
    "Guiding Bolt": {"gm": "the next attack roll against {target} before the end of {caster}'s next turn has Advantage"},
    "Mind Spike": {"gm": "{caster} knows {target}'s location until the spell ends"},
    "Phantasmal Killer": {"gm": "{target} saves again at the end of each of its turns, taking the damage again on a "
                                "failure, while {caster} concentrates"},
    "Harm": {"gm": "{target}'s Hit Point maximum is reduced by the Necrotic damage it took"},
    "Chain Lightning": {"gm": "up to three other creatures within 30 feet of {target} are struck too (each saves)"},
    "Ice Storm": {"gm": "the ground in the Cylinder is Difficult Terrain until the end of {caster}'s next turn"},
    "Vitriolic Sphere": {"first_damage": True, "gm": "each creature that failed takes 5d4 Acid damage more at the end of "
                                                     "its next turn"},
    "Ray of Sickness": {},
}
# spells the engine leaves to the GM in a fight, and why (a spell not on the rule sheet is named as such)
GM_SPELLS = {"Counterspell": "a Reaction to another caster's spell", "Sleep": "its creatures are chosen in two stages",
             "Thunderwave": "its Cube from the caster is not drawn for creatures yet",
             "Ice Knife": "its explosion after the attack", "Spiritual Weapon": "a summoned weapon",
             "Power Word Stun": "its Hit Point threshold and later saves", "Sanctuary": "a ward the AI does not read",
             "Lesser Restoration": "it ends a condition", "Greater Restoration": "it ends a condition",
             "Dispel Magic": "it ends a spell", "Invisibility": "a lasting state the AI does not read yet"}


def library():
    global _LIB
    if _LIB is None:
        _LIB = json.loads(LIBRARY.read_text(encoding="utf-8"))["creatures"]
    return _LIB


def kind_of(c):
    return c.get("srd_name") or re.sub(r"\s+\d+$", "", str(c.get("name") or "")).strip()


def base_name(name):
    return re.sub(r"\s*\(.*?\)\s*", " ", str(name or "")).strip().rstrip(".")


def _tools():
    p = str(ROOT / "tools")
    if p not in sys.path:
        sys.path.insert(0, p)
    import srd_library
    return srd_library


# ---------------------------------------------------------------------------------------------- spellcasting text
def split_spells(text):
    """"Command (level 2 version), Detect Magic, Scorching Ray" -> [("Command", ["level 2 version"]), ...]; commas inside
    parentheses stay."""
    out, depth, cur = [], 0, ""
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur); cur = ""
        else:
            cur += ch
    out.append(cur)
    items = []
    for item in out:
        item = item.strip().rstrip(".")
        if not item:
            continue
        notes = [n.strip().lower() for n in re.findall(r"\(([^)]*)\)", item)]
        name = re.sub(r"\s*\(.*?\)", "", item).strip().rstrip("*").strip()
        if name:
            items.append((name, notes))
    return items


def parse_spellcasting(desc):
    """A Spellcasting action or trait -> {"dc", "atk", "ability", "spells": [{"name", "uses", "pool", "notes"}]}."""
    text = str(desc or "").replace("\\n", "\n")
    dc = re.search(r"spell save DC (\d+)", text)
    atk = re.search(r"([+-]\d+) to hit with spell attacks", text)
    ability = re.search(r"using (\w+) as the spellcasting ability", text)
    out = {"dc": int(dc.group(1)) if dc else None, "atk": int(atk.group(1)) if atk else None,
           "ability": ability.group(1).lower() if ability else "", "spells": []}
    for n, line in enumerate(text.split("\n")[1:]):
        head, sep, rest = line.partition(":")
        if not sep:
            continue
        h = head.strip().lower()
        if h.startswith("at will"):
            uses, each = None, True
        else:
            m = re.match(r"(\d+)/day( each)?", h)
            if not m:
                continue
            uses, each = int(m.group(1)), bool(m.group(2))
        items = split_spells(rest)
        shared = [x for x in (items[-1][1] if items else []) if x.startswith("all ")]
        for name, notes in items:
            notes = notes + [x[4:] for x in shared if x[4:] not in notes]
            out["spells"].append({"name": name, "uses": uses, "pool": None if each or len(items) == 1 else "line%d" % n,
                                  "notes": notes})
    return out


def plan(name, notes=()):
    """The rules a creature casts a spell by, or (None, why). From the rule sheet with CASTS' additions; the shapes the
    engine draws for creatures: one creature (or a ray, a dart), a Sphere or Cylinder at a point, a Cone, a Line, an
    Emanation from the caster."""
    r = spell_rules.spell(name)
    if r is None:
        return None, "not on the SRD 5.2.1 rule sheet"
    if name in GM_SPELLS:
        return None, GM_SPELLS[name]
    if name == "Spirit Guardians" or name in zone_spells():
        return zone_plan(name, notes, r), None
    extra = CASTS.get(name, {})
    special = {"Bless": "bless", "Shield": "shield", "Power Word Kill": "pwk"}.get(name)
    if r.get("unread") and not special:
        return None, "no effect in a fight" if any("utility" in u for u in r["unread"]) else "its rules are not read yet"
    t, area = r["targets"], r["area"]
    if "Charmed" in r["conditions"]:
        return None, "Charmed is not read by the creatures' AI yet"
    kind = special or ("attack" if r["attack"] and r["damage"] else "save" if r["save"] and (r["damage"] or r["conditions"])
                       else "heal" if r["healing"] and not r["damage"] else "auto" if r["damage"] and r.get("count") else None)
    if kind is None:
        return None, "no effect in a fight"
    if area and not r["duration"]["instant"] and r["damage"] and kind == "save":
        return None, "a lasting area or wall the engine doesn't play for creatures (the GM rules it)"
    shape = "creature"
    if area and t["kind"] == "area":
        shape = {"sphere": "sphere", "cylinder": "sphere", "cone": "cone", "line": "line"}.get(area["shape"])
        if area["shape"] == "emanation" and area["origin"] == "self":
            shape = "emanation"
        if shape is None:
            return None, "its %s is not drawn for creatures yet" % area["shape"]
    rng = r["range"]
    reach = rng["ft"] or (5 if rng["kind"] == "touch" else 0)
    damage = r["damage"][:1] if extra.get("first_damage") else r["damage"]
    level = r["level"]
    for n in notes:
        m = re.match(r"level (\d) version", n)
        if m:
            level = max(level, int(m.group(1)))
    time = {"action": "action", "bonus_action": "bonus", "reaction": "reaction"}.get(r["casting_time"], "")
    if "bonus action" in notes or "bonus actions" in notes:
        time = "bonus"
    if "reaction" in notes:
        time = "reaction"
    if not time:
        return None, "a casting time longer than an action"
    step = re.search(r"healing increases by (\d+) for each", (r.get("scaling") or {}).get("text") or "")
    return dict(extra, name=name, level=r["level"], slot=level, time=time, kind=kind, shape=shape, area=area,
                range_ft=reach, range_kind=rng["kind"], attack=r["attack"], save=r["save"], damage=damage,
                healing=r["healing"], conditions=list(r["conditions"]), lasts=r.get("lasts") or {},
                concentration=bool(r["duration"]["concentration"]), instant=bool(r["duration"]["instant"]),
                rounds=_rounds(r["duration"]["text"]), scaling=r.get("scaling") or {}, count=r.get("count"),
                near=r.get("near"), components=r["components"], max_targets=t.get("max") or 1, choice_targets=t["choice"],
                clarified=r.get("clarified", False), duration_text=r["duration"]["text"],
                legendary_only="legendary action" in notes,
                # what the general caster (sim/live_general.py) now also reads: parts dealt together, the parts that scale,
                # Heal's step
                together=spell_rules.together(r), area_max=t.get("max") if t["kind"] == "area" else None,
                scaled=[extra["scale_part"]] if "scale_part" in extra else spell_rules.scaled_parts(r),
                heal_step=int(step.group(1)) if step else 0, rules=r), None


def zone_spells():
    import spell_zones
    return spell_zones.SPELLS


def zone_plan(name, notes, r):
    """Group 1 (GM 2026-10-27): a lasting area a creature casts: one of sim/spell_zones.py's at a point (Entangle,
    Moonbeam, Insect Plague ...), or Spirit Guardians around the caster as the Cleric's (sim/party.py)."""
    slot = r["level"]
    for n in notes:
        m = re.match(r"level (\d) version", n)
        if m:
            slot = max(slot, int(m.group(1)))
    z = zone_spells().get(name) or {}
    return dict(name=name, level=r["level"], slot=slot, time="action", kind="zone" if z else "guardians",
                shape="zone" if z else "emanation", area=r["area"], range_ft=z.get("range_ft", r["range"]["ft"] or 0),
                range_kind=r["range"]["kind"], attack=None, save=r["save"], damage=r["damage"], healing=None,
                conditions=list(r["conditions"]), lasts={}, concentration=bool(r["duration"]["concentration"]),
                instant=False, rounds=_rounds(r["duration"]["text"]), scaling=r.get("scaling") or {}, count=None,
                near=None, components=r["components"], max_targets=1, choice_targets=False,
                clarified=r.get("clarified", False), duration_text=r["duration"]["text"],
                legendary_only="legendary action" in notes, together=[], area_max=None, scaled=[], heal_step=0, rules=r)


def _rounds(text):
    m = re.search(r"(\d+)\s*(round|minute|hour)", str(text or ""))
    return int(m.group(1)) * {"round": 1, "minute": 10, "hour": 600}[m.group(2)] if m else 0


def avg(expr):
    total = 0.0
    for n, d in re.findall(r"(\d+)d(\d+)", str(expr or "")):
        total += int(n) * (int(d) + 1) / 2
    return total + sum(int(x) for x in re.findall(r"[+-]\s*(\d+)(?!d)", str(expr or "")))


class _Fight:
    """What the general caster (sim/live_general.py) reads of a fight, for a creature's cast outside Play live."""

    def __init__(self, sim):
        self.sim, self.turn_state = sim, None

    def add_ask(self, *a):
        return 0


class Abilities:
    """Every creature's spellcasting, legendary actions and traits in one fight."""

    def __init__(self, sim):
        self.sim, self.fs, self.ct = sim, sim.S, sim.creatures
        self.gm, self.party = getattr(sim, "gm_rules", None), getattr(sim, "party", None)
        import live_general
        self.general = live_general.General(getattr(sim, "live", None) or _Fight(sim))
        self.of, self.left, self.legendary, self.traits, self.ruled = {}, {}, {}, {}, {}
        self.lr, self.blessed, self.immune_aura, self.no_regen = {}, {}, set(), set()
        self.last_types, self.shielded, self.casting = {}, set(), False
        for c in sim.sc["combatants"]:
            if not c.get("pc"):
                self.learn(c)

    # ------------------------------------------------------------------ reading a creature's block
    def learn(self, c):
        block = library().get(kind_of(c))
        cid = c["id"]
        if not block:
            return
        ruled = self.ruled.setdefault(cid, [])
        spells = None
        for a in list(block.get("actions") or []) + list(block.get("gm_text") or []):
            if base_name(a.get("name")).lower().startswith("spellcasting"):
                spells = parse_spellcasting(a.get("desc"))
                break
        if spells and self.gm and self.party:
            pb = proficiency(block.get("cr"))
            # no DC in the text (the Priest): 8 + Proficiency Bonus + the spellcasting ability's modifier (SRD 5.2.1)
            dc = spells["dc"] or (8 + pb + int(block.get("%s_mod" % spells["ability"][:3]) or 0))
            c.setdefault("spell_dc", dc)
            c.setdefault("spell_atk", spells["atk"] if spells["atk"] is not None else dc - 8)
            c.setdefault("spell_mod", dc - 8 - pb)
            entries = []
            for n, sp in enumerate(spells["spells"]):
                p, why = plan(sp["name"], sp["notes"])
                if p is None:
                    ruled.append(("Spellcasting: " + sp["name"], why))
                    continue
                key = sp["pool"] or "%s#%d" % (sp["name"], n)
                if sp["uses"] is not None:
                    self.left.setdefault(cid, {}).setdefault(key, sp["uses"])
                entries.append(dict(sp, plan=p, key=key, node="%s%s.spells.s%d" % (LIST, cid, n + 1)))
            self.of[cid] = entries
        elif spells:
            ruled.append(("Spellcasting", "the simulator plays creatures' spells in fights with the party's rules"))
        traits = {}
        for g in block.get("gm_text") or []:
            part, name = g.get("part"), base_name(g.get("name"))
            if part == "Trait":
                traits[name] = g
            elif part == "Legendary Action":
                self.learn_legendary(cid, block, g)
            elif part in ("Lair Action",):
                ruled.append((name, "a lair action (lairs are not played)"))
            elif part in ("Bonus Action", "Reaction") and not name.lower().startswith("spellcasting"):
                if not re.search(r"cast|Spellcasting", g.get("desc", "")):
                    ruled.append((name, "a %s the engine does not play yet" % part.lower()))
        self.traits[cid] = traits
        for name, g in traits.items():
            self.setup_trait(c, name, g, ruled)

    def learn_legendary(self, cid, block, g):
        name = base_name(g.get("name"))
        L = self.legendary.setdefault(cid, {"uses": 0, "left": 0, "options": [], "once": set()})
        m = re.match(r"Legendary Action Uses: (\d+)", g.get("name", ""))
        if m:
            L["uses"] = L["left"] = int(m.group(1))
            return
        desc = g.get("desc", "")
        opt = {"name": name, "desc": desc, "once": "can't take this action again until the start of its next turn" in desc,
               "cost": int((re.search(r"Costs (\d) Actions", g.get("name", "")) or [0, 1])[1])}
        sp = re.search(r"(?:uses Spellcasting to cast|casts) ([A-Z][\w' /-]+?)(?: \((level \d) version\))?(?:[.,]| using)", desc)
        atk = re.search(r"makes one ([A-Z][\w ]*?) attack", desc)
        save = _tools().parse_save(desc)[0] if "Saving Throw" in desc else None
        if sp:
            opt.update(kind="spell", spell=sp.group(1).strip(), notes=[sp.group(2).lower()] if sp.group(2) else [])
        elif atk:
            opt.update(kind="attack", attack=atk.group(1).strip(), move="half" if re.search(r"moves up to half its Speed", desc) else None)
        elif save:
            opt.update(kind="save", spec=save)
        else:
            opt.update(kind="gm")
            self.ruled.setdefault(cid, []).append(("Legendary Action: " + name, "the GM rules it"))
        L["options"].append(opt)

    def setup_trait(self, c, name, g, ruled):
        cid, kind = c["id"], kind_of(c)
        if (kind, name) in HAND_PLAYED:
            return
        if name in NO_PROVOKE:
            if name == "Agile" or self.fs.getValue(cid, "speed", "") and re.search(r"fly", str(c.get("speed") or ""), re.I):
                self.fs.setValue(cid, "sim_no_provoke", 1)
            return
        if name == "Legendary Resistance":
            m = re.search(r"\((\d+)/Day", g.get("name", ""))
            self.lr[cid] = int(m.group(1)) if m else 3
            return
        if name in TRAIT_ATTACK or name in ("Magic Resistance", "Regeneration", "Undead Fortitude", "Evasion"):
            return
        if re.search(r"explodes when it dies|when it dies", g.get("desc", "")) and "Saving Throw" in g.get("desc", ""):
            return
        if re.search(r"starts its turn in an? \d+-foot Emanation", g.get("desc", "")):
            return
        if name in NOT_IN_FIGHTS or RESTORATION.search(name):
            ruled.append((name, "nothing to rule in a fight here"))
            return
        ruled.append((name, "the GM rules this trait"))

    def has(self, cid, trait):
        return trait in self.traits.get(cid, {}) and (kind_of(self.sim.by_id(cid)), trait) not in HAND_PLAYED

    def able(self, cid):
        return not self.fs.down(cid) and not (self.gm and self.gm.incapacitated(cid)) and not self.fs.stopped(cid)

    # ------------------------------------------------------------------ traits on attack rolls
    def attack_mode(self, src, tgt, roll):
        """Pack Tactics, Bloodied Frenzy/Fury (Advantage); Sunlight and Light Sensitivity (Disadvantage); Bless (+1d4)."""
        if self.has(src, "Pack Tactics"):
            side = self.ct.side(src)
            for o in self.fs.combatants:
                if o not in (src, tgt) and self.ct.side(o) == side and self.able(o) and self.fs.distance(o, tgt) <= 5:
                    roll["bADV"] = True
                    roll.setdefault("tNotifications", []).append("[Pack Tactics]")
                    break
        if (self.has(src, "Bloodied Frenzy") or self.has(src, "Bloodied Fury")) and self.bloodied(src):
            roll["bADV"] = True
            roll.setdefault("tNotifications", []).append("[Bloodied]")
        env = getattr(self.sim, "env", None)
        if self.has(src, "Sunlight Sensitivity") and env and env.in_sunlight(src) and \
                kind_of(self.sim.by_id(src)) not in getattr(__import__("environment"), "SUNLIGHT_ATTACKS", {}):
            roll["bDIS"] = True
            roll.setdefault("tNotifications", []).append("[Sunlight Sensitivity]")
        if self.has(src, "Light Sensitivity"):
            import lighting
            if self.sim.light_level(src) == lighting.BRIGHT:
                roll["bDIS"] = True
                roll.setdefault("tNotifications", []).append("[Light Sensitivity]")
        if src in self.blessed and self.party and self.party.concentrates(self.blessed[src]) == "Bless":
            roll["nBless"] = 4

    def bloodied(self, cid):
        w, hp = self.fs.num(cid, "wounds"), self.fs.num(cid, "hptotal")
        return hp > 0 and hp - w <= hp / 2

    # ------------------------------------------------------------------ traits on saving throws
    def save_tweak(self, t, ability):
        out = {}
        if self.has(t, "Magic Resistance") and self.able(t):
            ref = getattr(self.sim, "referee", None)
            if (ref and ref.open) or self.casting:
                out["adv"] = "Magic Resistance"
        if self.has(t, "Bloodied Frenzy") and self.bloodied(t):
            out["adv"] = out.get("adv") or "Bloodied Frenzy"
        if t in self.blessed and self.party and self.party.concentrates(self.blessed[t]) == "Bless":
            out["bless"] = True
        return out

    def save_result(self, t, ok, label):
        """Legendary Resistance: a failed save becomes a success while uses remain (it uses one each time)."""
        if ok or not self.lr.get(t) or self.fs.down(t):
            return ok
        self.lr[t] -= 1
        self.sim.say("dice", "%s uses Legendary Resistance (%d left today): the failed save against %s succeeds instead" % (
            self.fs.name(t), self.lr[t], label))
        return True

    def evasion(self, real):
        def has_evasion(t):
            return real(t) or (self.has(t, "Evasion") and self.able(t))
        return has_evasion

    def fortitude(self, real):
        """Undead Fortitude for every creature that has it (the hand-made rule plays the Zombie)."""
        def fortitude(tid, damage, radiant, crit):
            if real and real(tid, damage, radiant, crit):
                return True
            if not self.has(tid, "Undead Fortitude"):
                return False
            c = self.sim.by_id(tid)
            if radiant or crit:
                self.sim.say("dice", "%s: no Undead Fortitude (%s)" % (c["name"], "Radiant damage" if radiant else "a Critical Hit"))
                return False
            dc, d20, bonus = 5 + int(damage), self.sim.rng.randint(1, 20), c.get("con_save", 0)
            ok = d20 + bonus >= dc
            self.sim.say("dice", "%s Undead Fortitude: Constitution save d20 %d %+d = %d vs DC %d -> %s" % (
                c["name"], d20, bonus, d20 + bonus, dc, "drops to 1 HP instead" if ok else "it falls"))
            return ok
        return fortitude

    # ------------------------------------------------------------------ the start and end of turns
    def turn_begins(self, cid):
        """Uses regained, Shield's +5 gone, Regeneration, auras that work at the start of this creature's turn."""
        L = self.legendary.get(cid)
        if L:
            L["left"], L["once"] = L["uses"], set()
        if cid in self.shielded:                                 # Shield lasts until the start of its next turn
            self.shielded.discard(cid)
            self.fs.setValue(cid, "sim_ac_bonus", max(0, self.fs.num(cid, "sim_ac_bonus") - 5))
        if self.has(cid, "Regeneration") and not self.fs.down(cid):
            g = self.traits[cid]["Regeneration"]
            m = re.search(r"regains (\d+) Hit Points", g.get("desc", ""))
            if cid in self.no_regen:
                self.no_regen.discard(cid)
                self.sim.say("dice", "%s's Regeneration doesn't work this turn (it took %s damage)" % (
                    self.fs.name(cid), " or ".join(self.stoppers(cid))))
            elif m and self.fs.num(cid, "wounds") > 0:
                n = min(int(m.group(1)), self.fs.num(cid, "wounds"))
                self.fs.heal(cid, n)
                self.sim.say("dice", "%s Regeneration: regains %d HP" % (self.fs.name(cid), n))
        for src, g in self.auras():
            self.aura(src, g, cid)

    def stoppers(self, cid):
        g = self.traits.get(cid, {}).get("Regeneration") or {}
        m = re.search(r"takes ([A-Z]\w+)(?: or ([A-Z]\w+))? damage, this trait doesn't function", g.get("desc", ""))
        return [x for x in (m.groups() if m else ()) if x]

    def hurt(self, src, tid, amount):
        """Damage of a type that stops Regeneration on the creature's next turn (Acid or Fire for a troll)."""
        stop = {s.lower() for s in self.stoppers(tid)} if self.has(tid, "Regeneration") else set()
        if stop & self.last_types.get(tid, set()):
            self.no_regen.add(tid)

    def adjust_damage(self, real):
        """Remember the damage types each creature just took (Regeneration reads them)."""
        def adjust_damage(tgt, clauses, parts):
            self.last_types[tgt] = {str(c.get("dmgtype") or "").lower().strip() for i, c in enumerate(clauses)
                                    if i < len(parts) and parts[i] > 0}
            return real(tgt, clauses, parts)
        return adjust_damage

    def auras(self):
        for src, traits in self.traits.items():
            for name, g in traits.items():
                if re.search(r"starts its turn in an? \d+-foot Emanation", g.get("desc", "")) and "Saving Throw" in g.get("desc", ""):
                    yield src, g

    def aura(self, src, g, t):
        """"Any creature that starts its turn in a 5-foot Emanation originating from the ghast" (Stench and the like)."""
        if src == t or self.fs.down(src) or self.fs.down(t) or (src, t, g["name"]) in self.immune_aura or not self.gm:
            return
        m = re.search(r"starts its turn in an? (\d+)-foot Emanation", g["desc"])
        if self.fs.distance(src, t) > int(m.group(1)):
            return
        text = re.sub(r"any creature that starts its turn in an? (\d+)-foot Emanation[^.]*", r"each creature in a \1-foot "
                      r"Emanation originating from it", g["desc"])
        spec = _tools().parse_save(text)[0]
        if not spec:
            return
        label = "%s's %s" % (self.fs.name(src), base_name(g["name"]))
        saved, _ = self.gm.roll_save(src, t, spec, label)
        if saved:
            if "immune to this" in g["desc"]:
                self.immune_aura.add((src, t, g["name"]))
            return
        if spec.get("dmg"):
            self.fs.pcDamage(src, t, spec["dmg"], 0, False, spec.get("type", ""))
            self.sim.settle()
        if not self.fs.down(t):
            self.gm.apply_save_conditions(src, t, spec, base_name(g["name"]))

    def on_drop(self, real):
        """Death Burst and the like ("explodes when it dies"), from the trait's own save, after the damage that dropped it."""
        def on_drop(tid):
            if real:
                real(tid)
            c = self.sim.by_id(tid)
            if c.get("pc") or not self.gm or self.gm.effects(tid).get("death_burst"):
                return
            for name, g in self.traits.get(tid, {}).items():
                if re.search(r"when it dies", g.get("desc", "")) and "Saving Throw" in g.get("desc", ""):
                    spec = _tools().parse_save(g["desc"])[0]
                    if spec and spec.get("area"):
                        a = {"name": base_name(g["name"]), "save": spec}
                        self.sim.later.append(lambda a=a: self.burst(tid, a))
        return on_drop

    def burst(self, me, a):
        aim = {}
        targets = [o["id"] for o in self.sim.sc["combatants"] if o["id"] != me and not self.fs.down(o["id"])
                   and self.fs.distance(me, o["id"]) <= a["save"]["area"].get("size", 5)]
        aim["origin"] = list(self.party.pos(me)) if self.party else None
        self.gm.use_save_action(me, a, targets, None, aim)

    def damaged(self, real):
        """A creature that concentrates saves to keep it (SRD 5.2.1 Concentration: DC 10 or half the damage, up to 30);
        at 0 Hit Points it loses it."""
        def damaged(tid, amount, crit, was_down):
            if real:
                real(tid, amount, crit, was_down)
            c = self.sim.by_id(tid)
            if c.get("pc") or not self.party:
                return
            held = self.party.concentrates(tid)
            if not held:
                return
            if self.fs.down(tid):
                self.party.lose_concentration(tid, "at 0 hit points")
            elif not self.gm.condition_save(tid, "con", min(30, max(10, amount // 2)), "Concentration (%s)" % held):
                for spell in self.party.end_concentration(tid):
                    self.sim.say("dice", "%s's Concentration breaks: %s ends" % (c["name"], spell))
        return damaged

    # ------------------------------------------------------------------ spells on the creature's list of choices
    def usable(self, cid, time="action", legendary=False):
        out = []
        for e in self.of.get(cid, []):
            p = e["plan"]
            if p["time"] != time or (p["legendary_only"] and not legendary):
                continue
            if e["uses"] is not None and self.left.get(cid, {}).get(e["key"], 0) <= 0:
                continue
            out.append(e)
        return out

    def spec(self, p):
        """A spell's area in the shape gm_rules aims creatures' saving-throw actions with."""
        r = p["range_ft"]
        if p["shape"] == "sphere":
            area = {"shape": "sphere", "radius": p["area"]["size_ft"], "range": r}
        elif p["shape"] == "cone":
            area = {"shape": "cone", "size": p["area"]["size_ft"]}
        elif p["shape"] == "line":
            area = {"shape": "line", "length": p["area"]["size_ft"], "width": p["area"].get("width_ft") or 5}
        elif p["shape"] == "emanation":
            area = {"shape": "emanation", "size": p["area"]["size_ft"]}
        else:
            area = {"shape": "one", "range": r, "sees": True}
        return {"save": (p["save"] or {}).get("ability", "dex"), "dc": 10, "area": area,
                "type": p["damage"][0]["type"] if p["damage"] else None,
                "conditions": [{"name": n} for n in p["conditions"]]}

    def targets_for(self, cid, e):
        """[(target id, [creatures it affects], aim)] the spell can reach now: creatures in range the caster sees (an
        ally for a heal or Bless), or the best aim of its area (the most foes, no ally caught)."""
        p, fs, me = e["plan"], self.fs, cid
        side = self.ct.side(cid)
        held = self.party.concentrates(cid) if self.party else None
        if p["kind"] in ("zone", "guardians") and (held == "Spirit Guardians" or held in zone_spells()):
            return []                                            # it keeps the area it holds (no recast over it)
        if p["kind"] == "zone":
            return self.zone_aims(cid, e)
        if p["kind"] == "guardians":
            if not self.party or cid in self.party.guardians:
                return []
            reach = 15 + ai_turn.speed_ft(fs.getValue(cid, "speed", ""))
            near = [o for o in fs.combatants if self.ct.side(o) not in (side, "") and not fs.down(o)
                    and fs.distance(cid, o) <= reach and self.sim.sees(cid, o)]
            return [(cid, near, {"target": cid})] if near else []
        if p["shape"] != "creature":
            aim = {}
            got = self.gm.area_targets(me, self.spec(p), aim)
            foes = [t for t in got if self.ct.side(t) != side]
            return [(foes[0], got, aim)] if foes else []
        out = []
        for o in fs.combatants:
            ally = self.ct.side(o) == side
            if p["kind"] in ("heal", "bless", "shield"):
                if not ally or fs.down(o) and not self.sim.by_id(o).get("pc"):
                    continue
                if p["kind"] == "heal" and fs.num(o, "wounds") <= 0:
                    continue
            elif ally or o == me or fs.down(o):
                continue
            d = 0 if o == me else fs.distance(me, o)
            if d > max(p["range_ft"], 5 if p["range_kind"] == "touch" else 0):
                continue
            if o != me and not self.sim.sees(me, o):
                continue
            out.append((o, [o], {"target": o}))
        return out

    def zone_aims(self, cid, e):
        """Group 1: where a creature aims one of the zones (sim/spell_zones.py): a square in range it can see, on or
        near a foe it sees, that catches the most foes and none of its own side (Entangle spares its caster). The best
        aim: [(a foe caught, [creatures caught], {"origin": [x, y]})], or []."""
        import spell_zones
        st, name, p, fs = spell_zones.of(self.sim), e["name"], e["plan"], self.fs
        spec, side, units = spell_zones.SPELLS[name], self.ct.side(cid), self.sim.sc.get("units", 5)
        mx, my = self.party.pos(cid)
        best, seen = None, set()
        for f in sorted(fs.combatants):
            if self.ct.side(f) in (side, "") or fs.down(f) or not self.sim.sees(cid, f):
                continue
            fx, fy = self.party.pos(f)
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    x, y = int(round(fx)) + dx, int(round(fy)) + dy
                    if (x, y) in seen:
                        continue
                    seen.add((x, y))
                    if math.hypot(x - mx, y - my) * units > p["range_ft"] or not self.sim.sees_square(cid, x, y):
                        continue
                    got = st.caught(name, x, y)
                    if any(self.ct.side(t) == side and not (t == cid and spec.get("others")) for t in got):
                        continue
                    foes = [t for t in got if self.ct.side(t) not in (side, "")]
                    key = (-len(foes), abs(dx) + abs(dy), x, y)
                    if foes and (best is None or key < best[0]):
                        best = (key, (foes[0], got, {"origin": [x, y]}))
        return [best[1]] if best else []

    def zone_value(self, cid, e, affected):
        """A zone's or Spirit Guardians' worth for the scripted choice: its damage at the cast (or the first save in
        the Emanation) and once more while it lasts, a condition's worth, for each foe caught."""
        import spell_zones
        p, side = e["plan"], self.ct.side(cid)
        foes = [t for t in affected if self.ct.side(t) not in (side, "")]
        spec = spell_zones.SPELLS.get(e["name"]) or {}
        dmg = avg(p["damage"][0]["dice"]) if p["damage"] else 0.0
        if p["damage"] and p["slot"] > p["level"]:
            dmg += (p["slot"] - p["level"]) * avg("1d" + p["damage"][0]["dice"].split("d")[1])
        each = dmg * 0.75 * 2
        cond = spec.get("cast_save") or spec.get("later")
        if cond:
            each += CONDITION_VALUE.get(cond[1], 4) * 0.5
        return each * len(foes)

    def value(self, cid, e, affected):
        """The cast's expected effect in Hit Points (damage, healing, a condition's worth), for the scripted choice."""
        p, fs, c = e["plan"], self.fs, self.sim.by_id(cid)
        if p["kind"] in ("zone", "guardians"):
            return self.zone_value(cid, e, affected)
        if p["kind"] == "heal":
            return sum(avg(p["healing"]["dice"]) + c.get("spell_mod", 0) for t in affected
                       if fs.num(t, "wounds") * 3 >= 2 * fs.num(t, "hptotal"))
        dmg = sum(avg(self.general.dice(p, e["plan"]["slot"], {"level": 1}, i)[0]) + self.general.dice(p, p["slot"], {"level": 1}, i)[1]
                  for i in range(len(p["damage"])))
        n = self.general.strikes(p, p["slot"], {"level": 1}) if p["kind"] in ("attack", "auto") else 1
        foes = [t for t in affected if self.ct.side(t) != self.ct.side(cid)]
        if p["kind"] == "attack":
            return dmg * n * 0.6
        if p["kind"] == "auto":
            return dmg * n
        if p["kind"] == "pwk":
            return 100.0 if foes and fs.num(foes[0], "hptotal") - fs.num(foes[0], "wounds") <= 100 else avg("12d12")
        conds = sum(CONDITION_VALUE.get(x, 4) for x in p["conditions"]) * 0.5
        each = dmg * (0.75 if p["save"] and p["save"].get("half") else 0.5) + conds
        return each * len(foes)

    def best_attack(self, options):
        best = 0.0
        for ch in options["choices"]:
            if ch.get("spell") or ch.get("move_only") or ch["kind"] != "attack":
                continue
            a = self.ct.action(self.ct.by_path(options["source"]), ch["node_path"]) or {}
            per = avg(a.get("dmg")) + avg(a.get("dmg2"))
            best = max(best, per * 0.6 * ((ch.get("multi") or {}).get("of") or 1))
        return best

    def spell_choices(self, cid, options, combatants, space):
        """Add the creature's usable Action spells to the planner's list (one choice a target, one an area)."""
        t = self.ct.turn or {}
        if t.get("multi_done") or t.get("attacked") or options.get("search") or not self.able(cid):
            return
        searched = self.ct.awareness["search"].get(self.ct.path(cid))
        if searched and searched[0] == self.fs.turnSerial:
            return                                               # its Search used the action this turn
        best = self.best_attack(options)
        for e in self.usable(cid):
            for tid, affected, aim in self.targets_for(cid, e)[:8]:
                p = e["plan"]
                v = self.value(cid, e, affected)
                if v <= 0:
                    continue
                limited = e["uses"] is not None
                prio = 1 if v > best * (1.5 if limited else 1.15) else -1
                path = self.ct.path(tid)
                label = "%d creatures in the %s" % (len(affected), p["shape"].capitalize()) if p["shape"] != "creature" else \
                    combatants[path]["name"]
                choice = {"id": "C%d" % (len(options["choices"]) + 1), "node_path": e["node"], "move": None,
                          "roll_mode": "", "close_combat": [], "power_name": e["name"] + (
                              " (level %d version)" % p["slot"] if p["slot"] > p["level"] else ""),
                          "atktype": "ranged" if p["attack"] == "ranged" else "melee" if p["attack"] else "",
                          "kind": "attack" if p["kind"] == "attack" else "heal" if p["kind"] == "heal" else "save",
                          "spell": True, "level": p["slot"], "slots_left": None,
                          "uses_left_today": self.left.get(cid, {}).get(e["key"]) if limited else None, "bonus": False,
                          "multi": None, "target": path, "provokes": [], "target_name": label,
                          "distance_ft": float(self.fs.distance(cid, tid)) if tid != cid else 0.0,
                          "hp_total": combatants[path].get("hp_total", ""), "wounds": combatants[path].get("wounds", ""),
                          "health": ai_turn.health_text(combatants[path]), "priority": prio}
                options["choices"].append(choice)
                self.ct.handlers[e["node"]] = lambda me, s, e=e: self.cast(me, e, s)

    # ------------------------------------------------------------------ casting
    def spend(self, cid, e):
        if e["uses"] is not None:
            self.left[cid][e["key"]] -= 1

    def cast(self, cid, e, s=None, target=None, legendary=False):
        """Cast one spell from the creature's list, from its rules, inside the referee's watch."""
        p, fs, c = e["plan"], self.fs, self.sim.by_id(cid)
        tid = target or (self.ct.by_path(s["target"]) if s else None)
        if not self.able(cid):
            self.ct.refuse("%s cannot cast %s now." % (c["name"], e["name"]))
            return "done"
        reach = self.targets_for(cid, e)
        if tid is None:                                          # a legendary action: the target worth the most
            reach.sort(key=lambda x: -self.value(cid, e, x[1]))
        found = [x for x in reach if x[0] == tid or tid is None] or (reach if p["shape"] != "creature" else [])
        if not found:
            self.ct.refuse("%s's %s has no target it can reach now." % (c["name"], e["name"]))
            return "done"
        tid, affected, aim = found[0]
        live = getattr(self.sim, "live", None)                   # SPELL-BATCH-02: a player's Counterspell
        if live and getattr(live, "reactions", None) and live.reactions.counter(
                cid, e["name"], e["name"] + (" (level %d version)" % p["slot"] if p["slot"] > p["level"] else ""),
                p["components"], tid):
            self.spend(cid, e)                                   # a daily use is not a spell slot: it is spent
            return "done"
        slot, dc = p["slot"], int(c["spell_dc"])
        uses = "At Will" if e["uses"] is None else "%d/Day" % e["uses"]
        cmd = {"free": "%s's Spellcasting (%s%s)" % (c["name"], uses, ", a legendary action" if legendary else ""), "slot": slot,
               "time": p["time"]}                               # the referee reads the stat block's own time
        if legendary:
            cmd["legendary"] = True
        effect = {}
        if p["shape"] == "creature":
            cmd["target"] = tid
            if p["kind"] == "auto" or (p["kind"] == "attack" and p["count"]):
                cmd["targets"] = [tid]
            most = self.general.most_targets(p, slot, {"level": 1}) or 1
            if p["kind"] == "save" and most > 1:                 # a higher level's extra creatures (Command, level 2)
                more = sorted((x for x in reach if x[0] != tid), key=lambda x: -self.value(cid, e, x[1]))
                affected = [tid] + [x[0] for x in more][:most - 1]
                cmd["targets"] = list(affected)
        else:
            if aim.get("origin"):
                cmd["x"], cmd["y"] = aim["origin"][0], aim["origin"][1]
            effect = {k: v for k, v in aim.items() if k in ("origin", "toward", "angle_deg")}
        ref = getattr(self.sim, "referee", None)
        watch = ref.watch(cid, e["name"], cmd, effect) if ref else contextlib.nullcontext({})
        label = e["name"] + (" (level %d version)" % slot if slot > p["level"] else "")
        held, failed = set(), set()
        with watch:
            self.spend(cid, e)
            self.casting = True
            try:
                if p["concentration"] and self.party:
                    self.party.start_concentration(cid, e["name"])
                if p["kind"] == "attack":
                    held, failed = self.spell_attack(cid, c, p, slot, tid, label, dc)
                elif p["kind"] == "save":
                    held, failed = self.general.saves(cid, c, p, slot, affected, (p.get("choice") or [None])[0], label,
                                                      dc, aim)
                elif p["kind"] == "heal":
                    self.general.heal(cid, c, p, slot, [tid], label)
                elif p["kind"] == "auto":
                    self.general.darts(cid, c, p, slot, [tid], label)
                elif p["kind"] == "pwk":
                    self.power_word_kill(cid, c, tid)
                elif p["kind"] == "bless":
                    self.bless(cid, c, tid)
                elif p["kind"] == "zone":                        # group 1: the zone holds itself while it lasts
                    import spell_zones
                    spell_zones.of(self.sim).creature_cast(cid, e["name"], aim["origin"][0], aim["origin"][1], slot)
                elif p["kind"] == "guardians":
                    self.guardians(cid, c, slot)
                if p["concentration"] and self.party and p["kind"] not in ("bless", "zone", "guardians"):
                    self.general.hold(cid, c, p, held)
            finally:
                self.casting = False
        invisibility.cast_spell(self.sim, cid, e["name"])     # INVISIBILITY-01: a spell cast ends its own Invisibility
        if p.get("gm") and (failed or p["kind"] in ("save", "attack") and not p["conditions"]):
            text = p["gm"].format(caster=c["name"], target=fs.name(tid), dc=dc)
            self.sim.say("turn", "%s: the GM rules the rest: %s" % (e["name"], text))
        return "done"

    def spell_attack(self, cid, c, p, slot, tid, label, dc):
        """A spell attack roll for each ray (at the one target), with the creature's spell attack bonus; the spell's
        conditions on a hit (Ray of Sickness)."""
        n = self.general.strikes(p, slot, {"level": 1})
        dice, flat = self.general.dice(p, slot, {"level": 1}, 0)
        kind = p["damage"][0]["type"]
        self.sim.say("dice", "%s casts %s at %s: %s, %s%s %s" % (
            c["name"], label, self.fs.name(tid), "%d %ss" % (n, p["count"]["word"]) if p["count"] and n > 1 else
            "a %s spell attack" % p["attack"], dice, "+%d" % flat if flat else "", kind.capitalize()))
        import fight_state
        held, failed = set(), set()
        for _ in range(n):
            if self.fs.down(tid):
                break
            roll = {"sType": "attack", "nMod": int(c["spell_atk"]), "sRange": "R" if p["attack"] == "ranged" else "M",
                    "sim_action": p["name"], "sim_dmgtype": kind, "sim_spell": True}
            clauses = [{"dice": fight_state.dice_list(dice), "modifier": flat, "dmgtype": kind}]
            for extra in p["damage"][1:]:
                clauses.append({"dice": fight_state.dice_list(extra["dice"]), "modifier": 0, "dmgtype": extra["type"]})
            res = self.ct.strike(cid, tid, roll, clauses, p["name"])
            if res in ("hit", "crit"):
                failed.add(tid)
                if p["conditions"] and not self.fs.down(tid) and self.general.conditions(cid, c, p, tid, None, dc):
                    held.add(tid)
        return held, failed

    def power_word_kill(self, cid, c, tid):
        """Power Word Kill (SRD 5.2.1): a creature with 100 Hit Points or fewer dies; otherwise 12d12 Psychic damage."""
        left = self.fs.num(tid, "hptotal") - self.fs.num(tid, "wounds")
        if left <= 100:
            self.sim.say("dice", "%s casts Power Word Kill on %s (%d HP left, 100 or fewer): it dies" % (
                c["name"], self.fs.name(tid), left))
            self.fs.pcDamage(cid, tid, "", left, False, "psychic")
        else:
            self.sim.say("dice", "%s casts Power Word Kill on %s (%d HP left): 12d12 Psychic damage" % (
                c["name"], self.fs.name(tid), left))
            self.fs.pcDamage(cid, tid, "12d12", 0, False, "psychic")
        self.sim.settle()

    def bless(self, cid, c, tid):
        """Bless (SRD 5.2.1): up to three creatures add 1d4 to attack rolls and saving throws while the caster
        concentrates (its allies nearest to the fight first)."""
        side, fs = self.ct.side(cid), self.fs
        near = sorted((o for o in fs.combatants if self.ct.side(o) == side and not fs.down(o)
                       and (o == cid or fs.distance(cid, o) <= 30) and (o == cid or self.sim.sees(cid, o))),
                      key=lambda o: (o != tid, o == cid, fs.distance(cid, o)))[:3]
        for o in near:
            self.blessed[o] = cid
        self.party.__dict__.setdefault("gm_concentration", {})[cid] = "Bless"
        self.sim.say("dice", "%s casts Bless (Concentration): %s add 1d4 to attack rolls and saving throws" % (
            c["name"], ", ".join(fs.name(o) for o in near)))

    def guardians(self, cid, c, slot):
        """Spirit Guardians (SRD 5.2.1) cast by a creature (group 1): the 15-foot Emanation around it, as the Cleric's
        (sim/party.py): a foe saves when it ends its turn there or the Emanation reaches it as the caster walks."""
        import party as party_mod
        self.party.guardians[cid] = slot
        self.sim.say("dice", "%s casts Spirit Guardians (a level %d slot, Concentration): 15-ft Emanation, DC %d Wisdom "
                     "save, %s Radiant, half on a success" % (c["name"], slot, int(c["spell_dc"]), party_mod.guardians_dice(slot)))

    def bonus_spell(self, cid):
        """A Bonus Action spell first, when one helps: a heal on an ally (itself too) at a third of its Hit Points or
        fewer; Bless when it holds no Concentration and two or more of its side are near a foe."""
        if not self.able(cid):
            return
        for e in self.usable(cid, "bonus"):
            kind = e["plan"]["kind"]
            if kind == "heal":
                low = [x for x in self.targets_for(cid, e)
                       if self.fs.num(x[0], "wounds") * 3 >= 2 * self.fs.num(x[0], "hptotal") > 0]
                if low:
                    self.cast(cid, e, target=low[0][0])
                    return
            elif kind == "bless" and self.party and not self.party.concentrates(cid):
                if any(a["plan"]["kind"] in ("zone", "guardians") and self.targets_for(cid, a) for a in self.usable(cid)):
                    continue                                     # group 1: its area spell this turn holds Concentration
                side = self.ct.side(cid)
                fighting = [o for o, _, _ in self.targets_for(cid, e)
                            if any(self.ct.side(f) not in (side, "") and not self.fs.down(f) and self.fs.distance(o, f) <= 30
                                   for f in self.fs.combatants)]
                if len(fighting) >= 2:
                    self.cast(cid, e, target=cid)
                    return

    # ------------------------------------------------------------------ Shield, a Reaction
    def react_hit(self, real):
        def react_hit(tid, total, ac, crit, melee=True, src=None):
            out = real(tid, total, ac, crit, melee, src) if real else (0, False)
            if out and out[0]:
                return out
            if crit or not self.able(tid) or total >= ac + 5:
                return out
            for e in self.usable(tid, "reaction"):
                if e["name"] == "Shield":
                    self.spend(tid, e)
                    self.sim.say("dice", "%s casts Shield (Reaction, %s): +5 AC until the start of its next turn" % (
                        self.fs.name(tid), "At Will" if e["uses"] is None else "%d/Day" % e["uses"]))
                    self.shielded.add(tid)
                    invisibility.cast_spell(self.sim, tid, "Shield")
                    return 5, True
            return out
        return react_hit

    # ------------------------------------------------------------------ legendary actions
    def turn_ended(self, ended):
        """Right after a creature's turn: each legendary creature (not the one whose turn it was) may take one
        legendary action, by the scripted policy."""
        for cid, L in list(self.legendary.items()):
            if cid == ended or L["left"] <= 0 or not L["options"] or not self.able(cid):
                continue
            self.sim.checkpoint()
            self.legendary_action(cid, L)

    def legendary_action(self, cid, L):
        fs, c = self.fs, self.sim.by_id(cid)
        for opt in L["options"]:
            if opt["cost"] > L["left"] or (opt["once"] and opt["name"] in L["once"]) or opt["kind"] == "gm":
                continue
            done = False
            if opt["kind"] == "attack":
                done = self.legendary_attack(cid, opt)
            elif opt["kind"] == "save" and self.gm:
                aim = {}
                targets = self.gm.area_targets(cid, opt["spec"], aim)
                if any(self.ct.side(t) != self.ct.side(cid) for t in targets):
                    self.sim.say("turn", "%s takes a legendary action: %s" % (c["name"], opt["name"]))
                    self.gm.use_save_action(cid, {"name": opt["name"], "save": opt["spec"]}, targets, None, aim)
                    done = True
            elif opt["kind"] == "spell":
                e = next((e for e in self.of.get(cid, []) if e["name"] == opt["spell"]), None)
                if e:
                    e = dict(e, uses=None) if not opt["notes"] else dict(e, uses=None, plan=dict(e["plan"], slot=max(
                        e["plan"]["slot"], int(opt["notes"][0].split()[1]))))
                    if self.targets_for(cid, e):
                        self.sim.say("turn", "%s takes a legendary action: %s" % (c["name"], opt["name"]))
                        self.cast(cid, e, legendary=True)
                        done = True
            if done:
                L["left"] -= opt["cost"]
                if opt["once"]:
                    L["once"].add(opt["name"])
                self.sim.say("turn", "%s has %d legendary action%s left this round" % (c["name"], L["left"],
                                                                                    "" if L["left"] == 1 else "s"))
                return True
        return False

    def legendary_attack(self, cid, opt):
        """One attack of the named action at a foe in reach, after moving up to half its Speed when the text says so."""
        fs, ct = self.fs, self.ct
        a = next((a for a in self.sim.by_id(cid).get("actions") or [] if base_name(a.get("name")) == opt["attack"]
                  and a.get("atk") is not None), None)
        if not a:
            return False
        foes = [o for o in fs.combatants if ct.side(o) not in (ct.side(cid), "") and not fs.down(o)
                and (a.get("atktype") == "ranged" or True)]
        reach = a.get("reach") or 5
        inside = [o for o in foes if fs.distance(cid, o) <= reach and self.sim.sees(cid, o)]
        if not inside and opt.get("move") and not ct.turn:
            return self.pounce(cid, a, opt)
        if not inside:
            return False
        tid = min(inside, key=lambda o: (fs.num(o, "hptotal") - fs.num(o, "wounds"), o))
        self.sim.say("turn", "%s takes a legendary action: %s" % (fs.name(cid), opt["name"]))
        s = {"source": ct.path(cid), "source_name": fs.name(cid), "target": ct.path(tid), "target_name": fs.name(tid),
             "nodepath": "%s.actions.%s" % (ct.path(cid), a["id"]), "action_name": a["name"], "kind": "attack", "spell": False}
        return ct.attack(cid, s, opportunity=True) is not None

    def pounce(self, cid, a, opt):
        """Move up to half its Speed toward the nearest foe (the planner's route), then the attack if it got in reach."""
        ct, fs = self.ct, self.fs
        speed = ai_turn.speed_ft(fs.getValue(cid, "speed", "")) // 2
        ct.turn = {"id": cid, "serial": fs.turnSerial, "moved": float(ai_turn.speed_ft(fs.getValue(cid, "speed", "")) - speed),
                   "mdiag": 0, "attacked": False, "multi_done": [], "hits": [], "targets": [], "items": []}
        try:
            combatants, ranked = ct.combatants(), ct.ranked()
            space = dict(ct.space(cid), aware=True, avoid_provoking=True)
            path = ct.path(cid)
            ranked = [r for r in ranked if r["ctpath"] != path or r["node_path"].endswith("." + a["id"])]
            try:
                options = ai_turn.build_options(combatants, ranked, path, ct.distances(cid), fs.round(), False, False,
                                                space, [], None, simulation=True)
            except ai_turn.SuggestError:
                return False
            moves = [ch for ch in options["choices"] if ch.get("move") and not ch.get("move_only")]
            if not moves:
                return False
            ch = min(moves, key=lambda ch: ch["move"]["feet"])
            s = ai_turn.validate({"choice": ch["id"], "reason": "legendary", "narration": ""}, options)
            self.sim.say("turn", "%s takes a legendary action: %s" % (fs.name(cid), opt["name"]))
            if not ct.walk(cid, s):
                return True
            ct.attack(cid, s, opportunity=True)
            return True
        finally:
            ct.turn = None

    # ------------------------------------------------------------------ the GM's list
    def ruled_lines(self):
        """[(creature name, ability, why the GM rules it)] for every creature in the fight."""
        out = []
        for cid, rows in self.ruled.items():
            for name, why in rows:
                out.append((self.fs.name(cid), name, why))
        return out


def attach(sim):
    """Hook every creature's abilities into the fight (Python engine)."""
    if not getattr(sim, "creatures", None):
        return None
    ab = Abilities(sim)
    sim.abilities = ab
    ct, fs = sim.creatures, sim.S
    ct.extra_choices.append(ab.spell_choices)
    ct.attack_mode.append(ab.attack_mode)
    ct.on_turn_start.append(ab.bonus_spell)
    fs.turnBegins.append(ab.turn_begins)
    fs.turnEnded.append(ab.turn_ended)
    fs.adjust_damage = ab.adjust_damage(fs.adjust_damage)
    if sim.gm_rules:
        sim.gm_rules.has_evasion = ab.evasion(sim.gm_rules.has_evasion)
        fs.fortitude = ab.fortitude(fs.fortitude)
        fs.onDrop = ab.on_drop(fs.onDrop)
        fs.onDamage = ab.damaged(fs.onDamage)
        fs.reactHit = ab.react_hit(fs.reactHit)
        real_hurt = fs.onHurt
        fs.onHurt = lambda src, tid, amount, kinds="": (real_hurt(src, tid, amount, kinds) if real_hurt else None,
                                                        ab.hurt(src, tid, amount))
    for line in ab.ruled_lines():
        sim.say("gm", "The GM rules %s's %s (%s)" % line)
    return ab
