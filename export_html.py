#!/usr/bin/env python3
"""Export a dashboard as one self-contained HTML file.

    python3 export_html.py                          # -> dist/dashboard.html
    python3 export_html.py --dashboard econ         # -> dist/econ.html
    python3 export_html.py --out ~/Desktop/dashboard.html

The stylesheet, the script and the current snapshot are all inlined, so the
result opens straight from disk, can be emailed, or dropped on any static host.
It is a point-in-time copy: rebuild it after each `fetch.py` run.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, "web")

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    'family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">'
)


#: Each dashboard: its page, its stylesheets, its script, its data file, and
#: the global the inlined payload is assigned to.
DASHBOARDS = {
    "stocks": {
        "html": "index.html",
        "css": ["styles.css"],
        "js": "app.js",
        "data": os.path.join("data", "snapshot.json"),
        "global": "__SNAPSHOT__",
        "out": "dashboard.html",
        "title": "Exchange Drop Monitor",
    },
    "careers": {
        "html": "careers.html",
        # styles.css owns the base tokens, econ.css the country hues.
        "css": ["styles.css", "econ.css", "careers.css"],
        "js": "careers.js",
        "data": os.path.join("data", "careers.json"),
        "global": "__CAREERS__",
        "out": "careers.html",
        "title": "Advice Career Pathways",
    },
    "econ": {
        "html": "econ.html",
        # styles.css owns the base tokens; econ.css layers the tracker on top.
        "css": ["styles.css", "econ.css"],
        "js": "econ.js",
        "data": os.path.join("data", "econ.json"),
        "global": "__ECON__",
        "out": "econ.html",
        "title": "Five-Market Economic Tracker",
    },
}


def body_of(html: str, script_name: str, page: str) -> str:
    """The markup between <body> and </body>, minus the script tag."""
    match = re.search(r"<body>(.*)</body>", html, re.S)
    if not match:
        raise SystemExit(f"web/{page} has no <body> - cannot export")
    body = match.group(1)
    pattern = r'\s*<script src="%s"></script>' % re.escape(script_name)
    return re.sub(pattern, "", body).strip()


def title_of(html: str, fallback: str) -> str:
    match = re.search(r"<title>(.*?)</title>", html, re.S)
    return match.group(1).strip() if match else fallback


def build(root: str, snapshot_path: str, fragment: bool = False,
          dashboard: str = "stocks") -> str:
    spec = DASHBOARDS[dashboard]
    with open(os.path.join(WEB, spec["html"])) as handle:
        html = handle.read()
    css = "\n".join(
        open(os.path.join(WEB, name)).read() for name in spec["css"]
    )
    with open(os.path.join(WEB, spec["js"])) as handle:
        js = handle.read()
    with open(snapshot_path) as handle:
        snapshot = json.load(handle)

    # </script> inside the data would close the tag early.
    payload = json.dumps(snapshot, separators=(",", ":")).replace("</", "<\\/")
    built = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    parts = [
        f"<title>{title_of(html, spec['title'])}</title>",
        FONTS,
        f"<style>\n{css}\n</style>",
        body_of(html, spec["js"], spec["html"]),
        f"<script>window.{spec['global']} = {payload};</script>",
        f"<script>\n{js}\n</script>",
        f"<!-- exported {built} -->",
    ]
    page = "\n".join(parts)

    if fragment:
        return page
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"{page}\n</head>\n</html>\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dashboard", default="stocks", choices=sorted(DASHBOARDS),
                        help="which dashboard to export (default: stocks)")
    parser.add_argument("--snapshot", default=None,
                        help="data file to inline (default: the dashboard's own)")
    parser.add_argument("--out", default=None,
                        help="output path (default: dist/<dashboard>.html)")
    parser.add_argument("--fragment", action="store_true",
                        help="omit the html/head wrapper (for hosts that supply their own)")
    args = parser.parse_args()

    spec = DASHBOARDS[args.dashboard]
    args.snapshot = args.snapshot or os.path.join(ROOT, spec["data"])
    args.out = args.out or os.path.join(ROOT, "dist", spec["out"])

    page = build(ROOT, args.snapshot, fragment=args.fragment, dashboard=args.dashboard)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as handle:
        handle.write(page)

    size = os.path.getsize(args.out) / 1024
    print(f"{os.path.relpath(args.out, ROOT)} · {size:.0f} KB · self-contained")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
