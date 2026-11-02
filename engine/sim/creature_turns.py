"""FG-EXIT-01 step 2 (GM 2026-10-26: goals 1 and 2 of the Documents page list): the creatures' turns in Python.

A creature's turn used to run through the old Fantasy Grounds extension (extension_source/scripts/aibridge.lua) on the
stand-in FG (sim/fake_fg.lua), talking to the old bridge server over HTTP. Here the same turn is played on the fight
state in Python (sim/fight_state.py); the planner stays as it is (mythastria_core/ai_turn.py: legal choices, routes,
reach, sight, Multiattack patterns):

1. the planner offers the creature's legal choices from its stat block (the scenario's copy of
   sim/creatures/srd_library.json) and the fight as it stands now;
2. the model (or the scripted chooser) picks one, and ai_turn.validate maps the pick back to a choice;
3. the choice is carried out here, each rule checked again before any dice roll: a move (SRD 5.2.1 Speed, the map's
   diagonal rule, Moving around Other Creatures, swimming, HR-SQUEEZE, one door opened per move), an attack (reach, one
   Attack action, Multiattack one attack at a time with moves between), a Search (Wisdom (Perception) against the GM's
   DC), and opportunity attacks by creatures (SRD 5.2.1: a hostile creature it can see leaves its reach; one Reaction);
4. the narration goes to the players once the result is known (a miss is never narrated as a hit).

Written fresh from SRD 5.2.1 (DECISIONS "FG DROPPED", "SIMILAR IS FINE"). Where this module and the old extension decide
differently, the rules here win; docs/development/FG_EXIT_PLAN.md lists each difference.

The pieces that creature spellcasting, legendary actions and special traits plug into are named hooks on CreatureTurns:
extra_choices (more choices for the planner's list), on_turn_start / on_turn_end (uses that come back, Recharge), and
attack_mode (a trait that changes the attack roll). sim/creature_abilities.py fills them.
"""
import json
import logging
import math
import re

import ai_turn
import diagnostics
import lighting
import map_walls
import ollama_client
import statblock_ai

LIST = "combattracker.list."
SIGNATURE = "parseNPCPower(nodePower,false)"
MULTI_MAX = 8                       # attacks in one turn at most
SIZE_RANK = {"tiny": 0, "small": 1, "medium": 2, "large": 3, "huge": 4, "gargantuan": 5}
STOP_MOVE = ("grappled", "restrained", "prone")
LOG = logging.getLogger("mythastria.creatures")     # the GM's log of the creatures' decisions
LOG.setLevel(logging.INFO)
LOG.addHandler(logging.NullHandler())
KNOWLEDGE_ORIGIN = {"trait": "ct.traits", "reaction": "ct.reactions", "legendary action": "ct.legendaryactions",
                    "bonus action": "ct.actions"}


def event(kind, message):
    """One line in the GM's log ("ai-npc-turn offered to ...", "ai-reaction ...")."""
    LOG.info("%s %s", diagnostics.clean(kind, 60), diagnostics.clean(message))


def _text(v):
    """A fight-state field as text, the way the planner reads its raw fields."""
    if isinstance(v, bool):
        return "true" if v else "false"
    return "" if v is None else str(v)


def _dice(spec):
    """"2d6+3" -> (["d6", "d6"], 3); a flat "1" -> ([], 1)."""
    spec = str(spec or "").replace(" ", "")
    m = re.fullmatch(r"(\d*)d(\d+)([+-]\d+)?", spec)
    if m:
        return ["d" + m.group(2)] * int(m.group(1) or 1), int(m.group(3) or 0)
    m = re.fullmatch(r"[+-]?\d+", spec)
    return ([], int(spec)) if m else (["d4"], 0)


