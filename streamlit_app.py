import os

import requests
import streamlit as st
from dotenv import load_dotenv


load_dotenv()

API_BASE_URL = os.getenv(
    "API_BASE_URL",
    "http://127.0.0.1:8000",
).rstrip("/")

ERROR_MESSAGE = "The analysis service is unavailable. Please try again."
REQUEST_TIMEOUT_SECONDS = 120


def _read_chat_response(response: requests.Response) -> tuple[str, dict]:
    if response.status_code != 200:
        raise ValueError("Chat request failed.")

    payload = response.json()
    output = payload["output"]
    response_id = payload["response_id"]
    answer = output["answer"]
    key_findings = output["key_findings"]
    limitations = output["limitations"]

    if not isinstance(response_id, str) or not response_id:
        raise ValueError("Chat response is missing response_id.")

    if not isinstance(answer, str):
        raise ValueError("Chat response is missing answer.")

    if (
        not isinstance(key_findings, list)
        or not all(isinstance(item, str) for item in key_findings)
    ):
        raise ValueError("Chat response is missing key_findings.")

    if (
        not isinstance(limitations, list)
        or not all(isinstance(item, str) for item in limitations)
    ):
        raise ValueError("Chat response is missing limitations.")

    return response_id, {
        "answer": answer,
        "key_findings": key_findings,
        "limitations": limitations,
    }


def _render_message(message: dict) -> None:
    with st.chat_message(message["role"]):
        if message["role"] == "user":
            st.markdown(message["content"])
            return

        st.markdown(message["answer"])

        if message["key_findings"]:
            for finding in message["key_findings"]:
                st.markdown(f"- {finding}")

        if message["limitations"]:
            for limitation in message["limitations"]:
                st.markdown(f"- {limitation}")


st.title("Weather Risk Intelligence Agent")

if "messages" not in st.session_state:
    st.session_state.messages = []

if "previous_response_id" not in st.session_state:
    st.session_state.previous_response_id = None

prompt = st.chat_input("Ask about hub weather exposure")

for message in st.session_state.messages:
    _render_message(message)

if prompt:
    user_message = {
        "role": "user",
        "content": prompt,
    }
    st.session_state.messages.append(user_message)
    _render_message(user_message)

    with st.spinner("Analyzing weather exposure..."):
        try:
            response = requests.post(
                f"{API_BASE_URL}/chat",
                json={
                    "message": prompt,
                    "previous_response_id": (
                        st.session_state.previous_response_id
                    ),
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response_id, output = _read_chat_response(response)
        except (requests.RequestException, ValueError, KeyError, TypeError):
            st.error(ERROR_MESSAGE)
        else:
            assistant_message = {
                "role": "assistant",
                "answer": output["answer"],
                "key_findings": output["key_findings"],
                "limitations": output["limitations"],
            }
            st.session_state.messages.append(assistant_message)
            st.session_state.previous_response_id = response_id
            _render_message(assistant_message)
