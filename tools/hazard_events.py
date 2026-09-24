import re

import requests


FEMA_DISASTER_DECLARATIONS_URL = (
    "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries"
)

HAZARD_CATEGORIES = {
    "flood": ["Flood"],
    "hurricane": ["Hurricane"],
    "severe_storm": ["Severe Storm"],
    "winter": ["Snowstorm", "Severe Ice Storm"],
}

_ALL_INCIDENT_TYPES = [
    incident_type
    for incident_types in HAZARD_CATEGORIES.values()
    for incident_type in incident_types
]


def _normalize_area_name(name: str) -> str:
    normalized = name.strip().lower()
    normalized = re.sub(r"\s*\([^)]*\)\s*$", "", normalized)
    normalized = re.sub(
        r"\s+(county|parish|borough)$",
        "",
        normalized,
    )
    return normalized.strip()


def _get_area_search_term(name: str) -> str:
    search_term = name.strip()
    search_term = re.sub(r"\s*\([^)]*\)\s*$", "", search_term)
    search_term = re.sub(
        r"\s+(county|parish|borough)$",
        "",
        search_term,
        flags=re.IGNORECASE,
    )
    return search_term.strip()


def _is_within_period(
    declaration: dict,
    start_date: str | None,
    end_date: str | None,
) -> bool:
    declaration_date = declaration.get("declarationDate")

    if not declaration_date:
        return False

    date = declaration_date[:10]

    if start_date is not None and date < start_date:
        return False

    if end_date is not None and date > end_date:
        return False

    return True


def get_hazard_history(
    state_code: str,
    county: str,
    recent_events_limit: int = 5,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Return FEMA Major Disaster history for a U.S. county.

    FEMA declarations are filtered by primary incident type and optionally
    by a requested date range.
    """
    incident_type_filter = " or ".join(
        f"incidentType eq '{incident_type}'"
        for incident_type in _ALL_INCIDENT_TYPES
    )

    normalized_county = _normalize_area_name(county)
    county_search_term = _get_area_search_term(county)

    odata_county = county_search_term.replace("'", "''")

    filter_expression = (
        f"state eq '{state_code}' "
        f"and declarationType eq 'DR' "
        f"and contains(designatedArea, '{odata_county}') "
        f"and ({incident_type_filter})"
    )

    params = {
        "$filter": filter_expression,
        "$select": (
            "disasterNumber,"
            "incidentType,"
            "declarationTitle,"
            "declarationDate,"
            "designatedArea"
        ),
        "$orderby": "declarationDate desc",
        "$top": 1000,
    }

    response = requests.get(
        FEMA_DISASTER_DECLARATIONS_URL,
        params=params,
        timeout=20,
    )
    response.raise_for_status()

    data = response.json()

    declarations = data.get(
        "DisasterDeclarationsSummaries",
        [],
    )

    if len(declarations) >= 1000:
        raise ValueError(
            "FEMA response may be truncated (hit $top limit); "
            "pagination would be required for this query."
        )

    county_declarations = [
        declaration
        for declaration in declarations
        if (
            declaration.get("designatedArea")
            and _normalize_area_name(
                declaration["designatedArea"]
            )
            == normalized_county
            and _is_within_period(
                declaration,
                start_date,
                end_date,
            )
        )
    ]

    counts = {
        category: 0
        for category in HAZARD_CATEGORIES
    }

    for declaration in county_declarations:
        incident_type = declaration.get("incidentType")

        for category, incident_types in HAZARD_CATEGORIES.items():
            if incident_type in incident_types:
                counts[category] += 1
                break

    recent_events = [
        {
            "disaster_number": declaration.get("disasterNumber"),
            "declaration_title": declaration.get("declarationTitle"),
            "declaration_date": declaration.get("declarationDate"),
            "incident_type": declaration.get("incidentType"),
        }
        for declaration in county_declarations[:recent_events_limit]
    ]

    return {
        "state_code": state_code,
        "county": county,
        "period": {
            "start_date": start_date,
            "end_date": end_date,
        },
        "counts": counts,
        "recent_events": recent_events,
    }