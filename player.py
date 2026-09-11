"""Plays MP3 files on the wired speaker via the system's ALSA default output
using pygame's mixer.
"""
import logging
import subprocess
import threading

import pygame

import storage

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_initialized = False
_current_song: str | None = None
_paused = False
_fade_timer: threading.Timer | None = None

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


def _cancel_fade_timer_locked() -> None:
    global _fade_timer
    if _fade_timer is not None:
        _fade_timer.cancel()
        _fade_timer = None


def _do_fadeout(fade_ms: int) -> None:
    with _lock:
        if _initialized:
            pygame.mixer.music.fadeout(fade_ms)
        logger.info("Fading out after configured play duration")


def _schedule_fadeout_locked() -> None:
    """Start a timer that fades the current song out after the configured
    play duration. A duration of 0 means "play the whole song"."""
    global _fade_timer
    _cancel_fade_timer_locked()
    play_duration, fade_seconds = storage.get_fade_settings()
    if play_duration <= 0:
        return
    _fade_timer = threading.Timer(play_duration, _do_fadeout, args=(fade_seconds * 1000,))
    _fade_timer.daemon = True
    _fade_timer.start()


def play(filepath: str) -> None:
    """Stop whatever is playing and start playing filepath from the beginning."""
    global _current_song, _paused
    with _lock:
        _ensure_init()
        try:
            _cancel_fade_timer_locked()
            pygame.mixer.music.load(filepath)
            pygame.mixer.music.play()
            _current_song = filepath
            _paused = False
            logger.info("Playing %s", filepath)
            _schedule_fadeout_locked()
        except pygame.error:
            logger.exception("Failed to play %s", filepath)


def stop() -> None:
    global _current_song, _paused
    with _lock:
        _cancel_fade_timer_locked()
        if _initialized:
            pygame.mixer.music.stop()
        _current_song = None
        _paused = False


def toggle_pause() -> bool:
    """Pause if playing, resume if paused. Returns the resulting paused state."""
    global _paused
    with _lock:
        if not _initialized or not _current_song:
            return _paused
        if _paused:
            pygame.mixer.music.unpause()
            _paused = False
        else:
            pygame.mixer.music.pause()
            _paused = True
        return _paused


def is_paused() -> bool:
    with _lock:
        return _paused


def is_busy() -> bool:
    with _lock:
        return _initialized and pygame.mixer.music.get_busy()


def current_song() -> str | None:
    global _current_song
    with _lock:
        # Clear stale state once a song finishes naturally or fades out fully.
        if _initialized and _current_song and not _paused and not pygame.mixer.music.get_busy():
            _current_song = None
        return _current_song



def current_song() -> str | None:
    with _lock:
        return _current_song
