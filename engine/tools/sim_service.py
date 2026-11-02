"""MERGE-01 step 4 B (GM 2026-10-19: "build the simulator as a local service first (play without FG, the path to the Rust
engine)"): the simulator as a loopback service for the Isles Table client.

First increment: a session plays one simulator fight when it starts (the simulator decides everything, as in
tools/sim_messages.py) and the service reveals it one turn per request, in the shared format sim-messages/1
(docs/development/SIM_MESSAGES.md). The protocol is the one later increments keep when characters' choices are added:
a session id, a revision that every step must name, stale or repeated requests refused with nothing spent.

Security, as the AI Bridge: 127.0.0.1 only; the Host header must be 127.0.0.1:<port>; a request with another Origin is
refused; every write is a POST with the session token (new at every start); scenarios by name from sim/scenarios
only (no paths); bounded sizes and counts. The table's pages are served from the same origin (--table), so the browser
needs no cross-origin access.

STAGE-01 (GM 2026-10-19: "I only have one computer ... FG is too slow ... I like the [Isles Table] app. Let's just add
it there"): the service also holds one Stage for the table (rules: sim/stage.py). POST /api/stage applies a command
for a seat; POST /api/stage/state is a seat's view. Hotseat on one PC: the page names the seat and only the "GM" seat is
the Director; seats are not authenticated people (that waits for multiplayer).

DICE-TOOL-01 + TABLE-CHAT-01 (GM 2026-10-19: a dice tool; a small chat window with every roll, its outcome and who
rolled; a private roll only the GM sees): one table chat (sim/table_chat.py). POST /api/chat posts a typed line (text,
a picture or music link, /r, /gmr, /help), POST /api/roll a roll from the dice buttons (private: true for the GM only;
sim/dice_tool.py, the system's secure random), POST /api/chat/log is what one seat may see. The service filters per
seat; a page never receives what its seat may not see. A free roll never changes the fight.
CHAT-FUN-01 (GM 2026-10-21: no private messages; "use chat for fun stuff like gifs, sharing music"): POST
/api/chat/share {seat, name, data (base64), caption} shares a picture (5 MB) or an audio file (20 MB) from the PC, known
by its first bytes; it is kept in sim/chat_media under a random name and served at GET /chat-media/<name>.

LIVE-PLAY-01 (GM 2026-10-19: "Use the simulator: let players choose actions in a live fight, starting with weapon
attacks dragged from the sheet, then spells"): POST /api/live/new starts one live fight (sim/live_play.py: the
simulator runs in its own thread and waits on each character's turn), /api/live/state is what the table shows,
/api/live/act sends a choice (attack, move, end) naming fight_id, actor (the snapshot's waiting id), and revision.
All three must identify the current fight/turn; obsolete writes receive 409. The simulator checks every choice against SRD
5.2.1 before rolling; a refusal says why and changes nothing. One live fight at a time; a new one ends the old.
LIVE-UNDO-01: op "undo" asks to take back the turn's last choice when it touched nothing else (offers.undo says whether
it can, and why not); the GM answers with "undo_approve" or "undo_refuse". Any other choice first lets the request lapse.
PLAYTESTER-01 (GM 2026-10-27): /api/live/new takes `live`, the party's characters played at the table; the others play
by the simulator's party tactics (tools/playtester.py: a local model plays one seat, the simulator the rest).

RUST-DEPRECATE-01 (GM 2026-10-20: Python is the sole rules authority): POST /api/characters {op: character_list |
character_roster_load | character_save | character_delete, ...} is the Characters roster, checked by sim/character_roster.py
with the deprecated Rust engine's rules and messages (cases: sim/character_cases.json); artwork from --table's creatures.json.

JOIN-01 (GM 2026-10-21: the handshake connecting players to the engine; chose "over the internet", "GM approves each"):
--players-port opens the players' door, a second loopback listener that never hands out the token: a player asks to
join (POST /api/join), the GM approves on the GM door (POST /api/seats), and the seat ticket then names the seat on the
door's few routes, each answer cut to what that seat may see (tools/table_seats.py; docs/development/JOIN_PROTOCOL.md).

MARKET-01 (GM 2026-10-21: "a marketspace activated only by the DM"; chose carts approved line by line, shops at adventure
places, gold kept here): POST /api/market (sim/market.py). The GM makes shops at the loaded adventures' places, opens one
at a time, sets gold and approves or refuses each cart line; a seat at the players' door sees the open shop and fills and
sends its own character's cart only. Prices are SRD 5.2.1 (sim/srd_market.json); the GM's own lines are homebrew.

PILLARS (GM 2026-10-24: "not all creatures are automatically hostiles"; plan docs/development/ADVENTURE_PILLARS_PLAN.md):
each creature in a live fight has an attitude and a morale rule (sim/attitude.py), prepped in Remix Prep (POST /api/prep,
tools/remix_prep.py, saved with the campaign) and applied when the fight uses the saved Remix; POST /api/live/scene is
the GM's choices in the fight (attitudes, joining, morale suggestions, truce, retreat). Neither is on the players' door.
GM 2026-10-26 (goal 14, sim/scenes.py): /api/live/new takes `scene` (social, exploration or fight): no turns or
initiative until the GM starts the fight (/api/live/scene op fight with the surprised; talk, explore, not_yet), and the
scene goes on after a fight that ends with no winner. In a scene any character of the party acts (focus, check, ...).

  py tools\\sim_service.py --table ..\\isles-table\\dist [--port 8772]
  then open http://127.0.0.1:8772/replay.html (the Stage: http://127.0.0.1:8772/stage.html)
"""
import argparse, copy, json, mimetypes, random, re, secrets, sys, threading, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "sim"), str(ROOT / "mythastria_core")]
SCENARIOS = ROOT / "sim" / "scenarios"
FORMAT = "sim-messages/1"
MAX_SESSIONS, MAX_BODY, MAX_ROUNDS = 4, 4096, 10
# VIEW-01 (2026-10-20): larger bodies only where needed: the GM's map notes (200 notes of up to 2000 characters)
ROUTE_BODY = {"/api/oneshot": 1024 * 1024,                           # ONE-SHOT-01: a whole one-shot
              "/api/characters": 20 * 1024 * 1024,                 # RUST-DEPRECATE-01: up to 100 sheets of 180 kB
              "/api/new": 3 * 1024 * 1024,                          # GM 2026-10-28: Simulator fights' saved sheets
              "/api/live/new": 3 * 1024 * 1024,                     # CHARACTERS-01: saved characters' sheets join a fight
              "/api/adventures/day": 3 * 1024 * 1024,               # GM 2026-10-24: rests (the party's saved sheets)
              "/api/adventures/downtime": 3 * 1024 * 1024,          # GM 2026-10-26: crafting (the party's saved sheets)
              "/api/adventures/check": 3 * 1024 * 1024,             # ENCOUNTER-CHECK-01: the party's saved sheets
              "/api/party": 3 * 1024 * 1024,                        # GM 2026-10-25: the table's party with its saved sheets
              "/api/chat/share": 28 * 1024 * 1024,                  # CHAT-FUN-01: a 20 MB sound file as base64
              "/api/notes/save": 512 * 1024, "/api/import-map": 48 * 1024 * 1024, "/api/import-map/draft": 48 * 1024 * 1024,   # a map file carries its picture
              "/api/flavor/save": 24 * 1024 * 1024,                 # FLAVOR-01: the table's Flavor, paint pictures included
              "/api/map_paint/save": 16 * 1024 * 1024,              # MAP-PAINT-01: the GM's paint over a map
              "/api/atlas/save": 64 * 1024 * 1024,                  # ATLAS-01: a map with its picture
              "/api/atlas/import": 256 * 1024 * 1024}               # ATLAS-01: a whole project's maps in one file
NOTES = ROOT / "sim" / "notes"
CHAT_MEDIA = ROOT / "sim" / "chat_media"                           # CHAT-FUN-01: pictures and sounds shared in the chat
LINEUPS = ROOT / "sim" / "lineups" / "lineups.json"                # Remix Live's saved creature lineups (campaign data)
ADVENTURE_STATE = ROOT / "sim" / "adventures" / "loaded.json"      # ADVENTURE-01: the loaded adventures, reloaded at start
KEEP_DAYS = 14                                                      # JOIN-01 notice: chat media and the stand-in log
FLAVOR = ROOT / "sim" / "flavor"                                    # FLAVOR-01: the table's Flavor (a test port keeps its own file)
MARKET = ROOT / "sim" / "market"                                    # MARKET-01: shops, purses, carts (a test port keeps its own file)
MAX_NOTES, MAX_NOTE_TEXT = 200, 2000
NAME = re.compile(r"^((test|imported|region)/)?[A-Za-z0-9_]+\.json$")       # VIEW-01: imported maps; REGION-01: terrain battles
SEAT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 '\-]{0,39}$")          # a seat or a player's name at the table
STAGE_OPS = {"join", "leave", "discuss", "applaud", "spotlight", "pause", "resume", "stop", "newsession"}
STAGE_LOG = 100                                                     # public Stage lines kept for the page
LIVE_OPS = {"attack", "move", "end", "cast", "dash", "disengage", "dodge", "door", "stand", "drop_prone",                  # slices 1-3
            "help", "hide", "search", "ready", "second_wind", "action_surge", "rage", "lay_on_hands", "grapple", "shove",   # slice 4
            "undo", "undo_approve", "undo_refuse",                        # LIVE-UNDO-01: asked by the player, answered by the GM
            "innate_sorcery", "font_convert", "font_create",              # GM 2026-10-23: the Sorcerer (sim/live_sorcery.py)
            "dragon_wings", "fold_wings",                                 # SORCERER-20: Dragon Wings (sim/live_sorcery.py)
            "use_item",                                                   # GM 2026-10-23: the bag's items (sim/live_items.py)
            "study", "influence",                                         # GM 2026-10-23: sim/live_lore.py
            "ask_gm",                                                     # GM 2026-10-24: Ask the GM (sim/live_asks.py)
            "trap",                                                       # GM 2026-10-24: a known trap or a lock (sim/traps.py)
            "mount", "dismount", "mount_action",                          # MAP-LAYERS-01: Mounted Combat (sim/map_layers.py)
            "mount_consent", "shake", "spirit_strike",                    # GM 2026-10-25: rulings M2, L4; Spiritual Weapon
            "extinguish",                                                # GM 2026-10-26: roll on the ground (Burning)
            "focus", "check",                                            # GM 2026-10-26: a scene's focus, any ability check
            "abjure_foes",                                               # GM 2026-10-26: Abjure Foes (sim/high_levels.py)
            "intimidating_presence", "holy_nimbus",                      # MARTIAL-HIGH (sim/martial_high.py)
            "light",                                                     # LIGHTS-01: torches, lanterns, light spells
            "martial_arts", "flurry", "patient_defense", "step_of_the_wind",   # MONK-01: the Monk (sim/monk.py)
            "superior_defense",                                          # GM 2026-10-28: Superior Defense (Monk 18)
            "merge_shadows", "blink_steps",                              # EPIC-BOONS-01: Night Spirit, Dimensional Travel
            # SPELL-EFFECTS-01 (sim/more_spells.py): a Moonbeam or pack moved, breaking free, the familiar, the undead
            "move_beam", "move_pack", "break_free", "detonate", "familiar_dismiss", "familiar_help", "familiar_follow",
            "command_undead", "command_guard",
            "douse_door"}                                                # SPELL-OBJECTS-01: put out a burning door
SCENE_START = ("fight", "social", "exploration")                         # GM 2026-10-26: how an encounter starts (sim/scenes.py)
ITEM_ID = re.compile(r"^[a-z0-9-]{1,60}$")
METAMAGIC = {"Careful Spell", "Distant Spell", "Empowered Spell", "Extended Spell", "Heightened Spell", "Quickened Spell",
             "Seeking Spell", "Subtle Spell", "Transmuted Spell", "Twinned Spell"}
TRANSMUTE = {"acid", "cold", "fire", "lightning", "poison", "thunder"}
MORE_ATTACKS = tuple("more%d" % n for n in range(1, 19))           # NOTES 7.8: as sim/character_rules.py
LIVE_WEAPONS = {"weapon", "ranged", "offhand", "torch", "unarmed", *MORE_ATTACKS}   # offhand: GM 2026-10-25 (the Light property's extra attack); torch: LIGHTS-01; unarmed: MONK-01


# GM 2026-10-25: maps moved into folders (sim/scenarios/moved.json); the old names still work
try:
    MOVED = json.loads((SCENARIOS / "moved.json").read_text(encoding="utf-8"))["moved"]
except (OSError, ValueError, KeyError):
    MOVED = {}


def scenario_names():
    return sorted([p.name for p in SCENARIOS.glob("*.json") if p.name != "moved.json"]
                  + ["test/" + p.relative_to(SCENARIOS / "test").as_posix() for p in (SCENARIOS / "test").rglob("*.json")]
                  + ["imported/" + p.name for p in (SCENARIOS / "imported").glob("*.json")]
                  + ["region/" + p.name for p in (SCENARIOS / "region").glob("*.json")]      # REGION-01: terrain battles
                  + ["sites/" + p.relative_to(SCENARIOS / "sites").as_posix() for p in (SCENARIOS / "sites").rglob("*.json")])   # MAPGEN-02


_CREATURES = None


def creature_names():
    """VIEW-01: the creatures with a simulator stat block (an imported map is peopled with one of them)."""
    global _CREATURES
    if _CREATURES is None:
        import creature_threat
        _CREATURES = creature_threat.library()
    return _CREATURES


def pregens():
    return []     # SRD-EDITION-01 (GM 2026-11-01): no test characters; every party is saved characters


def top_level():
    return 20

INFLUENCE_MODES = {"deception", "intimidation", "performance", "persuasion", "animal_handling"}


