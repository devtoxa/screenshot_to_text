"""OCR 백엔드 선택/실행."""

from __future__ import annotations

import time

from PIL import Image

from ..config import AppConfig
from . import rapid, tesseract, vision, winocr
from .layout import clean_code_text, words_to_code
from .types import OcrResult

LABELS = {
    "rapid": "RapidOCR",
    "winocr": "Windows OCR",
    "vision": "Vision API",
    "tesseract": "Tesseract",
}


def available_backends(cfg: AppConfig) -> list[str]:
    result = []
    if rapid.available():
        result.append("rapid")
    if winocr.available():
        result.append("winocr")
    if vision.available(cfg.vision):
        result.append("vision")
    if tesseract.available(cfg.ocr.tesseract_path):
        result.append("tesseract")
    return result


def _upscale(image: Image.Image, setting) -> Image.Image:
    width, height = image.size
    if isinstance(setting, (int, float)) and not isinstance(setting, bool) and setting > 0:
        scale = float(setting)
    elif setting is None or str(setting).lower() == "auto":
        if width * height > 4_000_000:
            scale = 1.0
        elif width < 900:
            scale = 2.0
        elif width < 1200:
            scale = 1.5
        else:
            scale = 1.0
    else:
        try:
            scale = float(setting)
        except (TypeError, ValueError):
            scale = 1.0
    if scale <= 1.0:
        return image
    target = (int(width * scale), int(height * scale))
    if max(target) > 9000:  # Windows OCR 최대 10000px
        return image
    return image.resize(target, Image.LANCZOS)


def _candidates(cfg: AppConfig) -> list[str]:
    chosen = (cfg.ocr.backend or "auto").strip().lower()
    installed = available_backends(cfg)
    if chosen not in ("", "auto"):
        order = [chosen]
        order += [b for b in installed if b != chosen]
        return order
    if "vision" in installed:
        # API 키를 설정해 두었다면 가장 정확한 엔진을 먼저 쓴다.
        return ["vision"] + [b for b in installed if b != "vision"]
    return installed or ["rapid", "winocr", "vision", "tesseract"]


def run(image: Image.Image, cfg: AppConfig) -> OcrResult:
    started = time.perf_counter()
    working = _upscale(image, cfg.ocr.upscale)
    warnings: list[str] = []
    errors: list[str] = []
    empty: OcrResult | None = None

    for backend in _candidates(cfg):
        try:
            if backend == "vision":
                text = clean_code_text(vision.recognize(working, cfg.vision), cfg.ocr.tab_width)
                return OcrResult(
                    text=text,
                    backend=backend,
                    language=cfg.vision.model,
                    elapsed=time.perf_counter() - started,
                    word_count=len(text.split()),
                    image_size=working.size,
                    warnings=warnings,
                )

            if backend == "rapid":
                words = rapid.recognize(working, cfg.ocr.min_confidence, cfg.ocr.rec_model)
                language = "ko+en" if rapid.current_model() == "korean" else "en"
            elif backend == "winocr":
                words, language = winocr.recognize(working, cfg.ocr.languages)
            elif backend == "tesseract":
                words, language = tesseract.recognize(
                    working,
                    binary=cfg.ocr.tesseract_path,
                    languages=cfg.ocr.languages,
                    psm=cfg.ocr.tesseract_psm,
                )
            else:
                raise RuntimeError(f"알 수 없는 OCR 백엔드: {backend}")

            text = words_to_code(
                words,
                preserve_indent=cfg.ocr.preserve_indent,
                strip_line_numbers=cfg.ocr.strip_line_numbers,
            )
            text = clean_code_text(text, cfg.ocr.tab_width)
            if not text:
                warnings.append(f"{LABELS.get(backend, backend)}: 텍스트를 찾지 못했습니다.")
                if empty is None:
                    empty = OcrResult(
                        text="",
                        backend=backend,
                        language=language or "",
                        elapsed=time.perf_counter() - started,
                        word_count=len(words),
                        image_size=working.size,
                        warnings=list(warnings),
                    )
                continue
            return OcrResult(
                text=text,
                backend=backend,
                language=language or "",
                elapsed=time.perf_counter() - started,
                word_count=len(words),
                image_size=working.size,
                warnings=warnings,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{LABELS.get(backend, backend)}: {exc}")

    if empty is not None and not errors:
        return empty
    raise RuntimeError("\n".join(errors) or "사용 가능한 OCR 백엔드가 없습니다.")


def warmup(cfg: AppConfig) -> None:
    """가능한 백엔드의 모델을 미리 로딩해 첫 캡처를 빠르게 한다."""
    chosen = (cfg.ocr.backend or "auto").strip().lower()
    if chosen in ("", "auto"):
        if rapid.available():
            rapid.warmup(cfg.ocr.rec_model)
    elif chosen == "rapid":
        rapid.warmup(cfg.ocr.rec_model)


def language_note(cfg: AppConfig) -> str:
    if cfg.ocr.backend == "winocr":
        return ", ".join(winocr.available_languages()) or "없음"
    return ""
