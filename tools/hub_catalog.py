HUBS = [
    {"city": "Miami", "state": "Florida", "region": "Southeast"},
    {"city": "Houston", "state": "Texas", "region": "South"},
    {"city": "Dallas", "state": "Texas", "region": "South"},
    {"city": "Denver", "state": "Colorado", "region": "West"},
    {"city": "Chicago", "state": "Illinois", "region": "Midwest"},
    {"city": "Minneapolis", "state": "Minnesota", "region": "Midwest"},
    {"city": "Detroit", "state": "Michigan", "region": "Midwest"},
    {"city": "St. Louis", "state": "Missouri", "region": "Midwest"},
]


def get_hubs(region: str | None = None) -> list[dict]:
    if region is None:
        return [hub.copy() for hub in HUBS]

    normalized_region = region.strip().lower()

    return [
        hub.copy()
        for hub in HUBS
        if hub["region"].lower() == normalized_region
    ]