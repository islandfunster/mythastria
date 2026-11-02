"""The AI assistant review of the v0.7.62 snapshot (reviews/review_v0.7.62_ai_assistant.md): mixed alternatives revived a conditional
branch whose condition had failed. Alternatives A -> B (only if A hit) -> C, or A -> B -> D: after A misses and B is
made, only D may follow, never C. multi_left now checks conditional steps against the attacks' results and targets."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "mythastria_core"))
import unittest
import test_support  # noqa: F401  (paths)
import ai_turn, statblock_ai

A, B, C, D = "Claw", "Bite", "Tail", "Horn"
DUR, ELA = "combattracker.list.id-00001", "combattracker.list.id-00002"


def plan():
    step = lambda name, if_hit=False: {"attacks": [name], "only_if_previous_hit_same_target": if_hit}
    v = statblock_ai.validate({"patterns": [{"steps": [step(A), step(B, True), step(C)]},
                                            {"steps": [step(A), step(B), step(D)]}]}, [A, B, C, D])
    return statblock_ai.to_slots(v)


class MixedAlternatives(unittest.TestCase):
    def left(self, done, hits, targets, last_hit):
        return ai_turn.multi_names_left(ai_turn.multi_left(plan(), done, hits, targets), last_hit)

    def test_failed_condition_is_not_revived(self):
        self.assertEqual(self.left([A], [False], [DUR], False), {B, D})              # A missed: the plain branch only
        self.assertEqual(self.left([A, B], [False, True], [DUR, DUR], True), {D})     # never C
        self.assertEqual(self.left([A, B], [False, False], [DUR, DUR], False), {D})

    def test_kept_condition_allows_both_branches(self):
        self.assertEqual(self.left([A, B], [True, True], [DUR, DUR], True), {C, D})
        # the beak-like step went at another target: the conditional branch is gone
        self.assertEqual(self.left([A, B], [True, True], [DUR, ELA], True), {D})

    def test_without_results_conditional_branches_are_not_assumed(self):
        self.assertEqual(self.left([A, B], [], [], True), {D})

    def test_without_both_targets_same_target_is_not_assumed(self):
        # The AI assistant review of v0.7.64 (reviews/review_v0.7.64_ai_assistant.md): hits [True, True] with no target history kept
        # the conditional branch open; the bridge passes [] when the history does not line up
        self.assertEqual(self.left([A, B], [True, True], [], True), {D})
        self.assertEqual(self.left([A, B], [True, True], ["", DUR], True), {D})
        self.assertEqual(self.left([A, B], [True, True], [DUR], True), {D})
        self.assertEqual(self.left([A, B], [True, True], [DUR, DUR], True), {C, D})


if __name__ == "__main__":
    unittest.main()
