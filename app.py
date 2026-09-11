"""Flask web app: secure MP3 upload + NFC tag -> song assignment.

Run directly for local testing/production on the Pi:
    python app.py

First-time setup (creates the admin password):
    flask --app app.py init-admin
"""
import logging
import os
import threading
import time
import uuid
from datetime import time as dt_time
from pathlib import Path

import click
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

import player
import storage
from config import Config, SONGS_DIR
from forms import AssignForm, AudioOutputForm, CsrfOnlyForm, LoginForm, PlaybackWindowForm, UploadForm
from nfc_reader import NfcReader

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)

login_manager = LoginManager(app)
login_manager.login_view = "login"


class AdminUser(UserMixin):
    id = "admin"


@login_manager.user_loader
def load_user(user_id):
    return AdminUser() if user_id == "admin" else None


# --- NFC scan handling -------------------------------------------------

class ScanCapture:
    """Coordinates the "wave a new tag" UI flow with the NFC polling thread."""

    def __init__(self):
        self._lock = threading.Lock()
        self.active = False
        self.uid: str | None = None

    def start(self):
        with self._lock:
            self.active = True
            self.uid = None

    def stop(self):
        with self._lock:
            self.active = False
            self.uid = None

    def offer(self, uid: str) -> bool:
        """Called by the reader thread. Returns True if the scan was consumed
        for capture (i.e. normal playback should be skipped)."""
        with self._lock:
            if self.active:
                self.uid = uid
                return True
            return False

    def poll(self):
        with self._lock:
            return self.uid


scan_capture = ScanCapture()


def handle_scan(uid: str) -> None:
    if scan_capture.offer(uid):
        logger.info("Captured tag %s for assignment", uid)
        return
    song = storage.get_song_for_tag(uid)
    if not song:
        logger.info("Unknown tag scanned: %s", uid)
        return
    if not storage.is_within_playback_window():
        start, end = storage.get_playback_window()
        logger.info("Tag %s scanned outside allowed hours (%s-%s); ignoring", uid, start, end)
        return
    song_path = SONGS_DIR / song
    if song_path.exists():
        player.play(str(song_path))
    else:
        logger.warning("Assigned song %s for tag %s is missing on disk", song, uid)


nfc_reader = NfcReader(on_scan=handle_scan)


# --- Auth routes ---------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    form = LoginForm()
    password_hash = storage.get_admin_password_hash()
    if password_hash is None:
        flash(
            "No admin password is set yet. Run 'flask --app app.py init-admin' "
            "on the Pi to create one.",
            "error",
        )
    elif form.validate_on_submit():
        if form.username.data == Config.ADMIN_USERNAME and check_password_hash(
            password_hash, form.password.data
        ):
            login_user(AdminUser())
            return redirect(url_for("index"))
        flash("Invalid username or password.", "error")
    return render_template("login.html", form=form)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# --- Main dashboard --------------------------------------------------------

@app.route("/")
@login_required
def index():
    upload_form = UploadForm()
    assign_form = AssignForm()
    assign_form.song.choices = [(s, s) for s in storage.list_songs()]
    csrf_form = CsrfOnlyForm()
    playback_start, playback_end = storage.get_playback_window()
    settings_form = PlaybackWindowForm(
        start_time=dt_time.fromisoformat(playback_start),
        end_time=dt_time.fromisoformat(playback_end),
    )
    audio_output_form = AudioOutputForm(output=storage.get_audio_output())
    return render_template(
        "index.html",
        songs=storage.list_songs(),
        tags=storage.get_tags(),
        upload_form=upload_form,
        assign_form=assign_form,
        csrf_form=csrf_form,
        settings_form=settings_form,
        audio_output_form=audio_output_form,
        now_playing=(Path(player.current_song()).name if player.current_song() else None),
        hardware_available=nfc_reader.hardware_available,
    )


@app.route("/settings", methods=["POST"])
@login_required
def settings():
    form = PlaybackWindowForm()
    if not form.validate_on_submit():
        for field_errors in form.errors.values():
            for err in field_errors:
                flash(err, "error")
        return redirect(url_for("index"))
    storage.set_playback_window(
        form.start_time.data.strftime("%H:%M"), form.end_time.data.strftime("%H:%M")
    )
    flash("Allowed playback hours updated.", "success")
    return redirect(url_for("index"))


@app.route("/audio_output", methods=["POST"])
@login_required
def audio_output():
    form = AudioOutputForm()
    if not form.validate_on_submit():
        for field_errors in form.errors.values():
            for err in field_errors:
                flash(err, "error")
        return redirect(url_for("index"))
    storage.set_audio_output(form.output.data)
    player.set_output_device(form.output.data)
    flash("Speaker output updated.", "success")
    return redirect(url_for("index"))


