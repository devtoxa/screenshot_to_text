"""앱 아이콘 (PIL 로 그려서 .ico 로 저장)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def make_image(size: int = 64) -> Image.Image:
    scale = size / 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(
        [1 * scale, 1 * scale, size - 1 * scale, size - 1 * scale],
        radius=14 * scale,
        fill=(31, 111, 235, 255),
    )
    white = (255, 255, 255, 255)
    w = max(2, int(4 * scale))
    # < >
    d.line([(22 * scale, 20 * scale), (12 * scale, 32 * scale), (22 * scale, 44 * scale)], fill=white, width=w, joint="curve")
    d.line([(42 * scale, 20 * scale), (52 * scale, 32 * scale), (42 * scale, 44 * scale)], fill=white, width=w, joint="curve")
    # /
    d.line([(37 * scale, 17 * scale), (27 * scale, 47 * scale)], fill=(196, 223, 255, 255), width=w)
    return img


def ensure_ico(path: Path | None = None) -> Path | None:
    path = path or ASSETS / "icon.ico"
    try:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            sizes = [(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)]
            make_image(256).save(path, sizes=sizes)
        return path
    except OSError:
        return None
