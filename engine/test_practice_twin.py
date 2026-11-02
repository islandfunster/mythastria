"""v0.7.89 PRACTICE-TWIN-01: save the current fight, continue it in the simulator. Synthetic fixtures only (SRD 5.2.1
numbers: Kobold Warrior Dagger +4, 1d4+2; original names and an original map)."""
import json, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "mythastria_core"))
sys.path.insert(0, str(ROOT / "sim"))
import fight_snapshot   # noqa: E402

MAP = "image.id-00001.image@PRACTICE_TEST"
SIG = "parseNPCPower(nodePower,false)"
PC, K1, K2 = "combattracker.list.id-00001", "combattracker.list.id-00002", "combattracker.list.id-00003"


def actor(path, name, side, hp, wounds, x, y, init, pc=False, active=False, effects=()):
    return {"path": path, "name": name, "active": "1" if active else "0", "friend_foe": side, "initiative": str(init),
            "hp_total": str(hp), "wounds": str(wounds), "temporary_hp": "0",
            "actor_link": {"class": "charsheet" if pc else "npc", "recordname": "charsheet.id-00009" if pc else ""},
            "effects": [{"label": e, "active": "1"} for e in effects],
            "raw_fields": {"pos.map": MAP, "pos.x": str(x), "pos.y": str(y), "ac": "14" if not pc else "16",
                           "speed": "30 ft." if not pc else "30", "reach": "5", "space": "5", "init": "2",
                           "senses": "Darkvision 60 ft." if not pc else ""}}


def record(ct, idx, name, values, branch="actions"):
    node = "%s.%s.id-%05d" % (ct, branch, idx)
    return node, {"ctpath": ct, "node_path": node, "power_name": name, "description": "",
                  "attempts": {SIG: {"ok": "1", "fields": [{"key": k, "value": v} for k, v in values.items()]}}}


DAGGER = {"return1.1.type": "attack", "return1.1.atktype": "melee", "return1.1.modifier": "4", "return1.1.rangedist": "5",
          "return1.2.type": "damage", "return1.2.clauses.1.dice.1": "d4", "return1.2.clauses.1.modifier": "2",
          "return1.2.clauses.1.dmgtype": "piercing",
          "return1.3.type": "attack", "return1.3.atktype": "ranged", "return1.3.modifier": "4",
          "return1.4.type": "damage", "return1.4.clauses.1.dice.1": "d4", "return1.4.clauses.1.modifier": "2"}
FIRE_BOLT = {"return1.1.type": "attack", "return1.1.atktype": "ranged", "return1.1.modifier": "5",
             "return1.2.type": "damage", "return1.2.clauses.1.dice.1": "d10", "return1.2.clauses.1.modifier": "0"}


def walls():
    """An original 10 x 8 square map exported centre-up (the Kobold Pantry's frame): one wall from x=200..200, y=0..400
    in the token frame, i.e. square column 4 from row 0 to 8, and one closed door."""
    return {"map": "Practice Test Map", "fg_map": MAP, "transform": "center_up", "image_size": [500.0, 400.0],
            "gridsize": [50.0, 50.0], "open_doors": [], "confirmed": "2026-10-13 12:00",
            "occluders": [{"id": "0", "points": [[-50.0, 200.0], [-50.0, -200.0]], "door": False, "closed": False},
                          {"id": "1", "points": [[100.0, 0.0], [150.0, 0.0]], "door": True, "closed": False}],
            "lighting": {"ambient": "dark", "lights": [{"pos": [175.0, 25.0], "bright_ft": 20, "dim_ft": 40}]}}


