"""GM 2026-10-25 ("let's organize the adventure selection. There needs to be folders and subfolders"): test maps in
sim/scenarios/test/, each adventure's maps and their party-level versions in its module, the old names still taken.
  py -m unittest test_scenario_folders
"""
import sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "sim"), str(ROOT / "mythastria_core")]
import scenario_folders as sf

PACKS = ROOT.parent / "Mythastria_Adventures"


class Folders(unittest.TestCase):
    def test_test_maps_have_their_groups(self):
        self.assertEqual(sf.folder_of("test/live_keep.json"), ["Test", "Live play"])
        self.assertEqual(sf.folder_of("test/lab_cover.json"), ["Test", "Labs"])
        self.assertEqual(sf.folder_of("test/walls_door.json"), ["Test", "Walls and doors"])
        self.assertEqual(sf.folder_of("test/grick_2024.json"), ["Test", "Fights"])
        self.assertEqual(sf.folder_of("test/drowned_way/dw_1_gallery.json"), ["Test", "Drowned Way"])
        self.assertEqual(sf.folder_of("region/road_2901_bandit.json"), ["Region battles"])

    def test_no_test_map_is_left_at_the_top(self):
        top = {p.name for p in (ROOT / "sim" / "scenarios").glob("*.json")}
        for name in ("lab_cover.json", "walls_door.json", "grick_2024.json", "two_reactors.json"):
            self.assertNotIn(name, top)
            self.assertTrue(list((ROOT / "sim" / "scenarios" / "test").rglob(name)), name)

    def test_the_same_title_twice_is_told_apart(self):
        names = ["test/drowned_way/dw_1_gallery.json", "test/drowned_way/dw_1_gallery_shark.json"]
        t = sf.tree(names, {}, lambda n: {"name": "Drowned Way 1: the Breathing Gallery (simulator test)"})
        self.assertEqual([x["label"] for x in t], ["Drowned Way 1: the Breathing Gallery",
                                                   "Drowned Way 1: the Breathing Gallery (shark)"])


@unittest.skipUnless((PACKS / "seven_isles" / "adventure.json").is_file(), "the adventure packs are not on this PC")
class SevenIsles(unittest.TestCase):
    def setUp(self):
        import sim_service, adventure_packs
        self.svc = sim_service.Service()
        self.svc.packs = adventure_packs.Packs(PACKS)
        self.svc.packs.load("seven_isles")

    def test_levels_and_floors_are_subfolders_of_the_adventure(self):
        t = {x["name"]: x for x in self.svc.scenario_tree()}
        self.assertEqual(t["pack/seven_isles/bell_cove_L4.json"]["path"], ["Adventures", "Seven Isles (Free Adventure)", "Level 4"])
        self.assertEqual(t["pack/seven_isles/bell_cove_L4.json"]["label"], "The bell cove (party level 4)")
        self.assertEqual(t["pack/seven_isles/watch_temple_interior.json"]["path"][-1], "Watch Temple")
        self.assertEqual(t["pack/seven_isles/watch_temple_interior.json"]["label"], "Interior")
        self.assertEqual(list(t)[0].startswith("pack/"), True)              # the adventures come first

    def test_level_versions_are_not_places_of_the_adventure(self):
        places = self.svc.packs.plan("seven_isles")["places"]
        self.assertEqual(len(places), 17)
        self.assertFalse(any(p["key"].endswith("_L4") for p in places))

    def test_the_old_names_still_start_a_fight(self):
        self.assertEqual(self.svc.check_new({"scenario": "walls_door_ui.json"})[0], "test/walls_door_ui.json")
        self.assertEqual(self.svc.check_new({"scenario": "test/bell_cove_L4.json"})[0], "pack/seven_isles/bell_cove_L4.json")
