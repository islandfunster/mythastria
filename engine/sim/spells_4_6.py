"""SPELLS-4-6-FIGHT (GM 2026-10-28: "the SRD 5.2.1 spells of levels 4, 5 and 6 that matter in a fight" as Cast buttons in
Play live instead of Ask the GM): eighteen spells, each checked before anything is spent (turn, slot, range, sight, a
Material component with a cost) and watched by the rules referee.

Protections and buffs (a mark on the creature, held as the spell's own record, so End the spell, Dispel and the Combat
Tracker see them):
  Stoneskin (4)            a willing creature you touch: Resistance to Bludgeoning, Piercing and Slashing damage;
                           Concentration, 1 hour; diamond dust worth 100+ GP, used up
  Fire Shield (4)          the caster: warm shield (Resistance to Cold) or chill shield (Resistance to Fire); a creature
                           within 5 ft that hits it with a melee attack roll takes 2d8 Fire (warm) or Cold (chill); 10
                           minutes (its light is the GM's)
  Death Ward (4)           a creature you touch: the first time it would drop to 0 Hit Points it drops to 1 instead and
                           the spell ends; 8 hours (an effect that kills without damage: the GM's)
  Freedom of Movement (4)  a willing creature you touch (+1 a slot level above 4): Difficult Terrain from spells costs it
                           nothing extra, and a spell or magical effect can't give it Paralyzed or Restrained or cut its
                           Speed; 1 hour (its Swim Speed and slipping restraints: the GM's)
  Aura of Life (4)         a 30-ft Emanation from the caster: the caster and its allies in it have Resistance to Necrotic
                           damage, and an ally at 0 Hit Points that starts its turn in it regains 1 Hit Point;
                           Concentration, 10 minutes (Hit Point maximums that can't be cut: the GM's)
  Greater Restoration (5)  a creature you touch: one of the Charmed condition, the Petrified condition, 1 Exhaustion level
                           or a cut to its Hit Point maximum ends; diamond dust worth 100+ GP, used up (curses and ability
                           scores: the GM's)
  Dispel Evil and Good (5) the caster: Celestials, Elementals, Fey, Fiends and Undead have Disadvantage on attack rolls
                           against it; Concentration, 1 minute. Break Enchantment (a Magic action, touch): a creature
                           Charmed or Frightened by such a creature is free, and the spell ends (Dismissal: the GM's)
  True Seeing (6)          a willing creature you touch: Truesight 120 ft; 1 hour; mushroom powder worth 25+ GP, used up
Movement:
  Dimension Door (4)       teleport up to 500 ft to an unoccupied square on the map (no Opportunity Attack); a willing
                           creature within 5 ft may come along to a free square within 5 ft of it
Charms (the Charmed condition read by the creatures the game plays, sim/charms.py):
  Charm Monster (4)        a creature you can see within 30 ft (+1 a slot level above 4): Wisdom save (Advantage if you
                           are fighting it) or Charmed for 1 hour, until you or your allies damage it
  Dominate Beast (4)       a Beast you can see within 60 ft / Dominate Person (5) a Humanoid: Wisdom save (Advantage if
                           you are fighting it) or Charmed while you concentrate (1 minute; longer with a higher slot); it
                           saves again each time it takes damage. The commands you give it are the GM's (Ask the GM gets
                           a request); until then it won't attack you
  Irresistible Dance (6)   a creature you can see within 30 ft: Wisdom save. Success: it dances in place until the end of
                           its next turn (Speed 0). Failure: Charmed while you concentrate (1 minute): Speed 0, Disadvantage
                           on attack rolls and Dexterity saves, Advantage on attack rolls against it; an action to collect
                           itself repeats the save (a creature the game plays spends its turn on it)
  Mass Suggestion (6)      up to twelve creatures you can see within 60 ft: Wisdom save or Charmed for 24 hours, until you
                           or your allies damage it, pursuing the suggestion (the two Suggestion's engine plays, or the GM's)
Areas on the map (the map-layers zones, sim/map_layers.py: drawn, ended with their Concentration or their time):
  Black Tentacles (4)      a 20-ft square within 90 ft: Difficult Terrain; each creature in it when it appears, and one that
                           enters it or ends its turn there, once a turn: Strength save or 3d6 Bludgeoning and Restrained
                           until the spell ends; an action and a Strength (Athletics) check frees it; Concentration, 1 minute
  Guardian of Faith (4)    a guardian on a square within 30 ft: an enemy that comes within 10 ft for the first time on a
                           turn or starts its turn there: Dexterity save, 20 Radiant, half on a success; it vanishes when it
                           has dealt 60 damage; 8 hours
  Blade Barrier (6)        a straight wall 100 ft long, 5 ft thick, within 90 ft, along the grid (a ring and a diagonal:
                           the GM's): Difficult Terrain; each creature in it when it appears, and one that enters it or
                           ends its turn there, once a turn: Dexterity save, 6d10 Force, half on a success; Concentration,
                           10 minutes (its Three-Quarters Cover: the GM's)
  Wall of Thorns (6)       a straight wall 60 ft long, 5 ft thick, within 120 ft, along the grid: it blocks sight; each
                           creature in it when it appears: Dexterity save, 7d8 Piercing, half on a success; the first time a
                           creature enters it on a turn or ends its turn there: Dexterity save, 7d8 Slashing, half on a
                           success (+1d8 each a slot level above 6); Difficult Terrain (each foot costs 4: the engine
                           charges 2); Concentration, 10 minutes

Stays the GM's, and why (sim/live_general.py GM_WHY): Polymorph (a new stat block), Compulsion (forced movement in a
direction each turn), Resilient Sphere and Globe of Invulnerability (what passes a barrier), Antilife Shell and Walls of
Force, Stone and Ice (solid walls the map doesn't change yet), the summons (Giant Insect, Conjure Elemental, Conjure Fey, Animate Objects, Arcane Hand...),
Raise Dead and Heroes' Feast (an hour's and ten minutes' casting), Telekinesis, and the utility spells.
"""
import math, re

import more_spells as ms
import requirements as rq

