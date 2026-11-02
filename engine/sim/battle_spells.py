"""SPELL-BATCH-01 (GM 2026-10-28: "Make the most-used combat spells that are still GM-ruled into Cast buttons"): seven
SRD 5.2.1 spells in Play live, each checked before anything is spent and watched by the rules referee.

  Bane (1)          up to three creatures you can see within 30 ft make a Charisma save; one that fails subtracts 1d4
                    from its attack rolls and saving throws; Concentration, up to 1 minute; +1 creature per slot level
                    above 1
  Aid (2)           up to three creatures within 30 ft: Hit Point maximum and current Hit Points +5 (+5 more per slot
                    level above 2); 8 hours (the fight); a character at 0 Hit Points is back up with them
  Barkskin (2)      Bonus Action, a willing creature you touch: AC 17 if its AC is lower; 1 hour (the fight)
  Mirror Image (2)  three duplicates: each time an attack roll hits the caster, a d6 for each duplicate left, and on any
                    3 or higher a duplicate is hit instead and destroyed; an attacker Blinded or with Blindsight or
                    Truesight is unaffected; 1 minute; the spell ends with the last duplicate
  Misty Step (2)    Bonus Action: teleport up to 30 ft to an unoccupied square you can see (no Opportunity Attack)
  Fly (3)           a willing creature you touch gains a Fly Speed of 60 ft (a character: its turn's movement) and can
                    hover over drops; Concentration, up to 10 minutes; it falls when the spell ends while aloft; +1
                    creature per slot level above 3
  Revivify (3)      touch a character that died within the last minute (10 rounds): back with 1 Hit Point; a diamond
                    worth 300+ GP from the bag, used up

Each effect is a condition held as the spell's own record (gm_rules: "Baned", "Flying" by the caster's Concentration,
Party.control; "Aided", "Barkskin", "Mirror Image" lasting), so Dispel and the Combat
Tracker see them, and condition_changed puts each change on and takes it off.
Not here: a creature the game plays casting these (none of their SRD stat blocks does in Play live yet); Fly over Difficult
Terrain costs as before (the SRD exempts no flier).
"""
import re

import more_spells as ms
import requirements as rq

SPELLS = {
    "Bane": dict(level=1, time="action", shape="creatures", max_targets=3, per_level=1, range_ft=30, concentration=True,
                 appearance="shadow", rounds=10, save=("cha", "Charisma"),
                 rider="Charisma save; a target that fails subtracts 1d4 from its attack rolls and saving throws"),
    "Aid": dict(level=2, time="action", shape="creatures", max_targets=3, range_ft=30, appearance="radiant", helps=True,
                rider="Hit Point maximum and current Hit Points +5 (+5 per slot level above 2) for 8 hours"),
    "Barkskin": dict(level=2, time="bonus", shape="creature", range_ft=5, touch=True, appearance="nature", helps=True,
                     rider="AC 17 if its AC is lower, for 1 hour"),
    "Mirror Image": dict(level=2, time="action", shape="self", range_ft=0, appearance="arcane", rounds=10,
                         rider="three duplicates: a hit may strike a duplicate instead (d6 3+ for any duplicate left)"),
    "Misty Step": dict(level=2, time="bonus", shape="sphere", radius_ft=5, range_ft=30, appearance="arcane", teleport=True,
                       rider="teleport up to 30 ft to an unoccupied square you can see"),
    "Fly": dict(level=3, time="action", shape="creature", per_level=1, range_ft=5, touch=True, concentration=True,
                appearance="air", rounds=100, helps=True,
                rider="Fly Speed 60 ft, can hover; falls when the spell ends while aloft"),
    "Revivify": dict(level=3, time="action", shape="creature", range_ft=5, touch=True, appearance="radiant", helps=True,
                     cost_gp=300, rider="a character dead less than a minute comes back with 1 Hit Point (a 300+ GP diamond, used up)"),
}
BANED, AIDED, BARK, MIRROR, FLYING = "Baned", "Aided", "Barkskin", "Mirror Image", "Flying"
MINE = {BANED: "Bane", AIDED: "Aid", BARK: "Barkskin", MIRROR: "Mirror Image", FLYING: "Fly"}
FLY_FT, BARK_AC, MINUTE = 60, 17, 10


