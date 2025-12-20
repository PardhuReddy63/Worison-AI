# ai-learning-assistant

AI Learning Assistant — simple Flask + local utilities to extract text from files and interact with a configured generative model (Gemini/Google AI, optional).

## Overview ✅

- Backend: Flask (Python) providing endpoints for chat, summarization, keywords, file upload and extraction.
- Frontend: simple static files under `frontend/` (templates & static assets).
- Utilities for extracting text from PDFs/DOCX/CSV/images (PyPDF2, python-docx, pandas, pytesseract + Poppler)
- Model wrapper: single-model `MODEL_NAME` driven by `GEMINI_API_KEY` env var (optional). When not set the app runs in fallback mode.

---

## Quick start (local, Windows) 🔧

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

3. Install system requirements for OCR (Windows):
   - Install Poppler and add its `bin` path to PATH (or place in `C:\poppler\bin`).
   - Install Tesseract-OCR and ensure `tesseract.exe` is on PATH.

4. Set env vars (optional):

    ```powershell
    setx GEMINI_API_KEY "<your-key>"
    setx MODEL_NAME "models/gemini-2.0-flash-lite"
    ```

5. Run the app (from repository root):

    ```powershell
    # activate .venv first
    python -m backend.app
    # or
    python backend/app.py
    ```

6. Visit http://127.0.0.1:5000/

---

## Developer notes 🧭

- Model is disabled if `GEMINI_API_KEY` is not set. The code logs whether the model was successfully initialized.
- File uploads are written to `backend/uploads` and extracted text cached under your app storage dir (on Windows this defaults to `%APPDATA%/ai-learning-assistant`).
- The code includes helpful logging; check console output for extraction and model errors.

---

## Tests & Linting ⚠️

- Run `ruff` or `flake8` for linting. Small syntax checks can be done with `python -m py_compile backend/*.py`.
- Add tests in `tests/` and run via `pytest`.

---

## Contributing ✨

Please see `CONTRIBUTING.md` for contribution guidelines.

---

## License

This repository is delivered without a license file. Add a `LICENSE` if you plan to publish this project.