class Service:
    """The sessions, independent of HTTP (the same object runs under the tests). One fight is played at a time."""

    def __init__(self, recorder=None, clock=None, adventure_packs=None):
        import stage
        self.sessions, self.order = {}, []
        self.lock = threading.Lock()
        self.play = threading.Lock()
        self.panic, self.panic_kept, self.turn_timer = False, {}, True   # GM 2026-11-01: the Panic Button, the turn timer
        self.by_srd = False                                         # BY-THE-SRD-01: the GM's By the SRD switch
        self.timeline, self.fight_start = None, None                # GM-UNDO-01: a fight's steps, and what it began from
        self.rewinding, self.rewind_thread = False, None
        self.recorder = recorder
        self.clock = clock or time.time
        self.stage, self.stage_log, self.stage_n = stage.new(), [], 0
        self.rng = random.SystemRandom()                            # free rolls: the OS's secure random
        self.dice = lambda sides: self.rng.randint(1, sides)
        self.notes_dir = NOTES                                       # VIEW-01: the GM's map notes
        self.atlas_dir = None                                        # ATLAS-01: the map database (tools/atlas.py; tests set a folder)
        self.lineups_file = LINEUPS                                  # Remix Live: saved creature lineups
        self.scenarios_dir, self.table_dir = SCENARIOS, None         # VIEW-01: where an imported map is written
        self.llm_url, self.llm_model = "http://127.0.0.1:1234/v1", "google/gemma-4-12b-qat"   # MAPGEN-02: LM Studio designs sites
        self.site_designer = None                                    # MAPGEN-02: tests give a stand-in for the model
        import rules_monitor                                         # RULES-MONITOR-01: LM Studio watches every action
        self.monitor = rules_monitor.Monitor(lambda msgs: rules_monitor.ask_model(msgs, self.llm_url, self.llm_model))
        self.roster, self.roster_lock = None, threading.Lock()      # RUST-DEPRECATE-01: the Characters roster
        import table_chat
        self.chat = table_chat.new()
        self.model_talk, self.model_loaded = [], False           # CHAT-MODEL-01: the GM's talk with the loaded model
        self.chat_media_dir = CHAT_MEDIA
        self.live, self.live_scenario = None, None
        self.unloaded_pack = None
        self.adventure_state = None                                  # ADVENTURE-01: a file to remember loaded packs in
        import rests                                                 # GM 2026-10-24: the adventure day (sim/rests.py),
        # GM 2026-10-25: a test service (its own --adventure-state) keeps its own days; the table's stay in days/
        self.days = rests.Days(lambda: (Path(self.adventure_state).parent / ("days" if Path(self.adventure_state).stem == "loaded"
                                        else Path(self.adventure_state).stem + "_days")) if self.adventure_state else None)
        import director
        self.director = director.Director()                          # GUEST-DIRECTOR-01: who runs the GM console
        import table_seats
        self.seats = table_seats.Seats(self.clock, self.notice_version)   # JOIN-01: players who asked to join, and their seats
        import dm_handoff
        self.handoff = dm_handoff.Handoff(self.clock)              # DM-SWAP-01: a player asks to be the GM; the GM takes it back
        import door_guard
        self.door_guard = door_guard.DoorGuard(self.clock)           # BETA-B: limits and the door log
        import door_watch
        self.door_watch = door_watch.Watch(self.clock)               # CHEAT-LOG-01: what the door refused, by seat
        import table_flavor
        self.flavor = table_flavor.FlavorStore(FLAVOR / "flavor.json")   # FLAVOR-01 (main() gives a test port its own file)
        import map_paint
        self.map_paint = map_paint.MapPaint(FLAVOR / "map_paint.json")   # MAP-PAINT-01 (a test port keeps its own file)
        import market
        self.market = market.Market(MARKET / "market.json")          # MARKET-01 (main() gives a test port its own file)
        import downtime
        self.downtime = downtime.Ledger(MARKET / "downtime.json")    # GM 2026-10-26: crafting projects (likewise)
        self._market_places = (None, {})
        from adventure_packs import Packs
        from remix_service import Remix
        self.packs = Packs(adventure_packs)
        self.one_shots_dir = Path(__file__).resolve().parent.parent / "sim" / "one_shots"   # ONE-SHOT-01: the GM's, on this PC
        self.remix = Remix(packs=self.packs)
        import encounter_check                                   # ENCOUNTER-CHECK-01: the GM's winnable check
        self.checks = encounter_check.Checks()

    def _record(self, scenario, members, level, items, rounds, seed, extra=None):
        if self.recorder:
            return self.recorder(scenario, members, level, items, rounds, seed, *([extra] if extra else []))
        # 2026-10-20 (GM: "The simulator stopped: URLError ... [WinError 10060]"): a Simulator fights recording runs in its
        # own process. In this one it shared the bridge's state with a Play live fight, and the two fights collided.
        import subprocess, sys, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "recording.json"
            source = SCENARIOS / scenario
            if scenario.startswith("pack/"):
                source = Path(tmp) / "scenario.json"
                source.write_text(json.dumps(self.raw_scenario(scenario)), encoding="utf-8")
            cmd = [sys.executable, str(ROOT / "tools" / "sim_messages.py"), str(source), "--level", str(level or 5),
                   "--members", ",".join(members), "--rounds", str(rounds), "--seed", str(seed), "--out", str(out)]
            if items:
                cmd.append("--items")
            if extra:                                            # GM 2026-10-28: the saved characters
                (Path(tmp) / "extra.json").write_text(json.dumps(extra), encoding="utf-8")
                cmd += ["--extra", str(Path(tmp) / "extra.json")]
            run = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=900)
            if run.returncode or not out.exists():
                raise RuntimeError("The simulator could not record the fight: " + (run.stderr.strip().splitlines() or ["no output"])[-1])
            messages = json.loads(out.read_text(encoding="utf-8"))
            if messages and messages[0].get("type") == "scenario":
                messages[0]["source_scenario"] = scenario
            return messages

    def available_scenarios(self):
        return sorted((set(scenario_names()) - self.packs.legacy_names()) | set(self.packs.names()))

    def scenario_aliases(self):
        """Old names -> the names to use: maps moved into folders (MOVED), and an adventure's own maps (its pack)."""
        out = {k: v for k, v in MOVED.items()}
        out.update(self.packs.aliases())
        return out

    def scenario_tree(self):
        """GM 2026-10-25: the map pickers' folders and subfolders (tools/scenario_folders.py)."""
        import scenario_folders
        return scenario_folders.tree(self.available_scenarios(), self.packs.folders(), self.raw_scenario)

    def raw_scenario(self, name):
        return self.packs.scenario(name) if name.startswith("pack/") else json.loads((SCENARIOS / name).read_text(encoding="utf-8"))

    def check_new(self, req):
        scenario = str(req.get("scenario", ""))
        scenario = self.scenario_aliases().get(scenario, scenario)
        if scenario not in self.available_scenarios():
            raise ValueError("Unknown scenario (use a name from /api/hello).")
        members = req.get("members") or []
        if not isinstance(members, list) or len(members) > 7 or any(m not in pregens() for m in members):
            raise ValueError("Choose saved characters.")
        level = req.get("level")
        if members and not (isinstance(level, int) and 1 <= level <= top_level()):   # 2026-10-26: the heroes reach 20
            raise ValueError("Level 1-%d with members." % top_level())
        rounds, seed = req.get("rounds", 3), req.get("seed", 1)
        if not (isinstance(rounds, int) and 1 <= rounds <= MAX_ROUNDS) or not isinstance(seed, int):
            raise ValueError("Rounds 1-%d and an integer seed." % MAX_ROUNDS)
        return scenario, members, level if members else None, bool(req.get("items")), rounds, seed

    def new(self, req):
        args = self.check_new(req)
        # GM 2026-10-28 ("I only want to use characters saved in the saved characters tab"): Simulator fights takes the
        # saved characters' sheets (`characters`), each at its own level, as Play live does
        extra = self.saved_characters(req, args[1]) if req.get("characters") else None
        if not extra and not args[1]:
            raise ValueError("Choose the party: tick your Saved characters.")
        if extra and not args[1]:
            args = args[:2] + (max(b["level"] for b in extra.values()),) + args[3:]
        if not self.play.acquire(blocking=False):
            return 409, {"ok": False, "error": "A fight is being played; try again when it is done."}
        try:
            msgs = self._record(*args, extra=extra)
        finally:
            self.play.release()
        if not msgs or msgs[0].get("format") != FORMAT:
            return 500, {"ok": False, "error": "The simulator produced no recording."}
        sid = uuid.uuid4().hex
        with self.lock:
            self.sessions[sid] = {"messages": msgs, "shown": 2, "revision": 0}
            self.order.append(sid)
            while len(self.order) > MAX_SESSIONS:
                self.sessions.pop(self.order.pop(0), None)
        return 200, {"ok": True, "session": sid, "revision": 0, "messages": msgs[:2], "done": len(msgs) <= 2,
                     "authority": "simulator (Mythastria sim/)"}

    def step(self, req):
        sid, rev = str(req.get("session", "")), req.get("revision")
        with self.lock:
            s = self.sessions.get(sid)
            if not s:
                return 404, {"ok": False, "error": "No such session (it may have been replaced by newer ones)."}
            if rev != s["revision"]:
                return 409, {"ok": False, "error": "Stale step: that turn was already shown.", "revision": s["revision"]}
            nxt = s["messages"][s["shown"]:s["shown"] + 3]
            if not nxt:
                return 200, {"ok": True, "revision": s["revision"], "messages": [], "done": True}
            s["shown"] += len(nxt)
            s["revision"] += 1
            return 200, {"ok": True, "revision": s["revision"], "messages": nxt, "done": s["shown"] >= len(s["messages"])}

    def messages(self, req):
        with self.lock:
            s = self.sessions.get(str(req.get("session", "")))
            if not s:
                return 404, {"ok": False, "error": "No such session."}
            return 200, {"ok": True, "revision": s["revision"], "messages": s["messages"][:s["shown"]],
                         "done": s["shown"] >= len(s["messages"])}

    # ------------------------------------------------------------------ STAGE-01: one Stage for the table
    @staticmethod
    def check_seat(req):
        seat = req.get("seat")
        if not isinstance(seat, str) or not SEAT.match(seat):
            raise ValueError("A seat is GM or a player's name (letters, digits, spaces, ' and -; up to 40).")
        return seat

    @staticmethod
    def check_stage_cmd(cmd):
        if not isinstance(cmd, dict) or cmd.get("op") not in STAGE_OPS:
            raise ValueError("Unknown Stage command.")
        cid = cmd.get("id")
        if not isinstance(cid, str) or not 0 < len(cid) <= 64:
            raise ValueError("A Stage command needs an id.")
        out = {"id": cid, "op": cmd["op"]}
        if "to" in cmd:
            if not isinstance(cmd["to"], str) or not SEAT.match(cmd["to"]):
                raise ValueError("Name a player at the table.")
            out["to"] = cmd["to"]
        if "reason" in cmd:
            if not isinstance(cmd["reason"], str) or len(cmd["reason"]) > 300:
                raise ValueError("Applause reasons are text up to 300 characters.")
            out["reason"] = cmd["reason"]
        if "on" in cmd:
            out["on"] = cmd["on"] is True
        if "revision" in cmd:
            if not isinstance(cmd["revision"], int):
                raise ValueError("The revision is a number.")
            out["revision"] = cmd["revision"]
        return out

    def _stage_view(self, seat, now):
        import stage
        st, s = self.stage, self.stage["spotlight"]
        v = {"revision": s["revision"], "holder": s["holder"], "discussion": s["discussion"], "running": s["running"],
             "elapsed": stage.elapsed(st, now), "on_air": stage.on_air(st, now), "session": st["session"],
             "participants": sorted(({"name": p["name"], "stage": bool(p.get("stage"))} for p in st["participants"].values()),
                                    key=lambda p: p["name"].lower()),
             "log": list(self.stage_log), "director": seat == "GM"}
        if seat == "GM":
            v["time_report"] = stage.time_report(st, now)
        return v

    def stage_command(self, req):
        import stage
        seat, cmd = self.check_seat(req), self.check_stage_cmd(req.get("cmd"))
        cmd.update(user=seat, name=seat)
        with self.lock:
            now = self.clock()
            ok, pub, priv = stage.apply(self.stage, cmd, now, director=(seat == "GM"))
            if pub:
                self.stage_n += 1
                self.stage_log = (self.stage_log + [{"n": self.stage_n, "text": pub}])[-STAGE_LOG:]
            return 200, {"ok": ok, "public": pub, "private": priv, "stage": self._stage_view(seat, now)}

    # ------------------------------------------------------------------ LIVE-PLAY-01: a fight the players play
    def live_new(self, req, replay=None):
        """A live fight. GM-UNDO-01: `replay` {fight_id, rewinds}: the same fight built again for a rewind."""
        import live_play, run_sim, sim_messages, encounter_tuner
        if replay is None and (self.rewinding or self.panic):
            return 409, {"ok": False, "error": "The GM is taking the fight back; try again in a moment." if self.rewinding else
                         "Everything is stopped: press Resume first."}
        scenario, members, level, items, rounds, seed = self.check_new(dict(req, rounds=req.get("rounds", 10)))
        if "remix_enabled" in req and type(req["remix_enabled"]) is not bool:
            raise ValueError("remix_enabled is true or false.")
        if "scene" in req and req["scene"] not in SCENE_START:  # GM 2026-10-26: a social or exploration scene, or a fight
            raise ValueError("A scene starts as fight, social or exploration.")
        extra = self.saved_characters(req, members)               # CHARACTERS-01: saved characters join too
        if not members and not extra:
            raise ValueError("Choose the party: tick your Saved characters.")
        party = members + list(extra)
        # PLAYTESTER-01 (GM 2026-10-27): `live` names the characters people (or the local-model playtester) play; the
        # others play by the simulator's party tactics. Left out: every character is played at the table, as before.
        played = req.get("live")
        if played is not None and (not isinstance(played, list) or not played or any(n not in party for n in played)):
            raise ValueError("live names the party's characters played at the table (the others play by the simulator).")
        if not members:
            level = max(b["level"] for b in extra.values())      # alone: at their own level
        if not self.play.acquire(blocking=False):
            return 409, {"ok": False, "error": "A fight is being set up; try again in a moment."}
        try:
            raw = self.raw_scenario(scenario)                    # REMIX-02: a pack's map or a built-in one
            remix_meta = None
            if req.get("remix") is not None:                    # REMIX-01, the quick panel: this fight only, first
                import remix, creature_threat
                raw = remix.apply(raw, req["remix"], creature_threat.library())
                remix_meta = {"quick": raw.get("remix")}
            elif req.get("remix_enabled") is True:              # REMIX-02: the campaign's saved Remix (remix.html)
                raw, remix_meta = self.remix.resolve(scenario, raw, req.get("campaign", "default"), level, party)
            if self.live:                                       # a refused remix leaves the running fight alone
                if replay:
                    self.live.on_done = None                     # a rewind is no end of the fight for the adventure's day
                self.live.quit()
                self.live.thread.join(30)
                if self.live.thread.is_alive():                  # never two simulators in one process (they collide)
                    return 409, {"ok": False, "error": "The last fight is still stopping; try again in a moment."}
            if replay:
                self.restore_start()
            else:
                self.remember_start(req, scenario)
            sc = encounter_tuner.with_party(raw, party, level, items=items, extra=extra)
            day = self.day_for_fight(scenario, sc, extra)          # GM 2026-10-24: an adventure's fight starts from its day
            # GM 2026-10-24: each creature's attitude and morale (sim/attitude.py), from the campaign's Remix Prep
            # (tools/remix_prep.py) when its saved Remix is on, before the simulator builds the Combat Tracker
            import attitude, remix_prep
            prep = (remix_prep.for_fight(self.remix, req.get("campaign", "default"), scenario)
                    if req.get("remix_enabled") is True else None)
            # GM 2026-10-25: the campaign's optional rules packs (the Social rules pack's dispositions), Remix on or off
            optional = remix_prep.optional(self.remix, req.get("campaign", "default"))
            if optional:
                sc["optional_rules"] = optional
            if (prep and (prep["scenario"] or prep["levels"] or any(prep["pack"].values()))) or optional.get("social"):
                attitude.apply(sc, prep, level)                  # without prep the fight reads the map's sides
            if req.get("ambient") is not None:                   # LIGHTS-01: the map's own light for this fight
                if req["ambient"] not in ("bright", "dim", "dark"):
                    raise ValueError("ambient is bright, dim or dark.")
                sc["lighting"] = dict(sc.get("lighting") or {"lights": []}, ambient=req["ambient"])
            sim = run_sim.Sim(sc, "scripted", True, seed, True, True)
            self.live_scenario = {"type": "scenario", "format": FORMAT, "source_scenario": scenario, "party": party,
                                  "characters": list(extra),
                                  "level": level, "items": items, "seed": seed, "rounds": rounds, "live": True,
                                  "remix": remix_meta,
                                  "prep": bool(prep and (prep["scenario"] or prep["levels"] or any(prep["pack"].values()))),
                                  "map": sim_messages.map_part(sim.sc)}
            self.unloaded_pack = None
            fight = live_play.LiveFight(sim, rounds=rounds, live_ids=None if played is None else [
                c["id"] for c in sim.sc["combatants"] if c.get("pc") and c["name"] in played],
                ask_reactions=True)                              # SPELL-BATCH-02: screens here answer Reactions
            if getattr(fight, "reactions", None):               # OA-AUTO-01: the GM's Auto mode carries on
                fight.reactions.auto = getattr(self, "reaction_auto", False)
            fight.actions.lore.off = getattr(self, "social_off", False)   # GM 2026-11-01: the Influence buttons carry on
            if "scene" in req:                                   # GM 2026-10-26: scenes (sim/scenes.py); none: a fight as before
                import scenes
                scenes.Scenes(fight, req["scene"])
            fight.market = self.market                           # GM 2026-10-23: the characters' bags (sim/live_items.py)
            fight.monitor = None if replay else self.monitor     # RULES-MONITOR-01: on or off as the GM left it
            fight.timer_on = self.turn_timer                     # GM 2026-11-01: the tracker's turn timer
            fight.by_srd = self.by_srd                           # BY-THE-SRD-01
            fight.on_step = lambda cid, f=fight: self.note_creature(f, cid)   # GM-UNDO-01
            if replay:
                fight.replaying, fight.fight_id, fight.rewinds = True, replay["fight_id"], replay["rewinds"]
            if day:
                self.carry_into(fight, scenario, day)
            self.live = fight.start()
            self.live.wait_ready(120)
        finally:
            self.play.release()
        return 200, {"ok": True, "scenario": self.live_scenario, "live": self.live.snapshot(),
                     "authority": "simulator (Mythastria sim/), SRD 5.2.1 checks in sim/live_play.py"}

    def check_encounters(self, req):
        """ENCOUNTER-CHECK-01 (GM 2026-10-28: "before running a game, the GM can make sure the encounters are winnable";
        "We need characters only for the adventures"): POST /api/adventures/check {pack, characters: [saved sheets],
        campaign}. Every place of the loaded adventure, with the campaign's saved Remix when it fits this party, fought a
        few times by the simulator in a separate process (tools/encounter_check.py); the GM door only. The answer is the
        check's id; /api/adventures/check-status {check} follows it."""
        from remix_service import Conflict
        extra = self.saved_characters(req, [])
        if not extra:
            raise ValueError("Tick the party's saved characters first: the check fights with them.")
        level = max(b["level"] for b in extra.values())
        plan = self.packs.plan(req.get("pack"))
        campaign = req.get("campaign", "default")
        fights, notes, seen = [], [], set()
        for p in plan["places"]:
            if p["scenario"] in seen:
                continue
            seen.add(p["scenario"])
            raw, remix = self.raw_scenario(p["scenario"]), None
            try:                                                  # what Play live would fight: the saved Remix too
                raw, meta = self.remix.resolve(p["scenario"], raw, campaign, level, list(extra))
                remix = bool(meta)
            except Conflict as e:
                notes.append("%s: the map as written (%s)" % (p["place"], e))
            fights.append({"scenario": p["scenario"], "place": p["place"], "raw": raw, "remix": remix})
        if not fights:
            raise ValueError("This adventure has no encounters to check.")
        return {"check": self.checks.start(fights, list(extra), level, extra, notes)}

    @staticmethod
    def saved_characters(req, members):
        """CHARACTERS-01 phase 4 (GM 2026-10-21: "a first rate character builder that can quickly be tested in live"): the
        saved characters sent with a live fight (`characters`: their sheets), each made into a party member by the rules
        authority (sim/character_build.py member()), at its own level. A sheet that can't fight yet is refused, saying what
        it lacks. Names are kept apart from the pregens' (a second "Hero 1" becomes "Hero 1 (2)")."""
        chars = req.get("characters") or []
        if not isinstance(chars, list) or len(chars) + len(members) > 7:
            raise ValueError("Up to 7 characters in all: saved characters and pregens together.")
        import character_build
        out, taken = {}, set(members) | set(pregens())
        for sheet in chars:
            if not isinstance(sheet, dict) or len(json.dumps(sheet)) > 400_000:
                raise ValueError("A saved character is one character sheet (up to 400 kB).")
            name = re.sub(r"\s+", " ", str(sheet.get("name") or "")).strip()[:40] or "Character"
            m = character_build.member(sheet)
            if m["problems"]:
                raise ValueError("%s can't fight yet: %s Fix it on the Characters page." % (name, " ".join(m["problems"])))
            base, n = name, 2
            while name in taken:
                name, n = "%s (%d)" % (base, n), n + 1
            taken.add(name)
            import rests                                         # GM 2026-10-24: Hit Point Dice, Pact Magic (sim/rests.py)
            out[name] = dict(m["build"], **rests.sheet_extras(sheet))
        return out

    # ------------------------------------------------------------------ GM 2026-10-24: rests and the adventure day
    @staticmethod
    def pack_of(scenario):
        return scenario.split("/")[1] if scenario.startswith("pack/") and scenario.count("/") >= 2 else None

    def day_for_fight(self, scenario, sc, extra):
        """A fight on a loaded adventure's map: the party's carried state (sim/rests.py), a rest under way interrupted."""
        import rests
        pack = self.pack_of(scenario)
        if not pack or pack not in self.packs.loaded:
            return None
        with self.days.lock:
            day = self.days.get(pack)
            pcs = [c for c in sc["combatants"] if c.get("pc")]
            rests.ensure(day, {c["name"]: (c, "saved" if c["name"] in extra else "pregen") for c in pcs})
            rests.before_fight(day, [c["name"] for c in pcs])
            rests.prepare_scenario(sc, day)
            self.days.save(pack)
        return day

    def carry_into(self, fight, scenario, day):
        import rests
        pack, sim = day["pack"], fight.sim
        with self.days.lock:
            names = rests.apply_to_sim(sim, day)
        if names:
            sim.say("tactic", "From the adventure day (%s): %s" % (rests.clock_text(day["hour"]), ", ".join(
                "%s %d/%d HP" % (n, day["party"][n]["hp"], day["party"][n]["hp_max"]) for n in names)))

        def done(f):                                             # the fight's thread, when it ends or is stopped
            try:
                with self.days.lock:
                    d = self.days.get(pack)
                    lines = rests.capture(f.sim, d)
                    lines += rests.after_fight(d, [c["name"] for c in f.sim.sc["combatants"] if c.get("pc")], self.dice)
                    d["fights"] = d.get("fights", 0) + 1
                    rests.say(d, "A fight on %s ends: %s." % (scenario.split("/")[-1], ", ".join(lines) or "no characters"))
                    self.days.save(pack)
            except Exception as e:                               # never lose the fight's end over the day's file
                print("The adventure day could not be written back: %s" % e, flush=True)
        fight.on_done = done

    DAY_OPS = {"state", "short", "long", "die", "finish", "interrupt", "stop", "pass", "exhaustion", "reset", "end_fight",
               "restore",                                        # restore: GM 2026-10-25, the GM's full health and rest
               # RESTS-02 (GM 2026-10-26, goal 16): the rest hour by hour, interruptions the day sees, the dying
               "rest_on", "exert", "damage", "death_save", "stabilize", "heal", "cast",
               # HAZARDS-01 (GM 2026-10-26): the environment, contagions, rations, mental stress, travel (sim/hazards.py)
               "environment", "contagion", "cure", "ointment", "rations", "stress", "stress_end", "travel",
               "light"}                                          # LIGHTS-01: douse or light a carried light between fights
    DAY_OPS = DAY_OPS | {"magical_cunning"}                      # CASTER-HIGH: Magical Cunning, Eldritch Master

    def adventure_day(self, req):
        """POST /api/adventures/day {pack, op, members, level, characters: [sheets], ...}: the party's day on the adventure
        home page and its rests. The party is the page's (pregens at its level, saved characters' sheets)."""
        import rests
        op, pack = req.get("op", "state"), req.get("pack")
        if op not in self.DAY_OPS:
            raise ValueError("A day op is one of %s." % ", ".join(sorted(self.DAY_OPS)))
        if not isinstance(pack, str) or pack not in self.packs.loaded:
            raise ValueError("Start the adventure first (its pack is not loaded).")
        members = req.get("members") or []
        if not isinstance(members, list) or any(m not in pregens() for m in members):
            raise ValueError("Members must be pregen names.")
        level = req.get("level", 1)
        if not isinstance(level, int) or isinstance(level, bool) or not 1 <= level <= top_level():
            raise ValueError("Party level 1-%d." % top_level())
        extra = self.saved_characters(req, members)
        builds = {m: (rests.pregen_build(m, level), "pregen") for m in members}
        builds.update({n: (b, "saved") for n, b in extra.items()})
        if op == "end_fight":                                    # the GM ends the fight (the foes fled, the party left)
            if not (self.live and not self.live.done):
                raise ValueError("No fight is running.")
            if not self.play.acquire(blocking=False):
                return 409, {"ok": False, "error": "A fight is being set up; try again in a moment."}
            try:
                self.live.quit()
                self.live.thread.join(30)                        # its end writes the carried state back (carry_into)
            finally:
                self.play.release()
        fight = bool(self.live and not self.live.done)
        import hazards, light_sources
        with self.days.lock:
            day = self.days.get(pack)
            names = rests.ensure(day, builds)
            before = day["hour"]                                 # HAZARDS-01: hours that pass bring their hazards
            try:
                if op in ("short", "long"):
                    rests.start_rest(day, op, names, fight)
                elif op == "die":
                    rests.spend_die(day, str(req.get("name", "")), str(req.get("die", "")), self.dice)
                elif op == "finish":
                    r = day.get("rest") or {}
                    if r.get("kind") == "long":                  # the hours' hazards come before the rest's benefits
                        rests.rest_until(day, names, rests.rest_end(day), self.dice)     # RESTS-02: Trance on the way
                        before = day["hour"]
                    rests.finish_rest(day, {k: req.get(k) for k in ("arcane_recovery", "sorcerous_restoration", "fiendish_resilience",
                                                                    "natural_recovery") if isinstance(req.get(k), dict)})
                    if r.get("kind") == "long":
                        hazards.after_long_rest(day, r.get("names", []), self.dice, day["hour"])
                    else:
                        hazards.advance(day, names, before, day["hour"], self.dice)
                elif op == "interrupt":
                    rests.interrupt(day, req.get("why"))
                elif op == "stop":
                    r, hours = day.get("rest") or {}, req.get("hours")
                    if r and isinstance(hours, (int, float)) and not isinstance(hours, bool) and 0 <= hours <= 24:
                        rests.rest_until(day, names, r["start"] + hours, self.dice)     # RESTS-02: the hours rested
                        before = day["hour"]
                    rests.stop(day, hours, req.get("why"))
                    hazards.advance(day, names, before, day["hour"], self.dice)
                elif op == "rest_on":                            # RESTS-02: the rest goes on N hours
                    r, hours = day.get("rest"), req.get("hours")
                    if not r:
                        raise rests.RestError("No rest is under way.")
                    if not isinstance(hours, (int, float)) or isinstance(hours, bool) or not 0 < hours <= 24:
                        raise rests.RestError("The rest goes on for more than 0, up to 24 hours.")
                    rests.rest_until(day, names, day["hour"] + hours, self.dice)
                elif op in ("exert", "damage", "death_save", "stabilize", "heal", "cast"):
                    self.dying_day_op(op, req, day, names)
                elif op == "pass":
                    rests.pass_time(day, req.get("hours"), req.get("why", ""))
                    hazards.advance(day, names, before, day["hour"], self.dice)
                elif op in self.HAZARD_DAY_OPS:
                    self.hazard_day_op(op, req, day, names, fight)
                elif op == "exhaustion":                         # HAZARDS-01: its own field ("level" is the party's)
                    rests.set_exhaustion(day, str(req.get("name", "")), req.get("exhaustion"), req.get("why", ""))
                elif op == "reset":
                    rests.reset(day)
                    names = rests.ensure(day, builds)
                elif op == "restore":                            # GM 2026-10-25: at the start of a map
                    rests.restore(day, names, fight)
                elif op == "magical_cunning":                    # CASTER-HIGH: the Warlock's 1-minute rite
                    rests.magical_cunning(day, str(req.get("name", "")), fight)
                elif op == "light":                              # LIGHTS-01: between fights, no action cost
                    import requirements as rq
                    who = str(req.get("name", ""))
                    light_sources.day_op(day, who, req.get("n"), req.get("do"),
                                         rq.Bag(who, self.market) if getattr(self, "market", None) is not None else None)
                if day["hour"] > before and op != "reset":
                    light_sources.advance(day, before, day["hour"])   # LIGHTS-01: the hours burn what is lit
            except (rests.RestError, hazards.HazardError, light_sources.LightError) as e:
                return 409, {"ok": False, "refused": str(e), "error": str(e), "day": rests.view(day, names, fight),
                             **({"link": e.link} if getattr(e, "link", None) else {})}
            if op != "state":
                self.days.save(pack)
            return 200, {"ok": True, "day": rests.view(day, names, fight),
                         "authority": "simulator (Mythastria sim/rests.py), SRD 5.2.1 Short Rest and Long Rest"}

    # ------------------------------------------------------------------ GM 2026-10-26 (goal 13): downtime
    DOWNTIME_OPS = {"state", "plan", "start", "work", "look_again", "abandon"}

    def adventure_downtime(self, req):
        """POST /api/adventures/downtime {pack, op, members, level, characters: [sheets], ...}: crafting, brewing and
        scribing between adventures (sim/downtime.py), on the loaded adventure's day. The party is the page's, as for
        the day; gold and bags are the Market's. op plan: the needs of a project ({who, kind, item | spell, base, tool,
        helpers, place, gm_materials, gm_spells, gm_more_helpers}); start; work {days}; look_again {id}; abandon {id}."""
        import downtime, rests
        op, pack = req.get("op", "state"), req.get("pack")
        if op not in self.DOWNTIME_OPS:
            raise ValueError("A downtime op is one of %s." % ", ".join(sorted(self.DOWNTIME_OPS)))
        if not isinstance(pack, str) or pack not in self.packs.loaded:
            raise ValueError("Start the adventure first (its pack is not loaded).")
        members = req.get("members") or []
        if not isinstance(members, list) or any(m not in pregens() for m in members):
            raise ValueError("Members must be pregen names.")
        level = req.get("level", 1)
        if not isinstance(level, int) or isinstance(level, bool) or not 1 <= level <= top_level():
            raise ValueError("Party level 1-%d." % top_level())
        extra = self.saved_characters(req, members)
        builds = {m: (rests.pregen_build(m, level), "pregen") for m in members}
        builds.update({n: (b, "saved") for n, b in extra.items()})
        chars = {n: dict(b, name=n) for n, (b, _) in builds.items()}
        fight = bool(self.live and not self.live.done)
        with self.days.lock, self.downtime.lock:
            day = self.days.get(pack)
            names = rests.ensure(day, builds)
            dt = downtime.Downtime(self.downtime, self.market, chars, day, fight, roll=self.dice)
            out, lines = {"ok": True}, []
            try:
                if op == "plan":
                    out["plan"] = dt.plan(req)
                elif op == "start":
                    _, lines = dt.start(req)
                elif op == "work":
                    lines = dt.work(req.get("days"), names)
                elif op == "look_again":
                    lines = dt.look_again(str(req.get("id", "")))
                elif op == "abandon":
                    lines = dt.abandon(str(req.get("id", "")))
            except downtime.DowntimeError as e:
                return 409, {"ok": False, "refused": str(e), "error": str(e), "downtime": dt.view(names)}
            if op in ("start", "look_again", "abandon"):
                rests.say(day, " ".join(lines))
            if op in ("start", "work", "look_again", "abandon"):
                self.days.save(pack)
            out.update(downtime=dt.view(names), lines=lines, day=rests.view(day, names, fight),
                       authority="simulator (Mythastria sim/downtime.py), SRD 5.2.1 crafting, brewing and scribing")
            if op == "state":
                out["options"] = dt.options()
            return 200, out

    def dying_day_op(self, op, req, day, names):
        """RESTS-02 (GM 2026-10-26, goal 16; sim/rests.py, SRD 5.2.1): walking or toil during a rest {names, hours, why};
        the GM's hazard damage {names, dice, type, why}; a death save {name}; stabilize {name, helper, how: medicine | kit |
        spare}; healing {name, by, item: a potion in by's bag} or {name, hp, why}; a spell cast {name, level, spell, target,
        dice}. Each refusal says why (RestError, answered 409 with the day)."""
        import hazards, rests, requirements as rq
        text = lambda k, most=120: str(req.get(k) or "")[:most]
        who = lambda: [n for n in (req.get("names") if isinstance(req.get("names"), list) else names) if n in names]
        if op == "exert":
            rests.exert(day, who(), req.get("hours"), text("why"))
        elif op == "damage":
            kinds = text("type", 40)
            if kinds and any(k not in self.DAMAGE_TYPES for k in kinds.lower().replace(",", " ").split()):
                raise rests.RestError("A damage type is one of %s." % ", ".join(sorted(self.DAMAGE_TYPES)))
            rests.damage(day, who(), text("dice", 12), kinds, text("why"), self.dice)
        elif op == "death_save":
            rests.death_save(day, text("name", 40), self.dice)
        elif op == "stabilize":
            helper = text("helper", 40)
            bag = rq.Bag(helper, self.market) if getattr(self, "market", None) is not None and req.get("how") == "kit" else None
            rests.stabilize(day, text("name", 40), helper, text("how", 10), self.dice, bag)
        elif op == "heal":
            name, item = text("name", 40), text("item", 40)
            if item:
                from live_items import POTIONS
                if item not in POTIONS:
                    raise rests.RestError("Healing from the bag is a Potion of Healing.")
                by = text("by", 40) or name
                if by not in day["party"]:
                    raise rests.RestError("%s is not in the party." % by)
                bag = rq.Bag(by, self.market) if getattr(self, "market", None) is not None else None
                if bag is not None:
                    ready, rows = rq.check([rq.in_bag(bag, item, POTIONS[item][0])])
                    if not ready:
                        err = rests.RestError(rq.first_why(rows))
                        err.link = rq.first_link(rows)
                        raise err
                rests._alive(day, name)
                pname, dice = POTIONS[item]
                hp = hazards.roll_dice(self.dice, dice)
                if bag is not None:
                    bag.take(item, 1, "on the adventure day, for %s" % name)
                rests.heal(day, name, hp, "%s %s a %s, %s" % (by, "drinks" if by == name else "gives %s" % name, pname, dice))
            else:
                rests.heal(day, name, req.get("hp"), text("why") or "the GM")
        elif op == "cast":
            rests.cast(day, text("name", 40), req.get("level"), text("spell", 60), self.dice, text("target", 40) or None,
                       text("dice", 12))

    DAMAGE_TYPES = {"acid", "bludgeoning", "cold", "fire", "force", "lightning", "necrotic", "piercing", "poison", "psychic",
                    "radiant", "slashing", "thunder"}

    HAZARD_DAY_OPS = {"environment", "contagion", "cure", "ointment", "rations", "stress", "stress_end", "travel"}

    def hazard_day_op(self, op, req, day, names, fight):
        """HAZARDS-01 (GM 2026-10-26): the day's environment, contagions, rations, mental stress and travel (sim/hazards.py,
        SRD 5.2.1). Each refusal says why (HazardError, answered 409 with the day)."""
        import hazards, requirements as rq
        text = lambda k, most=120: str(req.get(k) or "")[:most]
        if op == "environment":
            hazards.set_environment(day, req.get("weather"), req.get("shelter") if isinstance(req.get("shelter"), bool) else None,
                                    req.get("water") if isinstance(req.get("water"), bool) else None)
        elif op == "contagion":
            if req.get("mode", "expose") not in ("expose", "infect"):
                raise hazards.HazardError("A contagion is given with its save (expose) or without (infect).")
            hazards.infect(day, text("name", 40), text("key", 20), self.dice, save=req.get("mode", "expose") == "expose",
                           why=text("why"))
        elif op == "cure":
            hazards.cure(day, text("name", 40), text("key", 20), text("how", 10))
        elif op == "ointment":
            maker, patient = text("maker", 40), text("name", 40)
            bag = rq.Bag(maker, self.market) if getattr(self, "market", None) is not None else None
            ready, rows = rq.check(hazards.ointment_needs(day, maker, patient, bag))
            if not ready:
                err = hazards.HazardError(rq.first_why(rows))
                err.link = rq.first_link(rows)
                raise err
            if fight:
                raise hazards.HazardError("A fight is running: the ointment takes an hour of work after it.")
            start = day["hour"]
            day["hour"] = start + 1
            hazards.advance(day, names, start, day["hour"], self.dice)
            hazards.apply_ointment(day, maker, patient, day["hour"])
        elif op == "rations":
            hazards.set_rations(day, text("name", 40), req.get("water"), req.get("food"))
        elif op == "stress":
            who = req.get("names") if isinstance(req.get("names"), list) else names
            dc = req.get("dc")
            hazards.mental_stress(day, [n for n in who if n in names], self.dice, text("save", 3) or "wis", dc,
                                  text("dice", 12), bool(req.get("half")), text("effect", 12) or "none",
                                  req.get("condition"), req.get("ability"), text("why"))
        elif op == "stress_end":
            hazards.end_stress(day, text("name", 40), req.get("n"), text("how", 10))
        elif op == "travel":
            if fight:
                raise hazards.HazardError("A fight is running: end it before the party travels on.")
            weather = req.get("weather")
            if weather is not None and (not isinstance(weather, list) or any(w not in hazards.WEATHER for w in weather)):
                raise hazards.HazardError("Weather is a list of %s." % ", ".join(sorted(hazards.WEATHER)))
            hazards.travel(day, names, self.dice, req.get("hours"), text("pace", 8), req.get("today_before", 0),
                           req.get("today_after", 0), weather=weather,
                           water=req.get("water") if isinstance(req.get("water"), bool) else None,
                           fast=bool(req.get("fast")), where=text("where", 80))

    def live_hazards(self, req):
        """HAZARDS-01 (GM 2026-10-26): the GM's hazards in the running fight (not on the players' door). op: catalog, weather
        {weather}, place {kind, squares, weights?}, remove {zone}, fear {targets, dc, source, why}, stress {targets, save, dc,
        dice, half, effect, condition, ability, why}, contagion {target, key, mode}, carrier {creature, key, on}. Run on the
        fight's thread (sim/hazards.py Hazards.drain)."""
        import hazards
        op = req.get("op")
        if op == "catalog":
            return 200, dict(hazards.catalog(), ok=True)
        if op not in ("weather", "place", "remove", "fear", "stress", "contagion", "carrier"):
            raise ValueError("A hazards op is catalog, weather, place, remove, fear, stress, contagion or carrier.")
        if len(json.dumps(req)) > 20000:
            raise ValueError("A hazard is a short description.")
        if not self.live or self.live.done:
            return 404, {"ok": False, "error": "No live fight: start one."}
        cmd = {k: req[k] for k in ("op", "weather", "kind", "squares", "weights", "zone", "targets", "dc", "source", "why",
                                   "save", "dice", "half", "effect", "condition", "ability", "target", "key", "mode",
                                   "creature", "on") if k in req}
        out = hazards.of(self.live.sim).submit(cmd)
        if not out.get("ok"):
            return 409, dict(out, live=self.live.snapshot(0))
        with self.live.lock:
            self.live.revision += 1
            self.live._publish_locked()
        return 200, dict(out, live=self.live.snapshot(req.get("since", 0) if isinstance(req.get("since", 0), int) else 0))

    def live_light(self, req):
        """LIGHTS-01 (GM 2026-10-26): POST /api/live/light {ambient}: the GM sets the map's own light in the running fight
        (bright, dim or dark; not on the players' door). The lights themselves are the characters' choices (op "light")."""
        import light_sources
        if not self.live or self.live.done:
            return 404, {"ok": False, "error": "No live fight: start one."}
        try:
            self.live.lights.set_ambient(req.get("ambient"))
        except light_sources.LightError as e:
            return 409, {"ok": False, "refused": str(e), "error": str(e)}
        with self.live.lock:
            self.live.revision += 1
            self.live._publish_locked()
        return 200, {"ok": True, "live": self.live.snapshot(req.get("since", 0) if isinstance(req.get("since", 0), int) else 0)}

    def remix_offer(self, req):
        """REMIX-01 (GM 2026-10-20: "As long as the encounters are customizable and recommendations are offered by Remix
        then it's okay to attach."): a map's encounter, substitutes for each kind, quick remixes and every creature the
        simulator can play, for the Remix panel on Play live. Estimates by XP and measured threat; nothing is changed."""
        import remix, creature_threat
        scenario, members, level, _, _, seed = self.check_new(dict(req, rounds=1))   # the same checks as a fight
        # GM 2026-10-28 ("I imported a character but cannot include it in a play live remix fight"): the saved characters
        # ticked for the fight count too, each at its own level (party_levels)
        saved = req.get("party_levels") or []
        if not isinstance(saved, list) or len(saved) > 8 or not all(
                isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 20 for v in saved):
            raise ValueError("party_levels: the saved characters' levels, 1-20 each (up to 8).")
        levels = [level] * len(members) + saved if saved else None
        level = (round(sum(levels) / len(levels)) if levels else level) or 1   # the measured threat's level
        size = len(levels) if levels else len(members) or 4
        lib = creature_threat.library()
        sc = self.raw_scenario(scenario)                         # a pack's map too (REMIX-02)
        enc = remix.encounter(sc, lib, size, level, levels)
        recs = {k["name"]: remix.recommend(k["name"], lib, level) for k in enc["kinds"] if k["in_library"]}
        every = sorted(({"name": n, "xp": int(b.get("xp") or 0), "cr": b.get("cr")} for n, b in lib.items()),
                       key=lambda c: (c["xp"], c["name"]))
        return 200, {"ok": True, "scenario": scenario, "encounter": enc, "recommendations": recs,
                     "suggestions": remix.suggest(sc, lib, size, level, seed, levels), "creatures": every,
                     "foe_start": remix.foe_start(sc), "map_size": list(remix._extent(sc)), "max_count": remix.MAX_COUNT,
                     "note": "Estimates (XP and measured threat). The map file is never changed; a remix applies to one fight."}

    def lineups(self, req):
        """Remix Live's creature lineups (2026-10-21): {op: list | save | load | delete, name, creatures: [{name, count}]}.
        A lineup is the creatures of a fight by kind, saved by name and loaded onto any map by the panel. Only SRD 5.2.1
        library creatures, checked on saving and again on loading (a name no longer in the library is refused)."""
        import remix, creature_threat
        op, lib = req.get("op"), creature_threat.library()
        if op not in ("list", "save", "load", "delete"):
            raise ValueError("A lineup op is list, save, load or delete.")
        f, out = Path(self.lineups_file), {"ok": True}
        with self.lock:
            try:
                saved = json.loads(f.read_text(encoding="utf-8")).get("lineups", []) if f.is_file() else []
            except (OSError, ValueError):
                raise ValueError("The saved lineups (%s) can't be read." % f)
            if op != "list":
                name = remix.lineup_name(req.get("name"))
                found = next((l for l in saved if l["name"].lower() == name.lower()), None)
                if op != "save" and not found:
                    raise ValueError("No lineup is saved as %s." % name)
            if op == "load":
                missing = [c["name"] for c in found["creatures"] if c["name"] not in lib]
                if missing:
                    raise ValueError("%s can't be loaded: %s is no longer in the SRD 5.2.1 creature library."
                                     % (found["name"], ", ".join(missing)))
                out["lineup"] = {"name": found["name"], "creatures": remix.check_lineup(found["creatures"], lib)}
            elif op in ("save", "delete"):
                saved = [l for l in saved if l is not found]
                if op == "save":
                    if len(saved) >= remix.MAX_LINEUPS:
                        raise ValueError("At most %d lineups: delete one first." % remix.MAX_LINEUPS)
                    saved.append({"name": name, "creatures": remix.check_lineup(req.get("creatures"), lib),
                                  "saved": time.strftime("%Y-%m-%d %H:%M")})
                f.parent.mkdir(parents=True, exist_ok=True)
                tmp = f.with_suffix(".tmp")
                tmp.write_text(json.dumps({"lineups": saved}, indent=1), encoding="utf-8")
                tmp.replace(f)
        xp = lambda c: int((lib.get(c["name"]) or {}).get("xp") or 0) * c["count"]
        out["lineups"] = [{"name": l["name"], "creatures": l["creatures"], "saved": l.get("saved"),
                           "xp": sum(xp(c) for c in l["creatures"]),
                           "missing": [c["name"] for c in l["creatures"] if c["name"] not in lib]}
                          for l in sorted(saved, key=lambda l: l["name"].lower())]
        return 200, out

    def live_ruling(self, req):
        """GM 2026-10-24: the GM's ruling on a player's Ask the GM request (any time in the fight; not on the players'
        door, which has no such route)."""
        import live_play
        n, text, allow = req.get("n"), req.get("text", ""), req.get("allow", False)
        if not isinstance(n, int) or isinstance(n, bool) or not isinstance(text, str) or len(text) > 300 or not isinstance(allow, bool):
            raise ValueError("A ruling names the request (n) and up to 300 characters of text.")
        if not self.live:
            return 404, {"ok": False, "error": "No live fight."}
        try:
            out = self.live.rule_ask(n, text, allow)
        except live_play.LiveError as e:
            return 409, {"ok": False, "refused": str(e)}
        return 200, dict(out, live=self.live.snapshot(req.get("since", 0) if isinstance(req.get("since", 0), int) else 0))

    def live_reaction_mode(self, req):
        """OA-AUTO-01 (GM 2026-10-28: "Auto mode ... is available for fast live games"): POST /api/live/reaction-mode
        {auto}: the GM's Auto mode on (the engine answers every player Reaction, as for monsters and foes) or off (each
        player is asked). Kept for the next fights until the service restarts; not on the players' door."""
        auto = req.get("auto")
        if not isinstance(auto, bool):
            raise ValueError("auto is true or false.")
        self.reaction_auto = auto
        if self.live and not self.live.done:
            self.live.reactions.set_auto(auto)
        return 200, {"ok": True, "auto": auto,
                     **({"live": self.live.snapshot(req.get("since", 0) if isinstance(req.get("since", 0), int) else 0)}
                        if self.live else {})}

    def live_social(self, req):
        """GM 2026-11-01 ("allow the GM to disable them"): POST /api/live/social {off}: the Influence buttons off or on. Kept for
        the next fights until the service restarts; not on the players' door."""
        off = req.get("off")
        if not isinstance(off, bool):
            raise ValueError("off is true or false.")
        self.social_off = off
        if self.live and not self.live.done:
            self.live.actions.lore.set_off(off)
        return 200, {"ok": True, "off": off,
                     **({"live": self.live.snapshot(req.get("since", 0) if isinstance(req.get("since", 0), int) else 0)}
                        if self.live else {})}

    def live_srd(self, req):
        """BY-THE-SRD-01 (GM 2026-11-02: "Yes, add the switch"): POST /api/live/srd {on}: the table's rulings for Hide and Spirit
        Guardians, or the SRD as written. Kept for the next fights until the service restarts; not on the players' door."""
        on = req.get("on")
        if not isinstance(on, bool):
            raise ValueError("on is true or false.")
        self.by_srd = on
        if self.live and not self.live.done:
            self.live.set_by_srd(on)
        return 200, {"ok": True, "on": on}

    def live_fly(self, req):
        """ON-THE-FLY-01 (GM 2026-11-02): POST /api/live/fly: the GM changes the running fight without starting it again. op:
        creature {name, count, at?, attitude?} joins it (near the foes' start or on a square), announce {text} goes to everyone's
        log, ac {target, ac, why?} sets a creature's AC for this fight (a spell cast between scenes), heal {target, hp} or
        stabilize {target} carries out what a ruling allows, temp {target, hp} gives Temporary Hit Points, check {target,
        skill or ability, roll?, dc?, about?} rolls a character's check in a fight. Traps go through
        /api/live/traps. All are steps on Undo. Never a door route."""
        import creature_threat, live_add, map_import, remix
        if not self.live or self.live.done:
            return 404, {"ok": False, "error": "No fight is running."}
        fight, op = self.live, req.get("op")
        since = req.get("since", 0) if isinstance(req.get("since", 0), int) else 0
        if op == "announce":
            text = req.get("text")
            if not isinstance(text, str) or not text.strip() or len(text) > 2000:
                raise ValueError("Type up to 2,000 characters.")
            fight.sim.say("gm", "GM: " + " ".join(text.split()))    # a location read aloud, a puzzle put to the table
            with fight.lock:
                fight.revision += 1
                fight._publish_locked()
            return 200, {"ok": True, "live": fight.snapshot(since)}
        if op == "ac":                                            # play-test 2026-11-02: a spell cast between scenes (Mage Armor)
            cid, ac, why = req.get("target"), req.get("ac"), req.get("why", "")
            if not isinstance(ac, int) or isinstance(ac, bool) or not 1 <= ac <= 30:
                raise ValueError("An AC is 1 to 30.")
            if not isinstance(why, str) or len(why) > 80:
                raise ValueError("The reason is up to 80 characters.")
            c = next((x for x in fight.sim.sc["combatants"] if x["id"] == cid), None)
            if c is None:
                raise ValueError("Choose a creature in this fight.")
            with fight.lock:
                c["ac"] = ac
                fight.sim.S.setField(cid, "ac", ac)
            fight.sim.say("gm", "GM: %s's AC is %d for this fight%s." % (c["name"], ac, " (%s)" % why.strip() if why.strip() else ""))
            with fight.lock:
                fight.revision += 1
                fight._publish_locked()
            return 200, {"ok": True, "live": fight.snapshot(since)}
        if op == "temp":                                          # play-test 2026-11-02: the finale's 10 Temporary Hit Points
            c = next((x for x in fight.sim.sc["combatants"] if x["id"] == req.get("target")), None)
            hp = req.get("hp")
            if c is None:
                raise ValueError("Choose a creature in this fight.")
            if not isinstance(hp, int) or isinstance(hp, bool) or not 1 <= hp <= 500:
                raise ValueError("Temporary Hit Points are 1 to 500.")
            with fight.lock:
                fight.sim.S.setField(c["id"], "sim_temp_hp", max(hp, int(fight.sim.S.getField(c["id"], "sim_temp_hp") or 0)))
            fight.sim.say("gm", "GM: %s has %d Temporary Hit Points." % (c["name"], hp))
            with fight.lock:
                fight.revision += 1
                fight._publish_locked()
            return 200, {"ok": True, "live": fight.snapshot(since)}
        if op == "check":                                         # play-test 2026-11-02: a check in a fight (a coronation post)
            import scenes
            c = next((x for x in fight.sim.sc["combatants"] if x["id"] == req.get("target") and x.get("pc")), None)
            dc = req.get("dc")
            if c is None:
                raise ValueError("Choose a character in this fight.")
            if dc is not None and (not isinstance(dc, int) or isinstance(dc, bool) or not 1 <= dc <= 40):
                raise ValueError("A DC is 1 to 40.")
            try:
                total, line = (lambda o: (o[1], o[4]))(scenes.roll_check(fight, c["id"], req))
            except scenes.SceneError as e:
                return 409, {"ok": False, "refused": str(e)}
            fight.sim.say("dice", line + (" vs DC %d -> %s" % (dc, "success" if total >= dc else "failure") if dc else ""))
            with fight.lock:
                fight.revision += 1
                fight._publish_locked()
            return 200, {"ok": True, "total": total, "live": fight.snapshot(since)}
        if op in ("heal", "stabilize"):                           # play-test 2026-11-02: a ruling alone changed nothing on the table
            c = next((x for x in fight.sim.sc["combatants"] if x["id"] == req.get("target")), None)
            if c is None:
                raise ValueError("Choose a creature in this fight.")
            sim, party = fight.sim, fight.sim.party
            if op == "stabilize":
                if not c.get("pc") or not sim.down(c["id"]) or party.deaths[c["id"]]["dead"]:
                    return 409, {"ok": False, "refused": "%s isn't dying." % c["name"]}
                with fight.lock:
                    party.deaths[c["id"]].update(successes=0, failures=0, stable=True)
                sim.say("gm", "GM: %s is Stable." % c["name"])
            else:
                hp = req.get("hp")
                if not isinstance(hp, int) or isinstance(hp, bool) or not 1 <= hp <= 500:
                    raise ValueError("Healing is 1 to 500 Hit Points.")
                if c.get("pc") and party.deaths[c["id"]]["dead"]:
                    return 409, {"ok": False, "refused": "%s is dead." % c["name"]}
                with fight.lock:
                    if c.get("pc") and sim.down(c["id"]):
                        party.revive(c["id"], hp)
                    else:
                        sim.S.heal(c["id"], hp)
                sim.say("gm", "GM: %s regains %d HP." % (c["name"], hp))
            with fight.lock:
                fight.revision += 1
                fight._publish_locked()
            return 200, {"ok": True, "live": fight.snapshot(since)}
        if op != "creature":
            raise ValueError("An on-the-fly op is creature, announce, ac, heal, stabilize, temp or check.")
        name, count, at, mood = req.get("name"), req.get("count", 1), req.get("at"), req.get("attitude")
        lib = creature_threat.library()
        if name not in lib:
            raise ValueError("%s isn't in the SRD 5.2.1 library." % name)
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 12:
            raise ValueError("Count 1-12.")
        if mood is not None and mood not in ("Hostile", "Indifferent", "Friendly"):
            raise ValueError("An attitude is Hostile, Indifferent or Friendly.")
        if at is not None and not (isinstance(at, list) and len(at) == 2 and all(isinstance(n, int) and not isinstance(n, bool) for n in at)):
            raise ValueError("A square is [x, y].")
        with fight.lock:
            sc, sim = fight.sim.sc, fight.sim
            cols, rows = remix._extent(sc)
            rock = {tuple(p) for p in sc.get("wall_cells") or []}
            standing = {(int(round(c["x"])), int(round(c["y"]))) for c in sc["combatants"] if not sim.down(c["id"])}
            start = tuple(at) if at else remix._foe_start(sc, cols, rows, rock)
            if start in rock:
                return 409, {"ok": False, "refused": "That square is rock: pick a floor square."}
            spots = map_import.spaces(start, count, cols, rows, rock | standing, remix._squares(lib[name]))
            if len(spots) < count:
                return 409, {"ok": False, "refused": "There isn't room for %d there." % count}
            made = live_add.join(fight, lib[name], name, spots, mood)
        sim.say("turn", live_add.joined(made))
        with fight.lock:
            fight.revision += 1
            fight._publish_locked()
        return 200, {"ok": True, "made": made, "live": fight.snapshot(since)}

    def one_shot(self, req):
        """ONE-SHOT-01 (GM 2026-11-02): POST /api/oneshot, the GM's One-shot builder. op: setup, list, get {id}, save {doc},
        delete {id}, publish {doc} (written into the adventure library, and loaded), generate {field, doc, place?, idea?} (the
        local model loaded in Chat), map {scenario} (for the builder's picture). Never a door route."""
        import chat_model, creature_threat, one_shot, traps
        op = req.get("op")
        if op == "setup":
            lib = creature_threat.library()
            return 200, {"ok": True, "maps": self.available_scenarios(), "creatures": sorted(lib), "model": bool(self.model_loaded),
                         "attitudes": list(one_shot.ATTITUDES),
                         "library": bool(self.packs.directory),
                         "traps": {k: {"name": t["name"], "bands": list(t["bands"])} for k, t in traps.TRAPS.items()}}
        if op == "list":
            return 200, {"ok": True, "one_shots": one_shot.listing(self.one_shots_dir)}
        if op == "get":
            return 200, {"ok": True, "doc": one_shot.load(req.get("id"), self.one_shots_dir)}
        if op == "delete":
            one_shot.delete(req.get("id"), self.one_shots_dir)
            return 200, {"ok": True, "one_shots": one_shot.listing(self.one_shots_dir)}
        if op == "map":
            if req.get("scenario") not in self.available_scenarios():
                raise ValueError("That map isn't on this PC.")
            return 200, {"ok": True, "map": one_shot.map_view(self.raw_scenario(req["scenario"]))}
        if op == "generate":
            if not self.model_loaded:
                raise ValueError("Load a model in Chat first, or type this part yourself.")
            doc = req.get("doc") if isinstance(req.get("doc"), dict) else {}
            place = req.get("place") if isinstance(req.get("place"), dict) else None
            try:
                answer = chat_model.complete(one_shot.prompt(req.get("field"), doc, place, req.get("idea") or ""), self.llm_url, self.llm_model)
            except chat_model.ModelError as e:
                raise ValueError(str(e))
            if not answer:
                raise ValueError("The model gave no answer. Try again, or type this part yourself.")
            return 200, {"ok": True, "text": answer}
        if op not in ("save", "publish"):
            raise ValueError("A one-shot op is setup, list, get, save, delete, publish, generate or map.")
        lib = creature_threat.library()
        doc = one_shot.check(req.get("doc"), self.available_scenarios(), lib, traps.TRAPS)
        with self.lock:
            doc = one_shot.save(doc, self.one_shots_dir)
            if op == "save":
                return 200, {"ok": True, "doc": doc}
            pid = one_shot.publish(doc, self.packs.directory, self.raw_scenario, lib)
            self.packs.load(pid)
            self.remember_adventures()
        return 200, {"ok": True, "doc": doc, "pack": pid}

    def live_reaction(self, req, seat=None):
        """SPELL-BATCH-02 (GM 2026-10-28: the fight asks the player live): POST /api/live/reaction {n, cast} answers the
        Reaction question the fight waits on (Shield, Counterspell: sim/live_reactions.py). On the players' door (seat): only
        the seat that plays the character asked, while the GM does not hold it. The GM's console answers any question
        (Answer for them: a slow or absent player, a character nobody plays, one the GM holds), so a fight never hangs."""
        import live_reactions, table_seats
        n, cast = req.get("n"), req.get("cast")
        if not isinstance(n, int) or isinstance(n, bool) or not isinstance(cast, bool):
            raise ValueError("A Reaction answer names the question (n) and cast true or false.")
        if not self.live or self.live.done:
            return 404, {"ok": False, "error": "No fight is running."}
        q = self.live.reactions.view()
        if not q or q["n"] != n:
            return 409, {"ok": False, "refused": "That Reaction question is no longer open."}
        if seat is not None:
            if not (seat.get("character") and table_seats._same(q["name"], seat["character"])):
                return 409, {"ok": False, "error": "%s's player answers this Reaction (or the GM)." % q["name"]}
            if self.live.gm_control.get(q["pc"]):
                return 409, {"ok": False, "error": "The GM is playing %s now: the GM answers." % q["name"]}
        try:
            out = self.live.reactions.respond(n, cast, "gm" if seat is None else "player")
        except live_reactions.ReactionError as e:
            return 409, {"ok": False, "refused": str(e)}
        return 200, dict(out, live=self.live.snapshot(req.get("since", 0) if isinstance(req.get("since", 0), int) else 0))

    def live_stealth(self, req, seat=None):
        """STEALTH-01 (GM 2026-10-28; sim/stealth.py): POST /api/live/stealth. The GM: check {id} (Perception against a
        declared stealth), call {who: [ids] or "all"} (a group stealth check: a popup on each player's screen), roll {id}
        (rolls for a character), resolve (Perception against the group), cancel. A seat: roll {id} for its own character
        in the open group check, while the GM does not hold it. The dice are rolled here."""
        import stealth, table_seats
        if not self.live or self.live.done:
            return 404, {"ok": False, "error": "No fight is running."}
        op, i, st = req.get("op"), req.get("id"), stealth.of(self.live)
        if seat is not None:
            if op != "roll":
                return 403, {"ok": False, "error": "The GM calls stealth checks and rolls Perception."}
            c = next((x for x in self.live.sim.sc["combatants"] if x.get("id") == i and x.get("pc")), None)
            if not (c and seat.get("character") and table_seats._same(c["name"], seat["character"])):
                return 409, {"ok": False, "error": "Each player rolls for their own character."}
            if self.live.gm_control.get(i):
                return 409, {"ok": False, "error": "The GM is playing %s now: the GM rolls." % c["name"]}
        if op in ("check", "resolve") and self.live.waiting is None and not self.live.frozen and not self.live.held:
            return 409, {"ok": False, "refused": "The creatures are acting: roll Perception on a character's turn."}
        try:
            if op == "check":
                out = st.check(i)
            elif op == "call":
                out = st.open_call(req.get("who", "all"))
            elif op == "roll":
                out = {"total": st.call_roll(i, "gm" if seat is None else "player")}
            elif op == "resolve":
                dc = req.get("dc")
                if dc is not None and (not isinstance(dc, int) or isinstance(dc, bool) or not 1 <= dc <= 40):
                    raise ValueError("A DC is 1 to 40.")
                out = st.resolve(dc)
            elif op == "cancel":
                out = {"cancelled": st.cancel()}
            else:
                raise ValueError("op is check, call, roll, resolve or cancel.")
        except stealth.StealthError as e:
            return 409, {"ok": False, "refused": str(e)}
        with self.live.lock:
            self.live.revision += 1
            self.live._publish_locked()
        return 200, {"ok": True, "stealth": out,
                     "live": self.live.snapshot(req.get("since", 0) if isinstance(req.get("since", 0), int) else 0)}

    def live_initiative(self, req, seat=None):
        """INITIATIVE-01 (GM 2026-10-28; sim/initiative.py): POST /api/live/initiative while the fight's start waits for
        the characters' Initiative. A seat: roll {id} for its own character (not while the GM holds it). The GM: roll {id}
        for any character, rest (every character still to roll). The dice are rolled here."""
        import initiative, table_seats
        if not self.live or self.live.done:
            return 404, {"ok": False, "error": "No fight is running."}
        op, i, call = req.get("op"), req.get("id"), initiative.of(self.live)
        if seat is not None:
            if op != "roll":
                return 403, {"ok": False, "error": "Each player rolls their own character's Initiative."}
            c = next((x for x in self.live.sim.sc["combatants"] if x.get("id") == i and x.get("pc")), None)
            if not (c and seat.get("character") and table_seats._same(c["name"], seat["character"])):
                return 409, {"ok": False, "error": "Each player rolls for their own character."}
            if self.live.gm_control.get(i):
                return 409, {"ok": False, "error": "The GM is playing %s now: the GM rolls." % c["name"]}
        try:
            if op == "roll":
                out = {"total": call.roll_for(i, "gm" if seat is None else "player")}
            elif op == "rest":
                out = {"rolled": len(call.roll_rest())}
            else:
                raise ValueError("op is roll or rest.")
        except initiative.InitiativeError as e:
            return 409, {"ok": False, "refused": str(e)}
        with self.live.lock:
            self.live.revision += 1
            self.live._publish_locked()
        return 200, {"ok": True, "initiative": out,
                     "live": self.live.snapshot(req.get("since", 0) if isinstance(req.get("since", 0), int) else 0)}

    def live_aim(self, req, seat=None):
        """HINTS-01 H4: POST /api/live/aim {spell, x, y, slot?}: who the waiting character's area spell, aimed at square
        (x, y), would catch now (sim/live_hints.py area_inside; aim None when it can't be aimed there). Read only:
        nothing is cast or spent. On the players' door (seat): only for its own character on its turn, at the Reminders
        level, and only the creatures that seat sees."""
        import live_hints, table_seats
        name, slot = req.get("spell"), req.get("slot")
        if not isinstance(name, str) or not 0 < len(name) <= 40:
            raise ValueError("Aim names a spell.")
        if not all(isinstance(req.get(k), int) and not isinstance(req.get(k), bool) and -50 <= req[k] <= 500 for k in ("x", "y")):
            raise ValueError("Aim names a square (x, y).")
        if slot is not None and not (isinstance(slot, int) and not isinstance(slot, bool) and 1 <= slot <= 9):
            raise ValueError("A slot is a level, 1 to 9.")
        if not self.live or self.live.done:
            return 404, {"ok": False, "error": "No fight is running."}
        snap = self.live.snapshot(1 << 30)
        me, seen = snap.get("waiting"), None
        if seat is not None:
            if seat.get("hints", "off") != "reminders":
                return 409, {"ok": False, "error": "Hints are off for this seat."}
            view = table_seats.player_view(snap, seat["character"], "reminders")
            if not isinstance(view.get("offers"), dict) or view["offers"].get("actor") != me:
                return 409, {"ok": False, "error": "Wait for your character's turn."}
            seen = {c.get("id") for c in (view.get("state") or {}).get("combatants") or []}
        with self.live.lock:
            got = live_hints.area_inside(self.live, me, name, req["x"], req["y"], slot) if me else None
        if got and seen is not None:
            got = dict(got, inside=[i for i in got["inside"] if i in seen], spared=[i for i in got["spared"] if i in seen])
        return 200, {"ok": True, "aim": got}

    def live_control(self, req, seat=None):
        """GM 2026-10-24 ("let the DM take control of any character turns, presumably by permission, but not required"):
        POST /api/live/control {character, gm}. The GM takes (gm true) or gives back (gm false) any player character.
        On the players' door (seat): a player hands its own character to the GM (gm true) and takes it back (gm false)
        only when it handed it; a character the GM took stays with the GM until the GM gives it back."""
        import live_play, table_seats
        gm = req.get("gm")
        if not isinstance(gm, bool):
            raise ValueError("gm is true or false.")
        if not self.live or self.live.done:
            return 404, {"ok": False, "error": "No fight is running."}
        state = self.live.snapshot(1 << 30).get("state") or {}
        if seat is not None:
            c = next((x for x in state.get("combatants") or [] if x.get("pc") and seat.get("character")
                      and table_seats._same(x.get("name"), seat["character"])), None)
            if not c:
                return 409, {"ok": False, "error": "%s plays no character in this fight." % seat["name"]}
            held = self.live.gm_control.get(c["id"])
            if not gm and held == "gm":
                return 409, {"ok": False, "error": "The GM has taken %s: ask the GM to give it back." % c["name"]}
            by = ("player" if held != "gm" else "gm") if gm else None
        else:
            c = next((x for x in state.get("combatants") or [] if x.get("pc") and x.get("id") == req.get("character")), None)
            if not c:
                raise ValueError("Name a player character (its id).")
            by = "gm" if gm else None
        try:
            self.live.control(c["id"], by)
        except live_play.LiveError as e:
            return 409, {"ok": False, "refused": str(e)}
        return 200, {"ok": True, "character": c["id"], "control": by, "live": self.live.snapshot(0)}

    # ------------------------------------------------------------------ GM 2026-11-01: the GM's stop, clock and rewind
    def live_panic(self, req):
        """GM 2026-11-01 ("a Panic Button that stops everything"): POST /api/live/panic {on}, the GM's door only. The rules
        engine holds at its next step (a freeze: nothing is lost), the Rules monitor stops, the turn timer waits, and the
        players' door takes no choice, roll, chat or request and says so on their screens. Resume goes on from there; a
        fight the GM had frozen already stays frozen."""
        on = req.get("on")
        if not isinstance(on, bool):
            raise ValueError("on is true or false.")
        if self.rewinding:
            return 409, {"ok": False, "refused": "The fight is being taken back; try again in a moment."}
        f = self.live if self.live and not self.live.done else None
        if on and not self.panic:
            self.panic_kept = {"frozen": bool(f and f.frozen), "monitor": self.monitor.on}
            self.panic = True
            if f and not f.frozen:
                f.freeze(True)
            if self.monitor.on:
                self.monitor.switch(False)
        elif not on and self.panic:
            self.panic = False
            if f and f.frozen and not self.panic_kept.get("frozen"):
                f.freeze(False)
            if self.panic_kept.get("monitor"):
                self.monitor.switch(True)
        return 200, {"ok": True, "panic": self.panic, "timeline": self.timeline_view(), **({"live": self.live.snapshot(0)} if self.live else {})}

    def live_timer(self, req):
        """GM 2026-11-01 ("a small timer on the combat tracker for each turn, which the GM can disable and enable at will"):
        POST /api/live/timer {on}. Kept for the next fights until the service restarts; not on the players' door."""
        on = req.get("on")
        if not isinstance(on, bool):
            raise ValueError("on is true or false.")
        self.turn_timer = on
        if self.live and not self.live.done:
            self.live.set_timer(on)
        return 200, {"ok": True, "on": on, **({"live": self.live.snapshot(0)} if self.live else {})}

    # GM-UNDO-01 (GM 2026-11-01: "an unlimited undo that tells the rules engine to go in reverse, one step at a time"). The
    # fight lives on a thread that can't be wound back, but it is repeatable: the same start, seed and choices give the same
    # fight, dice included. So the service keeps the fight's timeline (each choice that changed it, and each creature's
    # turn), and a step back builds the fight again and replays everything but the last step. Every rule stands exactly as
    # it stood, with no reverse written for any of them. The fight then waits, frozen, for the GM.
    def timeline_view(self):
        steps = self.timeline or []
        return {"steps": len(steps), "last": steps[-1]["label"] if steps else None}

    def remember_start(self, req, scenario):
        """What a fight began from, beyond its own files: the adventure day and the bags, which a replay would spend twice."""
        pack, day = self.pack_of(scenario), None
        if pack and pack in self.packs.loaded:
            with self.days.lock:
                day = copy.deepcopy(self.days.get(pack))
        with self.market.lock:
            purses = copy.deepcopy(self.market._load().get("purses"))
        self.fight_start = {"req": copy.deepcopy(req), "pack": pack, "day": day, "purses": purses,
                            "reaction_auto": getattr(self, "reaction_auto", False), "social_off": getattr(self, "social_off", False),
                            "by_srd": self.by_srd}
        self.timeline = []

    def restore_start(self):
        s = self.fight_start
        if s["day"] is not None:
            with self.days.lock:
                d = self.days.get(s["pack"])
                d.clear()
                d.update(copy.deepcopy(s["day"]))
                self.days.save(s["pack"])
        with self.market.lock:
            self.market._load()["purses"] = copy.deepcopy(s["purses"])
            self.market._write()
        self.reaction_auto, self.social_off, self.by_srd = s["reaction_auto"], s["social_off"], s["by_srd"]

    def note_creature(self, fight, cid):
        if not self.rewinding and self.timeline is not None:
            self.timeline.append({"kind": "creature", "label": "%s's turn" % fight.sim.by_id(cid)["name"]})

    def step_label(self, name, req):
        if name != "live_act":
            return STEP_LABELS.get(name, name)
        c = next((x for x in self.live.sim.sc["combatants"] if x.get("id") == req.get("actor")), None) if self.live else None
        who, op = c["name"] if c else "A character", req.get("op")
        return ("%s casts %s" % (who, req.get("spell")) if op == "cast" else "%s %s" % (who, STEP_WORDS[op]) if op in STEP_WORDS
                else "%s: %s" % (who, str(op).replace("_", " ")))

    def new_step(self, name, req, rest):
        """A choice for the timeline, or None for a read or a replay's own."""
        if self.rewinding or self.timeline is None or req.get("op") == "catalog":
            return None
        return {"kind": "choice", "name": name, "rest": copy.deepcopy(rest), "label": self.step_label(name, req),
                "req": {k: copy.deepcopy(v) for k, v in req.items() if k not in ("token", "ticket", "since")}}

    def replay_step(self, e):
        """One choice again, on the rebuilt fight -> why it could not be, or None."""
        f, end = self.live, time.monotonic() + 20
        while True:
            f.settle()
            req = copy.deepcopy(e["req"])
            if "revision" in req:
                req["revision"] = f.revision
            try:
                code, out = getattr(self, e["name"])(req, *copy.deepcopy(e["rest"]))
            except Exception as err:                              # said to the GM, and the rewind stops there
                return str(err)
            if code == 200 and out.get("ok"):
                return None
            why = out.get("refused") or out.get("error") or "refused"
            if not why.startswith(REPLAY_WAITS) or time.monotonic() > end:
                return why
            time.sleep(0.01)

    def rewind(self, keep, label):
        """The fight built again and replayed up to `keep`, then frozen -> what stopped it early, or None."""
        old, stopped, done = self.live, None, 0
        self.rewinding, self.rewind_thread = True, threading.get_ident()
        try:
            code, out = self.live_new(copy.deepcopy(self.fight_start["req"]), replay={"fight_id": old.fight_id, "rewinds": old.rewinds + 1})
            if code != 200:
                return out.get("error") or "the fight could not be built again"
            f = self.live
            for e in keep:
                why = (None if f.release() else "the creatures' turns did not line up") if e["kind"] == "creature" else self.replay_step(e)
                if why:
                    stopped = "%s could not be played again: %s" % (e["label"], why)
                    break
                done += 1
            f.settle(30)
            self.timeline = keep[:done]
            with f.lock:
                f.revision = max(f.revision, old.revision) + 1
                f.replaying, f.monitor = False, self.monitor
                f._publish_locked()
            f.sim.say("note", "The GM takes back: %s." % label)
            if not f.done and not f.frozen:
                f.freeze(True)
            return stopped
        finally:
            self.rewinding, self.rewind_thread = False, None

    def live_undo(self, req):
        """POST /api/live/undo, the GM's door only: one step back, as far as the fight's start. The fight waits, frozen, until
        the GM lets it go on; from there the same choices give the same dice."""
        if not self.live or self.timeline is None:
            return 404, {"ok": False, "error": "No fight is running."}
        if self.rewinding:
            return 409, {"ok": False, "refused": "The fight is being taken back; try again in a moment."}
        if not self.timeline:
            return 409, {"ok": False, "refused": "Nothing to undo: the fight is at its start."}
        gone = self.timeline[-1]
        stopped = self.rewind(self.timeline[:-1], gone["label"])
        return 200, {"ok": True, "undone": gone["label"], "stopped": stopped, "panic": self.panic, "timeline": self.timeline_view(),
                     "scenario": self.live_scenario, "live": self.live.snapshot(0), "hints_cap": self.seats.cap}

    def live_freeze(self, req):
        """GM 2026-10-24: POST /api/live/freeze {frozen}: the GM freezes the fight or lets it go on (not on the players'
        door)."""
        import live_play
        if not isinstance(req.get("frozen"), bool):
            raise ValueError("frozen is true or false.")
        if self.panic:
            return 409, {"ok": False, "refused": "Everything is stopped: press Resume first."}
        if not self.live or self.live.done:
            return 404, {"ok": False, "error": "No fight is running."}
        try:
            self.live.freeze(req["frozen"])
        except live_play.LiveError as e:
            return 409, {"ok": False, "refused": str(e)}
        return 200, {"ok": True, "frozen": self.live.frozen, "live": self.live.snapshot(0)}

    def live_sight(self, req):
        """SIGHT-01 (GM 2026-10-27): POST /api/live/sight {picks: {character id: {creature id: seen}}}: the GM's picks of
        which creatures each character sees (at the fight's start, or on the tracker); sim/combat_tracker.py. GM door only."""
        import combat_tracker
        if not self.live:
            return 404, {"ok": False, "error": "No live fight: start one."}
        fight = self.live
        with fight.lock:
            combat_tracker.set_sight(fight, req.get("picks"))
        return 200, {"ok": True, "live": fight.snapshot(req.get("since", 0) if isinstance(req.get("since"), int) else 0)}

    def live_traps(self, req):
        """GM 2026-10-24 (SRD Group 2): the GM's traps in the running fight (not on the players' door). op: catalog (the eight
        SRD traps and the band for a level), place {kind, band, squares, area?, statue?, toward?, door?, stone?} or remove
        {trap}. Checked by sim/traps.py (only squares a creature can enter). GM 2026-10-26 (goal 15): know {trap, who: [creature
        ids or "foes"], on}: those creatures know the trap (sim/creature_traps.py), or no longer do."""
        import traps
        op = req.get("op")
        if op == "catalog":
            level = req.get("level", 1)
            if not isinstance(level, int) or isinstance(level, bool) or not 1 <= level <= 20:
                raise ValueError("A level is 1 to 20.")
            return 200, dict(traps.suggest(level), ok=True,
                             every={k: {"name": t["name"], "bands": list(t["bands"]), "place": t["place"]} for k, t in traps.TRAPS.items()})
        if not self.live or self.live.done:
            return 404, {"ok": False, "error": "No live fight: start one."}
        tr = traps.of(self.live.sim)
        if op == "place":
            spec = {k: req[k] for k in ("kind", "band", "squares", "area", "statue", "toward", "door", "stone", "known_by",
                                        "climb_dc") if k in req}
            if len(json.dumps(spec)) > 4000:
                raise ValueError("A trap is a short description.")
            try:
                with self.live.lock:
                    t = tr.place(spec, quiet=True)       # the GM's secret: nothing in the players' log
                    self.live.revision += 1
                    self.live._publish_locked()
            except traps.TrapError as e:
                return 409, {"ok": False, "refused": str(e)}
            return 200, {"ok": True, "trap": t["id"], "live": self.live.snapshot(req.get("since", 0) if isinstance(req.get("since", 0), int) else 0)}
        if op == "remove":
            try:
                with self.live.lock:
                    tr.remove(str(req.get("trap", "")))
                    self.live.revision += 1
                    self.live._publish_locked()
            except traps.TrapError as e:
                return 409, {"ok": False, "refused": str(e)}
            return 200, {"ok": True, "live": self.live.snapshot()}
        if op == "know":                                  # GM 2026-10-26 (goal 15): which creatures know this trap
            who = req.get("who")
            if not isinstance(who, list) or not 0 < len(who) <= 40 or not all(isinstance(w, str) and 0 < len(w) <= 40 for w in who):
                raise ValueError("Name the creatures (ids, or foes for the whole lair).")
            try:
                with self.live.lock:
                    tr.minds.mark(str(req.get("trap", "")), who, on=req.get("on", True) is not False)
                    self.live.revision += 1
                    self.live._publish_locked()
            except (traps.TrapError, ValueError) as e:
                return 409, {"ok": False, "refused": str(e)}
            return 200, {"ok": True, "live": self.live.snapshot()}
        raise ValueError("A traps op is catalog, place, remove or know.")

    def live_mount_mode(self, req):
        """MAP-LAYERS-01: the GM decides whether a mount is controlled or independent (any time; not on the players' door)."""
        import map_layers
        m, mode = req.get("mount"), req.get("mode")
        if not isinstance(m, str) or not 0 < len(m) <= 40 or mode not in ("controlled", "independent"):
            raise ValueError("Name the mount and controlled or independent.")
        if not self.live:
            return 404, {"ok": False, "error": "No live fight."}
        with self.live.lock:
            try:
                self.live.layers.set_mode(m, mode)
            except map_layers.LayerError as e:
                return 409, {"ok": False, "refused": str(e)}
            self.live.revision += 1
            self.live._publish_locked()
        return 200, {"ok": True, "mount": m, "mode": mode, "live": self.live.snapshot(0)}
    def live_scene(self, req):
        """GM 2026-10-24: the GM's scene choices in a live fight (sim/attitude.py): set a creature's attitude, have a
        Friendly creature join or leave the party, set its status (surrenders, flees, bargains, fights again), answer a
        morale suggestion, call a truce, have the party retreat, end the scene. Not on the players' door."""
        op = req.get("op")
        cmd = {"op": op}
        for k, kind, most in (("creature", str, 40), ("attitude", str, 12), ("status", str, 12), ("why", str, 120),
                              ("wants", str, 12)):                  # GM 2026-10-25 (ruling P3): what an Influence urged
            if k in req:
                if not isinstance(req[k], kind) or len(req[k]) > most:
                    raise ValueError("%s is up to %d characters." % (k, most))
                cmd[k] = req[k]
        if "n" in req:
            if not isinstance(req["n"], int) or isinstance(req["n"], bool):
                raise ValueError("A morale suggestion is a number (n).")
            cmd["n"] = req["n"]
        if "accept" in req:
            if not isinstance(req["accept"], bool):
                raise ValueError("accept is true or false.")
            cmd["accept"] = req["accept"]
        if "surprised" in req:                                     # GM 2026-10-26: who is surprised as the fight starts
            s = req["surprised"]
            if not isinstance(s, list) or len(s) > 40 or not all(isinstance(x, str) and len(x) <= 40 for x in s):
                raise ValueError("surprised is a list of combatant ids.")
            cmd["surprised"] = s
        if not self.live:
            return 404, {"ok": False, "error": "No live fight."}
        fight = self.live
        if req.get("fight_id") is not None and req.get("fight_id") != fight.fight_id:
            return 409, {"ok": False, "error": "Stale fight: refresh the table.", "live": fight.snapshot()}
        import scenes
        if op in scenes.GM_OPS:                                   # GM 2026-10-26: talk, explore, start the fight, not yet
            out = (fight.scenes.submit(cmd) if fight.scenes else
                   {"ok": False, "refused": "This fight was started without scenes: start it from Play an adventure."})
        else:
            out = fight.attitudes.submit(cmd)
        since = req.get("since", 0) if isinstance(req.get("since", 0), int) else 0
        return (200 if out.get("ok") else 409), dict(out, live=fight.snapshot(since))

    def prep(self, req):
        """GM 2026-10-24: Remix Prep's attitudes and morale (tools/remix_prep.py): {op: state | save, campaign, scenario,
        level, levels, prep, revision}."""
        import remix_prep
        op, campaign = req.get("op"), req.get("campaign", "default")
        scenario = self.scenario_aliases().get(str(req.get("scenario", "")), str(req.get("scenario", "")))
        if op not in ("state", "save"):
            raise ValueError("Prep op is state or save.")
        if scenario not in self.available_scenarios():
            raise ValueError("Unknown map (use a name from /api/hello).")
        level = req.get("level", 1)
        if not isinstance(level, int) or isinstance(level, bool) or not 1 <= level <= 20:
            raise ValueError("Level is 1 to 20.")
        raw = self.raw_scenario(scenario)
        if op == "save":
            remix_prep.save(self.remix, campaign, scenario, raw, req)
        return 200, remix_prep.state(self.remix, campaign, scenario, raw, level)

    def live_state(self, req):
        if self.rewinding and threading.get_ident() != self.rewind_thread:   # GM-UNDO-01: no screen sees the replay
            return 200, {"ok": False, "rewinding": True, "panic": self.panic}
        if not self.live:
            return 404, {"ok": False, "error": "No live fight: start one.", "adventure_unloaded": self.unloaded_pack, "panic": self.panic}
        since = req.get("since", 0)
        if not isinstance(since, int):
            raise ValueError("since is a number.")
        return 200, {"ok": True, "scenario": self.live_scenario, "live": self.live.snapshot(since),
                     "hints_cap": self.seats.cap,                 # H3: the GM console's own hints obey the table cap
                     "panic": self.panic, "timeline": self.timeline_view()}

    def live_act(self, req):
        op, rev = req.get("op"), req.get("revision")
        if op not in LIVE_OPS or not isinstance(rev, int):
            raise ValueError("A choice is one of %s, with the revision it answers." % ", ".join(sorted(LIVE_OPS)))
        since = req.get("since", 0)
        if not isinstance(since, int) or since < 0:
            raise ValueError("since is a number.")
        cmd = {"op": op, "revision": rev, "since": since}
        if op == "attack":
            if req.get("weapon") not in LIVE_WEAPONS or not isinstance(req.get("target"), str) or len(req["target"]) > 40:
                raise ValueError("An attack names a sheet weapon and a target.")
            cmd.update(weapon=req["weapon"], target=req["target"])
        if op == "move":
            if not all(isinstance(req.get(k), int) and 0 <= req[k] <= 500 for k in ("x", "y")):
                raise ValueError("A move names a square (x, y).")
            cmd.update(x=req["x"], y=req["y"])
            if req.get("dash") is True:                           # GM 2026-10-24: Dash to get there
                cmd["dash"] = True
        if op == "cast":                                          # slice 2: a spell from the sheet
            name = req.get("spell")
            if not isinstance(name, str) or not 0 < len(name) <= 40:
                raise ValueError("A cast names a spell.")
            cmd["spell"] = name
            if "target" in req:
                if not isinstance(req["target"], str) or len(req["target"]) > 40:
                    raise ValueError("A target is a creature id.")
                cmd["target"] = req["target"]
            if "targets" in req:                                  # SPELLS-4-9: Divine Word, Mass Heal take any number
                ts = req["targets"]
                if not isinstance(ts, list) or len(ts) > 12 or not all(isinstance(x, str) and len(x) <= 40 for x in ts):
                    raise ValueError("Targets are up to twelve creature ids.")
                cmd["targets"] = ts
            if "x" in req or "y" in req:
                if not all(isinstance(req.get(k), int) and -50 <= req[k] <= 500 for k in ("x", "y")):
                    raise ValueError("A spell's point is a square (x, y).")
                cmd.update(x=req["x"], y=req["y"])
            if "points" in req:                                   # SPELLS-4-9: Meteor Swarm's points
                ps = req["points"]
                if not isinstance(ps, list) or not 0 < len(ps) <= 4 or not all(
                        isinstance(q, list) and len(q) == 2 and all(isinstance(v, int) and -50 <= v <= 500 for v in q) for q in ps):
                    raise ValueError("A spell's points are up to four squares [x, y].")
                cmd["points"] = ps
                cmd.setdefault("x", ps[0][0]); cmd.setdefault("y", ps[0][1])   # the first, for the referee's range
            if "door" in req:                                     # SPELL-OBJECTS-01: a spell cast at a door
                if not isinstance(req["door"], str) or not 0 < len(req["door"]) <= 40:
                    raise ValueError("A spell's door names the door.")
                cmd["door"] = req["door"]
            if "object" in req:                                   # SPELL-OBJECTS-01 step 6: or at a prop
                if not isinstance(req["object"], str) or not 0 < len(req["object"]) <= 60:
                    raise ValueError("A spell's object names the prop (its kind and square).")
                cmd["object"] = req["object"]
        if op in ("dash", "disengage", "dodge", "hide"):          # slices 3-4: the action, or a Rogue's Bonus Action
            if not isinstance(req.get("bonus", False), bool):
                raise ValueError("bonus is true or false.")
            cmd["bonus"] = req.get("bonus", False)
        if op in ("door", "douse_door"):                          # slice 3: open or close a door beside you; put out its fire
            if not isinstance(req.get("door"), str) or not 0 < len(req["door"]) <= 40:
                raise ValueError("A door choice names the door.")
            cmd["door"] = req["door"]
        if op == "influence":                                     # GM 2026-10-23: how, and what is urged
            if req.get("mode") not in INFLUENCE_MODES:
                raise ValueError("Influence is one of %s." % ", ".join(sorted(INFLUENCE_MODES)))
            cmd["mode"] = req["mode"]
            if "urge" in req:
                if not isinstance(req["urge"], str) or len(req["urge"]) > 120:
                    raise ValueError("What is urged is up to 120 characters.")
                cmd["urge"] = req["urge"]
        square = op in ("search", "study", "trap", "use_item") and ("x" in req or "y" in req)
        if square:                                                # GM 2026-10-24: Search/Study a square, gear on a square
            if not all(isinstance(req.get(k), int) and not isinstance(req.get(k), bool) and 0 <= req[k] <= 500 for k in ("x", "y")):
                raise ValueError("A square is (x, y), whole numbers 0 to 500.")
            cmd.update(x=req["x"], y=req["y"])
        if op in ("move_beam", "move_pack"):                      # SPELL-EFFECTS-01: where the area goes
            if not all(isinstance(req.get(k), int) and not isinstance(req.get(k), bool) and 0 <= req[k] <= 500 for k in ("x", "y")):
                raise ValueError("A square is (x, y), whole numbers 0 to 500.")
            cmd.update(x=req["x"], y=req["y"])
        if op in ("attack", "move", "dash", "disengage", "hide", "use_item") and "haste" in req:   # Haste's extra action
            if not isinstance(req["haste"], bool):
                raise ValueError("haste is true or false.")
            cmd["haste"] = req["haste"]
        if op in ("help", "grapple", "shove", "lay_on_hands", "study", "influence", "shake", "spirit_strike",
                  "familiar_help", "command_undead")                 and not (op == "study" and square):                # shake, spirit_strike: GM 2026-10-25
            if not isinstance(req.get("target"), str) or not 0 < len(req["target"]) <= 40:
                raise ValueError("That choice names a creature (target).")
            cmd["target"] = req["target"]
        if op == "trap":                                          # GM 2026-10-24: sim/traps.py
            import traps
            if req.get("how") not in traps.WAYS:
                raise ValueError("A trap step is one of %s." % ", ".join(sorted(traps.WAYS)))
            cmd["how"] = req["how"]
            for k in ("trap", "target", "door"):
                if k in req:
                    if not isinstance(req[k], str) or not 0 < len(req[k]) <= 40:
                        raise ValueError("%s is a name of up to 40 characters." % k)
                    cmd[k] = req[k]
        if op == "check":                                         # GM 2026-10-26: any ability check in a scene
            import character_rules
            if not (req.get("skill") in character_rules.rules()["skills"] or (
                    "skill" not in req and req.get("ability") in ("str", "dex", "con", "int", "wis", "cha"))):
                raise ValueError("A check names a skill or an ability (str, dex, con, int, wis, cha).")
            cmd.update({k: req[k] for k in ("skill", "ability") if k in req})
            if req.get("roll") not in (None, "advantage", "disadvantage"):
                raise ValueError("roll is advantage or disadvantage (or nothing).")
            if req.get("roll"):
                cmd["roll"] = req["roll"]
            if "about" in req:
                if not isinstance(req["about"], str) or len(req["about"]) > 120:
                    raise ValueError("What the check is about is up to 120 characters.")
                cmd["about"] = req["about"]
        if op == "mount_consent":                                 # GM 2026-10-25 (ruling M2): on or off
            if not isinstance(req.get("on"), bool):
                raise ValueError("Let others ride me is on (true) or off (false).")
            cmd["on"] = req["on"]
        if op == "shove":
            if req.get("mode") not in ("prone", "push"):
                raise ValueError("A Shove is prone or push.")
            cmd["mode"] = req["mode"]
        if op == "ready" and "spell" in req:                      # GM 2026-10-25: a readied spell
            if not isinstance(req["spell"], str) or not 0 < len(req["spell"]) <= 40:
                raise ValueError("Ready names a sheet attack or a spell.")
            cmd["spell"] = req["spell"]
        elif op == "ready":
            if req.get("weapon") not in LIVE_WEAPONS:
                raise ValueError("Ready names a sheet attack.")
            cmd["weapon"] = req["weapon"]
        if op in ("cast", "ready"):                               # GM 2026-10-25: a general spell's choice and upcast slot
            if "choice" in req:
                if not isinstance(req["choice"], str) or not 0 < len(req["choice"]) <= 40:
                    raise ValueError("A spell's choice is up to 40 characters.")
                cmd["choice"] = req["choice"]
            if "slot" in req:
                if not isinstance(req["slot"], int) or isinstance(req["slot"], bool) or not 1 <= req["slot"] <= 9:
                    raise ValueError("A slot level is 1 to 9.")
                cmd["slot"] = req["slot"]
        if op == "attack" and "dmgtype" in req:                   # GM 2026-11-01: Sorcerous Burst's type (checked in the fight)
            if not isinstance(req["dmgtype"], str) or not 0 < len(req["dmgtype"]) <= 20:
                raise ValueError("A damage type is a word.")
            cmd["dmgtype"] = req["dmgtype"]
        if op == "attack" and "mastery" in req:                   # GM 2026-10-26: Tactical Master (Fighter 9)
            if req["mastery"] not in ("Push", "Sap", "Slow"):
                raise ValueError("Tactical Master's mastery is Push, Sap or Slow.")
            cmd["mastery"] = req["mastery"]
        for k in ("divine", "overchannel", "use_slot") if op in ("cast", "ready") else ("hurl",) if op == "attack" else ():
            if k in req:                                          # CASTER-HIGH: Divine Intervention, Overchannel, a slot
                if not isinstance(req[k], bool):                  # instead of Spell Mastery's; Hurl Through Hell on a hit
                    raise ValueError("%s is true or false." % k)
                cmd[k] = req[k]
        if op in ("attack", "martial_arts", "flurry") and "stun" in req:   # MONK-01: Stunning Strike on a hit
            if not isinstance(req["stun"], bool):
                raise ValueError("stun is true or false.")
            cmd["stun"] = req["stun"]
        if op in ("martial_arts", "flurry"):                      # MONK-01: an Unarmed Strike at a creature
            if not isinstance(req.get("target"), str) or not 0 < len(req["target"]) <= 40:
                raise ValueError("That choice names a creature (target).")
            cmd["target"] = req["target"]
            if op == "flurry" and "target2" in req:
                if not isinstance(req["target2"], str) or not 0 < len(req["target2"]) <= 40:
                    raise ValueError("target2 is a creature id.")
                cmd["target2"] = req["target2"]
        if op in ("flurry", "patient_defense", "step_of_the_wind") and "mode" in req:   # MONK-01: which way
            if req["mode"] not in ("strikes", "addle", "push", "topple", "free", "focus"):
                raise ValueError("The Monk's choice is strikes, addle, push, topple, free or focus.")
            cmd["mode"] = req["mode"]
        if op == "attack" and "cunning" in req:                   # GM 2026-10-26: Supreme Sneak (Thief 9)
            if req["cunning"] != "stealth_attack":
                raise ValueError("A Cunning Strike option here is stealth_attack.")
            cmd["cunning"] = req["cunning"]
        if op == "abjure_foes" and "targets" in req:              # GM 2026-10-26: the creatures Abjure Foes takes
            ts = req["targets"]
            if not isinstance(ts, list) or len(ts) > 10 or not all(isinstance(x, str) and 0 < len(x) <= 40 for x in ts):
                raise ValueError("Abjure Foes names up to ten creatures.")
            cmd["targets"] = ts
        if op in ("attack", "cast"):                              # GM 2026-10-23: Metamagic on a spell or attack cantrip
            meta = req.get("metamagic")
            if meta is not None:
                meta = [meta] if isinstance(meta, str) else meta
                if not isinstance(meta, list) or len(meta) > 3 or not all(m in METAMAGIC for m in meta):
                    raise ValueError("Metamagic is up to three of: %s." % ", ".join(sorted(METAMAGIC)))
                cmd["metamagic"] = meta
            if "transmute" in req:
                if req["transmute"] not in TRANSMUTE:
                    raise ValueError("Transmuted Spell's damage type is one of %s." % ", ".join(sorted(TRANSMUTE)))
                cmd["transmute"] = req["transmute"]
            if "careful" in req:
                ts = req["careful"]
                if not isinstance(ts, list) or len(ts) > 6 or not all(isinstance(x, str) and len(x) <= 40 for x in ts):
                    raise ValueError("Careful Spell names up to six creatures.")
                cmd["careful"] = ts
            if "heightened" in req:
                if not isinstance(req["heightened"], str) or len(req["heightened"]) > 40:
                    raise ValueError("Heightened Spell names a creature.")
                cmd["heightened"] = req["heightened"]
        if op == "mount":                                         # MAP-LAYERS-01: a willing creature within 5 ft
            if not isinstance(req.get("target"), str) or not 0 < len(req["target"]) <= 40:
                raise ValueError("Mount names the creature to ride (target).")
            cmd["target"] = req["target"]
        if op == "dismount" and ("x" in req or "y" in req):
            if not all(isinstance(req.get(k), int) and -50 <= req[k] <= 500 for k in ("x", "y")):
                raise ValueError("Dismount names a square (x, y), or none for the nearest free one.")
            cmd.update(x=req["x"], y=req["y"])
        if op == "mount_action":
            if req.get("action") not in ("dash", "disengage", "dodge"):
                raise ValueError("A controlled mount can only Dash, Disengage or Dodge.")
            cmd["action"] = req["action"]
        if op == "use_item":                                      # an item from the bag, for a weapon or a creature
            if not isinstance(req.get("item"), str) or not ITEM_ID.match(req["item"]):
                raise ValueError("use_item names a bag item (its catalog id).")
            cmd["item"] = req["item"]
            if "weapon" in req:
                if req["weapon"] not in LIVE_WEAPONS:
                    raise ValueError("A weapon is weapon or ranged.")
                cmd["weapon"] = req["weapon"]
            if "target" in req:
                if not isinstance(req["target"], str) or len(req["target"]) > 40:
                    raise ValueError("A target is a creature id.")
                cmd["target"] = req["target"]
            if "use" in req:                                      # GM 2026-10-26: which of a tool's Utilize uses
                if not isinstance(req["use"], int) or isinstance(req["use"], bool) or not 0 <= req["use"] <= 9:
                    raise ValueError("A tool's use is its number (0-9).")
                cmd["use"] = req["use"]
        if op == "light":                                        # LIGHTS-01: sim/light_sources.py checks the rest
            if req.get("do") not in ("light", "take", "douse", "cover", "uncover", "drop", "pick_up", "hand", "hood", "aim",
                                     "fill", "cast"):
                raise ValueError("A light is lit, taken out, doused, covered, dropped, picked up, handed over, hooded, aimed, "
                                 "filled or cast.")
            cmd["do"] = req["do"]
            if "item" in req:
                if not isinstance(req["item"], str) or not ITEM_ID.match(req["item"]):
                    raise ValueError("A light from the bag names its catalog id.")
                cmd["item"] = req["item"]
            if "light" in req:
                if not isinstance(req["light"], int) or isinstance(req["light"], bool) or not 0 < req["light"] < 10000:
                    raise ValueError("A light is its number.")
                cmd["light"] = req["light"]
            for k, n in (("target", 40), ("spell", 40), ("on", 10)):
                if k in req:
                    if not isinstance(req[k], str) or len(req[k]) > n:
                        raise ValueError("A light's %s is a short name." % k)
                    cmd[k] = req[k]
            if "x" in req or "y" in req:
                if not all(isinstance(req.get(k), int) and 0 <= req[k] <= 500 for k in ("x", "y")):
                    raise ValueError("A square is x and y.")
                cmd.update(x=req["x"], y=req["y"])
        if op == "ask_gm":                                       # a spell or feature the GM rules
            if req.get("kind") not in ("spell", "feature", "action") or not isinstance(req.get("name"), str) or not 0 < len(req["name"]) <= 80:
                raise ValueError("Ask the GM names a spell, a feature or an action.")
            cmd.update(kind=req["kind"], name=req["name"])
            if "slot" in req:
                if not isinstance(req["slot"], int) or isinstance(req["slot"], bool) or not 1 <= req["slot"] <= 9:
                    raise ValueError("A slot level is 1 to 9.")
                cmd["slot"] = req["slot"]
            if "targets" in req:
                ts = req["targets"]
                if not isinstance(ts, list) or len(ts) > 12 or not all(isinstance(x, str) and len(x) <= 40 for x in ts):
                    raise ValueError("Targets are up to twelve creature ids.")
                cmd["targets"] = ts
            if "note" in req:
                if not isinstance(req["note"], str) or len(req["note"]) > 200:
                    raise ValueError("A note is up to 200 characters.")
                cmd["note"] = req["note"]
        if op in ("font_convert", "font_create"):
            if not isinstance(req.get("level"), int) or isinstance(req["level"], bool) or not 1 <= req["level"] <= 9:
                raise ValueError("Font of Magic names a slot level (1 to 9).")
            cmd["level"] = req["level"]
        if op == "lay_on_hands" and "amount" in req:
            if not isinstance(req["amount"], int) or isinstance(req["amount"], bool) or not 1 <= req["amount"] <= 200:
                raise ValueError("An amount is 1 to 200 hit points.")
            cmd["amount"] = req["amount"]
        if not self.live:
            return 404, {"ok": False, "error": "No live fight: start one.", "adventure_unloaded": self.unloaded_pack}
        # A revision restarts at zero in a new fight. Bind live writes to the exact fight and
        # actor the client saw; never apply an old tab's choice to the replacement fight.
        fight = self.live
        if not isinstance(req.get("fight_id"), str) or req["fight_id"] != fight.fight_id:
            return 409, {"ok": False, "error": "Stale fight: refresh the table before choosing.", "live": fight.snapshot()}
        if not isinstance(req.get("actor"), str):
            return 409, {"ok": False, "error": "Name the active actor from the live snapshot.", "live": fight.snapshot()}
        cmd.update(fight_id=req["fight_id"], actor=req["actor"])
        out = fight.act(cmd)
        status = out.pop("status", 200)
        snap = out.pop("snapshot", None) or fight.snapshot()
        out["live"] = snap
        return status, out

    # ------------------------------------------------------------------ TABLE-CHAT-01: chat, rolls, private rolls
    def _chat_view(self, seat):
        import table_chat
        return table_chat.visible(self.chat, seat)

    def chat_post(self, req):
        import table_chat
        seat, text = self.check_seat(req), req.get("text")
        if not isinstance(text, str):
            raise ValueError("Chat: messages are text.")
        with self.lock:
            try:
                _, answer = table_chat.post(self.chat, seat, text, self.dice, self.clock())
            except table_chat.ChatError as e:
                raise ValueError(str(e))
            return 200, {"ok": True, "answer": answer, "chat": self._chat_view(seat)}

    def roll(self, req):
        import table_chat
        seat, label, private = self.check_seat(req), req.get("label", ""), req.get("private", False)
        if not isinstance(label, str) or not isinstance(private, bool):
            raise ValueError("A roll's label is text and private is true or false.")
        with self.lock:
            try:
                table_chat.roll(self.chat, seat, req.get("expr"), label, self.dice, self.clock(), private=private)
            except table_chat.ChatError as e:
                raise ValueError(str(e))
            return 200, {"ok": True, "chat": self._chat_view(seat)}

    # ------------------------------------------------------------------ CHAT-MODEL-01: the GM's model in the chat window
    def _model_view(self, servers=False):
        import chat_model
        out = {"ok": True, "url": self.llm_url, "model": self.llm_model, "loaded": self.model_loaded, "talk": self.model_talk}
        return dict(out, servers=chat_model.servers()) if servers else out

    def chat_model(self, req):
        """GM 2026-11-01 ("make sure chat allows you to load an llm"): op: state, load (url, model), ask (text), clear. On the
        GM door only. What is loaded is llm_url and llm_model, so the Rules monitor and the site designer use it too."""
        import chat_model
        op = req.get("op", "state")
        try:
            if op == "state":
                return 200, self._model_view(True)
            if op == "load":
                chat_model.load(req.get("url"), req.get("model"))
                with self.lock:
                    self.llm_url, self.llm_model, self.model_loaded = req["url"], req["model"], True
                return 200, self._model_view(True)
            if op == "ask":
                if not self.model_loaded:
                    raise chat_model.ModelError("Load a model first.")
                text = req.get("text")
                answer = chat_model.ask(self.model_talk, text, self.llm_url, self.llm_model)
                with self.lock:
                    self.model_talk = (self.model_talk + [{"who": "GM", "text": text.strip()}, {"who": self.llm_model, "text": answer}])[-chat_model.MAX_TALK:]
                return 200, self._model_view()
            if op == "clear":
                with self.lock:
                    self.model_talk = []
                return 200, self._model_view()
        except chat_model.ModelError as e:
            raise ValueError(str(e))
        raise ValueError("A chat model op is state, load, ask or clear.")

    def chat_share(self, req):
        """CHAT-FUN-01: a picture or a sound file from the PC, for everyone in the chat."""
        import base64, binascii, table_chat
        seat, data, name, caption = self.check_seat(req), req.get("data"), req.get("name", ""), req.get("caption", "")
        if not isinstance(data, str) or not isinstance(name, str) or not isinstance(caption, str):
            raise ValueError("Chat: a shared file is sent as base64 text with its name and a caption.")
        try:
            raw = base64.b64decode(data, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("Chat: the file did not arrive whole; try again.")
        try:
            kind, ext = table_chat.check_file(raw)
        except table_chat.ChatError as e:
            raise ValueError(str(e))
        fname = "%s.%s" % (uuid.uuid4().hex, ext)
        self.chat_media_dir.mkdir(parents=True, exist_ok=True)
        (self.chat_media_dir / fname).write_bytes(raw)
        with self.lock:
            table_chat.share_file(self.chat, seat, kind, "/chat-media/" + fname, name, caption, self.clock())
            return 200, {"ok": True, "chat": self._chat_view(seat)}

    def chat_media(self, fname):
        """CHAT-FUN-01: (content type, bytes) of a shared file, or None. Only names the service gave (no paths)."""
        import table_chat
        if not table_chat.FILE_NAME.match(fname):
            return None
        f = self.chat_media_dir / fname
        if not f.is_file():
            return None
        return table_chat.MEDIA_TYPES[fname.rsplit(".", 1)[1]], f.read_bytes()

    def chat_log(self, req):
        seat = self.check_seat(req)
        with self.lock:
            return 200, {"ok": True, "chat": self._chat_view(seat)}

    # ------------------------------------------------------------------ VIEW-01: notes pinned to the map
    def _notes_file(self, req):
        name = req.get("map")
        if not isinstance(name, str) or not 0 < len(name) <= 120:
            raise ValueError("A map name is needed.")
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "map"
        return Path(self.notes_dir) / (slug + ".json")

    def characters(self, req):
        """RUST-DEPRECATE-01 parity item 2 (GM 2026-10-20: Python is the sole rules authority): the Characters roster,
        checked by sim/character_roster.py with the deprecated Rust engine's rules and messages. The roster lives here
        while the service runs; the browser keeps its copy and loads it again after a restart. Artwork comes from the
        table's creature manifest (--table .../dist/creatures.json)."""
        import character_roster
        if req.get("op") == "character_check":                   # CHARACTERS-01: SRD 5.2.1 or homebrew (no roster)
            import character_rules
            return 200, character_rules.check(req.get("character"))
        if req.get("op") in ("character_srd", "character_build", "character_member"):   # CHARACTERS-01 phase 3: the builder
            import character_rules, character_build
            if req["op"] == "character_srd":
                return 200, {"ok": True, "rules": dict(character_rules.rules(), kits=character_build.kits())}   # KITS-01
            if req["op"] == "character_build":
                return 200, character_build.build(req.get("choices"))
            out = character_build.member(req.get("character"))
            return 200, dict(out, ok=True, flags=character_rules.flags(req.get("character")))
        with self.roster_lock:
            if self.roster is None:
                catalog = character_roster.load_catalog(self.table_dir)
                if catalog is None:
                    return 503, {"ok": False, "error": "No creature catalog: start the service with --table (the table's "
                                                       "dist folder, which holds creatures.json)."}
                self.roster = character_roster.Roster(catalog)
            return 200, self.roster.apply(req)

    def notes_load(self, req):
        f = self._notes_file(req)
        with self.lock:
            try:
                notes = json.loads(f.read_text(encoding="utf-8")).get("notes", []) if f.is_file() else []
            except (OSError, ValueError):
                notes = []
        return 200, {"ok": True, "notes": notes}

    def notes_save(self, req):
        f, notes = self._notes_file(req), req.get("notes")
        if not isinstance(notes, list) or len(notes) > MAX_NOTES:
            raise ValueError("Notes are a list of at most %d." % MAX_NOTES)
        clean = []
        for n in notes:
            ok = (isinstance(n, dict) and isinstance(n.get("id"), str) and 0 < len(n["id"]) <= 40
                  and all(isinstance(n.get(k), int) and not isinstance(n.get(k), bool) and 0 <= n[k] <= 500 for k in ("x", "y"))
                  and isinstance(n.get("text"), str) and len(n["text"]) <= MAX_NOTE_TEXT
                  and isinstance(n.get("show_players", False), bool))
            if not ok:
                raise ValueError("A note has an id, a square (x, y), up to %d characters of text and show_players true or "
                                 "false." % MAX_NOTE_TEXT)
            clean.append({"id": n["id"], "x": n["x"], "y": n["y"], "text": n["text"], "show_players": bool(n.get("show_players"))})
        with self.lock:
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp = f.with_suffix(".tmp")
            tmp.write_text(json.dumps({"map": req["map"], "notes": clean}, indent=1), encoding="utf-8")
            tmp.replace(f)
        return 200, {"ok": True, "notes": clean}

    # ------------------------------------------------------------------ VIEW-01: map import (Universal VTT)
    def import_map(self, req):
        import map_import
        if self.table_dir is None:
            raise ValueError("The service was started without the table's folder: the picture has nowhere to go.")
        name, data, party, foes = req.get("name"), req.get("data"), req.get("party"), req.get("foes")
        pic, grid, cells, ambient = req.get("picture"), req.get("grid"), req.get("cells"), req.get("ambient", "dark")
        sq = lambda v: isinstance(v, list) and len(v) == 2 and all(isinstance(n, int) and not isinstance(n, bool) for n in v)
        if not isinstance(name, str) or not 0 < len(name.strip()) <= 80:
            raise ValueError("A map name, up to 80 characters.")
        if not sq(party) or not isinstance(foes, dict) or not sq(foes.get("at")) \
                or not isinstance(foes.get("creature"), str) or not isinstance(foes.get("count"), int):
            raise ValueError("A map import has the file, the party's square and the creatures (creature, count, square).")
        # MAP RULE (GM 2026-10-20) and the grid tools: the GM's squares (cells: {wall, door}); a picture with its grid
        if cells is not None and not isinstance(cells, dict):
            raise ValueError("The squares are {wall: [[x, y], ...], door: [[x, y], ...]}.")
        try:
            if pic is not None:
                if not isinstance(pic, str) or not isinstance(grid, dict) or ambient not in ("dark", "bright") or cells is None:
                    raise ValueError("A picture needs its grid, its squares and dark or bright.")
                sc, image, ext = map_import.convert_picture(pic.split(",", 1)[-1], grid, cells, name.strip(), tuple(party),
                                                            foes["creature"], foes["count"], tuple(foes["at"]), creature_names(),
                                                            ambient)
            else:
                sc, image, ext = map_import.convert(self._uvtt(data), name.strip(), tuple(party), foes["creature"],
                                                    foes["count"], tuple(foes["at"]), creature_names(), cells=cells)
        except map_import.ImportError_ as e:
            raise ValueError(str(e))
        with self.lock:
            scenario = map_import.write(sc, image, ext, scenarios_dir=self.scenarios_dir, table_dir=self.table_dir)
        return 200, {"ok": True, "scenario": scenario, "walls": len(sc["walls"]), "lights": len(sc["lighting"]["lights"])}

    # ------------------------------------------------------------------ REGION-01: a standard terrain battle map
    def terrain_battle(self, req):
        """GM 2026-10-20: "The outdoor map can simply create a popup of a standard terrain battle map." The region map's
        encounter (or the GM) asks for one: terrain, creature, count, seed, night; written to sim/scenarios/region/."""
        import terrain_battle
        terrain, creature, count, seed, night = req.get("terrain"), req.get("creature"), req.get("count", 4), req.get("seed", 1), req.get("night", False)
        if terrain not in terrain_battle.TERRAINS:
            raise ValueError("Terrain: one of %s." % ", ".join(terrain_battle.TERRAINS))
        lib = creature_names()
        if creature is None:
            creature = terrain_battle.suggested(terrain, lib)[0]
        if creature not in lib:
            raise ValueError("%s has no simulator stat block yet." % creature)
        if not (isinstance(count, int) and not isinstance(count, bool) and 1 <= count <= 12) or not isinstance(seed, int) or not isinstance(night, bool):
            raise ValueError("Count 1-12, an integer seed, night true or false.")
        design, context = req.get("design") or {}, req.get("context") or {}   # MAPGEN-01: the GM's preferences, the hex's features
        if not isinstance(design, dict) or not isinstance(context, dict):
            raise ValueError("design and context are objects.")
        sc = terrain_battle.build(terrain, creature, count, lib, seed, night, design=design, context=context)
        out = self.scenarios_dir / "region"
        with self.lock:
            name = terrain_battle.write(sc, out_dir=out)
        return 200, {"ok": True, "scenario": name, "terrain": terrain, "creature": creature, "count": count,
                     "suggested": terrain_battle.suggested(terrain, lib)}

    # ------------------------------------------------------------------ MAPGEN-02: a site drawn as indoor maps
    def site_map(self, req):
        """GM 2026-10-26 (goal 19, "in LM Studio"): a site on a made region (dungeon, cave, ruin, lair) drawn as indoor
        maps from the GM's preferences. The local model designs it (tools/site_maps.py), the code lays it out and checks
        it; each level is written into sim/scenarios/sites/<project>/<region>/ and its rooms' descriptions become the
        GM's notes on that map. A model that gives nothing usable is an error the GM sees: never a scripted map."""
        import site_maps
        creature, count = req.get("creature"), req.get("count", 4)
        lib = creature_names()
        if creature not in lib:
            raise ValueError("%s has no simulator stat block yet." % creature)
        if not (isinstance(count, int) and not isinstance(count, bool) and 1 <= count <= 12):
            raise ValueError("Count 1-12.")
        texts = {k: req.get(k) or "" for k in ("project", "region", "place")}
        if not all(isinstance(v, str) and len(v) <= 80 for v in texts.values()):
            raise ValueError("project, region and place are names of up to 80 characters.")
        prefs, context = req.get("prefs") or {}, req.get("context") or {}
        if not isinstance(prefs, dict) or not isinstance(context, dict):
            raise ValueError("prefs and context are objects.")
        try:
            prefs, context = site_maps.check_prefs(prefs), site_maps.check_context(context)
            designer = self.site_designer or (lambda p, c: site_maps.ask_model(p, c, self.llm_url, self.llm_model))
            raw, facts = designer(prefs, context)                    # minutes on a local model: no lock held
            design, fixes = site_maps.check_design(raw, prefs)
            levels = site_maps.build(design, prefs, creature, count, lib, model=facts.get("model"), where=texts["place"])
        except site_maps.SiteMapError as e:
            raise ValueError(str(e))
        with self.lock:
            names = site_maps.write(levels, texts["project"], texts["region"], texts["place"], out_dir=self.scenarios_dir / "sites")
            for sc in levels:                                         # the rooms' descriptions: the GM's notes on that map
                f = self._notes_file({"map": sc["map_name"]})
                try:
                    old = json.loads(f.read_text(encoding="utf-8")).get("notes", []) if f.is_file() else []
                except (OSError, ValueError):
                    old = []
                notes = [n for n in old if not str(n.get("id", "")).startswith("room-")] + sc["notes"]
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(json.dumps({"map": sc["map_name"], "notes": notes[:MAX_NOTES]}, indent=1), encoding="utf-8")
        return 200, {"ok": True, "scenarios": names, "name": design["name"], "summary": design["summary"],
                     "levels": design["levels"], "rooms": len(design["rooms"]), "fixes": fixes, "model": facts,
                     "size": [[max(w[0] for w in sc["wall_cells"]) + 1, max(w[1] for w in sc["wall_cells"]) + 1] for sc in levels]}

    def site_model(self, req):
        """MAPGEN-02: is the local model server there, and is the model loaded? (The site dialog says so first.)"""
        import site_maps
        from urllib.request import urlopen
        try:
            base = site_maps.check_local(self.llm_url)
            with urlopen(base + "/models", timeout=3) as r:
                ids = [m.get("id") for m in json.loads(r.read().decode()).get("data", [])]
        except site_maps.SiteMapError as e:
            return 200, {"ok": True, "ready": False, "url": self.llm_url, "model": self.llm_model, "why": str(e)}
        except (OSError, ValueError):
            return 200, {"ok": True, "ready": False, "url": self.llm_url, "model": self.llm_model,
                         "why": "No local model server answers at %s (start LM Studio's server)." % self.llm_url}
        ready = self.llm_model in ids
        return 200, {"ok": True, "ready": ready, "url": self.llm_url, "model": self.llm_model,
                     "why": "" if ready else "LM Studio answers, but %s is not among its models." % self.llm_model}

    # ------------------------------------------------------------------ ATLAS-01: the map database (GM 2026-10-22)
    ATLAS_ROUTES = ("list", "get", "save", "delete", "move", "project", "export", "import")

    def atlas(self, req, what):
        """GM: "create a database that allows multiple maps to be connected"; "a filing protocol that keeps all maps
        associated with a project, and a place for spare maps" (tools/atlas.py; project None is Spare maps)."""
        import atlas
        try:
            if what == "list":
                return 200, {"ok": True, "maps": atlas.list_maps(self.atlas_dir), "projects": atlas.list_projects(self.atlas_dir)}
            if what == "get":
                return 200, {"ok": True, "id": req.get("id"), "map": atlas.get_map(req.get("id"), self.atlas_dir)}
            if what == "export":
                return 200, {"ok": True, "bundle": atlas.export_project(req.get("project"), self.atlas_dir)}
            with self.lock:
                if what == "save":
                    project = req["project"] if "project" in req else atlas.KEEP
                    return 200, {"ok": True, "id": atlas.save_map(req.get("map"), req.get("id"), self.atlas_dir, project=project)}
                if what == "delete":
                    atlas.delete_map(req.get("id"), self.atlas_dir)
                    return 200, {"ok": True}
                if what == "move":
                    atlas.move_map(req.get("id"), req.get("project"), self.atlas_dir)
                    return 200, {"ok": True}
                if what == "import":
                    return 200, {"ok": True, "project": atlas.import_project(req.get("bundle"), self.atlas_dir)}
                if what == "project":
                    action, pid = req.get("action"), req.get("project")
                    if action == "create":
                        return 200, {"ok": True, "project": atlas.create_project(req.get("name"), self.atlas_dir)}
                    if action == "rename":
                        atlas.rename_project(pid, req.get("name"), self.atlas_dir)
                        return 200, {"ok": True, "project": pid}
                    if action == "delete":
                        atlas.delete_project(pid, self.atlas_dir)
                        return 200, {"ok": True}
        except atlas.AtlasError as e:
            raise ValueError(str(e))
        raise ValueError("Unknown atlas request.")

    # ------------------------------------------------------------------ REFEREE-01: the spell rules and the GM's clarifications
    def spells_list(self, req):
        """Every SRD 5.2.1 spell with what the engine plays of it and the rules the referee uses (the GM's wording over
        the SRD's). GM 2026-10-22: "allow ambiguous descriptions to be modified for clarity for that DM"."""
        import spell_rules
        path = getattr(self, "clarify_path", None)
        rows = []
        for r in spell_rules.coverage(path):
            s = spell_rules.spell(r["name"], path)
            rows.append(dict(r, school=s["school"], classes=s["classes"], casting_time=s["casting_time_text"],
                             range=s["range"], components=s["components"], duration=s["duration"]["text"],
                             concentration=s["duration"]["concentration"], area=s["area"], targets=s["targets"],
                             save=s["save"], attack=s["attack"], damage=s["damage"], healing=s["healing"],
                             conditions=s["conditions"], text=s["text"], srd_text=s.get("srd_text", s["text"]),
                             clarification=s.get("clarification")))
        return 200, {"ok": True, "spells": rows, "source": "SRD 5.2.1 (CC-BY-4.0)"}

    def spells_clarify(self, req):
        import spell_rules
        name, text, fields = req.get("spell"), req.get("text"), req.get("fields") or {}
        if not isinstance(name, str) or not isinstance(fields, dict) or (text is not None and not isinstance(text, str)):
            raise ValueError("A clarification is {spell, text, fields, note, clear}.")
        try:
            s = spell_rules.clarify(name, text=text, fields=fields, note=str(req.get("note") or ""),
                                    path=getattr(self, "clarify_path", None), clear=bool(req.get("clear")))
        except spell_rules.SpellRuleError as e:
            raise ValueError(str(e))
        return 200, {"ok": True, "spell": name, "clarified": s["clarified"], "text": s["text"]}

    def rules_monitor(self, req):
        """RULES-MONITOR-01 (GM 2026-10-28): the Rules monitor. op: state, on, off, clear, model (is LM Studio there?)."""
        op = req.get("op", "state")
        if op == "model":
            return self.site_model({})
        if op in ("on", "off"):
            self.monitor.switch(op == "on")
        elif op == "clear":
            self.monitor.clear()
        elif op != "state":
            raise ValueError("Unknown request.")
        return 200, dict(self.monitor.view(), ok=True)

    @staticmethod
    def terrain_suggest(req):
        """The terrain's usual foes that have a simulator stat block (the battle popup lists them first)."""
        import terrain_battle
        if req.get("terrain") not in terrain_battle.TERRAINS:
            raise ValueError("Terrain: one of %s." % ", ".join(terrain_battle.TERRAINS))
        return 200, {"ok": True, "suggested": terrain_battle.suggested(req["terrain"], creature_names())}

    @staticmethod
    def _uvtt(data):
        if not isinstance(data, str):
            raise ValueError("A map import has the file, the party's square and the creatures (creature, count, square).")
        try:
            return json.loads(data)
        except ValueError:
            raise ValueError("That file is not JSON: a Universal VTT file (.dd2vtt, .uvtt) is expected.")

    def import_draft(self, req):
        """MAP RULE: a Universal VTT file's thin walls drafted into wall and doorway squares, for the GM to correct."""
        import map_import
        try:
            return 200, dict(map_import.draft(self._uvtt(req.get("data"))), ok=True)
        except map_import.ImportError_ as e:
            raise ValueError(str(e))

    # REMIX-02: data packs, proposals, proof and campaign layers (loopback GM console).
    def remix_request(self, route, req):
        from remix_service import Conflict
        if not self.play.acquire(blocking=False):
            raise Conflict("A fight is being prepared; retry shortly.")
        try:
            if route == "/api/adventures/unload" and req.get("stop_fight") is True and self.live and not self.live.done:
                self.live.quit()                                 # GM 2026-10-24: End the adventure: stop the fight, then unload
                self.live.thread.join(30)                        # its end writes the carried state back (rests)
            if route in ("/api/remix/apply", "/api/remix/remove", "/api/adventures/unload") and self.live and not self.live.done:
                raise Conflict("Finish the current fight before changing Remix or unloading an adventure.")
            if route == "/api/remix/catalog":
                out = self.remix.catalog_view()
            elif route == "/api/remix/state":
                out = {"ok": True, "campaign": self.remix.state(req.get("campaign", "default"))}
            elif route == "/api/remix/propose":
                out = self.remix.propose(req)
                import traps                                         # GM 2026-10-24: SRD traps for the party's level band
                out = dict(out, traps=traps.suggest(req.get("level") if isinstance(req.get("level"), int) else 1))
            elif route == "/api/remix/traps":
                import traps
                lv = req.get("level")
                out = dict(traps.suggest(lv if isinstance(lv, int) and not isinstance(lv, bool) and 1 <= lv <= 20 else 1), ok=True)
            elif route == "/api/remix/apply":
                out = self.remix.apply(req)
            elif route == "/api/remix/remove":
                out = self.remix.remove(req)
            elif route == "/api/remix/proof/start":
                out = self.remix.start_proof(req, pregens())
            elif route == "/api/remix/proof/status":
                out = self.remix.proof_status(req)
            elif route == "/api/adventures/state":
                running = bool(self.live and not self.live.done)
                out = dict(self.packs.listing(), ok=True, fight_running=running,   # GM 2026-10-24: End the adventure asks
                           fight_frozen=bool(running and getattr(self.live, "frozen", False)))
            elif route == "/api/adventures/check":                   # ENCOUNTER-CHECK-01: are the encounters winnable?
                out = dict(self.check_encounters(req), ok=True)
            elif route == "/api/adventures/check-status":
                out = {"ok": True, "check": self.checks.view(req.get("check"))}
            elif route == "/api/adventures/plan":                    # ADVENTURE-01: the Adventure page's places
                out = dict(self.packs.plan(req.get("pack")), ok=True)
            elif route in ("/api/adventures/load", "/api/adventures/unload"):
                with self.remix.lock:
                    if self.remix.busy:
                        raise Conflict("Wait for proof to finish before changing loaded adventures.")
                    pack = req.get("pack")
                    if route.endswith("/unload"):
                        self.packs.unload(pack)
                        self.unloaded_pack = pack
                        self.remix.proposals = {k: p for k, p in self.remix.proposals.items() if p['encounter'].split(':')[0] != pack}
                        self.remix.jobs.clear()
                        # Finished live/replay snapshots can contain adventure data: release them too.
                        if self.live_scenario and self.live_scenario.get("source_scenario", "").startswith("pack/" + pack + "/"):
                            self.live = self.live_scenario = None
                        self.sessions.clear(); self.order.clear()
                    else:
                        self.packs.load(pack)
                    self.flavor.end_adventure(pack)                     # FLAVOR-01: paint for this adventure comes off
                    if route.endswith("/unload"):
                        self.market.close_pack(pack)                    # MARKET-01: its open shop closes (shops are kept)
                    self.remember_adventures()
                    out = dict(self.packs.listing(), ok=True, scenarios=self.available_scenarios())
            else:
                return 404, {"ok": False, "error": "Unknown Remix route."}
            return 200, out
        finally:
            self.play.release()

    # ADVENTURE-01 (GM 2026-10-21: "what happened to adventures?"): packs started unloaded at every service start, so the
    # loaded ones are kept in a small file (only their IDs; never in the pack folder) and loaded again at the next start.
    def remember_adventures(self):
        if not self.adventure_state:
            return
        path = Path(self.adventure_state)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"loaded": sorted(self.packs.loaded)}, indent=1), encoding="utf-8")
        tmp.replace(path)

    def restore_adventures(self):
        """Load the packs that were loaded when the service last stopped; one that no longer loads is reported and left."""
        path = Path(self.adventure_state) if self.adventure_state else None
        if not path or not path.is_file():
            return [], []
        try:
            wanted = json.loads(path.read_text(encoding="utf-8")).get("loaded") or []
        except (OSError, ValueError, AttributeError):
            return [], ["the remembered adventures file could not be read"]
        done, problems = [], []
        for pack in wanted if isinstance(wanted, list) else []:
            try:
                self.packs.load(pack)
                done.append(pack)
            except (OSError, ValueError, TypeError) as e:
                problems.append("%s: %s" % (pack, e))
        return done, problems

    def stage_state(self, req):
        seat = self.check_seat(req)
        with self.lock:
            return 200, {"ok": True, "stage": self._stage_view(seat, self.clock())}

    # ------------------------------------------------------------------ FLAVOR-01: the table's Flavor (tools/table_flavor.py)
    def flavor_gm(self, req):
        """The GM's console: the whole collection (unchanged: only the revision, when the page already has it), and the
        players' requests when they changed (PLAYER-FLAVOR-01)."""
        state, rev = self.flavor.get()
        asks, mark = self.flavor.waiting()
        out = {"ok": True, "rev": rev, "asks_rev": mark}
        if req.get("asks_rev") != mark:
            out["asks"] = asks
        out.update({"unchanged": True} if req.get("rev") == rev else {"flavor": state})
        return 200, out

    def flavor_rule(self, req):
        """PLAYER-FLAVOR-01: the GM approves a player's look or refuses it (no note goes to the player)."""
        if not isinstance(req.get("actor"), str):
            raise ValueError("Name the creature whose look was asked for.")
        state, rev = self.flavor.rule(req["actor"], req.get("approve") is True)
        return 200, {"ok": True, "rev": rev, "flavor": state}

    def flavor_own(self, seat):
        """PLAYER-FLAVOR-01: the rules names of the creatures a seat's player controls: its character, and what that
        character summoned (sim/summons.py: a familiar, a steed, the undead it raised)."""
        import summons, table_seats
        if not (self.live and seat.get("character")):
            return []
        everyone = self.live.sim.sc["combatants"]
        me = next((c for c in everyone if c.get("pc") and table_seats._same(c.get("name"), seat["character"])), None)
        if not me:
            return []
        made = summons.of(self.live.sim).made
        return [me["name"]] + [c["name"] for c in everyone if c is not me and (made.get(c.get("id")) or {}).get("by") == me["id"]]

    def flavor_ask(self, seat, req):
        """PLAYER-FLAVOR-01: a player's look for a creature they control, waiting for the GM."""
        actor = req.get("actor")
        if not isinstance(actor, str) or actor not in self.flavor_own(seat):
            return 403, {"ok": False, "error": "Flavor here is for your own character and the creatures you control."}
        map_name = ((self.live_scenario or {}).get("map") or {}).get("name") or ""
        return 200, {"ok": True, "flavor": self.flavor.ask(seat["name"], seat["character"], actor, map_name, req.get("flavor"))}

    def flavor_save(self, req):
        import table_flavor
        try:
            state, rev = self.flavor.save(req.get("flavor"), req.get("rev"))
        except table_flavor.Conflict as e:
            state, rev = self.flavor.get()
            return 409, {"ok": False, "error": str(e), "rev": rev, "flavor": state}
        return 200, {"ok": True, "rev": rev, "flavor": state}

    # ------------------------------------------------------------------ MAP-PAINT-01: the GM's paint over a map
    def map_paint_get(self, req, player=False):
        import map_paint
        try:
            player = player or bool(req.get("player"))             # the players' window on the GM's computer asks as a player
            return 200, dict(self.map_paint.get(req.get("map"), req.get("rev"), player=player), ok=True)
        except (map_paint.PaintError, TypeError, ValueError) as e:
            return 400, {"ok": False, "error": str(e)}

    def map_paint_save(self, req):
        import map_paint
        try:
            return 200, dict(self.map_paint.save(req.get("map"), req.get("picture"), req.get("shown")), ok=True)
        except map_paint.PaintError as e:
            return 400, {"ok": False, "error": str(e)}

    def flavor_player(self, seat, req):
        """A seat's Flavor: this map's (and every map's) for the creatures it sees now; shared footnotes only. PLAYER-FLAVOR-01:
        `mine`, the creatures it controls and its own requests still waiting; no other seat sees those."""
        import table_flavor, table_seats
        state, rev = self.flavor.get()
        snap = table_seats.player_view(self.live.snapshot(1 << 30), seat["character"]) if self.live else {}
        names = [c.get("name") for c in (snap.get("state") or {}).get("combatants") or [] if c.get("name")]
        map_name = ((self.live_scenario or {}).get("map") or {}).get("name") or ""
        view = table_flavor.player_view(state, map_name, names)
        own = self.flavor_own(seat)
        asks, asked = self.flavor.waiting(seat["character"]) if seat.get("character") else ([], 0)
        # changes when the Flavor, what the seat sees, what it controls or a request does
        mark = "%d:%s:%s:%d:%s" % (rev, map_name, ",".join(sorted(names)), asked, ",".join(sorted(own)))
        if req.get("rev") == mark:
            return 200, {"ok": True, "rev": mark, "unchanged": True}
        return 200, {"ok": True, "rev": mark, "flavor": view, "mine": {"actors": own, "pending": {a["actor"]: a["flavor"] for a in asks}}}

    # ------------------------------------------------------------------ MARKET-01: the GM's market (sim/market.py)
    def market_ctx(self):
        """What the market needs from the table: the loaded adventures' places, the party in the live fight (name, class,
        weapons, armor: for the magic items a shop suggests and the GM's warnings), its level, and who is at the table."""
        loaded = tuple(sorted(self.packs.loaded))
        if self._market_places[0] != loaded:
            places = {}
            for pack in loaded:
                try:
                    plan = self.packs.plan(pack)
                except (OSError, ValueError):
                    continue
                places[pack] = {"name": plan["name"], "places": [{"key": p["key"], "title": p["title"]} for p in plan["places"]]}
            self._market_places = (loaded, places)
        party, classes = [], {}
        cat = self.market.catalog
        weapons = {v["name"] for v in cat.values() if v["kind"] == "weapon"}
        armor = [v["name"] for v in cat.values() if v["kind"] == "armor" and v["name"] != "Shield"]
        for c in (self.live.sim.sc["combatants"] if self.live else []):
            if not c.get("pc"):
                continue
            cls = str(c.get("class") or "").title()
            names = [w.get("name") for w in (c.get(k) for k in ("weapon", "ranged") + MORE_ATTACKS) if isinstance(w, dict)]
            note = str(c.get("note") or "")
            party.append({"name": c["name"], "class": cls, "weapons": [n for n in names if n in weapons],
                          "armor": next((a for a in sorted(armor, key=len, reverse=True) if a in note), ""),
                          "shield": "Shield" in note and cls in ("Fighter", "Paladin", "Cleric", "Ranger", "Barbarian")})
            classes[c["name"]] = cls
        chars = self.live_characters() + [s["character"] for s in self.seats.gm({}).get("seats", []) if s["character"]]
        return {"places": self._market_places[1], "party": party, "classes": classes, "characters": chars,
                "level": (self.live_scenario or {}).get("level")}

    def market_gm(self, req):
        import market, table_chat
        try:
            out = self.market.gm(req, self.market_ctx())
        except market.Conflict as e:
            return 409, {"ok": False, "error": str(e), "market": self.market.gm({"op": "state"}, self.market_ctx())}
        if self.market.announce:                                  # the table sees what was bought (not the prices)
            with self.lock:
                table_chat.say(self.chat, "Market", self.market.announce, self.clock())
        return 200, out

    def market_player(self, seat, req):
        """A seat shops for its own character only (the ticket's, never a name the page sends)."""
        return 200, self.market.player(seat["character"], dict(req, seat=seat["name"]))

    # ------------------------------------------------------------------ JOIN-01: the players' door (tools/table_seats.py)
    def live_characters(self):
        """The player characters in the current fight, by name (what a joining player may ask to play)."""
        state = (self.live.snapshot(1 << 30) if self.live else {}).get("state") or {}
        return [c["name"] for c in state.get("combatants") or [] if c.get("pc")]

    def table_party(self, req):
        """GM 2026-10-25 ("the DM handoff will need to transfer the maps and logs to the server to make them available to
        the guest DM"): the party chosen on Play an adventure, kept by Mythastria (beside the loaded adventures, never
        committed) instead of one browser: {members (test heroes), level, characters (the saved characters' sheets)}.
        op get | save. Whoever holds the GM role reads and changes the same party."""
        st = Path(self.adventure_state) if self.adventure_state else None
        path = st.with_name(st.stem + "_party.json") if st else None   # loaded.json -> loaded_party.json (a test service: its own)
        op = req.get("op", "get")
        if op == "get":
            try:
                return 200, {"ok": True, "party": json.loads(path.read_text(encoding="utf-8")) if path else None}
            except (OSError, ValueError):
                return 200, {"ok": True, "party": None}
        if op != "save":
            raise ValueError("op is get or save.")
        p = req.get("party")
        if not isinstance(p, dict):
            raise ValueError("Save a party: {members, level, characters}.")
        members = p.get("members") or []
        chars = p.get("characters") or []
        level = p.get("level")
        if not isinstance(members, list) or any(m not in pregens() for m in members):
            raise ValueError("Choose saved characters.")
        if not isinstance(chars, list) or any(not isinstance(c, dict) or not isinstance(c.get("id"), str)
                                               or not isinstance(c.get("name"), str) for c in chars):
            raise ValueError("Characters are saved character sheets (each with its id and name).")
        if len(members) + len(chars) > 7:
            raise ValueError("A party has at most 7 characters.")
        if not (isinstance(level, int) and not isinstance(level, bool) and 1 <= level <= top_level()):
            raise ValueError("The party's level is 1 to %d." % top_level())
        if not path:
            raise ValueError("Mythastria keeps no adventure state here (--adventure-state).")
        party = {"members": members, "level": level, "characters": chars, "saved": int(self.clock())}
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(party), encoding="utf-8")
        tmp.replace(path)
        return 200, {"ok": True, "party": party}

    def dm_characters(self):
        """DM-SWAP-01: the player characters the owning GM may play while another is the GM: the fight's player
        characters no player's seat holds."""
        held = {str(s.get("character") or "").lower() for s in self.seats.gm({}).get("seats", []) if s.get("character")}
        return [n for n in self.live_characters() if n.lower() not in held]

    def dm_gm(self, req):
        """DM-SWAP-01, the GM door: the request waiting, approve (with the character to play), refuse, take back."""
        out = self.handoff.gm(req, self.dm_characters())
        return 200, out

    def handed_request(self, route, req):
        """DM-SWAP-01: the GM door while another is the GM is the old GM's player screen: table requests go through as
        the seat GM (the character he chose), the swap's own route for Take back; every other GM request is refused."""
        if route == "/api/dm":
            return self.dm_gm(req)
        if route in DOOR_ROUTES and route != "/api/join":
            return self.seat_request(route, req, self.handoff.old_dm_seat())
        who = (self.handoff.view().get("held") or {}).get("to", "another player")
        return 423, {"ok": False, "handed": True, "error": "%s is the GM now. Take back the GM role first." % who}

    def seats_gm(self, req):
        if req.get("op") == "watch_clear":                        # CHEAT-LOG-01: the GM has looked
            self.door_watch.clear()
            req = {"op": "state"}
        return 200, dict(self.seats.gm(req, self.live_characters()), link=getattr(self, "players_link", None),
                         door_log=self.door_guard.recent(), watch=self.door_watch.view())

    def notice_version(self):
        """JOIN-01 notice (GM 2026-10-22: a privacy notice and an age check before joining): the version of the table's
        notice (--table's table-notice.json, the text the pages show). None when there is no such file."""
        f = Path(self.table_dir) / "table-notice.json" if self.table_dir else None
        try:
            stamp = f.stat().st_mtime
        except (OSError, AttributeError):
            return None
        if getattr(self, "_notice", (None, None))[0] != stamp:
            try:
                self._notice = (stamp, json.loads(f.read_text(encoding="utf-8")).get("version"))
            except (OSError, ValueError, AttributeError):
                self._notice = (stamp, None)
        return self._notice[1]

    def forget_old(self, days=KEEP_DAYS):
        """JOIN-01 notice (GM 2026-10-22: "14 days, then deleted by Mythastria itself when it starts once a day"): chat
        pictures and sounds and the stand-in log older than `days` are deleted."""
        cutoff = self.clock() - days * 86400
        gone = 0
        for f in (self.chat_media_dir.glob("*") if self.chat_media_dir.is_dir() else []):
            try:
                if f.is_file() and f.stat().st_mtime < cutoff:
                    f.unlink()
                    gone += 1
            except OSError:
                pass
        return gone

    def door_hello(self):
        import table_seats
        return {"ok": True, "door": "players", "format": FORMAT, "open": self.seats.open, "characters": self.live_characters(),
                "notice": self.notice_version(),
                "beat": table_seats.BEAT, "scenarios": [], "scenario_aliases": {}, "creatures": []}   # the GM's lists stay on the GM door

    def door_request(self, route, req):
        """A players'-door request: the seat comes from its ticket only (table_seats.NoSeat when there is none), and
        what goes back is cut to what that seat may see."""
        import table_seats
        if route == "/api/join":
            return 200, self.seats.player(req)
        seat = self.seats.seat_for(req.get("ticket"))
        self.seats.check_notice(seat)                             # a new notice: accept it again on the join page
        if route == "/api/dm":                                    # DM-SWAP-01: ask to be the GM, or see the answer
            return 200, self.handoff.player(seat, req)
        return self.seat_request(route, req, seat)

    def seat_request(self, route, req, seat):
        """What a seat may do at the table (the players' door; the GM door while another is the GM, as the seat GM)."""
        import table_seats
        if self.panic and route not in PANIC_READS:               # GM 2026-11-01: the Panic Button
            return 423, {"ok": False, "panic": True, "refused": "The GM has stopped the game."}
        req = dict(req, seat=seat["name"])
        if route == "/api/live/act":
            if req.get("op") in ("undo_approve", "undo_refuse"):
                raise ValueError("Only the GM answers an undo.")
            state = (self.live.snapshot(1 << 30) if self.live else {}).get("state") or {}
            actor = next((c for c in state.get("combatants") or [] if c.get("id") == req.get("actor")), None)
            if not (actor and actor.get("pc") and seat["character"] and table_seats._same(actor["name"], seat["character"])):
                return 409, {"ok": False, "error": "%s plays %s: wait for that turn." % (seat["name"], seat["character"] or "no character")}
            if self.live and self.live.gm_control.get(actor["id"]):         # GM 2026-10-24: the GM plays it now
                return 409, {"ok": False, "error": "The GM is playing %s now." % actor["name"]}
            code, out = self.live_act(req)
        elif route == "/api/live/control":                            # GM 2026-10-24: hand my character to the GM
            code, out = self.live_control(req, seat)
        elif route == "/api/live/reaction":                           # SPELL-BATCH-02: my character's Reaction
            code, out = self.live_reaction(req, seat)
        elif route == "/api/live/stealth":                            # STEALTH-01: my roll in the group stealth check
            code, out = self.live_stealth(req, seat)
        elif route == "/api/live/initiative":                         # INITIATIVE-01: my character's Initiative
            code, out = self.live_initiative(req, seat)
        elif route == "/api/live/aim":                                # HINTS-01 H4: who my area spell would catch
            code, out = self.live_aim(req, seat)
        elif route == "/api/live/state":
            code, out = self.live_state(req)
        elif route == "/api/chat":
            code, out = self.chat_post(req)
        elif route == "/api/roll":
            code, out = self.roll(req)
        elif route == "/api/chat/log":
            code, out = self.chat_log(req)
        elif route == "/api/stage":
            code, out = self.stage_command(req)
        elif route == "/api/stage/state":
            code, out = self.stage_state(req)
        elif route == "/api/notes":
            code, out = self.notes_load(req)
            out = dict(out, notes=table_seats.player_notes(out.get("notes")))
        elif route == "/api/flavor":                                  # FLAVOR-01: what this seat may see
            code, out = self.flavor_player(seat, req)
        elif route == "/api/flavor/ask":                              # PLAYER-FLAVOR-01: a look, for the GM to approve
            code, out = self.flavor_ask(seat, req)
        elif route == "/api/map_paint":                               # MAP-PAINT-01: only while the GM shows it
            code, out = self.map_paint_get(req, player=True)
        elif route == "/api/market":                                  # MARKET-01: the open shop and this seat's own cart
            code, out = self.market_player(seat, req)
        else:
            return 404, {"ok": False, "error": "Not found"}
        out = dict(out)
        out.pop("timeline", None)                                     # GM-UNDO-01: the GM's
        if isinstance(out.get("lines"), list) and self.live:          # play-test 2026-11-02: an action's own reply
            out["lines"] = table_seats.player_lines(out["lines"], self.live.snapshot(1 << 30))
        if "live" in out:                                             # HINTS-01: the seat's own hints, at its level
            out["live"] = table_seats.player_view(out["live"], seat["character"], seat.get("hints", "off"),
                                                  watching=not seat["character"])   # GM 2026-10-25: a watcher sees every turn
            out["live"] = __import__("attitude").player_view(out["live"])   # GM 2026-10-24: no prep, morale or GM cards
            out["live"] = __import__("scenes").player_view(out["live"])     # GM 2026-10-26: no scene cards
        if "scenario" in out:
            out["scenario"] = table_seats.player_scenario(out["scenario"])
        out["seat"] = {"name": seat["name"], "character": seat["character"], "hints": seat.get("hints", "off"),
                       "hints_max": self.seats.hint_limit(seat)}   # H3: the highest level the GM allows this seat
        return code, out


