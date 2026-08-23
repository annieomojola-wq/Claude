#!/usr/bin/env python3
"""Throwaway: confirm the governance series come back under their new ids."""
import json, urllib.request

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
        print(f"  [API ERR ] {label}: " + "; ".join(str(m.get('value')) for m in payload[0]['message']))
        return
    rows = payload[1] if isinstance(payload, list) and len(payload) > 1 else None
    good = [r for r in (rows or []) if isinstance(r, dict) and r.get("value") is not None]
    if not good:
        print(f"  [EMPTY   ] {label}")
        return
    years = sorted({r["date"] for r in good})
    isos = sorted({r["countryiso3code"] for r in good})
    print(f"  [OK {len(good):>5}] {label}")
    print(f"             countries={isos} years={years[0]}..{years[-1]}")
    print(f"             e.g. {good[0]['countryiso3code']} {good[0]['date']} = {good[0]['value']}")


print("=== governance under the GOV_WGI_ ids ===")
for code in ["GOV_WGI_PV.EST", "GOV_WGI_GE.EST", "GOV_WGI_VA.EST"]:
    probe(f"{code} + source=3",
          f"{BASE}/country/{FIVE}/indicator/{code}?format=json&per_page=20000&date=1975:2026&source=3")
    probe(f"{code} without source",
          f"{BASE}/country/{FIVE}/indicator/{code}?format=json&per_page=20000&date=1975:2026")
