from pydantic import BaseModel, ConfigDict


class AgentAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    key_findings: list[str]
    limitations: list[str]
