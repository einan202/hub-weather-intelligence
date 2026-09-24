from datetime import date

from tools.geocoding import get_location_coordinates
from tools.hazard_events import get_hazard_history
from tools.historical_weather import (
    calculate_elevated_weather_exposure_metrics,
    calculate_high_precipitation_metrics,
    calculate_high_wind_metrics,
    calculate_snowfall_metrics,
    get_historical_weather,
)


DEFAULT_LOOKBACK_YEARS = 15


def _get_default_period() -> tuple[str, str]:
    """Return the last 15 complete calendar years."""
    last_complete_year = date.today().year - 1
    first_year = last_complete_year - DEFAULT_LOOKBACK_YEARS + 1

    return (
        f"{first_year}-01-01",
        f"{last_complete_year}-12-31",
    )


def _with_annual_average(
    metric: dict,
    count_key: str,
    years: float,
) -> dict:
    return {
        **metric,
        "average_days_per_year": round(
            metric[count_key] / years,
            2,
        ),
    }


def get_hub_exposure_report(
    city: str,
    state: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Return a deterministic weather and hazard exposure report.

    If no period is provided, the report uses the last 15 complete
    calendar years.

    A custom analysis period must provide both start_date and end_date.
    """

    if (start_date is None) != (end_date is None):
        raise ValueError(
            "start_date and end_date must either both be provided "
            "or both be omitted."
        )

    if start_date is None and end_date is None:
        start_date, end_date = _get_default_period()

    location = get_location_coordinates(city, state)

    historical_weather = get_historical_weather(
        latitude=location["latitude"],
        longitude=location["longitude"],
        timezone=location["timezone"],
        start_date=start_date,
        end_date=end_date,
    )

    snowfall = calculate_snowfall_metrics(
        historical_weather
    )

    high_precipitation = calculate_high_precipitation_metrics(
        historical_weather
    )

    high_wind = calculate_high_wind_metrics(
        historical_weather
    )

    elevated_exposure = (
        calculate_elevated_weather_exposure_metrics(
            historical_weather
        )
    )

    total_days = elevated_exposure["total_days"]
    years_observed = total_days / 365.25

    hazard_history = get_hazard_history(
        state_code=location["state_code"],
        county=location["county"],
        start_date=start_date,
        end_date=end_date,
    )

    return {
        "location": location,
        "period": {
            "start_date": start_date,
            "end_date": end_date,
            "total_days": total_days,
            "years_observed": round(years_observed, 2),
        },
        "weather_exposure": {
            "snowfall": _with_annual_average(
                snowfall,
                "snow_days",
                years_observed,
            ),
            "high_precipitation": _with_annual_average(
                high_precipitation,
                "high_precipitation_days",
                years_observed,
            ),
            "high_wind": _with_annual_average(
                high_wind,
                "high_wind_days",
                years_observed,
            ),
            "elevated_weather_exposure": _with_annual_average(
                elevated_exposure,
                "elevated_exposure_days",
                years_observed,
            ),
        },
        "fema_major_disaster_declarations": {
            "counts": hazard_history["counts"],
            "recent_events": hazard_history["recent_events"],
        },
    }