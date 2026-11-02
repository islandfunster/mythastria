"""v0.7.47 rules cache (RULES-CACHE-01, design: Rules_Cache_Pilot_v0.7.46.md by the AI assistant).

Durable SQLite store for rules evidence: sources, records, immutable revisions, parser evidence and
interpretations (the last two are schema only in this increment). Python stdlib only.

Rules kept here:
- Record identity = source + record type + logical path + edition (never the name alone); opaque stable ids.
- Revisions are immutable; a content change makes a new revision, a missing record becomes unavailable.
- Lookups default to edition 2024 and never fall back silently to another edition.
- Export policy is per source ("cloud_allowed" or "local_only"); unknown is local only. The cloud projection
  never shows local-only content, not even titles.
- One connection per call (HTTP threads never share one); writes are serialised by a module lock."""
import hashlib, json, os, re, sqlite3, threading, time, unicodedata
from pathlib import Path

import rules_overlay   # v0.7.94: SRD corrections on read projections only

SCHEMA_VERSION = 1
IMPORTER_VERSION = "rules-import-1"
DEFAULT_DB = Path(__file__).resolve().parent / "cache" / "rules_cache.sqlite"
STATUSES = ("ok", "ambiguous", "miss", "stale", "incomplete", "too_large", "unavailable")
MAX_QUERY = 120
MAX_LIMIT = 20
MAX_TEXT_OUT = 20000       # characters of readable text in one answer
_write_lock = threading.Lock()


def db_path():
    return Path(os.environ.get("MYTHASTRIA_RULES_DB") or DEFAULT_DB)


def connect(path=None):
    p = Path(path or db_path())
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p), timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    _ensure_schema(con)
    return con


