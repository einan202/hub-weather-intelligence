import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from agent.prompts import build_system_prompt
from agent.schemas import AgentAnswer
from agent.tools import TOOL_DEFINITIONS, execute_tool


MAX_TOOL_ROUNDS = 8


def _tool_output(call) -> dict:
    try:
        arguments = json.loads(call.arguments or "{}")
    except json.JSONDecodeError as error:
        result = {
            "error": {
                "type": "JSONDecodeError",
                "message": str(error),
            }
        }
    else:
        if not isinstance(arguments, dict):
            result = {
                "error": {
                    "type": "ValueError",
                    "message": "Tool arguments must be a JSON object.",
                }
            }
        else:
            result = execute_tool(call.name, arguments)

    return {
        "type": "function_call_output",
        "call_id": call.call_id,
        "output": json.dumps(result),
    }


def run_agent(
    user_message: str,
    previous_response_id: str | None = None,
) -> dict:
    """Answer one user turn with the Responses API and local tools."""
    load_dotenv()

    model = os.getenv("OPENAI_MODEL") or "gpt-4.1-mini"
    client = OpenAI()
    instructions = build_system_prompt()
    current_input: str | list = user_message
    previous_id = previous_response_id

    for _ in range(MAX_TOOL_ROUNDS):
        request = {
            "model": model,
            "instructions": instructions,
            "tools": TOOL_DEFINITIONS,
            "input": current_input,
        }

        if previous_id:
            request["previous_response_id"] = previous_id

        response = client.responses.parse(
            **request,
            text_format=AgentAnswer,
        )
        previous_id = response.id

        calls = [
            item
            for item in response.output
            if item.type == "function_call"
        ]

        if not calls:
            answer = response.output_parsed
            if answer is None:
                raise RuntimeError(
                    "Model response did not include a parsed final answer."
                )

            return {
                "response_id": response.id,
                "output": answer.model_dump(),
            }

        current_input = [
            _tool_output(call)
            for call in calls
        ]

    raise RuntimeError("Max tool-call iterations exceeded")
