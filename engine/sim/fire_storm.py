"""Group 2 (GM 2026-10-27, "let's do item 3"): Fire Storm in Play live, by SRD 5.2.1 (level 7, Action, 150 ft,
Instantaneous): up to ten 10-foot Cubes arranged as the caster likes, each contiguous with at least one other; each
creature in the area makes a Dexterity saving throw, 7d10 Fire damage on a failure, half on a success (one damage roll).
Flammable objects in it that aren't worn or carried start burning (the GM's here: the doors read circles and cones).

The table picks the Cubes like Meteor Swarm's points: each click a 10-foot Cube whose top-left square is the one clicked
(cmd "points": [[x, y], ...]); each in range (its nearest square within 150 ft), none overlapping, each touching another
along a side when there are two or more. A creature is in the area when any square of its space is; it saves once.
Metamagic: Careful, Distant, Empowered, Heightened, Quickened, Subtle, Transmuted.
"""
import re

import more_spells as ms

NAME = "Fire Storm"
SPELLS = {NAME: dict(level=7, time="action", range_ft=150, cube_ft=10, most=10, dice="7d10", appearance="fire")}


def known(c):
    return [n for n in SPELLS if ms.has_spell(c, n)]


def of(sim):
    st = getattr(sim, "_fire_storm", None)
    if st is None:
        st = sim._fire_storm = Storm(sim)
    return st


def contiguous(a, b, k):
    """Two k-square Cubes (top-left squares a and b) share a side: touching along one edge, overlapping on the other."""
    dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
    return (dx == k and dy < k) or (dy == k and dx < k)