SUGGEST = ("Stop fighting and leave", "Stop fighting", "Something else (the GM rules)")
SPELLS = {
    "Stoneskin": dict(level=4, time="action", shape="creature", range_ft=5, touch=True, concentration=True, rounds=600,
                      appearance="physical", helps=True, willing=True,
                      rider="Resistance to Bludgeoning, Piercing and Slashing damage (diamond dust 100+ GP, used up)"),
    "Fire Shield": dict(level=4, time="action", shape="self", range_ft=0, rounds=100, appearance="fire",
                        choices=["Warm", "Chill"],
                        rider="warm: Resistance to Cold, 2d8 Fire to a melee attacker that hits; chill: Resistance to "
                              "Fire, 2d8 Cold"),
    "Death Ward": dict(level=4, time="action", shape="creature", range_ft=5, touch=True, rounds=4800, appearance="radiant",
                       helps=True, rider="the first time it would drop to 0 Hit Points, it drops to 1 instead"),
    "Freedom of Movement": dict(level=4, time="action", shape="creature", range_ft=5, touch=True, per_level=1, rounds=600,
                                appearance="air", helps=True, willing=True,
                                rider="no Paralyzed, Restrained or Speed cut from magic; spells' Difficult Terrain costs "
                                      "nothing extra"),
    "Aura of Life": dict(level=4, time="action", shape="self", range_ft=0, concentration=True, rounds=100,
                         appearance="radiant", aura_ft=30,
                         rider="30-ft aura: you and your allies resist Necrotic; an ally at 0 HP starting its turn in it "
                               "regains 1 HP"),
    "Greater Restoration": dict(level=5, time="action", shape="creature", range_ft=5, touch=True, appearance="radiant",
                                helps=True, choices=["Charmed", "Petrified", "1 Exhaustion level", "Hit Point maximum"],
                                rider="ends Charmed, Petrified, 1 Exhaustion level or a cut to the Hit Point maximum "
                                      "(diamond dust 100+ GP, used up)"),
    "Dispel Evil and Good": dict(level=5, time="action", shape="self", range_ft=0, concentration=True, rounds=10,
                                 appearance="radiant",
                                 rider="Celestials, Elementals, Fey, Fiends and Undead have Disadvantage on attack rolls "
                                       "against you; Break Enchantment ends it"),
    "True Seeing": dict(level=6, time="action", shape="creature", range_ft=5, touch=True, rounds=600, appearance="arcane",
                        helps=True, willing=True, rider="Truesight 120 ft (mushroom powder 25+ GP, used up)"),
    "Dimension Door": dict(level=4, time="action", shape="sphere", radius_ft=5, range_ft=500, appearance="arcane",
                           teleport=True, rider="teleport up to 500 ft (a willing creature within 5 ft may come along)"),
    "Charm Monster": dict(level=4, time="action", shape="creature", range_ft=30, per_level=1, rounds=600,
                          appearance="arcane", charm=True, ends_if_hurt=True,
                          rider="Wisdom save or Charmed for 1 hour, until you or your allies damage it"),
    "Dominate Beast": dict(level=4, time="action", shape="creature", range_ft=60, concentration=True, rounds=10,
                           appearance="arcane", charm=True, kind="beast", longer={5: 100, 6: 600, 7: 4800},
                           rider="Wisdom save or Charmed; it saves again when it takes damage; your commands: the GM's"),
    "Dominate Person": dict(level=5, time="action", shape="creature", range_ft=60, concentration=True, rounds=10,
                            appearance="arcane", charm=True, kind="humanoid", longer={6: 100, 7: 600, 8: 4800},
                            rider="Wisdom save or Charmed; it saves again when it takes damage; your commands: the GM's"),
    "Irresistible Dance": dict(level=6, time="action", shape="creature", range_ft=30, concentration=True, rounds=10,
                               appearance="arcane",
                               rider="Wisdom save or Charmed, dancing: Speed 0, Disadvantage on attacks and Dexterity "
                                     "saves, attacks against it have Advantage"),
    "Mass Suggestion": dict(level=6, time="action", shape="creatures", max_targets=12, range_ft=60, rounds=14400,
                            appearance="arcane", charm=True, ends_if_hurt=True, choices=list(SUGGEST),
                            rider="Wisdom save or Charmed for 24 hours, pursuing the suggestion"),
    "Black Tentacles": dict(level=4, time="action", shape="cube", size_ft=20, range_ft=90, concentration=True, rounds=10,
                            appearance="shadow", zone=dict(cube_ft=20, difficult=True, damage=("str", "3d6", "bludgeoning", False),
                                                            cond="Restrained", when=("enter", "end"), at_cast=True),
                            rider="Difficult Terrain; Strength save or 3d6 Bludgeoning and Restrained"),
    "Guardian of Faith": dict(level=4, time="action", shape="sphere", radius_ft=10, range_ft=30, rounds=4800,
                              appearance="radiant", zone=dict(near_ft=10, damage=("dex", "20", "radiant", True),
                                                               when=("enter", "start"), enemies=True, pool=60),
                              rider="an enemy within 10 ft of it: Dexterity save, 20 Radiant (half on a success); it "
                                    "vanishes after 60 damage"),
    "Blade Barrier": dict(level=6, time="action", shape="wall", length_ft=100, range_ft=90, concentration=True,
                          rounds=100, appearance="arcane", along_grid=True,
                          zone=dict(wall_ft=100, difficult=True, damage=("dex", "6d10", "force", True),
                                    when=("enter", "end"), at_cast=True),
                          rider="a wall of blades along the grid: Dexterity save, 6d10 Force (half on a success)"),
    "Wall of Thorns": dict(level=6, time="action", shape="wall", length_ft=60, range_ft=120, concentration=True,
                           rounds=100, appearance="physical", along_grid=True, upcast=True,
                           zone=dict(wall_ft=60, difficult=True, veil="heavy", damage=("dex", "7d8", "slashing", True),
                                     cast_damage=("dex", "7d8", "piercing", True), when=("enter", "end"), at_cast=True,
                                     above=6),
                           rider="a wall of thorns along the grid (blocks sight): Dexterity save, 7d8 Piercing when it "
                                 "appears, 7d8 Slashing entering it or ending a turn there"),
}
OPS = ("break_tentacles", "collect_yourself", "break_enchantment")
STONESKIN, FIRE_SHIELD, DEATH_WARD, FREE, TRUE_SEEING = "Stoneskin", "Fire Shield", "Death Ward", "Freedom of Movement", \
    "True Seeing"
AURA, DISPEL, DANCING = "Aura of Life", "Dispel Evil and Good", "Dancing"
MARKS = (STONESKIN, FIRE_SHIELD, DEATH_WARD, FREE, TRUE_SEEING, AURA, DISPEL)
OTHERWORLDLY = ("celestial", "elemental", "fey", "fiend", "undead")
DOMINATE = ("Dominate Beast", "Dominate Person")
ABILITY = {"str": "Strength", "dex": "Dexterity", "con": "Constitution", "wis": "Wisdom"}


def known(c):
    return [n for n in SPELLS if ms.has_spell(c, n)]


def of(sim):
    st = getattr(sim, "_spells_4_6", None)
    if st is None:
        st = sim._spells_4_6 = Spells46(sim)
    st.hook()
    ms.ACTIVE = sim
    return st


def gm(sim):
    return getattr(sim, "gm_rules", None)


def info(sim, t, name):
    g = gm(sim)
    return (g.cond.get(t) or {}).get(name) if g else None


def _roll(rng, expr):
    total = sum(sum(rng.randint(1, int(d)) for _ in range(int(n))) for n, d in re.findall(r"(\d+)d(\d+)", expr))
    return total + (int(expr) if expr.isdigit() else 0)


