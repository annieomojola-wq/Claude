#!/usr/bin/env python3
"""Refresh the economic tracker snapshot.

    python3 fetch_econ.py                          # demo data, no network
    python3 fetch_econ.py --provider worldbank     # live data, no API key needed
    python3 fetch_econ.py --provider worldbank --indices yahoo
    python3 fetch_econ.py --provider worldbank --start 1960

The result is written to data/econ.json, which web/econ.html reads.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from econ import countries, indicators, providers, snapshot

ROOT = os.path.dirname(os.path.abspath(__file__))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--provider", default="demo", choices=["demo", "worldbank"],
                        help="data source (default: demo - synthetic, not real data)")
    parser.add_argument("--start", type=int, default=snapshot.DEFAULT_START,
                        help=f"first year to pull (default: {snapshot.DEFAULT_START})")
    parser.add_argument("--end", type=int, default=None, help="last year (default: this year)")
    parser.add_argument("--indices", default=None, choices=["yahoo", "stooq"],
                        help="also pull live equity index levels from this price provider")
    parser.add_argument("--lookback-days", type=int, default=500,
                        help="days of index history to pull (default: 500)")
    parser.add_argument("--delay", type=float, default=0.2,
                        help="pause between World Bank requests (default: 0.2s)")
    parser.add_argument("--seed", default="2026", help="demo provider seed")
    parser.add_argument("--out", default=os.path.join(ROOT, "data", "econ.json"))
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--fail-under", type=int, default=0, metavar="N",
                        help="exit non-zero if fewer than N observations came back, so a "
                             "scheduled run does not commit a hollowed-out snapshot")
    args = parser.parse_args(argv)

    def progress(msg: str) -> None:
        if not args.quiet:
            print(msg, file=sys.stderr)

    try:
        provider = providers.get_provider(args.provider, seed=args.seed)
    except providers.ProviderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    result = snapshot.build(
        ROOT,
        provider,
        start=args.start,
        end=args.end,
        index_provider=args.indices,
        lookback_days=args.lookback_days,
        delay=args.delay,
        progress=progress,
    )

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as handle:
        json.dump(result, handle, indent=1)
        handle.write("\n")

    meta = result["meta"]
    graded = sum(1 for iso3 in countries.ISO3_CODES if result["pulse"][iso3]["latest"] is not None)
    print(
        f"{meta['observations']} observations · {meta['indicators']} indicators · "
        f"{meta['countries']} countries · {meta['start_year']}-{meta['end_year']} · "
        f"{graded}/{meta['countries']} scored -> {os.path.relpath(args.out, ROOT)}"
    )
    for iso3 in countries.ISO3_CODES:
        entry = result["pulse"][iso3]
        latest = entry["latest"]
        shown = f"{latest:.1f} ({entry['band']})" if latest is not None else "not scored"
        print(f"  {countries.get(iso3)['short']:<15} pulse {shown}")

    if meta["errors"]:
        print(f"  {len(meta['errors'])} indicator(s) failed:", file=sys.stderr)
        for err in meta["errors"]:
            print(f"    {err['indicator']}: {err['error']}", file=sys.stderr)

    if args.fail_under and meta["observations"] < args.fail_under:
        print(
            f"error: only {meta['observations']} observations, expected at least "
            f"{args.fail_under}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
