#!/usr/bin/env python3
"""Throwaway: try several World Bank URL shapes and report which return data.

Egress is closed in the authoring environment, so this runs on Actions purely
to answer 'which spelling of this request actually works'. Delete once the
governance series are wired up.
"""
import json, sys, urllib.request, urllib.error

BASE = "https://api.worldbank.org/v2"
FIVE = "USA;GBR;IRL;CAN;NGA"


def probe(label, url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "probe/1.0"})
        with urllib.request.urlopen(req, timeout=45) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"  [HTTP FAIL] {label}: {exc}")
        return
    if isinstance(payload, list) and payload and isinstance(payload[0], dict) and "message" in payload[0]:
        msg = "; ".join(str(m.get("value")) for m in payload[0]["message"])
        print(f"  [API ERR ] {label}: {msg}")
        return
    rows = payload[1] if isinstance(payload, list) and len(payload) > 1 else None
    if not rows:
        print(f"  [EMPTY   ] {label}")
        return
    good = [r for r in rows if isinstance(r, dict) and r.get("value") is not None]
    sample = good[0] if good else None
    print(f"  [OK {len(good):>5}] {label}")
    if sample:
        print(f"             e.g. {sample.get('countryiso3code')} {sample.get('date')} = {sample.get('value')}")


print("=== governance: PV.EST url shapes ===")
probe("source=3, five countries, 1975:2026",
      f"{BASE}/country/{FIVE}/indicator/PV.EST?format=json&per_page=20000&date=1975:2026&source=3")
probe("source=3, five countries, 1996:2026",
      f"{BASE}/country/{FIVE}/indicator/PV.EST?format=json&per_page=20000&date=1996:2026&source=3")
probe("source=3, five countries, no date",
      f"{BASE}/country/{FIVE}/indicator/PV.EST?format=json&per_page=20000&source=3")
probe("source=3, one country, no date",
      f"{BASE}/country/USA/indicator/PV.EST?format=json&per_page=2000&source=3")
probe("source=3, one country, per_page=100",
      f"{BASE}/country/USA/indicator/PV.EST?format=json&per_page=100&source=3")
probe("no source, one country",
      f"{BASE}/country/USA/indicator/PV.EST?format=json&per_page=100")
probe("sources/3/country/../series/.. shape",
      f"{BASE}/sources/3/country/USA/series/PV.EST/data?format=json&per_page=100")
probe("country/all, source=3",
      f"{BASE}/country/all/indicator/PV.EST?format=json&per_page=100&source=3")

print("\n=== what indicators does source 3 actually expose? ===")
probe("source 3 indicator list", f"{BASE}/indicator?format=json&source=3&per_page=100")
try:
    req = urllib.request.Request(f"{BASE}/indicator?format=json&source=3&per_page=200",
                                 headers={"User-Agent": "probe/1.0"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    rows = payload[1] or []
    print(f"  source 3 exposes {len(rows)} indicators; first 25 ids:")
    for row in rows[:25]:
        print(f"    {row.get('id'):<24} {row.get('name','')[:70]}")
except Exception as exc:
    print(f"  could not list: {exc}")

print("\n=== government debt: coverage for Ireland and Nigeria ===")
for code in ["GC.DOD.TOTL.GD.ZS", "DT.DOD.DECT.GD.ZS", "DP.DOD.DECD.CR.GG.Z1"]:
    probe(f"{code} five countries",
          f"{BASE}/country/{FIVE}/indicator/{code}?format=json&per_page=20000&date=1975:2026")

print("\n=== business closure / formation candidates ===")
for code in ["IC.BUS.NDNS.ZS", "IC.BUS.DISC.XQ", "IC.ISV.RECRT"]:
    probe(f"{code} five countries",
          f"{BASE}/country/{FIVE}/indicator/{code}?format=json&per_page=20000&date=1975:2026")
