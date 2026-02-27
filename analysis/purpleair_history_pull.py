#!/usr/bin/env python3
"""
Pull historical PM2.5 from PurpleAir sensors along the Hyde Park plume path.
Round 2: adds 8 sensors to fill gaps in the 5–10 mi range.

Usage:
    export PURPLEAIR_API_KEY="your-read-key-here"
    python purpleair_history_pull_r2.py

Outputs:
    purpleair_plume_history_r2.csv  — hourly PM2.5 for the NEW sensors only
    (merge with purpleair_plume_history.csv for the complete dataset)
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

# ── Round 2 sensors (gap-fillers only) ──
SENSORS = [
    # 9–10 mi — filling the Whiting gap
    (185095, "Oliver (NLCEP)",              9.2, 148),
    (208687, "Whiting City Hall",           9.4, 148),
    (172085, "Peach",                       9.2, 147),
    # 7–9 mi — filling the empty band between Bug (6.9) and Lake George (9.5)
    (193807, "Smeller",                     7.1, 153),
    (193684, "Robin",                       7.4, 155),
    (220577, "MCC06 OUT",                   7.8, 158),
    # 5–7 mi — backfilling for lost Penguin/Tiger
    (175455, "LUC_CARE_13",                 5.6, 160),
    (193673, "Nala",                        6.7, 155),
]

START = datetime(2025, 10, 1, 0, 0, tzinfo=timezone.utc)
END   = datetime(2025, 11, 6, 0, 0, tzinfo=timezone.utc)
CHUNK_DAYS = 14


def fetch_sensor_history(sensor_index, start_ts, end_ts):
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
    chunk_sec = chunk_days * 86400
    s = int(start_dt.timestamp())
    e = int(end_dt.timestamp())
    while s < e:
        yield s, min(s + chunk_sec, e)
        s += chunk_sec


print(f"Round 2: pulling {len(SENSORS)} additional sensors")
print(f"Period: {START.date()} to {END.date()}")
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

        time.sleep(1.1)

    print(f"    → {sensor_rows} total hours\n")

# ── Write CSV ──
outfile = "purpleair_plume_history_r2.csv"
fieldnames = ["time_utc", "sensor_index", "name", "dist_mi", "bearing",
              "pm25_a", "pm25_b", "pm25_avg"]

with open(outfile, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(all_rows)

print(f"Done. {len(all_rows)} rows written to {outfile}")
print()
print("To combine with round 1:")
print("  import pandas as pd")
print("  r1 = pd.read_csv('purpleair_plume_history.csv')")
print("  r2 = pd.read_csv('purpleair_plume_history_r2.csv')")
print("  combined = pd.concat([r1, r2], ignore_index=True)")
print("  combined.to_csv('purpleair_plume_history_combined.csv', index=False)")
