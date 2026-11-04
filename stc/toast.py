"""포커스를 뺏지 않는 작은 알림 배지 (복사 완료 / 오류)."""

from __future__ import annotations

import ctypes
import tkinter as tk

from . import theme, winfocus
from .capture import Rect

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

KIND_COLORS = {
    "info": theme.ACCENT,
    "ok": theme.OK,
    "warn": theme.WARN,
    "error": theme.ERR,
}


class Toast:
    def __init__(self, root: tk.Misc) -> None:
        self.root = root
        self.top: tk.Toplevel | None = None
        self._job: str | None = None
        self._fade_job: str | None = None

    def show(
        self,
        text: str,
        *,
        kind: str = "info",
        anchor: Rect | None = None,
        monitor: Rect | None = None,
        duration: int = 1500,
    ) -> None:
        self.close()
        color = KIND_COLORS.get(kind, theme.ACCENT)

        top = tk.Toplevel(self.root)
        top.withdraw()
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        try:
            top.attributes("-alpha", 0.97)
        except tk.TclError:
            pass

        border = tk.Frame(top, bg=color, padx=1, pady=1)
        border.pack()
        body = tk.Frame(border, bg="#15161a", padx=14, pady=9)
        body.pack()
        tk.Label(
            body,
            text="●",
            bg="#15161a",
            fg=color,
            font=theme.ui_font(8),
        ).pack(side="left", padx=(0, 8))
        tk.Label(
            body,
            text=text,
            bg="#15161a",
            fg="#f2f2f2",
            font=theme.ui_font(10),
            justify="left",
            wraplength=420,
        ).pack(side="left")

        top.update_idletasks()
        width = top.winfo_reqwidth()
        height = top.winfo_reqheight()
        x, y = self._position(anchor, monitor, width, height)
        top.geometry(f"+{x}+{y}")
        self._make_non_activating(top)
        top.deiconify()
        self._make_non_activating(top)
        top.lift()

        self.top = top
        if duration > 0:
            self._job = top.after(duration, self._fade_out)

    # ------------------------------------------------------------------ utils

    def _position(
        self, anchor: Rect | None, monitor: Rect | None, width: int, height: int
    ) -> tuple[int, int]:
        if anchor is not None:
            x = anchor.right + 10
            y = anchor.bottom + 10
        else:
            x, y = self.root.winfo_pointerxy()
            x += 18
            y += 20

        if monitor is not None:
            x = max(monitor.left + 8, min(x, monitor.right - width - 8))
            y = max(monitor.top + 8, min(y, monitor.bottom - height - 8))
            return x, y

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        return max(0, min(x, screen_w - width)), max(0, min(y, screen_h - height))

    def _make_non_activating(self, top: tk.Toplevel) -> None:
        """클릭/포커스를 가로채지 않도록 WS_EX_NOACTIVATE 를 붙인다."""
        try:
            hwnd = winfocus.hwnd_of(top)
            if not hwnd:
                return
            user32 = ctypes.windll.user32
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
            )
        except Exception:  # noqa: BLE001
            pass

    def _fade_out(self, step: int = 0) -> None:
        if self.top is None:
            return
        try:
            if step >= 6:
                self.close()
                return
            self.top.attributes("-alpha", max(0.05, 0.97 - step * 0.16))
            self._fade_job = self.top.after(24, lambda: self._fade_out(step + 1))
        except tk.TclError:
            self.top = None

    def close(self) -> None:
        top, self.top = self.top, None
        for job in (self._job, self._fade_job):
            if job and top is not None:
                try:
                    top.after_cancel(job)
                except tk.TclError:
                    pass
        self._job = None
        self._fade_job = None
        if top is not None:
            try:
                top.destroy()
            except tk.TclError:
                pass
