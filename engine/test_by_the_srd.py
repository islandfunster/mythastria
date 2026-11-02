"""BY-THE-SRD-01 (GM 2026-11-02): the GM's switch between this table's rulings and the SRD as written, in real fights.
  py -3 -m unittest test_by_the_srd
"""
import copy, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "sim"), str(ROOT / "tools"), str(ROOT / "mythastria_core")]
import character_build as cb
import market
import sim_service
import stealth
import test_rulings_ask_gm as base
import test_gm_undo as undo


def d20(n):
    return lambda a, b: n if b == 20 else b


class Hide(base.Fight):
    scenario = "test/live_spells.json"

    def hide(self, roll, srd):
        self.f.by_srd = srd
        self.f.sim.rng.randint = d20(roll)
        st = stealth.of(self.f)
        st.declare(self.me)
        return st

    def invisible(self):
        return self.f.sim.gm_rules.has(self.me, "Invisible")

    def lines(self):
        return "\n".join(e["text"] for e in self.f.snapshot(0)["log"])

    def test_off_the_gm_still_rolls_perception(self):
        st = self.hide(19, False)
        self.assertIn(self.me, st.sneaks)
        self.assertFalse(self.invisible())

    def test_on_a_dc_15_check_hides_with_no_perception_roll(self):
        st = self.hide(13, True)                                  # 13 + 2 Dexterity = 15, the DC itself
        self.assertEqual(st.sneaks, {})
        self.assertTrue(self.invisible())
        self.assertEqual(self.f.sim.gm_rules.cond[self.me]["Invisible"].get("total"), 15)
        self.assertIn("vs DC 15 -> hidden", self.lines())

    def test_on_a_low_roll_stays_seen(self):
        st = self.hide(12, True)
        self.assertEqual(st.sneaks, {})
        self.assertFalse(self.invisible())
        self.assertFalse(st.last["hidden"])
        self.assertIn("vs DC 15 -> not hidden", self.lines())


class Guardians(base.Fight):
    scenario = "test/live_spells.json"
    build = dict(copy.deepcopy(base.HERO), spirit_guardians=True)   # as a built Cleric: the engine casts it

    def kind(self, srd, alignment):
        self.f.by_srd = srd
        c = self.f.sim.by_id(self.me)
        c["alignment"] = alignment
        return self.f.sim.party.guardian_kind(c)

    def test_off_it_is_radiant_for_anyone(self):
        self.assertEqual(self.kind(False, "Lawful Evil"), "radiant")

    def test_on_evil_is_necrotic(self):
        self.assertEqual(self.kind(True, "Chaotic Evil"), "necrotic")

    def test_on_good_neutral_and_unset_are_radiant(self):
        for a in ("Lawful Good", "Neutral", "", None):
            self.assertEqual(self.kind(True, a), "radiant", a)

    def test_the_ask_the_gm_row_goes_when_the_sheet_decides(self):
        self.assertIn("Spirit Guardians", self.asks())
        self.f.set_by_srd(True)
        self.assertNotIn("Spirit Guardians", self.asks())


class Switch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = sim_service.Service()
        self.s.market = market.Market(Path(self.tmp.name) / "market.json")
        self.assertEqual(self.s.live_new(dict(undo.FIGHT))[0], 200)

    def tearDown(self):
        self.s.live.quit()
        self.s.live.thread.join(30)
        self.tmp.cleanup()

    def test_it_starts_off(self):
        self.assertFalse(self.s.live.snapshot(1 << 30)["by_srd"])

    def test_it_lasts_into_the_next_fight(self):
        self.s.live_srd({"on": True})
        self.assertTrue(self.s.live.snapshot(1 << 30)["by_srd"])
        self.s.live_new(dict(undo.FIGHT))
        self.assertTrue(self.s.live.by_srd)

    def test_undo_takes_a_flip_back(self):
        self.s.live_srd({"on": True})
        self.assertEqual(self.s.timeline[-1]["label"], "the By the SRD switch")
        code, out = self.s.live_undo({})
        self.assertEqual(code, 200, out)
        self.assertFalse(self.s.by_srd)
        self.assertFalse(self.s.live.by_srd)

    def test_a_replay_keeps_a_flip(self):
        self.s.live_srd({"on": True})
        f = self.s.live
        self.s.live_act(dict(op="dodge", actor=f.waiting, revision=f.revision, fight_id=f.fight_id))
        self.assertEqual(self.s.live_undo({})[0], 200)
        self.assertTrue(self.s.live.by_srd)

    def test_it_is_on_or_off_only(self):
        with self.assertRaises(ValueError):
            self.s.live_srd({"on": 1})

    def test_it_is_the_gms_alone(self):
        self.assertNotIn("/api/live/srd", sim_service.DOOR_ROUTES)


class Sheets(unittest.TestCase):
    def test_a_sheet_carries_its_alignment_into_a_fight(self):
        sheet = dict(undo.sheet("Lyra", "Cleric", []), alignment="Neutral Evil")
        m = cb.member(copy.deepcopy(sheet))
        self.assertEqual(m.get("build", m)["alignment"], "Neutral Evil")

    def test_the_builder_keeps_the_choice(self):
        self.assertEqual(cb.build({"alignment": "Chaotic Evil"})["sheet"]["alignment"], "Chaotic Evil")

    def test_a_sheet_without_one_is_not_evil(self):
        m = cb.member(undo.sheet("Lyra", "Cleric", []))
        self.assertEqual(m.get("build", m)["alignment"], "")


class Hints(base.Fight):
    scenario = "test/live_spells.json"
    build = dict(copy.deepcopy(base.HERO), sneak="3d6")

    def test_no_sneak_attack_hint_on_a_cantrip(self):
        import live_hints
        with mock.patch("party.sneak_attack_ok", lambda *a: True):   # everything else about Sneak Attack is met
            facts = live_hints.attack_facts(self.f, self.offers())
        self.assertFalse(any(row.get("sneak") for row in facts.get("ranged", {}).values()))

    def test_a_ranged_weapon_still_gets_it(self):
        import live_hints
        self.f.sim.by_id(self.me)["ranged"] = {"name": "Longbow", "atk": 5, "dmg": "1d8+2", "dmgtype": "piercing", "reach": 150, "crit": 20}
        with mock.patch("party.sneak_attack_ok", lambda *a: True):
            offers = dict(self.offers(), attacks=[{"key": "ranged", "targets": self.offers()["attacks"][1]["targets"]}])
            facts = live_hints.attack_facts(self.f, offers)
        self.assertTrue(any(row.get("sneak") for row in facts["ranged"].values()))


if __name__ == "__main__":
    unittest.main()