def make_handler(service, token, port, table, gm_door=True):
    host = "127.0.0.1:%d" % port
    origin_ok = "http://" + host
    table = Path(table).resolve() if table else None

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, obj=None, body=None, ctype="application/json; charset=utf-8"):
            data = body if body is not None else json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def boundary(self):
            if self.headers.get_all("Host", []) != [host]:
                self.send(403, {"ok": False, "error": "Host must be " + host}); return False
            o = self.headers.get("Origin")
            if o is not None and o != origin_ok:
                self.send(403, {"ok": False, "error": "Cross-origin requests are refused."}); return False
            return True

        def do_GET(self):
            if not self.boundary():
                return
            path = urlparse(self.path).path
            if path == "/api/hello":
                return self.send(200, {"ok": True, "format": FORMAT, "token": token, "scenarios": service.available_scenarios(), "scenario_tree": service.scenario_tree(), "scenario_aliases": service.scenario_aliases(), "creatures": sorted(creature_names()),
                                       "members": pregens(), "authority": "simulator (Mythastria sim/)",
                                       "handed": service.handoff.view()["held"] if gm_door else None})   # DM-SWAP-01
            if path == "/api/rules/social":                       # GM 2026-10-25: the optional Social rules pack's page
                import social_pack
                rows = [dict(r, anchor=social_pack.anchor(r["name"])) for r in social_pack.library_rows()]
                return self.send(200, {"ok": True, "pack": social_pack.pack(), "creatures": rows})
            if path.startswith("/api/"):
                return self.send(404, {"ok": False, "error": "Not found"})
            if path.startswith("/chat-media/"):                       # CHAT-FUN-01: a picture or sound shared in the chat
                media = service.chat_media(path[len("/chat-media/"):])
                if not media:
                    return self.send(404, {"ok": False, "error": "Not found"})
                return self.send(200, body=media[1], ctype=media[0])
            if not table:
                return self.send(404, {"ok": False, "error": "No table folder served (--table)."})
            if gm_door and service.handoff.active():                  # DM-SWAP-01: the old GM's screen is a player's
                from urllib.parse import parse_qs
                where = handed_page(path, parse_qs(urlparse(self.path).query))
                if where:
                    self.send_response(302)
                    self.send_header("Location", where)
                    self.send_header("Content-Length", "0")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    return
            rel = path.lstrip("/") or "index.html"
            f = (table / rel).resolve()
            if not str(f).startswith(str(table)) or not f.is_file():
                return self.send(404, {"ok": False, "error": "Not found"})
            ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            if f.suffix == ".mjs":
                ctype = "text/javascript"
            if f.suffix == ".wasm":
                ctype = "application/wasm"
            self.send(200, body=f.read_bytes(), ctype=ctype)

        def do_POST(self):
            if not self.boundary():
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return self.send(400, {"ok": False, "error": "Bad length"})
            if not 0 < length <= ROUTE_BODY.get(urlparse(self.path).path, MAX_BODY):
                return self.send(400, {"ok": False, "error": "Request too large or empty"})
            try:
                req = json.loads(self.rfile.read(length).decode("utf-8"))
                assert isinstance(req, dict)
            except (ValueError, AssertionError):
                return self.send(400, {"ok": False, "error": "A JSON object is expected"})
            if not isinstance(req.get("token"), str) or not secrets.compare_digest(req["token"], token):
                return self.send(403, {"ok": False, "error": "Invalid session token; reload the page."})
            route = urlparse(self.path).path
            if gm_door and service.handoff.active():                  # DM-SWAP-01: another is the GM now
                try:
                    code, out = service.handed_request(route, req)
                except ValueError as e:
                    code, out = 400, {"ok": False, "error": str(e)}
                return self.send(code, out)
            try:
                service.director.check(route, req)                    # GUEST-DIRECTOR-01: controls the showrunner kept
                if route == "/api/new":
                    code, out = service.new(req)
                elif route == "/api/director":                        # GUEST-DIRECTOR-01: hand over, take back
                    code, out = 200, service.director.request(req)
                elif route == "/api/seats":                           # JOIN-01: the GM lets players in
                    code, out = service.seats_gm(req)
                elif route == "/api/dm":                              # DM-SWAP-01: a player asks to be the GM
                    code, out = service.dm_gm(req)
                elif route == "/api/step":
                    code, out = service.step(req)
                elif route == "/api/messages":
                    code, out = service.messages(req)
                elif route == "/api/stage":
                    code, out = service.stage_command(req)
                elif route == "/api/stage/state":
                    code, out = service.stage_state(req)
                elif route == "/api/roll":
                    code, out = service.roll(req)
                elif route == "/api/party":                           # GM 2026-10-25: the table's party (follows the GM role)
                    code, out = service.table_party(req)
                elif route == "/api/adventures/day":                  # GM 2026-10-24: rests and the party's day
                    code, out = service.adventure_day(req)
                elif route == "/api/adventures/downtime":             # GM 2026-10-26: crafting, brewing, scribing
                    code, out = service.adventure_downtime(req)
                elif route.startswith("/api/remix/") or route.startswith("/api/adventures/"):
                    code, out = service.remix_request(route, req)    # REMIX-02: the Remix page and adventure packs
                elif route == "/api/live/new":
                    code, out = service.live_new(req)
                elif route == "/api/remix":                           # REMIX-01: the Remix panel's offer
                    code, out = service.remix_offer(req)
                elif route == "/api/lineups":                         # Remix Live: saved creature lineups
                    code, out = service.lineups(req)
                elif route == "/api/live/state":
                    code, out = service.live_state(req)
                elif route == "/api/live/act":
                    code, out = service.live_act(req)
                elif route == "/api/live/scene":                     # GM 2026-10-24: attitudes, morale, truce
                    code, out = service.live_scene(req)
                elif route == "/api/prep":                           # GM 2026-10-24: Remix Prep's attitudes and morale
                    code, out = service.prep(req)
                elif route == "/api/live/ruling":                    # GM 2026-10-24: the GM rules an Ask the GM request
                    code, out = service.live_ruling(req)
                elif route == "/api/live/control":                   # GM 2026-10-24: the GM plays a character
                    code, out = service.live_control(req)
                elif route == "/api/live/reaction":                  # SPELL-BATCH-02: a Reaction asked (Answer for them)
                    code, out = service.live_reaction(req)
                elif route == "/api/live/stealth":                   # STEALTH-01: declared stealth, group stealth
                    code, out = service.live_stealth(req)
                elif route == "/api/live/initiative":                # INITIATIVE-01: Roll for them, Roll the rest
                    code, out = service.live_initiative(req)
                elif route == "/api/live/aim":                       # HINTS-01 H4: who an aimed area would catch
                    code, out = service.live_aim(req)
                elif route == "/api/live/social":                    # GM 2026-11-01: the Influence buttons
                    code, out = service.live_social(req)
                elif route == "/api/live/reaction-mode":             # OA-AUTO-01: the GM's Auto mode
                    code, out = service.live_reaction_mode(req)
                elif route == "/api/live/freeze":                    # GM 2026-10-24: freeze the fight or go on
                    code, out = service.live_freeze(req)
                elif route == "/api/live/srd":                       # BY-THE-SRD-01: the GM's By the SRD switch
                    code, out = service.live_srd(req)
                elif route == "/api/live/fly":                       # ON-THE-FLY-01: the GM's changes mid-fight
                    code, out = service.live_fly(req)
                elif route == "/api/oneshot":                        # ONE-SHOT-01: the GM's One-shot builder
                    code, out = service.one_shot(req)
                elif route == "/api/live/panic":                     # GM 2026-11-01: never door routes
                    code, out = service.live_panic(req)
                elif route == "/api/live/undo":
                    code, out = service.live_undo(req)
                elif route == "/api/live/timer":
                    code, out = service.live_timer(req)
                elif route == "/api/live/traps":                     # GM 2026-10-24: the GM's traps (sim/traps.py)
                    code, out = service.live_traps(req)
                elif route == "/api/live/mount-mode":                # MAP-LAYERS-01: controlled or independent mount
                    code, out = service.live_mount_mode(req)
                elif route == "/api/live/hazards":                   # HAZARDS-01: the GM's hazards, fear, contagions
                    code, out = service.live_hazards(req)
                elif route == "/api/live/sight":                     # SIGHT-01: which creatures each character sees
                    code, out = service.live_sight(req)
                elif route == "/api/live/light":                     # LIGHTS-01: the map's own light (the GM)
                    code, out = service.live_light(req)
                elif route == "/api/chat":
                    code, out = service.chat_post(req)
                elif route == "/api/chat/log":
                    code, out = service.chat_log(req)
                elif route == "/api/chat/model":                      # CHAT-MODEL-01: the GM's model (never a door route)
                    code, out = service.chat_model(req)
                elif route == "/api/chat/share":                      # CHAT-FUN-01: a picture or sound from the PC
                    code, out = service.chat_share(req)
                elif route == "/api/notes":                           # VIEW-01: the GM's map notes
                    code, out = service.notes_load(req)
                elif route == "/api/flavor":                          # FLAVOR-01: the table's Flavor
                    code, out = service.flavor_gm(req)
                elif route == "/api/flavor/save":
                    code, out = service.flavor_save(req)
                elif route == "/api/flavor/rule":                     # PLAYER-FLAVOR-01: never a door route
                    code, out = service.flavor_rule(req)
                elif route == "/api/map_paint":                       # MAP-PAINT-01: the GM's paint over a map
                    code, out = service.map_paint_get(req)
                elif route == "/api/map_paint/save":
                    code, out = service.map_paint_save(req)
                elif route == "/api/market":                          # MARKET-01: the GM's market
                    code, out = service.market_gm(req)
                elif route == "/api/characters":                      # RUST-DEPRECATE-01: the Characters roster
                    code, out = service.characters(req)
                elif route == "/api/notes/save":
                    code, out = service.notes_save(req)
                elif route.startswith("/api/atlas/") and route[11:] in Service.ATLAS_ROUTES:   # ATLAS-01
                    code, out = service.atlas(req, route[11:])
                elif route == "/api/spells":                          # REFEREE-01
                    code, out = service.spells_list(req)
                elif route == "/api/spells/clarify":
                    code, out = service.spells_clarify(req)
                elif route == "/api/rules/monitor":                   # RULES-MONITOR-01
                    code, out = service.rules_monitor(req)
                elif route == "/api/terrain-battle/suggest":
                    code, out = service.terrain_suggest(req)
                elif route == "/api/terrain-battle":                  # REGION-01: a standard terrain battle map
                    code, out = service.terrain_battle(req)
                elif route == "/api/site-map":                        # MAPGEN-02: a site drawn as indoor maps
                    code, out = service.site_map(req)
                elif route == "/api/site-map/model":                  # MAPGEN-02: is the local model there?
                    code, out = service.site_model(req)
                elif route == "/api/import-map":                      # VIEW-01: a Universal VTT map
                    code, out = service.import_map(req)
                elif route == "/api/import-map/draft":                # MAP RULE: its wall squares, drafted
                    code, out = service.import_draft(req)
                else:
                    code, out = 404, {"ok": False, "error": "Not found"}
            except __import__("remix_service").Conflict as e:
                code, out = 409, {"ok": False, "error": str(e)}
            except ValueError as e:
                code, out = 400, {"ok": False, "error": str(e)}
            self.send(code, out)

    return Handler


