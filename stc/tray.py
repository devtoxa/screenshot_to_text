"""트레이 아이콘 (pystray). 설치되어 있지 않으면 조용히 비활성화된다."""

from __future__ import annotations

import logging

from PIL import Image

log = logging.getLogger(__name__)


class Tray:
    def __init__(
        self,
        image: Image.Image,
        *,
        on_capture,
        on_open_folder,
        on_open_config,
        on_quit,
        on_show_last=None,
    ) -> None:
        import pystray

        items = [
            pystray.MenuItem("캡처 시작 (F12)", lambda: on_capture(), default=True),
        ]
        if on_show_last is not None:
            items.append(pystray.MenuItem("마지막 결과 보기", lambda: on_show_last()))
        items += [
            pystray.MenuItem("캡처 폴더 열기", lambda: on_open_folder()),
            pystray.MenuItem("설정 파일 열기", lambda: on_open_config()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("종료", lambda: on_quit()),
        ]

        self._icon = pystray.Icon(
            "screenshot_to_code",
            image,
            "Screenshot to Code  ·  F12",
            menu=pystray.Menu(*items),
        )
        self._running = False

    def start(self) -> None:
        self._icon.run_detached()
        self._running = True
        log.info("트레이 아이콘 시작")

    def notify(self, message: str) -> None:
        try:
            self._icon.notify(message, "Screenshot to Code")
        except Exception:  # noqa: BLE001
            pass

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        try:
            self._icon.stop()
        except Exception:  # noqa: BLE001
            pass
