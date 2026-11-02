"""SIM-ENV-01, 2026-10-18: environment zones for the simulator (test lab, the Drowned Way). Rules: SRD 5.2.1, see
docs/development/rules_underwater_sunlight.md. Currents and silt are adventure terrain, not SRD rules.

A scenario may carry "zones": [{"id", "kind", "rect": [x1, y1, x2, y2] (squares, inclusive), ...}] with kinds:
  water     fully immersed: impeded weapon attacks, Resistance to Fire, swimming costs, holding breath
  current   "dx", "dy", "ft": moves a creature that ends its turn inside it (stops at walls and creatures)
  obscured  "level": "heavy" (no sight into, out of or through it) or "light" (Perception only: not used yet)
  shade     no sunlight inside it, on a map whose ambient light is "sunlight"
  sunlit    sunlight inside it, whatever the ambient light
Monster movement is planned by the live bridge, which gets the water zones as the map's water areas (SWIM-01,
2026-10-19): Swim Speed in water, walking Speed on land, double cost without a Swim Speed; air pockets count as water. Monsters do not run out of breath here (the lab's are aquatic,
amphibious or do not breathe). The bridge's own sight for monsters ignores silt (the party's sight respects it)."""
import math, re

import map_layers                                        # MAP-LAYERS-01: spell zones (sim/map_layers.py)

SUNLIGHT_ATTACKS = {"Wight": "Sunlight Sensitivity", "Shadow": "Sunlight Weakness"}
SUNLIGHT_SAVES = {"Shadow": "Sunlight Weakness"}          # Weakness: Disadvantage on every D20 Test


