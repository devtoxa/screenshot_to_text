"""Screenshot to Text — F12 를 눌렀을 때만 화면의 코드를 텍스트로 추출한다."""

from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import logging
import os
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path

from stc import __version__, capture, clipboard, config, icon, ocr, winfocus
from stc.capture import Rect
from stc.config import AppConfig
from stc.hotkey import HotkeyManager
from stc.result_window import ResultWindow
from stc.snipper import Snipper
from stc.toast import Toast

ROOT = Path(__file__).resolve().parent
LOG_PATH = ROOT / "app.log"
# 내부 식별자: 이름을 바꾸면 이전 버전과 동시에 실행될 수 있어 그대로 둔다.
MUTEX_NAME = "Local\\ScreenshotToCode_single_instance"

HOTKEY_CAPTURE = 1
HOTKEY_QUIT = 2
HOTKEY_ESC = 3

log = logging.getLogger("stc")


def _first_line(text: str, limit: int = 140) -> str:
    line = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    return line if len(line) <= limit else line[: limit - 1] + "…"


# --------------------------------------------------------------------- setup


def setup_logging(verbose: bool) -> None:
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > 1_000_000:
            LOG_PATH.replace(LOG_PATH.with_suffix(".log.1"))
    except OSError:
        pass
    handlers: list[logging.Handler] = []
    try:
        handlers.append(logging.FileHandler(LOG_PATH, encoding="utf-8"))
    except OSError:
        pass
    if verbose and sys.stderr is not None:
        try:
            sys.stderr.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
        force=True,
    )


def enable_dpi_awareness() -> None:
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:  # noqa: BLE001
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:  # noqa: BLE001
        pass


def single_instance_lock():
    """이미 실행 중이면 None 을 돌려준다."""
    try:
        handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            return None
        return handle
    except Exception:  # noqa: BLE001
        return True


# ----------------------------------------------------------------------- app


