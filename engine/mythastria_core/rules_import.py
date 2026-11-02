"""v0.7.47 offline rules importer (RULES-CACHE-01 Stage A). Stdlib only.

Imports ONLY the sources listed in rules_sources.json (reviewed declarations: file, module name, edition, export
policy, licence). Reads the module zip members in place, never extracts files, never opens vault .dat files.
A failed import changes nothing; an unchanged source (same file hash, same importer version) is a no-op.

  py mythastria_core/rules_import.py              import / refresh every configured source
  py mythastria_core/rules_import.py --force      re-hash and re-import even when size/mtime are unchanged
"""
import argparse, hashlib, json, os, re, sys, time, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rules_cache

CONFIG = Path(__file__).resolve().parent / "rules_sources.json"
FG_DIR = Path(os.environ.get("APPDATA", "")) / "SmiteWorks" / "Fantasy Grounds"   # FG's own data (modules)
LIMITS = {"archive_bytes": 64 * 2**20, "member_bytes": 48 * 2**20, "compression_ratio": 200,
          "xml_depth": 64, "records": 20000, "record_text_chars": 200000}


class SourceError(Exception):
    pass


def fg_dir():
    return Path(os.environ.get("MYTHASTRIA_FG_DIR") or FG_DIR)


def load_config(path=None):
    data = json.loads(Path(path or CONFIG).read_text(encoding="utf-8"))
    out = []
    for s in data.get("sources", []):
        if s.get("kind") != "offline_srd":
            continue
        if not re.fullmatch(r"[a-z0-9-]{3,40}", s.get("source_id", "")):
            raise SourceError("bad source_id in config: %r" % s.get("source_id"))
        if ".." in s.get("file", "") or not s.get("file", "").lower().endswith(".mod"):
            raise SourceError("config file must be a .mod under the FG folder: %r" % s.get("file"))
        out.append(s)
    return out


# ------------------------------------------------------------------------------------------- XML helpers

def _check_depth(el, depth=1):
    if depth > LIMITS["xml_depth"]:
        raise SourceError("XML nesting deeper than %d" % LIMITS["xml_depth"])
    for c in el:
        _check_depth(c, depth + 1)


def readable(el):
    """Readable text of a formattedtext element: paragraphs and headings separated by blank lines, list items
    as '- item', table rows as cells joined by ' | '."""
    parts = []
    for c in el:
        if c.tag in ("p", "h", "frame", "frameid"):
            t = " ".join("".join(c.itertext()).split())
            if t: parts.append(t)
        elif c.tag == "list":
            parts.append("\n".join("- " + " ".join("".join(li.itertext()).split()) for li in c.iter("li")))
        elif c.tag == "table":
            rows = [" | ".join(" ".join("".join(td.itertext()).split()) for td in tr) for tr in c.iter("tr")]
            parts.append("\n".join(r for r in rows if r.strip()))
        else:
            t = " ".join("".join(c.itertext()).split())
            if t: parts.append(t)
    return "\n\n".join(parts)


def raw(elements):
    return "".join(ET.tostring(e, encoding="unicode") for e in elements)


def typed(el):
    """Element -> typed JSON, keeping child order: number, string, formattedtext {raw, text}, windowreference
    {class, recordname}, dice; untyped containers become ordered objects."""
    t = el.get("type")
    if t == "number":
        s = (el.text or "").strip()
        try: return int(s)
        except ValueError:
            try: return float(s)
            except ValueError: return {"type": "number", "invalid": s}
    if t in ("string", "dice", "token"):
        return el.text or ""
    if t == "formattedtext":
        return {"type": "formattedtext", "raw": raw(list(el)), "text": readable(el)}
    if t == "windowreference":
        return {"type": "windowreference", "class": el.findtext("class") or "", "recordname": el.findtext("recordname") or ""}
    if len(el):
        return {c.tag: typed(c) for c in el}
    if t:
        return {"type": t, "value": el.text or ""}
    return el.text or ""


# ------------------------------------------------------------------------------------------- extraction

def _records_under(node, prefix, loc):
    """Yield (tag, element, xml_location) for records below a root, through category wrappers."""
    for c in node:
        if c.tag == "category":
            yield from _records_under(c, prefix, loc + "/category[%s]" % (c.get("name") or ""))
        elif c.find("name") is not None:
            yield c.tag, c, loc + "/" + c.tag


