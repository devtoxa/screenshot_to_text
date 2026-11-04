"""OCR 단어 박스들을 코드 텍스트로 재조립한다.

OCR 엔진은 보통 단어(또는 단어 뭉치) 단위로 박스를 돌려준다. 이 모듈은
- 같은 줄에 있는 박스를 묶고, 박스 사이 간격으로 띄어쓰기를 복원하고,
- 박스의 x 좌표와 글자 폭으로 들여쓰기를 추정하고,
- (선택) 코드 왼쪽에 붙은 줄번호를 제거한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from statistics import median

_SEPARATOR = re.compile(r"^[|│¦¦:;.)\]>»\-–—]+$")
_LINE_NO = re.compile(r"^(\d{1,4})\s*[|│¦:.)\]>»]?$")


@dataclass
class Word:
    text: str
    left: float
    top: float
    right: float
    bottom: float

    def __post_init__(self) -> None:
        self.text = re.sub(r"\s+", " ", str(self.text)).strip(" \t\r\n")
        if self.right < self.left:
            self.left, self.right = self.right, self.left
        if self.bottom < self.top:
            self.top, self.bottom = self.bottom, self.top

    @property
    def width(self) -> float:
        return max(0.0, self.right - self.left)

    @property
    def height(self) -> float:
        return max(0.0, self.bottom - self.top)

    @property
    def cy(self) -> float:
        return (self.top + self.bottom) / 2


@dataclass
class TextLine:
    words: list[Word] = field(default_factory=list)

    def add(self, word: Word) -> None:
        self.words.append(word)

    @property
    def cy(self) -> float:
        return sum(w.cy for w in self.words) / len(self.words)

    @property
    def height(self) -> float:
        return median([w.height for w in self.words]) if self.words else 0.0

    @property
    def left(self) -> float:
        return min(w.left for w in self.words)


def _dedupe(words: list[Word]) -> list[Word]:
    out: list[Word] = []
    for w in words:
        duplicate = False
        for prev in out:
            if prev.text != w.text:
                continue
            if abs(prev.cy - w.cy) > max(2.0, 0.4 * max(prev.height, w.height)):
                continue
            span = max(prev.right, w.right) - min(prev.left, w.left)
            if span <= max(prev.width, w.width) * 1.15:
                duplicate = True
                break
        if not duplicate:
            out.append(w)
    return out


def _cluster(words: list[Word]) -> list[TextLine]:
    lines: list[TextLine] = []
    current: TextLine | None = None
    for w in sorted(words, key=lambda w: (w.cy, w.left)):
        if current is not None:
            tol = 0.5 * max(w.height, current.height, 4.0)
            if abs(w.cy - current.cy) <= tol:
                current.add(w)
                continue
        current = TextLine([w])
        lines.append(current)
    for line in lines:
        line.words.sort(key=lambda w: w.left)
    return lines


def _estimate_char_width(words: list[Word], line_height: float) -> float:
    samples = [w.width / len(w.text) for w in words if len(w.text) >= 2 and w.width > 1]
    fallback = max(1.0, 0.58 * line_height)
    if not samples:
        return fallback
    value = median(samples)
    if not (0.3 * line_height <= value <= 1.8 * line_height):
        return fallback
    return value


def _fit_char_width(lefts: list[float], estimate: float) -> float:
    """들여쓰기 x 좌표들이 정수 칸에 딱 맞도록 글자 폭을 미세 조정한다."""
    if len(lefts) < 2 or estimate <= 0:
        return estimate
    base = min(lefts)
    offsets = [x - base for x in lefts if x - base >= 0.4 * estimate]
    if not offsets:
        return estimate
    best = estimate
    best_err = None
    step = estimate * 0.01
    width = estimate * 0.85
    while width <= estimate * 1.15:
        err = sum(abs(offset / width - round(offset / width)) for offset in offsets) / len(offsets)
        if best_err is None or err < best_err - 1e-9:
            best_err, best = err, width
        width += step
    return best


def _strip_line_numbers(lines: list[TextLine]) -> list[TextLine]:
    numbers: list[int | None] = []
    for line in lines:
        match = _LINE_NO.match(line.words[0].text) if line.words else None
        numbers.append(int(match.group(1)) if match else None)

    found = [n for n in numbers if n is not None]
    if len(found) < 3 or len(found) < 0.55 * len(lines):
        return lines
    increasing = all(b > a for a, b in zip(found, found[1:])) and (found[-1] - found[0]) >= len(found) - 1
    if not increasing:
        return lines

    cleaned: list[TextLine] = []
    for line, number in zip(lines, numbers):
        if number is None:
            cleaned.append(line)
            continue
        words = line.words[1:]
        while words and _SEPARATOR.match(words[0].text):
            words = words[1:]
        if words:
            cleaned.append(TextLine(words))
    return cleaned


def _join_line(words: list[Word], char_width: float) -> str:
    parts: list[str] = []
    prev: Word | None = None
    for w in words:
        if prev is None:
            parts.append(w.text)
        else:
            gap = w.left - prev.right
            if gap <= 0.18 * char_width:
                parts.append(w.text)
            elif gap <= 1.35 * char_width:
                parts.append(" " + w.text)
            else:
                spaces = int(min(8, max(2, round(gap / char_width))))
                parts.append(" " * spaces + w.text)
        prev = w
    return "".join(parts)


def words_to_code(
    words: list[Word],
    *,
    preserve_indent: bool = True,
    strip_line_numbers: bool = True,
    dedent_common: bool = False,
) -> str:
    words = [w for w in words if w.text]
    if not words:
        return ""

    words = _dedupe(words)
    lines = _cluster(words)
    if strip_line_numbers:
        lines = _strip_line_numbers(lines)
    if not lines:
        return ""

    line_height = median([line.height for line in lines]) or 12.0
    char_width = _fit_char_width(
        [line.left for line in lines], _estimate_char_width(words, line_height)
    )
    base_left = min(line.left for line in lines)

    rendered: list[tuple[str, float]] = []
    for line in lines:
        text = _join_line(line.words, char_width)
        if preserve_indent:
            indent = int(round((line.left - base_left) / char_width))
            if indent > 0:
                text = " " * min(indent, 40) + text
        rendered.append((text.rstrip(), line.cy))

    # 단어가 없는 빈 줄은 y 좌표 간격으로 복원한다.
    if len(rendered) >= 2:
        pitches = [
            b[1] - a[1]
            for a, b in zip(rendered, rendered[1:])
            if 0 < (b[1] - a[1]) < 3.0 * line_height
        ]
        pitch = median(pitches) if pitches else line_height * 1.4
        expanded: list[tuple[str, float]] = []
        for (text, cy), (_, next_cy) in zip(rendered, rendered[1:] + [(None, None)]):
            expanded.append((text, cy))
            if next_cy is not None and pitch > 0:
                extra = int(round((next_cy - cy) / pitch)) - 1
                expanded.extend([("", cy)] * max(0, min(extra, 3)))
        rendered = expanded

    if dedent_common and rendered:
        widths = [len(t) - len(t.lstrip(" ")) for t, _ in rendered if t.strip()]
        common = min(widths) if widths else 0
        if common:
            rendered = [(t[common:] if t.strip() else "", cy) for t, cy in rendered]

    # 3줄 이상의 연속 공백은 1줄로 정리
    out: list[str] = []
    blanks = 0
    for text, _ in rendered:
        if text.strip():
            blanks = 0
            out.append(text)
        else:
            blanks += 1
            if blanks == 1:
                out.append("")
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out)


# OCR 이 코드에서 자주 내놓는 전각/따옴표 문자를 ASCII 로 되돌린다.
_LOOKALIKES = str.maketrans(
    {
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u2033": '"',
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u2032": "'",
        "\u3008": "<",
        "\u3009": ">",
        "\u2329": "<",
        "\u232a": ">",
        "\u00a0": " ",
        "\u2212": "-",
        "\uff1a": ":",
        "\uff08": "(",
        "\uff09": ")",
        "\uff0c": ",",
        "\uff1b": ";",
        "\uff3b": "[",
        "\uff3d": "]",
        "\uff5b": "{",
        "\uff5d": "}",
        "\uff1d": "=",
        "\uff0b": "+",
        "\uff0d": "-",
        "\uff0a": "*",
        "\uff0f": "/",
        "\uff3c": "\\",
        "\uff5c": "|",
        "\uff01": "!",
        "\uff1f": "?",
        "\uff05": "%",
        "\uff06": "&",
        "\uff1c": "<",
        "\uff1e": ">",
    }
)


def clean_code_text(text: str, tab_width: int = 4) -> str:
    text = (text or "").translate(_LOOKALIKES)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if tab_width:
        text = text.replace("\t", " " * tab_width)
    lines = [line.rstrip() for line in text.split("\n")]
    out: list[str] = []
    blanks = 0
    for line in lines:
        if line.strip():
            blanks = 0
            out.append(line)
        else:
            blanks += 1
            if blanks == 1:
                out.append("")
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out)
