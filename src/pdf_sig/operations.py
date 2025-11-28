from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import pymupdf as fitz  # PyMuPDF

from .config import DEFAULT_INSERT_RECT


class PDFOperationError(RuntimeError):
    """Raised when a low-level PDF manipulation fails."""


def fill_form_fields(doc: fitz.Document, values: Dict[str, str]) -> List[str]:
    """Fill AcroForm fields and return the names that were updated."""
    changed: List[str] = []
    if not values:
        return changed

    for page_index in range(len(doc)):
        page = doc.load_page(page_index)
        widgets = page.widgets() or []
        for widget in widgets:
            name = widget.field_name
            if name and name in values:
                widget.field_value = values[name]
                widget.update()
                changed.append(name)
    return changed


def insert_image(
    doc: fitz.Document,
    image_path: Path,
    page_index: int,
    rect: Optional[fitz.Rect] = None,
) -> fitz.Rect:
    """Insert an image on the requested page and return the final rectangle."""
    if not image_path.exists():
        raise PDFOperationError(f"Image path {image_path} does not exist.")

    try:
        page = doc.load_page(page_index)
    except IndexError as exc:
        raise PDFOperationError(
            f"Page {page_index} is out of range for document with {len(doc)} page(s)."
        ) from exc

    target_rect = rect or DEFAULT_INSERT_RECT
    page.insert_image(
        target_rect,
        filename=str(image_path),
        keep_proportion=True,
        overlay=True,
    )
    return target_rect
