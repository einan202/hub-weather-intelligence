from tools.ranking import rank_hubs_by_exposure


HUBS = [
    {"city": "Miami", "state": "Florida"},
    {"city": "Houston", "state": "Texas"},
    {"city": "Dallas", "state": "Texas"},
    {"city": "Denver", "state": "Colorado"},
]


def validate_ranking(result: dict) -> None:
    hubs = result["hubs"]

    assert len(hubs) == len(HUBS)

    assert [hub["rank"] for hub in hubs] == [1, 2, 3, 4]

    values = [hub["value"] for hub in hubs]

    assert values == sorted(
        values,
        reverse=True,
    )

    assert len(
        {hub["city"] for hub in hubs}
    ) == len(HUBS)


def print_ranking(result: dict) -> None:
    print(f"\nHazard: {result['hazard']}")
    print(f"Metric: {result['ranking_metric']}")
    print("-" * 60)

    for hub in result["hubs"]:
        print(
            f"{hub['rank']}. "
            f"{hub['city']}, {hub['state']} "
            f"-> {hub['value']}"
        )


def main() -> None:
    print("Running live overall exposure ranking...")

    overall = rank_hubs_by_exposure(
        hubs=HUBS,
        hazard="overall",
    )

    validate_ranking(overall)
    print_ranking(overall)

    print("\nRunning live hurricane declaration ranking...")

    hurricane = rank_hubs_by_exposure(
        hubs=HUBS,
        hazard="hurricane",
    )

    validate_ranking(hurricane)
    print_ranking(hurricane)

    print("\nLIVE RANKING CHECK PASSED")


if __name__ == "__main__":
    main()