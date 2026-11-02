"""v0.7.72 KNOWLEDGE-01: game knowledge for the local model's NPC decisions (user: "so ollama will have the resources it
needs"; step 1 after committing the AI assistant's work and the model resources).

Three references, each built locally and capped:
- creature_reference: the acting creature's own stat block as FG holds it in the Combat Tracker (traits, actions,
  reactions, legendary actions with their descriptions, from the parser probe), whatever module it came from.
- condition_reference: the 2024 definitions of the conditions active on the acting creature and its possible targets
  (rules cache: SRD 5.2.1).
- party_reference: the targeted player characters' class/level and feat names (synced sheets).
Book and module text goes only into the local Ollama prompt (ai_turn.messages), never into options, results, the page
or logs (the bridge logs names and counts only). Any problem gives an empty reference: knowledge never blocks a turn."""
import re

import rules_cache

MAX_ENTRY_CHARS = 280          # one trait/action description
MAX_CREATURE_CHARS = 2000      # the whole stat block
MAX_CONDITION_CHARS = 320      # one condition definition
MAX_CONDITIONS_TOTAL = 1400    # v0.8.6 AUDIT-05: all condition definitions together (each shortened to share it)
MIN_CONDITION_CHARS = 120
# v0.8.6 AUDIT-05 (the AI assistant SRD audit): each section has its own share of MAX_CREATURE_CHARS, filled in decision order;
# what is left over goes to the rest, and anything still left out is named under "omitted"
SECTION_SHARE = (("actions", 800), ("reactions", 400), ("legendary_actions", 400), ("traits", 400))
SECTIONS = (("ct.traits", "traits"), ("ct.actions", "actions"), ("ct.reactions", "reactions"),
            ("ct.legendaryactions", "legendary_actions"))
CONDITIONS = ("Blinded", "Charmed", "Deafened", "Exhaustion", "Frightened", "Grappled", "Incapacitated", "Invisible",
              "Paralyzed", "Petrified", "Poisoned", "Prone", "Restrained", "Stunned", "Unconscious")


def _short(text, limit):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = cut.rfind(". ")
    return cut[:end + 1] if end > limit // 3 else cut.rstrip() + "..."


def creature_reference(ranked, source):
    """{"traits": ["Name: text", ...], "actions": [...], ...} for the acting creature, CT copy first; {} if none.
    v0.8.6 AUDIT-05: sections share MAX_CREATURE_CHARS by SECTION_SHARE (actions first), so long traits no longer push
    out the actions, reactions or legendary actions; entries that do not fit are named under "omitted"."""
    seen, entries = set(), {key: [] for _, key in SECTIONS}
    rows = sorted((c for c in ranked if c.get("ctpath") == source and c.get("description")),
                  key=lambda c: (not (c.get("node_path") or "").startswith(source + "."), c.get("node_path") or ""))
    for origin, key in SECTIONS:
        for c in rows:
            name = (c.get("power_name") or "").strip()
            if c.get("origin") != origin or not name or (origin, name.lower()) in seen:
                continue
            seen.add((origin, name.lower()))
            entries[key].append((name, "%s: %s" % (name, _short(c["description"], MAX_ENTRY_CHARS))))
    kept, total = set(), 0
    for key, share in SECTION_SHARE:                      # pass 1: each section within its own share
        used = 0
        for i, (_, entry) in enumerate(entries[key]):
            if used + len(entry) <= share:
                kept.add((key, i)); used += len(entry)
        total += used
    for key, _ in SECTION_SHARE:                          # pass 2: what is left of the whole budget, in the same order
        for i, (_, entry) in enumerate(entries[key]):
            if (key, i) not in kept and total + len(entry) <= MAX_CREATURE_CHARS:
                kept.add((key, i)); total += len(entry)
    out, omitted = {}, []
    for _, key in SECTIONS:
        for i, (name, entry) in enumerate(entries[key]):
            if (key, i) in kept:
                out.setdefault(key, []).append(entry)
            else:
                omitted.append("%s (%s)" % (name, key.replace("_", " ")))
    if omitted:
        out["omitted"] = omitted
    return out


