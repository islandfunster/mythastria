"""Overlay for imported SRD records, where the SRD disagrees with itself.

The imported revision remains immutable.  This module adds small, attributable semantic
corrections to the read projection.  Every correction comes from the SRD 5.2.1 itself.
"""
import copy
import json
from functools import lru_cache
from pathlib import Path

OVERLAY_FILE = Path(__file__).with_name("official_rules_overlay.json")


@lru_cache(maxsize=1)
def load():
    with OVERLAY_FILE.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("schema_version") != 1:
        raise RuntimeError("unsupported official rules overlay schema")
    return data


def baseline():
    """Return a copy so callers cannot mutate the cached configuration."""
    return copy.deepcopy(load()["baseline"])


def _matches(correction, record):
    match = correction.get("match") or {}
    return (record.get("source_id") in match.get("source_ids", [])
            and record.get("record_type") == match.get("record_type")
            and " ".join(str(record.get("name") or "").casefold().split())
            in match.get("normalized_names", []))


def apply(record):
    """Apply corrections to a projected record without changing cached source text."""
    hits = [c for c in load().get("corrections", []) if _matches(c, record)]
    if not hits:
        return record
    out = copy.deepcopy(record)
    fields = out.setdefault("fields", {})
    for correction in hits:
        fields.update(correction.get("set_fields") or {})
    out["corrections"] = [{k: copy.deepcopy(c[k]) for k in ("id", "facts", "note", "source") if k in c}
                          for c in hits]
    out["rules_baseline"] = baseline()["label"]
    return out
