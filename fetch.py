#!/usr/bin/env python3
"""Refresh the dashboard snapshot.

    python3 fetch.py                      # demo data, no network
    python3 fetch.py --provider stooq     # live data, no API key needed
    python3 fetch.py --provider yahoo --basis calendar
    python3 fetch.py --provider twelvedata --exchanges LSE

The result is written to data/snapshot.json, which the dashboard reads.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from stockmon import providers, snapshot, universe

ROOT = os.path.dirname(os.path.abspath(__file__))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider", default="demo", choices=["demo", "stooq", "yahoo", "twelvedata"],
                        help="price source (default: demo - synthetic, not real prices)")
    parser.add_argument("--basis", default="rolling", choices=["rolling", "calendar"],
                        help="rolling: latest close vs one month earlier. "
                             "calendar: last completed month vs the month before")
    parser.add_argument("--exchanges", nargs="*", default=None, metavar="CODE",
                        help=f"subset of {sorted(universe.EXCHANGES)} (default: all three)")
    parser.add_argument("--lookback-days", type=int, default=500,
                        help="days of history to pull (default: 500, enough for year-on-year)")
    parser.add_argument("--cache-hours", type=float, default=0.0,
                        help="reuse cached history newer than this many hours (default: 0, always refetch)")
    parser.add_argument("--limit", type=int, default=None, help="only the first N companies (for testing)")
    parser.add_argument("--seed", default="2026", help="demo provider seed")
    parser.add_argument("--out", default=os.path.join(ROOT, "data", "snapshot.json"))
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--fail-under", type=int, default=0, metavar="N",
                        help="exit non-zero if fewer than N companies were priced, so a "
                             "scheduled run can fall back to another provider")
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
        exchanges=args.exchanges,
        basis=args.basis,
        lookback_days=args.lookback_days,
        cache_hours=args.cache_hours,
        limit=args.limit,
        progress=progress,
    )

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as handle:
        json.dump(result, handle, indent=1)
        handle.write("\n")

    counts = result["meta"]["counts"]
    print(
        f"{counts['tracked']} tracked · {counts['decliners']} down month-on-month · "
        f"{counts['sustained']} down two months running · {counts['errors']} failed "
        f"-> {os.path.relpath(args.out, ROOT)}"
    )
    if counts["errors"]:
        print("  failures:", ", ".join(sorted({e["ticker"] for e in result["meta"]["errors"]})), file=sys.stderr)

    if args.fail_under and counts["tracked"] < args.fail_under:
        print(
            f"error: only {counts['tracked']} companies priced, expected at least {args.fail_under}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
