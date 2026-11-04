"""화면 캡처 유틸리티 (mss 래퍼)."""

from __future__ import annotations

from dataclasses import dataclass

import mss
from PIL import Image


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def area(self) -> int:
        return self.width * self.height

    def shifted(self, dx: int, dy: int) -> "Rect":
        return Rect(self.left + dx, self.top + dy, self.width, self.height)

    def clamp_to(self, outer: "Rect") -> "Rect":
        left = max(self.left, outer.left)
        top = max(self.top, outer.top)
        right = min(self.right, outer.right)
        bottom = min(self.bottom, outer.bottom)
        return Rect(left, top, max(0, right - left), max(0, bottom - top))

    def intersects(self, other: "Rect") -> bool:
        return (
            self.left < other.right
            and other.left < self.right
            and self.top < other.bottom
            and other.top < self.bottom
        )


def _rect_from_mss(mon: dict) -> Rect:
    return Rect(int(mon["left"]), int(mon["top"]), int(mon["width"]), int(mon["height"]))


def virtual_screen() -> Rect:
    with mss.MSS() as sct:
        return _rect_from_mss(sct.monitors[0])


def monitors() -> list[Rect]:
    """실제 모니터 목록 (0번 가상 화면 제외)."""
    with mss.MSS() as sct:
        return [_rect_from_mss(m) for m in sct.monitors[1:]]


def capture(rect: Rect | None = None) -> tuple[Image.Image, Rect]:
    """주어진 영역(기본: 전체 가상 화면)을 RGB 이미지로 캡처한다."""
    with mss.MSS() as sct:
        area = _rect_from_mss(sct.monitors[0]) if rect is None else rect
        raw = sct.grab(
            {
                "left": area.left,
                "top": area.top,
                "width": area.width,
                "height": area.height,
            }
        )
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        return img, area


def capture_all() -> tuple[Image.Image, Rect, list[Rect]]:
    """한 번의 mss 세션으로 전체 화면 + 모니터 목록을 함께 가져온다."""
    with mss.MSS() as sct:
        area = _rect_from_mss(sct.monitors[0])
        mons = [_rect_from_mss(m) for m in sct.monitors[1:]] or [area]
        raw = sct.grab(
            {
                "left": area.left,
                "top": area.top,
                "width": area.width,
                "height": area.height,
            }
        )
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        return img, area, mons
