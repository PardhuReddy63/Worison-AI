# backend/model_wrapper.py

import os
import json
import logging
from typing import List, Optional, Any

from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type


# Configure logger for model wrapper operations
logger = logging.getLogger("model_wrapper")
logger.setLevel(logging.INFO)


# Flags and references for GenAI SDK availability
GENAI_AVAILABLE = False
genai = None


# Attempt to import Google GenAI SDK safely
try:
    import google.genai as genai_pkg  # type: ignore
    genai = genai_pkg
    GENAI_AVAILABLE = True
    logger.info("google.genai SDK loaded")
except Exception as e:
    logger.warning("google.genai SDK not available: %s", e)


# Read API key and model name from environment variables
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL_NAME = os.getenv("MODEL_NAME", "models/gemini-2.0-flash-lite").strip()


# Internal reference to the initialized model instance
_MODEL: Optional[Any] = None


# Initialize the Generative AI model if possible
def _init_model():
    global _MODEL
    _MODEL = None

    if not GENAI_AVAILABLE:
        logger.warning("GenAI SDK missing – model disabled")
        return

    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set – model disabled")
        return

    try:
        if hasattr(genai, "configure"):
            genai.configure(api_key=GEMINI_API_KEY)
    except Exception:
        pass

    try:
        if hasattr(genai, "GenerativeModel"):
            _MODEL = genai.GenerativeModel(MODEL_NAME)
            logger.info("Initialized GenerativeModel: %s", MODEL_NAME)
            return
    except Exception as e:
        logger.exception("Failed to initialize model: %s", e)

    logger.error("Model initialization failed completely")


# Extract readable text content from different response formats
def _extract_text(resp) -> Optional[str]:
    if resp is None:
        return None

    try:
        if hasattr(resp, "text") and resp.text:
            return str(resp.text).strip()
    except Exception:
        pass

    try:
        candidates = getattr(resp, "candidates", None)
        if candidates:
            for c in candidates:
                content = getattr(c, "content", None)
                if content:
                    parts = getattr(content, "parts", [])
                    texts = [getattr(p, "text", "") for p in parts if getattr(p, "text", "")]
                    if texts:
                        return " ".join(texts).strip()
    except Exception:
        pass

    try:
        if isinstance(resp, dict):
            for k in ("text", "output", "result"):
                if resp.get(k):
                    return str(resp[k]).strip()
    except Exception:
        pass

    try:
        s = str(resp).strip()
        return s if s else None
    except Exception:
        return None


# Split long text into manageable chunks for model input
def _chunk_text(text: str, max_chars: int = 3800) -> List[str]:
    if not text:
        return []

    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            slice_ = text[start:end]
            cut = max(slice_.rfind("\n"), slice_.rfind(". "))
            if cut > max_chars * 0.5:
                end = start + cut + 1
        chunks.append(text[start:end].strip())
        start = end
    return chunks


# Build generation configuration for text generation
def _gen_config(max_tokens=512, temperature=0.18, top_p=0.9):
    try:
        if GENAI_AVAILABLE and hasattr(genai, "types"):
            return genai.types.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
            )
    except Exception:
        pass
    return None


# Call the model with retry logic to handle transient failures
@retry(
    wait=wait_exponential(min=1, max=8),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(Exception),
)
def _call_model(prompt, gen_cfg):
    if gen_cfg is not None:
        return _MODEL.generate_content(prompt, generation_config=gen_cfg)
    return _MODEL.generate_content(prompt)


# Generate text output from the model with safety checks
def _generate(prompt, max_tokens=512, temperature=0.18, top_p=0.9) -> str:
    if _MODEL is None:
        return "(fallback) Model not configured."

    try:
        cfg = _gen_config(max_tokens, temperature, top_p)
        resp = _call_model(prompt, cfg)
        text = _extract_text(resp)
        return text or "(info) Empty model response."
    except Exception as e:
        logger.exception("Model call failed: %s", e)
        return f"(error) {e}"


