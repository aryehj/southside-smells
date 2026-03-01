# CLAUDE.md — AI Assistant Guide for southside-smells

This file provides guidance for AI assistants (Claude Code, Copilot, etc.) working on this repository.

---

## Project Overview

**Southside Smells** (subtitled "What's That Smell?") is a data science investigation into recurring chemical odors in Hyde Park, Chicago (Ward 5), during October–November 2025. It correlates citizen-reported smell episodes with:

- Hourly weather data (wind direction/speed, pressure, temperature) from Open-Meteo
- PM2.5 air quality readings from a network of PurpleAir sensors
- Industrial compliance records from nearby Calumet corridor facilities

**Primary finding**: 62% of smell reports occurred during southeasterly winds (vs. 31% baseline), a 2.0× enrichment ratio, pointing to the Calumet industrial corridor 10–18 miles southeast of Hyde Park.

---

## Repository Structure

```
southside-smells/
├── CLAUDE.md                              # This file
├── README.md                              # Public-facing report with findings
├── LICENSE                                # Apache 2.0
├── .gitignore                             # Standard Python ignores
│
├── code/                                  # Analysis and data retrieval
│   ├── hyde_park_smell_analysis.ipynb     # Main analysis notebook (42 cells)
│   ├── purpleair_sensor_scan.py           # Enumerate PurpleAir sensors in bounding box
│   └── purpleair_history_pull.py          # Fetch hourly PM2.5 history from sensors
│
├── data/                                  # All data files (committed to repo)
│   ├── open_meteo_hyde_park.json          # Hourly weather data, Oct 1–Nov 5 2025
│   ├── purpleair_plume_sensors.json       # PurpleAir sensor metadata (100+ sensors)
│   ├── purpleair_plume_history.csv        # PM2.5 subset (6,145 rows)
│   ├── purpleair_plume_history_all.csv    # Full PM2.5 dataset (10,032 rows)
│   └── reports/                           # IDEM compliance PDFs (9 files, ~17 MB)
│
└── figures/                               # Output PNG visualizations (7 files, ~1.5 MB)
    ├── fig_oct12_plume.png
    ├── fig_oct25_plume.png
    ├── fig_oct31_control.png
    ├── fig_source_alignment.png
    ├── fig_source_map.png
    ├── fig_timeline.png
    └── fig_wind_rose.png
```

---

## Technology Stack

