"""SIM-LAB-01 (2026-10-18): the simulator's test lab, small temporary maps for mechanics the Seven Isles maps do not
exercise (GM: "build the test lab with all five maps (sunlight, underwater, sky and falling, mounted land, cover and
hiding)"). Simulator only: not adventure maps, no FG module. Creatures come from the SRD 5.2.1 bestiary
(DNDSRD521BESTIARY) through bestiary_catalog; their simple attacks are read from the stat-block text.

  py tools/build_test_lab.py            # writes sim/scenarios/test/lab_*.json
  py tools/build_test_lab.py creature "Hunter Shark"   # prints a ready simulator block for one SRD creature (map
                                                        # authors paste it into a map spec's sim["creatures"])
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import bestiary_catalog  # noqa: E402

OUT = ROOT / "sim" / "scenarios" / "test"   # GM 2026-10-25: test maps in test/
SRD = ("This work includes material from the System Reference Document 5.2.1 (\"SRD 5.2.1\") by Wizards of the Coast "
       "LLC, available at https://www.dndbeyond.com/srd. The SRD 5.2.1 is licensed under the Creative Commons Attribution "
       "4.0 International License, available at https://creativecommons.org/licenses/by/4.0/legalcode.")
ATTACK = re.compile(r"(Melee|Ranged|Melee or Ranged) Attack Roll: \+(\d+)[^,]*, (?:reach|range) (\d+)(?:/\d+)? ft\..*?"
                    r"Hit: \d+ \((\d+d\d+)(?: \+ (\d+))?\) (\w+) damage(?: plus \d+ \((\d+d\d+)(?: \+ \d+)?\) (\w+) damage)?",
                    re.S)
_RECS = None
_IDS = {}


def records():
    global _RECS
    if _RECS is None:
        srd = bestiary_catalog.load_srd()
        _RECS = {r["name"]: r["fields"] for r in srd}
        _IDS.update({r["name"]: r.get("id") for r in srd})
    return _RECS


def fg_link(kind):
    """The SRD record's FG link and token, for a map spec's encounter: ("npc.id-NNNNN@DNDSRD521BESTIARY", token)."""
    f = records()[kind]
    return "npc.%s@DNDSRD521BESTIARY" % _IDS[kind], str(f.get("token") or "")


def text(v):
    return " ".join(text(x) for x in v.values()) if isinstance(v, dict) else str(v)


def creature(kind, number, x, y, side="foe", **extra):
    """A scenario combatant from the SRD record: hit points, AC, speed, size, senses, type, Int, attacks."""
    f = records()[kind]
    actions = []
    for k, e in enumerate((f.get("actions") or {}).values(), 1):
        if not isinstance(e, dict):
            continue
        desc = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text(e.get("desc", ""))))
        a = {"id": "id-%05d" % k, "name": str(e.get("name", "")), "desc": desc}
        m = ATTACK.search(desc)
        if m and e.get("name") != "Multiattack":
            kind_, atk, reach, dice, add, dtype, dice2, dtype2 = m.groups()
            a.update(atk=int(atk), atktype="ranged" if kind_ == "Ranged" else "melee",
                     reach=int(reach) if kind_ == "Ranged" else (int(reach) if kind_ == "Melee" else 5),
                     dmg=dice + ("+%s" % add if add else ""), dmgtype=dtype.lower())
            if dice2:
                a.update(dmg2=dice2, dmgtype2=dtype2.lower())
        actions.append(a)
    size = str(f.get("size") or "Medium").lower()
    space = {"large": 10, "huge": 15, "gargantuan": 20}.get(size, 5)
    ab = f.get("abilities") or {}
    c = {"id": extra.pop("id"), "name": "%s %d" % (kind, number), "side": side, "hp": int(str(f.get("hp")).split()[0]),
         "ac": int(str(f.get("ac")).split()[0]), "speed": str(f.get("speed") or "30 ft."), "space": space,
         "size": size, "type": str(f.get("type") or "").split()[0].capitalize(), "senses": str(f.get("senses") or ""),
         "int": int((ab.get("intelligence") or {}).get("score") or 10), "skills": str(f.get("skills") or ""),
         "x": x, "y": y, "init": extra.pop("init", 10),
         "actions": actions}
    c.update(extra)
    return c


def room(w, h):
    """The four outer walls of a w x h room (squares; walls on the square edges)."""
    a, b = -0.5, (w - 0.5, h - 0.5)
    return [{"id": "0", "points": [[a, a], [b[0], a]]}, {"id": "1", "points": [[b[0], a], [b[0], b[1]]]},
            {"id": "2", "points": [[b[0], b[1]], [a, b[1]]]}, {"id": "3", "points": [[a, b[1]], [a, a]]}]


def party(spots):
    return [{"id": "id-%05d" % (i + 1), "name": n, "side": "friend", "pc": True, "x": x, "y": y, "init": 15 - i}
            for i, (n, (x, y)) in enumerate(spots.items())]


def lab_underwater():
    """A flooded hall: a dry ledge (east), a pool (west) with a current along the north wall and a silt cloud."""
    foes = [creature("Hunter Shark", 1, 4, 8, id="id-00011", init=12), creature("Hunter Shark", 2, 6, 12, id="id-00012", init=8),
            creature("Sahuagin Warrior", 1, 9, 5, id="id-00013", init=11), creature("Sahuagin Warrior", 2, 10, 10, id="id-00014", init=9),
            creature("Giant Octopus", 1, 2, 3, id="id-00015", init=7)]
    return {"name": "Test lab: underwater (simulator only)", "rounds": 6, "level": 8,
            "source": SRD + " Simulator test map (SIM-LAB-01): not an adventure map. Monsters move at their listed speed "
                      "(the bridge plans their moves); only the party pays the swimming cost.",
            "grid": 50, "units": 5, "diag": 1, "map_name": "Test lab - underwater", "perception_dc": 15,
            "walls": room(24, 16), "open_doors": [], "locked_doors": [],
            "lighting": {"ambient": "dim", "lights": []}, "aware": [f["id"] for f in foes],
            "zones": [{"id": "pool", "kind": "water", "rect": [0, 0, 13, 15]},
                      {"id": "race", "kind": "current", "rect": [0, 0, 13, 2], "dx": 1, "dy": 0, "ft": 10},
                      {"id": "silt", "kind": "obscured", "rect": [5, 6, 7, 9], "level": "heavy"}],
            "combatants": party({"Hero 1": (16, 7), "Hero 3": (16, 9), "Hero 2": (18, 8), "Hero 4": (19, 9)}) + foes}


def lab_sunlight():
    """A sunlit courtyard with a shaded colonnade (east): a wight and shadows that prefer the shade."""
    foes = [creature("Wight", 1, 12, 4, id="id-00011", init=12), creature("Shadow", 1, 20, 3, id="id-00012", init=11),
            creature("Shadow", 2, 21, 8, id="id-00013", init=9), creature("Zombie", 1, 10, 9, id="id-00014", init=6),
            creature("Zombie", 2, 13, 11, id="id-00015", init=5)]
    return {"name": "Test lab: sunlight (simulator only)", "rounds": 6, "level": 5,
            "source": SRD + " Simulator test map (SIM-LAB-01): not an adventure map.",
            "grid": 50, "units": 5, "diag": 1, "map_name": "Test lab - sunlight", "perception_dc": 15,
            "walls": room(24, 16), "open_doors": [], "locked_doors": [],
            "lighting": {"ambient": "sunlight", "lights": []}, "aware": [f["id"] for f in foes],
            "zones": [{"id": "colonnade", "kind": "shade", "rect": [18, 0, 23, 15]}],
            "combatants": party({"Hero 1": (3, 7), "Hero 3": (3, 9), "Hero 2": (2, 8), "Hero 4": (1, 9)}) + foes}


def lab_sky():
    """A cliff ledge (west) above a 30-ft chasm (columns 12-15) with a far ledge (east): bandits hold the edge, gargoyles
    fly over the chasm. Shove off the ledge, fliers falling when they lose their flight, Hero 5's Winged Boots."""
    foes = [creature("Bandit", 1, 11, 4, id="id-00011", init=12), creature("Bandit", 2, 11, 7, id="id-00012", init=11),
            creature("Bandit", 3, 11, 10, id="id-00013", init=10), creature("Gargoyle", 1, 13, 5, id="id-00014", init=9),
            creature("Gargoyle", 2, 14, 9, id="id-00015", init=7)]
    return {"name": "Test lab: sky and falling (simulator only)", "rounds": 6, "level": 7,
            "source": SRD + " Simulator test map (SIM-LAB-01): not an adventure map. A creature walking into the chasm "
                      "climbs down; a shove or a lost flight makes it fall 30 ft.",
            "grid": 50, "units": 5, "diag": 1, "map_name": "Test lab - sky", "perception_dc": 15,
            "walls": room(24, 16), "open_doors": [], "locked_doors": [],
            "lighting": {"ambient": "bright", "lights": []}, "aware": [f["id"] for f in foes],
            "zones": [{"id": "chasm", "kind": "drop", "rect": [12, 0, 15, 15], "height": 30}],
            "combatants": party({"Hero 1": (6, 5), "Hero 5": (6, 9), "Hero 6": (5, 7), "Hero 4": (3, 7)}) + foes}


