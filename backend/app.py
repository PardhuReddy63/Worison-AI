# backend/app.py

import os
import uuid
import json
import time
import logging
from flask import (
    Flask, session, redirect,
    render_template, request, jsonify,
    send_from_directory, Response
)
from database import init_db, get_db
from auth import register_user, authenticate_user, validate_password
from chat_store import (
    save_message,
    load_conversation as db_load_conversation,
    list_sessions,
    load_session_messages,
)
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from flask_cors import CORS
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


# Load environment variables from .env file
load_dotenv()


# Configure application-wide logging
logger = logging.getLogger("ai-assistant")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(
    logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
)
if not logger.handlers:
    logger.addHandler(handler)


# Import model wrapper and utility functions used for text extraction and processing
from model_wrapper import get_wrapper  # noqa: E402
from utils import (  # noqa: E402
    extract_text_from_pdf,
    extract_text_from_docx,
    extract_text_from_txt,
    extract_text_from_csv_or_excel,
    extract_text_from_image,
    explain_pdf,
    summarize_text,
    extract_keywords,
)


# Initialize Flask application with frontend paths
app = Flask(
    __name__,
    static_folder="../frontend/static",
    template_folder="../frontend/templates",
)

# Enable Cross-Origin Resource Sharing
CORS(app)

# Enable CSRF protection (exempt JSON API endpoints where appropriate)
csrf = CSRFProtect(app)

# Make `csrf_token()` available in Jinja templates
app.jinja_env.globals["csrf_token"] = generate_csrf

# Rate limiter to protect endpoints from abuse
limiter = Limiter(get_remote_address, app=app, default_limits=["200 per hour"])

# Disable static file caching and set upload size limit
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
app.jinja_env.globals["static_version"] = str(int(time.time()))

# Session secret (required for login)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")

# Initialize database tables
init_db()

# Explicitly declare rate-limit storage (dev-safe)
app.config.update(
    RATELIMIT_STORAGE_URI="memory://"
)

# Determine a safe, OS-independent directory for persistent storage
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


# Create base storage paths for conversations and extracted file text
STORAGE_DIR = get_storage_dir()
CONVERSATIONS_DIR = os.path.join(STORAGE_DIR, "conversations")
FILES_DIR = os.path.join(STORAGE_DIR, "files")

os.makedirs(CONVERSATIONS_DIR, exist_ok=True)
os.makedirs(FILES_DIR, exist_ok=True)


# Configure upload directory used by Flask
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# Define allowed file extensions for uploads
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


# Validate file extension before accepting upload
def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS




# Return path to file mapping metadata
def _file_map_path():
    return os.path.join(STORAGE_DIR, "file_map.json")


# Store original file names mapped to generated unique names
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


# Initialize AI model wrapper instance
wrapper = get_wrapper()


# Serve main frontend page
@app.route("/")
def index():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("index.html", user_email=session.get("email"))


# Health check endpoint
@app.route("/ping")
def ping():
    return jsonify({"status": "ok"})


@limiter.limit("5 per minute")
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    user_id = authenticate_user(email, password)
    if not user_id:
        return render_template("login.html", error="Invalid email or password")

    session["user_id"] = user_id
    session["email"] = email
    return redirect("/")


@limiter.limit("3 per minute")
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("signup.html")

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    ok, error = validate_password(password)
    if not ok:
        return render_template("signup.html", error=error)

    user_id = register_user(email, password)
    if not user_id:
        return render_template("signup.html", error="User already exists")

    session["user_id"] = user_id
    session["email"] = email
    return redirect("/")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# Handle standard chat requests (non-streaming)
@csrf.exempt
@limiter.limit("30 per minute")
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json() or {}
    user_input = (data.get("message") or "").strip()
    session_id = data.get("session_id")

    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"response": "Login required"}), 401

    history = load_session_messages(user_id, session_id) if session_id else []

    if not user_input:
        return jsonify({"response": "(error) No input provided."})

    if not session_id:
        title = user_input.strip()[:60]
        session_id = str(uuid.uuid4())
        try:
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO chat_sessions (id, user_id, title, created_at) VALUES (?, ?, ?, ?)",
                    (session_id, user_id, title, int(time.time()))
                )
                conn.commit()
        except Exception as e:
            return jsonify({"response": f"(error) {e}"})

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
            bot_response = wrapper.chat_response(user_input, history=history)
        else:
            bot_response = "(error) Model wrapper not available."

        # Persist messages to database for multi-user support. We save the
        # user's input and the assistant's reply to the DB for the current
        # authenticated user.
        save_message(user_id, "user", user_input, session_id=session_id)
        save_message(user_id, "assistant", bot_response, session_id=session_id)

        return jsonify({"session_id": session_id, "response": bot_response})
    except Exception as e:
        logger.exception("chat error: %s", e)
        return jsonify({"response": f"(error) {e}"})


# Handle chat responses using Server-Sent Events streaming
@csrf.exempt
@limiter.limit("30 per minute")
@app.route("/stream_chat", methods=["POST"])
def stream_chat():
    data = request.get_json() or {}
    user_input = (data.get("message") or "").strip()
    session_id = data.get("session_id")

    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"response": "Login required"}), 401

    history = load_session_messages(user_id, session_id) if session_id else []

    if not user_input:
        return jsonify({"response": "(error) No input provided."})

    if hasattr(wrapper, "chat_response"):
        full = wrapper.chat_response(user_input, history=history)
    else:
        full = "(error) Model wrapper not available."

    save_message(user_id, "user", user_input, session_id=session_id)
    save_message(user_id, "assistant", full, session_id=session_id)

    def gen():
        import re
        parts = re.split(r"(\\.|\\?|!|\\n)", full)
        buf = ""
        for p in parts:
            buf += p
            if len(buf) > 120:
                yield f"data: {buf.strip()}\\n\\n"
                buf = ""
        if buf:
            yield f"data: {buf.strip()}\\n\\n"

    return Response(gen(), content_type="text/event-stream")


# Generate text summaries from raw input
@csrf.exempt
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


# Extract keywords from provided text
@csrf.exempt
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


# Return per-user conversation history for frontend sidebar
@csrf.exempt
@app.route("/api/history")
def api_history():
    if "user_id" not in session:
        return jsonify([])

    try:
        history = db_load_conversation(session["user_id"])
        return jsonify(history)
    except Exception:
        logger.exception("Failed to load conversation history for user")
        return jsonify([])


# List all chat sessions for the logged-in user
@csrf.exempt
@app.route("/api/sessions")
def api_sessions():
    if "user_id" not in session:
        return jsonify([])
    return jsonify(list_sessions(session["user_id"]))


# Load messages for a specific chat session
@csrf.exempt
@app.route("/api/session/<sid>")
def api_session(sid):
    if "user_id" not in session:
        return jsonify([])
    return jsonify(load_session_messages(session["user_id"], sid))


# Accept and store uploaded files securely
@csrf.exempt
@limiter.limit("10 per minute")
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


# Extract text from uploaded files and cache results
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


# Generate explanation for uploaded documents
@csrf.exempt
@limiter.limit("10 per minute")
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


# Serve uploaded files directly
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon'
    )


# Disable browser caching for static assets
@app.after_request
def add_no_cache_headers(response):
    if request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# Start Flask development server
if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", 5000))
    logger.info("Starting app on %s:%d", host, port)
    app.run(host=host, port=port)