def known(c):
    return [n for n in SPELLS if ms.has_spell(c, n)]


def of(sim):
    st = getattr(sim, "_battle_spells", None)
    if st is None:
        st = sim._battle_spells = BattleSpells(sim)
    return st


def gm(sim):
    return getattr(sim, "gm_rules", None)


def info(sim, t, name):
    g = gm(sim)
    return (g.cond.get(t) or {}).get(name) if g else None


class BattleSpells:
    def __init__(self, sim):
        self.sim = sim
        self.cast_round = {}              # (caster, spell) -> (round cast, rounds it lasts)
        self.died_at = {}                 # character -> the round it was first seen dead (Revivify: within a minute)
        self.walk = {}                    # flier -> its turn's Speed before Fly (a character on its own turn)
        self.aid_hp = {}                  # creature -> the Hit Points its Aid added (taken off when Aid ends)

    @property
    def fight(self):
        return self.sim.live

    @property
    def party(self):
        return self.sim.party

    def rnd(self):
        return int(self.sim.S.round() or 0)

    def dead(self, t):
        return bool((self.party.deaths.get(t) or {}).get("dead")) if self.party else False

    def note_deaths(self):
        for c in self.sim.sc["combatants"]:
            if c.get("pc") and self.dead(c["id"]):
                self.died_at.setdefault(c["id"], self.rnd())
            else:
                self.died_at.pop(c["id"], None)

    # ------------------------------------------------------------------ the cards
    def most(self, name, lv):
        s = SPELLS[name]
        base = s.get("max_targets", 1)
        return base + s.get("per_level", 0) * max(0, lv - s["level"])

    def needs(self, me, name, slot=None, time=None):
        s = SPELLS[name]
        out = ms.cast_needs(self.fight, me, name, s["level"], time or s["time"], slot)
        if name == "Revivify" and self.fight and (self.fight.turn_state or {}).get("id") == me:
            out.append(self.diamond(me)[0])
        return out

    def diamond(self, me):
        """Revivify's component: a diamond worth 300+ GP at hand (a spellcasting focus can't stand in for it)."""
        bag = self.fight.items.bag(me)
        have = [b for b in bag.entries() if int(b.get("qty", 0)) > 0 and self.diamond_gp(b) >= SPELLS["Revivify"]["cost_gp"]]
        return rq.need("a diamond worth 300+ GP at hand", bool(have),
                       "Revivify needs a diamond worth 300+ GP; %s has none in the bag (a spellcasting focus can't stand in "
                       "for a component with a cost)." % self.sim.by_id(me)["name"], rq.LINKS["market"]), (bag, have)

    @staticmethod
    def diamond_gp(entry):
        """Its worth in GP when it is a diamond: "Diamond (300 GP)" by its name, else the Market's price."""
        name = str(entry.get("name") or entry.get("item") or "")
        if "diamond" not in name.lower():
            return 0
        m = re.search(r"(\d[\d,]*)\s*GP", name, re.I)
        if m:
            return int(m.group(1).replace(",", ""))
        try:
            import market
            item = market.load_catalog(market.CATALOG).get(entry.get("item"))
            return int(item["cost_cp"]) // 100 if item else 0
        except Exception:
            return 0

    def check_target(self, me, name, s, tid):
        sim, party = self.sim, self.party
        o = sim.by_id(tid)
        if o is None or not any(c["id"] == tid for c in sim.sc["combatants"]):
            raise ms.EffectError("Choose a creature for %s." % name)
        if name == "Revivify":
            if not o.get("pc"):
                raise ms.EffectError("Revivify here takes a character (a fallen creature's body is the GM's).")
            if not self.dead(tid):
                raise ms.EffectError("%s is not dead%s." % (o["name"], ": dying at 0 Hit Points, heal them instead"
                                                         if sim.down(tid) else ""))
            died = self.died_at.get(tid)
            if died is not None and self.rnd() - died > MINUTE:
                raise ms.EffectError("%s died more than a minute ago (round %d): too late for Revivify." % (o["name"], died))
        elif sim.down(tid) and not (name == "Aid" and o.get("pc") and not self.dead(tid)):
            raise ms.EffectError("%s is down." % o["name"])
        if name in ("Barkskin", "Fly") and tid != me and party.side(tid) != party.side(me):
            raise ms.EffectError("%s takes a willing creature: %s is not one (a foe)." % (name, o["name"]))
        if name == "Bane" and tid == me:
            raise ms.EffectError("Bane takes other creatures, not the caster.")
        held = {"Aid": AIDED, "Barkskin": BARK, "Fly": FLYING, "Bane": BANED}.get(name)
        if held and info(sim, tid, held):
            raise ms.EffectError("%s already has %s." % (o["name"], name))
        ms.in_range(self.fight, me, tid, s["range_ft"], name, sight=name not in ("Aid", "Revivify"))
        return o

    def offers(self, me):
        import live_spells
        self.note_deaths()
        c, out = self.sim.by_id(me), []
        pool = live_spells.slots_of(self.party, me)
        for name in known(c):
            s = dict(SPELLS[name])
            top = max([lv for lv in range(s["level"], len(pool) + 1) if pool[lv - 1] > 0] or [s["level"]])
            most = self.most(name, top)
            if s["shape"] == "creature" and most > 1:
                s.update(shape="creatures", max_targets=most)
            elif s["shape"] == "creatures":
                s["max_targets"] = most
            e = ms.card(self.fight, me, name, s, self.needs(me, name), **({"helps": True} if s.get("helps") else {}),
                        **({"teleport": True} if s.get("teleport") else {}))
            if e["ready"] and s["shape"] in ("creature", "creatures"):
                e["targets"], e["refused"] = ms.targets_of(self.fight, me, lambda t: self.check_target(me, name, s, t))
            if c.get("metamagic"):
                import live_sorcery
                e["metamagic"] = live_sorcery.of(self.fight).options(me, name, self.meta_entry(name))
            out.append(e)
        return out

    @staticmethod
    def meta_entry(name):
        """The fields Metamagic reads (sim/live_sorcery.py): its time, range, Concentration, a save it forces."""
        s = SPELLS[name]
        return dict(s, save=bool(s.get("save")), twin=False)

    # ------------------------------------------------------------------ casting
    def cast(self, me, cmd):
        name = cmd["spell"]
        fight, party, sim = self.fight, self.party, self.sim
        self.note_deaths()
        s, plan = ms.metamagic(fight, me, name, self.meta_entry(name), cmd)   # Quickened, Distant, Extended, Subtle
        ms.check(self.needs(me, name, cmd.get("slot"), s["time"]))
        lv_now = max(s["level"], int(cmd.get("slot") or s["level"]))
        c = sim.by_id(me)
        if name == "Mirror Image":
            return self.mirror(me, c, s, plan, cmd)
        if name == "Misty Step":
            return self.misty(me, c, s, plan, cmd)
        tids = cmd.get("targets") or ([cmd["target"]] if cmd.get("target") is not None else [])
        tids = [t for t in tids if t is not None]
        most = self.most(name, lv_now)
        if not tids:
            raise ms.EffectError("Choose a creature for %s." % name)
        if len(set(tids)) != len(tids):
            raise ms.EffectError("Each creature once.")
        if len(tids) > most:
            raise ms.EffectError("%s takes %s with a level %d slot." % (name, "one creature" if most == 1 else
                                                                      "up to %d creatures" % most, lv_now))
        for t in tids:
            self.check_target(me, name, s, t)
        comp = self.diamond(me) if name == "Revivify" else None
        dis = []
        if (plan or {}).get("heighten"):
            import live_sorcery
            dis = live_sorcery.of(fight).heightened(me, tids, cmd)
        lv = ms.spend(fight, me, s["time"], s["level"], cmd.get("slot"))
        ms.pay_metamagic(fight, me, name, plan, heightened=dis)
        if s.get("concentration"):
            party.start_concentration(me, name)
            rounds = s["rounds"] * (2 if plan and "Extended Spell" in plan["metas"] else 1)
            self.cast_round[(me, name)] = (self.rnd(), rounds)
        held = getattr(self, name.lower())(me, c, tids, lv, dis, comp)
        if s.get("concentration"):
            if held:
                party.control[me] = {"spell": name, "targets": set(held)}
            else:
                party.holds_no_one(me, name, "affects no one")
            ms.extended(fight, me, name, plan)
        return self.effect(me, name, tids)

    def effect(self, me, name, tids):
        party = self.party
        e = {"spell": name, "appearance": SPELLS[name]["appearance"], "from": list(party.pos(me)), "targets": list(tids)}
        x, y = party.pos(tids[0] if tids else me)
        e.update(shape="circle", origin=[x, y], radius_ft=5)
        return e

    def bane(self, me, c, tids, lv, dis, comp):
        sim, g, party = self.sim, gm(self.sim), self.party
        dc = party.spell_dc(c)
        sim.say("dice", "%s casts Bane (a level %d slot, Concentration): DC %d Charisma save for %s" % (
            c["name"], lv, dc, ", ".join(party.name(t) for t in tids)))
        held = []
        for t in tids:
            hd = "Heightened Spell" if t in dis else False
            if g.condition_save(t, "cha", dc, "Bane", dis=hd):
                continue
            g.add(t, BANED, "(%s's Bane: -1d4 on attack rolls and saving throws)" % c["name"], by=me, spell="Bane")
            held.append(t)
        return held

    def aid(self, me, c, tids, lv, dis, comp):
        sim, s, party = self.sim, self.sim.S, self.party
        n = 5 * (lv - 1)
        sim.say("dice", "%s casts Aid (a level %d slot): %s %s %d Hit Points, maximum and current" % (
            c["name"], lv, ", ".join(party.name(t) for t in tids), "each gain" if len(tids) > 1 else "gains", n))
        for t in tids:
            was_down = sim.down(t)
            self.max_hp(t, n)
            if was_down and not sim.down(t):                     # a character at 0 Hit Points is up again
                import party as party_mod
                party.deaths[t] = party_mod.new_death_state()
                s.setField(t, "sim_dying", 0)
                sim.say("dice", "%s is back up with %d Hit Points (Aid)" % (party.name(t), n))
            gm(sim).add(t, AIDED, "(%s's Aid: +%d Hit Point maximum)" % (c["name"], n), by=me, spell="Aid", hp=n)
        return tids

    def barkskin(self, me, c, tids, lv, dis, comp):
        t = tids[0]
        self.sim.say("dice", "%s casts Barkskin on %s (Bonus Action, a level %d slot): AC 17 if it is lower" % (
            c["name"], self.party.name(t), lv))
        gm(self.sim).add(t, BARK, "(%s's Barkskin: AC 17 if lower)" % c["name"], by=me, spell="Barkskin")
        return tids

    def fly(self, me, c, tids, lv, dis, comp):
        self.sim.say("dice", "%s casts Fly on %s (a level %d slot, Concentration): Fly Speed %d ft" % (
            c["name"], ", ".join(self.party.name(t) for t in tids), lv, FLY_FT))
        for t in tids:
            gm(self.sim).add(t, FLYING, "(%s's Fly: Fly Speed %d ft, can hover)" % (c["name"], FLY_FT), by=me, spell="Fly")
        return tids

    def revivify(self, me, c, tids, lv, dis, comp):
        sim, s, party, t = self.sim, self.sim.S, self.party, tids[0]
        bag, have = comp[1]
        bag.take(have[0]["item"], 1, "%s's Revivify" % c["name"])
        import party as party_mod
        party.deaths[t] = party_mod.new_death_state()
        s.setField(t, "sim_dying", 0)
        s.setField(t, "wounds", max(0, int(s.state(t)[1] or 0) - 1))
        self.died_at.pop(t, None)
        sim.say("dice", "%s casts Revivify on %s (a level %d slot; the %s is used up): back with 1 Hit Point" % (
            c["name"], party.name(t), lv, have[0].get("name") or "diamond"))
        return tids

    def mirror(self, me, c, s, plan, cmd):
        if info(self.sim, me, MIRROR):
            raise ms.EffectError("%s already has Mirror Image." % c["name"])
        lv = ms.spend(self.fight, me, s["time"], s["level"], cmd.get("slot"))
        ms.pay_metamagic(self.fight, me, "Mirror Image", plan)
        rounds = s["rounds"] * (2 if plan and "Extended Spell" in plan["metas"] else 1)
        self.cast_round[(me, "Mirror Image")] = (self.rnd(), rounds)
        self.sim.say("dice", "%s casts Mirror Image (a level %d slot): three illusory duplicates" % (c["name"], lv))
        gm(self.sim).add(me, MIRROR, "(three duplicates)", by=me, spell="Mirror Image", dupes=3)
        return self.effect(me, "Mirror Image", [me])

    def misty(self, me, c, s, plan, cmd):
        sim, party = self.sim, self.party
        x, y = ms.square(cmd, "Misty Step")
        here = tuple(int(round(v)) for v in party.pos(me))
        if (x, y) == here:
            raise ms.EffectError("Choose another square to teleport to.")
        ms.point_in_range(self.fight, me, x, y, s["range_ft"], "Misty Step")
        import sim_messages
        board = sim_messages.map_part(sim.sc)
        if not (0 <= x < board["cols"] and 0 <= y < board["rows"]):
            raise ms.EffectError("That square is off the map.")
        if (x, y) in sim.occupied_cells(me):
            raise ms.EffectError("That square is occupied: Misty Step takes an unoccupied space.")
        if not sim.sees_square(me, x, y):
            raise ms.EffectError("%s can't see that square: Misty Step goes to a space you can see." % c["name"])
        lv = ms.spend(self.fight, me, s["time"], s["level"], cmd.get("slot"))
        ms.pay_metamagic(self.fight, me, "Misty Step", plan)
        S = sim.S                                                # a teleport provokes no Opportunity Attack
        S.addEffect(me, "Note: Disengage", True)
        try:
            S.move(me, x, y)
        finally:
            S.removeEffect(me, "Note: Disengage")
        sim.settle()
        sim.say("dice", "%s casts Misty Step (Bonus Action, a level %d slot): teleports to (%d, %d)" % (c["name"], lv, x, y))
        return {"spell": "Misty Step", "appearance": "arcane", "from": list(here), "shape": "circle", "origin": [x, y],
                "radius_ft": 5, "targets": [me]}

    # ------------------------------------------------------------------ what the conditions change
    def condition_changed(self, t, name):
        sim, S = self.sim, self.sim.S
        rec = info(sim, t, name)
        if name == BARK:
            S.setField(t, "sim_ac_floor", BARK_AC if rec else 0)
        elif name == AIDED and rec:
            self.aid_hp[t] = rec.get("hp", 5)
        elif name == AIDED and t in self.aid_hp:                 # its maximum drops back; current Hit Points to it at most
            n = self.aid_hp.pop(t)
            S.setField(t, "wounds", max(0, int(S.state(t)[0] or 0) - n))
            sim.say("dice", "%s's Aid ends: Hit Point maximum %d" % (self.party.name(t), self.max_hp(t, -n)))
        elif name == FLYING:
            self.flight(t, bool(rec))

    def max_hp(self, t, n):
        """The Hit Point maximum up (or down) by n: the fight state's and the sheet's, which the map and the tracker show."""
        S, c = self.sim.S, self.sim.by_id(t)
        top = max(1, int(S.state(t)[1] or 0) + n)
        S.setField(t, "hptotal", top)
        c["hp"] = top
        return top

    def flight(self, t, on):
        sim = self.sim
        c, env = sim.by_id(t), getattr(sim, "env", None)
        ts = self.fight.turn_state if self.fight else None
        mine = bool(ts and ts.get("id") == t)
        if on:
            c["fly_ft"] = FLY_FT
            if mine:
                self.walk[t] = ts.get("speed", 0)
                self.fly_turn(t)
            return
        aloft = bool(env and env.aloft(t))
        c.pop("fly_ft", None)
        if mine and t in self.walk:
            base = self.walk.pop(t)
            ts["movement"] = max(0, ts["movement"] - max(0, ts.get("speed", 0) - base))
            ts["speed"] = base
        if aloft:
            z = env.drop_at(env.pos(t))
            env.fall(t, int((z or {}).get("height", 10)), "Fly ends while it is aloft")

    def fly_turn(self, t):
        """A character with Fly on its turn: its movement is the Fly Speed (60 ft; Haste doubles it, Slow halves it)."""
        import haste_slow
        ts = self.fight.turn_state
        ft = int(FLY_FT * (2 if haste_slow.hasted(self.sim, t) else 1) * (0.5 if haste_slow.slowed(self.sim, t) else 1))
        if ts.get("speed", 0) < ft:
            ts["movement"] += ft - ts.get("speed", 0)
            ts["speed"] = ft

    def attack_mod(self, src, tgt):
        if not info(self.sim, src, BANED):
            return 0, ""
        b = self.sim.rng.randint(1, 4)
        return -b, "[Bane -%d]" % b

    def save_mod(self, t, ability):
        if not info(self.sim, t, BANED):
            return 0, ""
        b = self.sim.rng.randint(1, 4)
        self.sim.say("dice", "%s is baned: -%d on the saving throw (Bane)" % (self.party.name(t), b))
        return -b, ""

    def hit_redirect(self, src, tgt):
        """Mirror Image: a hit on the caster may strike a duplicate instead."""
        rec = info(self.sim, tgt, MIRROR)
        if not rec or not rec.get("dupes"):
            return ""
        a = self.sim.by_id(src) or {}
        senses = str(a.get("senses") or "")
        g = gm(self.sim)
        if (g and (g.cond.get(src) or {}).get("Blinded")) or re.search(r"blindsight|truesight", senses, re.I):
            return ""
        rolls = [self.sim.rng.randint(1, 6) for _ in range(rec["dupes"])]
        if max(rolls) < 3:
            return ""
        rec["dupes"] -= 1
        note = "[Mirror Image: a duplicate is hit instead (d6 %s); %d left]" % (", ".join(map(str, rolls)), rec["dupes"])
        if not rec["dupes"]:
            self.sim.later.append(lambda: g.remove(tgt, MIRROR, "its last duplicate is destroyed"))
        return note

    # ------------------------------------------------------------------ turns
    def expire(self, me):
        """The caster's turn starts: its Bane past its minute ends (and its Concentration); Mirror Image too."""
        for (caster, name), (rnd, rounds) in list(self.cast_round.items()):
            if caster != me:
                continue
            if SPELLS[name].get("concentration") and self.party.concentrates(me) != name:
                self.cast_round.pop((caster, name), None)
                continue
            if self.rnd() >= rnd + rounds:
                self.cast_round.pop((caster, name), None)
                self.sim.say("dice", "%s's %s ends: its duration is over" % (self.sim.by_id(me)["name"], name))
                if SPELLS[name].get("concentration"):
                    self.party.end_concentration(me)
                elif name == "Mirror Image" and info(self.sim, me, MIRROR):
                    gm(self.sim).remove(me, MIRROR, "its minute is over")

    def live_turn_start(self, me):
        self.note_deaths()
        self.expire(me)
        if info(self.sim, me, FLYING):
            self.walk[me] = self.fight.turn_state.get("speed", 0)
            self.fly_turn(me)

    def creature_turn_start(self, me):
        self.note_deaths()
        self.expire(me)
        return ""


# ---------------------------------------------------------------------- the hooks (sim/more_spells.py)
def condition_changed(sim, t, name):
    if name in MINE:
        of(sim).condition_changed(t, name)


def live_turn_start(fight, me):
    of(fight.sim).live_turn_start(me)


def creature_turn_start(sim, me):
    return of(sim).creature_turn_start(me)


def turn_ended(sim, me):
    of(sim).note_deaths()


def save_mod(sim, t, ability):
    return of(sim).save_mod(t, ability) if getattr(sim, "_battle_spells", None) else (0, "")


def attack_mod(sim, src, tgt):
    return of(sim).attack_mod(src, tgt) if getattr(sim, "_battle_spells", None) else (0, "")


def hit_redirect(sim, src, tgt):
    return of(sim).hit_redirect(src, tgt) if getattr(sim, "_battle_spells", None) else ""