def _effect_on(e):
    return str(e.get("active", "1")).strip() != "0"


def conditions_in_play(combatants, paths):
    """Condition names (2024 list) in the active effects of these combatants: every one (v0.8.6 AUDIT-05: the first four
    only before), those of paths[0] (the acting creature) first, each group in the list's order."""
    out = []
    for p in paths:
        found = set()
        for e in (combatants.get(p) or {}).get("effects") or []:
            if not _effect_on(e):
                continue
            for part in str(e.get("label") or "").split(";"):
                word = part.strip().split(":")[0].strip().title()
                if word in CONDITIONS:
                    found.add(word)
        out += [c for c in CONDITIONS if c in found and c not in out]
    return out


def condition_reference(names, path=None):
    """{"Prone": "definition", ...} from the rules cache (SRD 5.2.1); missing ones left out.
    v0.8.6 AUDIT-05: all definitions share MAX_CONDITIONS_TOTAL (each at most MAX_CONDITION_CHARS)."""
    out = {}
    each = max(MIN_CONDITION_CHARS, min(MAX_CONDITION_CHARS, MAX_CONDITIONS_TOTAL // max(1, len(names))))
    for name in names:
        for source in ("srd521-player",):
            try:
                found = rules_cache.lookup(name + " [Condition]", "rule", source_id=source, path=path)
            except Exception:
                continue
            res = [r for r in found.get("results", []) if (r.get("title") or "").endswith(name + " [Condition]")]
            if not res:
                continue
            rec = res[0] if found["status"] == "ok" else rules_cache.get_record(res[0]["record_id"], path=path).get("results", [{}])[0]
            text = (rec or {}).get("text") or ""
            if text:
                out[name] = _short(text, each)
                break
    return out


def party_reference(combatants, sheets, target_paths):
    """{"PC name": "Class level[/...]; feats: A, B"} for the targeted player characters with a synced sheet."""
    out = {}
    for p in target_paths:
        c = combatants.get(p) or {}
        link = (c.get("actor_link") or {}).get("recordname") or ""
        raw = str((c.get("raw_fields") or {}).get("link") or "")
        sheet = sheets.get(link) or sheets.get(raw.split(":", 1)[1] if raw.startswith("charsheet:") else "")
        if not sheet:
            continue
        name = (sheet.get("core") or {}).get("name") or c.get("name") or ""
        classes = "/".join("%s %s" % (k.get("name", ""), k.get("level", "")) for k in (sheet.get("classes") or {}).values()
                           if k.get("name"))
        feats = sorted({f.get("name") for f in (sheet.get("feats") or {}).values() if f.get("name")})
        text = classes + ("; feats: " + ", ".join(feats[:8]) if feats else "")
        if name and text:
            out[name] = text
    return out


def gather(combatants, ranked, sheets, options, path=None):
    """All three references for the turn in `options`; empty ones are left out; {} on any problem."""
    try:
        source = options["source"]
        targets = sorted({t for c in options["choices"] for t in str(c.get("target") or "").split(",") if t})
        out = {}
        creature = creature_reference(ranked, source)
        if creature:
            out["creature_reference"] = creature
        conditions = condition_reference(conditions_in_play(combatants, [source] + targets), path)
        if conditions:
            out["condition_reference"] = conditions
        party = party_reference(combatants, sheets or {}, [t for t in targets if t != source])
        if party:
            out["party_reference"] = party
        return out
    except Exception:
        return {}


def summary(k):
    """Names and counts only, for the log."""
    parts = []
    cr = k.get("creature_reference") or {}
    if cr:
        parts.append("stat block (" + ", ".join("%d %s" % (len(v), key) for key, v in cr.items() if key != "omitted") +
                     (", %d omitted" % len(cr["omitted"]) if cr.get("omitted") else "") + ")")
    if k.get("condition_reference"):
        parts.append("conditions: " + ", ".join(k["condition_reference"]))
    if k.get("party_reference"):
        parts.append("party: " + ", ".join(k["party_reference"]))
    return "; ".join(parts)
