"""
backend/utils.py

Purpose:
- Text extraction utilities (PDF, DOCX, TXT, CSV/XLSX, Images)
- OCR fallback for scanned PDFs and images
- High-level helpers for summarize, explain, keywords

This file is fully coordinated with:
- app.py
- model_wrapper.py
- ocr.py
"""

import os
from typing import List, Dict, Any, Optional

from model_wrapper import get_wrapper
from ocr import pdf_to_text_via_ocr, image_file_to_text

# Initialize model wrapper (safe even if model unavailable)
_model = get_wrapper()


# --------------------------------------------------
# Internal helpers
# --------------------------------------------------

def _chunk_text(text: str, max_chars: int = 3800) -> List[str]:
    """
    Split long text into reasonably coherent chunks so the model
    can process them safely.
    """
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


# --------------------------------------------------
# Text extraction
# --------------------------------------------------

def extract_text_from_pdf(path: str, use_ocr: bool = True) -> str:
    """
    Extract text from PDF:
    1) Try PyPDF2 (fast, text-based PDFs)
    2) Fallback to OCR for scanned PDFs
    """
    text = ""

    # Attempt PyPDF2 first
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

    # OCR fallback
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


def extract_text_from_docx(path: str) -> str:
    """Extract text from DOCX using python-docx."""
    try:
        import docx
        doc = docx.Document(path)
        return "\n".join(p.text for p in doc.paragraphs).strip()
    except Exception:
        return ""


def extract_text_from_txt(path: str) -> str:
    """Read plain text files safely."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    except Exception:
        return ""


def extract_text_from_csv_or_excel(path: str) -> str:
    """Read CSV/XLSX into a short preview string."""
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


def extract_text_from_image(path: str) -> str:
    """OCR for images using Tesseract."""
    try:
        text = image_file_to_text(path) or ""
        if not text:
            return "(error) Could not extract text from image."
        return text
    except Exception:
        return "(error) Image OCR failed."


# --------------------------------------------------
# High-level helpers used by app.py
# --------------------------------------------------

def summarize_text(text: str, bullets: int = 3) -> str:
    """
    Summarize any text using the model wrapper.
    Safe fallback if model unavailable.
    """
    if not text or not text.strip():
        return "(info) No text to summarize."

    try:
        return _model.summarize(text, bullets=bullets)
    except Exception as e:
        return f"(error) Summarization failed: {e}"


def extract_keywords(text: str, top_k: int = 8) -> List[str]:
    """
    Extract keywords from text using model wrapper.
    """
    if not text or not text.strip():
        return []

    try:
        return _model.keywords(text, top_k=top_k)
    except Exception:
        return []


def explain_pdf_text_only(
    path: str,
    bullets: int = 4,
    chunk_max_chars: int = 3800
) -> str:
    """
    Explain a PDF by:
    - Extracting text
    - Chunking
    - Summarizing chunks
    - Synthesizing final explanation
    """
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


def explain_pdf(
    path: Optional[str] = None,
    text: Optional[str] = None,
    bullets: int = 4,
    chunk_max_chars: int = 3800
) -> Dict[str, Any]:
    """
    Backward-compatible helper returning:
    {
      "partials": [...],
      "final": "..."
    }
    """
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