@app.route("/upload", methods=["POST"])
@login_required
def upload():
    form = UploadForm()
    if not form.validate_on_submit():
        for field_errors in form.errors.values():
            for err in field_errors:
                flash(err, "error")
        return redirect(url_for("index"))

    f = form.mp3.data
    filename = secure_filename(f.filename)
    if not filename.lower().endswith(".mp3"):
        flash("Only .mp3 files are allowed.", "error")
        return redirect(url_for("index"))

    # Avoid clobbering existing files / path traversal via a random-prefixed name.
    dest_name = f"{uuid.uuid4().hex[:8]}_{filename}"
    dest_path = (SONGS_DIR / dest_name).resolve()
    if SONGS_DIR.resolve() not in dest_path.parents:
        abort(400)

    f.save(dest_path)
    flash(f"Uploaded {filename}.", "success")
    return redirect(url_for("index"))


@app.route("/stop", methods=["POST"])
@login_required
def stop():
    form = CsrfOnlyForm()
    if not form.validate_on_submit():
        abort(400)
    player.stop()
    flash("Playback stopped.", "success")
    return redirect(url_for("index"))


@app.route("/delete_song", methods=["POST"])
@login_required
def delete_song_route():
    form = CsrfOnlyForm()
    if not form.validate_on_submit():
        abort(400)
    filename = request.form.get("filename", "")
    if filename not in storage.list_songs():
        abort(404)
    storage.delete_song(filename)
    if player.current_song() and Path(player.current_song()).name == filename:
        player.stop()
    flash(f"Deleted {filename}.", "success")
    return redirect(url_for("index"))


@app.route("/assign", methods=["POST"])
@login_required
def assign():
    form = AssignForm()
    form.song.choices = [(s, s) for s in storage.list_songs()]
    if not form.validate_on_submit():
        for field_errors in form.errors.values():
            for err in field_errors:
                flash(err, "error")
        return redirect(url_for("index"))
    storage.assign_tag(form.uid.data.strip(), form.song.data, form.label.data.strip())
    flash("Tag assigned.", "success")
    return redirect(url_for("index"))


@app.route("/unassign", methods=["POST"])
@login_required
def unassign():
    form = CsrfOnlyForm()
    if not form.validate_on_submit():
        abort(400)
    uid = request.form.get("uid", "")
    storage.unassign_tag(uid)
    flash("Tag unassigned.", "success")
    return redirect(url_for("index"))


# --- "Wave a new tag" capture API used by the assignment UI ---------------

@app.route("/api/capture/start", methods=["POST"])
@login_required
def capture_start():
    scan_capture.start()
    return jsonify({"ok": True})


@app.route("/api/capture/stop", methods=["POST"])
@login_required
def capture_stop():
    scan_capture.stop()
    return jsonify({"ok": True})


@app.route("/api/capture/status")
@login_required
def capture_status():
    return jsonify({"uid": scan_capture.poll()})


@app.route("/api/simulate_scan", methods=["POST"])
@login_required
def simulate_scan():
    """Dev-only helper: pretend a tag was scanned, for testing without real NFC hardware."""
    if nfc_reader.hardware_available:
        abort(404)
    uid = (request.get_json(silent=True) or {}).get("uid", "").strip()
    if not uid:
        abort(400)
    handle_scan(uid)
    return jsonify({"ok": True})


@app.route("/api/status")
@login_required
def status():
    song = player.current_song()
    return jsonify({"now_playing": Path(song).name if song else None})


@app.cli.command("init-admin")
@click.option("--username", default=Config.ADMIN_USERNAME, help="Admin username (set via ADMIN_USERNAME env var).")
def init_admin(username):
    """Interactively set the admin password used to log into the web UI."""
    password = click.prompt("New admin password", hide_input=True, confirmation_prompt=True)
    if len(password) < 8:
        click.echo("Password must be at least 8 characters.")
        raise SystemExit(1)
    storage.set_admin_password(password)
    click.echo(f"Admin password set for user '{username}'.")


def _start_background_services():
    player.set_output_device(storage.get_audio_output())
    nfc_reader.start()


_start_background_services()


if __name__ == "__main__":
    cert_path = Path("instance/cert.pem")
    key_path = Path("instance/key.pem")
    if cert_path.exists() and key_path.exists():
        ssl_context = (str(cert_path), str(key_path))
    else:
        # Self-signed cert generated on the fly; browsers will warn once.
        # For anything beyond home-LAN use, supply a real cert via instance/cert.pem.
        ssl_context = "adhoc"
    try:
        app.run(host="0.0.0.0", port=8443, ssl_context=ssl_context, threaded=True)
    finally:
        nfc_reader.stop()
