from pprint import pprint

from tools.geocoding import get_location_coordinates
from tools.hazard_events import get_hazard_history


LOCATIONS = [
    ("Miami", "Florida"),
    ("Houston", "Texas"),
    ("Dallas", "Texas"),
    ("Denver", "Colorado"),
]

START_DATE = "2011-01-01"
END_DATE = "2025-12-31"


def main():
    for city, state in LOCATIONS:
        location = get_location_coordinates(city, state)

        result = get_hazard_history(
            state_code=location["state_code"],
            county=location["county"],
            start_date=START_DATE,
            end_date=END_DATE,
        )

        print(f"\n=== {city}, {state} — FEMA Hazard History ===")
        print(
            f"County: {location['county']} | "
            f"State code: {location['state_code']}"
        )
        print(f"Period: {START_DATE} to {END_DATE}")

        print("\nHazard counts:")
        pprint(result["counts"])

        print("\nRecent events:")
        pprint(result["recent_events"])


if __name__ == "__main__":
    main()