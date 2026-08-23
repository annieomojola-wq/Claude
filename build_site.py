#!/usr/bin/env python3
"""Build the static site that GitHub Pages serves.

    python3 build_site.py            # -> site/

Each dashboard becomes one self-contained page: styles, script and data all
inlined, so the site is three HTML files with no fetches and nothing to
configure on the host.

The one wrinkle is naming. In `web/` the stock dashboard is `index.html`
because that is what a local server opens; on the site the *economy* tracker
should be the landing page. So the files are renamed here and the tab links
are rewritten to match, keyed off each link's `data-nav` attribute rather than
its href, which makes the rewrite unambiguous.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil

import export_html

ROOT = os.path.dirname(os.path.abspath(__file__))

#: dashboard -> the filename it takes on the published site
SITE_NAMES = {
    "econ": "index.html",        # the landing page
    "careers": "careers.html",
    "stocks": "markets.html",
}

#: data-nav value -> the site filename that link should point at
NAV_TARGETS = {
    "economy": "index.html",
    "careers": "careers.html",
    "markets": "markets.html",
}


def rewrite_nav(html: str) -> str:
    """Point the tab links at their published filenames.

    Keyed off data-nav, so it does not matter what the href says in `web/`.
    """
    def replace(match: re.Match) -> str:
        before, href, after = match.group(1), match.group(2), match.group(3)
        nav = re.search(r'data-nav="([^"]+)"', before + after)
        if not nav or nav.group(1) not in NAV_TARGETS:
            return match.group(0)
        return f'<a {before}href="{NAV_TARGETS[nav.group(1)]}"{after}>'

    return re.sub(r'<a ([^>]*?)href="([^"]+)"([^>]*?)>', replace, html)


def build(out_dir: str) -> list[tuple[str, int]]:
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)

    built: list[tuple[str, int]] = []
    for dashboard, filename in SITE_NAMES.items():
        spec = export_html.DASHBOARDS[dashboard]
        page = export_html.build(
            ROOT, os.path.join(ROOT, spec["data"]), dashboard=dashboard
        )
        page = rewrite_nav(page)
        path = os.path.join(out_dir, filename)
        with open(path, "w") as handle:
            handle.write(page)
        built.append((filename, os.path.getsize(path)))

    # Pages runs Jekyll unless told not to, which would drop any file or
    # directory whose name starts with an underscore.
    open(os.path.join(out_dir, ".nojekyll"), "w").close()
    return built


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=os.path.join(ROOT, "site"))
    args = parser.parse_args()

    built = build(args.out)
    total = sum(size for _, size in built)
    for filename, size in built:
        print(f"  {filename:<16} {size / 1024:>7.0f} KB")
    print(f"{len(built)} pages · {total / 1024:.0f} KB total -> "
          f"{os.path.relpath(args.out, ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
