#!/usr/bin/env python3
"""
Fetch PM2.5 and NO₂ hourly data from the Chicago Open Air network
(277 Clarity Node-S sensors) for the Hyde Park smell study period
October–November 2025.

Data source: Chicago Open Data Portal
Dataset:     Open Air Chicago Hour Aggregations (ID: di9s-96ws)
API:         Socrata SODA 2.1 — https://data.cityofchicago.org/resource/di9s-96ws.json

No API key required. Set CHICAGO_APP_TOKEN env var to raise rate limits (optional).

Usage:
    python code/chicago_openair_pull.py

Outputs:
    data/chicago_openair_history.csv

Filters to sensors in the SE arc (bearing 90°–200°, within 25 miles of Hyde Park)
to focus on the Calumet corridor plume path. Prints available column names on the
first run so you can verify field mappings against the live schema.
"""

import os
import sys
import csv
import json
import math
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone

# ── Reference point ──
HP_LAT, HP_LON = 41.794, -87.590   # Hyde Park (smell report center)

# ── Study period ──
START_STR = "2025-10-01T00:00:00"
END_STR   = "2025-11-07T00:00:00"

# ── SE corridor filter ──
SE_BEARING_MIN = 90
SE_BEARING_MAX = 200
MAX_DIST_MI    = 25.0

EARTH_RADIUS_MI = 3959

# ── Socrata API ──
BASE_URL   = "https://data.cityofchicago.org/resource/di9s-96ws.json"
APP_TOKEN  = os.environ.get("CHICAGO_APP_TOKEN", "")
PAGE_SIZE  = 10000   # rows per request; Socrata hard limit is 50000
PAGE_DELAY = 0.5     # seconds between paginated requests

# ── Output file ──
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT  = os.path.dirname(SCRIPT_DIR)
OUT_FILE   = os.path.join(REPO_ROOT, "data", "chicago_openair_history.csv")


# ── Geometry helpers (identical signatures to purpleair_sensor_scan.py) ──

def haversine(lat1, lon1, lat2, lon2):
    """Great-circle distance in miles."""
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return EARTH_RADIUS_MI * 2 * math.asin(math.sqrt(a))


def bearing(lat1, lon1, lat2, lon2):
    """Compass bearing in degrees (0–360) from point 1 to point 2."""
    dlon = math.radians(lon2 - lon1)
    y = math.sin(dlon) * math.cos(math.radians(lat2))
    x = (math.cos(math.radians(lat1)) * math.sin(math.radians(lat2))
         - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.cos(dlon))
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def compass(deg):
    """Convert bearing in degrees to 16-point compass label."""
    sectors = ['N','NNE','NE','ENE','E','ESE','SE','SSE',
               'S','SSW','SW','WSW','W','WNW','NW','NNW']
    return sectors[int((deg + 11.25) / 22.5) % 16]


# ── Socrata API helper ──

def soda_get(params):
    """GET request to Socrata SODA 2.1 API. Returns parsed JSON list or None."""
    url = BASE_URL + "?" + urllib.parse.urlencode(params)
    headers = {"Accept": "application/json"}
    if APP_TOKEN:
        headers["X-App-Token"] = APP_TOKEN
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {e.read().decode()[:300]}")
        return None
    except Exception as e:
        print(f"  Request error: {e}")
        return None


def find_col(candidates, available):
    """Return the first candidate that appears in available; None if none match."""
    for c in candidates:
        if c in available:
            return c
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Schema discovery
# ─────────────────────────────────────────────────────────────────────────────

print("Step 1: Discovering dataset schema...")
# Use the Socrata metadata endpoint — unlike a data row, it lists every column
# even when values are null in all rows, which is common for sparse fields like NO₂.
DATASET_ID   = BASE_URL.split("/resource/")[1].replace(".json", "")
meta_url     = f"https://data.cityofchicago.org/api/views/{DATASET_ID}.json"
meta_headers = {"Accept": "application/json"}
if APP_TOKEN:
    meta_headers["X-App-Token"] = APP_TOKEN
try:
    meta_req = urllib.request.Request(meta_url, headers=meta_headers)
    with urllib.request.urlopen(meta_req, timeout=30) as resp:
        meta = json.loads(resp.read())
    all_cols = [c["fieldName"] for c in meta.get("columns", [])
                if not c["fieldName"].startswith(":@")]
except Exception as e:
    print(f"Metadata endpoint failed ({e}); falling back to data-row discovery.")
    sample = soda_get({"$limit": 1, "$offset": 0})
    if not sample or not isinstance(sample, list) or len(sample) == 0:
        print("Could not reach Chicago Open Data Portal. Check your network connection.")
        sys.exit(1)
    all_cols = [k for k in sample[0].keys() if not k.startswith(":@")]

