from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Protocol

from tkinter import filedialog, messagebox


class FileDialogs(Protocol):
    def ask_open_pdf(self, parent) -> Path | None: ...

    def ask_save_pdf(self, parent) -> Path | None: ...

    def ask_image(self, parent) -> Path | None: ...


class MessageService(Protocol):
    def info(self, title: str, message: str) -> None: ...

    def error(self, title: str, message: str) -> None: ...


class BrowserService(Protocol):
    def open(self, url: str) -> bool: ...


class DefaultFileDialogs:
    def ask_open_pdf(self, parent) -> Path | None:
        filename = filedialog.askopenfilename(
            title="Open PDF", filetypes=[("PDF files", "*.pdf")], parent=parent
        )
        return Path(filename) if filename else None

    def ask_save_pdf(self, parent) -> Path | None:
        filename = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            title="Save PDF As",
            parent=parent,
        )
        return Path(filename) if filename else None

    def ask_image(self, parent) -> Path | None:
        filename = filedialog.askopenfilename(
            title="Select signature image",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.bmp"),
                ("All files", "*.*"),
            ],
            parent=parent,
        )
        return Path(filename) if filename else None


class DefaultMessageService:
    def info(self, title: str, message: str) -> None:  # pragma: no cover - UI side effect
        messagebox.showinfo(title, message)

    def error(self, title: str, message: str) -> None:  # pragma: no cover - UI side effect
        messagebox.showerror(title, message)


class DefaultBrowserService:
    def open(self, url: str) -> bool:  # pragma: no cover - system side effect
        try:
            return webbrowser.open_new_tab(url)
        except webbrowser.Error:
            return False

