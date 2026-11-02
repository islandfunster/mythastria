"""SPELL-EFFECTS-01 group 1 (GM 2026-10-26): Haste and Slow in Play live, by SRD 5.2.1.

Haste (level 3, Action, 30 ft, a willing creature you can see, Concentration up to 1 minute): until the spell ends the
target's Speed is doubled, it has +2 AC and Advantage on Dexterity saving throws, and on each of its turns it has one more
action, for the Attack action (one attack only), Dash, Disengage, Hide or Utilize. When the spell ends the target is
Incapacitated and has Speed 0 until the end of its next turn (the lethargy).
- A player's character: the extra action is taken by choosing Attack, Dash, Disengage or Hide once the turn's own Action
  is spent (or by sending "haste": true); the sheet marks those buttons "Haste's action". Utilize (an item) only with
  "haste": true. Speed doubles at the start of its turns (and at once when it is hasted on its own turn).
- A creature the game plays: its Speed, AC and saves change; after its own action it takes Haste's (group 1, GM
  2026-10-27): one attack at a foe it can reach, else a Dash toward one (sim/creature_turns.py extra_action).

Slow (level 3, Action, 120 ft, up to six creatures of your choice in a 40-foot Cube, Wisdom save, Concentration up to 1
minute; the save again at the end of each of its turns ends it on that creature): Speed halved, -2 AC and on Dexterity
saving throws, no Reactions; on its turns an action or a Bonus Action, not both, and one attack with the Attack action;
a spell with a Somatic component it casts fails 25 percent of the time.
- A player's character: once it uses its Action the Bonus Action is gone too (and the other way round); the Attack
  action stops after one attack; its casts with a Somatic component (attack cantrips too) roll the 25 percent.
- A creature the game plays: Speed, AC, saves and no Reactions; one attack and no Bonus Action (ai_turn.build_options).

The effects are the conditions "Hasted" and "Slow" (the spell's own records, held by the caster's Concentration as Hold
Person's Paralyzed is: Party.control); AC and Speed follow them (condition_changed), on the Combat Tracker for the
creatures the game plays.
"""
import re

import more_spells as ms
import requirements as rq

SPELLS = {
    "Haste": dict(level=3, time="action", shape="creature", range_ft=30, concentration=True, appearance="arcane",
                  rounds=10, rider="Speed doubled, +2 AC, Advantage on Dexterity saves, one more action each turn (Attack "
                  "with one attack, Dash, Disengage, Hide or Utilize); lethargy when it ends"),
    "Slow": dict(level=3, time="action", shape="creatures", max_targets=6, range_ft=120, concentration=True,
                 appearance="arcane", rounds=10, save=("wis", "Wisdom"), cube_ft=40,
                 rider="Speed halved, -2 AC and Dexterity saves, no Reactions, an action or a Bonus Action (not both), "
                 "one attack; a Somatic spell fails 25 percent of the time; Wisdom save again at the end of each of its turns"),
}
HASTE_OPS = ("attack", "dash", "disengage", "hide", "use_item", "move")
HASTED, SLOWED = "Hasted", "Slow"


def known(c):
    return [n for n in SPELLS if ms.has_spell(c, n)]


def of(sim):
    st = getattr(sim, "_haste_slow", None)
    if st is None:
        st = sim._haste_slow = HasteSlow(sim)
    return st


def gm(sim):
    return getattr(sim, "gm_rules", None)


def hasted(sim, t):
    g = gm(sim)
    return bool(g and (g.cond.get(t) or {}).get(HASTED))


def slowed(sim, t):
    g = gm(sim)
    return bool(g and (g.cond.get(t) or {}).get(SLOWED))


def lethargic(sim, t):
    g = gm(sim)
    return bool(g and ((g.cond.get(t) or {}).get("Incapacitated") or {}).get("lethargy"))


def _scaled(text, factor):
    """"30 ft., Fly 60 ft." x 2 -> "60 ft., Fly 120 ft." (halving rounds down)."""
    return re.sub(r"\d+", lambda m: str(int(int(m.group()) * factor)), str(text))


