"""LIVE-PLAY-01 slice 2 (GM 2026-10-19: "let's go ahead and merge the spells and effects"): the spells a player casts in a
live fight. Each one is checked against SRD 5.2.1 here, then resolved by the simulator's own spell code (the Party
resolve_* methods the scripted party uses too, so both play the same rules), and returns its real area for the table's
effect graphics (Isles Table effects: shape, appearance, origin in squares, angle, sizes in feet).

Checks before anything is rolled (SRD 5.2.1 "Spells", "Casting a Spell"; Rules Glossary):
- it is the caster's turn, the caster is not down and not Incapacitated;
- the spell is on the sheet (its flag, or the class list the pregens' notes give) and the character's level allows it;
- a spell slot of its level or higher is left, and no slot was spent this turn (One Spell with a Spell Slot per Turn);
- its casting time is free: the Action (shared with the Attack action) or the Bonus Action;
- range and a clear path (no wall on the way); a creature target must be seen (Hex: and its creature type when it
  matters: Hold Person, a Humanoid); Bless at most three creatures;
- a new Concentration spell ends the one the caster holds (start_concentration does that).
Areas follow the simulator's own reading: a creature counts when the centre of its square is inside, and a wall between
the area's origin and the creature shields it. Areas hit every creature inside, allies too (SRD), except Sleep, which
affects the creatures the caster chooses (here: the hostile ones), and Sculpt Spells, which spares allies.
GM 2026-10-23 (the Sorcerer): a cast may carry Metamagic (cmd["metamagic"], sim/live_sorcery.py), checked with the rest
before anything is spent; it can change the casting time, the range, the damage type, the creatures, the dice and saves.
"""
import math
import live_sorcery

FT = 5

# name -> how the spell is cast and shown. time: action / bonus. shape: creature (one target), creatures (several),
# cone (from the caster), sphere (on a point), self (an emanation). level: the slot level. flag: the sheet key (or class
# list). min_level: the character level the pregens gain it at (their at_level adds the flag; kept for the class lists).
SPELLS = {
    "Burning Hands": dict(flag="burning_hands", level=1, time="action", shape="cone", length_ft=15, appearance="fire"),
    # level 9 (2026-10-23): a cone's dice are (base + slot level) d die; its save and damage type
    "Cone of Cold": dict(flag="cone_of_cold", level=5, time="action", shape="cone", length_ft=60, appearance="frost",
                         dice=(3, 8), save=("Constitution", "con_save"), kind="cold"),
    "Sleep": dict(flag="sleep", level=1, time="action", shape="sphere", radius_ft=5, range_ft=60, appearance="arcane",
                  concentration=True),
    "Fireball": dict(flag="fireball", level=3, time="action", shape="sphere", radius_ft=20, range_ft=150, appearance="fire"),
    "Bless": dict(classes=("cleric", "paladin"), level=1, time="action", shape="creatures", max_targets=3, range_ft=30,
                  appearance="radiant", concentration=True),
    "Guiding Bolt": dict(classes=("cleric",), level=1, time="action", shape="creature", range_ft=120, appearance="radiant",
                         foe=True),
    "Healing Word": dict(classes=("cleric",), level=1, time="bonus", shape="creature", range_ft=60, appearance="healing",
                         heal=True),
    "Cure Wounds": dict(flag="cure_wounds", level=1, time="action", shape="creature", range_ft=5, appearance="healing",
                        heal=True),
    "Shield of Faith": dict(flag="shield_of_faith", level=1, time="bonus", shape="creature", range_ft=60,
                            appearance="radiant", concentration=True),
    "Spiritual Weapon": dict(flag="spiritual_weapon", level=2, time="bonus", shape="creature", range_ft=60,
                             appearance="arcane", concentration=True, foe=True),
    "Spirit Guardians": dict(flag="spirit_guardians", level=3, time="action", shape="self", radius_ft=15,
                             appearance="radiant", concentration=True),
    "Hex": dict(flag="hex", level=1, time="bonus", shape="creature", range_ft=90, appearance="shadow", concentration=True,
                foe=True),
    "Hold Person": dict(flag="hold_person", level=2, time="action", shape="creature", range_ft=60, appearance="arcane",
                        concentration=True, foe=True, humanoid=True),
    "Hold Monster": dict(flag="hold_monster", level=5, time="action", shape="creature", range_ft=90, appearance="arcane",
                         concentration=True, foe=True),
}


