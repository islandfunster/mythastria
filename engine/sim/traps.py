"""GM 2026-10-24 (the SRD parts still to build, Group 2: docs/development/SRD_GAPS_PLAN.md): traps on a map, read from
SRD 5.2.1 (Gameplay Toolbox: Traps; Equipment: Adventuring Gear and Tools; Rules Glossary: Search, Study, Utilize,
Falling, Difficult Terrain). Every step a character takes on a trap is checked first (sim/requirements.py), with the
reason and a link when it can't be taken.

The eight Toolbox traps, with the "At Higher Levels" tables (bands 1-4, 5-10, 11-16, 17-20):
- Collapsing Roof (Deadly, 1-4). Trigger: a creature crosses a trip wire. Each creature beneath the ceiling: DC 13
  Dexterity save, 2d10 Bludgeoning, half on a success; the rubble is Difficult Terrain. Detect: Search, DC 11 Wisdom
  (Perception); once found the wire is cut or avoided with no check. (5-10: 4d10, DC 15; 11-16: 10d10, DC 17; 17-20:
  18d10, DC 19.)
- Falling Net (Nuisance, 1-4). Trigger: a trip wire; the first creature to cross it: DC 10 Dexterity save or Restrained
  until it escapes (Huge or larger succeed). An action: DC 10 Strength (Athletics) frees itself or a creature within its
  reach. Detect: Search, DC 11 Perception; cut or avoided once found. (DC 12 at 5-10, 14 at 11-16, 16 at 17-20.)
- Fire-Casting Statue (Deadly, 1-4). Trigger: a creature moves onto the pressure plate for the first time on a turn or
  starts its turn there; resets at the start of the next turn. A 15-foot Cone of flame from the statue: DC 15 Dexterity
  save, 2d10 Fire, half on a success. Detect: Search within 5 ft of the statue, DC 10 Perception, finds the glyph; a
  Study, DC 15 Intelligence (Arcana), reads it ("fire"); an action with a sharp tool defaces it (disarmed). Search, DC 15
  Perception, finds the plate; an Iron Spike under it stops it. (5-10: 4d10, 30-ft Cone; 11-16: 10d10, 60 ft; 17-20:
  18d10, 120 ft.)
- Hidden Pit (Nuisance, 1-4). Trigger: a creature moves onto the lid: it falls in, 10 ft, 1d6 Bludgeoning; the lid
  stays open. Detect: Study, DC 15 Intelligence (Investigation); once found an Iron Spike (or Arcane Lock) keeps the lid
  shut. Escape: a Climb Speed, climbing gear or magic such as Spider Climb. (5-10: 30 ft, 3d6; 11-16: 60 ft, 6d6; 17-20:
  120 ft, 12d6.)
- Poisoned Darts (Deadly, 1-4). Trigger: a creature moves onto the plate for the first time on a turn; resets at the
  start of the next turn while it has fired fewer than three times. Each creature in the darts' path: DC 13 Dexterity
  save or 1d3 darts, 1d6 Poison each. Detect: Search, DC 15 Perception, the holes (plugged with wax, cloth or detritus)
  or the plate (an Iron Spike). (Per dart 2d6 at 5-10, 4d6 at 11-16, 7d6 at 17-20.)
- Poisoned Needle (Nuisance, 1-4). Trigger: the lock opened improperly (anything but its key) or a failed disarm: DC 11
  Constitution save, 1d10 Poison and Poisoned for 1 hour, half damage only on a success. Avoid: Knock. Detect: Search,
  DC 15 Perception; an action and DC 15 Dexterity (Sleight of Hand) disarms it, a failure sets it off. (5-10: 2d10, DC
  13; 11-16: 4d10, DC 15; 17-20: 10d10, DC 17.)
- Rolling Stone (Deadly 11-16, Nuisance 17-20; the SRD's name, asked for as "Rolling Sphere"). Trigger: a plate; a
  5-foot-radius stone rolls Initiative +8 and moves 60 ft a turn in one direction until a wall stops it; a creature whose
  space it enters for the first time on a turn, or that enters its space: DC 15 Dexterity save or 10d10 Bludgeoning and
  Prone. Detect: Study, DC 15 Investigation; an Iron Spike under the plate. Slow it: an action, DC 20 Strength
  (Athletics), 15 ft less a turn. (Destroying it, AC 17, HP 100, Damage Threshold 10: not simulated.)
- Spiked Pit (Deadly, 1-4): the Hidden Pit with spikes: 1d6 Bludgeoning plus 2d8 Piercing. (5-10: 30 ft, 3d6 + 3d8;
  11-16: 60 ft, 6d6 + 8d8; 17-20: 120 ft, 12d6 + 13d8.)
Thieves' Tools (Utilize: disarm a trap, DC 15) are offered beside each mechanical trap's own way (trip wires, plates, the
needle) and pick a lock (DC 15): the tools in the bag and their proficiency (the plan's rule; a Rogue's class gives it).

Area gear from the bag (SRD 5.2.1 Adventuring Gear), each the Utilize action:
- Caltrops: a 5-foot square within 5 ft; a creature entering it for the first time on a turn: DC 15 Dexterity save or
  1 Piercing and Speed 0 until the start of its next turn.
- Ball Bearings: a level 10-foot square within 10 ft; entering it for the first time on a turn: DC 10 Dexterity save or
  Prone.
- Oil (dousing a space): a 5-foot square within 5 ft; once lit (a Tinderbox, a Bonus Action) it burns until the end of
  the turn 2 rounds later: 5 Fire to a creature that enters it or ends its turn there, once a turn.
- Hunting Trap: set in a square within 5 ft (its chain on an Iron Spike driven in); a creature stepping on it: DC 13
  Dexterity save or 1d4 Piercing and Speed 0 until the start of its next turn, then held by the chain until it breaks
  free: an action, DC 13 Strength (Athletics), itself or a creature within reach; each failure 1 Piercing.

Where it lives: a scenario's (or an adventure pack's) "traps" list, or placed by the GM in Play live (Traps.place);
each trap: {"id", "kind", "band", "squares": [[x, y], ...]} plus "area" (the squares beneath a roof, the darts' path),
"statue" and "toward" (the statue and where it faces), "door" (the lock with the needle) or "stone" {"at", "dir"}. The
map-layers session may adopt this list as the Objects/GM layer. The engine (Sim.token_moved -> Traps.on_step) sees every
step a creature takes, the live players' and the simulator's own; the referee's arithmetic checks each trap's saves and
damage (Traps.referee_check).

GM 2026-10-26 (goal 15): the creatures the simulator plays know their lair's traps ("known_by" on a trap, "knows_traps" on
a creature), wary ones Search or Study, and every creature climbs out of a pit (sim/creature_traps.py). Climbing out
(SRD 5.2.1 Climbing, the pit's escape): a Climb Speed (or Spider Climb) climbs at its own rate. GM 2026-11-01 ("Change
Pit's wall hazard to ASK GM"): a character's other ways up go to Ask the GM, who can let it climb out (Traps.allowed). A
computer-played creature still rolls: a Strength (Athletics) check at the pit's climbing DC (CLIMB_DC, or the trap's
"climb_dc") each turn it climbs; a failed check makes no headway that turn.
"""
import requirements as rq

BANDS = ("1-4", "5-10", "11-16", "17-20")
SRD = "SRD 5.2.1 Gameplay Toolbox: Traps"
TOOLS, SPIKES, KIT, TINDER = "thieves-tools", "spikes-iron", "climbers-kit", "tinderbox"
OWN_CLIMB = ("a Climb Speed", "Spider Climb")                  # the ways up a pit that need no ruling
SPIKES_PER_BUNDLE = 10                                         # Spikes, Iron (10): a bundle of ten
GEAR = {"caltrops": "Caltrops", "ball-bearings": "Ball Bearings", "oil": "Oil", "hunting-trap": "Hunting Trap"}
SHARP = ("piercing", "slashing")
CLIMB_DC = 15                                                  # smooth walls: a Medium DC (SRD 5.2.1 Difficulty Class); GM 2026-10-27: confirmed


def band_of(level):
    level = int(level or 1)
    return "1-4" if level <= 4 else "5-10" if level <= 10 else "11-16" if level <= 16 else "17-20"


def _pit(spikes):
    depth = {"1-4": 10, "5-10": 30, "11-16": 60, "17-20": 120}
    fall = {"1-4": "1d6", "5-10": "3d6", "11-16": "6d6", "17-20": "12d6"}
    stab = {"1-4": "2d8", "5-10": "3d8", "11-16": "8d8", "17-20": "13d8"}
    return {b: dict(depth=depth[b], dice=fall[b], **({"spikes": stab[b]} if spikes else {})) for b in BANDS}


