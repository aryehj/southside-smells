#!/usr/bin/env python3
"""
Pull historical PM2.5 from PurpleAir sensors along the Hyde Park plume path.

Fetches hourly-averaged data for selected sensors at varying distances
from Hyde Park, covering the major smell episode dates (Oct 2025).

Usage:
    export PURPLEAIR_API_KEY="your-read-key-here"
    python purpleair_history_pull.py

Outputs:
    purpleair_plume_history.csv  — combined hourly PM2.5 for all sensors
    (one row per sensor per hour, with distance/bearing metadata)

Rate limiting: the PurpleAir API allows ~1 request/second for history.
This script sleeps between requests accordingly.
"""

import os
import sys
import csv
import json
import time
import math
import urllib.request
from datetime import datetime, timezone

API_KEY = os.environ.get("PURPLEAIR_API_KEY", "")
if not API_KEY:
    print("Set PURPLEAIR_API_KEY environment variable first.")
    sys.exit(1)

# ── Sensors to pull ──
# Selected for: active, good bearing alignment (~145–165°), spread across distance bands.
# Ordered near-source → Hyde Park so output reads intuitively.
#
# Adjust this list based on your sensor scan results. The sensor_index
# values below come from the purpleair_plume_sensors.json output.

SENSORS = [
    # (sensor_index, name, dist_mi, bearing) — from scan results
    # ~19 mi — near Gary Works
    (146228, "Progressive Community Church (NLCEP)", 19.1, 135),
    # ~12–13 mi — near SunCoke / BP Whiting
    (185123, "Harborworks (NLCEP)",                 12.9, 146),
    (185079, "Canalport (NLCEP)",                   12.4, 148),
    (203661, "Harrison Elementary",                 12.4, 153),
    # ~10–11 mi
    (220241, "MCC08 OUT",                           11.4, 162),
    (220537, "MCC07 OUT",                           10.4, 164),
    # ~9–10 mi — Whiting / far Calumet
    (146258, "CCSJ (NLCEP)",                         9.9, 150),
    (146110, "Lake George (NLCEP)",                  9.5, 151),
    # ~7–8 mi — SE Chicago
    (193797, "Tiger",                                7.3, 154),
    (193669, "Bug",                                  6.9, 155),
    # ~5–6 mi — midpath
    (193803, "Penguin",                              5.7, 152),
    (193676, "Rooster",                              5.4, 150),
    # ~0 mi — Hyde Park
    (153638, "Purple-HP-1",                          0.1, 152),
]

# ── Date ranges to pull ──
# Cover the full study period plus a buffer day on each side.
# The API uses Unix timestamps.
#
# Major episodes from your notebook:
#   Oct 9–10 (SSW wind, Calumet corridor)
#   Oct 12   (SE wind, biggest cluster)
#   Oct 16–17
#   Oct 25–26
#   Oct 31   (westerly, different source)
#   Nov 3    (westerly)

START = datetime(2025, 10, 1, 0, 0, tzinfo=timezone.utc)
END   = datetime(2025, 11, 6, 0, 0, tzinfo=timezone.utc)

# PurpleAir history API limits to ~14 days per request for hourly data.
# We'll chunk into 14-day windows.
CHUNK_DAYS = 14

# ── API helper ──
def fetch_sensor_history(sensor_index, start_ts, end_ts):
    """Fetch hourly PM2.5 history for one sensor, one time window.
    Returns list of (unix_timestamp, pm25_a, pm25_b) tuples."""

    fields = "pm2.5_atm_a,pm2.5_atm_b"
    url = (
        f"https://api.purpleair.com/v1/sensors/{sensor_index}/history/csv"
        f"?fields={fields}"
        f"&start_timestamp={start_ts}"
        f"&end_timestamp={end_ts}"
        f"&average=60"  # hourly average
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


# ── Main ──
print(f"Pulling hourly PM2.5 for {len(SENSORS)} sensors")
print(f"Period: {START.date()} to {END.date()}")
print(f"Chunks of {CHUNK_DAYS} days each")
print()

all_rows = []

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
            # Average channels A and B for the best PM2.5 estimate
            try:
                a = float(pm_a) if pm_a else None
                b = float(pm_b) if pm_b else None
                if a is not None and b is not None:
                    pm25 = round((a + b) / 2, 2)
                elif a is not None:
                    pm25 = round(a, 2)
                elif b is not None:
                    pm25 = round(b, 2)
                else:
                    pm25 = ""
            except ValueError:
                pm25 = ""

            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            all_rows.append({
                "time_utc": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "sensor_index": sensor_index,
                "name": name,
                "dist_mi": dist_mi,
                "bearing": bearing,
                "pm25_a": pm_a,
                "pm25_b": pm_b,
                "pm25_avg": pm25,
            })

        # Rate limit: ~1 req/sec
        time.sleep(1.1)

    print(f"    → {sensor_rows} total hours\n")

# ── Write CSV ──
outfile = "purpleair_plume_history.csv"
fieldnames = ["time_utc", "sensor_index", "name", "dist_mi", "bearing",
              "pm25_a", "pm25_b", "pm25_avg"]

with open(outfile, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(all_rows)

print(f"Done. {len(all_rows)} rows written to {outfile}")
print()
print("Next steps:")
print("  1. Load this CSV alongside your smell reports + weather data")
print("  2. For each episode, plot PM2.5 by distance over time")
print("     (nearer-source sensors should spike first if plume is real)")
print("  3. Check channel A vs B agreement — large divergence = suspect data")
