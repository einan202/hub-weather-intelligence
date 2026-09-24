from tools.weather_metrics import get_location_weather_metrics


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
        result = get_location_weather_metrics(
            city=city,
            state=state,
            start_date=START_DATE,
            end_date=END_DATE,
        )

        metrics = result["weather_metrics"]

        print(f"\n=== {city}, {state} — Historical Weather ===")
        print(f"Period: {START_DATE} to {END_DATE}")

        print("\nSnowfall:")
        print(metrics["snowfall"])

        print("\nHigh precipitation:")
        print(metrics["high_precipitation"])

        print("\nHigh wind:")
        print(metrics["high_wind"])

        print("\nElevated weather exposure:")
        print(metrics["elevated_weather_exposure"])


if __name__ == "__main__":
    main()