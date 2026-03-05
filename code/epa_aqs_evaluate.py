#!/usr/bin/env python3
"""
Evaluate EPA AQS (Air Quality System) data availability for the
Southside Smells investigation.

Discovers monitoring sites in Cook County IL and Lake County IN,
then checks for SO2, H2S, benzene, and PM2.5 data during the
Oct–Nov 2025 study period.

Requires:
    export EPA_AQS_EMAIL="your-registered-email"
    export EPA_AQS_KEY="your-api-key"

Register for free at https://aqs.epa.gov/aqsweb/documents/data_api.html#signup

Usage:
    python epa_aqs_evaluate.py

Outputs:
    data/epa_aqs_monitors.json   — monitor metadata for relevant sites
    data/epa_aqs_samples.csv     — any available sample data found
"""

import os
import sys
import json
import csv
import time
import math
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ── Credentials ──

EMAIL = os.environ.get("EPA_AQS_EMAIL", "")
KEY = os.environ.get("EPA_AQS_KEY", "")
if not EMAIL or not KEY:
    print("Set EPA_AQS_EMAIL and EPA_AQS_KEY environment variables first.")
    print("Register free at: https://aqs.epa.gov/aqsweb/documents/data_api.html#signup")
    sys.exit(1)

# ── Constants ──

API_BASE = "https://aqs.epa.gov/data/api"
REQUEST_DELAY = 6  # seconds between requests (EPA asks for 5s minimum)

HP_LAT, HP_LON = 41.794, -87.590   # Hyde Park reference point
EARTH_RADIUS_MI = 3959

# Counties of interest
COUNTIES = [
    ("17", "031", "Cook County, IL"),
    ("18", "089", "Lake County, IN"),
]

# Parameters to check (code, name, relevance)
PARAMETERS = [
    ("42401", "SO2",          "Combustion/coking signature from Calumet facilities"),
    ("42402", "H2S",          "Hydrogen sulfide — rotten egg odor marker"),
    ("45201", "Benzene",      "Refinery/coke oven VOC"),
    ("45202", "Toluene",      "Industrial solvent / refinery VOC"),
    ("88101", "PM2.5 (FRM)",  "Regulatory-grade fine particulate"),
    ("42602", "NO2",          "Combustion byproduct"),
]

# Study period
STUDY_START = "20251001"
STUDY_END   = "20251105"

# Also check a prior-year baseline for comparison
BASELINE_START = "20241001"
BASELINE_END   = "20241105"


# ── Geometry helpers (consistent with other project scripts) ──

def haversine(lat1, lon1, lat2, lon2):
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return EARTH_RADIUS_MI * 2 * math.asin(math.sqrt(a))

def bearing(lat1, lon1, lat2, lon2):
    dlon = math.radians(lon2 - lon1)
    y = math.sin(dlon) * math.cos(math.radians(lat2))
    x = (math.cos(math.radians(lat1)) * math.sin(math.radians(lat2))
         - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.cos(dlon))
    return (math.degrees(math.atan2(y, x)) + 360) % 360

def compass(deg):
    sectors = ['N','NNE','NE','ENE','E','ESE','SE','SSE',
               'S','SSW','SW','WSW','W','WNW','NW','NNW']
    return sectors[int((deg + 11.25) / 22.5) % 16]


# ── API helpers ──

def aqs_get(endpoint, params):
    """Make a GET request to the AQS API. Returns parsed JSON or None."""
    params["email"] = EMAIL
    params["key"] = KEY
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{API_BASE}/{endpoint}?{query}"

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        # Try to extract the structured error message from AQS JSON
        try:
            err_json = json.loads(body)
            err_msg = err_json.get("Header", [{}])[0].get("error", body[:200])
        except (json.JSONDecodeError, IndexError):
            err_msg = body[:200]
        print(f"    API error {e.code}: {err_msg}")
        return None
    except urllib.error.URLError as e:
        print(f"    Network error: {e.reason}")
        return None

def aqs_delay():
    """Respect EPA's rate limit (max 10 req/min, 5s pause requested)."""
    time.sleep(REQUEST_DELAY)


# ── Phase 1: Discover monitors ──

