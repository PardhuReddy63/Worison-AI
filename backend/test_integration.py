# backend/test_integration.py
"""
Simple integration tests for AI Learning Assistant backend.

Run:
    python test_integration.py

Ensure:
    - backend/app.py is importable
    - Environment variables (GEMINI_API_KEY, MODEL_NAME) are set if using real model
"""

import json
from app import app


def run_tests():
    client = app.test_client()

    print("\n--- POST /ping")
    resp = client.get("/ping")
    print(resp.status_code, resp.get_json())

    print("\n--- POST /chat")
    resp = client.post(
        "/chat",
        json={
            "message": "Hello, this is a quick integration test.",
            "history": [],
        },
    )
    print(resp.status_code, resp.get_json())

    print("\n--- POST /api/summarize")
    resp = client.post(
        "/api/summarize",
        json={
            "text": "This is a test document. It has two sentences.",
            "bullets": 2,
        },
    )
    print(resp.status_code, resp.get_json())

    print("\n--- POST /api/keywords")
    resp = client.post(
        "/api/keywords",
        json={
            "text": "Apples, oranges, and bananas are fruits used in pies and smoothies.",
            "top_k": 5,
        },
    )
    print(resp.status_code, resp.get_json())

    print("\n--- POST /stream_chat")
    resp = client.post(
        "/stream_chat",
        json={
            "message": "Stream test: say something long enough to chunk and stream.",
            "history": [],
        },
    )
    print("Status:", resp.status_code)
    print("Streamed output (first 1000 chars):")
    print(resp.get_data(as_text=True)[:1000])


if __name__ == "__main__":
    run_tests()
