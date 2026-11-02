"""SPELL-EFFECTS-01 group 3 (GM 2026-10-26): lasting areas on the map beyond Fog Cloud, Darkness and Stinking Cloud, by SRD
5.2.1, on the map-layers zones (sim/map_layers.py: they join the environment's zones, the map draws them, and they end
with their caster's Concentration or their time). Their later saves go through the referee (REFEREE-02: watch_area),
their Difficult Terrain through the movement rules (live _walk, Sim._route_search).

- Entangle (1; 90 ft; a 20-foot square; Concentration, 1 minute): Difficult Terrain; each creature other than the
  caster in it when it is cast: Strength save or Restrained until the spell ends; an action and a Strength (Athletics)
  check against the spell save DC frees it (Break free).
- Grease (1; 60 ft; a 10-foot square; 1 minute, no Concentration): Difficult Terrain; each creature standing in it when
  it appears, and one that enters it or ends its turn there: Dexterity save or Prone.
- Web (2; 60 ft; a 20-foot Cube; Concentration, 1 hour): Difficult Terrain, Lightly Obscured; the first time a creature
  enters it on a turn or starts its turn there: Dexterity save or Restrained while in the webs (Break free: an action
  and a Strength (Athletics) check). Flammable: fire damage to a creature in the webs sets its 5-foot square alight
  (2d4 Fire to a creature that starts its turn there; it frees one held there), and a round later those webs are gone.
  (Whether the webs are anchored is the GM's.)
- Spike Growth (2; 150 ft; a 20-foot-radius Sphere; Concentration, 10 minutes): Difficult Terrain; 2d4 Piercing for
  every 5 feet a creature moves into or within it. (Its camouflage is the GM's.)
- Moonbeam (2; 120 ft; a 5-foot-radius Cylinder; Concentration, 1 minute): each creature in it when it appears, when it
  moves into the creature's space, when the creature enters it or ends its turn there, once per turn: Constitution save,
  2d10 Radiant (+1d10 a slot level above 2), half on a success. On a later turn a Magic action moves it up to 60 feet.
- Silence (2; 120 ft; a 20-foot-radius Sphere; Concentration, 10 minutes): creatures inside are Deafened, and a spell
  with a Verbal component can't be cast there (Subtle Spell can). (Immunity to Thunder damage inside: the GM's.)
- Sleet Storm (3; 150 ft; a 20-foot-radius Cylinder; Concentration, 1 minute): Heavily Obscured, Difficult Terrain; the
  first time a creature enters it on a turn or starts its turn there: Dexterity save or Prone and its Concentration ends.
- Cloudkill (5; 120 ft; a 20-foot-radius Sphere; Concentration, 10 minutes): Heavily Obscured; Constitution save, 5d8
  Poison (+1d8 a slot level above 5), half on a success, when it appears, when it moves into a creature's space, when a
  creature enters it or ends its turn there, once per turn; it drifts 10 feet away from the caster at the start of each
  of the caster's turns. (Level 5: here because it is an area of this module; the other level 4-9 spells are goal 3's.)
- Conjure Animals (3; 60 ft; Concentration, 10 minutes): a Large pack of spectral animals (intangible: creatures pass
  through it). Whenever it moves within 10 feet of a creature the caster can see, and whenever such a creature enters a
  space within 10 feet of it or ends its turn there, once per turn, the caster may force a Dexterity save: 3d10 Slashing
  (+1d10 a slot level above 3) on a failure; the engine forces it on the caster's foes. When the caster moves on its turn,
  it can move the pack up to 30 feet (Move the pack). The caster has Advantage on Strength saves within 5 feet of it.
- Insect Plague (5; 300 ft; a 20-foot-radius Sphere; Concentration, 10 minutes; group 1, GM 2026-10-27): Lightly
  Obscured, Difficult Terrain; Constitution save, 4d10 Piercing (+1d10 a slot level above 5), half on a success, when it
  appears, when a creature enters it for the first time on a turn or ends its turn there, once per turn.
SPELLS-7-9 (GM 2026-10-28: the level 7-9 spells that matter in a fight as Cast buttons):
- Conjure Celestial (7; 90 ft; a 10-foot-radius Cylinder; Concentration, 10 minutes): for each creature the caster can
  see in it when it appears, and whenever the Cylinder moves into a creature's space or a creature enters it or ends its
  turn there (once per turn), one of two lights: Healing Light, 4d12 + the spellcasting modifier (the engine shines it
  on the caster's side), or Searing Light, Dexterity save, 6d12 Radiant, half on a success (on the caster's foes); both
  +1d12 a slot level above 7. When the caster moves on its turn, it can move the Cylinder up to 30 feet (Move the light).
- Incendiary Cloud (8; 150 ft; a 20-foot-radius Sphere; Concentration, 1 minute): Heavily Obscured; Dexterity save, 10d8
  Fire, half on a success, when it appears, when it moves into a creature's space, when a creature enters it or ends its
  turn there, once per turn; it moves 10 feet away from the caster at the start of each of the caster's turns.
- Earthquake (8; 500 ft; a 100-foot-radius circle; Concentration, 1 minute): Difficult Terrain; when it is cast and at
  the end of each of the caster's turns, each creature on the ground in it: Dexterity save or Prone and its
  Concentration broken. (The fissures and the structures it shakes down are the GM's.)
Group 1 (GM 2026-10-27): creatures the game plays keep off the areas that would harm or hold them (keep_off_cells:
damage, spikes, a save against a condition; not one they already stand in) and pay their Difficult Terrain
(sim/creature_turns.py); a creature with one of these spells in its Spellcasting casts it (creature_cast, from
sim/creature_abilities.py). Without Play live's map layers (the simulator alone) the zones are counted and swept here.
"""
import contextlib, math, re