def set_ct_text(sim, cid, key, value):
    """A text field of a creature on the fight state (the Combat Tracker of the stand-in FG; FightState after
    FG-EXIT-01), which the creature turns read (its Speed)."""
    S = getattr(sim, "S", None)
    if S is not None and hasattr(S, "setValue"):
        S.setValue(cid, key, value)
        return
    sim.S.setValue(cid, key, value)                              # FG-EXIT-01: the Python fight state


class HasteSlow:
    def __init__(self, sim):
        self.sim = sim
        self.used = {}                    # hasted creature -> turn serial its Haste action was taken
        self.cast_round = {}              # caster -> (spell, round cast, rounds it lasts)
        self.base = {}                    # creature -> {"ac": ..., "speed": ...} before these spells changed them
        self.noted = set()                # (creature, turn serial): Slow's "an action or a Bonus Action" said

    @property
    def fight(self):
        return self.sim.live

    @property
    def party(self):
        return self.sim.party

    def serial(self):
        return int(self.sim.S.turnSerial or 0)

    # ------------------------------------------------------------------ the cards
    def needs(self, me, name, slot=None):
        return ms.cast_needs(self.fight, me, name, SPELLS[name]["level"], SPELLS[name]["time"], slot)

    def check_target(self, me, name, s, tid):
        sim = self.sim
        target = sim.by_id(tid)
        if target is None or not any(o["id"] == tid for o in sim.sc["combatants"]):
            raise ms.EffectError("Choose a creature for %s." % name)
        if sim.down(tid):
            raise ms.EffectError("%s is down." % target["name"])
        if name == "Haste" and tid != me and self.party.side(tid) != self.party.side(me):
            raise ms.EffectError("Haste takes a willing creature: %s is not one (a foe)." % target["name"])
        if name == "Slow" and tid == me:
            raise ms.EffectError("Slow takes other creatures, not the caster.")
        if name == "Haste" and hasted(sim, tid):
            raise ms.EffectError("%s is already hasted." % target["name"])
        ms.in_range(self.fight, me, tid, s["range_ft"], name)
        return target

    def offers(self, me):
        c, out = self.sim.by_id(me), []
        for name in known(c):
            s = SPELLS[name]
            e = ms.card(self.fight, me, name, s, self.needs(me, name), **({"helps": True} if name == "Haste" else {}))
            if e["ready"]:
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
        return dict(s, save=bool(s.get("save")))

    # ------------------------------------------------------------------ casting
    def cast(self, me, cmd):
        name = cmd["spell"]
        fight, party, sim = self.fight, self.party, self.sim
        s, plan = ms.metamagic(fight, me, name, self.meta_entry(name), cmd)   # Quickened Spell: the Bonus Action
        ms.check(ms.cast_needs(fight, me, name, s["level"], s["time"], cmd.get("slot")))
        tids = cmd.get("targets") or ([cmd["target"]] if cmd.get("target") is not None else [])
        tids = [t for t in tids if t is not None]
        most = s.get("max_targets", 1)
        if not tids:
            raise ms.EffectError("Choose a creature for %s." % name)
        if len(set(tids)) != len(tids):
            raise ms.EffectError("Each creature once.")
        if len(tids) > most:
            raise ms.EffectError("%s takes %s." % (name, "one creature" if most == 1 else "up to %d creatures" % most))
        for t in tids:
            self.check_target(me, name, s, t)
        if name == "Slow":
            self.check_cube(tids)
        c = sim.by_id(me)
        dis = []
        if (plan or {}).get("heighten"):
            import live_sorcery
            dis = live_sorcery.of(fight).heightened(me, tids, cmd)
        lv = ms.spend(fight, me, s["time"], s["level"], cmd.get("slot"))
        ms.pay_metamagic(fight, me, name, plan, heightened=dis)
        party.start_concentration(me, name)
        rounds = s["rounds"] * (2 if plan and "Extended Spell" in plan["metas"] else 1)
        self.cast_round[me] = (name, int(sim.S.round() or 0), rounds)
        if name == "Haste":
            held = self.haste(me, c, tids[0], lv)
        else:
            held = self.slow(me, c, tids, lv, dis)
        if held:
            party.control[me] = {"spell": name, "targets": set(held)}
        else:
            party.holds_no_one(me, name, "affects no one")
        ms.extended(fight, me, name, plan)
        return self.effect(me, name, tids)

    def check_cube(self, tids):
        """Slow: the creatures chosen are all inside one 40-foot Cube (8 squares a side)."""
        n = SPELLS["Slow"]["cube_ft"] // self.sim.sc.get("units", 5)
        xs = [self.party.pos(t)[0] for t in tids]
        ys = [self.party.pos(t)[1] for t in tids]
        if max(xs) - min(xs) >= n or max(ys) - min(ys) >= n:
            raise ms.EffectError("Slow takes creatures inside one 40-foot Cube: these are farther apart.")

    def effect(self, me, name, tids):
        party = self.party
        e = {"spell": name, "appearance": "arcane", "from": list(party.pos(me)), "targets": list(tids)}
        if name == "Haste":
            x, y = party.pos(tids[0])
            e.update(shape="circle", origin=[x, y], radius_ft=5)
        else:
            n = SPELLS["Slow"]["cube_ft"] // self.sim.sc.get("units", 5)
            xs, ys = [party.pos(t)[0] for t in tids], [party.pos(t)[1] for t in tids]
            x0 = min(xs) - 0.5 - (n - (max(xs) - min(xs) + 1)) // 2    # the 40-foot Cube around them, on the grid
            y0 = min(ys) - 0.5 - (n - (max(ys) - min(ys) + 1)) // 2
            box = [x0, y0, x0 + n, y0 + n]
            e.update(shape="rectangle", origin=[box[0], (box[1] + box[3]) / 2], angle_deg=0, length_ft=40, width_ft=40,
                     cube=box)
            e["_cmd"] = {"targets": list(tids)}
        return e

    def haste(self, me, c, t, lv):
        sim, g = self.sim, gm(self.sim)
        sim.say("dice", "%s casts Haste on %s (a level %d slot, Concentration): Speed doubled, +2 AC, Advantage on Dexterity "
                "saves, one more action each turn" % (c["name"], self.party.name(t), lv))
        g.add(t, HASTED, "(%s's Haste)" % c["name"], by=me, spell="Haste")
        ts = self.fight.turn_state if self.fight else None
        if ts and ts.get("id") == t:                             # hasted on its own turn: the doubled Speed now
            ts["movement"] += ts.get("speed", 0)
            ts["speed"] = ts.get("speed", 0) * 2
        return [t]

    def slow(self, me, c, tids, lv, dis):
        sim, g, party = self.sim, gm(self.sim), self.party
        dc = party.spell_dc(c)
        sim.say("dice", "%s casts Slow (a level %d slot, Concentration): DC %d Wisdom save for %s" % (
            c["name"], lv, dc, ", ".join(party.name(t) for t in tids)))
        held = []
        for t in tids:
            hd = "Heightened Spell" if t in dis else False
            if g.condition_save(t, "wis", dc, "Slow", dis=hd):
                continue
            g.add(t, SLOWED, "(%s's Slow: Speed halved, -2 AC and Dexterity saves, no Reactions, an action or a Bonus "
                  "Action, one attack)" % c["name"], by=me, spell="Slow", save="wis", dc=dc, repeat_spell=True,
                  **({"dis": hd} if hd else {}))
            sim.S.setField(t, "reaction", 1)         # no Reactions
            held.append(t)
        return held

    # ------------------------------------------------------------------ what the conditions change
    def condition_changed(self, t, name):
        if name == HASTED and not hasted(self.sim, t) and not self.sim.down(t):
            self.lethargy(t)
        if name in (HASTED, SLOWED):
            self.refresh(t)

    def lethargy(self, t):
        """"When the spell ends, the target is Incapacitated and has a Speed of 0 until the end of its next turn"."""
        sim, g = self.sim, gm(self.sim)
        ts = self.fight.turn_state if self.fight else None
        mine = (ts and ts.get("id") == t) or sim.S.active()[0] == t
        info = (g.cond.get(t) or {}).get(HASTED) or {}
        g.add(t, "Incapacitated", "(Haste ends: a wave of lethargy, Speed 0 until the end of its next turn)",
              by=info.get("by", t), lethargy=True, lib=True, until={"who": "target", "when": "end"}, skip=1 if mine else 0)
        if ts and ts.get("id") == t:
            ts["movement"], ts["action_used"], ts["attacks_left"] = 0, True, 0

    def refresh(self, t):
        """AC and Speed from the base and these spells: +2 AC hasted, -2 slowed; Speed x2 hasted, half slowed."""
        sim = self.sim
        c = sim.by_id(t)
        h, s = hasted(sim, t), slowed(sim, t)
        base = self.base.get(t)
        if base is None:
            if not (h or s):
                return
            base = self.base[t] = {"ac": c.get("ac"), "speed": c.get("speed")}
        ac = int(base["ac"] or 10) + (2 if h else 0) - (2 if s else 0)
        c["ac"] = ac
        sim.S.setField(t, "ac", ac)
        if not c.get("pc"):                                      # a player's character: its turn state (live_turn_start)
            factor = (2 if h else 1) * (0.5 if s else 1)
            text = _scaled(base["speed"] or "30 ft.", factor)
            c["speed"] = text if isinstance(base["speed"], str) else int(text)
            set_ct_text(sim, t, "speed", str(c["speed"]) if isinstance(base["speed"], str) else "%s ft." % c["speed"])
        if not (h or s):
            self.base.pop(t, None)

    def save_mod(self, t, ability):
        if not str(ability).startswith("dex"):
            return 0, ""
        return (-2 if slowed(self.sim, t) else 0), ("Haste" if hasted(self.sim, t) else "")

    # ------------------------------------------------------------------ turns
    def expire(self, me):
        """The caster's turn starts: its Haste or Slow past its minute ends (and its Concentration)."""
        held = self.cast_round.get(me)
        if not held:
            return
        name, rnd, rounds = held
        if self.party.concentrates(me) != name:
            self.cast_round.pop(me, None)
            return
        if int(self.sim.S.round() or 0) >= rnd + rounds:
            self.cast_round.pop(me, None)
            self.sim.say("dice", "%s's %s ends: its duration is over" % (self.sim.by_id(me)["name"], name))
            self.party.end_concentration(me)

    def creature_turn_start(self, me):
        self.expire(me)
        if slowed(self.sim, me):
            self.sim.S.setField(me, "reaction", 1)
        return ""

    def live_turn_start(self, me):
        self.expire(me)
        ts = self.fight.turn_state
        if lethargic(self.sim, me):
            ts["movement"] = ts["speed"] = 0
            self.sim.say("turn", "%s is lethargic after Haste: Incapacitated, Speed 0 this turn" % self.sim.by_id(me)["name"])
            return
        if hasted(self.sim, me):
            ts["movement"], ts["speed"] = ts["movement"] * 2, ts["speed"] * 2
        if slowed(self.sim, me):
            ts["movement"], ts["speed"] = ts["movement"] // 2, ts["speed"] // 2
            self.sim.S.setField(me, "reaction", 1)

    # ------------------------------------------------------------------ a player's choices
    def haste_free(self, me):
        return hasted(self.sim, me) and self.used.get(me) != self.serial() and not lethargic(self.sim, me)

    def main_spent(self, me, cmd):
        t, op = self.fight.turn_state, cmd.get("op")
        if op == "attack":
            return t["action_used"] and t["attacks_left"] <= 0 and cmd.get("weapon") != "offhand" and not cmd.get("metamagic")
        if op == "move":
            return bool(cmd.get("dash")) and t["action_used"]
        return t["action_used"] and op in ("dash", "disengage", "hide")

    def choose(self, me, cmd, do):
        import live_play
        fight, t, op = self.fight, self.fight.turn_state, cmd.get("op")
        if slowed(self.sim, me):
            failed = self.slow_cantrip_fails(me, cmd)
            if failed:
                return failed
        use = op in HASTE_OPS and not cmd.get("bonus") and self.haste_free(me) and (
            cmd.get("haste") or self.main_spent(me, cmd))
        if cmd.get("haste") and not use:
            if not hasted(self.sim, me):
                raise live_play.LiveError("%s is not hasted." % self.sim.by_id(me)["name"])
            if self.used.get(me) == self.serial():
                raise live_play.LiveError("%s has taken Haste's action this turn." % self.sim.by_id(me)["name"])
            raise live_play.LiveError("Haste's action is for the Attack action (one attack), Dash, Disengage, Hide or Utilize.")
        if not use:
            out = do(me, cmd)
            self.after(me, cmd, out)
            return out
        saved = (t["action_used"], t["attacks_left"])
        if op == "attack":
            t["action_used"], t["attacks_left"] = True, 1
        else:
            t["action_used"] = False
        try:
            out = do(me, cmd)
        except Exception:
            t["action_used"], t["attacks_left"] = saved
            raise
        if op == "move" and out.get("dashed") != "action":           # the move needed no Dash: nothing taken
            t["action_used"], t["attacks_left"] = saved
            return out
        t["action_used"], t["attacks_left"] = saved
        self.used[me] = self.serial()
        what = {"attack": "the Attack action (one attack)", "dash": "Dash", "disengage": "Disengage", "hide": "Hide",
                "use_item": "Utilize", "move": "Dash"}[op]
        self.sim.say("turn", "%s uses Haste's extra action: %s" % (self.sim.by_id(me)["name"], what))
        out.setdefault("lines", []).append("%s uses Haste's extra action: %s" % (self.sim.by_id(me)["name"], what))
        out["haste"] = True
        return out

    def after(self, me, cmd, out):
        """Slow: an action or a Bonus Action, not both; one attack with the Attack action."""
        if not out.get("ok") or not slowed(self.sim, me) or cmd.get("op") == "end":
            return
        t, party, c = self.fight.turn_state, self.party, self.sim.by_id(me)
        took = None
        if t["action_used"] and party.bonus_free(me):
            party.use_bonus(me)
            took = "its action: no Bonus Action this turn"
        elif not party.bonus_free(me) and not t["action_used"]:
            t["action_used"], t["attacks_left"] = True, 0
            took = "its Bonus Action: no action this turn"
        if cmd.get("op") == "attack" and t["attacks_left"] > 0:
            t["attacks_left"] = 0
            took = took or "one attack with the Attack action"
        key = (me, self.serial())
        if took and key not in self.noted:
            self.noted.add(key)
            self.sim.say("turn", "%s is slowed (Slow): %s" % (c["name"], took))

    def slow_cantrip_fails(self, me, cmd):
        """Slow on an attack cantrip of the sheet (it has a Somatic component): 25 percent it fails."""
        if cmd.get("op") != "attack":
            return None
        import party as party_mod, spell_rules
        c = self.sim.by_id(me)
        w = c.get(cmd.get("weapon")) if cmd.get("weapon") in __import__("character_rules").WEAPON_KEYS + ("offhand",) else None
        if not isinstance(w, dict) or not party_mod.spell_attack(w):
            return None
        rules = spell_rules.spell(w.get("name")) or {}
        if not (rules.get("components") or {}).get("s"):
            return None
        fight = self.fight
        fight.attack_check(me, cmd.get("weapon"), cmd.get("target"))
        return self.somatic_roll(me, w["name"], "action", 0, attack=True)

    def before_cast(self, me, cmd):
        if not slowed(self.sim, me):
            return None
        import live_asks, spell_rules
        name = cmd.get("spell")
        rules = spell_rules.spell(name) or {}
        info = live_asks.spell_info(name) or {}
        if not (rules.get("components") or {}).get("s") or (cmd.get("metamagic") and "Subtle Spell" in (
                [cmd["metamagic"]] if isinstance(cmd["metamagic"], str) else cmd["metamagic"])):
            return None
        time, level = info.get("time", "action"), info.get("level", 0)
        if time not in ("action", "bonus"):
            return None
        ms.check(ms.cast_needs(self.fight, me, name, level, time, cmd.get("slot"))[1:])   # the sheet: the cast checks it
        return self.somatic_roll(me, name, time, level, slot=cmd.get("slot"))

    def somatic_roll(self, me, name, time, level, slot=None, attack=False):
        sim, c = self.sim, self.sim.by_id(me)
        d = sim.rng.randint(1, 100)
        if d > 25:
            sim.say("dice", "%s is slowed: casting %s with a Somatic component, d100 %d: the gestures are in time" % (
                c["name"], name, d))
            return None
        t, party = self.fight.turn_state, self.party
        spent = ms.spend(self.fight, me, time, level, slot) if not attack else 0
        if attack:
            t["action_used"] = True
            t["attacks_left"] = 0
        sim.say("dice", "%s is slowed: casting %s with a Somatic component, d100 %d: the spell fails (Slow, 25 percent)%s"
                % (c["name"], name, d, "; the level %d slot is spent" % spent if spent else ""))
        self.after(me, {"op": "cast"}, {"ok": True})
        return {"ok": True, "result": "failed", "spell": name, "lines": ["%s's %s fails (Slow)" % (c["name"], name)]}

    def adjust_offers(self, me, out):
        """The sheet: the Haste action's buttons, Slow's note."""
        sim, fight = self.sim, self.fight
        t = fight.turn_state
        if hasted(sim, me):
            free = self.haste_free(me)
            out["haste"] = {"free": free, "for": "Attack (one attack), Dash, Disengage, Hide or Utilize"}
            if free and t and t["action_used"]:
                saved = (t["action_used"], t["attacks_left"])
                try:
                    t["action_used"] = False
                    for a in out.get("actions") or []:
                        if a.get("op") in ("dash", "disengage", "hide") and not a.get("ready"):
                            try:
                                fight.actions.check(me, a["op"])
                                a.update(ready=True, why="", haste=True, label="%s (Haste's action)" % a.get("label", a["op"]))
                            except Exception:
                                pass
                    t["action_used"], t["attacks_left"] = True, 1
                    for a in out.get("attacks") or []:
                        if a.get("targets") or a.get("key") == "offhand":
                            continue
                        ok, no = [], {}
                        for o in sim.sc["combatants"]:
                            if o["id"] == me:
                                continue
                            try:
                                fight.attack_check(me, a["key"], o["id"])
                                ok.append(o["id"])
                            except Exception as e:
                                no[o["id"]] = str(e)
                        if ok:
                            a.update(targets=ok, refused=no, haste=True)
                finally:
                    t["action_used"], t["attacks_left"] = saved
        if slowed(sim, me):
            out["slowed"] = "Slow: an action or a Bonus Action (not both), one attack, no Reactions; a Somatic spell " \
                            "fails 25 percent of the time"


