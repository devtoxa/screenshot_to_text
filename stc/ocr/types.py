"""OCR 백엔드 공통 타입."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Recognized:
    """백엔드가 돌려주는 원시 결과."""

    words: list  # list[stc.ocr.layout.Word]
    language: str = ""
    backend: str = ""


@dataclass
class OcrResult:
    text: str
    backend: str
    language: str
    elapsed: float
    word_count: int
    image_size: tuple[int, int]
    warnings: list[str] = field(default_factory=list)

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def line_count(self) -> int:
        return len(self.text.splitlines()) if self.text else 0
