# What's That Smell?

**A data-driven investigation into recurring chemical odors noticed by neighbors in Hyde Park, Chicago**

*Ward 5 Smell Log — October–November 2025*

---

Hyde Park and surrounding neighborshoods share an active community email list called Good Neighbors. Several times over the years, neighbors have exchanged information about strong smells noted by multiple people simultaneously as much as two miles away from oeach other. Between October 7 and November 3, 2025, neighbors in Hyde Park and surrounding areas fielded an informal commnity survey. Neighbors submitted 39 smell self-reports over approximately three months in Q4 2025. Most described a **burning plastic or chemical smell**. This analysis correlates those reports with hourly weather data, PM2.5 measurements from a network of open source air quality sensors, and self-reported compliance records from nearby industrial facilities to determine plausible causes of the smell(s).

This is an ongoing, open-source investigation. The data, code, and methodology are available in this repository for review and replication. If you have questions, corrections, or additional data, please open an issue in this repository.

## Key Findings

**1. The smell comes from the southeast.** 62% of real-time reports occurred during southeast or east winds, compared to only 31% of all hours in the same period. The smell is 2.0× more likely when wind blows from the SE.[^enrichment] When wind comes from the north or west, reports drop off sharply.

**2. The source area is the Calumet industrial corridor and northwest Indiana**, 10–18 miles southeast of Hyde Park. A cluster of heavy industrial facilities sits at bearings 133°–176° from Hyde Park, directly aligned with the wind during smell episodes. The top candidates by wind-bearing match are:

- **Indiana Harbor Coke Company** (East Chicago, IN) — 13 mi, bearing 146°. Operated by Cleveland-Cliffs.[^ihcc-name] Coke oven emissions produce complex mixtures of polycyclic aromatic hydrocarbons (PAHs), benzene, and coal tar volatiles — compounds with an acrid, synthetic character that closely matches the "burning plastic" description reported by neighbors.[^coke-odor]
- **BP Whiting Refinery** — 11 mi, bearing 154°. The sixth-largest refinery in the United States by capacity.[^bp-capacity] Known for H₂S, VOC, and flaring emissions, with an extensive enforcement history including a $40 million Clean Air Act penalty in 2023.[^bp-penalty]
- **US Steel Gary Works** — 18 mi, bearing 133°. Integrated steel mill with coke ovens.
- The **Calumet corridor** facilities (American Zinc Recycling, S.H. Bell,[^shbell] RMG, and others) at bearings 163°–176°, all approximately 10 miles away.

