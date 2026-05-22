import re
from io import BytesIO
from typing import Optional, Tuple

import fitz  # PyMuPDF

# Standard VIN: 17 alphanumeric chars, excluding I, O, Q
_VIN_RE = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b")

# Carfax-specific markers — if none found we treat as non-Carfax
_CARFAX_MARKERS = ["carfax", "vehicle history report", "vehicle identification number"]


def parse_pdf(pdf_bytes: bytes) -> Tuple[Optional[str], str, bool]:
    """
    Parse a PDF from raw bytes.

    Returns:
        vin         – 17-char VIN or None
        raw_text    – full extracted text
        is_carfax   – True if document appears to be a Carfax report
    """
    try:
        doc = fitz.open(stream=BytesIO(pdf_bytes), filetype="pdf")
    except Exception as exc:
        raise ValueError(f"Cannot open PDF: {exc}") from exc

    pages_text: list[str] = []
    for page in doc:
        pages_text.append(page.get_text("text"))
    doc.close()

    raw_text = "\n".join(pages_text)
    lower_text = raw_text.lower()

    is_carfax = any(marker in lower_text for marker in _CARFAX_MARKERS)

    vin: Optional[str] = None
    matches = _VIN_RE.findall(raw_text)
    if matches:
        # Pick the most frequent VIN (Carfax repeats it many times)
        vin = max(set(matches), key=matches.count)

    return vin, raw_text, is_carfax
