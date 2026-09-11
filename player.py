"""Plays MP3 files on the wired speaker via the system's ALSA default output
using pygame's mixer.
"""
import logging
import subprocess
import threading

import pygame

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_initialized = False
_current_song: str | None = None

# Raspberry Pi's onboard audio (bcm2835) exposes a "PCM Playback Route" control
# that forces output to the analog 3.5mm aux jack, HDMI, or lets ALSA pick.
_AUDIO_ROUTE_NUMID = {"auto": "0", "headphones": "1", "hdmi": "2"}


def set_output_device(output: str) -> None:
    """Force audio output to the Pi's aux jack ("headphones"), HDMI, or "auto".

    No-op (with a log message) on non-Pi systems where the `amixer` control
    doesn't exist.
    """
    numid = _AUDIO_ROUTE_NUMID.get(output)
    if numid is None:
        logger.warning("Unknown audio output %r; ignoring", output)
        return
    try:
        subprocess.run(
            ["amixer", "cset", "numid=3", numid],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info("Set audio output route to %s", output)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        logger.warning("Could not set audio output route (expected off-Pi): %s", exc)


def _ensure_init() -> None:
    global _initialized
    if not _initialized:
        pygame.mixer.init()
        _initialized = True



def play(filepath: str) -> None:
    """Stop whatever is playing and start playing filepath from the beginning."""
    global _current_song
    with _lock:
        _ensure_init()
        try:
            pygame.mixer.music.load(filepath)
            pygame.mixer.music.play()
            _current_song = filepath
            logger.info("Playing %s", filepath)
        except pygame.error:
            logger.exception("Failed to play %s", filepath)


def stop() -> None:
    global _current_song
    with _lock:
        if _initialized:
            pygame.mixer.music.stop()
        _current_song = None


def is_busy() -> bool:
    with _lock:
        return _initialized and pygame.mixer.music.get_busy()


def current_song() -> str | None:
    with _lock:
        return _current_song
