"""한국어 인식 모델(korean rec + dict)을 내려받는다.

- `models/korean/` 에 이미 있으면 건너뛴다.
- 네트워크가 없으면 경고만 하고 종료한다 (기본 모델로는 계속 동작하지만 한글은 인식되지 않음).
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "models" / "korean"
BASE_URL = "https://huggingface.co/monkt/paddleocr-onnx/resolve/main/languages/korean"

FILES = {
    "rec.onnx": 1_000_000,  # 최소 크기 검증용
    "dict.txt": 10_000,
}


def fetch(quiet: bool = False) -> bool:
    DEST.mkdir(parents=True, exist_ok=True)
    ok = True
    for name, min_size in FILES.items():
        target = DEST / name
        if target.is_file() and target.stat().st_size >= min_size:
            if not quiet:
                print(f"[skip] {name} (이미 있음)")
            continue
        if not quiet:
            print(f"[down] {name} ...")
        tmp = target.with_suffix(target.suffix + ".part")
        try:
            urllib.request.urlretrieve(f"{BASE_URL}/{name}", tmp)
            if tmp.stat().st_size < min_size:
                raise RuntimeError(f"{name} 다운로드가 불완전합니다")
            tmp.replace(target)
        except Exception as exc:  # noqa: BLE001
            ok = False
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            print(f"[warn] {name} 다운로드 실패: {exc}", file=sys.stderr)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
    return ok


if __name__ == "__main__":
    try:
        success = fetch()
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] 한국어 모델 준비 실패: {exc}", file=sys.stderr)
        success = False
    if success:
        print(f"한국어 모델 준비 완료: {DEST}")
    else:
        print("한국어 모델 없이 실행됩니다 (영문/숫자만 인식).", file=sys.stderr)
