#!/usr/bin/env python3
"""fetch_sed.py — pull NOAA SED and split per state-year for the Storm Claim Tool.

Workflow:
  1. Lists the NCEI bulk-CSV directory and picks the latest "details" file
     for each year in --years (default: most recent 10).
  2. Downloads + decompresses + parses each file (no third-party deps).
  3. Writes per-state per-year CSVs to ./sed-data/<STATE>/details_<year>.csv
     in the same column order the source files use, so the existing
     parseSEDCsv() in the HTML app can read them as-is.
  4. Records what it has already pulled in ./sed-data/_manifest.json so
     subsequent runs skip files NCEI hasn't republished.

Usage:
  python fetch_sed.py                 # 1996 to current (~30 years)
  python fetch_sed.py --years 2018 2019 2020
  python fetch_sed.py --years-from 2015        # from 2015 to current year
  python fetch_sed.py --states TX OK LA        # limit output to specific states
  python fetch_sed.py --refresh-current        # force re-download of current year

Hosting tip: drag the resulting `sed-data/` folder onto https://app.netlify.com/drop
to publish. Paste the URL Netlify gives you into SED_BASE_URL inside
storm-claim-tool.html.
"""

import argparse
import csv
import datetime as dt
import gzip
import io
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

NCEI_INDEX = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/"
USER_AGENT = "fetch_sed.py/1.0 (Storm Claim Tool)"
OUTPUT_ROOT = Path("sed-data")
MANIFEST_PATH = OUTPUT_ROOT / "_manifest.json"

# Match e.g. StormEvents_details-ftp_v1.0_d2024_c20240417.csv.gz
DETAILS_RE = re.compile(
    r'href="(StormEvents_details-ftp_v1\.0_d(\d{4})_c(\d{8})\.csv\.gz)"',
    re.IGNORECASE,
)


def http_get(url, *, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", errors="replace")


def list_details_files():
    """Return {year: (filename, creation_date)} for the latest creation per year."""
    html = http_get(NCEI_INDEX)
    by_year = {}
    for m in DETAILS_RE.finditer(html):
        fname, year, cdate = m.group(1), int(m.group(2)), m.group(3)
        cur = by_year.get(year)
        if cur is None or cdate > cur[1]:
            by_year[year] = (fname, cdate)
    return by_year


def load_manifest():
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text())
        except Exception:
            pass
    return {}


def save_manifest(m):
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(m, indent=2, sort_keys=True))


# Mapping NOAA's full state name -> 2-letter postal code. Includes territories
# present in SED data. Anything not in this map is dropped (e.g., state="ATLANTIC").
STATE_TO_ABBR = {
    "ALABAMA":"AL","ALASKA":"AK","ARIZONA":"AZ","ARKANSAS":"AR","CALIFORNIA":"CA",
    "COLORADO":"CO","CONNECTICUT":"CT","DELAWARE":"DE","DISTRICT OF COLUMBIA":"DC",
    "FLORIDA":"FL","GEORGIA":"GA","HAWAII":"HI","IDAHO":"ID","ILLINOIS":"IL",
    "INDIANA":"IN","IOWA":"IA","KANSAS":"KS","KENTUCKY":"KY","LOUISIANA":"LA",
    "MAINE":"ME","MARYLAND":"MD","MASSACHUSETTS":"MA","MICHIGAN":"MI","MINNESOTA":"MN",
    "MISSISSIPPI":"MS","MISSOURI":"MO","MONTANA":"MT","NEBRASKA":"NE","NEVADA":"NV",
    "NEW HAMPSHIRE":"NH","NEW JERSEY":"NJ","NEW MEXICO":"NM","NEW YORK":"NY",
    "NORTH CAROLINA":"NC","NORTH DAKOTA":"ND","OHIO":"OH","OKLAHOMA":"OK","OREGON":"OR",
    "PENNSYLVANIA":"PA","PUERTO RICO":"PR","RHODE ISLAND":"RI","SOUTH CAROLINA":"SC",
    "SOUTH DAKOTA":"SD","TENNESSEE":"TN","TEXAS":"TX","UTAH":"UT","VERMONT":"VT",
    "VIRGINIA":"VA","WASHINGTON":"WA","WEST VIRGINIA":"WV","WISCONSIN":"WI","WYOMING":"WY",
    "AMERICAN SAMOA":"AS","GUAM":"GU","VIRGIN ISLANDS":"VI",
}