def bridge_state(wounds=3, pc_effects=(), spell=False, moved=0):
    """What the bridge holds mid-fight: round 2, Kobold Warrior A active, the PC hurt."""
    combatants = {PC: actor(PC, "Test Hero", "friend", 20, wounds, 325, 125, 15, pc=True, effects=pc_effects),
                  K1: actor(K1, "Kobold Warrior A", "foe", 7, 2, 375, 125, 9, active=True),
                  K2: actor(K2, "Kobold Warrior B", "foe", 7, 0, 425, 175, 9)}
    recs = dict([record(K1, 1, "Dagger", DAGGER), record(K2, 1, "Dagger", DAGGER),
                 record(K1, 2, "Pack Tactics", {}, "traits")])
    if spell:
        recs.update([record(K1, 1, "Fire Bolt", FIRE_BOLT, "spells")])
    combat = {"round": 2, "space": {"map": MAP, "mapname": "Practice Test Map", "grid": 50.0, "grid_h": 50.0,
                                    "units": 5.0, "diag": "1", "moved": moved},
              "multi_done": (K1, [], []), "bonus_used": None, "slot_used": None}
    sheets = {"charsheet.id-00009": {"core": {"name": "Test Hero", "strmod": "3", "dexmod": "1", "profbonus": "2"},
                                     "weapons": {"w": {"name": "Mace", "carried": "2", "type": "0", "prof": "1",
                                                       "properties": "",
                                                       "fields": {"damagelist.id-1.dice": {"value": "d6"},
                                                                  "damagelist.id-1.stat": {"value": "base"},
                                                                  "damagelist.id-1.bonus": {"value": "0"}}}}},
              "charsheet.id-00077": {"core": {"name": "Not in this fight"}}}
    return fight_snapshot.take(combat, combatants, recs, sheets, {K1, "combattracker.list.id-00099"}, 14, walls(),
                               "0.7.89")


class Snapshot(unittest.TestCase):
    def test_round_trip_keeps_the_fight(self):
        snap = bridge_state()
        with tempfile.TemporaryDirectory() as d:
            path = fight_snapshot.save(snap, d)
            self.assertTrue(path.name.startswith("Practice_Test_Map_"))
            again = fight_snapshot.load(path)
        self.assertEqual(again, json.loads(json.dumps(snap)))
        self.assertEqual((again["round"], again["active"], again["policy"]), (2, K1, "local_only"))
        self.assertEqual(again["combatants"][PC]["wounds"], "3")
        self.assertEqual(again["awareness"], {"aware": [K1], "perception_dc": 14})   # only creatures in this fight
        self.assertEqual(list(again["sheets"]), ["charsheet.id-00009"])            # only linked PCs
        self.assertEqual(again["walls"]["fg_map"], MAP)
        self.assertIn("Nothing in this file is sent back", again["note"])

    def test_not_a_snapshot_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.json"; p.write_text('{"name": "a scenario"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                fight_snapshot.load(p)

    def test_summary_names_turn_and_walls(self):
        text = "\n".join(fight_snapshot.summary(bridge_state()))
        self.assertIn("Round 2, Kobold Warrior A's turn; 3 combatants.", text)
        self.assertIn("Test Hero: 17/20 HP", text)
        self.assertIn("Map Practice Test Map: confirmed walls (2)", text)