class CreatureTurns:
    """Plays every creature (every combatant that is not a player character) through its turns."""

    def __init__(self, sim):
        self.sim, self.fs = sim, sim.S
        sc = sim.sc
        # SRD 5.2.1 (and the GM's AWARE-01 rulings): who noticed the party, this turn's Search, who made noise when
        self.awareness = {"aware": {LIST + i for i in sc.get("aware") or []}, "search": {}, "noise": {}}
        self.perception_dc = int(sc.get("perception_dc") or ai_turn.DEFAULT_PERCEPTION_DC)
        self.mode = sim.gm                                       # "auto" (Autopilot) or "suggest" (the players react)
        self.turn = None                                         # this activation of the acting creature
        self.pending = None                                      # the latest decision, as the GM's log shows it
        self.oa_asked = {}                                       # (reactor, mover) -> activation already asked
        self.extra_choices, self.on_turn_start, self.on_turn_end = [], [], []
        self.attack_mode = []                                    # fn(src, tgt, roll): a trait changes the roll
        self.handlers = {}                                       # node path of an ability's choice -> fn(cid, s)
        self.seq = 0
        self.due = None                                          # the activation whose turn is the creature's to play
        self.fs.attackPostResolve.append(self._noise)
        self.fs.turnStart.append(self._turn_started)

    def _turn_started(self, cid):
        """A turn really started for this combatant (the simulator as GM did not take it: a breath, a song, a trap)."""
        self.due = (cid, self.fs.turnSerial)

    def is_due(self, cid):
        return self.due == (cid, self.fs.turnSerial)

    # ------------------------------------------------------------------ the fight as the planner reads it
    def path(self, cid):
        return LIST + cid

    def by_path(self, path):
        return str(path).rsplit(".", 1)[-1]

    def normalized(self, c):
        """One combatant in the planner's shape (the old bridge's normalize_combatant), from the fight state now."""
        cid, fs = c["id"], self.fs
        node = fs._c(cid)
        raw = {k: _text(v) for k, v in node.fields.items() if isinstance(v, (str, int, float, bool))}
        raw.update({"pos.x": _text(node.px), "pos.y": _text(node.py), "pos.map": self.sim.MAP})
        pc = bool(node.fields.get("pc"))
        link = ("charsheet", "charsheet." + cid) if pc else ("npc", "")
        raw["link"] = "%s:%s" % link
        effects = []
        for eid, e in sorted(node.effects.items()):
            active = "0" if str(e.get("isactive", 1)) == "0" else "1"
            raw["effects.%s.label" % eid], raw["effects.%s.isactive" % eid] = e["label"], active
            effects.append({"path": "effects." + eid, "raw_fields": {"label": e["label"], "isactive": active},
                            "label": e["label"], "active": active})
        return {"path": self.path(cid), "name": raw.get("name", ""), "active": raw.get("active", ""),
                "friend_foe": raw.get("friendfoe", ""), "initiative": raw.get("initresult", ""), "visible": "",
                "hp_total": raw.get("hptotal", ""), "wounds": raw.get("wounds", ""), "temporary_hp": "",
                "token": {}, "actor_link": {"value": raw["link"], "class": link[0], "recordname": link[1],
                                            "source_class": "", "source_recordname": ""},
                "effects": effects, "targets": [], "raw_fields": raw}

    def combatants(self):
        return {self.path(c["id"]): self.normalized(c) for c in self.sim.sc["combatants"] if c["id"] in self.fs.combatants}

    def ranked(self):
        """Every creature's actions as planner records, in stat-block order (the old bridge ranked FG's parser results,
        whose order among equal scores changed from run to run). An attack carries its type, melee or ranged, and its
        reach or normal range; the rest (Multiattack, Spellcasting, traits) only their text."""
        out = []
        for c in self.sim.sc["combatants"]:
            if c.get("pc") or c["id"] not in self.fs.combatants:
                continue
            ct = self.path(c["id"])
            for a in c.get("actions") or []:
                fields = []
                if a.get("atk") is not None:
                    fields = [{"key": "return1.1.type", "value": "attack"},
                              {"key": "return1.1.atktype", "value": a.get("atktype") or "melee"},
                              {"key": "return1.1.rangedist", "value": _text(a.get("reach") or 5)},
                              {"key": "return1.1.modifier", "value": _text(a["atk"])},
                              {"key": "return1.2.type", "value": "damage"}]
                out.append({"score": 1, "ctpath": ct, "actor_name": c.get("name", ""), "power_name": a.get("name", ""),
                            "origin": "ct.actions", "node_path": "%s.actions.%s" % (ct, a["id"]),
                            "description": " ".join(str(a.get("desc") or "").replace("\\n", "\n").split()),
                            "signature": SIGNATURE, "ok": "1", "error": "", "fields": fields})
            for n, g in enumerate(c.get("gm_text") or []):       # traits and reactions: the model's reference only
                origin = KNOWLEDGE_ORIGIN.get(str(g.get("part") or "").lower())
                if origin:
                    out.append({"score": 0, "ctpath": ct, "actor_name": c.get("name", ""), "power_name": g.get("name", ""),
                                "origin": origin, "node_path": "%s.reference.r%d" % (ct, n + 1),
                                "description": " ".join(str(g.get("desc") or "").split()), "signature": "reference",
                                "ok": "1", "error": "", "fields": []})
        return out

    def action(self, cid, node_path):
        """The scenario's action behind a planner node path."""
        aid = str(node_path).rsplit(".", 1)[-1]
        return next((a for a in self.sim.by_id(cid).get("actions") or [] if a.get("id") == aid), None)

    def distances(self, cid):
        me = self.path(cid)
        return {(me, self.path(o)): float(self.fs.distance(cid, o)) for o in self.fs.combatants if o != cid}

    def space(self, cid):
        """The map for one decision: grid, diagonal rule, walls and closed doors, light, water, this turn's movement so
        far, and who noticed whom."""
        sc, t = self.sim.sc, self.turn or {}
        diag = str(sc.get("diag", 1))
        space = {"map": self.sim.MAP, "mapname": sc.get("map_name", "Simulated map"), "grid": float(sc.get("grid", 50)),
                 "grid_h": float(sc.get("grid", 50)), "units": float(sc.get("units", 5)),
                 "diag": diag if diag in ("1", "1.5", "*") else "1",
                 "moved": float(t.get("moved", 0) if t.get("id") == cid else 0),
                 "moved_diag": int(t.get("mdiag", 0) if t.get("id") == cid else 0)}
        walls = self.sim.walls
        space["walls"] = map_walls.blocking_segments(walls) if walls else None
        space["doors"] = map_walls.closed_door_segments(walls) if walls else None
        space["door_list"] = map_walls.closed_doors(walls) if walls else None
        space["lighting"] = map_walls.lighting(walls)
        space["water"] = map_walls.water(walls)
        space["avoid_provoking"] = self.mode == "auto"
        space["allow_move"] = True
        me = self.path(cid)
        seen = self.awareness["search"].get(me)
        space.update(aware=me in self.awareness["aware"], noise=self.recent_noise(),
                     searched=seen[1] if seen and seen[0] == self.fs.turnSerial else None,
                     perception_dc=self.perception_dc)
        keep, rough = self.route_cells(cid)
        g = space["grid"]
        if keep:
            space["keep_off"] = [[x * g, y * g] for x, y in sorted(keep)]
        if rough:
            space["rough"] = [[x * g, y * g] for x, y in sorted(rough)]
        return space

    def route_cells(self, cid):
        """Group 1 (GM 2026-10-27): (squares it keeps off, Difficult Terrain squares) on its routes: the lasting spell
        areas that would harm or hold it (sim/spell_zones.py), their Difficult Terrain and the environment's (ice,
        frigid water: sim/hazards.py)."""
        import more_spells
        keep = more_spells.keep_off_cells(self.sim, cid)
        rough = set(more_spells.difficult_cells(self.sim, cid))
        hz = getattr(self.sim, "hazards", None)
        if hz:
            rough |= hz.difficult_cells(cid)
        return keep, rough

    def recent_noise(self):
        """Who fought this round or the last (an attack roll, made or taken): heard by creatures nearby (HEAR-01)."""
        rnd = self.fs.round()
        return [p for p, r in self.awareness["noise"].items() if rnd - 1 <= r <= rnd]

    def _noise(self, src, tgt, result):
        rnd = self.fs.round()
        for cid in (src, tgt):
            if cid:
                self.awareness["noise"][self.path(cid)] = rnd

    def knowledge(self, combatants, ranked, options):
        """The model's reference for this decision (its own stat block, the conditions in play, the targets' classes)."""
        import knowledge
        sheets = {}
        for c in self.sim.sc["combatants"]:
            if c.get("pc"):
                sheets["charsheet." + c["id"]] = {"core": {"name": c.get("name", "")}, "feats": {},
                                                 "classes": {"1": {"name": str(c.get("class") or "").title(),
                                                                   "level": c.get("level", 1)}} if c.get("class") else {}}
        k = knowledge.gather(combatants, ranked, sheets, options)
        if k:
            event("ai-rules", "knowledge for " + options.get("source_name", "") + ": " + knowledge.summary(k)[:400])
        return k

    # ------------------------------------------------------------------ one creature's turn
    def take_turn(self, cid):
        """The creature's whole turn: decisions one at a time (a Search, then a move; a move and an attack; Multiattack
        attacks one by one) until it is done, then the next combatant. False when the decision failed (the run stops)."""
        fs = self.fs
        serial = fs.turnSerial
        self.turn = {"id": cid, "serial": serial, "moved": 0.0, "mdiag": 0, "attacked": False, "multi_done": [],
                     "hits": [], "targets": [], "items": []}
        for fn in list(self.on_turn_start):
            fn(cid)
        ok, guard = True, 0
        while fs.turnSerial == serial and guard < MULTI_MAX + 4:
            guard += 1
            self.sim.checkpoint()
            step = self.decide_and_act(cid)
            if step == "again":
                continue
            ok = step != "failed"
            break
        if ok and fs.turnSerial == serial and not fs.down(cid):
            self.extra_action(cid)                               # SPELL-EFFECTS-01: Haste's action (sim/haste_slow.py)
        for fn in list(self.on_turn_end):
            fn(cid)
        self.sim.settle()
        self.turn = None                    # over before the next one starts (legendary actions come in between)
        if fs.turnSerial == serial and ok:
            fs.nextActor()
        return ok

    def decide(self, cid):
        """The planner's options for this moment of the turn and the chosen one, validated; (choice, options) or an
        ai_turn exception."""
        t, fs = self.turn, self.fs
        path = self.path(cid)
        combatants, ranked = self.combatants(), self.ranked()
        space = self.space(cid)
        hook = getattr(self.sim, "trap_space", None)
        if hook:                                                 # goal 15: the traps this creature knows (keeps off them)
            try:
                more = hook(path, combatants) or {}
                if more.get("keep_off") and space.get("keep_off"):   # the traps' squares and the zones' together
                    more = dict(more, keep_off=space["keep_off"] + more["keep_off"])
                space.update(more)
            except Exception as e:                               # noqa: BLE001  (a fault there never stops the turn)
                event("ai-turn", "space hook failed: %s" % str(e)[:160])
        self.seq += 1
        result = {"seq": self.seq, "source": path, "source_name": combatants[path]["name"], "status": "thinking"}
        self.pending = result
        warnings = ai_turn.faction_warnings(combatants) + ai_turn.lighting_warnings(space, combatants)
        if warnings:
            result["warning"] = " ".join(warnings)
        interpreted = self.interpret_multiattack(ranked, path, result)
        done, hits, targets = t["multi_done"], t["hits"], t["targets"]
        try:
            options = ai_turn.build_options(combatants, ranked, path, self.distances(cid), fs.round(), False, False, space,
                                            done, interpreted, bool(hits and hits[-1]), targets[-1] if targets else None,
                                            hits, targets if len(targets) == len(done) else [], simulation=True)
            failed = None
        except (ai_turn.Incapacitated, ai_turn.MultiattackDone, ai_turn.Unaware):
            raise
        except ai_turn.SuggestError as e:                        # no attack or approach: an ability may still do
            if not self.extra_choices or done or t.get("held"):
                raise
            failed, options = e, {"round": fs.round(), "bonus_used": False, "multi_done": [], "slot_used": False,
                                  "source": path, "source_name": result["source_name"],
                                  "source_health": ai_turn.health_text(combatants[path]), "choices": [],
                                  "distances_known": True, "npc_choices": [], "aware": True, "search": False,
                                  "heard": [], "names": sorted({c.get("name", "") for c in combatants.values()})}
        self.handlers = {}
        if not options.get("search") and not t.get("limited"):
            for fn in self.extra_choices:                        # creature abilities (sim/creature_abilities.py)
                fn(cid, options, combatants, space)
        if t.get("limited"):                                     # Haste's action: one attack (no spell, no Bonus Action)
            options["choices"] = [ch for ch in options["choices"] if ch.get("move_only") or (
                ch.get("kind") == "attack" and not ch.get("spell") and not ch.get("bonus"))]
            if not options["choices"] and not options.get("search"):
                raise ai_turn.SuggestError("no attack or approach for %s's action" % t["limited"])
        import martial_high                                      # MARTIAL-HIGH: Daze (Devious Strikes), one thing a turn
        options["choices"] = martial_high.daze_choices(self.sim, cid, options["choices"])
        if failed and not options["choices"]:
            raise failed
        if options.get("aware"):
            self.awareness["aware"].add(path)
            if options.get("heard"):
                event("ai-npc-turn", "%s hears the fighting (%s): aware, no Search" % (
                    result["source_name"], ", ".join(options["heard"])))
        if done:
            options["earlier_attacks"] = t["items"] or done
        alts = ai_turn.alternatives(options)
        event("ai-npc-turn", "offered to " + result["source_name"] + ": " + "; ".join(a["summary"] for a in alts)[:900])
        result["alternatives"] = alts
        if options.get("search"):
            s = ai_turn.validate({"choice": "C1", "reason": "no enemy in sight", "narration": ""}, options)
        else:
            notes = self.spell_reference(options)
            know = self.knowledge(combatants, ranked, options) if not self.sim.fake else {}
            reply = self.choose(options, notes, know)
            s = ai_turn.validate(reply, options, know)
        result.update(s)
        result["status"] = "running"
        return s, options

    def choose(self, options, notes=None, know=None):
        if self.sim.fake:
            return self.sim.scripted_choice(options)
        return ollama_client.choose(self.sim.model, ai_turn.messages(options, rules=notes, knowledge=know),
                                    ai_turn.schema(options))

    def spell_reference(self, options):
        try:
            import rules_context
            return rules_context.spell_notes(options["choices"])
        except Exception:
            return None

    def interpret_multiattack(self, ranked, path, result):
        """A Multiattack the planner cannot read is read once by the local model (cached; the GM approves it)."""
        text = ai_turn.multiattack_text(ranked, path)
        names = ai_turn.attack_names(ai_turn.npc_actions(ranked).get(path, []))
        if not text or not self.sim.model or len(names) < 1 or ai_turn.parse_multiattack(text, names):
            return None
        chooser = (lambda model, messages, schema: self.sim.sc.get("fake_plan") or {"patterns": [], "notes": ""}) \
            if self.sim.fake else ollama_client.choose
        fresh = statblock_ai.cached(statblock_ai.key(text, list(names))) is None
        entry = statblock_ai.interpret(text, list(names), self.sim.model, chooser)
        if fresh and not entry.get("transient"):
            event("ai-statblock", "%s's Multiattack read by the local model: %s" % (
                result.get("source_name", ""), entry.get("summary") or "no fixed attack pattern (single attacks)"))
        if entry.get("patterns"):
            result.update(multi_plan=entry["summary"], multi_plan_key=entry["key"],
                          multi_plan_approved=bool(entry.get("approved")))
        return statblock_ai.usable_slots(entry)

    def log_result(self, result):
        """One line per decision in the GM's log, as before: what runs, at whom, the route."""
        move = result.get("move")
        event("ai-npc-turn", result.get("status", "") + ": " + result.get("source_name", "") +
                          (" -> " + result.get("target_name", "") + " using " + result.get("action_name", "")
                           if result.get("target_name") else "") +
                          (" | " + result["error"] if result.get("error") else "") +
                          (" | move %s ft via %s" % (move.get("feet"), " > ".join("%g,%g" % (x, y) for x, y in
                           (move.get("path") or [])[:40]) or "%g,%g" % (move["x"], move["y"])) if move else ""))

    def decide_and_act(self, cid):
        """One decision and what it does. Returns "again" (the turn goes on: a Search, or a Multiattack attack with
        more to come), "done" or "failed"."""
        name = self.fs.name(cid)
        try:
            s, options = self.decide(cid)
        except ai_turn.Incapacitated as e:
            self.end_line(cid, str(e), narrate=True)
            return "done"
        except ai_turn.MultiattackDone as e:
            self.end_line(cid, str(e))
            return "done"
        except ai_turn.Unaware as e:
            self.end_line(cid, str(e), narrate=True)
            return "done"
        except ai_turn.SuggestError as e:
            if self.turn.get("held") or self.turn["multi_done"]:
                self.end_line(cid, "%s has nothing left to do from where it stands." % name)
                return "done"                                    # after a stopped move: no target within reach
            att = getattr(self.sim, "attitudes", None)
            if att and att.held_any():                           # GM 2026-10-27: the foes left are held by a lasting
                self.end_line(cid, "%s has no one to fight: the foes left are held by a spell." % name)   # spell
                return "done"
            self.pending = dict(self.pending or {}, status="error", error=str(e))
            self.sim.say("error", "AI decision failed for %s: %s" % (name, e))
            return "failed"
        except ollama_client.OllamaError as e:
            self.pending = dict(self.pending or {}, status="error", error=str(e))
            self.sim.say("error", "AI decision failed for %s: %s" % (name, e))
            return "failed"
        self.log_result(self.pending)
        if s.get("kind") == "search":
            self.search(cid, s["dc"])
            return "again"
        handler = self.handlers.get(s.get("nodepath"))
        if handler:                                              # a creature ability (sim/creature_abilities.py)
            if s.get("move") and not self.walk(cid, s):
                return "done"
            self.turn["acted"] = True
            return handler(cid, s) or "done"
        if s.get("move") and not self.walk(cid, s):
            t = self.turn
            if t.get("held") and not s.get("move_only") and not self.fs.down(cid) and self.fs.turnSerial == t["serial"]:
                return "again"                                   # its move was stopped: it still has its action
            return "done"
        if s.get("move_only"):
            self.narrate(ai_turn.move_narration(s))
            return "done"
        multi = s.get("multi")
        res = self.attack(cid, s, multi=bool(multi and not multi.get("last")))
        if res is None:
            return "done"
        return "again" if multi and not multi.get("last") else "done"

    def end_line(self, cid, text, narrate=False):
        """The turn ends with no action: the GM's log says why (and the players hear it when it shows)."""
        self.pending = dict(self.pending or {}, status="running", error=text, summary="end its turn")
        self.log_result(self.pending)
        if narrate:
            self.narrate(text)

    def narrate(self, text):
        if text:
            self.sim.say("players", text)

    # ------------------------------------------------------------------ Haste's action (SPELL-EFFECTS-01)
    def extra_action(self, cid):
        """SRD 5.2.1 Haste: one more action on each of its turns, for the Attack action (one attack only), Dash,
        Disengage, Hide or Utilize. Taken after the creature's own: one attack (no Multiattack, no spell) at a foe it can
        reach, else a Dash toward one; when its own Action is still unused after the Dash, it takes it there."""
        import more_spells
        label = more_spells.creature_extra_action(self.sim, cid)
        if not label:
            return
        fs, t, name = self.fs, self.turn, self.fs.name(cid)
        free = not (t["attacked"] or t.get("acted"))
        fresh = dict(attacked=False, multi_done=[], hits=[], targets=[], items=[])
        t.update(fresh, limited=label)
        dashed = False
        try:
            s, why = self.limited_decision(cid)
            if s is not None and s.get("kind") == "search":
                return                                           # it noticed no one: nothing to use the action on
            if s is not None and not s.get("move_only"):
                self.sim.say("turn", "%s uses %s's extra action: the Attack action (one attack)" % (name, label))
                if not s.get("move") or self.walk(cid, s):
                    self.attack(cid, dict(s, multi=None), multi=False)
                return
            speed = ai_turn.speed_ft(fs.getValue(cid, "speed", ""))
            if t.get("held") or speed <= 0:
                self.end_line(cid, "%s takes no %s action: %s" % (name, label, why or "it can't move on"))
                return
            t["moved"] -= speed                                  # Dash: more movement, as much as its Speed
            s, why = self.limited_decision(cid)
            if s is None or not s.get("move"):
                t["moved"] += speed
                self.end_line(cid, "%s takes no %s action: %s" % (name, label, why or "no foe to move toward"))
                return
            self.sim.say("turn", "%s uses %s's extra action: Dash (%d ft more movement)" % (name, label, speed))
            dashed = True
            self.walk(cid, s)                                    # the Dash is its action: no attack with it
        finally:
            t["limited"] = None
        if dashed and free and not fs.down(cid) and fs.turnSerial == t["serial"]:
            t.update(fresh)                                      # its own Action, still unused, where it stands now
            for _ in range(MULTI_MAX + 1):
                if fs.turnSerial != t["serial"] or self.decide_and_act(cid) != "again":
                    break

    def limited_decision(self, cid):
        """One decision for Haste's action: (choice, None), or (None, why nothing can be done with it)."""
        try:
            s, _ = self.decide(cid)
        except (ai_turn.SuggestError, ollama_client.OllamaError) as e:
            return None, str(e)
        self.log_result(self.pending)
        return s, None

    # ------------------------------------------------------------------ a Search (AWARE-01)
    def search(self, cid, dc):
        """SRD 5.2.1 Search: a Wisdom (Perception) check against the GM's DC; success: it noticed the party."""
        fs, name = self.fs, self.fs.name(cid)
        self.sim.say("chat", "%s searches for enemies (Wisdom (Perception), DC %d)." % (name, dc))
        m = re.search(r"perception\s*([+-]?\d+)", str(fs.getValue(cid, "skills", "") or ""), re.I)
        bonus = int(m.group(1)) if m else int(fs.num(cid, "sim_wis_mod"))
        d20 = fs.rand(20)
        total = d20 + bonus
        ok = total >= dc
        self.sim.say("dice", "%s Perception check: d20 %d %+d = %d vs DC %d -> %s" % (
            name, d20, bonus, total, dc, "success" if ok else "failure"))
        path = self.path(cid)
        self.awareness["search"][path] = (fs.turnSerial, "success" if ok else "fail")
        if ok:
            self.awareness["aware"].add(path)
        event("ai-npc-turn", "search: %s rolled %d vs DC %d: %s" % (
            name, total, dc, "notices the party" if ok else "notices no one"))

    # ------------------------------------------------------------------ a move
    def occupant(self, cid, x, y):
        """(name, "free" / "difficult" / "block") of the most restrictive other creature filling pixel point (x, y) for
        cid's space (SRD 5.2.1 Moving around Other Creatures), or (None, None)."""
        fs, g, units = self.fs, self.sim.sc.get("grid", 50), self.sim.sc.get("units", 5)
        side, rank, msq = self.side(cid), self.size_rank(cid), fs.size_squares(cid)
        who, kind = None, None
        for o in fs.combatants:
            if o == cid:
                continue
            n = fs._c(o)
            lim = (fs.size_squares(o) + msq) / 2 * g - 0.02 * g
            if abs(n.px - x) < lim and abs(n.py - y) < lim:
                r = self.size_rank(o)
                if (side and self.side(o) == side) or r == 0:
                    k = "free"
                elif fs.stopped(o) or abs(rank - r) >= 2:
                    k = "difficult"
                else:
                    k = "block"
                if not kind or k == "block" or (k == "difficult" and kind == "free"):
                    who, kind = fs.name(o), k
        return who, kind

    def side(self, cid):
        return "friend" if self.fs.getValue(cid, "pc") else self.fs.getValue(cid, "friendfoe", "")

    def size_rank(self, cid):
        units = self.sim.sc.get("units", 5)
        word = str(self.fs.getValue(cid, "size", "") or "").strip().lower().split(" ")[0]
        if word in SIZE_RANK:
            return SIZE_RANK[word]
        ft = float(self.fs.num(cid, "space", 0) or 0) or units
        return 0 if ft < units else 2 if ft < 2 * units else 3 if ft < 3 * units else 4 if ft < 4 * units else 5

    def refuse(self, text):
        """A rule check the chosen action failed: nothing happens, and the run records it (the planner and the rules
        disagree, which is a bug to look at)."""
        self.sim.say("chat", "Not run: " + text)

    def walk(self, cid, s):
        """Carry out the planned move, square by square, after checking it: SRD 5.2.1 Speed (the faster of walking and
        flying; in water Swim or Fly, else each square costs 1 extra), the map's diagonal rule continued over the turn,
        creatures' spaces (an ally's passed freely, a non-ally's as Difficult Terrain when it is Incapacitated or two
        sizes apart, else blocked), HR-SQUEEZE (a squeezed step costs 1 extra), never ending in another creature's
        space. A step that leaves a hostile creature's reach lets it make an opportunity attack first. True when the
        creature got there (or was already there)."""
        fs, sc, t = self.fs, self.sim.sc, self.turn
        g, units = float(sc.get("grid", 50)), float(sc.get("units", 5))
        diag = str(sc.get("diag", 1))
        move, name = s["move"], fs.name(cid)
        if fs.getValue(cid, "pc"):
            self.refuse("%s is a player character." % name); return False
        cond = ai_turn.incapacitating_condition(self.normalized(self.sim.by_id(cid)))
        if cond:
            self.refuse("%s is %s." % (name, cond)); return False
        labels = [str(l).split(";")[0].strip().lower() for l in fs.active_labels(cid)]
        for c in STOP_MOVE:
            if c in labels:
                self.refuse("%s is %s." % (name, c)); return False
        node = fs._c(cid)
        start = (node.px, node.py)
        x, y = float(move["x"]), float(move["y"])
        route = [tuple(map(float, p)) for p in (move.get("path") or [])[1:-1]]
        wet = [bool(w) for w in move.get("water") or []] if any(move.get("water") or []) else None
        if wet is not None and len(wet) != len(route) + 1:
            self.refuse("%s's route and its water marks do not match." % name); return False
        squeeze = int(move.get("squeeze") or 0)
        pd = t["mdiag"]

        def squares(straight, diagonal):
            if diag == "*":
                return straight + diagonal * math.sqrt(2)
            if diag == "1.5":
                return straight + diagonal + (pd + diagonal) // 2 - pd // 2
            return straight + diagonal

        step_sq = []
        if not route:
            dx, dy = abs(x - start[0]) / g, abs(y - start[1]) / g
            diag_now = int(math.floor(min(dx, dy) + 0.5))
            if diag == "*":
                sq = math.sqrt(dx * dx + dy * dy)
            elif diag == "1.5":
                sq = max(dx, dy) + math.floor((pd + min(dx, dy)) / 2) - math.floor(pd / 2)
            else:
                sq = max(dx, dy)
            step_sq.append(sq)
        else:
            straight = diagonal = 0
            last = (0, 0)
            for p in route + [(x, y)]:
                cx, cy = (p[0] - start[0]) / g, (p[1] - start[1]) / g
                rx, ry = math.floor(cx + 0.5), math.floor(cy + 0.5)
                if abs(cx - rx) >= 0.05 or abs(cy - ry) >= 0.05:
                    self.refuse("%s's route steps must be whole squares." % name); return False
                dx, dy = abs(rx - last[0]), abs(ry - last[1])
                if dx > 1 or dy > 1:
                    self.refuse("%s's route has a step longer than one square." % name); return False
                if dx == 0 and dy == 0:
                    self.refuse("%s's route steps must be whole squares." % name); return False
                if dx == 1 and dy == 1:
                    diagonal += 1
                else:
                    straight += 1
                last = (rx, ry)
                step_sq.append(squares(straight, diagonal))
            diag_now = diagonal
            sq = step_sq[-1]
        speed_text = str(fs.getValue(cid, "speed", "") or "")
        m = re.search(r"\d+", speed_text)
        walk_ft = int(m.group(0)) if m else 0
        fly = re.search(r"fly\s*(\d+)", speed_text, re.I)
        fly_ft = int(fly.group(1)) if fly else None
        speed = max(walk_ft, fly_ft or 0)
        swim = max(int((re.search(r"swim\s*(\d+)", speed_text, re.I) or [0, 0])[1] or 0), fly_ft or 0)
        water_speed, water_extra = (swim, 0) if swim > 0 else (walk_ft, 1)
        extra, extra_by = squeeze, []
        rough = self.route_cells(cid)[1]                         # group 1: zones' and the environment's Difficult Terrain
        n = max(1, int(fs.size_squares(cid) or 1))

        def on_rough(p):
            lo = -(n - 1) / 2
            return any((int(round(p[0] / g + lo + a)), int(round(p[1] / g + lo + b))) in rough
                       for a in range(n) for b in range(n))
        for i in range(len(route) + 1):
            kind = None
            if i < len(route):
                who, kind = self.occupant(cid, *route[i])
                if kind == "block":
                    self.refuse("%s is in the way of %s." % (who, name)); return False
                if kind == "difficult":
                    extra += 1
            if rough and kind != "difficult" and on_rough(route[i] if i < len(route) else (x, y)):
                extra += 1
            if wet and wet[i]:
                extra += water_extra * (math.ceil(sq - 0.000001) if not route else 1)
            extra_by.append(extra - squeeze)
        feet = math.ceil(sq + extra - 0.000001) * units
        if feet <= 0:
            self.sim.say("chat", "%s is already there." % name)
            return True
        moved = t["moved"]
        if wet:
            for i in range(len(route) + 1):
                lim = water_speed if wet[i] else speed
                f = math.ceil(step_sq[i] + extra_by[i] + (squeeze if i == len(route) else 0) - 0.000001) * units
                if f > lim - moved:
                    self.refuse("%s would have moved %g ft by step %d (%s); its %s is %d ft." % (
                        name, f + moved, i + 1, "in water" if wet[i] else "on land",
                        "Speed in water" if wet[i] else "Speed on land", lim)); return False
        elif feet > speed - moved:
            self.refuse("%s would move %g ft; it has %g ft of its %d ft Speed left this turn." % (
                name, feet, max(0, speed - moved), speed)); return False
        who, _ = self.occupant(cid, x, y)
        if who:
            self.refuse("%s is in that square (%s cannot end its move there)." % (who, name)); return False
        wanted = {str(d) for d in move.get("opens") or []}
        opens = [d for d in (map_walls.closed_doors(self.sim.walls) if self.sim.walls else []) if d["id"] in wanted]
        here, walked = start, [start]
        party = getattr(self.sim, "party", None)                 # group 1: its Spirit Guardians reach foes as it walks
        guard = party.guardian_foes(cid) if party and cid in getattr(party, "guardians", {}) else None
        for p in route + [(x, y)]:
            for door in sorted({d["id"] for d in opens if map_walls.blocked(here, p, [d["seg"]])}):
                opens = [d for d in opens if d["id"] != door]    # DOORS-01: it opens the door as it reaches it
                self.sim.set_door(self.sim.MAP, door, True)
                label = move.get("opens_name") or "a door"
                self.narrate("%s opens %s." % (name, label))
                event("walls", "door %s (%s) opened by %s" % (door, label, name))
            self.step(cid, p[0] / g, p[1] / g)
            if guard is not None and not fs.down(cid) and cid in party.guardians:
                guard = party.guardians_reach(cid, guard)
            here = (node.px, node.py)
            if here != walked[-1]:
                walked.append(here)
            if fs.down(cid) or fs.turnSerial != t["serial"] or here != p:
                break                       # an opportunity attack dropped it, a trap held it, or its turn ended
        stopped = here != (x, y)
        if stopped:                         # stopped on the way: the feet of the squares it really walked
            feet = ai_turn.route_cost(walked, g, units, diag, 0, pd)
        t["moved"], t["mdiag"] = moved + feet, pd + diag_now
        if stopped and not fs.down(cid) and fs.turnSerial == t["serial"]:
            t["moved"], t["held"] = max(t["moved"], speed), True   # held where it stands: no more movement this turn
        self.sim.say("chat", "%s moves %d ft." % (name, feet))
        return not fs.down(cid) and fs.turnSerial == t["serial"] and here == (x, y)

    def step(self, cid, x, y):
        """One square of a creature's own move; the players' opportunity attacks (gm_mode "suggest") and any
        creature's come first when the step leaves their reach."""
        if self.mode == "suggest":
            self.players_react(cid, x, y)
            if self.fs.down(cid):
                return
        self.fs.step(cid, x, y)
        self.sim.settle()

    def players_react(self, cid, x, y):
        """SRD 5.2.1 Opportunity Attacks for the player characters whose reach this step leaves (the simulator answers
        for them by the scenario's reaction_policy, as a player would on the table)."""
        fs, sc = self.fs, self.sim.sc
        if ai_turn.disengaged(self.normalized(self.sim.by_id(cid))):
            return                                               # Disengage: its move provokes nothing this turn
        g, units, diag = sc.get("grid", 50), sc.get("units", 5), str(sc.get("diag", 1))
        leaving = []
        for o in sc["combatants"]:
            if not o.get("pc") or self.sim.down(o["id"]) or self.side(o["id"]) == self.side(cid):
                continue
            reach = (o.get("weapon") or {}).get("reach", 5) + 0.01
            n = fs._c(o["id"])
            after = self._apart(x * g, y * g, n.px, n.py, g, fs.size_squares(cid), fs.size_squares(o["id"]), diag) * units
            if fs.distance(o["id"], cid) <= reach and after > reach:
                leaving.append(o["name"])
        if leaving:
            self.narrate("%s leaves %s reach: %s may make an opportunity attack." % (
                self.fs.name(cid), " and ".join(n + "'s" for n in leaving), " or ".join(leaving)))
            here = self.fs.state(cid)[2:4]
            w = self.sim.reaction_window(cid, {"provokes": leaving, "source_name": self.fs.name(cid), "seq": self.seq}, here)
            self.sim.settle()
            w["resume"] = ("End turn: %s is at 0 hit points" % self.fs.name(cid) if self.fs.down(cid)
                           else "Continue: %s moves on" % self.fs.name(cid))
            self.sim.say("react", "resume: " + w["resume"])

    # ------------------------------------------------------------------ an attack
    def attack(self, cid, s, multi=False, opportunity=False):
        """One attack: d20 + the attack bonus against AC (fight_state rolls it), the damage on a hit. Checked first: the
        attacker can act and is up, a melee target is within reach (not for an opportunity attack: the mover just
        left it), one Attack action a turn, at most MULTI_MAX Multiattack attacks. Returns the result ("hit", "crit",
        "miss") or None when refused."""
        fs, t = self.fs, self.turn
        name, tid = fs.name(cid), self.by_path(s["target"])
        a = self.action(cid, s["nodepath"])
        if a is None or a.get("atk") is None:
            self.refuse("%s has no attack %s." % (name, s.get("action_name"))); return None
        cond = ai_turn.incapacitating_condition(self.normalized(self.sim.by_id(cid)))
        if cond:
            self.refuse("%s is %s and cannot act." % (name, cond)); return None
        if fs.down(cid):
            self.refuse("%s is at 0 hit points." % name); return None
        if tid not in fs.combatants:
            self.refuse("%s's target is no longer in the fight." % name); return None
        melee = (a.get("atktype") or "melee") != "ranged"
        reach = a.get("reach") or 5
        if melee and not opportunity:
            d = fs.distance(cid, tid)
            if d > reach:
                self.refuse("%s is %d ft away; %s reaches %s ft." % (fs.name(tid), d, a["name"], reach)); return None
        if not opportunity and t:
            if t["attacked"] and not multi and not t["multi_done"]:
                self.refuse("%s already attacked this turn." % name); return None
            if multi and len(t["multi_done"]) >= MULTI_MAX:
                self.refuse("%s already made %d attacks this turn." % (name, len(t["multi_done"]))); return None
        held = self.hold_narration(s)
        roll = {"sType": "attack", "nMod": a["atk"], "sRange": "M" if melee else "R", "sim_action": a.get("name", ""),
                "sim_dmgtype": a.get("dmgtype") or ""}
        if s.get("roll_mode") == "adv":
            roll["bADV"] = True
        elif s.get("roll_mode") == "dis":
            roll["bDIS"] = True
        if multi and t:
            t["multi_done"].append(a["name"])
        what = a["name"] + (" (Multiattack %d of %d)" % (s["multi"]["n"], s["multi"]["of"]) if s.get("multi") else "")
        res = self.strike(cid, tid, roll, self.damage_clauses(a), what)
        if t and not opportunity:
            t["attacked"] = True
        if multi and t:
            t["hits"].append(res in ("hit", "crit"))
            t["targets"].append(s["target"])
            t["items"].append("%s at %s" % (s["action_name"], "itself" if s["target"] == s["source"] else s["target_name"]))
        if held:
            self.narrate(ai_turn.narration_after(held[0], res, held[1], held[2]))
        return res

    def strike(self, cid, tid, roll, clauses, what):
        """One attack roll (fight_state rolls it: Advantage, Disadvantage, cover of conditions, reactions) and on a hit
        its damage at once, before anything the hit sets going. The creature's traits may change the roll first (Pack
        Tactics ...). Returns "hit", "crit" or "miss"."""
        fs = self.fs
        for fn in self.attack_mode:                              # traits that change the roll (Pack Tactics, ...)
            fn(cid, tid, roll)
        self.sim.say("chat", "%s attacks %s with %s." % (fs.name(cid), fs.name(tid), what))
        self.audit_line(cid, tid)
        seen = {}

        def landed(src, tgt, result):
            if src == cid and tgt == tid and "res" not in seen:
                seen["res"] = result.get("sResult")
                if seen["res"] in ("hit", "crit") and clauses:
                    fs.actionRoll(cid, tid, [{"sType": "damage", "clauses": clauses}])
        fs.attackPostResolve.append(landed)
        try:
            fs.actionRoll(cid, tid, [roll])
            self.sim.settle()
        finally:
            fs.attackPostResolve.remove(landed)
        return seen.get("res") or "miss"

    @staticmethod
    def damage_clauses(a):
        """The attack's damage: its dice and modifier of its damage type, plus a second type when it has one
        ("13 (1d10 + 8) Slashing damage plus 5 (2d4) Fire damage"); dice doubled on a Critical Hit by fight_state."""
        dice, mod = _dice(a.get("dmg") or "1d4")
        clauses = [{"dice": dice, "modifier": mod, "dmgtype": a.get("dmgtype") or "", "sim_weapon": bool(a.get("weapon"))}]
        if a.get("dmg2"):
            dice2, mod2 = _dice(a["dmg2"])
            clauses.append({"dice": dice2, "modifier": mod2, "dmgtype": a.get("dmgtype2") or ""})
        return clauses

    def hold_narration(self, s):
        """The model's narration of an attack waits for the roll's result (a miss is never narrated as a hit)."""
        text = s.get("narration")
        if not text:
            return None
        if not ai_turn.holds_narration(s):
            self.narrate(text)
            return None
        return text, {k: s.get(k) for k in ("source", "source_name", "target", "target_name", "action_name", "kind",
                                             "spell", "move_only")}, s.get("narration_miss") or ""

    def audit_line(self, cid, tid):
        """The simulator's wall audit: no attack between two creatures a wall separates."""
        audit = getattr(self.sim, "audit_attack", None)
        if audit:
            audit(cid, tid)

    # ------------------------------------------------------------------ opportunity attacks by creatures
    def on_step(self, cid, x0, y0, x1, y1):
        """A token stepped: when it is the acting creature and leaves the reach of a hostile creature the AI runs (not a
        player character: players choose their own Reactions), that creature may make an opportunity attack, once per
        turn of the mover. It comes before anything else happens (the next step, the mover's attack)."""
        fs = self.fs
        if fs.active()[0] != cid or ai_turn.disengaged(self.normalized(self.sim.by_id(cid))):
            return
        g, units, diag = self.sim.sc.get("grid", 50), self.sim.sc.get("units", 5), str(self.sim.sc.get("diag", 1))
        side, msq = self.side(cid), fs.size_squares(cid)
        for r in list(fs.combatants):
            rside = self.side(r)
            key = (r, cid)
            if r == cid or fs.getValue(r, "pc") or not ((rside == "foe" and side == "friend") or (rside == "friend" and side == "foe")):
                continue
            if self.oa_asked.get(key) == fs.turnSerial or fs.num(r, "reaction") != 0 or fs.num(r, "sim_no_oa") != 0:
                continue
            if fs.stopped(r):
                continue
            n = fs._c(r)
            ring = max(1, math.floor(fs.num(r, "reach", 5) / units + 0.5))
            rsq = fs.size_squares(r)
            before = self._apart(x0, y0, n.px, n.py, g, msq, rsq, diag) <= ring
            after = self._apart(x1, y1, n.px, n.py, g, msq, rsq, diag) <= ring
            if before and not after:
                self.oa_asked[key] = fs.turnSerial
                self.sim.say("chat", "%s leaves %s's reach." % (fs.name(cid), fs.name(r)))
                serial = fs.turnSerial
                self.sim.later.append(lambda r=r, at=(x0, y0), serial=serial: self.opportunity(r, cid, at, serial))

    @staticmethod
    def _apart(ax, ay, bx, by, grid, size_a, size_b, diag):
        dx = max(0, abs(ax - bx) / grid - (size_a - 1) / 2 - (size_b - 1) / 2)
        dy = max(0, abs(ay - by) / grid - (size_a - 1) / 2 - (size_b - 1) / 2)
        dx, dy = math.floor(dx * 1000 + 0.5) / 1000, math.floor(dy * 1000 + 0.5) / 1000
        if diag == "*":
            return math.sqrt(dx * dx + dy * dy)
        hi, lo = max(dx, dy), min(dx, dy)
        return hi + math.floor(lo / 2) if diag == "1.5" else hi

    def opportunity(self, reactor, mover, at, serial):
        """SRD 5.2.1 Opportunity Attacks: one melee attack (its first melee attack in stat-block order) with its
        Reaction, against a creature it can see leaving its reach, during the mover's same turn."""
        fs = self.fs
        rname, mname = fs.name(reactor), fs.name(mover)
        if fs.turnSerial != serial or fs.active()[0] != mover or fs.num(reactor, "reaction") != 0:
            self.sim.say("chat", "%s's opportunity attack is no longer possible." % rname)
            return
        ranked = self.ranked()
        act = ai_turn.opportunity_attack(ranked, self.path(reactor))
        if not act:
            event("ai-reaction", "no melee attack for %s: nothing done" % rname)
            return
        combatants = self.combatants()
        space = self.space(reactor)
        if not ai_turn.oa_sees(space, combatants, self.path(reactor), self.path(mover), at):
            event("ai-reaction", "%s cannot see %s leave its reach: no opportunity attack" % (rname, mname))
            return
        event("ai-reaction", "%s may attack %s (%s): queued" % (rname, mname, act["power_name"]))
        s = {"source": self.path(reactor), "source_name": rname, "target": self.path(mover), "target_name": mname,
             "nodepath": act["node_path"], "action_name": act["power_name"], "kind": "attack", "spell": False}
        res = self.attack(reactor, s, opportunity=True)
        if res is not None:
            fs.setValue(reactor, "reaction", 1)                  # its Reaction until the start of its next turn
            self.sim.say("chat", "%s makes an opportunity attack against %s." % (rname, mname))
            self.narrate("%s makes an opportunity attack against %s." % (rname, mname))
