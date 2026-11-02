"""THREAT-02 step 1 (GM 2026-10-20: how long to make all the SRD creatures' stat blocks): every SRD 5.2.1 creature has a
basic simulator block in sim/creatures/srd_library.json (tools/srd_library.py), so the region map's battle popup, Remix
and Play live can use any of them. Hand-made blocks (the scenarios') win; what the engine cannot play stays as text
labelled "GM rules this", never dropped."""
import json, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "sim"), str(ROOT / "mythastria_core")]
import bestiary_catalog
import srd_library as sl

GM = "GM rules this"


def srd_names():
    return {r["name"] for r in bestiary_catalog.load_srd()} - sl.NOT_IN_SRD     # FG's module goes beyond the official PDF


class TheFile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(sl.LIBRARY.read_text(encoding="utf-8"))
        cls.lib = cls.data["creatures"]

    def test_every_srd_creature_and_nothing_else(self):
        self.assertEqual(set(self.lib), srd_names())
        self.assertEqual(len(self.lib), 336)
        self.assertIn("System Reference Document 5.2.1", self.data["source"])

    def test_the_file_is_what_the_converter_makes_now(self):
        built = sl.build()                                       # the adventures' maps have left the engine, so hand-made blocks stay as saved
        self.assertEqual({k: v for k, v in built.items() if k != "creatures"}, {k: v for k, v in self.data.items() if k != "creatures"})
        self.assertEqual({n: c for n, c in built["creatures"].items() if self.lib[n].get("made") != "hand"},
                         {n: c for n, c in self.lib.items() if c.get("made") != "hand"})

    def test_each_block_fights_with_hit_points_ac_and_its_actions_recorded(self):
        for name, c in self.lib.items():
            self.assertGreater(c["hp"], 0, name)
            self.assertGreater(c["ac"], 0, name)
            self.assertGreater(c["xp"], -1, name)
            names = [a["name"] for a in c["actions"]]
            self.assertEqual(sorted(c["played"] + c["text"]), sorted(names), name)
            for a in c["actions"]:
                self.assertEqual(a["name"] in c["played"], "gm" not in a or a["gm"].startswith(GM + ": the rest"), (name, a))
                if a["name"] in c["text"]:
                    self.assertEqual(a["gm"], GM, (name, a["name"]))

    def test_no_srd_action_is_dropped(self):
        recs = {r["name"]: r["fields"] for r in bestiary_catalog.load_srd()}
        for name, c in self.lib.items():
            if c.get("made") == "hand":
                continue
            want = [e["name"] for e in (recs[name].get("actions") or {}).values() if isinstance(e, dict)]
            self.assertEqual([a["name"] for a in c["actions"]], want, name)
            for part in ("bonusactions", "reactions", "legendaryactions"):
                for e in (recs[name].get(part) or {}).values() if isinstance(recs[name].get(part), dict) else ():
                    self.assertTrue(any(g["name"] == e["name"] and g["gm"] == GM for g in c["gm_text"]), (name, part, e["name"]))

    def test_hand_made_blocks_are_kept_as_they_are(self):
        g = self.lib["Gargoyle"]
        self.assertEqual(g["made"], "hand")
        self.assertTrue(g["source"].startswith("sim/scenarios/"))
        self.assertEqual(g["played"], ["Multiattack", "Claw"])
        self.assertEqual(self.lib["Wolf"]["made"], "srd")

    def test_multiattack_is_played_when_the_parser_understands_it(self):
        bear = self.lib["Brown Bear"]
        self.assertEqual(bear["played"], ["Multiattack", "Bite", "Claw"])
        claw = next(a for a in bear["actions"] if a["name"] == "Claw")
        self.assertEqual((claw["atk"], claw["dmg"], claw["dmgtype"]), (5, "1d4+3", "slashing"))
        self.assertIn("Prone", claw["gm"])                                   # the rider stays with the GM
        dragon = self.lib["Adult Red Dragon"]
        self.assertIn("Multiattack", dragon["played"])
        self.assertIn("Rend", dragon["played"])
        self.assertIn("Fire Breath (Recharge 5-6)", dragon["played"])               # THREAT-02 step 2: a save action
        self.assertEqual(dragon["text"], ["Spellcasting"])
        self.assertTrue(any(g["part"] == "Legendary Action" for g in dragon["gm_text"]))


