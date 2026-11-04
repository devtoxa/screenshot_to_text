"""README.md 를 보기 좋은 HTML 로 만들고 Edge/Chrome headless 로 PDF 를 생성한다.

사용법:
    .venv\\Scripts\\python.exe tools\\build_pdf.py

결과:
    docs/Screenshot-to-Code.html
    docs/Screenshot-to-Code_Guide.pdf
"""

from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
DOCS = ROOT / "docs"
HTML_PATH = DOCS / "Screenshot-to-Code.html"
PDF_PATH = DOCS / "Screenshot-to-Code_Guide.pdf"

BROWSER_CANDIDATES = [
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    / "Microsoft/Edge/Application/msedge.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    / "Microsoft/Edge/Application/msedge.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Edge/Application/msedge.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    / "Google/Chrome/Application/chrome.exe",
]

CSS = """
@page { size: A4; margin: 16mm 15mm 17mm 15mm; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  margin: 0;
  color: #1f2328;
  font-family: "Malgun Gothic", "Segoe UI", "Apple SD Gothic Neo", sans-serif;
  font-size: 10pt;
  line-height: 1.62;
  word-break: keep-all;
}
a { color: #1f6feb; text-decoration: none; }

/* 표지 */
.cover {
  height: 248mm;
  display: flex;
  flex-direction: column;
  justify-content: center;
  page-break-after: always;
}
.cover .kicker {
  color: #1f6feb;
  font-size: 10pt;
  font-weight: 700;
  letter-spacing: 1px;
  text-transform: uppercase;
  margin-bottom: 10mm;
}
.cover h1 {
  font-size: 34pt;
  line-height: 1.15;
  margin: 0 0 6mm;
  letter-spacing: -1px;
}
.cover .lead {
  font-size: 13pt;
  color: #57606a;
  line-height: 1.7;
  margin: 0 0 12mm;
}
.cover .hotkey {
  display: inline-block;
  align-self: flex-start;
  background: #1f6feb;
  color: #fff;
  font-family: Consolas, monospace;
  font-weight: 700;
  font-size: 20pt;
  padding: 3mm 9mm;
  border-radius: 10px;
  letter-spacing: 1px;
}
.cover .facts {
  margin: 14mm 0 0;
  padding: 0;
  list-style: none;
  color: #57606a;
  font-size: 9.5pt;
  border-top: 1px solid #d8dee4;
  padding-top: 6mm;
}
.cover .facts li { margin: 2mm 0; }

/* 본문 */
h2 {
  font-size: 16pt;
  margin: 9mm 0 3mm;
  padding-bottom: 2mm;
  border-bottom: 2px solid #1f6feb;
  page-break-after: avoid;
}
h3 {
  font-size: 11.5pt;
  margin: 6mm 0 2mm;
  color: #0b3d91;
  page-break-after: avoid;
}
p { margin: 2mm 0 3mm; }
ul, ol { margin: 2mm 0 3mm; padding-left: 6mm; }
li { margin: 1mm 0; }
hr { border: none; border-top: 1px solid #e5e7eb; margin: 7mm 0; }

strong { color: #0b3d91; }

code {
  font-family: Consolas, "D2Coding", "Courier New", monospace;
  background: #f0f3f7;
  border-radius: 3px;
  padding: 0.5mm 1.2mm;
  font-size: 9pt;
}
pre {
  background: #f6f8fa;
  border: 1px solid #e1e4e8;
  border-radius: 6px;
  padding: 3mm 4mm;
  font-size: 8.5pt;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  page-break-inside: avoid;
}
pre code { background: none; padding: 0; font-size: 8.5pt; }

blockquote {
  margin: 4mm 0;
  padding: 3mm 4mm;
  background: #eef5ff;
  border-left: 4px solid #1f6feb;
  border-radius: 0 6px 6px 0;
  color: #243b53;
  page-break-inside: avoid;
}
blockquote p { margin: 1mm 0; }

table {
  width: 100%;
  border-collapse: collapse;
  margin: 3mm 0 5mm;
  font-size: 9pt;
}
th, td {
  border: 1px solid #d8dee4;
  padding: 2mm 2.5mm;
  vertical-align: top;
  text-align: left;
}
th { background: #f0f4fa; color: #0b3d91; }
thead { display: table-header-group; }
tr { page-break-inside: avoid; }

.footer-note {
  margin-top: 10mm;
  padding-top: 4mm;
  border-top: 1px solid #d8dee4;
  color: #8b949e;
  font-size: 8.5pt;
  text-align: center;
}

/* 목차 */
.toc { page-break-after: always; }
.toc h2 { margin-top: 0; }
.toc ol, .toc ul {
  columns: 2;
  column-gap: 12mm;
  margin: 8mm 0 0;
  padding-left: 7mm;
  font-size: 10.5pt;
  line-height: 1.9;
}
.toc ul { list-style: none; padding-left: 0; }
.toc li { break-inside: avoid; }
"""

