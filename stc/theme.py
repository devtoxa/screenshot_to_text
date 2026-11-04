"""UI 색상/폰트."""

from __future__ import annotations

import ctypes
import tkinter as tk
from ctypes import wintypes
from tkinter import font as tkfont

from . import winfocus

BG = "#1e1e1e"
PANEL = "#252526"
PANEL_ALT = "#2d2d30"
BORDER = "#3c3c3c"
TEXT = "#e8e8e8"
MUTED = "#9d9d9d"
ACCENT = "#3b8eea"
ACCENT_HOVER = "#4f9bf0"
ACCENT_DARK = "#1f6feb"
OK = "#3fb950"
WARN = "#d29922"
ERR = "#f85149"
SELECT = "#264f78"

UI_FAMILY = "Segoe UI"
CODE_FAMILY = "Consolas"
HANGUL_UI = "Malgun Gothic"


def ui_font(size: int = 10, weight: str = "normal") -> tkfont.Font:
    return tkfont.Font(family=UI_FAMILY, size=size, weight=weight)


def code_font(size: int = 10) -> tkfont.Font:
    return tkfont.Font(family=CODE_FAMILY, size=size)


def enable_dark_titlebar(window: tk.Misc) -> None:
    """Windows 10/11 타이틀 바를 어둡게 만든다."""
    try:
        hwnd = winfocus.hwnd_of(window)
        if not hwnd:
            return
        value = ctypes.c_int(1)
        dwm = ctypes.windll.dwmapi
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (신/구 빌드)
            if dwm.DwmSetWindowAttribute(
                wintypes.HWND(hwnd), attribute, ctypes.byref(value), ctypes.sizeof(value)
            ) == 0:
                break
    except Exception:  # noqa: BLE001
        pass