- **Language**: Python 3.7+
- **Primary interface**: Jupyter Notebook (`hyde_park_smell_analysis.ipynb`)
- **Key libraries**: `pandas`, `numpy`, `matplotlib`
- **External APIs**:
  - [Open-Meteo](https://open-meteo.com/) — free weather API, no key required
  - [PurpleAir API v1](https://api.purpleair.com/) — requires `PURPLEAIR_API_KEY`
- **Data formats**: JSON (weather, sensor metadata), CSV (PM2.5 timeseries), PDF (compliance docs)
- **No build system, no package manager, no test framework, no database**

---

## Environment Setup

### Prerequisites

```bash
pip install pandas numpy matplotlib jupyter
```

No `requirements.txt` exists; install the above manually.

### PurpleAir API Key

Required to run either data retrieval script:

```bash
export PURPLEAIR_API_KEY="your-read-key-here"
```

Both scripts check for this at startup and exit with an error if it is missing. The Open-Meteo weather data is already cached in `data/open_meteo_hyde_park.json`; no API key is needed to re-run the analysis notebook.

---

## Development Workflows

### Running the Full Analysis

The data is already committed to the repo, so you can skip straight to analysis:

1. Open `code/hyde_park_smell_analysis.ipynb` in Jupyter
2. Run all cells (Kernel → Restart & Run All)
3. Figures are written to `figures/`

### Re-fetching Data (Optional)

Only needed if the study period or geographic scope changes:

```bash
# 1. Discover sensors in the bounding box
python code/purpleair_sensor_scan.py
# → writes data/purpleair_plume_sensors.json

# 2. Pull hourly PM2.5 history for selected sensors
python code/purpleair_history_pull.py
# → writes data/purpleair_plume_history_all.csv
```

Both scripts include a 1.1-second rate-limit delay between API calls to respect PurpleAir's limits.

### Updating the Report

The public-facing report is `README.md`. It embeds the figures from `figures/` using relative paths. Update it whenever analysis conclusions change or new figures are generated.

---

## Key Code Conventions

### Notebook Structure (`hyde_park_smell_analysis.ipynb`)

The notebook is divided into 7 logical sections (reflected in markdown headers):

1. **Setup & Data Loading** — imports and file reads
2. **Report Classification** — separates real-time vs. retrospective smell reports
3. **Wind Direction Analysis** — SE enrichment ratios, timelines, wind rose plots
4. **Source Matching** — haversine bearings to industrial facilities; angular alignment
5. **PM2.5 Plume Tracking** — sensor network correlation with wind direction and lag
6. **Negative Control** — Oct 31 westerly-wind case validating the methodology
7. **Anomaly Analysis** — outlier sensor readings

Keep the section order and markdown headers intact when adding new cells.

### Geospatial Helper Functions

These utilities appear in the data retrieval scripts and should remain consistent if reused:

```python
def haversine(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance in miles between two lat/lon points."""

def bearing(lat1, lon1, lat2, lon2) -> float:
    """Compass bearing in degrees (0–360) from point 1 to point 2."""

def compass(degrees) -> str:
    """Convert bearing in degrees to 8-point compass label (N, NE, E, …)."""
```

### Data File Conventions

| File | Format | Key columns / fields |
|------|--------|----------------------|
| `open_meteo_hyde_park.json` | Open-Meteo response JSON | `hourly.time`, `hourly.wind_direction_10m`, `hourly.wind_speed_10m` |
| `purpleair_plume_sensors.json` | Array of sensor objects | `sensor_index`, `name`, `lat`, `lon`, `dist_mi`, `bearing` |
| `purpleair_plume_history_all.csv` | CSV, hourly rows | `time_utc`, `sensor_index`, `name`, `dist_mi`, `bearing`, `pm25_avg` |

Wind direction convention: **meteorological** (the direction *from which* wind blows). Southeasterly means wind coming *from* the southeast, bearing ~135°.

### API Rate Limiting

`purpleair_history_pull.py` enforces a minimum 1.1-second sleep between API calls. Do not remove this delay; PurpleAir will throttle or ban the key otherwise.

---

## Data Provenance

| Dataset | Source | Coverage | Notes |
|---------|--------|----------|-------|
| Smell reports | Community survey | Oct–Nov 2025 | 39 total, 26–27 valid real-time |
| Weather | Open-Meteo (Hyde Park: 41.79°N, 87.65°W) | Oct 1–Nov 5 2025 | Hourly, cached in repo |
| PM2.5 | PurpleAir network (13 sensors, SE arc) | Oct 1–Nov 6 2025 | Hourly, dual-channel averaged |
| Compliance reports | IDEM (Indiana) | Q4 2025 | 9 PDFs for Calumet corridor facilities |

---

## What NOT to Do

- **Do not delete committed data files** in `data/` without good reason — they are the source of truth for reproducibility.
- **Do not add a `requirements.txt` or `pyproject.toml`** unless refactoring into a proper Python package (the project is intentionally minimal).
- **Do not reorder notebook sections** — the analytical narrative is sequential.
- **Do not hardcode API keys** anywhere in the codebase; always use the environment variable.
- **Do not push figures that were generated from modified data** without also committing the updated data and notebook.

---

## Git Conventions

- Commit messages are short imperative phrases (e.g., `insert figures`, `correct file path references`).
- Data files and figures are committed directly to the repo (no LFS; total repo is ~20 MB).
- There is no CI/CD pipeline and no test suite.

---

## Contact / Context

This is a civic/community investigation, not a commercial product. The audience for the report (`README.md`) is neighbors, journalists, and local officials — write accessibly. Code should be readable by scientists who may not be professional software engineers.
