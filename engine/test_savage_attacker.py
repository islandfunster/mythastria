"""2024 feat semantics on synthetic engine fixtures; no campaign or service access.
FG-EXIT-01 step 4: on sim/fight_state.py, which replaced the stand-in FG these ran on (they had stopped running there:
the stand-in's table was renamed SIM, the fixture still set S)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "sim"))
import fight_state  # noqa: E402

SRC, TGT = "id-00001", "id-00002"


class SavageDiceTests(unittest.TestCase):
    def engine(self, rolls):
        self.rolls = iter(rolls)
        self.draws, self.lines = [], []

        def rand(sides):
            value = next(self.rolls)
            self.assertTrue(1 <= value <= sides)
            self.draws.append(value)
            return value
        fs = fight_state.FightState(grid=32, units=5, diag=1, instant=True, rand=rand,
                                    say=lambda k, t: self.lines.append((k, t)), later=lambda fn: fn())
        fs.addCombatant({"id": SRC, "name": "Feat bearer", "hp": 100, "ac": 10, "init": 10, "x": 0, "y": 0,
                         "savage_attacker": True})
        fs.addCombatant({"id": TGT, "name": "Target", "hp": 200, "ac": 10, "init": 9, "x": 1, "y": 0})
        fs.startCombat()
        return fs

    def attack(self, fs):
        fs.actionRoll(SRC, TGT, [{"sType": "attack", "nMod": 0}])

    def damage(self, fs, weapon):
        fs.actionRoll(SRC, TGT, [{"sType": "damage", "clauses": [{"dice": ["d6", "d6"], "modifier": 4, "sim_weapon": weapon}]}])

    def wounds(self, fs):
        return fs.getValue(TGT, "wounds", 0)

    def test_higher_whole_pool_modifier_once_and_second_hit_ordinary(self):
        fs = self.engine([15, 1, 2, 5, 6, 15, 2, 2])
        self.attack(fs); self.damage(fs, True)
        self.assertEqual(self.wounds(fs), 15)  # max(3,11)+4
        self.attack(fs); self.damage(fs, True)
        self.assertEqual(self.wounds(fs), 23)  # second hit 4+4, no second feat use
        self.assertEqual(len(fs.savageRecords), 1)
        self.assertEqual(len(self.draws), 8)

    def test_cannot_choose_individual_dice_from_both_rolls(self):
        fs = self.engine([15, 6, 1, 1, 6])
        self.attack(fs); self.damage(fs, True)
        self.assertEqual(self.wounds(fs), 11)  # one pool of 7, not two selected sixes

    def test_no_feat_means_no_additional_rolls(self):
        fs = self.engine([15, 1, 2])
        fs.setValue(SRC, "sim_savage_attacker", 0)
        self.attack(fs); self.damage(fs, True)
        self.assertEqual(self.wounds(fs), 7)
        self.assertEqual(len(fs.savageRecords), 0)
        self.assertEqual(len(self.draws), 3)

    def test_miss_does_not_consume_feat_and_nonweapon_damage_is_excluded(self):
        fs = self.engine([1, 15, 2, 3, 15, 1, 1, 6, 6])
        self.attack(fs)
        self.assertEqual(len(fs.savageRecords), 0)
        self.attack(fs); self.damage(fs, False)
        self.assertEqual(len(fs.savageRecords), 0)
        self.assertEqual(self.wounds(fs), 9)
        self.attack(fs); self.damage(fs, True)
        self.assertEqual(self.wounds(fs), 25)
        self.assertEqual(len(fs.savageRecords), 1)

    def test_critical_weapon_dice_in_both_pools_and_modifier_once(self):
        fs = self.engine([20, 1, 1, 1, 1, 6, 6, 6, 6])
        self.attack(fs); self.damage(fs, True)
        self.assertEqual(self.wounds(fs), 28)  # max(4d6=4,4d6=24)+4
        record = fs.savageRecords[0]
        self.assertEqual((record["first"], record["second"], record["chosen"]), (4, 24, 24))

    def test_first_pool_can_win_and_extra_damage_is_not_rerolled(self):
        fs = self.engine([15, 6, 6, 2, 1, 1])
        self.attack(fs)
        fs.actionRoll(SRC, TGT, [{"sType": "damage", "clauses": [
            {"dice": ["d6", "d6"], "modifier": 4, "sim_weapon": True},
            {"dice": ["d8"], "modifier": 0, "sim_weapon": False}]}])
        self.assertEqual(self.wounds(fs), 18)  # max(12,2)+4+2 rider
        self.assertEqual(len(self.draws), 6)

    def test_resets_on_each_combatant_turn_including_an_off_turn_attack(self):
        fs = self.engine([15, 1, 1, 2, 2, 15, 1, 1, 3, 3, 15, 2, 2])
        self.attack(fs); self.damage(fs, True)
        fs.nextActor()
        self.attack(fs); self.damage(fs, True)
        self.attack(fs); self.damage(fs, True)
        records = fs.savageRecords
        self.assertEqual(len(records), 2)
        self.assertEqual((records[0]["turn"], records[1]["turn"]), (1, 2))
        self.assertEqual(self.wounds(fs), 26)  # 8,10,8; same bearer can use again on target's turn


if __name__ == "__main__":
    unittest.main()
