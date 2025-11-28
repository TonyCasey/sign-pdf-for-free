from __future__ import annotations

import fitz

from pdf_sig.layout import clamp_rect, canvas_to_pdf, new_signature_rect, pdf_rect_to_canvas_rect


def test_clamp_rect_keeps_rect_inside_bounds():
    bounds = fitz.Rect(0, 0, 100, 100)
    rect = fitz.Rect(80, 80, 140, 140)

    clamped = clamp_rect(rect, bounds)

    assert clamped.x1 <= bounds.x1
    assert clamped.y1 <= bounds.y1
    assert clamped.x0 >= bounds.x0
    assert clamped.y0 >= bounds.y0


def test_canvas_to_pdf_and_back_round_trip():
    page_rect = fitz.Rect(0, 0, 200, 100)
    scale = (2.0, 2.0)
    x_pdf, y_pdf = canvas_to_pdf(10, 5, page_rect, scale)
    x0, y0, x1, y1 = pdf_rect_to_canvas_rect(
        fitz.Rect(x_pdf, y_pdf, x_pdf + 20, y_pdf + 10), page_rect, scale
    )

    assert (x_pdf, y_pdf) == (20, 10)
    assert (x0, y0) == (10, 5)
    assert (x1, y1) == (20, 10)


def test_new_signature_rect_respects_max_width_and_aspect():
    page_rect = fitz.Rect(0, 0, 300, 300)
    page_scale = (1.0, 1.0)
    image_size = (100, 50)  # aspect 0.5

    rect = new_signature_rect(10, 20, page_rect, page_scale, image_size, 80)

    assert rect.width == 80
    assert rect.height == 40  # aspect applied
    assert rect.x0 >= page_rect.x0
    assert rect.y0 >= page_rect.y0


def test_clamp_rect_handles_top_left_overflow():
    bounds = fitz.Rect(10, 10, 60, 60)
    rect = fitz.Rect(-20, -5, 30, 30)

    clamped = clamp_rect(rect, bounds)

    assert clamped.x0 == bounds.x0
    assert clamped.y0 == bounds.y0
