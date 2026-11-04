"""Windows 내장 OCR (Windows.Media.Ocr) 백엔드.

별도 설치 없이 쓸 수 있는 폴백. 언어 팩이 설치된 언어만 사용할 수 있다.
"""

from __future__ import annotations

import asyncio
import importlib.util
import io

from PIL import Image

from .layout import Word

_engine_cache: dict[tuple[str, ...], tuple[object, str]] = {}


def available() -> bool:
    try:
        return importlib.util.find_spec("winrt.windows.media.ocr") is not None
    except ModuleNotFoundError:
        return False


def available_languages() -> list[str]:
    try:
        from winrt.windows.media.ocr import OcrEngine

        return [str(lang.language_tag) for lang in OcrEngine.available_recognizer_languages]
    except Exception:  # noqa: BLE001
        return []


def _pick_engine(languages: tuple[str, ...]):
    from winrt.windows.globalization import Language
    from winrt.windows.media.ocr import OcrEngine

    if languages in _engine_cache:
        return _engine_cache[languages]

    for tag in languages:
        try:
            engine = OcrEngine.try_create_from_language(Language(tag))
        except Exception:  # noqa: BLE001
            engine = None
        if engine is not None:
            _engine_cache[languages] = (engine, tag)
            return engine, tag

    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise RuntimeError(
            "Windows OCR 언어 팩이 없습니다. 설정 > 시간 및 언어 > 언어에서 "
            "OCR 언어를 추가하거나 RapidOCR 백엔드를 사용하세요."
        )
    tag = str(engine.recognizer_language.language_tag)
    _engine_cache[languages] = (engine, tag)
    return engine, tag


async def _recognize_async(engine, png: bytes):
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(png)
    await writer.store_async()
    await writer.flush_async()
    writer.detach_stream()
    stream.seek(0)
    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    return await engine.recognize_async(bitmap)


def recognize(image: Image.Image, languages: list[str] | tuple[str, ...] = (), **_kwargs) -> tuple[list[Word], str]:
    engine, tag = _pick_engine(tuple(languages))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    result = asyncio.run(_recognize_async(engine, buf.getvalue()))

    words: list[Word] = []
    for line in result.lines:
        for word in line.words:
            rect = word.bounding_rect
            words.append(
                Word(
                    str(word.text),
                    float(rect.x),
                    float(rect.y),
                    float(rect.x + rect.width),
                    float(rect.y + rect.height),
                )
            )
    return words, tag
