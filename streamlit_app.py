import os
import threading
from concurrent.futures import ThreadPoolExecutor

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
HEALTH_TIMEOUT_SECONDS = 8


@st.cache_resource
def _chat_executor() -> ThreadPoolExecutor:
    return ThreadPoolExecutor(max_workers=1)


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


def _post_chat(message: str, previous_response_id: str | None) -> tuple[str, dict]:
    response = requests.post(
        f"{API_BASE_URL}/chat",
        json={
            "message": message,
            "previous_response_id": previous_response_id,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    return _read_chat_response(response)


def _warm_backend() -> None:
    try:
        requests.get(
            f"{API_BASE_URL}/health",
            timeout=HEALTH_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        return


def _render_message(message: dict) -> None:
    with st.chat_message(message["role"]):
        if message["role"] == "user":
            st.markdown(message["content"])
            return

        st.markdown(message["answer"])

        if message["key_findings"]:
            st.markdown(
                '<p class="key-findings-heading">Key findings</p>',
                unsafe_allow_html=True,
            )
            for finding in message["key_findings"]:
                st.markdown(f"- {finding}")

        if message["limitations"]:
            with st.expander("Limitations"):
                for limitation in message["limitations"]:
                    st.markdown(f"- {limitation}")


EXAMPLE_QUESTIONS = (
    (
        "Midwest winter exposure",
        "Which hubs in the Midwest are most exposed to winter disruption?",
    ),
    (
        "Miami vs Houston",
        "Compare Miami and Houston in terms of hurricane and flood exposure.",
    ),
    (
        "Denver snowfall",
        "What percentage of days in Denver last year had snowfall?",
    ),
    (
        "Dallas exposure",
        "Why is the Dallas hub's weather disruption risk high?",
    ),
)


def _queue_user_message(text: str) -> None:
    active_future = st.session_state.chat_future
    if active_future is not None and not active_future.done():
        return
    if st.session_state.is_processing or st.session_state.pending_message is not None:
        return

    st.session_state.messages.append({
        "role": "user",
        "content": text,
    })
    st.session_state.pending_message = text
    st.session_state.is_processing = True
    st.session_state.chat_future = _chat_executor().submit(
        _post_chat,
        text,
        st.session_state.previous_response_id,
    )
    st.rerun()


st.markdown(
    """
    <style>
    .stApp {
      background: #F8FAFC;
      color: #0F172A;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    [data-testid="stMainBlockContainer"] {
      padding-top: 1.25rem;
    }
    .st-key-app_header {
      gap: 0.15rem;
    }
    .st-key-app_header h1 {
      margin-top: 0.65rem;
      margin-bottom: 0;
      color: #0F172A;
      font-size: 2.13rem;
      text-align: center;
    }
    .st-key-app_header p {
      margin-top: 0;
      color: #64748B;
      text-align: center;
    }
    .welcome-block {
      color: #64748B;
      margin: 0.15rem 0 0.4rem;
      text-align: center;
    }
    .welcome-block p {
      margin: 0.15rem 0;
    }
    .st-key-example_questions button {
      background: #FFFFFF;
      color: #0F172A;
      border: 1px solid #E2E8F0;
      border-radius: 12px;
      padding: 0.28rem 0.75rem;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
    }
    .st-key-example_questions button:hover {
      border-color: #2563EB;
      transform: translateY(-1px);
      box-shadow: 0 4px 10px rgba(15, 23, 42, 0.08);
      color: #0F172A;
    }
    .st-key-example_questions button:disabled {
      transform: none;
      box-shadow: none;
    }
    .st-key-example_questions {
      gap: 0.35rem;
    }
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
      background: #EFF6FF;
      border: 1px solid #E2E8F0;
      border-radius: 12px;
    }
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
      background: #FFFFFF;
      border: 1px solid #E2E8F0;
      border-radius: 12px;
    }
    [data-testid="stChatMessageAvatarUser"] {
      background: #F8E4DF;
      color: #C45C52;
    }
    [data-testid="stChatMessageAvatarAssistant"] {
      background: #F8EBD6;
      color: #C4843A;
    }
    [data-testid="stChatMessageAvatarUser"] svg {
      fill: #C45C52;
      color: #C45C52;
    }
    [data-testid="stChatMessageAvatarAssistant"] svg {
      fill: #C4843A;
      color: #C4843A;
    }
    .key-findings-heading {
      font-weight: 650;
      color: #0F172A;
      margin: 0.85rem 0 0.2rem;
    }
    [data-testid="stChatMessageContent"] ul {
      margin-top: 0.15rem;
      margin-bottom: 0.3rem;
    }
    [data-testid="stChatMessageContent"] li + li {
      margin-top: 0.12rem;
    }
    [data-testid="stChatMessage"] [data-testid="stExpander"] {
      border: 1px solid #E2E8F0;
      border-radius: 10px;
      background: transparent;
    }
    [data-testid="stSidebar"] {
      background: #FFFFFF;
      border-right: 1px solid #E2E8F0;
    }
    [data-testid="stSidebar"] h3 {
      color: #0F172A;
      font-size: 1rem;
      font-weight: 650;
      margin-bottom: 0.35rem;
    }
    .sidebar-label {
      color: #0F172A;
      font-size: 0.78rem;
      font-weight: 650;
      margin: 0.7rem 0 0.1rem;
    }
    .sidebar-value {
      color: #64748B;
      font-size: 0.92rem;
      margin: 0;
    }
    [data-testid="stChatInput"] {
      border: 1px solid #E2E8F0;
      border-radius: 12px;
      background: #FFFFFF;
    }
    [data-testid="stChatInput"]:focus-within {
      border-color: #2563EB;
      box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.16);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.subheader("About this analysis")
    st.markdown('<p class="sidebar-label">Data sources</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sidebar-value">Open-Meteo · OpenFEMA</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="sidebar-label">Analysis window</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="sidebar-value">Last 15 complete calendar years</p>',
        unsafe_allow_html=True,
    )
    st.markdown('<p class="sidebar-label">Scope</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sidebar-value">Historical exposure only</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="sidebar-value">Not operational disruption probability</p>',
        unsafe_allow_html=True,
    )

if "messages" not in st.session_state:
    st.session_state.messages = []

if "previous_response_id" not in st.session_state:
    st.session_state.previous_response_id = None

if "is_processing" not in st.session_state:
    st.session_state.is_processing = False

if "pending_message" not in st.session_state:
    st.session_state.pending_message = None

if "show_error" not in st.session_state:
    st.session_state.show_error = False

if "chat_future" not in st.session_state:
    st.session_state.chat_future = None

if "health_warmup_started" not in st.session_state:
    st.session_state.health_warmup_started = False

if not st.session_state.health_warmup_started:
    st.session_state.health_warmup_started = True
    threading.Thread(target=_warm_backend, daemon=True).start()

chat_future = st.session_state.chat_future
request_in_flight = chat_future is not None and not chat_future.done()

with st.container(key="app_header"):
    st.title("Weather Risk Intelligence Agent")
    st.markdown(
        "Historical weather and hazard exposure analysis for U.S. logistics hubs."
    )

if not st.session_state.messages:
    st.markdown(
        """
        <div class="welcome-block">
        <p>Explore historical weather exposure across U.S. logistics hubs</p>
        <p>Compare locations, examine specific hazards, or choose an example question from the sidebar.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

with st.sidebar:
    st.subheader("Example questions")
    with st.container(key="example_questions"):
        for label, question in EXAMPLE_QUESTIONS:
            clicked = st.button(
                label,
                disabled=(
                    st.session_state.is_processing
                    or st.session_state.pending_message is not None
                    or request_in_flight
                ),
                key=f"example-{label}",
                use_container_width=True,
            )
            if (
                clicked
                and not st.session_state.is_processing
                and st.session_state.pending_message is None
                and not request_in_flight
            ):
                _queue_user_message(question)

for message in st.session_state.messages:
    _render_message(message)

if st.session_state.show_error:
    st.error(ERROR_MESSAGE)
    st.session_state.show_error = False

prompt = st.chat_input(
    "Ask about hub weather exposure",
    disabled=(
        st.session_state.is_processing
        or request_in_flight
        or st.session_state.pending_message is not None
    ),
)

if prompt:
    _queue_user_message(prompt)

if chat_future is not None:
    if not chat_future.done():
        with st.spinner("Analyzing weather exposure..."):
            try:
                chat_future.result()
            except (requests.RequestException, ValueError, KeyError, TypeError):
                pass

    if st.session_state.chat_future is chat_future and chat_future.done():
        try:
            response_id, output = chat_future.result()
            failed = False
        except (requests.RequestException, ValueError, KeyError, TypeError):
            response_id, output = None, None
            failed = True
        if st.session_state.chat_future is chat_future:
            st.session_state.chat_future = None
            st.session_state.pending_message = None
            st.session_state.is_processing = False
            if failed:
                st.session_state.show_error = True
            else:
                st.session_state.messages.append({
                    "role": "assistant",
                    "answer": output["answer"],
                    "key_findings": output["key_findings"],
                    "limitations": output["limitations"],
                })
                st.session_state.previous_response_id = response_id
            st.rerun()