DOOR_ROUTES = {"/api/join", "/api/live/state", "/api/live/act", "/api/live/control", "/api/live/reaction", "/api/live/stealth", "/api/live/initiative", "/api/live/aim", "/api/chat", "/api/roll", "/api/chat/log", "/api/notes",
               "/api/stage", "/api/stage/state", "/api/flavor", "/api/flavor/ask", "/api/market",
               "/api/map_paint"}
STEP_LABELS = {"live_scene": "a scene choice", "live_ruling": "a ruling", "live_control": "who plays a character", "live_reaction": "a Reaction answered",
               "live_stealth": "a Stealth roll", "live_initiative": "an Initiative roll", "live_social": "the Influence switch", "live_srd": "the By the SRD switch",
               "live_fly": "an on-the-fly change",
               "live_reaction_mode": "the Reactions switch", "live_traps": "a trap", "live_mount_mode": "a mount's mode", "live_hazards": "a hazard",
               "live_sight": "who sees whom", "live_light": "the map's light"}
STEP_WORDS = {"attack": "attacks", "move": "moves", "end": "ends the turn"}
REPLAY_WAITS = ("Stale", "Initiative is being rolled", "The creatures are acting")   # a replay's step, a moment early
PANIC_READS = {"/api/live/state", "/api/chat/log", "/api/stage/state", "/api/notes", "/api/flavor", "/api/market", "/api/map_paint"}   # what a stopped table still answers
DOOR_BODY = {"/api/flavor/ask": 1024 * 1024}                       # PLAYER-FLAVOR-01: a look with its paint (two pictures under 400 KB)
# GM 2026-10-25 ("Once they join a game, all the GM options are locked"; 2026-10-28: "Let's leave out the Stand-in key"):
# the players' door serves only these pages (play.html as the players' view); any other page goes to the join page, and
# fight recordings not at all.
def _on_the_timeline(name):
    """GM-UNDO-01: a route that changes the fight: refused while it is being taken back, and a step on its timeline, in the
    order the fight met them: noted as it comes, so the creatures' turns an ended turn lets go come after it, except the GM's
    choices the fight's own thread picks up when it gets there."""
    plain, queued = getattr(Service, name), name in ("live_scene", "live_hazards")

    def run(self, req, *rest):
        if self.rewinding and threading.get_ident() != self.rewind_thread:
            return 409, {"ok": False, "refused": "The GM is taking the fight back; a moment."}
        step = self.new_step(name, req, rest)
        if step and not queued:
            self.timeline.append(step)
        code, out = plain(self, req, *rest)
        if step and code == 200 and out.get("ok"):
            if queued:
                self.timeline.append(step)
        elif step and not queued:
            self.timeline[:] = [e for e in self.timeline if e is not step]
        return code, out
    setattr(Service, name, run)


