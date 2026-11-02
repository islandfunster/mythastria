"""The Mythastria simulator: plays a scenario on the fight state in Python (sim/fight_state.py) with the creatures'
turns in Python (sim/creature_turns.py: the planner's choices, the GM's local model or the scripted chooser) and the
party's tactics (sim/party.py). Writes a transcript to sim/runs/. FG-EXIT-01 (2026-10-26): the old way (the FG extension
aibridge.lua on the stand-in FG sim/fake_fg.lua, through lupa, against the old bridge) is in archive/fg_exit_2026-10-26/.

  py sim/run_sim.py sim/scenarios/test/grick_2024.json                 # local model (default qwen3.5 if installed)
  py sim/run_sim.py sim/scenarios/test/grick_2024.json --fake-model    # scripted chooser, repeatable (tests)
  options: --model NAME  --rounds N  --seed N  --instant (dice resolve inside the roll call)  --quiet
  py sim/run_sim.py --from-snapshot mythastria_core/cache/fight_snapshots/<file>.json [--rounds N] [--local-model]
        [--pcs pass|attack]      # v0.7.89: continue a fight saved on the bridge page from its saved turn

Nothing here touches the GM's real settings, logs or plan cache: temporary files only. The rules cache is read
(spell text for the prompt) but not written. Player characters follow the scenario's script; NPCs are run by the AI
in Autopilot. Not FG's rules engine: see sim/README.md for what is and is not simulated."""
import argparse, json, logging, os, random, re, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIM_DIR = ROOT / "sim"
TMP = Path(tempfile.mkdtemp(prefix="mythastria_sim_"))
os.environ.setdefault("MYTHASTRIA_PLANS_FILE", str(TMP / "statblock_plans.json"))
sys.path.insert(0, str(ROOT / "mythastria_core"))

import ai_turn                           # noqa: E402  the planner (legal choices, routes, reach, sight)
import ollama_client                     # noqa: E402
import statblock_ai                      # noqa: E402  (after the environment is set)
import map_walls                         # noqa: E402
import lighting                          # noqa: E402
import map_layers                        # noqa: E402  MAP-LAYERS-01 (sim/map_layers.py)

MAP = "image.id-00001.image"
DEFENSE_FIELDS = ("damageimmunities", "damageresistances", "damagevulnerabilities")
ABILITIES = ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")
_SRD_DEFENSES = None


def srd_defenses(sc):
    """SIM-MECHANICS-01 (a), 2026-10-18: each creature without its own damage defenses takes them from its SRD 5.2.1
    bestiary record (DNDSRD521BESTIARY, the NPC fields FG copies to the Combat Tracker), found by its name without the
    number ("Shadow 2" -> Shadow). A combatant that sets any of the three fields keeps its own; characters and names
    the SRD lacks get nothing. Without the module installed nothing changes."""
    global _SRD_DEFENSES
    if _SRD_DEFENSES is None:
        sys.path.insert(0, str(ROOT / "tools"))
        import bestiary_catalog
        _SRD_DEFENSES = {}
        for r in bestiary_catalog.load_srd():
            f, saves = r["fields"], {}
            for ab in ABILITIES:                                 # SIM-MECHANICS-01 (d): bonus + the save's modifier
                a = (f.get("abilities") or {}).get(ab)
                if isinstance(a, dict):
                    try:
                        saves[ab[:3] + "_save"] = int(a.get("bonus") or 0) + int(a.get("savemodifier") or 0)
                    except ValueError:
                        pass
            _SRD_DEFENSES[r["name"]] = ({k: str(f.get(k) or "") for k in DEFENSE_FIELDS}, saves)
    for c in sc.get("combatants") or []:
        if c.get("pc"):
            continue
        rec = _SRD_DEFENSES.get(c.get("srd_name") or c.get("name", "").rstrip("0123456789").strip())
        if not rec:
            continue
        defenses, saves = rec
        if not any(k in c for k in DEFENSE_FIELDS):
            c.update({k: v for k, v in defenses.items() if v})
        for k, v in saves.items():                               # the scenario's own saves stay
            c.setdefault(k, v)
    return sc


def scenario_walls(scenario):
    """v0.7.76: the scenario's walls as a confirmed map for map_walls (positions in squares, scaled by the grid)."""
    g = scenario.get("grid", 50)
    return {"map": "simulated", "transform": "identity", "image_size": None,
            "open_doors": [str(i) for i in scenario.get("open_doors") or []],
            "locked_doors": [str(i) for i in scenario.get("locked_doors") or []],   # v0.7.95
            "occluders": [{"id": str(w["id"]), "points": [[x * g, y * g] for x, y in w["points"]],
                           "door": bool(w.get("door")), "closed": bool(w.get("closed")),
                           "hidden": False, "single_sided": False, "counterclockwise": False}
                          for w in scenario.get("walls") or []]}


SPELL_WEAPONS = ("Fire Bolt", "Eldritch Blast", "Sacred Flame", "Ray of Frost", "Scorching Ray")
CON_SAVE_CLASSES = ("fighter", "barbarian")