import more_spells as ms
import requirements as rq

# level, range, the area (radius or square side), how long, Concentration, what it does
SPELLS = {
    "Entangle": dict(level=1, range_ft=90, cube_ft=20, rounds=10, concentration=True, appearance="physical",
                     difficult=True, cast_save=("str", "Restrained"), others=True,
                     what="grasping plants (Difficult Terrain); Strength save or Restrained"),
    "Grease": dict(level=1, range_ft=60, cube_ft=10, rounds=10, concentration=False, appearance="physical",
                   difficult=True, cast_save=("dex", "Prone"), later=("dex", "Prone", ("enter", "end")),
                   what="grease (Difficult Terrain); Dexterity save or Prone"),
    "Web": dict(level=2, range_ft=60, cube_ft=20, rounds=600, concentration=True, appearance="physical",
                difficult=True, veil="light", later=("dex", "Restrained", ("enter", "start")), flammable=True,
                what="sticky webs (Difficult Terrain, Lightly Obscured); Dexterity save or Restrained"),
    "Spike Growth": dict(level=2, range_ft=150, radius_ft=20, rounds=100, concentration=True, appearance="physical",
                         difficult=True, spikes="2d4", what="spikes and thorns (Difficult Terrain): 2d4 Piercing a 5 ft moved"),
    "Moonbeam": dict(level=2, range_ft=120, radius_ft=5, rounds=10, concentration=True, appearance="radiant",
                     damage=("con", "2d10", "radiant", True, 2), later_dmg=("moved", "enter", "end"), at_cast=True,
                     move_ft=60, what="a beam of moonlight: Constitution save, 2d10 Radiant"),
    "Silence": dict(level=2, range_ft=120, radius_ft=20, rounds=100, concentration=True, appearance="arcane",
                    silence=True, what="silence: Deafened inside, no spell with a Verbal component"),
    "Sleet Storm": dict(level=3, range_ft=150, radius_ft=20, rounds=10, concentration=True, appearance="frost",
                        difficult=True, veil="heavy", later=("dex", "Prone", ("enter", "start")), breaks=True,
                        what="sleet (Heavily Obscured, Difficult Terrain); Dexterity save or Prone and no Concentration"),
    "Cloudkill": dict(level=5, range_ft=120, radius_ft=20, rounds=100, concentration=True, appearance="poison",
                      veil="heavy", damage=("con", "5d8", "poison", True, 5), later_dmg=("moved", "enter", "end"),
                      at_cast=True, drifts=10, what="a poison fog (Heavily Obscured): Constitution save, 5d8 Poison"),
    "Insect Plague": dict(level=5, range_ft=300, radius_ft=20, rounds=100, concentration=True, appearance="physical",
                          veil="light", difficult=True, damage=("con", "4d10", "piercing", True, 5),
                          later_dmg=("enter", "end"), at_cast=True,
                          what="swarming locusts (Lightly Obscured, Difficult Terrain): Constitution save, 4d10 Piercing"),
    "Conjure Animals": dict(level=3, range_ft=60, radius_ft=5, rounds=100, concentration=True, appearance="physical",
                            pack=True, near_ft=10, damage=("dex", "3d10", "slashing", False, 3),
                            later_dmg=("moved", "enter", "end"), move_ft=30,
                            what="a Large pack of spectral animals: Dexterity save, 3d10 Slashing within 10 ft"),
    # SPELLS-7-9 (GM 2026-10-28)
    "Conjure Celestial": dict(level=7, range_ft=90, radius_ft=10, rounds=100, concentration=True, appearance="radiant",
                              damage=("dex", "6d12", "radiant", True, 7), heal="4d12", bathe=True, at_cast=True,
                              later_dmg=("moved", "enter", "end"), move_ft=30,
                              what="a pillar of light: Healing Light (4d12 + modifier) on your side, Searing Light "
                                   "(Dexterity save, 6d12 Radiant) on your foes"),
    "Incendiary Cloud": dict(level=8, range_ft=150, radius_ft=20, rounds=10, concentration=True, appearance="fire",
                             veil="heavy", damage=("dex", "10d8", "fire", True, 8), later_dmg=("moved", "enter", "end"),
                             at_cast=True, drifts=10,
                             what="a cloud of embers and smoke (Heavily Obscured): Dexterity save, 10d8 Fire"),
    "Earthquake": dict(level=8, range_ft=500, radius_ft=100, rounds=10, concentration=True, appearance="physical",
                       difficult=True, cast_save=("dex", "Prone"), breaks=True, quake=True,
                       what="a tremor (Difficult Terrain): Dexterity save or Prone and Concentration broken, now and at "
                            "the end of each of your turns"),
}
OPS = ("move_beam", "move_pack", "break_free", "move_celestial")   # SPELLS-7-9: Conjure Celestial's Cylinder
MOVES = {"move_beam": "Moonbeam", "move_pack": "Conjure Animals", "move_celestial": "Conjure Celestial"}
ABILITY = {"str": "Strength", "dex": "Dexterity", "con": "Constitution"}


def known(c):
    return [n for n in SPELLS if ms.has_spell(c, n)]


def of(sim):
    st = getattr(sim, "_spell_zones", None)
    if st is None:
        st = sim._spell_zones = Zones(sim)
    return st


def _roll(rng, expr):
    total = 0
    for n, d in re.findall(r"(\d+)d(\d+)", expr):
        total += sum(rng.randint(1, int(d)) for _ in range(int(n)))
    return total