for _name in ("live_act", "live_scene", "live_ruling", "live_control", "live_reaction", "live_stealth", "live_initiative", "live_social", "live_srd", "live_fly",
              "live_reaction_mode", "live_traps", "live_mount_mode", "live_hazards", "live_sight", "live_light"):
    _on_the_timeline(_name)

PLAYER_PAGES = {"join.html", "play.html", "stage.html", "rules-social.html", "donate.html"}   # GM 2026-10-28: "the client side also needs The Stage"
GM_FOLDERS = ("recordings/",)
# PLAYER-PACKAGE-01 (the GM's Player Client Plan, 2026-10-28: "GM setup, Remix, prep and other GM tools are left out
# entirely"): the door serves a page, script or stylesheet only from the player package's list
CODE_FILES = (".html", ".mjs", ".js", ".css")
_player_files = {}


def player_files(table):
    """PLAYER-PACKAGE-01: the player package's pages, scripts and stylesheets (isles-table/player-client/files.json beside
    the served dist folder, written by build_player_client.py), read again when it changes. Missing or unreadable: an
    empty set, so the door serves no code at all (a broken package shows at once; it never falls back to the GM's files)."""
    path = Path(table).resolve().parent / "player-client" / "files.json"
    try:
        stamp = path.stat().st_mtime_ns
        if _player_files.get(path, (None,))[0] != stamp:
            _player_files[path] = (stamp, {f.lower() for f in json.loads(path.read_text(encoding="utf-8"))["files"]})
        return _player_files[path][1]
    except (OSError, ValueError, KeyError, TypeError):
        print("PLAYER-PACKAGE-01: no player package list at %s; the players' door serves no pages" % path, flush=True)
        return set()


