from tools.hub_catalog import get_hubs
from tools.hub_report import get_hub_exposure_report
from tools.ranking import rank_hubs_by_exposure


_NULLABLE_STRING = {"type": ["string", "null"]}

_HUB_SCHEMA = {
    "type": "object",
    "properties": {
        "city": {"type": "string"},
        "state": _NULLABLE_STRING,
    },
    "required": ["city", "state"],
    "additionalProperties": False,
}

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "name": "get_hubs",
        "description": (
            "List catalog hubs. Pass a region such as Midwest, "
            "or null to return every hub."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "region": _NULLABLE_STRING,
            },
            "required": ["region"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_hub_exposure_report",
        "description": (
            "Return deterministic weather exposure and FEMA Major "
            "Disaster declaration context for one U.S. hub. "
            "Pass null dates to use the default 15-year window. "
            "State is the full state name, not an abbreviation."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "state": _NULLABLE_STRING,
                "start_date": _NULLABLE_STRING,
                "end_date": _NULLABLE_STRING,
            },
            "required": [
                "city",
                "state",
                "start_date",
                "end_date",
            ],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "rank_hubs_by_exposure",
        "description": (
            "Rank hubs with the deterministic ranking tool. "
            "Do not sort the values yourself. "
            "hazard is overall, winter, flood, storm, or hurricane."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "hubs": {
                    "type": "array",
                    "items": _HUB_SCHEMA,
                },
                "hazard": {
                    "type": "string",
                    "enum": [
                        "overall",
                        "winter",
                        "flood",
                        "storm",
                        "hurricane",
                    ],
                },
                "start_date": _NULLABLE_STRING,
                "end_date": _NULLABLE_STRING,
            },
            "required": [
                "hubs",
                "hazard",
                "start_date",
                "end_date",
            ],
            "additionalProperties": False,
        },
    },
]


def _error_result(error: Exception) -> dict:
    return {
        "error": {
            "type": type(error).__name__,
            "message": str(error),
        }
    }


def _without_embedded_reports(result: dict) -> dict:
    return {
        **result,
        "hubs": [
            {
                key: value
                for key, value in hub.items()
                if key != "report"
            }
            for hub in result["hubs"]
        ],
    }


def execute_tool(name: str, arguments: dict) -> dict | list:
    """Run one model-facing tool and return JSON-serializable data."""
    try:
        if name == "get_hubs":
            return get_hubs(region=arguments.get("region"))

        if name == "get_hub_exposure_report":
            return get_hub_exposure_report(
                city=arguments["city"],
                state=arguments.get("state"),
                start_date=arguments.get("start_date"),
                end_date=arguments.get("end_date"),
            )

        if name == "rank_hubs_by_exposure":
            ranked = rank_hubs_by_exposure(
                hubs=arguments["hubs"],
                hazard=arguments.get("hazard", "overall"),
                start_date=arguments.get("start_date"),
                end_date=arguments.get("end_date"),
            )
            return _without_embedded_reports(ranked)

        raise ValueError(f"Unknown tool '{name}'.")

    except Exception as error:
        return _error_result(error)
