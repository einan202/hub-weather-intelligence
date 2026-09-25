import argparse
import json
import re
from datetime import date
from pathlib import Path
from unittest.mock import patch

from agent.schemas import AgentAnswer
from agent.service import run_agent


CASES_PATH = Path(__file__).with_name("cases.json")

METRIC_NAMES = {
    "overall": "elevated_weather_exposure_days_per_year",
    "winter": "snow_days_per_year",
    "flood": "high_precipitation_days_per_year",
    "storm": "high_wind_days_per_year",
    "hurricane": "fema_hurricane_declarations_per_year",
}

STATE_NAMES = {
    "denver": "Colorado",
    "dallas": "Texas",
    "miami": "Florida",
    "houston": "Texas",
    "chicago": "Illinois",
    "minneapolis": "Minnesota",
    "detroit": "Michigan",
    "st. louis": "Missouri",
}

ERROR_FIXTURE = {
    "error": {
        "type": "RuntimeError",
        "message": "fixture failure",
    }
}

CONTROLLED_FAILURES = {
    "Max tool-call iterations exceeded",
    "Model response did not include a parsed final answer.",
}

# Plural "floods" and "flood events" avoid matching "flood declarations".
FLOOD_EVENT_OVERCLAIM = re.compile(
    r"\bmore\s+(?:frequent|intense|severe)\s+floods\b"
    r"|\bmore\s+(?:frequent|intense|severe)\s+flood\s+events\b"
    r"|\bmore\s+(?:frequent|intense|severe)\s+flooding\b"
    r"|\bmore\s+flood\s+events\b"
    r"|\bmore\s+floods\b"
    r"|\bfloods?\s+more\s+(?:frequently|often)\b"
    r"|\bflooding\s+more\s+(?:frequently|often)\b"
    r"|\bflooded\s+more\s+(?:frequently|often)\b"
    r"|\b(?:higher|greater|increased)\s+flood\s+"
    r"(?:frequency|intensity|severity)\b"
    r"|\b(?:higher|greater)\s+(?:frequency|intensity|severity)\s+"
    r"of\s+floods\b"
    r"|\bmore\s+flooding\b"
    r"|\bmore\s+flooding\s+incidents\b"
    r"|\bmore\s+flood\s+incidents\b"
    r"|\b(?:greater|higher|more)\s+flood\s+impact\b"
    r"|\bflood\s+impact\s+is\s+(?:greater|higher|larger)\b",
    re.IGNORECASE,
)

# "high-precipitation days" is the metric name and must not match.
PRECIP_EVENT_RENAME = re.compile(
    r"\bhigh[-\s]precipitation\s+events?\b"
    r"|\bheavy\s+(?:precipitation|precip|rain|rainfall)\s+events?\b"
    r"|\b(?:extreme|severe|intense)\s+"
    r"(?:precipitation|rain|rainfall)\s+events?\b"
    r"|\bmore\s+frequent\s+(?:precipitation|precip|rain|rainfall)\s+events?\b"
    r"|\bmore\s+frequent\s+or\s+intense\s+"
    r"(?:precipitation|rain|rainfall)\b",
    re.IGNORECASE,
)

OUTCOME_OVERCLAIM = re.compile(
    r"\b(?:high|higher|greater|increased)\s+"
    r"(?:weather\s+|operational\s+)?disruption\s+risks?\b"
    r"|\boperational\s+disruption\s+risks?\s+"
    r"(?:is|are)\s+(?:high|higher|elevated)\b"
    r"|\bdisruption\s+risks?\s+(?:is|are)\s+"
    r"(?:considered\s+|rated\s+)?(?:high|higher|elevated|driven)\b"
    r"|\bpose[sd]?\s+disruption\s+risks?\b"
    r"|\bgreater\s+operational\s+disruption(?:\s+risks?)?\b"
    r"|\blikely\s+to\s+(?:experience|face|suffer)\s+"
    r"(?:operational\s+)?disruption\b"
    r"|\b(?:high|higher|elevated)\s+shutdown\s+probability\b"
    r"|\bshutdown\s+probability\s+is\s+(?:high|higher|elevated)\b"
    r"|\bdirect(?:ly)?\s+(?:physical(?:ly)?\s+)?impact(?:ed)?\b"
    r"|\bphysical(?:ly)?\s+(?:impact(?:ed)?|affected)\b"
    r"|\bhazards?\s+directly\s+affected\b"
    r"|\bdirectly\s+affected\s+(?:dallas|the\s+hub|the\s+city)\b"
    r"|\bfuture\s+disruption\b"
    r"|\b(?:elevated|high|higher|greater)\s+risk\s+of\s+"
    r"(?:weather-related\s+)?disruptions?\b"
    r"|\bweather-related\s+disruptions?\b"
    r"|\bcontribut(?:e|es|ing)\s+to\b"
    r"(?:\s+\w+){0,8}\s+"
    r"(?:disruptions?|disruption\s+risks?)\b"
    r"|\b(?:cause|causes|explain|explains|prove|proves)\b"
    r"(?:\s+\w+){0,12}\s+"
    r"(?:operational\s+|weather\s+)?disruption\s+risks?\b"
    r"|\bhigh[-\s]precipitation\s+and\s+high[-\s]wind\s+events?\b"
    r"|\bhigh[-\s]wind\s+and\s+high[-\s]precipitation\s+events?\b"
    r"|\b(?:high[-\s]precipitation|high[-\s]wind)\s+events?\b"
    r"|\bweather\s+incidents?\b"
    r"|\bprone\s+to\b(?:\s+\w+){0,6}\s+incidents?\b"
    r"|\b(?:can|could|may)\s+disrupt\s+operations\b"
    r"|\bdisrupt(?:s|ing)?\s+operations\b",
    re.IGNORECASE,
)