class App:
    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("Screenshot to Text")

        ico = icon.ensure_ico()
        if ico:
            try:
                self.root.iconbitmap(default=str(ico))
            except tk.TclError:
                pass

        self.queue: queue.Queue = queue.Queue()
        self.snipper = Snipper(self.root, cfg.behavior.dim)
        self.result: ResultWindow | None = None
        self.tray = None
        self.toast = Toast(self.root)

        self._shot = None
        self._origin = Rect(0, 0, 0, 0)
        self._monitors: list[Rect] = []
        self._seq = 0
        self._last_trigger = 0.0
        self._hotkey_ok = False
        self._prev_hwnd = 0
        self.hotkeys = HotkeyManager()
        self._esc_armed = False

        # 창 없이 복사만 하는 모드에서도 트레이로 다시 열어볼 수 있게 보관한다.
        self.last_result = None
        self.last_anchor: Rect | None = None
        self.last_png: Path | None = None

    # ------------------------------------------------------------------ start

    def run(self) -> None:
        self._install_hotkeys()
        if self.cfg.tray:
            self._start_tray()
        try:
            log.info(
                "로컬 OCR 모델: %s",
                "한국어+영어" if ocr.rapid.korean_available() else "영문(한국어 모델 없음)",
            )
        except Exception:  # noqa: BLE001
            pass
        threading.Thread(target=ocr.warmup, args=(self.cfg,), daemon=True).start()
        if self.cfg.hotkey and not self._hotkey_ok:
            self.root.after(300, self._warn_no_hotkey)
        self.root.after(40, self._poll)
        self.root.mainloop()

    def _warn_no_hotkey(self) -> None:
        if self._hotkey_ok:
            return
        from tkinter import messagebox

        messagebox.showwarning(
            "Screenshot to Text",
            "전역 단축키(F12)를 등록하지 못했습니다.\n\n"
            "· config.json 의 hotkey 값이 올바른지 확인하세요. (예: f12, ctrl+alt+s)\n"
            "· 관리자 권한으로 실행 중인 앱 위에서는 단축키가 동작하지 않을 수 있습니다.\n"
            "· 트레이 아이콘 메뉴에서도 캡처를 시작할 수 있습니다.",
        )

    def _install_hotkeys(self) -> None:
        started = self.hotkeys.start()
        if not started:
            log.error("단축키 엔진을 시작하지 못했습니다: %s", self.hotkeys.error)

        hotkey = (self.cfg.hotkey or "").strip()
        if hotkey:
            try:
                self.hotkeys.register(hotkey, self._on_hotkey, HOTKEY_CAPTURE)
                self._hotkey_ok = started
            except Exception as exc:  # noqa: BLE001
                log.error("단축키 등록 실패: %s", exc)
        else:
            log.info("캡처 단축키 사용 안 함")

        quit_hotkey = (self.cfg.quit_hotkey or "").strip()
        if quit_hotkey and quit_hotkey.lower() != hotkey.lower():
            try:
                self.hotkeys.register(
                    quit_hotkey, lambda: self.queue.put(("quit",)), HOTKEY_QUIT
                )
                log.info("종료 단축키 등록: %s", quit_hotkey)
            except Exception as exc:  # noqa: BLE001
                log.error("종료 단축키 등록 실패: %s", exc)

    def _on_hotkey(self) -> None:
        now = time.monotonic()
        if now - self._last_trigger < 0.35:
            return
        self._last_trigger = now
        self.queue.put(("capture",))

    def _start_tray(self) -> None:
        try:
            from stc.tray import Tray

            self.tray = Tray(
                icon.make_image(64),
                on_capture=lambda: self.queue.put(("capture",)),
                on_open_folder=lambda: self.queue.put(("open", "folder")),
                on_open_config=lambda: self.queue.put(("open", "config")),
                on_quit=lambda: self.queue.put(("quit",)),
                on_show_last=lambda: self.queue.put(("last",)),
            )
            self.tray.start()
        except Exception:  # noqa: BLE001
            log.exception("트레이 아이콘을 시작하지 못했습니다")
            self.tray = None

    # ------------------------------------------------------------------- loop

    def _poll(self) -> None:
        while True:
            try:
                message = self.queue.get_nowait()
            except queue.Empty:
                break
            try:
                self._handle(message)
            except Exception:  # noqa: BLE001
                log.exception("이벤트 처리 실패: %s", message)
        self.root.after(40, self._poll)

    def _handle(self, message: tuple) -> None:
        kind = message[0]
        if kind == "capture":
            self.begin_capture()
        elif kind == "ocr":
            _, seq, result, error = message
            self._on_ocr(seq, result, error)
        elif kind == "quit":
            self.quit()
        elif kind == "cancel":
            if self.snipper.active:
                self.snipper.cancel()
        elif kind == "last":
            self._show_last()
        elif kind == "open":
            self._open(message[1])

    # ---------------------------------------------------------------- capture

    def begin_capture(self) -> None:
        if self.snipper.active:
            return
        self._dismiss_result()
        self.toast.close()
        # 오버레이가 끝난 뒤 이 창으로 포커스를 돌려준다.
        self._prev_hwnd = winfocus.get_foreground()
        try:
            shot, origin, monitors = capture.capture_all()
        except Exception as exc:  # noqa: BLE001
            log.exception("화면 캡처 실패")
            self._restore_foreground()
            self._show_error(f"화면을 캡처할 수 없습니다.\n\n{exc}")
            return
        self._shot = shot
        self._origin = origin
        self._monitors = monitors
        log.info("캡처 시작 (%dx%d)", origin.width, origin.height)
        self.snipper.start(shot, origin, monitors, self._on_region)
        self._arm_escape()

    def _arm_escape(self) -> None:
        """캡처 중에만 Esc 를 전역 단축키로 등록한다 (키 훅 아님)."""
        if self._esc_armed:
            return
        try:
            self.hotkeys.register("esc", lambda: self.queue.put(("cancel",)), HOTKEY_ESC)
            self._esc_armed = True
        except Exception as exc:  # noqa: BLE001
            log.debug("Esc 단축키 등록 실패: %s", exc)

    def _disarm_escape(self) -> None:
        if not self._esc_armed:
            return
        self.hotkeys.unregister(HOTKEY_ESC)
        self._esc_armed = False

    def _restore_foreground(self) -> None:
        """캡처 전에 쓰던 창으로 포커스를 돌려준다 (키 입력 먹통 방지)."""
        hwnd, self._prev_hwnd = self._prev_hwnd, 0
        if hwnd:
            winfocus.force_foreground(hwnd)

    def _on_region(self, rect: Rect | None) -> None:
        self._disarm_escape()
        shot = self._shot
        self._shot = None
        if rect is None or shot is None:
            log.info("선택 취소")
            self._restore_foreground()
            return
        box = (
            rect.left - self._origin.left,
            rect.top - self._origin.top,
            rect.right - self._origin.left,
            rect.bottom - self._origin.top,
        )
        try:
            crop = shot.crop(box)
        except Exception:  # noqa: BLE001
            log.exception("선택 영역 자르기 실패")
            self._restore_foreground()
            return

        png = self._save_png(crop)
        self.last_png = png
        self.last_anchor = rect
        self._seq += 1
        seq = self._seq

        if self.cfg.behavior.show_result_window:
            if self.result is not None and not self.result.closed:
                self.result.close()
            self.result = ResultWindow(
                self.root,
                self.cfg,
                anchor=rect,
                png_path=png,
                on_recapture=self.begin_capture,
                on_closed=self._restore_foreground,
            )
        else:
            self.result = None
            self._restore_foreground()
            self._toast("코드 인식 중…", anchor=rect, duration=0)
        threading.Thread(target=self._recognize, args=(seq, crop), daemon=True).start()

    def _save_png(self, image) -> Path | None:
        if not self.cfg.behavior.save_png:
            return None
        try:
            folder = self.cfg.output_path
            folder.mkdir(parents=True, exist_ok=True)
            stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            path = folder / f"shot_{stamp}.png"
            image.save(path)
            return path
        except OSError:
            log.exception("PNG 저장 실패")
            return None

    def _recognize(self, seq: int, image) -> None:
        try:
            result = ocr.run(image, self.cfg)
        except Exception as exc:  # noqa: BLE001
            log.exception("OCR 실패")
            self.queue.put(("ocr", seq, None, str(exc)))
            return
        log.info(
            "OCR 완료 backend=%s %.2fs lines=%d chars=%d",
            result.backend,
            result.elapsed,
            result.line_count,
            result.char_count,
        )
        if result.text and self.cfg.behavior.save_text:
            try:
                folder = self.cfg.output_path
                folder.mkdir(parents=True, exist_ok=True)
                stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
                (folder / f"code_{stamp}.txt").write_text(result.text, encoding="utf-8")
            except OSError:
                log.exception("텍스트 저장 실패")
        self.queue.put(("ocr", seq, result, None))

    def _on_ocr(self, seq: int, result, error) -> None:
        if seq != self._seq:
            return

        if self.cfg.behavior.show_result_window:
            window = self.result
            if window is None or window.closed:
                return
            if error:
                window.show_error(error)
            else:
                self.last_result = result
                window.show_result(result)
            return

        # 창 없이: 곧바로 클립보드로
        if error:
            log.error("OCR 오류: %s", error)
            self._toast(
                "인식 실패 · " + _first_line(error),
                kind="error",
                anchor=self.last_anchor,
                duration=4500,
            )
            return

        self.last_result = result
        if not result.text:
            self._toast(
                "텍스트를 찾지 못했습니다 · 조금 더 크게 캡처해 보세요",
                kind="warn",
                anchor=self.last_anchor,
                duration=3200,
            )
            return

        if self._copy_text(result.text):
            self._toast(f"복사됨 · {result.line_count}줄", kind="ok", anchor=self.last_anchor)
        else:
            log.error("클립보드 복사 실패 — 결과 창으로 대체합니다")
            self._open_last_window()

    # --------------------------------------------------------------- helpers

    def _toast(
        self,
        text: str,
        *,
        kind: str = "info",
        anchor: Rect | None = None,
        duration: int = 1500,
    ) -> None:
        if not self.cfg.behavior.show_toast:
            return
        try:
            self.toast.show(
                text,
                kind=kind,
                anchor=anchor,
                monitor=self._monitor_for(anchor),
                duration=duration,
            )
        except tk.TclError:
            pass
        except Exception:  # noqa: BLE001
            log.exception("알림 표시 실패")

    def _monitor_for(self, rect: Rect | None) -> Rect | None:
        if rect is None:
            return None
        for monitor in self._monitors:
            if monitor.intersects(rect):
                return monitor
        return None

    def _copy_text(self, text: str) -> bool:
        try:
            if clipboard.copy_text(text, self.root.winfo_id()):
                return True
        except Exception:  # noqa: BLE001
            log.exception("Win32 클립보드 복사 실패")
        # 마지막 수단: Tk 클립보드 (Win+V 기록에는 안 남을 수 있음)
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update_idletasks()
            return True
        except tk.TclError:
            log.exception("클립보드 복사 실패")
            return False

    def _show_last(self) -> None:
        if self.last_result is None or not self.last_result.text:
            self._toast("아직 복사된 결과가 없습니다", kind="warn")
            return
        self._open_last_window()

    def _open_last_window(self, *, copy: bool = False) -> None:
        result = self.last_result
        if result is None or not result.text:
            self._toast("아직 복사된 결과가 없습니다", kind="warn")
            return
        self._dismiss_result()
        self._remember_foreground()
        self.result = ResultWindow(
            self.root,
            self.cfg,
            anchor=self.last_anchor,
            png_path=self.last_png,
            on_recapture=self.begin_capture,
            on_closed=self._restore_foreground,
        )
        self.result.show_result(result, copy=copy)

    def _remember_foreground(self) -> None:
        if not self._prev_hwnd:
            self._prev_hwnd = winfocus.get_foreground()

    def _dismiss_result(self) -> None:
        if self.result is not None and not self.result.closed:
            self.result.close()
        self.result = None

    def _show_error(self, message: str) -> None:
        if not self.cfg.behavior.show_result_window:
            self._restore_foreground()
            self._toast(
                "오류 · " + _first_line(message),
                kind="error",
                duration=5000,
            )
            return
        self._dismiss_result()
        self._remember_foreground()
        self.result = ResultWindow(
            self.root,
            self.cfg,
            anchor=None,
            png_path=None,
            on_closed=self._restore_foreground,
        )
        self.result.show_error(message)

    def _open(self, what: str) -> None:
        target = config.CONFIG_PATH if what == "config" else self.cfg.output_path
        try:
            if what == "folder":
                target.mkdir(parents=True, exist_ok=True)
            os.startfile(str(target))  # noqa: S606
        except OSError:
            log.exception("열기 실패: %s", target)

    def quit(self) -> None:
        log.info("종료")
        self._disarm_escape()
        self.hotkeys.stop()
        if self.tray is not None:
            self.tray.stop()
        self.toast.close()
        self._dismiss_result()
        try:
            self.root.quit()
            self.root.destroy()
        except tk.TclError:
            pass