def _ensure_schema(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS sources (
        source_id TEXT PRIMARY KEY, module TEXT NOT NULL, display_name TEXT NOT NULL,
        kind TEXT NOT NULL CHECK (kind IN ('offline_srd','fg_runtime')),
        declared_edition TEXT, policy TEXT NOT NULL CHECK (policy IN ('cloud_allowed','local_only')),
        attribution TEXT, license TEXT, fingerprint TEXT, file_size INTEGER, file_mtime REAL,
        importer_version TEXT, imported_at REAL, checked_at REAL, available INTEGER NOT NULL DEFAULT 1,
        issues TEXT NOT NULL DEFAULT '[]');
    CREATE TABLE IF NOT EXISTS records (
        record_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(source_id),
        record_type TEXT NOT NULL, fg_path TEXT NOT NULL, xml_location TEXT, edition TEXT NOT NULL,
        edition_reason TEXT NOT NULL, name TEXT NOT NULL, norm_name TEXT NOT NULL, title_path TEXT,
        current_revision TEXT, available INTEGER NOT NULL DEFAULT 1,
        UNIQUE (source_id, record_type, fg_path, edition));
    CREATE TABLE IF NOT EXISTS revisions (
        revision_id TEXT PRIMARY KEY, record_id TEXT NOT NULL REFERENCES records(record_id),
        content_hash TEXT NOT NULL, extraction_version TEXT NOT NULL, raw_text TEXT, readable_text TEXT,
        fields_json TEXT NOT NULL, captured_at REAL NOT NULL, status TEXT NOT NULL DEFAULT 'complete');
    CREATE TABLE IF NOT EXISTS parser_evidence (
        evidence_id TEXT PRIMARY KEY, record_id TEXT REFERENCES records(record_id),
        revision_id TEXT REFERENCES revisions(revision_id), signature TEXT NOT NULL, output_json TEXT NOT NULL,
        policy TEXT NOT NULL DEFAULT 'local_only', ct_power_path TEXT, use_label TEXT, base_name TEXT,
        gave TEXT, fingerprints TEXT, captured_at REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS interpretations (
        interpretation_id TEXT PRIMARY KEY, claim TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('provisional','verified','needs_review')),
        supporting_ids TEXT NOT NULL DEFAULT '[]', verifier TEXT, exceptions TEXT, dependency_ids TEXT,
        updated_at REAL NOT NULL);
    CREATE INDEX IF NOT EXISTS records_lookup ON records (record_type, edition, norm_name);
    """)
    row = con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    if row is None:
        con.execute("INSERT INTO meta (key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
        con.commit()
    elif int(row["value"]) != SCHEMA_VERSION:
        raise RuntimeError("rules cache schema %s, expected %s" % (row["value"], SCHEMA_VERSION))


def normalize(text):
    """Search key: Unicode casefold + single spaces. The original text is kept separately."""
    return " ".join(unicodedata.normalize("NFKC", str(text or "")).casefold().split())


def stable_id(*parts):
    return hashlib.sha256("\x1f".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:24]


def content_hash(fields, raw_text, readable_text):
    blob = json.dumps({"f": fields, "r": raw_text or "", "t": readable_text or ""}, sort_keys=True,
                      ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------------------------- writes

def apply_import(source, records, path=None, now=None, partial=False):
    """Commit one complete, already validated source import in a single transaction.
    source: dict of sources columns. records: list of dicts with record_type, fg_path, xml_location, edition,
    edition_reason, name, title_path, fields, raw_text, readable_text, status. Records of this source that are
    absent become unavailable; their revisions stay. partial=True (one runtime record read through FG) leaves the
    source's other records alone. Returns counts."""
    now = now or time.time()
    counts = {"new": 0, "changed": 0, "unchanged": 0, "removed": 0}
    with _write_lock:
        con = connect(path)
        try:
            con.execute("BEGIN IMMEDIATE")
            cols = ("source_id", "module", "display_name", "kind", "declared_edition", "policy", "attribution",
                    "license", "fingerprint", "file_size", "file_mtime", "importer_version", "issues")
            vals = [source.get(c) for c in cols]
            con.execute("INSERT INTO sources (%s, imported_at, checked_at, available) VALUES (%s, ?, ?, 1) "
                        "ON CONFLICT(source_id) DO UPDATE SET %s, imported_at=excluded.imported_at, "
                        "checked_at=excluded.checked_at, available=1"
                        % (", ".join(cols), ", ".join("?" * len(cols)),
                           ", ".join("%s=excluded.%s" % (c, c) for c in cols if c != "source_id")),
                        vals + [now, now])
            seen = set()
            for r in records:
                rid = stable_id(source["source_id"], r["record_type"], r["fg_path"], r["edition"])
                seen.add(rid)
                h = content_hash(r["fields"], r.get("raw_text"), r.get("readable_text"))
                row = con.execute("SELECT r.current_revision, v.content_hash, v.extraction_version FROM records r "
                                  "LEFT JOIN revisions v ON v.revision_id=r.current_revision WHERE r.record_id=?",
                                  (rid,)).fetchone()
                con.execute("INSERT INTO records (record_id, source_id, record_type, fg_path, xml_location, edition, "
                            "edition_reason, name, norm_name, title_path, available) VALUES (?,?,?,?,?,?,?,?,?,?,1) "
                            "ON CONFLICT(record_id) DO UPDATE SET xml_location=excluded.xml_location, "
                            "edition_reason=excluded.edition_reason, name=excluded.name, norm_name=excluded.norm_name, "
                            "title_path=excluded.title_path, available=1",
                            (rid, source["source_id"], r["record_type"], r["fg_path"], r.get("xml_location"),
                             r["edition"], r["edition_reason"], r["name"], normalize(r["name"]), r.get("title_path")))
                if row and row["content_hash"] == h and row["extraction_version"] == source["importer_version"]:
                    counts["unchanged"] += 1
                    continue
                rev = stable_id(rid, h, source["importer_version"])
                con.execute("INSERT OR IGNORE INTO revisions (revision_id, record_id, content_hash, extraction_version, "
                            "raw_text, readable_text, fields_json, captured_at, status) VALUES (?,?,?,?,?,?,?,?,?)",
                            (rev, rid, h, source["importer_version"], r.get("raw_text"), r.get("readable_text"),
                             json.dumps(r["fields"], ensure_ascii=False), now, r.get("status", "complete")))
                con.execute("UPDATE records SET current_revision=? WHERE record_id=?", (rev, rid))
                counts["changed" if row else "new"] += 1
            for row in ([] if partial else con.execute("SELECT record_id FROM records WHERE source_id=? AND available=1",
                                                       (source["source_id"],)).fetchall()):
                if row["record_id"] not in seen:
                    con.execute("UPDATE records SET available=0 WHERE record_id=?", (row["record_id"],))
                    counts["removed"] += 1
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        finally:
            con.close()
    return counts


def mark_missing(source_id, record_type, seen_ids, path=None):
    """v0.7.48: after a COMPLETE runtime scan of one record type, records of that type the scan did not see become
    unavailable (their revisions stay). Returns how many."""
    with _write_lock:
        con = connect(path)
        try:
            rows = con.execute("SELECT record_id FROM records WHERE source_id=? AND record_type=? AND available=1",
                               (source_id, record_type)).fetchall()
            gone = [r["record_id"] for r in rows if r["record_id"] not in seen_ids]
            con.executemany("UPDATE records SET available=0 WHERE record_id=?", [(g,) for g in gone])
            con.commit()
            return len(gone)
        finally:
            con.close()


def source_row(source_id, path=None):
    con = connect(path)
    try:
        row = con.execute("SELECT * FROM sources WHERE source_id=?", (source_id,)).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def touch_source(source_id, path=None, **updates):
    allowed = {"checked_at", "available", "file_size", "file_mtime"}
    sets = {k: v for k, v in updates.items() if k in allowed}
    if not sets:
        return
    with _write_lock:
        con = connect(path)
        try:
            con.execute("UPDATE sources SET %s WHERE source_id=?" % ", ".join("%s=?" % k for k in sets),
                        list(sets.values()) + [source_id])
            con.commit()
        finally:
            con.close()


# ---------------------------------------------------------------------------------------------- reads

def _citation(row):
    return "%s — %s — %s — %s; revision %s" % (row["display_name"], row["title_path"] or row["name"], row["edition"],
                                                row["fg_path"], (row["content_hash"] or "")[:10])


def _project(row, with_body):
    out = {"record_id": row["record_id"], "name": row["name"], "record_type": row["record_type"],
           "edition": row["edition"], "edition_reason": row["edition_reason"], "title": row["title_path"] or row["name"],
           "fg_path": row["fg_path"], "source_id": row["source_id"], "source": row["display_name"],
           "policy": row["policy"], "attribution": row["attribution"], "revision_id": row["current_revision"],
           "revision_hash": (row["content_hash"] or "")[:16], "freshness": row["freshness"],
           "evidence_kind": "source_text", "citation": _citation(row)}
    if with_body:
        text = row["readable_text"] or ""
        out["text"] = text[:MAX_TEXT_OUT]
        out["text_truncated"] = len(text) > MAX_TEXT_OUT
        out["fields"] = json.loads(row["fields_json"] or "{}")
        out = rules_overlay.apply(out)
    return out


_SELECT = """SELECT r.*, s.display_name, s.policy, s.attribution, s.available AS source_available,
             s.fingerprint, v.content_hash, v.readable_text, v.fields_json, v.status AS revision_status,
             CASE WHEN s.available=1 THEN 'current' ELSE 'source_unavailable' END AS freshness
             FROM records r JOIN sources s ON s.source_id=r.source_id
             LEFT JOIN revisions v ON v.revision_id=r.current_revision"""


def _allowed(audience):
    return ("cloud_allowed",) if audience == "cloud" else ("cloud_allowed", "local_only")


def lookup(query, record_type, edition="2024", audience="local", limit=5, source_id=None, path=None):
    """Find records by name. Returns {"status", "edition", "results", ...}. Never falls back to another edition."""
    q = normalize(query)
    if not q or len(q) > MAX_QUERY:
        return {"status": "miss", "edition": edition, "results": [], "error": "query must be 1..%d characters" % MAX_QUERY}
    if record_type not in ("spell", "rule", "npc"):   # npc: v0.7.49 (paid bestiary stat blocks)
        return {"status": "miss", "edition": edition, "results": [], "error": "unknown record type"}
    limit = max(1, min(int(limit or 5), MAX_LIMIT))
    pol = _allowed(audience)
    where = ("r.record_type=? AND r.edition=? AND r.available=1 AND s.policy IN (%s)" % ",".join("?" * len(pol)))
    args = [record_type, str(edition)] + list(pol)
    if source_id:
        where += " AND r.source_id=?"; args.append(source_id)
    con = connect(path)
    try:
        exact = con.execute(_SELECT + " WHERE " + where + " AND r.norm_name=? LIMIT ?", args + [q, MAX_LIMIT + 1]).fetchall()
        if len(exact) > 1:
            return {"status": "ambiguous", "edition": edition, "results": [_project(r, False) for r in exact[:limit]]}
        if len(exact) == 1:
            return _single(exact[0], edition)
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        rows = con.execute(_SELECT + " WHERE " + where + " AND (r.norm_name LIKE ? ESCAPE '\\' OR "
                           "lower(r.title_path) LIKE ? ESCAPE '\\') ORDER BY length(r.name) LIMIT ?",
                           args + [like, like, limit]).fetchall()
        if not rows:
            return {"status": "miss", "edition": edition, "results": []}
        if len(rows) == 1:
            return _single(rows[0], edition)
        return {"status": "ambiguous", "edition": edition, "results": [_project(r, False) for r in rows]}
    finally:
        con.close()


def _single(row, edition):
    status = "ok"
    if row["revision_status"] == "too_large":
        status = "too_large"
    elif row["revision_status"] != "complete":
        status = "incomplete"
    elif not row["source_available"]:
        status = "stale"
    return {"status": status, "edition": edition, "results": [_project(row, status == "ok")]}


def get_record(record_id, audience="local", path=None):
    if not re.fullmatch(r"[0-9a-f]{24}", str(record_id or "")):
        return {"status": "miss", "results": [], "error": "bad record id"}
    pol = _allowed(audience)
    con = connect(path)
    try:
        row = con.execute(_SELECT + " WHERE r.record_id=? AND s.policy IN (%s)" % ",".join("?" * len(pol)),
                          [record_id] + list(pol)).fetchone()
    finally:
        con.close()
    if row is None:
        return {"status": "miss", "results": []}
    if not row["available"]:
        return {"status": "unavailable", "results": [_project(row, False)]}
    return _single(row, row["edition"])


def export(query, record_type, edition="2024", limit=5, path=None):
    """Cloud-safe projection: only cloud_allowed sources, always; callers cannot relax it."""
    return lookup(query, record_type, edition, "cloud", limit, None, path)
