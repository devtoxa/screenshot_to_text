"""RapidOCR (ONNX PaddleOCR) 로컬 백엔드.

- 설치만 하면 바로 동작하고 오프라인에서도 쓸 수 있다.
- 단어 박스 좌표를 돌려주므로 들여쓰기 복원이 가능하다.
- `models/korean` 에 한국어 인식 모델이 있으면 한국어+영어를 함께 인식한다.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import threading
from pathlib import Path

from PIL import Image

from .layout import Word

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
KOREAN_MODEL = ROOT / "models" / "korean" / "rec.onnx"
KOREAN_KEYS = ROOT / "models" / "korean" / "dict.txt"

_engine = None
_engine_key: str | None = None
_lock = threading.Lock()


def available() -> bool:
    return importlib.util.find_spec("rapidocr_onnxruntime") is not None


def korean_available() -> bool:
    return (
        KOREAN_MODEL.is_file()
        and KOREAN_MODEL.stat().st_size > 1_000_000
        and KOREAN_KEYS.is_file()
        and KOREAN_KEYS.stat().st_size > 10_000
    )


def resolve_model(choice: str | None) -> str:
    """설정값을 실제 사용할 모델 이름으로 바꾼다."""
    value = (choice or "auto").strip().lower()
    if value == "korean":
        if not korean_available():
            raise RuntimeError(
                "한국어 인식 모델이 없습니다. tools/fetch_models.py 를 실행하세요."
            )
        return "korean"
    if value in ("default", "ch", "base"):
        return "default"
    return "korean" if korean_available() else "default"


def _patch_rec_keys() -> None:
    """rapidocr-onnxruntime 1.2.3 은 rec_keys_path 를 읽지 않아서 보정한다."""
    try:
        from rapidocr_onnxruntime import rapid_ocr_api  # noqa: F401
    except Exception:  # noqa: BLE001
        return

    # rapidocr 는 자기 루트를 sys.path 에 넣고 최상위 모듈명으로 import 한다.
    # 그래서 두 모듈 이름 모두 패치해야 한다.
    for module_name in (
        "rapidocr_onnxruntime.ch_ppocr_v3_rec.text_recognize",
        "ch_ppocr_v3_rec.text_recognize",
    ):
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        cls = getattr(module, "TextRecognizer", None)
        if cls is None or getattr(cls, "_stc_keys_path", False):
            continue
        original = cls.__init__

        def patched(self, config, _original=original):
            config = dict(config)
            if not config.get("keys_path") and config.get("rec_keys_path"):
                config["keys_path"] = config["rec_keys_path"]
            _original(self, config)

        cls.__init__ = patched
        cls._stc_keys_path = True


def _build(model: str):
    from rapidocr_onnxruntime import RapidOCR

    base = {
        # 코드 스크린샷은 항상 수평이라 방향 분류는 끈다 (속도).
        "use_angle_cls": False,
        "det_model_path": "",
        "det_limit_type": "max",
        "det_limit_side_len": 1600,
    }
    if model == "korean":
        _patch_rec_keys()
        try:
            return RapidOCR(
                **base,
                rec_model_path=str(KOREAN_MODEL),
                rec_keys_path=str(KOREAN_KEYS),
            )
        except Exception:  # noqa: BLE001
            log.exception("한국어 모델 로딩 실패 → 기본 모델로 대체")
    try:
        return RapidOCR(**base)
    except Exception:  # noqa: BLE001
        # 옵션 이름이 다른 버전 대비
        return RapidOCR()


def _get_engine(model: str | None = "auto"):
    global _engine, _engine_key
    resolved = resolve_model(model)
    if _engine is not None and _engine_key == resolved:
        return _engine
    with _lock:
        if _engine is None or _engine_key != resolved:
            _engine = _build(resolved)
            _engine_key = resolved
    return _engine


def current_model() -> str:
    return _engine_key or ""


def warmup(model: str | None = "auto") -> None:
    """첫 캡처 때 모델 로딩 때문에 느려지지 않도록 미리 로드한다."""
    try:
        _get_engine(model)
    except Exception:  # noqa: BLE001
        pass


def recognize(
    image: Image.Image,
    min_confidence: float = 0.25,
    model: str | None = "auto",
) -> list[Word]:
    import numpy as np

    engine = _get_engine(model)
    arr = np.asarray(image.convert("RGB"))[:, :, ::-1]  # RGB → BGR
    arr = np.ascontiguousarray(arr)

    result, _elapse = engine(arr, text_score=min_confidence)
    words: list[Word] = []
    for box, text, score in result or []:
        try:
            score_f = float(score)
        except (TypeError, ValueError):
            score_f = 1.0
        if score_f < min_confidence:
            continue
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        words.append(Word(str(text), min(xs), min(ys), max(xs), max(ys)))
    return words
