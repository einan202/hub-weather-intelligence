from tools.weather_metrics import get_location_weather_metrics


def test_get_location_weather_metrics(monkeypatch):
    fake_location = {
        "name": "Denver",
        "latitude": 39.73915,
        "longitude": -104.9847,
        "timezone": "America/Denver",
        "state": "Colorado",
        "state_code": "CO",
        "county": "Denver",
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
            2.0,
            0.0,
            1.0,
        ],
        "precipitation_sum": [
            0.0,
            25.4,
            10.0,
            30.0,
        ],
        "wind_gusts_10m_max": [
            30.0,
            74.0,
            60.0,
            90.0,
        ],
    }

    monkeypatch.setattr(
        "tools.weather_metrics.get_location_coordinates",
        lambda city, state=None: fake_location,
    )

    monkeypatch.setattr(
        "tools.weather_metrics.get_historical_weather",
        lambda **kwargs: fake_historical_weather,
    )

    result = get_location_weather_metrics(
        city="Denver",
        state="Colorado",
        start_date="2025-01-01",
        end_date="2025-01-04",
    )

    assert result["location"]["name"] == "Denver"
    assert result["location"]["state"] == "Colorado"
    assert result["period"]["start_date"] == "2025-01-01"
    assert result["period"]["end_date"] == "2025-01-04"

    snowfall = result["weather_metrics"]["snowfall"]
    high_precipitation = result["weather_metrics"]["high_precipitation"]
    high_wind = result["weather_metrics"]["high_wind"]
    elevated_exposure = result["weather_metrics"][
        "elevated_weather_exposure"
    ]

    assert snowfall["snow_days"] == 2
    assert snowfall["snow_days_percentage"] == 50.0

    assert high_precipitation["high_precipitation_days"] == 2
    assert high_precipitation["high_precipitation_days_percentage"] == 50.0
    assert high_precipitation["threshold_mm"] == 25.4

    assert high_wind["high_wind_days"] == 2
    assert high_wind["high_wind_days_percentage"] == 50.0
    assert high_wind["gust_threshold_kmh"] == 74.0

    assert elevated_exposure["total_days"] == 4
    assert elevated_exposure["elevated_exposure_days"] == 2
    assert elevated_exposure["elevated_exposure_days_percentage"] == 50.0
    assert elevated_exposure["precipitation_threshold_mm"] == 25.4
    assert elevated_exposure["gust_threshold_kmh"] == 74.0


def test_get_location_weather_metrics_without_state(monkeypatch):
    fake_location = {
        "name": "Denver",
        "latitude": 39.73915,
        "longitude": -104.9847,
        "timezone": "America/Denver",
        "state": "Colorado",
        "state_code": "CO",
        "county": "Denver",
        "country_code": "US",
    }

    fake_historical_weather = {
        "dates": ["2025-01-01"],
        "snowfall_sum": [0.0],
        "precipitation_sum": [0.0],
        "wind_gusts_10m_max": [30.0],
    }

    monkeypatch.setattr(
        "tools.weather_metrics.get_location_coordinates",
        lambda city, state=None: fake_location,
    )

    monkeypatch.setattr(
        "tools.weather_metrics.get_historical_weather",
        lambda **kwargs: fake_historical_weather,
    )

    result = get_location_weather_metrics(
        city="Denver",
        start_date="2025-01-01",
        end_date="2025-01-01",
    )

    assert result["location"]["name"] == "Denver"
    assert result["location"]["state"] == "Colorado"

    elevated_exposure = result["weather_metrics"][
        "elevated_weather_exposure"
    ]

    assert elevated_exposure["total_days"] == 1
    assert elevated_exposure["elevated_exposure_days"] == 0
    assert elevated_exposure["elevated_exposure_days_percentage"] == 0.0