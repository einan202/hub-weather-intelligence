from fastapi.testclient import TestClient

import app as app_module


client = TestClient(app_module.app)


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_strips_message_and_forwards_previous_response_id(monkeypatch):
    calls = []

    def fake_run_agent(user_message, previous_response_id=None):
        calls.append(
            {
                "user_message": user_message,
                "previous_response_id": previous_response_id,
            }
        )
        return {
            "response_id": "resp_123",
            "output": {
                "answer": "Houston has higher precipitation exposure.",
                "key_findings": ["257 high-precipitation days"],
                "limitations": ["Not a shutdown probability"],
            },
        }

    monkeypatch.setattr(app_module, "run_agent", fake_run_agent)

    response = client.post(
        "/chat",
        json={
            "message": "  hello  ",
            "previous_response_id": "resp_prev",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "response_id": "resp_123",
        "output": {
            "answer": "Houston has higher precipitation exposure.",
            "key_findings": ["257 high-precipitation days"],
            "limitations": ["Not a shutdown probability"],
        },
    }
    assert calls == [
        {
            "user_message": "hello",
            "previous_response_id": "resp_prev",
        }
    ]


def test_chat_rejects_empty_message():
    response = client.post(
        "/chat",
        json={"message": ""},
    )

    assert response.status_code == 422


def test_chat_rejects_whitespace_only_message():
    response = client.post(
        "/chat",
        json={"message": "   "},
    )

    assert response.status_code == 422