COVER = """
<section class="cover">
  <div class="kicker">사용 설명서 &amp; 개발 정리</div>
  <h1>Screenshot<br>to Code</h1>
  <p class="lead">
    F12 한 번으로 화면 속 코드를 텍스트로.<br>
    한글·영어 OCR 내장, API 키 없이 오프라인 동작.
  </p>
  <div class="hotkey">F12</div>
  <ul class="facts">
    <li>Windows 11 · Python 3.14 · Tkinter</li>
    <li>RapidOCR + 한국어 인식 모델</li>
    <li>v{version} · {date}</li>
  </ul>
</section>
"""


def find_browser() -> Path | None:
    for path in BROWSER_CANDIDATES:
        try:
            if path and path.is_file():
                return path
        except OSError:
            continue
    return None


def build_html(version: str) -> str:
    import html
    import markdown

    text = README.read_text(encoding="utf-8")
    # 첫 H1 은 표지에 있으므로 본문에서 제거
    if text.startswith("# "):
        text = text.split("\n", 1)[1]
    body = markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "sane_lists", "attr_list"],
    )
    sections = [line[3:].strip() for line in text.splitlines() if line.startswith("## ")]
    toc = ""
    if sections:
        items = "".join(f"<li>{html.escape(name)}</li>" for name in sections)
        toc = f'<section class="toc"><h2>목차</h2><ul>{items}</ul></section>'

    cover = COVER.format(version=version, date=dt.date.today().isoformat())
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>Screenshot to Code — 사용 설명서 &amp; 개발 정리</title>
<style>{CSS}</style>
</head>
<body>
{cover}
{toc}
{body}
<p class="footer-note">Screenshot to Code v{version} · {dt.date.today().isoformat()}</p>
</body>
</html>
"""


def main() -> int:
    if not README.is_file():
        print(f"README.md 가 없습니다: {README}", file=sys.stderr)
        return 1

    sys.path.insert(0, str(ROOT))
    from stc import __version__ as version

    DOCS.mkdir(parents=True, exist_ok=True)
    HTML_PATH.write_text(build_html(version), encoding="utf-8")
    print(f"HTML 생성: {HTML_PATH}")

    browser = find_browser()
    if browser is None:
        print("Edge/Chrome 을 찾을 수 없어 PDF 를 만들지 못했습니다.", file=sys.stderr)
        return 1

    profile = Path(tempfile.gettempdir()) / "stc_pdf_profile"
    cmd = [
        str(browser),
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        f"--user-data-dir={profile}",
        "--no-pdf-header-footer",
        "--print-to-pdf-no-header",
        "--virtual-time-budget=5000",
        f"--print-to-pdf={PDF_PATH}",
        HTML_PATH.as_uri(),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        print("PDF 생성 시간 초과", file=sys.stderr)
        return 1

    if not PDF_PATH.is_file():
        print("PDF 생성 실패", file=sys.stderr)
        print((result.stdout or "")[-1500:], file=sys.stderr)
        print((result.stderr or "")[-1500:], file=sys.stderr)
        return 1

    size_kb = PDF_PATH.stat().st_size / 1024
    print(f"PDF 생성: {PDF_PATH} ({size_kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
