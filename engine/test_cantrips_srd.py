"""NOTES 7.8 and GM 2026-11-02 ("Let's allow spells like sorcerous burst follow SRD"): every attack on the sheet has a card, and a
cantrip cast from a card does what the SRD says, in real fights.
  py -3 -m unittest test_cantrips_srd
"""
import copy, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "sim"), str(ROOT / "tools"), str(ROOT / "mythastria_core")]
import character_build as cb
import character_rules as cr
import sim_service
import test_rulings_ask_gm as base


def spell(name, die, kind, reach=120, **more):
    return dict({"name": name, "atk": 7, "dmg": "1d%d" % die, "dmgtype": kind, "reach": reach, "cantrip": True, "crit": 20}, **more)


def hero(ranged, **more):
    return dict(copy.deepcopy(base.HERO), ranged=ranged, spell_mod=4, spell_dc=15, **more)


class Card(base.Fight):
    scenario = "test/live_spells.json"

    def card(self, key="ranged"):
        return next(a for a in self.offers()["attacks"] if a["key"] == key)

    def cast(self, key="ranged", high=True, **more):
        row = self.card(key)
        if high:                                                  # a hit, not a Critical Hit: 19 on the d20, the top of every die
            self.f.sim.rng.randint = lambda a, b: 19 if b == 20 else b
        return self.act(op="attack", weapon=key, target=row["targets"][0], **more)

    def lines(self):
        return "\n".join(e["text"] for e in self.f.snapshot(0)["log"])


class Burst(Card):
    build = hero(dict(base.BURST))

    def test_an_eight_rolls_more_up_to_the_modifier(self):
        out = self.cast(dmgtype="fire")
        self.assertTrue(out["ok"], out)
        self.assertIn("Sorcerous Burst: an 8 on the d8, 4 more d8 (8, 8, 8, 8) = 32 Fire (at most 4 in a cast)", self.lines())

    def test_no_eight_rolls_nothing_more(self):
        self.f.sim.rng.randint = lambda a, b: 19 if b == 20 else 3
        out = self.act(op="attack", weapon="ranged", target=self.card()["targets"][0])
        self.assertTrue(out["ok"], out)
        self.assertNotIn("more d8", self.lines())

    def test_a_chain_stops_when_a_die_is_no_eight(self):
        rolls = iter([19, 8, 5])
        self.f.sim.rng.randint = lambda a, b: next(rolls, 1)
        self.act(op="attack", weapon="ranged", target=self.card()["targets"][0])
        self.assertIn("1 more d8 (5) = 5", self.lines())

    def test_the_damage_lands(self):
        target = self.card()["targets"][0]
        rolls = iter([19, 8, 1])                                  # a hit, an 8, then a 1: 9 damage to a 10 HP Goblin Warrior
        self.f.sim.rng.randint = lambda a, b: next(rolls, 1)
        self.act(op="attack", weapon="ranged", target=target)
        self.assertEqual(next(c for c in self.f.snapshot(999999)["state"]["combatants"] if c["id"] == target)["hp"], 1)


class Riders(Card):
    build = hero(spell("Ray of Frost", 8, "cold", 60))

    def test_ray_of_frost_slows(self):
        self.assertTrue(self.cast()["ok"])
        self.assertIn("Ray of Frost: Speed -10 ft", self.lines())


class Grasp(Card):
    build = hero(spell("Shocking Grasp", 8, "lightning", 120))

    def test_no_opportunity_attacks(self):
        self.assertTrue(self.cast()["ok"])
        self.assertIn("can't make Opportunity Attacks", self.lines())


class Wisp(Card):
    build = hero(spell("Starry Wisp", 8, "radiant", 60))

    def test_outlined(self):
        self.assertTrue(self.cast()["ok"])
        self.assertIn("Starry Wisp: no benefit from Invisible", self.lines())


class Touch(Card):
    build = hero(spell("Chill Touch", 4, "necrotic", 120))    # a small die: the Goblin Warrior lives to feel it

    def test_the_gm_rules_the_healing(self):
        self.assertTrue(self.cast()["ok"])
        self.assertIn("can't regain Hit Points", self.lines())


class MagicAction(Card):
    build = hero(spell("Fire Bolt", 10, "fire"), attacks=2)

    def test_extra_attack_gives_no_second_cast(self):
        target = self.card()["targets"][0]
        self.assertTrue(self.cast()["ok"])
        self.assertFalse(self.card()["targets"])
        out = self.act(op="attack", weapon="ranged", target=target)
        self.assertFalse(out["ok"])

    def test_it_is_said_as_a_cast(self):
        self.cast()
        self.assertIn("casts Fire Bolt (Magic action)", self.lines())
        self.assertNotIn("takes the Attack action", self.lines())

    def test_no_weapon_attack_after_it(self):
        self.cast()
        self.assertTrue(any("went on Fire Bolt" in why for why in self.card("weapon")["refused"].values()))


class Beams(Card):
    build = hero(spell("Eldritch Blast", 10, "force"), beams=2)

    def test_each_beam_is_a_roll_at_any_target(self):
        self.assertTrue(self.cast()["ok"])
        self.assertIn("2 beams", self.lines())
        self.assertTrue(self.cast()["ok"])
        self.assertFalse(self.card()["targets"])


class Sneak(Card):
    build = hero(spell("Fire Bolt", 10, "fire"), sneak="3d6")

    def test_no_sneak_attack_on_a_cantrip(self):
        self.cast()
        self.assertNotIn("Sneak Attack", self.lines())


