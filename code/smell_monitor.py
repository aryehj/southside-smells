#!/usr/bin/env python3
"""
Southside Smells — Air Quality Monitor

Polls Open-Meteo (wind) and PurpleAir (PM2.5) to assess the risk of
industrial odor reaching Hyde Park from the Calumet corridor.

Outputs:
  - data/monitor_history.json   (rolling 48-hour reading log)
  - docs/index.html             (static status page for GitHub Pages)
  - (optional) email alert when risk transitions to High / Active Alert

Usage:
    export PURPLEAIR_API_KEY="your-read-key-here"
    python code/smell_monitor.py

Set SMTP env vars for email alerts (all optional):
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS,
    ALERT_EMAIL_FROM, ALERT_EMAIL_TO
"""

import json
import math
import os
import smtplib
import sys
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Missing dependency: pip install requests")

# ── Paths (relative to repo root) ──
REPO_ROOT = Path(__file__).resolve().parent.parent
HISTORY_PATH = REPO_ROOT / "data" / "monitor_history.json"
HTML_PATH = REPO_ROOT / "docs" / "index.html"
MAX_HISTORY = 48  # entries (48 hours at hourly polling)

# ── Reference point ──
HP_LAT, HP_LON = 41.794, -87.590  # Hyde Park

# ── Sensors: 5 representative stations along the SE plume corridor ──
# (sensor_index, name, distance_mi, bearing_deg)
SENSORS = [
    (146228, "Progressive Community Church", 19.1, 135),  # source (far)
    (185079, "Canalport",                    12.4, 148),  # source (near)
    (193669, "Bug",                           6.9, 155),  # mid-path
    (193676, "Rooster",                       5.4, 150),  # mid-path (close)
    (153638, "Purple-HP-1",                   0.1, 152),  # Hyde Park
]

SENSOR_IDS = [s[0] for s in SENSORS]
SOURCE_BEARING_CENTER = 143  # degrees — center of facility bearings (131-156)


# ── Geometry helpers (consistent with purpleair_sensor_scan.py) ──

def compass(deg):
    """Convert bearing in degrees to 8-point compass label."""
    sectors = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return sectors[int((deg + 22.5) / 45) % 8]


# ── Data fetching ──

def fetch_weather():
    """Get current wind and temperature from Open-Meteo (free, no key)."""
    url = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude=41.794&longitude=-87.59"
        "&current=wind_direction_10m,wind_speed_10m,temperature_2m"
        "&wind_speed_unit=mph&temperature_unit=fahrenheit"
        "&timezone=America/Chicago"
    )
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    current = resp.json()["current"]
    return {
        "wind_dir": current["wind_direction_10m"],
        "wind_speed_mph": current["wind_speed_10m"],
        "temperature_f": current["temperature_2m"],
    }