# Declarations are not incident counts. "incident frequency" in a
# disclaimer does not match these phrases.
INCIDENT_OVERCLAIM = re.compile(
    r"\bhurricane\s+incident\s+counts?\b"
    r"|\b(?:higher|more|greater)\s+hurricane\s+incidents?\b"
    r"|\b(?:flood|hurricane|disaster)\s+incidents?\b",
    re.IGNORECASE,
)

_DISCLAIMER = re.compile(
    r"\b(not|never|no|n't|cannot|can't|rather than|instead of|without)\b",
    re.IGNORECASE,
)

UNRELATED_HUBS = (
    "denver",
    "dallas",
    "chicago",
    "minneapolis",
    "detroit",
    "st. louis",
)


def load_suite() -> dict:
    return json.loads(CASES_PATH.read_text())


def previous_calendar_year(today: date | None = None) -> tuple[str, str]:
    current = today or date.today()
    year = current.year - 1
    return f"{year}-01-01", f"{year}-12-31"


def _city_key(city: str | None) -> str:
    return (city or "").strip().lower()


def _state_is_acceptable(city: str | None, state: str | None) -> bool:
    if state is None:
        return True

    expected = STATE_NAMES.get(_city_key(city))
    if expected is None:
        return False

    return state.strip().lower() == expected.lower()


def _cities(arguments: dict) -> set[str]:
    cities = set()

    for hub in arguments.get("hubs") or []:
        city = hub.get("city")
        if isinstance(city, str) and city.strip():
            cities.add(city.strip())

    return cities


def _report_fixture(arguments: dict, hurricane_count: int) -> dict:
    city = arguments.get("city") or "Unknown"
    normalized = _city_key(city)
    hurricane_declarations = (
        hurricane_count if normalized == "miami" else 0
    )

    return {
        "location": {
            "name": city,
            "state": arguments.get("state"),
            "county": city,
        },
        "period": {
            "start_date": arguments.get("start_date"),
            "end_date": arguments.get("end_date"),
            "total_days": 365,
            "years_observed": 1.0,
        },
        "weather_exposure": {
            "snowfall": {
                "total_days": 365,
                "snow_days": 10,
                "snow_days_percentage": 2.74,
                "average_days_per_year": 10.0,
            },
            "high_precipitation": {
                "total_days": 365,
                "high_precipitation_days": 4,
                "high_precipitation_days_percentage": 1.1,
                "threshold_mm": 25.4,
                "average_days_per_year": 4.0,
            },
            "high_wind": {
                "total_days": 365,
                "high_wind_days": 3,
                "high_wind_days_percentage": 0.82,
                "gust_threshold_kmh": 74.0,
                "average_days_per_year": 3.0,
            },
            "elevated_weather_exposure": {
                "total_days": 365,
                "elevated_exposure_days": 16,
                "elevated_exposure_days_percentage": 4.38,
                "precipitation_threshold_mm": 25.4,
                "gust_threshold_kmh": 74.0,
                "average_days_per_year": 16.0,
            },
        },
        "fema_major_disaster_declarations": {
            "counts": {
                "flood": 1,
                "hurricane": hurricane_declarations,
                "severe_storm": 0,
                "winter": 0,
            },
            "recent_events": [],
        },
    }


def _ranking_fixture(arguments: dict) -> dict:
    hazard = arguments.get("hazard") or "overall"
    metric = METRIC_NAMES.get(hazard)

    if metric is None:
        return {
            "error": {
                "type": "ValueError",
                "message": f"Unsupported hazard '{hazard}'.",
            }
        }

    if hazard == "overall":
        fema_context = {
            "flood": 0,
            "hurricane": 0,
            "severe_storm": 0,
            "winter": 0,
        }
    elif hazard == "storm":
        fema_context = {"severe_storm": 0}
    else:
        fema_context = {hazard: 0}

    hubs = []

    for index, hub in enumerate(arguments.get("hubs") or [], start=1):
        hubs.append(
            {
                "city": hub.get("city"),
                "state": hub.get("state"),
                "county": hub.get("city"),
                "metric": metric,
                "value": 0.0,
                "fema_context": dict(fema_context),
                "rank": index,
            }
        )

    return {
        "hazard": hazard,
        "ranking_metric": metric,
        "hubs": hubs,
    }


