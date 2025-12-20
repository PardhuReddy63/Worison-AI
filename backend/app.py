# backend/app.py
"""
Main Flask app for AI Learning Assistant
- Chat (normal + streaming)
- File upload (treated as conversation turns)
- File explanation / summarization
- Conversation persistence
"""

import os
import uuid
import json
import time
import logging
from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_from_directory,
    Response,
)
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from jinja2 import TemplateNotFound
from flask_cors import CORS

# --------------------------------------------------
# Environment & logging
# --------------------------------------------------
load_dotenv()

logger = logging.getLogger("ai-assistant")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(
    logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
)
if not logger.handlers:
    logger.addHandler(handler)

# --------------------------------------------------
# Internal imports
# --------------------------------------------------
from model_wrapper import get_wrapper
from utils import (
    extract_text_from_pdf,
    extract_text_from_docx,
    extract_text_from_txt,
    extract_text_from_csv_or_excel,
    extract_text_from_image,
    explain_pdf,
    summarize_text,
    extract_keywords,
)

# --------------------------------------------------
# Flask setup
# --------------------------------------------------
app = Flask(
    __name__,
    static_folder="../frontend/static",
    template_folder="../frontend/templates",
)

CORS(app)

app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB upload limit
app.jinja_env.globals["static_version"] = str(int(time.time()))

# --------------------------------------------------
# Storage directories
# --------------------------------------------------
def get_storage_dir():
    name = "ai-learning-assistant"
    try:
        if os.name == "nt":
            base = os.getenv("APPDATA") or os.path.join(
                os.path.expanduser("~"), "AppData", "Roaming"
            )
            path = os.path.join(base, name)
        else:
            path = os.path.join(os.path.expanduser("~"), ".local", "share", name)
        os.makedirs(path, exist_ok=True)
        return path
    except Exception:
        fallback = os.path.join(os.path.dirname(__file__), "data")
        os.makedirs(fallback, exist_ok=True)
        return fallback


STORAGE_DIR = get_storage_dir()
CONVERSATIONS_DIR = os.path.join(STORAGE_DIR, "conversations")
FILES_DIR = os.path.join(STORAGE_DIR, "files")

os.makedirs(CONVERSATIONS_DIR, exist_ok=True)
os.makedirs(FILES_DIR, exist_ok=True)

