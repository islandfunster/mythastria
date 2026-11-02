"""v0.7.51: rules text for the local AI's spell choices, read from the rules cache.

For each spell among the turn's choices: the exact-name 2024 record, preferring the GM's purchased books
(local_only, read through FG) over the SRD. The text goes only to the local Ollama model in the prompt; it is never
put into options (served on the page's read routes), logs or snapshots. Any cache problem gives no notes."""
import re

import rules_cache

MAX_SPELLS = 6
MAX_CHARS = 420


def lookup_name(power_name):
    """FG power name -> spell name: "Bless (1/day)" -> "Bless", "Cure Wounds - 1st level (3 slots)" -> "Cure Wounds"."""
    name = re.sub(r"\s*\([^)]*\)\s*$", "", str(power_name or ""))
    return re.sub(r"\s+-\s+(cantrip|\d+(st|nd|rd|th) level)\b.*$", "", name, flags=re.I).strip()


def _header(fields):
    level = fields.get("level")
    parts = ["Cantrip" if str(level) == "0" else ("Level %s" % level if level not in (None, "") else "")]
    parts += [str(fields.get(k) or "").strip() for k in ("castingtime", "range", "duration")]
    return "; ".join(p for p in parts if p)


def _short(text, limit):
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = cut.rfind(". ")
    return cut[:end + 1] if end > limit // 3 else cut.rstrip() + "..."


def _best(name):
    found = rules_cache.lookup(name, "spell", edition="2024", audience="local", limit=rules_cache.MAX_LIMIT)
    exact = [r for r in found.get("results", []) if rules_cache.normalize(r["name"]) == rules_cache.normalize(name)]
    if not exact:
        return None
    exact.sort(key=lambda r: (r["policy"] != "local_only", r["source_id"]))   # purchased book first, then SRD
    rec = rules_cache.get_record(exact[0]["record_id"])
    if rec.get("status") != "ok":
        return None
    return rec["results"][0]


def spell_notes(choices):
    """[{"spell", "text", "source_id", "source"}] for up to MAX_SPELLS distinct spells; [] on any cache problem."""
    notes, seen = [], set()
    try:
        for c in choices:
            if not c.get("spell"):
                continue
            name = lookup_name(c.get("power_name"))
            key = rules_cache.normalize(name)
            if not name or key in seen:
                continue
            seen.add(key)
            rec = _best(name)
            if not rec:
                continue
            head = _header(rec.get("fields") or {})
            body = _short(rec.get("text", ""), MAX_CHARS - len(head) - 2)
            notes.append({"spell": name, "text": (head + ". " if head else "") + body,
                          "source_id": rec["source_id"], "source": rec["source"]})
            if len(notes) >= MAX_SPELLS:
                break
    except Exception:
        return []
    return notes
