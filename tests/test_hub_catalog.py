from tools.hub_catalog import get_hubs


def test_get_hubs_returns_all_hubs():
    hubs = get_hubs()

    assert len(hubs) == 8
    assert any(hub["city"] == "Miami" for hub in hubs)
    assert any(hub["city"] == "Chicago" for hub in hubs)


def test_get_hubs_filters_by_region_case_insensitive():
    hubs = get_hubs(region="midwest")

    assert [hub["city"] for hub in hubs] == [
        "Chicago",
        "Minneapolis",
        "Detroit",
        "St. Louis",
    ]

    assert all(
        hub["region"] == "Midwest"
        for hub in hubs
    )