def _hub_fixture(arguments: dict, midwest_hubs: list[dict]) -> list[dict]:
    region = arguments.get("region")

    if region is None:
        return [dict(hub) for hub in midwest_hubs]

    if region.strip().lower() == "midwest":
        return [dict(hub) for hub in midwest_hubs]

    return []


class FixtureExecutor:
    def __init__(self, suite: dict, use_error_fixture: bool):
        self.midwest_hubs = suite["fixtures"]["midwest_hubs"]
        self.hurricane_count = suite["fixtures"][
            "miami_hurricane_declarations"
        ]
        self.use_error_fixture = use_error_fixture
        self.calls = []

    def __call__(self, name: str, arguments: dict):
        self.calls.append(
            {
                "name": name,
                "arguments": arguments,
            }
        )

        if self.use_error_fixture:
            result = ERROR_FIXTURE
        elif name == "get_hubs":
            result = _hub_fixture(arguments, self.midwest_hubs)
        elif name == "get_hub_exposure_report":
            result = _report_fixture(arguments, self.hurricane_count)
        elif name == "rank_hubs_by_exposure":
            result = _ranking_fixture(arguments)
        else:
            result = {
                "error": {
                    "type": "ValueError",
                    "message": f"Unknown tool '{name}'.",
                }
            }

        self.calls[-1]["result"] = result
        return result


def combined_answer_text(output: dict) -> str:
    parts = [output.get("answer") or ""]
    parts.extend(output.get("key_findings") or [])
    parts.extend(output.get("limitations") or [])
    return "\n".join(str(part) for part in parts)


def _is_disclaimed(text: str, start: int, window: int = 160) -> bool:
    prefix = text[max(0, start - window):start]
    return _DISCLAIMER.search(prefix) is not None


def _has_undisclaimed(text: str, pattern: re.Pattern) -> bool:
    for match in pattern.finditer(text):
        if not _is_disclaimed(text, match.start()):
            return True

    return False


def _has_flood_event_overclaim(text: str) -> bool:
    """Fail event-frequency or severity claims, not negated metric caveats."""
    return _has_undisclaimed(text, FLOOD_EVENT_OVERCLAIM)


def _has_precip_event_rename(text: str) -> bool:
    """Fail event-category renames of high-precipitation days."""
    return _has_undisclaimed(text, PRECIP_EVENT_RENAME)


def _has_outcome_overclaim(text: str) -> bool:
    """Fail claims that proxies prove impact, severity, or disruption."""
    return _has_undisclaimed(text, OUTCOME_OVERCLAIM)


def _has_incident_overclaim(text: str) -> bool:
    """Fail wording that turns declarations into incident counts."""
    return _has_undisclaimed(text, INCIDENT_OVERCLAIM)


_ZERO_HIGH_PRECIP_DAYS = re.compile(
    r"\b(?:zero|no|0)\s+high[-\s]precipitation\s+days\b",
    re.IGNORECASE,
)


def _claims_zero_high_precip(text: str, city: str) -> bool:
    """Fail a zero-day claim tied to a city, not a negated caveat."""
    city_re = re.compile(
        rf"\b{re.escape(_city_key(city))}\b",
        re.IGNORECASE,
    )
    for match in _ZERO_HIGH_PRECIP_DAYS.finditer(text):
        if _is_disclaimed(text, match.start()):
            continue
        window = text[max(0, match.start() - 80):match.start()]
        if city_re.search(window):
            return True
    return False


def _check_nonzero_precip_not_called_zero(
    calls: list[dict],
    outputs: list[dict | None],
) -> list[str]:
    """Reject zero high-precipitation days when the hub report is non-zero."""
    returned = {}

    for call in calls:
        if call.get("name") != "get_hub_exposure_report":
            continue

        result = call.get("result") or {}
        if _result_error(result):
            continue

        precip = (
            result.get("weather_exposure") or {}
        ).get("high_precipitation") or {}
        annual = precip.get("average_days_per_year")
        city = (call.get("arguments") or {}).get("city")
        if annual is None or not city or float(annual) == 0.0:
            continue

        returned[_city_key(city)] = (city, float(annual))

    failures = []
    texts = [
        combined_answer_text(output)
        for output in outputs
        if output
    ]

    for city, annual in returned.values():
        if any(_claims_zero_high_precip(text, city) for text in texts):
            failures.append(
                f"answer says {city} has zero high-precipitation days "
                f"although the hub report returned {annual:g} per year"
            )

    return failures


def _has_positive_claim(text: str, pattern: str) -> bool:
    for match in re.finditer(pattern, text, re.IGNORECASE):
        if not _is_disclaimed(text, match.start()):
            return True

    return False


def _calls_named(calls: list[dict], name: str) -> list[dict]:
    return [call for call in calls if call["name"] == name]


def _ordered_calls(names: list[str], sequence: list[str]) -> bool:
    """Require sequence order while allowing extra get_hubs calls."""
    index = 0

    for name in names:
        if index < len(sequence) and name == sequence[index]:
            index += 1
            continue

        if name == "get_hubs":
            continue

        return False

    return index == len(sequence)


