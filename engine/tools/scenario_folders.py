"""GM 2026-10-25 ("let's organize the adventure selection. There needs to be folders and subfolders. Test maps need to go
into a test folder. Adventures need their own folders included in their modules. Levels of each adventures need their own
sub folders"; chose levels = both party levels and floors): the folder each map is shown in on the map pickers.

  Adventures > <adventure> > Level <n> [> <place, its floors>]  a loaded pack's maps (Packs.folders)
  Test > Live play | Labs | Walls and doors | Fights  sim/scenarios/test/
  Region battles, Region sites > <project> > <region>, Imported maps, Other   sim/scenarios/region/, sites/, imported/, the rest
Read only; the names stay what the service takes (scenario names)."""
import re

TEST_GROUPS = (("live_", "Live play"), ("lab_", "Labs"), ("walls_", "Walls and doors"))
TOP = {"test": "Test", "region": "Region battles", "imported": "Imported maps", "sites": "Region sites"}   # sites: MAPGEN-02
ORDER = ["Adventures", "Test", "Region battles", "Region sites", "Imported maps", "Other"]


def title(sc, fallback):
    """A map's own name without its "(...)" note, or the file name made readable."""
    name = str((sc or {}).get("name") or "").strip()
    name = re.sub(r"\s*\([^)]*\)\s*$", "", name)
    return name or fallback.rsplit("/", 1)[-1].replace(".json", "").replace("_", " ").capitalize()


def folder_of(name):
    """The folders of a map outside the adventures (its name's own folders)."""
    parts = name.split("/")
    if len(parts) == 1:
        return ["Other"]
    top = TOP.get(parts[0], parts[0].replace("_", " ").title())
    if parts[0] != "test":
        return [top] + [p.replace("_", " ").title() for p in parts[1:-1]]
    if len(parts) > 2:
        return [top] + [p.replace("_", " ").title() for p in parts[1:-1]]
    group = next((g for prefix, g in TEST_GROUPS if parts[1].startswith(prefix)), "Fights")
    return [top, group]


def tree(names, pack_folders, read):
    """[{name, path: [folder, subfolder...], label}] for every name, adventures first, each folder's maps in order.
    `pack_folders`: {name: (path, label, order)} from Packs.folders(); `read(name)`: the scenario (for its title)."""
    out = []
    for n in names:
        if n in pack_folders:
            path, label, order = pack_folders[n]
            out.append({"name": n, "path": ["Adventures"] + list(path), "label": label, "_k": order})
            continue
        try:
            sc = read(n)
        except (OSError, ValueError):
            sc = None
        out.append({"name": n, "path": folder_of(n), "label": title(sc, n), "_k": (0, n)})
    top = lambda p: ORDER.index(p[0]) if p[0] in ORDER else len(ORDER)
    out.sort(key=lambda x: (top(x["path"]), x["path"][:1], x["_k"] if x["path"][0] == "Adventures" else (0, x["path"], x["label"].lower())))
    seen = {}
    for x in out:                                                # the same title twice in a folder: its file tells them apart
        seen.setdefault((tuple(x["path"]), x["label"]), []).append(x)
    for group in seen.values():
        if len(group) > 1:
            stems = [g["name"].rsplit("/", 1)[-1][:-5] for g in group]
            short = min(stems, key=len)
            for g, s in zip(group, stems):
                if s != short and s.startswith(short):
                    g["label"] += " (%s)" % s[len(short):].strip("_").replace("_", " ")
    for x in out:
        x.pop("_k")
    return out
