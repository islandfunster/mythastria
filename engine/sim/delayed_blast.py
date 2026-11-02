"""Group 2 (GM 2026-10-27, "let's do item 3"): Delayed Blast Fireball in Play live, by SRD 5.2.1 (level 7, Action, 150 ft,
Concentration up to 1 minute).

A glowing bead at a chosen point for the duration. When the spell ends the bead explodes: each creature in a 20-foot-radius
Sphere centred there makes a Dexterity saving throw, Fire damage equal to the total accumulated damage on a failure, half on
a success. The base damage is 12d6 (+1d6 a slot level above 7) and grows by 1d6 whenever the caster's turn ends and the
spell hasn't ended. Flammable objects in the explosion start burning (a wooden door: sim/spell_doors.py after_area).

Here: the bead is kept per caster; it explodes whenever the spell ends: the caster sets it off (Set off the bead: ending
Concentration needs no action), its Concentration breaks (damage, Incapacitated, 0 HP), it casts another Concentration
spell, or the minute is over (checked at the start of the caster's turns). Metamagic: Quickened, Distant, Extended, Subtle
and Transmuted (the explosion's Fire); not Careful, Heightened or Empowered (their creatures and dice are chosen when it
explodes, later). Not played (the GM rules it, Ask the GM): a creature touching the bead (its Dexterity save; on a success
it throws the bead up to 40 feet, which explodes where it lands).
"""
import math

import more_spells as ms

NAME = "Delayed Blast Fireball"
SPELLS = {NAME: dict(level=7, time="action", range_ft=150, radius_ft=20, concentration=True, rounds=10, appearance="fire",
                     base=12)}
OPS = ("detonate",)


def known(c):
    return [n for n in SPELLS if ms.has_spell(c, n)]


def of(sim):
    st = getattr(sim, "_delayed_blast", None)
    if st is None:
        st = sim._delayed_blast = Beads(sim)
    return st