def fetch_pm25(api_key):
    """Get latest PM2.5 from the 5 key sensors via PurpleAir bulk endpoint."""
    ids_str = ",".join(str(i) for i in SENSOR_IDS)
    url = (
        "https://api.purpleair.com/v1/sensors"
        f"?fields=name,pm2.5_10minute,pm2.5_60minute"
        f"&show_only={ids_str}"
    )
    resp = requests.get(url, headers={"X-API-Key": api_key}, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    fields = data["fields"]
    readings = {}
    for row in data["data"]:
        rec = dict(zip(fields, row))
        sid = rec["sensor_index"]
        # Prefer 10-minute average; fall back to 60-minute
        pm25 = rec.get("pm2.5_10minute")
        if pm25 is None:
            pm25 = rec.get("pm2.5_60minute")
        readings[sid] = pm25

    # Build result keyed by sensor index, preserving our SENSORS order
    result = []
    for sid, name, dist, brg in SENSORS:
        result.append({
            "sensor_index": sid,
            "name": name,
            "dist_mi": dist,
            "bearing": brg,
            "pm25": readings.get(sid),
        })
    return result


# ── Risk scoring ──

def compute_risk(wind_dir, wind_speed_mph, sensor_readings):
    """
    Compute smell risk score (0-100) based on wind direction, speed, and PM2.5.

    Returns (risk_score, risk_level, eta_minutes).

    Both wind alignment AND elevated source PM2.5 are needed for high scores.
    Wind alone (clean air) caps at Moderate. PM2.5 alone (wrong wind) scores Low.

    Scoring breakdown:
      - Wind direction: 0-60 pts (primary predictor; SE wind = highest)
        Capped at 30 if source PM2.5 is clean (<10 µg/m³)
      - PM2.5 at source: 0-30 pts (only counted when wind is from SE)
      - Source-to-local gradient: 0-10 pts (only counted when wind is from SE)
    """
    # -- Wind direction component (0-60 points) --
    # 62% of smell reports occurred during SE winds (90-180 degrees).
    # Sweet spot is ~143 degrees (center of facility bearings 131-156).
    wind_aligned = False
    wind_points = 0.0
    if 90 <= wind_dir <= 200:
        wind_aligned = True
        angular_dist = abs(wind_dir - SOURCE_BEARING_CENTER)
        wind_points = max(0, 60 - angular_dist * (60 / 45))
        # Calm winds (<2 mph) barely transport anything
        if wind_speed_mph < 2:
            wind_points *= 0.3

    # -- PM2.5 at source --
    source_vals = [s["pm25"] for s in sensor_readings[:2] if s["pm25"] is not None]
    source_pm25 = max(source_vals) if source_vals else 0

    local_vals = [s["pm25"] for s in sensor_readings[-1:] if s["pm25"] is not None]
    local_pm25 = local_vals[0] if local_vals else 0

    # Cap wind points if air is clean — SE wind alone is only a "watch"
    if source_pm25 < 10:
        wind_points = min(wind_points, 30)

    # -- PM2.5 component (0-30 points, only when wind is aligned) --
    pm25_points = 0
    if wind_aligned:
        if source_pm25 >= 35:
            pm25_points = 30
        elif source_pm25 >= 20:
            pm25_points = 20
        elif source_pm25 >= 10:
            pm25_points = 10

    # -- Gradient component (0-10 points, only when wind is aligned) --
    gradient_points = 0
    if wind_aligned and source_pm25 > 0:
        ratio = source_pm25 / max(local_pm25, 1)
        if ratio > 2.0:
            gradient_points = 10
        elif ratio > 1.5:
            gradient_points = 5

    risk_score = int(wind_points + pm25_points + gradient_points)

    if risk_score >= 70:
        level = "Active Alert"
    elif risk_score >= 45:
        level = "High"
    elif risk_score >= 25:
        level = "Moderate"
    else:
        level = "Low"

    # ETA: plume transport speed is roughly 30% of surface wind speed
    eta_minutes = None
    if wind_aligned and wind_speed_mph > 2:
        transport_mph = wind_speed_mph * 0.3
        if transport_mph > 0:
            eta_minutes = int(12 / transport_mph * 60)  # 12 miles from source

    return risk_score, level, eta_minutes


# ── History management ──

def load_history():
    if HISTORY_PATH.exists():
        try:
            return json.loads(HISTORY_PATH.read_text())
        except (json.JSONDecodeError, IOError):
            return []
    return []


def save_history(history):
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, indent=2) + "\n")


def previous_risk_level(history):
    """Return the risk level from the most recent reading, or 'Low'."""
    if history:
        return history[-1].get("risk_level", "Low")
    return "Low"


# ── Email alerts ──

def send_alert_email(reading):
    """Send email alert if SMTP env vars are configured. Silently skip if not."""
    host = os.environ.get("SMTP_HOST")
    to_addr = os.environ.get("ALERT_EMAIL_TO")
    from_addr = os.environ.get("ALERT_EMAIL_FROM")
    if not (host and to_addr and from_addr):
        return

    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASS", "")

    level = reading["risk_level"]
    score = reading["risk_score"]
    wind = reading["wind_dir"]
    eta = reading.get("eta_minutes")

    subject = f"Southside Smells: {level} (score {score})"
    body_lines = [
        f"Risk level: {level} (score {score}/100)",
        f"Wind: {wind}° ({compass(wind)}) at {reading['wind_speed_mph']:.0f} mph",
        f"Temperature: {reading['temperature_f']:.1f}°F",
        "",
    ]
    if eta:
        hours = eta // 60
        mins = eta % 60
        body_lines.append(f"Estimated plume arrival: ~{hours}h {mins}m")
        body_lines.append("")

    body_lines.append("Sensor readings (PM2.5 µg/m³):")
    for s in reading["sensors"]:
        val = f"{s['pm25']:.1f}" if s["pm25"] is not None else "n/a"
        body_lines.append(f"  {s['name']} ({s['dist_mi']} mi): {val}")

    msg = MIMEText("\n".join(body_lines))
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr

    try:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.starttls()
            if user and password:
                server.login(user, password)
            server.send_message(msg)
        print(f"  Alert email sent to {to_addr}")
    except Exception as e:
        print(f"  Email send failed: {e}")