**3. PM2.5 sensor data confirms plume transport from the industrial corridor to Hyde Park.** On October 12 — the largest smell episode — PM2.5 peaked at sensors near the industrial source area 4 hours before reaching Hyde Park, matching the expected travel time at the observed wind speed of ~3.5 mph. During the sustained October 25–26 episode, PM2.5 was approximately 2× higher near the source than at Hyde Park. No such pattern appeared during the October 31 westerly-wind episode, confirming the directional signal. (See [PM2.5 Plume Analysis](#pm25-plume-analysis) below.)

**4. Industrial compliance records document active violations during the study period.** Both IHCC and BP Whiting filed quarterly deviation reports with IDEM covering October–December 2025. IHCC reported opacity exceedances on the days immediately preceding the first smell reports, ongoing positive-pressure events in the coke oven common tunnel, and baghouse failures. BP Whiting reported a 105-hour continuous H₂S release from a weld rupture that overlapped with the entire second half of the study period, multiple unmonitored catalyst releases, and chronic equipment leaks dating back months. (See [Compliance Cross-Reference](#compliance-cross-reference) below.)

**5. Episodes cluster during stable atmospheric conditions** — light winds (mean 5.0 mph vs. 6.8 mph baseline) and elevated barometric pressure (999.9 vs. 997.1 hPa), consistent with conditions that trap and concentrate pollutants near ground level.[^stable-atm]

**6. Two reports during westerly wind** (October 31 and November 3) appear to be a separate phenomenon, possibly from the Clearing industrial district or other sources to the west.

**7. One respondent reports 8–10 years of the same recurring smell**, suggesting this is a chronic, long-standing exposure — not a one-time event.

---

## How We Did the Analysis

### Data sources

| Source | What it provides | Access |
|--------|-----------------|--------|
| Ward 5 smell survey | 39 neighbor reports with timestamps, locations, descriptions, intensity (1–5) | `data/hyde_park_smell_reports_cleaned.csv` |
| Open-Meteo API | Hourly wind direction, wind speed, barometric pressure, temperature for Hyde Park | `data/open_meteo_hyde_park.json` |
| PurpleAir API | Hourly PM2.5 from 13 sensors along the SE plume corridor | `data/purpleair_plume_history_all.csv` |
| IDEM Virtual File Cabinet | Quarterly deviation reports from IHCC and BP Whiting | Referenced by permit number below |
| EPA ECHO | Enforcement and compliance history | [echo.epa.gov](https://echo.epa.gov) |

### Methodology overview

The analysis proceeds in four steps, each building on the last:

1. **Wind correlation.** We matched each real-time smell report to the hourly wind observation and asked: does the wind come from a consistent direction during smell episodes? It does — overwhelmingly from the SE.

2. **Source matching.** We computed the bearing from Hyde Park to every major industrial facility in the Calumet corridor and NW Indiana, then checked how closely the wind during each episode aligned with each facility's bearing.

3. **PM2.5 plume tracking.** We pulled hourly PM2.5 data from PurpleAir sensors distributed along the hypothesized plume path (13 sensors from 0.1 to 19 miles from Hyde Park) and looked for time-lagged propagation patterns during the major smell episodes.

4. **Compliance cross-reference.** We reviewed IDEM quarterly deviation reports for the candidate facilities to check whether documented violations coincided with the smell episodes.

The full step-by-step analysis is in `notebooks/hyde_park_smell_analysis.ipynb`. All data files needed to reproduce it are in `data/`, and the PurpleAir data retrieval scripts are in `scripts/`.

---

## Wind Direction Analysis

### The central result

Of the 39 total reports, 27 were real-time ("Just Now" or submitted before the timing field was added to the form). After matching to hourly weather data, 26 reports had valid wind observations. Of those:

- **16 of 26 (62%)** occurred during SE wind (67.5°–180°)
- **SE wind occurs only 31% of the time** during the study period overall
- **Enrichment ratio: 2.0×** — you are twice as likely to smell the odor when the wind blows from the SE[^enrichment]

### Episode timeline

The major smell episodes were:

| Dates | Reports | Wind | Best-match sources |
|-------|---------|------|--------------------|
| Oct 9–10 | 3 | SSW ~195° | Calumet corridor (American Zinc, S.H. Bell) |
| **Oct 12** | **6** | **SE 118°–137°** | **IHCC, US Steel Gary Works, BP Whiting** |
| Oct 16–17 | 4 | SE/SSW 113°–183° | IHCC, US Steel Gary Works, Calumet WRP |
| **Oct 25–26** | **4** | **SE 96°–118°** | **US Steel Gary Works, IHCC, BP Whiting** |
| Oct 31 | 1 | W 272° | Stickney WRP (different source) |
| Nov 3 | 1 | W 267° | Clearing Industrial District (different source) |

The wind rose, timeline, and source-matching plots are generated by the notebook and will be available as figures once the notebook is run. (See `notebooks/` for instructions.)

### Why we probably can't pin it to one facility

At 10–15 miles, atmospheric turbulence disperses a plume across a broad arc.[^plume-spread] The Calumet corridor sources sit in a 15° band (154°–176°) and the coke/steel plants in Indiana cover another 15° (133°–146°). When wind comes from this broad SE quadrant, emissions from multiple sources mix before reaching Hyde Park. Different episodes likely emphasize different sources depending on the exact wind bearing and atmospheric conditions.

---

## PM2.5 Plume Analysis

### Sensor network

We queried the PurpleAir API for outdoor sensors along the SE corridor from Hyde Park to Gary, IN. Of 73 outdoor sensors in the SE arc, we selected 21 on bearings 135°–165° — aligned with BP Whiting (154°), IHCC (146°), and the Calumet facilities. Thirteen returned data for October 2025. The retrieval script is at `scripts/purpleair_history_pull_all.py`.

Five sensors at well-spaced distances serve as the primary reference set:

| Sensor | Distance | Role |
|--------|----------|------|
| Canalport (NLCEP) | 12.4 mi | Near source (Whiting/East Chicago area) |
| Oliver (NLCEP) | 9.2 mi | Mid-corridor |
| Bug | 6.9 mi | SE Chicago |
| Rooster | 5.4 mi | Mid-path |
| Purple-HP-1 | 0.1 mi | Hyde Park (observation point) |

### October 12: Plume propagation

October 12 was the largest smell episode — 6 reports between 6:53 AM and 5:25 PM CT, all during SE wind at 3.4–5.3 mph.

The PM2.5 peak moved progressively from the source area to Hyde Park:

| Sensor | Distance | Peak hour (UTC) | Peak PM2.5 | Lag |
|--------|----------|-----------------|------------|-----|
| Canalport | 12.4 mi | 07:00 | 12.7 µg/m³ | 0h |
| Oliver | 9.2 mi | 08:00 | 15.4 µg/m³ | 1h |
| Bug | 6.9 mi | 08:00 | 13.3 µg/m³ | 1h |
| Rooster | 5.4 mi | 09:00 | 11.7 µg/m³ | 2h |
| Purple-HP-1 | 0.1 mi | 11:00 | 11.4 µg/m³ | 4h |

The 4-hour lag from Canalport to Hyde Park matches the expected travel time: 12 miles at ~3.5 mph = 3.4 hours.[^transport-approx] This is direct physical evidence of airborne transport from the industrial corridor to Hyde Park.

### October 25–26: Distance gradient

During this sustained SE-wind episode, PM2.5 was consistently higher near the source than at Hyde Park. During the peak window (October 26, 05:00–09:00 UTC), the near-source sensor averaged approximately 2× the Hyde Park reading — the expected signature of a dispersing point-source plume.

### October 31: Negative control

During the westerly-wind episode, all sensors spiked simultaneously with no distance-dependent lag and no systematic gradient. This is what we'd expect when the source is *not* in the SE corridor, and it confirms that the October 12 and October 25–26 patterns are not artifacts of regional weather or the sensor network itself.

### Limitations of PM2.5 as a plume tracer

PM2.5 is a general indicator, not specific to any source or pollutant.[^pm25-general] PurpleAir sensors are low-cost instruments with known humidity sensitivity;[^purpleair-humidity] we mitigate this by analyzing relative patterns (timing and gradients) rather than absolute concentrations, and by using multiple sensors at similar distances for cross-validation. There is a coverage gap between 0 and 5 miles from Hyde Park.

---

## Compliance Cross-Reference

The following information comes from facilities' own quarterly deviation reports filed with the Indiana Department of Environmental Management (IDEM). These are public records available through IDEM's Virtual File Cabinet.[^vfc]

### Indiana Harbor Coke Company (IHCC)

**Source:** Q4 2025 Quarterly Deviation and Compliance Monitoring Report, Permit No. T089-41059-00382, submitted January 28, 2026.[^ihcc-filing]

IHCC reported the following deviations during the study period:

**October 7** — Fugitive visible emissions from pushing operations exceeded 20% opacity on oven A(44). The cause was high carbon buildup on the oven floor. Decarbonization was not completed until October 31 — meaning this oven operated in a degraded condition for 24 days spanning the first three weeks of smell reports.

**October 21** — Oven B(51) experienced a door leak for 60 minutes during push-side uptake elbow repair.

**19 positive-pressure events in the common tunnel** (continuation from Q3) — IHCC reviewed common tunnel pressure cell readings and observed positive pressure readings attributed to reduced draft from Cokenergy due to fouled heat recovery steam generators (HRSGs). Positive pressure in the common tunnel means coke oven gas can leak outward rather than being drawn through the collection system. IHCC states that no visible emissions were observed. However, coke oven gas does not need to be visible to carry VOCs and PAHs at concentrations detectable by the human nose.

**November 20 and 23** — Two additional charging opacity exceedances on D Battery.

**Significance:** The October 7 pushing violation occurred two days before the first smell reports in our dataset. The ongoing common tunnel pressure issues indicate that the coke oven gas collection system was operating in a compromised state throughout the entire study period.

### BP Products North America — Whiting Refinery

**Source:** Q4 2025 Title V Deviation and CAM Report, and Q4 2025 NSR Limit Report, Permit Nos. T089-30396-00453 / T089-41271-00453, submitted January 30, 2026.[^bp-filing]

BP Whiting's Q4 deviation report is extensive. The events most relevant to the smell investigation are:

**October 16 – November 3 (105 hours)** — The 4UF Flare exceeded the H₂S limit (3-hour rolling average >162 ppm) following a weld rupture at the Cat Feed Hydrotreating Unit. This was a continuous release lasting over four days. H₂S is detectable by the human nose at concentrations measured in parts per billion — orders of magnitude below the flare's exceedance threshold.[^h2s-odor] **This release was active during every smell report from October 16 onward**, including the major October 25–26 episode.

**October 11 (~3 hours)** — A catalyst leak from the FCU 500 slide valve packing released fine particulate through the stack. No formal opacity measurement (Method 9) was conducted; the event was reported on "credible evidence" only. This occurred the day before the largest smell episode (October 12). The unquantified catalyst release may account for some of the PM2.5 elevation observed in the plume propagation analysis the following morning.

**October 24** — A refinery-wide power blip caused the South Flare to exceed H₂S limits and produce visible smoke for 24 minutes. The FCU 500 coke burn monitor was simultaneously offline for 5 hours. This compound event occurred the day before the sustained October 25–26 smell episode.

**Chronic sources active throughout the study period:**

- Three pressure relief valves leaking continuously since February–May 2025 (VRU 100 and VRU 200), awaiting unit outages for repair.
- Coker Feed Tank TK-6254 exceeding the H₂S 12-month rolling limit since the January 2025 refinery fire, with vapors not fully routed to recovery.
- 312 components found undocumented during the 2025 LDAR audit across four process units — representing an unknown background VOC/H₂S emission source with no historical monitoring record.
- Fenceline monitoring Station 26 offline for an extended period overlapping late Q3/early Q4 due to flooding — creating a data gap in the facility's own perimeter monitoring during the run-up to the study period.

### Facilities with no deviations

For completeness: TMS International (Gary Works scrap operations), Industrial Steel Construction, and US Steel East Chicago Tin Products all reported no deviations for Q4 2025.[^clean-reports]

---

## Limitations

This analysis has several important limitations:

**Sample size.** 39 reports from a convenience sample — not a random population survey. The 2.0× SE wind enrichment is consistent and directional, but the small sample limits statistical power.[^enrichment]

**Hourly wind resolution.** We match reports to the nearest hourly wind observation. The actual wind at the moment of the smell may differ, especially during transition periods.

**PM2.5 is not source-specific.** The plume propagation patterns are consistent with industrial transport, but PM2.5 includes contributions from all sources (traffic, construction, cooking, etc.). The directional propagation makes non-industrial explanations unlikely for the observed gradient, but we cannot attribute the PM2.5 to a specific facility or pollutant.

**Self-selection bias.** People who suspect an industrial source may be more likely to report. Conversely, people who experience the smell but don't know about the survey don't report at all.

**Transport approximation.** Plume travel time is estimated as distance ÷ wind speed, a first-order approximation that does not account for turbulent diffusion, vertical wind shear, or terrain effects.[^transport-approx]

**Facility naming.** The notebook's original references to "Acme/SunCoke" have been updated. The facility is Indiana Harbor Coke Company, L.P., currently operated as a contractor of Cleveland-Cliffs, Inc. The coke plant was previously owned by SunCoke Energy.[^ihcc-name]

---

## What Comes Next

This analysis establishes a strong directional signal and temporal correlation between industrial emissions and odor complaints in Hyde Park. Several extensions would strengthen the evidence further:

- **Continued smell reporting.** More data points improve statistical power and may reveal seasonal patterns.
- **Indoor air quality monitoring.** Deploying PM2.5 and VOC sensors in Hyde Park homes during SE wind episodes would measure actual indoor exposure.
- **HYSPLIT back-trajectory modeling.** NOAA's atmospheric transport model can trace where air parcels arriving at Hyde Park actually originated over the prior 6–12 hours, accounting for full atmospheric dynamics rather than surface wind alone.
- **Additional compliance records.** Q1 2026 deviation reports (due ~April 2026) will cover the later period of the smell survey. NRC reports and EPA enforcement actions may provide additional incident-level detail.

---

## Repository Structure

```
├── README.md                  ← This report
├── data/
│   ├── hyde_park_smell_reports_cleaned.csv
│   ├── open_meteo_hyde_park.json
│   └── purpleair_plume_history_all.csv
├── notebooks/
│   └── hyde_park_smell_analysis.ipynb
├── scripts/
│   ├── purpleair_sensor_scan.py
│   └── purpleair_history_pull_all.py
├── compliance/
│   ├── indiana_emissions_q4_2025.md
│   └── IHCC_Q4_2025_deviation_report.pdf
└── figures/
    ├── fig_wind_rose.png
    ├── fig_timeline.png
    ├── fig_source_map.png
    ├── fig_source_alignment.png
    ├── fig_oct12_plume.png
    ├── fig_oct25_plume.png
    └── fig_oct31_control.png
```

Figures are generated by running the notebook. The `figures/` directory will be populated after execution.

---

## Footnotes

[^enrichment]: The enrichment ratio is the fraction of smell reports during SE wind divided by the fraction of all hours with SE wind: 62% / 31% = 2.0×. This is a descriptive statistic; a formal hypothesis test (e.g., Fisher's exact test) would provide a p-value. With 26 reports, the sample is small but the directional pattern is consistent across episodes.

[^coke-odor]: Coke oven emissions contain over 200 identified compounds including PAHs, benzene, toluene, xylene, phenol, and naphthalene. EPA classifies coke oven emissions as a known human carcinogen. The sensory profile — described in occupational health literature as acrid, tarry, and chemical — is consistent with the "burning plastic" descriptor used by Hyde Park residents. See: EPA, "Coke Oven Emissions — Hazard Summary," Technology Transfer Network Air Toxics; ATSDR, "Toxicological Profile for Coke Oven Emissions" (2017 update).

[^ihcc-name]: The facility at 3210 Watling Street, East Chicago, IN 46312 is operated by Indiana Harbor Coke Company, L.P., identified in IDEM filings as "a contractor of Cleveland-Cliffs, Inc." (Permit No. T089-41059-00382). The coke plant was previously owned by SunCoke Energy, Inc. Earlier versions of this analysis referred to the facility as "Acme/SunCoke."

[^bp-capacity]: BP's Whiting refinery has a crude oil processing capacity of approximately 435,000 barrels per day, making it the sixth-largest refinery in the United States. Source: U.S. Energy Information Administration, Refinery Capacity Report.

[^bp-penalty]: In 2023, the U.S. Department of Justice and EPA announced a settlement requiring BP to pay a $40 million civil penalty and install $197 million in pollution-prevention improvements at the Whiting refinery — the largest civil penalty ever secured for a Clean Air Act stationary source settlement. A prior settlement in 2022 required a $512,450 penalty and improvements to particulate monitoring and pollution control operations. Sources: DOJ press release, "United States and Indiana Reach Agreement with BP" (2023); Environmental Integrity Project, "BP Agrees to $500K Penalty" (2022).

[^shbell]: S.H. Bell Company's Chicago facility on Avenue O was subject to a 2017 EPA consent decree for manganese emissions. The facility handles bulk manganese-bearing materials. Source: EPA Region 5 enforcement action.

[^stable-atm]: High barometric pressure and light winds are associated with atmospheric subsidence inversions, which suppress vertical mixing and concentrate surface-level pollutants. This is a standard finding in air quality meteorology. See: Seinfeld & Pandis, *Atmospheric Chemistry and Physics* (3rd ed.), Ch. 16.

[^plume-spread]: At downwind distances of 10–15 miles, Gaussian plume dispersion models predict lateral spread on the order of 20°–40° of arc depending on atmospheric stability class. This is a first-order approximation. See: Turner, "Workbook of Atmospheric Dispersion Estimates" (EPA, 1970); Seinfeld & Pandis, Ch. 18.

[^transport-approx]: Plume travel time estimated as distance ÷ surface wind speed is a first-order approximation. Actual transport depends on vertical wind profile, turbulent diffusion, and boundary layer height. The close match between predicted and observed lag (3.4 hours predicted, 4 hours observed) suggests this approximation is adequate for the conditions during the October 12 episode.

[^pm25-general]: PM2.5 (particulate matter with aerodynamic diameter ≤2.5 µm) is a bulk measurement that includes contributions from all sources — industrial emissions, vehicle exhaust, cooking, construction dust, and secondary aerosol formation. It is not specific to any single pollutant or facility.

[^purpleair-humidity]: PurpleAir sensors use Plantower laser particle counters, which overestimate PM2.5 under high humidity due to hygroscopic growth of particles. EPA has developed a correction factor ("US-wide correction") to improve accuracy. See: Barkjohn et al., "Development and application of a United States-wide correction for PM2.5 data collected with the PurpleAir sensor," *Atmospheric Measurement Techniques*, 14 (2021), 4617–4637.

[^vfc]: IDEM's Virtual File Cabinet provides public access to facility compliance documents. Search at: https://vfc.idem.in.gov/FacilitySearch.aspx

[^ihcc-filing]: Indiana Harbor Coke Company, L.P., Q4 2025 Quarterly Deviation and Compliance Monitoring Report, Part 70 Permit No. T089-41059-00382, submitted to IDEM January 28, 2026. Filed by Edward Glass, General Manager.

[^bp-filing]: BP Products North America, Q4 2025 Title V Deviation and CAM Report, Permit No. T089-30396-00453, submitted to IDEM January 30, 2026. NSR Limit Report for the same period submitted under the same permit.

[^h2s-odor]: The human odor threshold for hydrogen sulfide (H₂S) is approximately 0.5–8 parts per billion (ppb). The BP Whiting 4UF Flare exceeded 162 ppm (162,000 ppb) on a 3-hour rolling average. While flare combustion destroys some H₂S, incomplete combustion during upset conditions and ground-level concentrations during poor dispersion can produce detectable odor miles downwind. Source: ATSDR, "Toxicological Profile for Hydrogen Sulfide/Carbonyl Sulfide" (2016).

[^clean-reports]: TMS International LLC (Permit T089-42560-00174), Industrial Steel Construction (Permit T089-43131-00161), and U.S. Steel East Chicago Tin Products (Permit T089-00300) all reported no deviations for Q4 2025 in their Part 70 quarterly reports.
