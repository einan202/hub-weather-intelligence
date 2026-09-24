# Weather Risk Intelligence Agent

## Overview

This project is a weather-risk analysis agent for a logistics company operating regional distribution hubs across the United States.

The goal is to help analysts compare hub locations, understand the main weather and hazard exposure drivers, and prioritize resilience analysis using deterministic metrics rather than relying on the LLM to calculate scores.

The current deterministic layer combines two complementary public data sources:

1. Historical daily weather exposure from Open-Meteo.
2. Historical FEMA Major Disaster declarations from OpenFEMA.

The LLM layer will use these deterministic tools to answer natural-language questions, compare hubs, explain drivers, and support conversational follow-ups.

A key design decision is that the system does **not** create an arbitrary 0-100 risk score. The available public data does not provide facility-level shutdown or downtime labels that would justify calibrating weights, normalization constants, or a probability of operational disruption.

---

## Data Sources and Tools

### Open-Meteo Geocoding API

The geocoding tool converts a U.S. city name into location metadata used by downstream weather and hazard tools.

The current output includes:

- Latitude
- Longitude
- Timezone
- Full state name
- Two-letter U.S. state code
- County
- Country code

Location resolution is deterministic:

1. Keep only U.S. results.
2. Prefer exact city-name matches.
3. If a state is provided, require a matching state.
4. If multiple valid matches remain, select the location with the largest population.

U.S. state names are deterministically mapped to two-letter state codes because Open-Meteo returns full state names while FEMA queries use state abbreviations.

The high-level hub report geocodes a hub once and reuses the result:

- latitude / longitude / timezone for Open-Meteo
- state code / county for OpenFEMA

### Open-Meteo Historical Weather API

Historical daily weather data is retrieved using the coordinates returned by the geocoding tool.

The implementation currently requests exactly three daily variables:

- `snowfall_sum` — centimeters (cm)
- `precipitation_sum` — millimeters (mm)
- `wind_gusts_10m_max` — kilometers per hour (km/h)

`wind_speed_10m_max` was intentionally removed because no current KPI uses it. This reduces Open-Meteo Archive request weight without changing any metric used by the application.

The raw weather data is converted into deterministic Python metrics. The LLM does not calculate these values.

Current metrics include:

- Snow days and percentage of snow days
- High-precipitation days and percentage of high-precipitation days
- High-wind days and percentage of high-wind days
- Elevated Weather Exposure Days and percentage

### OpenFEMA Disaster Declarations Summaries API

OpenFEMA v2 is used as a historical severe-hazard signal.

Only FEMA Major Disaster declarations are included:

```text
declarationType == "DR"
```

The current project categories are:

```text
Flood        -> Flood
Hurricane    -> Hurricane
Severe Storm -> Severe Storm
Winter       -> Snowstorm, Severe Ice Storm
```

For each county, the tool returns:

- Declaration counts by hazard category
- Recent matching disaster declarations
- FEMA disaster number
- Declaration title
- Declaration date
- Primary incident type

The correct interpretation is:

> FEMA Major Disaster declarations naming this county, grouped by FEMA's primary incident type.

These counts must **not** be narrated as the number of hazards that directly struck a city or hub. For example, a county may appear in a hurricane declaration because of disaster assistance or related impacts even if the hurricane did not directly strike that city.

FEMA is therefore treated as a severe-event context signal, not as a complete local hazard-frequency dataset and not as direct proof of facility disruption.

---

## Weather Metric Thresholds

The thresholds are deterministic and documented rather than selected by the LLM.

### Snow Day

A day is considered a snow day when:

```text
daily snowfall > 0 cm
```

This is an exposure metric, not a claim that any snowfall causes operational disruption.

The choice is intentionally simple because one of the assignment questions asks for the percentage of days on which snowfall occurred. Open-Meteo's `snowfall_sum` is the daily snowfall total, so a value above zero directly answers that question.

### High-Precipitation Day

A day is considered a high-precipitation day when:

```text
daily precipitation >= 25.4 mm
```

25.4 mm is exactly 1 inch.