class Environment:   # _Falling (below) is mixed in at the end of the module
    def __init__(self, sim):
        self.sim = sim
        self.landed = set()         # SIM-ENV-02: fliers that fell or landed in a drop
        self.dismounted = set()     # SIM-ENV-04: riders that came off their mounts
        self.zones = list(sim.sc.get("zones") or [])
        self.breath = {}            # creature -> rounds of breath left
        self.exhaustion = {}        # creature -> Exhaustion levels from suffocating
        self.carried = {}           # GM 2026-10-24 (sim/rests.py): Exhaustion carried into the fight (not from air)
        self.given_air = set()      # creatures breathing water by a potion or the ritual
        if self.of_kind("water"):
            self.prepare_dive()

    # ------------------------------------------------------------ where
    def pos(self, i):
        st = self.sim.S.state(i)
        return float(st[2]), float(st[3])

    def of_kind(self, kind):
        # MAP-LAYERS-01: a spell's zone lives with its caster's Concentration
        return [z for z in self.zones if z.get("kind") == kind and map_layers.alive(self, z)]

    @staticmethod
    def inside(z, p):
        if "circle" in z:                                        # MAP-LAYERS-01: a spell's Sphere (centre, radius in squares)
            cx, cy, r = z["circle"]
            return math.hypot(p[0] - cx, p[1] - cy) <= r + 1e-6
        x1, y1, x2, y2 = z["rect"]
        return x1 - 0.5 <= p[0] <= x2 + 0.5 and y1 - 0.5 <= p[1] <= y2 + 0.5

    def zone_at(self, p, kind):
        return next((z for z in self.of_kind(kind) if self.inside(z, p)), None)

    def underwater(self, i):
        p = self.pos(i)
        if any(z.get("state", "working") == "working" for z in self.of_kind("air") if self.inside(z, p)):
            return False                                         # SIM-ESC-01: a working air pocket
        return self.zone_at(p, "water") is not None

    def in_sunlight(self, i):
        p = self.pos(i)
        if self.zone_at(p, "sunlit"):
            return True
        return (self.sim.sc.get("lighting") or {}).get("ambient") == "sunlight" and not self.zone_at(p, "shade")

    # ------------------------------------------------------------ breathing
    def breathes(self, i):
        c = self.sim.by_id(i)
        return bool(c.get("breathes_water") or i in self.given_air or not c.get("pc"))

    def prepare_dive(self):
        """Before the party goes under: the Water Breathing ritual (24 hours, ten creatures) covers everyone; else each
        Potion of Water Breathing goes to someone who cannot breathe water (its owner first)."""
        pcs = [c for c in self.sim.sc["combatants"] if c.get("pc")]
        caster = next((c for c in pcs if c.get("water_breathing_ritual")), None)
        if caster:
            self.given_air |= {c["id"] for c in pcs}
            self.sim.say("dice", "%s casts Water Breathing as a ritual before the dive: the whole party breathes water "
                         "for 24 hours" % caster["name"])
            return
        for owner in [c for c in pcs if c.get("water_breathing_potions")]:
            needing = sorted([c for c in pcs if not self.breathes(c["id"])], key=lambda c: c["id"] != owner["id"])
            for c in needing[:owner["water_breathing_potions"]]:
                self.given_air.add(c["id"])
                self.sim.say("dice", "%s drinks a Potion of Water Breathing from %s before the dive (24 hours)" % (
                    c["name"], owner["name"]))

    def max_breath(self, i):
        c = self.sim.by_id(i)
        if (c.get("abilities") or {}).get("con"):                # the score itself (items can raise saves)
            con = (c["abilities"]["con"] - 10) // 2
        else:
            prof = 2 if (c.get("level") or 1) <= 4 else 3
            con = c.get("con_save", 0) - (prof if c.get("class") in ("fighter", "barbarian") else 0)
        return max(5, 10 * (1 + con))

    # ------------------------------------------------------------ turn ends: currents, breath
    def turn_ended(self, i):
        layers = getattr(self.sim, "layers", None)
        if layers:
            layers.sweep()                                       # MAP-LAYERS-01: zones whose Concentration ended
        if self.sim.down(i) and not self.sim.by_id(i).get("pc"):
            return
        self.drift(i)
        hz = getattr(self.sim, "hazards", None)
        if hz:
            hz.turn_ended(i)                                     # HAZARDS-01: wind, frigid water, Cackle Fever's laughter
        c = self.sim.by_id(i)
        if not c.get("pc"):
            return
        gm = self.sim.gm_rules
        if gm and gm.whelmed(i) and not self.breathes(i):        # Whelm: suffocating unless it breathes water
            self.breath[i] = 0
        elif not self.underwater(i) or self.breathes(i):
            if self.exhaustion.get(i, 0) > self.carried.get(i, 0):
                self.sim.say("dice", "%s breathes again: its %d Exhaustion levels from suffocating end" % (
                    c["name"], self.exhaustion[i] - self.carried.get(i, 0)))
            if self.carried.get(i):
                self.exhaustion[i] = self.carried[i]
            else:
                self.exhaustion.pop(i, None)
            self.breath[i] = self.max_breath(i)
            return
        if i not in self.breath and not (gm and gm.whelmed(i)):
            self.breath[i] = self.max_breath(i)
        if self.breath[i] > 0:
            self.breath[i] -= 1
            if self.breath[i] in (10, 3):
                self.sim.say("dice", "%s has %d rounds of breath left" % (c["name"], self.breath[i]))
            return
        lv = self.exhaustion.get(i, 0) + 1
        self.exhaustion[i] = lv
        self.sim.say("dice", "%s is out of breath: Exhaustion level %d (end of its turn)" % (c["name"], lv))
        if lv >= 6:
            self.exhaustion_death(i, "suffocation")

    def exhaustion_death(self, i, why):
        c = self.sim.by_id(i)
        if not self.sim.party:
            return
        g = self.sim.S
        g.setField(i, "wounds", c["hp"]); g.setField(i, "sim_dying", 0)
        self.sim.party.deaths.setdefault(i, {"successes": 0, "failures": 0, "stable": False, "dead": False})["dead"] = True
        self.sim.say("turn", "%s dies: Exhaustion level 6 (%s)" % (c["name"], why))
        self.sim.party.lose_concentration(i, "dead")             # SIM-MECHANICS-01 (e)

    def add_exhaustion(self, i, n, why):
        """HAZARDS-01: Exhaustion levels that stay after the fight (frigid water, a hazard): kept with the carried ones,
        so breathing again removes only the levels from suffocating."""
        lv = min(6, self.exhaustion.get(i, 0) + n)
        self.carried[i] = min(6, self.carried.get(i, 0) + n)
        self.exhaustion[i] = lv
        self.sim.say("dice", "%s gains %d Exhaustion level%s (%s): level %d" % (
            self.sim.by_id(i)["name"], n, "" if n == 1 else "s", why, lv))
        if lv >= 6:
            self.exhaustion_death(i, why)

    def drift(self, i):
        z = self.zone_at(self.pos(i), "current")
        if not z or not z.get("on", True):                       # SIM-ESC-01: a gate can stop a current
            return
        if self.zone_at(self.pos(i), "rail"):
            return                                               # SIM-ESC-03: holding the guide chains
        g = self.sim.S
        x, y = self.pos(i)
        steps, moved = int(z.get("ft", 5)) // int(self.sim.sc.get("units", 5)), 0
        for _ in range(steps):
            nx, ny = x + z.get("dx", 0), y + z.get("dy", 0)
            if self.square_taken(i, nx, ny) or self.walled((x, y), (nx, ny)):
                break
            x, y, moved = nx, ny, moved + 1
        if moved:
            self.forced_move(i, x, y, "the current")
            self.sim.say("dice", "the current (%s) carries %s %d ft" % (z.get("id", "current"), self.sim.by_id(i)["name"],
                                                                        moved * int(self.sim.sc.get("units", 5))))

    def square_taken(self, me, x, y):
        for c in self.sim.sc["combatants"]:
            if c["id"] != me and not self.sim.down(c["id"]):
                px, py = self.pos(c["id"])
                if abs(px - x) < 0.5 and abs(py - y) < 0.5:
                    return True
        return False

    def walled(self, a, b):
        segs, g = self.sim.wall_segs, self.sim.sc.get("grid", 50)
        return bool(segs) and self.sim.map_walls.blocked((a[0] * g, a[1] * g), (b[0] * g, b[1] * g), segs)

    # ------------------------------------------------------------ sight, attacks, saves, speed
    def blocks_sight(self, a, b, at=None):
        heavy = [z for z in self.of_kind("obscured") if z.get("level") == "heavy"]
        if not heavy:
            return False
        p, q = self.pos(a), (tuple(at) if at else self.pos(b))
        heavy = [z for z in heavy if not map_layers.sees_through(self, a, z, p, q)]   # Blindsight, Truesight, Devil's Sight
        n = max(2, int(math.hypot(q[0] - p[0], q[1] - p[1]) * 4))
        return any(self.inside(z, (p[0] + (q[0] - p[0]) * k / n, p[1] + (q[1] - p[1]) * k / n))
                   for z in heavy for k in range(n + 1))

    def swim_speed(self, i):
        c = self.sim.by_id(i)
        if c.get("swim_ft"):
            return int(c["swim_ft"])
        sp = str(c.get("speed") or "")
        m = __import__("re").search(r"Swim (\d+)", sp)
        return int(m.group(1)) if m else 0

    def d20_penalty(self, i):
        return -2 * self.exhaustion.get(i, 0)

    def attack_mode(self, src, tgt, rng, dmgtype, spell):
        """(Advantage, Disadvantage, notes, modifier) from the environment for one attack roll."""
        adv = dis = False
        notes, mod = [], self.d20_penalty(src)
        if mod:
            notes.append("[Exhaustion %d: %d]" % (self.exhaustion[src], mod))
        if self.underwater(src) and not spell:
            if rng == "R":
                dis = True; notes.append("[underwater: ranged weapon]")
            elif not self.swim_speed(src) and "piercing" not in str(dmgtype).lower():
                dis = True; notes.append("[underwater: no Swim Speed, not Piercing]")
        kind = self.sim.by_id(src)["name"].rstrip("0123456789").strip()
        if kind in SUNLIGHT_ATTACKS and self.in_sunlight(src):
            dis = True; notes.append("[%s]" % SUNLIGHT_ATTACKS[kind])
        hz = getattr(self.sim, "hazards", None)
        if hz:                                                   # HAZARDS-01: Strong Wind
            wind, note = hz.attack_mode(src, rng, spell)
            if wind:
                dis = True; notes.append(note)
        z = map_layers.zone_blind(self, src, tgt)
        if z:
            dis = True; notes.append("[can't see the target: %s]" % z["spell"])
        z = map_layers.zone_blind(self, tgt, src)
        if z:
            adv = True; notes.append("[unseen attacker: %s]" % z["spell"])
        return adv, dis, notes, mod

    def save_dis(self, i):
        kind = self.sim.by_id(i)["name"].rstrip("0123456789").strip()
        return kind in SUNLIGHT_SAVES and self.in_sunlight(i)

    def extra_resist(self, i):
        return "fire" if self.underwater(i) else ""

    def speed(self, i, speed, extra=0):
        """This turn's Speed in the environment: Exhaustion -5 ft a level; in water, the Swim Speed, else each foot costs
        1 extra foot; a rider moves at its mount's Speed (SIM-ENV-04). `extra`: other extra feet per foot (carrying a
        friend). Extra costs add up (SIM-ESC-05: swimming while carrying is 3 ft a foot, 30 ft -> 10 ft)."""
        if self.mount_of(i):
            return self.mount_speed(i)
        speed = max(0, speed - 5 * self.exhaustion.get(i, 0))
        if self.underwater(i):
            swim = self.swim_speed(i)
            if swim:
                speed = max(0, swim - 5 * self.exhaustion.get(i, 0))
            else:
                extra += 1
        if self.zone_at(self.pos(i), "rail"):
            extra += 1                                           # SIM-ESC-03: hand over hand along the chains
        return speed // (1 + extra)


