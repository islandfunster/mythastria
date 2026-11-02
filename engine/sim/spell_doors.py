"""SPELL-OBJECTS-01 step 2 (GM 2026-10-27: "Mark spells now; casting at doors and other objects comes next"): spells cast
at the map's doors in Play live.

The object rules are SRD 5.2.1's (Rules Glossary, "Breaking Objects"): an object's Armor Class by its material (cloth,
paper, rope 11; crystal, glass, ice 13; wood, bone 15; stone 17; iron, steel 19; mithral 21; adamantine 23) and its Hit
Points by its size and whether it is fragile or resilient (Medium: 4 or 18; Large: 5 or 27); objects are immune to
Poison and Psychic damage. What the SRD leaves to the GM was asked (GM 2026-10-27, each the recommended answer):
- a door is wood, Medium and resilient unless the map says otherwise: AC 15, 18 Hit Points, no Damage Threshold (a map's
  door may carry "material", "size", "resilience" or "hp");
- a door at 0 Hit Points is gone: the doorway is open for good, can't be closed or locked again, and a needle in its
  lock goes with it;
- Knock opening a lock with a Poisoned Needle in it does not set the needle off (no creature works the lock: the needle
  stays armed in the open lock);
- a flammable door a spell sets alight (Fire Bolt: "A flammable object hit by this spell starts burning"; Fireball's
  flammable objects in its area) burns: 1d4 Fire at the start of each round until it breaks or a creature beside it
  puts the fire out with an action.

Step 3 (GM 2026-10-27, "work on each one not done yet"; chose Disintegrate, Arcane Lock, Stone Shape and Heat Metal;
Mending stays the GM's; Arcane Lock opens for the caster's party):
- Disintegrate: "automatically disintegrates a Large or smaller nonmagical object" (a Huge one loses a 10-foot Cube: a
  door all the same): the door is gray dust, the doorway open for good;
- Arcane Lock (touch, a closed door, 25 GP of gold dust it consumes; until dispelled): the door is locked by magic; the
  caster and its party open and close it as if unlocked; "This lock can't be unlocked by any nonmagical means" (no
  Thieves' Tools); Knock suppresses it for 10 minutes (100 rounds); breaking the door still works;
- Stone Shape (touch, a stone door): "shape a stone door or its frame to seal the door shut" (sealed: stuck, so Knock
  unsticks it; no lock to pick) or shape it into an open passage (the door is gone);
- Heat Metal (60 ft, a metal door: iron, steel, mithral, adamantine; Concentration): the door glows red-hot; no
  creature is in contact with a door on the map, so it deals no damage here.
Step 5 (GM 2026-10-27): the Sorcerer's Metamagic on a spell at a door, through the same plan and payment as on a creature
(sim/live_sorcery.py): Quickened (the Bonus Action), Distant (double range; a touch spell from 30 ft), Subtle, Extended
(Heat Metal), and on the attack cantrips Transmuted (a new damage type: no fire, no burning; poison or psychic, no damage)
and Seeking (a missed attack roll rolled again). The options that need creatures (Careful, Empowered, Heightened,
Twinned) are refused by Metamagic's own words. Innate Sorcery's Advantage on spell attacks counts at a door too.
Step 6 (GM 2026-10-27): the map's props are objects too: furniture, containers and statues (not plants, rocks or a
well's or hearth's fixed stone). Each kind has a material and size (PROPS: wood crates, barrels, tables...; cloth sacks;
stone statues, columns, altars; iron anvils, cauldrons, braziers; Large boats, sarcophagi, obelisks; Small lanterns and
bones), a map's prop may say otherwise. A prop's id is its name and square ("crate at (4, 5)"); a cast names it as
cmd["object"]. At 0 Hit Points it is rubble on its square (a container's contents are the GM's to say); a wooden or
cloth one burns like a door. Knock, Arcane Lock and Stone Shape on a prop stay the GM's (no lock or shape the engine
holds on a prop).
Step 7 (GM 2026-10-27): seeing the object. Knock, Heat Metal and Disintegrate name "an object (a target) you can see":
the caster must see the door's near side (or the prop's square) by the table's own sight (Sim.sees_square: walls and
closed doors, light, darkvision, Blindsight, heavy obscurement; a Blinded caster sees nothing). The attack cantrips
don't ask for sight: an attack roll against an object the caster can't see has Disadvantage (SRD 5.2.1 Unseen
Attackers and Targets). Creatures the game plays never cast at objects (GM 2026-10-27: "Never").
Step 8 (GM 2026-10-27, "Yes to recommendation"): Dispel Magic at a door or prop ends the ongoing spells on it, from
its SRD 5.2.1 text: one of level 3 or lower ends, so does one no higher than the slot used; a higher one ends on an
ability check with the caster's spellcasting ability against DC 10 + its level. Here the ongoing spells an object can
hold are Arcane Lock (its level is the slot it was cast with) and Heat Metal (its caster's Concentration ends with it);
Stone Shape and Knock are instantaneous. These door spells keep their Ask the GM entry for everything else they do
(Heat Metal on a foe's armor, Dispel Magic on a creature, Knock on a chest): the card is for doors and props.
A door's lock is then any of: its mundane lock (the map's, picked with Thieves' Tools or opened by Knock), an Arcane
Lock not suppressed, a Stone Shape seal; the map's locked_doors lists a door while one of them holds.

Which spells: a spell marked "also" or "only" (sim/spell_objects.py) that the engine plays at a door here:
- the spell-attack cantrips the general caster plays (Fire Bolt, Eldritch Blast, Starry Wisp): each strike's spell
  attack against the door's AC, the damage of the spell's dice (cmd["door"] in place of a creature);
- Knock (level 2, Action, 60 ft, an object you can see): a locked door becomes unlocked; the loud knock;
- Shatter's Sphere: "A nonmagical object that isn't being worn or carried also takes the damage if it's in the spell's
  area" (the damage the creatures failing their save take); a Sphere whose text sets flammable objects alight
  (Fireball, Delayed Blast Fireball) lights a wooden door in it.
A door is in a Sphere when the middle of the door is within the radius, measured like a creature's square, with no
wall between the point and the door's near side. Every other spell at a door says why (a creature only; or "not played
at a door yet: ask the GM").
"""
import math, re

