"""v0.8.4 (the AI assistant review of v0.8.3, R083-01..05): one geometry and cost contract for movers larger than one square.
A creature of s squares fills the s x s block centred on its token (whatever the token's grid phase); positions are
pixels on a 50 px grid, 5 ft squares. A Large token aligned to the grid sits on a grid intersection."""
import sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "mythastria_core"))
import ai_turn as A  # noqa: E402

G = 50
c = lambda x, y: (x * G + 25, y * G + 25)                 # centre of square (x, y)
# two rooms two squares high (rows 0-1) joined by a one-square corridor (row 0, squares x 3..5)
ROOMS = [((0, 0), (450, 0)), ((0, 100), (150, 100)), ((300, 100), (450, 100)), ((150, 50), (300, 50)),
         ((150, 50), (150, 100)), ((300, 50), (300, 100)), ((0, 0), (0, 100)), ((450, 0), (450, 100))]
FAR = [((0, -100), (500, -100))]


class LargeFootprint(unittest.TestCase):
    """R083-01: a Large mover never ends overlapping another creature."""
    def test_the_planner_stops_a_large_mover_short_of_the_target(self):
        # Large on a grid corner (squares 0-1 x 0-1), Medium target in square (4, 0): it ends filling squares 2-3
        m = A.plan_walled_move((50, 50), c(4, 0), [], G, 5, 1, 30, 5, 1, FAR, mover_size=2)
        self.assertEqual((m["x"], m["y"], m["feet"]), (150, 50, 10))

    def test_a_large_token_off_the_grid_phase_never_overlaps(self):
        # on a square centre a Large token's space is half a square off; it may not end over the target to reach it
        m = A.plan_walled_move(c(0, 0), c(4, 0), [], G, 5, 1, 30, 5, 1, FAR, mover_size=2)
        if m:
            self.assertGreaterEqual(abs(m["x"] - c(4, 0)[0]), 75)

    def test_may_end_counts_both_spaces(self):
        self.assertFalse(A._may_end(c(3, 0), [(*c(4, 0), 1, A.PASS_FREE)], G, 2, []))
        self.assertTrue(A._may_end(c(2, 0), [(*c(4, 0), 1, A.PASS_FREE)], G, 2, []))

    def test_two_large_creatures(self):
        self.assertFalse(A._may_end((150, 50), [(225, 50, 2, A.PASS_BLOCK)], G, 2, []))
        self.assertTrue(A._may_end((100, 50), [(200, 50, 2, A.PASS_BLOCK)], G, 2, []))


class SqueezeAndDifficult(unittest.TestCase):
    """R083-02: a squeezed step through a creature's space costs both extras, as FG's npcMove counts them."""
    def test_costs_stack(self):
        occ = [(*c(4, 0), 1, A.PASS_DIFFICULT)]
        m = A.plan_walled_move((50, 50), c(8, 1), occ, G, 5, 1, 60, 5, 1, ROOMS, mover_size=2)
        self.assertIsNotNone(m)
        self.assertEqual((m["x"], m["y"]), (350, 50))
        self.assertEqual(m["squeeze"], 4)
        self.assertEqual(sum(m["extra"]), 6)                           # 4 squeezed + 2 through the creature
        self.assertEqual(m["feet"], 60)
        self.assertEqual(A.route_cost(m["path"], G, 5, 1, sum(m["extra"])), 60)
        self.assertIsNone(A.plan_walled_move((50, 50), c(8, 1), occ, G, 5, 1, 55, 5, 1, ROOMS, mover_size=2))


class CentredFit(unittest.TestCase):
    """R083-03: the wall test checks the space centred on the token, not a block shifted next to it."""
    def test_a_wall_through_the_space(self):
        self.assertFalse(A._room_for((50, 50), 2, G, [((75, -100), (75, 200))]))
        self.assertTrue(A._room_for((50, 50), 2, G, [((100, -100), (100, 200))]))    # a wall on its edge
        self.assertFalse(A._room_for((50, 50), 2, G, [((50, 60), (50, 200))]))       # an interior wall stub

    def test_the_planner_never_ends_a_large_mover_across_a_wall(self):
        wall = [((175, -100), (175, 50))]   # cuts x=175 from the top to the middle row
        m = A.plan_walled_move((50, 50), (400, 50), [], G, 5, 1, 30, 5, 1, wall + FAR, mover_size=2)
        if m:
            self.assertTrue(A._room_for((m["x"], m["y"]), 2, G, wall))


