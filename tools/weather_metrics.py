from tools.geocoding import get_location_coordinates
from tools.historical_weather import (
    calculate_elevated_weather_exposure_metrics,
    calculate_high_precipitation_metrics,
    calculate_high_wind_metrics,
    calculate_snowfall_metrics,
    get_historical_weather,
)


def get_location_weather_metrics(
    city: str,
    start_date: str,
    end_date: str,
    state: str | None = None,
) -> dict:
    """Return deterministic historical weather metrics for a U.S. city.

    This is the high-level weather tool intended to be exposed to the agent.

    It resolves the city to coordinates, retrieves historical weather once,
    and calculates snowfall, high-precipitation, high-wind, and combined
    elevated-weather-exposure metrics locally.

    Raises:
        ValueError: If the location or returned weather data is invalid.
        requests.RequestException: Propagated from the underlying HTTP tools.
    """

    location = get_location_coordinates(city, state)

    historical_weather = get_historical_weather(
        latitude=location["latitude"],
        longitude=location["longitude"],
        timezone=location["timezone"],
        start_date=start_date,
        end_date=end_date,
    )

    return {
        "location": location,
        "period": {
            "start_date": start_date,
            "end_date": end_date,
        },
        "weather_metrics": {
            "snowfall": calculate_snowfall_metrics(
                historical_weather
            ),
            "high_precipitation": calculate_high_precipitation_metrics(
                historical_weather
            ),
            "high_wind": calculate_high_wind_metrics(
                historical_weather
            ),
            "elevated_weather_exposure": (
                calculate_elevated_weather_exposure_metrics(
                    historical_weather
                )
            ),
        },
    }