def handed_page(path, query):
    """DM-SWAP-01: where the GM door sends its own pages while another is the GM: the old GM's players' view."""
    rel = path.lstrip("/").lower()
    if rel in ("", "index.html") or rel.endswith(".html") and rel not in ("play.html", "rules-social.html", "donate.html"):
        return "/play.html?view=player&dm=handed"
    if rel == "play.html" and query.get("view") != ["player"]:
        return "/play.html?view=player&dm=handed"
    return None


def door_page(path, query, table=None):
    """Where the players' door sends a visitor: None (serve it), the page to go to, or False (not
    served: a script or stylesheet outside the player package). With `table`, the file the path really opens decides
    (Windows ignores case and trailing dots in names)."""
    rel = path.lstrip("/")
    if table is not None and rel:
        try:
            rel = (Path(table) / rel).resolve().relative_to(Path(table).resolve()).as_posix()
        except (OSError, ValueError):
            return "/join.html"
    rel = rel.lower()
    if rel in ("", "index.html"):
        return "/join.html"
    if rel == "play.html" and query.get("view") != ["player"]:
        return "/play.html?view=player"
    if rel.endswith(".html") and rel not in PLAYER_PAGES or rel.startswith(GM_FOLDERS):
        return "/join.html"
    if table is not None and rel.endswith(CODE_FILES) and rel not in player_files(table):
        return "/join.html" if rel.endswith(".html") else False   # PLAYER-PACKAGE-01
    return None