NOAA/NCEI Daily Climate Normals includes the probability of daily precipitation reaching at least 1.00 inch as a standard climatological statistic. This gives the project a documented daily threshold rather than an arbitrary value.

The metric is deliberately named `high_precipitation` rather than `heavy_rain`. National Weather Service terminology for heavy rain is commonly based on rainfall intensity over shorter time intervals, while the current Open-Meteo input is `precipitation_sum`, a 24-hour total.

### High-Wind Day

A day is considered a high-wind day when:

```text
maximum daily wind gust >= 74 km/h
```

74 km/h is approximately 46 mph.

The threshold is based on the lower gust boundary used for Wind Advisory criteria by multiple National Weather Service forecast offices.

NWS criteria can vary by forecast office and region, so this is treated as a documented national-scale analytical assumption rather than a universal operational rule.

### Elevated Weather Exposure Day

The primary cross-hazard weather KPI is **Elevated Weather Exposure Days**.

A day is counted once when at least one of the following is true:

```text
snowfall > 0 cm
OR
precipitation >= 25.4 mm/day
OR
maximum wind gust >= 74 km/h
```

The conditions are combined using a boolean union, so a day that exceeds multiple thresholds is still counted exactly once.

This metric describes recurring weather exposure. It does **not** estimate the probability that a logistics hub will shut down.

### Threshold References

- Open-Meteo Historical Weather API:  
  https://open-meteo.com/en/docs/historical-weather-api
- NOAA/NCEI Daily Climate Normals:  
  https://www.ncei.noaa.gov/access/search/datasets/normals-daily/
- National Weather Service Wind Advisory criteria example:  
  https://www.weather.gov/iln/criteria
- National Weather Service surface-observation training material for rate-based heavy-rain terminology:  
  https://www.weather.gov/media/surface/SFCTraining.pdf

---

## Historical Analysis Period

For long-term hub comparison, the default analysis window is the **last 15 complete calendar years**.

The dates are calculated dynamically rather than hard-coded.

For example, when the application runs during 2026, the default period is:

```text
2011-01-01 -> 2025-12-31
```

When it runs during 2027, the default automatically becomes:

```text
2012-01-01 -> 2026-12-31
```

Weather and FEMA use the same start and end dates for a hub report.

Custom periods are also supported for questions such as:

```text
What percentage of days in Denver last year had snowfall?
```

Both `start_date` and `end_date` must be supplied for a custom period.

Annualized values are derived from observed days:

```text
years_observed = total_days / 365.25
average_days_per_year = event_days / years_observed
```

This avoids hard-coding a division by 15 and keeps the calculation valid for custom date ranges.

---

## High-Level Hub Exposure Report

`get_hub_exposure_report(...)` is the deterministic high-level report intended to sit underneath the agent.

Its flow is:

```text
city + optional state + optional date range
        |
        v
Geocode once
        |
        +--> Open-Meteo historical weather
        |
        +--> OpenFEMA county hazard history
        |
        v
Deterministic weather metrics + FEMA context
        |
        v
Structured hub exposure report
```

The report contains:

- Resolved location metadata
- Analysis period
- `total_days`
- `years_observed`
- Snowfall exposure
- High-precipitation exposure
- High-wind exposure
- Elevated Weather Exposure Days
- Average days per year for each weather metric
- FEMA Major Disaster declaration counts
- Recent FEMA declarations

Weather exposure and FEMA declaration history remain separate. FEMA counts are **not** mathematically blended into the weather KPI.

---

## Why There Is No 0-100 Composite Risk Score

A synthetic 0-100 score was considered and intentionally rejected for the MVP.

The available public data describes hazards and regional disruption signals, but it does not provide a clean facility-level target such as:

```text
Hub X was unavailable for 6 hours because of flooding.
```

Without that kind of ground truth, assigning weights such as `70% weather + 30% FEMA` would create false precision rather than a calibrated operational-risk estimate.

The MVP therefore exposes direct, interpretable KPIs and keeps the calculations reproducible.

The primary weather KPI is:

```text
Elevated Weather Exposure Days
```