def _edition(record_version, declared, issues, where):
    v = (record_version or "").strip()
    if v:
        if declared and v != declared:
            issues.append("%s: record edition %s differs from the source declaration %s" % (where, v, declared))
        return v, "record version tag"
    if declared:
        return declared, "reviewed source declaration (record has no version tag)"
    return "unknown", "no version tag and no source declaration"


def _order(value):
    try: return float(value)
    except (TypeError, ValueError): return 0.0


def page_sections(page_name, texts):
    """Split a page's formattedtext blocks (in order) into sections at each <h>: [{"heading", "els"}].
    Shared by the offline importer and the FG runtime reader (v0.7.48)."""
    sections, current = [], {"heading": page_name, "els": []}
    for txt in texts:
        for c in txt:
            if c.tag == "h":
                if current["els"]:
                    sections.append(current)
                current = {"heading": " ".join("".join(c.itertext()).split()) or page_name, "els": [c]}
            else:
                current["els"].append(c)
    if current["els"]:
        sections.append(current)
    return sections


def section_record(page_name, page_path, n, sec, edition, reason, index_path=None, xml_location=None):
    holder = ET.Element("text"); holder.extend(sec["els"])
    title = page_name if sec["heading"] == page_name else page_name + " > " + sec["heading"]
    return {"record_type": "rule", "fg_path": "%s#%d" % (page_path, n), "xml_location": xml_location,
            "edition": edition, "edition_reason": reason, "name": sec["heading"], "title_path": title,
            "fields": {"page": page_name, "heading": sec["heading"], "section": n, "index_path": index_path or []},
            "raw_text": raw(sec["els"]), "readable_text": readable(holder)}


def load_runtime(path=None):
    """v0.7.48: reviewed FG-runtime sources (purchased books read through FG): always local_only."""
    data = json.loads(Path(path or CONFIG).read_text(encoding="utf-8"))
    out = {}
    for s in data.get("sources", []):
        if s.get("kind") == "fg_runtime" and re.fullmatch(r"[A-Za-z0-9_ .-]{1,60}", s.get("module", "")):
            out[s["module"]] = dict(s, policy="local_only")
    return out


def extract(root, module, declared, issues):
    records, paths = [], set()

    def add(r):
        if r["fg_path"] in paths:
            issues.append("duplicate FG path skipped: " + r["fg_path"]); return
        paths.add(r["fg_path"])
        text = (r.get("readable_text") or "") + (r.get("raw_text") or "")
        if len(text) > LIMITS["record_text_chars"]:
            r.update(status="too_large", readable_text=None, raw_text=None)
        records.append(r)
        if len(records) > LIMITS["records"]:
            raise SourceError("more than %d records" % LIMITS["records"])

    for root_path, fg_root in (("spell", "spell"), ("reference/spelldata", "reference.spelldata")):
        node = root.find(root_path)
        if node is None:
            continue
        for tag, el, loc in _records_under(node, fg_root, root_path):
            fields = typed(el)
            desc = el.find("description")
            ed, why = _edition(el.findtext("version"), declared, issues, fg_root + "." + tag)
            add({"record_type": "spell", "fg_path": "%s.%s@%s" % (fg_root, tag, module), "xml_location": loc,
                 "edition": ed, "edition_reason": why, "name": el.findtext("name") or tag, "title_path": None,
                 "fields": fields, "raw_text": raw(list(desc)) if desc is not None else None,
                 "readable_text": readable(desc) if desc is not None else ""})

    ref = root.find("reference")
    data = ref.find("refmanualdata") if ref is not None else None
    if data is not None:
        hierarchy = {}
        for ch in ref.findall("refmanualindex/chapters/*"):
            for sub in ch.findall("subchapters/*"):
                for page in sub.findall("refpages/*"):
                    rec = page.findtext("listlink/recordname") or ""
                    hierarchy[rec] = [ch.findtext("name") or "", sub.findtext("name") or "", page.findtext("name") or ""]
        for page in data:
            page_name = page.findtext("name") or page.tag
            index_path = hierarchy.get("reference.refmanualdata." + page.tag, [])
            blocks = sorted(page.findall("blocks/*"), key=lambda b: float(b.findtext("order") or 0))
            sections = page_sections(page_name, [b.find("text") for b in blocks if b.find("text") is not None])
            for n, sec in enumerate(sections, 1):
                ed, why = _edition(None, declared, issues, "reference")
                add(section_record(page_name, "reference.refmanualdata.%s@%s" % (page.tag, module), n, sec, ed, why,
                                   index_path, "reference/refmanualdata/%s" % page.tag))
    return records


