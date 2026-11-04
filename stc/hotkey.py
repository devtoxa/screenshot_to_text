"""전역 단축키 (Win32 저수준 키보드 훅, 최소 간섭).

`keyboard` 라이브러리는 단축키를 가로채기 위해 모든 키 이벤트를 자체 상태
머신으로 재생/필터링해서 Alt+Tab 같은 조합키가 가끔 꼬이는 문제가 있었다.
여기서는 **등록한 단축키의 키만** 삼키고, 나머지 키는 그대로 통과시킨다.
(수정키 상태를 건드리지 않으므로 Ctrl/Alt/Win/Alt+Tab 에 영향을 주지 않음)
"""

from __future__ import annotations

import ctypes
import logging
import time
from ctypes import wintypes

log = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

VK_CONTROL = 0x11
VK_MENU = 0x12
VK_SHIFT = 0x10
VK_LWIN = 0x5B
VK_RWIN = 0x5C

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_MASK = MOD_ALT | MOD_CONTROL | MOD_SHIFT | MOD_WIN


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

_MODIFIERS = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "windows": MOD_WIN,
}

_KEYS = {
    "esc": 0x1B,
    "escape": 0x1B,
    "enter": 0x0D,
    "return": 0x0D,
    "space": 0x20,
    "tab": 0x09,
    "backspace": 0x08,
    "delete": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "pause": 0x13,
    "printscreen": 0x2C,
}
for _i in range(1, 25):
    _KEYS[f"f{_i}"] = 0x6F + _i


def parse(combo: str) -> tuple[int, int]:
    """'ctrl+alt+q', 'f12' 같은 문자열을 (modifiers, virtual_key) 로 바꾼다."""
    parts = [part.strip().lower() for part in (combo or "").split("+") if part.strip()]
    if not parts:
        raise ValueError("단축키가 비어 있습니다.")

    modifiers = 0
    key = None
    for part in parts:
        if part in _MODIFIERS:
            modifiers |= _MODIFIERS[part]
        elif part in _KEYS:
            key = _KEYS[part]
        elif len(part) == 1 and part.isalnum():
            key = ord(part.upper())
        else:
            raise ValueError(f"알 수 없는 키 이름: {part}")
    if key is None:
        raise ValueError(f"단축키에 키가 없습니다: {combo}")
    return modifiers, key


def _pressed_modifiers() -> int:
    modifiers = 0
    if user32.GetAsyncKeyState(VK_CONTROL) & 0x8000:
        modifiers |= MOD_CONTROL
    if user32.GetAsyncKeyState(VK_MENU) & 0x8000:
        modifiers |= MOD_ALT
    if user32.GetAsyncKeyState(VK_SHIFT) & 0x8000:
        modifiers |= MOD_SHIFT
    if (user32.GetAsyncKeyState(VK_LWIN) & 0x8000) or (
        user32.GetAsyncKeyState(VK_RWIN) & 0x8000
    ):
        modifiers |= MOD_WIN
    return modifiers


class HotkeyManager:
    """저수준 키보드 훅으로 등록된 키만 가로챈다."""

    def __init__(self) -> None:
        self._hook = 0
        self._callbacks: dict[int, tuple[int, int, callable]] = {}
        self._swallowed: set[int] = set()
        self._swallow_time: dict[int, float] = {}
        self._error: str | None = None
        self._hook_ref = HOOKPROC(self._on_key)

    @property
    def error(self) -> str | None:
        return self._error

    def start(self) -> bool:
        if self._hook:
            return True
        try:
            hinstance = kernel32.GetModuleHandleW(None)
            hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._hook_ref, hinstance, 0)
            if not hook:
                raise OSError(f"SetWindowsHookExW 실패 ({ctypes.get_last_error()})")
            self._hook = int(hook)
            self._error = None
            log.info("키보드 훅 시작")
            return True
        except Exception as exc:  # noqa: BLE001
            self._error = str(exc)
            log.exception("키보드 훅 시작 실패")
            return False

    def _on_key(self, n_code, w_param, l_param):
        try:
            if n_code == 0:
                info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                vk = int(info.vkCode)
                if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    if vk in self._swallowed:
                        # key-up 을 놓쳤더라도 영구적으로 키가 막히지 않게 한다.
                        if time.monotonic() - self._swallow_time.get(vk, 0.0) < 2.0:
                            return 1
                        self._swallowed.discard(vk)
                    pressed = _pressed_modifiers()
                    for modifiers, key, callback in list(self._callbacks.values()):
                        if key != vk:
                            continue
                        if (pressed & MOD_MASK) != (modifiers & MOD_MASK):
                            continue
                        self._swallowed.add(vk)
                        self._swallow_time[vk] = time.monotonic()
                        try:
                            callback()
                        except Exception:  # noqa: BLE001
                            log.exception("단축키 콜백 오류")
                        return 1
                elif w_param in (WM_KEYUP, WM_SYSKEYUP) and vk in self._swallowed:
                    self._swallowed.discard(vk)
                    return 1
        except Exception:  # noqa: BLE001
            log.exception("키보드 훅 처리 오류")
        return user32.CallNextHookEx(0, n_code, w_param, l_param)

    def register(self, combo: str, callback, hotkey_id: int) -> None:
        modifiers, key = parse(combo)
        self._callbacks[hotkey_id] = (modifiers, key, callback)
        log.info("전역 단축키 등록: %s", combo)

    def unregister(self, hotkey_id: int) -> None:
        self._callbacks.pop(hotkey_id, None)

    def stop(self) -> None:
        self._callbacks.clear()
        self._swallowed.clear()
        if self._hook:
            user32.UnhookWindowsHookEx(wintypes.HHOOK(self._hook))
            self._hook = 0
