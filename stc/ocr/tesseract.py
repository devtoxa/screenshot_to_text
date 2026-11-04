"""Tesseract CLI 백엔드 (선택 사항).

Tesseract 가 PATH 또는 기본 설치 경로에 있으면 사용할 수 있다.
단어별 좌표를 TSV 출력에서 읽어 들여쓰기를 복원한다.
"""

from __future__ import annotations

import csv
import io
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from .layout import Word

_DEFAULT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]

_LANG_MAP = {
    "ko-kr": "kor",
    "ko": "kor",
    "en-us": "eng",
    "en": "eng",
    "ja-jp": "jpn",
    "ja": "jpn",
    "zh-cn": "chi_sim",
    "zh-tw": "chi_tra",
}


def find_binary(configured: str = "") -> str | None:
    if configured and Path(configured).exists():
        return configured
    found = shutil.which("tesseract")
    if found:
        return found
    for path in _DEFAULT_PATHS:
        if Path(path).exists():
            return path
    return None


def available(configured: str = "") -> bool:
    return find_binary(configured) is not None


def recognize(
    image: Image.Image,
    *,
    binary: str = "",
    languages: list[str] | tuple[str, ...] = (),
    psm: int = 6,
) -> tuple[list[Word], str]:
    exe = find_binary(binary)
    if not exe:
        raise RuntimeError("Tesseract 실행 파일을 찾을 수 없습니다. tesseract_path 를 설정하세요.")

    lang = "+".join(
        dict.fromkeys(_LANG_MAP.get(str(tag).lower(), str(tag)) for tag in languages if tag)
    ) or "eng"

    tmp = Path(tempfile.gettempdir()) / "stc_tesseract_input.png"
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    tmp.write_bytes(buf.getvalue())

    cmd = [exe, str(tmp), "stdout", "--psm", str(psm), "-l", lang, "tsv"]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Tesseract 실패: {proc.stderr.strip()[:300]}")

    words: list[Word] = []
    reader = csv.DictReader(io.StringIO(proc.stdout), delimiter="\t")
    for row in reader:
        if row.get("level") != "5":
            continue
        text = (row.get("text") or "").strip()
        if not text:
            continue
        try:
            conf = float(row.get("conf") or "-1")
            left = float(row["left"])
            top = float(row["top"])
            width = float(row["width"])
            height = float(row["height"])
        except (KeyError, TypeError, ValueError):
            continue
        if conf < 20:
            continue
        words.append(Word(text, left, top, left + width, top + height))
    return words, lang


def cleanup() -> None:
    try:
        os.remove(Path(tempfile.gettempdir()) / "stc_tesseract_input.png")
    except OSError:
        pass
