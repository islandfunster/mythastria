"""THREAT-02 step 2 (GM 2026-10-21: "Next: THREAT-02 step 2, creatures' saving-throw actions and Recharge breath
weapons."): the library reads SRD 5.2.1 actions that work by saving throw (areas from the creature, damage, half on a
success, conditions with how long they last, Recharge and X/Day), and an attack's save rider; the simulator, as GM,
plays them (sim/gm_rules.py). What it cannot play stays "GM rules this" text."""
import json, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "sim"), str(ROOT / "mythastria_core")]
import srd_library as sl

_LIB = None


def lib():
    global _LIB
    if _LIB is None:
        _LIB = json.loads(sl.LIBRARY.read_text(encoding="utf-8"))["creatures"]
    return _LIB


def action(creature, prefix):
    return next(a for a in lib()[creature]["actions"] if a["name"].startswith(prefix))


class Parse(unittest.TestCase):
    def test_a_cone_breath_with_recharge(self):
        s = action("Young Red Dragon", "Fire Breath")["save"]
        self.assertEqual((s["save"], s["dc"], s["area"], s["dmg"], s["type"], s["half"], s["recharge"]),
                         ("dex", 17, {"shape": "cone", "size": 30}, "16d6", "fire", True, 5))

    def test_a_line_a_sphere_at_a_point_and_an_emanation(self):
        self.assertEqual(action("Adult Black Dragon", "Acid Breath")["save"]["area"], {"shape": "line", "length": 60, "width": 5})
        ape = action("Giant Ape", "Boulder Toss")["save"]
        self.assertEqual((ape["area"], ape["dmg"], ape["half"], ape["recharge"]),
                         ({"shape": "sphere", "radius": 5, "range": 90}, "7d6", True, 6))
        self.assertEqual(ape["conditions"], [{"name": "Prone", "max_size": "large"}])
        burst = action("Planetar", "Holy Burst")["save"]
        self.assertEqual(burst["area"], {"shape": "sphere", "radius": 20, "range": 120, "enemies": True})
        cloud = action("Dretch", "Fetid Cloud")["save"]
        self.assertEqual((cloud["area"], cloud["uses"]), ({"shape": "emanation", "size": 10}, 1))
        self.assertEqual(cloud["conditions"], [{"name": "Poisoned", "until": {"who": "target", "when": "end"}}])
        self.assertIn("GM rules this", action("Dretch", "Fetid Cloud")["gm"])            # "While Poisoned, ..."

    def test_one_creature_and_how_long_a_condition_lasts(self):
        roar = action("Lion", "Roar")["save"]
        self.assertEqual((roar["area"], roar["conditions"]), ({"shape": "one", "range": 15},
                         [{"name": "Frightened", "until": {"who": "self", "when": "start"}}]))
        glare = action("Mummy", "Dreadful Glare")["save"]
        self.assertEqual(glare["conditions"], [{"name": "Frightened", "until": {"who": "self", "when": "end"}}])
        self.assertTrue(glare["area"]["sees"])
        web = action("Giant Spider", "Web")["save"]
        self.assertEqual(web["conditions"], [{"name": "Restrained", "object": {"ac": 10, "hp": 5}}])

    def test_an_attack_s_save_rider(self):
        claw = action("Ghoul", "Claw")
        self.assertEqual((claw["atk"], claw["dmg"]), (4, "1d4+2"))
        self.assertEqual(claw["save"], {"save": "con", "dc": 10, "rider": True, "not": ["Undead", "elf"],
                                        "conditions": [{"name": "Paralyzed", "until": {"who": "target", "when": "end"}}]})

    def test_what_cannot_be_played_stays_text(self):
        glaive = action("Bearded Devil", "Infernal Glaive")                   # an infernal wound: no engine block
        self.assertNotIn("save", glaive)
        self.assertIn("infernal wound", glaive["gm"])
        storm = action("Storm Giant", "Lightning Storm")                       # a Cylinder from a far point
        self.assertNotIn("save", storm)
        self.assertEqual(storm["gm"], "GM rules this")

    def test_save_actions_are_counted_as_played(self):
        red = lib()["Young Red Dragon"]
        self.assertIn("Fire Breath (Recharge 5-6)", red["played"])
        self.assertIn("Web (Recharge 5-6)", lib()["Giant Spider"]["played"])
        played = sum(1 for c in lib().values() for a in c["actions"] if "save" in a and not a["save"].get("rider"))
        self.assertGreaterEqual(played, 90)                                       # 91 of 135 on 2026-10-21


