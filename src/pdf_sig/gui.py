from __future__ import annotations

import os
import sys
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from typing import Dict, Optional, Tuple

import ctypes
import ctypes.util

import customtkinter as ctk
import pymupdf as fitz  # PyMuPDF
from PIL import Image, ImageTk

# Allow running as a standalone script (PyInstaller entry point) by using
# absolute imports that don't depend on package context.
from pdf_sig.operations import PDFOperationError, insert_image
from pdf_sig.config import (
    APP_AUTHOR,
    APP_DESCRIPTION,
    APP_NAME,
    APP_VERSION,
    DEFAULT_CANVAS_BG,
    DEFAULT_RENDER_DEBOUNCE_MS,
    DEFAULT_STATUS_BG,
)
from pdf_sig.controllers import DocumentController, SignatureController
from pdf_sig.layout import clamp_rect, canvas_to_pdf, pdf_rect_to_canvas_rect
from pdf_sig.services import (
    BrowserService,
    DefaultBrowserService,
    DefaultFileDialogs,
    DefaultMessageService,
    FileDialogs,
    MessageService,
)


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


TIP_URL = "https://www.buymeacoffee.com/tonycasey"
ICON_CANDIDATES = [
    "AppIcon~ios-marketing.png",  # 1024px
    "AppIcon@3x.png",
    "AppIcon@2x.png",
]


def _set_macos_app_name(name: str) -> None:
    """Set the process/app name shown in the macOS menu bar.

    Tk's `appname` changes the Tcl app id, but macOS still shows "Python"
    unless we also rename the NSProcess. Uses the Objective-C runtime via
    ctypes; safe no-op on other platforms or if frameworks are unavailable.
    """

    if sys.platform != "darwin":
        return


def _asset_icon_dir() -> Path:
    """
    Resolve the assets/icon/ios directory both in dev (source tree) and
    in a PyInstaller bundle (sys._MEIPASS).
    """

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parents[2]
    return base / "assets" / "icon" / "ios"


def _load_app_icon() -> Optional[ImageTk.PhotoImage]:
    """Try to load a bundled PNG app icon; return None on failure.

    Icons live under assets/icon/ios/. We avoid shipping an .icns and rely on
    Tk's PNG support. If the assets folder isn't present (e.g., packaged
    differently), this safely no-ops.
    """

    icon_dir = _asset_icon_dir()
    if not icon_dir.exists():
        return None
    for name in ICON_CANDIDATES:
        candidate = icon_dir / name
        if candidate.exists():
            try:
                return ImageTk.PhotoImage(file=str(candidate))
            except Exception:
                continue
    return None
    try:
        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))

        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]

        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]

        # objc_msgSend is variadic; adjust argtypes per call.
        objc.objc_msgSend.restype = ctypes.c_void_p

        ns_process_info = objc.objc_getClass(b"NSProcessInfo")
        process_info_sel = objc.sel_registerName(b"processInfo")
        objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        process_info = objc.objc_msgSend(ns_process_info, process_info_sel)

        ns_string = objc.objc_getClass(b"NSString")
        string_with_utf8_sel = objc.sel_registerName(b"stringWithUTF8String:")
        objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p]
        name_nsstring = objc.objc_msgSend(
            ns_string, string_with_utf8_sel, name.encode("utf-8")
        )

        set_process_name_sel = objc.sel_registerName(b"setProcessName:")
        objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        objc.objc_msgSend(process_info, set_process_name_sel, name_nsstring)
    except Exception:
        # Missing frameworks or type signature mismatch; ignore silently.
        return