Hazard-specific comparisons can use the relevant direct metric:

```text
Winter    -> snowfall exposure (FEMA winter declarations as context)
Flood     -> high-precipitation exposure (FEMA flood declarations as context)
Storm     -> high-wind exposure (FEMA severe-storm declarations as context)
Hurricane -> FEMA hurricane declaration frequency
```

The deterministic ranking layer ranks hubs using these explicit KPIs rather than inventing an opaque score.

---

## Deterministic Multi-Hub Ranking

`rank_hubs_by_exposure(...)` ranks multiple hubs using deterministic, directly interpretable metrics.

Supported ranking modes are:

```text
overall   -> Elevated Weather Exposure Days per year
winter    -> Snow days per year
flood     -> High-precipitation days per year
storm     -> High-wind days per year
hurricane -> FEMA Hurricane declarations per year
```

Weather-based rankings use `average_days_per_year` from the hub exposure report.

FEMA counts are returned as supporting context for every ranking mode — the matching category for `winter`, `flood`, `storm`, and `hurricane`, and all four categories for `overall` — but they are **not mathematically blended** into the weather ranking value.

The hurricane ranking is the exception because the current weather layer does not contain a direct hurricane metric. It therefore ranks by FEMA Major Disaster declaration frequency:

```text
hurricane_declarations / years_observed
```

This value means FEMA Major Disaster declarations naming the county whose primary incident type was Hurricane. It must not be narrated as the number of hurricanes that directly struck the hub.

Ranking is descending by the selected metric. If two hubs have the same value, city and state names provide deterministic tie-breaking.

The ranking layer accepts the same optional date range as the hub report. If no custom period is supplied, each hub uses the dynamically calculated last 15 complete calendar years.


---

## Why No Logistics / Transportation Impact Metric Is Blended In

Operational sources were investigated, but none provided a clean, nationwide, hub-level ground truth suitable for calibrating the MVP.

Examples considered include:

- EAGLE-I power-outage data
- BTS weather-delay data
- FMCSA emergency declarations
- State 511 road-closure feeds
- FEMA National Risk Index / community-resilience data

These sources were not blended into the current KPI because they are either:

- **Partial** — they measure only one part of disruption, such as regional power outages.
- **Fragmented** — road-closure data is distributed across different state systems and formats rather than one consistent national historical API.
- **Proxies** — airport delays, county outages, or disaster declarations can indicate regional disruption without proving that a specific logistics hub stopped operating.

The FEMA National Risk Index was also deferred because its resilience measures are community-level rather than warehouse-specific, creating scale mismatch and ecological-fallacy risk if interpreted as facility resilience.

A stronger production model would combine:

1. Weather hazard exposure
2. Facility-specific operational thresholds and resilience
3. Road, power, and access disruption
4. Hub business criticality / throughput
5. Historical facility outcomes for calibration

---

## Open-Meteo Quota, Caching, and Retry Handling

Historical Open-Meteo requests are intentionally made **sequentially**, not in parallel.

Each hub uses one Archive API request containing the three daily variables currently required by the KPIs:

```text
snowfall_sum
precipitation_sum
wind_gusts_10m_max
```

Earlier development used four variables, including `wind_speed_10m_max`. That variable was removed because it was unused.

This distinction is important: the optimization was **four weather variables to three variables per hub request**, not four simultaneous requests to three simultaneous requests.

Open-Meteo Archive usage is weighted by the amount of data requested, including variable count and date span, rather than only by raw HTTP request count.

For the 15-year development window, the observed/request-weighting calculation was approximately:

```text
4 variables -> ~157 weighted units per hub
3 variables -> ~117 weighted units per hub
4 cold hubs -> ~470 weighted units total
```

Removing the unused fourth variable therefore reduced request weight by roughly 25% and allowed the normal four-hub analysis to stay below the minute-level development budget that previously caused HTTP 429 responses.

### In-Memory Historical Cache

Identical historical weather requests are cached in memory.

The cache key includes:

- Latitude
- Longitude
- Timezone
- Start date
- End date
- Requested daily-variable tuple

