import pytest
from pydantic import ValidationError

from agent.schemas import AgentAnswer


def test_agent_answer_accepts_required_fields():
    answer = AgentAnswer.model_validate(
        {
            "answer": "Houston has higher precipitation exposure.",
            "key_findings": ["257 high-precipitation days"],
            "limitations": ["Not a shutdown probability"],
        }
    )

    assert answer.model_dump() == {
        "answer": "Houston has higher precipitation exposure.",
        "key_findings": ["257 high-precipitation days"],
        "limitations": ["Not a shutdown probability"],
    }


def test_agent_answer_accepts_empty_lists():
    answer = AgentAnswer.model_validate(
        {
            "answer": "No matching hubs.",
            "key_findings": [],
            "limitations": [],
        }
    )

    assert answer.key_findings == []
    assert answer.limitations == []


def test_agent_answer_rejects_missing_field():
    with pytest.raises(ValidationError):
        AgentAnswer.model_validate(
            {
                "answer": "Dallas",
                "key_findings": [],
            }
        )


def test_agent_answer_rejects_extra_field():
    with pytest.raises(ValidationError):
        AgentAnswer.model_validate(
            {
                "answer": "Dallas",
                "key_findings": [],
                "limitations": [],
                "report": {"secret": True},
            }
        )