def _expected_behavior(expect: dict) -> str:
    parts = []

    if expect.get("tool_sequence"):
        parts.append("sequence=" + " -> ".join(expect["tool_sequence"]))

    if expect.get("required_tools"):
        parts.append("required=" + ",".join(expect["required_tools"]))

    if expect.get("forbidden_tools"):
        parts.append("forbidden=" + ",".join(expect["forbidden_tools"]))

    if expect.get("no_tools"):
        parts.append("no tool calls")

    if expect.get("hazard"):
        parts.append(f"hazard={expect['hazard']}")

    if expect.get("ranking_hazards"):
        parts.append(
            "hazards=" + " -> ".join(expect["ranking_hazards"])
        )

    if expect.get("error_fixture"):
        parts.append("tool error fixture")

    if expect.get("context_turns"):
        parts.append(
            "each turn uses Denver and Dallas via ranking or hub reports"
        )

    if expect.get("comparison_cities"):
        parts.append(
            "compare "
            + " and ".join(expect["comparison_cities"])
            + " for hurricane and flood via reports or rankings"
        )

    if expect.get("forbid_flood_event_claims"):
        parts.append("no flood frequency or severity overclaim")

    if expect.get("forbid_precip_event_rename"):
        parts.append("no heavy-precipitation event rename")

    if expect.get("forbid_outcome_overclaims"):
        parts.append("no disruption, impact, or future-event overclaim")

    if expect.get("context_cities"):
        parts.append(
            "preserve "
            + " and ".join(expect["context_cities"])
        )

    if expect.get("flood_metric_grounding"):
        parts.append("final answer stays on precipitation and flood declarations")

    if expect.get("disruption_limitation"):
        parts.append("states that disruption risk is not directly measured")

    return "; ".join(parts) or "wording and schema"


def _check_schema(output: dict | None) -> list[str]:
    if output is None:
        return ["final output is missing"]

    try:
        AgentAnswer.model_validate(output)
    except Exception as error:
        return [f"AgentAnswer schema failed: {error}"]

    return []


def _check_tools(calls: list[dict], expect: dict) -> list[str]:
    failures = []
    names = [call["name"] for call in calls]

    if expect.get("no_tools") and names:
        failures.append(f"expected no tool calls, got {names}")

    for tool_name in expect.get("required_tools") or []:
        if tool_name not in names:
            failures.append(f"missing required tool {tool_name}")

    for tool_name in expect.get("forbidden_tools") or []:
        if tool_name in names:
            failures.append(f"forbidden tool was called: {tool_name}")

    sequence = expect.get("tool_sequence") or []
    ranking_hazards = expect.get("ranking_hazards")

    if sequence and not ranking_hazards and not _ordered_calls(names, sequence):
        failures.append(
            "expected tool order "
            + " -> ".join(sequence)
            + f", got {names or ['none']}"
        )

    if expect.get("region"):
        region_calls = [
            call
            for call in _calls_named(calls, "get_hubs")
            if (call["arguments"].get("region") or "").strip().lower()
            == expect["region"].lower()
        ]
        if not region_calls:
            failures.append(
                f"get_hubs was not called for region {expect['region']}"
            )

    if expect.get("report_city"):
        city = expect["report_city"]
        matches = [
            call
            for call in _calls_named(calls, "get_hub_exposure_report")
            if _city_key(call["arguments"].get("city")) == _city_key(city)
            and _state_is_acceptable(
                city,
                call["arguments"].get("state"),
            )
        ]
        if not matches:
            failures.append(
                f"get_hub_exposure_report was not called for {city}"
            )
        elif expect.get("report_state_required"):
            required_state = expect["report_state_required"].strip().lower()
            state_matches = [
                call
                for call in matches
                if (call["arguments"].get("state") or "").strip().lower()
                == required_state
            ]
            if not state_matches:
                failures.append(
                    f"get_hub_exposure_report for {city} did not use "
                    f"state {expect['report_state_required']}"
                )

    if expect.get("previous_calendar_year"):
        start_date, end_date = previous_calendar_year()
        dated = [
            call
            for call in _calls_named(calls, "get_hub_exposure_report")
            if call["arguments"].get("start_date") == start_date
            and call["arguments"].get("end_date") == end_date
        ]
        if not dated:
            failures.append(
                "report dates were not the previous calendar year "
                f"{start_date} to {end_date}"
            )

    rank_calls = _calls_named(calls, "rank_hubs_by_exposure")

    if expect.get("hazard"):
        matching = [
            call
            for call in rank_calls
            if call["arguments"].get("hazard") == expect["hazard"]
        ]
        if not matching:
            failures.append(
                f"ranking hazard was not {expect['hazard']}"
            )
        else:
            failures.extend(
                _check_ranked_cities(
                    matching[0],
                    expect,
                    calls,
                )
            )

    if ranking_hazards:
        actual_hazards = [
            call["arguments"].get("hazard")
            for call in rank_calls
        ]
        if actual_hazards != ranking_hazards:
            failures.append(
                "expected ranking hazards "
                + " -> ".join(ranking_hazards)
                + f", got {actual_hazards}"
            )
        else:
            for call in rank_calls:
                failures.extend(
                    _check_ranked_cities(call, expect, calls)
                )

    return failures