# SIM-ESC-06's swim_in_water (2026-10-18: a creature starting underwater got its Swim Speed written first in its speed
# text) was removed in SWIM-01 (2026-10-19): the live bridge now reads the water zones as the map's water areas.


# ---------------------------------------------------------------------- SIM-ENV-02 (2026-10-18): falling and fliers
def fall_dice(feet):
    """SRD 5.2.1 Falling: 1d6 Bludgeoning per 10 ft fallen, at most 20d6."""
    n = min(20, int(feet) // 10)
    return "%dd6" % n if n else ""


class _Falling:
    """Mixed into Environment: "drop" zones (the floor below a ledge; rect, height), forced moves, fliers aloft."""

    def fly_speed(self, i):
        c = self.sim.by_id(i)
        if c.get("fly_ft"):
            return int(c["fly_ft"])
        m = re.search(r"Fly (\d+)", str(c.get("speed") or ""))
        return int(m.group(1)) if m else 0

    def drop_at(self, p):
        return self.zone_at(p, "drop")

    def aloft(self, i):
        """A flier over a drop is in the air until it lands or falls."""
        return bool(self.fly_speed(i)) and self.drop_at(self.pos(i)) is not None and i not in self.landed

    def can_fly_now(self, i):
        gm = self.sim.gm_rules
        return bool(self.fly_speed(i)) and not self.sim.down(i) and not (
            gm and (gm.has(i, "Prone") or gm.incapacitated(i) or gm.has(i, "Grappled")))

    def fall(self, i, feet, why):
        c = self.sim.by_id(i)
        dice = fall_dice(feet)
        self.landed.add(i)
        self.sim.say("dice", "%s falls %d ft (%s): %s Bludgeoning" % (c["name"], feet, why, dice or "no damage"))
        if not dice:
            return
        g = self.sim.S
        before = g.getField(i, "wounds")
        if self.sim.by_id(i).get("slow_fall"):                   # MONK-01: Slow Fall (Monk 4), a Reaction
            import monk, party as party_mod
            rolled = party_mod.roll(self.sim.rng, dice)
            self.sim.say("dice", "%s = %d Bludgeoning" % (dice, rolled))
            left = monk.slow_fall(self.sim, i, rolled, why)
            if left:
                g.pcDamage(i, i, "", left, False, "bludgeoning")
        else:
            g.pcDamage(i, i, dice, 0, False, "bludgeoning")
        self.sim.settle(0.2)
        gm = self.sim.gm_rules
        if gm and g.getField(i, "wounds") > before and not self.sim.down(i):
            gm.add(i, "Prone", "(landed from the fall)", by=i)

    def forced_move(self, i, x, y, why):
        """A push or a current: into a drop from outside it, a creature that cannot fly now falls."""
        start = self.drop_at(self.pos(i))
        self.sim.S.move(i, x, y)
        if self.rider_of(i) is not None:                         # SIM-ENV-04: the rider goes along, or falls off
            rider = self.rider_of(i)
            off = self.sim.by_id(rider).get("mount_offset") or (0, 0)   # MAP-LAYERS-01: on a Large mount's first square
            self.sim.S.move(rider, x - off[0], y - off[1])
            self.rider_check(i, "its mount is moved against its will")
        z = self.drop_at((x, y))
        if z and z is not start:
            if self.can_fly_now(i):
                self.landed.discard(i)                           # it simply flies
            else:
                self.fall(i, int(z.get("height", 10)), why)

    def lost_flight(self, i):
        """Prone, Incapacitated (Unconscious too) or Speed 0 (Grappled): a flier over a drop falls."""
        if self.aloft(i) and not self.can_fly_now(i):
            z = self.drop_at(self.pos(i))
            self.fall(i, int(z.get("height", 10)), "it loses its flight")


for _name, _fn in list(vars(_Falling).items()):   # the falling rules belong to the same environment object
    if callable(_fn) and not _name.startswith("__"):
        setattr(Environment, _name, _fn)


# ---------------------------------------------------------------------- SIM-ENV-03 (2026-10-18): cover
COVER_AC = {"half": 2, "three-quarters": 5}


def _cover(self, a, b):
    """Cover the target b has against the attacker a: 0, 2 (Half) or 5 (Three-Quarters). A "cover" zone square or
    another standing creature on the line between them counts, except squares next to the attacker."""
    return self.cover_from(self.pos(a), b, a)


def _cover_from(self, p, b, a=None):
    """GM 2026-10-25 (ruling S4; SRD 5.2.1 Cover: "+2 bonus to AC and Dexterity saving throws", only when "an attack or
    other effect originates on the opposite side of the cover"): the cover b has against an effect from point p (a
    spell's origin: its caster for a Cone or Line, its point for a Sphere). a: the creature at p, if any."""
    q = self.pos(b)
    n = max(2, int(math.hypot(q[0] - p[0], q[1] - p[1]) * 4))
    seen, best = set(), 0
    for k in range(1, n):
        x, y = round(p[0] + (q[0] - p[0]) * k / n), round(p[1] + (q[1] - p[1]) * k / n)
        if (x, y) in seen or max(abs(x - p[0]), abs(y - p[1])) <= 1 or (abs(x - q[0]) < 0.5 and abs(y - q[1]) < 0.5):
            continue
        seen.add((x, y))
        z = self.zone_at((x, y), "cover")
        if z:
            best = max(best, COVER_AC.get(z.get("level", "half"), 2))
        elif self.square_taken(a, x, y) and not self.square_taken_by(b, x, y):
            best = max(best, 2)
    return best


def _square_taken_by(self, i, x, y):
    px, py = self.pos(i)
    return abs(px - x) < 0.5 and abs(py - y) < 0.5


Environment.cover = _cover
Environment.cover_from = _cover_from
Environment.square_taken_by = _square_taken_by


# ---------------------------------------------------------------------- SIM-ENV-04 (2026-10-18): mounted combat
def _mount_of(self, rider):
    """The mount a rider sits on (scenario: the rider's "mount" id), or None once it is off."""
    m = self.sim.by_id(rider).get("mount")
    return m if m and rider not in self.dismounted else None


def _controlled_mount(self, m):
    """MAP-LAYERS-01: an independent mount (the GM's choice, mount_mode) keeps its own turn."""
    if self.sim.by_id(m).get("mount_mode") == "independent":
        return False
    return any(_mount_of(self, c["id"]) == m for c in self.sim.sc["combatants"] if c.get("mount"))


def _rider_of(self, m):
    return next((c["id"] for c in self.sim.sc["combatants"] if c.get("mount") and _mount_of(self, c["id"]) == m), None)


def _mount_speed(self, rider):
    m = _mount_of(self, rider)
    return int(str(self.sim.by_id(m).get("speed", "30")).split()[0]) if m else None


def _free_square_near(self, i):
    x, y = self.pos(i)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, 1), (1, -1), (-1, -1), (2, 0), (-2, 0), (0, 2), (0, -2)):
        nx, ny = x + dx, y + dy
        if not self.square_taken(i, nx, ny) and not self.walled((x, y), (nx, ny)):
            return nx, ny
    return None


