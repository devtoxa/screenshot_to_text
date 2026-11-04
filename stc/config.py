"""config.json 로딩/저장.

dataclass 기본값 위에 파일 값을 덮어쓰는 방식이라, 사용자가 일부 키만 적어도
나머지는 기본값이 그대로 적용된다. 알 수 없는 키는 무시한다.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"

VISION_PROMPT = (
    "You are a precise OCR engine for source code screenshots. "
    "Read the code in the image and return it verbatim.\n"
    "Rules:\n"
    "- Output only the code, inside a single ``` fenced block.\n"
    "- Preserve indentation with spaces exactly as shown.\n"
    "- Never translate, summarize, fix or reformat anything.\n"
    "- Keep comments, strings and identifiers exactly as they appear.\n"
    "- If characters are ambiguous, choose the ones that make the code valid.\n"
    "- Do not add line numbers that are not part of the code."
)


@dataclass
class OcrConfig:
    # auto | rapid | winocr | vision | tesseract
    backend: str = "auto"
    # 인식 모델: "auto" (한국어 모델이 있으면 사용) | "korean" | "default"
    rec_model: str = "auto"
    # Windows OCR 언어 우선순위 (설치된 언어만 사용됨)
    languages: list[str] = field(default_factory=lambda: ["ko-KR", "en-US"])
    # "auto" 또는 숫자. 작은 글씨 인식을 돕기 위한 확대 배율
    upscale: Any = "auto"
    strip_line_numbers: bool = True
    preserve_indent: bool = True
    tab_width: int = 4
    min_confidence: float = 0.25
    # Tesseract 백엔드용 (비워두면 PATH/기본 경로에서 자동 탐색)
    tesseract_path: str = ""
    tesseract_psm: int = 6


@dataclass
class VisionConfig:
    # OpenAI 호환 /chat/completions 엔드포인트
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    api_key_env: str = "OPENAI_API_KEY"
    api_key: str = ""
    timeout: int = 90
    max_tokens: int = 8192
    # provider 별 추가 파라미터 (예: {"reasoning_effort": "low"})
    extra_body: dict = field(default_factory=dict)
    prompt: str = VISION_PROMPT


@dataclass
class BehaviorConfig:
    copy_to_clipboard: bool = True
    save_png: bool = True
    save_text: bool = False
    output_dir: str = "captures"
    # 선택 영역 바깥을 어둡게 만드는 정도 (0 = 없음, 0.8 = 아주 어둡게)
    dim: float = 0.55
    # 결과 창을 캡처 영역 근처에 띄우기
    popup_near_selection: bool = True
    # False 면 결과 창 없이 곧바로 클립보드에만 복사한다.
    show_result_window: bool = False
    # 복사/오류 알림 배지를 잠깐 띄운다 (포커스는 뺏지 않음).
    show_toast: bool = True


@dataclass
class AppConfig:
    hotkey: str = "f12"
    quit_hotkey: str = "ctrl+alt+q"
    tray: bool = True
    ocr: OcrConfig = field(default_factory=OcrConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    behavior: BehaviorConfig = field(default_factory=BehaviorConfig)

    @property
    def output_path(self) -> Path:
        p = Path(self.behavior.output_dir)
        return p if p.is_absolute() else ROOT / p


def _apply(obj: Any, data: Any) -> None:
    if not isinstance(data, dict):
        return
    known = {f.name: f for f in fields(obj)}
    for key, value in data.items():
        f = known.get(key)
        if f is None:
            continue
        current = getattr(obj, key)
        if is_dataclass(current) and isinstance(value, dict):
            _apply(current, value)
        elif value is not None:
            setattr(obj, key, value)


def load(path: Path | None = None) -> AppConfig:
    path = path or CONFIG_PATH
    cfg = AppConfig()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            _apply(cfg, data)
        except (OSError, json.JSONDecodeError):
            pass
    else:
        save(cfg, path)
    return cfg


def save(cfg: AppConfig, path: Path | None = None) -> Path:
    path = path or CONFIG_PATH
    path.write_text(
        json.dumps(asdict(cfg), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path
