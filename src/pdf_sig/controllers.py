from __future__ import annotations

from pathlib import Path
from typing import Optional

import pymupdf as fitz  # PyMuPDF

from .config import DEFAULT_MAX_SIGNATURE_WIDTH
from .layout import clamp_rect, new_signature_rect, pdf_rect_to_canvas_rect


class DocumentController:
    def __init__(self, pdf_opener=fitz.open) -> None:
        self._open_pdf = pdf_opener
        self.doc: Optional[fitz.Document] = None
        self.current_file: Optional[Path] = None
        self.page_index: int = 0

    @property
    def page_count(self) -> int:
        return len(self.doc) if self.doc else 0

    def open(self, path: Path) -> fitz.Document:
        doc = self._open_pdf(path)
        self.doc = doc
        self.current_file = Path(path)
        self.page_index = 0
        return doc

    def reload(self, path: Path) -> Optional[fitz.Document]:
        try:
            return self.open(path)
        except RuntimeError:
            return None

    def close(self) -> None:
        if self.doc:
            self.doc.close()
        self.doc = None
        self.current_file = None
        self.page_index = 0

    def load_page(self) -> Optional[fitz.Page]:
        if not self.doc:
            return None
        return self.doc.load_page(self.page_index)

    def next_page(self) -> None:
        if self.doc and self.page_index < self.page_count - 1:
            self.page_index += 1

    def prev_page(self) -> None:
        if self.doc and self.page_index > 0:
            self.page_index -= 1

    def clamp_page_index(self) -> None:
        if not self.doc:
            self.page_index = 0
            return
        self.page_index = min(self.page_index, self.page_count - 1)


class SignatureController:
    def __init__(self, max_width_points: float = DEFAULT_MAX_SIGNATURE_WIDTH) -> None:
        self.max_width_points = max_width_points
        self.image_path: Optional[Path] = None
        self.rect: Optional[fitz.Rect] = None
        self.page_index: Optional[int] = None

    def reset(self) -> None:
        self.image_path = None
        self.rect = None
        self.page_index = None

    def set_image(self, image_path: Path) -> None:
        self.image_path = image_path
        self.rect = None
        self.page_index = None

    def place_on_page(
        self,
        canvas_x: float,
        canvas_y: float,
        page_index: int,
        page_rect: fitz.Rect,
        page_scale: tuple[float, float],
        image_size: tuple[int, int],
    ) -> fitz.Rect:
        rect = new_signature_rect(
            canvas_x,
            canvas_y,
            page_rect,
            page_scale,
            image_size,
            self.max_width_points,
        )
        self.rect = rect
        self.page_index = page_index
        return rect

    def move_to(
        self,
        canvas_x: float,
        canvas_y: float,
        page_rect: fitz.Rect,
        page_scale: tuple[float, float],
    ) -> Optional[fitz.Rect]:
        if not self.rect:
            return None
        width = self.rect.width
        height = self.rect.height
        x_pdf = canvas_x * page_scale[0] + page_rect.x0
        y_pdf = canvas_y * page_scale[1] + page_rect.y0
        rect = fitz.Rect(x_pdf, y_pdf, x_pdf + width, y_pdf + height)
        self.rect = clamp_rect(rect, page_rect)
        return self.rect

    def resize(
        self,
        handle: str,
        pdf_x: float,
        pdf_y: float,
        page_rect: fitz.Rect,
        min_width: float = 20,
        min_height: float = 20,
    ) -> Optional[fitz.Rect]:
        if not self.rect:
            return None
        rect = fitz.Rect(self.rect)
        if handle == "n":
            rect.y0 = min(pdf_y, rect.y1 - min_height)
        elif handle == "s":
            rect.y1 = max(pdf_y, rect.y0 + min_height)
        elif handle == "w":
            rect.x0 = min(pdf_x, rect.x1 - min_width)
        elif handle == "e":
            rect.x1 = max(pdf_x, rect.x0 + min_width)
        self.rect = clamp_rect(rect, page_rect)
        return self.rect

    def point_in_signature(
        self, canvas_x: float, canvas_y: float, page_rect, page_scale
    ) -> bool:
        if not self.rect:
            return False
        x0, y0, x1, y1 = pdf_rect_to_canvas_rect(self.rect, page_rect, page_scale)
        return x0 <= canvas_x <= x1 and y0 <= canvas_y <= y1
