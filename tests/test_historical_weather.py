import pytest

from tools.historical_weather import (
    calculate_elevated_weather_exposure_metrics,
    calculate_high_precipitation_metrics,
    calculate_high_wind_metrics,
    calculate_snowfall_metrics,
    get_historical_weather,
)


class FakeResponse:
    def __init__(self, data, status_code=200):
        self.data = data
        self.status_code = status_code
        self.text = ""

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


@pytest.fixture(autouse=True)
def clear_archive_cache():
    from tools import historical_weather

    historical_weather._ARCHIVE_CACHE.clear()


def test_get_historical_weather(monkeypatch):
    fake_data = {
        "latitude": 39.73915,
        "longitude": -104.9847,
        "timezone": "America/Denver",
        "daily": {
            "time": [
                "2025-01-01",
                "2025-01-02",
                "2025-01-03",
            ],
            "snowfall_sum": [
                0.0,
                2.5,
                0.0,
            ],
            "precipitation_sum": [
                0.0,
                3.2,
                0.0,
            ],
            "wind_gusts_10m_max": [
                35.0,
                42.0,
                30.0,
            ],
        },
    }

    def fake_get(*args, **kwargs):
        return FakeResponse(fake_data)

    monkeypatch.setattr(
        "tools.historical_weather.requests.get",
        fake_get,
    )

    result = get_historical_weather(
        latitude=39.73915,
        longitude=-104.9847,
        timezone="America/Denver",
        start_date="2025-01-01",
        end_date="2025-01-03",
    )

    assert result["timezone"] == "America/Denver"
    assert len(result["dates"]) == 3
    assert result["snowfall_sum"] == [
        0.0,
        2.5,
        0.0,
    ]


def test_calculate_snowfall_metrics():
    weather = {
        "dates": [
            "2025-01-01",
            "2025-01-02",
            "2025-01-03",
            "2025-01-04",
        ],
        "snowfall_sum": [
            0.0,
            1.2,
            0.0,
            3.5,
        ],
    }

    result = calculate_snowfall_metrics(weather)

    assert result["total_days"] == 4
    assert result["snow_days"] == 2
    assert result["snow_days_percentage"] == 50.0


def test_no_snowfall_returns_zero_percent():
    weather = {
        "dates": [
            "2025-01-01",
            "2025-01-02",
        ],
        "snowfall_sum": [
            0.0,
            0.0,
        ],
    }

    result = calculate_snowfall_metrics(weather)

    assert result["snow_days"] == 0
    assert result["snow_days_percentage"] == 0.0


def test_raises_when_daily_data_missing(monkeypatch):
    def fake_get(*args, **kwargs):
        return FakeResponse({})

    monkeypatch.setattr(
        "tools.historical_weather.requests.get",
        fake_get,
    )

    with pytest.raises(ValueError):
        get_historical_weather(
            latitude=39.73915,
            longitude=-104.9847,
            timezone="America/Denver",
            start_date="2025-01-01",
            end_date="2025-12-31",
        )


def test_raises_when_snowfall_contains_missing_values():
    weather = {
        "dates": [
            "2025-01-01",
            "2025-01-02",
        ],
        "snowfall_sum": [
            0.0,
            None,
        ],
    }

    with pytest.raises(ValueError):
        calculate_snowfall_metrics(weather)


def test_calculate_high_precipitation_metrics():
    weather = {
        "dates": [
            "2025-01-01",
            "2025-01-02",
            "2025-01-03",
            "2025-01-04",
        ],
        "precipitation_sum": [
            0.0,
            25.4,
            10.0,
            35.0,
        ],
    }

    result = calculate_high_precipitation_metrics(weather)

    assert result["total_days"] == 4
    assert result["high_precipitation_days"] == 2
    assert result["high_precipitation_days_percentage"] == 50.0
    assert result["threshold_mm"] == 25.4


def test_calculate_high_wind_metrics():
    weather = {
        "dates": [
            "2025-01-01",
            "2025-01-02",
            "2025-01-03",
            "2025-01-04",
        ],
        "wind_gusts_10m_max": [
            30.0,
            74.0,
            60.0,
            90.0,
        ],
    }

    result = calculate_high_wind_metrics(weather)

    assert result["total_days"] == 4
    assert result["high_wind_days"] == 2
    assert result["high_wind_days_percentage"] == 50.0
    assert result["gust_threshold_kmh"] == 74.0


def test_calculate_elevated_weather_exposure_metrics_counts_each_day_once():
    weather = {
        "dates": [
            "2025-01-01",
            "2025-01-02",
            "2025-01-03",
            "2025-01-04",
        ],
        "snowfall_sum": [
            1.0,
            0.0,
            2.0,
            0.0,
        ],
        "precipitation_sum": [
            0.0,
            30.0,
            30.0,
            0.0,
        ],
        "wind_gusts_10m_max": [
            20.0,
            20.0,
            80.0,
            20.0,
        ],
    }

    result = calculate_elevated_weather_exposure_metrics(weather)

    assert result["total_days"] == 4
    assert result["elevated_exposure_days"] == 3
    assert result["elevated_exposure_days_percentage"] == 75.0
    assert result["precipitation_threshold_mm"] == 25.4
    assert result["gust_threshold_kmh"] == 74.0


@pytest.mark.parametrize(
    "calculator, weather",
    [
        (
            calculate_high_precipitation_metrics,
            {
                "dates": [
                    "2025-01-01",
                    "2025-01-02",
                ],
                "precipitation_sum": [
                    10.0,
                    None,
                ],
            },
        ),
        (
            calculate_high_wind_metrics,
            {
                "dates": [
                    "2025-01-01",
                    "2025-01-02",
                ],
                "wind_gusts_10m_max": [
                    80.0,
                ],
            },
        ),
    ],
)
def test_weather_metrics_reject_invalid_series(
    calculator,
    weather,
):
    with pytest.raises(ValueError):
        calculator(weather)