# ── HTML generation ──

RISK_COLORS = {
    "Low": ("#22c55e", "#f0fdf4"),         # green
    "Moderate": ("#eab308", "#fefce8"),     # yellow
    "High": ("#f97316", "#fff7ed"),         # orange
    "Active Alert": ("#ef4444", "#fef2f2"), # red
}


def pm25_color(val):
    """Return a CSS color for a PM2.5 value (EPA-ish breakpoints)."""
    if val is None:
        return "#9ca3af"
    if val < 12:
        return "#22c55e"
    if val < 35:
        return "#eab308"
    if val < 55:
        return "#f97316"
    return "#ef4444"


def sparkline_svg(history, width=600, height=80):
    """Generate an inline SVG sparkline of risk scores over time."""
    scores = [h.get("risk_score", 0) for h in history]
    if len(scores) < 2:
        return ""
    max_score = max(max(scores), 1)
    n = len(scores)
    points = []
    for i, s in enumerate(scores):
        x = i / (n - 1) * width
        y = height - (s / max_score * (height - 10)) - 5
        points.append(f"{x:.1f},{y:.1f}")

    # Color the line based on current risk
    current = scores[-1]
    if current >= 70:
        color = "#ef4444"
    elif current >= 45:
        color = "#f97316"
    elif current >= 25:
        color = "#eab308"
    else:
        color = "#22c55e"

    # Threshold lines
    thresholds = ""
    for threshold, label in [(25, "Mod"), (45, "High"), (70, "Alert")]:
        ty = height - (threshold / max_score * (height - 10)) - 5
        if 5 < ty < height - 5:
            thresholds += (
                f'<line x1="0" y1="{ty:.1f}" x2="{width}" y2="{ty:.1f}" '
                f'stroke="#e5e7eb" stroke-width="1" stroke-dasharray="4,4"/>'
                f'<text x="{width - 2}" y="{ty - 3:.1f}" fill="#9ca3af" '
                f'font-size="10" text-anchor="end">{label}</text>'
            )

    return (
        f'<svg viewBox="0 0 {width} {height}" '
        f'style="width:100%;max-width:{width}px;height:{height}px">'
        f'{thresholds}'
        f'<polyline points="{" ".join(points)}" '
        f'fill="none" stroke="{color}" stroke-width="2" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{points[-1].split(",")[0]}" cy="{points[-1].split(",")[1]}" '
        f'r="4" fill="{color}"/>'
        f'</svg>'
    )


def wind_arrow_svg(degrees):
    """Small SVG arrow showing wind direction (points the way wind blows TO)."""
    # Meteorological convention: wind_dir is where it comes FROM.
    # Arrow should point in the direction it's blowing (opposite).
    to_deg = (degrees + 180) % 360
    return (
        f'<svg viewBox="0 0 40 40" style="width:40px;height:40px">'
        f'<g transform="rotate({to_deg},20,20)">'
        f'<line x1="20" y1="34" x2="20" y2="6" stroke="#1e293b" stroke-width="2.5"/>'
        f'<polyline points="12,14 20,6 28,14" fill="none" '
        f'stroke="#1e293b" stroke-width="2.5" stroke-linejoin="round"/>'
        f'</g></svg>'
    )


