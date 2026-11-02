"""ATLAS-01 (GM 2026-10-22: "create a database that allows multiple maps to be connected"): the map database
(tools/atlas.py) and its service routes."""
import json, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "sim"), str(ROOT / "mythastria_core")]
import atlas  # noqa: E402


def region(name, places=()):
    return {"format": "region-map/1", "name": name, "grid": {"pxPerMile": 30, "ox": 0, "oy": 0}, "terrain": {},
            "locations": [dict(p) for p in places], "picture": None}


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_maps_are_kept_listed_and_opened_again(self):
        a = atlas.save_map(region("The Ember Coast"), root=self.root)
        self.assertRegex(a, r"^m[0-9a-f]{10}$")
        self.assertEqual(atlas.get_map(a, self.root)["name"], "The Ember Coast")
        b = atlas.save_map(region("The Isles"), root=self.root)
        self.assertEqual({m["name"] for m in atlas.list_maps(self.root)}, {"The Ember Coast", "The Isles"})
        atlas.save_map(region("The Ember Coast, renamed"), a, self.root)
        self.assertEqual(len(atlas.list_maps(self.root)), 2, "saving again keeps one map")
        self.assertEqual(atlas.get_map(a, self.root)["name"], "The Ember Coast, renamed")
        atlas.delete_map(b, self.root)
        self.assertEqual([m["id"] for m in atlas.list_maps(self.root)], [a])
        with self.assertRaises(atlas.AtlasError):
            atlas.get_map(b, self.root)
        self.assertEqual((self.root / ".gitignore").read_text(), "*\n", "the GM's maps are never committed")

    def test_places_connect_maps_both_ways(self):
        valley = atlas.save_map(region("The Valley"), root=self.root)
        coast = atlas.save_map(region("The Coast", [{"hex": "3,4", "number": 1, "name": "", "to": {"map": valley}},
                                                    {"hex": "5,1", "number": 2, "name": "Old Mill", "map": "bell_cove.json"}]),
                               root=self.root)
        rows = {m["id"]: m for m in atlas.list_maps(self.root)}
        self.assertEqual(rows[coast]["links"], [valley])
        self.assertEqual(rows[coast]["tactical"], ["bell_cove.json"])
        self.assertEqual(rows[valley]["linked_from"], [coast], "the valley knows the coast leads to it")

    def test_only_mythastria_maps_are_kept(self):
        for bad in ({}, {"format": "something"}, region("x", [{"number": 1}]), region("x", [{"hex": "1,1", "to": {"map": "../../etc"}}])):
            with self.assertRaises(atlas.AtlasError):
                atlas.save_map(bad, root=self.root)
        for bad_id in ("../x", "m123", "M0123456789"):
            with self.assertRaises(atlas.AtlasError):
                atlas.get_map(bad_id, self.root)

    def test_filing_protocol_projects_and_spare_maps(self):
        """GM: "a filing protocol that keeps all maps associated with a project, and a place for spare maps"."""
        isles = atlas.create_project("Seven Isles", self.root)
        a = atlas.save_map(region("Bell Cove"), root=self.root, project=isles)
        b = atlas.save_map(region("Loose sketch"), root=self.root)                       # rule 1: no project -> Spare maps
        self.assertEqual([m["name"] for m in atlas.list_maps(self.root, isles)], ["Bell Cove"])
        self.assertEqual([m["name"] for m in atlas.list_maps(self.root, None)], ["Loose sketch"])
        atlas.save_map(region("Bell Cove, painted"), a, self.root)                       # saving again keeps its project
        self.assertEqual(atlas.list_maps(self.root, isles)[0]["name"], "Bell Cove, painted")
        atlas.move_map(b, isles, self.root)                                                # rule 3: the GM moves it
        self.assertEqual(len(atlas.list_maps(self.root, isles)), 2)
        rows = {p["name"]: p for p in atlas.list_projects(self.root)}
        self.assertEqual((rows["Seven Isles"]["maps"], rows["Spare maps"]["maps"], atlas.list_projects(self.root)[-1]["id"]), (2, 0, None))
        atlas.rename_project(isles, "The Seven Isles", self.root)
        atlas.delete_project(isles, self.root)                                            # rule 4: maps go to Spare maps
        self.assertEqual(len(atlas.list_maps(self.root, None)), 2)
        self.assertEqual(len(atlas.list_maps(self.root)), 2, "no map deleted")
        for bad in (lambda: atlas.move_map(a, "pdeadbeef", self.root), lambda: atlas.delete_project(None, self.root),
                    lambda: atlas.create_project("", self.root), lambda: atlas.save_map(region("x"), root=self.root, project="nope")):
            with self.assertRaises(atlas.AtlasError):
                bad()

    def test_a_project_exports_as_one_file_and_imports_with_its_links(self):
        pid = atlas.create_project("Ember", self.root)
        valley = atlas.save_map(region("Valley"), root=self.root, project=pid)
        coast = atlas.save_map(region("Coast", [{"hex": "1,1", "number": 1, "name": "", "kind": "portal", "to": {"map": valley, "hex": "4,4"}}]),
                               root=self.root, project=pid)
        bundle = json.loads(json.dumps(atlas.export_project(pid, self.root)))
        self.assertEqual((bundle["format"], bundle["name"], len(bundle["maps"])), ("mythastria-project/1", "Ember", 2))
        new = atlas.import_project(bundle, self.root)
        self.assertNotEqual(new, pid)
        self.assertEqual({p["name"] for p in atlas.list_projects(self.root)}, {"Ember", "Ember (2)", "Spare maps"})
        maps = {m["name"]: m for m in atlas.list_maps(self.root, new)}
        self.assertNotIn(maps["Valley"]["id"], (valley, coast), "new ids")
        portal = atlas.get_map(maps["Coast"]["id"], self.root)["locations"][0]
        self.assertEqual(portal["to"], {"map": maps["Valley"]["id"], "hex": "4,4"}, "the portal follows the new ids")
        self.assertEqual(maps["Coast"]["portals"], 1)
        with self.assertRaises(atlas.AtlasError):
            atlas.import_project({"format": "nope"}, self.root)

    def test_a_portal_leads_to_a_spot_on_another_map(self):
        valley = atlas.save_map(region("Valley"), root=self.root)
        atlas.save_map(region("Coast", [{"hex": "1,1", "kind": "portal", "to": {"map": valley, "hex": "-3,7"}}]), root=self.root)
        with self.assertRaises(atlas.AtlasError):
            atlas.save_map(region("Bad", [{"hex": "1,1", "kind": "portal", "to": {"map": valley, "hex": "up"}}]), root=self.root)

    def test_the_service_routes(self):
        import sim_service as S
        service = S.Service()
        service.atlas_dir = self.root
        code, out = service.atlas({"map": region("Through the service")}, "save")
        self.assertEqual(code, 200)
        map_id = out["id"]
        self.assertEqual(service.atlas({}, "list")[1]["maps"][0]["name"], "Through the service")
        self.assertEqual(service.atlas({}, "list")[1]["projects"][-1]["name"], "Spare maps")
        pid = service.atlas({"action": "create", "name": "Campaign"}, "project")[1]["project"]
        service.atlas({"id": map_id, "project": pid}, "move")
        self.assertEqual(service.atlas({"project": pid}, "export")[1]["bundle"]["maps"][0]["id"], map_id)
        new = service.atlas({"map": region("Filed"), "project": pid}, "save")[1]["id"]
        self.assertEqual({m["id"] for m in service.atlas({}, "list")[1]["maps"] if m["project"] == pid}, {map_id, new})
        self.assertEqual(service.atlas({"id": map_id}, "get")[1]["map"]["name"], "Through the service")
        self.assertEqual(service.atlas({"id": map_id}, "delete")[0], 200)
        with self.assertRaises(ValueError):
            service.atlas({"id": map_id}, "get")
        with self.assertRaises(ValueError):
            service.atlas({"map": {"format": "nope"}}, "save")
        self.assertGreaterEqual(S.ROUTE_BODY["/api/atlas/save"], 48 * 1024 * 1024, "a map with its picture fits")


if __name__ == "__main__":
    unittest.main()