class Beads:
    def __init__(self, sim):
        self.sim = sim
        self.beads = {}                   # caster -> {"x", "y", "dice", "slot", "dc", "round", "kind", "n"}

    @property
    def fight(self):
        return self.sim.live

    @property
    def party(self):
        return self.sim.party

    def name(self, i):
        return self.sim.by_id(i)["name"]

    def round(self):
        return int(self.sim.S.round() or 0)

    # ------------------------------------------------------------------ the card
    @staticmethod
    def meta_entry(name):
        """The fields Metamagic reads (sim/live_sorcery.py): no save or area damage at the cast (see the module's text)."""
        s = SPELLS[name]
        return {"time": s["time"], "range_ft": s["range_ft"], "concentration": True, "rounds": s["rounds"], "kind": "fire",
                "save": False, "area_damage": False}

    def needs(self, me, name, slot=None):
        return ms.cast_needs(self.fight, me, name, SPELLS[name]["level"], "action", slot)

    def offers(self, me):
        c, out = self.sim.by_id(me), []
        for name in known(c):
            s = SPELLS[name]
            card = dict(s, shape="sphere", radius_ft=s["radius_ft"], upcast=True,
                        rider="a glowing bead: 12d6 Fire now, 1d6 more each time your turn ends; it explodes (Dexterity "
                              "save, half on a success) when the spell ends")
            e = ms.card(self.fight, me, name, card, self.needs(me, name))
            if c.get("metamagic"):
                import live_sorcery
                e["metamagic"] = live_sorcery.of(self.fight).options(me, name, self.meta_entry(name))
            out.append(e)
        return out

    def adjust_offers(self, me, out):
        b = self.beads.get(me)
        if b:
            out.setdefault("actions", []).append({
                "op": "detonate", "ready": True, "why": "", "time": "free",
                "label": "Set off the bead (Delayed Blast Fireball, %dd6 Fire): end Concentration" % b["dice"]})

    # ------------------------------------------------------------------ casting
    def cast(self, me, cmd):
        name = cmd["spell"]
        fight, party, sim = self.fight, self.party, self.sim
        x, y = ms.square(cmd, name)
        s, plan = ms.metamagic(fight, me, name, self.meta_entry(name), cmd)
        ms.check(ms.cast_needs(fight, me, name, SPELLS[name]["level"], s["time"], cmd.get("slot")))
        ms.point_in_range(fight, me, x, y, s["range_ft"], name)
        c = sim.by_id(me)
        lv = ms.spend(fight, me, s["time"], SPELLS[name]["level"], cmd.get("slot"))
        ms.pay_metamagic(fight, me, name, plan)
        party.start_concentration(me, name)                     # a bead it already holds explodes now
        party.__dict__.setdefault("gm_concentration", {})[me] = name
        rounds = SPELLS[name]["rounds"] * (2 if plan and "Extended Spell" in plan["metas"] else 1)
        self.beads[me] = {"x": x, "y": y, "dice": SPELLS[name]["base"] + max(0, lv - SPELLS[name]["level"]), "slot": lv,
                          "dc": party.spell_dc(c), "round": self.round(), "rounds": rounds,
                          "kind": (plan or {}).get("kind") or "fire"}
        ms.extended(fight, me, name, plan)
        b = self.beads[me]
        sim.say("turn", "%s casts %s (a level %d slot, Concentration): a glowing bead at square (%d, %d), %dd6 %s now, 1d6 "
                "more each time %s's turn ends; it explodes when the spell ends" % (
                    c["name"], name, lv, x, y, b["dice"], b["kind"].capitalize(), c["name"]))
        return {"spell": name, "appearance": "fire", "from": list(party.pos(me)), "targets": [], "lasting": True,
                "shape": "circle", "origin": [x, y], "radius_ft": 1}

    # ------------------------------------------------------------------ the explosion
    def inside(self, b):
        """Creatures (not down) in the 20-foot-radius Sphere: the nearest square of each one's space."""
        u, r = self.sim.sc.get("units", 5), SPELLS[NAME]["radius_ft"]
        out = []
        for o in self.sim.sc["combatants"]:
            i = o["id"]
            if self.sim.down(i):
                continue
            px, py = self.party.pos(i)
            n = max(1, int(self.sim.S.size_squares(i)))
            dx, dy = max(0.0, abs(px - b["x"]) - (n - 1) / 2), max(0.0, abs(py - b["y"]) - (n - 1) / 2)
            if math.hypot(dx, dy) * u <= r + 0.01:
                out.append(i)
        return out

    def explode(self, me, why):
        b = self.beads.pop(me, None)
        if not b:
            return
        sim, gm = self.sim, self.sim.gm_rules
        rng = sim.rng
        dmg = sum(rng.randint(1, 6) for _ in range(b["dice"]))
        caught = self.inside(b)
        sim.say("dice", "%s's %s explodes (%s) at square (%d, %d): DC %d Dexterity save, %dd6 = %d %s, half on a success (%s)" % (
            self.name(me), NAME, why, b["x"], b["y"], b["dc"], b["dice"], dmg, b["kind"].capitalize(),
            ", ".join(self.name(t) for t in caught) or "no creature inside"))
        for t in caught:
            if sim.down(t):
                continue
            saved = gm.condition_save(t, "dex", b["dc"], NAME)
            amount = dmg // 2 if saved else dmg
            if gm.has_evasion(t):
                amount = 0 if saved else dmg // 2
                sim.say("dice", "%s: Evasion, %s" % (self.name(t), "no damage" if saved else "half damage"))
            if amount:
                sim.S.pcDamage(me, t, "", amount, False, b["kind"])
                sim.settle(0.2)
            if b["kind"] == "fire" and not sim.down(t):
                import traps                                     # oil on a creature catches (GM 2026-10-25, T10)
                traps.of(sim).ignite_creatures([t], me, "%s's %s" % (self.name(me), NAME))
        if b["kind"] == "fire":
            import spell_doors                                   # a wooden door in it starts burning
            spell_doors.of(sim).after_area(me, NAME, {"shape": "circle", "origin": [b["x"], b["y"]],
                                                      "radius_ft": SPELLS[NAME]["radius_ft"]})

    # ------------------------------------------------------------------ the engine's moments
    def turn_ended(self, me):
        """1d6 more whenever the caster's turn ends and the spell hasn't ended."""
        b = self.beads.get(me)
        if b and self.party.concentrates(me) == NAME:
            b["dice"] += 1
            self.sim.say("dice", "%s's bead glows brighter: %dd6 now" % (self.name(me), b["dice"]))

    def turn_start(self, me):
        b = self.beads.get(me)
        if b and self.round() >= b["round"] + b["rounds"]:
            self.party.end_concentration(me)                    # the minute is over: it explodes (concentration_ended)

    def concentration_ended(self, me, spells):
        if NAME in spells and me in self.beads:
            self.explode(me, "the spell ends")

    def act(self, me, cmd):
        if me not in self.beads:
            raise ms.EffectError("%s holds no Delayed Blast Fireball." % self.name(me))
        self.party.drop_concentration(me, "the bead is set off")
        return {"ok": True, "result": "detonate"}


# ---------------------------------------------------------------------- the hooks (sim/more_spells.py)
def _st(sim):
    return getattr(sim, "_delayed_blast", None)


def turn_ended(sim, me):
    st = _st(sim)
    if st:
        st.turn_ended(me)


def creature_turn_start(sim, me):
    st = _st(sim)
    if st:
        st.turn_start(me)
    return ""


def live_turn_start(fight, me):
    st = _st(fight.sim)
    if st:
        st.turn_start(me)


def concentration_ended(sim, me, spells):
    st = _st(sim)
    if st:
        st.concentration_ended(me, spells)


def adjust_offers(fight, me, out):
    st = _st(fight.sim)
    if st:
        st.adjust_offers(me, out)
