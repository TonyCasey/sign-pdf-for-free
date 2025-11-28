from __future__ import annotations

from typing import Tuple

import pymupdf as fitz  # PyMuPDF


def clamp_rect(rect: fitz.Rect, bounds: fitz.Rect) -> fitz.Rect:
    """Return a rectangle confined within bounds."""
    clamped = fitz.Rect(rect)
    dx = max(0, clamped.x1 - bounds.x1)
    dy = max(0, clamped.y1 - bounds.y1)
    clamped.x0 -= dx
    clamped.x1 -= dx
    clamped.y0 -= dy
    clamped.y1 -= dy

    if clamped.x0 < bounds.x0:
        clamped.x1 += bounds.x0 - clamped.x0
        clamped.x0 = bounds.x0
    if clamped.y0 < bounds.y0:
        clamped.y1 += bounds.y0 - clamped.y0
        clamped.y0 = bounds.y0
    return clamped


def canvas_to_pdf(
    x: float, y: float, page_rect: fitz.Rect, page_scale: Tuple[float, float]
) -> tuple[float, float]:
    return (
        x * page_scale[0] + page_rect.x0,
        y * page_scale[1] + page_rect.y0,
    )


def pdf_rect_to_canvas_rect(
    rect: fitz.Rect, page_rect: fitz.Rect, page_scale: Tuple[float, float]
) -> tuple[float, float, float, float]:
    x0 = (rect.x0 - page_rect.x0) / page_scale[0]
    y0 = (rect.y0 - page_rect.y0) / page_scale[1]
    x1 = (rect.x1 - page_rect.x0) / page_scale[0]
    y1 = (rect.y1 - page_rect.y0) / page_scale[1]
    return x0, y0, x1, y1


def new_signature_rect(
    canvas_x: float,
    canvas_y: float,
    page_rect: fitz.Rect,
    page_scale: Tuple[float, float],
    image_size: Tuple[int, int],
    max_width_points: float,
) -> fitz.Rect:
    width = max(10.0, min(max_width_points, page_rect.width))
    aspect = image_size[1] / image_size[0] if image_size[0] else 1.0
    height = width * aspect

    x_pdf, y_pdf = canvas_to_pdf(canvas_x, canvas_y, page_rect, page_scale)
    rect = fitz.Rect(x_pdf, y_pdf, x_pdf + width, y_pdf + height)
    return clamp_rect(rect, page_rect)
