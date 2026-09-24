from agent.tools import execute_tool
from tools.hub_catalog import get_hubs


def test_get_hubs_dispatch_without_region():
    result = execute_tool("get_hubs", {"region": None})

    assert result == get_hubs()


def test_get_hubs_dispatch_with_region():
    result = execute_tool("get_hubs", {"region": "Midwest"})

    assert result == get_hubs("Midwest")
    assert {hub["city"] for hub in result} == {
        "Chicago",
        "Minneapolis",
        "Detroit",
        "St. Louis",
    }


def test_get_hub_exposure_report_dispatch(monkeypatch):
    expected = {"location": {"name": "Dallas"}}

    def fake_report(**kwargs):
        assert kwargs == {
            "city": "Dallas",
            "state": "Texas",
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
        }
        return expected

    monkeypatch.setattr(
        "agent.tools.get_hub_exposure_report",
        fake_report,
    )

    result = execute_tool(
        "get_hub_exposure_report",
        {
            "city": "Dallas",
            "state": "Texas",
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
        },
    )

    assert result == expected


def test_rank_hubs_strips_report_and_keeps_ranking_fields(monkeypatch):
    def fake_rank(**kwargs):
        assert kwargs["hazard"] == "overall"
        return {
            "hazard": "overall",
            "ranking_metric": "elevated_weather_exposure_days_per_year",
            "hubs": [
                {
                    "city": "Denver",
                    "state": "Colorado",
                    "county": "Denver",
                    "metric": "elevated_weather_exposure_days_per_year",
                    "value": 55.1,
                    "fema_context": {
                        "flood": 2,
                        "hurricane": 0,
                        "severe_storm": 0,
                        "winter": 0,
                    },
                    "report": {"secret": True},
                    "rank": 1,
                }
            ],
        }

    monkeypatch.setattr(
        "agent.tools.rank_hubs_by_exposure",
        fake_rank,
    )

    result = execute_tool(
        "rank_hubs_by_exposure",
        {
            "hubs": [{"city": "Denver", "state": "Colorado"}],
            "hazard": "overall",
            "start_date": None,
            "end_date": None,
        },
    )

    hub = result["hubs"][0]

    assert "report" not in hub
    assert hub["rank"] == 1
    assert hub["value"] == 55.1
    assert hub["metric"] == "elevated_weather_exposure_days_per_year"
    assert hub["fema_context"]["flood"] == 2


def test_value_error_becomes_structured_error(monkeypatch):
    def fake_report(**kwargs):
        raise ValueError("bad dates")

    monkeypatch.setattr(
        "agent.tools.get_hub_exposure_report",
        fake_report,
    )

    result = execute_tool(
        "get_hub_exposure_report",
        {
            "city": "Dallas",
            "state": None,
            "start_date": "2025-01-01",
            "end_date": None,
        },
    )

    assert result == {
        "error": {
            "type": "ValueError",
            "message": "bad dates",
        }
    }


def test_runtime_error_becomes_structured_error(monkeypatch):
    def fake_report(**kwargs):
        raise RuntimeError("Open-Meteo rate limit reached")

    monkeypatch.setattr(
        "agent.tools.get_hub_exposure_report",
        fake_report,
    )

    result = execute_tool(
        "get_hub_exposure_report",
        {
            "city": "Dallas",
            "state": "Texas",
            "start_date": None,
            "end_date": None,
        },
    )

    assert result["error"]["type"] == "RuntimeError"
    assert "rate limit" in result["error"]["message"]


def test_unknown_tool_becomes_structured_error():
    result = execute_tool("not_a_tool", {})

    assert result["error"]["type"] == "ValueError"
    assert "not_a_tool" in result["error"]["message"]
