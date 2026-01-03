# ai-learning-assistant

WORISON — Wisdom-Oriented Responsive Intelligent Support & Operations Network. A simple Flask app with local utilities to extract text from files and interact with a configured generative model (Gemini/Google AI, optional).

## Overview 

- Backend: Flask (Python) providing endpoints for chat, summarization, keywords, file upload and extraction.
- Frontend: simple static files under `frontend/` (templates & static assets).
- Utilities for extracting text from PDFs/DOCX/CSV/images (PyPDF2, python-docx, pandas, pytesseract + Poppler)
- Model wrapper: single-model `MODEL_NAME` driven by `GEMINI_API_KEY` env var (optional). When not set the app runs in fallback mode.

---

## Quick start (local, Windows) 

Follow this checklist to get the project running locally on Windows.

1. Create and activate a virtual environment (PowerShell):

    ```powershell
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    ```

2. Install dependencies:

    ```powershell
    pip install -r backend/requirements.txt
    # For development tools (linting/tests): pip install ruff pytest
    ```

3. Set up local environment variables:
   - Copy `backend/.env.example` to `backend/.env` and fill in values locally (do NOT commit `backend/.env`).
   - Set `GEMINI_API_KEY` if you want the model enabled; otherwise the app runs in fallback mode.

4. Install OCR system requirements (Windows):
   - Install Poppler and add its `bin` path to PATH (or place in `C:\poppler\bin`).
   - Install Tesseract-OCR and ensure `tesseract.exe` is on PATH.

5. Run the app (from repository root):

    ```powershell
    # activate .venv first
    python -m backend.app
    # or
    python backend/app.py
    ```

6. Visit the UI in your browser: http://127.0.0.1:5000/

---

## Developer notes 

- The model wrapper checks `GEMINI_API_KEY` and will log if the model is disabled (informational). Set `GEMINI_API_KEY` to enable model interactions.
- File uploads are written to `backend/uploads`. Extracted text is cached under your app storage dir (Windows: `%APPDATA%/ai-learning-assistant`).
- Logging is enabled — check console output for extraction and model errors. Use `logging` configuration to adjust verbosity for development vs production.

## Security & Git 

- **Do NOT commit secrets.** Use `backend/.env` locally and add `backend/.env.example` to the repo to show the expected variables.
- If a secret was committed:
  - Remove the tracked file and commit: `git rm --cached backend/.env && git commit -m "Remove backend/.env from repository"`.
  - To remove secrets from history, use a history rewriting tool like the [BFG Repo Cleaner](https://rtyley.github.io/bfg-repo-cleaner/) or `git filter-branch`, followed by rotating the exposed credentials.
- Untrack local virtualenvs: if `.venv` was accidentally added run `git rm -r --cached .venv && git commit -m "Remove tracked virtualenv"` and ensure `.venv/` is listed in `.gitignore`.

---

## Tests & Linting 

- Unit tests:
  - Run all tests in the backend: `python -m pytest backend -q`.
  - Example: `backend/test_app_ping.py` checks the `/ping` health endpoint.

- Integration tests:
  - Use `backend/test_integration.py` for a manual end-to-end exercise (it performs signup/login, chat, summarize, keyword extraction).

- Linting and formatting:
  - `ruff` for linting: `pip install ruff` then `ruff check backend` or `ruff check --fix backend`.
  - (Optional) use `black` for formatting.

- Handling noisy warnings (flask-limiter):
  - During tests you may see `Using the in-memory storage for tracking rate limits` from `flask-limiter`. To avoid this:
    - Disable rate-limiting in tests: set `app.config['RATELIMIT_ENABLED'] = False` in your test setup; or
    - Configure a persistent backend (Redis) and set `RATELIMIT_STORAGE_URI`.
  - You can also suppress specific warnings using pytest filters, but prefer addressing the root cause for production parity.

---

## Production notes 

- Use a production WSGI server (gunicorn/uWSGI) behind a reverse proxy (NGINX) in production.
- Configure `FLASK_SECRET_KEY` via environment variable to a strong secret — do not use the default development key.
- Configure a persistent rate-limit backend (Redis recommended) by setting `RATELIMIT_STORAGE_URI` (e.g., `redis://127.0.0.1:6379`).
- Review file upload storage, permissions, and retention policies before deploying.

---

## CI / GitHub Actions (optional)

- It's recommended to add a basic GitHub Actions workflow to run tests on push/PRs. Steps: checkout, set up Python, install dependencies, run `pytest`.
- If you'd like, I can create a minimal `.github/workflows/ci.yml` that runs the test suite on every push.

---

## Contributing 

Please see `CONTRIBUTING.md` for contribution guidelines.

---

## License

**All rights reserved.** This project is not licensed for reuse. If you'd like to allow reuse or redistribution, consider adding a license (for example, `MIT` or `CC BY-NC`).

---

## Contributing 

Please see `CONTRIBUTING.md` for contribution guidelines.

---

## License

This repository is delivered without a license file. Add a `LICENSE` if you plan to publish this project.
