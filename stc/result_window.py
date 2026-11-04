"""OCR 결과를 보여주고 복사/저장할 수 있는 창."""

from __future__ import annotations

import datetime as dt
import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from . import capture, clipboard, theme
from .capture import Rect
from .config import AppConfig
from .ocr import LABELS
from .ocr.types import OcrResult


class ResultWindow:
    def __init__(
        self,
        root: tk.Misc,
        cfg: AppConfig,
        *,
        anchor: Rect | None = None,
        png_path: Path | None = None,
        on_recapture=None,
        on_closed=None,
    ) -> None:
        self.root = root
        self.cfg = cfg
        self.png_path = png_path
        self.on_recapture = on_recapture
        self.on_closed = on_closed
        self.closed = False
        self.result: OcrResult | None = None
        self._base_status = ""
        self._toast_job: str | None = None

        top = tk.Toplevel(root)
        self.top = top
        top.title("코드 추출")
        top.configure(bg=theme.BG)
        top.minsize(480, 240)
        top.protocol("WM_DELETE_WINDOW", self.close)
        top.bind("<Escape>", lambda _e: self.close())
        top.bind("<Control-s>", lambda _e: self.save())
        theme.enable_dark_titlebar(top)

        self._build()
        self._place(anchor)

        top.deiconify()
        top.attributes("-topmost", True)
        top.after(350, lambda: self._safe(lambda: top.attributes("-topmost", False)))
        top.lift()
        top.focus_force()

    # ------------------------------------------------------------------- build

    def _build(self) -> None:
        top = self.top

        header = tk.Frame(top, bg=theme.BG)
        header.pack(fill="x", padx=16, pady=(12, 4))

        title = tk.Label(
            header,
            text="코드 추출",
            bg=theme.BG,
            fg=theme.TEXT,
            font=theme.ui_font(12, "bold"),
        )
        title.pack(side="left")
        self.subtitle = tk.Label(
            header,
            text="",
            bg=theme.BG,
            fg=theme.MUTED,
            font=theme.ui_font(9),
        )
        self.subtitle.pack(side="left", padx=(10, 0), pady=(3, 0))

        close_btn = tk.Button(
            header,
            text="✕",
            command=self.close,
            bg=theme.BG,
            fg=theme.MUTED,
            activebackground=theme.PANEL_ALT,
            activeforeground=theme.TEXT,
            bd=0,
            relief="flat",
            font=theme.ui_font(10),
            padx=8,
            pady=0,
            cursor="hand2",
            highlightthickness=0,
        )
        close_btn.pack(side="right")

        footer = tk.Frame(top, bg=theme.PANEL)
        footer.pack(side="bottom", fill="x")

        self.status = tk.Label(
            footer,
            text="",
            bg=theme.PANEL,
            fg=theme.MUTED,
            font=theme.ui_font(9),
            anchor="w",
        )
        self.status.pack(side="left", padx=16, pady=10)

        buttons = tk.Frame(footer, bg=theme.PANEL)
        buttons.pack(side="right", padx=12, pady=8)
        self.btn_copy = self._button(buttons, "복사", self.copy, primary=True)
        self.btn_save = self._button(buttons, "저장", self.save)
        self.btn_open = self._button(buttons, "원본", self.open_image)
        self.btn_again = self._button(buttons, "다시 캡처", self.recapture)

        body = tk.Frame(top, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=16, pady=(6, 10))

        style = ttk.Style(top)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Dark.Vertical.TScrollbar",
            gripcount=0,
            background=theme.BORDER,
            darkcolor=theme.PANEL,
            lightcolor=theme.BORDER,
            troughcolor=theme.PANEL,
            bordercolor=theme.PANEL,
            arrowcolor=theme.MUTED,
            relief="flat",
            arrowsize=9,
        )
        style.configure(
            "Dark.Horizontal.TScrollbar",
            gripcount=0,
            background=theme.BORDER,
            darkcolor=theme.PANEL,
            lightcolor=theme.BORDER,
            troughcolor=theme.PANEL,
            bordercolor=theme.PANEL,
            arrowcolor=theme.MUTED,
            relief="flat",
            arrowsize=9,
        )
        for name in ("Dark.Vertical.TScrollbar", "Dark.Horizontal.TScrollbar"):
            style.map(
                name,
                background=[("active", theme.MUTED), ("pressed", theme.ACCENT)],
                arrowcolor=[("active", theme.TEXT)],
            )

        self.text = tk.Text(
            body,
            wrap="none",
            font=theme.code_font(10),
            bg=theme.PANEL,
            fg=theme.TEXT,
            insertbackground=theme.TEXT,
            selectbackground=theme.SELECT,
            selectforeground="#ffffff",
            relief="flat",
            bd=0,
            padx=12,
            pady=10,
            highlightthickness=1,
            highlightbackground=theme.BORDER,
            highlightcolor=theme.BORDER,
            undo=True,
            spacing1=1,
            spacing3=1,
        )
        yscroll = ttk.Scrollbar(
            body, orient="vertical", command=self.text.yview, style="Dark.Vertical.TScrollbar"
        )
        xscroll = ttk.Scrollbar(
            body, orient="horizontal", command=self.text.xview, style="Dark.Horizontal.TScrollbar"
        )
        self.text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        self.set_loading()

    def _button(self, parent: tk.Misc, text: str, command, primary: bool = False) -> tk.Button:
        bg = theme.ACCENT if primary else theme.PANEL_ALT
        active = theme.ACCENT_HOVER if primary else theme.BORDER
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg="#ffffff" if primary else theme.TEXT,
            activebackground=active,
            activeforeground="#ffffff" if primary else theme.TEXT,
            disabledforeground="#6f6f6f",
            bd=0,
            relief="flat",
            font=theme.ui_font(9, "bold" if primary else "normal"),
            padx=13,
            pady=6,
            cursor="hand2",
            highlightthickness=0,
        )
        btn.pack(side="left", padx=(6, 0))
        return btn

    # ------------------------------------------------------------------- state

    def _safe(self, fn) -> None:
        if self.closed:
            return
        try:
            fn()
        except tk.TclError:
            pass

    def _set_buttons(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for btn in (self.btn_copy, self.btn_save):
            btn.configure(state=state)

    def set_loading(self) -> None:
        self._set_buttons(False)
        self.btn_open.configure(state="disabled" if not self.png_path else "normal")
        self.subtitle.configure(text="인식 중…", fg=theme.MUTED)
        self.status.configure(text="스크린샷을 텍스트로 변환하는 중입니다")
        self.text.configure(state="normal", fg=theme.MUTED)
        self._replace_text("인식 중…")

    def show_result(self, result: OcrResult, *, copy: bool = True) -> None:
        self.result = result
        self.text.configure(fg=theme.TEXT)
        self._replace_text(result.text or "")
        self._set_buttons(bool(result.text))
        self.btn_open.configure(state="normal" if self.png_path else "disabled")

        backend = LABELS.get(result.backend, result.backend)
        detail = f"{backend} · {result.elapsed:.1f}s · {result.line_count}줄 · {result.char_count:,}자"
        if result.language and result.backend == "winocr":
            detail += f" · {result.language}"
        self.subtitle.configure(text=detail, fg=theme.MUTED)
        self._base_status = "복사할 준비가 되었습니다" if result.text else "텍스트를 찾지 못했습니다"
        if result.warnings:
            self._base_status += "  ⚠ " + result.warnings[0]
        self.status.configure(text=self._base_status, fg=theme.MUTED)

        if result.text and copy and self.cfg.behavior.copy_to_clipboard:
            self.copy(toast=False)
            self._toast("클립보드에 복사됨 ✓", theme.OK)

        self.text.focus_set()
        self.text.see("1.0")

    def show_error(self, message: str) -> None:
        self._set_buttons(False)
        self.text.configure(fg=theme.ERR)
        self._replace_text(message)
        self.subtitle.configure(text="오류", fg=theme.ERR)
        self._base_status = "인식에 실패했습니다"
        self.status.configure(text=self._base_status, fg=theme.ERR)

    # ----------------------------------------------------------------- actions

    def _replace_text(self, value: str) -> None:
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value)

    def _text(self) -> str:
        return self.text.get("1.0", "end-1c")

    def copy(self, toast: bool = True) -> None:
        try:
            value = self.text.get("sel.first", "sel.last")
        except tk.TclError:
            value = self._text()
        if not value:
            return
        if not clipboard.copy_text(value, self.top.winfo_id()):
            try:
                self.top.clipboard_clear()
                self.top.clipboard_append(value)
                self.top.update_idletasks()
            except tk.TclError:
                self._toast("복사 실패", theme.ERR)
                return
        if toast:
            self._toast("복사됨 ✓", theme.OK)

    def save(self) -> None:
        value = self._text()
        if not value:
            return
        self.cfg.output_path.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = filedialog.asksaveasfilename(
            parent=self.top,
            title="코드 저장",
            initialdir=str(self.cfg.output_path),
            initialfile=f"code_{stamp}.txt",
            defaultextension=".txt",
            filetypes=[("텍스트 파일", "*.txt"), ("Python", "*.py"), ("모든 파일", "*.*")],
        )
        if not path:
            return
        try:
            Path(path).write_text(value, encoding="utf-8")
        except OSError as exc:
            self._toast(f"저장 실패: {exc}", theme.ERR)
            return
        self._toast(f"저장됨: {Path(path).name}", theme.OK)

    def open_image(self) -> None:
        if self.png_path and Path(self.png_path).exists():
            os.startfile(str(self.png_path))  # noqa: S606

    def recapture(self) -> None:
        callback = self.on_recapture
        self.close()
        if callback:
            self.root.after(60, callback)

    def _toast(self, message: str, color: str = theme.MUTED) -> None:
        self.status.configure(text=message, fg=color)
        if self._toast_job:
            self._safe(lambda: self.top.after_cancel(self._toast_job))
        self._toast_job = self.top.after(
            1800,
            lambda: self._safe(
                lambda: self.status.configure(text=self._base_status, fg=theme.MUTED)
            ),
        )

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.top.grab_release()
        except tk.TclError:
            pass
        try:
            self.top.destroy()
        except tk.TclError:
            pass
        callback, self.on_closed = self.on_closed, None
        if callback is not None:
            try:
                callback()
            except Exception:  # noqa: BLE001
                pass

    # ---------------------------------------------------------------- geometry

    def _place(self, anchor: Rect | None) -> None:
        top = self.top
        top.update_idletasks()

        lines = 14
        width = 760
        height = 420
        try:
            monitors = capture.monitors() or [capture.virtual_screen()]
        except Exception:  # noqa: BLE001
            monitors = []

        target = None
        if anchor is not None:
            for mon in monitors:
                if mon.intersects(anchor):
                    target = mon
                    break

        if anchor is not None and self.cfg.behavior.popup_near_selection:
            width = max(560, min(980, int(anchor.width * 1.1)))
            height = max(280, min(680, 150 + lines * 22))
            x = anchor.left
            y = anchor.bottom + 14
            if target is not None:
                if y + height > target.bottom:
                    y = anchor.top - height - 14
                if y < target.top:
                    y = target.top + 8
                x = max(target.left + 8, min(x, target.right - width - 8))
            screen_w = top.winfo_screenwidth()
            screen_h = top.winfo_screenheight()
            x = max(0, min(x, screen_w - width))
            y = max(0, min(y, screen_h - height))
        else:
            width = 760
            height = 440
            screen_w = top.winfo_screenwidth()
            screen_h = top.winfo_screenheight()
            x = (screen_w - width) // 2
            y = (screen_h - height) // 3

        top.geometry(f"{width}x{height}{x:+d}{y:+d}")