def discover_monitors():
    """Find all monitors for our parameters of interest in both counties.
    AQS limits queries to 1 year, so we query per-year and deduplicate."""
    all_monitors = []
    seen = set()  # (state, county, site, param, poc) to deduplicate

    # Query year-by-year to stay within AQS 1-year limit
    year_ranges = [
        ("20250101", "20251231"),
        ("20240101", "20241231"),
        ("20230101", "20231231"),
    ]

    for state, county, county_name in COUNTIES:
        for param_code, param_name, _ in PARAMETERS:
            print(f"  Querying monitors: {param_name} ({param_code}) in {county_name}...")

            data = []
            for bdate, edate in year_ranges:
                result = aqs_get("monitors/byCounty", {
                    "param": param_code,
                    "bdate": bdate,
                    "edate": edate,
                    "state": state,
                    "county": county,
                })
                aqs_delay()

                if not result:
                    continue

                header = result.get("Header", [{}])
                if header and header[0].get("status") == "Failed":
                    # Some params may simply not exist in a county — not an error
                    break

                year_data = result.get("Data", [])
                if year_data:
                    data.extend(year_data)
                    break  # found monitors, no need to check older years

            if not data:
                print(f"    → No monitors found")
                continue

            # Deduplicate and collect
            new_count = 0
            for mon in data:
                key = (state, county, mon.get("site_number", ""),
                       param_code, mon.get("poc", ""))
                if key in seen:
                    continue
                seen.add(key)
                new_count += 1

                lat = mon.get("latitude")
                lon = mon.get("longitude")
                dist = haversine(HP_LAT, HP_LON, lat, lon) if lat and lon else None
                brg = bearing(HP_LAT, HP_LON, lat, lon) if lat and lon else None

                all_monitors.append({
                    "state": state,
                    "county": county,
                    "county_name": county_name,
                    "site_number": mon.get("site_number", ""),
                    "parameter_code": param_code,
                    "parameter_name": param_name,
                    "poc": mon.get("poc", ""),
                    "latitude": lat,
                    "longitude": lon,
                    "dist_mi": round(dist, 1) if dist else None,
                    "bearing": round(brg) if brg else None,
                    "compass": compass(brg) if brg else None,
                    "local_site_name": mon.get("local_site_name", ""),
                    "address": mon.get("address", ""),
                    "monitor_type": mon.get("monitor_type", ""),
                    "open_date": mon.get("open_date", ""),
                    "close_date": mon.get("close_date", ""),
                    "last_sample_date": mon.get("last_sample_date", ""),
                    "reporting_agency": mon.get("reporting_agency", ""),
                })

            print(f"    → {new_count} monitor(s)")

    return all_monitors


# ── Phase 2: Check data availability ──

def check_data_availability(monitors):
    """Query sample data for active monitors during the study period."""
    # Deduplicate by (state, county, site, param) for queries
    seen = set()
    queries = []
    for m in monitors:
        key = (m["state"], m["county"], m["site_number"], m["parameter_code"])
        if key not in seen:
            seen.add(key)
            # Only query monitors that were active recently
            if m.get("close_date") and m["close_date"] < "2025-01-01":
                continue
            queries.append(m)

    all_samples = []

    for period_name, bdate, edate in [
        ("Study period (Oct-Nov 2025)", STUDY_START, STUDY_END),
        ("Baseline (Oct-Nov 2024)", BASELINE_START, BASELINE_END),
    ]:
        print(f"\n── Checking {period_name} ──")

        for m in queries:
            label = (f"{m['parameter_name']} at {m['local_site_name'] or m['site_number']}"
                     f" ({m['county_name']})")
            print(f"  {label}...", end=" ", flush=True)

            result = aqs_get("sampleData/bySite", {
                "param": m["parameter_code"],
                "bdate": bdate,
                "edate": edate,
                "state": m["state"],
                "county": m["county"],
                "site": m["site_number"],
            })
            aqs_delay()

            if not result:
                print("no response")
                continue

            header = result.get("Header", [{}])
            if header and header[0].get("status") == "Failed":
                print(f"error: {header[0].get('error', '?')[:60]}")
                continue

            data = result.get("Data", [])
            if not data:
                print("no data")
                continue

            print(f"{len(data)} samples!")

            for sample in data:
                lat = sample.get("latitude")
                lon = sample.get("longitude")
                dist = haversine(HP_LAT, HP_LON, lat, lon) if lat and lon else None

                all_samples.append({
                    "period": period_name,
                    "date_local": sample.get("date_local", ""),
                    "time_local": sample.get("time_local", ""),
                    "parameter_name": m["parameter_name"],
                    "parameter_code": m["parameter_code"],
                    "sample_measurement": sample.get("sample_measurement", ""),
                    "units": sample.get("units_of_measure", ""),
                    "site_name": sample.get("local_site_name", m["local_site_name"]),
                    "state": m["state"],
                    "county": m["county"],
                    "site": m["site_number"],
                    "county_name": m["county_name"],
                    "dist_mi": round(dist, 1) if dist else None,
                    "method": sample.get("method", ""),
                    "sample_duration": sample.get("sample_duration", ""),
                    "aqi": sample.get("aqi", ""),
                })

    return all_samples


