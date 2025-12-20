# backend/ocr.py
"""
OCR utilities for AI Learning Assistant

Features:
- PDF OCR using pdf2image + Tesseract
- Image OCR using Pillow + Tesseract
- Windows auto PATH setup for Poppler & Tesseract
- Image preprocessing to improve OCR accuracy
"""

import os
import logging
from typing import Optional

from PIL import Image, ImageFilter, ImageOps
import pytesseract

logger = logging.getLogger("ocr")
logger.setLevel(logging.INFO)

# --------------------------------------------------
# Optional pdf2image import
# --------------------------------------------------
try:
    from pdf2image import convert_from_path, convert_from_bytes
except Exception:
    convert_from_path = None
    convert_from_bytes = None
    logger.warning("pdf2image not available – PDF OCR disabled")


# --------------------------------------------------
# Windows: Auto-detect Poppler
# --------------------------------------------------
def _ensure_poppler_on_path():
    if os.name != "nt":
        return

    possible_paths = [
        r"C:\poppler\Library\bin",
        r"C:\poppler\bin",
        r"C:\Program Files\poppler\bin",
        r"C:\Program Files (x86)\poppler\bin",
    ]

    current_path = os.environ.get("PATH", "")

    for p in possible_paths:
        if os.path.isdir(p) and p not in current_path:
            os.environ["PATH"] += os.pathsep + p
            logger.info("Poppler added to PATH: %s", p)
            return


_ensure_poppler_on_path()


# --------------------------------------------------
# Windows: Auto-detect Tesseract
# --------------------------------------------------
def _ensure_tesseract_on_path():
    if os.name != "nt":
        return

    possible_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]

    for exe in possible_paths:
        if os.path.exists(exe):
            pytesseract.pytesseract.tesseract_cmd = exe
            logger.info("Tesseract detected: %s", exe)
            return


_ensure_tesseract_on_path()


# --------------------------------------------------
# Image preprocessing
# --------------------------------------------------
def preprocess_image(img: Image.Image) -> Image.Image:
    """
    Light preprocessing to improve OCR:
    - grayscale
    - contrast enhancement
    - sharpening
    - binary threshold
    """
    try:
        img = img.convert("L")
        img = ImageOps.autocontrast(img)
        img = img.filter(ImageFilter.SHARPEN)
        img = img.point(lambda x: 0 if x < 140 else 255, "1")
    except Exception as e:
        logger.debug("Image preprocessing failed: %s", e)
        return img

    return img


# --------------------------------------------------
# PDF OCR
# --------------------------------------------------
def pdf_to_text_via_ocr(
    path: str,
    dpi: int = 300,
    first_n_pages: Optional[int] = None,
) -> str:
    """
    Convert a PDF file to text using OCR.

    Returns:
        Extracted text or empty string on failure
    """
    if not (convert_from_path or convert_from_bytes):
        logger.error("pdf2image not installed – cannot OCR PDFs")
        return ""

    images = []

    try:
        if os.path.exists(path) and convert_from_path:
            images = convert_from_path(path, dpi=dpi)
        else:
            with open(path, "rb") as f:
                images = convert_from_bytes(f.read(), dpi=dpi)
    except Exception as e:
        logger.exception("PDF to image conversion failed: %s", e)
        return ""

    if not images:
        return ""

    if first_n_pages:
        images = images[:first_n_pages]

    pages_text = []

    for idx, img in enumerate(images, start=1):
        try:
            img = preprocess_image(img)
            text = pytesseract.image_to_string(img)
            if text.strip():
                pages_text.append(text.strip())
        except Exception as e:
            logger.exception("OCR failed on page %d: %s", idx, e)

    return "\n\n".join(pages_text).strip()


# --------------------------------------------------
# Image OCR
# --------------------------------------------------
def image_file_to_text(path: str) -> str:
    """
    Extract text from an image file using Tesseract.
    """
    try:
        if not getattr(pytesseract.pytesseract, "tesseract_cmd", None):
            logger.error("Tesseract not configured")
            return ""

        img = Image.open(path)
        img = preprocess_image(img)
        return pytesseract.image_to_string(img).strip()

    except Exception as e:
        logger.exception("Image OCR failed: %s", e)
        return ""
