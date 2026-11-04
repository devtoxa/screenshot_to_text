"""Windows 포커스/창 핸들 다루기.

오버레이가 화면을 덮는 동안에만 포커스를 가져오고, 끝나면 원래 창으로
포커스를 돌려주기 위한 유틸. (포커스가 남의 창에 남아 키 입력이 먹통이 되는 문제 방지)
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# 64비트에서 HWND 가 잘리지 않도록 시그니처를 명시한다.
user32.GetForegroundWindow.restype = wintypes.HWND
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.AttachThreadInput.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.BringWindowToTop.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

GA_ROOT = 2


def hwnd_of(window) -> int:
    """Tk 위젯(창)의 최상위 HWND."""
    try:
        frame = window.wm_frame()
        hwnd = int(frame, 16) if frame else 0
        if not hwnd:
            hwnd = int(window.winfo_id())
        top = user32.GetAncestor(wintypes.HWND(hwnd), GA_ROOT)
        return int(top or hwnd)
    except Exception:  # noqa: BLE001
        return 0


def get_foreground() -> int:
    try:
        return int(user32.GetForegroundWindow() or 0)
    except Exception:  # noqa: BLE001
        return 0


def is_window(hwnd: int) -> bool:
    if not hwnd:
        return False
    try:
        return bool(user32.IsWindow(wintypes.HWND(hwnd)))
    except Exception:  # noqa: BLE001
        return False


def force_foreground(hwnd: int) -> bool:
    """다른 스레드의 창이어도 안정적으로 포그라운드로 가져온다."""
    if not is_window(hwnd):
        return False
    try:
        if get_foreground() == hwnd:
            return True

        target = wintypes.HWND(hwnd)
        current = kernel32.GetCurrentThreadId()
        threads = {
            user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None),
            user32.GetWindowThreadProcessId(target, None),
        }
        attached: list[int] = []
        for thread in threads:
            if thread and thread != current:
                if user32.AttachThreadInput(current, thread, True):
                    attached.append(thread)
        try:
            user32.BringWindowToTop(target)
            user32.SetForegroundWindow(target)
            return get_foreground() == hwnd
        finally:
            for thread in attached:
                user32.AttachThreadInput(current, thread, False)
    except Exception:  # noqa: BLE001
        return False
