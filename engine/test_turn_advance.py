"""GM 2026-10-27 (the threat batch hung): a queued end of turn ends only the turn it was queued for (sim/fight_state.py
_advance_from). A dying character's turn the simulator as GM took was also ended at once by the run loop; the queued end
then skipped the next creature, whose turn the engine waited for forever."""
import json, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "sim"), str(ROOT / "tools"), str(ROOT / "mythastria_core")]


class QueuedEndOfTurn(unittest.TestCase):
    def setUp(self):
        import run_sim
        sc = json.loads((ROOT / "sim" / "scenarios" / "test" / "walls_route.json").read_text(encoding="utf-8"))
        self.sim = run_sim.Sim(sc, "scripted", True, 1, True, True)
        self.s = self.sim.S
        self.s.startCombat()
        self.sim.settle()

    def tearDown(self):
        self.sim.close()

    def test_a_stale_queued_end_does_not_skip_the_next_turn(self):
        s = self.s
        first = s.turnSerial
        stale = s._advance_from(first)        # queued for this turn (the simulator as GM took it)
        s.nextActor()                         # ... but the turn was ended at once another way
        nxt, active = s.turnSerial, s.active()[0]
        self.assertEqual(nxt, first + 1)
        stale()                               # the queued end fires later: nothing happens
        self.assertEqual((s.turnSerial, s.active()[0]), (nxt, active))

    def test_a_queued_end_still_ends_its_own_turn(self):
        s = self.s
        first = s.turnSerial
        s._advance_from(first)()
        self.assertEqual(s.turnSerial, first + 1)


if __name__ == "__main__":
    unittest.main()
