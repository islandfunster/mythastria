"""v0.7.73 WALLS-01a: walls from a map's "Export Image to File" XML (user: exports are easy, live reading is not needed).
Import into a local wall cache, then a visual calibration: candidate alignments between the export's coordinates and
FG's token positions are drawn side by side in a local HTML page; the GM confirms one, which is stored with the map.
Synthetic XML only (no module geometry)."""
import json, os, shutil, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "mythastria_core"))
import map_walls

XML = """<?xml version="1.0" encoding="utf-8"?>
<root version="5.1" dataversion="20260124">
  <grid>on</grid><gridsize>41,41</gridsize><gridoffset>39,2</gridoffset>
  <occluders>
    <occluder><id>1</id><points>-100,-50,100,-50,100,50,-100,50</points><closed /></occluder>
    <occluder><id>2</id><points>0,-50,0,50</points><toggleable /><closed /></occluder>
    <occluder><id>3</id><points>-200,0,-150,0</points><single_sided /><counterclockwise /></occluder>
    <occluder><id>4</id><points>5,5,6,6</points><hidden /><toggleable /></occluder>
    <occluder><id>5</id><points>1,2,3</points></occluder>
  </occluders>
  <lights><light><id>9</id><position>10,20</position><on /><range>30</range></light></lights>
</root>"""


class Import(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.xml = self.dir / "Map - Test.xml"; self.xml.write_text(XML, encoding="utf-8")
        os.environ["MYTHASTRIA_WALLS_DIR"] = str(self.dir / "walls")
    def tearDown(self):
        os.environ.pop("MYTHASTRIA_WALLS_DIR", None); shutil.rmtree(self.dir, ignore_errors=True)

    def test_parse_occluders_flags_by_presence_and_skips_bad_points(self):
        w = map_walls.parse_export(self.xml)
        self.assertEqual((w["gridsize"], w["gridoffset"]), ([41.0, 41.0], [39.0, 2.0]))
        ids = [o["id"] for o in w["occluders"]]
        self.assertEqual(ids, ["1", "2", "3", "4"])                                  # odd point count rejected
        o1, o2, o3, o4 = w["occluders"]
        self.assertEqual((o1["closed"], o1["door"], len(map_walls.segments(o1))), (True, False, 4))   # closed loop
        self.assertEqual((o2["door"], o3["single_sided"], o4["hidden"]), (True, True, True))
        self.assertEqual(len(map_walls.segments(o3)), 1)
        self.assertEqual(w["skipped"], 1); self.assertEqual(len(w["lights"]), 1)

    def test_transforms(self):
        size = (2000.0, 1600.0)
        self.assertEqual(map_walls.apply("center_down", (-100, -50), size), (900.0, 750.0))
        self.assertEqual(map_walls.apply("center_up", (-100, -50), size), (900.0, 850.0))
        self.assertEqual(map_walls.apply("identity", (-100, -50), size), (-100, -50))
        self.assertEqual(map_walls.apply("flip_y", (-100, -50), None), (-100, 50))
        self.assertEqual(sorted(map_walls.TRANSFORMS), ["center_down", "center_up", "flip_y", "identity"])
        # field result 18:36: FG reported no image size; only size-free options are offered then
        self.assertEqual(map_walls.candidates(None), ["identity", "flip_y"])
        self.assertEqual(map_walls.candidates((2000.0, 1600.0)), list(map_walls.TRANSFORMS))

    def test_store_load_confirm_stays_in_the_cache(self):
        w = map_walls.parse_export(self.xml)
        p = map_walls.save("My Map", w, source=str(self.xml))
        self.assertTrue(str(p).startswith(str(self.dir / "walls")))
        self.assertIsNone(map_walls.load("My Map")["transform"])           # not usable until confirmed
        self.assertIsNone(map_walls.usable("My Map"))
        map_walls.confirm("My Map", "center_down", (2000.0, 1600.0))
        u = map_walls.usable("My Map")
        self.assertEqual(u["transform"], "center_down"); self.assertEqual(u["image_size"], [2000.0, 1600.0])
        with self.assertRaises(ValueError):
            map_walls.confirm("My Map", "rotated", (1, 1))
        map_walls.confirm("My Map", "identity", None)                    # no image size needed
        self.assertEqual(map_walls.usable("My Map")["transform"], "identity")
        with self.assertRaises(ValueError):
            map_walls.confirm("My Map", "center_down", None)            # needs the image size

    def test_calibration_page_draws_every_candidate_with_tokens(self):
        w = map_walls.parse_export(self.xml)
        tokens = [{"name": "Gobliez 1", "x": 900.0, "y": 760.0, "side": "foe"},
                  {"name": "Pally", "x": 1050.0, "y": 800.0, "side": "friend"}]
        html = map_walls.calibration_html("Test map", w, tokens, (2000.0, 1600.0), (33.1, 26.3), (5.93, 2.0))
        for t in map_walls.TRANSFORMS:
            self.assertIn('data-transform="%s"' % t, html)
        self.assertEqual(html.count("<svg"), 4)
        # no image size: drawn to fit walls and tokens, only the size-free options
        html2 = map_walls.calibration_html("Test map", w, tokens, None, (33.1, 26.3), (5.93, 2.0))
        self.assertEqual(html2.count("<svg"), 2); self.assertNotIn('data-transform="center_down"', html2)
        self.assertIn("Gobliez 1", html); self.assertIn("Pally", html)
        self.assertIn("stroke-dasharray", html)                                    # doors drawn dashed
        self.assertNotIn("http://", html.replace('xmlns="http://www.w3.org/2000/svg"', ""))   # no external fetches


if __name__ == "__main__":
    unittest.main()