class Storm:
    def __init__(self, sim):
        self.sim = sim

    @property
    def fight(self):
        return self.sim.live

    @property
    def party(self):
        return self.sim.party

    def name(self, i):
        return self.sim.by_id(i)["name"]

    @staticmethod
    def meta_entry(name):
        s = SPELLS[name]
        return {"time": s["time"], "range_ft": s["range_ft"], "concentration": False, "rounds": 0, "kind": "fire",
                "save": True, "area_damage": True}

    def needs(self, me, name, slot=None):
        return ms.cast_needs(self.fight, me, name, SPELLS[name]["level"], "action", slot)

    def offers(self, me):
        c, out = self.sim.by_id(me), []
        for name in known(c):
            s = SPELLS[name]
            card = dict(s, shape="cubes", size_ft=s["cube_ft"], points=s["most"], upcast=False,
                        rider="up to ten 10-ft Cubes, each touching another: Dexterity save, 7d10 Fire, half on a success")
            e = ms.card(self.fight, me, name, card, self.needs(me, name))
            e.update(shape="cubes", size_ft=s["cube_ft"], points=s["most"])   # the table picks each Cube's square
            if c.get("metamagic"):
                import live_sorcery
                e["metamagic"] = live_sorcery.of(self.fight).options(me, name, self.meta_entry(name))
            out.append(e)
        return out

    def cubes(self, me, name, pts, range_ft):
        """The Cubes checked (top-left squares), or EffectError with the reason."""
        s, k = SPELLS[name], SPELLS[name]["cube_ft"] // self.sim.sc.get("units", 5)
        if not pts:
            raise ms.EffectError("Click the squares for %s's Cubes (up to %d), then Cast." % (name, s["most"]))
        if len(pts) > s["most"]:
            raise ms.EffectError("%s has up to %d Cubes." % (name, s["most"]))
        if len(set(pts)) != len(pts):
            raise ms.EffectError("Each Cube once.")
        for i, a in enumerate(pts):
            for b in pts[i + 1:]:
                if abs(a[0] - b[0]) < k and abs(a[1] - b[1]) < k:
                    raise ms.EffectError("%s's Cubes don't overlap: (%d, %d) and (%d, %d) do." % (name, a[0], a[1], b[0], b[1]))
        if len(pts) > 1:
            for a in pts:
                if not any(contiguous(a, b, k) for b in pts if b != a):
                    raise ms.EffectError("Each Cube of %s touches another along a side: the one at (%d, %d) doesn't." % (
                        name, a[0], a[1]))
        u = self.sim.sc.get("units", 5)
        mx, my = self.party.pos(me)
        for a in pts:                                            # its nearest square within range
            nx, ny = min(max(mx, a[0]), a[0] + k - 1), min(max(my, a[1]), a[1] + k - 1)
            if max(abs(nx - mx), abs(ny - my)) * u > range_ft + 0.01:
                raise ms.EffectError("%s's Cube at (%d, %d) is out of range (%d ft)." % (name, a[0], a[1], range_ft))
        return k

    def inside(self, pts, k):
        cells = {(a[0] + i, a[1] + j) for a in pts for i in range(k) for j in range(k)}
        out = []
        for o in self.sim.sc["combatants"]:
            i = o["id"]
            if self.sim.down(i):
                continue
            px, py = self.party.pos(i)
            n = max(1, int(self.sim.S.size_squares(i)))
            lo = -(n - 1) / 2
            if any((int(round(px + lo + a)), int(round(py + lo + b))) in cells for a in range(n) for b in range(n)):
                out.append(i)
        return out

    def cast(self, me, cmd):
        name = cmd["spell"]
        fight, party, sim, gm = self.fight, self.party, self.sim, self.sim.gm_rules
        try:
            pts = [(int(q[0]), int(q[1])) for q in cmd.get("points") or []]
        except (TypeError, ValueError, IndexError):
            raise ms.EffectError("Click the squares for %s's Cubes." % name)
        s, plan = ms.metamagic(fight, me, name, self.meta_entry(name), cmd)
        ms.check(ms.cast_needs(fight, me, name, SPELLS[name]["level"], s["time"], cmd.get("slot")))
        k = self.cubes(me, name, pts, s["range_ft"])
        caught = self.inside(pts, k)
        import live_sorcery
        sorc, plan = live_sorcery.of(fight), plan or {}
        careful = sorc.careful(me, caught, cmd) if plan.get("careful") else []
        heighten = sorc.heightened(me, caught, cmd) if plan.get("heighten") else []
        c = sim.by_id(me)
        lv = ms.spend(fight, me, s["time"], SPELLS[name]["level"], cmd.get("slot"))
        ms.pay_metamagic(fight, me, name, plan or None, careful=careful, heightened=heighten)
        dc, dice = party.spell_dc(c), SPELLS[name]["dice"]
        kind = plan.get("kind") or "fire"
        if plan.get("empower"):
            import live_general
            dmg = live_general.of(fight).empowered_roll(dice, plan["empower"])
        else:
            dmg = sum(sim.rng.randint(1, int(d)) for n, d in re.findall(r"(\d+)d(\d+)", dice) for _ in range(int(n)))
        plus = party.affinity(c, kind)                           # Elemental Affinity: one damage roll
        if plus:
            sim.say("dice", "%s: Elemental Affinity, +%d %s damage" % (c["name"], plus, kind.capitalize()))
            dmg += plus
        sim.say("dice", "%s casts %s (a level %d slot): %d 10-ft Cubes, DC %d Dexterity save, %s = %d %s, half on a "
                "success (%s)" % (c["name"], name, lv, len(pts), dc, dice, dmg, kind.capitalize(),
                                  ", ".join(self.name(t) for t in caught) or "no creature inside"))
        for t in caught:
            if sim.down(t):
                continue
            if t in careful:
                sim.say("dice", "%s succeeds on its save against %s and takes no damage (Careful Spell)" % (self.name(t), name))
                continue
            saved = gm.condition_save(t, "dex", dc, name, dis="Heightened Spell" if t in heighten else False)
            amount = dmg // 2 if saved else dmg
            if gm.has_evasion(t):
                amount = 0 if saved else dmg // 2
                sim.say("dice", "%s: Evasion, %s" % (self.name(t), "no damage" if saved else "half damage"))
            if amount:
                sim.S.pcDamage(me, t, "", amount, False, kind)
                sim.settle(0.2)
            if kind == "fire" and not sim.down(t):
                import traps                                     # oil on a creature catches (GM 2026-10-25, T10)
                traps.of(sim).ignite_creatures([t], me, "%s's %s" % (c["name"], name))
        boxes = [[a[0] - 0.5, a[1] - 0.5, a[0] + k - 0.5, a[1] + k - 0.5] for a in pts]
        e = {"spell": name, "appearance": "fire", "from": list(party.pos(me)), "targets": list(caught), "shape": "rectangle",
             "origin": [boxes[0][0], (boxes[0][1] + boxes[0][3]) / 2], "angle_deg": 0, "length_ft": SPELLS[name]["cube_ft"],
             "width_ft": SPELLS[name]["cube_ft"], "cube": boxes[0], "_cmd": {"points": [list(a) for a in pts]}}
        if len(boxes) > 1:
            e["origins"] = [[b[0], (b[1] + b[3]) / 2] for b in boxes]
        return e