Historical closed-period data is stable, so caching repeated queries reduces both latency and quota consumption during conversational follow-ups.

The cache is process-local and is lost when the process exits.

### Retry Policy

Open-Meteo retry behavior is intentionally small and explicit:

```text
Timeout / ConnectionError -> retry once after 2 seconds
HTTP 500 / 502 / 503 / 504 -> retry once after 2 seconds
HTTP 429                   -> fail immediately
Other 4xx                  -> fail immediately
```

The request timeout is:

```text
connect timeout = 10 seconds
read timeout    = 60 seconds
```

A live smoke test produced a TLS-handshake timeout on one request. Review of the installed `urllib3` behavior confirmed that the reported `read timeout=10` message was the 10-second connection timeout being hit during TLS establishment, not a misconfigured 60-second read timeout.

No additional retry, higher timeout, or chunking was added because the failure was consistent with a transient network/API-node issue rather than a correctness bug.

Chunking a 15-year request was also intentionally avoided because it would not materially reduce total weighted usage and would add more HTTP requests and implementation complexity.

### Geocoding and Quota

No special retry or cache was added to geocoding for the Archive API quota issue.

Geocoding uses a separate Open-Meteo endpoint and is inexpensive relative to the 15-year Archive request. The hub report already geocodes once per hub and reuses the result.

---

## FEMA Query Design and Limitations

### County Matching Across Providers

Open-Meteo and FEMA do not always format county names consistently.

For example:

```text
Open-Meteo: Miami-Dade County
FEMA:       Miami-Dade (County)
```

The FEMA request is first narrowed server-side using a case-preserving substring filter such as:

```text
contains(designatedArea, 'Miami-Dade')
```

Returned areas are then normalized and compared using exact equality in Python.

This prevents substring collisions such as `Harris` and `Harrison` while keeping the remote result set small.

### FEMA Query Completeness

The request uses:

```text
$top=1000
```

as a safety cap.

If a narrowed request reaches 1,000 rows, the tool fails explicitly rather than returning potentially incomplete counts.

The date-window filter is applied locally after the truncation guard. If fewer than 1,000 county rows were returned, the local date filter can safely select the requested period from the complete narrowed result set.

Full pagination is intentionally not implemented for the MVP because county-level narrowing keeps normal result sets well below the safety cap.

### FEMA Timeout / Retry Choice

OpenFEMA currently uses a flat 20-second timeout and no custom retry loop.

This is intentionally simpler than the Open-Meteo handling because the quota problem that motivated the Open-Meteo retry/cache design does not apply to this FEMA request pattern.

### Primary Incident Type Limitation

FEMA's `incidentType` is the declaration's primary classified incident.

For example, flooding associated with a hurricane may still appear as:

```text
incidentType = "Hurricane"
```

rather than:

```text
incidentType = "Flood"
```

This means FEMA category counts should not be interpreted as a complete reconstruction of every secondary hazard associated with a disaster.

The agent system prompt must also avoid statements such as:

```text
"N hurricanes hit Dallas"
```

A correct formulation is closer to:

```text
"Dallas County was named in N FEMA Major Disaster declarations whose primary incident type was Hurricane."
```

---

## Example 15-Year Sanity Check

The following values were observed in a live run for `2011-01-01` through `2025-12-31`.

| Hub | Snow days | High-precipitation days | High-wind days | Elevated exposure days | Elevated exposure % |
|---|---:|---:|---:|---:|---:|
| Miami | 0 | 109 | 22 | 119 | 2.17% |
| Houston | 12 | 257 | 22 | 283 | 5.17% |
| Dallas | 52 | 210 | 39 | 287 | 5.24% |
| Denver | 804 | 17 | 21 | 826 | 15.08% |

The union sanity check also confirms that overlapping threshold days are not double-counted.

FEMA Major Disaster declaration counts for the same period were:

| County / Hub | Flood | Hurricane | Severe Storm | Winter |
|---|---:|---:|---:|---:|
| Miami-Dade | 0 | 4 | 0 | 0 |
| Harris / Houston | 4 | 2 | 2 | 1 |
| Dallas | 1 | 1 | 2 | 1 |
| Denver | 2 | 0 | 0 | 0 |

