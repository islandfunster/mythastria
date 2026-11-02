"""GM 2026-10-24 ("When players use their own characters in Play Live, they will need full access. We need a mechanism to
reach them."): every spell and feature on a character's sheet is reachable in a live fight. What the rules engine plays
is cast or used as before; everything else is "Ask the GM": the player picks it (and creatures, and a note), the engine
checks what it can (the turn, the casting time, a slot of the right level, One Spell with a Spell Slot per Turn, a
feature's uses), spends it (the action, the slot, a use; a Concentration spell ends the one held), and the GM rules
the outcome from the GM's screen (live_play.LiveFight.rule_ask), even after the turn has moved on.

The spell list and features come from the character sheet (sim/character_build.py member(): spell_list,
feature_list); the casting time, level and Concentration from the SRD 5.2.1 text (sim/spell_rules.py).
"""
import requirements as rq

TIME = {"action": "action", "bonus_action": "bonus", "reaction": "reaction", "long": "long"}
# GM 2026-11-01 (Thieves' Tools, a pit's wall): what the GM rules with no check here; True: it takes the Action. Influence: sim/live_lore.py
ACTIONS = {"Thieves' Tools": True, "Climb out of the pit": False}
# GM 2026-11-01 ("Ask the GM if you can choose"): a played spell that can go to the GM too, and why
ASK_TOO = {"Spirit Guardians": "Radiant as a Cast button. To deal Necrotic, ask the GM whether you can choose."}


class AskError(ValueError):
    pass


def spell_info(name):
    import spell_rules
    try:
        r = spell_rules.spell(name)
    except Exception:
        return None
    if not r:
        return None
    return {"level": int(r.get("level") or 0), "time": TIME.get(r.get("casting_time"), "action"),
            "time_text": r.get("casting_time_text") or "", "concentration": bool((r.get("duration") or {}).get("concentration")),
            "range": (r.get("range") or {}).get("ft")}