def _city_set(cities: list[str]) -> set[str]:
    return {_city_key(city) for city in cities}


def _check_context_turns(
    turn_calls: list[list[dict]],
    turns: list[dict],
) -> list[str]:
    if len(turn_calls) != len(turns):
        return ["context turns did not all complete"]

    failures = []

    for index, (calls, turn) in enumerate(zip(turn_calls, turns), start=1):
        expected = _city_set(turn["cities"])
        hazard = turn["hazard_if_ranked"]
        rank_calls = _calls_named(calls, "rank_hubs_by_exposure")
        report_calls = _calls_named(calls, "get_hub_exposure_report")
        ranked_ok = False
        reported_cities = set()

        if not rank_calls and not report_calls:
            failures.append(
                f"turn {index} did not use ranking or hub reports"
            )
            continue

        for call in rank_calls:
            arguments = call["arguments"]
            actual = _city_set(list(_cities(arguments)))

            if arguments.get("hazard") != hazard:
                failures.append(
                    f"turn {index} ranking hazard was "
                    f"{arguments.get('hazard')}, expected {hazard}"
                )

            if actual != expected:
                failures.append(
                    f"turn {index} ranked {sorted(actual)}, "
                    f"expected {sorted(expected)}"
                )
            else:
                ranked_ok = arguments.get("hazard") == hazard

            for hub in arguments.get("hubs") or []:
                if not _state_is_acceptable(hub.get("city"), hub.get("state")):
                    failures.append(
                        f"turn {index} has an unexpected state for "
                        f"{hub.get('city')}"
                    )

        for call in report_calls:
            city = call["arguments"].get("city")
            reported_cities.add(_city_key(city))

            if not _state_is_acceptable(city, call["arguments"].get("state")):
                failures.append(
                    f"turn {index} has an unexpected state for {city}"
                )

        if reported_cities - expected:
            failures.append(
                f"turn {index} included an unrelated hub report"
            )

        if not ranked_ok and reported_cities != expected:
            failures.append(
                f"turn {index} did not cover {sorted(expected)} "
                "with ranking or hub reports"
            )

    return failures


def _float_tokens(text: str) -> list[float]:
    return [
        float(token)
        for token in re.findall(r"\d+(?:\.\d+)?", text)
    ]


def _value_present(text: str, value: float) -> bool:
    return any(
        abs(token - float(value)) < 1e-6
        for token in _float_tokens(text)
    )


def _declaration_count_stated(
    text: str,
    city: str,
    hazard: str,
    count: float,
) -> bool:
    """Require the numeric count, except zero may be stated as an absence."""
    if float(count) != 0.0:
        return _value_present(text, count)

    if _value_present(text, 0):
        return True

    city_name = _city_key(city)
    hazard_name = hazard.strip().lower()
    absence = re.compile(r"\b(?:zero|none|no)\b", re.IGNORECASE)

    for sentence in re.split(r"[.\n]+", text):
        lowered = sentence.lower()
        if city_name not in lowered or hazard_name not in lowered:
            continue
        if "declaration" not in lowered:
            continue
        if absence.search(sentence):
            return True

    return False


def _result_error(result: object) -> bool:
    return isinstance(result, dict) and "error" in result


def _exact_cities(arguments: dict, expected: set[str]) -> bool:
    return _city_set(list(_cities(arguments))) == expected