print(f"Available columns ({len(all_cols)}):")
for c in all_cols:
    print(f"  {c}")
print()

# Map logical fields to actual column names.
# Socrata converts special characters (e.g. "." → "_") in some export formats;
# we try both variants so the script works regardless of API version.
COL_TIME   = find_col(["startofperiod",
                        "measurement_time", "time", "timestamp",
                        "date_time", "start_time", "hour"], all_cols)
COL_LAT    = find_col(["latitude", "lat", "location_latitude",
                        "sensor_latitude"], all_cols)
COL_LON    = find_col(["longitude", "lon", "long", "location_longitude",
                        "sensor_longitude"], all_cols)
COL_SENSOR = find_col(["datasourceid",
                        "sensor_id", "sensor_index", "device_id",
                        "sensorid", "node_id", "id"], all_cols)
COL_NAME   = find_col(["sensor_name", "name", "location_name",
                        "device_name", "site_name"], all_cols)
COL_PM25   = find_col(["pm2_5concmass1hourmean_value",
                        "pm2_5concmass1hourmean_raw",
                        "pm2_5_value", "pm25_value", "pm2_5",
                        "pm25", "pm2_5_avg", "pm25_avg",
                        "value_pm2_5", "pm2_5_calibrated"], all_cols)
COL_NO2    = find_col(["no2conc1hourmean_value",
                        "no2conc1hourmean_raw",
                        "no2_value", "no2", "no2_ppb",
                        "value_no2", "no2_calibrated"], all_cols)

print("Column mapping:")
print(f"  timestamp   → {COL_TIME}")
print(f"  latitude    → {COL_LAT}")
print(f"  longitude   → {COL_LON}")
print(f"  sensor_id   → {COL_SENSOR}")
print(f"  sensor_name → {COL_NAME or '(not found — will use sensor_id)'}")
print(f"  PM2.5       → {COL_PM25 or '(not found)'}")
print(f"  NO2         → {COL_NO2 or '(not found)'}")
print()

missing = [label for label, col in [("timestamp", COL_TIME), ("latitude", COL_LAT),
                                      ("longitude", COL_LON), ("sensor_id", COL_SENSOR)]
           if col is None]
if missing:
    print(f"ERROR: Could not identify required columns: {missing}")
    print("Update the find_col() candidate lists above to match the column names printed above.")
    sys.exit(1)

if not COL_PM25 and not COL_NO2:
    print("ERROR: Neither PM2.5 nor NO₂ columns found. Cannot proceed.")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Enumerate SE-arc sensors
# ─────────────────────────────────────────────────────────────────────────────

print("Step 2: Enumerating sensor locations within the study period...")

# Query unique (sensor_id, lat, lon[, name]) combinations appearing in the
# date range. $group by these columns to get one representative row per sensor.
group_cols = [COL_SENSOR, COL_LAT, COL_LON]
if COL_NAME:
    group_cols.append(COL_NAME)
group_str = ",".join(group_cols)

sensor_rows = soda_get({
    "$select": group_str,
    "$where": (f"{COL_TIME} >= '{START_STR}' AND {COL_TIME} < '{END_STR}'"
               f" AND {COL_LAT} IS NOT NULL AND {COL_LON} IS NOT NULL"),
    "$group":  group_str,
    "$limit":  5000,
})

if not sensor_rows:
    print("Failed to enumerate sensors. The $group query may not be supported. "
          "Try fetching without $group (comment out the $group parameter).")
    sys.exit(1)

print(f"Found {len(sensor_rows)} unique sensor-location records in study period.")

sensors = {}   # sensor_id (str) → metadata dict
for row in sensor_rows:
    sid = str(row.get(COL_SENSOR, "")).strip()
    lat_raw = row.get(COL_LAT)
    lon_raw = row.get(COL_LON)
    if not sid or lat_raw is None or lon_raw is None:
        continue
    try:
        lat, lon = float(lat_raw), float(lon_raw)
    except (TypeError, ValueError):
        continue

    dist = haversine(HP_LAT, HP_LON, lat, lon)
    brg  = bearing(HP_LAT, HP_LON, lat, lon)

    if dist > MAX_DIST_MI:
        continue
    if not (SE_BEARING_MIN <= brg <= SE_BEARING_MAX):
        continue

    name = str(row.get(COL_NAME, sid)).strip() if COL_NAME else sid
    sensors[sid] = {
        "sensor_id": sid,
        "name":      name,
        "lat":       lat,
        "lon":       lon,
        "dist_mi":   round(dist, 1),
        "bearing":   round(brg),
        "compass":   compass(brg),
    }

if not sensors:
    print(f"No sensors found in the SE arc (bearing {SE_BEARING_MIN}°–{SE_BEARING_MAX}°, "
          f"within {MAX_DIST_MI} mi).")
    print("Check that the bounding area covers Chicago's South Side and SE suburbs.")
    sys.exit(1)

