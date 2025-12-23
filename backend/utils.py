# backend/utils.py

import os
from typing import List, Dict, Any, Optional

from model_wrapper import get_wrapper
from ocr import pdf_to_text_via_ocr, image_file_to_text


# Initialize the shared model wrapper instance
_model = get_wrapper()


# Split long text into manageable chunks for safe model processing
def _chunk_text(text: str, max_chars: int = 3800) -> List[str]:
    if not text:
        return []

    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    chunks: List[str] = []
    start = 0
    length = len(text)

    while start < length:
        end = min(start + max_chars, length)

        if end < length:
            slice_ = text[start:end]
            last_nl = slice_.rfind("\n")
            last_period = slice_.rfind(". ")
            cut = max(last_nl, last_period)

            if cut > int(max_chars * 0.5):
                end = start + cut + 1

        chunks.append(text[start:end].strip())
        start = end

    return chunks


# Extract readable text from a PDF file with OCR fallback
def extract_text_from_pdf(path: str, use_ocr: bool = True) -> str:
    text = ""

    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(path)
        for page in reader.pages:
            try:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text += page_text + "\n"
            except Exception:
                continue
    except Exception:
        text = ""

    if not text.strip() and use_ocr:
        try:
            text = pdf_to_text_via_ocr(path, dpi=200)
        except Exception:
            text = ""

    if not text.strip():
        return (
            "(error) Could not extract text from PDF. "
            "This may be a scanned document or OCR/Poppler is not configured."
        )

    return text.strip()


# Extract text from Microsoft Word documents
def extract_text_from_docx(path: str) -> str:
    try:
        import docx
        doc = docx.Document(path)
        return "\n".join(p.text for p in doc.paragraphs).strip()
    except Exception:
        return ""


# Read plain text files safely with UTF-8 fallback
def extract_text_from_txt(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    except Exception:
        return ""


# Extract a short preview of CSV or Excel files
def extract_text_from_csv_or_excel(path: str) -> str:
    try:
        import pandas as pd
        ext = os.path.splitext(path)[1].lower()
        if ext == ".csv":
            df = pd.read_csv(path)
        else:
            df = pd.read_excel(path)
        return df.head(20).to_string(index=False)
    except Exception:
        return ""


# Perform OCR on an image file and return extracted text
def extract_text_from_image(path: str) -> str:
    try:
        text = image_file_to_text(path) or ""
        if not text:
            return "(error) Could not extract text from image."
        return text
    except Exception:
        return "(error) Image OCR failed."


# Summarize text using the model wrapper with safe fallback
def summarize_text(text: str, bullets: int = 3) -> str:
    if not text or not text.strip():
        return "(info) No text to summarize."

    try:
        return _model.summarize(text, bullets=bullets)
    except Exception as e:
        return f"(error) Summarization failed: {e}"


# Extract keywords from text using the model wrapper
def extract_keywords(text: str, top_k: int = 8) -> List[str]:
    if not text or not text.strip():
        return []

    try:
        return _model.keywords(text, top_k=top_k)
    except Exception:
        return []


# Explain a PDF by summarizing chunks and synthesizing a final explanation
def explain_pdf_text_only(
    path: str,
    bullets: int = 4,
    chunk_max_chars: int = 3800
) -> str:
    text = extract_text_from_pdf(path, use_ocr=True)
    if not text or text.startswith("(error)"):
        return text

    chunks = _chunk_text(text, max_chars=chunk_max_chars)
    partials: List[str] = []

    for i, chunk in enumerate(chunks, start=1):
        try:
            summary = _model.summarize(chunk, bullets=2)
            partials.append(f"Part {i} summary:\n{summary}")
        except Exception as e:
            partials.append(f"Part {i} summary failed: {e}")

    synth_source = "\n\n".join(partials)

    try:
        return _model.explain_pdf_text(synth_source, bullets=bullets)
    except Exception as e:
        return f"(error) Final explanation failed: {e}"


# Backward-compatible PDF explanation helper returning partials and final output
def explain_pdf(
    path: Optional[str] = None,
    text: Optional[str] = None,
    bullets: int = 4,
    chunk_max_chars: int = 3800
) -> Dict[str, Any]:
    if text is None:
        if not path:
            return {
                "partials": [],
                "final": "(error) No PDF path or text provided."
            }
        text = extract_text_from_pdf(path, use_ocr=True)

    if not text or text.startswith("(error)"):
        return {"partials": [], "final": text}

    chunks = _chunk_text(text, max_chars=chunk_max_chars)
    partials: List[Dict[str, str]] = []

    for i, chunk in enumerate(chunks, start=1):
        try:
            summary = _model.summarize(chunk, bullets=2)
            partials.append({"part": i, "summary": summary})
        except Exception as e:
            partials.append({"part": i, "summary": f"(error) {e}"})

    synth_source = "\n\n".join(
        f"Part {p['part']} summary:\n{p['summary']}"
        for p in partials
    )

    try:
        final = _model.explain_pdf_text(synth_source, bullets=bullets)
    except Exception as e:
        final = f"(error) Explanation synthesis failed: {e}"

    return {"partials": partials, "final": final}
