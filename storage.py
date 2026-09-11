"""JSON-backed storage for admin credentials and tag -> song assignments.

A simple JSON file is sufficient for this use case (a handful of tags/songs on
a single-user home device) and avoids adding a database dependency.
"""
import json
import os
import threading
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Optional

from werkzeug.security import generate_password_hash

from config import DATA_FILE, SONGS_DIR

_lock = threading.Lock()

DEFAULT_PLAYBACK_START = "08:00"
DEFAULT_PLAYBACK_END = "22:00"
DEFAULT_AUDIO_OUTPUT = "headphones"  # Pi's 3.5mm aux jack
AUDIO_OUTPUTS = ("auto", "headphones", "hdmi")
DEFAULT_PLAY_DURATION_SECONDS = 0  # 0 = play the full song, no auto fade-out
DEFAULT_FADE_SECONDS = 5

_DEFAULT_DATA = {
    "admin_password_hash": None,
    # uid -> {"song": "<filename in SONGS_DIR>", "label": "<friendly name>"}
    "tags": {},
    "playback_start": DEFAULT_PLAYBACK_START,
    "playback_end": DEFAULT_PLAYBACK_END,
    "audio_output": DEFAULT_AUDIO_OUTPUT,
    "play_duration_seconds": DEFAULT_PLAY_DURATION_SECONDS,
    "fade_seconds": DEFAULT_FADE_SECONDS,
}


def _read() -> dict:
    if not DATA_FILE.exists():
        return dict(_DEFAULT_DATA)
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("admin_password_hash", None)
    data.setdefault("tags", {})
    data.setdefault("playback_start", DEFAULT_PLAYBACK_START)
    data.setdefault("playback_end", DEFAULT_PLAYBACK_END)
    data.setdefault("audio_output", DEFAULT_AUDIO_OUTPUT)
    data.setdefault("play_duration_seconds", DEFAULT_PLAY_DURATION_SECONDS)
    data.setdefault("fade_seconds", DEFAULT_FADE_SECONDS)
    return data


def _write(data: dict) -> None:
    tmp_path = DATA_FILE.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp_path, DATA_FILE)
    try:
        DATA_FILE.chmod(0o600)
    except OSError:
        pass


def get_admin_password_hash() -> Optional[str]:
    with _lock:
        return _read().get("admin_password_hash")


def set_admin_password(password: str) -> None:
    with _lock:
        data = _read()
        data["admin_password_hash"] = generate_password_hash(password)
        _write(data)


def get_tags() -> dict:
    with _lock:
        return _read()["tags"]


def get_playback_window() -> tuple[str, str]:
    """Returns (start, end) as "HH:MM" strings."""
    with _lock:
        data = _read()
        return data["playback_start"], data["playback_end"]


def set_playback_window(start: str, end: str) -> None:
    dt_time.fromisoformat(start)
    dt_time.fromisoformat(end)
    with _lock:
        data = _read()
        data["playback_start"] = start
        data["playback_end"] = end
        _write(data)


def is_within_playback_window(now: Optional[dt_time] = None) -> bool:
    start_str, end_str = get_playback_window()
    start = dt_time.fromisoformat(start_str)
    end = dt_time.fromisoformat(end_str)
    now = now or datetime.now().time()
    if start <= end:
        return start <= now <= end
    # Window wraps past midnight (e.g. 22:00 -> 08:00).
    return now >= start or now <= end


def get_audio_output() -> str:
    with _lock:
        return _read()["audio_output"]


def set_audio_output(output: str) -> None:
    if output not in AUDIO_OUTPUTS:
        raise ValueError(f"Invalid audio output: {output!r}")
    with _lock:
        data = _read()
        data["audio_output"] = output
        _write(data)


def get_fade_settings() -> tuple[int, int]:
    """Returns (play_duration_seconds, fade_seconds). A play_duration of 0
    means the song plays in full with no auto fade-out."""
    with _lock:
        data = _read()
        return data["play_duration_seconds"], data["fade_seconds"]


def set_fade_settings(play_duration_seconds: int, fade_seconds: int) -> None:
    if play_duration_seconds < 0 or fade_seconds < 0:
        raise ValueError("Durations must be zero or positive")
    with _lock:
        data = _read()
        data["play_duration_seconds"] = play_duration_seconds
        data["fade_seconds"] = fade_seconds
        _write(data)


def get_song_for_tag(uid: str) -> Optional[str]:
    with _lock:
        entry = _read()["tags"].get(uid)
        return entry["song"] if entry else None


def assign_tag(uid: str, song_filename: str, label: str = "") -> None:
    with _lock:
        data = _read()
        data["tags"][uid] = {"song": song_filename, "label": label}
        _write(data)


def unassign_tag(uid: str) -> None:
    with _lock:
        data = _read()
        data["tags"].pop(uid, None)
        _write(data)


def list_songs() -> list[str]:
    return sorted(p.name for p in SONGS_DIR.glob("*.mp3"))


def delete_song(filename: str) -> None:
    """Remove a song file and any tag assignments pointing to it."""
    safe_name = Path(filename).name
    song_path = SONGS_DIR / safe_name
    with _lock:
        data = _read()
        data["tags"] = {
            uid: entry for uid, entry in data["tags"].items() if entry["song"] != safe_name
        }
        _write(data)
    if song_path.exists() and song_path.is_file():
        song_path.unlink()
