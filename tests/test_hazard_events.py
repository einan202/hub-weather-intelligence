from tools.hazard_events import get_hazard_history


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


def test_get_hazard_history_counts_matching_county(monkeypatch):
    fake_data = {
        "DisasterDeclarationsSummaries": [
            {
                "disasterNumber": 4834,
                "incidentType": "Hurricane",
                "declarationTitle": "HURRICANE MILTON",
                "declarationDate": "2024-10-11T00:00:00.000Z",
                "designatedArea": "Miami-Dade (County)",
            },
            {
                "disasterNumber": 4673,
                "incidentType": "Hurricane",
                "declarationTitle": "HURRICANE IAN",
                "declarationDate": "2022-09-29T00:00:00.000Z",
                "designatedArea": "Miami-Dade (County)",
            },
            {
                "disasterNumber": 1609,
                "incidentType": "Flood",
                "declarationTitle": "SEVERE STORMS AND FLOODING",
                "declarationDate": "2005-10-24T00:00:00.000Z",
                "designatedArea": "Miami-Dade (County)",
            },
            {
                "disasterNumber": 9999,
                "incidentType": "Flood",
                "declarationTitle": "SIMILAR COUNTY NAME",
                "declarationDate": "2023-01-01T00:00:00.000Z",
                "designatedArea": "Miami-Dade-North (County)",
            },
        ]
    }

    captured_request = {}

    def fake_get(url, params=None, timeout=None):
        captured_request["url"] = url
        captured_request["params"] = params
        captured_request["timeout"] = timeout
        return FakeResponse(fake_data)

    monkeypatch.setattr(
        "tools.hazard_events.requests.get",
        fake_get,
    )

    result = get_hazard_history(
        state_code="FL",
        county="Miami-Dade County",
        recent_events_limit=2,
    )

    assert result["state_code"] == "FL"
    assert result["county"] == "Miami-Dade County"

    assert result["counts"] == {
        "flood": 1,
        "hurricane": 2,
        "severe_storm": 0,
        "winter": 0,
    }

    assert len(result["recent_events"]) == 2
    assert result["recent_events"][0]["disaster_number"] == 4834
    assert result["recent_events"][0]["incident_type"] == "Hurricane"

    filter_expression = captured_request["params"]["$filter"]

    assert "state eq 'FL'" in filter_expression
    assert "declarationType eq 'DR'" in filter_expression
    assert "contains(designatedArea, 'Miami-Dade')" in filter_expression
    assert captured_request["timeout"] == 20


def test_get_hazard_history_filters_by_date_range(monkeypatch):
    fake_data = {
        "DisasterDeclarationsSummaries": [
            {
                "disasterNumber": 4834,
                "incidentType": "Hurricane",
                "declarationTitle": "HURRICANE MILTON",
                "declarationDate": "2024-10-11T00:00:00.000Z",
                "designatedArea": "Miami-Dade (County)",
            },
            {
                "disasterNumber": 4673,
                "incidentType": "Hurricane",
                "declarationTitle": "HURRICANE IAN",
                "declarationDate": "2022-09-29T00:00:00.000Z",
                "designatedArea": "Miami-Dade (County)",
            },
            {
                "disasterNumber": 1609,
                "incidentType": "Flood",
                "declarationTitle": "OLD FLOOD",
                "declarationDate": "2005-10-24T00:00:00.000Z",
                "designatedArea": "Miami-Dade (County)",
            },
            {
                "disasterNumber": 9999,
                "incidentType": "Flood",
                "declarationTitle": "SIMILAR COUNTY NAME",
                "declarationDate": "2023-01-01T00:00:00.000Z",
                "designatedArea": "Miami-Dade-North (County)",
            },
        ]
    }

    def fake_get(url, params=None, timeout=None):
        return FakeResponse(fake_data)

    monkeypatch.setattr(
        "tools.hazard_events.requests.get",
        fake_get,
    )

    result = get_hazard_history(
        state_code="FL",
        county="Miami-Dade County",
        start_date="2011-01-01",
        end_date="2025-12-31",
    )

    assert result["period"] == {
        "start_date": "2011-01-01",
        "end_date": "2025-12-31",
    }

    assert result["counts"] == {
        "flood": 0,
        "hurricane": 2,
        "severe_storm": 0,
        "winter": 0,
    }

    assert len(result["recent_events"]) == 2

    assert all(
        event["declaration_date"][:10] >= "2011-01-01"
        for event in result["recent_events"]
    )

    assert all(
        event["declaration_date"][:10] <= "2025-12-31"
        for event in result["recent_events"]
    )


def test_get_hazard_history_handles_no_matching_county(monkeypatch):
    fake_data = {
        "DisasterDeclarationsSummaries": [
            {
                "disasterNumber": 9999,
                "incidentType": "Flood",
                "declarationTitle": "OTHER COUNTY FLOOD",
                "declarationDate": "2023-01-01T00:00:00.000Z",
                "designatedArea": "Boulder (County)",
            }
        ]
    }

    def fake_get(url, params=None, timeout=None):
        return FakeResponse(fake_data)

    monkeypatch.setattr(
        "tools.hazard_events.requests.get",
        fake_get,
    )

    result = get_hazard_history(
        state_code="CO",
        county="Denver",
    )

    assert result["counts"] == {
        "flood": 0,
        "hurricane": 0,
        "severe_storm": 0,
        "winter": 0,
    }

    assert result["recent_events"] == []


def test_get_hazard_history_raises_when_response_hits_limit(monkeypatch):
    fake_data = {
        "DisasterDeclarationsSummaries": [
            {
                "disasterNumber": index,
                "incidentType": "Flood",
                "declarationTitle": "TEST",
                "declarationDate": "2020-01-01T00:00:00.000Z",
                "designatedArea": "Test (County)",
            }
            for index in range(1000)
        ]
    }

    def fake_get(url, params=None, timeout=None):
        return FakeResponse(fake_data)

    monkeypatch.setattr(
        "tools.hazard_events.requests.get",
        fake_get,
    )

    try:
        get_hazard_history(
            state_code="TX",
            county="Test County",
        )
    except ValueError as exc:
        assert "may be truncated" in str(exc)
    else:
        raise AssertionError(
            "Expected ValueError for a potentially truncated FEMA response"
        )


def test_get_hazard_history_counts_winter_and_severe_storm(monkeypatch):
    fake_data = {
        "DisasterDeclarationsSummaries": [
            {
                "disasterNumber": 1001,
                "incidentType": "Severe Storm",
                "declarationTitle": "SEVERE STORMS",
                "declarationDate": "2024-01-01T00:00:00.000Z",
                "designatedArea": "Denver (County)",
            },
            {
                "disasterNumber": 1002,
                "incidentType": "Snowstorm",
                "declarationTitle": "SNOWSTORM",
                "declarationDate": "2023-01-01T00:00:00.000Z",
                "designatedArea": "Denver (County)",
            },
            {
                "disasterNumber": 1003,
                "incidentType": "Severe Ice Storm",
                "declarationTitle": "SEVERE ICE STORM",
                "declarationDate": "2022-01-01T00:00:00.000Z",
                "designatedArea": "Denver (County)",
            },
        ]
    }

    def fake_get(url, params=None, timeout=None):
        return FakeResponse(fake_data)

    monkeypatch.setattr(
        "tools.hazard_events.requests.get",
        fake_get,
    )

    result = get_hazard_history(
        state_code="CO",
        county="Denver",
    )

    assert result["counts"] == {
        "flood": 0,
        "hurricane": 0,
        "severe_storm": 1,
        "winter": 2,
    }