def apply_items(b, level):
    """PARTY-ITEMS (2026-10-18, simulator tests only): add the kit items gained at or below `level` to a built member
    (sim/parties/srd_pregen_items.json). Numbers change in place; behaviour flags stay for the party and the GM rules.
    Pearl of Power: once a day, used between fights, so a fight starts with one more slot of level 3 or lower."""
    kits = json.loads((SIM_DIR / "parties" / "srd_pregen_items.json").read_text(encoding="utf-8"))["kits"]
    items = [it for it in kits.get(b.get("_name", ""), []) if not level or it["level"] <= int(level)]
    if not items:
        return b
    bonus = {}
    for it in items:
        e = it["effect"]
        for key, n in [e["weapon_bonus"]] if "weapon_bonus" in e else []:
            bonus[key] = max(bonus.get(key, 0), n)
        b["ac"] = b.get("ac", 10) + e.get("ac", 0)
        for ab in ("str", "dex", "con", "int", "wis", "cha"):
            if e.get("saves"):
                b[ab + "_save"] = b.get(ab + "_save", 0) + e["saves"]
        if e.get("spell_atk"):
            b["spell_atk"] = b.get("spell_atk", 0) + e["spell_atk"]
            for key in ("weapon", "ranged"):
                if b.get(key) and b[key].get("name") in SPELL_WEAPONS:
                    b[key] = dict(b[key], atk=b[key].get("atk", 0) + e["spell_atk"])
        if e.get("con_score"):
            prof = 2 if (b.get("level") or 1) <= 4 else 3
            mod = b.get("con_save", 0) - (prof if b.get("class") in CON_SAVE_CLASSES else 0)
            gain = max(0, (e["con_score"] - 10) // 2 - mod)
            b["con_save"] = b.get("con_save", 0) + gain
            b["hp"] = b.get("hp", 0) + gain * (b.get("level") or 1)
            if b.get("abilities"):
                b["abilities"] = dict(b["abilities"], con=max(b["abilities"].get("con", 10), e["con_score"]))
        if e.get("potions"):
            b["potions"] = b.get("potions", 0) + e["potions"]
        if e.get("pearl_of_power") and b.get("slots"):
            slots = list(b["slots"])
            slots[min(2, len(slots) - 1)] += 1
            b["slots"] = slots
        for flag in ("periapt", "displacement", "pearl_of_power", "breathes_water", "fly_ft", "water_breathing_potions",
                     "water_breathing_ritual", "free_action", "stealth_boots", "striding", "web_wand"):
            if flag in e:
                b[flag] = e[flag]
        if "swim_ft" in e:
            ft = int(str(b.get("speed", "30")).split()[0]) if e["swim_ft"] == "speed" else e["swim_ft"]
            b["swim_ft"] = max(b.get("swim_ft", 0), ft)
    for key, n in bonus.items():
        w = b.get(key)
        if w:
            dice, _, add = str(w.get("dmg", "1d4")).partition("+")
            b[key] = dict(w, atk=w.get("atk", 0) + n, dmg="%s+%d" % (dice, int(add or 0) + n), magic=n)
    b["items"] = [it["item"] for it in items]
    return b


def apply_party(sc, name, level=None, items=False, extra=None):
    """PARTY-01 (simulator, 2026-10-14): replace the scenario's characters of the same name with a party file's builds (sim/parties/
    <name>.json; id, position and initiative kept), play them with the team tactics (sim/party.py), death saves on.
    PARTY-02: members the scenario lacks join on free squares next to the party (in sight of it, never through a wall);
    level applies each member's "at_level" changes up to that level.
    CHARACTERS-01 (GM 2026-10-21): `extra` adds saved characters, {name: build} made by sim/character_build.py member(),
    at their own level (no at_level, no pregen kit)."""
    path = SIM_DIR / "parties" / (name + ".json")               # SRD-EDITION-01: no party files; saved characters only
    team = json.loads(path.read_text(encoding="utf-8"))["members"] if path.exists() else {}
    extra = extra or {}
    team = {**{n: b for n, b in team.items() if n not in extra}, **extra}
    def build(b):
        b = dict(b)
        for lv, changes in sorted((b.pop("at_level", None) or {}).items(), key=lambda kv: int(kv[0])):
            if level and int(lv) <= int(level):
                b.update(changes)
        if items and member not in extra:                        # PARTY-ITEMS: simulator tests only
            b = apply_items(dict(b, _name=member), level or 1)
            b.pop("_name", None)
        return {k: v for k, v in b.items() if k != "note"}
    placed = set()
    for c in sc["combatants"]:
        b, member = team.get(c.get("name")), c.get("name")
        if b and c.get("pc"):
            for k in [k for k in c if k not in ("id", "name", "side", "pc", "x", "y", "init", "wounds", "mount")]:
                c.pop(k)
            c.update(build(b))
            c["script"] = {"*": ["team"]}
            placed.add(c["name"])
    missing = [n for n in team if n not in placed]
    pcs = [c for c in sc["combatants"] if c.get("pc")]
    if missing and pcs:
        g = sc.get("grid", 50)
        segs = map_walls.blocking_segments(scenario_walls(sc)) if sc.get("walls") else []
        taken = {(c["x"], c["y"]) for c in sc["combatants"]} | {tuple(p) for p in sc.get("wall_cells") or []}
        cx, cy = sum(c["x"] for c in pcs) / len(pcs), sum(c["y"] for c in pcs) / len(pcs)
        def open_to_party(x, y):   # next to a member, with no wall between them and the first member
            return any(max(abs(p["x"] - x), abs(p["y"] - y)) <= 1 for p in pcs) and not (
                segs and map_walls.blocked((pcs[0]["x"] * g, pcs[0]["y"] * g), (x * g, y * g), segs))
        squares = sorted({(p["x"] + dx, p["y"] + dy) for p in pcs for dx in (-1, 0, 1) for dy in (-1, 0, 1)},
                         key=lambda s: ((s[0] - cx) ** 2 + (s[1] - cy) ** 2, s[1], s[0]))
        ids = {c["id"] for c in sc["combatants"]}
        serial = 101
        for n in missing:
            member = n
            spot = next((s for s in squares if s not in taken and open_to_party(*s)), None)
            if spot is None:                                     # play-test 2026-11-02: no one is left out; the nearest free square
                wide = [(pcs[0]["x"] + dx, pcs[0]["y"] + dy) for dx in range(-12, 13) for dy in range(-12, 13)]
                spot = min((s for s in wide if s not in taken and s[0] >= 0 and s[1] >= 0
                            and not (segs and map_walls.blocked((pcs[0]["x"] * g, pcs[0]["y"] * g), (s[0] * g, s[1] * g), segs))),
                           key=lambda s: (s[0] - cx) ** 2 + (s[1] - cy) ** 2, default=None)
            if spot is None:
                raise ValueError("There's no room for %s on this map." % n)
            while "id-%05d" % serial in ids:
                serial += 1
            c = {"id": "id-%05d" % serial, "name": n, "side": pcs[0].get("side", "friend"), "pc": True,
                 "x": spot[0], "y": spot[1]}
            c.update(build(team[n]))
            c.setdefault("init", 10)
            c["script"] = {"*": ["team"]}
            sc["combatants"].insert(len(pcs), c)
            pcs.append(c); taken.add(spot); ids.add(c["id"])
    sc["party_tactics"] = name
    return sc


class Sim:
    MAP = MAP

    def __init__(self, scenario, model, fake_model, seed, instant, quiet):
        self.sc, self.model, self.fake, self.quiet = scenario, model, fake_model, quiet
        import gm_rules as _gm
        _gm.creature_lights(scenario)   # SIM-MECHANICS-01 (d): Azer and Magmin light on maps with lighting
        self.sc['_seed'], self.sc['_instant'] = seed, bool(instant)
        self.progress = 0
        self.rng = random.Random(seed)
        self.lines, self.later = [], []
        self.t0 = time.monotonic()
        self.stalls, self.problems = 0, []
        self.stopped = None
        # SIM-INTERRUPT-01: "gm_mode": "suggest" -> the simulator plays the GM on the bridge page (approves each NPC
        # turn, answers the opportunity-attack pause for the players with an explicit policy, then Continue or End turn)
        self.gm = scenario.get("gm_mode") or "auto"
        self.reaction_policy = dict(scenario.get("reaction_policy") or {})
        self.windows, self.gm_log = [], []
        self.creatures = None
        statblock_ai.AUTO_APPROVE = bool(scenario.get("approve_plans"))   # scenarios may pre-approve model readings
        # v0.7.76: scenario walls, in squares like the positions ("walls": [{"id", "points": [[x, y], ...], "door"}],
        # "open_doors": [ids]). The planner sees them as a confirmed map (map_walls.for_map), so sight, routes and the
        # creatures' moves use them; every token step and attack is audited against them.
        g = scenario.get("grid", 50)
        self.walls = None
        water = [z["rect"] for z in scenario.get("zones") or [] if z.get("kind") == "water"]
        if scenario.get("walls") or water:
            self.walls = scenario_walls(scenario)
        if water:
            # SWIM-01 (2026-10-19): the water zones go to the planner as the map's water areas (squares, inclusive
            # -> pixel edges), so monsters swim at their Swim Speed there (replaces SIM-ESC-06's speed rewrite)
            self.walls["water"] = [[(x1 - 0.5) * g, (y1 - 0.5) * g, (x2 + 0.5) * g, (y2 + 0.5) * g] for x1, y1, x2, y2 in water]
        if self.walls and scenario.get("lighting"):
            # v0.7.81 LIGHT-01: {"ambient", "lights": [{"x", "y"} in squares or "carrier": CT id, "bright_ft", "dim_ft"}]}
            lit = scenario["lighting"]
            self.walls["lighting"] = {"ambient": lit.get("ambient", "bright"), "lights": [
                dict({"bright_ft": l.get("bright_ft", 0), "dim_ft": l.get("dim_ft", 0)},
                     **({"carrier": "combattracker.list." + l["carrier"]} if l.get("carrier") else {"pos": [l["x"] * g, l["y"] * g]}))
                for l in lit.get("lights") or []]}
        self.wall_segs = map_walls.blocking_segments(self.walls) if self.walls else []
        self._real_for_map = map_walls.for_map
        self._real_set_door = map_walls.set_door
        if self.walls:
            map_walls.for_map = lambda m: self.walls if m == MAP else self._real_for_map(m)
            map_walls.set_door = self.set_door   # v0.7.95: an NPC opening a door changes the simulated map
        self.wall_crossings = 0
        self.second_winds = {}
        handler = logging.Handler()
        handler.emit = lambda r: self._bridge_event(r.getMessage())
        import creature_turns
        self._logger = creature_turns.LOG
        self._logger.addHandler(handler)
        self._handler = handler
        srd_defenses(scenario)
        s = self._start(scenario, instant)
        # PARTY-01 (simulator, 2026-10-14): team tactics and death saves for the party (apply_party / --party)
        self.map_walls, self.party, self.gm_rules, self.referee = map_walls, None, None, None
        if scenario.get("party_tactics"):
            import party as party_mod
            self.party = party_mod.Party(self)
            s.reactHit = self.react_hit   # PARTY-01 (Shield, ...), SIM-MECHANICS-01 (d): Parry
            s.inspireMiss = lambda tid, total, ac: self.party.inspire_miss(tid, total, ac)   # PARTY-03
            s.onDamage = lambda tid, amount, crit, was_down: self.party.damaged(tid, amount, crit, was_down)
            s.onAdjust = lambda tid, kind, what: self.party.learn(tid, kind, what)   # SIM-MECHANICS-01 (a)
            s.dodgeHit = lambda tid, src: self.party.dodge_hit(tid, src)   # PARTY-04: Uncanny Dodge
            # CUTTING-WORDS-01: a played Bard's Cutting Words, asked live (the simulator's own party doesn't use it)
            s.cutWords = lambda src, tid, total, ac: (self.live.reactions.cutting_words(src, tid, total, ac)
                                                      if getattr(getattr(self, "live", None), "reactions", None) else 0)
            # SIM-MECHANICS-01 (b): monster Recharge breath and Death Burst, played by the simulator as the GM
            import gm_rules
            self.gm_rules = gm_rules.GmRules(self)
            # play-test 2026-11-02: never a dying character's turn: the run loop ends that one, with its Death Saving Throw
            s.gmTurnStart = lambda tid: bool(self.gm_rules.turn_start(tid)) and not (self.party and self.by_id(tid).get("pc") and self.down(tid))
            s.onDrop = lambda tid: self.gm_rules.on_drop(tid)
            # SIM-MECHANICS-01 (c): conditions (riders on hits, damage taken, every attack's Advantage/Disadvantage)
            s.onHit = lambda src, tid, action, res: self.gm_rules.on_hit(src, tid, action, res)
            s.onHurt = self.on_hurt
            # REFEREE-01: every spell the party (or a creature) casts is checked against its rules; a note is a problem
            import referee
            self.referee = referee.Referee(sim=self)
            s.condMode = lambda src, tid, *roll: self.gm_rules.cond_mode(src, tid, *roll)
            s.fortitude = lambda tid, dmg, radiant, crit: self.gm_rules.fortitude(tid, dmg, radiant, crit)
            s.onAttackRoll = lambda src: self.gm_rules.attack_rolled(src)   # SIM-ENV-03: an attack ends hiding
            import more_spells                                   # SPELL-BATCH-01: Mirror Image
            s.hitRedirect = lambda src, tid: more_spells.hit_redirect(self, src, tid)
            for c in scenario["combatants"]:
                if c.get("pc") and self.down(c["id"]):
                    s.setField(c["id"], "sim_dying", 1)
        # SIM-ENV-01: environment zones (water, currents, silt, shade/sunlight); inert without "zones"
        import environment, escape
        self.env = environment.Environment(self)
        self.escape = escape.Escape(self)                        # SIM-ESC-01: inert without "escape"
        s.extraResist = lambda tid: self.env.extra_resist(tid)
        # GM 2026-10-24 (SRD Group 2): traps and area gear on the map (sim/traps.py); inert without "traps"
        import traps
        self.traps = traps.Traps(self)
        s.holdStep = self.traps.hold_step                        # a creature a trap caught stays where it is
        gm_start = s.gmTurnStart
        s.gmTurnStart = lambda tid: bool(gm_start and gm_start(tid)) or bool(self.traps.npc_turn_start(tid))
        for p in self.traps.problems:
            self.say("turn", p)
        # HAZARDS-01 (GM 2026-10-26): ice, frigid water, wind and rain, contagions, fear (sim/hazards.py); inert without them
        import hazards
        self.hazards = hazards.Hazards(self)
        for p in self.hazards.problems:
            self.say("turn", p)
        if scenario.get("creature_abilities", True):
            import creature_abilities                            # spellcasting, legendary actions, traits
            creature_abilities.attach(self)

    def _start(self, scenario, instant):
        """FG-EXIT-01: the fight state (sim/fight_state.py) and the creatures' turns (sim/creature_turns.py) in Python."""
        import fight_state, creature_turns
        fs = fight_state.FightState(grid=scenario.get("grid", 50), units=scenario.get("units", 5),
                                    diag=scenario.get("diag", 1), instant=bool(instant),
                                    rand=lambda n: self.rng.randint(1, int(n)), say=self.say, later=self.later.append)
        self.S = fs
        fs.tokenMoved = self.token_moved
        for c in scenario["combatants"]:
            fs.addCombatant({k: v for k, v in c.items() if not isinstance(v, (dict, list))})
            for a in c.get("actions", []):
                fs.addAction(c["id"], a)
            for e in c.get("effects", []):
                fs.addEffect(c["id"], e["label"], e.get("active", True))
        self.creatures = creature_turns.CreatureTurns(self)
        return fs

    # -------------------------------------------------------------- the fight state
    def next_actor(self):
        """End the active combatant's turn."""
        self.S.nextActor()

    def set_side(self, cid, side):
        """A combatant changes sides (attitudes: surrendered, befriended)."""
        self.S.setValue(cid, "friendfoe", side)

    def place(self, cid, x, y):
        """Put a token back on square (x, y) without a step (an undone move): no opportunity attack, readied attack or
        wall audit."""
        self.S.place(cid, x, y)

    def set_round(self, n):
        """Set the combat round (directed tests)."""
        self.S.round_n = n

    def roll_for(self, src, tgt, rolls):
        """A creature's attack or damage rolls outside its planned turn (tests, the simulator as GM): [{"sType": "attack",
        "nMod": 4}, {"sType": "damage", "clauses": [{"dice": ["d6"], "modifier": 2, "dmgtype": "fire"}]}]."""
        return self.S.actionRoll(src, tgt, rolls)

    def checkpoint(self):
        """Called by the creatures between their steps; Play live wraps it to freeze or stop a fight."""

    def save_tweak(self, t, ability):
        """A creature's trait on its saving throw (sim/creature_abilities.py: Magic Resistance, Bless on a creature):
        {"adv": the reason, "bless": True}, or {}."""
        ab = getattr(self, "abilities", None)
        return ab.save_tweak(t, ability) if ab else {}

    def save_result(self, t, ok, label):
        """The final result of a saving throw (sim/creature_abilities.py: Legendary Resistance turns a failure into a
        success)."""
        ab = getattr(self, "abilities", None)
        return ab.save_result(t, ok, label) if ab else ok

    def recent_noise(self):
        """Who fought this round or the last (HEAR-01), as combat tracker paths."""
        return self.creatures.recent_noise()

    def awareness(self):
        """(aware, searches, noise) for the record of what a choice changed (Play live's undo)."""
        a = self.creatures.awareness
        return sorted(a["aware"]), sorted(map(repr, a["search"].items())), sorted(map(repr, a["noise"].items()))

    def queued(self):
        """Actions and narration waiting to run: none (the old bridge queued them; the creatures act at once)."""
        return 0

    def decision(self):
        """The latest creature decision record (what it chose, at whom, the route)."""
        return self.creatures.pending

    def scripted_choice(self, options):
        """The scripted chooser: the scenario's named target first ("fake_target"), then a Multiattack attack, then the
        first choice in stat-block order (the planner's own order). Order-independent: the same options give the same
        choice (the old bridge listed equal-ranked actions in a different order each run)."""
        choices = options["choices"]
        want = self.sc.get("fake_target")

        def order(c):
            m = re.search(r"(\d+)$", c.get("node_path") or "")
            move = c.get("move") or {}
            # a creature ability's choice carries its priority (sim/creature_abilities.py: 1 when it does clearly
            # more than the creature's best attack, -1 otherwise); the planner's own choices have none
            return (not (want and c.get("target_name") == want), -int(c.get("priority") or 0), not c.get("multi"),
                    int(m.group(1)) if m else 10 ** 9, c.get("target_name") or "", c.get("target") or "",
                    float(move.get("feet") or 0), json.dumps(move.get("path") or [], default=str))
        pick = min(choices, key=order)
        return {"choice": pick["id"], "reason": "scripted", "narration": ""}

    def audit_attack(self, src, tgt):
        """v0.7.76: an attack between two tokens whose centres a wall separates is a problem."""
        if not self.wall_segs:
            return
        g = self.sc.get("grid", 50)
        pa, pb = self.S.state(src), self.S.state(tgt)
        if map_walls.blocked((pa[2] * g, pa[3] * g), (pb[2] * g, pb[3] * g), self.wall_segs):
            self.wall_crossings += 1
            self.problems.append("%s attacked %s through a wall" % (self.by_id(src)["name"], self.by_id(tgt)["name"]))

    # -------------------------------------------------------------- plumbing
    def say(self, kind, text):
        line = "%6.1fs %-8s %s" % (time.monotonic() - self.t0, kind, text)
        self.lines.append((kind, str(text)))
        if kind in ("dice", "turn") or (kind == "bridge" and str(text).startswith("ai-npc-turn running:")):
            self.progress += 1
        low = str(text).lower()
        if kind == "error" or (kind == "chat" and any(w in low for w in ("blocked", "failed", "not run", "refused"))):
            self.problems.append(str(text))   # v0.7.62 (review of v0.7.61): handler errors count as failures
        if not self.quiet and (kind != "chat" or not self._sync_noise(text)):
            print(line, flush=True)

    def trap_space(self, ctpath, combatants):
        """GM 2026-10-26 (goal 15): the planner's extras for a creature's decision (sim/creature_turns.py adds them to
        the map it plans on): the trap squares it keeps off (sim/creature_traps.py Minds.planner_space)."""
        if not getattr(self, "traps", None) or not self.traps.traps:
            return {}
        raw = (combatants.get(ctpath) or {}).get("raw_fields") or {}
        g = self.sc.get("grid", 50)
        try:
            here = (float(raw["pos.x"]) / g, float(raw["pos.y"]) / g)
        except (KeyError, TypeError, ValueError):
            here = None
        me = str(ctpath).rsplit(".", 1)[-1]
        if not any(c["id"] == me for c in self.sc["combatants"]):
            return {}
        return self.traps.minds.planner_space(me, here)

    def on_hurt(self, src, tid, amount, kinds=""):
        """Damage taken (the fake FG): the referee notes who dealt it (REFEREE-01), then the GM's rules react. kinds: the
        damage types that dealt it ("fire,psychic"; HAZARDS-01: Cackle Fever's laughter is for damage other than Psychic)."""
        if self.referee:
            self.referee.hurt(src, tid, amount)
        self.gm_rules.hurt(src, tid, amount)
        import more_spells                                       # SPELL-EFFECTS-01: fire burns a web; a charm ends
        more_spells.on_hurt(self, src, tid, amount, kinds)
        if getattr(self, "hazards", None):
            self.hazards.hurt(src, tid, amount, kinds)
        if getattr(self, "attitudes", None):                     # GM 2026-10-24: hurting a creature provokes it
            self.attitudes.hurt(src, tid)

    @staticmethod
    def _sync_noise(text):
        return any(str(text).startswith(p) for p in ("Found ", "Prepared ", "Queued ", "Sent ", "Sync", "PARSED_ATTACK input"))

    def token_moved(self, name, x0, y0, x1, y1):
        """A token stepped (pixels): the step's checks, then (Python engine) the creatures whose reach it left."""
        self._step_checks(name, x0, y0, x1, y1)
        if self.creatures:
            cid = next((c["id"] for c in self.sc["combatants"] if c["name"] == name), None)
            if cid:
                self.creatures.on_step(cid, x0, y0, x1, y1)

    def _step_checks(self, name, x0, y0, x1, y1):
        """v0.7.76: every token step is checked against the scenario's blocking walls (closed doors included)."""
        if getattr(self, "live", None):                          # LIVE-PLAY-01 slice 4: a readied attack's trigger
            self.live.actions.on_step(name, x0, y0, x1, y1)
            self.live.layers.on_step(name, x0, y0, x1, y1)       # MAP-LAYERS-01: an independent mount carries its rider
        if getattr(self, "traps", None) and not getattr(self, "_offstage", False):
            self.traps.on_step(name, x0, y0, x1, y1)             # GM 2026-10-24: a trap under the step (sim/traps.py)
        if getattr(self, "party", None) and not getattr(self, "_offstage", False):
            import more_spells                                   # SPELL-EFFECTS-01: Spike Growth, a web, the sleet
            more_spells.on_step(self, name, x0, y0, x1, y1)
        if getattr(self, "hazards", None) and not getattr(self, "_offstage", False):
            self.hazards.on_step(name, x0, y0, x1, y1)           # HAZARDS-01: slippery ice, thin ice
        if self.sc.get("practice"):   # v0.7.89: the practice report lists every step in squares
            g = self.sc.get("grid", 50)
            self.lines.append(("move", "%s steps to square (%g, %g)" % (name, round(x1 / g, 3), round(y1 / g, 3))))
        segs = self.wall_segs
        if getattr(self, "_offstage", False):
            return                                               # SIM-ESC-01: an escaped character leaves the map
        # v0.8.4: a squeezed Large creature's centre may pass over the wall beside a gap (HR-SQUEEZE corner rule)
        c = next((c for c in self.sc["combatants"] if c["name"] == name), {})
        size = max(1, int(round(float(c.get("space") or 5) / self.sc.get("units", 5))))
        if segs and not ai_turn.step_passes((x0, y0), (x1, y1), size, self.sc.get("grid", 50), segs):
            self.wall_crossings += 1
            self.problems.append("%s stepped through a wall: (%g, %g) -> (%g, %g)" % (name, x0, y0, x1, y1))
        # v0.7.79 (field 00:42: a Gobliez ended its move with a wall across its square): a token may not stop where a
        # wall passes within a quarter square of its centre (the planner's rule; standing still is not a move)
        # v0.8.4: a Large creature may pass squeezed (room in one corner of its space); the planner never ends it there
        # (one square: its own test, independent of the planner, as before)
        elif segs and (x1, y1) != (x0, y0) and (map_walls.near((x1, y1), segs, 0.25 * self.sc.get("grid", 50)) if size <= 1
                                                else not ai_turn.has_room((x1, y1), size, self.sc.get("grid", 50), segs)):
            self.wall_crossings += 1
            self.problems.append("%s stopped inside a wall: (%g, %g)" % (name, x1, y1))

    def _bridge_event(self, msg):
        if msg.startswith(("ai-", "rules ", "narration ")):   # the creatures' log (sim/creature_turns.py): decisions
            self.say("bridge", msg)

    def react_hit(self, tid, total, ac, crit, melee=True, src=None):
        """A hit and the target's Reaction is free: the party's (Shield, Defense), else a monster's (Parry).
        SPELL-BATCH-02: a character played at the table is asked whether it casts Shield (sim/live_reactions.py)."""
        live = getattr(self, "live", None)
        if live and getattr(live, "reactions", None):
            got = live.reactions.shield_hit(tid, total, ac, crit, src)
            if got:
                return got
        bonus, lasting = self.party.react_hit(tid, total, ac, crit)
        if bonus or not self.gm_rules:
            return bonus, lasting
        return self.gm_rules.react_hit(tid, total, ac, bool(melee), src), False

    def step(self):
        """Run the queued callbacks (landed dice, an opportunity attack a step provoked). True when something happened."""
        did = False
        if self.later:
            fns, self.later[:] = list(self.later), []
            for fn in fns:
                fn()
            did = True
        return did

    def settle(self, seconds=5.0):
        """Let whatever was queued run (e.g. an opportunity attack during a player's turn) and the dice land, as happens
        while a real player takes their time."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            busy = self.step()
            queued = bool(self.queued())
            if not busy and not queued:
                return
            if not busy:
                self.idle()

    def calm(self):
        """GM 2026-10-26 (sim/scenes.py): a fight ended and the encounter goes on as a scene: no combatant is active and
        nothing queued for that fight runs later (a creature's turn under way is dropped; the next fight starts afresh)."""
        self.creatures.turn, self.creatures.pending = None, None
        self.later[:] = []
        for c in self.sc["combatants"]:
            self.S.setValue(c["id"], "active", 0)

    def idle(self):
        """Nothing to do for a moment (a dice roll landing on the next step)."""
        time.sleep(0.05)

    # -------------------------------------------------------------- the fight
    def by_id(self, ctid):
        return next(c for c in self.sc["combatants"] if c["id"] == ctid)

    def down(self, ctid):
        w, hp, *_ = self.S.state(ctid)
        return hp and w >= hp

    def corpse(self, c):
        """GM 2026-10-24: "corpses become barriers. They should not block movement or targeting". A dead creature is an
        object, not a creature: it neither blocks nor slows a mover, and a move may end on it. A creature at 0 HP is dead
        (SRD 5.2.1 monsters die at 0 HP); a character at 0 HP is dying (Unconscious, still a creature) until the death
        saves say dead."""
        if not self.down(c["id"]):
            return False
        if not c.get("pc"):
            return True
        party = getattr(self, "party", None)
        return bool(party and party.deaths.get(c["id"], {}).get("dead"))

    def side_down(self, side):
        members = [c["id"] for c in self.sc["combatants"] if (c.get("side") or "") == side]
        return members and all(self.down(m) for m in members)

    def sees(self, viewer, target, at=None):
        """v0.7.81: the same sight rule as the bridge (lighting.py) for scripted player characters. SIM-INTERRUPT-01:
        at = the target's square (x, y) to judge instead of where it stands now."""
        s, g = self.S, self.sc.get("grid", 50)
        if getattr(self, "env", None) and self.env.blocks_sight(viewer, target, at):
            return False                                         # SIM-ENV-01: Heavily Obscured (silt)
        if getattr(self, "gm_rules", None) and self.gm_rules.has(target, "Invisible") and \
                not self.gm_rules.has(target, "Outlined") and \
                not map_layers.sees_invisible(self, viewer, target):  # SPELL-CASTER-01: Faerie Fire, Starry Wisp
            return False                                         # SIM-ENV-03: hidden; MAP-LAYERS-01: Truesight, Blindsight
        pos = lambda i: (at[0] * g, at[1] * g) if (i == target and at) else (s.state(i)[2] * g, s.state(i)[3] * g)
        lit = (self.walls or {}).get("lighting")
        if not lit:
            return not (self.wall_segs and map_walls.blocked(pos(viewer), pos(target), self.wall_segs))
        lights = [{"pos": pos(l["carrier"].rsplit(".", 1)[1]) if l.get("carrier") else tuple(l["pos"]),
                   "bright": l["bright_ft"] / self.sc.get("units", 5) * g, "dim": l["dim_ft"] / self.sc.get("units", 5) * g,
                   "dir": l.get("dir")} for l in lit["lights"]]   # LIGHTS-01: a Bullseye Lantern's Cone
        dv = lighting.darkvision_ft(self.by_id(viewer).get("senses")) / self.sc.get("units", 5) * g
        bs = lighting.blindsight_ft(self.by_id(viewer).get("senses")) / self.sc.get("units", 5) * g   # v0.7.92
        t = self.by_id(target)   # v0.7.91: more than half of the target's space (lighting.space_ft)
        side = lighting.space_ft(t.get("size"), t.get("space")) / self.sc.get("units", 5) * g
        v = self.by_id(viewer)   # v0.8.4: Blindsight from the edge of the viewer's space (GM 2026-10-15)
        vside = lighting.space_ft(v.get("size"), v.get("space")) / self.sc.get("units", 5) * g
        return lighting.can_see(pos(viewer), pos(target), {"ambient": lit["ambient"], "lights": lights}, self.wall_segs,
                                dv, side, bs, vside, g)

    def sees_square(self, viewer, x, y):
        """VIEW-01 (2026-10-20, the table's fog of war): whether the viewer sees square (x, y), by the same rules as
        sees() for a one-square target there: walls and closed doors, light, darkvision, Blindsight, heavy
        obscurement. Hidden creatures are a matter for sees(), not for the square."""
        s, g = self.S, self.sc.get("grid", 50)
        if getattr(self, "env", None) and self.env.blocks_sight(viewer, viewer, (x, y)):
            return False
        here, there = (s.state(viewer)[2] * g, s.state(viewer)[3] * g), (x * g, y * g)
        lit = (self.walls or {}).get("lighting")
        if not lit:
            return not (self.wall_segs and map_walls.blocked(here, there, self.wall_segs))
        u = self.sc.get("units", 5)
        pos = lambda i: (s.state(i)[2] * g, s.state(i)[3] * g)
        lights = [{"pos": pos(l["carrier"].rsplit(".", 1)[1]) if l.get("carrier") else tuple(l["pos"]),
                   "bright": l["bright_ft"] / u * g, "dim": l["dim_ft"] / u * g, "dir": l.get("dir")} for l in lit.get("lights") or []]
        v = self.by_id(viewer)
        dv = lighting.darkvision_ft(v.get("senses")) / u * g
        bs = lighting.blindsight_ft(v.get("senses")) / u * g
        vside = lighting.space_ft(v.get("size"), v.get("space")) / u * g
        return lighting.can_see(here, there, {"ambient": lit["ambient"], "lights": lights}, self.wall_segs, dv, g, bs,
                                vside, g)

    def light_level(self, i):
        """SIM-ENV-03: the light where a creature stands (lighting.DARK 0, DIM 1, BRIGHT 2); bright without lighting."""
        lit = (self.walls or {}).get("lighting") or (self.sc.get("lighting") if not self.walls else None)
        if not lit:
            return lighting.BRIGHT
        s, g, u = self.S, self.sc.get("grid", 50), self.sc.get("units", 5)
        pos = lambda k: (s.state(k)[2] * g, s.state(k)[3] * g)
        lights = []
        for l in lit.get("lights") or []:
            if l.get("carrier"):
                where = pos(str(l["carrier"]).rsplit(".", 1)[-1])
            elif "pos" in l:
                where = tuple(l["pos"])
            else:
                where = (l["x"] * g, l["y"] * g)
            lights.append({"pos": where, "bright": l["bright_ft"] / u * g, "dim": l["dim_ft"] / u * g, "dir": l.get("dir")})
        if getattr(self, "lights", None) and self.lights.in_darkness(pos(i)):
            return lighting.DARK                                 # LIGHTS-01: "nonmagical light can't illuminate" Darkness
        return lighting.level_at(pos(i), {"ambient": lit.get("ambient", "bright"), "lights": lights}, self.wall_segs or ())

    def pc_attack(self, ctid):
        """v0.7.81: a scripted PC attacks the nearest living foe within its weapon's reach (the player's choice in FG),
        with Advantage/Disadvantage from sight (SRD 5.2.1 "Unseen Attackers and Targets")."""
        c, s, g = self.by_id(ctid), self.S, self.sc.get("grid", 50)
        w = c.get("weapon") or {}
        me = s.state(ctid)
        foes = []
        for o in self.sc["combatants"]:
            if o.get("side") == c.get("side") or self.down(o["id"]):
                continue
            st = s.state(o["id"])
            sq = max(abs(st[2] - me[2]), abs(st[3] - me[3]))
            blocked = self.wall_segs and map_walls.blocked((me[2] * g, me[3] * g), (st[2] * g, st[3] * g), self.wall_segs)
            if sq * self.sc.get("units", 5) <= w.get("reach", 5) + 0.01 and not blocked:
                foes.append((sq, o["id"]))
        if not foes:
            self.say("turn", c["name"] + " has no foe within reach")
            return
        tid = sorted(foes)[0][1]
        mode = lighting.attack_mode(self.sees(ctid, tid), self.sees(tid, ctid))
        dmg = w.get("dmg", "1d4")
        dice, bonus = (dmg.split("+", 1) + ["0"])[:2]
        s.pcAttack(ctid, tid, w.get("atk", 0), w.get("crit", 20), dice, int(bonus), mode, w.get("graze", 0))

    # -------------------------------------------------------------- SIM-INTERRUPT-01: the GM and the players' reactions
    def reaction_window(self, ctid, result, start):
        """SRD 5.2.1 Opportunity Attacks: each player whose reach the NPC left may take a Reaction to make one melee
        attack against it. Simultaneous Effects: on the NPC's turn the GM orders them; the simulator's recorded
        order is initiative (highest first). Eligibility is checked again at the window (an earlier reaction may have
        dropped the mover). Each player's answer comes from reaction_policy ("accept" or "pass"; default accept)."""
        s = self.S
        names = result.get("provokes") or []
        window = {"trigger": "%s leaves the reach of %s" % (result.get("source_name"), ", ".join(names)),
                  "mover": result.get("source_name"), "seq": result.get("seq"), "responses": []}
        self.windows.append(window)
        self.say("react", "window: " + window["trigger"])
        for c in sorted((c for c in self.sc["combatants"] if c["name"] in names and c.get("pc")),
                        key=lambda c: -c.get("init", 0)):
            before = int(s.state(c["id"])[4] or 0)
            why = self.oa_ineligible(c, ctid, start)
            if why:
                choice, outcome = "not offered", why
            else:
                asked = self.party.asked_live(c["id"]) if self.party else None
                if asked:                                        # OA-AUTO-01: its player is asked (Auto mode off)
                    choice = "accept" if asked.opportunity(c["id"], ctid) else "pass"
                else:
                    choice = self.reaction_policy.get(c["id"], self.reaction_policy.get("*", "accept"))
                if choice == "accept":
                    s.setField(c["id"], "reaction", 1)
                    outcome = self.pc_opportunity_attack(c["id"], ctid)
                else:
                    choice, outcome = "pass", "no attack; Reaction kept"
            r = {"responder": c["name"], "choice": choice, "reaction_before": before,
                 "reaction_after": int(s.state(c["id"])[4] or 0), "outcome": outcome}
            window["responses"].append(r)
            self.say("react", "%s: %s (Reaction %d -> %d): %s" % (c["name"], choice, before, r["reaction_after"], outcome))
        return window

    def oa_ineligible(self, c, mover, start):
        """Why this player cannot make the opportunity attack now (None: the choice is offered)."""
        s = self.S
        if self.down(c["id"]):
            return "at 0 hit points"
        if int(s.state(c["id"])[4] or 0):
            return "Reaction already used"
        if int(s.getField(c["id"], "sim_no_oa") or 0):      # GM 2026-10-25 (S2): Shocking Grasp (SRD 5.2.1)
            return "Shocking Grasp: no Opportunity Attacks until its next turn"
        effects = [{"label": e["label"], "active": "1" if e.get("active", True) else "0"} for e in c.get("effects") or []]
        cond = ai_turn.incapacitating_condition({"effects": effects})
        if cond:
            return cond
        if self.gm_rules and self.gm_rules.incapacitated(c["id"]):
            return "Incapacitated"
        if self.down(mover):
            return "the mover is already at 0 hit points"
        if not c.get("weapon"):
            return "no melee weapon in the scenario"
        if not self.sees(c["id"], mover, start):
            return "cannot see it leave"
        return None

    def pc_opportunity_attack(self, ctid, tid):
        """One melee weapon attack (the player rolls in FG; here the same dice rules as pc_attack)."""
        c, s = self.by_id(ctid), self.S
        w = c["weapon"]
        dice, bonus = (w.get("dmg", "1d4").split("+", 1) + ["0"])[:2]
        res = s.pcAttack(ctid, tid, w.get("atk", 0), w.get("crit", 20), dice, int(bonus), self.attack_mode_for(ctid, tid), 0)
        w_, hp = s.state(tid)[:2]
        return "%s; %s at %d/%d HP" % (res, self.by_id(tid)["name"], hp - w_, hp)

    def set_door(self, map_name, door_id, is_open):
        """v0.7.95 DOORS-01: the bridge opened (or closed) a door of the simulated map: sight, routes and the wall
        audit use it from now on."""
        if map_name != MAP:
            return self._real_set_door(map_name, door_id, is_open)
        opened = [i for i in self.walls.get("open_doors", []) if i != str(door_id)] + ([str(door_id)] if is_open else [])
        self.walls["open_doors"] = opened
        self.wall_segs = map_walls.blocking_segments(self.walls)
        return self.walls

    def attack_mode_for(self, me, tid):
        return lighting.attack_mode(self.sees(me, tid), self.sees(tid, me))

    def size_sq(self, cid):
        """Squares per side of a creature's space (Large 2), from its "space" in feet."""
        return max(1, int(round(float(self.by_id(cid).get("space") or self.sc.get("units", 5)) / self.sc.get("units", 5))))

    def gap(self, a, b):
        """2026-10-16: squares from the edge of a's space to the edge of b's (adjacent = 1), the bridge's convention since
        v0.8.4 (a Large token sits on a grid corner): centre distance minus the two half-spaces, plus one."""
        s = self.S
        sa, sb = s.state(a), s.state(b)
        return max(abs(sa[2] - sb[2]), abs(sa[3] - sb[3])) - ((self.size_sq(a) + self.size_sq(b)) / 2 - 1)

    def pc_advance(self, ctid, tid=None, reach=None):
        """v0.7.81: a scripted PC walks toward the nearest foe it can see, along the bridge's own path planner (around
        walls, never through creatures), one square per step, up to its speed; it stops when it can attack.
        PARTY-01: or toward a chosen foe (tid) until within reach feet (the party's tactics)."""
        c, s, g = self.by_id(ctid), self.S, self.sc.get("grid", 50)
        units = self.sc.get("units", 5)
        me = s.state(ctid)
        reach = (c.get("weapon") or {}).get("reach", 5) if reach is None else reach
        if tid is None:
            seen = [(self.gap(ctid, o["id"]), o["id"])
                    for o in self.sc["combatants"]
                    if o.get("side") != c.get("side") and not self.down(o["id"]) and self.sees(ctid, o["id"])]
            if not seen:
                self.say("turn", c["name"] + " sees no foe and holds position")
                return
            dist, tid = sorted(seen)[0]
        else:
            dist = self.gap(ctid, tid)
        blocked = self.wall_segs and map_walls.blocked((me[2] * g, me[3] * g), (s.state(tid)[2] * g, s.state(tid)[3] * g), self.wall_segs)
        if dist * units <= reach + 0.01 and not blocked:
            return   # already within reach
        t = s.state(tid)
        occupied = self.occupants(ctid, (ctid, tid))
        speed = c["_speed_now"] if "_speed_now" in c else int(str(c.get("speed", "30")).split()[0])
        if speed <= 0:                                           # SIM-MECHANICS-01 (c): Grappled, Frightened
            self.say("turn", c["name"] + " cannot move this turn")
            return
        move = ai_turn.plan_path_toward((me[2] * g, me[3] * g), (t[2] * g, t[3] * g), occupied, g, units,
                                               self.sc.get("diag", 1), speed, reach, self.size_sq(tid),
                                               self.wall_segs, mover_size=self.size_sq(ctid))
        if not move:
            self.say("turn", c["name"] + " cannot get closer")
            return
        mount = self.env.mount_of(ctid) if getattr(self, "env", None) else None
        if mount:
            self.say("turn", "%s rides %s" % (c["name"], self.by_id(mount)["name"]))
        for x, y in move["path"][1:]:
            s.move(ctid, x / g, y / g)
            for f in self.followers(ctid):
                s.move(f, x / g, y / g)                          # SIM-ENV-04 mount, SIM-ESC-01 a carried friend
            self.settle()

    def occupants(self, ctid, skip):
        if getattr(self, "env", None) and self.env.mount_of(ctid):
            skip = tuple(skip) + (self.env.mount_of(ctid),)      # SIM-ENV-04: a rider never blocks on its own mount
        """2026-10-15: every other creature for the route planner, with SRD 5.2.1 Moving around Other Creatures: allies
        are passed freely, a creature at 0 HP (Unconscious) or two sizes different as Difficult Terrain, the rest block."""
        s, g, units = self.S, self.sc.get("grid", 50), self.sc.get("units", 5)
        A = ai_turn
        me = self.by_id(ctid)
        rank = lambda c: A.size_rank(c.get("size"), c.get("space", units), units)
        out = []
        for o in self.sc["combatants"]:
            if o["id"] in skip or self.corpse(o):
                continue
            st = s.state(o["id"])
            kind = A.pass_kind(o.get("side") == me.get("side"), bool(self.down(o["id"])), rank(me), rank(o))
            out.append((st[2] * g, st[3] * g, max(1, int(round(o.get("space", units) / units))), kind))
        return out

    def pc_move_to(self, ctid, x, y):
        """PARTY-02: walk a scripted PC to a free square (x, y) along the bridge's path planner (around walls, never
        through creatures), within its speed. True when it got there (nothing moves otherwise)."""
        return self.pc_walk(ctid, x, y) is not None

    def pc_walk(self, ctid, x, y, budget=None):
        """pc_move_to with what is left of the turn's movement (LIVE-PLAY-01): `budget` feet at most (None: the whole
        Speed). Returns the feet spent, or None when it cannot get there (nothing moves)."""
        c, s, g = self.by_id(ctid), self.S, self.sc.get("grid", 50)
        units, me = self.sc.get("units", 5), s.state(ctid)
        speed = c["_speed_now"] if "_speed_now" in c else int(str(c.get("speed", "30")).split()[0])
        if budget is not None:
            speed = min(speed, int(budget))
        if speed <= 0:                                           # SIM-MECHANICS-01 (c): Grappled, Frightened
            return None
        if (int(round(me[2])), int(round(me[3]))) == (x, y):
            return 0
        if self.size_sq(ctid) <= 1:
            # 2026-10-19: the exact-square search. The monsters' planner stops next to a point, so a move could end on
            # an ally's square and a 5-ft step detour out of a foe's reach (found in live play, test_scripted_moves.py)
            route = self.exact_route(ctid, x, y, speed)
            if isinstance(route, str):
                return None
            path, cost = [(px * g, py * g) for px, py in route[0]], route[1]
        else:   # Large and bigger: the bridge planner (footprints, HR-SQUEEZE), never ending in another creature's space
            start, goal = (me[2] * g, me[3] * g), (x * g, y * g)
            occupied, mover = self.occupants(ctid, (ctid,)), self.size_sq(ctid)
            move = ai_turn.plan_path_toward(start, goal, occupied, g, units, self.sc.get("diag", 1), speed, 0, 1,
                                                   self.wall_segs, mover_size=mover)
            path = [tuple(p) for p in move["path"]] if move else [start]
            end = path[-1]
            if end != goal and max(abs(end[0] - goal[0]), abs(end[1] - goal[1])) <= g and not (
                    self.wall_segs and map_walls.blocked(end, goal, self.wall_segs)) and \
                    ai_turn._may_end(goal, occupied, g, mover, self.wall_segs) and \
                    ai_turn.route_cost(path + [goal], g, units, self.sc.get("diag", 1)) <= speed:
                path.append(goal)   # the planner stops next to a point; the last step onto the free square
            if path[-1] != goal:
                return None
            cost = ai_turn.route_cost(path, g, units, self.sc.get("diag", 1))
        for px, py in path[1:]:
            s.move(ctid, px / g, py / g)
            for f in self.followers(ctid):
                s.move(f, px / g, py / g)                        # SIM-ENV-04, SIM-ESC-01
            self.settle()
        return cost

    def npc_walk(self, ctid, path, stop=None):
        """GM 2026-10-25 (rulings P11, M4): a creature the simulator moves outside its planner (fleeing, leaving a Stinking
        Cloud) walks the squares of `path` (its start first); before each step, each player character whose reach it
        leaves may make an Opportunity Attack (reaction_window). Stops if it drops, or (GM 2026-10-27) when stop() turns
        true after an Opportunity Attack (its damage ended the Suggestion it fled by). Returns the squares it walked."""
        s, party, walked = self.S, self.party, 0
        name = self.by_id(ctid)["name"]
        for a, b in zip(path, path[1:]):
            leaving = []
            for o in self.sc["combatants"]:
                if not o.get("pc") or self.down(o["id"]) or o.get("side") == self.by_id(ctid).get("side"):
                    continue                                     # SPELL-EFFECTS-01: an ally (a familiar) provokes no one
                reach = (o.get("weapon") or {}).get("reach", 5) + 0.01
                ox, oy = party.pos(o["id"])
                if party.dist(o["id"], ctid) <= reach and max(abs(ox - b[0]), abs(oy - b[1])) * self.sc.get("units", 5) > reach:
                    leaving.append(o["name"])
            if leaving:
                self.reaction_window(ctid, {"provokes": leaving, "source_name": name, "seq": None}, (a[0], a[1]))
                self.settle()
                if self.down(ctid) or (stop and stop()):
                    return walked
            s.move(ctid, b[0], b[1])
            self.settle()
            walked += 1
        return walked

    def occupied_cells(self, ctid, ignore=()):
        """Every square another creature fills, for ctid's movement: {(x, y): bridge pass kind}. A creature of n squares
        whose centre is at c fills c - (n - 1) / 2 onward (2026-10-19: a Large creature at 9.5 fills 9 and 10; rounding
        the centre put it on 10 and 11). ignore: creatures left out (INVISIBILITY-01: ones the mover doesn't see)."""
        g, out = self.sc.get("grid", 50), {}
        for ox, oy, size, kind in self.occupants(ctid, (ctid,) + tuple(self.followers(ctid)) + tuple(ignore)):
            x0, y0 = int(round(ox / g - (size - 1) / 2)), int(round(oy / g - (size - 1) / 2))
            for i in range(size):
                for j in range(size):
                    out[(x0 + i, y0 + j)] = kind
        return out

    def _route_search(self, ctid, budget, goal=None, ignore=()):
        """Cheapest routes from ctid's square within `budget` feet, by SRD 5.2.1 movement: walls block (a diagonal may
        not cut a wall's corner), an ally's space may be crossed but a hostile creature's may not (one at 0 HP or two
        sizes apart is Difficult Terrain, as the bridge planner counts it). Cost: the map's diagonal rule (bridge
        route_cost). Returns {square: (feet, path)}; with a goal it stops there. Medium and smaller movers."""
        import heapq
        units, g = self.sc.get("units", 5), self.sc.get("grid", 50)
        A, segs, diag = ai_turn, self.wall_segs, self.sc.get("diag", 1)
        me = self.S.state(ctid)
        start = (int(round(me[2])), int(round(me[3])))
        kinds = self.occupied_cells(ctid, ignore)

        def wall(a, b):
            return bool(segs) and map_walls.blocked((a[0] * g, a[1] * g), (b[0] * g, b[1] * g), segs)

        def cost_of(path, extra):
            return A.route_cost([(p[0] * g, p[1] * g) for p in path], g, units, diag, extra)

        avoid, rubble = self.traps.route_cells(ctid) if getattr(self, "traps", None) else (set(), set())   # sim/traps.py
        if getattr(self, "hazards", None):
            rubble = rubble | self.hazards.difficult_cells(ctid)     # HAZARDS-01: slippery ice, swimming in frigid water
        import more_spells
        rubble = rubble | more_spells.difficult_cells(self, ctid)    # SPELL-EFFECTS-01: Web, Spike Growth, Grease...
        best, frontier = {}, [(0, 0, start, (start,), 0)]
        while frontier:
            feet, _, here, path, extra = heapq.heappop(frontier)
            if here in best:
                continue
            best[here] = (feet, list(path))
            if here == goal:
                break
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if not (dx or dy):
                        continue
                    nxt = (here[0] + dx, here[1] + dy)
                    if nxt in best or nxt[0] < -2 or nxt[1] < -2 or nxt[0] > 500 or nxt[1] > 500:
                        continue
                    if wall(here, nxt) or (dx and dy and (wall(here, (here[0] + dx, here[1])) or wall(here, (here[0], here[1] + dy)))):
                        continue
                    kind = kinds.get(nxt)
                    if kind == A.PASS_BLOCK or nxt in avoid:
                        continue
                    ex = extra + (1 if kind == A.PASS_DIFFICULT or nxt in rubble else 0)
                    f = cost_of(path + (nxt,), ex)
                    if f <= budget:
                        heapq.heappush(frontier, (f, len(path), nxt, path + (nxt,), ex))
        return best, kinds, start

    def exact_route(self, ctid, x, y, budget):
        """The cheapest route to exactly square (x, y) within `budget` feet (_route_search), never ending in another
        creature's space. Returns (path in squares, feet) or the reason it cannot be done. LIVE-PLAY-01; scripted party
        moves (pc_walk) since 2026-10-19."""
        goal = (x, y)
        if goal in self.occupied_cells(ctid):
            return "Another creature is in that square: a move cannot end there."
        best, _, _ = self._route_search(ctid, budget, goal)
        if goal in best:
            feet, path = best[goal]
            return path, feet
        return "Cannot get there with %d ft of movement left (walls, creatures or distance)." % budget

    def reach(self, ctid, budget, as_seen=False):
        """2026-10-19 (GM: "the movement spline and area boundaries isn't showing"): every square ctid can end a move on
        within `budget` feet: [[x, y, feet, previous x, previous y]], the previous square giving the route back.
        as_seen (INVISIBILITY-01): as ctid knows the map, an Invisible creature it doesn't see leaves no gap there (a move
        into its space is still refused when it is made)."""
        gm = getattr(self, "gm_rules", None)
        ignore = [o["id"] for o in self.sc["combatants"] if as_seen and gm and o["id"] != ctid
                  and gm.has(o["id"], "Invisible") and not self.sees(ctid, o["id"])]
        best, kinds, start = self._route_search(ctid, budget, ignore=ignore)
        out = []
        for (x, y), (feet, path) in sorted(best.items()):
            if (x, y) == start or (x, y) in kinds:
                continue
            px, py = path[-2]
            out.append([x, y, feet, px, py])
        return out

    def followers(self, ctid):
        """Who moves with this character: its mount (SIM-ENV-04) and a friend it carries (SIM-ESC-01)."""
        out = []
        if getattr(self, "env", None) and self.env.mount_of(ctid):
            out.append(self.env.mount_of(ctid))
        if getattr(self, "escape", None) and self.escape.carried_by(ctid):
            out.append(self.escape.carried_by(ctid))
        return out

    def pc_move_toward(self, ctid, x, y):
        """SIM-ESC-01: walk (or swim) a character toward a square, as far as this turn's Speed goes, along the bridge's
        path planner. True when it moved."""
        c, s, g = self.by_id(ctid), self.S, self.sc.get("grid", 50)
        units, me = self.sc.get("units", 5), s.state(ctid)
        speed = c["_speed_now"] if "_speed_now" in c else int(str(c.get("speed", "30")).split()[0])
        if speed <= 0:
            return False
        skip = (ctid,) + tuple(self.followers(ctid))
        move = ai_turn.plan_path_toward((me[2] * g, me[3] * g), (x * g, y * g), self.occupants(ctid, skip), g, units,
                                               self.sc.get("diag", 1), speed, 0, 1, self.wall_segs,
                                               mover_size=self.size_sq(ctid))
        start, goal = (me[2] * g, me[3] * g), (x * g, y * g)
        path = [tuple(p) for p in move["path"]] if move else [start]
        end = path[-1]
        taken = any(abs(o[0] - goal[0]) < g / 2 and abs(o[1] - goal[1]) < g / 2 for o in self.occupants(ctid, skip))
        if end != goal and not taken and max(abs(end[0] - goal[0]), abs(end[1] - goal[1])) <= g and not (
                self.wall_segs and map_walls.blocked(end, goal, self.wall_segs)) and                 ai_turn.route_cost(path + [goal], g, units, self.sc.get("diag", 1)) <= speed:
            path.append(goal)   # the planner stops next to a point; the last step onto the square itself
        if len(path) < 2:
            return False
        for px, py in path[1:]:
            s.move(ctid, px / g, py / g)
            for f in self.followers(ctid):
                s.move(f, px / g, py / g)
            self.settle()
        return True

    def second_wind(self, ctid):
        """v0.7.81: 2024 Fighter Second Wind (Bonus Action, 1d10 + Fighter level, uses per scenario) below half HP."""
        c, s = self.by_id(ctid), self.S
        w, hp = s.state(ctid)[0], s.state(ctid)[1]
        left = self.second_winds.setdefault(ctid, c.get("second_wind", 0))
        if left and w * 2 >= hp and w < hp:
            heal = self.rng.randint(1, 10) + c.get("level", 1)
            self.second_winds[ctid] = left - 1
            self.say("dice", "%s uses Second Wind: 1d10 + %d = %d HP (%d/%d HP)" % (c["name"], c.get("level", 1), heal,
                                                                                  hp - s.heal(ctid, heal), hp))

    def run(self, rounds, stall_seconds=None):
        """Play up to `rounds` rounds. stall_seconds: kept for callers; nothing stalls since FG-EXIT-01 (each creature
        turn is played to its end at once; the old bridge's turns could hang waiting for FG)."""
        s = self.S
        self.say("turn", "creatures played by Mythastria (%s; %s)" % (
            "the players react to provoking moves" if self.gm == "suggest" else "Autopilot",
            "scripted chooser" if self.fake else self.model))
        resume = self.sc.get("resume")
        # GM 2026-10-26 (goal 14, sim/scenes.py): a live encounter may start as a social or exploration scene, with no
        # initiative until the GM starts the fight, and goes on as a scene after a fight that ends without a winner
        scenes = getattr(getattr(self, "live", None), "scenes", None) if not resume else None
        while True:
            if scenes and not scenes.hold():
                break                                            # the GM ended the scene
            if resume:   # v0.7.89 practice twin: continue a saved fight at its saved round and turn
                s.resumeCombat(resume["active"], resume["round"], bool(resume.get("skip_current")))
            elif scenes:
                scenes.start_combat()                            # Initiative rolled, with Surprise
            else:
                s.startCombat()
            self.combat(rounds, stall_seconds, resume)
            if not scenes or self.stopped or not scenes.after_fight():
                break
        _, duplicates = self.savage_check()
        if duplicates:
            self.say('error', 'Savage Attacker applied more than once in one turn')

    def combat(self, rounds, stall_seconds, resume=None):
        """The fight's rounds, until it ends (a side down, the rounds run out, the attitudes end it, a stop)."""
        s = self.S
        seen, pc_done = None, False
        att = getattr(self, "attitudes", None)                  # GM 2026-10-24: attitudes and morale (sim/attitude.py)
        hz = getattr(self, "hazards", None)
        while True:
            did = self.step()
            if att:
                att.drain()                                      # the GM's scene choices, on this thread
            if hz:
                hz.drain()                                       # HAZARDS-01: the GM's hazards, on this thread
            ctid, name = s.active()
            rnd = s.round()
            if (ctid, rnd) != seen:
                if self.party and seen and seen[0] and seen[0] != ctid:
                    self.party.turn_ended(seen[0])   # PARTY-04: Spirit Guardians at the end of a foe's turn
                    if self.gm_rules:
                        self.gm_rules.turn_ended(seen[0])   # SIM-MECHANICS-01 (c): Steam Breath's slow
                    if getattr(self, "env", None):
                        self.env.turn_ended(seen[0])        # SIM-ENV-01: currents, breath
                    if getattr(self, "escape", None) and self.escape.active:
                        self.escape.turn_ended(seen[0])     # SIM-ESC-01: exit, delays, the outer winch
                if getattr(self, "traps", None):            # GM 2026-10-24: traps reset, the stone rolls, holds end
                    self.traps.turn_changed(seen[0] if seen and seen[0] and seen[0] != ctid else None, ctid)
                if self.referee:                            # REFEREE-01: conditions past their time must be gone
                    self.referee.turn_changed(seen[0] if seen and seen[0] and seen[0] != ctid else None, ctid)
                seen, pc_done = (ctid, rnd), False
                if att:
                    att.check_morale()
                reason = self.not_simulated(ctid) if rnd <= rounds and not (
                    resume and (rnd, ctid) == (rounds, resume["active"])) else None
                if reason:
                    self.stop(reason); break
            down_pc = self.down_pc()
            if down_pc:
                self.stop(down_pc + " dropped to 0 hit points: death saving throws are not simulated"); break
            esc = getattr(self, "escape", None)
            if esc and esc.active:                               # SIM-ESC-01: the escape ends when everyone is out
                if rnd > rounds or esc.done():
                    self.settle(); break
            elif att and att.over():                             # GM 2026-10-24: no settle while creatures are out
                if not any(o.get("side") == "neutral" and not self.down(o["id"]) for o in self.sc["combatants"]):
                    self.settle()                                # of the fight: the bridge would play them (neutral)
                break
            elif rnd > rounds or self.side_down("foe") and not (att and att.held_any()) or self.side_down("friend"):
                self.settle(); break
            if resume and (rnd, ctid) == (rounds, resume["active"]):
                break   # v0.7.89: --rounds N from a saved turn = N full rotations, back to the saved combatant
            c = self.by_id(ctid)
            if self.down(ctid):
                if self.party and c.get("pc"):
                    if not pc_done:
                        pc_done = True
                        self.party.dying_turn(ctid)   # PARTY-01: a death saving throw, then the turn ends
                        if self.down(ctid):
                            self.next_actor()
                        else:
                            pc_done = False           # play-test 2026-11-02: a natural 20: 1 HP, and the turn goes on
                    continue
                self.say("turn", name + " is down: turn skipped"); self.next_actor(); continue
            if att and not c.get("pc") and (att.rows.get(ctid) or {}).get("status") == "fled" \
                    and att.flee_turn(ctid):                     # GM 2026-10-25 (ruling P11): it Dashes for the edge
                self.next_actor(); continue
            out_of_it = att.sits_out(ctid) if att and not c.get("pc") else None
            if out_of_it:                                        # GM 2026-10-24: Indifferent, surrendered, fled
                self.say("turn", out_of_it); self.next_actor(); continue
            if c.get("pc") and c.get("live") and getattr(self, "live", None):
                if not pc_done:                                  # LIVE-PLAY-01: a person chooses this turn
                    pc_done = True
                    self.live.turn(ctid)
                    self.say("turn", name + " ends the turn (player)")
                    if att and att.over() and getattr(self.live, "scenes", None):
                        break                                    # GM 2026-10-26: the scene goes on; no next turn
                    self.next_actor()
                continue
            if c.get("pc"):
                if not pc_done:
                    pc_done = True
                    self.second_wind(ctid)
                    for act in (c.get("script") or {}).get(str(rnd), (c.get("script") or {}).get("*", [])):
                        if act.startswith("move "):
                            x, y = (float(v) for v in act.split()[1:3]); s.move(ctid, x, y)
                            self.settle()
                        elif act == "advance":
                            self.pc_advance(ctid)
                        elif act == "attack":
                            self.pc_attack(ctid); self.settle()
                        elif act == "team" and self.party:
                            self.party.turn(ctid); self.settle()   # PARTY-01 (simulator, 2026-10-14)
                    self.say("turn", name + " ends the turn (player script)")
                    self.next_actor()
                continue
            # FG-EXIT-01: the creature's turn, in Python (not when the simulator as GM took the turn)
            if not pc_done and self.creatures.is_due(ctid):
                if getattr(self, "live", None) and self.live.hold_turn(ctid):
                    continue                                     # GM-UNDO-01: a fight taken back stood here
                pc_done = True
                if not self.creatures.take_turn(ctid):
                    break                                        # the decision failed: an error, the run stops
            elif not did:
                self.idle()

    def stop(self, reason):
        """v0.7.89: a mechanic the fake FG cannot resolve was reached: stop instead of guessing."""
        self.stopped = reason
        self.say("stop", "NOT SIMULATED: %s. The practice run stops here." % reason)

    def not_simulated(self, ctid):
        """v0.7.89: why this turn cannot be simulated (the saved fight's practice list), or None. A player character
        that only passes reaches nothing; a creature that acts reaches its own unsupported actions and effects and
        those of every living creature hostile to it."""
        p = self.sc.get("practice")
        c = self.by_id(ctid)
        if not p or self.down(ctid) or (c.get("pc") and not c.get("script")):
            return None
        reasons = list(p["blocking"].get(ctid, []))
        for o in self.sc["combatants"]:
            if o.get("side") != c.get("side") and not self.down(o["id"]):
                reasons += [r for r in p["targets"].get(o["id"], []) if r not in reasons]
        return "; ".join(reasons) or None

    def down_pc(self):
        if not self.sc.get("practice"):
            return None
        return next((c["name"] for c in self.sc["combatants"] if c.get("pc") and self.down(c["id"])), None)

    def savage_check(self):
        records = self.S.savageRecords
        used, duplicates = set(), 0
        for record in records:
            key = (record['actor'], record['turn'])
            duplicates += key in used
            used.add(key)
        return len(records), duplicates

    def report(self):
        s = self.S
        out = ["# Simulation: %s" % self.sc.get("name", "scenario"), "",
               "Model: %s. Seed: %s. %s" % ("scripted" if self.fake else self.model, self.sc.get("_seed"),
                                             "Dice resolve instantly." if self.sc.get("_instant") else ""), "",
               "| Combatant | HP left | Position (squares) |", "|---|---|---|"]
        for c in self.sc["combatants"]:
            w, hp, x, y, _ = s.state(c["id"])
            out.append("| %s | %d/%d | (%g, %g) |" % (c["name"], hp - w, hp, x, y))
        if self.sc.get('source_geometry'):
            geo = self.sc['source_geometry']
            out += ["", "Source grid: %s x %s px; offset %s, %s. Simulator positions are normalized cells." % (
                geo['width'], geo['height'], geo['offset_x'], geo['offset_y']),
                "Native alignment and walls are not verified by this rehearsal."]
        if self.walls:
            out += ["", "Walls: %d segments (%d doors, open: %s). Wall crossings (steps or attacks): %d." % (
                len(self.wall_segs), sum(1 for o in self.walls["occluders"] if o["door"]),
                ", ".join(self.walls["open_doors"]) or "none", self.wall_crossings)]
        out += ["", "Stalls: %d. Problems detected: %d." % (self.stalls, len(self.problems))]
        out += ["- " + p for p in self.problems[:20]]
        uses, duplicates = self.savage_check()
        if any(c.get('savage_attacker') for c in self.sc['combatants']):
            out += ["", "Savage Attacker uses: %d. Duplicate uses in one turn: %d." % (uses, duplicates)]
        if self.gm == "suggest":   # SIM-INTERRUPT-01
            out += ["", "## Reaction windows (GM: the simulator, Suggest mode; policy %s)" % (self.reaction_policy or "accept"), ""]
            out += ["- %s -> %s" % (w["trigger"], w.get("resume", "not resumed")) for w in self.windows] or ["- none"]
            for w in self.windows:
                out += ["  - %s: %s, Reaction %d -> %d, %s" % (r["responder"], r["choice"], r["reaction_before"],
                                                              r["reaction_after"], r["outcome"]) for r in w["responses"]]
            out += ["", "Not modelled here: Shield and other spell reactions as a decision window, NPC stat-block "
                    "reactions, Ready, legendary actions. NPC opportunity attacks are approved by the GM at once."]
        import sim_coverage   # v0.8.6 AUDIT-07: what this run did not simulate
        out += [""] + sim_coverage.report_lines(self.sc, [t for _, t in self.lines])
        out += ["", "## Transcript", "", "```"]
        out += ["%-8s %s" % (k, t) for k, t in self.lines if not (k == "chat" and self._sync_noise(t))]
        out += ["```", ""]
        return "\n".join(out)

    def close(self):
        statblock_ai.AUTO_APPROVE = False   # never leaks into anything that runs after the simulator
        map_walls.for_map = self._real_for_map
        map_walls.set_door = self._real_set_door
        self._logger.removeHandler(self._handler)


def pick_model(name):
    models = ollama_client.list_models()
    if name:
        if name not in models:
            raise SystemExit("Model %s is not installed in Ollama (have: %s)" % (name, ", ".join(models)))
        return name
    pref = [m for m in models if m.startswith("qwen3.5")] or models
    if not pref:
        raise SystemExit("No Ollama model found: start Ollama or use --fake-model")
    return pref[0]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("scenario", nargs="?")
    ap.add_argument("--from-snapshot", metavar="FILE", help="continue a saved fight (bridge page: Save this fight)")
    ap.add_argument("--local-model", action="store_true", help="with --from-snapshot: your local Ollama model "
                    "(default there: the scripted chooser)")
    ap.add_argument("--pcs", choices=("pass", "attack"), default="pass",
                    help="with --from-snapshot: player characters pass (default) or attack the nearest foe in reach")
    ap.add_argument("--model"); ap.add_argument("--fake-model", action="store_true")
    ap.add_argument("--rounds", type=int); ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--instant", action="store_true"); ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--stall", type=int, default=200)
    ap.add_argument("--party", metavar="NAME", help="PARTY-01: play the characters as sim/parties/NAME.json with team "
                    "tactics and death saves (e.g. level1_team, srd_pregens)")
    ap.add_argument("--items", action="store_true", help="PARTY-ITEMS: with --party srd_pregens, the members' magic-item "
                    "kits up to the party level (simulator tests only; sim/parties/srd_pregen_items.json)")
    ap.add_argument("--party-level", type=int, metavar="N", help="PARTY-02: with --party, the members' level-N builds "
                    "(each member's at_level changes up to N)")
    ap.add_argument("--openai", metavar="MODEL", help="OPENAI-NPC-01: an OpenAI model (e.g. gpt-5.5) chooses the "
                    "monsters' actions instead of the local Ollama model (simulator only; sends each turn's prompt)")
    ap.add_argument("--effort", default="low", help="with --openai: reasoning effort (low, medium, high)")
    ap.add_argument("--llm-url", metavar="URL", help="LOCAL-LLM-01: a model server on this PC that speaks the "
                    "OpenAI-compatible API (LM Studio http://127.0.0.1:1234/v1, Ollama http://127.0.0.1:11434/v1); "
                    "--model names the model there")
    ap.add_argument("--reasoning", choices=["none", "low", "medium", "high"], help="thinking for an LM Studio model (2026-10-16): none = off, like the live bridge on Ollama; omitted = the model's own default (Gemma 4 thinks first)")
    a = ap.parse_args(argv)
    if bool(a.scenario) == bool(a.from_snapshot):
        ap.error("give a scenario file or --from-snapshot FILE")
    if a.from_snapshot:
        return practice_run(a)
    sc = json.loads(Path(a.scenario).read_text(encoding="utf-8"))
    if a.party:
        apply_party(sc, a.party, a.party_level, items=a.items)
    a.instant = a.instant or bool(sc.get("instant"))
    sc["_seed"], sc["_instant"] = a.seed, a.instant
    model = "scripted" if a.fake_model else pick_model(None if a.llm_url else a.model)
    real_choose = ollama_client.choose
    if a.llm_url and not a.fake_model:
        import local_llm_chooser   # LOCAL-LLM-01: the bridge's chooser answers with a local model server
        if not a.model:
            ap.error("--llm-url needs --model (the model's name on that server)")
        ollama_client.choose = local_llm_chooser.make_choose(a.llm_url, a.model, reasoning=a.reasoning)
    if a.openai and not a.fake_model:
        import openai_chooser   # OPENAI-NPC-01: the bridge's chooser answers with the OpenAI model
        ollama_client.choose = openai_chooser.make_choose(a.openai, a.effort)
    sim = Sim(sc, model, a.fake_model, a.seed, a.instant, a.quiet)
    try:
        sim.run(a.rounds or sc.get("rounds", 3), 20 if a.fake_model else a.stall)
    finally:
        sim.close()
        ollama_client.choose = real_choose
    if a.llm_url and not a.fake_model:
        st = local_llm_chooser.STATS
        print("Local model %s at %s: %d calls (%d failed), %d prompt + %d completion tokens, %.0f s" % (
            a.model, a.llm_url, st["calls"], st["failures"], st["prompt_tokens"], st["completion_tokens"], st["seconds"]))
    if a.openai and not a.fake_model:
        st = openai_chooser.STATS
        print("OpenAI %s: %d calls (%d failed), %d input + %d output tokens, %.0f s" % (
            a.openai, st["calls"], st["failures"], st["input_tokens"], st["output_tokens"], st["seconds"]))
    text = sim.report()
    runs = SIM_DIR / "runs"; runs.mkdir(exist_ok=True)
    out = runs / ("%s_%s.md" % (Path(a.scenario).stem, time.strftime("%Y%m%d_%H%M%S")))
    out.write_text(text, encoding="utf-8")
    print("\nTranscript: %s  (stalls %d, problems %d)" % (out.relative_to(ROOT), sim.stalls, len(sim.problems)))
    return sim


def practice_run(a, out_dir=None):
    """v0.7.89 PRACTICE-TWIN-01: continue a saved fight from its saved turn; report to mythastria_core/cache/practice_runs
    (local only). Nothing is written back to Fantasy Grounds."""
    if str(SIM_DIR) not in sys.path:
        sys.path.insert(0, str(SIM_DIR))
    import practice
    try:
        snap = practice.fight_snapshot.load(a.from_snapshot)
        sc = practice.to_scenario(snap, a.pcs)
    except (OSError, ValueError) as error:
        raise SystemExit("Practice run not started: %s" % error)
    rounds = a.rounds or 3
    sc["_seed"], sc["_instant"] = a.seed, a.instant
    say = (lambda *_: None) if a.quiet else print
    say("Saved fight: " + practice.fight_snapshot.summary(snap)[0])
    say("Not simulated (listed before the run):")
    for line in practice.not_simulated_lines(sc):
        say("  - " + line)
    model = pick_model(a.model) if a.local_model else "scripted"
    sim = Sim(sc, model, model == "scripted", a.seed, a.instant, a.quiet)
    try:
        sim.run(sc["resume"]["round"] + rounds, a.stall if a.local_model else 20)
        text = practice.report(sim, Path(a.from_snapshot).name, snap, rounds, model)
    finally:
        sim.close()
    out_dir = Path(out_dir) if out_dir else ROOT / "mythastria_core" / "cache" / "practice_runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / ("%s_run_%s.md" % (Path(a.from_snapshot).stem, time.strftime("%Y%m%d_%H%M%S")))
    out.write_text(text, encoding="utf-8")
    say("\n%s\nReport (local only): %s  (stalls %d, problems %d)" % (
        ("Stopped: " + sim.stopped) if sim.stopped else "Finished.", out, sim.stalls, len(sim.problems)))
    say(practice.NO_WRITE_BACK)
    sim.report_path = out
    return sim


if __name__ == "__main__":
    s = main()
    sys.exit(1 if (s.stalls or s.problems) else 0)
