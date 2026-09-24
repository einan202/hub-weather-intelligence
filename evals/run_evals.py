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


def _negated(text: str, match: re.Match) -> bool:
    window = text[max(0, match.start() - 50):match.start()]
    return re.search(r"\b(not|never|no|n't)\b", window, re.IGNORECASE) is not None


def _has_positive_claim(text: str, pattern: str) -> bool:
    for match in re.finditer(pattern, text, re.IGNORECASE):
        if not _negated(text, match):
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

    return {
        "name": case["name"],
        "passed": not failures,
        "expected": _expected_behavior(expect),
        "calls": executor.calls,
        "failures": failures,
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
        print()

    print(f"{passed}/{len(results)} passed")

    if passed != len(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
