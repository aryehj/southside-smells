#!/usr/bin/env python3
"""
Pull historical PM2.5 from PurpleAir sensors along the Hyde Park → Calumet
/ NW Indiana plume path.

This script queries ALL candidate sensors selected for the analysis.
Sensors that return no data for the study period are included in the
output with zero rows — so readers can see exactly which sensors were
attempted and which had data.

Sensor selection criteria:
  1. Outdoor sensors only (location_type=0)
  2. Bearing 135°–165° from Hyde Park (the SE plume corridor identified
     in the wind-direction analysis, pointing toward the Calumet industrial
     corridor and NW Indiana heavy industry)
  3. Reported to PurpleAir within the 90 days prior to the analysis
  4. Spaced across distance bands from source (~19 mi) to observer (~0 mi)
     to enable plume-propagation analysis

Requires:
    export PURPLEAIR_API_KEY="your-read-key-here"

Usage:
    python purpleair_history_pull_all.py

Outputs:
    purpleair_plume_history_all.csv
"""

import os
import sys
import csv
import json
import time
from datetime import datetime, timezone
import urllib.request

API_KEY = os.environ.get("PURPLEAIR_API_KEY", "")
if not API_KEY:
    print("Set PURPLEAIR_API_KEY environment variable first.")
    sys.exit(1)

# ── Study period ──
# Covers the full smell report window (Oct 7 – Nov 3, 2025) with buffer.
START = datetime(2025, 10, 1, 0, 0, tzinfo=timezone.utc)
END   = datetime(2025, 11, 6, 0, 0, tzinfo=timezone.utc)
CHUNK_DAYS = 14  # API limit for hourly data per request

# ── All candidate sensors ──
# Every sensor attempted across both analysis rounds.
# Sorted source-to-observer (descending distance from Hyde Park).
#
# Selection was drawn from a bounding-box scan of all outdoor PurpleAir
# sensors between Hyde Park (41.85, -87.70) and Gary, IN (41.58, -87.30)
# using the PurpleAir /v1/sensors endpoint. That scan found 73 outdoor
# sensors in the SE arc (bearing 90°–200°). From those, we selected
# sensors on bearings 135°–165° with at least one sensor per ~2-mile
# distance band, favoring NLCEP and MCC-series sensors for reliability,
# and adding community sensors (animal-named series, LUC_CARE) for
# density in the critical 5–10 mile range.

SENSORS = [
    # ── ~19 mi: near US Steel Gary Works ──
    (146228, "Progressive Community Church (NLCEP)", 19.1, 135),

    # ── ~12–13 mi: near Acme/SunCoke and BP Whiting ──
    (185123, "Harborworks (NLCEP)",                 12.9, 146),
    (185079, "Canalport (NLCEP)",                   12.4, 148),
    (203661, "Harrison Elementary",                 12.4, 153),

    # ── ~10–11 mi: mid-corridor ──
    (220241, "MCC08 OUT",                           11.4, 162),
    (220537, "MCC07 OUT",                           10.4, 164),

    # ── ~9–10 mi: Whiting / East Chicago area ──
    (146258, "CCSJ (NLCEP)",                         9.9, 150),
    (146110, "Lake George (NLCEP)",                  9.5, 151),
    (208687, "Whiting City Hall",                    9.4, 148),
    (185095, "Oliver (NLCEP)",                       9.2, 148),
    (172085, "Peach",                                9.2, 147),

    # ── ~7–8 mi: SE Chicago ──
    (220577, "MCC06 OUT",                            7.8, 158),
    (193684, "Robin",                                7.4, 155),
    (193807, "Smeller",                              7.1, 153),
    (193669, "Bug",                                  6.9, 155),

    # ── ~5–7 mi: mid-path ──
    (193673, "Nala",                                 6.7, 155),
    (193797, "Tiger",                                7.3, 154),
    (193803, "Penguin",                              5.7, 152),
    (175455, "LUC_CARE_13",                          5.6, 160),
    (193676, "Rooster",                              5.4, 150),

    # ── ~0 mi: Hyde Park (observation point) ──
    (153638, "Purple-HP-1",                          0.1, 152),
]

# ── API helpers ──

