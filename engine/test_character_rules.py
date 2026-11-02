"""CHARACTERS-01: sim/character_rules.py, the SRD 5.2.1 character rules of the simulator service.
  py -m unittest test_character_rules
"""
import sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "sim")); sys.path.insert(0, str(ROOT / "tools"))
import character_rules as cr


class Data(unittest.TestCase):
    def test_the_srd_data(self):
        r = cr.rules()
        self.assertEqual(r["version"], "SRD 5.2.1")
        self.assertEqual(len(r["classes"]), 12)
        self.assertEqual(len(r["spells"]), 339)
        self.assertEqual(r["classes"]["Wizard"]["subclass"]["name"], "Evoker")
        self.assertIn([5, "Extra Attack"], r["classes"]["Fighter"]["features"])
        self.assertEqual(r["classes"]["Fighter"]["asi"], [4, 6, 8, 12, 14, 16])
        self.assertEqual(r["multiclass_slots"][4], [4, 3, 2])           # caster level 5
        self.assertEqual(r["classes"]["Warlock"]["resources"]["pact_level"][8], 5)


class Flags(unittest.TestCase):
    def test_srd_sheet_has_no_flags(self):
        sheet = {"species": "Wood Elf", "background": "Criminal", "ruleset": "SRD 5.2.1",
                 "classes": [{"name": "Rogue", "level": 3, "subclass": "Thief"}], "feats": ["Alert"],
                 "spells": [{"name": "Hunter’s Mark"}, "Fire Bolt"], "features": ["Sneak Attack (2d6)", "Cunning Action",
                                                                            "Fey Ancestry", "Second-Story Work"]}
        self.assertEqual(cr.flags(sheet), [])

    def test_homebrew_is_flagged_never_refused(self):
        out = cr.check({"ruleset": "D&D 5e (2014)", "species": "Half-Elf", "background": "Folk Hero",
                        "classes": [{"name": "Fighter", "subclass": "Battle Master"}, {"name": "Artificer"}],
                        "feats": ["Sharpshooter", "Magic Initiate (Wizard)"], "spells": ["Toll the Dead", "Shield"],
                        "features": ["Superiority Dice", "Hit Points"]})
        self.assertTrue(out["ok"])
        got = {(f["kind"], f["name"]) for f in out["flags"]}
        self.assertEqual(got, {("rules", "D&D 5e (2014)"), ("species", "Half-Elf"), ("background", "Folk Hero"),
                               ("subclass", "Battle Master"), ("class", "Artificer"), ("feat", "Sharpshooter"),
                               ("spell", "Toll the Dead"), ("feature", "Superiority Dice")})
        self.assertTrue(all("GM rules it" in f["note"] for f in out["flags"]))

    def test_species_forms(self):
        for s in ("Elf", "High Elf", "Elf (Drow)", "Gold Dragonborn", "Goliath (Stone)", "Infernal Tiefling", "Rock Gnome", "Drow"):
            self.assertTrue(cr.species_is_srd(s), s)
        for s in ("Half-Elf", "Hill Dwarf", "Lightfoot Halfling", "Tabaxi"):
            self.assertFalse(cr.species_is_srd(s), s)


class Service(unittest.TestCase):
    def test_the_check_op_needs_no_roster(self):
        import sim_service
        code, out = sim_service.Service().characters({"op": "character_check", "character": {"species": "Tabaxi"}})
        self.assertEqual(code, 200)
        self.assertEqual(out["flags"][0]["kind"], "species")


class AlertInPlay(unittest.TestCase):
    """Found by the 2026-11-02 play-test: a played fight rolled Dexterity alone, leaving out Alert's proficiency bonus."""

    def test_a_built_sheet_brings_its_initiative_to_the_fight(self):
        import character_build as cb, scenes
        sheet = {"name": "A", "classes": [{"name": "Rogue", "level": 3}], "abilities": {"str": 8, "dex": 16, "con": 14, "int": 10, "wis": 12, "cha": 10},
                 "combat": {"hp_max": 20, "ac": 14, "speed": 30, "attack_bonus": 5, "damage_count": 1, "damage_die": 6, "damage_bonus": 3, "reach": 5},
                 "derived": {"initiative": 5, "attacks": []}, "equipment": ["Dagger"], "spells": [], "features": []}
        m = cb.member(sheet)
        self.assertEqual(scenes.init_bonus(m.get("build", m))[0], 5)


if __name__ == "__main__":
    unittest.main()
