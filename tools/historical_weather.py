import logging
import time

import requests


logger = logging.getLogger(__name__)

HISTORICAL_WEATHER_URL = "https://archive-api.open-meteo.com/v1/archive"

DAILY_VARIABLES = [
    "snowfall_sum",
    "precipitation_sum",
    "wind_gusts_10m_max",
]

HIGH_PRECIPITATION_THRESHOLD_MM = 25.4
STRONG_WIND_GUST_THRESHOLD_KMH = 74.0

RETRYABLE_STATUS_CODES = {
    500,
    502,
    503,
    504,
}

_ARCHIVE_CACHE: dict[tuple, dict] = {}


def get_historical_weather(
    latitude: float,
    longitude: float,
    timezone: str,
    start_date: str,
    end_date: str,
) -> dict:
    """Fetch daily historical weather observations for a location.

    Results are cached in memory because historical data for a fixed
    past period is stable and may be reused in conversational follow-ups.

    Transient connection failures and selected 5xx responses are retried
    once. Rate-limit responses are not retried immediately.

    Raises:
        ValueError: If the response does not contain daily weather data.
        RuntimeError: If the Open-Meteo rate limit is reached.
        requests.RequestException: If an HTTP/network request fails.
    """
    cache_key = (
        latitude,
        longitude,
        timezone,
        start_date,
        end_date,
        tuple(DAILY_VARIABLES),
    )

    if cache_key in _ARCHIVE_CACHE:
        return _ARCHIVE_CACHE[cache_key]

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date,
        "end_date": end_date,
        "daily": ",".join(DAILY_VARIABLES),
        "timezone": timezone,
    }

    for attempt in range(2):
        try:
            response = requests.get(
                HISTORICAL_WEATHER_URL,
                params=params,
                timeout=(10, 60),
            )
        except (requests.Timeout, requests.ConnectionError):
            if attempt == 1:
                raise

            logger.warning(
                "Open-Meteo request failed; retrying once in 2 seconds."
            )
            time.sleep(2)
            continue

        if response.status_code == 429:
            raise RuntimeError(
                "Open-Meteo rate limit reached: "
                f"{response.text[:200]}"
            )

        if (
            response.status_code in RETRYABLE_STATUS_CODES
            and attempt == 0
        ):
            logger.warning(
                "Open-Meteo returned %s; retrying once in 2 seconds.",
                response.status_code,
            )
            time.sleep(2)
            continue

        response.raise_for_status()
        break

    data = response.json()
    daily = data.get("daily")

    if not daily:
        raise ValueError(
            "Historical weather response does not contain daily data."
        )

    result = {
        "latitude": data.get("latitude"),
        "longitude": data.get("longitude"),
        "timezone": data.get("timezone"),
        "dates": daily.get("time", []),
        "snowfall_sum": daily.get("snowfall_sum", []),
        "precipitation_sum": daily.get("precipitation_sum", []),
        "wind_gusts_10m_max": daily.get("wind_gusts_10m_max", []),
    }

    _ARCHIVE_CACHE[cache_key] = result

    return result


def _validate_series(
    dates: list,
    values: list,
    label: str,
) -> None:
    """Validate a daily metric series before deterministic calculation."""
    if not dates or not values:
        raise ValueError(
            f"Historical weather data does not contain {label} observations."
        )

    if len(dates) != len(values):
        raise ValueError(
            f"Dates and {label} observations have different lengths."
        )

    if any(value is None for value in values):
        raise ValueError(
            f"Historical {label} data contains missing values."
        )


def _threshold_metrics(
    dates: list,
    values: list,
    predicate,
) -> tuple[int, int, float]:
    """Count matching days and calculate their percentage."""
    total_days = len(dates)

    matching_days = sum(
        1
        for value in values
        if predicate(value)
    )

    percentage = round(
        (matching_days / total_days) * 100,
        2,
    )

    return total_days, matching_days, percentage