# The catalog. "parts": what Search or Study finds (action, skill, DC, where); "scale": the band's numbers.
TRAPS = {
    "collapsing_roof": {
        "name": "Collapsing Roof", "severity": "Deadly", "levels": "1-4", "bands": BANDS,
        "trigger": "A creature crosses a trip wire", "duration": "Instantaneous", "place": "wire",
        "parts": {"wire": {"what": "the trip wire and the unstable ceiling", "action": "search", "skill": "Perception",
                           "ability": "wis", "dc": 11, "on": "squares"}},
        "scale": {"1-4": {"dice": "2d10", "dc": 13}, "5-10": {"dice": "4d10", "dc": 15},
                  "11-16": {"dice": "10d10", "dc": 17}, "17-20": {"dice": "18d10", "dc": 19}},
        "ways": ["cut", "tools"], "escape": "The rubble is Difficult Terrain.",
        "effect": "each creature beneath the ceiling: Dexterity save, Bludgeoning damage, half on a success"},
    "falling_net": {
        "name": "Falling Net", "severity": "Nuisance", "levels": "1-4", "bands": BANDS,
        "trigger": "A creature crosses a trip wire", "duration": "Instantaneous", "place": "wire",
        "parts": {"wire": {"what": "the trip wire and the suspended Net", "action": "search", "skill": "Perception",
                           "ability": "wis", "dc": 11, "on": "squares"}},
        "scale": {"1-4": {"dc": 10}, "5-10": {"dc": 12}, "11-16": {"dc": 14}, "17-20": {"dc": 16}},
        "ways": ["cut", "tools"], "escape": "An action: Strength (Athletics) at the Net's DC frees itself or a creature "
                                            "within its reach (the Net itself: AC 10, 5 HP, not simulated).",
        "effect": "the first creature across: Dexterity save or Restrained until it escapes (Huge or larger: no effect)"},
    "fire_statue": {
        "name": "Fire-Casting Statue", "severity": "Deadly", "levels": "1-4", "bands": BANDS,
        "trigger": "A creature moves onto a pressure plate", "duration": "Instantaneous; resets at the start of the next turn",
        "place": "plate",
        "parts": {"glyph": {"what": "a tiny glyph on the statue", "action": "search", "skill": "Perception", "ability": "wis",
                            "dc": 10, "on": "statue"},
                  "meaning": {"what": 'the glyph\'s meaning ("fire")', "action": "study", "skill": "Arcana", "ability": "int",
                              "dc": 15, "on": "statue", "after": "glyph"},
                  "plate": {"what": "the pressure plate", "action": "search", "skill": "Perception", "ability": "wis",
                            "dc": 15, "on": "squares"}},
        "scale": {"1-4": {"dice": "2d10", "dc": 15, "cone": 15}, "5-10": {"dice": "4d10", "dc": 15, "cone": 30},
                  "11-16": {"dice": "10d10", "dc": 15, "cone": 60}, "17-20": {"dice": "18d10", "dc": 15, "cone": 120}},
        "ways": ["deface", "spike", "tools"], "escape": None,
        "effect": "a Cone of flame from the statue: Dexterity save, Fire damage, half on a success"},
    "hidden_pit": {
        "name": "Hidden Pit", "severity": "Nuisance", "levels": "1-4", "bands": BANDS,
        "trigger": "A creature moves onto the pit's lid", "duration": "Instantaneous", "place": "lid",
        "parts": {"lid": {"what": "the pit's lid", "action": "study", "skill": "Investigation", "ability": "int", "dc": 15,
                          "on": "squares"}},
        "scale": _pit(False), "ways": ["spike"],
        "escape": "A Climb Speed, climbing gear or magic such as Spider Climb to scale its smooth walls (without a Climb "
                  "Speed: Ask the GM).",
        "effect": "the creature falls into the pit (Bludgeoning damage from the fall); the lid stays open"},
    "poisoned_darts": {
        "name": "Poisoned Darts", "severity": "Deadly", "levels": "1-4", "bands": BANDS,
        "trigger": "A creature moves onto a pressure plate",
        "duration": "Instantaneous; resets at the start of the next turn while it has fired fewer than three times",
        "place": "plate",
        "parts": {"holes": {"what": "the holes in the walls", "action": "search", "skill": "Perception", "ability": "wis",
                            "dc": 15, "on": "area"},
                  "plate": {"what": "the pressure plate", "action": "search", "skill": "Perception", "ability": "wis",
                            "dc": 15, "on": "squares"}},
        "scale": {"1-4": {"dice": "1d6", "dc": 13}, "5-10": {"dice": "2d6", "dc": 13}, "11-16": {"dice": "4d6", "dc": 13},
                  "17-20": {"dice": "7d6", "dc": 13}},
        "ways": ["plug", "spike", "tools"], "escape": None,
        "effect": "each creature in the darts' path: Dexterity save or 1d3 darts, Poison damage per dart"},
    "poisoned_needle": {
        "name": "Poisoned Needle", "severity": "Nuisance", "levels": "1-4", "bands": BANDS,
        "trigger": "A creature opens the trap's lock improperly or fails to disarm the trap", "duration": "Instantaneous",
        "place": "lock",
        "parts": {"needle": {"what": "the needle in the lock", "action": "search", "skill": "Perception", "ability": "wis",
                             "dc": 15, "on": "squares"}},
        "scale": {"1-4": {"dice": "1d10", "dc": 11}, "5-10": {"dice": "2d10", "dc": 13}, "11-16": {"dice": "4d10", "dc": 15},
                  "17-20": {"dice": "10d10", "dc": 17}},
        "ways": ["sleight", "tools"], "escape": None,
        "effect": "the creature opening the lock: Constitution save, Poison damage and Poisoned for 1 hour; half damage only "
                  "on a success"},
    "rolling_stone": {
        "name": "Rolling Stone", "severity": "Deadly", "levels": "11-16", "bands": ("11-16", "17-20"),
        "severity_by_band": {"11-16": "Deadly", "17-20": "Nuisance"},
        "trigger": "A creature moves onto a pressure plate", "duration": "Until the stone stops rolling", "place": "plate",
        "parts": {"plate": {"what": "the pressure plate's function", "action": "study", "skill": "Investigation",
                            "ability": "int", "dc": 15, "on": "squares"}},
        "scale": {"11-16": {"dice": "10d10", "dc": 15, "ft": 60, "init": 8}, "17-20": {"dice": "10d10", "dc": 15, "ft": 60, "init": 8}},
        "ways": ["spike", "tools"],
        "escape": "An action within 5 ft: DC 20 Strength (Athletics) slows it 15 ft a turn (destroying it: AC 17, HP 100, "
                  "Damage Threshold 10, not simulated).",
        "effect": "a Large stone rolls 60 ft a turn; a creature it reaches: Dexterity save or Bludgeoning damage and Prone"},
    "spiked_pit": {
        "name": "Spiked Pit", "severity": "Deadly", "levels": "1-4", "bands": BANDS,
        "trigger": "A creature moves onto the pit's lid", "duration": "Instantaneous", "place": "lid",
        "parts": {"lid": {"what": "the pit's lid", "action": "study", "skill": "Investigation", "ability": "int", "dc": 15,
                          "on": "squares"}},
        "scale": _pit(True), "ways": ["spike"],
        "escape": "A Climb Speed, climbing gear or magic such as Spider Climb to scale its smooth walls (without a Climb "
                  "Speed: Ask the GM).",
        "effect": "the creature falls onto the spikes (Bludgeoning from the fall plus Piercing from the spikes); the lid "
                  "stays open"},
}
# the area gear a character puts down (GEAR): drawn for everyone, never hidden
GEAR_KINDS = {"caltrops": {"name": "Caltrops", "dc": 15, "size": 1, "within": 5},
              "ball-bearings": {"name": "Ball Bearings", "dc": 10, "size": 2, "within": 10},
              "oil": {"name": "Oil", "size": 1, "within": 5},
              "hunting-trap": {"name": "Hunting Trap", "dc": 13, "size": 1, "within": 5},
              "net": {"name": "Net", "dc": 10, "size": 1, "within": 15}}       # GM 2026-10-26: thrown (sim/live_items.py)
WAYS = {"cut": "Cut the trip wire", "spike": "Wedge an Iron Spike", "plug": "Plug the holes", "deface": "Deface the glyph",
        "tools": "Disarm with Thieves' Tools", "sleight": "Disarm the needle (Sleight of Hand)", "pick": "Pick the lock",
        "free_net": "Free from the Net", "free_trap": "Break free of the Hunting Trap", "climb": "Climb out of the pit",
        "slow": "Slow the stone", "light": "Light the oil"}


class TrapError(ValueError):
    pass


def severity(kind, band):
    t = TRAPS[kind]
    return (t.get("severity_by_band") or {}).get(band, t["severity"])


def numbers(kind, band):
    return dict(TRAPS[kind]["scale"][band])


def describe(kind, band):
    """The trap's card (for the GM's lists and Remix Prep): its SRD parts and this band's numbers."""
    t, n = TRAPS[kind], numbers(kind, band)
    out = {"kind": kind, "name": t["name"], "band": band, "severity": severity(kind, band), "trigger": t["trigger"],
           "duration": t["duration"], "effect": t["effect"], "escape": t["escape"], "numbers": n,
           "detect": ["%s: %s, DC %d %s (%s)" % (p["action"].title(), p["what"], p["dc"],
                                                {"wis": "Wisdom", "int": "Intelligence"}[p["ability"]], p["skill"])
                      for p in t["parts"].values()],
           "disarm": [WAYS[w] for w in t["ways"]], "source": SRD}
    return out


def suggest(level):
    """Remix Prep (GM 2026-10-24: "Remix Prep suggests SRD traps by the party's level band"): every SRD trap made for the
    party's band, Nuisance first, then Deadly, with its card. The Rolling Stone is made only for levels 11-20."""
    band = band_of(level)
    rows = [describe(k, band) for k, t in TRAPS.items() if band in t["bands"]]
    rows.sort(key=lambda r: (r["severity"] != "Nuisance", r["name"]))
    return {"level": int(level or 1), "band": band, "traps": rows,
            "note": "SRD 5.2.1 traps scaled to levels %s (At Higher Levels). The SRD warns that a Nuisance trap can be "
                    "Deadly for characters below its levels. Place them on squares a creature can enter." % band}


def _sq(p):
    return int(round(float(p[0]))), int(round(float(p[1])))


