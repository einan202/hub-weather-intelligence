from tools.ranking import rank_hubs_by_exposure


def _fake_report(
    city,
    state,
    overall_days_per_year,
    snow_days_per_year=0.0,
    precipitation_days_per_year=0.0,
    wind_days_per_year=0.0,
    hurricane_declarations=0,
    years_observed=15.0,
):
    return {
        "location": {
            "name": city,
            "state": state,
            "county": f"{city} County",
        },
        "period": {
            "years_observed": years_observed,
        },
        "weather_exposure": {
            "snowfall": {
                "average_days_per_year": snow_days_per_year,
            },
            "high_precipitation": {
                "average_days_per_year": precipitation_days_per_year,
            },
            "high_wind": {
                "average_days_per_year": wind_days_per_year,
            },
            "elevated_weather_exposure": {
                "average_days_per_year": overall_days_per_year,
            },
        },
        "fema_major_disaster_declarations": {
            "counts": {
                "flood": 0,
                "hurricane": hurricane_declarations,
                "severe_storm": 0,
                "winter": 0,
            },
            "recent_events": [],
        },
    }


def test_rank_hubs_by_overall_exposure(monkeypatch):
    reports = {
        "Miami": _fake_report(
            "Miami",
            "Florida",
            overall_days_per_year=7.93,
        ),
        "Houston": _fake_report(
            "Houston",
            "Texas",
            overall_days_per_year=18.87,
        ),
        "Dallas": _fake_report(
            "Dallas",
            "Texas",
            overall_days_per_year=19.13,
        ),
        "Denver": _fake_report(
            "Denver",
            "Colorado",
            overall_days_per_year=55.07,
        ),
    }

    monkeypatch.setattr(
        "tools.ranking.get_hub_exposure_report",
        lambda city, state=None, start_date=None, end_date=None: reports[city],
    )

    result = rank_hubs_by_exposure(
        hubs=[
            {"city": "Miami", "state": "Florida"},
            {"city": "Houston", "state": "Texas"},
            {"city": "Dallas", "state": "Texas"},
            {"city": "Denver", "state": "Colorado"},
        ],
        hazard="overall",
    )

    ranked = result["hubs"]

    assert result["hazard"] == "overall"
    assert result["ranking_metric"] == (
        "elevated_weather_exposure_days_per_year"
    )

    assert [hub["city"] for hub in ranked] == [
        "Denver",
        "Dallas",
        "Houston",
        "Miami",
    ]

    assert [hub["rank"] for hub in ranked] == [1, 2, 3, 4]


def test_rank_hubs_by_hurricane_declarations(monkeypatch):
    reports = {
        "Miami": _fake_report(
            "Miami",
            "Florida",
            overall_days_per_year=0,
            hurricane_declarations=4,
        ),
        "Houston": _fake_report(
            "Houston",
            "Texas",
            overall_days_per_year=0,
            hurricane_declarations=2,
        ),
    }

    monkeypatch.setattr(
        "tools.ranking.get_hub_exposure_report",
        lambda city, state=None, start_date=None, end_date=None: reports[city],
    )

    result = rank_hubs_by_exposure(
        hubs=[
            {"city": "Houston", "state": "Texas"},
            {"city": "Miami", "state": "Florida"},
        ],
        hazard="hurricane",
    )

    ranked = result["hubs"]

    assert ranked[0]["city"] == "Miami"
    assert ranked[0]["rank"] == 1
    assert ranked[0]["value"] == round(4 / 15, 3)

    assert ranked[1]["city"] == "Houston"
    assert ranked[1]["rank"] == 2
    assert ranked[1]["value"] == round(2 / 15, 3)


def test_rank_hubs_rejects_unsupported_hazard():
    try:
        rank_hubs_by_exposure(
            hubs=[
                {
                    "city": "Denver",
                    "state": "Colorado",
                }
            ],
            hazard="earthquake",
        )
    except ValueError as exc:
        assert "Unsupported hazard" in str(exc)
    else:
        raise AssertionError(
            "Expected ValueError for unsupported hazard."
        )


def test_rank_hubs_requires_at_least_one_hub():
    try:
        rank_hubs_by_exposure(
            hubs=[],
            hazard="overall",
        )
    except ValueError as exc:
        assert "At least one hub" in str(exc)
    else:
        raise AssertionError(
            "Expected ValueError when no hubs are provided."
        )