# ---------------------------------------------------------------------- the hooks (sim/more_spells.py)
def condition_changed(sim, t, name):
    if name in (HASTED, SLOWED):
        of(sim).condition_changed(t, name)


def creature_turn_start(sim, me):
    return of(sim).creature_turn_start(me) if getattr(sim, "_haste_slow", None) else ""


def creature_extra_action(sim, me):
    """creature_turns.extra_action: "Haste" while a creature the game plays has Haste's action this turn (taken now)."""
    st = getattr(sim, "_haste_slow", None)
    if st is None or not st.haste_free(me):
        return ""
    st.used[me] = st.serial()
    return "Haste"


def live_turn_start(fight, me):
    of(fight.sim).live_turn_start(me)


def save_mod(sim, t, ability):
    return of(sim).save_mod(t, ability) if getattr(sim, "_haste_slow", None) else (0, "")


def choose(fight, me, cmd, do):
    return of(fight.sim).choose(me, cmd, do)


def before_cast(fight, me, cmd):
    return of(fight.sim).before_cast(me, cmd)


def adjust_offers(fight, me, out):
    of(fight.sim).adjust_offers(me, out)


def plan_rules(me):
    """ai_turn.build_options: (one attack only, no Bonus Action) for a creature with the Slow effect."""
    import ai_turn
    s = ai_turn.has_effect(me, SLOWED.lower())
    return s, s