class Spells46:
    def __init__(self, sim):
        self.sim = sim
        self.cast_round = {}              # (caster, spell) -> (round cast, rounds it lasts) of a Concentration spell
        self.saved = {}                   # (zone n, creature) -> turn serial of its last save there
        self.hooked = None                # the fight state whose hooks are wrapped (sim.S)

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

    def rnd(self):
        return int(self.sim.S.round() or 0)

    def serial(self):
        return int(self.sim.S.turnSerial or 0)

    def units(self):
        return self.sim.sc.get("units", 5)

    def hook(self):
        """The fight state's own hooks, wrapped once: Resistance (Stoneskin, Fire Shield, Aura of Life), dropping to 0 Hit
        Points (Death Ward), a melee hit (Fire Shield's flames)."""
        S = self.sim.S
        if self.hooked is S:
            return
        self.hooked = S
        resist, fort = getattr(S, "extraResist", None), getattr(S, "fortitude", None)
        S.extraResist = lambda tid: " ".join(x for x in (resist(tid) if resist else "", self.extra_resist(tid)) if x)
        S.fortitude = lambda tid, dmg, radiant, crit: self.ward(tid) or (fort(tid, dmg, radiant, crit) if fort else False)
        S.attackPostResolve.append(self.after_attack)

    # ------------------------------------------------------------------ the cards
    def most(self, name, lv):
        s = SPELLS[name]
        return s.get("max_targets", 1) + s.get("per_level", 0) * max(0, lv - s["level"])

    def needs(self, me, name, slot=None, time=None):
        s = SPELLS[name]
        out = ms.cast_needs(self.fight, me, name, s["level"], time or s["time"], slot)
        if self.fight and (self.fight.turn_state or {}).get("id") == me:
            comp = self.component(me, name)
            if comp:
                out.append(comp[0])
        return out

    def component(self, me, name):
        """A Material component with a cost at hand (diamond dust, mushroom powder), as the general caster reads it."""
        import live_general, spell_rules
        r = spell_rules.spell(name)
        return live_general.of(self.fight).component(me, {"name": name, "components": r["components"]})

    def check_target(self, me, name, s, tid):
        sim, party = self.sim, self.party
        o = sim.by_id(tid)
        if o is None or not any(c["id"] == tid for c in sim.sc["combatants"]):
            raise ms.EffectError("Choose a creature for %s." % name)
        if sim.down(tid) and name != "Greater Restoration":
            raise ms.EffectError("%s is down." % o["name"])
        if s.get("willing") and tid != me and party.side(tid) != party.side(me):
            raise ms.EffectError("%s takes a willing creature: %s is not one (a foe)." % (name, o["name"]))
        if (s.get("charm") or name == "Irresistible Dance") and tid == me:
            raise ms.EffectError("%s takes another creature." % name)
        if s.get("kind") and s["kind"] not in str(o.get("type", "")).lower():
            raise ms.EffectError("%s takes a %s; %s is not one." % (name, s["kind"].capitalize(), o["name"]))
        held = {"Stoneskin": STONESKIN, "Death Ward": DEATH_WARD, "Freedom of Movement": FREE, "True Seeing": TRUE_SEEING}.get(name)
        if held and info(sim, tid, held):
            raise ms.EffectError("%s already has %s." % (o["name"], name))
        if s.get("charm") and (info(sim, tid, "Charmed") or {}).get("by") == me:
            raise ms.EffectError("%s is already Charmed by %s." % (o["name"], self.name(me)))
        ms.in_range(self.fight, me, tid, s["range_ft"], name, sight=not s.get("touch"))
        return o

    def offers(self, me):
        import live_spells
        c, out = self.sim.by_id(me), []
        pool = live_spells.slots_of(self.party, me)
        for name in known(c):
            s = dict(SPELLS[name])
            s.pop("zone", None)
            top = max([lv for lv in range(s["level"], len(pool) + 1) if pool[lv - 1] > 0] or [s["level"]])
            most = self.most(name, top)
            if s["shape"] == "creature" and most > 1:
                s.update(shape="creatures", max_targets=most)
            elif s["shape"] == "creatures":
                s["max_targets"] = most
            more = {k: True for k in ("helps", "teleport", "along_grid") if s.get(k)}
            if s.get("choices"):
                more["choices"] = list(s["choices"])
            e = ms.card(self.fight, me, name, s, self.needs(me, name), **more)
            if e["ready"] and s["shape"] in ("creature", "creatures"):
                e["targets"], e["refused"] = ms.targets_of(self.fight, me, lambda t: self.check_target(me, name, s, t))
            if SPELLS[name].get("zone"):
                e["zone"] = s["rider"]
            if c.get("metamagic"):
                import live_sorcery
                e["metamagic"] = live_sorcery.of(self.fight).options(me, name, self.meta_entry(name))
            out.append(e)
        return out

    @staticmethod
    def meta_entry(name):
        """The fields Metamagic reads (sim/live_sorcery.py): its time, range, Concentration, a save it forces."""
        s = SPELLS[name]
        z = s.get("zone") or {}
        save = bool(s.get("charm") or z or name == "Irresistible Dance")
        return dict({k: v for k, v in s.items() if k != "zone"}, save=save, twin=bool(s.get("per_level")) and s.get("charm"),
                    kind=(z.get("damage") or (None, None, None))[2])

    # ------------------------------------------------------------------ casting
    def cast(self, me, cmd):
        name = cmd["spell"]
        fight, party, sim = self.fight, self.party, self.sim
        s, plan = ms.metamagic(fight, me, name, self.meta_entry(name), cmd)   # Quickened, Distant, Extended, Subtle
        ms.check(self.needs(me, name, cmd.get("slot"), s["time"]))
        c = sim.by_id(me)
        spec = SPELLS[name]
        if spec.get("zone"):
            return self.zone_cast(me, c, name, s, plan, cmd)
        if name == "Dimension Door":
            return self.door(me, c, s, plan, cmd)
        choice = None
        if spec.get("choices"):
            choice = cmd.get("choice") or spec["choices"][0]
            if choice not in spec["choices"]:
                raise ms.EffectError("%s: choose one of %s." % (name, ", ".join(spec["choices"])))
        if spec["shape"] == "self":
            tids = [me]
            if name == "Fire Shield" and info(sim, me, FIRE_SHIELD):
                raise ms.EffectError("%s already has Fire Shield." % c["name"])
        else:
            tids = cmd.get("targets") or ([cmd["target"]] if cmd.get("target") is not None else [])
            tids = [t for t in tids if t is not None]
            twin = 1 if plan and plan.get("twin") else 0
            if not cmd.get("slot"):                              # the lowest slot that takes this many creatures
                cmd = dict(cmd, slot=self.lowest_slot(me, name, len(tids) - twin))
            lv_now = max(spec["level"], int(cmd["slot"]))
            most = self.most(name, lv_now) + twin
            if not tids:
                raise ms.EffectError("Choose a creature for %s." % name)
            if len(set(tids)) != len(tids):
                raise ms.EffectError("Each creature once.")
            if len(tids) > most:
                raise ms.EffectError("%s takes %s with a level %d slot." % (name, "one creature" if most == 1 else
                                                                          "up to %d creatures" % most, lv_now))
            for t in tids:
                self.check_target(me, name, s, t)
            if name == "Greater Restoration":
                self.restorable(tids[0], choice)
        comp = self.component(me, name)                         # diamond dust, mushroom powder: used up
        dis = []
        if (plan or {}).get("heighten"):
            import live_sorcery
            dis = live_sorcery.of(fight).heightened(me, tids, cmd)
        lv = ms.spend(fight, me, s["time"], spec["level"], cmd.get("slot"))
        ms.pay_metamagic(fight, me, name, plan, heightened=dis)
        if comp and comp[1][1]:
            bag, have = comp[1]
            bag.take(have[0]["item"], 1, "%s's %s" % (c["name"], name))
        if spec.get("concentration"):
            party.start_concentration(me, name)
            longer = [r for k, r in sorted((spec.get("longer") or {}).items()) if lv >= k]   # Dominate: a higher slot
            rounds = longer[-1] if longer else spec["rounds"]
            rounds *= 2 if plan and "Extended Spell" in plan["metas"] else 1
            self.cast_round[(me, name)] = (self.rnd(), rounds)
        fn = getattr(self, re.sub(r"\W+", "_", name.lower()))
        held = fn(me, c, tids, lv, dis, choice)
        if spec.get("concentration"):
            if held:
                party.control[me] = {"spell": name, "targets": set(held)}
            else:
                party.holds_no_one(me, name, "affects no one")
            ms.extended(fight, me, name, plan)
        e = {"spell": name, "appearance": spec["appearance"], "from": list(party.pos(me)), "targets": list(tids)}
        x, y = party.pos(tids[0])
        e.update(shape="circle", origin=[x, y], radius_ft=spec.get("aura_ft", 5))
        if len(tids) > 1:
            e["_cmd"] = {"targets": list(tids)}
        return e

    def lowest_slot(self, me, name, n):
        import live_spells
        pool = live_spells.slots_of(self.party, me)
        lv = SPELLS[name]["level"]
        return next((k for k in range(lv, len(pool) + 1) if pool[k - 1] > 0 and self.most(name, k) >= n), lv)

    def lasting(self, me, name):
        """The record's end for a spell without Concentration (gm_rules.tick ends it at the start of the caster's turn)."""
        return self.rnd() + SPELLS[name]["rounds"]

    # ---- protections and buffs
    def stoneskin(self, me, c, tids, lv, dis, choice):
        t = tids[0]
        self.sim.say("dice", "%s casts Stoneskin on %s (a level %d slot, Concentration; the diamond dust is used up): "
                     "Resistance to Bludgeoning, Piercing and Slashing damage" % (c["name"], self.name(t), lv))
        gm(self.sim).add(t, STONESKIN, "(%s's Stoneskin: Resistance to Bludgeoning, Piercing, Slashing)" % c["name"],
                         by=me, spell="Stoneskin")
        return tids

    def fire_shield(self, me, c, tids, lv, dis, choice):
        kind, resist = ("fire", "cold") if choice == "Warm" else ("cold", "fire")
        self.sim.say("dice", "%s casts Fire Shield (a level %d slot): a %s shield, Resistance to %s damage; a melee hit "
                     "from within 5 ft costs the attacker 2d8 %s" % (c["name"], lv, choice.lower(), resist.capitalize(),
                                                                     kind.capitalize()))
        gm(self.sim).add(me, FIRE_SHIELD, "(%s shield: Resistance to %s)" % (choice, resist.capitalize()), by=me,
                         spell="Fire Shield", kind=kind, resist=resist, expires=self.lasting(me, "Fire Shield"))
        return tids

    def death_ward(self, me, c, tids, lv, dis, choice):
        t = tids[0]
        self.sim.say("dice", "%s casts Death Ward on %s (a level %d slot): the first drop to 0 Hit Points is 1 instead" % (
            c["name"], self.name(t), lv))
        gm(self.sim).add(t, DEATH_WARD, "(%s's Death Ward)" % c["name"], by=me, spell="Death Ward",
                         expires=self.lasting(me, "Death Ward"))
        return tids

    def freedom_of_movement(self, me, c, tids, lv, dis, choice):
        g = gm(self.sim)
        self.sim.say("dice", "%s casts Freedom of Movement on %s (a level %d slot)" % (
            c["name"], ", ".join(self.name(t) for t in tids), lv))
        for t in tids:
            g.add(t, FREE, "(%s's Freedom of Movement)" % c["name"], by=me, spell="Freedom of Movement",
                  expires=self.lasting(me, "Freedom of Movement"))
            for cond in ("Paralyzed", "Restrained", "Slowed"):
                self.free(t, cond)
        return tids

    def aura_of_life(self, me, c, tids, lv, dis, choice):
        self.sim.say("dice", "%s casts Aura of Life (a level %d slot, Concentration): a 30-ft aura, Resistance to Necrotic "
                     "damage; an ally at 0 Hit Points starting its turn in it regains 1" % (c["name"], lv))
        gm(self.sim).add(me, AURA, "(Aura of Life, 30 ft)", by=me, spell="Aura of Life")
        return [me]

    def greater_restoration(self, me, c, tids, lv, dis, choice):
        t, sim, g = tids[0], self.sim, gm(self.sim)
        sim.say("dice", "%s casts Greater Restoration on %s (a level %d slot; the diamond dust is used up): %s" % (
            c["name"], self.name(t), lv, choice))
        if choice in ("Charmed", "Petrified"):
            g.remove(t, choice, "Greater Restoration")
        elif choice == "1 Exhaustion level":
            env = self.env
            n = env.exhaustion.get(t, 0) if env else 0
            if n:
                env.exhaustion[t] = n - 1
                if not env.exhaustion[t]:
                    env.exhaustion.pop(t)
            sim.say("dice", "%s's Exhaustion: level %d" % (self.name(t), max(0, n - 1)))
        else:
            S, o = sim.S, sim.by_id(t)
            top = int(o.get("hp_max") or o.get("hp") or 0)
            if top > int(S.state(t)[1] or 0):
                S.setField(t, "hptotal", top)
                sim.say("dice", "%s's Hit Point maximum is %d again" % (self.name(t), top))
        return tids

    def restorable(self, t, choice):
        """Greater Restoration ends one effect: one the creature has."""
        sim = self.sim
        if choice in ("Charmed", "Petrified"):
            ok = bool(info(sim, t, choice))
        elif choice == "1 Exhaustion level":
            ok = bool(self.env and self.env.exhaustion.get(t))
        else:
            o = sim.by_id(t)
            ok = int(o.get("hp_max") or o.get("hp") or 0) > int(sim.S.state(t)[1] or 0)
        if not ok:
            raise ms.EffectError("%s has no %s to end." % (self.name(t), "cut to its Hit Point maximum" if choice ==
                                                           "Hit Point maximum" else choice if choice[0] == "1" else
                                                           "%s condition" % choice))

    def dispel_evil_and_good(self, me, c, tids, lv, dis, choice):
        self.sim.say("dice", "%s casts Dispel Evil and Good (a level %d slot, Concentration): Celestials, Elementals, Fey, "
                     "Fiends and Undead have Disadvantage on attack rolls against %s" % (c["name"], lv, c["name"]))
        gm(self.sim).add(me, DISPEL, "(Dispel Evil and Good)", by=me, spell="Dispel Evil and Good")
        return [me]

    def true_seeing(self, me, c, tids, lv, dis, choice):
        t = tids[0]
        o = self.sim.by_id(t)
        self.sim.say("dice", "%s casts True Seeing on %s (a level %d slot; the mushroom powder is used up): Truesight "
                     "120 ft" % (c["name"], self.name(t), lv))
        gm(self.sim).add(t, TRUE_SEEING, "(%s's True Seeing: Truesight 120 ft)" % c["name"], by=me, spell="True Seeing",
                         senses=o.get("senses"), expires=self.lasting(me, "True Seeing"))
        return tids

    # ---- charms
    def charm_save(self, me, c, t, name, dc, dis):
        """Wisdom save or Charmed; Advantage when the caster is fighting it (a foe in this fight). True: Charmed."""
        g, party = gm(self.sim), self.party
        if g.cond_immune(t, "Charmed"):
            self.sim.say("dice", "%s is immune to the Charmed condition" % self.name(t))
            return False
        adv = SPELLS[name].get("charm") and party.side(t) != party.side(me)
        hd = "Heightened Spell" if t in dis else False
        return not g.condition_save(t, "wis", dc, name, charm=True, adv="you are fighting it" if adv else False, dis=hd)

    def charm_monster(self, me, c, tids, lv, dis, choice):
        dc, g = self.party.spell_dc(c), gm(self.sim)
        self.sim.say("dice", "%s casts Charm Monster (a level %d slot): DC %d Wisdom save for %s" % (
            c["name"], lv, dc, ", ".join(self.name(t) for t in tids)))
        for t in tids:
            if self.charm_save(me, c, t, "Charm Monster", dc, dis):
                g.add(t, "Charmed", "(%s's Charm Monster)" % c["name"], by=me, spell="Charm Monster", save="wis", dc=dc,
                      ends_if_hurt_by=self.party.side(me), expires=self.lasting(me, "Charm Monster"))
        return tids

    def dominate(self, me, c, tids, lv, dis, name):
        t, dc, g = tids[0], self.party.spell_dc(c), gm(self.sim)
        self.sim.say("dice", "%s casts %s (a level %d slot, Concentration): DC %d Wisdom save for %s" % (
            c["name"], name, lv, dc, self.name(t)))
        if not self.charm_save(me, c, t, name, dc, dis):
            return []
        g.add(t, "Charmed", "(%s's %s: it obeys %s's commands)" % (c["name"], name, c["name"]), by=me, spell=name,
              save="wis", dc=dc, dominated=True)
        if self.fight is not None:
            n = self.fight.add_ask(me, c["name"], "spell", name, [t], "the GM plays the commands %s gives the Charmed %s "
                                   "(no action; it does its best to obey on its turn; a Reaction costs %s's own)" % (
                                       c["name"], self.name(t), c["name"]))
            self.sim.say("turn", "%s: the GM plays %s's commands to %s (request %d); it won't attack %s" % (
                name, c["name"], self.name(t), n, c["name"]))
        return [t]

    def dominate_beast(self, me, c, tids, lv, dis, choice):
        return self.dominate(me, c, tids, lv, dis, "Dominate Beast")

    def dominate_person(self, me, c, tids, lv, dis, choice):
        return self.dominate(me, c, tids, lv, dis, "Dominate Person")

    def irresistible_dance(self, me, c, tids, lv, dis, choice):
        t, dc, g = tids[0], self.party.spell_dc(c), gm(self.sim)
        self.sim.say("dice", "%s casts Irresistible Dance (a level %d slot, Concentration): DC %d Wisdom save for %s" % (
            c["name"], lv, dc, self.name(t)))
        if g.cond_immune(t, "Charmed"):
            self.sim.say("dice", "%s is immune to the Charmed condition" % self.name(t))
            return []
        if g.condition_save(t, "wis", dc, "Irresistible Dance", charm=True, dis="Heightened Spell" if t in dis else False):
            g.add(t, "Slowed", "(%s's Irresistible Dance: it dances in place until the end of its next turn)" % c["name"],
                  by=me, ft=999, ends=999, lib=True, dance=True, until={"who": "target", "when": "end"})
            return []
        g.add(t, "Charmed", "(%s's Irresistible Dance: it dances)" % c["name"], by=me, spell="Irresistible Dance",
              save="wis", dc=dc)
        g.add(t, DANCING, "(Speed 0; Disadvantage on attack rolls and Dexterity saves; attacks against it have Advantage)",
              by=me, spell="Irresistible Dance")
        g.add(t, "Slowed", "(dancing in place: Speed 0)", by=me, spell="Irresistible Dance", ft=999, ends=999, dance=True)
        return [t]

    def mass_suggestion(self, me, c, tids, lv, dis, choice):
        dc, g, party = self.party.spell_dc(c), gm(self.sim), self.party
        self.sim.say("dice", "%s casts Mass Suggestion (a level %d slot): DC %d Wisdom save for %s: \"%s\"" % (
            c["name"], lv, dc, ", ".join(self.name(t) for t in tids), choice))
        held = []
        for t in tids:
            if (g.cond.get(t) or {}).get("Deafened"):
                self.sim.say("dice", "%s can't hear the suggestion (Deafened)" % self.name(t))
                continue
            if self.charm_save(me, c, t, "Mass Suggestion", dc, dis):
                g.add(t, "Charmed", "(%s's Mass Suggestion: \"%s\")" % (c["name"], choice), by=me, spell="Mass Suggestion",
                      save="wis", dc=dc, ends_if_hurt_by=party.side(me), suggestion=choice,
                      expires=self.lasting(me, "Mass Suggestion"))
                held.append(t)
        if held and choice in SUGGEST[:2]:
            self.sim.say("turn", "Mass Suggestion: %s %s Charmed: on %s turns %s will %s" % (
                ", ".join(self.name(t) for t in held), "is" if len(held) == 1 else "are", "its" if len(held) == 1 else
                "their", "it" if len(held) == 1 else "they", choice.lower()))
        elif held and self.fight is not None:
            n = self.fight.add_ask(me, c["name"], "spell", "Mass Suggestion", held, "the GM rules the suggestion the "
                                   "Charmed %s pursue" % ", ".join(self.name(t) for t in held))
            self.sim.say("turn", "Mass Suggestion: the GM rules the course of activity (request %d)" % n)
        return held

    # ---- Dimension Door
    def door(self, me, c, s, plan, cmd):
        sim, party = self.sim, self.party
        x, y = ms.square(cmd, "Dimension Door")
        here = tuple(int(round(v)) for v in party.pos(me))
        if (x, y) == here:
            raise ms.EffectError("Choose another square to teleport to.")
        far = max(abs(x - here[0]), abs(y - here[1])) * self.units()
        if far > s["range_ft"] + 0.01:
            raise ms.EffectError("That square is %d ft away: out of Dimension Door's range (500 ft)." % far)
        import sim_messages
        board = sim_messages.map_part(sim.sc)
        free = lambda q: 0 <= q[0] < board["cols"] and 0 <= q[1] < board["rows"] and q not in sim.occupied_cells(me)
        if not free((x, y)):
            raise ms.EffectError("That square is off the map or occupied: Dimension Door takes an unoccupied space.")
        friend, spot = cmd.get("target"), None
        if friend is not None and friend != me:
            o = sim.by_id(friend)
            if o is None or party.side(friend) != party.side(me) or sim.down(friend):
                raise ms.EffectError("Dimension Door takes along one willing creature of your side.")
            if party.dist(me, friend) > 5.01:
                raise ms.EffectError("%s is not within 5 ft of %s." % (o["name"], c["name"]))
            taken = set(sim.occupied_cells(friend)) | {(x, y)}
            spot = next(((x + dx, y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1))
                         if 0 <= x + dx < board["cols"] and 0 <= y + dy < board["rows"] and (x + dx, y + dy) not in taken
                         and (x + dx, y + dy) not in sim.occupied_cells(me) and not party.walled((x, y), (x + dx, y + dy))), None)
            if spot is None:
                raise ms.EffectError("No free square within 5 ft of that one for %s." % o["name"])
        lv = ms.spend(self.fight, me, s["time"], s["level"], cmd.get("slot"))
        ms.pay_metamagic(self.fight, me, "Dimension Door", plan)
        S = sim.S                                                # a teleport provokes no Opportunity Attack
        for who, (qx, qy) in [(me, (x, y))] + ([(friend, spot)] if spot else []):
            S.addEffect(who, "Note: Disengage", True)
            try:
                S.move(who, qx, qy)
            finally:
                S.removeEffect(who, "Note: Disengage")
        sim.settle()
        sim.say("dice", "%s casts Dimension Door (a level %d slot): teleports to (%d, %d)%s" % (
            c["name"], lv, x, y, ", %s with them to (%d, %d)" % (self.name(friend), spot[0], spot[1]) if spot else ""))
        return {"spell": "Dimension Door", "appearance": "arcane", "from": list(here), "shape": "circle", "origin": [x, y],
                "radius_ft": 5, "targets": [me] + ([friend] if spot else [])}

    # ------------------------------------------------------------------ the areas
    def zones(self):
        import map_layers
        return [z for z in self.env.zones if z.get("spells_4_6") and map_layers.alive(self.env, z)]

    def wall_squares(self, me, x, y, length_ft):
        """A straight wall centred on (x, y), across the caster's view of it, along the grid (the page's wallOf)."""
        here = self.party.pos(me)
        a = (math.atan2(y - here[1], x - here[0]) + math.pi / 2) / (math.pi / 2)
        k = 2 * math.floor(a + 0.5) if (x, y) != tuple(here) else 0   # as JavaScript's Math.round on the page
        sx, sy = round(math.cos(k * math.pi / 4)), round(math.sin(k * math.pi / 4))
        n = int(length_ft // self.units())
        return [(x + (j - n // 2) * sx, y + (j - n // 2) * sy) for j in range(n)], (sx, sy)

    def make(self, me, name, x, y, lv):
        spec, party, c = SPELLS[name], self.party, self.sim.by_id(me)
        zs = spec["zone"]
        layers = getattr(self.sim, "layers", None)
        if layers is not None:
            layers.n += 1
            n = layers.n
        else:
            n = max([int(z.get("n") or 0) for z in self.env.zones] + [0]) + 1
        z = {"id": "%s-%d" % (name.lower().replace(" ", "-"), n), "n": n, "spell": name, "owner": me, "spells_4_6": True,
             "origin": [x, y], "appearance": spec["appearance"], "layer": "air" if zs.get("veil") else "ground",
             "darkness": False, "stinking": False, "cast_round": self.rnd(), "ends_round": self.rnd() + spec["rounds"],
             "dc": party.spell_dc(c), "slot": lv, "kind": "obscured" if zs.get("veil") else "spell_area",
             "level": zs.get("veil") or "none", "veil": zs.get("veil") or "none", "lasting": not spec.get("concentration"),
             "dealt": 0}
        u = self.units()
        if zs.get("cube_ft"):                                    # as the page aims it: the square up-left of the middle
            k = zs["cube_ft"] // u
            x0, y0 = x + 1 - math.ceil(k / 2), y + 1 - math.ceil(k / 2)
            z.update(rect=[x0, y0, x0 + k - 1, y0 + k - 1], cube=[x0 - 0.5, y0 - 0.5, x0 + k - 0.5, y0 + k - 0.5],
                     size_ft=zs["cube_ft"], radius_ft=zs["cube_ft"] / 2)
        elif zs.get("wall_ft"):
            squares, toward = self.wall_squares(me, x, y, zs["wall_ft"])
            xs, ys = [q[0] for q in squares], [q[1] for q in squares]
            z.update(rect=[min(xs), min(ys), max(xs), max(ys)], cube=[min(xs) - 0.5, min(ys) - 0.5, max(xs) + 0.5, max(ys) + 0.5],
                     squares=[list(q) for q in squares], toward=list(toward), radius_ft=zs["wall_ft"] / 2)
        else:
            r = zs["near_ft"] / u
            z.update(rect=[x - int(r), y - int(r), x + int(r), y + int(r)], radius_ft=zs["near_ft"] + u / 2.0)
        if spec.get("concentration"):
            party.__dict__.setdefault("gm_concentration", {})[me] = name
            party.__dict__.setdefault("layer_zone", {})[me] = n
        self.env.zones.append(z)
        return z

    def inside(self, z, p):
        x1, y1, x2, y2 = z["rect"]                               # every shape here is its rect: a square, a wall along
        return x1 - 0.01 <= p[0] <= x2 + 0.01 and y1 - 0.01 <= p[1] <= y2 + 0.01   # the grid, 10 ft round a guardian

    def cells(self, z):
        x1, y1, x2, y2 = z["rect"]
        return {(x, y) for x in range(int(x1), int(x2) + 1) for y in range(int(y1), int(y2) + 1)}

    def creatures_in(self, z):
        sim = self.sim
        return [o["id"] for o in sim.sc["combatants"] if not sim.down(o["id"]) and self.inside(z, self.party.pos(o["id"]))
                and not (SPELLS[z["spell"]]["zone"].get("enemies") and not self.enemy(z, o["id"]))]

    def enemy(self, z, t):
        return t != z["owner"] and self.party.side(t) != self.party.side(z["owner"])

    def zone_cast(self, me, c, name, s, plan, cmd):
        fight, sim, party = self.fight, self.sim, self.party
        spec, zs = SPELLS[name], SPELLS[name]["zone"]
        x, y = ms.square(cmd, name)
        ms.point_in_range(fight, me, x, y, s["range_ft"], name)
        if name == "Guardian of Faith" and (x, y) in set(sim.occupied_cells(me)) | {tuple(int(round(v)) for v in party.pos(me))}:
            raise ms.EffectError("The guardian appears in an unoccupied space: that square is taken.")
        if name == "Guardian of Faith" and not sim.sees_square(me, x, y):
            raise ms.EffectError("%s can't see that square: the guardian appears in a space you can see." % c["name"])
        lv = ms.spend(fight, me, s["time"], spec["level"], cmd.get("slot"))
        if spec.get("concentration"):
            party.start_concentration(me, name)
            if getattr(sim, "layers", None) is not None:
                sim.layers.sweep()                               # the zone of the spell it ended leaves the map now
        z = self.make(me, name, x, y, lv)
        inside = self.creatures_in(z)
        import live_sorcery                                      # Metamagic: who it spares, who saves at Disadvantage
        sorc, meta = live_sorcery.of(fight), plan or {}
        careful = sorc.careful(me, inside, cmd) if meta.get("careful") else []
        z["dis"] = sorc.heightened(me, inside, cmd) if meta.get("heighten") else []
        z["dmg_kind"] = meta.get("kind")                        # Transmuted Spell
        ms.pay_metamagic(fight, me, name, plan, careful=careful, heightened=z["dis"])
        sim.say("turn", "%s casts %s (a level %d slot%s) on square (%d, %d): %s%s" % (
            c["name"], name, lv, ", Concentration" if spec.get("concentration") else "", x, y, spec["rider"],
            "; inside: " + ", ".join(self.name(i) for i in inside) if inside else ""))
        if zs.get("at_cast"):
            for t in inside:
                self.once(z, t)
                if t in careful:
                    sim.say("dice", "%s succeeds on its save against %s and takes no damage (Careful Spell)" % (self.name(t), name))
                    continue
                self.zone_save(z, t, None, zs.get("cast_damage"))
        if plan and "Extended Spell" in plan["metas"]:
            z["ends_round"] += spec["rounds"]
        ms.extended(fight, me, name, plan)
        e = {"spell": name, "appearance": z["appearance"], "targets": list(inside), "lasting": True,
             "from": list(party.pos(me)), "origin": [x, y]}
        if zs.get("cube_ft") or zs.get("wall_ft"):
            x0, y0, x1, y1 = z["cube"]
            e.update(shape="rectangle", origin=[x0, (y0 + y1) / 2], angle_deg=0, length_ft=(x1 - x0) * self.units(),
                     width_ft=(y1 - y0) * self.units(), cube=list(z["cube"]), cube_origin=[(x0 + x1) / 2, (y0 + y1) / 2])
            if zs.get("wall_ft"):
                e["wall"] = list(z["squares"])
        else:
            e.update(shape="circle", radius_ft=z["radius_ft"])
        return e

    def watch(self, z, t, when):
        import contextlib
        ref = getattr(self.sim, "referee", None)
        if ref is None or when is None:
            return contextlib.nullcontext()
        return ref.watch_area(z["owner"], z["spell"], t, when, slot_level=z["slot"], origin=z["origin"])

    def once(self, z, t):
        key, now = (z["n"], t), self.serial()
        if self.saved.get(key) == now:
            return False
        self.saved[key] = now
        return True

    def zone_save(self, z, t, when, damage=None):
        """A creature's save in an area: its damage (half or none on a success) and, for the tentacles, Restrained."""
        sim, g = self.sim, gm(self.sim)
        zs = SPELLS[z["spell"]]["zone"]
        ab, dice, kind, half = damage or zs["damage"]
        kind = z.get("dmg_kind") or kind
        extra = max(0, z["slot"] - zs["above"]) if zs.get("above") else 0
        expr = "%s+%dd8" % (dice, extra) if extra else dice
        with self.watch(z, t, when):
            dmg = _roll(sim.rng, expr)
            label = "%s (%s = %d %s%s)" % (z["spell"], expr, dmg, kind.capitalize(),
                                          ", half on a success" if half else ", none on a success")
            if g.auto_fail(t, ab):
                sim.say("dice", "%s %s save against %s: fails automatically" % (self.name(t), ABILITY[ab], label))
                ok = False
            else:
                ok = g.condition_save(t, ab, z["dc"], label, dis="Heightened Spell" if t in z.get("dis", ()) else False)
            amount = (dmg // 2 if half else 0) if ok else dmg
            if zs.get("pool"):
                amount = min(amount, zs["pool"] - z["dealt"])
            if amount:
                z["dealt"] += amount
                sim.S.pcDamage(z["owner"], t, "", amount, False, kind)
                sim.settle(0.2)
            if not ok and zs.get("cond") and not sim.down(t) and not (g.cond.get(t) or {}).get(zs["cond"]) \
                    and not g.cond_immune(t, zs["cond"]):
                g.add(t, zs["cond"], "(%s's %s, until the spell ends or it breaks free)" % (self.name(z["owner"]), z["spell"]),
                      by=z["owner"], spell=z["spell"], zone=z["n"])
        if zs.get("pool") and z["dealt"] >= zs["pool"]:
            z["ended"] = "the guardian has dealt %d damage and vanishes" % zs["pool"]
            if getattr(sim, "layers", None) is not None:
                sim.layers.sweep()
            else:
                self.env.zones.remove(z)
        return ok

    def later(self, z, t, when):
        zs = SPELLS[z["spell"]]["zone"]
        if self.sim.down(t) or when not in zs["when"] or (zs.get("enemies") and not self.enemy(z, t)) or z.get("ended"):
            return
        if self.once(z, t):
            self.zone_save(z, t, when)

    def tidy(self):
        """Restrained by the tentacles ends with the spell."""
        g = gm(self.sim)
        if g is None:
            return
        live = {z["n"] for z in self.zones()}
        for t, conds in list(g.cond.items()):
            for cond, rec in list(conds.items()):
                if (rec or {}).get("spell") in SPELLS and rec.get("zone") is not None and rec["zone"] not in live:
                    g.remove(t, cond, "%s ends" % rec["spell"])

    def difficult_cells(self, me=None):
        out = set()
        for z in self.zones():
            if SPELLS[z["spell"]]["zone"].get("difficult"):
                out |= self.cells(z)                             # Wall of Thorns' 4 ft a foot: charged as 2
        return out

    def keep_off_cells(self, me):
        """Creatures the game plays keep off the areas that would harm them (not one they stand in)."""
        out, p = set(), self.party.pos(me)
        for z in self.zones():
            if self.inside(z, p) or (SPELLS[z["spell"]]["zone"].get("enemies") and not self.enemy(z, me)):
                continue
            out |= self.cells(z)
        return out

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
            if self.inside(z, b) and not self.inside(z, a):
                self.later(z, me, "enter")
            if sim.down(me):
                return

    def creature_turn_start(self, me):
        """Any creature's turn starts: the tentacles' and guardian's saves; Aura of Life lifts an ally at 0 HP; a dancer
        the game plays spends its turn collecting itself; a Concentration spell past its time ends."""
        sim = self.sim
        self.expire(me)
        self.tidy()
        if getattr(sim, "layers", None) is None:                 # the simulator alone: a zone's time
            for z in self.zones():
                if z["owner"] == me and self.rnd() >= z["ends_round"]:
                    z["ended"] = "its duration is over"
                    if not z.get("lasting"):
                        self.party.end_concentration(me)
        for z in self.zones():
            if not sim.down(me) and self.inside(z, self.party.pos(me)):
                self.later(z, me, "start")
        self.aura_lift(me)
        if info(sim, me, DANCING) and not sim.by_id(me).get("pc") and not sim.down(me):
            rec = info(sim, me, "Charmed") or {}
            g = gm(sim)
            sim.say("turn", "%s dances in place and takes its action to collect itself (Irresistible Dance)" % self.name(me))
            if g.condition_save(me, "wis", rec.get("dc", 10), "Irresistible Dance (collecting itself)"):
                g.end_one_spell_on(me, rec.get("by"), "Irresistible Dance", "it collects itself")
            return "it spent its turn dancing in place and collecting itself (Irresistible Dance)"
        return ""

    def live_turn_start(self, me):
        self.expire(me)

    def turn_ended(self, me):
        sim = self.sim
        for z in self.zones():
            if sim.down(me):
                break
            if self.inside(z, self.party.pos(me)):
                self.later(z, me, "end")
        self.tidy()

    def expire(self, me):
        """The caster's turn starts: its Concentration spell past its time ends."""
        for (caster, name), (rnd, rounds) in list(self.cast_round.items()):
            if caster != me:
                continue
            if self.party.concentrates(me) != name:
                self.cast_round.pop((caster, name), None)
                continue
            if self.rnd() >= rnd + rounds:
                self.cast_round.pop((caster, name), None)
                self.sim.say("dice", "%s's %s ends: its duration is over" % (self.name(me), name))
                self.party.end_concentration(me)

    # ------------------------------------------------------------------ what the marks change
    def auras(self):
        g = gm(self.sim)
        return [t for t, conds in (g.cond.items() if g else ()) if conds.get(AURA) and not self.sim.down(t)]

    def in_aura(self, t):
        return any(o == t or (self.party.side(o) == self.party.side(t) and self.party.dist(o, t) <= SPELLS[AURA]["aura_ft"] + 0.01)
                   for o in self.auras())

    def extra_resist(self, t):
        out = []
        if info(self.sim, t, STONESKIN):
            out.append("bludgeoning piercing slashing")
        rec = info(self.sim, t, FIRE_SHIELD)
        if rec:
            out.append(rec["resist"])
        if self.in_aura(t):
            out.append("necrotic")
        return " ".join(out)

    def aura_lift(self, t):
        """Aura of Life: "If an ally with 0 Hit Points starts its turn in the aura, that ally regains 1 Hit Point"."""
        party, sim = self.party, self.sim
        if not sim.down(t) or not sim.by_id(t).get("pc") or not self.in_aura(t) or party.deaths.get(t, {}).get("dead"):
            return
        if party.revive(t, 1):
            sim.say("dice", "%s starts its turn in the Aura of Life: regains 1 Hit Point" % self.name(t))

    def ward(self, t):
        """Death Ward: the first drop to 0 Hit Points is 1 instead, and the spell ends."""
        if not info(self.sim, t, DEATH_WARD):
            return False
        self.sim.say("dice", "%s's Death Ward: it drops to 1 Hit Point instead of 0, and the spell ends" % self.name(t))
        self.sim.later.append(lambda: gm(self.sim).remove(t, DEATH_WARD, "it saved %s from 0 Hit Points" % self.name(t)))
        return "Death Ward"

    def after_attack(self, src, tgt, res):
        """Fire Shield: a creature within 5 ft that hits the caster with a melee attack roll takes 2d8."""
        rec = info(self.sim, tgt, FIRE_SHIELD)
        la = self.sim.S.lastAttack or {}
        if not rec or res.get("sResult") not in ("hit", "crit") or la.get("ranged") or src == tgt:
            return
        if self.sim.down(src) or self.party.dist(src, tgt) > 5.01:
            return
        kind = rec["kind"]
        self.sim.say("dice", "%s's Fire Shield erupts: %s takes 2d8 %s" % (self.name(tgt), self.name(src), kind.capitalize()))
        self.sim.later.append(lambda: self.sim.S.pcDamage(tgt, src, "2d8", 0, False, kind))

    def free(self, t, cond):
        """Freedom of Movement: a spell's or magical effect's Paralyzed, Restrained or Speed cut ends at once."""
        g = gm(self.sim)
        rec = (g.cond.get(t) or {}).get(cond) if g else None
        if not rec or rec.get("dance") or not (rec.get("spell") or rec.get("zone") is not None or rec.get("magic")):
            return
        g.remove(t, cond, "Freedom of Movement")

    def condition_changed(self, t, name):
        sim, rec = self.sim, info(self.sim, t, name)
        if name in ("Paralyzed", "Restrained", "Slowed") and rec and info(sim, t, FREE):
            self.free(t, name)
        elif name == TRUE_SEEING:
            c = sim.by_id(t)
            if rec:
                c["senses"] = ", ".join(x for x in (str(c.get("senses") or ""), "Truesight 120 ft") if x)
            else:
                c["senses"] = re.sub(r",?\s*Truesight 120 ft", "", str(c.get("senses") or "")).strip(", ")
        elif name == "Charmed" and not rec:
            g = gm(sim)                                          # the dance ends with its charm
            for n in (DANCING, "Slowed"):
                r = (g.cond.get(t) or {}).get(n)
                if r and r.get("spell") == "Irresistible Dance":
                    g.remove(t, n, "the dance ends")

    def attack_mode(self, src, tgt):
        """(Advantage, Disadvantage, notes) on an attack roll: the dancer's; Dispel Evil and Good against its types."""
        adv = dis = False
        notes = []
        if info(self.sim, src, DANCING):
            dis = True; notes.append("[attacker dancing: Irresistible Dance]")
        if info(self.sim, tgt, DANCING):
            adv = True; notes.append("[target dancing: Irresistible Dance]")
        if info(self.sim, tgt, DISPEL) and any(k in str(self.sim.by_id(src).get("type", "")).lower() for k in OTHERWORLDLY):
            dis = True; notes.append("[Dispel Evil and Good]")
        return adv, dis, notes

    def save_dis(self, t, ability):
        return str(ability).startswith("dex") and bool(info(self.sim, t, DANCING))

    def ignores_difficult(self, me):
        return bool(me is not None and info(self.sim, me, FREE))

    def on_hurt(self, src, tid, amount, kinds=""):
        """Dominate Beast and Person: the target saves again each time it takes damage."""
        rec = info(self.sim, tid, "Charmed")
        if not amount or not rec or not rec.get("dominated") or self.sim.down(tid):
            return
        foe = self.party.side(tid) != self.party.side(rec["by"])
        if gm(self.sim).condition_save(tid, "wis", rec["dc"], "%s (it took damage)" % rec["spell"], charm=True,
                                       adv="you are fighting it" if foe else False):
            gm(self.sim).end_one_spell_on(tid, rec["by"], rec["spell"], "it shook off the domination")

    # ------------------------------------------------------------------ actions
    def tentacled(self, me):
        rec = info(self.sim, me, "Restrained")
        return rec if rec and rec.get("spell") == "Black Tentacles" else None

    def adjust_offers(self, me, out):
        acts = out.setdefault("actions", [])
        able = [rq.able(self.fight, me), rq.action_free(self.fight, me, "this")]
        if self.tentacled(me):
            ready, rows = rq.check(able)
            acts.append({"op": "break_tentacles", "label": "Break free of the tentacles (Strength (Athletics))",
                         "ready": ready, "why": rq.first_why(rows)})
        if info(self.sim, me, DANCING):
            ready, rows = rq.check(able)
            acts.append({"op": "collect_yourself", "label": "Collect yourself (Irresistible Dance: Wisdom save)",
                         "ready": ready, "why": rq.first_why(rows)})
        if info(self.sim, me, DISPEL):
            ready, rows = rq.check(able)
            ok, no = ms.targets_of(self.fight, me, lambda t: self.enchanted(me, t))
            acts.append({"op": "break_enchantment", "label": "Break Enchantment (Dispel Evil and Good, ends the spell)",
                         "ready": ready and bool(ok), "why": rq.first_why(rows) if not ready else
                         "" if ok else "No creature within 5 ft is Charmed or Frightened by a Celestial, Elemental, Fey, "
                                       "Fiend or Undead.", "targets": ok})

    def enchanted(self, me, t):
        """Break Enchantment: a creature within 5 ft Charmed or Frightened by one of Dispel Evil and Good's types."""
        g, sim, held = gm(self.sim), self.sim, []
        for n in ("Charmed", "Frightened"):
            by = ((g.cond.get(t) or {}).get(n) or {}).get("by")
            kind = str((sim.by_id(by) or {}).get("type", "")).lower() if by else ""
            if any(k in kind for k in OTHERWORLDLY):
                held.append(n)
        if not held:
            raise ms.EffectError("%s is not Charmed or Frightened by a Celestial, Elemental, Fey, Fiend or Undead." % self.name(t))
        if t != me and self.party.dist(me, t) > 5.01:
            raise ms.EffectError("%s is not within 5 ft (a touch)." % self.name(t))
        return held

    def act(self, me, cmd):
        op, sim, g = cmd["op"], self.sim, gm(self.sim)
        ms.check([rq.able(self.fight, me), rq.action_free(self.fight, me, "this")])
        t = self.fight.turn_state
        if op == "break_tentacles":
            rec = self.tentacled(me)
            if not rec:
                raise ms.EffectError("%s is not held by the tentacles." % self.name(me))
            t["action_used"], t["attacks_left"] = True, 0
            import live_lore
            bonus = live_lore.check_bonus(sim.by_id(me), "str", "Athletics")[0]
            dc = next((z["dc"] for z in self.env.zones if z.get("n") == rec["zone"]), 10)
            d20 = sim.rng.randint(1, 20)
            ok = d20 + bonus >= dc
            sim.say("dice", "%s tries to break free of the tentacles: Strength (Athletics) d20 %d %+d = %d vs DC %d -> %s" % (
                self.name(me), d20, bonus, d20 + bonus, dc, "free" if ok else "still held"))
            if ok:
                g.remove(me, "Restrained", "broke free")
            return {"ok": True, "result": op, "free": ok}
        if op == "collect_yourself":
            rec = info(sim, me, "Charmed") or {}
            if not info(sim, me, DANCING):
                raise ms.EffectError("%s is not dancing." % self.name(me))
            t["action_used"], t["attacks_left"] = True, 0
            ok = g.condition_save(me, "wis", rec.get("dc", 10), "Irresistible Dance (collecting itself)")
            if ok:
                g.end_one_spell_on(me, rec.get("by"), "Irresistible Dance", "%s collects itself" % self.name(me))
            return {"ok": True, "result": op, "free": ok}
        tid = cmd.get("target")
        if tid is None:
            raise ms.EffectError("Choose a creature to free.")
        held = self.enchanted(me, tid)
        t["action_used"], t["attacks_left"] = True, 0
        for n in held:
            g.remove(tid, n, "%s's Break Enchantment" % self.name(me))
        sim.say("dice", "%s uses Break Enchantment (a Magic action): %s is free; Dispel Evil and Good ends" % (
            self.name(me), self.name(tid)))
        self.party.end_concentration(me)
        return {"ok": True, "result": op}


# ---------------------------------------------------------------------- the hooks (sim/more_spells.py)
def _st(sim):
    return getattr(sim, "_spells_4_6", None)


def condition_changed(sim, t, name):
    st = _st(sim)
    if st:
        st.condition_changed(t, name)


def live_turn_start(fight, me):
    st = _st(fight.sim)
    if st:
        st.live_turn_start(me)


def creature_turn_start(sim, me):
    st = _st(sim)
    return st.creature_turn_start(me) if st else ""


def turn_ended(sim, me):
    st = _st(sim)
    if st:
        st.turn_ended(me)


def on_step(sim, name, x0, y0, x1, y1):
    st = _st(sim)
    if st:
        st.on_step(name, x0, y0, x1, y1)


def on_hurt(sim, src, tid, amount, kinds=""):
    st = _st(sim)
    if st:
        st.on_hurt(src, tid, amount, kinds)


def difficult_cells(sim, me=None):
    st = _st(sim)
    return st.difficult_cells(me) if st else set()


def keep_off_cells(sim, me):
    st = _st(sim)
    return st.keep_off_cells(me) if st else set()


def adjust_offers(fight, me, out):
    st = _st(fight.sim)
    if st:
        st.adjust_offers(me, out)


def attack_mode(sim, src, tgt):
    st = _st(sim)
    return st.attack_mode(src, tgt) if st else (False, False, [])


def save_dis(sim, t, ability):
    st = _st(sim)
    return st.save_dis(t, ability) if st else False


def ignores_difficult(sim, me):
    st = _st(sim)
    return st.ignores_difficult(me) if st else False
