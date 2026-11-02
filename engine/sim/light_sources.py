"""LIGHTS-01 (GM 2026-10-26, the Documents page goal "Light sources in play"): torches, lanterns, lamps, candles and the
light spells in a live fight, and their burning time on the adventure day. The engine decides; the table only draws
what this module publishes (LiveFight snapshot "lights"), and every rule that already reads light reads these lights
too: they go into the map's lighting (Sim.walls["lighting"], mythastria_core/lighting.py) as carried or placed lights,
so Sim.sees / sees_square (the party's fog, each player's map), attacks against an unseen target, Hide and the
creatures' own sight (mythastria_core/ai_turn.py _sight) follow the carrier as it moves.

SRD 5.2.1 (Equipment: Adventuring Gear; Spells; Rules Glossary "Bright Light", "Dim Light", "Darkness", "Darkvision"):
- Torch: burns 1 hour, Bright Light in a 20-foot radius and Dim Light for an additional 20 feet. When you take the
  Attack action you can attack with it as a Simple Melee weapon: 1 Fire damage on a hit.
- Lantern, Hooded: burns Oil, Bright 30 ft and Dim 30 ft more. As a Bonus Action, lower the hood (Dim Light in a 5-foot
  radius) or raise it again.
- Lantern, Bullseye: burns Oil, Bright Light in a 60-foot Cone and Dim Light for an additional 60 feet.
- Lamp: burns Oil, Bright 15 ft and Dim 30 ft more. Candle: 1 hour, Bright 5 ft and Dim 5 ft more.
- Oil: a flask is fuel for a Lamp or Lantern, which then burns for 6 hours.
- Tinderbox: lighting a Candle, Lamp, Lantern or Torch with it takes a Bonus Action.
- Light (cantrip, Action, Touch, 1 hour): an object not worn or carried by someone else sheds Bright 20 ft and Dim
  20 ft more. Casting it again ends the earlier one.
- Continual Flame (level 2, Action, Touch, until dispelled; ruby dust worth 50+ GP, consumed): a flame on an object you
  touch, Bright 20 ft and Dim 20 ft more; it can be covered or hidden but not smothered or quenched.
- Daylight (level 3, Action, 60 ft, 1 hour): sunlight in a 60-foot-radius Sphere from a point (or around an object not
  worn or carried), Bright Light and Dim Light for an additional 60 feet. It dispels a Darkness of level 3 or lower
  whose area overlaps it.
- Darkness (MAP-LAYERS-01): "nonmagical light can't illuminate it"; it dispels a light made by a spell of level 2 or
  lower (Light, Continual Flame) whose area overlaps it.
- Dim Light: Lightly Obscured, Disadvantage on Wisdom (Perception) checks that rely on sight (passive: -5). Darkness:
  Heavily Obscured, a creature is Blinded while trying to see something there (a sight-based check fails).

Costs in Play live (SRD 5.2.1 "Interacting with Things": one object interaction is free during the move or action):
light it (a Tinderbox: a Bonus Action; from another flame within 5 ft: an action); douse it or cover a magical light,
pick it up, hand it to an ally within 5 ft: the free object interaction (GM 2026-10-27: "all dousing of light is free
outside the magic rules": only a spell's own text limits it, Continual Flame covered but not quenched, Daylight not at
all); drop it: no cost (the light stays lit on the square); the hood:
a Bonus Action; fill a Lamp or Lantern with Oil: the Utilize action. A creature that drops to 0 Hit Points drops what it
holds (Unconscious), and the light goes on burning where it falls.

GM rulings, confirmed 2026-10-27 ("the rest are fine"; SRD_GAPS_PLAN.md "Built 2026-10-26: light sources"): lighting without a
Tinderbox from another flame is an action; pointing a Bullseye Lantern is free whenever its carrier wants; filling a
Lamp or Lantern is the Utilize action; a Lamp or Lantern taken from the bag is empty until filled; no free-hand count.
"""
import math

import requirements as rq

ROUND_S = 6
OIL = "oil"
TINDERBOX = "tinderbox"
OIL_S = 6 * 3600
SOURCES = {   # bag item -> what it is (radii in feet; burn_s: how long one burns; oil: a Lamp or Lantern)
    "torch": {"name": "Torch", "bright": 20, "dim": 20, "burn_s": 3600},
    "lantern-hooded": {"name": "Hooded Lantern", "bright": 30, "dim": 30, "oil": True, "hood": True},
    "lantern-bullseye": {"name": "Bullseye Lantern", "bright": 60, "dim": 60, "oil": True, "cone": True},
    "lamp": {"name": "Lamp", "bright": 15, "dim": 30, "oil": True},
    "candle": {"name": "Candle", "bright": 5, "dim": 5, "burn_s": 3600},
}
HOOD_DOWN = (0, 5)                                            # the hood lowered: Dim Light in a 5-foot radius
SPELLS = {
    "Light": {"level": 0, "bright": 20, "dim": 20, "last_s": 3600, "range_ft": 5, "time": "action"},
    "Continual Flame": {"level": 2, "bright": 20, "dim": 20, "last_s": None, "range_ft": 5, "time": "action",
                        "material": "ruby dust", "cost_gp": 50},
    "Daylight": {"level": 3, "bright": 60, "dim": 60, "last_s": 3600, "range_ft": 60, "time": "action", "sunlight": True},
}
CONE_HALF = math.degrees(math.atan(0.5))                      # an SRD Cone is as wide as it is far from its origin
TORCH_ATTACK = {"name": "Torch", "reach": 5, "dmg": "0d1+1", "dmgtype": "fire", "torch": True}


class LightError(ValueError):
    pass


