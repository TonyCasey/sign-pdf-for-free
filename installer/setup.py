from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

APP_NAME = "PDF Sig"
PAYLOAD_NAME = "pdf-sig.exe"
DEFAULT_INSTALL_SUBDIR = Path("PDF Sig")


def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative


def default_install_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    return base / "Programs" / DEFAULT_INSTALL_SUBDIR


def choose_install_dir(root: tk.Tk) -> Path | None:
    target = default_install_dir()
    if target.exists():
        return target

    if messagebox.askyesno(
        APP_NAME,
        f"Install {APP_NAME} under\n{target}?",
        icon=messagebox.QUESTION,
    ):
        return target

    selection = filedialog.askdirectory(
        title=f"Choose {APP_NAME} install folder",
        initialdir=str(target.parent),
    )
    if not selection:
        return None
    return Path(selection)


def install_binary(target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    payload = resource_path(f"payload/{PAYLOAD_NAME}")
    destination = target_dir / PAYLOAD_NAME
    shutil.copy2(payload, destination)
    return destination


def main() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        target_dir = choose_install_dir(root)
        if not target_dir:
            return
        exe_path = install_binary(target_dir)
        messagebox.showinfo(
            APP_NAME,
            f"{APP_NAME} installed to:\n{exe_path}\n\n"
            "Add a shortcut manually or pin it from this folder.",
        )
        if messagebox.askyesno(APP_NAME, "Launch PDF Sig now?"):
            os.startfile(exe_path)
    finally:
        root.destroy()


if __name__ == "__main__":
    main()