# ── Main ──

def main():
    print("=" * 70)
    print("EPA AQS Data Evaluation for Southside Smells")
    print("=" * 70)
    print(f"Reference point: Hyde Park ({HP_LAT}, {HP_LON})")
    print(f"Study period:    {STUDY_START} – {STUDY_END}")
    print(f"Baseline:        {BASELINE_START} – {BASELINE_END}")
    print(f"Counties:        {', '.join(name for _, _, name in COUNTIES)}")
    print(f"Parameters:      {', '.join(name for _, name, _ in PARAMETERS)}")
    print()

    # Phase 1: Discover monitors
    print("── Phase 1: Discovering monitors ──\n")
    monitors = discover_monitors()

    if not monitors:
        print("\nNo monitors found. Check credentials and try again.")
        sys.exit(1)

    # Save monitor metadata
    outfile_monitors = os.path.join(os.path.dirname(__file__), "..", "data", "epa_aqs_monitors.json")
    with open(outfile_monitors, "w") as f:
        json.dump(monitors, f, indent=2)
    print(f"\n→ {len(monitors)} monitor records saved to {outfile_monitors}")

    # Print monitor summary
    print(f"\n{'Site Name':<35s} {'Param':<10s} {'County':<18s} "
          f"{'Dist':>5s} {'Brg':>4s} {'Dir':>4s}  {'Last Sample':<12s}")
    print("-" * 100)

    seen_sites = set()
    for m in sorted(monitors, key=lambda x: (x["parameter_code"], x.get("dist_mi") or 999)):
        site_key = (m["site_number"], m["parameter_code"])
        if site_key in seen_sites:
            continue
        seen_sites.add(site_key)

        name = (m["local_site_name"] or m["site_number"])[:34]
        dist = f"{m['dist_mi']:5.1f}" if m["dist_mi"] else "    ?"
        brg = f"{m['bearing']:4d}°" if m["bearing"] else "   ?°"
        comp = m.get("compass", "?") or "?"
        last = (m.get("last_sample_date") or "?")[:10]
        print(f"{name:<35s} {m['parameter_name']:<10s} {m['county_name']:<18s} "
              f"{dist} {brg} {comp:>4s}  {last}")

    # Phase 2: Check data availability
    print("\n── Phase 2: Checking data availability ──")
    samples = check_data_availability(monitors)

    if samples:
        outfile_samples = os.path.join(os.path.dirname(__file__), "..", "data", "epa_aqs_samples.csv")
        fieldnames = ["period", "date_local", "time_local", "parameter_name",
                       "parameter_code", "sample_measurement", "units",
                       "site_name", "state", "county", "site", "county_name",
                       "dist_mi", "method", "sample_duration", "aqi"]
        with open(outfile_samples, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(samples)
        print(f"\n→ {len(samples)} sample records saved to {outfile_samples}")
    else:
        print("\n→ No sample data found for either period.")

    # Final summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    unique_sites = set()
    for m in monitors:
        unique_sites.add((m["state"], m["county"], m["site_number"], m["local_site_name"]))
    print(f"Unique monitoring sites found: {len(unique_sites)}")

    by_param = {}
    for m in monitors:
        by_param.setdefault(m["parameter_name"], set()).add(
            (m["state"], m["county"], m["site_number"]))
    for param, sites in sorted(by_param.items()):
        print(f"  {param}: {len(sites)} site(s)")

    if samples:
        study_samples = [s for s in samples if "2025" in s["period"]]
        baseline_samples = [s for s in samples if "2024" in s["period"]]
        print(f"\nSample data found:")
        print(f"  Study period (Oct-Nov 2025): {len(study_samples)} records")
        print(f"  Baseline (Oct-Nov 2024):     {len(baseline_samples)} records")

        # Break down by parameter
        for period_name, subset in [("2025", study_samples), ("2024", baseline_samples)]:
            if subset:
                by_p = {}
                for s in subset:
                    by_p.setdefault(s["parameter_name"], []).append(s)
                print(f"\n  {period_name} breakdown:")
                for p, recs in sorted(by_p.items()):
                    print(f"    {p}: {len(recs)} records")
    else:
        print("\nNo sample data available yet for either period.")
        print("Q4 2025 data may not be loaded into AQS until mid-2026.")
        print("Consider re-running this script in a few months.")


if __name__ == "__main__":
    main()