def of(sim):
    return getattr(sim, "lights", None)


def radii(light):
    """(bright, dim) in feet for a light as it is now (a lowered hood: Dim Light in 5 ft)."""
    if light.get("hood") == "down":
        return HOOD_DOWN
    return light["bright"], light["dim"]


def prof(c):
    return 2 + (int(c.get("level", 1) or 1) - 1) // 4


def ability_mod(c, a):
    v = (c.get("abilities") or {}).get(a, c.get(a + "_score", 10)) or 10
    return (int(v) - 10) // 2


def takes_light(c):
    """A creature that can be handed a light: a player character or a humanoid (a horse can't hold a torch)."""
    return bool(c.get("pc")) or "humanoid" in str(c.get("type") or "").lower()


def torch_weapon(c):
    """The Torch as a Simple Melee weapon (every SRD class is proficient with Simple weapons): Strength + Proficiency
    Bonus to hit, 1 Fire damage."""
    return dict(TORCH_ATTACK, atk=ability_mod(c, "str") + prof(c))


# ---------------------------------------------------------------------- what a creature sees (Perception in Dim Light)
def view(sim):
    """The map's lighting for lighting.py (pixel frame), Darkness zones applied by the caller, or None (all Bright)."""
    lit = (sim.walls or {}).get("lighting") if getattr(sim, "walls", None) else None
    if not lit:
        return None
    s, g, u = sim.S, sim.sc.get("grid", 50), sim.sc.get("units", 5)
    out = []
    for l in lit.get("lights") or []:
        if l.get("carrier"):
            st = s.state(str(l["carrier"]).rsplit(".", 1)[-1])
            where = (float(st[2]) * g, float(st[3]) * g)
        elif "pos" in l:
            where = tuple(l["pos"])
        else:
            continue
        out.append({"pos": where, "bright": l["bright_ft"] / u * g, "dim": l["dim_ft"] / u * g, "dir": l.get("dir")})
    return {"ambient": lit.get("ambient", "bright"), "lights": out}


def in_darkness_zone(sim, p):
    env = getattr(sim, "env", None)
    return bool(env) and any(z.get("darkness") and env.inside(z, p) for z in env.of_kind("obscured"))


def level_at(sim, p):
    """The light on square p (lighting.DARK 0, DIM 1, BRIGHT 2); magical Darkness: none."""
    import lighting
    if in_darkness_zone(sim, p):
        return lighting.DARK
    v = view(sim)
    if not v:
        return lighting.BRIGHT
    g = sim.sc.get("grid", 50)
    return lighting.level_at((p[0] * g, p[1] * g), v, getattr(sim, "wall_segs", None) or ())


def seen_level(sim, viewer, target):
    """The light on the target's square as the viewer perceives it (Darkvision one step up within range; Blindsight
    within range: as Bright; magical Darkness: Darkness unless the viewer's senses pierce it)."""
    import lighting
    env, g, u = sim.env, sim.sc.get("grid", 50), sim.sc.get("units", 5)
    v, t = sim.by_id(viewer), sim.by_id(target)
    p, q = env.pos(viewer), env.pos(target)
    far = math.hypot(q[0] - p[0], q[1] - p[1]) * u
    bs = lighting.blindsight_ft(v.get("senses"))
    if bs and far <= bs + 0.01:
        return lighting.BRIGHT
    if in_darkness_zone(sim, q):
        import map_layers
        z = next(z for z in env.of_kind("obscured") if z.get("darkness") and env.inside(z, q))
        return lighting.BRIGHT if map_layers.sees_through(env, viewer, z, p, q) else lighting.DARK
    lit = view(sim)
    if not lit:
        return lighting.BRIGHT
    side = lighting.space_ft(t.get("size"), t.get("space")) / u * g
    dv = lighting.darkvision_ft(v.get("senses")) / u * g
    return lighting.seen_level((p[0] * g, p[1] * g), (q[0] * g, q[1] * g), lit, getattr(sim, "wall_segs", None) or (), dv, side)


def perception(sim, viewer, target):
    """How light changes a sight-based Wisdom (Perception) check of viewer on target: "" (Bright Light), "dis" (Dim
    Light: Disadvantage, -5 passive) or "blind" (Darkness: Blinded for seeing there, the check fails)."""
    try:
        lv = seen_level(sim, viewer, target)
    except Exception:                                            # no positions yet (a stand-in): no change
        return ""
    return "" if lv >= 2 else "dis" if lv == 1 else "blind"