These are declaration counts naming the county, not counts of direct hazard strikes.

---

## Deterministic vs. LLM Responsibilities

The LLM is not responsible for calculating weather metrics, FEMA counts, annualized values, or ranking values.

The deterministic layer is responsible for:

- Location resolution
- Historical weather retrieval
- Weather metric calculation
- Elevated-weather union calculation
- FEMA declaration aggregation
- Date-window handling
- Annualized metric calculation
- Hub exposure report generation
- Ranking inputs and ranking logic

The LLM layer will be responsible for:

- Understanding natural-language questions
- Selecting high-level tools
- Comparing locations
- Explaining deterministic results
- Handling conversational follow-up questions
- Communicating assumptions and limitations

The ranking logic is deterministic and reproducible.

---

## Current Architecture

```text
User query
    |
    v
LLM Agent
    |
    v
High-level deterministic tools
    |
    +--> Hub exposure report
            |
            +--> Geocoding
            |
            +--> Open-Meteo historical weather
            |
            +--> OpenFEMA hazard history
    |
    +--> Ranking / comparison
    |
    v
Structured response
```

Low-level API and calculation helpers remain internal. The agent should only be exposed to high-level tools.

---

## Testing

The deterministic components are covered by unit tests using mocked external API responses.

Coverage includes:

- U.S. state mapping
- Geocoding and state/county resolution
- Historical weather retrieval
- Weather threshold calculations
- Elevated-weather union and overlap handling
- High-level weather metric aggregation
- FEMA county filtering
- Similar-name county collision protection
- FEMA winter and severe-storm categories
- FEMA result-limit protection
- FEMA date-window filtering
- Historical-weather cache isolation between tests
- Hub exposure report aggregation
- Custom-period validation
- Deterministic overall ranking
- Hurricane declaration-frequency ranking
- Unsupported ranking-mode validation
- Empty hub-list validation

The current full suite has been verified with:

```text
28 passed
```

Run the full suite with:

```bash
pytest -q
```

Live hub-report checks can be run with:

```bash
python -m scripts.check_hub_report
```

Live ranking checks can be run with:

```bash
python -m scripts.check_ranking
```

The ranking smoke script exercises the real hub-report stack before sorting the returned deterministic values.

A live ranking smoke attempt encountered a transient TLS-handshake timeout while connecting to `archive-api.open-meteo.com`. The failure occurred during the Open-Meteo fetch, before ranking data was returned, and the configured retry ran exactly once as designed. Inspection of the installed `urllib3` behavior confirmed that the reported `read timeout=10` message corresponds to the 10-second connection timeout being hit during TLS establishment; the configured `timeout=(10, 60)` remains correct.

No production-code change was made for this transient network/API-node failure. The deterministic ranking logic itself is covered by the passing unit suite.

Because the historical cache is process-local, an immediate full rerun after a failed multi-hub smoke test will fetch earlier hubs again. After a network failure, waiting for the minute-level API budget to reset before re-running avoids stacking a quota failure on top of a transient network failure.

---

## Current Scope

### Implemented

- Deterministic U.S. geocoding
- State-code and county resolution
- Historical Open-Meteo weather retrieval
- Three-variable weather request optimized for current KPIs
- Snow, high-precipitation, and high-wind metrics
- Elevated Weather Exposure Days union KPI
- Dynamic default window of the last 15 complete calendar years
- Custom date ranges
- Annualized exposure metrics
- In-memory historical-weather cache
- Selective Open-Meteo retry/error handling
- FEMA Major Disaster declaration history
- FEMA date-window filtering
- Cross-provider county normalization
- High-level hub exposure report
- Deterministic multi-hub ranking
- Unit tests and live API sanity checks

### Still to implement

- LLM tool-calling layer
- Structured LLM output schema
- FastAPI chat endpoint
- Streamlit chat interface
- Small evaluation set and evaluation runner
- Deployment, if time permits

The project intentionally prioritizes a narrow, explainable implementation over a broader but less reliable system.
