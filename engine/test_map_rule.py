"""The GM's map rule (2026-10-20): walls are at least one 5-ft square, with no floor on a map's edge. Every map with wall
squares passes it. Only rules test maps keep plain line walls.
  py -3 -m unittest test_map_rule
"""
import json, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "sim"), str(ROOT / "mythastria_core")]
import site_maps

MAPS = ROOT / "sim" / "scenarios"


def maps():
    for f in sorted(MAPS.rglob("*.json")):
        sc = json.loads(f.read_text(encoding="utf-8"))
        if "combatants" in sc:
            yield f.relative_to(MAPS).as_posix(), sc


class Rule(unittest.TestCase):
    def test_walls_are_whole_squares(self):
        for name, sc in maps():
            if sc.get("wall_cells"):
                with self.subTest(name):
                    self.assertEqual(site_maps.check_map(dict(sc, doorways=sc.get("doorways", []))), [])


if __name__ == "__main__":
    unittest.main()