# ---------------------------------------------------------------------- the live fight's lights
class LiveLights:
    def __init__(self, fight):
        self.fight, self.n = fight, 0
        self.lights = []                                         # every light object in this fight
        self.base = None                                         # the map's own lights (scenario), kept as they were
        fight.sim.lights = self
        if fight.sim.sc.get("lighting"):
            self.ensure_walls()
        self.from_creatures()

    def from_creatures(self):
        """Group 1 (GM 2026-10-27): the lights the creatures the game plays hold when the fight starts, from the scenario
        (a combatant's "lights": ["torch"] or [{"kind": "lantern-hooded", "lit": false}]; lit unless it says so; a Lamp
        or Lantern comes filled with Oil). Held like a character's: they follow it, burn their time, and fall where it
        drops at 0 Hit Points (sweep)."""
        for c in self.sim.sc["combatants"]:
            if c.get("pc"):
                continue
            for d in c.get("lights") or []:
                d = {"kind": d} if isinstance(d, str) else dict(d)
                if d.get("kind") not in SOURCES:
                    continue
                l = self.new(d["kind"], c["id"])
                if l.get("oil"):
                    l["left_s"] = OIL_S
                l["lit"] = bool(d.get("lit", True))
        if self.lights:
            self.sync()

    @property
    def sim(self):
        return self.fight.sim

    @property
    def party(self):
        return self.sim.party

    def name(self, i):
        return self.sim.by_id(i)["name"]

    def round(self):
        try:
            return int(self.sim.S.round())
        except Exception:
            return 0

    # ------------------------------------------------------------------ the map's lighting
    def ensure_walls(self):
        """A map without walls gets an empty wall map so its lighting reaches every sight rule (Sim.__init__ only sets
        one up for maps with walls or water)."""
        sim = self.sim
        if sim.walls is None:
            import run_sim, map_walls
            sim.walls = run_sim.scenario_walls(sim.sc)
            sim.wall_segs = []
            map_walls.for_map = lambda m: sim.walls if m == run_sim.MAP else sim._real_for_map(m)
        if "lighting" not in sim.walls:
            lit = sim.sc.get("lighting") or {}
            g = sim.sc.get("grid", 50)
            sim.walls["lighting"] = {"ambient": lit.get("ambient", "bright"), "lights": [
                dict({"bright_ft": l.get("bright_ft", 0), "dim_ft": l.get("dim_ft", 0)},
                     **({"carrier": "combattracker.list." + l["carrier"]} if l.get("carrier") else {"pos": [l["x"] * g, l["y"] * g]}))
                for l in lit.get("lights") or []]}
        if self.base is None:
            self.base = [l for l in sim.walls["lighting"]["lights"] if "src" not in l]
        return sim.walls["lighting"]

    def in_darkness(self, p):
        return in_darkness_zone(self.sim, p)

    def ambient(self):
        lit = (self.sim.walls or {}).get("lighting") if self.sim.walls else None
        return (lit or self.sim.sc.get("lighting") or {}).get("ambient", "bright")

    def set_ambient(self, ambient):
        """The GM sets the light the map has without any source: bright, dim or dark (SRD 5.2.1 Vision and Light)."""
        if ambient not in ("bright", "dim", "dark"):
            raise LightError("The map's own light is bright, dim or dark.")
        lit = self.ensure_walls()
        lit["ambient"] = ambient
        self.sim.sc.setdefault("lighting", {"lights": []})["ambient"] = ambient
        self.sim.say("note", "The GM sets the map's own light: %s" % {"bright": "Bright Light", "dim": "Dim Light",
                                                                      "dark": "Darkness"}[ambient])
        return ambient

    def sync(self):
        """The lit lights into the map's lighting (carried ones follow their carrier there); a lit Torch in hand on the
        sheet as a weapon."""
        if not any(l["lit"] for l in self.lights) and not (self.sim.walls and "lighting" in self.sim.walls):
            for c in self.sim.sc["combatants"]:
                c.pop("torch", None)
            return
        lit = self.ensure_walls()
        g = self.sim.sc.get("grid", 50)
        out = list(self.base)
        for l in self.lights:
            if not l["lit"]:
                continue
            bright, dim = radii(l)
            e = {"bright_ft": bright, "dim_ft": bright + dim, "src": l["n"]}
            e.update({"carrier": "combattracker.list." + l["holder"]} if l["holder"] else {"pos": [l["at"][0] * g, l["at"][1] * g]})
            if l.get("cone"):
                e["dir"] = l.get("aim", 0)
            out.append(e)
        lit["lights"] = out
        self.daylight_zones()
        for c in self.sim.sc["combatants"]:
            if c.get("live") or c.get("torch"):
                self.torch_on(c["id"])

    def where(self, l):
        return tuple(self.party.pos(l["holder"])) if l["holder"] else tuple(l["at"])

    def daylight_zones(self):
        """Daylight is sunlight (Sunlight Sensitivity and the like): a "sunlit" zone over its Bright Light."""
        env = self.sim.env
        env.zones[:] = [z for z in env.zones if not z.get("daylight")]
        u = self.sim.sc.get("units", 5)
        for l in self.lights:
            if l["lit"] and l.get("sunlight"):
                x, y = self.where(l)
                r = l["bright"] / u
                env.zones.append({"id": "daylight-%d" % l["n"], "kind": "sunlit", "daylight": l["n"], "circle": [x, y, r],
                                  "rect": [int(math.floor(x - r)), int(math.floor(y - r)), int(math.ceil(x + r)), int(math.ceil(y + r))]})

    # ------------------------------------------------------------------ time
    def left(self, l, rnd=None):
        """Seconds of burning (or of the spell) left, None: no end."""
        if l["left_s"] is None:
            return None
        if not l["lit"]:
            return l["left_s"]
        rnd = self.round() if rnd is None else rnd
        return max(0, l["left_s"] - ROUND_S * max(0, rnd - l["since"]))

    def settle_time(self, l):
        """Fix the time burned so far (before it is doused, handed over or written to the day)."""
        if l["lit"] and l["left_s"] is not None:
            l["left_s"], l["since"] = self.left(l), self.round()

    def sweep(self):
        """Lights that burned out, spells that ended, lights a Darkness dispels, Daylight dispelling a Darkness, and lights
        a creature at 0 Hit Points drops (never under the publication lock: it logs). -> True when anything changed."""
        changed = False
        say = lambda text: self.sim.say("dice", text)
        for l in list(self.lights):
            if l["holder"] and self.sim.down(l["holder"]):
                self.settle_time(l)
                l["at"], who = list(self.party.pos(l["holder"])), l["holder"]
                l["holder"] = None
                say("%s drops the %s (Unconscious)%s" % (self.name(who), l["name"], ": it burns on the ground" if l["lit"] else ""))
                changed = True
            if l["lit"] and l["left_s"] is not None and self.left(l) <= 0:
                changed = True
                self.settle_time(l)
                if l.get("spell"):
                    self.lights.remove(l)
                    say("%s's %s ends: its time is over" % (l["owner_name"], l["spell"]))
                elif l.get("oil"):
                    l["lit"], l["left_s"] = False, 0
                    say("The %s runs out of Oil and goes out" % l["name"])
                else:
                    self.lights.remove(l)
                    say("The %s burns out" % l["name"])
        env = self.sim.env
        dark = [z for z in env.of_kind("obscured") if z.get("darkness") and z.get("spell")]
        for l in list(self.lights):
            if not l.get("spell") or not l["lit"]:
                continue
            p, reach = self.where(l), (l["bright"] + l["dim"]) / self.sim.sc.get("units", 5)
            for z in dark:
                cx, cy, r = z["circle"]
                if math.hypot(p[0] - cx, p[1] - cy) > r + reach:
                    continue
                if l["level"] <= 2:                                # Darkness dispels Light and Continual Flame
                    self.lights.remove(l)
                    say("The Darkness dispels %s's %s (a spell of level 2 or lower whose light overlaps it)" % (
                        l["owner_name"], l["spell"]))
                    changed = True
                    break
                if l.get("sunlight") and not z.get("ended"):      # Daylight dispels a Darkness of level 3 or lower
                    z["ended"] = "dispelled by %s's Daylight" % l["owner_name"]
                    self.party.end_concentration(z["owner"])
                    changed = True
        if changed:
            self.fight.layers.sweep()
        self.sync()
        return changed

    def turn_start(self, me):
        self.sweep()

    # ------------------------------------------------------------------ the adventure day
    def from_day(self, day):
        """The lights each carried character holds (lit ones go on burning), from the day (sim/rests.py)."""
        held = (day or {}).get("lights") or {}
        for c in self.sim.sc["combatants"]:
            for d in held.get(c["name"], []) if c.get("pc") else []:
                l = self.new(d["kind"], c["id"], spell=d.get("spell"), owner_name=d.get("owner_name"))
                l.update(lit=bool(d.get("lit")), left_s=d.get("left_s"), hood=d.get("hood", l.get("hood")), since=self.round())
        self.sync()

    def to_day(self, day):
        """What each character holds when the fight ends; lights left on the ground stay behind. -> log lines."""
        pcs = {c["id"]: c["name"] for c in self.sim.sc["combatants"] if c.get("pc")}
        held, lines = {}, []
        for l in self.lights:
            self.settle_time(l)
            if l["holder"] in pcs:
                held.setdefault(pcs[l["holder"]], []).append({k: l.get(k) for k in ("kind", "spell", "owner_name", "lit", "left_s", "hood")})
            else:
                lines.append("a %s left %s on the map" % (l["name"], "burning" if l["lit"] else "unlit"))
        if day is not None:
            day["lights"] = held
        return lines

    # ------------------------------------------------------------------ one light
    def new(self, kind, holder, at=None, spell=None, owner_name=None):
        self.n += 1
        if spell:
            s = SPELLS[spell]
            l = {"n": self.n, "kind": "spell", "spell": spell, "name": spell if spell != "Light" else "Light spell",
                 "bright": s["bright"], "dim": s["dim"], "left_s": s["last_s"], "level": s["level"],
                 "sunlight": bool(s.get("sunlight")), "owner_name": owner_name or "", "covered": False}
        else:
            s = SOURCES[kind]
            l = {"n": self.n, "kind": kind, "name": s["name"], "bright": s["bright"], "dim": s["dim"],
                 "left_s": s.get("burn_s", 0 if s.get("oil") else None), "oil": bool(s.get("oil")), "cone": bool(s.get("cone"))}
            if s.get("hood"):
                l["hood"] = "up"
        l.update(holder=holder, at=list(at) if at else None, lit=False, since=self.round(), aim=0)
        self.lights.append(l)
        return l

    def get(self, n):
        try:
            n = int(n)
        except (TypeError, ValueError):
            raise LightError("Which light? Give its number.")
        l = next((l for l in self.lights if l["n"] == n), None)
        if not l:
            raise LightError("No such light here.")
        return l

    def held_by(self, me):
        return [l for l in self.lights if l["holder"] == me]

    def flame_near(self, me):
        """A lit flame within 5 ft to light from (its own or an ally's, or one on the ground); not the Light spell."""
        for l in self.lights:
            if not l["lit"] or l.get("spell") or l.get("hood") == "down":
                continue
            if self._far(me, self.where(l)) <= 5.01:
                return l
        return None

    def _far(self, me, p):
        """Feet from the creature's square to square p on the grid (its own square and the next ones: 5 ft or less)."""
        q, u = self.party.pos(me), self.sim.sc.get("units", 5)
        return max(abs(p[0] - q[0]), abs(p[1] - q[1])) * u

    def turn(self):
        return self.fight.turn_state or {}

    def bag(self, me):
        return self.fight.items.bag(me)

    # ------------------------------------------------------------------ the needs of each choice
    def base_needs(self, me):
        t, c = self.turn(), self.sim.by_id(me)
        return [rq.need("this character's turn", t.get("id") == me, "It is not %s's turn." % c["name"]), rq.able(self.fight, me)]

    def interaction(self, me, what):
        return rq.need("the free object interaction", not self.turn().get("interaction_used"),
                       "%s has used the free object interaction this turn (%s needs it)." % (self.name(me), what))

    def needs(self, me, cmd):
        do, c = cmd.get("do"), self.sim.by_id(me)
        needs = self.base_needs(me)
        if do == "light":                                        # from the bag (item) or one held unlit (light)
            l = self.get(cmd["light"]) if cmd.get("light") is not None else None
            item = l["kind"] if l else cmd.get("item")
            if item not in SOURCES:
                return needs + [rq.need("a light source", False, "Light a Torch, Candle, Lamp or Lantern.")]
            name = SOURCES[item]["name"]
            if l:
                needs += [rq.need("holding it", l["holder"] == me, "%s doesn't hold that %s." % (c["name"], name)),
                          rq.need("not lit yet", not l["lit"], "The %s is already lit." % name)]
                if l.get("oil"):
                    needs.append(rq.need("Oil in it", (l["left_s"] or 0) > 0,
                                         "The %s has no Oil: fill it with a flask of Oil first (the Utilize action)." % name))
            else:
                needs.append(rq.in_bag(self.bag(me), item, name))
                if SOURCES[item].get("oil"):
                    needs.append(rq.need("Oil in it", False, "A %s from the bag is empty: take it out and fill it with a "
                                         "flask of Oil first (the Utilize action)." % name))
            tinder = self.bag(me).count(TINDERBOX) > 0
            if tinder:
                needs.append(rq.bonus_free(self.fight, me, "A Tinderbox"))
            else:
                needs += [rq.need("a Tinderbox or a flame within 5 ft", self.flame_near(me) is not None,
                                  "%s has no Tinderbox and no flame within 5 ft to light it from." % c["name"], rq.LINKS["market"]),
                          rq.action_free(self.fight, me, "Lighting it from another flame")]
            return needs
        if do == "take":                                         # an unlit Lamp or Lantern out of the bag, to fill it
            item = cmd.get("item")
            if item not in SOURCES:
                return needs + [rq.need("a light source", False, "Take out a Torch, Candle, Lamp or Lantern.")]
            return needs + [rq.in_bag(self.bag(me), item, SOURCES[item]["name"]), self.interaction(me, "taking it out")]
        if do == "cast":
            return needs + self.cast_needs(me, cmd)
        l = self.get(cmd.get("light"))
        held = l["holder"] == me
        if do in ("douse", "cover"):
            needs += [rq.need("holding it or within 5 ft", held or (l["at"] and self._far(me, l["at"]) <= 5.01),
                              "The %s is out of reach (hold it or stand within 5 ft)." % l["name"]),
                      rq.need("lit", l["lit"], "The %s is not lit." % l["name"])]
            if l.get("spell") == "Continual Flame":
                needs.append(rq.need("covered, not quenched", do == "cover", "Continual Flame can be covered or hidden but "
                                     "not smothered or quenched."))
            elif l.get("spell") == "Daylight":
                needs.append(rq.need("an object to cover", False, "Daylight can't be covered or doused."))
            elif l.get("spell"):
                needs.append(rq.need("covered", do == "cover", "The Light spell is covered, not doused."))
            return needs + [self.interaction(me, "dousing it")]
        if do == "uncover":
            return needs + [rq.need("holding it", held, "%s doesn't hold it." % c["name"]),
                            rq.need("a covered spell", bool(l.get("spell")) and l.get("covered"), "It is not covered."),
                            self.interaction(me, "uncovering it")]
        if do == "drop":
            return needs + [rq.need("holding it", held, "%s doesn't hold the %s." % (c["name"], l["name"]))]
        if do == "pick_up":
            return needs + [rq.need("on the ground within 5 ft", bool(l["at"]) and self._far(me, l["at"]) <= 5.01,
                                    "The %s is not on the ground within 5 ft." % l["name"]),
                            self.interaction(me, "picking it up")]
        if do == "hand":
            tid = cmd.get("target")
            t = next((o for o in self.sim.sc["combatants"] if o["id"] == tid), None)
            ok = t is not None and tid != me and self.party.side(tid) == self.party.side(me) and not self.sim.down(tid) \
                and self.party.dist(me, tid) <= 5.01
            return needs + [rq.need("holding it", held, "%s doesn't hold the %s." % (c["name"], l["name"])),
                            rq.need("an ally within 5 ft", ok, "Hand it to an ally within 5 ft (standing)." if t is None or tid == me
                                    else "%s is not an ally within 5 ft who can take it." % t["name"]),
                            rq.need("hands to hold it", t is None or takes_light(t),
                                    "%s has no hands to hold a light (a character or a humanoid takes it)." % (t or {}).get("name", "")),
                            self.interaction(me, "handing it over")]
        if do == "hood":
            return needs + [rq.need("holding it", held, "%s doesn't hold the %s." % (c["name"], l["name"])),
                            rq.need("a Hooded Lantern", "hood" in l, "Only a Hooded Lantern has a hood."),
                            rq.bonus_free(self.fight, me, "The hood")]
        if do == "aim":
            return needs + [rq.need("holding it", held, "%s doesn't hold the %s." % (c["name"], l["name"])),
                            rq.need("a Bullseye Lantern", l.get("cone"), "Only a Bullseye Lantern is aimed.")]
        if do == "fill":
            return needs + [rq.need("holding it", held, "%s doesn't hold the %s." % (c["name"], l["name"])),
                            rq.need("a Lamp or Lantern", l.get("oil"), "Only a Lamp or Lantern burns Oil."),
                            rq.need("not burning", not l["lit"], "Douse the %s before filling it." % l["name"]),
                            rq.in_bag(self.bag(me), OIL, "a flask of Oil"),
                            rq.action_free(self.fight, me, "the Utilize action")]
        return needs + [rq.need("a light choice", False, "A light is lit, doused, dropped, picked up, handed over, hooded, "
                                "aimed or filled.")]

    # ------------------------------------------------------------------ the light spells
    @staticmethod
    def known(c):
        listed = {sp.get("name") for sp in c.get("spell_list") or [] if isinstance(sp, dict)}
        return [n for n in SPELLS if n in listed]

    def cast_needs(self, me, cmd):
        c, name = self.sim.by_id(me), cmd.get("spell")
        s = SPELLS.get(name)
        needs = [rq.need("the spell on the sheet", s is not None and name in self.known(c),
                         "%s is not on %s's sheet." % (name, c["name"]), rq.LINKS["characters"])]
        if s is None:
            return needs
        needs.append(rq.action_free(self.fight, me, name))
        if s["level"]:
            pool = self.party.pools.get(me) or [self.party.slots.get(me, 0)]
            needs.append(rq.need("a spell slot", sum(pool[s["level"] - 1:]) > 0, "No spell slot of level %d or higher left for %s." % (s["level"], name)))
            needs.append(rq.need("no other slot this turn", self.party.slot_turn.get(me) != self.party.s.turnSerial,
                                 "One spell with a spell slot per turn: %s already spent a slot this turn (SRD 5.2.1)." % c["name"]))
        if s.get("material"):
            have = [b for b in self.bag(me).entries() if int(b.get("qty", 0)) > 0 and s["material"] in str(b.get("name") or "").lower()]
            needs.append(rq.need("%s (%d+ GP) at hand" % (s["material"], s["cost_gp"]), bool(have),
                                 "%s needs %s worth %d+ GP, which it consumes; %s has none in the bag." % (
                                     name, s["material"], s["cost_gp"], c["name"]), rq.LINKS["market"]))
        on = cmd.get("on", "self")                               # self: an object the caster holds; or a square (x, y)
        if on == "square" or name == "Daylight" and on != "self":
            try:
                x, y = int(cmd["x"]), int(cmd["y"])
            except (KeyError, TypeError, ValueError):
                return needs + [rq.need("a square", False, "Choose the square for %s." % name)]
            far = self._far(me, (x, y))
            needs.append(rq.need("in range", far <= s["range_ft"] + 0.01, "That square is %d ft away: %s reaches %d ft%s." % (
                far, name, s["range_ft"], " (Touch)" if s["range_ft"] == 5 else "")))
            needs.append(rq.need("a clear path", not self.party.walled(self.party.pos(me), (x, y)), "A wall is in the way."))
        elif name == "Daylight":
            needs.append(rq.need("a point or an object not carried", False, "Daylight is cast on a point or on an object "
                                 "no one wears or carries: choose a square."))
        return needs

    def cast(self, me, cmd):
        c, name, party = self.sim.by_id(me), cmd["spell"], self.party
        s = SPELLS[name]
        t = self.turn()
        t["action_used"], t["attacks_left"] = True, 0
        lv = party.spend_slot(me, s["level"]) if s["level"] else 0
        if s.get("material"):
            item = next(b for b in self.bag(me).entries() if int(b.get("qty", 0)) > 0 and s["material"] in str(b.get("name") or "").lower())
            self.bag(me).take(item.get("item"), 1, "consumed by %s" % name)
        if name == "Light":                                      # casting it again ends the earlier one
            for old in [l for l in self.lights if l.get("spell") == "Light" and l.get("owner") == me]:
                self.lights.remove(old)
                self.sim.say("dice", "%s's earlier Light spell ends (cast again)" % c["name"])
        on_square = cmd.get("on") == "square" or name == "Daylight"
        at = [int(cmd["x"]), int(cmd["y"])] if on_square else None
        l = self.new(None, None if on_square else me, at=at, spell=name, owner_name=c["name"])
        l.update(owner=me, lit=True, since=self.round())
        self.sim.say("turn", "%s casts %s%s: Bright Light %d ft and Dim Light %d ft more, %s%s" % (
            c["name"], name, " (a level %d slot)" % lv if lv else "", s["bright"], s["dim"],
            "on an object %s holds" % c["name"] if not on_square else "on square (%d, %d)" % tuple(at),
            "; for 1 hour" if s["last_s"] else "; until dispelled"))
        self.sweep()
        return {"spell": name, "light": l["n"]}

    # ------------------------------------------------------------------ doing one
    def do(self, me, cmd):
        ready, rows = rq.check(self.needs(me, cmd))
        if not ready:
            raise LightError(rq.first_why(rows))
        do, c, t, say = cmd["do"], self.sim.by_id(me), self.turn(), lambda text: self.sim.say("turn", text)
        out = {"ok": True, "result": "light", "do": do}
        if do == "cast":
            out.update(self.cast(me, cmd))
            return out
        if do in ("light", "take"):
            if cmd.get("light") is not None:
                l = self.get(cmd["light"])
            else:
                item = cmd["item"]
                self.bag(me).take(item, 1, "taken out in a fight")
                l = self.new(item, me)
            out["light"] = l["n"]
            if do == "take":
                t["interaction_used"] = True
                say("%s takes a %s out of the pack (free object interaction)" % (c["name"], l["name"]))
                self.sync()
                return out
            if self.bag(me).count(TINDERBOX) > 0:
                self.party.use_bonus(me)
                how = "with a Tinderbox (Bonus Action)"
            else:
                t["action_used"], t["attacks_left"] = True, 0
                how = "from the %s (an action)" % self.flame_near(me)["name"]
            l.update(lit=True, since=self.round())
            if l.get("cone"):
                l["aim"] = self.aim_at(me, cmd)
            say("%s lights the %s %s: Bright Light %d ft, Dim Light %d ft more" % (c["name"], l["name"], how, l["bright"], l["dim"]))
        elif do in ("douse", "cover"):
            l = self.get(cmd["light"])
            self.settle_time(l)
            t["interaction_used"] = True
            if l.get("spell"):
                l["lit"], l["covered"] = False, True
                say("%s covers the %s (free object interaction): no light while it is covered" % (c["name"], l["name"]))
            else:
                l["lit"] = False
                say("%s douses the %s (free object interaction)" % (c["name"], l["name"]))
        elif do == "uncover":
            l = self.get(cmd["light"])
            t["interaction_used"] = True
            l.update(lit=True, covered=False, since=self.round())
            say("%s uncovers the %s (free object interaction)" % (c["name"], l["name"]))
        elif do == "drop":
            l = self.get(cmd["light"])
            self.settle_time(l)
            l["holder"], l["at"] = None, [int(round(v)) for v in self.party.pos(me)]
            say("%s drops the %s%s (no action)" % (c["name"], l["name"], ": it lights the ground where it lies" if l["lit"] else ""))
        elif do == "pick_up":
            l = self.get(cmd["light"])
            t["interaction_used"] = True
            self.settle_time(l)
            l["holder"], l["at"] = me, None
            say("%s picks up the %s (free object interaction)" % (c["name"], l["name"]))
        elif do == "hand":
            l = self.get(cmd["light"])
            t["interaction_used"] = True
            self.settle_time(l)
            l["holder"] = cmd["target"]
            say("%s hands the %s to %s (free object interaction)" % (c["name"], l["name"], self.name(cmd["target"])))
        elif do == "hood":
            l = self.get(cmd["light"])
            self.party.use_bonus(me)
            l["hood"] = "up" if l["hood"] == "down" else "down"
            say("%s %s the hood of the Hooded Lantern (Bonus Action): %s" % (
                c["name"], "lowers" if l["hood"] == "down" else "raises",
                "Dim Light in a 5-foot radius" if l["hood"] == "down" else "Bright Light 30 ft and Dim Light 30 ft more"))
        elif do == "aim":
            l = self.get(cmd["light"])
            l["aim"] = self.aim_at(me, cmd)
            say("%s points the Bullseye Lantern (a 60-foot Cone of Bright Light)" % c["name"])
        elif do == "fill":
            l = self.get(cmd["light"])
            self.bag(me).take(OIL, 1, "fuel for the %s" % l["name"])
            t["action_used"], t["attacks_left"] = True, 0
            l["left_s"] = OIL_S
            say("%s fills the %s with a flask of Oil (the Utilize action): 6 hours of light" % (c["name"], l["name"]))
        out["light"] = cmd.get("light", out.get("light"))
        self.sync()
        return out

    def aim_at(self, me, cmd):
        """The Bullseye's direction in degrees (0 east, 90 south on the map) toward square (x, y), or kept."""
        if cmd.get("x") is None or cmd.get("y") is None:
            return next((l["aim"] for l in self.held_by(me) if l.get("cone")), 0)
        p = self.party.pos(me)
        return round(math.degrees(math.atan2(int(cmd["y"]) - p[1], int(cmd["x"]) - p[0])), 1)

    # ------------------------------------------------------------------ the Torch as a weapon
    def torch_on(self, me):
        """A lit Torch in hand puts its attack on the sheet (live_play.EXTRA "torch"); none: it leaves."""
        c = self.sim.by_id(me)
        if any(l["kind"] == "torch" and l["lit"] for l in self.held_by(me)):
            c["torch"] = torch_weapon(c)
        else:
            c.pop("torch", None)

    # ------------------------------------------------------------------ for the sheet and the map
    def offers(self, me):
        c, out = self.sim.by_id(me), []
        bag = self.bag(me)
        entry = lambda label, cmd, time: self.entry(me, label, dict(cmd, op="light"), time)
        for item, s in SOURCES.items():
            if bag.count(item) > 0:
                if s.get("oil"):
                    out.append(entry("Take out a %s" % s["name"], {"do": "take", "item": item}, "interaction"))
                else:
                    out.append(entry("Light a %s" % s["name"], {"do": "light", "item": item},
                                     "bonus" if bag.count(TINDERBOX) else "action"))
        for l in self.held_by(me):
            lid = {"light": l["n"]}
            if not l["lit"] and not l.get("covered"):
                if l.get("oil") and not (l["left_s"] or 0):
                    out.append(entry("Fill the %s with Oil" % l["name"], dict(lid, do="fill"), "action"))
                out.append(entry("Light the %s" % l["name"], dict(lid, do="light"), "bonus" if bag.count(TINDERBOX) else "action"))
            if l["lit"]:
                out.append(entry(("Cover the %s" if l.get("spell") else "Douse the %s") % l["name"],
                                 dict(lid, do="cover" if l.get("spell") else "douse"), "interaction"))
            if l.get("covered"):
                out.append(entry("Uncover the %s" % l["name"], dict(lid, do="uncover"), "interaction"))
            if "hood" in l:
                out.append(entry("%s the hood" % ("Raise" if l["hood"] == "down" else "Lower"), dict(lid, do="hood"), "bonus"))
            if l.get("cone") and l["lit"]:
                out.append(dict(entry("Aim the Bullseye Lantern", dict(lid, do="aim"), "free"), square=True))
            out.append(entry("Drop the %s" % l["name"], dict(lid, do="drop"), "free"))
            for a in self.party.allies(me):
                if a != me and not self.sim.down(a) and self.party.dist(me, a) <= 5.01 and takes_light(self.sim.by_id(a)):
                    out.append(entry("Hand the %s to %s" % (l["name"], self.name(a)), dict(lid, do="hand", target=a), "interaction"))
        for l in self.lights:
            if l["at"] and self._far(me, l["at"]) <= 5.01:
                out.append(entry("Pick up the %s" % l["name"], {"do": "pick_up", "light": l["n"]}, "interaction"))
                if l["lit"] and not l.get("spell"):
                    out.append(entry("Douse the %s on the ground" % l["name"], {"do": "douse", "light": l["n"]}, "interaction"))
        for name in self.known(c):
            s = SPELLS[name]
            if name != "Daylight":
                out.append(dict(entry("Cast %s on something you hold" % name, {"do": "cast", "spell": name, "on": "self"}, "action"),
                                spell=name, level=s["level"]))
            out.append(dict(entry("Cast %s on a square%s" % (name, " (Touch)" if s["range_ft"] == 5 else " (60 ft)"),
                                  {"do": "cast", "spell": name, "on": "square"}, "action"), spell=name, level=s["level"], square=True))
        return out

    def entry(self, me, label, cmd, time):
        try:
            ready, rows = rq.check(self.needs(me, cmd))
        except LightError as e:
            ready, rows = False, [rq.need("it", False, str(e))]
        e = dict(cmd, label=label, time=time, ready=ready)
        if not ready:
            e["why"], e["link"] = rq.first_why(rows), rq.first_link(rows)
        return e

    def publish(self):
        """What the table draws (no logging: this runs under the publication lock). Each light where it is now."""
        rnd, out = self.round(), []
        for l in self.lights:
            try:
                x, y = self.where(l)
            except Exception:
                continue
            bright, dim = radii(l) if l["lit"] else (0, 0)       # dim_ft: the outer radius, as on the map's lighting
            left = self.left(l, rnd)
            out.append({"n": l["n"], "name": l["name"], "kind": l["kind"], "spell": l.get("spell"), "lit": l["lit"],
                        "holder": l["holder"], "at": l["at"], "x": x, "y": y, "bright_ft": bright, "dim_ft": bright + dim,
                        "hood": l.get("hood"), "cone": bool(l.get("cone")), "aim": l.get("aim", 0),
                        "minutes_left": None if left is None else int(math.ceil(left / 60.0)), "covered": bool(l.get("covered"))})
        return {"ambient": self.ambient(), "sources": out}


