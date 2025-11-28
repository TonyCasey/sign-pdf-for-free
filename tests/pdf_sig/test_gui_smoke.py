from __future__ import annotations

import os
import pytest

if not os.environ.get("ENABLE_GUI_TESTS"):
    pytest.skip("GUI smoke test requires ENABLE_GUI_TESTS=1", allow_module_level=True)

tk = pytest.importorskip("tkinter")

from pdf_sig.gui import PDFFormApp


class DummyDialogs:
    def ask_open_pdf(self, parent):
        return None

    def ask_save_pdf(self, parent):
        return None

    def ask_image(self, parent):
        return None


class DummyMessages:
    def __init__(self):
        self.infos = []
        self.errors = []

    def info(self, title: str, message: str) -> None:
        self.infos.append((title, message))

    def error(self, title: str, message: str) -> None:
        self.errors.append((title, message))


class DummyBrowser:
    def __init__(self, succeed: bool = True):
        self.succeed = succeed
        self.urls = []

    def open(self, url: str) -> bool:
        self.urls.append(url)
        return self.succeed


def _can_init_tk() -> bool:
    try:
        root = tk.Tk()
        root.destroy()
        return True
    except tk.TclError:
        return False


@pytest.mark.skipif(not _can_init_tk(), reason="Tk not available in headless env")
def test_gui_constructs_and_disposes_without_mainloop():
    messages = DummyMessages()
    browser = DummyBrowser()
    app = PDFFormApp(
        file_dialogs=DummyDialogs(),
        messages=messages,
        browser=browser,
        pdf_opener=lambda p: None,
    )
    # Exercise a couple of menu callbacks without user interaction.
    app._open_tip_link()
    app._show_about()
    app.update_idletasks()
    app.destroy()

    assert browser.urls  # tip link attempted
    assert app.winfo_exists() is False
