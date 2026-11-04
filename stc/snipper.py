"""화면을 얼려놓고 드래그로 영역을 선택하는 오버레이."""

from __future__ import annotations

import time
import tkinter as tk
from typing import Callable

from PIL import Image, ImageTk

from . import theme, winfocus
from .capture import Rect

MIN_SIZE = 8
HINT = "드래그해서 코드 영역을 선택하세요      Esc / 우클릭: 취소"


class Snipper:
    """모니터마다 dim 처리된 오버레이 창을 띄우고 선택 영역을 돌려준다."""

    def __init__(self, root: tk.Misc, dim: float = 0.55) -> None:
        self.root = root
        self.dim = max(0.0, min(0.85, float(dim)))
        self._windows: list[dict] = []
        self._shot: Image.Image | None = None
        self._origin = Rect(0, 0, 0, 0)
        self._monitors: list[Rect] = []
        self._active = -1
        self._start: tuple[int, int] | None = None
        self._rect: Rect | None = None
        self._on_done: Callable[[Rect | None], None] | None = None
        self._crop_photo: ImageTk.PhotoImage | None = None
        self._last_crop_at = 0.0
        self._finished = True

    @property
    def active(self) -> bool:
        return bool(self._windows)

    def start(
        self,
        shot: Image.Image,
        origin: Rect,
        monitors: list[Rect],
        on_done: Callable[[Rect | None], None],
    ) -> None:
        if self._windows:
            return
        self._shot = shot
        self._origin = origin
        self._monitors = monitors or [origin]
        self._on_done = on_done
        self._finished = False
        self._start = None
        self._rect = None
        self._active = -1
        self._crop_photo = None

        for mon in self._monitors:
            self._create_window(mon)
        self._focus_under_pointer()
        self.root.after(80, self._focus_under_pointer)

    # ---------------------------------------------------------------- windows

    def _create_window(self, mon: Rect) -> None:
        top = tk.Toplevel(self.root)
        top.withdraw()
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        top.geometry(f"{mon.width}x{mon.height}{mon.left:+d}{mon.top:+d}")
        top.configure(bg=theme.BG)

        canvas = tk.Canvas(
            top,
            width=mon.width,
            height=mon.height,
            bd=0,
            highlightthickness=0,
            bg=theme.BG,
            cursor="crosshair",
        )
        canvas.pack(fill="both", expand=True)

        box = (
            mon.left - self._origin.left,
            mon.top - self._origin.top,
            mon.left - self._origin.left + mon.width,
            mon.top - self._origin.top + mon.height,
        )
        slice_img = self._shot.crop(box).convert("RGB")
        if self.dim > 0:
            slice_img = Image.blend(
                slice_img, Image.new("RGB", slice_img.size, (0, 0, 0)), self.dim
            )
        photo = ImageTk.PhotoImage(slice_img)
        canvas.create_image(0, 0, anchor="nw", image=photo)

        hint_bg = canvas.create_rectangle(0, 0, 0, 0, fill="#101010", outline=theme.ACCENT, width=1)
        hint_text = canvas.create_text(
            0,
            0,
            text=HINT,
            fill="#efefef",
            font=(theme.UI_FAMILY, 11),
            anchor="center",
        )
        canvas.coords(hint_text, mon.width // 2, 90)
        bbox = canvas.bbox(hint_text) or (0, 0, 200, 30)
        canvas.coords(hint_bg, bbox[0] - 18, bbox[1] - 12, bbox[2] + 18, bbox[3] + 12)
        canvas.tag_lower(hint_bg, hint_text)

        window = {
            "top": top,
            "canvas": canvas,
            "mon": mon,
            "photo": photo,
            "hint": (hint_bg, hint_text),
            "guides": [],
            "border": None,
            "crop": None,
            "handles": [],
            "label_bg": None,
            "label": None,
        }
        self._windows.append(window)

        canvas.bind("<ButtonPress-1>", lambda e, w=window: self._on_press(e, w))
        canvas.bind("<B1-Motion>", lambda e, w=window: self._on_drag(e, w))
        canvas.bind("<ButtonRelease-1>", lambda e, w=window: self._on_release(e, w))
        canvas.bind("<Motion>", lambda e, w=window: self._on_motion(e, w))
        canvas.bind("<ButtonPress-3>", lambda e: self._cancel())
        top.bind("<Escape>", lambda e: self._cancel())

        top.deiconify()
        top.lift()
        top.update_idletasks()
        top.attributes("-topmost", True)

    def _take_focus(self, window: dict) -> None:
        """오버레이가 확실히 키보드 포커스를 갖도록 한다."""
        top = window["top"]
        try:
            top.lift()
            winfocus.force_foreground(winfocus.hwnd_of(top))
            top.focus_force()
        except tk.TclError:
            pass

    def _focus_under_pointer(self) -> None:
        if not self._windows:
            return
        try:
            px, py = self.root.winfo_pointerxy()
        except tk.TclError:
            return
        for index, window in enumerate(self._windows):
            mon = window["mon"]
            if mon.left <= px < mon.right and mon.top <= py < mon.bottom:
                self._active = index
                self._take_focus(window)
                return

    # ----------------------------------------------------------------- events

    def _local(self, window: dict, event: tk.Event) -> tuple[int, int]:
        mon = window["mon"]
        return int(mon.left + event.x), int(mon.top + event.y)

    def _on_press(self, event: tk.Event, window: dict) -> None:
        self._active = self._windows.index(window)
        for win in self._windows:
            for item in win["hint"]:
                win["canvas"].delete(item)
            win["hint"] = ()
            self._clear_guides(win)
        self._start = self._local(window, event)
        self._rect = None
        window["canvas"].configure(cursor="crosshair")
        self._take_focus(window)

    def _on_drag(self, event: tk.Event, window: dict) -> None:
        if self._start is None:
            return
        mon = window["mon"]
        x, y = self._local(window, event)
        sx, sy = self._start
        left = max(mon.left, min(sx, x))
        top_ = max(mon.top, min(sy, y))
        right = min(mon.right, max(sx, x))
        bottom = min(mon.bottom, max(sy, y))
        rect = Rect(left, top_, max(0, right - left), max(0, bottom - top_))
        self._rect = rect
        self._draw(window, rect, event.x, event.y)

    def _on_release(self, event: tk.Event, window: dict) -> None:
        rect = self._rect
        self._start = None
        if rect is None or rect.width < MIN_SIZE or rect.height < MIN_SIZE:
            self._cancel()
            return
        self._finish(rect)

    def _on_motion(self, event: tk.Event, window: dict) -> None:
        if self._start is not None:
            return
        self._active = self._windows.index(window)
        canvas = window["canvas"]
        self._clear_guides(window)
        guides = [
            canvas.create_line(event.x, 0, event.x, window["mon"].height, fill=theme.ACCENT, dash=(3, 3)),
            canvas.create_line(0, event.y, window["mon"].width, event.y, fill=theme.ACCENT, dash=(3, 3)),
        ]
        window["guides"] = guides

    def _clear_guides(self, window: dict) -> None:
        canvas = window["canvas"]
        for item in window["guides"]:
            canvas.delete(item)
        window["guides"] = []

    # ------------------------------------------------------------------ paint

    def _draw(self, window: dict, rect: Rect, mouse_x: int, mouse_y: int) -> None:
        canvas = window["canvas"]
        mon = window["mon"]
        x0 = rect.left - mon.left
        y0 = rect.top - mon.top
        x1 = x0 + rect.width
        y1 = y0 + rect.height

        if window["border"] is None:
            window["border"] = canvas.create_rectangle(
                x0, y0, x1, y1, outline=theme.ACCENT, width=2
            )
            window["crop"] = canvas.create_image(x0, y0, anchor="nw")
            window["label_bg"] = canvas.create_rectangle(
                0, 0, 0, 0, fill=theme.ACCENT, outline=""
            )
            window["label"] = canvas.create_text(
                0,
                0,
                text="",
                fill="#ffffff",
                font=(theme.UI_FAMILY, 9, "bold"),
                anchor="nw",
            )
            for _ in range(4):
                window["handles"].append(
                    canvas.create_rectangle(0, 0, 0, 0, fill=theme.ACCENT, outline="")
                )
        else:
            canvas.coords(window["border"], x0, y0, x1, y1)

        canvas.coords(window["crop"], x0, y0)
        self._update_crop(window, rect)

        size = 5
        for item, (hx, hy) in zip(
            window["handles"], [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]
        ):
            canvas.coords(item, hx - size, hy - size, hx + size, hy + size)

        text = f"{rect.width} × {rect.height}"
        canvas.itemconfigure(window["label"], text=text)
        lx = min(max(mouse_x + 16, 6), mon.width - 90)
        ly = min(max(mouse_y + 18, 6), mon.height - 30)
        canvas.coords(window["label"], lx + 6, ly + 3)
        bbox = canvas.bbox(window["label"]) or (lx, ly, lx + 80, ly + 20)
        canvas.coords(window["label_bg"], bbox[0] - 6, bbox[1] - 3, bbox[2] + 6, bbox[3] + 3)

        canvas.tag_raise(window["border"])
        for item in window["handles"]:
            canvas.tag_raise(item)
        canvas.tag_raise(window["label_bg"])
        canvas.tag_raise(window["label"])

    def _update_crop(self, window: dict, rect: Rect) -> None:
        canvas = window["canvas"]
        if rect.width < 1 or rect.height < 1:
            return
        if rect.area > 1_600_000:
            canvas.itemconfigure(window["crop"], image="")
            return
        now = time.monotonic()
        if now - self._last_crop_at < 0.02:
            return
        self._last_crop_at = now

        mon = window["mon"]
        box = (
            rect.left - self._origin.left,
            rect.top - self._origin.top,
            rect.right - self._origin.left,
            rect.bottom - self._origin.top,
        )
        try:
            crop = self._shot.crop(box)
        except (ValueError, OSError):
            return
        self._crop_photo = ImageTk.PhotoImage(crop)
        canvas.itemconfigure(window["crop"], image=self._crop_photo)
        canvas.coords(window["crop"], rect.left - mon.left, rect.top - mon.top)

    # ------------------------------------------------------------------ close

    def _cancel(self) -> None:
        self._finish(None)

    def cancel(self) -> None:
        """다른 입력 경로(전역 Esc 단축키 등)에서 취소할 때 사용한다."""
        self._cancel()

    def _finish(self, rect: Rect | None) -> None:
        if self._finished:
            return
        self._finished = True
        for window in self._windows:
            try:
                window["top"].destroy()
            except tk.TclError:
                pass
        self._windows.clear()
        self._shot = None
        callback, self._on_done = self._on_done, None
        if callback is not None:
            self.root.after_idle(lambda: callback(rect))