import more_spells as ms
import requirements as rq

AC = {"cloth": 11, "paper": 11, "rope": 11, "crystal": 13, "glass": 13, "ice": 13, "wood": 15, "bone": 15, "stone": 17,
      "iron": 19, "steel": 19, "mithral": 21, "adamantine": 23}
HP = {("tiny", "fragile"): 2, ("tiny", "resilient"): 5, ("small", "fragile"): 3, ("small", "resilient"): 10,
      ("medium", "fragile"): 4, ("medium", "resilient"): 18, ("large", "fragile"): 5, ("large", "resilient"): 27}
FLAMMABLE = {"cloth", "paper", "rope", "wood"}
IMMUNE = {"poison", "psychic"}
DEFAULT = {"material": "wood", "size": "medium", "resilience": "resilient"}      # GM 2026-10-27
ATTACKS = ("Fire Bolt", "Eldritch Blast", "Starry Wisp")                           # played at a door (general caster)
AREAS = ("Shatter",)                                                                 # damage a door in the area
IGNITE = re.compile(r"flammable object", re.I)
BURN = "1d4"

METAL = {"iron", "steel", "mithral", "adamantine"}
# Step 6 (GM 2026-10-27): the props a spell may target: kind -> (material, size); resilient unless a map says fragile
PROPS = {**{k: ("wood", "medium") for k in ("crate", "barrel", "table", "bench", "bed", "lectern", "weapon_rack",
                                            "net_rack")},
         "boat": ("wood", "large"), "sacks": ("cloth", "medium"),
         **{k: ("stone", "medium") for k in ("statue", "stone_bench", "stone_shelf", "stone_table", "broken_column", "altar",
                                             "throne")},
         "obelisk": ("stone", "large"), "sarcophagus": ("stone", "large"),
         **{k: ("iron", "medium") for k in ("anvil", "cauldron", "bell", "gears", "brazier")},
         "lantern": ("iron", "small"), "crystal": ("crystal", "medium"), "bones": ("bone", "small")}
CONTAINERS = {"crate", "barrel", "sacks", "sarcophagus"}
SUPPRESS_ROUNDS = 100                                                                # Knock on an Arcane Lock: 10 minutes
SPELLS = {
    "Knock": dict(level=2, time="action", shape="door", range_ft=60, appearance="arcane",
                  rider="a locked door you can see becomes unlocked; a loud knock, audible up to 300 feet away"),
    "Arcane Lock": dict(level=2, time="action", shape="door", range_ft=5, appearance="arcane", touch=True,
                        rider="a closed door you touch is locked by magic until dispelled; you and your party open it freely; "
                              "no nonmagical means unlocks it"),
    "Stone Shape": dict(level=4, time="action", shape="door", range_ft=5, appearance="physical", touch=True,
                        choices=["Seal it shut", "Shape an open passage"],
                        rider="a stone door you touch: seal it shut, or shape it into an open passage"),
    "Heat Metal": dict(level=2, time="action", shape="door", range_ft=60, appearance="fire", concentration=True,
                       rider="a metal door you can see glows red-hot (no creature touches it: no damage)"),
    "Dispel Magic": dict(level=3, time="action", shape="door", range_ft=120, appearance="arcane", upcast=True,
                         rider="ends the spells on a door or prop: level 3 or lower (or up to the slot used) at once, a "
                               "higher one on a spellcasting ability check, DC 10 + its level"),
}
OTHERS = ("Disintegrate",)
SEEN = ("Knock", "Heat Metal", "Disintegrate")                                       # "...that you can see" (step 7)                                                           # general caster spells at a door
OPS = ("douse_door",)


class DoorError(ms.EffectError):
    pass


def known(c):
    return [n for n in SPELLS if ms.has_spell(c, n)]


def of(sim):
    st = getattr(sim, "_spell_doors", None)
    if st is None:
        st = sim._spell_doors = Doors(sim)
    return st


def stats(w):
    """A door's (material, AC, Hit Points) from the map's wall entry (the GM's defaults where it says nothing)."""
    mat = str(w.get("material") or DEFAULT["material"]).lower()
    size = str(w.get("size") or DEFAULT["size"]).lower()
    res = str(w.get("resilience") or DEFAULT["resilience"]).lower()
    return mat, AC.get(mat, AC["wood"]), int(w.get("hp") or HP.get((size, res), HP[("medium", "resilient")]))


