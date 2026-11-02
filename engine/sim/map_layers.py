"""MAP-LAYERS-01 (GM 2026-10-24: "address maps and adding mask layers to allow tokens to overlap, selectably merge, have
effects on layers"; "like spell effects that cause obscurement (fog, smoke, darkness etc), invisibility"; "A rider uses
the mount's movement until separated"): steps 1-3 of docs/development/MAP_LAYERS_PLAN.md. The engine decides; the
table only draws what this module publishes (LiveFight snapshot "layers", party_sight "seen_by" and "invisible").

1. Vision masks from spells. Fog Cloud, Darkness and Stinking Cloud cast in Play live make a zone in the environment
   (sim/environment.py, kind "obscured", level "heavy", a circle), so everything that already reads sight reads it
   too: Sim.sees and sees_square (the party's fog), attacks against an unseen target or by an unseen attacker, Hide,
   Search, spells that need sight. Each zone has its caster (owner), its spell and its time; it lasts while the
   caster keeps Concentration on that cast (Party.concentrates) and its duration runs, and it ends with either.
   Who sees through (SRD 5.2.1 Rules Glossary): Blindsight within its range sees through any of them; in magical
   Darkness also Truesight within its range and Devil's Sight within 120 ft ("Darkvision can't see through it").
   Stinking Cloud: a creature that starts its turn inside makes a Constitution save or is Poisoned until the end of
   that turn, and can't take an action or a Bonus Action.
2. Invisibility per viewer: who sees an Invisible creature (Truesight or Blindsight within range, See Invisibility),
   and for each player character the creatures it sees, so a seat's map leaves out what its own character can't see.
3. Mount and Dismount (SRD 5.2.1 Mounted Combat): during its move a creature mounts a willing creature within 5 ft
   that is at least one size larger, or dismounts, for half its Speed (round down). A controlled mount (trained:
   horses, mules and the like; or the GM's choice) moves on its rider's turn on its own Speed and can only Dash,
   Disengage or Dodge; an independent mount keeps its own turn and carries its rider along. Falling Off and a mount at
   0 HP are SIM-ENV-04 (sim/environment.py). Every prerequisite goes through sim/requirements.py with its reason.
"""
import contextlib, math, re

import requirements as rq

# name -> SRD 5.2.1: level, range, the Sphere's radius (and per slot level above), how long (rounds), the look.
ZONE_SPELLS = {
    "Fog Cloud": dict(level=1, range_ft=120, radius_ft=20, per_level_ft=20, rounds=600, appearance="smoke",
                      flag="fog_cloud", what="a Sphere of fog (Heavily Obscured)"),
    "Darkness": dict(level=2, range_ft=60, radius_ft=15, rounds=100, appearance="darkness", darkness=True,
                     flag="darkness", what="magical Darkness (Darkvision can't see through it)"),
    "Stinking Cloud": dict(level=3, range_ft=90, radius_ft=20, rounds=10, appearance="poison", stinking=True,
                           flag="stinking_cloud", what="a Sphere of nauseating gas (Heavily Obscured)"),
}
# Mounted Combat: "Domesticated horses, mules, and similar creatures have such training" (a controlled mount)
TRAINED = ("horse", "pony", "mule", "camel", "elephant", "mastiff", "warhorse", "donkey", "ox")
MOUNT_ACTIONS = ("dash", "disengage", "dodge")
SIZES = ["tiny", "small", "medium", "large", "huge", "gargantuan"]


class LayerError(ValueError):
    pass


def _senses_ft(c, sense):
    m = re.search(r"%s\s*(\d+)" % sense, str(c.get("senses") or ""), re.I)
    return int(m.group(1)) if m else 0


def devils_sight(c):
    names = [str(f.get("name") if isinstance(f, dict) else f) for f in (c.get("feature_list") or []) + (c.get("invocations") or [])]
    return bool(c.get("devils_sight")) or any("devil's sight" in n.lower().replace("’", "'") for n in names)


def size_of(c):
    s = str(c.get("size") or "").lower()
    if s in SIZES:
        return s
    sq = max(1, int(round(float(c.get("space") or 5) / 5)))
    return {1: "medium", 2: "large", 3: "huge"}.get(sq, "gargantuan")


def feet(sim, p, q):
    return math.hypot(q[0] - p[0], q[1] - p[1]) * sim.sc.get("units", 5)