# ----------------------------------------------------------------------- cli


def run_from_image(path: Path, cfg: AppConfig) -> int:
    from PIL import Image

    image = Image.open(path).convert("RGB")
    try:
        result = ocr.run(image, cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 1
    print(
        f"# backend={result.backend} language={result.language} "
        f"elapsed={result.elapsed:.2f}s words={result.word_count} size={result.image_size}"
    )
    for warning in result.warnings:
        print(f"# warning: {warning}")
    print(result.text)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="screenshot-to-text", description="F12를 누를 때만 코드 스크린샷을 텍스트로 변환")
    parser.add_argument("--hotkey", help="캡처 단축키 (기본: config.json 값, f12)")
    parser.add_argument("--backend", choices=["auto", "rapid", "winocr", "vision", "tesseract"], help="OCR 백엔드 강제 지정")
    parser.add_argument("--from-image", type=Path, help="파일을 바로 OCR 해서 stdout 으로 출력 (테스트용)")
    parser.add_argument("--no-tray", action="store_true", help="트레이 아이콘 사용 안 함")
    parser.add_argument("--no-hotkey", action="store_true", help="전역 단축키 사용 안 함")
    parser.add_argument("--verbose", "-v", action="store_true", help="콘솔에 로그 출력")
    parser.add_argument("--version", action="version", version=f"screenshot-to-text {__version__}")
    args = parser.parse_args(argv)

    cfg = config.load()
    if args.hotkey:
        cfg.hotkey = args.hotkey
    if args.backend:
        cfg.ocr.backend = args.backend
    if args.no_tray:
        cfg.tray = False
    if args.no_hotkey:
        cfg.hotkey = ""
        cfg.quit_hotkey = ""

    setup_logging(args.verbose or bool(args.from_image))
    enable_dpi_awareness()

    if args.from_image:
        if sys.stdout is not None:
            try:
                sys.stdout.reconfigure(errors="replace")
            except (AttributeError, ValueError):
                pass
        return run_from_image(args.from_image, cfg)

    lock = single_instance_lock()
    if lock is None:
        log.info("이미 실행 중입니다.")
        try:
            root = tk.Tk()
            root.withdraw()
            from tkinter import messagebox

            messagebox.showinfo(
                "Screenshot to Text",
                "이미 실행 중입니다.\n화면 오른쪽 아래 트레이 아이콘을 확인하세요.",
            )
            root.destroy()
        except tk.TclError:
            pass
        return 0

    log.info("시작 v%s backend=%s hotkey=%s", __version__, cfg.ocr.backend, cfg.hotkey)
    app = App(cfg)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