print(f"\nSE-arc sensors (bearing {SE_BEARING_MIN}°–{SE_BEARING_MAX}°, ≤ {MAX_DIST_MI} mi):")
print(f"  Total: {len(sensors)}")
for lo, hi, label in [(0,3,'0–3 mi'),(3,6,'3–6 mi'),(6,10,'6–10 mi'),
                       (10,15,'10–15 mi'),(15,25,'15–25 mi')]:
    n = sum(1 for s in sensors.values() if lo <= s['dist_mi'] < hi)
    print(f"    {label}: {n} sensors")
print()


# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Fetch hourly time-series data
# ─────────────────────────────────────────────────────────────────────────────

print(f"Step 3: Fetching hourly data for study period ({START_STR[:10]} to {END_STR[:10]})...")
print(f"  Page size: {PAGE_SIZE} rows. Delay between pages: {PAGE_DELAY}s.")
if not APP_TOKEN:
    print("  Tip: set CHICAGO_APP_TOKEN env var for higher rate limits.")
print()

where_clause = (
    f"{COL_TIME} >= '{START_STR}' AND {COL_TIME} < '{END_STR}'"
    f" AND {COL_LAT} IS NOT NULL"
)

select_parts = [COL_TIME, COL_SENSOR, COL_LAT, COL_LON]
if COL_PM25:
    select_parts.append(COL_PM25)
if COL_NO2:
    select_parts.append(COL_NO2)
data_select = ",".join(select_parts)

all_rows = []
offset   = 0
page_num = 0

while True:
    page_num += 1
    rows = soda_get({
        "$select": data_select,
        "$where":  where_clause,
        "$order":  f"{COL_TIME},{COL_SENSOR}",
        "$limit":  PAGE_SIZE,
        "$offset": offset,
    })

    if rows is None:
        print(f"  Page {page_num}: request failed, stopping.")
        break
    if len(rows) == 0:
        print(f"  Page {page_num}: no more rows.")
        break

    kept = 0
    for row in rows:
        sid = str(row.get(COL_SENSOR, "")).strip()
        if sid not in sensors:
            continue

        s       = sensors[sid]
        ts_raw  = row.get(COL_TIME, "")
        pm25_raw = row.get(COL_PM25, "") if COL_PM25 else ""
        no2_raw  = row.get(COL_NO2,  "") if COL_NO2  else ""

        # Normalize timestamp to "YYYY-MM-DD HH:MM:SS" UTC string.
        # SODA returns ISO 8601 like "2025-10-01T01:00:00.000" or with TZ suffix.
        ts_utc = ts_raw[:19].replace("T", " ") if ts_raw else ""

        def safe_float(v):
            try:
                return round(float(v), 4) if v not in (None, "", "null", "NaN") else None
            except (ValueError, TypeError):
                return None

        all_rows.append({
            "time_utc":   ts_utc,
            "sensor_id":  sid,
            "name":       s["name"],
            "lat":        s["lat"],
            "lon":        s["lon"],
            "dist_mi":    s["dist_mi"],
            "bearing":    s["bearing"],
            "pm25_value": safe_float(pm25_raw),
            "no2_value":  safe_float(no2_raw),
        })
        kept += 1

    print(f"  Page {page_num}: {len(rows)} rows fetched, {kept} in SE arc "
          f"(total so far: {len(all_rows)})")

    if len(rows) < PAGE_SIZE:
        break   # last page

    offset += PAGE_SIZE
    time.sleep(PAGE_DELAY)

print(f"\nTotal rows collected: {len(all_rows)}")


# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Write output CSV
# ─────────────────────────────────────────────────────────────────────────────

if not all_rows:
    print("No data rows collected. Check the date range and sensor filter settings.")
    sys.exit(1)

fieldnames = ["time_utc", "sensor_id", "name", "lat", "lon",
              "dist_mi", "bearing", "pm25_value", "no2_value"]

os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
with open(OUT_FILE, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(all_rows)

# ── Summary ──
sensors_with_data = {r["sensor_id"] for r in all_rows}
pm25_valid = sum(1 for r in all_rows if r["pm25_value"] is not None)
no2_valid  = sum(1 for r in all_rows if r["no2_value"]  is not None)

print(f"\nWrote {len(all_rows)} rows to {OUT_FILE}")
print(f"Sensors with data:   {len(sensors_with_data)}")
print(f"Valid PM2.5 readings: {pm25_valid} "
      f"({pm25_valid / len(all_rows):.0%})")
print(f"Valid NO₂ readings:   {no2_valid} "
      f"({no2_valid / len(all_rows):.0%})")
print()
print("Next step: open code/hyde_park_smell_analysis.ipynb and run Section 6.")
