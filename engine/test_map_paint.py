"""MAP-PAINT-01 (GM 2026-10-27, Flavor: the GM paints on the map and erases it; the GM reveals it on/off; kept per map):
tools/map_paint.py keeps each map's picture and shown flag; a player sees it only while it is shown."""
import sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "tools")]

import map_paint  # noqa: E402

PIC = "data:image/png;base64,iVBORw0KGgo="


class MapPaint(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "map_paint.json"
        self.paint = map_paint.MapPaint(self.path)

    def test_kept_per_map_and_shown_only_when_revealed(self):
        out = self.paint.save("Cave", picture=PIC)
        self.assertEqual((out["rev"], out["shown"], out["picture"]), (1, False, PIC))
        self.assertNotIn("picture", self.paint.get("Cave", player=True))      # hidden from the players
        self.assertEqual(self.paint.get("Hall")["picture"], "")                 # another map has its own
        self.paint.save("Cave", shown=True)
        again = map_paint.MapPaint(self.path)                                   # kept on disk
        self.assertEqual(again.get("Cave", player=True)["picture"], PIC)
        self.assertNotIn("picture", again.get("Cave", rev=2, player=True))     # unchanged since the last look

    def test_cleared_keeps_its_revision_and_refuses_other_pictures(self):
        self.paint.save("Cave", picture=PIC, shown=True)
        out = self.paint.save("Cave", picture="", shown=False)
        self.assertEqual((out["rev"], out["picture"]), (2, ""))
        self.assertEqual(self.paint.save("Cave", picture=PIC)["rev"], 3)     # a page following rev 1 still sees the change
        with self.assertRaises(map_paint.PaintError):
            self.paint.save("Cave", picture="data:image/svg+xml;base64,PHN2Zz4=")
        with self.assertRaises(map_paint.PaintError):
            self.paint.save("", picture=PIC)


if __name__ == "__main__":
    unittest.main()