def split_by_state(year, csv_text, only_states=None):
    """Split a yearly details CSV into per-state CSVs. Returns {abbr: row_count}."""
    reader = csv.reader(io.StringIO(csv_text))
    header = next(reader)
    try:
        state_idx = header.index("STATE")
    except ValueError:
        raise SystemExit(f"Year {year}: STATE column not found. Header: {header[:5]}…")

    buffers = {}  # abbr -> list of rows (header included)
    rows_seen = 0
    rows_skipped = 0
    for row in reader:
        rows_seen += 1
        if state_idx >= len(row):
            rows_skipped += 1
            continue
        st_full = (row[state_idx] or "").strip().upper()
        abbr = STATE_TO_ABBR.get(st_full)
        if abbr is None:
            rows_skipped += 1
            continue
        if only_states and abbr not in only_states:
            continue
        if abbr not in buffers:
            buffers[abbr] = [header]
        buffers[abbr].append(row)

    counts = {}
    for abbr, rows in buffers.items():
        outdir = OUTPUT_ROOT / abbr
        outdir.mkdir(parents=True, exist_ok=True)
        path = outdir / f"details_{year}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rows)
        counts[abbr] = len(rows) - 1  # exclude header
    return counts, rows_seen, rows_skipped


def main():
    p = argparse.ArgumentParser(description="Download and split NOAA SED data per state-year.")
    p.add_argument("--years", type=int, nargs="+",
                   help="Specific years to download. Default: 1996 to current.")
    p.add_argument("--years-from", type=int, default=None,
                   help="Download from this year through current year.")
    p.add_argument("--states", nargs="+",
                   help="Only output for these 2-letter state codes (default: all).")
    p.add_argument("--refresh-current", action="store_true",
                   help="Force re-download of the current year even if not changed.")
    args = p.parse_args()

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    only_states = set(s.upper() for s in args.states) if args.states else None

    print(f"  Listing NCEI directory: {NCEI_INDEX}")
    avail = list_details_files()
    print(f"  Found {len(avail)} years available ({min(avail)}–{max(avail)})")

    current_year = dt.date.today().year
    if args.years:
        years_wanted = sorted(args.years)
    elif args.years_from is not None:
        years_wanted = list(range(args.years_from, current_year + 1))
    else:
        # Default: 1996 to current. NCEI's modern Storm Events Database
        # launched in 1996 — that's when event format became consistent
        # and lat/lon was reliably recorded. Pre-1996 records are mostly
        # county-only and not useful to a radius-based tool.
        years_wanted = list(range(1996, current_year + 1))

    print(f"  Targeting years: {years_wanted[0]}–{years_wanted[-1]} ({len(years_wanted)} years)")
    if only_states:
        print(f"  Limiting output to states: {sorted(only_states)}")

    manifest = load_manifest()
    fetched = 0
    skipped = 0

    for year in years_wanted:
        info = avail.get(year)
        if not info:
            print(f"  [{year}] not on NCEI yet — skipping")
            continue
        fname, cdate = info
        prev = manifest.get(str(year))
        if prev and prev.get("creation") == cdate and not (
                args.refresh_current and year == current_year):
            print(f"  [{year}] up to date ({cdate}) — skipping")
            skipped += 1
            continue

        url = NCEI_INDEX + fname
        print(f"  [{year}] downloading {fname} …")
        try:
            data = http_get(url, binary=True)
            csv_text = gzip.decompress(data).decode("utf-8", errors="replace")
        except Exception as e:
            print(f"     FAILED: {e}", file=sys.stderr)
            continue

        counts, seen, skipped_rows = split_by_state(year, csv_text, only_states)
        total = sum(counts.values())
        print(f"     {seen} rows in source; wrote {total} rows across {len(counts)} states "
              f"({skipped_rows} ignored: territories or missing state).")

        manifest[str(year)] = {
            "filename": fname,
            "creation": cdate,
            "fetched_at": dt.datetime.utcnow().isoformat() + "Z",
            "states_count": len(counts),
            "row_total": total,
        }
        save_manifest(manifest)
        fetched += 1

    print(f"\nDone. {fetched} year(s) refreshed, {skipped} skipped.")
    print(f"Output: {OUTPUT_ROOT.resolve()}")
    print(f"Manifest: {MANIFEST_PATH.resolve()}")
    if fetched:
        print(f"\nNext steps:")
        print(f"  1. (First time only) drag the '{OUTPUT_ROOT}' folder onto https://app.netlify.com/drop")
        print(f"     to publish, then copy the URL Netlify gives you.")
        print(f"  2. Open storm-claim-tool.html in a text editor, find SED_BASE_URL, and set it to:")
        print(f"       const SED_BASE_URL = \"https://YOUR-SITE.netlify.app/sed-data\";")
        print(f"  3. After updates: re-run this script, then drag the updated folder onto Netlify Drop")
        print(f"     (it replaces the previous deploy if you reuse the same site name).")


if __name__ == "__main__":
    main()
