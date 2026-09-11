"""Application configuration loaded from environment / .env file."""
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
SONGS_DIR = INSTANCE_DIR / "songs"
DATA_FILE = INSTANCE_DIR / "tags.json"
SECRET_KEY_FILE = INSTANCE_DIR / "secret_key"

INSTANCE_DIR.mkdir(exist_ok=True)
SONGS_DIR.mkdir(exist_ok=True)

load_dotenv(BASE_DIR / ".env")


def _load_or_create_secret_key() -> str:
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key
    if SECRET_KEY_FILE.exists():
        return SECRET_KEY_FILE.read_text().strip()
    key = secrets.token_hex(32)
    SECRET_KEY_FILE.write_text(key)
    SECRET_KEY_FILE.chmod(0o600)
    return key


class Config:
    SECRET_KEY = _load_or_create_secret_key()
    MAX_CONTENT_LENGTH = 64 * 1024 * 1024  # 64 MB upload limit
    ALLOWED_EXTENSIONS = {"mp3"}
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    # Password hash set via the `flask init-admin` CLI command (see storage.py / app.py).
    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "1") != "0"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