def make_players_door(service, port, table, hosts=(), sites=()):
    """JOIN-01 (docs/development/JOIN_PROTOCOL.md): the players' door, a second listener beside the GM's. The same pages,
    but it never hands out the GM token (its /api/hello has none) and answers only DOOR_ROUTES, each with a seat ticket
    the GM approved. `hosts`: public names a tunnel gives this door (HTTPS).
    PLAYER-SITE-01: `sites`: the addresses of the hosted player site (https://...); pages from there may call this door
    (CORS). GM 2026-10-28 ("Let's leave out the Stand-in key"): this door is never the GM's console."""
    import table_seats
    from urllib.parse import parse_qs
    Base = make_handler(service, secrets.token_urlsafe(32), port, table, gm_door=False)   # a token no one is ever given
    allowed = {"127.0.0.1:%d" % port: "http://127.0.0.1:%d" % port}
    allowed.update({h: "https://" + h for h in hosts})
    sites = {s.rstrip("/") for s in sites}
    guard = service.door_guard

    class Door(Base):
        timeout = 20                                              # BETA-B: an idle or trickling connection is dropped

        def visitor(self):
            """BETA-B: who is knocking. Behind the Cloudflare Tunnel every request comes from this PC with a public Host;
            only then is Cloudflare's CF-Connecting-IP believed. Kept in memory only (door_guard.py)."""
            ip = self.client_address[0]
            if ip in ("127.0.0.1", "::1") and self.headers.get("Host") in hosts and self.headers.get("CF-Connecting-IP"):
                return self.headers["CF-Connecting-IP"].strip()[:64]
            return ip

        def asker(self):
            """CHEAT-LOG-01: who asked for a GM route: the seat its ticket names, or the door log's anonymous tag."""
            try:
                length = int(self.headers.get("Content-Length", "0"))
                req = json.loads(self.rfile.read(length).decode("utf-8")) if 0 < length <= MAX_BODY else {}
            except ValueError:
                req = {}
            return (service.seats.name_for(req.get("ticket")) if isinstance(req, dict) else None) or guard.tag(self.visitor())

        def limited(self, kind="any"):
            out = guard.check(self.visitor(), kind)
            if out:
                self.send(out[0], {"ok": False, "slow_down": True, "error": out[1]})
            return bool(out)

        def boundary(self):
            h = self.headers.get_all("Host", [])
            if len(h) != 1 or h[0] not in allowed:
                self.send(403, {"ok": False, "error": "Unknown host for the players' door."}); return False
            o = self.headers.get("Origin")
            if o is not None and o != allowed[h[0]] and o not in sites:
                self.send(403, {"ok": False, "error": "Cross-origin requests are refused."}); return False
            return True

        def site(self):
            """PLAYER-SITE-01: the hosted player site this request comes from, or None."""
            o = self.headers.get("Origin")
            return o if o in sites else None

        def end_headers(self):
            if self.site():                                       # PLAYER-SITE-01: the hosted site may read the answer
                self.send_header("Access-Control-Allow-Origin", self.site())
                self.send_header("Vary", "Origin")
            super().end_headers()

        def do_OPTIONS(self):
            """PLAYER-SITE-01: the browser's check before a hosted page posts JSON (a CORS preflight)."""
            if not self.boundary():
                return
            if not self.site() or self.headers.get("Access-Control-Request-Method") not in ("GET", "POST"):
                return self.send(403, {"ok": False, "error": "Cross-origin requests are refused."})
            self.send_response(204)
            self.send_header("Access-Control-Allow-Methods", "GET, POST")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def go(self, where):
            self.send_response(302)
            self.send_header("Location", where)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

        def send(self, code, obj=None, body=None, ctype="application/json; charset=utf-8"):
            if isinstance(obj, dict):
                obj = table_seats.player_words(obj)               # BETA-B: game words for players
            return super().send(code, obj, body, ctype)

        def do_GET(self):
            u = urlparse(self.path)
            if self.limited():
                return
            if u.path == "/api/hello":
                if not self.boundary():
                    return
                return self.send(200, service.door_hello())
            where = door_page(u.path, parse_qs(u.query), table)       # GM 2026-10-25: never the GM pages
            if where is False:                                    # PLAYER-PACKAGE-01: a GM tool's code
                return self.send(404, {"ok": False, "error": "Not part of the player client."}) if self.boundary() else None
            if where:
                return self.go(where) if self.boundary() else None
            return super().do_GET()

        def read_body(self, limit):
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return self.send(400, {"ok": False, "error": "Bad length"})
            if not 0 < length <= limit:                           # refused before anything is read
                return self.send(413 if length > limit else 400, {"ok": False, "error": "Request too large or empty"})
            raw = self.rfile.read(length)
            try:
                req = json.loads(raw.decode("utf-8"))
                assert isinstance(req, dict)
            except (ValueError, AssertionError):
                return self.send(400, {"ok": False, "error": "A JSON object is expected"})
            return raw, req

        def do_POST(self):
            if not self.boundary() or self.limited():
                return
            route = urlparse(self.path).path
            if route not in DOOR_ROUTES:
                service.door_watch.add(self.asker(), "not allowed", route, "A GM route, asked at the players' door.")   # CHEAT-LOG-01
                return self.send(403, {"ok": False, "error": "The players' door does not do that: GM controls are on the GM's PC."})   # /api/dm too: no player asks to be the GM
            got = self.read_body(DOOR_BODY.get(route, MAX_BODY))
            if not got:
                return
            req = got[1]
            asking = route == "/api/join" and req.get("op") == "ask"
            if asking and self.limited("ask"):
                return
            name = req.get("name")[:40] if asking and isinstance(req.get("name"), str) else None
            try:
                code, out = service.door_request(route, req)
                if asking:                                        # BETA-B: the door log
                    guard.note(name or guard.tag(self.visitor()), "knocked" + (", asks to play %s" % req["character"][:40]
                               if isinstance(req.get("character"), str) and req["character"].strip() else ", to watch"))
            except table_seats.WrongInvite as e:
                guard.missed(self.visitor(), "invite code")
                code, out = 400, {"ok": False, "error": str(e)}
            except table_seats.NoSeat:
                code, out = 403, {"ok": False, "no_seat": True, "error": "Your seat is closed (you left, the GM removed it, "
                                  "or Mythastria restarted). Ask to join again on the join page."}
            except table_seats.NoticeNeeded:
                code, out = 403, {"ok": False, "notice": True, "error": "The table's notice has changed: open the join page "
                                  "and accept it again to keep your seat."}
            except __import__("remix_service").Conflict as e:
                code, out = 409, {"ok": False, "error": str(e)}
            except ValueError as e:
                if asking:
                    guard.note(name or guard.tag(self.visitor()), "turned away: %s" % e)
                code, out = 400, {"ok": False, "error": str(e)}
            service.door_watch.note(service.seats.name_for(req.get("ticket")), route, req, code, out)   # CHEAT-LOG-01
            self.send(code, out)

    return Door