# Public-facing wrapper exposing AI capabilities
class ModelWrapper:
    def __init__(self):
        self.available = _MODEL is not None
        logger.info("ModelWrapper available=%s", self.available)

    # Generate a conversational response using recent history
    def chat_response(self, user_message: str, history: Optional[List[dict]] = None) -> str:
        if not self.available:
            return "(fallback) Model not available."

        history = history or []
        system = (
            "You are WORISON — Wisdom-Oriented Responsive Intelligent Support & Operations Network. "
            "You are a helpful, precise, and reliable AI assistant focused on learning, analysis, and guidance."
        )

        lines = [f"System: {system}"]
        for turn in history[-8:]:
            role = turn.get("role")
            content = turn.get("content") or turn.get("text") or ""
            if not content:
                continue
            label = "Assistant" if role in ("assistant", "bot") else "User"
            lines.append(f"{label}: {content}")
        lines.append(f"User: {user_message}")
        lines.append("Assistant:")

        return _generate("\n".join(lines), max_tokens=600)

    # Summarize long text into concise bullet points
    def summarize(self, text: str, bullets: int = 3) -> str:
        if not self.available:
            return "(fallback) Model not available."
        if not text.strip():
            return "(info) No text provided."

        parts = _chunk_text(text)
        partials = []
        for i, p in enumerate(parts, 1):
            prompt = f"Summarize part {i}/{len(parts)} into {bullets} bullet points:\n\n{p}"
            partials.append(_generate(prompt, max_tokens=220, temperature=0.12))

        synth = (
            "Combine the partial summaries into a final concise summary with "
            f"{bullets} numbered bullet points:\n\n" + "\n\n".join(partials)
        )
        return _generate(synth, max_tokens=300, temperature=0.12)

    # Extract important keywords from text
    def keywords(self, text: str, top_k: int = 8) -> List[str]:
        if not self.available:
            return []

        prompt = (
            f"Extract the top {top_k} keywords. "
            "Return ONLY a JSON array of strings.\n\n" + text
        )
        raw = _generate(prompt, max_tokens=150, temperature=0.0)

        try:
            arr = json.loads(raw)
            if isinstance(arr, list):
                return [str(x).strip() for x in arr][:top_k]
        except Exception:
            pass

        out = []
        for p in raw.replace("\n", ",").split(","):
            p = p.strip(" \"'[]{}")
            if p and p not in out:
                out.append(p)
            if len(out) >= top_k:
                break
        return out

    # Generate vector embeddings for semantic search
    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        if not self.available or not texts:
            return []

        try:
            if hasattr(genai, "embeddings") and hasattr(genai.embeddings, "create"):
                resp = genai.embeddings.create(
                    model=getattr(genai, "EMBEDDING_MODEL", "text-embedding-3-large"),
                    input=texts,
                )
                data = getattr(resp, "data", None) or resp.get("data", [])
                return [list(item["embedding"]) for item in data if "embedding" in item]
        except Exception:
            logger.warning("Embedding generation failed")

        return []

    # Explain extracted PDF text in plain language
    def explain_pdf_text(self, text: str, bullets: int = 4) -> str:
        if not self.available:
            return "(fallback) Model not available."
        if not text.strip():
            return "(info) No text to explain."

        parts = _chunk_text(text)
        partials = []
        for i, p in enumerate(parts, 1):
            prompt = (
                f"Part {i}/{len(parts)}: Explain in plain language "
                "and list 2 takeaways:\n\n" + p
            )
            partials.append(_generate(prompt, max_tokens=300, temperature=0.12))

        synth = (
            "Using the partial explanations, provide:\n"
            "1) Short explanation (3–5 sentences)\n"
            f"2) {bullets} numbered key takeaways\n\n"
            + "\n\n".join(partials)
        )
        return _generate(synth, max_tokens=450, temperature=0.12)

    # Generate a textual description for an image
    def describe_image(self, image_path: str) -> str:
        if not self.available:
            return "(fallback) Model not available."

        try:
            if hasattr(genai, "types") and hasattr(genai.types.Part, "from_image"):
                img = genai.types.Part.from_image(image_path)
                txt = genai.types.Part.from_text("Describe the image clearly.")
                resp = _MODEL.generate_content([txt, img])
                return _extract_text(resp) or "(info) No description."
        except Exception:
            pass

        return _generate(f"Describe the image at path: {image_path}", max_tokens=300)


# Singleton instance for shared model access
_WRAPPER: Optional[ModelWrapper] = None


# Retrieve or create the model wrapper instance
def get_wrapper() -> ModelWrapper:
    global _WRAPPER
    if _WRAPPER is None:
        _init_model()
        _WRAPPER = ModelWrapper()
    return _WRAPPER


# Perform eager initialization to surface startup issues in logs
_init_model()