class BlindsightRange(unittest.TestCase):
    """R083-04: without lighting data Blindsight still has a range."""
    def cs(self, x, bs=5):
        return {"r": {"raw_fields": {"pos.x": "25", "pos.y": "25", "senses": "Blindsight %d ft." % bs}},
                "v": {"raw_fields": {"pos.x": str(x), "pos.y": "25"}, "effects": [{"label": "Invisible", "active": "1"}]}}

    def test_out_of_range(self):
        self.assertFalse(A.oa_sees({"grid": G, "units": 5}, self.cs(175), "r", "v"))

    def test_in_range(self):
        self.assertTrue(A.oa_sees({"grid": G, "units": 5}, self.cs(75, 10), "r", "v"))   # adjacent, 10 ft


class BlindsightFromTheEdge(unittest.TestCase):
    """v0.8.4 (GM 2026-10-15): Blindsight range counts from the edge of the creature's space, like every grid range:
    5 ft Blindsight perceives a creature in any square next to it."""
    def test_five_feet_reaches_an_adjacent_creature(self):
        cs = BlindsightRange.cs(None, 75)
        self.assertTrue(A.oa_sees({"grid": G, "units": 5}, cs, "r", "v"))
        self.assertTrue(A.oa_sees({"grid": G, "units": 5}, BlindsightRange.cs(None, 75, 5), "r", "v"))
        self.assertFalse(A.oa_sees({"grid": G, "units": 5}, BlindsightRange.cs(None, 125, 5), "r", "v"))

    def test_on_a_lit_map(self):
        import lighting
        dark = {"ambient": "dark", "lights": []}
        see = lambda tx, rng, vside=G: lighting.can_see((25, 25), (tx, 25), dark, [], 0, G, rng, viewer_side=vside, grid=G)
        self.assertTrue(see(75, 50))                     # adjacent, 5 ft
        self.assertFalse(see(125, 50))                   # one square between: 10 ft
        self.assertTrue(see(125, 100))
        self.assertTrue(lighting.can_see((50, 50), (125, 25), dark, [], 0, G, 50, viewer_side=2 * G, grid=G))  # next to a Large viewer


class SqueezedStep(unittest.TestCase):
    """v0.8.4: a squeezed Large creature's token centre may pass over the wall beside a gap while the corner of its space
    goes through the gap; the simulator's wall audit uses the planner's own step test."""
    def test_corner_through_a_gap(self):
        wall = [((0, 75), (110, 75))]                       # a wall with a gap from x 110 on
        self.assertTrue(A.step_passes((100, 50), (100, 100), 2, G, wall))
        self.assertFalse(A.step_passes((100, 50), (100, 100), 1, G, wall))         # a Medium token centre crosses it

    def test_a_squeezed_position_has_room_in_a_corner(self):
        wall = [((0, 50), (100, 50))]                      # a wall ending at a Large token's centre
        self.assertFalse(A._space_clear((100, 50), 2, G, wall))
        self.assertTrue(A.has_room((100, 50), 2, G, wall))                    # its right half is clear: squeezing
        cut = [((75, -50), (75, 150)), ((125, -50), (125, 150))]   # through the middle of both columns of squares
        self.assertFalse(A.has_room((100, 50), 2, G, cut))                    # no corner square of it is whole
        self.assertFalse(A.has_room((100, 50), 1, G, wall))

    def test_a_solid_wall(self):
        self.assertFalse(A.step_passes((100, 50), (100, 100), 2, G, [((0, 75), (300, 75))]))


class DiagonalParity(unittest.TestCase):
    """R083-05: the 5/10 diagonal rule continues across the moves of one turn."""
    def test_route_cost_after_one_diagonal(self):
        path = [(25, 25), (75, 75)]
        self.assertEqual(A.route_cost(path, G, 5, "1.5"), 5)
        self.assertEqual(A.route_cost(path, G, 5, "1.5", diag_before=1), 10)

    def test_planner_after_one_diagonal(self):
        m = A.plan_walled_move(c(0, 0), c(3, 3), [], G, 5, "1.5", 10, 5, 1, FAR, approach=True, diag_before=1)
        self.assertEqual(m["feet"], 10)
        self.assertEqual(A.route_cost(m["path"], G, 5, "1.5", sum(m["extra"]), diag_before=1), m["feet"])


if __name__ == "__main__":
    unittest.main()