def generate_html(reading, history):
    """Generate the static status page."""
    level = reading["risk_level"]
    badge_color, _ = RISK_COLORS[level]
    wind_dir = reading["wind_dir"]
    wind_speed = reading["wind_speed_mph"]
    temp = reading["temperature_f"]
    eta = reading.get("eta_minutes")
    timestamp = reading["timestamp"]

    # Wind alignment and compass label for explanatory text
    wind_aligned = 90 <= wind_dir <= 200
    compass_label = compass(wind_dir)

    # ETA box — always rendered; active (green) when SE wind, inactive (grey) otherwise
    if eta:
        hours = eta // 60
        mins = eta % 60
        time_str = f"{hours}h {mins:02d}m" if hours else f"{mins}m"
        eta_html = (
            f'<div class="eta-box active">'
            f'<div class="eta-label">Estimated time for Calumet emissions to reach Hyde Park</div>'
            f'<div class="eta-value">~{time_str}</div>'
            f'<div class="eta-note">Based on current wind speed ({wind_speed:.0f}&nbsp;mph)'
            f' and ~12&nbsp;mi to nearest corridor sources.</div>'
            f'</div>'
        )
    else:
        eta_html = (
            f'<div class="eta-box inactive">'
            f'<div class="eta-label">Estimated time for Calumet emissions to reach Hyde Park</div>'
            f'<div class="eta-value">N/A</div>'
            f'<div class="eta-note">Wind is from the {compass_label} —'
            f' industrial corridor emissions are not heading toward Hyde Park right now.</div>'
            f'</div>'
        )

    # Wind card explanation — conditional on direction
    if wind_aligned:
        wind_explain = (
            f'<p class="explain"><span class="warn">Wind is from the'
            f' {compass_label} ({wind_dir:.0f}°) — carrying Calumet industrial'
            f' emissions toward Hyde Park.</span> The corridor sits 10–18 miles'
            f' to the southeast; southeasterly winds (roughly 90°–180°) are the'
            f' key risk signal for neighborhood odors.</p>'
        )
    else:
        wind_explain = (
            f'<p class="explain"><span class="ok">Wind is currently from the'
            f' {compass_label} ({wind_dir:.0f}°) — emissions are not heading'
            f' toward Hyde Park right now.</span> The risk rises when wind shifts'
            f' to southeasterly (roughly 90°–180°), carrying Calumet corridor'
            f' emissions 10–18 miles northwest into the neighborhood.</p>'
        )

    # Sensor rows
    sensor_rows = ""
    for s in reading["sensors"]:
        val = s["pm25"]
        val_str = f"{val:.1f}" if val is not None else "n/a"
        color = pm25_color(val)
        sensor_rows += (
            f'<tr>'
            f'<td>{s["name"]}</td>'
            f'<td>{s["dist_mi"]} mi</td>'
            f'<td style="color:{color};font-weight:600">{val_str}</td>'
            f'</tr>'
        )

    # PM2.5 card — only shown when wind is southeasterly
    if wind_aligned:
        pm25_card_html = (
            f'<div class="card">'
            f'<h2>PM2.5 Sensor Readings (µg/m³)</h2>'
            f'<p class="explain no-border">These sensors form a chain between the Calumet industrial\n'
            f'    corridor and Hyde Park. Fine particulate matter (PM2.5) is a\n'
            f'    <span class="warn">proxy for industrial pollutants traveling through the air you are\n'
            f'    breathing, or about to breathe</span> — elevated readings that appear first at distant\n'
            f'    sensors and then at closer ones signal an arriving plume. US&nbsp;EPA considers levels\n'
            f'    above 12&nbsp;µg/m³ unhealthy for sensitive groups; above 35&nbsp;µg/m³ unhealthy\n'
            f'    for everyone.</p>'
            f'<table>'
            f'<tr><th>Sensor</th><th>Distance</th><th>PM2.5</th></tr>'
            f'{sensor_rows}'
            f'</table>'
            f'</div>'
        )
    else:
        pm25_card_html = ""

    sparkline = sparkline_svg(history)
    sparkline_section = ""
    if sparkline and wind_aligned:
        # Time labels for sparkline
        if len(history) >= 2:
            oldest = history[0].get("timestamp", "")[:16]
            newest = history[-1].get("timestamp", "")[:16]
            sparkline_section = (
                f'<div class="card">'
                f'<h2>Risk Score — Last {len(history)} Hours</h2>'
                f'{sparkline}'
                f'<div style="display:flex;justify-content:space-between;'
                f'font-size:12px;color:#6b7280;margin-top:4px">'
                f'<span>{oldest}</span><span>{newest}</span>'
                f'</div></div>'
            )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="600">