def _check_hurricane_flood_comparison(
    calls: list[dict],
    output: dict | None,
    expect: dict,
) -> list[str]:
    """Accept reports or rankings that cover hurricane and flood for the cities."""
    failures = []
    expected = _city_set(expect["comparison_cities"])
    report_calls = []
    hurricane_rank_calls = []
    flood_rank_calls = []

    for call in _calls_named(calls, "get_hub_exposure_report"):
        arguments = call["arguments"]
        city = arguments.get("city")
        key = _city_key(city)

        if key not in expected:
            failures.append(
                f"analysis included an unrelated hub report for {city}"
            )
            continue

        if not _state_is_acceptable(city, arguments.get("state")):
            failures.append(
                f"unexpected state for {city}: {arguments.get('state')}"
            )

        if not _result_error(call.get("result")):
            report_calls.append(call)

    for call in _calls_named(calls, "rank_hubs_by_exposure"):
        arguments = call["arguments"]
        actual = _city_set(list(_cities(arguments)))

        if actual - expected:
            failures.append(
                "ranking included an unrelated hub: "
                + ", ".join(sorted(actual - expected))
            )
            continue

        for hub in arguments.get("hubs") or []:
            if not _state_is_acceptable(hub.get("city"), hub.get("state")):
                failures.append(
                    f"unexpected state for {hub.get('city')}: "
                    f"{hub.get('state')}"
                )

        if not _exact_cities(arguments, expected):
            continue

        if _result_error(call.get("result")):
            continue

        hazard = arguments.get("hazard")
        if hazard == "hurricane":
            hurricane_rank_calls.append(call)
        elif hazard == "flood":
            flood_rank_calls.append(call)

    reported = {
        _city_key(call["arguments"].get("city"))
        for call in report_calls
    }
    reports_cover = reported == expected
    hurricane_covered = reports_cover or bool(hurricane_rank_calls)
    flood_covered = reports_cover or bool(flood_rank_calls)

    if not hurricane_covered:
        failures.append(
            "hurricane exposure was not retrieved from hub reports "
            "or a hurricane ranking of "
            + " and ".join(expect["comparison_cities"])
        )

    if not flood_covered:
        failures.append(
            "flood exposure was not retrieved from hub reports "
            "or a flood ranking of "
            + " and ".join(expect["comparison_cities"])
        )

    if output is None:
        failures.append("final output is missing")
        return failures

    text = combined_answer_text(output)
    lowered = text.lower()

    for city in expect["comparison_cities"]:
        if _city_key(city) not in lowered:
            failures.append(f"answer does not discuss {city}")

    if "hurricane" not in lowered:
        failures.append("answer does not address hurricane exposure")

    if "flood" not in lowered and "precipitation" not in lowered:
        failures.append("answer does not address flood exposure")

    if "declaration" not in lowered:
        failures.append(
            "answer does not describe hurricane counts as declarations"
        )

    if _has_positive_claim(text, r"hurricanes?\s+hit"):
        failures.append("answer claims hurricanes hit the location")

    if reports_cover:
        missing_hurricane_counts = [
            call["arguments"].get("city")
            for call in report_calls
            if not _declaration_count_stated(
                text,
                call["arguments"].get("city") or "",
                "hurricane",
                float(
                    call["result"]["fema_major_disaster_declarations"][
                        "counts"
                    ]["hurricane"]
                ),
            )
        ]
        if missing_hurricane_counts:
            failures.append(
                "answer does not use the FEMA hurricane declaration "
                "counts returned by the hub reports"
            )

        for call in report_calls:
            precip = call["result"]["weather_exposure"]["high_precipitation"]
            options = {
                float(precip["high_precipitation_days"]),
                float(precip["average_days_per_year"]),
                float(precip["high_precipitation_days_percentage"]),
            }
            if not any(_value_present(text, value) for value in options):
                failures.append(
                    "answer does not use the high-precipitation metric "
                    f"returned for {call['arguments'].get('city')}"
                )
    elif hurricane_rank_calls:
        for call in hurricane_rank_calls:
            missing = [
                hub.get("city")
                for hub in call["result"].get("hubs") or []
                if not _declaration_count_stated(
                    text,
                    hub.get("city") or "",
                    "hurricane",
                    float(hub["value"]),
                )
            ]
            if missing:
                failures.append(
                    "answer does not use the hurricane ranking values"
                )
                break

    if not reports_cover and flood_rank_calls:
        for call in flood_rank_calls:
            values = [
                float(hub["value"])
                for hub in call["result"].get("hubs") or []
            ]
            if not all(_value_present(text, value) for value in values):
                failures.append(
                    "answer does not use the flood ranking values"
                )
                break

    return failures


def _check_ranked_cities(
    call: dict,
    expect: dict,
    calls: list[dict],
) -> list[str]:
    failures = []
    arguments = call["arguments"]
    actual = _cities(arguments)

    if expect.get("cities_from_midwest_fixture"):
        source = [
            item
            for item in _calls_named(calls, "get_hubs")
            if (item["arguments"].get("region") or "").strip().lower()
            == "midwest"
        ]
        if not source:
            return ["Midwest get_hubs result was not available"]

        expected = {
            hub["city"]
            for hub in source[0]["result"]
        }
    else:
        expected = set(expect.get("cities") or [])

    if expected and actual != expected:
        failures.append(
            f"ranked cities were {sorted(actual)}, expected {sorted(expected)}"
        )

    for hub in arguments.get("hubs") or []:
        if not _state_is_acceptable(hub.get("city"), hub.get("state")):
            failures.append(
                f"unexpected state for {hub.get('city')}: {hub.get('state')}"
            )

    return failures


def _states_disruption_limitation(text: str) -> bool:
    targets = re.compile(
        r"operational disruption|operational impact|shutdown probability|"
        r"shutdown(?:\s+or\s+disruption)?\s+likelihood|"
        r"disruption likelihood|disruption risk|operational[-\s]risk|"
        r"future risk|future predictions|future disruptions|shutdowns",
        re.IGNORECASE,
    )
    for match in targets.finditer(text):
        window = text[max(0, match.start() - 80):match.end() + 40]
        if _DISCLAIMER.search(window):
            return True

    return False


