"""Background thread that polls the RC522 NFC reader (SPI) for tags.

On a real Raspberry Pi this uses the `mfrc522` + `RPi.GPIO` libraries. When
those aren't available (e.g. running the web app on a dev machine), a no-op
stub reader is used instead so the rest of the app still works.
"""
import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

try:
    from mfrc522 import SimpleMFRC522
    import RPi.GPIO as GPIO

    _HARDWARE_AVAILABLE = True
except (ImportError, RuntimeError):
    _HARDWARE_AVAILABLE = False


class NfcReader:
    """Polls for NFC tags on a background thread and invokes a callback per scan."""

    def __init__(self, on_scan: Callable[[str], None], poll_interval: float = 0.3):
        self._on_scan = on_scan
        self._poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._reader = SimpleMFRC522() if _HARDWARE_AVAILABLE else None

    @property
    def hardware_available(self) -> bool:
        return _HARDWARE_AVAILABLE

    def start(self) -> None:
        if not _HARDWARE_AVAILABLE:
            logger.warning(
                "mfrc522/RPi.GPIO not available; NFC reading is disabled "
                "(this is expected when not running on a Raspberry Pi)."
            )
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
        if _HARDWARE_AVAILABLE:
            GPIO.cleanup()

    def _run(self) -> None:
        last_uid = None
        last_time = 0.0
        debounce_seconds = 2.0
        while not self._stop_event.is_set():
            try:
                # read_no_block avoids blocking forever so we can check _stop_event.
                uid, _text = self._reader.read_no_block()
            except Exception:
                logger.exception("Error reading NFC tag")
                uid = None
            if uid is not None:
                uid_str = str(uid)
                now = time.monotonic()
                if uid_str != last_uid or (now - last_time) > debounce_seconds:
                    last_uid = uid_str
                    last_time = now
                    try:
                        self._on_scan(uid_str)
                    except Exception:
                        logger.exception("Error handling scanned tag %s", uid_str)
            else:
                last_uid = None
            time.sleep(self._poll_interval)