# --------------------------------------------------
# Upload config
# --------------------------------------------------
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {
    "pdf",
    "txt",
    "docx",
    "csv",
    "xlsx",
    "png",
    "jpg",
    "jpeg",
    "gif",
    "py",
    "js",
    "html",
    "json",
    "md",
    "webm",
}

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# --------------------------------------------------
# Conversation persistence
# --------------------------------------------------
def save_conversation(history):
    try:
        path = os.path.join(CONVERSATIONS_DIR, "conversation.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        logger.exception("Failed to save conversation: %s", e)


def load_conversation():
    path = os.path.join(CONVERSATIONS_DIR, "conversation.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


# --------------------------------------------------
# File name mapping (original → unique)
# --------------------------------------------------
def _file_map_path():
    return os.path.join(STORAGE_DIR, "file_map.json")


def save_file_mapping(original_name, unique_name):
    mapping = {}
    path = _file_map_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                mapping = json.load(f)
        except Exception:
            mapping = {}

    mapping[original_name] = {
        "unique_name": unique_name,
        "timestamp": time.time(),
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2)


# --------------------------------------------------
# Model wrapper
# --------------------------------------------------
wrapper = get_wrapper()

# --------------------------------------------------
# Routes
# --------------------------------------------------
@app.route("/")
def index():
    try:
        return render_template("index.html")
    except TemplateNotFound:
        return "<h3>index.html not found</h3>"


@app.route("/ping")
def ping():
    return jsonify({"status": "ok"})


# --------------------------------------------------
# Chat (NON-streaming)
# --------------------------------------------------
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json() or {}
    user_input = (data.get("message") or "").strip()
    history = data.get("history") or []

    if not user_input:
        return jsonify({"response": "(error) No input provided."})

    # ---- FIX: support both `text` (frontend) and `content` (backend)
    for turn in reversed(history):
        if turn.get("role") == "file":
            file_id = turn.get("file_id")
            original = turn.get("original_name", "")
            if file_id:
                file_text = _get_file_text(file_id)
                if file_text:
                    user_input = (
                        f"\n\n--- File: {original} ---\n"
                        f"{file_text}\n---\n"
                        + user_input
                    )
            break

    try:
        if hasattr(wrapper, "chat_response"):
            reply = wrapper.chat_response(user_input, history=history)
        else:
            reply = "(error) Model wrapper not available."

        history.append({"role": "assistant", "content": reply})
        save_conversation(history)

        return jsonify({"response": reply})
    except Exception as e:
        logger.exception("chat error: %s", e)
        return jsonify({"response": f"(error) {e}"})


# --------------------------------------------------
# Chat (STREAMING via SSE)
# --------------------------------------------------
@app.route("/stream_chat", methods=["POST"])
def stream_chat():
    data = request.get_json() or {}
    user_input = (data.get("message") or "").strip()
    history = data.get("history") or []

    if not user_input:
        return jsonify({"response": "(error) No input provided."})

    if hasattr(wrapper, "chat_response"):
        full = wrapper.chat_response(user_input, history=history)
    else:
        full = "(error) Model wrapper not available."

    def gen():
        import re

        parts = re.split(r"(\.|\?|!|\n)", full)
        buf = ""
        for p in parts:
            buf += p
            if len(buf) > 120:
                yield f"data: {buf.strip()}\n\n"
                buf = ""
        if buf:
            yield f"data: {buf.strip()}\n\n"

    return Response(gen(), content_type="text/event-stream")


# --------------------------------------------------
# Text utilities
# --------------------------------------------------
@app.route("/api/summarize", methods=["POST"])
def api_summarize():
    data = request.get_json() or {}
    text = data.get("text") or ""
    bullets = int(data.get("bullets", 3))

    if not text.strip():
        return jsonify({"summary": "(error) No text provided."})

    try:
        summary = (
            wrapper.summarize(text, bullets=bullets)
            if hasattr(wrapper, "summarize")
            else summarize_text(text, bullets)
        )
        return jsonify({"summary": summary})
    except Exception as e:
        return jsonify({"summary": f"(error) {e}"})


@app.route("/api/keywords", methods=["POST"])
def api_keywords():
    data = request.get_json() or {}
    text = data.get("text") or ""
    top_k = int(data.get("top_k", 8))

    if not text.strip():
        return jsonify({"keywords": []})

    try:
        kws = (
            wrapper.keywords(text, top_k=top_k)
            if hasattr(wrapper, "keywords")
            else extract_keywords(text, top_k)
        )
        return jsonify({"keywords": kws})
    except Exception:
        return jsonify({"keywords": []})


# --------------------------------------------------
# File upload
# --------------------------------------------------
@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded."})

    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"error": "No selected file."})

    if not allowed_file(file.filename):
        return jsonify({"error": "File type not allowed."})

    original_name = secure_filename(file.filename)
    unique_name = f"{uuid.uuid4().hex}_{original_name}"
    path = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)

    try:
        file.save(path)
        save_file_mapping(original_name, unique_name)

        ext = original_name.rsplit(".", 1)[1].lower()
        text_available = bool(_get_file_text(unique_name))

        return jsonify(
            {
                "role": "file",
                "file_id": unique_name,
                "original_name": original_name,
                "file_type": ext,
                "text_available": text_available,
            }
        )
    except Exception as e:
        logger.exception("Upload error: %s", e)
        return jsonify({"error": str(e)}), 500


# --------------------------------------------------
# Extract & cache file text
# --------------------------------------------------
def _get_file_text(filename):
    cache_path = os.path.join(FILES_DIR, f"{filename}.txt")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass

    original_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    if not os.path.exists(original_path):
        return ""

    ext = filename.rsplit(".", 1)[1].lower()
    try:
        if ext == "pdf":
            text = extract_text_from_pdf(original_path)
        elif ext in ("png", "jpg", "jpeg", "gif"):
            text = extract_text_from_image(original_path)
        elif ext == "docx":
            text = extract_text_from_docx(original_path)
        elif ext in ("csv", "xlsx"):
            text = extract_text_from_csv_or_excel(original_path)
        else:
            text = extract_text_from_txt(original_path)
    except Exception:
        text = ""

    if text and not text.startswith("(error)"):
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            pass

    return "" if text.startswith("(error)") else text


# --------------------------------------------------
# Explain uploaded file
# --------------------------------------------------
@app.route("/explain_file", methods=["POST"])
def explain_file():
    data = request.get_json() or {}
    filename = data.get("filename")
    bullets = int(data.get("bullets", 4))

    if not filename:
        return jsonify({"error": "filename required"})

    path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    if not os.path.exists(path):
        return jsonify({"error": "file not found"})

    try:
        resp = explain_pdf(path=path, bullets=bullets)
        return jsonify(
            {
                "ok": True,
                "partials": resp.get("partials", []),
                "final": resp.get("final", ""),
            }
        )
    except Exception as e:
        logger.exception("explain_file error: %s", e)
        return jsonify({"error": str(e)})


# --------------------------------------------------
# Static uploaded files
# --------------------------------------------------
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# --------------------------------------------------
# Disable static caching
# --------------------------------------------------
@app.after_request
def add_no_cache_headers(response):
    if request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# --------------------------------------------------
# Run
# --------------------------------------------------
if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", 5000))
    logger.info("Starting app on %s:%d", host, port)
    app.run(host=host, port=port)