def fetch_sensor_history(sensor_index, start_ts, end_ts):
    """Fetch hourly PM2.5 history for one sensor, one time window.
    Returns list of (unix_timestamp, pm25_a, pm25_b) tuples."""

    fields = "pm2.5_atm_a,pm2.5_atm_b"
    url = (
        f"https://api.purpleair.com/v1/sensors/{sensor_index}/history/csv"
        f"?fields={fields}"
        f"&start_timestamp={start_ts}"
        f"&end_timestamp={end_ts}"
        f"&average=60"
    )
    req = urllib.request.Request(url, headers={"X-API-Key": API_KEY})
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print(f"    API error {e.code}: {err}")
        return []

    lines = body.strip().split("\n")
    if len(lines) < 2:
        return []

    header = lines[0].split(",")
    rows = []
    for line in lines[1:]:
        vals = line.split(",")
        if len(vals) < len(header):
            continue
        d = dict(zip(header, vals))
        ts = d.get("time_stamp", "")
        pm_a = d.get("pm2.5_atm_a", "")
        pm_b = d.get("pm2.5_atm_b", "")
        if ts:
            rows.append((int(ts), pm_a, pm_b))
    return rows


def chunked_ranges(start_dt, end_dt, chunk_days):
    """Yield (start_ts, end_ts) Unix timestamp pairs in chunks."""
    chunk_sec = chunk_days * 86400
    s = int(start_dt.timestamp())
    e = int(end_dt.timestamp())
    while s < e:
        yield s, min(s + chunk_sec, e)
        s += chunk_sec


def avg_pm25(pm_a_str, pm_b_str):
    """Average channels A and B, tolerating missing values."""
    try:
        a = float(pm_a_str) if pm_a_str else None
        b = float(pm_b_str) if pm_b_str else None
        if a is not None and b is not None:
            return round((a + b) / 2, 2)
        elif a is not None:
            return round(a, 2)
        elif b is not None:
            return round(b, 2)
    except ValueError:
        pass
    return ""


# ── Main ──

print(f"Querying {len(SENSORS)} sensors")
print(f"Period: {START.date()} to {END.date()}")
print(f"Chunks of {CHUNK_DAYS} days\n")

all_rows = []
sensor_summary = []

for idx, (sensor_index, name, dist_mi, bearing) in enumerate(SENSORS):
    print(f"[{idx+1}/{len(SENSORS)}] {name} (#{sensor_index}, {dist_mi} mi, {bearing}°)")
    sensor_rows = 0

    for chunk_start, chunk_end in chunked_ranges(START, END, CHUNK_DAYS):
        s_str = datetime.fromtimestamp(chunk_start, tz=timezone.utc).strftime("%m/%d")
        e_str = datetime.fromtimestamp(chunk_end, tz=timezone.utc).strftime("%m/%d")
        print(f"    {s_str}–{e_str} ... ", end="", flush=True)

        rows = fetch_sensor_history(sensor_index, chunk_start, chunk_end)
        print(f"{len(rows)} rows")
        sensor_rows += len(rows)

        for ts, pm_a, pm_b in rows:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            all_rows.append({
                "time_utc": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "sensor_index": sensor_index,
                "name": name,
                "dist_mi": dist_mi,
                "bearing": bearing,
                "pm25_a": pm_a,
                "pm25_b": pm_b,
                "pm25_avg": avg_pm25(pm_a, pm_b),
            })

        time.sleep(1.1)

    sensor_summary.append((sensor_index, name, dist_mi, bearing, sensor_rows))
    status = f"{sensor_rows} hours" if sensor_rows > 0 else "NO DATA"
    print(f"    → {status}\n")

# ── Write data CSV ──
outfile = "purpleair_plume_history_all.csv"
fieldnames = ["time_utc", "sensor_index", "name", "dist_mi", "bearing",
              "pm25_a", "pm25_b", "pm25_avg"]

with open(outfile, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(all_rows)

# ── Print summary ──
print("=" * 75)
print(f"RESULTS: {len(all_rows)} rows written to {outfile}")
print("=" * 75)
print()
print(f"{'Sensor':<42s} {'Dist':>5s} {'Brg':>4s} {'Hours':>6s}  Status")
print("-" * 75)
for sid, name, dist, brg, hours in sensor_summary:
    status = f"{hours} hours" if hours > 0 else "NO DATA for study period"
    print(f"{name:<42s} {dist:5.1f} {brg:4d}° {hours:>6d}  {status}")

reporting = sum(1 for _, _, _, _, h in sensor_summary if h > 0)
empty = sum(1 for _, _, _, _, h in sensor_summary if h == 0)
print(f"\n{reporting} sensors with data, {empty} sensors with no data for this period")