def lab_cover():
    """A dark courtyard lit by a lantern: low walls (Half Cover), a barricade (Three-Quarters) with two scouts behind it,
    two bandits in the open, two shadows in the unlit north-east corner. Cover, Hide (Hero 3: Cunning Action, Boots of
    Elvenkind), Shadow Stealth."""
    foes = [creature("Scout", 1, 18, 6, id="id-00011", init=13), creature("Scout", 2, 18, 9, id="id-00012", init=12),
            creature("Bandit", 1, 11, 4, id="id-00013", init=10), creature("Bandit", 2, 11, 11, id="id-00014", init=9),
            creature("Shadow", 1, 21, 1, id="id-00015", init=8), creature("Shadow", 2, 22, 2, id="id-00016", init=7)]
    return {"name": "Test lab: cover and hiding (simulator only)", "rounds": 6, "level": 5,
            "source": SRD + " Simulator test map (SIM-LAB-01): not an adventure map.",
            "grid": 50, "units": 5, "diag": 1, "map_name": "Test lab - cover", "perception_dc": 15,
            "walls": room(24, 16), "open_doors": [], "locked_doors": [],
            "lighting": {"ambient": "dark", "lights": [{"x": 11, "y": 8, "bright_ft": 20, "dim_ft": 40, "label": "lantern"},
                                                       {"carrier": "id-00001", "bright_ft": 20, "dim_ft": 40,
                                                        "label": "Hero 1's Torch (SRD 5.2.1)"}]},
            "aware": [f["id"] for f in foes],
            "zones": [{"id": "low wall north", "kind": "cover", "rect": [8, 2, 8, 6], "level": "half"},
                      {"id": "low wall south", "kind": "cover", "rect": [8, 10, 8, 13], "level": "half"},
                      {"id": "barricade", "kind": "cover", "rect": [16, 4, 16, 11], "level": "three-quarters"}],
            "combatants": party({"Hero 1": (3, 7), "Hero 3": (4, 9), "Hero 2": (2, 8), "Hero 4": (2, 10)}) + foes}


