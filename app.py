from fastapi import FastAPI
from pydantic import BaseModel, field_validator

from agent.schemas import AgentAnswer
from agent.service import run_agent

app = FastAPI()


class ChatRequest(BaseModel):
    message: str
    previous_response_id: str | None = None

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("message must not be empty")
        return stripped


class ChatResponse(BaseModel):
    response_id: str
    output: AgentAnswer


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest) -> dict:
    return run_agent(
        user_message=body.message,
        previous_response_id=body.previous_response_id,
    )
