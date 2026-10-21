"""Ekstraksi teks: teks asli PDF dulu (cepat), OCR hanya untuk halaman tanpa teks."""
import io
from dataclasses import dataclass

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

from .config import MIN_CHARS_PER_PAGE, OCR_DPI, OCR_LANG

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".tif", ".tiff")


@dataclass
class Extraction:
    text: str
    page_count: int
    needs_ocr: bool      # (mode native) masih ada halaman yang butuh OCR
    ocr_used: bool       # OCR benar-benar dijalankan


def is_image(filename: str) -> bool:
    return filename.lower().endswith(IMAGE_EXT)


def _ocr_image(img: Image.Image) -> str:
    img = img.convert("L")  # grayscale membantu Tesseract
    return pytesseract.image_to_string(img, lang=OCR_LANG, config="--psm 3")


def extract_native(data: bytes, filename: str) -> Extraction:
    """Tahap CEPAT (antrean fast): hanya teks yang sudah tertanam di PDF."""
    if is_image(filename):
        return Extraction("", 1, needs_ocr=True, ocr_used=False)

    doc = fitz.open(stream=data, filetype="pdf")
    texts, needs_ocr = [], False
    for page in doc:
        t = page.get_text().strip()
        texts.append(t)
        if len(t) < MIN_CHARS_PER_PAGE:
            needs_ocr = True
    return Extraction("\n\n".join(texts), len(doc), needs_ocr=needs_ocr, ocr_used=False)


def extract_with_ocr(data: bytes, filename: str) -> Extraction:
    """Tahap BERAT (antrean ocr): OCR hanya untuk halaman yang teks aslinya kosong."""
    if is_image(filename):
        img = Image.open(io.BytesIO(data))
        pages = getattr(img, "n_frames", 1)
        texts = []
        for i in range(pages):
            img.seek(i)
            texts.append(_ocr_image(img.copy()))
        return Extraction("\n\n".join(texts), pages, needs_ocr=False, ocr_used=True)

    doc = fitz.open(stream=data, filetype="pdf")
    texts, ocr_used = [], False
    for page in doc:
        t = page.get_text().strip()
        if len(t) < MIN_CHARS_PER_PAGE:
            pix = page.get_pixmap(dpi=OCR_DPI)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            t = _ocr_image(img)
            ocr_used = True
        texts.append(t)
    return Extraction("\n\n".join(texts), len(doc), needs_ocr=False, ocr_used=ocr_used)