class Doors:
    def __init__(self, sim):
        self.sim = sim
        self.hp = {}                 # door -> Hit Points left (only once damaged)
        self.broken = set()
        self.burning = {}            # door -> who set it alight
        self.burn_round = None       # the round whose start burned the doors last
        self.arcane = {}             # door -> {"by", "side", "until": round its Knock suppression ends, or None}
        self.sealed = set()          # Stone Shape
        self.heated = {}             # door -> who holds Heat Metal on it
        self.heat_level = {}         # door -> the slot level Heat Metal was cast with (step 8)
        self._mundane = {str(d) for d in (getattr(sim, "walls", None) or {}).get("locked_doors") or []}   # mundane locks

    # ------------------------------------------------------------------ the map
    @property
    def fight(self):
        return getattr(self.sim, "live", None)

    def walls(self):
        return {str(w["id"]): w for w in self.sim.sc.get("walls") or [] if w.get("door")}

    def props(self):
        """Step 6: the map's props a spell may target, as entries like a door's (id: its name and square)."""
        out = {}
        for p in self.sim.sc.get("props") or []:
            kind = str(p.get("kind") or "")
            if kind not in PROPS or "x" not in p or "y" not in p:
                continue
            x, y = int(p["x"]), int(p["y"])
            mat, size = PROPS[kind]
            pid = "%s at (%d, %d)" % (kind.replace("_", " "), x, y)
            out[pid] = {"id": pid, "prop": True, "kind": kind, "x": x, "y": y, "points": [[x, y], [x, y]],
                        "material": p.get("material") or mat, "size": p.get("size") or size,
                        "resilience": p.get("resilience"), "hp": p.get("hp")}
        return out

    def things(self):
        return {**self.walls(), **self.props()}

    def door(self, door_id):
        w = self.things().get(str(door_id))
        if w is None:
            raise DoorError("No door or object called %s here." % door_id)
        return w

    @staticmethod
    def mid(w):
        if w.get("prop"):
            return w["x"], w["y"]
        (ax, ay), (bx, by) = w["points"][0], w["points"][-1]
        return (ax + bx) / 2, (ay + by) / 2

    def sides(self, w):
        """The two squares the door stands between (a door lies on the squares' edge); a prop's own square."""
        if w.get("prop"):
            return [(w["x"], w["y"])]
        (ax, ay), (bx, by) = w["points"][0], w["points"][-1]
        mx, my = self.mid(w)
        if abs(ax - bx) < abs(ay - by):                          # a door along a north-south wall
            return [(int(round(mx - 0.5)), int(round(my))), (int(round(mx + 0.5)), int(round(my)))]
        return [(int(round(mx)), int(round(my - 0.5))), (int(round(mx)), int(round(my + 0.5)))]

    def near_side(self, w, at):
        return min(self.sides(w), key=lambda s: (max(abs(s[0] - at[0]), abs(s[1] - at[1])), abs(s[0] - at[0]) + abs(s[1] - at[1])))

    def ft_to(self, me, w):
        """Feet from the caster to the door: 5 ft from the square beside it (the square's edge is the door)."""
        here = self.sim.party.pos(me)
        s = self.near_side(w, here)
        n = max(abs(s[0] - here[0]), abs(s[1] - here[1]))
        return (max(n, 1) if w.get("prop") else n + 1) * self.sim.sc.get("units", 5), s

    def state(self, door_id):
        w = self.door(door_id)
        mat, ac, most = stats(w)
        walls = self.sim.walls or {}
        d = str(door_id)
        if w.get("prop"):
            return {"material": mat, "ac": ac, "hp": self.hp.get(d, most), "max_hp": most, "broken": d in self.broken,
                    "burning": d in self.burning, "open": False, "locked": False, "flammable": mat in FLAMMABLE,
                    "hot": d in self.heated, "prop": True, "kind": w["kind"], "x": w["x"], "y": w["y"]}
        return {"material": mat, "ac": ac, "hp": self.hp.get(d, most), "max_hp": most, "broken": d in self.broken,
                "burning": d in self.burning, "open": d in walls.get("open_doors", []),
                "locked": d in walls.get("locked_doors", []), "flammable": mat in FLAMMABLE,
                "arcane_lock": self.arcane_on(d), "sealed": d in self.sealed, "hot": d in self.heated}

    def view(self, which=None):
        """For the live snapshot: every door's (and prop's) AC, Hit Points, broken, burning."""
        src = self.walls() if which == "doors" else self.props() if which == "props" else self.things()
        return {d: self.state(d) for d in src}

    # ------------------------------------------------------------------ locks
    def locked_list(self):
        return (self.sim.walls or {}).get("locked_doors") or []

    def mundane(self):
        return self._mundane

    def note_mundane(self, door):
        """A lock the map (or the GM) put on since: a door locked by nothing of ours is locked mundanely."""
        if door in self.locked_list() and not self.arcane_on(door) and door not in self.sealed:
            self.mundane().add(door)

    def arcane_on(self, door):
        a = self.arcane.get(door)
        return bool(a) and (a["until"] is None or int(self.sim.S.round()) >= a["until"])

    def sync(self, door):
        """The map's locked_doors from the door's locks."""
        locked = door not in self.broken and (door in self.mundane() or self.arcane_on(door) or door in self.sealed)
        walls = self.sim.walls
        rest = [d for d in self.locked_list() if str(d) != door]
        walls["locked_doors"] = rest + ([door] if locked else [])
        self.sim.sc["locked_doors"] = list(walls["locked_doors"])

    def no_tools(self, door):
        """Why Thieves' Tools can't open this door now (None: they can try)."""
        if self.arcane_on(door):
            return "The %s is held by Arcane Lock: no nonmagical means unlocks it." % door
        if door in self.sealed:
            return "The %s is sealed shut by Stone Shape: there is no lock to pick." % door
        return None

    def opens_freely(self, door, me):
        """Arcane Lock: the caster and its party open and close the door despite the lock (no other lock on it)."""
        a = self.arcane.get(door)
        return bool(a) and self.arcane_on(door) and door not in self.mundane() and door not in self.sealed \
            and self.sim.by_id(me).get("side") == a["side"]

    def picked(self, door):
        """traps.pick: the mundane lock opened with Thieves' Tools."""
        self.mundane().discard(door)
        self.sync(door)

    # ------------------------------------------------------------------ the checks
    def check(self, me, name, rng_ft, door_id):
        """A door this spell may be cast at: on the map, not broken, in range, no wall on the way. -> the wall entry."""
        w = self.door(door_id)
        if str(door_id) in self.broken:
            raise DoorError("The %s is broken: nothing is left of it to target." % door_id)
        ft, side = self.ft_to(me, w)
        reach = max(rng_ft, 5)
        if ft > reach + 0.01:
            raise DoorError("The %s is %d ft away: out of %s's range (%d ft)." % (door_id, ft, name, reach))
        here = self.sim.party.pos(me)
        if tuple(here) != tuple(side) and self.sim.party.walled(here, side):
            raise DoorError("A wall blocks the line to the %s." % door_id)
        if name in SEEN and not self.seen(me, w):
            raise DoorError("%s cannot see the %s (%s needs an object you can see)." % (
                self.sim.by_id(me)["name"], door_id, name))
        return w

    def seen(self, me, w):
        """Step 7: the caster sees the door's near side (a prop's square) by the table's sight; not while Blinded."""
        gm = getattr(self.sim, "gm_rules", None)
        if gm and gm.has(me, "Blinded"):
            return False
        x, y = self.near_side(w, self.sim.party.pos(me))
        try:
            return bool(self.sim.sees_square(me, x, y))
        except (AttributeError, TypeError, KeyError):
            return True

    def refusal(self, name, what="a door"):
        """Why this spell is never cast at a door (or an object) here (None: it may be)."""
        import spell_objects
        marks = spell_objects.objects(name)
        if marks == "no":
            return "%s targets a creature, not %s." % (name, what)
        if name not in ATTACKS and name not in SPELLS and name not in OTHERS:
            return "%s at %s is not played yet: ask the GM." % (name, what)
        return None

    def door_targets(self, me, name, rng_ft, which="doors"):
        ok, no = [], {}
        why = self.refusal(name, "a door" if which == "doors" else "an object")
        for d in (self.walls() if which == "doors" else self.props()):
            try:
                if why:
                    raise DoorError(why)
                self.check(me, name, rng_ft, d)
                self.fits(name, d)
                ok.append(d)
            except DoorError as e:
                no[d] = str(e)
        return ok, no

    def ongoing(self, d):
        """[(spell, level)] of the spells on this door or prop now (step 8)."""
        out = []
        if d in self.arcane:
            out.append(("Arcane Lock", self.arcane[d].get("level", 2)))
        if d in self.heated:
            out.append(("Heat Metal", self.heat_level.get(d, 2)))
        return out

    def fits(self, name, d):
        """What each spell asks of the door (or prop) itself."""
        if name == "Dispel Magic":
            if not self.ongoing(d):
                raise DoorError("No spell holds the %s: Dispel Magic has nothing to end." % d)
            return
        st = self.state(d)
        if st.get("prop") and name in ("Knock", "Arcane Lock", "Stone Shape"):
            raise DoorError("%s on the %s is the GM's to rule (ask the GM)." % (name, d))
        if name == "Knock" and not st["locked"]:
            raise DoorError("The %s is not locked: Knock has nothing to open." % d)
        if name == "Arcane Lock":
            if st["open"]:
                raise DoorError("The %s is open: Arcane Lock locks a closed door." % d)
            if d in self.arcane:
                raise DoorError("The %s already has an Arcane Lock." % d)
        if name == "Stone Shape" and st["material"] != "stone":
            raise DoorError("Stone Shape shapes stone; the %s is %s." % (d, st["material"]))
        if name == "Heat Metal" and st["material"] not in METAL:
            raise DoorError("Heat Metal heats metal; the %s is %s." % (d, st["material"]))

    def mark_card(self, me, e):
        """A spell card on the sheet: the doors it may be cast at now ("doors") and why not the others."""
        if not self.things() or not e.get("ready") or e.get("shape") not in ("creature", "creatures", "door"):
            return e
        rng = e.get("range_ft") or 0
        if self.walls():
            e["doors"], e["door_refused"] = self.door_targets(me, e["name"], rng)
        if self.props():                                         # step 6: the props it may be cast at
            e["props"], e["prop_refused"] = self.door_targets(me, e["name"], rng, "props")
        self.distant(me, e, rng)
        return e

    def distant(self, me, e, rng):
        """Step 5: the doors (and props) Distant Spell would reach (double range; Touch: 30 ft), for a Sorcerer who
        knows it."""
        if "Distant Spell" in (self.sim.by_id(me).get("metamagic") or []) and rng:
            far = 30 if rng <= 5 else rng * 2
            if self.walls():
                e["distant_doors"] = self.door_targets(me, e["name"], far)[0]
            if self.props():
                e["distant_props"] = self.door_targets(me, e["name"], far, "props")[0]

    # ------------------------------------------------------------------ casting
    def cast(self, me, cmd):
        """Knock (more_spells owns it) and any spell cast with cmd["door"]."""
        name = cmd.get("spell")
        if cmd.get("door") is None and cmd.get("object") is not None:        # step 6: a prop, named like a door
            cmd = dict(cmd, door=cmd["object"])
        if cmd.get("door") is None:
            raise DoorError("Choose a door for %s." % name)
        why = self.refusal(name, "an object" if self.door(cmd["door"]).get("prop") else "a door")
        if why:
            raise DoorError(why)
        if name in SPELLS:
            return self.spell(me, cmd)
        if name == "Disintegrate":
            return self.disintegrate(me, cmd)
        return self.attack(me, cmd)

    def metamagic(self, me, name, s, cmd, attack=False):
        """(the entry as the chosen Metamagic changes it, the plan or None): checked by live_sorcery, nothing spent."""
        if not cmd.get("metamagic"):
            return s, None
        import live_sorcery
        try:
            return live_sorcery.of(self.fight).plan(me, name, s, cmd, attack=attack)
        except live_sorcery.SorceryError as e:
            raise DoorError(str(e))

    def pay(self, me, name, plan):
        if plan:
            import live_sorcery
            live_sorcery.of(self.fight).pay(me, name, plan)

    def timed(self, needs, me, name, s):
        """Quickened Spell: the Bonus Action instead of the Action."""
        if s.get("time") != "bonus":
            return needs
        return [n for n in needs if n.get("need") != "the Action free"] + [rq.bonus_free(self.fight, me, name)]

    def spell_needs(self, me, name, slot=None, time=None):
        s, fight = SPELLS[name], self.fight
        needs = ms.cast_needs(fight, me, name, s["level"], time or s["time"], slot)
        comp = self.component(me, name)
        if comp:
            needs.append(comp[0])
        return needs

    def component(self, me, name):
        """Arcane Lock's 25 GP of gold dust: at hand in the bag (live_general's check)."""
        import live_general, spell_rules
        rules = spell_rules.spell(name)
        if not rules or not rules["components"].get("cost_gp"):
            return None
        return live_general.of(self.fight).component(me, {"components": rules["components"], "name": name})

    def spell(self, me, cmd):
        """Knock, Arcane Lock, Stone Shape, Heat Metal: checked, then the time, the slot and a consumed component."""
        name, door, fight = cmd["spell"], str(cmd["door"]), self.fight
        s, plan = self.metamagic(me, name, dict(SPELLS[name]), cmd)
        ms.check(self.spell_needs(me, name, cmd.get("slot"), s["time"]))
        w = self.check(me, name, s["range_ft"], door)
        self.fits(name, door)
        choice = cmd.get("choice") or (s.get("choices") or [None])[0]
        if s.get("choices") and choice not in s["choices"]:
            raise DoorError("%s: choose one of %s." % (name, ", ".join(s["choices"])))
        c, party = self.sim.by_id(me), self.sim.party
        self.note_mundane(door)
        comp = self.component(me, name)
        slot = ms.spend(fight, me, s["time"], s["level"], cmd.get("slot"))
        self.pay(me, name, plan)
        if comp and __import__("spell_rules").spell(name)["components"].get("consumed"):
            bag, have = comp[1]
            bag.take(have[0]["item"], 1, "%s's %s" % (c["name"], name))
        if s.get("concentration"):                               # held as itself (as live_general.hold)
            party.start_concentration(me, name)
            party.__dict__.setdefault("gm_concentration", {})[me] = name
            ms.extended(fight, me, name, plan)
        label = "%s casts %s (a level %d slot)" % (c["name"], name, slot)
        if name == "Knock":
            return self.knock(me, door, w, label)
        if name == "Dispel Magic":
            return self.dispel(me, door, w, label, slot)
        if name == "Arcane Lock":
            self.arcane[door] = {"by": me, "side": c.get("side"), "until": None, "level": slot}
            self.sync(door)
            self.sim.say("dice", "%s on the %s: it is locked by magic until dispelled; %s and the party open and close it "
                         "freely; no nonmagical means unlocks it" % (label, door, c["name"]))
        elif name == "Stone Shape" and choice == "Seal it shut":
            self.sealed.add(door)
            self.sync(door)
            self.sim.say("dice", "%s on the %s: the stone of the door and its frame flows together, sealing it shut" % (label, door))
        elif name == "Stone Shape":
            self.sim.say("dice", "%s on the %s: the stone door is shaped into an open passage" % (label, door))
            self.smash(door, "is gone: shaped into an open passage (it can't be closed or locked again)")
        elif name == "Heat Metal":
            self.heated[door], self.heat_level[door] = me, slot
            self.sim.say("dice", "%s on the %s: the door glows red-hot; no creature is touching it, so no one takes the 2d8 Fire"
                         % (label, door))
        return self.effect(me, name, s["appearance"], w, door)

    def dispel(self, me, door, w, label, slot):
        """Dispel Magic (SRD 5.2.1) on a door or prop: each ongoing spell on it, by its level."""
        c = self.sim.by_id(me)
        self.sim.say("dice", "%s at the %s" % (label, door))
        for spell, level in self.ongoing(door):
            if level <= max(3, slot):
                ends, why = True, "level %d: it ends" % level
            else:
                mod = int(c.get("spell_mod", 0))
                d20 = self.sim.rng.randint(1, 20)
                ends = d20 + mod >= 10 + level
                why = "level %d: spellcasting ability check d20 %d + %d = %d vs DC %d -> %s" % (
                    level, d20, mod, d20 + mod, 10 + level, "it ends" if ends else "it holds")
            self.sim.say("dice", "Dispel Magic on the %s's %s (%s)" % (door, spell, why))
            if not ends:
                continue
            if spell == "Arcane Lock":
                self.arcane.pop(door, None)
                self.sync(door)
                self.sim.say("turn", "The %s's Arcane Lock is gone%s" % (door, "" if door in self.locked_list()
                                                                           else ": it is unlocked now"))
            else:
                by = self.heated.pop(door, None)
                self.heat_level.pop(door, None)
                if by is not None and self.sim.party.concentrates(by) == "Heat Metal":
                    self.sim.party.end_concentration(by)
                    self.sim.say("turn", "Heat Metal ends: the %s cools (%s's Concentration ends)" % (door, self.sim.by_id(by)["name"]))
        return self.effect(me, "Dispel Magic", "arcane", w, door)

    def disintegrate(self, me, cmd):
        import live_general
        name, door, fight = cmd["spell"], str(cmd["door"]), self.fight
        g, c = live_general.of(fight), self.sim.by_id(me)
        p = live_general.plan(name)
        s, plan = self.metamagic(me, name, {"time": p["time"], "range_ft": p["range_ft"]}, cmd)
        ms.check(self.timed(g.needs(me, name, cmd.get("slot"))[0], me, name, s))
        w = self.check(me, name, s["range_ft"], door)
        slot = ms.spend(fight, me, s["time"], p["level"], g.slot_for(me, p, cmd))
        self.pay(me, name, plan)
        self.sim.say("dice", "%s casts Disintegrate (a level %d slot) at the %s: a Large or smaller nonmagical object is "
                     "disintegrated automatically" % (c["name"], slot, door))
        self.smash(door, "is disintegrated into gray dust: the doorway is open for good")
        return self.effect(me, name, "arcane", w, door)

    def knock(self, me, door, w, label):
        """One lock: an Arcane Lock is suppressed for 10 minutes first; else the seal (stuck) or the mundane lock."""
        if self.arcane_on(door):
            self.arcane[door]["until"] = int(self.sim.S.round()) + SUPPRESS_ROUNDS
            what = "the Arcane Lock is suppressed for 10 minutes (it can be opened and closed)"
        elif door in self.sealed:
            self.sealed.discard(door)
            what = "the sealed stone comes unstuck"
        else:
            self.mundane().discard(door)
            what = "the lock opens"
        self.sync(door)
        self.sim.say("dice", "%s at the %s: %s; a loud knock, audible up to 300 feet away, sounds from the door" % (label, door, what))
        import traps
        needle = next((t for t in traps.of(self.sim).traps if t["kind"] == "poisoned_needle" and t.get("door") == door
                       and t["armed"]), None)
        if needle:                                               # GM 2026-10-27: no creature works the lock
            self.sim.say("turn", "The needle in the %s's lock does not fire: no one touched the lock (it stays armed)" % door)
        self.sim.say("turn", "The %s is unlocked: it can be opened now" % door if door not in self.locked_list()
                     else "The %s is still locked (another lock holds it)" % door)
        return self.effect(me, "Knock", "arcane", w, door)

    def attack(self, me, cmd):
        import live_general
        name, door, fight = cmd["spell"], str(cmd["door"]), self.fight
        g, c = live_general.of(fight), self.sim.by_id(me)
        p = live_general.plan(name)
        if not p or p["kind"] != "attack":
            raise DoorError("%s at a door is not played yet: ask the GM." % name)
        s, plan = self.metamagic(me, name, {"time": p["time"], "range_ft": p["range_ft"], "kind": p["damage"][0]["type"]},
                                 cmd, attack=True)
        ready, rows = rq.check(self.timed(self.attack_needs(me, name, cmd.get("slot")), me, name, s))   # (Disintegrate: its own)
        if not ready:
            raise DoorError(rq.first_why(rows))
        w = self.check(me, name, s["range_ft"], door)
        c, party = self.sim.by_id(me), self.sim.party
        slot = ms.spend(fight, me, s["time"], p["level"], g.slot_for(me, p, cmd) if p["level"] >= 1 else None)
        self.pay(me, name, plan)
        seeking = bool((plan or {}).get("seeking"))
        n = g.strikes(p, slot, c)
        dice, flat = g.dice(p, slot, c, 0)
        flat += g.mod_bonus(p, c)
        kind = (plan or {}).get("kind") or p["damage"][0]["type"]               # Transmuted Spell
        st = self.state(door)
        self.sim.say("dice", "%s casts %s at the %s (%s, AC %d): %s, %s%s %s" % (
            c["name"], name, door, st["material"], st["ac"], "%d %ss" % (n, p["count"]["word"]) if p["count"] and n > 1
            else "a %s spell attack" % p["attack"], dice, "+%d" % flat if flat else "", kind.capitalize()))
        rng, atk = self.sim.rng, int(c.get("spell_atk", 5))
        adv = bool(getattr(party, "innate_on", lambda i: 0)(me))               # Innate Sorcery: Advantage
        unseen = not self.seen(me, w)                                          # step 7: Disadvantage on an unseen object
        for _ in range(n):
            if door in self.broken:
                break
            crit, hit = self.roll_at(c, name, door, atk, st["ac"], adv, unseen)
            if not hit and seeking:                                            # Seeking Spell: the miss rolled again
                import live_sorcery
                live_sorcery.of(fight).pay_seeking(me, name)
                seeking = False
                crit, hit = self.roll_at(c, name, door, atk, st["ac"], adv, unseen)
            if not hit:
                continue
            amount = g.roll(dice) + (g.roll(dice) if crit else 0) + flat
            self.damage(me, door, amount, kind, name)
            if kind == "fire" and IGNITE.search(p["rules"].get("text") or ""):
                self.ignite(me, door, "%s's %s" % (c["name"], name))
        e = self.effect(me, name, live_general.APPEAR.get(kind, "arcane"), w, door)
        return e

    def roll_at(self, c, name, door, atk, ac, adv=False, dis=False):
        """One spell attack roll at a door or prop: Advantage (Innate Sorcery) and Disadvantage (unseen) cancel."""
        rng = self.sim.rng
        two = adv != dis
        rolls = [rng.randint(1, 20) for _ in range(2 if two else 1)]
        d20 = (max if adv else min)(rolls)
        total = d20 + atk
        crit, hit = d20 == 20, d20 != 1 and (d20 == 20 or total >= ac)
        why = "(Advantage: %s) " % "/".join(map(str, rolls)) if two and adv else \
            "(Disadvantage, it can't see the %s: %s) " % (door, "/".join(map(str, rolls))) if two else \
            "(Advantage and Disadvantage cancel) " if adv and dis else ""
        self.sim.say("dice", "%s's %s at the %s: d20 %s%d + %d = %d vs AC %d -> %s" % (
            c["name"], name, door, why, d20, atk, total, ac, "crit" if crit else "hit" if hit else "miss"))
        return crit, hit

    def sheet_attack(self, c, name):
        """The pregens' way: a cantrip that is the sheet's attack (Hero 4's Fire Bolt is her "ranged")."""
        return any((c.get(k) or {}).get("name") == name for k in ("weapon", "ranged"))

    def attack_needs(self, me, name, slot=None):
        import live_general
        fight, c = self.fight, self.sim.by_id(me)
        if name in live_general.of(fight).known(c) or not self.sheet_attack(c, name):
            return live_general.of(fight).needs(me, name, slot)[0]
        t = fight.turn_state
        return [rq.able(fight, me), rq.need("your turn", bool(t) and t.get("id") == me, "It is not this character's turn."),
                rq.action_free(fight, me, name)]

    def effect(self, me, name, appearance, w, door):
        x, y = self.mid(w)
        return {"spell": name, "appearance": appearance, "shape": "circle", "origin": [x, y], "radius_ft": 5,
                "targets": [], "door": door, "from": list(self.sim.party.pos(me)), "_cmd": {"door": door}}

    # ------------------------------------------------------------------ damage, fire, breaking
    def damage(self, me, door, amount, kind, why):
        if door in self.broken:
            return 0
        st = self.state(door)
        if kind in IMMUNE:
            self.sim.say("dice", "The %s takes no %s damage (objects are immune to Poison and Psychic)" % (door, kind.capitalize()))
            return 0
        left = max(0, st["hp"] - amount)
        self.hp[door] = left
        self.sim.say("dice", "The %s takes %d %s damage (%s): %d of %d Hit Points left" % (
            door, amount, kind.capitalize(), why, left, st["max_hp"]))
        if left <= 0:
            self.smash(door)
        return amount

    def ignite(self, me, door, why):
        st = self.state(door)
        if st["broken"] or st["burning"] or not st["flammable"]:
            return False
        self.burning[door] = me
        self.sim.say("turn", "The %s catches fire (%s): it takes %s Fire at the start of each round until it is put out "
                     "(an action, beside it)" % (door, why, BURN))
        return True

    def smash(self, door, how="breaks apart: the doorway is open for good (it can't be closed or locked again)"):
        """GM 2026-10-27: the door is gone; the doorway stays open for good."""
        import run_sim, traps
        if self.door(door).get("prop"):                          # step 6: rubble on its square
            self.broken.add(door)
            for held in (self.burning, self.heated):
                held.pop(door, None)
            kind = self.door(door)["kind"]
            self.sim.say("turn", "The %s is smashed to rubble%s" % (door, ": what was inside is the GM's to say"
                                                                  if kind in CONTAINERS else ""))
            return
        self.broken.add(door)
        for held in (self.burning, self.arcane, self.heated, self.heat_level):
            held.pop(door, None)
        self.sealed.discard(door)
        self.mundane().discard(door)
        self.sync(door)
        if door not in (self.sim.walls or {}).get("open_doors", []):
            self.sim.set_door(run_sim.MAP, door, True)
        for t in traps.of(self.sim).traps:
            if t["kind"] == "poisoned_needle" and t.get("door") == door and t["armed"]:
                t["armed"], t["disarmed"], t["how"] = False, True, "destroyed with the door"
        self.sim.say("turn", "The %s %s" % (door, how))

    def round_start(self):
        """A burning door takes its 1d4 Fire at the start of each round (the first turn of a new round)."""
        rnd = int(self.sim.S.round())
        if self.burn_round == rnd:
            return
        self.burn_round = rnd
        for door, a in self.arcane.items():                      # a Knock's 10 minutes are over: locked again
            if a["until"] is not None:
                if door not in self.locked_list():
                    self.mundane().discard(door)                 # picked meanwhile
                if rnd >= a["until"]:
                    a["until"] = None
                    self.sync(door)
                    self.sim.say("turn", "Knock's 10 minutes are over: the Arcane Lock holds the %s again" % door)
        for door, by in list(self.heated.items()):             # Heat Metal ends with its Concentration
            if self.sim.party.concentrates(by) != "Heat Metal":
                self.heated.pop(door, None)
        for door, by in list(self.burning.items()):
            n = sum(self.sim.rng.randint(1, 4) for _ in range(1))
            self.damage(by, door, n, "fire", "it burns: %s Fire" % BURN)

    # ------------------------------------------------------------------ the areas (after the engine resolved them)
    def in_sphere(self, origin, radius_ft):
        u, out = self.sim.sc.get("units", 5), []
        for d, w in self.things().items():
            if d in self.broken:
                continue
            mx, my = self.mid(w)
            if math.hypot(mx - origin[0], my - origin[1]) * u > radius_ft + 0.01:
                continue
            side = self.near_side(w, origin)
            if tuple(side) != tuple(origin) and self.sim.party.walled(tuple(origin), side):
                continue
            out.append(d)
        return out

    def in_cone(self, origin, angle_deg, length_ft):
        """Doors whose middle is in the Cone (as wide as it is far, as live_spells.cone_targets reads it), no wall from
        its point to the door's near side."""
        u, out = self.sim.sc.get("units", 5), []
        ux, uy = math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg))
        for d, w in self.things().items():
            if d in self.broken:
                continue
            mx, my = self.mid(w)
            vx, vy = mx - origin[0], my - origin[1]
            along, across = vx * ux + vy * uy, abs(vx * uy - vy * ux)
            if not (0 < along * u <= length_ft + 0.01 and across <= along / 2 + 0.01):
                continue
            side = self.near_side(w, origin)
            if tuple(side) != tuple(origin) and self.sim.party.walled(tuple(origin), side):
                continue
            out.append(d)
        return out

    def in_area(self, effect):
        """The doors a cast's area reaches: a Sphere (Meteor Swarm: each of its Spheres) or a Cone."""
        if effect.get("shape") == "cone" and effect.get("length_ft"):
            return self.in_cone(effect["origin"], effect.get("angle_deg", 0), effect["length_ft"])
        if effect.get("shape") == "circle" and effect.get("radius_ft"):
            return list(dict.fromkeys(d for o in (effect.get("origins") or [effect["origin"]])
                                      for d in self.in_sphere(o, effect["radius_ft"])))
        return []

    def after_area(self, me, name, effect, hits=None):
        """Shatter: each door in the Sphere takes the damage (a nonmagical object); an area that lights flammable
        objects (Fireball, Meteor Swarm, Burning Hands' Cone) sets a wooden door in it alight. Returns the doors it
        reached."""
        if not effect or effect.get("door") or effect.get("shape") not in ("circle", "cone"):
            return []
        import spell_rules
        r = spell_rules.spell(name) or {}
        damages, lights = name in AREAS, bool(r.get("area")) and IGNITE.search(r.get("text") or "")
        if not damages and not lights:
            return []
        doors = self.in_area(effect)
        c = self.sim.by_id(me)
        for d in doors:
            if damages:
                for amount, kind in hits or []:
                    self.damage(me, d, amount, kind, "%s's %s: a nonmagical object in its area" % (c["name"], name))
            if lights:
                self.ignite(me, d, "%s's %s" % (c["name"], name))
        if doors:
            effect["doors"] = doors
        return doors

    # ------------------------------------------------------------------ putting the fire out
    def douse_ways(self, me):
        out, fight = [], self.fight
        for d in self.burning:
            w = self.things().get(d)
            if not w:
                continue
            needs = [rq.able(fight, me), rq.action_free(fight, me, "putting out the fire"),
                     rq.need("beside the door", fight.actions.near(me, w),
                             "%s must stand next to the %s to put the fire out." % (self.sim.by_id(me)["name"], d))]
            out.append((d, needs))
        return out

    def act(self, me, cmd):
        door = str(cmd.get("door"))
        row = next((r for r in self.douse_ways(me) if r[0] == door), None)
        if not row:
            raise DoorError("The %s is not burning." % door)
        ms.check(row[1])
        t = self.fight.turn_state
        t["action_used"], t["attacks_left"] = True, 0
        self.burning.pop(door, None)
        self.sim.say("turn", "%s puts out the fire on the %s (an action)" % (self.sim.by_id(me)["name"], door))
        return {"ok": True, "result": "douse_door", "door": door}

    # ------------------------------------------------------------------ more_spells' interface
    def offers(self, me):
        fight, out = self.fight, []
        if fight is None:
            return out
        c = self.sim.by_id(me)
        for name in known(c):
            s = SPELLS[name]
            e = ms.card(fight, me, name, s, self.spell_needs(me, name), objects="only")
            if c.get("metamagic"):                               # step 5: the Sorcerer's options on this card
                import live_sorcery
                e["metamagic"] = live_sorcery.of(fight).options(me, name, dict(s))
            out.append(self.mark_card(me, e))
        return out

    def adjust_offers(self, me, out):
        import live_general
        for a in out.get("attacks") or []:                       # a cantrip that is the sheet's attack (Fire Bolt)
            if a.get("name") in ATTACKS and self.things():
                p = live_general.plan(a["name"])
                ready = rq.check(self.attack_needs(me, a["name"]))[0]
                a["spell"] = a["name"]
                if ready and p:
                    if self.walls():
                        a["doors"], a["door_refused"] = self.door_targets(me, a["name"], p["range_ft"])
                    if self.props():
                        a["props"], a["prop_refused"] = self.door_targets(me, a["name"], p["range_ft"], "props")
                    self.distant(me, a, p["range_ft"])
        for d, needs in self.douse_ways(me):
            ready, rows = rq.check(needs)
            e = {"op": "douse_door", "door": d, "label": "Put out the fire on the %s" % d, "ready": ready, "bonus": False,
                 "time": "action"}
            if not ready:
                e["why"] = rq.first_why(rows)
            out.setdefault("actions", []).append(e)
        for d in out.get("doors") or []:                         # the door list: its AC, Hit Points, fire, broken
            try:
                st = self.state(d["id"])
            except DoorError:
                continue
            d.update(ac=st["ac"], hp=st["hp"], max_hp=st["max_hp"], material=st["material"], broken=st["broken"],
                     burning=st["burning"])
            if st["broken"]:
                d["ready"] = False


# ---------------------------------------------------------------------- module hooks (more_spells)
def live_turn_start(fight, me):
    if getattr(fight.sim, "_spell_doors", None):
        fight.sim._spell_doors.round_start()


def creature_turn_start(sim, me):
    if getattr(sim, "_spell_doors", None):
        sim._spell_doors.round_start()
    return ""


def adjust_offers(fight, me, out):
    of(fight.sim).adjust_offers(me, out)
