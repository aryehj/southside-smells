#!/usr/bin/env python3
"""
Query PurpleAir API for outdoor sensors along the plume path
from Hyde Park to the Calumet / NW Indiana industrial corridor.

Usage:
    export PURPLEAIR_API_KEY="your-read-key-here"
    python purpleair_sensor_scan.py

Outputs a table of sensors with lat/lon, distance from Hyde Park,
and bearing — so you can assess whether there's enough spatial
coverage for plume-tracking analysis.
"""

import os
import sys
import json
import math
import urllib.request
from datetime import datetime, timezone

API_KEY = os.environ.get("PURPLEAIR_API_KEY", "")
if not API_KEY:
    print("Set PURPLEAIR_API_KEY environment variable first.")
    sys.exit(1)

# ── Reference points ──
HP_LAT, HP_LON = 41.794, -87.590   # Hyde Park (smell report center)

# Bounding box: generous rectangle covering Hyde Park → Gary Works plume path
# NW corner: north/west of Hyde Park
# SE corner: south/east of Gary Works
NW_LAT, NW_LON = 41.85, -87.70
SE_LAT, SE_LON = 41.58, -87.30

EARTH_RADIUS_MI = 3959  # mean radius of Earth in miles

# ── Geometry helpers ──
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

# ── Query PurpleAir API ──
url = (
    f"https://api.purpleair.com/v1/sensors"
    f"?fields=name,latitude,longitude,location_type,last_seen,model"
    f"&location_type=0"          # outdoor only
    f"&max_age=0"                # include all sensors ever seen
    f"&nwlng={NW_LON}&nwlat={NW_LAT}"
    f"&selng={SE_LON}&selat={SE_LAT}"
)

req = urllib.request.Request(url, headers={"X-API-Key": API_KEY})
print(f"Querying PurpleAir for outdoor sensors in bounding box...")
print(f"  NW: {NW_LAT}, {NW_LON}")
print(f"  SE: {SE_LAT}, {SE_LON}")
print()

try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
except urllib.error.HTTPError as e:
    print(f"API error {e.code}: {e.read().decode()}")
    sys.exit(1)

fields = data["fields"]
sensors = data["data"]

# Parse into list of dicts
records = []
for row in sensors:
    d = dict(zip(fields, row))
    lat, lon = d.get("latitude"), d.get("longitude")
    if lat is None or lon is None:
        continue
    dist = haversine(HP_LAT, HP_LON, lat, lon)
    brg = bearing(HP_LAT, HP_LON, lat, lon)
    records.append({
        "sensor_index": d["sensor_index"],
        "name": d.get("name", "?"),
        "lat": lat,
        "lon": lon,
        "dist_mi": round(dist, 1),
        "bearing": round(brg),
        "compass": compass(brg),
        "last_seen": d.get("last_seen"),
        "model": d.get("model", "?"),
    })

records.sort(key=lambda r: r["bearing"])

# ── Print results ──
print(f"Found {len(records)} outdoor sensors in bounding box\n")

if not records:
    print("No sensors found. Check your bounding box or API key.")
    sys.exit(0)

# Header
print(f"{'Index':>7s}  {'Name':<35s} {'Lat':>8s} {'Lon':>9s}  "
      f"{'Dist':>5s} {'Brg':>4s} {'Dir':>4s}  {'Last Seen':<12s}")
print("-" * 105)

for r in records:
    ls = r["last_seen"]
    if ls:
        ls_str = datetime.fromtimestamp(ls, tz=timezone.utc).strftime("%Y-%m-%d")
    else:
        ls_str = "?"
    print(f"{r['sensor_index']:>7d}  {r['name']:<35s} {r['lat']:8.4f} {r['lon']:9.4f}  "
          f"{r['dist_mi']:5.1f} {r['bearing']:4d}° {r['compass']:>4s}  {ls_str}")

# ── Summary by zone ──
print("\n── Coverage summary ──")
se_sensors = [r for r in records if 90 <= r["bearing"] <= 200]
print(f"Sensors in SE arc (90°–200°, plume path): {len(se_sensors)}")

for band_name, lo, hi in [("0–3 mi (Hyde Park)", 0, 3),
                           ("3–6 mi (midpath)", 3, 6),
                           ("6–10 mi (Calumet)", 6, 10),
                           ("10–15 mi (Whiting/E.Chi)", 10, 15),
                           ("15+ mi (Gary)", 15, 50)]:
    in_band = [r for r in se_sensors if lo <= r["dist_mi"] < hi]
    print(f"  {band_name}: {len(in_band)} sensors")

# ── Also dump JSON for later use ──
with open("purpleair_plume_sensors.json", "w") as f:
    json.dump(records, f, indent=2)
print(f"\nFull results saved to purpleair_plume_sensors.json")