# ---------------------------------------------------------------------- the adventure day (sim/rests.py, the service)
def advance(day, frm, to):
    """Hours pass on the day: every lit light burns (a Torch or Candle burns away, a Lamp or Lantern runs out of Oil, the
    Light spell and Daylight end after their hour). -> lines, also written to the day's log."""
    import rests
    if to <= frm + 1e-9:
        return []
    lines = []
    for name, held in ((day or {}).get("lights") or {}).items():
        for l in list(held):
            if not l.get("lit") or l.get("left_s") is None:
                continue
            l["left_s"] = l["left_s"] - (to - frm) * 3600
            if l["left_s"] > 0:
                continue
            what = l.get("spell") or SOURCES.get(l["kind"], {}).get("name", l["kind"])
            if SOURCES.get(l["kind"], {}).get("oil"):
                l.update(lit=False, left_s=0)
                lines.append("%s's %s runs out of Oil" % (name, what))
            else:
                held.remove(l)
                lines.append("%s's %s %s" % (name, what, "ends" if l.get("spell") else "burns out"))
    if lines:
        rests.say(day, "; ".join(lines) + ".")
    return lines


def day_view(day):
    """Each character's lights for the adventure home page: [{n, name, lit, minutes_left, hood}]."""
    out = {}
    for name, held in ((day or {}).get("lights") or {}).items():
        out[name] = [{"n": k, "name": l.get("spell") or SOURCES.get(l["kind"], {}).get("name", l["kind"]), "lit": bool(l.get("lit")),
                      "minutes_left": None if l.get("left_s") is None else int(math.ceil(max(0, l["left_s"]) / 60.0)),
                      "hood": l.get("hood"), "spell": bool(l.get("spell"))} for k, l in enumerate(held)]
    return out