class Weapons(Card):
    build = hero(dict(base.BURST), attacks=2, weapon={"name": "Longbow", "atk": 5, "dmg": "1d8+2", "dmgtype": "piercing", "reach": 150, "crit": 20})

    def test_a_weapon_is_still_the_attack_action(self):
        self.assertTrue(self.cast("weapon")["ok"])
        self.assertIn("takes the Attack action (2 attacks)", self.lines())
        self.assertTrue(self.cast("weapon")["ok"])


class MoreCards(Card):
    build = hero(dict(base.BURST), more1=spell("Fire Bolt", 10, "fire"), more2=spell("Ray of Frost", 8, "cold", 60),
                 spell_list=[{"name": "Fire Bolt", "level": 0}, {"name": "Ray of Frost", "level": 0}])

    def test_every_attack_has_a_card(self):
        self.assertEqual({a["name"] for a in self.offers()["attacks"]}, {"Dagger", "Sorcerous Burst", "Fire Bolt", "Ray of Frost"})

    def test_none_falls_to_ask_the_gm(self):
        self.assertFalse({"Fire Bolt", "Ray of Frost"} & set(self.asks()))

    def test_a_card_past_the_second_plays(self):
        self.assertTrue(self.cast("more2")["ok"])
        self.assertIn("Ray of Frost: Speed -10 ft", self.lines())


class Computer(Card):
    build = hero(dict(base.BURST), weapon=spell("Fire Bolt", 10, "fire"), more1=spell("Ray of Frost", 8, "cold", 60),
                 more2={"name": "Dagger", "atk": 5, "dmg": "1d4+2", "dmgtype": "piercing", "reach": 120, "crit": 20})

    def setUp(self):
        super().setUp()
        self.c, self.p = self.f.sim.by_id(self.me), self.f.sim.party
        self.c["live"] = False
        self.foe = self.card("weapon")["targets"][0]

    def seen(self, *kinds):
        self.p.known.update({(self.p.kind(self.foe), k): "immune" for k in kinds})

    def pick(self, weapon, sneak=False):
        return self.p.unwasted_attack(self.me, self.foe, self.c, weapon, sneak)

    def test_it_keeps_its_choice_when_that_harms(self):
        self.assertIs(self.pick(self.c["weapon"]), self.c["weapon"])

    def test_a_wasted_spell_gives_way_to_another_spell(self):
        self.seen("fire")
        self.assertEqual(self.pick(self.c["weapon"])["name"], "Sorcerous Burst")

    def test_burst_takes_a_type_that_harms(self):
        self.seen("fire", "acid")
        got = self.pick(self.c["weapon"])
        self.assertEqual((got["name"], got["dmgtype"]), ("Sorcerous Burst", "cold"))

    def test_a_spell_is_never_swapped_for_a_weapon(self):
        self.seen("fire", *self.c["ranged"]["dmg_choices"])
        self.assertEqual(self.pick(self.c["weapon"])["name"], "Fire Bolt")

    def test_a_played_character_is_left_to_its_player(self):
        self.c["live"] = True
        self.seen("fire")
        self.assertIs(self.pick(self.c["weapon"]), self.c["weapon"])

    def test_the_swap_is_what_lands(self):
        self.seen("fire", "acid")
        self.f.sim.rng.randint = lambda a, b: 19 if b == 20 else 3
        self.p.attack(self.me, self.foe, self.c["weapon"], spell=True)
        self.assertIn("won't harm", self.lines())
        self.assertIn("Sorcerous Burst", self.lines())


class Build(unittest.TestCase):
    SHEET = {"name": "Vex", "classes": [{"name": "Sorcerer", "level": 5}], "species": "Human",
             "abilities": {"str": 8, "dex": 14, "con": 14, "int": 10, "wis": 10, "cha": 18},
             "combat": {"hp_max": 32, "ac": 13, "speed": 30, "attack_bonus": 7, "damage_count": 1, "damage_die": 8, "damage_bonus": 0, "reach": 60},
             "equipment": ["Dagger"], "spells": ["Fire Bolt", "Ray of Frost", "Sorcerous Burst", "Shocking Grasp"], "features": []}

    def built(self):
        m = cb.member(copy.deepcopy(self.SHEET))
        return m.get("build", m) if isinstance(m, dict) else m

    def test_the_sheets_attacks_all_get_a_slot(self):
        b = self.built()
        names = {(b.get(k) or {}).get("name") for k in cr.WEAPON_KEYS}
        self.assertLessEqual({"Dagger", "Fire Bolt", "Ray of Frost", "Sorcerous Burst", "Shocking Grasp"}, names)

    def test_a_long_list_keeps_every_attack(self):
        sheet = dict(self.SHEET, spells=self.SHEET["spells"] + ["Starry Wisp", "Poison Spray", "Chill Touch", "Produce Flame", "Eldritch Blast"])
        m = cb.member(sheet)
        b = m.get("build", m)
        self.assertEqual(len({(b.get(k) or {}).get("name") for k in cr.WEAPON_KEYS} - {None}), 10)

    def test_names_outside_the_pdf_are_gone(self):
        self.assertFalse({"Thorn Whip", "Toll the Dead", "Word of Radiance", "Mind Sliver"} & set(cb.DAMAGE_CANTRIPS))

    def test_no_attack_is_left_for_the_gm(self):
        self.assertFalse([g for g in self.built().get("gm", []) if "(spell)" in g and "Burst" in g])

    def test_the_service_takes_each_slot(self):
        self.assertLessEqual(set(cr.WEAPON_KEYS), sim_service.LIVE_WEAPONS)
        self.assertEqual(sim_service.MORE_ATTACKS, cr.MORE_ATTACKS)


if __name__ == "__main__":
    unittest.main()