def attribution(root):
    """The licence attribution statement exactly as the module's Legal Information page gives it."""
    for page in root.findall("reference/refmanualdata/*"):
        text = " ".join("".join(page.itertext()).split())
        m = re.search(r"This work includes material from the System Reference Document.*?legalcode\.", text)
        if m:
            return m.group(0)
    return None


# ------------------------------------------------------------------------------------------- import

def import_source(cfg, force=False, db=None):
    """Import one configured source. Returns {"status": "ok"|"unchanged"|"error", ...}; on error the cache is
    left exactly as it was."""
    sid = cfg["source_id"]
    path = fg_dir() / cfg["file"]
    try:
        if not path.is_file():
            raise SourceError("file not found: " + cfg["file"])
        st = path.stat()
        if st.st_size > LIMITS["archive_bytes"]:
            raise SourceError("archive larger than %d bytes" % LIMITS["archive_bytes"])
        old = rules_cache.source_row(sid, db)
        if (old and not force and old["file_size"] == st.st_size and old["file_mtime"] == st.st_mtime
                and old["importer_version"] == rules_cache.IMPORTER_VERSION):
            rules_cache.touch_source(sid, db, checked_at=time.time(), available=1)
            return {"status": "unchanged", "source_id": sid}
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if old and old["fingerprint"] == digest and old["importer_version"] == rules_cache.IMPORTER_VERSION:
            rules_cache.touch_source(sid, db, checked_at=time.time(), available=1,
                                     file_size=st.st_size, file_mtime=st.st_mtime)
            return {"status": "unchanged", "source_id": sid}
        try:
            z = zipfile.ZipFile(path)
        except zipfile.BadZipFile:
            raise SourceError("not a readable module archive (encrypted or damaged)")
        with z:
            members = {i.filename: i for i in z.infolist()}
            member = cfg.get("member") or ("client.xml" if "client.xml" in members else "db.xml")
            info = members.get(member)
            if info is None or "definition.xml" not in members:
                raise SourceError("module member missing: " + member)
            for i in (info, members["definition.xml"]):
                if i.file_size > LIMITS["member_bytes"]:
                    raise SourceError("member %s larger than %d bytes" % (i.filename, LIMITS["member_bytes"]))
                if i.compress_size and i.file_size / i.compress_size > LIMITS["compression_ratio"]:
                    raise SourceError("member %s compression ratio too high" % i.filename)
            blobs = {m: z.read(m) for m in (member, "definition.xml")}
        for m, b in blobs.items():
            if re.search(rb"<!(DOCTYPE|ENTITY)", b, re.I):
                raise SourceError("DTD/entity declarations are refused (%s)" % m)
        definition = ET.fromstring(blobs["definition.xml"])
        module = definition.findtext("name") or ""
        if module != cfg["module"]:
            raise SourceError("module name %r does not match the reviewed config %r" % (module, cfg["module"]))
        root = ET.fromstring(blobs[member])
        _check_depth(root)
        issues = []
        records = extract(root, module, cfg.get("declared_edition"), issues)
        policy = cfg.get("policy") if cfg.get("policy") in ("cloud_allowed", "local_only") else "local_only"
        attr = attribution(root)
        if policy == "cloud_allowed" and not attr:
            policy = "local_only"
            issues.append("no attribution statement found in the module: export policy lowered to local_only")
        source = {"source_id": sid, "module": module, "display_name": definition.findtext("displayname") or module,
                  "kind": "offline_srd", "declared_edition": cfg.get("declared_edition"), "policy": policy,
                  "attribution": attr, "license": cfg.get("license"), "fingerprint": digest, "file_size": st.st_size,
                  "file_mtime": st.st_mtime, "importer_version": rules_cache.IMPORTER_VERSION,
                  "issues": json.dumps(issues[:200], ensure_ascii=False)}
        counts = rules_cache.apply_import(source, records, db)
        return {"status": "ok", "source_id": sid, "records": len(records), "issues": len(issues), **counts}
    except (SourceError, ET.ParseError, OSError) as error:
        return {"status": "error", "source_id": sid, "error": str(error)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--source")
    a = ap.parse_args()
    for cfg in load_config():
        if a.source and cfg["source_id"] != a.source:
            continue
        print(json.dumps(import_source(cfg, a.force)))


if __name__ == "__main__":
    main()
