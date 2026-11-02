"""PLAYER-PACKAGE-01 (docs: player-client/README.md): the player client's own file list, and the hosted player site.

Walks the code the player pages load (static and dynamic imports, script and stylesheet links, fetches) from ../dist,
never into the GM's own modules (GM_ONLY), and writes files.json beside this script. The players' door
(Mythastria tools/sim_service.py) serves a page, script or stylesheet only when it is on that list. Run it after changing which modules the player pages load:

    py isles-table\\player-client\\build_player_client.py

--check: fail (exit 1) when files.json is out of date, instead of writing it.

PLAYER-SITE-01 (GM 2026-10-28: the player client is a hosted HTML site):
    --site FOLDER --server https://play.example.com
writes the hosted player site into FOLDER (emptied first): the player pages with the GM's address in each, the scripts,
stylesheets and pictures they load, and index.html opening the join page. Publish FOLDER as it is (Cloudflare Pages), and start Mythastria with
--players-site <the site's address> so the players' door answers it.
"""
import json, re, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIST = HERE.parent / "dist"
OUT = HERE / "files.json"
# the pages a player opens through the players' door (tools/sim_service.py PLAYER_PAGES)
ENTRIES = ["join.html", "play.html", "stage.html", "rules-social.html", "donate.html"]
# the GM's own modules: Remix, the director, the map picker, the Players dialog, the GM swap. A player
# page may load one only with a dynamic import() on the GM console; a static import of one fails the build.
GM_ONLY = {"remix-panel.mjs", "director-ui.mjs", "map-picker.mjs", "seats-ui.mjs",
           "dm-swap-ui.mjs",   # GM 2026-10-28: no Ask to be the GM on the player client
           "rules-monitor-ui.mjs"}   # RULES-MONITOR-01: the GM console only
CODE = (".html", ".mjs", ".js", ".css")
EXT = r"(?:mjs|js|css|json|wasm|png|svg|webp|jpg|woff2?)"
REF = re.compile(r"""(?P<how>\bfrom\s*|\bimport\s*\(\s*|\bimport\s+|\bsrc=|\bhref=|new URL\(\s*|\bfetch\w*\(\s*|url\(\s*)"""
                 r"""["']?(?:\./)?(?P<path>[\w./-]+\.""" + EXT + r""")["')]""")


def walk(entries=ENTRIES):
    """Every file the player pages reach (code and pictures), and any static import of a GM_ONLY module (a mistake)."""
    seen, bad, todo = set(), [], list(entries)
    while todo:
        f = todo.pop()
        if f in seen or not (DIST / f).is_file():
            continue
        seen.add(f)
        if not f.endswith(CODE):
            continue
        base = Path(f).parent
        for m in REF.finditer((DIST / f).read_text(encoding="utf-8", errors="ignore")):
            ref = (base / m["path"]).as_posix()
            if ref in GM_ONLY:
                if not m["how"].lstrip().startswith("import") or "(" not in m["how"]:
                    bad.append("%s loads %s without a dynamic import()" % (f, ref))
                continue
            todo.append(ref)
    return seen, bad


def site(folder, server):
    """PLAYER-SITE-01: the hosted player site, with `server` (the players' door's public address) in every page."""
    if not re.fullmatch(r"https?://[\w.-]+(?::\d+)?", server.rstrip("/")):
        raise SystemExit("--server is the players' door's address, such as https://play.example.com")
    folder = Path(folder).resolve()
    if folder == DIST.resolve() or DIST.resolve() in folder.parents:
        raise SystemExit("--site must be a folder outside dist")
    seen, bad = walk()
    if bad:
        raise SystemExit("The player package would carry GM tools:\n  " + "\n  ".join(bad))
    if folder.exists():
        shutil.rmtree(folder)
    meta = '<meta name="mythastria-server" content="%s">' % server.rstrip("/")
    for f in sorted(seen):
        out = folder / f
        out.parent.mkdir(parents=True, exist_ok=True)
        if f.endswith(".html"):
            html = (DIST / f).read_text(encoding="utf-8")
            assert "<head>" in html, f
            out.write_text(html.replace("<head>", "<head>" + meta, 1), encoding="utf-8", newline="\n")
        else:
            shutil.copyfile(DIST / f, out)
    (folder / "index.html").write_text('<!doctype html><meta charset="utf-8"><title>Mythastria</title>'
                                       '<meta http-equiv="refresh" content="0; url=join.html"><a href="join.html">Join the table</a>\n',
                                       encoding="utf-8", newline="\n")
    print("Hosted player site: %d files -> %s (the GM's Mythastria at %s)" % (len(seen) + 1, folder, server))


def main(argv):
    if "--site" in argv:
        try:
            folder, server = argv[argv.index("--site") + 1], argv[argv.index("--server") + 1]
        except (ValueError, IndexError):
            print("--site FOLDER needs --server https://<the players' door>")
            return 1
        site(folder, server)
        return 0
    seen, bad = walk()
    if bad:
        print("The player package would carry GM tools:\n  " + "\n  ".join(bad))
        return 1
    files = sorted(x for x in seen if x.endswith(CODE))
    data = {"about": "PLAYER-PACKAGE-01: the pages, scripts and stylesheets the players' door serves "
                     "(written by build_player_client.py; do not edit)", "entries": ENTRIES, "gm_only": sorted(GM_ONLY),
            "files": files}
    text = json.dumps(data, indent=1) + "\n"
    if "--check" in argv:
        same = OUT.is_file() and OUT.read_text(encoding="utf-8") == text
        print("files.json is up to date" if same else "files.json is out of date: run build_player_client.py")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print("Player package: %d pages, scripts and stylesheets -> %s" % (len(files), OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
