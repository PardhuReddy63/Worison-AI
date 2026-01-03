# backend/test_integration.py

import re
from app import app


# Run basic end-to-end tests against the Flask application
def _extract_csrf(html_text: str) -> str:
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html_text)
    return m.group(1) if m else ""


def run_tests():
    client = app.test_client()

    print("\n--- GET /ping")
    resp = client.get("/ping")
    print(resp.status_code, resp.get_json())

    # Ensure we are logged in (signup or login) so /chat is allowed
    test_email = "test@example.com"
    test_password = "Test123!"

    # Try signup first (fetch CSRF token from the form)
    print("--- GET /signup (fetch CSRF)")
    r = client.get("/signup")
    token = _extract_csrf(r.get_data(as_text=True))
    print("csrf token present:", bool(token))

    print("--- POST /signup")
    resp = client.post(
        "/signup",
        data={"email": test_email, "password": test_password, "csrf_token": token},
        follow_redirects=True,
    )
    print(resp.status_code)

    # If signup failed (user exists), try login
    if resp.status_code != 200 and resp.status_code != 302:
        print("Signup did not redirect — attempting login")
        r = client.get("/login")
        token = _extract_csrf(r.get_data(as_text=True))
        resp = client.post(
            "/login",
            data={"email": test_email, "password": test_password, "csrf_token": token},
            follow_redirects=True,
        )
        print("login status:", resp.status_code)

    # Now test standard chat endpoint with a simple message
    print("--- POST /chat")
    resp = client.post(
        "/chat",
        json={"message": "Hello, this is a quick integration test.", "history": []},
    )
    print(resp.status_code, resp.get_json())

    # Test text summarization API
    print("--- POST /api/summarize")
    resp = client.post(
        "/api/summarize",
        json={"text": "This is a test document. It has two sentences.", "bullets": 2},
    )
    print(resp.status_code, resp.get_json())

    # Test keyword extraction API
    print("--- POST /api/keywords")
    resp = client.post(
        "/api/keywords",
        json={
            "text": "Apples, oranges, and bananas are fruits used in pies and smoothies.",
            "top_k": 5,
        },
    )
    print(resp.status_code, resp.get_json())

    # Test streaming chat endpoint using Server-Sent Events
    print("--- POST /stream_chat")
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
