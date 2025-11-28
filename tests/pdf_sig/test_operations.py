from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import fitz  # PyMuPDF
import pytest
from PIL import Image

from pdf_sig.operations import PDFOperationError, fill_form_fields, insert_image


class DummyWidget:
    def __init__(self, name: str | None):
        self.field_name = name
        self.field_value: str | None = None
        self.updated = False

    def update(self) -> None:
        self.updated = True


class DummyPage:
    def __init__(self, widgets: list[DummyWidget]):
        self._widgets = widgets

    def widgets(self) -> list[DummyWidget]:
        return list(self._widgets)


class RecordingPage:
    def __init__(self):
        self.calls: list[dict] = []

    def insert_image(self, rect, filename, keep_proportion=True, overlay=True):
        self.calls.append(
            {
                "rect": rect,
                "filename": filename,
                "keep_proportion": keep_proportion,
                "overlay": overlay,
            }
        )


class DummyDoc:
    def __init__(self, pages):
        self._pages = pages

    def __len__(self) -> int:  # pragma: no cover - simple forwarder
        return len(self._pages)

    def load_page(self, index: int):
        return self._pages[index]


class OutOfRangeDoc(DummyDoc):
    def load_page(self, index: int):  # type: ignore[override]
        raise IndexError("page out of range")


def test_fill_form_fields_updates_matching_fields():
    widgets = [DummyWidget("name"), DummyWidget("title")]
    doc = DummyDoc([DummyPage(widgets)])

    updated = fill_form_fields(doc, {"name": "Alice"})

    assert updated == ["name"]
    assert widgets[0].field_value == "Alice"
    assert widgets[0].updated is True
    assert widgets[1].field_value is None
    assert widgets[1].updated is False


def test_fill_form_fields_no_values_returns_empty_and_skips_updates():
    widget = DummyWidget("ignored")
    doc = DummyDoc([DummyPage([widget])])

    updated = fill_form_fields(doc, {})

    assert updated == []
    assert widget.field_value is None
    assert widget.updated is False


def test_insert_image_uses_custom_rect_and_returns_it():
    page = RecordingPage()
    doc = DummyDoc([page])
    custom_rect = fitz.Rect(10, 20, 30, 40)

    with TemporaryDirectory() as tmpdir:
        img_path = Path(tmpdir) / "sig.png"
        Image.new("RGB", (8, 8), color="red").save(img_path)

        returned = insert_image(doc, img_path, 0, custom_rect)

    assert returned == custom_rect
    assert len(page.calls) == 1
    call = page.calls[0]
    assert call["rect"] == custom_rect
    assert call["filename"] == str(img_path)
    assert call["keep_proportion"] is True
    assert call["overlay"] is True


def test_insert_image_defaults_rect_when_none_given():
    page = RecordingPage()
    doc = DummyDoc([page])

    with TemporaryDirectory() as tmpdir:
        img_path = Path(tmpdir) / "sig.png"
        Image.new("RGB", (4, 4), color="blue").save(img_path)

        returned = insert_image(doc, img_path, 0)

    assert returned == fitz.Rect(36, 36, 300, 300)
    assert page.calls[0]["rect"] == fitz.Rect(36, 36, 300, 300)


def test_insert_image_raises_for_missing_path():
    doc = DummyDoc([])
    missing = Path("/tmp/does-not-exist.png")

    with pytest.raises(PDFOperationError):
        insert_image(doc, missing, 0)


def test_insert_image_wraps_page_index_errors():
    page = RecordingPage()
    doc = OutOfRangeDoc([page])

    with TemporaryDirectory() as tmpdir:
        img_path = Path(tmpdir) / "sig.png"
        Image.new("RGB", (2, 2), color="green").save(img_path)

        with pytest.raises(PDFOperationError) as excinfo:
            insert_image(doc, img_path, 5)

    assert "out of range" in str(excinfo.value)
