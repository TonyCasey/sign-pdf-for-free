from __future__ import annotations

from pathlib import Path

import fitz

from pdf_sig.controllers import DocumentController, SignatureController


def test_signature_controller_place_and_move():
    controller = SignatureController(max_width_points=50)
    page_rect = fitz.Rect(0, 0, 200, 200)
    page_scale = (1.0, 1.0)

    controller.place_on_page(10, 20, 0, page_rect, page_scale, (100, 50))
    assert controller.page_index == 0
    assert controller.rect.width == 50
    assert controller.rect.height == 25

    controller.move_to(100, 100, page_rect, page_scale)
    assert controller.rect.x0 == 100
    assert controller.rect.y0 == 100


def test_signature_controller_resize_clamps_min_size():
    controller = SignatureController(max_width_points=80)
    page_rect = fitz.Rect(0, 0, 200, 200)
    controller.rect = fitz.Rect(50, 50, 100, 100)

    controller.resize("w", 10, 60, page_rect, min_width=30)

    assert controller.rect.width >= 30
    assert controller.rect.x0 == 10


class DummyPage:
    def __init__(self):
        self.rect = fitz.Rect(0, 0, 100, 100)


class DummyDoc:
    def __init__(self, pages=2):
        self._pages = [DummyPage() for _ in range(pages)]

    def __len__(self):
        return len(self._pages)

    def load_page(self, idx: int):
        return self._pages[idx]

    def close(self):
        pass


def test_document_controller_navigation_and_reload():
    opener_calls = []

    def opener(path):
        opener_calls.append(path)
        return DummyDoc()

    controller = DocumentController(pdf_opener=opener)
    doc = controller.open(Path("dummy.pdf"))

    assert controller.page_count == 2
    assert controller.page_index == 0
    assert isinstance(doc.load_page(0), DummyPage)

    controller.next_page()
    assert controller.page_index == 1
    controller.next_page()  # should clamp at end
    assert controller.page_index == 1

    controller.prev_page()
    assert controller.page_index == 0
    controller.prev_page()
    assert controller.page_index == 0

    controller.clamp_page_index()
    assert controller.page_index == 0

    controller.close()
    assert controller.doc is None
    controller.clamp_page_index()
    assert controller.page_index == 0

    # reload should succeed and update doc
    reloaded = controller.reload(Path("dummy.pdf"))
    assert reloaded is not None
    assert opener_calls[-1] == Path("dummy.pdf")

    # simulate reload failure
    def bad_opener(_):
        raise RuntimeError("fail")

    controller_bad = DocumentController(pdf_opener=bad_opener)
    assert controller_bad.reload(Path("x.pdf")) is None