class InMultiattack(unittest.TestCase):
    """2026-10-22 smoke run: the Mummy, Mummy Lord, Chain Devil, Sphinx of Valor and the brass and silver dragons used
    a save action named in their Multiattack in place of the whole turn and never attacked."""
    def kind(self, creature, prefix):
        import gm_rules
        block = lib()[creature]
        sim = type("S", (), {"by_id": lambda self, i: block})()
        rules = gm_rules.GmRules.__new__(gm_rules.GmRules)
        rules.sim = sim
        return rules.in_multiattack("x", action(creature, prefix))

    def test_how_the_multiattack_names_it(self):
        self.assertEqual(self.kind("Mummy", "Dreadful Glare"), "with")              # "... and uses Dreadful Glare"
        self.assertEqual(self.kind("Chain Devil", "Conjure Infernal Chain"), "with")
        self.assertEqual(self.kind("Sphinx of Valor", "Third Roar"), "with")         # "... and uses Roar"
        self.assertEqual(self.kind("Adult Brass Dragon", "Sleep Breath"), "replace")
        self.assertEqual(self.kind("Guardian Naga", "Poisonous Spittle"), "replace")
        self.assertIsNone(self.kind("Planetar", "Holy Burst"))                     # "... or uses Holy Burst twice"
        self.assertIsNone(self.kind("Young Red Dragon", "Fire Breath"))             # its own action


class Plays(unittest.TestCase):
    def fight(self, creature, level, rounds=3, seeds=(1, 2, 3, 4, 5), arena="open", count=1, until=None, only=None):
        import copy, creature_threat as ct, encounter_tuner as tuner, run_sim
        block = copy.deepcopy(ct.library()[creature])
        if only:                                       # the chooser takes the stronger attack: test the one with the rider
            block["actions"] = [a for a in block["actions"] if a["name"] in only]
        texts = []
        for seed in seeds:
            sc = ct.arena_scenario(arena, block, count)
            for c in sc["combatants"]:
                if c.get("side") == "foe":
                    c["init"] = 30
            sc = tuner.with_party(sc, ct.PARTY, level)
            sim = run_sim.Sim(sc, "scripted", True, seed, True, True)
            try:
                sim.run(rounds, 20)
            finally:
                sim.close()
            self.assertEqual((sim.stalls, sim.problems), (0, []), creature)
            texts.append("\n".join(t for _, t in sim.lines))
            if until and until in texts[-1]:
                break
        return texts

    def test_a_young_dragon_breathes_fire(self):
        text = self.fight("Young Red Dragon", 8, seeds=(1,))[0]
        self.assertIn("Young Red Dragon 1 uses Fire Breath (Recharge 5-6)", text)
        self.assertIn("Dexterity save", text)

    def test_a_ghoul_s_claw_paralyses_and_the_paralysis_ends(self):
        texts = self.fight("Ghoul", 1, rounds=4, count=2, until="has the Paralyzed condition", only=("Claw",),
                           seeds=range(1, 16))                    # DC 10 against Con +4: most saves succeed
        self.assertTrue(any("Constitution save against Claw" in t for t in texts))
        text = next((t for t in texts if "has the Paralyzed condition" in t), "")
        self.assertIn("has the Paralyzed condition", text)
        self.assertIn("is no longer Paralyzed", text)

    def test_a_mummy_glares_and_still_attacks(self):
        text = self.fight("Mummy", 3, rounds=3, seeds=(1, 2, 3), until="Mummy 1 attacks")[-1]
        self.assertIn("Mummy 1's Dreadful Glare is part of its Multiattack: its attacks follow", text)
        self.assertIn("Mummy 1 attacks", text)

    def test_a_giant_spider_webs_a_character_who_breaks_free(self):
        texts = self.fight("Giant Spider", 2, rounds=4, until="strikes the web")
        text = next((t for t in texts if "has the Restrained condition" in t), "")
        self.assertIn("Giant Spider 1 uses Web (Recharge 5-6)", text)
        self.assertIn("strikes the web", text)


if __name__ == "__main__":
    unittest.main()