def day_op(day, name, k, do, bag=None):
    """Between fights (no action costs): douse or light a light a character holds. Lighting needs a Tinderbox in that
    character's bag or another lit flame in the party (SRD 5.2.1 Tinderbox)."""
    import rests
    held = ((day or {}).get("lights") or {}).get(name) or []
    if not isinstance(k, int) or isinstance(k, bool) or not 0 <= k < len(held):
        raise LightError("%s holds no such light." % name)
    l, what = held[k], held[k].get("spell") or SOURCES.get(held[k]["kind"], {}).get("name", held[k]["kind"])
    if do == "douse":
        if not l.get("lit"):
            raise LightError("The %s is not lit." % what)
        if l.get("spell"):
            raise LightError("A spell's light is covered, not doused: it goes on until it ends.")
        l["lit"] = False
    elif do == "light":
        if l.get("lit"):
            raise LightError("The %s is already lit." % what)
        if l.get("spell"):
            raise LightError("A spell's light is cast, not lit.")
        if SOURCES.get(l["kind"], {}).get("oil") and not (l.get("left_s") or 0):
            raise LightError("The %s has no Oil: fill it in a fight (a flask of Oil, the Utilize action)." % what)
        flame = any(o.get("lit") and not o.get("spell") for hs in day["lights"].values() for o in hs)
        if not ((bag is not None and bag.count(TINDERBOX) > 0) or flame):
            raise LightError("%s has no Tinderbox and the party no flame to light it from." % name)
        l["lit"] = True
    else:
        raise LightError("A light between fights is doused or lit.")
    rests.say(day, "%s %s the %s." % (name, "douses" if do == "douse" else "lights", what))