def calculate_snowfall_metrics(
    historical_weather: dict,
) -> dict:
    """Calculate the number and percentage of days with snowfall above zero."""
    dates = historical_weather.get("dates", [])
    snowfall = historical_weather.get("snowfall_sum", [])

    _validate_series(
        dates,
        snowfall,
        "snowfall",
    )

    total_days, snow_days, snow_days_percentage = _threshold_metrics(
        dates,
        snowfall,
        lambda snowfall_amount: snowfall_amount > 0,
    )

    return {
        "total_days": total_days,
        "snow_days": snow_days,
        "snow_days_percentage": snow_days_percentage,
    }


def calculate_high_precipitation_metrics(
    historical_weather: dict,
    threshold_mm: float = HIGH_PRECIPITATION_THRESHOLD_MM,
) -> dict:
    """Calculate high-precipitation days using a daily precipitation threshold."""
    dates = historical_weather.get("dates", [])
    precipitation = historical_weather.get(
        "precipitation_sum",
        [],
    )

    _validate_series(
        dates,
        precipitation,
        "precipitation",
    )

    (
        total_days,
        high_precipitation_days,
        high_precipitation_days_percentage,
    ) = _threshold_metrics(
        dates,
        precipitation,
        lambda amount: amount >= threshold_mm,
    )

    return {
        "total_days": total_days,
        "high_precipitation_days": high_precipitation_days,
        "high_precipitation_days_percentage": (
            high_precipitation_days_percentage
        ),
        "threshold_mm": threshold_mm,
    }


def calculate_high_wind_metrics(
    historical_weather: dict,
    gust_threshold_kmh: float = STRONG_WIND_GUST_THRESHOLD_KMH,
) -> dict:
    """Calculate high-wind days using a daily gust threshold."""
    dates = historical_weather.get("dates", [])
    wind_gusts = historical_weather.get(
        "wind_gusts_10m_max",
        [],
    )

    _validate_series(
        dates,
        wind_gusts,
        "wind gust",
    )

    (
        total_days,
        high_wind_days,
        high_wind_days_percentage,
    ) = _threshold_metrics(
        dates,
        wind_gusts,
        lambda gust: gust >= gust_threshold_kmh,
    )

    return {
        "total_days": total_days,
        "high_wind_days": high_wind_days,
        "high_wind_days_percentage": high_wind_days_percentage,
        "gust_threshold_kmh": gust_threshold_kmh,
    }


def calculate_elevated_weather_exposure_metrics(
    historical_weather: dict,
    precipitation_threshold_mm: float = HIGH_PRECIPITATION_THRESHOLD_MM,
    gust_threshold_kmh: float = STRONG_WIND_GUST_THRESHOLD_KMH,
) -> dict:
    """Calculate days with at least one elevated weather condition.

    A day is counted once when at least one of these conditions is met:
    - snowfall > 0
    - precipitation >= configured daily threshold
    - maximum wind gust >= configured threshold
    """
    dates = historical_weather.get("dates", [])
    snowfall = historical_weather.get("snowfall_sum", [])
    precipitation = historical_weather.get("precipitation_sum", [])
    wind_gusts = historical_weather.get("wind_gusts_10m_max", [])

    _validate_series(
        dates,
        snowfall,
        "snowfall",
    )
    _validate_series(
        dates,
        precipitation,
        "precipitation",
    )
    _validate_series(
        dates,
        wind_gusts,
        "wind gust",
    )

    elevated_exposure_days = sum(
        1
        for snow, precipitation_amount, gust in zip(
            snowfall,
            precipitation,
            wind_gusts,
        )
        if (
            snow > 0
            or precipitation_amount >= precipitation_threshold_mm
            or gust >= gust_threshold_kmh
        )
    )

    total_days = len(dates)

    elevated_exposure_days_percentage = round(
        (elevated_exposure_days / total_days) * 100,
        2,
    )

    return {
        "total_days": total_days,
        "elevated_exposure_days": elevated_exposure_days,
        "elevated_exposure_days_percentage": (
            elevated_exposure_days_percentage
        ),
        "precipitation_threshold_mm": precipitation_threshold_mm,
        "gust_threshold_kmh": gust_threshold_kmh,
    }