class Official(unittest.TestCase):
    """GM 2026-11-01: the official PDF over the first versions' relics (tools/srd_library.py official())."""
    def setUp(self):
        self.lib = sl.load()

    def test_the_numbers(self):
        self.assertEqual((self.lib["Earth Elemental"]["hp"], self.lib["Animated Flying Sword"]["hp"]), (147, 14))
        flame = next(a for a in self.lib["Priest"]["actions"] if a["name"] == "Radiant Flame")
        self.assertEqual(flame["atk"], 5)
        self.assertIn("+5,", flame["desc"])

    def test_the_initiative_scores_are_the_pdfs(self):
        want = {"Aboleth": 17, "Ape": 12, "Goblin Warrior": 12, "Air Elemental": 15, "Gray Ooze": 13, "Invisible Stalker": 22}
        self.assertEqual({n: self.lib[n]["init"] for n in want}, want)

    def test_the_library_wins_over_a_maps_own_numbers(self):
        import creature_threat
        self.assertEqual(creature_threat.library()["Earth Elemental"]["hp"], 147)             # a map keeps 84 for its encounter

    def test_the_green_hags_coven_spells_are_its_trait(self):
        hag = self.lib["Green Hag"]
        self.assertNotIn("1/Day", next(a for a in hag["actions"] if a["name"] == "Spellcasting")["desc"])
        self.assertIn("Coven Magic", [g["name"] for g in hag["gm_text"]])

    def test_no_relic_is_left_in_the_words(self):
        text = json.dumps(self.lib, ensure_ascii=False)
        self.assertNotRegex(text, r"\bDM\b|whilst|DNDSRD521BESTIARY")
        self.assertNotIn("\\\\n", text)


class Parsing(unittest.TestCase):
    def test_flat_damage_feet_and_negative_modifiers(self):
        self.assertEqual(sl.parse_attack("Melee Attack Roll: +4, reach 5 ft. Hit: 1 Slashing damage.")["dmg"], "0d1+1")
        self.assertEqual(sl.parse_attack("Melee Attack Roll: +1, reach 5 ft. Hit: 1 (1d4 - 1) Piercing damage.")["dmg"], "1d4-1")
        a = sl.parse_attack("Melee Attack Roll: +5, reach 5 feet. Hit: 5 (1d4 + 3) Piercing damage.")
        self.assertEqual((a["atk"], a["reach"], a["dmg"]), (5, 5, "1d4+3"))
        self.assertEqual(sl.parse_attack("Melee Attack Roll: +6, reach 10 ft. Hit: 14 (3d6 +4) Bludgeoning damage.")["dmg"], "3d6+4")
        r = sl.parse_attack("Ranged Attack Roll: +9, range 120 feet. Hit: 13 (3d8) Thunder damage. If the target is "
                            "a Large or smaller creature, it has the Prone condition.")
        self.assertEqual((r["atktype"], r["reach"], r["dmg"], r["dmgtype"]), ("ranged", 120, "3d8", "thunder"))
        self.assertTrue(r["rest"].startswith("If the target"))

    def test_second_damage_and_summon_placeholders(self):
        a = sl.parse_attack("Melee Attack Roll: +4, reach 5 ft. Hit: 1 Piercing damage plus 5 (2d4) Poison damage.")
        self.assertEqual((a["dmg"], a["dmg2"], a["dmgtype2"]), ("0d1+1", "2d4", "poison"))
        self.assertIsNone(sl.parse_attack("Melee Attack Roll: +[SUMMONATK], reach 5 ft. Hit: 1d8 + [SUMMONLVL] Radiant damage."))


class Pickers(unittest.TestCase):
    def test_creature_threat_and_the_service_offer_all_336(self):
        import creature_threat, sim_service
        lib = creature_threat.library()
        self.assertEqual(set(lib), srd_names())
        self.assertEqual(lib["Gargoyle"]["source"], sl_block("Gargoyle")["source"])     # hand-made from the scenario
        self.assertIn("Wolf", sim_service.creature_names())
        self.assertGreater(lib["Wolf"]["xp"], 0)

    def test_the_forest_battle_now_suggests_wolves(self):
        import creature_threat, terrain_battle
        self.assertEqual(terrain_battle.suggested("forest", creature_threat.library())[0], "Wolf")


def sl_block(name):
    return json.loads(sl.LIBRARY.read_text(encoding="utf-8"))["creatures"][name]


if __name__ == "__main__":
    unittest.main()
