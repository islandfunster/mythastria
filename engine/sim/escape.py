"""SIM-ESC-01 (2026-10-18): the escape layer for the Drowned Way test (TEST ONLY; docs/development/
DROWNED_WAY_TEST_DESIGN.md). Adventure mechanics, not SRD rules: the exposure track, air stations, gate levers, the
sluice, the dormant guardian. SRD 5.2.1 supplies the ability checks, breath, swimming, currents' forced movement.

Scenario keys: "escape": {"par_rounds", "thresholds": {"active", "chamber"}, "max_reduction", "guardian", "chamber_spot"}
and zones of kinds "exit", "air" (state working/damaged, repair_dc), "lever" (door, dc, current), "sluice_lever"
(channel), "channel"; currents carry "on"."""

ABILITY_OF = {"Athletics": "str", "Acrobatics": "dex", "Sleight of Hand": "dex", "Stealth": "dex",
              "Investigation": "int", "Arcana": "int", "Perception": "wis", "Survival": "wis", "Medicine": "wis"}


class Escape:
    def __init__(self, sim):
        self.sim = sim
        cfg = dict(sim.sc.get("escape") or {})
        self.active = bool(cfg)
        self.cfg = cfg
        th = cfg.get("thresholds") or {}
        self.t_active, self.t_chamber = int(th.get("active", 4)), int(th.get("chamber", 6))
        self.max_reduction = int(cfg.get("max_reduction", 1))
        self.exposure, self.reduced, self.keys, self.log = int(cfg.get("exposure_start", 0)), 0, set(), []
        self.guardian = cfg.get("guardian")
        self.awake = False
        self.status = {c["id"]: "inside" for c in sim.sc["combatants"] if c.get("pc")}
        self.carrying = {}             # carrier -> carried
        self.events = []               # (round, what) for the report: checks, rescues, guardian
        self.sluice_rounds = 0
        self.last_round = 0
        self.escaped_spot = 0
        self.start_x = {c["id"]: c["x"] for c in sim.sc["combatants"] if c.get("pc")}
        self.flags = set()
        self.held = {}                 # SIM-ESC-05: rounds a sluice operator has waited for the others
        self.placed = False            # SIM-ESC-05: the guardian is placed in the final chamber once
        if self.active:
            self.thresholds()                                    # a stage may start at or above a threshold
        if self.active and cfg.get("breath_start") is not None:  # SIM-ESC-03: air already spent on arrival
            for i in self.status:
                if not sim.env.breathes(i):
                    sim.env.breath[i] = int(cfg["breath_start"])
        if self.active and cfg.get("spent") and sim.party:       # SIM-ESC-03: little or no spell capacity left
            for i in self.status:
                if sim.party.slots.get(i):
                    sim.party.slots[i] = 0
                    sim.party.pools[i] = [0] * len(sim.party.pools.get(i) or [0])

    # ------------------------------------------------------------ helpers
    def zone(self, zid):
        return next((z for z in self.sim.sc.get("zones") or [] if z.get("id") == zid), None)

    def zones(self, kind):
        return [z for z in self.sim.sc.get("zones") or [] if z.get("kind") == kind]

    def inside(self, z, i):
        return self.sim.env.inside(z, self.sim.env.pos(i))

    def round(self):
        return int(self.sim.S.round())

    def note(self, what):
        self.events.append((self.round(), what))
        self.sim.say("dice", what)

    # ------------------------------------------------------------ ability checks (SRD 5.2.1)
    def check(self, i, skill, ability):
        """d20 + ability modifier + Proficiency Bonus with the skill (twice with Expertise): (total, d20)."""
        c = self.sim.by_id(i)
        score = (c.get("abilities") or {}).get(ability, 10)
        prof = 2 if (c.get("level") or 1) <= 4 else 3
        bonus = (score - 10) // 2
        if skill in (c.get("skills") or []):
            bonus += prof * (2 if skill in (c.get("expertise") or []) else 1)
        d20 = self.sim.rng.randint(1, 20)
        if c.get("reliable_talent") and skill in (c.get("skills") or []) and d20 < 10:
            d20 = 10
        return d20 + bonus, d20

    def best_check(self, i, options):
        """The better of several (skill, ability) options for this character."""
        c = self.sim.by_id(i)
        def bonus(opt):
            skill, ab = opt
            prof = 2 if (c.get("level") or 1) <= 4 else 3
            return ((c.get("abilities") or {}).get(ab, 10) - 10) // 2 + (prof if skill in (c.get("skills") or []) else 0)
        skill, ab = max(options, key=bonus)
        total, d20 = self.check(i, skill, ab)
        return total, d20, skill

    # ------------------------------------------------------------ exposure
    def raise_exposure(self, key, why):
        """+1 for a distinct noisy or delayed event (each key counts once); capped at 6, never a defeat by itself."""
        if not self.active or key in self.keys:
            return
        self.keys.add(key)
        before = self.exposure
        self.exposure = min(6, self.exposure + 1)
        self.log.append({"round": self.round(), "change": self.exposure - before, "why": why, "exposure": self.exposure})
        self.sim.say("dice", "Exposure %d/6 (+%d: %s)" % (self.exposure, self.exposure - before, why))
        self.thresholds()

    def lower(self, key, why):
        """A quiet solution: -1, at most max_reduction per stage."""
        if not self.active or key in self.keys:
            return
        self.keys.add(key)
        if self.reduced >= self.max_reduction or self.exposure <= 0:
            self.sim.say("dice", "Exposure %d/6 (quiet: %s; no change, reductions capped at %d this stage)" % (
                self.exposure, why, self.max_reduction))
            return
        self.reduced += 1
        self.exposure -= 1
        self.log.append({"round": self.round(), "change": -1, "why": why, "exposure": self.exposure})
        self.sim.say("dice", "Exposure %d/6 (-1: %s)" % (self.exposure, why))

    def thresholds(self):
        if self.guardian and not self.awake and self.exposure >= self.t_active:
            self.awake = True
            self.note("The guardian stirs (exposure %d): %s is active" % (self.exposure, self.sim.by_id(self.guardian)["name"]))
        spot = self.cfg.get("chamber_spot")
        if self.guardian and spot and self.exposure >= self.t_chamber and not self.placed and not self.sim.down(self.guardian):
            self.placed = True                                   # SIM-ESC-05: once; then it hunts from there
            g = self.sim.S
            x, y = self.sim.env.pos(self.guardian)
            if max(abs(x - spot[0]), abs(y - spot[1])) > 2:
                g.move(self.guardian, spot[0], spot[1])
                self.note("The guardian reaches the final chamber (exposure 6)")

    def dormant(self, i):
        return bool(self.active and i == self.guardian and not self.awake)

    # ------------------------------------------------------------ the turn and the round
    def round_passed(self, rnd):
        """Delays past par (par + 1, + 3, + 5) are distinct events; the outer winch runs once someone is out, when
        someone inside is in the channel (SIM-ESC-05: the helpers outside do not churn an empty channel)."""
        par = int(self.cfg.get("par_rounds", 99))
        for extra in (1, 3, 5):
            if rnd >= par + extra:
                self.raise_exposure("delay@par+%d" % extra, "the escape is taking long (round %d, par %d)" % (rnd, par))
        if any(s in ("escaped", "rescued") for s in self.status.values()):
            for z in self.zones("sluice_lever"):
                chan = self.zone(z.get("channel"))
                if chan and any(s == "inside" and self.inside(chan, i) for i, s in self.status.items()):
                    self.run_sluice(None, z["id"])

    def turn_ended(self, i):
        if not self.active:
            return
        rnd = self.round()
        if rnd != self.last_round:
            for r in range(self.last_round + 1, rnd + 1):
                if r > 1:
                    self.round_passed(r - 1)
            self.last_round = rnd
        x = self.sim.env.pos(i)[0]
        for cur in self.zones("current"):                        # a quiet solution: across without the lever
            if cur.get("on", True) and self.status.get(i) == "inside" and x > cur["rect"][2] \
                    and self.start_x.get(i, x) < cur["rect"][0]:
                self.lower("quiet:%s" % cur["id"], "%s swims across the %s without the lever" % (
                    self.sim.by_id(i)["name"], cur["id"]))
        self.start_x.setdefault(i, x)
        if self.status.get(i) == "inside" and any(self.inside(z, i) for z in self.zones("exit")):
            self.escape(i, "reaches the exit")

    def escape(self, i, why, rescued=False):
        g = self.sim.S
        self.status[i] = "rescued" if rescued else "escaped"
        carried = self.carrying.pop(i, None)
        self.escaped_spot += 1
        self.sim._offstage = True                                          # not a step: the wall audit skips it
        try:
            g.move(i, -10 - self.escaped_spot * 2, -10)                   # off the map: out of the fight
        finally:
            self.sim._offstage = False
        self.note("%s %s (%s)" % (self.sim.by_id(i)["name"], "is carried out" if rescued else "escapes", why))
        if carried is not None:
            self.escape(carried, "carried by %s" % self.sim.by_id(i)["name"], rescued=True)

    def done(self):
        """Everyone out, dead, or (for the report) left behind at 0 HP with no one able to carry them."""
        if not self.active:
            return False
        for i, s in self.status.items():
            if s != "inside":
                continue
            st = (self.sim.party.deaths.get(i) if self.sim.party else None) or {}
            if not st.get("dead"):
                return False
        return True

    def escaped_or_carried(self, i):
        return self.status.get(i) in ("escaped", "rescued") or i in self.carrying.values()

    # ------------------------------------------------------------ actions
    def repair(self, i, zid):
        """Repair a damaged air station (an action): the better of Investigation (Int) and Athletics (Str)."""
        z = self.zone(zid)
        total, d20, skill = self.best_check(i, [("Investigation", "int"), ("Athletics", "str")])
        ok = total >= int(z.get("repair_dc", 12))
        self.note("%s repairs air station %s: %s %d (d20 %d) vs DC %d -> %s" % (
            self.sim.by_id(i)["name"], zid, skill, total, d20, z.get("repair_dc", 12), "working" if ok else "fails"))
        if ok:
            z["state"] = "working"
        else:
            self.raise_exposure("repair-fail:" + zid, "a failed repair at %s clatters" % zid)
        return ok

    def operate(self, i, zid):
        """Work a gate lever (an action): Strength (Athletics) vs its DC; the gate opens and its current stops."""
        z = self.zone(zid)
        total, d20 = self.check(i, "Athletics", "str")
        ok = total >= int(z.get("dc", 13))
        self.note("%s works the lever %s: Athletics %d (d20 %d) vs DC %d -> %s" % (
            self.sim.by_id(i)["name"], zid, total, d20, z.get("dc", 13), "the gate opens" if ok else "it sticks"))
        if not ok:
            z["fails"] = z.get("fails", 0) + 1
            self.raise_exposure("lever-fail:" + zid, "the lever %s jams and bangs" % zid)
            return False
        import run_sim
        if z.get("door"):
            self.sim.set_door(run_sim.MAP, str(z["door"]), True)
        cur = self.zone(z.get("current")) if z.get("current") else None
        if cur is not None:
            cur["on"] = not cur.get("on", True)
            self.note("the current %s %s" % (cur["id"], "starts" if cur["on"] else "stops"))
        z["done"] = True
        self.raise_exposure("lever:" + zid, "the gate %s grinds open" % z.get("door", zid))
        return True

    def run_sluice(self, operator, zid):
        """The sluice (an action at its lever, or the outer winch once someone is out): every character in the channel
        is carried out. Noisy: the first round and every second round after it."""
        z = self.zone(zid)
        chan = self.zone(z.get("channel"))
        self.sluice_rounds += 1
        n = self.sluice_rounds
        if n == 1 or n % 2 == 1:
            self.raise_exposure("sluice@%d" % n, "the sluice churns (round %d of running it)" % n)
        who = self.sim.by_id(operator)["name"] if operator else "the outer winch (from outside)"
        moved = [i for i, s in self.status.items() if s == "inside" and self.inside(chan, i)]
        self.note("%s runs the sluice: %s" % (who, ", ".join(self.sim.by_id(i)["name"] for i in moved) or "no one in the channel"))
        for i in moved:
            self.escape(i, "carried out by the sluice", rescued=self.sim.down(i))

    def pick_up(self, carrier, ally):
        """Pick up an incapacitated ally next to the carrier (dragging: half Speed while carrying)."""
        if self.sim.party.dist(carrier, ally) > 5.01 or ally in self.carrying.values() or carrier in self.carrying:
            return False
        self.carrying[carrier] = ally
        self.note("%s picks up %s" % (self.sim.by_id(carrier)["name"], self.sim.by_id(ally)["name"]))
        return True

    def carried_by(self, carrier):
        return self.carrying.get(carrier)

    def separated(self, i):
        """No ally within 30 ft that it can see (inside the passage)."""
        p = self.sim.party
        others = [a for a in p.allies(i) if self.status.get(a) == "inside" and not self.sim.down(a)]
        return bool(others) and not any(p.dist(i, a) <= 30 and self.sim.sees(i, a) for a in others)

    def report(self):
        return {"exposure": self.exposure, "exposure_log": list(self.log), "status": dict(self.status),
                "events": list(self.events), "guardian_awake": self.awake}
