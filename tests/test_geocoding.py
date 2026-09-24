import pytest

from tools.geocoding import get_location_coordinates


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


def test_selects_largest_exact_match(monkeypatch):
    fake_data = {
        "results": [
            {
                "name": "Denver",
                "latitude": 39.73915,
                "longitude": -104.9847,
                "timezone": "America/Denver",
                "country_code": "US",
                "admin1": "Colorado",
                "admin2": "Denver",
                "population": 729019,
            },
            {
                "name": "Denver",
                "latitude": 40.23315,
                "longitude": -76.13717,
                "timezone": "America/New_York",
                "country_code": "US",
                "admin1": "Pennsylvania",
                "admin2": "Lancaster",
                "population": 3875,
            },
        ]
    }

    def fake_get(*args, **kwargs):
        return FakeResponse(fake_data)

    monkeypatch.setattr(
        "tools.geocoding.requests.get",
        fake_get,
    )

    result = get_location_coordinates("Denver")

    assert result["state"] == "Colorado"
    assert result["state_code"] == "CO"
    assert result["county"] == "Denver"
    assert result["latitude"] == 39.73915


def test_state_filter_selects_correct_location(monkeypatch):
    fake_data = {
        "results": [
            {
                "name": "Springfield",
                "latitude": 39.78,
                "longitude": -89.64,
                "timezone": "America/Chicago",
                "country_code": "US",
                "admin1": "Illinois",
                "admin2": "Sangamon",
                "population": 114000,
            },
            {
                "name": "Springfield",
                "latitude": 44.05,
                "longitude": -123.02,
                "timezone": "America/Los_Angeles",
                "country_code": "US",
                "admin1": "Oregon",
                "admin2": "Lane",
                "population": 61000,
            },
        ]
    }

    def fake_get(*args, **kwargs):
        return FakeResponse(fake_data)

    monkeypatch.setattr(
        "tools.geocoding.requests.get",
        fake_get,
    )

    result = get_location_coordinates(
        "Springfield",
        "Oregon",
    )

    assert result["state"] == "Oregon"
    assert result["state_code"] == "OR"
    assert result["county"] == "Lane"


def test_prefers_exact_name_over_similar_name(monkeypatch):
    fake_data = {
        "results": [
            {
                "name": "Denver City",
                "latitude": 32.96,
                "longitude": -102.82,
                "timezone": "America/Chicago",
                "country_code": "US",
                "admin1": "Texas",
                "admin2": "Yoakum",
                "population": 4864,
            },
            {
                "name": "Denver",
                "latitude": 39.73915,
                "longitude": -104.9847,
                "timezone": "America/Denver",
                "country_code": "US",
                "admin1": "Colorado",
                "admin2": "Denver",
                "population": 729019,
            },
        ]
    }

    def fake_get(*args, **kwargs):
        return FakeResponse(fake_data)

    monkeypatch.setattr(
        "tools.geocoding.requests.get",
        fake_get,
    )

    result = get_location_coordinates("Denver")

    assert result["name"] == "Denver"
    assert result["state"] == "Colorado"
    assert result["state_code"] == "CO"
    assert result["county"] == "Denver"


def test_raises_when_state_not_found(monkeypatch):
    fake_data = {
        "results": [
            {
                "name": "Denver",
                "latitude": 39.73915,
                "longitude": -104.9847,
                "timezone": "America/Denver",
                "country_code": "US",
                "admin1": "Colorado",
                "admin2": "Denver",
                "population": 729019,
            }
        ]
    }

    def fake_get(*args, **kwargs):
        return FakeResponse(fake_data)

    monkeypatch.setattr(
        "tools.geocoding.requests.get",
        fake_get,
    )

    with pytest.raises(ValueError):
        get_location_coordinates(
            "Denver",
            "Texas",
        )


def test_raises_when_location_not_found(monkeypatch):
    def fake_get(*args, **kwargs):
        return FakeResponse({})

    monkeypatch.setattr(
        "tools.geocoding.requests.get",
        fake_get,
    )

    with pytest.raises(ValueError):
        get_location_coordinates(
            "UnknownPlace",
        )