class Scenario(unittest.TestCase):
    def test_positions_walls_and_resume_point(self):
        import practice
        sc = practice.to_scenario(bridge_state())
        k = {c["name"]: c for c in sc["combatants"]}
        self.assertEqual((k["Kobold Warrior A"]["x"], k["Kobold Warrior A"]["y"]), (7.5, 2.5))
        self.assertEqual(k["Test Hero"]["wounds"], 3)
        self.assertEqual(k["Kobold Warrior A"]["actions"][0]["dmg"], "1d4+2")
        self.assertEqual(sc["resume"], {"active": "id-00002", "round": 2, "skip_current": False})
        # centre-up export frame -> FG's top-left token frame -> squares
        self.assertEqual(sc["walls"][0]["points"], [[4.0, 0.0], [4.0, 8.0]])
        self.assertEqual(sc["lighting"]["lights"][0]["x"], 8.5)
        self.assertEqual((sc["aware"], sc["perception_dc"]), (["id-00002"], 14))
        text = "\n".join(practice.not_simulated_lines(sc))
        self.assertIn("Pack Tactics not applied", text)
        self.assertIn("only its first attack form (melee)", text)
        self.assertIn("death saving throws are not simulated", text)

    def test_spells_and_effects_are_listed_as_stops(self):
        import practice
        sc = practice.to_scenario(bridge_state(pc_effects=("Blessed",), spell=True))
        text = "\n".join(practice.not_simulated_lines(sc))
        self.assertIn("STOPS the run at Kobold Warrior A's turn: spell Fire Bolt (spells are not simulated yet)", text)
        self.assertIn("STOPS the run when a creature hostile to Test Hero takes its turn: effect Blessed", text)

    def test_turn_under_way_starts_with_the_next_combatant(self):
        import practice
        sc = practice.to_scenario(bridge_state(moved=10))
        self.assertTrue(sc["resume"]["skip_current"])

    def test_missing_faction_or_grid_refuses(self):
        import practice
        snap = bridge_state(); snap["combatants"][K2]["friend_foe"] = ""
        with self.assertRaisesRegex(ValueError, "no faction"):
            practice.to_scenario(snap)
        snap = bridge_state(); snap["space"] = {}; snap["walls"] = None
        with self.assertRaisesRegex(ValueError, "grid size is unknown"):
            practice.to_scenario(snap)

    def test_pc_weapon_from_the_synced_sheet(self):
        import practice
        sc = practice.to_scenario(bridge_state(), pcs="attack")
        hero = next(c for c in sc["combatants"] if c["pc"])
        self.assertEqual(hero["weapon"], {"name": "Mace", "atk": 5, "reach": 5, "dmg": "1d6+3"})


class PracticeRun(unittest.TestCase):
    def run_snapshot(self, snap, rounds=1, pcs="pass"):
        import argparse, run_sim
        with tempfile.TemporaryDirectory() as d:
            path = fight_snapshot.save(snap, d)
            a = argparse.Namespace(from_snapshot=str(path), pcs=pcs, rounds=rounds, seed=3, instant=False, quiet=True,
                                   local_model=False, model=None, stall=200)
            sim = run_sim.practice_run(a, out_dir=d)
            report = Path(sim.report_path).read_text(encoding="utf-8")
        return sim, report

    def test_continues_from_the_saved_turn_and_reports(self):
        sim, report = self.run_snapshot(bridge_state())
        self.assertEqual((sim.stalls, sim.problems), (0, []))
        turns = [t for k, t in sim.lines if k == "turn" and t.endswith("'s turn")]
        self.assertEqual(turns[0], "Kobold Warrior A's turn")            # the saved turn, not round 1's first
        self.assertIn("--- round 2 ---", [t for _, t in sim.lines])
        self.assertIn("nothing was written back to Fantasy Grounds", report)
        self.assertIn("Kobold Warrior B steps to square (7.5, 3.5)", report)
        self.assertIn("### Round 3", report)
        self.assertNotIn("Round 4", report)
        self.assertEqual(turns[-1], "Kobold Warrior A's turn")           # --rounds 1: one full rotation, back to it
        self.assertEqual(report.count("**Kobold Warrior A's turn**"), 1)
        self.assertIn("Continued from round 2, Kobold Warrior A's turn", report)
        self.assertIn("| Test Hero |", report)
        self.assertIn("## Not simulated (listed before the run)", report)
        self.assertIn("attacks Test Hero", report)                         # the roll is in the report
        self.assertIsNone(sim.stopped)

    def test_unsupported_spell_stops_safely(self):
        sim, report = self.run_snapshot(bridge_state(spell=True))
        self.assertIn("spell Fire Bolt", sim.stopped)
        self.assertFalse(any(k == "dice" for k, _ in sim.lines))           # nothing was guessed
        self.assertIn("**Stopped: not simulated.**", report)

    def test_effect_on_a_target_stops_when_a_foe_acts(self):
        sim, _ = self.run_snapshot(bridge_state(pc_effects=("Blessed",)))
        self.assertIn("effect Blessed", sim.stopped)

    def test_pc_at_zero_stops(self):
        sim, report = self.run_snapshot(bridge_state(wounds=20))
        self.assertIn("death saving throws are not simulated", sim.stopped)


if __name__ == "__main__":
    unittest.main()
