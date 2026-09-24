from tools.hub_report import get_hub_exposure_report


HUBS = [
    ("Miami", "Florida"),
    ("Houston", "Texas"),
    ("Dallas", "Texas"),
    ("Denver", "Colorado"),
]


def validate_report(report: dict) -> None:
    location = report["location"]
    period = report["period"]
    weather = report["weather_exposure"]
    fema = report["fema_major_disaster_declarations"]

    assert location["country_code"] == "US"
    assert location["state_code"]
    assert location["county"]

    assert period["total_days"] > 0
    assert period["years_observed"] > 0

    snowfall = weather["snowfall"]
    precipitation = weather["high_precipitation"]
    wind = weather["high_wind"]
    elevated = weather["elevated_weather_exposure"]

    assert snowfall["total_days"] == period["total_days"]
    assert precipitation["total_days"] == period["total_days"]
    assert wind["total_days"] == period["total_days"]
    assert elevated["total_days"] == period["total_days"]

    assert 0 <= snowfall["snow_days_percentage"] <= 100
    assert 0 <= precipitation["high_precipitation_days_percentage"] <= 100
    assert 0 <= wind["high_wind_days_percentage"] <= 100
    assert 0 <= elevated["elevated_exposure_days_percentage"] <= 100

    assert elevated["elevated_exposure_days"] >= snowfall["snow_days"]
    assert (
        elevated["elevated_exposure_days"]
        >= precipitation["high_precipitation_days"]
    )
    assert elevated["elevated_exposure_days"] >= wind["high_wind_days"]

    assert precipitation["threshold_mm"] == 25.4
    assert wind["gust_threshold_kmh"] == 74.0

    assert set(fema["counts"]) == {
        "flood",
        "hurricane",
        "severe_storm",
        "winter",
    }

    assert all(
        count >= 0
        for count in fema["counts"].values()
    )


def main() -> None:
    for city, state in HUBS:
        print(f"\n{'=' * 60}")
        print(f"{city}, {state}")
        print("=" * 60)

        report = get_hub_exposure_report(
            city=city,
            state=state,
        )

        validate_report(report)

        period = report["period"]
        weather = report["weather_exposure"]
        fema = report["fema_major_disaster_declarations"]

        print(
            f"Period: {period['start_date']} -> "
            f"{period['end_date']}"
        )
        print(
            f"Days: {period['total_days']} | "
            f"Years observed: {period['years_observed']}"
        )

        print("\nWeather exposure:")

        snowfall = weather["snowfall"]
        print(
            f"  Snowfall: "
            f"{snowfall['snow_days']} days | "
            f"{snowfall['snow_days_percentage']}% | "
            f"{snowfall['average_days_per_year']} days/year"
        )

        precipitation = weather["high_precipitation"]
        print(
            f"  High precipitation: "
            f"{precipitation['high_precipitation_days']} days | "
            f"{precipitation['high_precipitation_days_percentage']}% | "
            f"{precipitation['average_days_per_year']} days/year"
        )

        wind = weather["high_wind"]
        print(
            f"  High wind: "
            f"{wind['high_wind_days']} days | "
            f"{wind['high_wind_days_percentage']}% | "
            f"{wind['average_days_per_year']} days/year"
        )

        elevated = weather["elevated_weather_exposure"]
        print(
            f"  Elevated exposure: "
            f"{elevated['elevated_exposure_days']} days | "
            f"{elevated['elevated_exposure_days_percentage']}% | "
            f"{elevated['average_days_per_year']} days/year"
        )

        print("\nFEMA Major Disaster declarations:")
        for hazard, count in fema["counts"].items():
            print(f"  {hazard}: {count}")

        print("\nPASS")


if __name__ == "__main__":
    main()