class PDFFormApp(ctk.CTk):
    def __init__(
        self,
        file_dialogs: FileDialogs | None = None,
        messages: MessageService | None = None,
        browser: BrowserService | None = None,
        pdf_opener=fitz.open,
    ) -> None:
        _set_macos_app_name(APP_NAME)
        super().__init__()
        self.title(APP_NAME)
        # macOS shows the Tk "appname" in the menu bar/dock; set it so it isn't just "python".
        try:
            self.tk.call("tk", "appname", APP_NAME)
        except tk.TclError:
            pass  # platform without appname support

        # Set window/dock icon when assets are available.
        self._icon_image = _load_app_icon()
        if self._icon_image:
            try:
                self.iconphoto(True, self._icon_image)
            except tk.TclError:
                pass
        self.geometry("900x1200")

        self.file_dialogs = file_dialogs or DefaultFileDialogs()
        self.messages = messages or DefaultMessageService()
        self.browser = browser or DefaultBrowserService()
        self.doc_controller = DocumentController(pdf_opener=pdf_opener)
        self.signature_controller = SignatureController()

        self.page_photo: Optional[ImageTk.PhotoImage] = None
        self.page_scale: Tuple[float, float] = (1.0, 1.0)
        self.page_rect: Optional[fitz.Rect] = None
        self.signature_photo: Optional[ImageTk.PhotoImage] = None
        self.signature_overlay: Optional[int] = None
        self.signature_image_item: Optional[int] = None
        self._about_window: Optional[ctk.CTkToplevel] = None
        self._last_saved: Optional[Path] = None

        self.status_var = tk.StringVar(value="Open a PDF to get started.")
        self.signature_handles: Dict[str, int] = {}
        self.active_handle: Optional[str] = None
        self._is_resizing: bool = False
        self._is_dragging: bool = False
        self._drag_offset: Tuple[float, float] = (0.0, 0.0)

        self._render_job: Optional[str] = None

        self._build_ui()

    # Tk helpers --------------------------------------------------------------
    def winfo_exists(self) -> bool:  # type: ignore[override]
        """Return False instead of raising if the Tk app has already been destroyed."""
        try:
            return bool(super().winfo_exists())
        except tk.TclError:
            return False

    # UI setup -----------------------------------------------------------------
    def _build_ui(self) -> None:
        self._configure_menu_fonts()
        self._build_menu()

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill=tk.X, padx=12, pady=12)
        button_kwargs = {"corner_radius": 8, "height": 36, "width": 150}
        self.open_button = ctk.CTkButton(
            toolbar, text="Open PDF", command=self._open_pdf, **button_kwargs
        )
        self.open_button.pack(side=tk.LEFT, padx=6)
        self.image_button = ctk.CTkButton(
            toolbar,
            text="Insert Image",
            command=self._load_signature,
            state=tk.DISABLED,
            **button_kwargs,
        )
        self.image_button.pack(side=tk.LEFT, padx=6)
        self.save_button = ctk.CTkButton(
            toolbar,
            text="Save PDF",
            command=self._save_pdf,
            state=tk.DISABLED,
            **button_kwargs,
        )
        self.save_button.pack(side=tk.LEFT, padx=6)

        canvas_frame = ctk.CTkFrame(self, corner_radius=12)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        self.canvas = tk.Canvas(
            canvas_frame,
            bg=DEFAULT_CANVAS_BG,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.canvas.bind("<Button-1>", self._handle_canvas_click)
        self.canvas.bind("<Configure>", self._handle_canvas_resize)

        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.pack(fill=tk.X, padx=12, pady=(0, 6))
        nav_button_kwargs = {"height": 34, "width": 90, "corner_radius": 6}
        self.prev_button = ctk.CTkButton(
            nav,
            text="◀ Prev",
            command=self._prev_page,
            state=tk.DISABLED,
            **nav_button_kwargs,
        )
        self.prev_button.pack(side=tk.LEFT)
        self.next_button = ctk.CTkButton(
            nav,
            text="Next ▶",
            command=self._next_page,
            state=tk.DISABLED,
            **nav_button_kwargs,
        )
        self.next_button.pack(side=tk.LEFT, padx=5)
        self.page_label = ctk.CTkLabel(nav, text="No PDF loaded", anchor="w")
        self.page_label.pack(side=tk.LEFT, padx=16)

        status_bar = ctk.CTkFrame(self, fg_color=DEFAULT_STATUS_BG, corner_radius=0)
        status_bar.pack(fill=tk.X)
        ctk.CTkLabel(
            status_bar,
            textvariable=self.status_var,
            anchor="w",
            font=ctk.CTkFont(size=13),
        ).pack(fill=tk.X, padx=10, pady=6)

    def _configure_menu_fonts(self) -> None:
        """Increase Tk's menu font so File/Help entries stay readable on Windows."""
        target_size = 24 if sys.platform.startswith("win") else 12
        try:
            base = tkfont.nametofont("TkMenuFont").copy()
        except tk.TclError:
            try:
                base = tkfont.nametofont("TkDefaultFont").copy()
            except tk.TclError:
                base = tkfont.Font(family="Segoe UI", size=target_size)
        if base.cget("size") < target_size:
            base.configure(size=target_size)
        self._menu_font = base
        try:
            self.option_add("*Menu*Font", self._menu_font)
        except tk.TclError:
            pass

    def _build_menu(self) -> None:
        font = getattr(self, "_menu_font", tkfont.Font(size=12))
        menubar = tk.Menu(self, tearoff=0, font=font)
        item_kwargs = {
            "font": font,
            "bg": "#1e1e1e",
            "fg": "#e0e0e0",
            "activebackground": "#2a2a2a",
            "activeforeground": "#ffffff",
            "tearoff": 0,
        }
        file_menu = tk.Menu(menubar, **item_kwargs)
        file_menu.add_command(label="Open...", command=self._open_pdf, font=font)
        file_menu.add_command(
            label="Save As...",
            command=self._save_pdf,
            state=tk.DISABLED,
            font=font,
        )
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy, font=font)
        menubar.add_cascade(label="File", menu=file_menu, font=font)
        help_menu = tk.Menu(menubar, **item_kwargs)
        help_menu.add_command(label="About", command=self._show_about, font=font)
        menubar.add_cascade(label="Help", menu=help_menu, font=font)
        self.configure(menu=menubar)
        self._file_menu = file_menu
        self._help_menu = help_menu

    # Menu actions -------------------------------------------------------------
    def _open_pdf(self) -> None:
        filename = self.file_dialogs.ask_open_pdf(self)
        if not filename:
            return

        # Close any existing document before opening the new one so we don't immediately
        # discard the freshly opened doc (happened when _close_document ran after open).
        self._close_document()

        try:
            doc = self.doc_controller.open(filename)
        except RuntimeError:
            self.messages.error("Error", "Unable to open that PDF.")
            return
        self._file_menu.entryconfig("Save As...", state=tk.NORMAL)
        self.image_button.configure(state="normal")
        self.save_button.configure(state="normal")
        self.prev_button.configure(
            state="normal" if self.doc_controller.page_count > 1 else "disabled"
        )
        self.next_button.configure(
            state="normal" if self.doc_controller.page_count > 1 else "disabled"
        )
        self.status_var.set("PDF loaded. Use Insert Image to place a signature.")

        self._render_page()

    def _save_pdf(self) -> None:
        if not self.doc_controller.doc or not self.doc_controller.current_file:
            self.messages.info("Nothing to save", "Load a PDF first.")
            return

        filename = self.file_dialogs.ask_save_pdf(self)
        if not filename:
            return

        try:
            doc = self.doc_controller._open_pdf(self.doc_controller.current_file)
            if (
                self.signature_controller.image_path
                and self.signature_controller.rect is not None
            ):
                insert_image(
                    doc,
                    self.signature_controller.image_path,
                    self.signature_controller.page_index or 0,
                    fitz.Rect(self.signature_controller.rect),
                )
            doc.save(filename)
            doc.close()
        except (RuntimeError, PDFOperationError) as exc:
            self.messages.error("Error", f"Could not save PDF:\n{exc}")
            return
        self._show_saved_dialog(Path(filename))
        self._open_pdf_after_save(Path(filename))

    def _open_pdf_after_save(self, filename: Path) -> None:
        doc = self.doc_controller.reload(filename)
        if not doc:
            return
        self._close_document()
        self.doc_controller.clamp_page_index()
        self._file_menu.entryconfig("Save As...", state=tk.NORMAL)
        self.image_button.configure(state="normal")
        self.save_button.configure(state="normal")
        self.prev_button.configure(
            state="normal" if self.doc_controller.page_count > 1 else "disabled"
        )
        self.next_button.configure(
            state="normal" if self.doc_controller.page_count > 1 else "disabled"
        )
        self.status_var.set("PDF saved and reloaded.")
        self._render_page()
        self._last_saved = filename

    def _open_saved_file(self, filename: Path) -> None:
        """
        Open a file in the user's default PDF viewer. Works on macOS, Windows, and Linux.
        """

        try:
            if sys.platform == "darwin":
                os.spawnlp(os.P_NOWAIT, "open", "open", str(filename))
            elif sys.platform.startswith("win"):
                os.startfile(str(filename))  # type: ignore[attr-defined]
            else:
                os.spawnlp(os.P_NOWAIT, "xdg-open", "xdg-open", str(filename))
        except Exception:
            self.messages.error(
                "Unable to open file",
                f"Saved to {filename}, but the file could not be opened automatically.",
            )

    def _show_saved_dialog(self, filename: Path) -> None:
        """
        Present a small dialog after saving with an Open button.
        """

        dialog = ctk.CTkToplevel(self)
        dialog.title("Saved")
        dialog.geometry("360x150")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text=f"Saved updated PDF to\n{filename}",
            justify="center",
            wraplength=320,
        ).pack(pady=(20, 10), padx=16)

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=(0, 16))
        ctk.CTkButton(
            btn_frame,
            text="Open",
            width=100,
            command=lambda: (self._open_saved_file(filename), dialog.destroy()),
        ).pack(side=tk.LEFT, padx=6)
        ctk.CTkButton(
            btn_frame,
            text="Close",
            width=100,
            command=dialog.destroy,
        ).pack(side=tk.LEFT, padx=6)

        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)

    def _close_document(self) -> None:
        self.doc_controller.close()
        self.image_button.configure(state="disabled")
        self.save_button.configure(state="disabled")
        self.prev_button.configure(state="disabled")
        self.next_button.configure(state="disabled")
        self.signature_controller.reset()
        self._remove_signature_overlay()
        self.status_var.set("Open a PDF to get started.")

    # Page controls ------------------------------------------------------------
    def _render_page(self) -> None:
        if self._render_job:
            self.after_cancel(self._render_job)
            self._render_job = None

        if not self.doc_controller.doc:
            self.canvas.delete("all")
            self.page_label.configure(text="No PDF loaded")
            self.canvas.create_text(
                self.canvas.winfo_width() / 2,
                self.canvas.winfo_height() / 2,
                text="Open a PDF to preview it here.",
                fill="#bbbbbb",
                font=("Segoe UI", 16),
            )
            return

        page = self.doc_controller.load_page()
        rect = page.rect

        canvas_width = max(100, self.canvas.winfo_width())
        canvas_height = max(100, self.canvas.winfo_height())
        scale = min(canvas_width / rect.width, canvas_height / rect.height)
        scale = max(scale, 0.25)
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self.page_photo = ImageTk.PhotoImage(image)

        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.page_photo, anchor="nw")
        self.canvas.config(scrollregion=(0, 0, image.width, image.height))
        self.page_label.configure(
            text=f"Page {self.doc_controller.page_index + 1} / {self.doc_controller.page_count}"
        )

        self.page_rect = rect
        self.page_scale = (rect.width / image.width, rect.height / image.height)

        if (
            self.signature_controller.rect
            and self.signature_controller.page_index == self.doc_controller.page_index
            and self.signature_controller.image_path
        ):
            self._draw_signature_overlay()
        else:
            self._remove_signature_overlay()

    def _prev_page(self) -> None:
        self.doc_controller.prev_page()
        self._render_page()

    def _next_page(self) -> None:
        self.doc_controller.next_page()
        self._render_page()

    # Signature helpers --------------------------------------------------------
    def _load_signature(self) -> None:
        if not self.doc_controller.doc:
            self.messages.info("No PDF", "Open a PDF before inserting an image.")
            return
        candidate = self.file_dialogs.ask_image(self)
        if not candidate:
            return
        try:
            with Image.open(candidate) as img:
                img.load()
        except (OSError, ValueError):
            self.messages.error("Error", "Unable to open that image file.")
            return

        self.signature_controller.set_image(candidate)
        self._remove_signature_overlay()
        self.status_var.set(
            f"Loaded {candidate.name}. Click anywhere on the PDF to place it."
        )

    def _handle_canvas_click(self, event: tk.Event) -> None:  # type: ignore[override]
        if not self.doc_controller.doc or not self.page_rect:
            return

        if (
            self.signature_controller.rect
            and self.signature_controller.page_index == self.doc_controller.page_index
            and self.signature_controller.point_in_signature(
                event.x, event.y, self.page_rect, self.page_scale
            )
            and not self._is_resizing
        ):
            self._start_drag(event)
            return

        if not self.signature_controller.image_path or self._is_resizing:
            return
        with Image.open(self.signature_controller.image_path) as image:
            image_size = image.size
        rect = self.signature_controller.place_on_page(
            event.x,
            event.y,
            self.doc_controller.page_index,
            self.page_rect,
            self.page_scale,
            image_size,
        )
        self.status_var.set(
            f"Signature ready on page {self.doc_controller.page_index + 1}. Drag or resize, then click Save PDF."
        )
        self._draw_signature_overlay()

    def _draw_signature_overlay(self) -> None:
        if (
            not self.signature_controller.rect
            or not self.page_rect
            or not self.signature_controller.image_path
            or not self.doc_controller.doc
            or self.signature_controller.page_index != self.doc_controller.page_index
        ):
            self._remove_signature_overlay()
            return

        x0, y0, x1, y1 = pdf_rect_to_canvas_rect(
            self.signature_controller.rect, self.page_rect, self.page_scale
        )

        width = max(1, int(x1 - x0))
        height = max(1, int(y1 - y0))
        try:
            with Image.open(self.signature_controller.image_path) as img:
                img = img.convert("RGBA")
                resized = img.resize((width, height), Image.LANCZOS)
        except (OSError, ValueError):
            resized = None

        if resized:
            self.signature_photo = ImageTk.PhotoImage(resized)
            if self.signature_image_item is None:
                self.signature_image_item = self.canvas.create_image(
                    x0, y0, image=self.signature_photo, anchor="nw"
                )
            else:
                self.canvas.coords(self.signature_image_item, x0, y0)
                self.canvas.itemconfig(self.signature_image_item, image=self.signature_photo)

        if self.signature_overlay is None:
            self.signature_overlay = self.canvas.create_rectangle(
                x0,
                y0,
                x1,
                y1,
                outline="#1f6aa5",
                width=2,
            )
        else:
            self.canvas.coords(self.signature_overlay, x0, y0, x1, y1)

        handle_positions = {
            "n": ((x0 + x1) / 2, y0),
            "s": ((x0 + x1) / 2, y1),
            "w": (x0, (y0 + y1) / 2),
            "e": (x1, (y0 + y1) / 2),
        }
        for key, (cx, cy) in handle_positions.items():
            coords = (cx - 6, cy - 6, cx + 6, cy + 6)
            handle_id = self.signature_handles.get(key)
            if handle_id is None:
                handle_id = self.canvas.create_rectangle(
                    *coords,
                    fill="#1f6aa5",
                    outline="white",
                    width=1,
                )
                self.signature_handles[key] = handle_id
                self.canvas.tag_bind(
                    handle_id,
                    "<ButtonPress-1>",
                    lambda event, corner=key: self._start_resize(corner, event),
                )
            else:
                self.canvas.coords(handle_id, *coords)

    def _remove_signature_overlay(self) -> None:
        if self.signature_overlay:
            self.canvas.delete(self.signature_overlay)
            self.signature_overlay = None
        if self.signature_image_item:
            self.canvas.delete(self.signature_image_item)
            self.signature_image_item = None
        self.signature_photo = None
        for handle_id in self.signature_handles.values():
            self.canvas.delete(handle_id)
        self.signature_handles.clear()
        self.active_handle = None
        self._is_resizing = False
        self._is_dragging = False
        self.canvas.unbind("<B1-Motion>")
        self.canvas.unbind("<ButtonRelease-1>")

    def _start_resize(self, corner: str, event: tk.Event) -> str:
        if not self.signature_controller.rect:
            return "break"
        self.active_handle = corner
        self._is_resizing = True
        self.canvas.bind("<B1-Motion>", self._resize_drag)
        self.canvas.bind("<ButtonRelease-1>", self._end_resize)
        return "break"

    def _resize_drag(self, event: tk.Event) -> None:
        if (
            not self.signature_controller.rect
            or not self.page_rect
            or not self.active_handle
        ):
            return

        pdf_x, pdf_y = canvas_to_pdf(event.x, event.y, self.page_rect, self.page_scale)
        rect = fitz.Rect(self.signature_controller.rect)
        min_width = 20
        min_height = 20

        if self.active_handle == "n":
            rect.y0 = min(pdf_y, rect.y1 - min_height)
        elif self.active_handle == "s":
            rect.y1 = max(pdf_y, rect.y0 + min_height)
        elif self.active_handle == "w":
            rect.x0 = min(pdf_x, rect.x1 - min_width)
        elif self.active_handle == "e":
            rect.x1 = max(pdf_x, rect.x0 + min_width)

        rect = clamp_rect(rect, self.page_rect)
        self.signature_controller.rect = rect
        self._draw_signature_overlay()

    def _end_resize(self, _event: tk.Event) -> None:
        self.canvas.unbind("<B1-Motion>")
        self.canvas.unbind("<ButtonRelease-1>")
        self.active_handle = None
        self._is_resizing = False

    def _start_drag(self, event: tk.Event) -> None:
        if not self.signature_controller.rect:
            return
        x0, y0, x1, y1 = self._signature_canvas_rect()
        if not (x0 <= event.x <= x1 and y0 <= event.y <= y1):
            return
        self._drag_offset = (event.x - x0, event.y - y0)
        self._is_dragging = True
        self.canvas.bind("<B1-Motion>", self._drag_move)
        self.canvas.bind("<ButtonRelease-1>", self._end_drag)

    def _drag_move(self, event: tk.Event) -> None:
        if not self._is_dragging or not self.signature_controller.rect or not self.page_rect:
            return
        width = self.signature_controller.rect.width
        height = self.signature_controller.rect.height
        x_canvas = event.x - self._drag_offset[0]
        y_canvas = event.y - self._drag_offset[1]
        x_pdf, y_pdf = canvas_to_pdf(x_canvas, y_canvas, self.page_rect, self.page_scale)
        rect = fitz.Rect(x_pdf, y_pdf, x_pdf + width, y_pdf + height)
        rect = clamp_rect(rect, self.page_rect)
        self.signature_controller.rect = rect
        self._draw_signature_overlay()

    def _end_drag(self, _event: tk.Event) -> None:
        self.canvas.unbind("<B1-Motion>")
        self.canvas.unbind("<ButtonRelease-1>")
        self._is_dragging = False

    def _signature_canvas_rect(self) -> Tuple[float, float, float, float]:
        if not self.signature_controller.rect or not self.page_rect:
            return (0.0, 0.0, 0.0, 0.0)
        return pdf_rect_to_canvas_rect(
            self.signature_controller.rect, self.page_rect, self.page_scale
        )

    def _point_in_signature(self, x: float, y: float) -> bool:
        x0, y0, x1, y1 = self._signature_canvas_rect()
        return x0 <= x <= x1 and y0 <= y <= y1

    def _handle_canvas_resize(self, _event: tk.Event) -> None:  # type: ignore[override]
        if not self.doc_controller.doc:
            self.canvas.delete("all")
            self.canvas.create_text(
                self.canvas.winfo_width() / 2,
                self.canvas.winfo_height() / 2,
                text="Open a PDF to preview it here.",
                fill="#bbbbbb",
                font=("Segoe UI", 16),
            )
            return
        if self._render_job:
            self.after_cancel(self._render_job)
        self._render_job = self.after(DEFAULT_RENDER_DEBOUNCE_MS, self._render_page)

    # Help menu --------------------------------------------------------------
    def _show_about(self) -> None:
        if self._about_window and self._about_window.winfo_exists():
            self._about_window.lift()
            self._about_window.focus_force()
            return

        about = ctk.CTkToplevel(self)
        about.title("About")
        about.geometry("440x320")
        about.resizable(False, False)
        about.transient(self)
        about.grab_set()
        self._about_window = about

        heading_font = ctk.CTkFont(size=20, weight="bold")
        ctk.CTkLabel(about, text=APP_NAME, font=heading_font).pack(pady=(18, 6))
        ctk.CTkLabel(about, text=f"Version {APP_VERSION}").pack()
        ctk.CTkLabel(about, text=f"Developer: {APP_AUTHOR}").pack(pady=(2, 12))
        ctk.CTkLabel(
            about,
            text=APP_DESCRIPTION,
            wraplength=380,
            justify="center",
        ).pack(padx=16, pady=(0, 16))

        link_frame = ctk.CTkFrame(about, fg_color="transparent")
        link_frame.pack(pady=(0, 14))
        ctk.CTkButton(
            link_frame,
            text="Buy me a coffee",
            width=110,
            command=self._open_tip_link,
        ).pack(side=tk.LEFT)

        def handle_close() -> None:
            self._about_window = None
            about.destroy()

        ctk.CTkButton(about, text="Close", command=handle_close, width=100).pack(
            pady=(4, 16)
        )
        about.protocol("WM_DELETE_WINDOW", handle_close)
        about.bind("<Destroy>", lambda _event: setattr(self, "_about_window", None))

    def _open_tip_link(self) -> None:
        if not TIP_URL:
            self.messages.info("Coming soon", "Tipping link is not set yet.")
            return
        success = self.browser.open(TIP_URL)
        if not success:
            self.messages.error(
                "Unable to open link",
                "Could not launch your browser. Please copy the link manually.",
            )


def main() -> None:
    app = PDFFormApp()
    app.mainloop()


if __name__ == "__main__":
    main()
