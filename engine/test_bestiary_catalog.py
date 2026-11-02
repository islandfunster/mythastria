"""CATALOG-01: the bestiary catalogue's tags, on synthetic stat blocks (no book text in the tests)."""
import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
import bestiary_catalog as bc


def rec(name, **f):
    base = {"type": "Beast", "size": "Medium", "cr": "1/4", "xp": "50", "ac": "12", "hp": "11", "speed": "30 ft.",
            "abilities": {"intelligence": {"score": "3"}, "wisdom": {"score": "12"}}}
    base.update(f)
    return {"name": name, "source": f.pop("_source", "srd"), "fields": base}


def act(*pairs):
    return {"id-%05d" % i: {"name": n, "desc": d} for i, (n, d) in enumerate(pairs, 1)}


class StatLine(unittest.TestCase):
    def test_parsers(self):
        self.assertEqual(bc.speeds("30 ft., fly 60 ft. (hover), swim 40 ft."), {"walk": 30, "fly": 60, "swim": 40, "hover": True})
        self.assertEqual(bc.senses("Darkvision 60 ft.; Blindsight 10 ft.; Passive Perception 9"), {"darkvision": 60, "blindsight": 10})
        self.assertEqual(bc.split_list("Mountain, Planar (Elemental Plane of Air, Plane of Water)"),
                         ["Mountain", "Planar (Elemental Plane of Air, Plane of Water)"])
        self.assertEqual((bc.cr_value("1/8"), bc.cr_value("3"), bc.cr_value("")), (0.125, 3.0, None))

    def test_xp_from_cr_and_habitat_inferred_for_a_swimmer(self):
        c = bc.normalise(rec("Crab-thing", xp="", cr="1/8", speed="30 ft., swim 30 ft."))
        self.assertEqual((c["xp"], c["xp_from_cr"]), (25, True))
        self.assertTrue(c["habitat"][0].startswith("Coastal (inferred"))


class Tags(unittest.TestCase):
    def test_themes_and_roles(self):
        c = bc.classify(bc.normalise(rec("Reef Hunter", speed="10 ft., swim 50 ft.", actions=act(
            ("Bite", "Melee Attack Roll: +4, reach 5 ft. Hit: 6 Piercing damage, and the target has the Grappled condition."),
            ("Ink", "Each creature must make a Dexterity saving throw or have the Blinded condition.")))))
        self.assertIn("aquatic", c["themes"]); self.assertIn("grappler", c["themes"])
        self.assertIn("controller", c["roles"]); self.assertIn("skirmisher", c["roles"])

    def test_pack_tactics_is_not_leadership(self):
        c = bc.classify(bc.normalise(rec("Pack Biter", traits=act(("Pack Tactics", "Advantage on an attack roll against "
            "a creature if at least one of its allies is within 5 feet of the creature.")),
            actions=act(("Bite", "Melee Attack Roll: +4, reach 5 ft.")))))
        self.assertNotIn("leader", c["roles"]); self.assertIn("pack", c["themes"])
        self.assertEqual(c["roles"], ["melee"])

    def test_tone(self):
        g = bc.classify(bc.normalise(rec("Grave Eater", type="Undead", actions=act(("Bite", "It devours flesh.")))))
        self.assertEqual(g["tone"], "dark"); self.assertIn('"flesh"', g["tone_reasons"])
        k = bc.classify(bc.normalise(rec("Sea Turtle")))
        self.assertEqual(k["tone"], "family")
        o = bc.classify(bc.normalise(rec("Grave Eater", type="Undead")), {"Grave Eater": "family"})
        self.assertEqual((o["tone"], o["tone_reasons"]), ("family", ["GM override"]))

    def test_behaviour_quadrants(self):
        q = lambda i, w: bc.behaviour({"int": i, "wis": w})
        self.assertEqual([q(1, 3), q(3, 12), q(10, 8), q(14, 11)], ["relentless", "instinct-wary", "clever-rash", "tactician"])

    def test_levels_for_four_characters(self):
        armor = bc.normalise(rec("Guardian", cr="1", xp="200", type="Construct"))
        self.assertEqual(bc.levels(armor), {"alone_moderate_from": 1, "four_moderate_from": 3})
        big = bc.normalise(rec("Big", cr="8", xp="3900"))   # fits a level-6 party, CR 8 > 6
        self.assertIn("CR above party level", bc.levels(big)["note"])


class Query(unittest.TestCase):
    def test_srd_only_and_filters(self):
        # SRD-ONLY-MONSTERS (GM, 2026-10-14): a paid bestiary record left in an older catalogue file is never offered
        cat = [bc.classify(bc.normalise(r)) for r in (rec("Wolfish"), dict(rec("Mmonly"), source="mm"),
                                                       rec("Ghostly", type="Undead"))]
        rows = bc.query(cat, tone_max="family")
        self.assertEqual([(c["name"], c["source"]) for c in rows], [("Wolfish", "srd")])
        self.assertNotIn("Mmonly", bc.page(cat))

    def test_the_tool_never_reads_the_monster_manual(self):
        src = Path(bc.__file__).read_text(encoding="utf-8")
        self.assertNotIn("wotc50", src.lower()); self.assertNotIn("rules_cache", src)


if __name__ == "__main__":
    unittest.main()
