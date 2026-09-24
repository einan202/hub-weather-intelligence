from tools.hub_report import get_hub_exposure_report


def test_get_hub_exposure_report(monkeypatch):
    fake_location = {
        "name": "Dallas",
        "latitude": 32.78306,
        "longitude": -96.80667,
        "timezone": "America/Chicago",
        "state": "Texas",
        "state_code": "TX",
        "county": "Dallas",
        "country_code": "US",
    }

    fake_historical_weather = {
        "dates": [
            "2025-01-01",
            "2025-01-02",
            "2025-01-03",
            "2025-01-04",
        ],
        "snowfall_sum": [
            0.0,
            1.0,
            0.0,
            0.0,
        ],
        "precipitation_sum": [
            0.0,
            0.0,
            30.0,
            0.0,
        ],
        "wind_gusts_10m_max": [
            20.0,
            20.0,
            20.0,
            80.0,
        ],
    }

    fake_hazard_history = {
        "state_code": "TX",
        "county": "Dallas",
        "period": {
            "start_date": "2025-01-01",
            "end_date": "2025-01-04",
        },
        "counts": {
            "flood": 1,
            "hurricane": 0,
            "severe_storm": 2,
            "winter": 1,
        },
        "recent_events": [
            {
                "disaster_number": 4781,
                "declaration_title": "SEVERE STORMS AND FLOODING",
                "declaration_date": "2024-05-17T00:00:00.000Z",
                "incident_type": "Flood",
            }
        ],
    }

    monkeypatch.setattr(
        "tools.hub_report.get_location_coordinates",
        lambda city, state=None: fake_location,
    )

    monkeypatch.setattr(
        "tools.hub_report.get_historical_weather",
        lambda **kwargs: fake_historical_weather,
    )

    monkeypatch.setattr(
        "tools.hub_report.get_hazard_history",
        lambda **kwargs: fake_hazard_history,
    )

    result = get_hub_exposure_report(
        city="Dallas",
        state="Texas",
        start_date="2025-01-01",
        end_date="2025-01-04",
    )

    assert result["location"]["name"] == "Dallas"
    assert result["location"]["state"] == "Texas"

    assert result["period"]["start_date"] == "2025-01-01"
    assert result["period"]["end_date"] == "2025-01-04"
    assert result["period"]["total_days"] == 4

    snowfall = result["weather_exposure"]["snowfall"]
    high_precipitation = result["weather_exposure"]["high_precipitation"]
    high_wind = result["weather_exposure"]["high_wind"]
    elevated = result["weather_exposure"]["elevated_weather_exposure"]

    assert snowfall["snow_days"] == 1
    assert snowfall["snow_days_percentage"] == 25.0

    assert high_precipitation["high_precipitation_days"] == 1
    assert high_precipitation["high_precipitation_days_percentage"] == 25.0

    assert high_wind["high_wind_days"] == 1
    assert high_wind["high_wind_days_percentage"] == 25.0

    assert elevated["elevated_exposure_days"] == 3
    assert elevated["elevated_exposure_days_percentage"] == 75.0

    assert result["fema_major_disaster_declarations"]["counts"] == {
        "flood": 1,
        "hurricane": 0,
        "severe_storm": 2,
        "winter": 1,
    }


def test_get_hub_exposure_report_requires_complete_custom_period():
    try:
        get_hub_exposure_report(
            city="Dallas",
            state="Texas",
            start_date="2025-01-01",
        )
    except ValueError as exc:
        assert "start_date and end_date" in str(exc)
    else:
        raise AssertionError(
            "Expected ValueError when only one date is provided."
        )