class SpellError(ValueError):
    pass


# GM 2026-10-28 ("also many spells like bless can be upcast"): these grow with a higher slot (SRD 5.2.1 "Using a
# Higher-Level Spell Slot"): more dice (Burning Hands, Cone of Cold, Fireball, Guiding Bolt, Healing Word, Cure Wounds,
# Spiritual Weapon, Spirit Guardians) or one more creature a level (Bless). Hold Person and Hold Monster (more creatures)
# are aimed at one creature here; Hex only lasts longer; Sleep and Shield of Faith don't grow.
UPCAST = {"Burning Hands", "Cone of Cold", "Fireball", "Bless", "Guiding Bolt", "Healing Word", "Cure Wounds",
          "Spiritual Weapon", "Spirit Guardians"}
EXTRA_TARGETS = {"Bless": 1}


def known(c):
    """The spells on this character's sheet, in the order above."""
    out, listed = [], {sp.get("name") for sp in c.get("spell_list") or [] if isinstance(sp, dict)}
    built = bool(c.get("spell_list"))                                # play-test 2026-11-02: a built sheet casts only what it lists
    for name, s in SPELLS.items():
        if name in listed and s["level"] >= 4:                       # SPELLS-4-9: Cone of Cold, Hold Monster on a sheet
            out.append(name)
        elif s.get("flag") and c.get(s["flag"]):
            out.append(name)
        elif s.get("classes") and c.get("class") in s["classes"] and (not built or name in listed):
            out.append(name)
    return out


def slots_of(party, me):
    """Slots left per level: [level 1, level 2, ...]."""
    pool = party.pools.get(me)
    return list(pool) if pool else [party.slots.get(me, 0)]


