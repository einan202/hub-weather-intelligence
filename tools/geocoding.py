import requests

from tools.us_states import get_state_code


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

def get_location_coordinates(
    location_name: str,
    state: str | None = None,
) -> dict:
    """Resolve a U.S. city name to coordinates and location metadata.

    Resolution is deterministic:
    - only U.S. results are accepted,
    - exact city-name matches are preferred,
    - an optional state must match,
    - if several candidates remain, the largest population wins.

    Raises:
        ValueError: If no suitable location can be resolved.
        requests.RequestException: If the Open-Meteo request fails.
    """

    params = {
        "name": location_name,
        "count": 10,
        "language": "en",
        "format": "json",
        "countryCode": "US",
    }

    response = requests.get(
        GEOCODING_URL,
        params=params,
        timeout=10,
    )
    response.raise_for_status()

    data = response.json()
    results = data.get("results", [])

    if not results:
        raise ValueError(f"Location not found: {location_name}")

    # Intentional defense-in-depth: the API request is already scoped to the
    # U.S., but we also validate the returned payload before using it.
    results = [
        result
        for result in results
        if result.get("country_code") == "US"
    ]

    exact_matches = [
        result
        for result in results
        if result.get("name", "").lower() == location_name.lower()
    ]

    if exact_matches:
        results = exact_matches

    if state:
        state_matches = [
            result
            for result in results
            if result.get("admin1", "").lower() == state.lower()
        ]

        if not state_matches:
            raise ValueError(
                f"Location '{location_name}' was not found in state '{state}'."
            )

        results = state_matches

    if not results:
        raise ValueError(f"No suitable US location found for: {location_name}")

    results.sort(
        key=lambda result: result.get("population", 0),
        reverse=True,
    )

    location = results[0]

    required_fields = [
        "name",
        "latitude",
        "longitude",
        "timezone",
        "country_code",
        "admin1",
        "admin2",
    ]

    missing_fields = [
        field
        for field in required_fields
        if location.get(field) is None
    ]

    if missing_fields:
        raise ValueError(
            "Geocoding response is missing required fields: "
            + ", ".join(missing_fields)
        )

    state_name = location["admin1"]
    county = location["admin2"]

    return {
        "name": location["name"],
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "timezone": location["timezone"],
        "state": state_name,
        "state_code": get_state_code(state_name),
        "county": county,
        "country_code": location["country_code"],
    }