def default_mode(c):
    """"You can control a mount only if it has been trained to accept a rider": trained kinds (horses, mules and the
    like) start controlled, the rest independent; the GM may change either (set_mode)."""
    kind = str(c.get("srd_name") or c.get("name") or "").lower()
    return "controlled" if any(w in kind for w in TRAINED) or c.get("trained_mount") else "independent"


def mount_mode(c):
    return c.get("mount_mode") if c.get("mount_mode") in ("controlled", "independent") else "controlled"


# ---------------------------------------------------------------------- sight (called by the environment and Sim.sees)
def sees_through(env, viewer, z, p, q):
    """True when the viewer's senses pierce this spell zone between p (the viewer) and q (what it looks at). Zones from
    the map itself (silt, smoke drawn by the GM) keep the environment's old rule: nothing sees through them."""
    c, d = env.sim.by_id(viewer), feet(env.sim, p, q)
    bs = _senses_ft(c, "blindsight")
    if bs and d <= bs + 0.01:                                    # GM 2026-10-25 (ruling M5): silt too (not Total Cover)
        return True
    if not z.get("spell"):
        return False
    if z.get("darkness"):
        ts = _senses_ft(c, "truesight")
        if (ts and d <= ts + 0.01) or (devils_sight(c) and d <= 120.01):
            return True
    return False


def sees_invisible(sim, viewer, target):
    """SRD 5.2.1: Truesight and Blindsight within range see a creature that has the Invisible condition; so does See
    Invisibility (a sheet flag "sees_invisible" until that spell is played here)."""
    c = sim.by_id(viewer)
    if c.get("sees_invisible") or c.get("see_invisibility"):
        return True
    env = getattr(sim, "env", None)
    if env is None:
        return False
    d = feet(sim, env.pos(viewer), env.pos(target))
    return any(r and d <= r + 0.01 for r in (_senses_ft(c, "truesight"), _senses_ft(c, "blindsight")))


def zone_blind(env, viewer, target):
    """The spell zone that keeps the viewer from seeing the target (for attack rolls), or None."""
    p, q = env.pos(viewer), env.pos(target)
    zones = [z for z in env.of_kind("obscured") if z.get("spell") and z.get("level") == "heavy"]
    if not zones:
        return None
    n = max(2, int(math.hypot(q[0] - p[0], q[1] - p[1]) * 4))
    for z in zones:
        if sees_through(env, viewer, z, p, q):
            continue
        if any(env.inside(z, (p[0] + (q[0] - p[0]) * k / n, p[1] + (q[1] - p[1]) * k / n)) for k in range(n + 1)):
            return z
    return None


def alive(env, z):
    """A map zone always; a spell zone while its caster keeps Concentration on this very cast."""
    if not z.get("owner"):
        return True
    if z.get("lasting"):                                         # SPELL-EFFECTS-01: no Concentration (Grease): its time
        return not z.get("ended")
    party = getattr(env.sim, "party", None)
    return (not z.get("ended") and party is not None and party.concentrates(z["owner"]) == z["spell"]
            and getattr(party, "layer_zone", {}).get(z["owner"]) == z["n"])