class Asks:
    def __init__(self, fight):
        self.fight = fight

    @property
    def sim(self):
        return self.fight.sim

    @property
    def party(self):
        return self.sim.party

    def played(self, me):
        """The spells the engine casts for this character (Cast buttons, sim/live_spells.py)."""
        import live_spells, live_general, map_layers, invisibility, light_sources, more_spells
        c = self.sim.by_id(me)
        import spell_doors                           # SPELL-OBJECTS-01: a door card is for doors and props only
        return (set(live_spells.known(c)) | set(live_general.of(self.fight).known(c)) | \
            set(map_layers.Layers.known(c)) | \
            ({invisibility.SPELL} if invisibility.LiveInvisibility.known(c) else set()) | \
            set(light_sources.LiveLights.known(c)) | \
            more_spells.known(c)) - set(spell_doors.SPELLS)   # LIGHTS-01, SPELL-EFFECTS-01

    def uses_left(self, me, name, most):
        left = self.party.__dict__.setdefault("ask_uses", {}).setdefault(me, {})
        return left.setdefault(name, most)

    # ------------------------------------------------------------------ the offers
    def offers(self, me):
        c, out = self.sim.by_id(me), []
        played = self.played(me)
        attacks = {str((c.get(k) or {}).get("name")) for k in __import__("character_rules").WEAPON_KEYS}
        for sp in c.get("spell_list") or []:
            name = sp.get("name")
            if not name or name in attacks:
                continue
            if name in played:
                if name in ASK_TOO and not self.fight.by_srd:    # BY-THE-SRD-01: the sheet's alignment decides
                    out.append(self.entry(me, {"kind": "spell", "name": name}, sp))
                continue
            out.append(self.entry(me, {"kind": "spell", "name": name}, sp))
        for f in c.get("feature_list") or []:
            out.append(self.entry(me, {"kind": "feature", "name": f["name"]}, f))
        for name in self.actions(me):
            out.append(self.entry(me, {"kind": "action", "name": name}, {}))
        return out

    def actions(self, me):
        """The actions the GM rules that this character can ask about now."""
        import traps
        return traps.of(self.sim).asks(me)

    def entry(self, me, cmd, data):
        ready, rows = rq.check(self.needs(me, cmd))
        e = dict(cmd, op="ask_gm", ready=ready)
        if cmd["kind"] == "spell":
            info = spell_info(cmd["name"]) or {}
            e.update(level=info.get("level", data.get("level", 0)), time=info.get("time", "action"),
                     concentration=info.get("concentration", False), always=bool(data.get("always")),
                     objects=__import__("spell_objects").objects(cmd["name"]))   # SPELL-OBJECTS-01
            import live_general
            why = live_general.gm_why(cmd["name"])                   # SPELLS-4-9: why it is not a Cast button
            if why:
                e["note"] = "Ask the GM: %s." % why
            import spell_doors                                       # SPELL-OBJECTS-01
            if cmd["name"] in spell_doors.SPELLS:
                e["note"] = "At a door or a prop, use the %s card; anything else, the GM rules." % cmd["name"]
            if cmd["name"] in ASK_TOO:
                e["note"] = ASK_TOO[cmd["name"]]
        elif cmd["kind"] == "action":
            e.update(time="action" if ACTIONS.get(cmd["name"]) else "free")
        else:
            e.update(time=data.get("time", "free"))
            if data.get("uses") is not None:
                e["uses"] = self.uses_left(me, cmd["name"], int(data["uses"]))
            e.update(__import__("high_levels").ask_entry(self.party, me, cmd["name"]))   # CASTER-HIGH: Divine Intervention
            import live_reactions                                # CUTTING-WORDS-01: asked live, not Ask the GM
            if cmd["name"] in live_reactions.ASKED:
                ready, rows = False, rows + [rq.need("its trigger", False, live_reactions.ASKED[cmd["name"]])]
                e["ready"] = False
        if not ready:
            e["why"] = rq.first_why(rows)
        return e

    def free_cast(self, me, name, slot=None):
        """GM 2026-10-26 (levels 10-20): a spell the sheet casts without a slot (its "free" uses a rest: Mystic Arcanum,
        Magic Initiate, Signature Spells) with a use left, cast at its own level (no higher slot asked for)."""
        sp = next((sp for sp in self.sim.by_id(me).get("spell_list") or [] if sp.get("name") == name), None)
        if not sp or not sp.get("free") or (slot and int(slot) != int(sp.get("level") or 0)):
            return False
        return self.uses_left(me, "free:" + name, int(sp["free"])) > 0

    def needs(self, me, cmd, slot=None):
        c = self.sim.by_id(me)
        needs = [rq.able(self.fight, me)]
        if cmd["kind"] == "spell":
            names = {sp.get("name") for sp in c.get("spell_list") or []}
            needs.append(rq.need("the spell on the sheet", cmd["name"] in names,
                                 "%s is not on %s's sheet." % (cmd["name"], c["name"]), rq.LINKS["characters"]))
            info = spell_info(cmd["name"])
            if info is None:
                needs.append(rq.need("an SRD spell", False, "%s is not an SRD 5.2.1 spell the table knows." % cmd["name"]))
                return needs
            if info["time"] == "long":
                needs.append(rq.need("a casting time of one turn", False, "%s takes %s to cast: the GM rules it outside the "
                                     "fight's turns." % (cmd["name"], info["time_text"] or "longer than a turn")))
            elif info["time"] == "reaction":
                import live_reactions                            # SPELL-BATCH-02: Shield and Counterspell are asked live
                needs.append(rq.need("its trigger", False, live_reactions.ASKED.get(cmd["name"]) or
                                     "%s is a Reaction (%s): it is cast when that happens; tell the GM."
                                     % (cmd["name"], info["time_text"])))
            elif info["time"] == "bonus":
                needs.append(rq.bonus_free(self.fight, me, cmd["name"]))
            else:
                needs.append(rq.action_free(self.fight, me, cmd["name"]))
            if info["level"] >= 1 and self.free_cast(me, cmd["name"], slot):
                pass                                             # GM 2026-10-26: Mystic Arcanum and the like, no slot
            elif info["level"] >= 1:
                lv = max(info["level"], int(slot or info["level"]))
                pool = self.party.pools.get(me) or [self.party.slots.get(me, 0)]
                needs.append(rq.need("a spell slot", sum(pool[lv - 1:]) > 0,
                                     "No spell slot of level %d or higher left for %s." % (lv, cmd["name"])))
                needs.append(rq.need("no other slot this turn", self.party.slot_turn.get(me) != self.party.s.turnSerial,
                                     "One spell with a spell slot per turn: %s already spent a slot this turn." % c["name"]))
        elif cmd["kind"] == "action":
            needs.append(rq.need("something to ask now", cmd["name"] in self.actions(me), "%s is not open to %s now." % (cmd["name"], c["name"])))
            if ACTIONS.get(cmd["name"]):
                needs.append(rq.action_free(self.fight, me, cmd["name"]))
        else:
            f = next((f for f in c.get("feature_list") or [] if f["name"] == cmd["name"]), None)
            needs.append(rq.need("the feature on the sheet", f is not None, "%s is not on %s's sheet." % (cmd["name"], c["name"]),
                                 rq.LINKS["characters"]))
            if f and f.get("uses") is not None:
                needs.append(rq.need("a use left", self.uses_left(me, f["name"], int(f["uses"])) > 0,
                                     "No use of %s left (they come back with a rest)." % f["name"]))
            import high_levels                                   # CASTER-HIGH: Divine Intervention's use, a Magic action
            if f and high_levels.ask_entry(self.party, me, f["name"]):
                why = high_levels.ask_why(self.party, me, f["name"])
                needs.append(rq.need("Divine Intervention's use", not why, why))
                needs.append(rq.action_free(self.fight, me, f["name"]))
        return needs

    # ------------------------------------------------------------------ asking
    def do(self, me, cmd):
        ready, rows = rq.check(self.needs(me, cmd, cmd.get("slot")))
        if not ready:
            raise AskError(rq.first_why(rows))
        c, party, t = self.sim.by_id(me), self.party, self.fight.turn_state
        targets = [x for x in (cmd.get("targets") or []) if isinstance(x, str)]
        names = ", ".join(self.sim.by_id(x)["name"] for x in targets if any(o["id"] == x for o in self.sim.sc["combatants"]))
        note = str(cmd.get("note") or "").strip()[:200]
        spent = []
        if cmd["kind"] == "spell":
            info = spell_info(cmd["name"])
            if info["time"] == "bonus":
                party.use_bonus(me); spent.append("Bonus Action")
            else:
                t["action_used"], t["attacks_left"] = True, 0; spent.append("Action")
            if info["level"] >= 1 and self.free_cast(me, cmd["name"], cmd.get("slot")):
                party.ask_uses[me]["free:" + cmd["name"]] -= 1
                spent.append("no slot: its use this Long Rest")
            elif info["level"] >= 1:
                lv = party.spend_slot(me, max(info["level"], int(cmd.get("slot") or info["level"])))
                spent.append("a level %d slot" % lv)
            if info["concentration"]:
                party.start_concentration(me, cmd["name"])
                party.__dict__.setdefault("gm_concentration", {})[me] = cmd["name"]
                spent.append("Concentration")
            what = "casts %s" % cmd["name"]
            if cmd["name"] == "Divine Smite":                    # MARTIAL-HIGH: Smite of Protection (Devotion 15)
                __import__("martial_high").smite_protection(party, me)
            import invisibility
            invisibility.cast_spell(self.sim, me, cmd["name"])   # INVISIBILITY-01: a spell cast ends it
        elif cmd["kind"] == "action":
            if ACTIONS.get(cmd["name"]) and t:
                t["action_used"], t["attacks_left"] = True, 0
                spent.append("Action")
            what = "asks about %s" % cmd["name"]
        else:
            f = next(f for f in c.get("feature_list") or [] if f["name"] == cmd["name"])
            if f.get("uses") is not None:
                party.ask_uses[me][f["name"]] -= 1
                spent.append("a use (%d left)" % party.ask_uses[me][f["name"]])
            import high_levels                                   # CASTER-HIGH: Divine Intervention, a Magic action
            divine = high_levels.ask_spend(party, me, f["name"])
            if divine:
                t["action_used"], t["attacks_left"] = True, 0
                spent += ["Magic action", divine]
            what = "uses %s" % cmd["name"]
        n = self.fight.add_ask(me, c["name"], cmd["kind"], cmd["name"], targets, note)
        self.sim.say("turn", "%s %s%s (%s)%s: the GM rules it (request %d)" % (
            c["name"], what, " on " + names if names else "", ", ".join(spent) or "no cost here",
            ' "%s"' % note if note else "", n))
        return {"ask": n}
