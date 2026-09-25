# Weather Risk Intelligence Agent

## Overview

This project is a weather-risk analysis agent for a logistics company operating regional distribution hubs across the United States.

The goal is to help analysts compare hub locations, understand the main weather and hazard exposure drivers, and prioritize resilience analysis using deterministic metrics rather than relying on the LLM to calculate scores.

The current deterministic layer combines two complementary public data sources:

1. Historical daily weather exposure from Open-Meteo.
2. Historical FEMA Major Disaster declarations from OpenFEMA.

The LLM layer uses these deterministic tools to answer natural-language questions, compare hubs, explain drivers, and support conversational follow-ups.

A key design decision is that the system does **not** create an arbitrary 0-100 risk score. The available public data does not provide facility-level shutdown or downtime labels that would justify calibrating weights, normalization constants, or a probability of operational disruption.

---



## Live Demo

https://hub-weather-agent.onrender.com

The application is deployed on Render using separate FastAPI and Streamlit web services.

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
[https://open-meteo.com/en/docs/historical-weather-api](https://open-meteo.com/en/docs/historical-weather-api)
- NOAA/NCEI Daily Climate Normals:  
[https://www.ncei.noaa.gov/access/search/datasets/normals-daily/](https://www.ncei.noaa.gov/access/search/datasets/normals-daily/)
- National Weather Service Wind Advisory criteria example:  
[https://www.weather.gov/iln/criteria](https://www.weather.gov/iln/criteria)
- National Weather Service surface-observation training material for rate-based heavy-rain terminology:  
[https://www.weather.gov/media/surface/SFCTraining.pdf](https://www.weather.gov/media/surface/SFCTraining.pdf)

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

No nationwide hub-level operational ground truth was found. The operational sources that were considered are partial, fragmented, or proxies, so they were not blended into the current KPI.

A production model could later combine weather exposure with facility resilience, road and power access, business criticality, and historical facility outcomes.

---



## Open-Meteo Quota, Caching, and Retry Handling

Historical Open-Meteo requests are made sequentially, not in parallel. Each hub uses one Archive API request containing the three daily variables required by the KPIs: `snowfall_sum`, `precipitation_sum`, and `wind_gusts_10m_max`.

Identical historical requests are cached in process memory. The cache is process-local and is lost when the process restarts.

Transient Open-Meteo failures are retried once.

---



## FEMA Query Design and Limitations

County names must be normalized across Open-Meteo and FEMA, because the two providers do not format them the same way. For example, Open-Meteo returns `Miami-Dade County` while FEMA uses `Miami-Dade (County)`. Returned areas are normalized and then matched with exact equality, which prevents similar-name collisions such as `Harris` and `Harrison`.

FEMA counts represent Major Disaster declarations naming the county. `incidentType` is the primary FEMA incident classification, so flooding associated with a hurricane may still be classified as Hurricane rather than Flood. These counts must not be interpreted as direct hazard strikes or as a complete record of local hazard frequency. A county was named in N FEMA Major Disaster declarations whose primary incident type was Hurricane; that is not the same as saying N hurricanes hit the city.

---



## LLM Role and Responsibilities

Deterministic code is the source of truth for all calculations and rankings. The LLM does not calculate weather metrics, FEMA counts, annualized values, or ranking values.

The deterministic layer owns:

- Location resolution
- Historical weather retrieval
- Weather metric calculation
- Elevated-weather union calculation
- FEMA declaration aggregation
- Date-window handling
- Annualized metric calculation
- Hub exposure report generation
- Ranking inputs and ranking logic

The LLM owns:

- Understanding natural-language questions
- Selecting and orchestrating high-level tools
- Comparing locations
- Explaining deterministic results, assumptions, and limitations
- Handling conversational follow-up questions

The agent uses the OpenAI Responses API and calls three high-level tools:

- `get_hubs`
- `get_hub_exposure_report`
- `rank_hubs_by_exposure`

A follow-up question is sent with the previous turn's `previous_response_id`. The model's final message is a structured `AgentAnswer` with `answer`, `key_findings`, and `limitations`.

The deterministic layer already calculates hub metrics, generates exposure reports, resolves configured hub groups, and ranks locations. The LLM adds a natural-language interface over that system: it interprets intent, chains tool calls when a question needs more than one step, preserves conversational context, and explains the structured results. For example, "Which Midwest hubs are most exposed to winter disruption?" leads the agent to call `get_hubs` for the Midwest, then `rank_hubs_by_exposure` with the `winter` mode. That ranking uses snow days per year as an exposure measure, not a probability of hub shutdown or disruption. Analysts can ask flexible questions without learning the underlying API, while the numerical analysis stays reproducible.

---



## System Prompt

The agent uses a compact system prompt that keeps numerical reasoning inside the deterministic tool layer and gives the LLM responsibility for orchestration and explanation.

The live prompt includes the current date dynamically so relative periods such as "last year" can be converted into explicit date ranges.

```text
You are a weather exposure analyst for U.S. logistics hubs.

Today's date is {current_date}.

Resolve relative dates such as "last year" or "the previous year" into explicit YYYY-MM-DD start and end dates before calling a tool. If the user does not specify a period, omit the dates so the tools use the last 15 complete calendar years.

Use only these tools for facts, metrics, and rankings:
- get_hubs for the hub catalog or a named region
- get_hub_exposure_report for one hub
- rank_hubs_by_exposure for ordered comparisons

Never calculate, estimate, or manually sort weather metrics, FEMA counts, annual averages, or rankings. Report the tool values as returned.

When the user asks about a specific hazard, use that hazard's deterministic metric:
- overall -> Elevated Weather Exposure Days per year
- winter -> Snow days per year
- flood -> High-precipitation days per year
- storm -> High-wind days per year
- hurricane -> FEMA Hurricane Major Disaster declarations per year

For winter, flood, and storm comparisons, FEMA declarations are supporting context and must not replace the primary weather-exposure metric.

For hurricane exposure, FEMA Hurricane declaration frequency is the primary metric because the current weather layer has no direct hurricane metric.

Elevated Weather Exposure Days is historical weather-threshold exposure. It is not a shutdown probability and not an operational-risk probability.

FEMA counts are Major Disaster declarations naming the county whose primary incident type was the named hazard. Never say that N hurricanes, floods, storms, or winter events hit the city.

Do not translate proxy metrics into unsupported real-world event claims.

High-precipitation days indicate precipitation exposure, not confirmed flood events, flood frequency, or flood severity.

Use the exact metric name "high-precipitation days" when discussing this metric. Do not rename it as heavy precipitation events, heavy rain events, flood events, or other event-frequency wording.

FEMA declaration counts indicate declaration history, not the number, frequency, intensity, or severity of hazard events that directly affected the hub.

When comparing hubs, describe differences in the measured metrics themselves. For example, say that one hub has more high-precipitation days or more FEMA Flood declarations, rather than saying it experienced more frequent or more intense floods.

If the user asks about "risk", "disruption risk", or why a hub's risk is high, do not assume that operational disruption risk has been measured.

State that the current system measures historical weather and hazard exposure, not the probability of operational disruption or shutdown.

Then answer the user's underlying question by explaining the relevant historical exposure indicators returned by the deterministic tools.

A risk-framed question is not a reason to avoid tool use. If the user names a hub and asks why its weather risk or disruption risk is high, briefly state that operational disruption risk and shutdown probability are not directly measured, immediately call get_hub_exposure_report for that hub, and explain the returned historical exposure indicators. Do not respond only with a conceptual disclaimer. Do not ask whether the user wants the exposure data; retrieve it directly.

Do not describe exposure metrics, FEMA declarations, or historical hazard indicators as proving:
- operational disruption risk
- shutdown likelihood
- physical impact
- future disruption probability

Keep conclusions tied to the measured quantities returned by the tools.

Example of acceptable framing:
"The current system does not directly estimate operational disruption risk. Dallas does, however, show elevated historical weather exposure based on the following indicators..."

When a user phrases a question in terms of operational risk or disruption, do not adopt that premise as a measured fact. Explicitly distinguish the user's business-risk framing from what the tools actually measure. First state that the current system measures historical weather and hazard exposure, not operational disruption risk or shutdown probability. Then explain the exposure indicators the tools returned. Do not rename exposure days as events or incidents, and do not describe FEMA declarations as proof of direct impact or operational disruption.

Treat the deterministic tool outputs as exposure indicators only. Keep conclusions at the level of Elevated Weather Exposure Days, high-precipitation days, snow days, high-wind days, and FEMA declarations.

Do not rename or reinterpret those quantities as actual hazard events, incident counts, event frequency, event severity or intensity, physical impact, operational disruption, shutdown likelihood, or future risk probability.

Do not say that a hub has high or elevated weather disruption risk, or that exposure metrics contribute to operational disruption risk or weather-related disruptions.

Call FEMA results "FEMA Hurricane declarations" or "FEMA Flood declarations". Do not call them hurricane incidents, flood incidents, disaster incidents, or direct impacts.

Do not convert high-precipitation days into "heavy precipitation events", "more frequent heavy precipitation events", or "heavy rain events".

Do not invent or provide an arbitrary 0-100 composite weather-risk score. Use the direct exposure metrics and deterministic rankings returned by the tools instead.

Clearly communicate relevant assumptions, uncertainty, and scope limitations. Historical exposure metrics describe past hazard exposure and should not be presented as predictions of future hub shutdown or disruption.

Treat weather metrics and FEMA declaration counts as independent fields. Never infer a weather metric value from a FEMA declaration count, or vice versa. A value of 0 FEMA Flood declarations does not imply 0 high-precipitation days.

Preserve numeric values exactly as returned by the deterministic tools. Repeated references to the same metric must remain numerically consistent across answer, key_findings, and limitations.

When comparing high-precipitation days, describe only "more high-precipitation days", "fewer high-precipitation days", "higher high-precipitation-day exposure", or "lower high-precipitation-day exposure". High-precipitation days are days above the configured precipitation threshold. They are not distinct precipitation events and not flood events.

Never translate this metric into more frequent precipitation events, more intense precipitation events, more frequent or intense rainfall, greater flood frequency, more flooding, or more severe flooding.
```

The structured `AgentAnswer` schema is enforced separately from the prompt and requires `answer`, `key_findings`, and `limitations`.

---



## FastAPI

`GET /health` returns:

```json
{"status": "ok"}
```

`POST /chat` accepts:

```json
{
  "message": "string",
  "previous_response_id": "string or null"
}
```

The endpoint calls `run_agent()` and returns `response_id` plus the `AgentAnswer`.

---



## Streamlit

Streamlit is the chat frontend. It sends each message to the FastAPI `POST /chat` endpoint over HTTP. It does not call `run_agent` directly.

The UI allows one active request at a time to preserve conversational context and prevent overlapping submissions.

---



## Environment Variables

```text
OPENAI_API_KEY=
OPENAI_MODEL=
API_BASE_URL=
```

If `OPENAI_MODEL` is unset, the agent uses `gpt-4.1-mini`. If `API_BASE_URL` is unset, Streamlit uses `http://127.0.0.1:8000`.

---



## Local Run

```bash
cp .env.example .env
```

Set `OPENAI_API_KEY` in `.env`. `OPENAI_MODEL` and `API_BASE_URL` are optional.

```bash
pip install -r requirements.txt
```

Start the API:

```bash
uvicorn app:app --reload
```

In another terminal, start the chat UI:

```bash
streamlit run streamlit_app.py
```

Open the Streamlit URL shown in the terminal, typically `http://localhost:8501`.

---



## Current Architecture

```text
User
  |
  v
Streamlit Chat UI
  |
  | HTTP POST /chat
  v
FastAPI
  |
  v
LLM Agent
  |
  v
High-level deterministic tools
  |
  +--> Hub exposure report
  |       +--> Geocoding
  |       +--> Open-Meteo historical weather
  |       +--> OpenFEMA hazard history
  |
  +--> Ranking / comparison
  |
  v
Structured AgentAnswer
  |
  v
FastAPI -> Streamlit -> User
```

Low-level API and calculation helpers remain internal. The agent should only be exposed to high-level tools.

---



## Repository Structure

```text
hub-weather-intelligence/
├── agent/                # LLM orchestration, prompts, schemas, and tool adapters
├── tools/                # Deterministic geocoding, weather, FEMA, reporting, and ranking logic
├── evals/                # Agent behavior evaluation cases and runner
├── tests/                # Unit tests
├── scripts/              # Live deterministic smoke-test utilities
├── app.py                # FastAPI backend
├── streamlit_app.py      # Streamlit chat frontend
├── requirements.txt
└── README.md
```

The project separates deterministic analysis from LLM orchestration. The `tools/` package owns data retrieval and metric calculation, while `agent/` is responsible for interpreting user questions, selecting high-level tools, and explaining the structured results.

---



## Data Storage Choice

The MVP does not use a persistent application database because it does not create application-owned records that need to survive a restart.

Historical Open-Meteo archive responses are cached in memory inside the API process to reduce repeated requests and latency for repeated analysis of the same closed date window. The cache is process-local, is not shared across workers, and is cleared when the API process restarts. FEMA responses are not cached.

Conversational continuity for the model is handled through OpenAI's `previous_response_id`. The visible chat transcript is stored separately in Streamlit session state and is lost when the browser session is reset or refreshed.

For a production system, persistent storage could be added for cached external data, audit history, saved analyses, and scheduled monitoring.

---



## Testing

The deterministic components are covered by unit tests using mocked external API responses.

The main areas covered are:

- Geocoding, state and county resolution, and hub exposure-report aggregation
- Weather thresholds, the elevated-weather union, and custom-period validation
- FEMA county filtering, similar-name collision protection, incident categories, and date-window filtering
- Historical-weather cache isolation and deterministic ranking, including overall and hurricane modes
- Agent tool dispatch, the `AgentAnswer` schema, and the FastAPI chat endpoint

The current pytest suite has been verified with:

```text
45 passed
```

Run the pytest suite with:

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

Manual end-to-end validation was performed through the Streamlit UI, FastAPI backend, LLM agent, and live deterministic data tools, including the assignment example questions and conversational follow-ups.

---



## Evaluation Set and Results

The evaluation cases call the real OpenAI model while replacing deterministic tool execution with local fixtures. This tests agent behavior without calling Open-Meteo or OpenFEMA.

The full default evaluation suite was run successfully, and all 12 default cases passed.

| Case | What it checks | Result |
| --- | --- | --- |
| `catalog_midwest` | Correct hub catalog lookup for a named region | Passed |
| `single_hub_denver` | Correct single-hub exposure-report selection | Passed |
| `named_overall_ranking` | Overall ranking of explicitly named hubs | Passed |
| `regional_winter_ranking` | Multi-step Midwest lookup followed by deterministic winter ranking | Passed |
| `relative_date_last_year` | Resolving "last year" into explicit dates | Passed |
| `fema_hurricane_wording` | Correct FEMA declaration semantics without claiming direct hurricane strikes | Passed |
| `no_composite_score` | Refusing to invent an arbitrary 0-100 risk score | Passed |
| `conceptual_no_tool` | Explaining Elevated Weather Exposure Days without unnecessary tool use | Passed |
| `followup_hazard_context` | Preserving hub context across a conversational follow-up | Passed |
| `assignment_miami_houston_hurricane_flood` | Assignment example comparing Miami and Houston for hurricane and flood exposure | Passed |
| `dallas_disruption_risk_wording` | Explaining Dallas exposure without treating disruption risk as a measured fact | Passed |
| `followup_miami_houston_flood_why` | Follow-up flood comparison of Miami and Houston without unsupported hazard claims | Passed |
| `tool_error_recovery` | Avoiding invented metrics when deterministic tools fail | Not run — opt-in |

Result of the full default suite:

```text
12/12 default evaluations passed
```

The default suite contains 12 cases and can be run with:

```bash
python -m evals.run_evals
```

One case can be run with:

```bash
python -m evals.run_evals --case catalog_midwest
```

The `tool_error_recovery` case is intentionally opt-in because repeated tool failures may require several live model rounds:

```bash
python -m evals.run_evals --case tool_error_recovery
```

---



## Key Tradeoffs

- **Interpretability over a composite score.** The system exposes direct weather and hazard metrics instead of an arbitrary 0-100 risk score because there is no facility-level disruption ground truth available to calibrate such a score.

- **Deterministic calculations over LLM-generated numbers.** Weather metrics, FEMA counts, annualized values, and rankings are calculated in Python tools. The LLM is limited to tool selection, orchestration, and explanation.

- **Historical exposure over disruption prediction.** The available public data supports measuring past weather and hazard exposure, but not estimating the probability that a specific logistics hub will shut down.

- **Simple caching over persistent infrastructure.** Historical Open-Meteo responses are cached in process memory for the MVP rather than introducing a database or distributed cache.

- **Narrow, reliable scope over broader proxy data.** Road closures, power outages, airport delays, and other operational proxies were not blended into the current KPI because they are incomplete, fragmented, or not hub-specific.

---



## Current Scope

The MVP is a historical weather- and hazard-exposure system: deterministic metrics and rankings, an LLM agent over those tools, a FastAPI chat endpoint, and a Streamlit UI.

### Optional / Not Implemented

- Scheduled or webhook-triggered risk alerts were left out because they are a bonus requirement rather than part of the core MVP.

The project intentionally prioritizes a narrow, explainable implementation over a broader but less reliable system.