# ---------------------------------------------------------------------- the live fight's layers
class Layers:
    def __init__(self, fight):
        self.fight, self.n = fight, 0
        fight.sim.layers = self                                  # gm_rules.turn_start and Sim.token_moved find it here

    @property
    def sim(self):
        return self.fight.sim

    @property
    def party(self):
        return self.fight.sim.party

    @property
    def env(self):
        return self.fight.sim.env

    def name(self, i):
        return self.sim.by_id(i)["name"]

    def round(self):
        return int(self.sim.S.round())

    # ------------------------------------------------------------------ step 1: spell zones
    @staticmethod
    def known(c):
        listed = {sp.get("name") for sp in c.get("spell_list") or [] if isinstance(sp, dict)}
        return [n for n, s in ZONE_SPELLS.items() if n in listed or c.get(s["flag"])]

    def zones(self):
        return [z for z in self.env.zones if z.get("owner") and alive(self.env, z)]

    def needs(self, me, name, x=None, y=None, slot=None):
        c, s, t = self.sim.by_id(me), ZONE_SPELLS.get(name), self.fight.turn_state
        needs = [rq.need("the spell on the sheet", s is not None and name in self.known(c),
                         "%s is not on %s's sheet." % (name, c["name"]), rq.LINKS["characters"])]
        if s is None:
            return needs
        needs.append(rq.need("this character's turn", bool(t) and t.get("id") == me, "It is not %s's turn." % c["name"]))
        needs.append(rq.able(self.fight, me))
        needs.append(rq.action_free(self.fight, me, name))
        lv = max(s["level"], int(slot or s["level"]))
        pool = self.party.pools.get(me) or [self.party.slots.get(me, 0)]
        needs.append(rq.need("a spell slot", sum(pool[lv - 1:]) > 0,
                             "No spell slot of level %d or higher left for %s." % (lv, name)))
        needs.append(rq.need("no other slot this turn", self.party.slot_turn.get(me) != self.party.s.turnSerial,
                             "One spell with a spell slot per turn: %s already spent a slot this turn (SRD 5.2.1)." % c["name"]))
        if x is not None:
            here, u = self.party.pos(me), self.sim.sc.get("units", 5)
            far = max(abs(x - here[0]), abs(y - here[1])) * u
            needs.append(rq.need("the point in range", far <= s["range_ft"] + 0.01,
                                 "That point is %d ft away: out of %s's range (%d ft)." % (far, name, s["range_ft"])))
            needs.append(rq.need("a clear path to the point", not self.party.walled(here, (x, y)),
                                 "A wall blocks the way to that point."))
        return needs

    def spell_offers(self, me):
        c, out = self.sim.by_id(me), []
        for name in self.known(c):
            s = ZONE_SPELLS[name]
            ready, rows = rq.check(self.needs(me, name))
            out.append({"name": name, "level": s["level"], "time": "action", "shape": "sphere", "appearance": s["appearance"],
                        "range_ft": s["range_ft"], "radius_ft": s["radius_ft"], "concentration": True, "layer": "air",
                        "zone": s["what"], "ready": ready, "why": rq.first_why(rows), "link": rq.first_link(rows)})
        return out

    def cast(self, me, cmd):
        name = cmd.get("spell")
        try:
            x, y = int(cmd["x"]), int(cmd["y"])
        except (KeyError, TypeError, ValueError):
            raise LayerError("Place %s on a square." % name)
        ready, rows = rq.check(self.needs(me, name, x, y, cmd.get("slot")))
        if not ready:
            raise LayerError(rq.first_why(rows))
        s, c, party, t = ZONE_SPELLS[name], self.sim.by_id(me), self.party, self.fight.turn_state
        t["action_used"], t["attacks_left"] = True, 0
        lv = party.spend_slot(me, max(s["level"], int(cmd.get("slot") or s["level"])))
        radius = s["radius_ft"] + s.get("per_level_ft", 0) * (lv - s["level"])
        party.start_concentration(me, name)                      # a new Concentration spell ends the one held
        self.sweep()                                             # (its zone leaves the map now)
        party.__dict__.setdefault("gm_concentration", {})[me] = name
        self.n += 1
        party.__dict__.setdefault("layer_zone", {})[me] = self.n
        u = self.sim.sc.get("units", 5)
        r = radius / u
        z = {"id": "%s-%d" % (name.lower().replace(" ", "-"), self.n), "n": self.n, "kind": "obscured", "level": "heavy",
             "spell": name, "owner": me, "circle": [x, y, r], "origin": [x, y], "radius_ft": radius,
             "rect": [int(math.floor(x - r)), int(math.floor(y - r)), int(math.ceil(x + r)), int(math.ceil(y + r))],
             "appearance": s["appearance"], "layer": "air", "darkness": bool(s.get("darkness")),
             "stinking": bool(s.get("stinking")), "cast_round": self.round(), "ends_round": self.round() + s["rounds"],
             "dc": party.spell_dc(c)}
        self.env.zones.append(z)
        inside = [o["id"] for o in self.sim.sc["combatants"] if not self.sim.down(o["id"]) and self.env.inside(z, self.party.pos(o["id"]))]
        self.sim.say("turn", "%s casts %s (a level %d slot, Concentration): %s, %d-ft radius, centred on square (%d, %d)%s" % (
            c["name"], name, lv, s["what"], radius, x, y,
            "; inside: " + ", ".join(self.name(i) for i in inside) if inside else ""))
        return {"spell": name, "appearance": s["appearance"], "shape": "circle", "origin": [x, y], "radius_ft": radius,
                "targets": inside, "lasting": True, "from": list(self.party.pos(me))}

    def sweep(self):
        """Spell zones whose Concentration ended leave the map, with a line in the log (never under the publication lock)."""
        gone = [z for z in self.env.zones if z.get("owner") and not alive(self.env, z)]
        for z in gone:
            self.env.zones.remove(z)
            self.sim.say("dice", "%s's %s ends: %s" % (self.name(z["owner"]), z["spell"],
                                                      z.get("ended") or "its Concentration ended"))
        if gone:
            import spell_zones                                   # SPELL-EFFECTS-01: what a zone held ends with it
            spell_zones.ended(self.sim, gone)

    def turn_start(self, me):
        """The start of a creature's turn: its own zones past their time end; Stinking Cloud's save. Returns why its turn
        is lost, or "": it can't take an action or a Bonus Action (a monster's turn then ends: its move is not played),
        or it already moved this round as a controlled mount on its rider's Initiative and has since lost its rider."""
        rnd = self.round()
        c = self.sim.by_id(me)
        if c.get("ridden_round") == rnd and self.env.rider_of(me) is None and not c.get("pc"):
            return "it moved this round as %s's controlled mount (its Initiative matched its rider's)" % c.get("ridden_by", "its rider")
        for z in [z for z in self.env.zones if z.get("owner") == me and alive(self.env, z)]:
            if rnd >= z["ends_round"]:
                z["ended"] = "its duration is over"
                if not z.get("lasting"):                         # SPELL-EFFECTS-01: Grease holds no Concentration
                    self.party.end_concentration(me)
        self.sweep()
        if self.sim.down(me):
            return ""
        gm = self.sim.gm_rules
        cloud = next((z for z in self.zones() if z.get("stinking") and self.env.inside(z, self.party.pos(me))), None)
        if not cloud or not gm:
            return ""
        if gm.cond_immune(me, "Poisoned"):
            self.sim.say("dice", "%s starts its turn in the Stinking Cloud: immune to the Poisoned condition" % self.name(me))
            return ""
        ref = getattr(self.sim, "referee", None)                  # REFEREE-02: the referee checks this later save
        with ref.watch_area(cloud["owner"], "Stinking Cloud", me, "start", origin=cloud["origin"]) if ref \
                else contextlib.nullcontext():
            if gm.condition_save(me, "con", cloud["dc"], "Stinking Cloud", adv=gm.antitoxin(me, "Poisoned")):
                return ""
            gm.add(me, "Poisoned", "(Stinking Cloud: no action or Bonus Action this turn)", by=cloud["owner"], lib=True,
                   until={"who": "target", "when": "end"})
        if not gm.cond.get(me, {}).get("Poisoned"):
            return ""
        if not c.get("pc"):
            self.leave_cloud(me, cloud)                          # GM 2026-10-25 (ruling M4): it still moves
        return "it is Poisoned by the Stinking Cloud: no action or Bonus Action"

    def leave_cloud(self, me, cloud):
        """GM 2026-10-25 (ruling M4; SRD 5.2.1 Stinking Cloud: no action or Bonus Action, its move kept): a creature the
        simulator plays walks out of the cloud by the shortest way it can, within its Speed (Opportunity Attacks allowed);
        no way out: it stays."""
        c, sim = self.sim.by_id(me), self.sim
        speed = c["_speed_now"] if "_speed_now" in c else int(str(c.get("speed", "30")).split()[0])
        if speed <= 0:
            return
        best, _, _ = sim._route_search(me, speed)
        occupied = sim.occupied_cells(me)
        out = [q for q in best if q not in occupied and not self.env.inside(cloud, q)]
        if not out:
            self.sim.say("turn", "%s can't get out of the Stinking Cloud this turn" % self.name(me))
            return
        goal = min(out, key=lambda q: best[q][0])
        self.sim.say("turn", "%s staggers out of the Stinking Cloud (its move; no action or Bonus Action)" % self.name(me))
        sim.npc_walk(me, best[goal][1])

    def live_turn_start(self, me):
        """A live character's turn begins (after LiveFight.turn set its turn state)."""
        t = self.fight.turn_state
        for f in [o["id"] for o in self.sim.sc["combatants"] if o.get("mount_dodge_by") == me]:
            self.sim.by_id(f).pop("dodging", None)                # a controlled mount's Dodge lasts until now
            self.sim.by_id(f).pop("mount_dodge_by", None)
        m = self.env.mount_of(me)
        if m:
            self._ride_turn(me, m)
        if self.turn_start(me):                                  # a character keeps its move; the cloud takes the rest
            t["action_used"], t["attacks_left"] = True, 0
            self.party.use_bonus(me)
            self.sim.say("turn", "%s is Poisoned by the Stinking Cloud: no action or Bonus Action this turn" % self.name(me))

    def live_turn_end(self, me):
        m = (self.fight.turn_state or {}).get("mount_disengaged")
        if m:
            self.sim.S.removeEffect(m, "Note: Disengage")

    def publish(self):
        """What the table draws (no logging: this runs under the publication lock)."""
        rnd = self.round()
        zones = [{"n": z["n"], "spell": z["spell"], "owner": z["owner"], "owner_name": self.name(z["owner"]),
                  "origin": z["origin"], "radius_ft": z["radius_ft"], "appearance": z["appearance"], "layer": z["layer"],
                  "darkness": z["darkness"], "rounds_left": max(0, z["ends_round"] - rnd),
                  **({"cube": z["cube"]} if z.get("cube") else {}),         # SPELL-EFFECTS-01: a square area (Web)
                  **({"veil": z["veil"]} if z.get("veil") else {})} for z in self.zones()]
        mounts = [{"rider": c["id"], "mount": self.env.mount_of(c["id"]), "mode": self.mode(self.env.mount_of(c["id"]))}
                  for c in self.sim.sc["combatants"] if c.get("mount") and self.env.mount_of(c["id"])]
        return {"zones": zones, "mounts": mounts}

    # ------------------------------------------------------------------ step 2: who sees whom, per character
    def sight_parts(self, pcs):
        """For each standing player character, the creatures it sees now (other characters too); the creatures that
        are Invisible. A seat's map keeps an Invisible creature only when its own character sees it."""
        gm = self.sim.gm_rules
        everyone = [c["id"] for c in self.sim.sc["combatants"]]
        invisible = [i for i in everyone if gm and gm.cond.get(i, {}).get("Invisible")]
        seen_by = {p: [o for o in everyone if o != p and self.sim.sees(p, o)] for p in pcs}
        return {"seen_by": seen_by, "invisible": invisible}

    # ------------------------------------------------------------------ step 3: mounts
    def mode(self, m):
        """controlled or independent (the environment's reading: a scenario's mount is controlled unless it says not)."""
        return mount_mode(self.sim.by_id(m))

    def set_mode(self, m, mode):
        if mode not in ("controlled", "independent"):
            raise LayerError("A mount is controlled or independent.")
        if not any(c["id"] == m for c in self.sim.sc["combatants"]):
            raise LayerError("No such creature.")
        self.sim.by_id(m)["mount_mode"] = mode
        return mode

    def half_speed(self, me):
        t = self.fight.turn_state or {}
        return int(t.get("speed", 30)) // 2

    def own_movement(self, me):
        """The rider's own movement left (spent on mounting and dismounting); the pair's movement is the mount's."""
        t = self.fight.turn_state or {}
        return t.get("rider_movement", t.get("movement", 0)) if self.env.mount_of(me) else t.get("movement", 0)

    def mount_needs(self, me, tid):
        c, sim, t = self.sim.by_id(me), self.sim, self.fight.turn_state
        m = next((o for o in sim.sc["combatants"] if o["id"] == tid), None)
        needs = [rq.need("this character's turn", bool(t) and t.get("id") == me, "It is not %s's turn." % c["name"])]
        blocked = self.fight.movement_blocked(me) if t else None
        needs.append(rq.need("able to move", not blocked, blocked or ""))      # mounting is movement, not an action
        needs.append(rq.need("not mounted already", not self.env.mount_of(me),
                             "%s is already riding %s." % (c["name"], self.name(self.env.mount_of(me)) if self.env.mount_of(me) else "")))
        half = self.half_speed(me)
        needs.append(rq.need("half its Speed in movement", (t or {}).get("movement", 0) >= half,
                             "Mounting costs half %s's Speed (%d ft); %d ft of movement left." % (c["name"], half, (t or {}).get("movement", 0))))
        if m is None or tid == me:
            needs.append(rq.need("a creature to ride", False, "Choose another creature to mount."))
            return needs
        needs.append(rq.need("the mount standing", not sim.down(tid), "%s is down." % m["name"]))
        needs.append(rq.need("within 5 ft", self.party.dist(me, tid) <= 5.01,
                             "%s is %d ft away: mounting needs a creature within 5 ft." % (m["name"], round(self.party.dist(me, tid)))))
        willing = m.get("side") == c.get("side") and not m.get("unwilling")
        needs.append(rq.need("a willing creature", willing, "%s is not willing to carry %s (a mount must be willing)." % (m["name"], c["name"])))
        if m.get("pc"):                                          # GM 2026-10-25 (ruling M2): that player is asked first
            needs.append(rq.need("its player's yes", bool(m.get("lets_ride")),
                                 "%s is a player's character: %s's player turns on Let others ride me on their own sheet first."
                                 % (m["name"], m["name"])))
        bigger = SIZES.index(size_of(m)) >= SIZES.index(size_of(c)) + 1
        needs.append(rq.need("one size larger", bigger, "%s is %s and %s is %s: a mount must be at least one size larger than its rider." % (
            m["name"], size_of(m).title(), c["name"], size_of(c).title())))
        needs.append(rq.need("an anatomy for a rider", not m.get("no_rider"), "%s has no anatomy for a rider (the GM's ruling)." % m["name"]))
        needs.append(rq.need("no other rider", self.env.rider_of(tid) is None,
                             "%s already carries %s." % (m["name"], self.name(self.env.rider_of(tid)) if self.env.rider_of(tid) else "")))
        needs.append(rq.need("the mount not riding", not self.env.mount_of(tid), "%s is itself riding a creature." % m["name"]))
        return needs

    def _ride_turn(self, me, m):
        """A rider's turn: a controlled mount moves on it with the mount's Speed; an independent one moves on its own."""
        t = self.fight.turn_state
        t["rider_movement"] = t["movement"]
        if self.mode(m) == "controlled" and not self.sim.down(m) and not (self.sim.gm_rules and self.sim.gm_rules.incapacitated(m)):
            mc = self.sim.by_id(m)
            t["movement"] = int(str(mc.get("speed", "30")).split()[0])
            mc["ridden_round"], mc["ridden_by"] = self.round(), self.name(me)
        else:
            t["movement"] = 0

    def mount(self, me, cmd):
        tid = cmd.get("target")
        ready, rows = rq.check(self.mount_needs(me, tid))
        if not ready:
            raise LayerError(rq.first_why(rows))
        c, m, t, s = self.sim.by_id(me), self.sim.by_id(tid), self.fight.turn_state, self.sim.S
        half = self.half_speed(me)
        t["movement"] -= half
        c["mount"] = tid
        m.setdefault("mount_mode", default_mode(m))              # the GM can change it (set_mode)
        self.env.dismounted.discard(me)
        mx, my = self.party.pos(tid)
        n = self.sim.size_sq(tid)                                # the rider sits on the mount's first square; the mount
        rx, ry = int(round(mx - (n - 1) / 2)), int(round(my - (n - 1) / 2))   # keeps that offset as the pair moves
        c["mount_offset"] = [mx - rx, my - ry]
        s.move(me, rx, ry)
        self.sim.settle()
        self._ride_turn(me, tid)
        mode = self.mode(tid)
        self.sim.say("turn", "%s mounts %s (%d ft of movement): %s" % (c["name"], m["name"], half,
                     "a controlled mount, it moves on %s's turn with its own Speed (%d ft now) and can only Dash, Disengage "
                     "or Dodge" % (c["name"], t["movement"]) if mode == "controlled" else
                     "an independent mount, it keeps its own turn and carries %s along" % c["name"]))
        return {"ok": True, "result": "mount", "mount": tid, "mode": mode}

    def dismount_squares(self, me):
        m = self.env.mount_of(me)
        if not m:
            return []
        mx, my = self.party.pos(m)
        n = self.sim.size_sq(m)
        out = []
        for x in range(int(math.floor(mx - n / 2 - 1)), int(math.ceil(mx + n / 2 + 1)) + 1):
            for y in range(int(math.floor(my - n / 2 - 1)), int(math.ceil(my + n / 2 + 1)) + 1):
                gap = max(abs(x - mx), abs(y - my)) - ((1 + n) / 2 - 1)
                if 0.5 < gap <= 1.01 and not self.env.square_taken(me, x, y) and not self.env.square_taken(m, x, y) \
                        and not self.env.walled((mx, my), (x, y)):
                    out.append([x, y])
        here = self.party.pos(me)
        return sorted(out, key=lambda p: (abs(p[0] - here[0]) + abs(p[1] - here[1]), p))

    def dismount_needs(self, me, square=None):
        c, t = self.sim.by_id(me), self.fight.turn_state
        m = self.env.mount_of(me)
        needs = [rq.need("this character's turn", bool(t) and t.get("id") == me, "It is not %s's turn." % c["name"]),
                 rq.need("mounted", bool(m), "%s is not riding anything." % c["name"])]
        if not m:
            return needs
        blocked = self.fight.movement_blocked(me) if t else None
        needs.append(rq.need("able to move", not blocked, blocked or ""))
        half, own = self.half_speed(me), self.own_movement(me)
        needs.append(rq.need("half its Speed in movement", own >= half,
                             "Dismounting costs half %s's Speed (%d ft); %d ft of its own movement left." % (c["name"], half, own)))
        free = self.dismount_squares(me)
        needs.append(rq.need("a free space beside the mount", bool(free), "No free space within 5 ft of %s." % self.name(m)))
        if square is not None and free:
            needs.append(rq.need("that space", list(square) in free, "Square (%d, %d) is not a free space within 5 ft of %s." % (
                square[0], square[1], self.name(m))))
        return needs

    def dismount(self, me, cmd):
        square = (int(cmd["x"]), int(cmd["y"])) if isinstance(cmd.get("x"), int) and isinstance(cmd.get("y"), int) else None
        ready, rows = rq.check(self.dismount_needs(me, square))
        if not ready:
            raise LayerError(rq.first_why(rows))
        c, t, m = self.sim.by_id(me), self.fight.turn_state, self.env.mount_of(me)
        x, y = square or self.dismount_squares(me)[0]
        half = self.half_speed(me)
        own = self.own_movement(me) - half
        self.env.dismounted.add(me)
        t.pop("rider_movement", None)
        t["movement"] = own                                      # its own feet again: what it has not spent
        self.sim.S.move(me, x, y)
        self.sim.settle()
        self.sim.say("turn", "%s dismounts from %s to square (%d, %d) (%d ft of movement; %d ft left)" % (
            c["name"], self.name(m), x, y, half, own))
        return {"ok": True, "result": "dismount", "mount": m, "at": [x, y]}

    def mount_action_needs(self, me, what):
        c, t = self.sim.by_id(me), self.fight.turn_state or {}
        m = self.env.mount_of(me)
        needs = [rq.need("mounted", bool(m), "%s is not riding anything." % c["name"])]
        if not m:
            return needs
        gm = self.sim.gm_rules
        needs += [rq.need("a controlled mount", self.mode(m) == "controlled",
                          "%s is an independent mount: it acts on its own turn." % self.name(m)),
                  rq.need("the mount able", not self.sim.down(m) and not (gm and gm.incapacitated(m)),
                          "%s can't act (down or Incapacitated)." % self.name(m)),
                  rq.need("Dash, Disengage or Dodge", what in MOUNT_ACTIONS,
                          "A controlled mount can only Dash, Disengage or Dodge (SRD 5.2.1 Controlling a Mount)."),
                  rq.need("the mount's action free", not t.get("mount_action"),
                          "%s already took its action this turn (%s)." % (self.name(m), t.get("mount_action")))]
        return needs

    def mount_action(self, me, cmd):
        what = cmd.get("action")
        ready, rows = rq.check(self.mount_action_needs(me, what))
        if not ready:
            raise LayerError(rq.first_why(rows))
        t, m = self.fight.turn_state, self.env.mount_of(me)
        t["mount_action"] = what
        mc = self.sim.by_id(m)
        if what == "dash":
            extra = int(str(mc.get("speed", "30")).split()[0])
            t["movement"] += extra
            line = "Dashes: %d ft more movement for the pair" % extra
        elif what == "disengage":
            self.sim.S.addEffect(m, "Note: Disengage", True)
            t["mount_disengaged"] = m
            line = "Disengages: its movement provokes no Opportunity Attacks this turn"
        else:
            mc["dodging"], mc["mount_dodge_by"] = True, me
            line = "Dodges: attacks against it have Disadvantage until %s's next turn" % self.name(me)
        self.sim.say("turn", "%s (controlled by %s) %s" % (mc["name"], self.name(me), line))
        return {"ok": True, "result": "mount_action", "action": what}

    def mount_consent(self, me, cmd):
        """GM 2026-10-25 (ruling M2): a player character lets others ride it (or stops); free, on its own sheet."""
        c = self.sim.by_id(me)
        if not c.get("pc"):
            raise LayerError("Only a player's character says whether others may ride it.")
        if self.env.rider_of(me) is not None and not cmd.get("on"):
            raise LayerError("%s carries %s now: the rider dismounts first." % (c["name"], self.name(self.env.rider_of(me))))
        c["lets_ride"] = bool(cmd.get("on"))
        self.sim.say("turn", "%s %s" % (c["name"], "lets others ride on its back" if c["lets_ride"] else "no longer lets others ride it"))
        return {"ok": True, "result": "mount_consent", "on": c["lets_ride"]}

    def mount_offers(self, me):
        c = self.sim.by_id(me)
        m = self.env.mount_of(me)
        out = {"riding": m, "mode": self.mode(m) if m else None, "half_ft": self.half_speed(me), "candidates": []}
        if c.get("pc"):
            out["consent"] = {"on": bool(c.get("lets_ride"))}    # GM 2026-10-25 (ruling M2)
        if m:
            ready, rows = rq.check(self.dismount_needs(me))
            out["dismount"] = {"ready": ready, "why": rq.first_why(rows), "squares": self.dismount_squares(me)}
            out["own_movement"] = self.own_movement(me)
            out["actions"] = []
            for what in MOUNT_ACTIONS:
                ready, rows = rq.check(self.mount_action_needs(me, what))
                out["actions"].append({"action": what, "ready": ready, "why": rq.first_why(rows)})
            return out
        for o in self.sim.sc["combatants"]:
            if o["id"] == me or o.get("side") != c.get("side") or self.sim.down(o["id"]):
                continue
            if self.party.dist(me, o["id"]) > 5.01:
                continue                                         # the creatures within 5 ft: a button each, or why not
            ready, rows = rq.check(self.mount_needs(me, o["id"]))
            out["candidates"].append({"target": o["id"], "name": o["name"], "ready": ready, "why": rq.first_why(rows),
                                      "link": rq.first_link(rows),
                                      "mode": o.get("mount_mode") or default_mode(o)})
        return out

    def follow_at(self, me, f, x, y):
        """Where a follower goes when the rider steps to square (x, y): its mount keeps its offset (a Large mount's centre
        is half a square from its rider's square)."""
        if f == self.env.mount_of(me):
            off = self.sim.by_id(me).get("mount_offset") or (0, 0)
            return x + off[0], y + off[1]
        return x, y

    def ride_blocked(self, me):
        """A rider walks only on a controlled mount that can move; an independent mount moves on its own turn."""
        m = self.env.mount_of(me)
        if m and self.mode(m) != "controlled":
            return "%s rides %s, an independent mount: it moves on its own turn. Dismount to walk." % (self.name(me), self.name(m))
        if m and (self.sim.down(m) or (self.sim.gm_rules and self.sim.gm_rules.incapacitated(m))):
            return "%s can't move: dismount to walk." % self.name(m)
        return None

    def on_step(self, name, x0, y0, x1, y1):
        """Sim.token_moved: an independent mount moving on its own turn carries its rider along."""
        mover = next((o for o in self.sim.sc["combatants"] if o["name"] == name), None)
        if not mover or self.env.controlled_mount(mover["id"]):
            return
        rider = self.env.rider_of(mover["id"])
        if rider and self.fight.turn_state is None:              # the mount's own turn, not a rider walking it
            g, off = self.sim.sc.get("grid", 50), self.sim.by_id(rider).get("mount_offset") or (0, 0)
            self.sim.later.append(lambda: self.sim.S.move(rider, x1 / g - off[0], y1 / g - off[1]))