class Zones:
    def __init__(self, sim):
        self.sim = sim
        self.saved = {}               # (zone n, creature) -> turn serial of its last save (once per turn / first time)
        self.burning = {}             # zone n -> {square: round it caught fire}
        self.burnt = {}               # zone n -> squares whose webs burned away
        self.moved = {}               # caster -> turn serial its pack moved

    @property
    def fight(self):
        return self.sim.live

    @property
    def party(self):
        return self.sim.party

    @property
    def env(self):
        return self.sim.env

    def name(self, i):
        return self.sim.by_id(i)["name"]

    def serial(self):
        return int(self.sim.S.turnSerial or 0)

    def round(self):
        return int(self.sim.S.round() or 0)

    def units(self):
        return self.sim.sc.get("units", 5)

    # ------------------------------------------------------------------ the zones on the map
    def zones(self):
        import map_layers
        return [z for z in self.env.zones if z.get("effects") and map_layers.alive(self.env, z)]

    def inside(self, z, p):
        if z.get("pack"):                                        # the pack itself: its 10-foot square
            return max(abs(p[0] - z["origin"][0]), abs(p[1] - z["origin"][1])) <= 1.0
        if "circle" not in z:
            x1, y1, x2, y2 = z["rect"]
            if (round(p[0]), round(p[1])) in self.burnt.get(z["n"], set()):
                return False
            return x1 - 0.01 <= p[0] <= x2 + 0.01 and y1 - 0.01 <= p[1] <= y2 + 0.01
        cx, cy, r = z["circle"]
        return math.hypot(p[0] - cx, p[1] - cy) <= r + 0.01

    def near_pack(self, z, p, ft=None):
        """Within 10 feet of the pack (its 10-foot square around its point; the creature's square's centre)."""
        gap = max(abs(p[0] - z["origin"][0]), abs(p[1] - z["origin"][1])) - 1.0
        return max(0.0, gap) * self.units() <= (z["near_ft"] if ft is None else ft) + 0.01

    def touches(self, z, p):
        return self.near_pack(z, p) if z.get("pack") else self.inside(z, p)

    def cells(self, z):
        if "circle" not in z:
            x1, y1, x2, y2 = z["rect"]
            return {(x, y) for x in range(int(x1), int(x2) + 1) for y in range(int(y1), int(y2) + 1)} - self.burnt.get(z["n"], set())
        cx, cy, r = z["circle"]
        return {(x, y) for x in range(int(math.floor(cx - r)), int(math.ceil(cx + r)) + 1)
                for y in range(int(math.floor(cy - r)), int(math.ceil(cy + r)) + 1) if math.hypot(x - cx, y - cy) <= r + 0.01}

    def difficult_cells(self, me=None):
        out = set()
        for z in self.zones():
            if SPELLS[z["spell"]].get("difficult"):
                out |= self.cells(z)
        return out

    def keep_off_cells(self, me):
        """Group 1 (GM 2026-10-27): the squares a creature the game plays keeps off on its routes: the zones that harm or
        hold a creature coming in (damage, spikes, a save against a condition), but not one it already stands in (it
        walks out as it likes). The pack harms only its caster's foes."""
        out, p = set(), self.party.pos(me)
        for z in self.zones():
            spec = SPELLS[z["spell"]]
            if not (spec.get("damage") or spec.get("spikes") or spec.get("later")) or self.touches(z, p):
                continue
            if spec.get("bathe") and (me == z["owner"] or self.party.side(me) == self.party.side(z["owner"])):
                continue                                         # SPELLS-7-9: its light heals the caster's side
            if spec.get("pack"):
                if me == z["owner"] or self.party.side(me) == self.party.side(z["owner"]):
                    continue
                reach = 1 + int(z["near_ft"] // self.units())       # its 10-foot square and 10 feet round it
                ox, oy = z["origin"]
                out |= {(int(ox) + dx, int(oy) + dy) for dx in range(-reach, reach + 1) for dy in range(-reach, reach + 1)}
                continue
            out |= self.cells(z)
        return out

    # ------------------------------------------------------------------ the cards
    def needs(self, me, name, slot=None):
        return ms.cast_needs(self.fight, me, name, SPELLS[name]["level"], "action", slot)

    def offers(self, me):
        c, out = self.sim.by_id(me), []
        for name in known(c):
            s = SPELLS[name]
            card = dict(s, time="action", shape="cube" if s.get("cube_ft") else "sphere", upcast=bool(s.get("damage")),
                        rider=s["what"])
            if s.get("cube_ft"):
                card["size_ft"] = s["cube_ft"]
            e = ms.card(self.fight, me, name, card, self.needs(me, name), zone=s["what"],
                        layer="air" if s.get("veil") else "ground")
            if c.get("metamagic"):
                import live_sorcery
                e["metamagic"] = live_sorcery.of(self.fight).options(me, name, self.meta_entry(name))
            out.append(e)
        return out

    @staticmethod
    def meta_entry(name):
        """The fields Metamagic reads (sim/live_sorcery.py): its time, range, Concentration, damage type, a save."""
        s = SPELLS[name]
        dmg = s.get("damage")
        return dict(s, time="action", kind=dmg[2] if dmg else None,
                    save=bool(s.get("cast_save") or dmg or s.get("later")), area_damage=bool(dmg and s.get("at_cast")))

    def adjust_offers(self, me, out):
        acts = out.setdefault("actions", [])
        for z in self.zones():
            if z["owner"] != me:
                continue
            if z["spell"] == "Moonbeam":
                ready, rows = rq.check(self.move_needs(me, z, "move_beam"))
                acts.append({"op": "move_beam", "label": "Moonbeam: move it up to 60 ft (Magic action)", "square": True,
                             "ready": ready, "why": rq.first_why(rows)})
            if z["spell"] == "Conjure Animals":
                ready, rows = rq.check(self.move_needs(me, z, "move_pack"))
                acts.append({"op": "move_pack", "label": "Conjure Animals: move the pack up to 30 ft", "square": True,
                             "ready": ready, "why": rq.first_why(rows), "time": "free"})
            if z["spell"] == "Conjure Celestial":                  # SPELLS-7-9
                ready, rows = rq.check(self.move_needs(me, z, "move_celestial"))
                acts.append({"op": "move_celestial", "label": "Conjure Celestial: move the light up to 30 ft",
                             "square": True, "ready": ready, "why": rq.first_why(rows), "time": "free"})
        held = self.held_by(me)
        if held:
            ready, rows = rq.check([rq.able(self.fight, me), rq.action_free(self.fight, me, "breaking free")])
            acts.append({"op": "break_free", "label": "Break free of the %s (Strength (Athletics))" % (
                "webs" if held["spell"] == "Web" else "plants"), "ready": ready, "why": rq.first_why(rows)})

    # ------------------------------------------------------------------ casting
    def cast(self, me, cmd):
        name = cmd["spell"]
        fight, sim, party = self.fight, self.sim, self.party
        x, y = ms.square(cmd, name)
        s, plan = ms.metamagic(fight, me, name, self.meta_entry(name), cmd)   # Quickened Spell: the Bonus Action
        ms.check(ms.cast_needs(fight, me, name, s["level"], s["time"], cmd.get("slot")))
        ms.point_in_range(fight, me, x, y, s["range_ft"], name)
        spec, c = SPELLS[name], sim.by_id(me)
        lv = ms.spend(fight, me, s.get("time", "action"), spec["level"], cmd.get("slot"))
        if spec["concentration"]:
            party.start_concentration(me, name)
            fight.layers.sweep()                                 # the zone of the spell it ended leaves the map now
        z = self.make(me, name, x, y, lv, [])
        inside = self.creatures_in(z)
        import live_sorcery                                      # Metamagic: who it spares, who saves at Disadvantage
        sorc, meta = live_sorcery.of(fight), plan or {}
        careful = sorc.careful(me, inside, cmd) if meta.get("careful") else []
        z["dis"] = sorc.heightened(me, inside, cmd) if meta.get("heighten") else []
        z["dmg_kind"] = meta.get("kind")                        # Transmuted Spell
        z["empower"] = meta.get("empower", 0)
        ms.pay_metamagic(fight, me, name, plan, careful=careful, heightened=z["dis"])
        sim.say("turn", "%s casts %s (a level %d slot%s): %s, %s on square (%d, %d)%s" % (
            c["name"], name, lv, ", Concentration" if spec["concentration"] else "", spec["what"],
            "a %d-ft square" % spec["cube_ft"] if spec.get("cube_ft") else "%d-ft radius" % spec["radius_ft"], x, y,
            "; inside: " + ", ".join(self.name(i) for i in inside) if inside else ""))
        if spec.get("cast_save"):
            ab, cond = spec["cast_save"]
            for t in inside:
                if not (spec.get("others") and t == me) and t not in careful:
                    self.condition_save(z, t, ab, cond, None)
        if spec.get("at_cast"):
            for t in inside:
                self.once(z, t)
                if t in careful:
                    sim.say("dice", "%s succeeds on its save against %s and takes no damage (Careful Spell)" % (self.name(t), name))
                    continue
                if spec.get("bathe"):                            # SPELLS-7-9: Conjure Celestial's two lights
                    self.bathe(z, t, None)
                    continue
                self.damage_save(z, t, None)
        z["empower"] = 0                                         # Empowered Spell: the casting's damage roll only
        if spec.get("silence"):
            self.hush()
        if plan and "Extended Spell" in plan["metas"]:
            z["ends_round"] += spec["rounds"]
        ms.extended(fight, me, name, plan)
        return self.effect(me, z, inside)

    def make(self, me, name, x, y, lv, dis):
        spec, party, c = SPELLS[name], self.party, self.sim.by_id(me)
        layers = getattr(self.sim, "layers", None)              # MAP-LAYERS-01 (Play live); the simulator alone: here
        if layers is not None:
            layers.n += 1
            n = layers.n
        else:
            n = max([int(z.get("n") or 0) for z in self.env.zones] + [0]) + 1
        z = {"id": "%s-%d" % (name.lower().replace(" ", "-"), n), "n": n, "spell": name, "owner": me, "effects": True,
             "origin": [x, y], "appearance": spec["appearance"], "layer": "air" if spec.get("veil") else "ground",
             "darkness": False, "stinking": False, "cast_round": self.round(), "ends_round": self.round() + spec["rounds"],
             "dc": party.spell_dc(c), "slot": lv, "cast_serial": self.serial(),
             "kind": "obscured" if spec.get("veil") else "spell_area", "level": spec.get("veil") or "none",
             "lasting": not spec["concentration"], "dis": list(dis), "veil": spec.get("veil") or "none"}
        z.update(self.geometry(name, x, y))
        if spec["concentration"]:
            party.__dict__.setdefault("gm_concentration", {})[me] = name
            party.__dict__.setdefault("layer_zone", {})[me] = n
        self.env.zones.append(z)
        return z

    def geometry(self, name, x, y):
        """The area of `name` aimed at square (x, y): its rect, and its cube or circle (a pack: its 10-foot square)."""
        spec, u, z = SPELLS[name], self.units(), {}
        if spec.get("cube_ft"):                                  # as the page aims it: the square up-left of the middle
            k = spec["cube_ft"] // u
            x0, y0 = x + 1 - math.ceil(k / 2), y + 1 - math.ceil(k / 2)
            z["rect"] = [x0, y0, x0 + k - 1, y0 + k - 1]
            z["cube"] = [x0 - 0.5, y0 - 0.5, x0 + k - 0.5, y0 + k - 0.5]
            z["size_ft"] = spec["cube_ft"]
            z["radius_ft"] = spec["cube_ft"] / 2
        else:
            r = spec["radius_ft"] / u
            z["circle"] = [x, y, r]
            z["radius_ft"] = spec["radius_ft"]
            z["rect"] = [int(math.floor(x - r)), int(math.floor(y - r)), int(math.ceil(x + r)), int(math.ceil(y + r))]
        if spec.get("pack"):
            z.update(pack=True, near_ft=spec["near_ft"], circle=[x, y, 1.0], radius_ft=5)
        return z

    # ------------------------------------------------------------------ a creature the game plays casts one (group 1)
    def caught(self, name, x, y):
        """The creatures (not down) an area of `name` aimed at (x, y) would hold now."""
        z = dict(self.geometry(name, x, y), n=-1, origin=[x, y])
        return [o["id"] for o in self.sim.sc["combatants"] if not self.sim.down(o["id"]) and self.touches(z, self.party.pos(o["id"]))]

    def creature_cast(self, me, name, x, y, slot):
        """Group 1 (GM 2026-10-27): a creature casts one of these areas from its Spellcasting (its uses and Concentration
        are counted there, sim/creature_abilities.py): the zone on the map as a character's, its saves at the creature's
        spell save DC, the saves of those inside when it appears. Returns the creatures inside."""
        spec, sim = SPELLS[name], self.sim
        self.sweep()
        z = self.make(me, name, x, y, slot, [])
        inside = self.creatures_in(z)
        sim.say("turn", "%s casts %s (%s): %s, %s on square (%d, %d)%s" % (
            self.name(me), name, "a level %d version" % slot if slot > spec["level"] else "level %d" % spec["level"],
            spec["what"], "a %d-ft square" % spec["cube_ft"] if spec.get("cube_ft") else "%d-ft radius" % spec["radius_ft"],
            x, y, "; inside: " + ", ".join(self.name(i) for i in inside) if inside else ""))
        if spec.get("cast_save"):
            ab, cond = spec["cast_save"]
            for t in inside:
                if not (spec.get("others") and t == me):
                    self.condition_save(z, t, ab, cond, None)
        if spec.get("at_cast"):
            for t in inside:
                self.once(z, t)
                self.damage_save(z, t, None)
        if spec.get("silence"):
            self.hush()
        return inside

    def sweep(self):
        """Zones whose Concentration ended leave the map (Play live: its layers do it; the simulator alone: here)."""
        layers = getattr(self.sim, "layers", None)
        if layers is not None:
            layers.sweep()
            return
        import map_layers
        gone = [z for z in self.env.zones if z.get("owner") and z.get("spell") in SPELLS and not map_layers.alive(self.env, z)]
        for z in gone:
            self.env.zones.remove(z)
            self.sim.say("dice", "%s's %s ends: %s" % (self.name(z["owner"]), z["spell"], z.get("ended") or "its Concentration ended"))
        if gone:
            self.ended(gone)

    def effect(self, me, z, inside):
        e = {"spell": z["spell"], "appearance": z["appearance"], "targets": list(inside), "lasting": True,
             "from": list(self.party.pos(me)), "origin": list(z["origin"])}
        if z.get("cube"):
            x0, y0, x1, y1 = z["cube"]
            e.update(shape="rectangle", origin=[x0, (y0 + y1) / 2], angle_deg=0, length_ft=z["size_ft"], width_ft=z["size_ft"],
                     cube=list(z["cube"]), cube_origin=[(x0 + x1) / 2, (y0 + y1) / 2])
        else:
            e.update(shape="circle", radius_ft=z["radius_ft"])
        return e

    def creatures_in(self, z):
        sim = self.sim
        return [o["id"] for o in sim.sc["combatants"] if not sim.down(o["id"]) and self.touches(z, self.party.pos(o["id"]))]

    # ------------------------------------------------------------------ saves
    def watch(self, z, t, when):
        ref = getattr(self.sim, "referee", None)
        if ref is None or when is None:
            return contextlib.nullcontext()
        return ref.watch_area(z["owner"], z["spell"], t, when, slot_level=z["slot"], origin=z["origin"])

    def once(self, z, t):
        """True the first time this turn (and records it): "once per turn", "the first time ... on a turn"."""
        key, now = (z["n"], t), self.serial()
        if self.saved.get(key) == now:
            return False
        self.saved[key] = now
        return True

    def save(self, z, t, ab, label):
        gm = self.sim.gm_rules
        if gm.auto_fail(t, ab):
            self.sim.say("dice", "%s %s save against %s: fails automatically" % (self.name(t), ABILITY[ab], label))
            return False
        return gm.condition_save(t, ab, z["dc"], label, dis="Heightened Spell" if t in z.get("dis", ()) else False)

    def condition_save(self, z, t, ab, cond, when):
        gm, sim = self.sim.gm_rules, self.sim
        if gm.cond_immune(t, cond):
            return True
        label = z["spell"]
        with self.watch(z, t, when):
            if self.save(z, t, ab, label):
                return True
            if (gm.cond.get(t) or {}).get(cond) and not SPELLS[label].get("breaks"):
                return False                                     # Prone or Restrained already
            why = "(%s's %s%s)" % (self.name(z["owner"]), label, ", while in the webs or until it breaks free" if label == "Web"
                                   else ", until the spell ends or it breaks free" if label == "Entangle" else "")
            if not (gm.cond.get(t) or {}).get(cond):
                held = {"spell": label, "zone": z["n"]} if cond == "Restrained" else {}   # Prone: it stands up as usual
                gm.add(t, cond, why, by=z["owner"], **held)
            if SPELLS[label].get("breaks"):
                held = self.party.concentrates(t) if (self.party and t in self.party.pools) else None
                if held:
                    self.party.end_concentration(t)
                    sim.say("dice", "%s is thrown down by the tremor: Concentration ends, %s ends" % (self.name(t), held)
                            if label == "Earthquake" else "%s falls in the sleet: its Concentration on %s ends" % (self.name(t), held))
        return False

    def damage_save(self, z, t, when):
        spec, sim = SPELLS[z["spell"]], self.sim
        ab, dice, kind, half, base = spec["damage"]
        kind = z.get("dmg_kind") or kind                         # Transmuted Spell
        extra = max(0, z["slot"] - base)
        expr = "%s+%dd%s" % (dice, extra, dice.split("d")[1]) if extra else dice
        with self.watch(z, t, when):
            dmg = self.empowered(z, expr) if z.get("empower") else _roll(sim.rng, expr)
            ok = self.save(z, t, ab, "%s (%s = %d %s%s)" % (z["spell"], expr, dmg, kind.capitalize(),
                                                          ", half on a success" if half else ", none on a success"))
            amount = (dmg // 2 if half else 0) if ok else dmg
            if amount:
                sim.S.pcDamage(z["owner"], t, "", amount, False, kind)
                sim.settle(0.2)
        return ok

    def bathe(self, z, t, when):
        """SPELLS-7-9: Conjure Celestial, on a creature the caster can see: Healing Light on the caster's side (one that
        has lost Hit Points), Searing Light on the others (the damage save)."""
        spec, sim, owner = SPELLS[z["spell"]], self.sim, z["owner"]
        if t != owner and not sim.sees(owner, t):
            return
        if t != owner and self.party.side(t) != self.party.side(owner):
            self.damage_save(z, t, when)
            return
        if not int(sim.S.state(t)[0] or 0):
            return
        extra = max(0, z["slot"] - spec["damage"][4])
        expr = spec["heal"] + ("+%dd12" % extra if extra else "")
        mod = int(sim.by_id(owner).get("spell_mod", 0))
        with self.watch(z, t, when):
            amount = _roll(sim.rng, expr) + mod
            sim.say("dice", "%s's Conjure Celestial: Healing Light on %s, %s + %d = %d Hit Points" % (
                self.name(owner), self.name(t), expr, mod, amount))
            self.party.revive(t, amount)

    def empowered(self, z, expr):
        """Empowered Spell: up to the Charisma modifier of the lowest damage dice rolled again (once)."""
        rng = self.sim.rng
        dice = [(int(d), rng.randint(1, int(d))) for n, d in re.findall(r"(\d+)d(\d+)", expr) for _ in range(int(n))]
        low = sorted(range(len(dice)), key=lambda k: dice[k][1])[:z["empower"]]
        again = [(dice[k][0], rng.randint(1, dice[k][0])) if k in low else dice[k] for k in range(len(dice))]
        self.sim.say("dice", "Empowered Spell: %s rolled again -> %s" % (
            ", ".join(str(dice[k][1]) for k in low), ", ".join(str(again[k][1]) for k in low)))
        return sum(v for _, v in again)

    def later_save(self, z, t, when):
        """A creature's later save in a zone (its condition or its damage), once per turn."""
        spec = SPELLS[z["spell"]]
        if self.sim.down(t):
            return
        if spec.get("later"):
            ab, cond, whens = spec["later"]
            if when in whens and self.once(z, t):
                self.condition_save(z, t, ab, cond, when)
        elif spec.get("later_dmg") and when in spec["later_dmg"]:
            if spec.get("pack") and (t == z["owner"] or self.party.side(t) == self.party.side(z["owner"])
                                     or not self.sim.sees(z["owner"], t)):
                return                                           # the caster forces it on foes it can see
            if spec.get("bathe"):                                # SPELLS-7-9: Conjure Celestial
                if (t == z["owner"] or self.sim.sees(z["owner"], t)) and self.once(z, t):
                    self.bathe(z, t, when)
                return
            if self.once(z, t):
                self.damage_save(z, t, when)

    # ------------------------------------------------------------------ the engine's moments
    def on_step(self, name, x0, y0, x1, y1):
        sim = self.sim
        mover = next((c for c in sim.sc["combatants"] if c["name"] == name), None)
        if not mover or sim.down(mover["id"]):
            return
        me, g = mover["id"], sim.sc.get("grid", 50)
        a, b = (x0 / g, y0 / g), (x1 / g, y1 / g)
        if a == b:
            return
        for z in self.zones():
            spec = SPELLS[z["spell"]]
            was, now = self.touches(z, a), self.touches(z, b)
            if spec.get("spikes") and now:
                sim.say("dice", "%s moves through the Spike Growth: %s Piercing" % (name, spec["spikes"]))
                sim.S.pcDamage(z["owner"], me, spec["spikes"], 0, False, "piercing")
            if now and not was and not sim.down(me):
                self.later_save(z, me, "enter")
            if spec.get("silence") and now != was:
                self.hush()
            if spec.get("later") and spec["later"][1] == "Restrained" and was and not now:
                self.tidy()
            if sim.down(me):
                return

    def creature_turn_start(self, me):
        """Any creature's turn starts (gmTurnStart: players' characters too): Web and Sleet Storm save; a burning web;
        the caster's Cloudkill drifts."""
        sim = self.sim
        if getattr(sim, "layers", None) is None:                 # the simulator alone: a zone's time (Layers in Play live)
            for z in self.zones():
                if z["owner"] == me and self.round() >= z["ends_round"]:
                    z["ended"] = "its duration is over"
                    if not z.get("lasting"):
                        self.party.end_concentration(me)
            self.sweep()
        self.tidy()
        for z in self.zones():
            if z["owner"] == me and SPELLS[z["spell"]].get("drifts"):
                self.drift(z)
        burn = self.burning_square(me)
        if burn:
            sim.say("dice", "%s starts its turn in burning webs: 2d4 Fire" % self.name(me))
            sim.S.pcDamage(burn["owner"], me, "2d4", 0, False, "fire")
            sim.settle(0.2)
        for z in self.zones():
            if not sim.down(me) and self.inside(z, self.party.pos(me)):
                self.later_save(z, me, "start")
        self.hush()
        return ""

    def turn_ended(self, me):
        """Grease, Moonbeam, Cloudkill, the pack: a creature ending its turn there saves; burnt webs fall away."""
        sim = self.sim
        for z in self.zones():
            if sim.down(me):
                break
            if self.touches(z, self.party.pos(me)):
                self.later_save(z, me, "end")
        for z in [z for z in self.zones() if z["owner"] == me and SPELLS[z["spell"]].get("quake")]:
            self.quake(z)                                        # SPELLS-7-9: Earthquake, the end of the caster's turns
        rnd = self.round()
        for n, squares in self.burning.items():
            for sq, when in list(squares.items()):
                if rnd > when:                                   # "burns away in 1 round"
                    squares.pop(sq)
                    self.burnt.setdefault(n, set()).add(sq)
        self.tidy()

    def quake(self, z):
        """Earthquake: "at the end of each of your turns ... each creature on the ground in the area makes a Dexterity
        saving throw" (a creature aloft is not on the ground)."""
        env = self.env
        for t in self.creatures_in(z):
            if not (env and env.aloft(t)) and not self.sim.down(t):
                self.condition_save(z, t, "dex", "Prone", "your_end")

    def drift(self, z):
        """Cloudkill: "The Sphere moves 10 feet away from you at the start of each of your turns"."""
        u = self.units()
        before = set(self.creatures_in(z))
        hx, hy = self.party.pos(z["owner"])
        ox, oy = z["origin"]
        dx, dy = ox - hx, oy - hy
        n = math.hypot(dx, dy) or 1.0
        step = SPELLS[z["spell"]]["drifts"] / u
        nx, ny = int(round(ox + dx / n * step)), int(round(oy + dy / n * step))
        if (nx, ny) == (ox, oy):
            nx = ox + int(step)
        self.relocate(z, nx, ny)
        self.sim.say("turn", "%s's %s drifts %d ft away from %s, to square (%d, %d)" % (
            self.name(z["owner"]), z["spell"], SPELLS[z["spell"]]["drifts"], self.name(z["owner"]), nx, ny))
        for t in self.creatures_in(z):
            if t not in before:
                self.later_save(z, t, "moved")

    def relocate(self, z, x, y):
        z["origin"] = [x, y]
        if "circle" in z:
            r = z["circle"][2]
            z["circle"] = [x, y, r]
            z["rect"] = [int(math.floor(x - r)), int(math.floor(y - r)), int(math.ceil(x + r)), int(math.ceil(y + r))]

    def burning_square(self, me):
        p = tuple(int(round(v)) for v in self.party.pos(me))
        return next((z for z in self.zones() if p in self.burning.get(z["n"], {})), None)

    def on_hurt(self, src, tid, amount, kinds=""):
        """Web: fire damage to a creature in the webs sets its 5-foot square alight (they burn away in a round)."""
        if "fire" not in str(kinds):
            return
        p = tuple(int(round(v)) for v in self.party.pos(tid))
        for z in self.zones():
            if SPELLS[z["spell"]].get("flammable") and self.inside(z, p) and p not in self.burning.get(z["n"], {}):
                self.burning.setdefault(z["n"], {})[p] = self.round()
                self.sim.say("dice", "The webs around %s catch fire: that 5-foot square burns away in a round" % self.name(tid))
                info = (self.sim.gm_rules.cond.get(tid) or {}).get("Restrained") or {}
                if info.get("zone") == z["n"]:
                    self.sim.gm_rules.remove(tid, "Restrained", "the webs burn away")

    def tidy(self):
        """Conditions a zone holds end with it, or outside it: Web's Restrained (while in the webs), Entangle's."""
        gm = self.sim.gm_rules
        if gm is None:
            return
        live = {z["n"]: z for z in self.zones()}
        for t, conds in list(gm.cond.items()):
            for cond, info in list(conds.items()):
                n = (info or {}).get("zone")
                if n is None or info.get("spell") not in SPELLS:
                    continue
                z = live.get(n)
                if z is None:
                    gm.remove(t, cond, "%s ends" % info["spell"])
                elif info["spell"] == "Web" and not self.inside(z, self.party.pos(t)):
                    gm.remove(t, cond, "out of the webs")

    def hush(self):
        """Silence: Deafened while inside the Sphere."""
        gm, sim = self.sim.gm_rules, self.sim
        if gm is None:
            return
        quiet = [z for z in self.zones() if SPELLS[z["spell"]].get("silence")]
        for o in sim.sc["combatants"]:
            i = o["id"]
            z = next((z for z in quiet if self.inside(z, self.party.pos(i))), None)
            info = (gm.cond.get(i) or {}).get("Deafened")
            if z and not info and not sim.down(i):
                gm.add(i, "Deafened", "(inside %s's Silence)" % self.name(z["owner"]), by=z["owner"], spell="Silence", zone=z["n"])
            elif info and info.get("spell") == "Silence" and not z:
                gm.remove(i, "Deafened", "out of the Silence")

    def ended(self, z):
        """map_layers.Layers.sweep: a zone left the map."""
        self.tidy()
        self.hush()

    def silenced(self, me):
        return next((z for z in self.zones() if SPELLS[z["spell"]].get("silence") and self.inside(z, self.party.pos(me))), None)

    def before_cast(self, me, cmd):
        """Silence: "Casting a spell that includes a Verbal component is impossible there" (Subtle Spell drops it)."""
        z = self.silenced(me)
        if not z:
            return None
        import spell_rules
        rules = spell_rules.spell(cmd.get("spell")) or {}
        metas = cmd.get("metamagic") or []
        metas = [metas] if isinstance(metas, str) else metas
        if (rules.get("components") or {}).get("v") and "Subtle Spell" not in metas:
            raise ms.EffectError("%s stands in %s's Silence: a spell with a Verbal component can't be cast there."
                                 % (self.name(me), self.name(z["owner"])))
        return None

    def save_mod(self, t, ability):
        """Conjure Animals: the caster has Advantage on Strength saves within 5 feet of the pack."""
        if str(ability).startswith("str"):
            for z in self.zones():
                if z.get("pack") and z["owner"] == t and self.near_pack(z, self.party.pos(t), ft=5):
                    return 0, "Conjure Animals"
        return 0, ""

    # ------------------------------------------------------------------ actions
    def held_by(self, me):
        gm = self.sim.gm_rules
        info = (gm.cond.get(me) or {}).get("Restrained") if gm else None
        return info if info and info.get("spell") in ("Web", "Entangle") and info.get("zone") is not None else None

    def move_needs(self, me, z, op):
        t, c = self.fight.turn_state, self.sim.by_id(me)
        needs = [rq.able(self.fight, me)]
        if op == "move_beam":
            needs.append(rq.need("a later turn", z["cast_serial"] != self.serial(),
                                 "Moonbeam moves on a later turn than the one it was cast."))
            needs.append(rq.action_free(self.fight, me, "moving the Moonbeam"))
        else:
            needs.append(rq.need("moved this turn", bool(t) and t.get("movement", 0) < t.get("speed", 0),
                                 "The pack moves when %s moves on the turn: move first." % c["name"]))
            needs.append(rq.need("once a turn", self.moved.get(me) != self.serial(), "The pack has moved this turn."))
        return needs

    def act(self, me, cmd):
        op, sim = cmd["op"], self.sim
        if op == "break_free":
            info = self.held_by(me)
            if not info:
                raise ms.EffectError("%s is not held by webs or plants." % self.name(me))
            ms.check([rq.able(self.fight, me), rq.action_free(self.fight, me, "breaking free")])
            t = self.fight.turn_state
            t["action_used"], t["attacks_left"] = True, 0
            import live_lore
            bonus = live_lore.check_bonus(sim.by_id(me), "str", "Athletics")[0]
            dc = next((z["dc"] for z in self.zones() if z["n"] == info["zone"]), 10)
            d20 = sim.rng.randint(1, 20)
            ok = d20 + bonus >= dc
            sim.say("dice", "%s tries to break free of the %s: Strength (Athletics) d20 %d %+d = %d vs DC %d -> %s" % (
                self.name(me), "webs" if info["spell"] == "Web" else "plants", d20, bonus, d20 + bonus, dc,
                "free" if ok else "still held"))
            if ok:
                sim.gm_rules.remove(me, "Restrained", "broke free")
            return {"ok": True, "result": op, "free": ok}
        spell = MOVES[op]
        z = next((z for z in self.zones() if z["owner"] == me and z["spell"] == spell), None)
        if z is None:
            raise ms.EffectError("%s holds no %s." % (self.name(me), spell))
        ms.check(self.move_needs(me, z, op))
        x, y = ms.square(cmd, spell)
        far = max(abs(x - z["origin"][0]), abs(y - z["origin"][1])) * self.units()
        most = SPELLS[spell]["move_ft"]
        if far > most + 0.01:
            raise ms.EffectError("%s moves up to %d ft; that square is %d ft away." % (spell, most, far))
        before = set(self.creatures_in(z))
        if op == "move_beam":
            t = self.fight.turn_state
            t["action_used"], t["attacks_left"] = True, 0
        self.moved[me] = self.serial()
        self.relocate(z, x, y)
        sim.say("turn", "%s moves %s to square (%d, %d)%s" % (self.name(me), {"move_beam": "the Moonbeam", "move_pack": "the pack",
                                                                               "move_celestial": "the pillar of light"}[op],
                                                               x, y, " (a Magic action)" if op == "move_beam" else ""))
        for t in self.creatures_in(z):
            if t not in before:
                self.later_save(z, t, "moved")
        return {"ok": True, "result": op, "at": [x, y]}


# ---------------------------------------------------------------------- the hooks (sim/more_spells.py)
def _st(sim):
    return getattr(sim, "_spell_zones", None)


def difficult_cells(sim, me=None):
    st = _st(sim)
    return st.difficult_cells(me) if st else set()


def keep_off_cells(sim, me):
    st = _st(sim)
    return st.keep_off_cells(me) if st else set()


def on_step(sim, name, x0, y0, x1, y1):
    st = _st(sim)
    if st:
        st.on_step(name, x0, y0, x1, y1)


def creature_turn_start(sim, me):
    st = _st(sim)
    return st.creature_turn_start(me) if st else ""


def turn_ended(sim, me):
    st = _st(sim)
    if st:
        st.turn_ended(me)


def on_hurt(sim, src, tid, amount, kinds=""):
    st = _st(sim)
    if st:
        st.on_hurt(src, tid, amount, kinds)


def save_mod(sim, t, ability):
    st = _st(sim)
    return st.save_mod(t, ability) if st else (0, "")


def before_cast(fight, me, cmd):
    st = _st(fight.sim)
    return st.before_cast(me, cmd) if st else None


def adjust_offers(fight, me, out):
    st = _st(fight.sim)
    if st:
        st.adjust_offers(me, out)


def ended(sim, zones):
    st = _st(sim)
    if st:
        st.ended(zones)
