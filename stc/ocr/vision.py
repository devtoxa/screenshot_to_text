"""OpenAI 호환 Vision API 백엔드 (가장 정확한 결과).

- base_url/model/api_key 만 바꾸면 OpenAI, OpenRouter, Gemini(OpenAI 호환),
  Ollama 같은 서버를 모두 쓸 수 있다.
- API 키는 config.json 의 vision.api_key 또는 환경 변수에서 읽는다.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import urllib.error
import urllib.request

from PIL import Image

from ..config import VisionConfig

_FENCE = re.compile(r"```[^\n`]*\n?(.*?)```", re.S)


def api_key(cfg: VisionConfig) -> str:
    return (cfg.api_key or os.environ.get(cfg.api_key_env, "")).strip()


def available(cfg: VisionConfig) -> bool:
    return bool(api_key(cfg))


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    match = _FENCE.search(text)
    if match:
        text = match.group(1)
    elif text.lstrip().startswith("```"):
        text = text.lstrip()[3:]
        text = text.split("\n", 1)[1] if "\n" in text else text
    return text.strip("\n")


def recognize(image: Image.Image, cfg: VisionConfig) -> str:
    key = api_key(cfg)
    if not key:
        raise RuntimeError(
            f"Vision API 키가 없습니다. config.json 의 vision.api_key 또는 "
            f"환경 변수 {cfg.api_key_env} 를 설정하세요."
        )

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

    payload: dict = {
        "model": cfg.model,
        "messages": [
            {"role": "system", "content": cfg.prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract the code from this screenshot."},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
    }
    if cfg.max_tokens and cfg.max_tokens > 0:
        payload["max_tokens"] = cfg.max_tokens
    if cfg.extra_body:
        payload.update(cfg.extra_body)

    body = json.dumps(payload).encode("utf-8")
    url = cfg.base_url.rstrip("/") + "/chat/completions"
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=cfg.timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"Vision API 오류 {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Vision API 연결 실패: {exc.reason}") from exc

    try:
        data = json.loads(raw)
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Vision API 응답을 해석할 수 없습니다: {raw[:300]}") from exc

    if isinstance(content, list):  # 일부 provider 는 파트 배열로 응답
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return _clean(str(content))
