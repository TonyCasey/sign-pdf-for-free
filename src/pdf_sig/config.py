from __future__ import annotations

from dataclasses import dataclass

import pymupdf as fitz  # PyMuPDF


APP_NAME = "PDF Sig"
APP_VERSION = "0.1.0"
APP_AUTHOR = "Tony Casey"
APP_DESCRIPTION = (
    "An app for adding signatures to pdf's. "
    "Open a PDF, drop in your signature, save, BOOM!"
)


DEFAULT_INSERT_RECT = fitz.Rect(36, 36, 300, 300)
DEFAULT_MAX_SIGNATURE_WIDTH = 200.0
DEFAULT_CANVAS_BG = "#111111"
DEFAULT_STATUS_BG = "#0f0f0f"
DEFAULT_RENDER_DEBOUNCE_MS = 120


@dataclass(frozen=True)
class AppMetadata:
    name: str = APP_NAME
    version: str = APP_VERSION
    author: str = APP_AUTHOR
    description: str = APP_DESCRIPTION