def _check_overclaim_flags(text: str, expect: dict) -> list[str]:
    failures = []

    if expect.get("forbid_flood_event_claims") and _has_flood_event_overclaim(text):
        failures.append(
            "answer treats high-precipitation days or FEMA declarations "
            "as flood frequency or severity"
        )

    if expect.get("forbid_flood_event_claims") and _has_incident_overclaim(text):
        failures.append(
            "answer converts declarations into incident counts"
        )

    if expect.get("forbid_precip_event_rename") and _has_precip_event_rename(text):
        failures.append(
            "answer renames high-precipitation days as a weather event "
            "category"
        )

    if expect.get("forbid_outcome_overclaims") and _has_outcome_overclaim(text):
        failures.append(
            "answer treats proxy metrics as operational disruption, "
            "physical impact, or future disruption"
        )

    return failures


def _check_context_cities(
    turn_calls: list[list[dict]],
    expect: dict,
) -> list[str]:
    """Allow reports or a flood ranking, and reject unrelated hubs."""
    expected = _city_set(expect["context_cities"])
    failures = []
    covered = False

    for index, calls in enumerate(turn_calls, start=1):
        reported = set()

        for call in _calls_named(calls, "get_hub_exposure_report"):
            city = call["arguments"].get("city")
            key = _city_key(city)

            if key not in expected:
                failures.append(
                    f"turn {index} included an unrelated hub report for {city}"
                )
                continue

            if not _state_is_acceptable(city, call["arguments"].get("state")):
                failures.append(
                    f"turn {index} has an unexpected state for {city}"
                )

            if not _result_error(call.get("result")):
                reported.add(key)

        for call in _calls_named(calls, "rank_hubs_by_exposure"):
            arguments = call["arguments"]
            actual = _city_set(list(_cities(arguments)))

            if actual - expected:
                failures.append(
                    f"turn {index} ranking included an unrelated hub: "
                    + ", ".join(sorted(actual - expected))
                )
                continue

            if (
                not _result_error(call.get("result"))
                and actual == expected
                and arguments.get("hazard") == "flood"
            ):
                covered = True

        if reported == expected:
            covered = True

    if not covered:
        failures.append(
            "high-precipitation and FEMA flood context were not retrieved "
            "for " + " and ".join(expect["context_cities"])
        )

    return failures


def _check_wording(output: dict, expect: dict) -> list[str]:
    text = combined_answer_text(output)
    failures = []

    if expect.get("fema_wording"):
        if _has_positive_claim(text, r"hurricanes?\s+hit"):
            failures.append("answer claims hurricanes hit the location")

        lowered = text.lower()
        if not (
            ("fema" in lowered or "major disaster" in lowered)
            and "declaration" in lowered
            and "hurricane" in lowered
            and (
                "county" in lowered
                or "named" in lowered
                or "naming" in lowered
            )
        ):
            failures.append(
                "answer does not describe FEMA declarations naming "
                "the county by primary hurricane incident type"
            )

    failures.extend(_check_overclaim_flags(text, expect))

    if expect.get("historical_exposure_explanation"):
        lowered = text.lower()
        if "dallas" not in lowered or "exposure" not in lowered:
            failures.append(
                "answer does not explain Dallas using historical "
                "weather exposure"
            )
        elif not any(
            word in lowered
            for word in (
                "historical",
                "weather",
                "elevated",
                "precipitation",
                "snow",
                "wind",
            )
        ):
            failures.append(
                "answer does not explain Dallas using historical "
                "weather exposure"
            )

    if expect.get("disruption_limitation"):
        if not _states_disruption_limitation(text):
            failures.append(
                "answer does not say that operational disruption risk "
                "or shutdown probability is not directly measured"
            )

    if expect.get("flood_metric_grounding"):
        lowered = text.lower()
        for city in expect.get("context_cities") or []:
            if _city_key(city) not in lowered:
                failures.append(f"answer does not discuss {city}")

        if not (
            "high-precipitation" in lowered
            or "high precipitation" in lowered
            or "precipitation exposure" in lowered
            or "precipitation days" in lowered
        ):
            failures.append(
                "answer does not ground flood exposure in "
                "high-precipitation days or precipitation exposure"
            )

        if "flood" not in lowered or not (
            "declaration" in lowered or "fema" in lowered
        ):
            failures.append(
                "answer does not ground flood exposure in "
                "FEMA Flood declarations"
            )

        for hub in UNRELATED_HUBS:
            if hub in lowered:
                failures.append(f"answer introduced an unrelated hub: {hub}")

    if expect.get("no_score"):
        if re.search(r"\b\d{1,3}\s*/\s*100\b", text):
            failures.append("answer presents a fabricated X/100 score")

        if re.search(
            r"risk score\s*(of|is|:)?\s*\d+",
            text,
            re.IGNORECASE,
        ):
            failures.append("answer presents a fabricated numeric risk score")

    if expect.get("exposure_definition"):
        lowered = text.lower()
        if "exposure" not in lowered or not (
            "threshold" in lowered or "weather" in lowered
        ):
            failures.append(
                "answer does not describe historical weather-threshold exposure"
            )

        if _has_positive_claim(
            text,
            r"shutdown probability|operational[-\s]?risk probability",
        ):
            failures.append(
                "answer describes the KPI as a shutdown or "
                "operational-risk probability"
            )

    if expect.get("no_fabricated_metrics"):
        if re.search(r"\d+(?:\.\d+)?\s*%", text) or re.search(
            r"\b\d+(?:\.\d+)?\s+days\b",
            text,
            re.IGNORECASE,
        ) or re.search(
            r"\b\d+\s+declarations?\b",
            text,
            re.IGNORECASE,
        ):
            failures.append(
                "answer fabricates exposure or declaration numbers "
                "after the tool failure"
            )

    return failures


