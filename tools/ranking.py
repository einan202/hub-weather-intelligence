from tools.hub_report import get_hub_exposure_report


SUPPORTED_RANKINGS = {
    "overall",
    "winter",
    "flood",
    "storm",
    "hurricane",
}


def _get_ranking_value(
    report: dict,
    hazard: str,
) -> tuple[float, str]:
    weather = report["weather_exposure"]

    if hazard == "overall":
        return (
            weather["elevated_weather_exposure"]["average_days_per_year"],
            "elevated_weather_exposure_days_per_year",
        )

    if hazard == "winter":
        return (
            weather["snowfall"]["average_days_per_year"],
            "snow_days_per_year",
        )

    if hazard == "flood":
        return (
            weather["high_precipitation"]["average_days_per_year"],
            "high_precipitation_days_per_year",
        )

    if hazard == "storm":
        return (
            weather["high_wind"]["average_days_per_year"],
            "high_wind_days_per_year",
        )

    if hazard == "hurricane":
        years = report["period"]["years_observed"]
        declarations = report[
            "fema_major_disaster_declarations"
        ]["counts"]["hurricane"]

        return (
            round(declarations / years, 3),
            "fema_hurricane_declarations_per_year",
        )

    raise ValueError(
        f"Unsupported hazard '{hazard}'. "
        f"Expected one of: {sorted(SUPPORTED_RANKINGS)}"
    )


def _get_fema_context(
    report: dict,
    hazard: str,
) -> dict:
    counts = report[
        "fema_major_disaster_declarations"
    ]["counts"]

    if hazard == "winter":
        return {"winter": counts["winter"]}

    if hazard == "flood":
        return {"flood": counts["flood"]}

    if hazard == "storm":
        return {"severe_storm": counts["severe_storm"]}

    if hazard == "hurricane":
        return {"hurricane": counts["hurricane"]}

    return counts


def rank_hubs_by_exposure(
    hubs: list[dict],
    hazard: str = "overall",
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Rank U.S. hubs using deterministic exposure metrics.

    Weather-based rankings use average exposure days per year.
    Hurricane ranking uses FEMA Major Disaster declaration frequency
    because the current weather layer does not contain a direct
    hurricane metric.

    FEMA counts are supporting context for weather-based rankings and
    are not mathematically blended into the weather KPI.
    """

    if hazard not in SUPPORTED_RANKINGS:
        raise ValueError(
            f"Unsupported hazard '{hazard}'. "
            f"Expected one of: {sorted(SUPPORTED_RANKINGS)}"
        )

    if not hubs:
        raise ValueError("At least one hub is required.")

    ranked = []

    for hub in hubs:
        city = hub["city"]
        state = hub.get("state")

        report = get_hub_exposure_report(
            city=city,
            state=state,
            start_date=start_date,
            end_date=end_date,
        )

        value, metric = _get_ranking_value(
            report,
            hazard,
        )

        ranked.append(
            {
                "city": report["location"]["name"],
                "state": report["location"]["state"],
                "county": report["location"]["county"],
                "metric": metric,
                "value": value,
                "fema_context": _get_fema_context(
                    report,
                    hazard,
                ),
                "report": report,
            }
        )

    ranked.sort(
        key=lambda item: (
            -item["value"],
            item["city"],
            item["state"],
        )
    )

    for index, item in enumerate(ranked, start=1):
        item["rank"] = index

    return {
        "hazard": hazard,
        "ranking_metric": (
            ranked[0]["metric"]
            if ranked
            else None
        ),
        "hubs": ranked,
    }