def _dismount(self, rider, prone, why):
    """The rider comes off into an unoccupied space within 5 ft (Prone after a failed save); a drop there means a fall,
    and so does coming off a mount that was in the air over a drop."""
    m = _mount_of(self, rider)
    in_air = bool(m) and self.aloft(m)
    self.dismounted.add(rider)
    spot = _free_square_near(self, rider)
    c = self.sim.by_id(rider)
    self.sim.say("dice", "%s %s (%s)" % (c["name"], "falls off" if prone else "steps off", why))
    if spot:
        self.forced_move(rider, spot[0], spot[1], "thrown from its mount" if prone else "off its falling mount")
    z = self.drop_at(self.pos(rider))
    if in_air and z and rider not in self.landed and not self.can_fly_now(rider):
        self.fall(rider, int(z.get("height", 10)), "off its mount in the air")
        return
    gm = self.sim.gm_rules
    if prone and gm and not self.sim.down(rider):
        gm.add(rider, "Prone", "(fell off its mount)", by=rider)


def _rider_check(self, m, why):
    """Falling Off: DC 10 Dexterity save when the mount is moved against its will or knocked Prone (a mount at 0 HP is
    Unconscious, so Prone); off on a failure; off on its feet when the mount is down."""
    rider = _rider_of(self, m)
    if rider is None or self.sim.down(rider):
        return
    gm = self.sim.gm_rules
    parts = gm.save_parts(rider, "dex") if gm else {"bonus": 0}
    d20 = self.sim.rng.randint(1, 20)
    ok = d20 + parts["bonus"] >= 10
    self.sim.say("dice", "%s DC 10 Dexterity save to stay mounted (%s): d20 %d %+d = %d -> %s" % (
        self.sim.by_id(rider)["name"], why, d20, parts["bonus"], d20 + parts["bonus"], "stays on" if ok else "falls off"))
    if not ok:
        _dismount(self, rider, True, why)
    elif self.sim.down(m):
        _dismount(self, rider, False, "its mount is down")


Environment.mount_of = _mount_of
Environment.controlled_mount = _controlled_mount
Environment.rider_of = _rider_of
Environment.mount_speed = _mount_speed
Environment.dismount = _dismount
Environment.rider_check = _rider_check