class ExclusiveServer(ThreadingHTTPServer):
    """A thread per connection (Chrome keeps spare connections idle; one at a time hung the Stage page), and the port
    is never shared: on Windows SO_REUSEADDR lets a second service bind it while the old one keeps answering (as the
    AI Bridge's ExclusiveServer)."""
    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self):
        import socket
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def serve(port=8772, table=None, service=None, token=None, adventure_packs=None):
    """Bind first (port 0: a free one), then build the handler with the real port for the Host check."""
    token = token or secrets.token_urlsafe(32)
    server = ExclusiveServer(("127.0.0.1", port), BaseHTTPRequestHandler)
    service = service or Service(adventure_packs=adventure_packs)
    if table and getattr(service, "table_dir", None) is None:
        service.table_dir = Path(table)                          # VIEW-01: an imported map's picture goes there
    server.RequestHandlerClass = make_handler(service, token, server.server_address[1], table)
    return server, token


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=8772)
    ap.add_argument("--table", help="the Isles Table dist folder to serve (same origin as the API)")
    ap.add_argument("--adventure-packs", help="external folder containing adventure pack directories (the ones loaded "
                    "when the service last stopped are loaded again)")
    ap.add_argument("--adventure-state", help="the file that remembers the loaded adventures (default sim/adventures/loaded.json; "
                    "a test service gives its own)")
    ap.add_argument("--players-port", type=int, help="JOIN-01: the players' door (127.0.0.1 only; docs/development/JOIN_PROTOCOL.md)")
    ap.add_argument("--players-host", action="append", default=[], help="a public name a tunnel gives the players' door (HTTPS)")
    ap.add_argument("--players-site", action="append", default=[], help="PLAYER-SITE-01: the hosted player site's address "
                    "(https://...); its pages may call the players' door, and the invite link opens it")
    ap.add_argument("--llm-url", default="http://127.0.0.1:1234/v1", help="MAPGEN-02: the local model server that designs "
                    "sites (LM Studio; this PC only)")
    ap.add_argument("--model", default="google/gemma-4-12b-qat", help="MAPGEN-02: the model that designs sites")
    a = ap.parse_args(argv)
    a.adventure_packs = a.adventure_packs or str(Path(__file__).resolve().parents[2] / "adventures")   # ONE-SHOT-01: where a one-shot goes
    service = Service(adventure_packs=a.adventure_packs)
    service.llm_url, service.llm_model = a.llm_url, a.model
    if a.port != 8772:                                           # FLAVOR-01: a test service never writes the GM's Flavor
        service.flavor.path = FLAVOR / ("flavor_test_%d.json" % a.port)
        service.map_paint.path = FLAVOR / ("map_paint_test_%d.json" % a.port)   # MAP-PAINT-01
        service.market.path = MARKET / ("market_test_%d.json" % a.port)   # MARKET-01: nor the GM's market
        service.downtime.path = MARKET / ("downtime_test_%d.json" % a.port)   # GM 2026-10-26: nor the crafting ledger
    try:
        server, _ = serve(a.port, a.table, service=service)
    except OSError:
        print("ANOTHER SIMULATOR SERVICE IS ALREADY RUNNING on 127.0.0.1:%d. Close that window, then start this again." % a.port)
        return 1
    print("Simulator service on http://127.0.0.1:%d (loopback only). Ctrl+C stops it." % a.port, flush=True)
    if a.players_port:                                           # JOIN-01: the players' door
        try:
            door = ExclusiveServer(("127.0.0.1", a.players_port), BaseHTTPRequestHandler)
        except OSError:
            print("Players' door NOT open: port %d is in use." % a.players_port, flush=True)
        else:
            door.RequestHandlerClass = make_players_door(service, door.server_address[1], a.table, a.players_host, a.players_site)
            threading.Thread(target=door.serve_forever, daemon=True).start()
            service.door_link = ("https://%s/" % a.players_host[0]) if a.players_host else "http://127.0.0.1:%d/" % door.server_address[1]
            # PLAYER-SITE-01: players are invited to the hosted site
            service.players_link = a.players_site[0].rstrip("/") + "/join.html" if a.players_site else service.door_link
            print("Players' door on http://127.0.0.1:%d/ (players ask to join; the GM lets them in on Play live, Players...)."
                  % door.server_address[1], flush=True)
    def forget():                                                # JOIN-01 notice: at start, then once a day
        while True:
            try:
                n = service.forget_old()
                if n:
                    print("Deleted %d chat picture or sound file(s) older than %d days." % (n, KEEP_DAYS), flush=True)
            except Exception as e:
                print("Could not delete old chat files or stand-in log lines: %s" % e, flush=True)
            time.sleep(86400)
    threading.Thread(target=forget, daemon=True).start()
    if a.adventure_packs:                                        # ADVENTURE-01: the adventure stays loaded across restarts
        service.adventure_state = Path(a.adventure_state) if a.adventure_state else ADVENTURE_STATE
        done, problems = service.restore_adventures()
        for pack in done:
            print("Adventure loaded again: %s" % pack, flush=True)
        for p in problems:
            print("Adventure not loaded again: %s" % p, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
