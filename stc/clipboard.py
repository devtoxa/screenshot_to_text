"""Windows 클립보드에 실제 데이터를 올린다 (Win+V 기록 호환).

Tk 의 ``clipboard_append`` 는 지연 렌더링(delayed rendering) 방식이라
Windows 11 클립보드 기록(Win+V)에 항목이 남지 않는다. Win32 API 로
CF_UNICODETEXT 를 직접 넣으면 다른 앱은 물론 클립보드 기록에서도
바로 붙여넣을 수 있다.
"""

from __future__ import annotations

import ctypes
import logging
import time
from ctypes import wintypes

log = logging.getLogger(__name__)

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

# 다른 앱이 클립보드를 잡고 있을 때를 대비한 재시도
OPEN_RETRIES = 12
OPEN_RETRY_DELAY = 0.02

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_user32.OpenClipboard.argtypes = [wintypes.HWND]
_user32.OpenClipboard.restype = wintypes.BOOL
_user32.EmptyClipboard.argtypes = []
_user32.EmptyClipboard.restype = wintypes.BOOL
_user32.CloseClipboard.argtypes = []
_user32.CloseClipboard.restype = wintypes.BOOL
_user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
_user32.SetClipboardData.restype = wintypes.HANDLE
_user32.GetClipboardData.argtypes = [wintypes.UINT]
_user32.GetClipboardData.restype = wintypes.HANDLE
_user32.GetDesktopWindow.argtypes = []
_user32.GetDesktopWindow.restype = wintypes.HWND

_kernel32.GetConsoleWindow.argtypes = []
_kernel32.GetConsoleWindow.restype = wintypes.HWND

_kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
_kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
_kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalLock.restype = ctypes.c_void_p
_kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalUnlock.restype = wintypes.BOOL
_kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalFree.restype = wintypes.HGLOBAL


def normalize(text: str) -> str:
    """클립보드 표준인 CRLF 로 통일한다."""
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")


def _open_clipboard(hwnd: int | None) -> bool:
    for attempt in range(OPEN_RETRIES):
        if _user32.OpenClipboard(hwnd):
            return True
        if attempt + 1 < OPEN_RETRIES:
            time.sleep(OPEN_RETRY_DELAY)
    return False


def _fallback_owner() -> int:
    """창 없이 호출될 때 쓸 클립보드 소유자 핸들.

    EmptyClipboard 이후 소유자가 NULL 이면 SetClipboardData 가 실패하므로
    콘솔 창(없으면 데스크톱 창)을 소유자로 넘긴다.
    """
    return _kernel32.GetConsoleWindow() or _user32.GetDesktopWindow()


def copy_text(text: str, hwnd: int | None = None) -> bool:
    """텍스트를 Windows 클립보드(CF_UNICODETEXT)에 복사한다."""
    if not text:
        return False

    payload = normalize(text).encode("utf-16-le") + b"\x00\x00"
    handle = _kernel32.GlobalAlloc(GMEM_MOVEABLE, len(payload))
    if not handle:
        log.error("GlobalAlloc 실패 (err=%s)", ctypes.get_last_error())
        return False

    pointer = _kernel32.GlobalLock(handle)
    if not pointer:
        _kernel32.GlobalFree(handle)
        log.error("GlobalLock 실패 (err=%s)", ctypes.get_last_error())
        return False
    try:
        ctypes.memmove(pointer, payload, len(payload))
    finally:
        _kernel32.GlobalUnlock(handle)

    if not _open_clipboard(hwnd or _fallback_owner()):
        _kernel32.GlobalFree(handle)
        log.error("클립보드를 열 수 없습니다")
        return False

    owned = True
    try:
        if not _user32.EmptyClipboard():
            log.error("EmptyClipboard 실패 (err=%s)", ctypes.get_last_error())
            return False
        if not _user32.SetClipboardData(CF_UNICODETEXT, handle):
            log.error("SetClipboardData 실패 (err=%s)", ctypes.get_last_error())
            return False
        owned = False  # 소유권이 클립보드로 넘어갔다
        return True
    finally:
        _user32.CloseClipboard()
        if owned:
            _kernel32.GlobalFree(handle)


def read_text() -> str | None:
    """클립보드의 텍스트를 읽는다 (확인/테스트용)."""
    if not _open_clipboard(None):
        return None
    try:
        handle = _user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        pointer = _kernel32.GlobalLock(handle)
        if not pointer:
            return None
        try:
            return ctypes.wstring_at(pointer)
        finally:
            _kernel32.GlobalUnlock(handle)
    finally:
        _user32.CloseClipboard()