def _format_calls(calls: list[dict]) -> str:
    if not calls:
        return "  none"

    lines = []

    for index, call in enumerate(calls, start=1):
        arguments = json.dumps(call["arguments"], sort_keys=True)
        lines.append(f"  {index}. {call['name']} {arguments}")

    return "\n".join(lines)


def run_case(case: dict, suite: dict) -> dict:
    expect = case["expect"]
    executor = FixtureExecutor(
        suite,
        use_error_fixture=bool(expect.get("error_fixture")),
    )
    outputs = []
    turn_calls = []
    previous_response_id = None
    controlled_failure = None

    for turn in case["turns"]:
        call_count = len(executor.calls)
        try:
            with patch("agent.service.execute_tool", executor):
                result = run_agent(
                    turn,
                    previous_response_id=previous_response_id,
                )
        except RuntimeError as error:
            if (
                expect.get("allow_controlled_failure")
                and str(error) in CONTROLLED_FAILURES
            ):
                controlled_failure = str(error)
                break

            return {
                "name": case["name"],
                "passed": False,
                "expected": _expected_behavior(expect),
                "calls": executor.calls,
                "failures": [f"run_agent raised {error}"],
            }

        previous_response_id = result.get("response_id")
        outputs.append(result.get("output"))
        turn_calls.append(executor.calls[call_count:])

        if previous_response_id is None and turn != case["turns"][-1]:
            return {
                "name": case["name"],
                "passed": False,
                "expected": _expected_behavior(expect),
                "calls": executor.calls,
                "failures": ["turn did not return response_id"],
            }

    failures = []

    if controlled_failure is None:
        if expect.get("schema"):
            for output in outputs:
                failures.extend(_check_schema(output))

        if outputs:
            failures.extend(_check_wording(outputs[-1], expect))
            if expect.get("flood_metric_grounding") or expect.get(
                "comparison_cities"
            ):
                failures.extend(
                    _check_nonzero_precip_not_called_zero(
                        executor.calls,
                        outputs,
                    )
                )
            if expect.get("overclaims_each_turn"):
                for output in outputs[:-1]:
                    if output:
                        failures.extend(
                            _check_overclaim_flags(
                                combined_answer_text(output),
                                expect,
                            )
                        )
    elif expect.get("no_fabricated_metrics") and outputs:
        failures.extend(_check_wording(outputs[-1], expect))

    failures.extend(_check_tools(executor.calls, expect))

    if expect.get("context_turns"):
        failures.extend(
            _check_context_turns(
                turn_calls,
                expect["context_turns"],
            )
        )

    if expect.get("comparison_cities"):
        failures.extend(
            _check_hurricane_flood_comparison(
                executor.calls,
                outputs[-1] if outputs else None,
                expect,
            )
        )

    if expect.get("context_cities"):
        failures.extend(
            _check_context_cities(
                turn_calls,
                expect,
            )
        )

    return {
        "name": case["name"],
        "passed": not failures,
        "expected": _expected_behavior(expect),
        "calls": executor.calls,
        "failures": failures,
        "answer_texts": [
            combined_answer_text(output)
            for output in outputs
            if output
        ],
    }


def select_cases(suite: dict, case_name: str | None) -> list[dict]:
    cases = suite["cases"]

    if case_name is None:
        return [case for case in cases if case.get("default", True)]

    selected = [case for case in cases if case["name"] == case_name]

    if not selected:
        known = ", ".join(case["name"] for case in cases)
        raise SystemExit(f"Unknown case '{case_name}'. Known cases: {known}")

    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", default=None)
    args = parser.parse_args()

    suite = load_suite()
    selected = select_cases(suite, args.case)
    results = [run_case(case, suite) for case in selected]
    passed = 0

    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        if result["passed"]:
            passed += 1

        print(f"{status} {result['name']}")
        print(f"Expected: {result['expected']}")
        print("Actual calls:")
        print(_format_calls(result["calls"]))
        print(
            "Failed checks: "
            + (
                "none"
                if not result["failures"]
                else "; ".join(result["failures"])
            )
        )
        if result["failures"] and result.get("answer_texts"):
            print("Model answers:")
            for index, text in enumerate(result["answer_texts"], start=1):
                print(f"--- turn {index} ---")
                print(text)
        print()

    print(f"{passed}/{len(results)} passed")

    if passed != len(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
