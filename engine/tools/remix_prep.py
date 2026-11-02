"""GM 2026-10-24 ("The adventure can have a default hostility for each level. or even encounter if it's written into
the adventure as a narrative. Morale should also be part of the prep along-side hostility. That can be added to
remix."): Remix Prep's attitudes and morale (plan: docs/development/ADVENTURE_PILLARS_PLAN.md step 3; the rules:
sim/attitude.py).

Saved with the campaign's Remix (sim/remixes/<campaign>.json, the same revision as its saved remixes), under "prep":
  {"levels": {"3": "Indifferent"},                     the GM's default attitude for a level
   "scenarios": {"<map>": {"attitude": "Hostile",     this encounter's default (its narrative)
                           "groups": {"<creature kind>": {"attitude": "Indifferent",
                                                          "morale": {"rule": "surrender", "when": ["half", "leader"],
                                                                     "leader": "Bandit Captain"}}}}}}
An adventure pack may carry defaults in its manifest (adventure.json), the same shape under "attitudes":
  {"levels": {"1": "Hostile"}, "encounters": {"<map>": "Indifferent"}}; the GM's prep wins over them.
Every choice is checked (sim/requirements.py through attitude.check_prep) before it is saved, with the reason when not.
"""
import attitude


def _prep(st):
    p = st.get("prep") or {}
    return {"levels": dict(p.get("levels") or {}), "scenarios": dict(p.get("scenarios") or {}),
            "optional": dict(p.get("optional") or {})}


OPTIONAL = {"social": "the Social interaction rules pack (creature dispositions on first meeting; sim/social_pack.py)"}


def optional(remix, campaign):
    """GM 2026-10-25: the campaign's optional rules packs ({"social": True}); every live fight reads them, Remix on or
    off."""
    with remix.lock:
        return {k: True for k, v in _prep(remix._campaign(campaign))["optional"].items() if v and k in OPTIONAL}


def pack_defaults(remix, scenario):
    """The adventure pack's own defaults for a map ("pack/<id>/..."), or {}."""
    parts = str(scenario or "").split("/")
    if len(parts) < 3 or parts[0] != "pack":
        return {}
    try:
        _, manifest = remix.packs._manifest(parts[1])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}
    a = manifest.get("attitudes") or {}
    short = "/".join(parts[2:])
    enc = (a.get("encounters") or {})
    return {"levels": dict(a.get("levels") or {}), "encounter": enc.get(scenario, enc.get(short))}


def kinds(raw):
    """The creature kinds of a map (not the characters), each with its count and a sample stat block."""
    out = {}
    for c in raw.get("combatants") or []:
        if c.get("pc"):
            continue
        k = attitude.kind(c)
        e = out.setdefault(k, {"kind": k, "count": 0, "sample": c})
        e["count"] += 1
    return out


def for_fight(remix, campaign, scenario):
    """The prep a live fight uses: the GM's (campaign) over the pack's defaults."""
    with remix.lock:
        p = _prep(remix._campaign(campaign))
    return {"levels": p["levels"], "scenario": p["scenarios"].get(scenario) or {}, "pack": pack_defaults(remix, scenario),
            "optional": {k: True for k, v in p["optional"].items() if v and k in OPTIONAL}}


def state(remix, campaign, scenario, raw, level):
    """Remix Prep's view of one map: the defaults, each creature kind with its nature, its prep and the attitude it
    would start with at this level."""
    with remix.lock:
        st = remix._campaign(campaign)
    p = _prep(st)
    prep = {"levels": p["levels"], "scenario": p["scenarios"].get(scenario) or {}, "pack": pack_defaults(remix, scenario),
            "optional": {k: True for k, v in p["optional"].items() if v and k in OPTIONAL}}
    groups = prep["scenario"].get("groups") or {}
    rows = []
    for k, e in sorted(kinds(raw).items()):
        c = dict(e["sample"], group=k)
        nat, why = attitude.nature(c)
        start, source, _ = attitude.starting(c, prep, level)
        g = groups.get(k) or {}
        rows.append({"kind": k, "count": e["count"], "nature": nat, "nature_why": why, "attitude": g.get("attitude"),
                     "morale": g.get("morale"), "starts": start, "from": source,
                     "morale_text": attitude.morale_text(g.get("morale")),
                     "pack": attitude.social_pack.disposition(c)})
    return {"ok": True, "campaign": st["campaign"], "revision": st["revision"], "scenario": scenario, "level": level,
            "levels": p["levels"], "encounter": prep["scenario"].get("attitude"), "pack": prep["pack"], "kinds": rows,
            "attitudes": list(attitude.ATTITUDES), "rules": attitude.RULES, "when": attitude.WHEN,
            "optional": prep["optional"], "optional_packs": OPTIONAL}


def save(remix, campaign, scenario, raw, req):
    """Save the GM's levels and this map's prep after every check; a stale revision is refused (another window)."""
    import remix_service
    levels, sc = req.get("levels") or {}, req.get("prep") or {}
    opt = req.get("optional")
    if opt is not None and (not isinstance(opt, dict) or any(k not in OPTIONAL or not isinstance(v, bool) for k, v in opt.items())):
        raise ValueError("Optional rules are on or off: %s." % ", ".join(sorted(OPTIONAL)))
    if not isinstance(levels, dict) or not isinstance(sc, dict) or not isinstance(sc.get("groups") or {}, dict):
        raise ValueError("Prep is the levels' defaults and this map's encounter and groups.")
    clean = {"groups": {}}
    if sc.get("attitude"):
        clean["attitude"] = sc["attitude"]
    for k, g in (sc.get("groups") or {}).items():
        if not isinstance(g, dict):
            raise ValueError("Each group is an attitude and a morale rule.")
        e = {}
        if g.get("attitude"):
            e["attitude"] = g["attitude"]
        m = g.get("morale")
        if isinstance(m, dict) and m.get("rule", "fight") != "fight":
            e["morale"] = {"rule": m.get("rule"), "when": list(m.get("when") or [])}
            if "leader" in e["morale"]["when"]:
                e["morale"]["leader"] = m.get("leader")
        if e:
            clean["groups"][k] = e
    levels = {str(k): v for k, v in levels.items() if v}
    ready, rows = attitude.check_prep({"levels": levels, "scenario": clean}, set(kinds(raw)))
    if not ready:
        raise ValueError(attitude.rq.first_why(rows))
    with remix.lock:
        st = remix._campaign(campaign)
        if type(req.get("revision")) is not int or req["revision"] != st["revision"]:
            raise remix_service.Conflict("Campaign changed in another window; refresh before saving.")
        p = _prep(st)
        p["levels"] = levels
        if opt is not None:
            p["optional"] = {k: True for k, v in opt.items() if v}
        if clean.get("attitude") or clean["groups"]:
            p["scenarios"][scenario] = clean
        else:
            p["scenarios"].pop(scenario, None)
        st["prep"] = p
        st["revision"] += 1
        remix._write(st)
    return {"saved": True, "message": "Attitudes and morale saved with the campaign for the next fight on this map."}