<title>Southside Smells Monitor</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
         background:#f8fafc; color:#1e293b; line-height:1.5; padding:16px; }}
  .container {{ max-width:640px; margin:0 auto; }}
  .experiment-banner {{ background:#fef9c3; border-left:4px solid #eab308;
    border-radius:6px; padding:10px 14px; margin-bottom:18px;
    font-size:13px; color:#713f12; line-height:1.5; }}
  .experiment-banner strong {{ font-weight:600; }}
  h1 {{ font-size:22px; margin-bottom:2px; }}
  .subtitle {{ color:#64748b; font-size:14px; margin-bottom:6px; }}
  .last-updated {{ font-size:12px; color:#94a3b8; margin-bottom:18px; }}
  .last-updated time {{ font-weight:500; color:#64748b; }}
  .badge {{ display:inline-block; padding:12px 24px; border-radius:12px;
            font-size:28px; font-weight:700; color:#fff;
            background:{badge_color}; margin-bottom:16px; }}
  .score {{ font-size:14px; font-weight:400; opacity:0.9; }}
  .card {{ background:#fff; border:1px solid #e2e8f0; border-radius:10px;
           padding:16px; margin-bottom:14px; }}
  .card h2 {{ font-size:15px; color:#64748b; margin-bottom:10px; }}
  .wind-row {{ display:flex; align-items:center; gap:12px; margin-bottom:10px; }}
  .wind-detail {{ font-size:15px; }}
  .wind-detail strong {{ font-size:20px; }}
  .explain {{ font-size:13px; color:#64748b; border-top:1px solid #f1f5f9;
              padding-top:10px; line-height:1.6; }}
  .explain.no-border {{ border-top:none; padding-top:0; margin-bottom:12px; }}
  .explain .ok   {{ color:#15803d; font-weight:500; }}
  .explain .warn {{ color:#b45309; font-weight:500; }}
  .eta-box {{ border-radius:10px; padding:12px 16px; margin-bottom:14px; text-align:center; }}
  .eta-box.active   {{ background:#f0fdf4; border:2px solid #22c55e; }}
  .eta-box.inactive {{ background:#f8fafc; border:2px solid #cbd5e1; }}
  .eta-label {{ font-size:11px; text-transform:uppercase; letter-spacing:0.07em;
                color:#94a3b8; margin-bottom:4px; }}
  .eta-value {{ font-size:24px; font-weight:700; }}
  .eta-box.active   .eta-value {{ color:#15803d; }}
  .eta-box.inactive .eta-value {{ color:#94a3b8; }}
  .eta-note  {{ font-size:12px; color:#94a3b8; margin-top:5px; line-height:1.5; }}
  table {{ width:100%; border-collapse:collapse; font-size:14px; }}
  th {{ text-align:left; color:#64748b; font-weight:500; padding:6px 8px;
       border-bottom:1px solid #e2e8f0; }}
  td {{ padding:6px 8px; border-bottom:1px solid #f1f5f9; }}
  .footer {{ margin-top:20px; font-size:12px; color:#94a3b8; text-align:center; }}
  .footer a {{ color:#64748b; }}
</style>
</head>
<body>
<div class="container">
  <div class="experiment-banner">
    <strong>Prototype under active development.</strong>
    Data may be incomplete, delayed, or inaccurate. This tool is a community
    experiment — do not rely on it for health or safety decisions.
  </div>

  <h1>Southside Smells Monitor</h1>
  <p class="subtitle">Hyde Park air quality — industrial odor risk from the Calumet corridor</p>
  <p class="last-updated">Last updated <time datetime="{timestamp}">{timestamp}</time></p>

  <div class="badge">{level} <span class="score">{reading["risk_score"]}/100</span></div>

  {eta_html}

  <div class="card">
    <h2>Current Wind</h2>
    <div class="wind-row">
      {wind_arrow_svg(wind_dir)}
      <div class="wind-detail">
        <strong>{wind_dir}° {compass(wind_dir)}</strong><br>
        {wind_speed:.0f} mph &middot; {temp:.1f}°F
      </div>
    </div>
    {wind_explain}
  </div>

  {pm25_card_html}

  {sparkline_section}

  <div class="footer">
    <p>Data: <a href="https://open-meteo.com/">Open-Meteo</a> &middot;
       <a href="https://www.purpleair.com/">PurpleAir</a></p>
    <p><a href="https://github.com/aryehj/southside-smells">Full analysis &amp; methodology</a></p>
  </div>
</div>
</body>
</html>"""

    HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
    HTML_PATH.write_text(html)


# ── Main ──

def main():
    print("Southside Smells Monitor")
    print("=" * 40)

    # Always fetch wind — Open-Meteo requires no API key.
    print("Fetching weather from Open-Meteo...")
    weather = fetch_weather()
    wind_dir = weather["wind_dir"]
    print(f"  Wind: {wind_dir}° {compass(wind_dir)} "
          f"at {weather['wind_speed_mph']:.0f} mph")
    print(f"  Temp: {weather['temperature_f']:.1f}°F")

    now = datetime.now(timezone(timedelta(hours=-6)))  # Chicago / CST offset
    is_se = 90 <= wind_dir <= 180

    # ── Non-SE branch: update timestamp + wind display only ──────────────────
    if not is_se:
        history = load_history()
        if history:
            last = history[-1]
            ghost = {
                "timestamp":      now.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "wind_dir":       weather["wind_dir"],
                "wind_speed_mph": weather["wind_speed_mph"],
                "temperature_f":  weather["temperature_f"],
                "risk_score":     last["risk_score"],
                "risk_level":     last["risk_level"],
                "eta_minutes":    None,
                "sensors":        last["sensors"],
            }
            generate_html(ghost, history)
            print(f"\nNon-SE winds ({compass(wind_dir)}) — "
                  "updated wind/timestamp only, skipped PurpleAir.")
        else:
            print(f"\nNon-SE winds ({compass(wind_dir)}) — "
                  "no history yet, skipping HTML update.")
        print(f"Status page: {HTML_PATH}")
        print("Done.")
        return

    # ── SE branch: full pipeline ──────────────────────────────────────────────
    api_key = os.environ.get("PURPLEAIR_API_KEY", "")
    if not api_key:
        print("Set PURPLEAIR_API_KEY environment variable.")
        sys.exit(1)

    print("Fetching PM2.5 from PurpleAir...")
    sensors = fetch_pm25(api_key)
    for s in sensors:
        val = f"{s['pm25']:.1f}" if s["pm25"] is not None else "n/a"
        print(f"  {s['name']} ({s['dist_mi']} mi): {val} µg/m³")

    # Score
    risk_score, risk_level, eta_minutes = compute_risk(
        weather["wind_dir"], weather["wind_speed_mph"], sensors
    )
    print(f"\nRisk: {risk_level} ({risk_score}/100)")
    if eta_minutes:
        print(f"ETA:  ~{eta_minutes // 60}h {eta_minutes % 60}m")

    # Build reading
    reading = {
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "wind_dir": weather["wind_dir"],
        "wind_speed_mph": weather["wind_speed_mph"],
        "temperature_f": weather["temperature_f"],
        "risk_score": risk_score,
        "risk_level": risk_level,
        "eta_minutes": eta_minutes,
        "sensors": [
            {"name": s["name"], "pm25": s["pm25"], "dist_mi": s["dist_mi"]}
            for s in sensors
        ],
    }

    # Update history
    history = load_history()
    prev_level = previous_risk_level(history)
    history.append(reading)
    history = history[-MAX_HISTORY:]
    save_history(history)

    # Generate status page
    generate_html(reading, history)
    print(f"\nStatus page: {HTML_PATH}")

    # Email alert on transition to High or Active Alert
    alert_levels = {"High", "Active Alert"}
    if risk_level in alert_levels and prev_level not in alert_levels:
        print("Risk escalated — sending alert email...")
        send_alert_email(reading)

    print("Done.")


if __name__ == "__main__":
    main()