def lab_mounted():
    """An open field: Hero 1 and Hero 6 ride Warhorses (controlled mounts), Hero 3 and Hero 4 on foot, against guards and scouts
    who may bring the horses down (Falling Off)."""
    pcs = party({"Hero 1": (4, 6), "Hero 6": (4, 10), "Hero 3": (2, 8), "Hero 4": (1, 9)})
    pcs[0]["mount"], pcs[1]["mount"] = "id-00021", "id-00022"
    horses = [creature("Warhorse", 1, 4, 6, side="friend", id="id-00021", init=15),
              creature("Warhorse", 2, 4, 10, side="friend", id="id-00022", init=14)]
    foes = [creature("Guard", n, 19, 4 + 2 * n, id="id-%05d" % (10 + n), init=12 - n) for n in range(1, 5)]
    foes += [creature("Scout", 1, 22, 5, id="id-00015", init=13), creature("Scout", 2, 22, 11, id="id-00016", init=8)]
    return {"name": "Test lab: mounted combat (simulator only)", "rounds": 6, "level": 5,
            "source": SRD + " Simulator test map (SIM-LAB-01): not an adventure map. Controlled mounts move with their "
                      "riders and take no turn of their own.",
            "grid": 50, "units": 5, "diag": 1, "map_name": "Test lab - mounted", "perception_dc": 15,
            "walls": room(24, 16), "open_doors": [], "locked_doors": [],
            "lighting": {"ambient": "bright", "lights": []}, "aware": [f["id"] for f in foes],
            "combatants": pcs + horses + foes}


MAPS = {"lab_underwater": lab_underwater, "lab_sunlight": lab_sunlight, "lab_sky": lab_sky, "lab_cover": lab_cover,
        "lab_mounted": lab_mounted}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["creature"]:
        kind = " ".join(argv[1:])
        c = creature(kind, 1, 0, 0, id="id-00000")
        link, token = fg_link(kind)
        print("# encounter link and token: %r, %r" % (link, token))
        print(json.dumps({k: v for k, v in c.items() if k not in ("id", "name", "side", "x", "y", "init")}, indent=1))
        return
    for name, build in MAPS.items():
        path = OUT / (name + ".json")
        path.write_text(json.dumps(build(), indent=1) + "\n", encoding="utf-8")
        print("wrote", path.relative_to(ROOT))


if __name__ == "__main__":
    main()