class Traps:
    """The traps of one fight (sim/run_sim.py: Sim.traps). Inert without traps or gear on the map."""

    def __init__(self, sim):
        self.sim = sim
        self.traps, self.problems = [], []
        self.held = {}             # ctid -> {"at": (x, y), "trap": id, "why", "until": "turn" | "free" | "climb"}
        self.in_pit = {}           # ctid -> trap id (the creature is at the bottom of an open pit)
        self.climbed = {}          # ctid -> feet climbed so far
        self.hit = {}              # (trap id, ctid) -> turn serial: "for the first time on a turn"
        self.oiled = {}            # GM 2026-10-26: ctid -> {"until": round, "by": ctid}, Oil thrown on a creature
        self.climb_tried = {}      # GM 2026-10-26 (goal 15): ctid -> (turn serial, passed): this turn's climbing check
        self.allowed = set()       # GM 2026-11-01: characters the GM has let climb out of a pit
        self.climb_help = {}       # ctid in a pit -> the ally whose Help gives its next climbing check Advantage
        import creature_traps
        self.minds = creature_traps.Minds(self)                  # what the creatures know and do (sim/creature_traps.py)
        self.n = 0
        for spec in sim.sc.get("traps") or []:
            try:
                self.place(spec, quiet=True)
            except TrapError as e:
                self.problems.append("Trap %s left off the map: %s" % (spec.get("id") or spec.get("kind"), e))

    # ------------------------------------------------------------------ the map
    @property
    def g(self):
        return self.sim.sc.get("grid", 50)

    def serial(self):
        return int(self.sim.S.turnSerial or 0)

    def S(self):
        """The fight's state (sim/fight_state.py)."""
        return self.sim.S

    def pos(self, ctid):
        return self.sim.party.pos(ctid) if getattr(self.sim, "party", None) else self.S().state(ctid)[2:4]

    def enterable(self, x, y):
        """A square a creature can enter: on the map, not a wall square, no wall through its middle (the planner's rule)."""
        import sim_messages
        board = sim_messages.map_part(self.sim.sc)
        if not (0 <= x < board["cols"] and 0 <= y < board["rows"]):
            return False
        if [x, y] in [list(w) for w in self.sim.sc.get("wall_cells") or []]:
            return False
        segs = self.sim.wall_segs
        return not (segs and self.sim.map_walls.near((x * self.g, y * self.g), segs, 0.25 * self.g))

    def place(self, spec, quiet=False, by=None):
        """Put a trap (or a piece of area gear) on the map, after checking it: its kind, band and squares (only squares a
        creature can enter, never one a creature or another trap holds)."""
        kind = str(spec.get("kind") or "")
        gear = kind in GEAR_KINDS
        if not gear and kind not in TRAPS:
            raise TrapError("Unknown trap kind %r (one of %s)." % (kind, ", ".join(sorted(TRAPS))))
        band = str(spec.get("band") or "1-4")
        if not gear and band not in TRAPS[kind]["bands"]:
            raise TrapError("%s is made for levels %s, not %s." % (TRAPS[kind]["name"], " and ".join(TRAPS[kind]["bands"]), band))
        squares = [list(_sq(p)) for p in spec.get("squares") or []]
        if not squares or len(squares) > 16:
            raise TrapError("A trap covers 1 to 16 squares.")
        for x, y in squares + [list(_sq(p)) for p in spec.get("area") or []]:
            if not self.enterable(x, y):
                raise TrapError("Square (%d, %d) is not one a creature can enter (a wall or off the map)." % (x, y))
        taken = {tuple(s) for t in self.traps if not t.get("gone") for s in t["squares"]}
        if any(tuple(s) in taken for s in squares):
            raise TrapError("Another trap is already on that square.")
        self.n += 1
        t = {"id": str(spec.get("id") or "trap-%d" % self.n), "kind": kind, "band": band, "squares": squares,
             "armed": True, "found": [], "disarmed": False, "how": "", "fired": 0, "open": False, "spent": None,
             "known": bool(gear)}
        if gear:
            t.update(name=GEAR_KINDS[kind]["name"], gear=True, by=by, lit=None)
        else:
            t["name"] = TRAPS[kind]["name"]
            t["area"] = [list(_sq(p)) for p in spec.get("area") or []] or [list(s) for s in squares]
            kb = spec.get("known_by") or []                      # GM 2026-10-26: the lair's creatures (sim/creature_traps.py)
            if isinstance(kb, str):
                kb = [kb]
            t["known_by"] = [str(k) for k in kb][:40]
            if kind in ("hidden_pit", "spiked_pit"):
                dc = spec.get("climb_dc", CLIMB_DC)
                if not isinstance(dc, int) or isinstance(dc, bool) or not 5 <= dc <= 30:
                    raise TrapError("A pit's climbing DC is a whole number from 5 to 30.")
                t["climb_dc"] = dc
            if kind == "fire_statue":
                st = spec.get("statue")
                if not st:
                    raise TrapError("A Fire-Casting Statue needs the statue's square (statue) and where it faces (toward).")
                t["statue"], t["toward"] = list(_sq(st)), list(_sq(spec.get("toward") or squares[0]))
            if kind == "poisoned_needle":
                door = spec.get("door")
                if door is not None and str(door) not in [str(w["id"]) for w in self.sim.sc.get("walls") or [] if w.get("door")]:
                    raise TrapError("No door %s on this map for the needle's lock." % door)
                t["door"] = str(door) if door is not None else None
            if kind == "rolling_stone":
                st = spec.get("stone") or {}
                if not st.get("at") or not st.get("dir"):
                    raise TrapError("A Rolling Stone needs where the stone waits (stone.at) and its direction (stone.dir).")
                dx, dy = (int(v) for v in st["dir"])
                if (dx, dy) == (0, 0) or abs(dx) > 1 or abs(dy) > 1:
                    raise TrapError("The stone rolls one way: dir is a step such as [1, 0].")
                t["stone"] = {"at": list(_sq(st["at"])), "dir": [dx, dy], "rolling": False, "init": None, "ft": 60, "done": False}
        if any(t["id"] == o["id"] for o in self.traps):
            t["id"] += "-%d" % self.n
        self.traps.append(t)
        if not quiet and not gear:
            self.sim.say("gm", "The GM places a %s (%s, levels %s) at %s" % (t["name"], severity(kind, band), band,
                                                                          ", ".join("(%d, %d)" % tuple(s) for s in squares)))
        return t

    def remove(self, tid):
        t = self.by_id(tid)
        self.traps.remove(t)
        return t

    def by_id(self, tid):
        t = next((t for t in self.traps if t["id"] == str(tid)), None)
        if not t:
            raise TrapError("No trap %s here." % tid)
        return t

    def footprint(self, ctid, at=None):
        x, y = at if at is not None else self.pos(ctid)
        n = self.sim.size_sq(ctid)
        x0, y0 = int(round(float(x) - (n - 1) / 2)), int(round(float(y) - (n - 1) / 2))
        return {(x0 + i, y0 + j) for i in range(n) for j in range(n)}

    def who_on(self, squares):
        sq = {tuple(s) for s in squares}
        return [c["id"] for c in self.sim.sc["combatants"] if not self.sim.down(c["id"]) and self.footprint(c["id"]) & sq]

    def say(self, text, kind="dice"):
        self.sim.say(kind, text)                                 # "secret": the GM's log only (tools/table_seats.py)

    # ------------------------------------------------------------------ routes (the party knows where its traps are)
    def route_cells(self, ctid):
        """For a mover's route (Sim._route_search): squares to keep off (a trap its side found and that would still go
        off: a lid, a plate; a found trip wire is stepped over) and Difficult Terrain (collapsed rubble)."""
        avoid, difficult = set(), set()
        side = self.sim.by_id(ctid).get("side")
        for t in self.traps:
            if t.get("rubble"):
                difficult |= {tuple(s) for s in t["area"]}
            if t.get("gear") or t.get("gone"):
                if t.get("gear") and t["armed"] and t.get("by_side") == side and t["kind"] != "oil":
                    avoid |= {tuple(s) for s in t["squares"]}            # its own side's caltrops: walk round them
                continue
        avoid |= self.minds.keep_off(ctid)                       # open pits; the lids and plates it knows (goal 15)
        return avoid, difficult

    @staticmethod
    def place_of(t):
        return "gear" if t.get("gear") else TRAPS[t["kind"]]["place"]

    def found_main(self, t, side="friend"):
        """The part that says where it goes off has been found (the lid, the plate, the wire, the needle): by the party,
        or (side "foe") by the creatures' own Search or Study (sim/creature_traps.py)."""
        place = TRAPS[t["kind"]]["place"]
        found = t["found"] if side == "friend" else t.get("foe_found") or []
        return any(p in found for p in {"lid": ("lid",), "plate": ("plate",), "wire": ("wire",), "lock": ("needle",)}[place])

    # ------------------------------------------------------------------ the trigger: every step (Sim.token_moved)
    def hold_step(self, name, x0, y0, x1, y1):
        """The fake FG asks before a token steps (sim/fake_fg.lua holdStep): True keeps it where it is. A creature caught by
        a trap (fallen into a pit, Speed 0) stays; its move ends there, as a GM stops the token at the table."""
        c = next((c for c in self.sim.sc["combatants"] if c["name"] == name), None)
        if c and c["id"] not in self.held and self.traps and not self.minds.party_side(c["id"]):
            # GM 2026-10-26 (goal 15): a creature never steps onto a lid or plate it knows (the planner routes round
            # them; this stops a move that would anyway, as the GM would)
            into = self.footprint(c["id"], (x1 / self.g, y1 / self.g)) - self.footprint(c["id"], (x0 / self.g, y0 / self.g))
            if into & self.minds.keep_off(c["id"]):
                self.say("%s stops short of a trap it knows" % c["name"], "secret")
                return True
        if not c or c["id"] not in self.held:
            return False
        h = self.held[c["id"]]
        g = self.g
        return (round(x1 / g), round(y1 / g)) != tuple(h["at"])

    def on_step(self, name, x0, y0, x1, y1):
        mover = next((c for c in self.sim.sc["combatants"] if c["name"] == name), None)
        if not mover or not self.traps or self.sim.down(mover["id"]):
            return
        me, g = mover["id"], self.g
        if me in self.held:
            return
        new, old = self.footprint(me, (x1 / g, y1 / g)), self.footprint(me, (x0 / g, y0 / g))
        entered = new - old
        if not entered:
            return
        for t in list(self.traps):
            if t.get("gone"):
                continue
            if t.get("stone", {}).get("rolling") and self.stone_cells(t) & entered:
                self.stone_hits(t, me, "steps into the rolling stone's space")
            into = {tuple(s) for s in t["squares"]} & entered
            if t["kind"] in ("hidden_pit", "spiked_pit") and t["open"] and into and self.in_pit.get(me) != t["id"]:
                self.fire(t, me, sorted(into)[0], why="steps into the open pit")    # an open pit is a hole
                return
            if not t["armed"] or not into:
                continue
            self.enter(t, me, tuple(sorted({tuple(s) for s in t["squares"]} & entered))[0])
            if me in self.held:
                return

    def enter(self, t, me, at):
        c, kind = self.sim.by_id(me), t["kind"]
        if t.get("gear"):
            return self.gear_entered(t, me, at)
        if kind == "poisoned_needle":
            return                                               # a lock's needle: opening the lock sets it off
        place = TRAPS[kind]["place"]
        if place == "wire" and "wire" in t["found"] and c.get("side") == "friend":
            self.say("%s steps over the trip wire the party found (%s): it doesn't go off" % (c["name"], t["name"]), "turn")
            return
        if place == "wire" and not self.minds.party_side(me) and self.minds.knows(me, t):
            self.say("%s steps over its own trip wire (%s): it doesn't go off" % (c["name"], t["name"]), "secret")
            return
        if place == "plate" and t["spent"] == self.serial():
            return                                               # it went off this turn: it resets at the next turn
        self.fire(t, me, at)

    # ------------------------------------------------------------------ going off
    def fire(self, t, me, at=None, why=None):
        kind, n, c = t["kind"], numbers(t["kind"], t["band"]), self.sim.by_id(me)
        t["fired"] += 1
        sq = at or t["squares"][0]
        pcs = [o["id"] for o in self.sim.sc["combatants"] if o.get("pc") and not self.sim.down(o["id"])]
        t["known"] = t["known"] or me in pcs or any(self.sim.sees_square(i, sq[0], sq[1]) for i in pcs)   # the party saw it
        t["spent"] = self.serial()
        start_hurt = len(self.sim.referee.hurts) if getattr(self.sim, "referee", None) else 0
        self.say("%s %s: the %s goes off (%s; %s)" % (c["name"], why or {"wire": "crosses a trip wire",
                 "lid": "steps onto the lid", "plate": "steps onto a pressure plate", "lock": "opens the lock"}[TRAPS[kind]["place"]],
                 t["name"], severity(kind, t["band"]), SRD), "turn")
        record = {"trap": t, "dc": n.get("dc"), "victims": {}, "start_hurt": start_hurt}
        if kind in ("hidden_pit", "spiked_pit"):
            t["open"], t["armed"] = True, False
            self.held[me] = {"at": tuple(at or _sq(self.sim.party.pos(me))), "trap": t["id"], "why": "at the bottom of the pit",
                             "until": "climb"}
            self.in_pit[me] = t["id"]
            self.sim.later.append(lambda: self.fall(t, me, record))
            if self.sim.S.active()[0] == me and not c.get("pc"):
                self.sim.later.append(lambda: self.end_npc_turn(me, "it fell into the pit"))
            return record
        if kind == "falling_net":
            t["armed"] = False
            big = str(c.get("size") or "").lower() in ("huge", "gargantuan") or self.sim.size_sq(me) >= 3
            if big:
                self.say("%s is too big for the Net (Huge or larger succeed automatically)" % c["name"])
                return record
            saved = self.save(me, "dex", n["dc"], t["name"], record)
            if not saved:
                self.held[me] = {"at": tuple(at or _sq(self.sim.party.pos(me))), "trap": t["id"], "why": "Restrained by the Net",
                                 "until": "free"}
                self.sim.later.append(lambda: self.restrain(t, me, n["dc"]))
                if self.sim.S.active()[0] == me and not c.get("pc"):
                    self.sim.later.append(lambda: self.end_npc_turn(me, "it is caught in the Net"))
            self.sim.later.append(lambda: self.referee_check(record))
            return record
        if kind == "collapsing_roof":
            t["armed"] = False
            victims = self.who_on(t["area"])
            self.sim.later.append(lambda: self.area_damage(t, victims, "dex", n["dc"], n["dice"], "bludgeoning", record, rubble=True))
            return record
        if kind == "fire_statue":
            victims = self.cone_victims(t, n["cone"])
            self.show_cone(t, n["cone"])
            self.sim.later.append(lambda: self.area_damage(t, victims, "dex", n["dc"], n["dice"], "fire", record))
            return record
        if kind == "poisoned_darts":
            if t["fired"] >= 3:
                t["armed"] = False                               # three times: it does not reset
            victims = self.who_on(t["area"])
            self.sim.later.append(lambda: self.darts(t, victims, n, record))
            return record
        if kind == "poisoned_needle":
            self.sim.later.append(lambda: self.needle(t, me, n, record))
            return record
        if kind == "rolling_stone":
            t["armed"] = False
            st = t["stone"]
            st["rolling"], st["init"] = True, self.sim.rng.randint(1, 20) + n["init"]
            st["ft"] = n["ft"]
            self.say("The stone is released: Initiative d20 +8 = %d; it rolls %d ft a turn %s" % (
                st["init"], st["ft"], self.compass(st["dir"])))
            return record
        return record

    @staticmethod
    def compass(d):
        return {(1, 0): "east", (-1, 0): "west", (0, 1): "south", (0, -1): "north", (1, 1): "south-east",
                (-1, 1): "south-west", (1, -1): "north-east", (-1, -1): "north-west"}[tuple(d)]

    def end_npc_turn(self, me, why):
        s = self.sim.S
        if s.active()[0] != me:
            return
        self.say("%s's turn ends: %s (the simulator as GM stops its move there)" % (self.sim.by_id(me)["name"], why), "turn")
        self.sim.next_actor()

    def roll(self, dice):
        import party as party_mod
        return party_mod.roll(self.sim.rng, dice)

    def save(self, t, ability, dc, label, record):
        gm = getattr(self.sim, "gm_rules", None)
        if gm:
            saved, evasion = gm.roll_save(t, t, {"save": ability, "dc": dc}, label)
        else:
            d20 = self.sim.rng.randint(1, 20)
            bonus = int(self.sim.by_id(t).get(ability + "_save", 0) or 0)
            saved, evasion = d20 + bonus >= dc, False
            self.say("%s %s save against %s: d20 %d %+d = %d vs DC %d -> %s" % (
                self.sim.by_id(t)["name"], ability.upper(), label, d20, bonus, d20 + bonus, dc, "success" if saved else "failure"))
        record["victims"].setdefault(t, {})["saved"] = saved
        record["victims"][t]["evasion"] = evasion
        return saved

    def deal(self, t, amount, kind, record):
        if amount <= 0:
            return
        record["victims"].setdefault(t, {}).setdefault("dealt", 0)
        record["victims"][t]["dealt"] += amount
        if record.get("trap"):
            self.minds.learn(t, record["trap"])                  # goal 15: hurt by it, a creature knows it and is wary
        self.sim.S.pcDamage(t, t, "", amount, False, kind)
        self.sim.settle(0.2)

    def fall(self, t, me, record):
        n, c = numbers(t["kind"], t["band"]), self.sim.by_id(me)
        dmg = self.roll(n["dice"])
        self.say("%s falls %d ft into the %s (SRD 5.2.1 Falling): %s = %d Bludgeoning" % (c["name"], n["depth"], t["name"], n["dice"], dmg))
        stab = self.roll(n["spikes"]) if n.get("spikes") else 0
        if n.get("spikes"):
            self.say("The spikes at the bottom: %s = %d Piercing" % (n["spikes"], stab))
        record["victims"].setdefault(me, {})["max"] = _dice_max(n["dice"]) + _dice_max(n.get("spikes", ""))
        import monk                                              # MONK-01: Slow Fall (Monk 4), a Reaction
        dmg = monk.slow_fall(self.sim, me, dmg, "the %s" % t["name"])
        self.deal(me, dmg, "bludgeoning", record)
        if stab:
            self.deal(me, stab, "piercing", record)
        gm = getattr(self.sim, "gm_rules", None)
        if gm and dmg > 0 and not self.sim.down(me):
            gm.add(me, "Prone", "(landed at the bottom of the pit)", by=me)
            record["victims"][me]["prone"] = True
        how = self.climb_means(me)
        way = ("it can climb out (%s)" % how) if how else "its smooth walls need a Climb Speed, climbing gear or magic such as Spider Climb"
        if c.get("pc") and how not in OWN_CLIMB:                 # GM 2026-11-01: any other way up goes to the GM
            way = "climbing its smooth walls goes to the GM (Ask the GM)"
        self.say("%s is %d ft down in the open pit: %s" % (c["name"], n["depth"], way), "turn")
        self.referee_check(record)

    def restrain(self, t, me, dc):
        gm = getattr(self.sim, "gm_rules", None)
        if gm:
            gm.add(me, "Restrained", "(the Falling Net: an action and DC %d Strength (Athletics) frees it)" % dc, by=me, net=t["id"], dc=dc)

    def area_damage(self, t, victims, ability, dc, dice, kind, record, rubble=False):
        import gm_rules
        dmg = self.roll(dice)
        self.say("%s: %s = %d %s; DC %d %s save for %s" % (t["name"], dice, dmg, kind.capitalize(), dc,
                 {"dex": "Dexterity", "con": "Constitution"}[ability], ", ".join(self.sim.by_id(v)["name"] for v in victims) or "no one"))
        for v in victims:
            saved = self.save(v, ability, dc, t["name"], record)
            amount = gm_rules.area_damage(dmg, saved, record["victims"][v].get("evasion"))
            record["victims"][v]["max"] = _dice_max(dice) // (2 if saved else 1)
            self.deal(v, amount, kind, record)
        if rubble:
            t["rubble"] = True
            self.say("Rubble from the collapse: the squares beneath are Difficult Terrain now", "turn")
        self.referee_check(record)

    def darts(self, t, victims, n, record):
        for v in victims:
            if not self.save(v, "dex", n["dc"], t["name"], record):
                k = self.roll("1d3")
                dmg = sum(self.roll(n["dice"]) for _ in range(k))
                self.say("%s is struck by %d dart%s: %d Poison" % (self.sim.by_id(v)["name"], k, "" if k == 1 else "s", dmg))
                record["victims"][v]["max"] = 3 * _dice_max(n["dice"])
                self.deal(v, dmg, "poison", record)
            else:
                record["victims"][v]["max"] = 0
        if t["fired"] >= 3:
            self.say("%s has fired three times: it does not reset" % t["name"], "turn")
        self.referee_check(record)

    def needle(self, t, me, n, record):
        c = self.sim.by_id(me)
        saved = self.save(me, "con", n["dc"], t["name"], record)
        dmg = self.roll(n["dice"])
        amount = dmg // 2 if saved else dmg
        self.say("The needle stabs %s: %s = %d Poison%s" % (c["name"], n["dice"], dmg, " (half: %d)" % amount if saved else ""))
        record["victims"][me]["max"] = _dice_max(n["dice"]) // (2 if saved else 1)
        self.deal(me, amount, "poison", record)
        gm = getattr(self.sim, "gm_rules", None)
        if not saved and gm and not self.sim.down(me):
            if gm.cond_immune(me, "poisoned"):
                self.say("%s is immune to the Poisoned condition" % c["name"])
            else:
                gm.add(me, "Poisoned", "(the Poisoned Needle, 1 hour)", by=me)
                record["victims"][me]["poisoned"] = True
        self.referee_check(record)

    # ------------------------------------------------------------------ the statue's cone
    def cone_victims(self, t, length):
        import party as party_mod
        u = self.sim.sc.get("units", 5)
        o = (t["statue"][0] * u, t["statue"][1] * u)
        aim = ((t["toward"][0] - t["statue"][0]) * u, (t["toward"][1] - t["statue"][1]) * u)     # a direction from the statue
        out = []
        for c in self.sim.sc["combatants"]:
            if self.sim.down(c["id"]):
                continue
            px, py = self.sim.S.state(c["id"])[2:4]
            if party_mod.in_cone(o, aim, (float(px) * u, float(py) * u), length):
                out.append(c["id"])
        return out

    def show_cone(self, t, length):
        import math
        live = getattr(self.sim, "live", None)
        if not live:
            return
        dx, dy = t["toward"][0] - t["statue"][0], t["toward"][1] - t["statue"][1]
        effect = {"shape": "cone", "origin": list(t["statue"]), "angle_deg": math.degrees(math.atan2(dy, dx)),
                  "length_ft": length, "appearance": "fire", "targets": []}
        live._show(None, t["name"], effect)

    # ------------------------------------------------------------------ the rolling stone
    def stone_cells(self, t):
        x, y = t["stone"]["at"]
        return {(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)}          # a 5-foot radius: a Large 10-ft space

    def stone_hits(self, t, me, why):
        key = (t["id"] + "/stone", me)
        if self.hit.get(key) == self.serial():
            return
        self.hit[key] = self.serial()
        n = numbers(t["kind"], t["band"])
        c = self.sim.by_id(me)
        self.say("%s %s" % (c["name"], why))
        record = {"trap": t, "dc": n["dc"], "victims": {}, "start_hurt": len(self.sim.referee.hurts) if getattr(self.sim, "referee", None) else 0}
        saved = self.save(me, "dex", n["dc"], t["name"], record)
        record["victims"][me]["max"] = 0 if saved else _dice_max(n["dice"])
        if not saved:
            dmg = self.roll(n["dice"])
            self.say("The stone crushes %s: %s = %d Bludgeoning" % (c["name"], n["dice"], dmg))
            self.deal(me, dmg, "bludgeoning", record)
            gm = getattr(self.sim, "gm_rules", None)
            if gm and not self.sim.down(me):
                gm.add(me, "Prone", "(the Rolling Stone)", by=me)
                record["victims"][me]["prone"] = True
        self.referee_check(record)

    def stone_turn(self, t):
        """The stone's turn: up to 60 ft (less when slowed) straight on, until a wall or the map's edge stops it."""
        st = t["stone"]
        dx, dy = st["dir"]
        squares = st["ft"] // self.sim.sc.get("units", 5)
        moved = 0
        for _ in range(squares):
            nx, ny = st["at"][0] + dx, st["at"][1] + dy
            cells = {(nx, ny), (nx + 1, ny), (nx, ny + 1), (nx + 1, ny + 1)}
            here = self.stone_cells(t)
            if any(not self.enterable(*q) for q in cells) or any(
                    self.sim.wall_segs and self.sim.map_walls.blocked(((a[0]) * self.g, a[1] * self.g),
                                                                       ((a[0] + dx) * self.g, (a[1] + dy) * self.g), self.sim.wall_segs)
                    for a in here):
                st["rolling"], st["done"] = False, True
                break
            st["at"] = [nx, ny]
            moved += 1
            for v in self.who_on(cells - here):
                self.stone_hits(t, v, "is in the rolling stone's way")
        self.say("The Rolling Stone rolls %d ft %s%s" % (moved * self.sim.sc.get("units", 5), self.compass(st["dir"]),
                 ": it hits a wall and stops" if st["done"] else ""), "turn")

    # ------------------------------------------------------------------ turns
    def turn_changed(self, ended, started):
        """Sim.run, at every turn change: oil burning at the end of a turn, the stone's Initiative, holds that last until
        the start of a creature's next turn, a creature starting its turn on the statue's plate."""
        if not self.traps:
            return
        if ended:
            for t in self.traps:
                if t.get("gear") and t["kind"] == "oil" and t.get("lit") is not None and not t.get("gone"):
                    if ended in self.who_on(t["squares"]):
                        self.burn(t, ended, "ends its turn in the burning oil")
            for t in self.traps:                                 # the oil burns out at the end of the turn 2 rounds later
                if t.get("gear") and t["kind"] == "oil" and t.get("lit") is not None and not t.get("gone"):
                    if t["lit"]["turn"] == ended and int(self.sim.S.round()) >= t["lit"]["round"] + 2:
                        t["gone"], t["armed"] = True, False
                        self.say("The burning oil goes out", "turn")
        for t in self.traps:
            st = t.get("stone")
            if st and st.get("rolling") and self.stone_due(ended, started, st["init"]):
                self.stone_turn(t)
        if started:
            for v, helper in list(self.climb_help.items()):      # SRD 5.2.1 Help: until the start of the helper's next turn
                if helper == started:
                    self.climb_help.pop(v)
            h = self.held.get(started)
            if h and h["until"] == "turn":
                self.held.pop(started)
                self.say("%s's Speed comes back (the start of its turn)" % self.sim.by_id(started)["name"], "turn")
            for t in self.traps:
                if (t["kind"] == "fire_statue" and t["armed"] and not t.get("gone") and started in self.who_on(t["squares"])
                        and t["spent"] != self.serial()):
                    self.fire(t, started, why="starts its turn on the pressure plate")

    def stone_due(self, ended, started, init):
        if not ended or not started:
            return False
        a, b = self.init_of(ended), self.init_of(started)
        if a is None or b is None:
            return False
        return (a > init >= b) if a > b else (init < a or init >= b)

    def init_of(self, i):
        try:
            return float(self.sim.by_id(i).get("init") or 0)
        except (StopIteration, TypeError, ValueError):
            return None

    def npc_turn_start(self, me):
        """A creature the simulator plays, at the start of its turn (before the bridge plans it): in the Net it spends its
        action breaking free; at the bottom of a pit it climbs (or, with no way up, stays: its turn ends there). Free, it
        may wait behind a trap it knows or search (sim/creature_traps.py). True: that was its turn."""
        if self.sim.down(me):
            return False
        if me not in self.held:
            c = self.sim.by_id(me)
            return False if c.get("pc") else self.minds.turn_start(me)
        h = self.held[me]
        if h["until"] == "free":
            t = self.by_id(h["trap"])
            dc = numbers(t["kind"], t["band"])["dc"] if not t.get("gear") else GEAR_KINDS[t["kind"]]["dc"]
            self.athletics_free(me, me, t, dc)
            return True
        if h["until"] == "climb":
            if self.sim.by_id(me).get("pc") and getattr(self.sim, "live", None) and self.climb_means(me):
                return False                                     # Play live: the player climbs (Climb out of the pit)
            return self.minds.climb_turn(me)                     # goal 15: up the wall with its Speed
        return False

    # ------------------------------------------------------------------ gear on the ground
    def gear_entered(self, t, me, at):
        key, c = (t["id"], me), self.sim.by_id(me)
        if self.hit.get(key) == self.serial():
            return
        self.hit[key] = self.serial()
        kind, k = t["kind"], GEAR_KINDS[t["kind"]]
        if kind == "oil":
            if t.get("lit") is not None:
                self.burn(t, me, "enters the burning oil")
            return
        record = {"trap": t, "dc": k.get("dc"), "victims": {}, "start_hurt": len(self.sim.referee.hurts) if getattr(self.sim, "referee", None) else 0}
        saved = self.save(me, "dex", k["dc"], k["name"], record)
        if saved:
            record["victims"][me]["max"] = 0
            self.referee_check(record)
            return
        if kind == "ball-bearings":
            record["victims"][me]["max"] = 0
            gm = getattr(self.sim, "gm_rules", None)
            if gm:
                self.sim.later.append(lambda: gm.add(me, "Prone", "(slips on the Ball Bearings)", by=me))
            self.referee_check(record)
            return
        dmg = 1 if kind == "caltrops" else self.roll("1d4")
        record["victims"][me]["max"] = 1 if kind == "caltrops" else 4
        self.held[me] = {"at": tuple(at), "trap": t["id"], "until": "turn" if kind == "caltrops" else "free",
                         "why": "Speed 0 until the start of its next turn" if kind == "caltrops" else "caught in the Hunting Trap"}
        self.say("%s: %d Piercing; %s" % (k["name"], dmg, "Speed 0 until the start of its next turn" if kind == "caltrops" else
                 "Speed 0 until the start of its next turn, then held by the chain until it breaks free (an action, "
                 "DC 13 Strength (Athletics))"))
        if kind == "hunting-trap":
            t["armed"] = False
            t["caught"] = me
        self.sim.later.append(lambda: (self.deal(me, dmg, "piercing", record), self.referee_check(record)))
        if self.sim.S.active()[0] == me and not c.get("pc"):
            self.sim.later.append(lambda: self.end_npc_turn(me, "its Speed is 0 (%s)" % k["name"]))

    def burn(self, t, me, why):
        key = (t["id"] + "/burn", me)
        if self.hit.get(key) == self.serial():
            return                                               # once per turn
        self.hit[key] = self.serial()
        self.say("%s %s: 5 Fire" % (self.sim.by_id(me)["name"], why))
        record = {"trap": t, "dc": None, "victims": {me: {"max": 5}}, "start_hurt": len(self.sim.referee.hurts) if getattr(self.sim, "referee", None) else 0}
        self.sim.later.append(lambda: (self.deal(me, 5, "fire", record), self.referee_check(record)))

    def ignite(self, squares, by, why):
        """GM 2026-10-25 (ruling T10): fire lights spilled oil (SRD 5.2.1 Oil: "If lit"): a fire spell's area or a creature
        hit by fire (Alchemist's Fire) on an oil square lights it, as a Tinderbox would."""
        cells = {tuple(s) for s in squares}
        for t in self.traps:
            if not (t.get("gear") and t["kind"] == "oil") or t.get("lit") is not None or t.get("gone"):
                continue
            if cells & {tuple(s) for s in t["squares"]}:
                t["lit"] = {"turn": by, "round": int(self.sim.S.round())}
                self.say("%s lights the oil: it burns until the end of %s's turn 2 rounds from now; 5 Fire to a creature that "
                         "enters it or ends its turn there" % (why, self.sim.by_id(by)["name"]), "turn")
                for v in self.who_on(t["squares"]):
                    self.burn(t, v, "is in the oil as it lights")

    def ignite_creatures(self, targets, by, why):
        """Fire on these creatures: their squares light any oil under them, and oil thrown on one of them burns (SRD 5.2.1
        Oil: "If the target takes Fire damage before the oil dries (after 1 minute), the target takes an extra 5 Fire
        damage from burning oil")."""
        cells = [s for i in targets for s in self.footprint(i)]
        if cells:
            self.ignite(cells, by, why)
        for i in targets:
            o = self.oiled.pop(i, None)
            if o and int(self.sim.S.round()) <= o["until"] and not self.sim.down(i):
                self.say("The oil on %s catches fire (%s): 5 Fire" % (self.sim.by_id(i)["name"], why))
                self.sim.later.append(lambda i=i: (self.sim.S.pcDamage(by, i, "", 5, False, "fire"),
                                                    self.sim.settle(0.2)))

    def oil_on(self, tid, by):
        """GM 2026-10-26: Oil thrown on a creature (it failed its save): covered for 1 minute (10 rounds)."""
        self.oiled[tid] = {"until": int(self.sim.S.round()) + 9, "by": by}

    def net_on(self, me, tid):
        """GM 2026-10-26: a thrown Net (SRD 5.2.1 Net) on a creature that failed its save: Restrained until it escapes, an
        action and DC 10 Strength (Athletics) by it or a creature within 5 ft (the Hunting Trap's and the Falling Net's
        way out, sim/traps.py). The net lies on its squares until then."""
        self.n += 1
        t = {"id": "net-%d" % self.n, "kind": "net", "band": "1-4", "squares": [list(q) for q in sorted(self.footprint(tid))],
             "armed": False, "found": [], "disarmed": False, "how": "", "fired": 0, "open": False, "spent": None, "known": True,
             "name": GEAR_KINDS["net"]["name"], "gear": True, "by": me, "lit": None, "caught": tid}
        self.traps.append(t)
        self.held[tid] = {"at": tuple(_sq(self.sim.party.pos(tid))), "trap": t["id"], "until": "free", "why": "Restrained by a Net"}
        gm = getattr(self.sim, "gm_rules", None)
        if gm:
            gm.add(tid, "Restrained", "(a Net: an action and DC 10 Strength (Athletics) frees it)", by=me, net=t["id"], dc=10)
        return t

    # ------------------------------------------------------------------ what a character can do about them
    def climb_means(self, me):
        c = self.sim.by_id(me)
        import re
        if c.get("climb_ft") or re.search(r"Climb \d+", str(c.get("speed") or "")):
            return "a Climb Speed"
        if self.bag_count(me, KIT):
            return "a Climber's Kit"
        # GM 2026-10-25 (ruling T6): Rope or a Grappling Hook, or a friend at the edge pulling
        if self.bag_count(me, "rope") or self.bag_count(me, "grappling-hook"):
            return "Rope" if self.bag_count(me, "rope") else "a Grappling Hook"
        h = self.held.get(me) or {}
        pit = next((t for t in self.traps if t.get("id") == h.get("trap")), None)
        if pit is not None:
            mine = self.sim.party.allies(me) if getattr(self.sim, "party", None) else []
            gm = getattr(self.sim, "gm_rules", None)
            for a in mine:
                if self.sim.down(a) or (gm and gm.incapacitated(a)) or a in self.held:
                    continue
                if self.near(a, pit["squares"]) and not any(list(s) in [list(q) for q in pit["squares"]] for s in self.footprint(a)):
                    return "%s pulling from the edge" % self.sim.by_id(a)["name"]
        gm = getattr(self.sim, "gm_rules", None)
        if gm and gm.has(me, "Spider Climb"):
            return "Spider Climb"
        return ""

    def bag(self, me):
        c = self.sim.by_id(me)
        live = getattr(self.sim, "live", None)
        return rq.Bag(c["name"], getattr(live, "market", None) if live else None, c.get("bag"))

    def bag_count(self, me, item):
        try:
            return self.bag(me).count(item)
        except Exception:
            return 0

    def tools_proficient(self, c):
        """GM 2026-11-01 ("Thieves tools work according to Ask GM"): without proficiency the GM rules it (Ask the GM)."""
        return rq.need("proficiency with Thieves' Tools", not self.untrained(c), "%s has no proficiency with Thieves' Tools: "
                       "Ask the GM." % c["name"], rq.LINKS["characters"])

    def untrained(self, c):
        return "thieves-tools" not in rq.tool_proficiencies(c)

    def near(self, me, squares, ft=5):
        here = self.footprint(me)
        reach = ft // self.sim.sc.get("units", 5)
        return any(max(abs(a - x), abs(b - y)) <= reach for a, b in here for x, y in squares)

    def known_to(self, t, side="friend"):
        return t.get("gear") or t["known"] or bool(t["found"])

    def ways(self, me, t):
        """The ways this trap can be made safe now, each with its needs. -> [(how, label, needs, cmd extras)]"""
        out = []
        if t.get("gone"):
            return out
        c, kind = self.sim.by_id(me), t["kind"]
        fight = self.sim.live
        bag = self.bag(me)
        act = [rq.able(fight, me), rq.action_free(fight, me, "the Utilize action")]
        if t.get("gear"):
            if kind == "oil" and t.get("lit") is None:
                out.append(("light", "Light the oil (Tinderbox)", [rq.able(fight, me), rq.in_bag(bag, TINDER, "a Tinderbox"),
                            rq.bonus_free(fight, me, "a Tinderbox"), self.need_near(me, t["squares"], "the oil")], {}))
            if kind in ("hunting-trap", "net") and t.get("caught") in self.held:
                v = t["caught"]
                out.append(("free_trap", ("Free %s from the Net" if kind == "net" else "Break %s free of the Hunting Trap") % (
                                "yourself" if v == me else self.sim.by_id(v)["name"]),
                            [rq.able(fight, me), rq.action_free(fight, me, "breaking free"),
                             self.need_near(me, self.footprint(v), self.sim.by_id(v)["name"])], {}))
            return out
        if kind in ("falling_net",) and not t["armed"]:
            for v, h in self.held.items():
                if h["trap"] == t["id"] and h["until"] == "free":
                    out.append(("free_net", "Free %s from the Net" % ("yourself" if v == me else self.sim.by_id(v)["name"]),
                                [rq.able(fight, me), rq.action_free(fight, me, "freeing a creature"),
                                 self.need_near(me, self.footprint(v), self.sim.by_id(v)["name"])], {"target": v}))
        if kind in ("hidden_pit", "spiked_pit") and self.in_pit.get(me) == t["id"]:
            if self.climb_means(me) in OWN_CLIMB or me in self.allowed:   # any other way up: Ask the GM (asks)
                out.append(("climb", "Climb out of the pit", [rq.able(fight, me), rq.need(
                    "movement left", (fight.turn_state or {}).get("movement", 0) > 0, "No movement left this turn.")], {}))
        st = t.get("stone")
        if st and st.get("rolling"):
            out.append(("slow", "Slow the stone (DC 20 Athletics)", act + [self.need_near(me, self.stone_cells(t), "the stone")], {}))
        if not t["armed"]:
            return out
        parts = TRAPS[kind]["parts"]
        where = lambda p: {"statue": [t.get("statue")], "area": t.get("area")}.get(parts[p]["on"], t["squares"])
        for how in TRAPS[kind]["ways"]:
            part = {"cut": "wire", "spike": "lid" if "lid" in parts else "plate", "plug": "holes", "deface": "glyph",
                    "tools": next((p for p in ("wire", "plate", "needle") if p in parts), None), "sleight": "needle"}[how]
            if part not in t["found"]:
                continue                                          # a hidden part: nothing to offer (and nothing to tell)
            needs = list(act) + [self.need_near(me, where(part), parts[part]["what"])]
            if how == "spike":
                needs.append(rq.in_bag(bag, SPIKES, "Iron Spikes"))
            if how == "deface":
                sharp = any(isinstance(c.get(k), dict) and str(c[k].get("dmgtype", "")).lower() in SHARP for k in ("weapon", "ranged")) \
                        or bag.count(TOOLS)
                needs.append(rq.need("a sharp tool", sharp, "%s needs a sharp tool: a Piercing or Slashing weapon on the sheet, "
                                     "or Thieves' Tools." % c["name"], rq.LINKS["market"]))
            if how == "tools":
                needs += [rq.in_bag(bag, TOOLS, "Thieves' Tools"), self.tools_proficient(c)]
            out.append((how, "%s (%s)" % (WAYS[how], t["name"]), needs, {}))
        return out

    def need_near(self, me, squares, what):
        return rq.need("within 5 ft of %s" % what, self.near(me, squares), "%s must stand within 5 ft of %s." % (
            self.sim.by_id(me)["name"], what))

    def lock_ways(self, me):
        """Pick a locked door's lock with Thieves' Tools (Utilize, DC 15): a door beside the character."""
        out, fight = [], self.sim.live
        walls = self.sim.walls or {}
        c = self.sim.by_id(me)
        bag = self.bag(me)
        for d in walls.get("locked_doors") or []:
            w = next((w for w in self.sim.sc.get("walls") or [] if str(w["id"]) == str(d)), None)
            if not w or not fight.actions.near(me, w):
                continue
            import spell_doors                                   # SPELL-OBJECTS-01: Arcane Lock, a Stone Shape seal
            magic = spell_doors.of(self.sim).no_tools(str(d))
            needs = [rq.able(fight, me), rq.action_free(fight, me, "the Utilize action"), rq.in_bag(bag, TOOLS, "Thieves' Tools"),
                     self.tools_proficient(c), rq.need("a lock to pick", not magic, magic or "")]
            out.append(("pick", "Pick the lock of the %s (Thieves' Tools, DC 15)" % d, needs, {"door": str(d)}))
        return out

    def asks(self, me):
        """GM 2026-11-01: what this character can ask the GM about here (sim/live_asks.py): Thieves' Tools without
        proficiency, at a trap or a lock it has reached; the wall of a pit it is in, with no Climb Speed or magic."""
        if not getattr(self.sim, "live", None):
            return []
        out = []
        if self.untrained(self.sim.by_id(me)) and any(e.get("how") in ("tools", "pick") for e in self.offers(me)):
            out.append("Thieves' Tools")
        if me in self.in_pit and me not in self.allowed and self.climb_means(me) not in OWN_CLIMB:
            out.append("Climb out of the pit")
        return out

    def offers(self, me):
        """For the sheet: Utilize entries for the traps the party knows and the locks beside the character."""
        if not getattr(self.sim, "live", None):
            return []
        out = []
        for t in self.traps:
            if not self.known_to(t):
                continue
            for how, label, needs, extra in self.ways(me, t):
                ready, rows = rq.check(needs)
                e = dict(extra, op="trap", trap=t["id"], how=how, label=label, ready=ready, needs=rows,
                         time="bonus" if how == "light" else "move" if how == "climb" else "action")
                if not ready:
                    e["why"], e["link"] = rq.first_why(rows), rq.first_link(rows)
                out.append(e)
        for how, label, needs, extra in self.lock_ways(me):
            ready, rows = rq.check(needs)
            e = dict(extra, op="trap", how=how, label=label, ready=ready, needs=rows, time="action")
            if not ready:
                e["why"], e["link"] = rq.first_why(rows), rq.first_link(rows)
            out.append(e)
        return out

    def do(self, me, cmd):
        """A Utilize (or other) step on a trap, checked again, then done. -> how it was paid."""
        how = cmd.get("how")
        if how == "pick":
            row = next((w for w in self.lock_ways(me) if w[3]["door"] == str(cmd.get("door"))), None)
            if not row:
                raise TrapError("No locked door beside %s to pick." % self.sim.by_id(me)["name"])
            ready, rows = rq.check(row[2])
            if not ready:
                raise TrapError(rq.first_why(rows))
            return self.pick(me, str(cmd["door"]))
        t = self.by_id(cmd.get("trap"))
        if not self.known_to(t):
            raise TrapError("No trap the party knows of there.")
        row = next((w for w in self.ways(me, t) if w[0] == how and (w[3].get("target") in (None, cmd.get("target")))), None)
        if not row:
            raise TrapError("%s can't do that to the %s now." % (self.sim.by_id(me)["name"], t["name"]))
        ready, rows = rq.check(row[2])
        if not ready:
            raise TrapError(rq.first_why(rows))
        c, turn, fight = self.sim.by_id(me), self.sim.live.turn_state, self.sim.live
        bag = self.bag(me)
        if how == "light":
            bag_n = bag.count(TINDER)
            self.sim.party.use_bonus(me)
            t["lit"] = {"turn": me, "round": int(self.sim.S.round())}
            self.say("%s lights the oil with a Tinderbox (Bonus Action): it burns until the end of %s's turn 2 rounds from now; "
                     "5 Fire to a creature that enters it or ends its turn there" % (c["name"], c["name"]), "turn")
            for v in self.who_on(t["squares"]):
                self.burn(t, v, "is in the oil as it lights")
            return "bonus"
        if how == "climb":
            return self.climb(me, t, cmd)
        turn["action_used"], turn["attacks_left"] = True, 0
        name = t["name"]
        if how == "cut":
            self.make_safe(t, "%s cuts the trip wire (Utilize action; no check needed once it is found): the %s is disarmed" % (c["name"], name))
        elif how == "spike":
            bag.use_charge(SPIKES, SPIKES_PER_BUNDLE, "wedged under the %s" % name)
            self.make_safe(t, "%s wedges an Iron Spike %s (Utilize action): the %s can't go off" % (
                c["name"], "between the lid and the floor" if "lid" in TRAPS[t["kind"]]["parts"] else "under the pressure plate", name))
        elif how == "plug":
            self.make_safe(t, "%s plugs the holes with wax, cloth or detritus (Utilize action): the darts can't fire" % c["name"])
        elif how == "deface":
            self.make_safe(t, "%s defaces the glyph with a sharp tool (an action): the %s is disarmed" % (c["name"], name))
        elif how in ("tools", "sleight"):
            skill = "Sleight of Hand" if how == "sleight" else None
            total, line = self.dex_check(c, skill, tools=how == "tools")
            ok = total >= 15
            self.say("%s tries to disarm the %s (%s): %s vs DC 15 -> %s" % (c["name"], name, "Thieves' Tools, Utilize action"
                     if how == "tools" else "an action, Dexterity (Sleight of Hand)", line, "disarmed" if ok else "fails"))
            if ok:
                self.make_safe(t, None)
            elif t["kind"] == "poisoned_needle":
                self.fire(t, me, why="fails to disarm the needle")
        elif how in ("free_net", "free_trap"):
            v = cmd.get("target") or t.get("caught") or me
            dc = GEAR_KINDS[t["kind"]]["dc"] if t.get("gear") else numbers(t["kind"], t["band"])["dc"]
            self.athletics_free(me, v, t, dc)
        elif how == "slow":
            total, line = self.str_check(c, "Athletics")
            ok = total >= 20
            self.say("%s tries to slow the stone (an action): Strength (Athletics) %s vs DC 20 -> %s" % (c["name"], line,
                     "it slows by 15 ft" if ok else "it rolls on"))
            if ok:
                t["stone"]["ft"] = max(0, t["stone"]["ft"] - 15)
                if t["stone"]["ft"] <= 0:
                    t["stone"]["rolling"], t["stone"]["done"] = False, True
                    self.say("The stone stops: it is no longer a threat", "turn")
        return "action"

    def make_safe(self, t, line):
        t["armed"], t["disarmed"], t["how"] = False, True, line or "disarmed"
        if line:
            self.say(line, "turn")

    def pick(self, me, door):
        c = self.sim.by_id(me)
        self.sim.live.turn_state["action_used"], self.sim.live.turn_state["attacks_left"] = True, 0
        total, line = self.dex_check(c, None, tools=True)
        ok = total >= 15
        self.say("%s picks the lock of the %s (Thieves' Tools, Utilize action): %s vs DC 15 -> %s" % (
            c["name"], door, line, "it opens" if ok else "it holds"))
        needle = next((t for t in self.traps if t["kind"] == "poisoned_needle" and t.get("door") == door and t["armed"]), None)
        if needle:
            self.fire(needle, me, why="works the lock with Thieves' Tools, not its key")
        if ok:
            import spell_doors                                   # SPELL-OBJECTS-01: its mundane lock only
            spell_doors.of(self.sim).picked(door)
            self.say("The %s is unlocked: it can be opened now" % door, "turn")
        return "action"

    def climb(self, me, t, cmd):
        """Play live: a character climbs with the movement it has left (climb_core); the climb may take more than one
        turn. Out of the pit it comes onto the free square beside the pit it chose (x, y), or the first one free."""
        turn = self.sim.live.turn_state
        want = (cmd.get("x"), cmd.get("y"))
        res = self.climb_core(me, t, turn["movement"], want=None if None in want else tuple(want))
        turn["movement"] -= res["spent"]
        if res["status"] == "no_room":
            raise TrapError("No free square beside the pit to climb out onto.")
        return "move"

    def climb_core(self, me, t, budget, want=None, toward=None, check=None):
        """Up the pit's wall with `budget` feet of movement (SRD 5.2.1 Climbing). A Climb Speed (or Spider Climb): a
        foot a foot, no check. Any other way up: 1 extra foot a foot, and a Strength (Athletics) check at the pit's
        climbing DC once each turn it climbs (Advantage after an ally's Help); a failure makes no headway this turn.
        -> {"status": "up" | "out" | "slipped" | "no_room", "spent": feet}"""
        c = self.sim.by_id(me)
        depth = numbers(t["kind"], t["band"])["depth"]
        how = self.climb_means(me) or "the GM's ruling"
        per = 1 if how in OWN_CLIMB else 2
        if per == 2 and me not in self.allowed and self.climbed.get(me, 0) < depth:
            tried = self.climb_tried.get(me)
            if not tried or tried[0] != self.serial():
                dc = t.get("climb_dc", CLIMB_DC)
                helper = self.climb_help.pop(me, None)
                bonus = check() if check else None
                total, line = self.str_check(c, "Athletics", adv=helper is not None, bonus=bonus)
                tried = self.climb_tried[me] = (self.serial(), total >= dc)
                self.say("%s climbs the pit's smooth walls (%s): Strength (Athletics) %s vs DC %d -> %s" % (
                    c["name"], how, line + (" (Advantage: %s Helps)" % self.sim.by_id(helper)["name"] if helper else ""),
                    dc, "a hold" if tried[1] else "slips back: no headway this turn"))
            if not tried[1]:
                return {"status": "slipped", "spent": min(budget, (depth - self.climbed.get(me, 0)) * per)}
        need = (depth - self.climbed.get(me, 0)) * per
        spend = min(budget, need)
        self.climbed[me] = self.climbed.get(me, 0) + spend // per
        if self.climbed[me] < depth:
            self.say("%s climbs %d ft up the pit's wall (%s; %d of %d ft)" % (c["name"], spend // per, how, self.climbed[me], depth), "turn")
            return {"status": "up", "spent": spend}
        spot = self.edge_square(me, t, want, toward)
        if not spot:
            self.climbed[me] = depth                             # at the top, waiting for room
            return {"status": "no_room", "spent": spend}
        self.held.pop(me, None)
        self.in_pit.pop(me, None)
        self.climbed.pop(me, None)
        self.climb_tried.pop(me, None)
        self.allowed.discard(me)
        s = self.S()
        hook = s.tokenMoved
        s.tokenMoved = None                                      # the climb itself sets off nothing on the edge it leaves
        try:
            s.move(me, spot[0], spot[1])
        finally:
            s.tokenMoved = hook
        self.say("%s climbs out of the pit (%s) onto (%d, %d)" % (c["name"], how, spot[0], spot[1]), "turn")
        return {"status": "out", "spent": spend}

    def edge_square(self, me, t, want=None, toward=None):
        """A free square beside the pit: the one asked for (want), else the nearest to `toward`, else the first."""
        here = _sq(self.pos(me))
        pit = {tuple(s) for s in t["squares"]}
        cands = [(here[0] + dx, here[1] + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
        env = getattr(self.sim, "env", None)
        ok = [p for p in cands if p not in pit and self.enterable(*p) and not (env and env.square_taken(me, *p))
              and not (env and env.walled(here, p)) and p not in self.minds.keep_off(me)]
        if want is not None and tuple(want) in ok:
            return tuple(want)
        if toward is not None and ok:
            return min(ok, key=lambda p: (max(abs(p[0] - toward[0]), abs(p[1] - toward[1])),
                                          (p[0] - toward[0]) ** 2 + (p[1] - toward[1]) ** 2, p))
        return ok[0] if ok else None

    # ------------------------------------------------------------------ checks
    def dex_check(self, c, skill, tools=False, dis=False):
        import live_lore
        score = (c.get("abilities") or {}).get("dex", c.get("dex_score", 10)) or 10
        bonus = live_lore.mod(score)
        pb = 2 + (int(c.get("level", 1) or 1) - 1) // 4
        prof_skill = bool(skill) and skill in (c.get("skills") or [])
        prof_tools = tools and "thieves-tools" in rq.tool_proficiencies(c)
        if prof_skill or prof_tools:
            bonus += pb
        if skill and skill in (c.get("expertise") or []):
            bonus += pb
        adv = tools and prof_tools and "Sleight of Hand" in (c.get("skills") or [])   # 2024: tool and skill both: Advantage
        a, b = self.sim.rng.randint(1, 20), self.sim.rng.randint(1, 20)
        if dis and not adv:                                      # GM 2026-10-25 (T3): Thieves' Tools without proficiency
            d20 = min(a, b)
            rolls = "d20 %d/%d (Disadvantage: one try without proficiency)" % (a, b)
            return d20 + bonus, "Dexterity %s%s %+d = %d" % ("(%s) " % skill if skill else "", rolls, bonus, d20 + bonus)
        d20 = max(a, b) if adv else a
        rolls = "d20 %d/%d (Advantage: Thieves' Tools and Sleight of Hand)" % (a, b) if adv else "d20 %d" % a
        return d20 + bonus, "Dexterity %s%s %+d = %d" % ("(%s) " % skill if skill else "", rolls, bonus, d20 + bonus)

    def str_check(self, c, skill, adv=False, bonus=None):
        import live_lore
        if bonus is None:
            bonus, _ = live_lore.check_bonus(c, "str", skill) if c.get("abilities") else (int(c.get("str_save", 0) or 0), False)
        a = self.sim.rng.randint(1, 20)
        if adv:                                                  # goal 15: an ally's Help on the climb
            b = self.sim.rng.randint(1, 20)
            return max(a, b) + bonus, "d20 %d/%d (Advantage) %+d = %d" % (a, b, bonus, max(a, b) + bonus)
        return a + bonus, "d20 %d %+d = %d" % (a, bonus, a + bonus)

    def athletics_free(self, me, v, t, dc):
        c, vc = self.sim.by_id(me), self.sim.by_id(v)
        total, line = self.str_check(c, "Athletics")
        ok = total >= dc
        what = "the Net" if t["kind"] in ("falling_net", "net") else "the Hunting Trap"
        self.say("%s tries to free %s from %s (an action): Strength (Athletics) %s vs DC %d -> %s" % (
            c["name"], "itself" if v == me else vc["name"], what, line, dc, "free" if ok else "still held"))
        if ok:
            self.held.pop(v, None)
            gm = getattr(self.sim, "gm_rules", None)
            if gm and t["kind"] in ("falling_net", "net"):
                gm.remove(v, "Restrained", "freed from the Net")
            if t.get("caught") == v:
                t["caught"] = None
                if t["kind"] == "net":
                    t["gone"] = True                             # a thrown net lies there no more
        elif t["kind"] == "hunting-trap":
            self.say("The failed pull costs %s 1 Piercing" % vc["name"])
            self.deal(v, 1, "piercing", {"victims": {}})

    # ------------------------------------------------------------------ Search and Study of a square
    def examine(self, me, op, x, y, bonus=None):
        """The Search (Wisdom (Perception)) or Study (Intelligence (Investigation); Arcana for the statue's glyph) action
        on a square within 5 ft the character can see: one roll, every hidden part there whose DC it reaches.
        GM 2026-10-26 (goal 15): a creature the simulator plays searches too (sim/creature_traps.py, its own bonus):
        what it finds its side knows (foe_found), and its roll and finds are the GM's lines only."""
        c, label = self.sim.by_id(me), "Searches" if op == "search" else "Studies"
        party = self.minds.party_side(me)
        mine = (lambda t: t["found"]) if party else (lambda t: t.setdefault("foe_found", []))
        tell = "turn" if party else "secret"
        parts = []
        for t in self.traps:
            if t.get("gear") or t.get("gone"):
                continue
            for pid, p in TRAPS[t["kind"]]["parts"].items():
                if p["action"] != op or pid in mine(t) or (p.get("after") and p["after"] not in mine(t)):
                    continue
                on = [t["statue"]] if p["on"] == "statue" else t["area"] if p["on"] == "area" else t["squares"]
                if [x, y] in [list(s) for s in on]:
                    parts.append((t, pid, p))
        skill = "Perception" if op == "search" else "Investigation"
        study_arcana = op == "study" and parts and all(p["skill"] == "Arcana" for _, _, p in parts)
        if study_arcana:
            skill = "Arcana"
        if bonus is not None and not study_arcana:
            pass                                                 # a creature's own Perception or Investigation
        elif op == "search":
            gm = self.sim.gm_rules
            bonus = gm.passive_perception(me) - 10 if gm else 0
        else:
            import creature_traps
            bonus = creature_traps.creature_bonus(c, "int", skill)
        d20 = self.sim.rng.randint(1, 20)
        total = d20 + bonus
        self.say("%s %s square (%d, %d) (Action): %s (%s) d20 %d %+d = %d" % (
            c["name"], label, x, y, "Wisdom" if op == "search" else "Intelligence", skill, d20, bonus, total),
            "dice" if party else "secret")
        found = []
        for t, pid, p in parts:
            if p["skill"] != skill:
                continue
            if total >= p["dc"]:
                mine(t).append(pid)
                found.append((t, pid, p))
        for t, pid, p in found:
            self.say("%s finds %s: a %s (%s). %s knows it now" % (c["name"], p["what"], t["name"],
                     severity(t["kind"], t["band"]), "The party" if party else "Its side"), tell)
            if pid == "meaning":
                self.say('The glyph means "fire": the statue breathes flame when its trap goes off', tell)
        if not found:
            self.say("%s finds nothing there" % c["name"], tell)
        return found

    def examine_needs(self, me, op, x, y):
        fight = self.sim.live
        sees = self.sim.sees_square(me, x, y)
        return [rq.able(fight, me), rq.action_free(fight, me, "Search" if op == "search" else "Study"),
                rq.need("a square within 5 ft", self.near(me, [(x, y)]), "Examine a square within 5 ft (%s stands too far "
                        "from (%d, %d))." % (self.sim.by_id(me)["name"], x, y)),
                rq.need("a square you can see", sees, "%s can't see square (%d, %d)." % (self.sim.by_id(me)["name"], x, y))]

    # ------------------------------------------------------------------ area gear from the bag (sim/live_items.py)
    def gear_needs(self, me, item, x, y, bag):
        k = GEAR_KINDS[item]
        fight = self.sim.live
        needs = [rq.able(fight, me), rq.in_bag(bag, item, k["name"]), rq.action_free(fight, me, "the Utilize action")]
        if item == "hunting-trap":
            needs.append(rq.in_bag(bag, SPIKES, "Iron Spikes (to anchor its chain)"))
        if x is None or y is None:
            needs.append(rq.need("a square", False, "Choose the square (x, y) to cover."))
            return needs
        cells = self.gear_cells(item, x, y)
        ok_cells = all(self.enterable(*q) for q in cells)
        needs.append(rq.need("level ground a creature can enter", ok_cells, "%s needs level ground: (%d, %d) is a wall or off "
                             "the map." % (k["name"], x, y)))
        reach = k["within"] // self.sim.sc.get("units", 5)
        here = self.footprint(me)
        needs.append(rq.need("within %d ft" % k["within"], all(any(max(abs(a - q[0]), abs(b - q[1])) <= reach for a, b in here)
                                                                for q in cells),
                             "%s covers %s within %d ft of %s." % (k["name"], "a 10-foot square" if k["size"] == 2 else "a 5-foot square",
                                                                    k["within"], self.sim.by_id(me)["name"])))
        busy = {tuple(s) for t in self.traps if not t.get("gone") and t.get("gear") for s in t["squares"]}
        needs.append(rq.need("no gear there yet", not (busy & set(cells)), "Something is already spread on that square."))
        return needs

    @staticmethod
    def gear_cells(item, x, y):
        n = GEAR_KINDS[item]["size"]
        return [(x + i, y + j) for i in range(n) for j in range(n)]

    def put_gear(self, me, item, x, y, bag):
        c = self.sim.by_id(me)
        bag.take(item, 1, "spread in a fight" if item != "hunting-trap" else "set in a fight")
        if item == "hunting-trap":
            bag.use_charge(SPIKES, SPIKES_PER_BUNDLE, "anchors a Hunting Trap's chain")
        t = self.place({"kind": item, "squares": [list(q) for q in self.gear_cells(item, x, y)]}, quiet=True, by=me)
        t["by_side"] = c.get("side")
        say = {"caltrops": "%s spreads Caltrops on (%d, %d) (Utilize action): DC 15 Dexterity save on entering, or 1 Piercing and Speed 0",
               "ball-bearings": "%s spills Ball Bearings over the 10-foot square from (%d, %d) (Utilize action): DC 10 Dexterity save on entering, or Prone",
               "oil": "%s pours Oil on (%d, %d) (Utilize action): it burns once lit",
               "hunting-trap": "%s sets a Hunting Trap on (%d, %d), its chain on an Iron Spike (Utilize action): DC 13 Dexterity save, or 1d4 Piercing and held"}[item]
        self.say(say % (c["name"], x, y), "turn")
        return t

    def pit_gap(self, a, b):
        """Feet down between a creature at the bottom of a pit and one outside it (0: none, or both in the same pit)."""
        pa, pb = self.in_pit.get(a), self.in_pit.get(b)
        if pa == pb:
            return 0
        t = self.by_id(pa or pb)
        return numbers(t["kind"], t["band"])["depth"]

    # ------------------------------------------------------------------ what the table draws
    def view(self, gm=True):
        out = []
        for t in self.traps:
            if t.get("gone") and not t.get("rubble") and not t.get("open"):
                continue
            row = {"id": t["id"], "kind": t["kind"], "name": t["name"], "squares": t["squares"], "armed": t["armed"],
                   "disarmed": t["disarmed"], "found": list(t["found"]), "fired": t["fired"], "open": t["open"],
                   "known": bool(self.known_to(t)), "gear": bool(t.get("gear")), "rubble": bool(t.get("rubble"))}
            if not t.get("gear"):
                row.update(band=t["band"], severity=severity(t["kind"], t["band"]))
                if gm or "glyph" in t["found"] or t["fired"]:
                    row["statue"] = t.get("statue")
                if gm:
                    row["area"] = t.get("area")
                    row["known_by"] = list(t.get("known_by") or [])          # goal 15: the lair's creatures
                    row["foe_found"] = list(t.get("foe_found") or [])
                if t.get("stone") and (gm or t["fired"]):
                    row["stone"] = dict(t["stone"])
            else:
                row["lit"] = t.get("lit") is not None
            out.append(row)
        return out

    # ------------------------------------------------------------------ the referee (arithmetic only)
    def referee_check(self, record):
        """REFEREE-01 for traps: only the creatures the trap reaches took its damage; no one more than its dice (half on a
        success); the DC is the band's; the conditions are the trap's own."""
        ref = getattr(self.sim, "referee", None)
        t = record["trap"]
        if not ref:
            return
        expect = numbers(t["kind"], t["band"]).get("dc") if not t.get("gear") else GEAR_KINDS[t["kind"]].get("dc")
        if record.get("dc") is not None and expect is not None and record["dc"] != expect:
            ref.note(t["name"], "used DC %s; levels %s give DC %s." % (record["dc"], t.get("band"), expect), SRD)
        taken = {}
        for src, tgt, amount in ref.hurts[record.get("start_hurt", 0):]:
            taken[tgt] = taken.get(tgt, 0) + int(amount or 0)
        for v, row in record["victims"].items():
            top = row.get("max")
            if top is not None and taken.get(v, 0) > top:
                ref.note(t["name"], "dealt %d to %s; its dice allow at most %d." % (taken[v], self.sim.by_id(v)["name"], top), SRD)
        record["start_hurt"] = len(ref.hurts)


def _dice_max(expr):
    import re
    return sum(int(n) * int(d) for n, d in re.findall(r"(\d+)d(\d+)", expr or ""))


def of(sim):
    """The fight's traps (made once)."""
    t = getattr(sim, "traps", None)
    if t is None:
        t = sim.traps = Traps(sim)
    return t