class LiveSpells:
    """Spell checks and casting for one LiveFight (its turn_state, its simulator)."""

    def __init__(self, fight):
        self.fight = fight

    @property
    def sim(self):
        return self.fight.sim

    @property
    def party(self):
        return self.fight.sim.party

    # ------------------------------------------------------------------ geometry (squares; feet = squares x 5)
    def units(self):
        return self.sim.sc.get("units", 5)

    def creatures(self):
        import high_levels                                           # CASTER-HIGH: none hurled through Hell
        return [o["id"] for o in self.sim.sc["combatants"] if not self.sim.down(o["id"])
                and not high_levels.gone(self.party, o["id"])]

    def cone_targets(self, me, aim, length_ft):
        """Everyone (not the caster) whose square's centre is in the Cone from the caster toward `aim`: within its
        length and as wide as it is far, no wall from the caster."""
        u, (hx, hy) = self.units(), self.party.pos(me)
        dx, dy = aim[0] - hx, aim[1] - hy
        n = math.hypot(dx, dy)
        if n < 1e-9:
            raise SpellError("Aim the Cone away from the caster.")
        ux, uy = dx / n, dy / n
        out = []
        for i in self.creatures():
            if i == me:
                continue
            x, y = self.party.pos(i)
            vx, vy = x - hx, y - hy
            along, across = vx * ux + vy * uy, abs(vx * uy - vy * ux)
            if 0 < along * u <= length_ft + 0.01 and across <= along / 2 + 0.01 and not self.party.walled((hx, hy), (x, y)):
                out.append(i)
        return out, math.degrees(math.atan2(uy, ux))

    def sphere_targets(self, point, radius_ft, me=None):
        u, out = self.units(), []
        for i in self.creatures():
            x, y = self.party.pos(i)
            if math.hypot(x - point[0], y - point[1]) * u <= radius_ft + 0.01 and not self.party.walled(point, (x, y)):
                out.append(i)
        return out

    # ------------------------------------------------------------------ checks
    def check_common(self, me, name, cmd=None):
        return self.prepared(me, name, cmd)[:2]

    def prepared(self, me, name, cmd=None):
        """The checks every cast makes. Returns (the spell's casting entry, as Metamagic changes it; the caster; the
        Metamagic plan or None)."""
        s = SPELLS.get(name)
        c, t, sim, party = self.sim.by_id(me), self.fight.turn_state, self.sim, self.party
        if s is None or name not in known(c):
            listed = any(isinstance(sp, dict) and sp.get("name") == name for sp in c.get("spell_list") or [])
            raise SpellError("The table doesn't play %s by itself: use Ask the GM." % name if listed
                             else "%s is not on %s's sheet." % (name, c["name"]))
        if not t or t["id"] != me:
            raise SpellError("It is not this character's turn.")
        if sim.down(me):
            raise SpellError("%s is down." % c["name"])
        if t.get("surged") and not t["action_used"] and s["time"] == "action":
            raise SpellError("Action Surge's extra action can't be the Magic action.")
        gm = getattr(sim, "gm_rules", None)
        if gm and gm.incapacitated(me):
            raise SpellError("%s is Incapacitated: no actions (SRD 5.2.1 Incapacitated)." % c["name"])
        if self.moves_hex(me, name):                                 # GM 2026-10-24: moving Hex is a Bonus Action, no slot
            if cmd and cmd.get("metamagic"):
                raise SpellError("Moving Hex to a new creature is not casting a spell: no Metamagic.")
            if not party.bonus_free(me):
                raise SpellError("%s's Bonus Action is used this turn." % c["name"])
            return s, c, None
        plan = None
        if cmd and cmd.get("metamagic"):
            try:
                s, plan = live_sorcery.of(self.fight).plan(me, name, s, cmd)
            except live_sorcery.SorceryError as e:
                raise SpellError(str(e))
        if s["level"] >= 1 and getattr(party, "quickened_turn", {}).get(me) == party.s.turnSerial:
            raise SpellError("After a Quickened Spell, no level 1+ spell this turn (SRD 5.2.1 Metamagic).")
        if s["time"] == "action" and t["action_used"]:
            raise SpellError("%s's action is used this turn." % c["name"])
        if s["time"] == "bonus" and not party.bonus_free(me):
            raise SpellError("%s's Bonus Action is used this turn." % c["name"])
        pool = slots_of(party, me)
        import high_levels                                           # CASTER-HIGH: Spell Mastery, Signature Spells,
        free = high_levels.no_slot(party, me, name, (cmd or {}).get("slot"))   # Divine Intervention: no slot
        if not free and sum(pool[s["level"] - 1:]) <= 0:
            raise SpellError("No spell slot of level %d or higher left for %s." % (s["level"], name))
        if not free and not party.slot_free(me, s["level"]):
            raise SpellError("One spell with a spell slot per turn: %s already spent a slot this turn (SRD 5.2.1)." % c["name"])
        return s, c, plan

    def check_creature(self, me, name, s, tid):
        sim, party = self.sim, self.party
        target = next((o for o in sim.sc["combatants"] if o["id"] == tid), None)
        if target is None:
            raise SpellError("Choose a creature for %s." % name)
        import high_levels                                           # CASTER-HIGH: Hurl Through Hell
        if high_levels.gone(party, tid):
            raise SpellError(high_levels.gone_why(party, tid))
        if s.get("heal") and party.deaths.get(tid, {}).get("dead"):
            raise SpellError("%s is dead: %s cannot restore life." % (target["name"], name))
        if s.get("foe") and tid == me:
            import spell_objects                                     # SPELL-OBJECTS-01, the playtester's finding 3
            raise SpellError("%s targets %s other than you." % (name, spell_objects.WORDS[spell_objects.objects(name)]))
        if sim.down(tid) and not s.get("heal"):
            raise SpellError("%s is down." % target["name"])
        if s.get("humanoid") and "humanoid" not in str(target.get("type", "")).lower():
            raise SpellError("%s affects a Humanoid; %s is not one." % (name, target["name"]))
        if tid != me:
            dist = party.dist(me, tid)
            if dist > s["range_ft"] + 0.01:
                raise SpellError("%s is %d ft away: out of %s's range (%d ft)." % (target["name"], round(dist), name, s["range_ft"]))
            if party.blocked(me, tid):
                raise SpellError("A wall blocks the line to %s." % target["name"])
            if s["range_ft"] > FT and not sim.sees(me, tid):
                raise SpellError("%s cannot see %s." % (self.sim.by_id(me)["name"], target["name"]))
        return target

    def check_point(self, me, name, s, x, y):
        here, u = self.party.pos(me), self.units()
        if max(abs(x - here[0]), abs(y - here[1])) * u > s["range_ft"] + 0.01:
            raise SpellError("That point is out of %s's range (%d ft)." % (name, s["range_ft"]))
        if self.party.walled(here, (x, y)):
            raise SpellError("A wall blocks the way to that point.")

    # ------------------------------------------------------------------ casting
    def cast(self, me, cmd):
        name = cmd.get("spell")
        import invisibility
        if name == invisibility.SPELL:                               # INVISIBILITY-01 (sim/invisibility.py)
            try:
                return invisibility.of(self.fight).cast(me, cmd)
            except invisibility.InvisibilityError as e:
                raise SpellError(str(e))
        import more_spells, spell_doors                              # SPELL-EFFECTS-01: Haste, Slow, summons, zones, charms
        if cmd.get("door") is not None or cmd.get("object") is not None:   # SPELL-OBJECTS-01: at a door or a prop
            try:
                return spell_doors.of(self.sim).cast(me, cmd)
            except more_spells.EffectError as e:
                raise SpellError(str(e))
        if more_spells.owner(name):
            try:
                return more_spells.cast(self.fight, me, cmd)
            except more_spells.EffectError as e:
                raise SpellError(str(e))
        if name not in SPELLS:                                       # SPELL-CASTER-01: the general caster
            import live_general
            g = live_general.of(self.fight)
            g.last_hits = []
            try:
                effect = g.cast(me, cmd)
            except live_general.GeneralError as e:
                raise SpellError(str(e))
            spell_doors.of(self.sim).after_area(me, name, effect, g.last_hits)   # SPELL-OBJECTS-01: Shatter's doors
            return effect
        s, c, plan = self.prepared(me, name, cmd)
        party, t = self.party, self.fight.turn_state
        slot = cmd.get("slot")                                       # the Cast at level the player chose
        if slot is not None:
            pool = slots_of(party, me)
            if name not in UPCAST or not isinstance(slot, int) or isinstance(slot, bool) or slot < s["level"]:
                raise SpellError("%s can't be cast with a level %s slot here." % (name, slot))
            if slot > len(pool) or pool[slot - 1] <= 0:
                raise SpellError("No level %d spell slot left." % slot)
            party.__dict__.setdefault("upcast", {})[me] = slot
        try:
            return self._cast_old(me, cmd, name, s, c, plan, slot)
        finally:
            party.__dict__.get("upcast", {}).pop(me, None)          # a refused cast keeps no chosen slot

    def _cast_old(self, me, cmd, name, s, c, plan, slot):
        import spell_doors                                           # SPELL-OBJECTS-01: Fireball's doors
        party, t = self.party, self.fight.turn_state
        effect = {"spell": name, "appearance": s["appearance"]}
        shape = s["shape"]
        sorc, meta = live_sorcery.of(self.fight), (plan or {})
        heighten = lambda caught: sorc.heightened(me, caught, cmd) if meta.get("heighten") else []
        if meta.get("twin"):                                         # Twinned Spell: Hold Person on two Humanoids
            tids = cmd.get("targets") or [x for x in (cmd.get("target"), cmd.get("twin")) if x]
            if len(tids) != 2 or tids[0] == tids[1]:
                raise SpellError("Twinned Spell: choose two different creatures for %s." % name)
            for tid in tids:
                self.check_creature(me, name, s, tid)
            dis = heighten(tids)
            self._use_time(me, s)
            sorc.pay(me, name, plan, heightened=dis)
            party.resolve_hold_person(me, c, tids[0], more=tids[1:], dis=dis, spell=name)
            x, y = party.pos(tids[0])
            effect.update(shape="circle", origin=[x, y], radius_ft=5, targets=list(tids), from_=list(party.pos(me)))
        elif shape == "creature":
            tid = cmd.get("target")
            target = self.check_creature(me, name, s, tid)
            if self.moves_hex(me, name):                             # the referee: no slot is right for a move
                effect["_cmd"] = {"free": "moving Hex to a new creature"}
            dis = heighten([tid])
            self._use_time(me, s)
            if plan:
                sorc.pay(me, name, plan, heightened=dis)
            self._resolve_creature(me, c, name, tid, dis=dis)
            x, y = party.pos(tid)
            effect.update(shape="circle", origin=[x, y], radius_ft=5, targets=[tid], from_=list(party.pos(me)))
        elif shape == "creatures":
            tids = cmd.get("targets") or []
            most = s["max_targets"] + EXTRA_TARGETS.get(name, 0) * max(0, (slot or s["level"]) - s["level"])   # Bless upcast
            if not tids or len(tids) > most:
                raise SpellError("%s takes 1 to %d creatures (at most %d)." % (name, most, most))
            if len(set(tids)) != len(tids):
                raise SpellError("Each creature once.")
            for tid in tids:
                self.check_creature(me, name, s, tid)
            self._use_time(me, s)
            if plan:
                sorc.pay(me, name, plan)
            party.spend_slot(me, s["level"])
            party.resolve_bless(me, c, list(tids))
            effect.update(shape="circle", origin=list(party.pos(me)), radius_ft=s["range_ft"], targets=list(tids))
        elif shape == "cone":
            try:
                aim = (int(cmd["x"]), int(cmd["y"]))
            except (KeyError, TypeError, ValueError):
                raise SpellError("Aim %s at a square." % name)
            targets, angle = self.cone_targets(me, aim, s["length_ft"])
            careful = sorc.careful(me, targets, cmd) if meta.get("careful") else []
            hit = [i for i in targets if i not in careful]
            dis = heighten(hit)
            self._use_time(me, s)
            if plan:
                sorc.pay(me, name, plan, careful=careful, heightened=dis)
            level = party.spend_slot(me, s["level"])
            base, die = s.get("dice", (2, 6))
            ability, key = s.get("save", ("Dexterity", "dex_save"))
            party.area_spell(me, c, "%s (a level %d slot)" % (name, level), hit, ability, key,
                             "%dd%d" % (base + level, die), meta.get("kind") or s.get("kind", "fire"),
                             "%d-ft Cone" % s["length_ft"], dis=dis, empower=meta.get("empower", 0))
            effect.update(shape="cone", origin=list(party.pos(me)), angle_deg=angle, length_ft=s["length_ft"],
                          width_ft=s["length_ft"], targets=targets)
        elif shape == "sphere":
            try:
                pt = (int(cmd["x"]), int(cmd["y"]))
            except (KeyError, TypeError, ValueError):
                raise SpellError("Place %s on a square." % name)
            self.check_point(me, name, s, *pt)
            inside = self.sphere_targets(pt, s["radius_ft"])
            if name == "Sleep":
                gm = self.sim.gm_rules
                foes = set(party.foes(me))
                targets = [i for i in inside if i in foes and not gm.incapacitated(i)
                           and "elf" not in gm.kind(i).lower() and not gm.cond_immune(i, "exhaustion")]
                dis = heighten(targets)
                self._use_time(me, s)
                if plan:
                    sorc.pay(me, name, plan, heightened=dis)
                party.resolve_sleep(me, c, targets, dis=dis)
            else:                                                    # Fireball: everyone inside; Sculpt Spells spares allies
                level_hint = s["level"]
                allies = [i for i in inside if i in set([me] + party.allies(me))]
                spare = allies[:1 + level_hint] if c.get("sculpt_spells") and me not in allies else []
                why = "Sculpt Spells"
                if meta.get("careful"):                              # Careful Spell (Metamagic)
                    spare, why = sorc.careful(me, inside, cmd), "Careful Spell"
                targets = [i for i in inside if i not in spare]
                dis = heighten(targets)
                self._use_time(me, s)
                if plan:
                    sorc.pay(me, name, plan, careful=spare if why == "Careful Spell" else (), heightened=dis)
                party.resolve_fireball(me, c, pt, targets, spare, kind=meta.get("kind") or "fire", dis=dis,
                                       empower=meta.get("empower", 0), spare_why=why)
            effect.update(shape="circle", origin=list(pt), radius_ft=s["radius_ft"], targets=targets)
        elif shape == "self":
            self._use_time(me, s)
            if plan:
                sorc.pay(me, name, plan)
            party.resolve_guardians(me, c)
            effect.update(shape="circle", origin=list(party.pos(me)), radius_ft=s["radius_ft"], targets=[me], aura=True)
        else:
            raise SpellError("Not something this table can cast yet.")
        if "Extended Spell" in meta.get("metas", ()) and party.concentrates(me) == name:
            party.__dict__.setdefault("extended", {})[me] = name     # Advantage on the saves to keep it
        effect["from"] = effect.pop("from_", list(party.pos(me)))
        if shape in ("sphere", "cone"):                              # SPELL-OBJECTS-01: Fireball, Burning Hands light
            spell_doors.of(self.sim).after_area(me, name, effect)    # a wooden door in the area
        return effect

    def _use_time(self, me, s):
        t = self.fight.turn_state
        if s["time"] == "action":
            t["action_used"], t["attacks_left"] = True, 0
        else:
            self.party.use_bonus(me)

    def _resolve_creature(self, me, c, name, tid, dis=()):
        party = self.party
        if name == "Healing Word":
            party.healing_word(me, c, [tid])                         # spends the slot and the Bonus Action itself
            return
        if name == "Cure Wounds":
            party.resolve_cure_wounds(me, c, tid)
            return
        if name == "Shield of Faith":
            party.bonus_turn.pop(me, None)                           # resolve_shield_of_faith uses the Bonus Action itself
            party.resolve_shield_of_faith(me, c, tid)
            return
        if name == "Guiding Bolt":
            level = party.spend_slot(me, 1)
            party.resolve_guiding_bolt(me, c, tid, level=level)
            return
        if name == "Hex" and self.moves_hex(me, name):
            self.sim.say("dice", "%s moves Hex to %s (Bonus Action, no spell slot): +1d6 Necrotic on each hit" % (
                c["name"], party.name(tid)))
            party.hex[me] = tid
            return
        if name == "Hex":
            party.resolve_hex(me, c, tid)
            party.hex[me] = tid
            return
        if name in ("Hold Person", "Hold Monster"):
            party.resolve_hold_person(me, c, tid, dis=dis, spell=name)
            return
        if name == "Spiritual Weapon":
            party.resolve_spiritual_weapon(me, c, tid)
            return
        raise SpellError("Not something this table can cast yet.")

    # ------------------------------------------------------------------ what the sheet shows
    def offers(self, me):
        c, party = self.sim.by_id(me), self.party
        out = []
        for name in known(c):
            s = SPELLS[name]
            entry = {"name": name, "level": s["level"], "time": s["time"], "shape": s["shape"], "appearance": s["appearance"],
                     "range_ft": s.get("range_ft", 0), "concentration": bool(s.get("concentration")),
                     "objects": __import__("spell_objects").objects(name)}     # SPELL-OBJECTS-01
            for k in ("length_ft", "radius_ft", "max_targets"):
                if k in s:
                    entry[k] = s[k]
            if name in UPCAST:                                       # the Cast at levels: every slot left at its level or up
                pool = slots_of(party, me)
                entry["upcast"] = True
                entry["slots_ok"] = [i + 1 for i, n in enumerate(pool) if i + 1 >= s["level"] and n > 0]
                if name in EXTRA_TARGETS:
                    entry["extra_targets_per_level"] = EXTRA_TARGETS[name]
            try:
                self.check_common(me, name)
                entry["ready"], entry["why"] = True, ""
            except SpellError as e:
                entry["ready"], entry["why"] = False, str(e)
            if self.moves_hex(me, name):                             # the card says: Move Hex, a Bonus Action, no slot
                entry["moves"] = "Move Hex to a new creature (Bonus Action, no spell slot)"
            if s["shape"] in ("creature", "creatures") and entry["ready"]:
                ok, no = [], {}
                for o in self.sim.sc["combatants"]:
                    try:
                        self.check_creature(me, name, s, o["id"])
                        ok.append(o["id"])
                    except SpellError as e:
                        no[o["id"]] = str(e)
                entry["targets"], entry["refused"] = ok, no
            if c.get("metamagic"):                                   # GM 2026-10-23: the Metamagic this card can take
                entry["metamagic"] = live_sorcery.of(self.fight).options(me, name, s)
                far = next((m for m in entry["metamagic"] if m["name"] == "Distant Spell" and m["ready"]), None)
                if far and s["shape"] == "creature" and entry["ready"]:
                    longer = dict(s, range_ft=far["range_ft"])
                    entry["distant_targets"] = [o["id"] for o in self.sim.sc["combatants"] if self._fits(me, name, longer, o["id"])]
            out.append(entry)
        import live_general, invisibility, more_spells, spell_doors  # SPELL-CASTER-01: the rest the engine casts
        out = out + live_general.of(self.fight).offers(me) + invisibility.of(self.fight).offers(me) +             more_spells.offers(self.fight, me)                       # SPELL-EFFECTS-01
        import high_levels                                           # CASTER-HIGH: no slot, Overchannel, Divine Intervention
        out = [high_levels.card(party, me, e, lambda e: self.divine_recheck(me, e)) if e.get("general") or e.get("name") in SPELLS
               else e for e in out]
        doors = spell_doors.of(self.sim)                             # SPELL-OBJECTS-01: the doors each card may target
        return [e if e.get("shape") == "door" else doors.mark_card(me, e) for e in out]

    def divine_recheck(self, me, e):
        """CASTER-HIGH: a card greyed for want of a slot or a Material component, checked again while Divine Intervention
        is armed for it (high_levels.card): its ready flag and creatures, or None."""
        import live_general, requirements as rq
        name, out, ok, no = e["name"], {"ready": True, "why": ""}, [], {}
        if e.get("general"):
            g = live_general.of(self.fight)
            if not rq.check(g.needs(me, name)[0])[0]:
                return None
            p = live_general.plan(name)
            if p["shape"] != "creature":
                return out
            for o in self.sim.sc["combatants"]:
                try:
                    g.check_target(me, p, o["id"]); ok.append(o["id"])
                except live_general.GeneralError as err:
                    no[o["id"]] = str(err)
        else:
            try:
                self.check_common(me, name)
            except SpellError:
                return None
            s = SPELLS[name]
            if s["shape"] not in ("creature", "creatures"):
                return out
            for o in self.sim.sc["combatants"]:
                try:
                    self.check_creature(me, name, s, o["id"]); ok.append(o["id"])
                except SpellError as err:
                    no[o["id"]] = str(err)
        return dict(out, targets=ok, refused=no)

    def _fits(self, me, name, s, tid):
        try:
            self.check_creature(me, name, s, tid)
            return True
        except SpellError:
            return False

    def turn_start(self, me):
        """Hex (SRD 5.2.1): once its creature drops to 0 HP, the caster "can take a Bonus Action on a later turn to curse
        a new creature". A turn that starts with the cursed creature down is such a later turn; so is each one after it,
        for as long as the caster concentrates (GM 2026-10-24)."""
        party = self.party
        cursed = party.hex.get(me, False)
        free = self.__dict__.setdefault("hex_free", set())
        free.discard(me)
        if cursed is not False and (cursed is None or self.sim.down(cursed)):
            free.add(me)

    def moves_hex(self, me, name):
        """Casting Hex now moves the held curse instead: Concentration on Hex, its creature down since before this turn."""
        if name != "Hex" or self.party.concentrates(me) != "Hex" or me not in self.__dict__.get("hex_free", ()):
            return False
        cursed = self.party.hex.get(me)
        return cursed is None or self.sim.down(cursed)

    def concentrating(self, me):
        party = self.party
        name = party.concentrates(me)
        if name:
            return name
        ctl = getattr(party, "control", {}).get(me)
        return ctl["spell"] if ctl else None
