# nfc-walk-out-music

Raspberry Pi "walk-out music" player: scan an NFC tag to play its assigned MP3
on a wired speaker. Songs are uploaded and assigned to tags through a
password-protected, HTTPS web interface running on the Pi.

## Hardware

- Raspberry Pi (any model with a 3.5mm aux/headphone jack)
- A wired (passive/powered) speaker plugged into the Pi's 3.5mm aux jack
- MFRC522 RC522 NFC/RFID reader wired to the Pi's SPI pins:

  | RC522 pin | Pi pin (BCM)      |
  |-----------|-------------------|
  | SDA       | GPIO8 (CE0)       |
  | SCK       | GPIO11 (SCLK)     |
  | MOSI      | GPIO10 (MOSI)     |
  | MISO      | GPIO9 (MISO)      |
  | RST       | GPIO25            |
  | GND       | GND               |
  | 3.3V      | 3.3V              |

Enable SPI first: `sudo raspi-config` → *Interface Options* → *SPI* → enable, then reboot.

### Connecting the speaker via the aux jack

Plug the speaker into the Pi's 3.5mm audio-out jack. The web UI's **Speaker
output** setting (under the dashboard) controls the Pi's audio routing via
`amixer` and defaults to **Aux / headphone jack**, so no extra configuration
is normally required. If you ever need to change it manually on the Pi:

```bash
amixer cset numid=3 1   # 1 = force aux/headphone jack, 2 = HDMI, 0 = auto
```

## Install (on the Pi)

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip libasound2-dev mpg123
git clone <this-repo-url> nfc-walk-out-music
cd nfc-walk-out-music
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Add your user to the groups needed for GPIO/SPI/audio access instead of running as root:

```bash
sudo usermod -aG gpio,spi,audio $USER
```

### First-time setup: create the admin password

The web UI is protected by a single admin account. Set its password once:

```bash
flask --app app.py init-admin
```

This stores a salted hash in `instance/tags.json` — the plaintext password is
never saved. You can also set `ADMIN_USERNAME` in a `.env` file to change the
username (defaults to `admin`).

### Run it

```bash
python app.py
```

This starts the web UI on `https://<pi-ip>:8443` (self-signed TLS certificate
by default — your browser will show a one-time warning) and starts polling
the NFC reader in the background.

To run permanently on boot, install the provided systemd unit:

```bash
sudo cp systemd/nfc-walkout-music.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nfc-walkout-music
```

Edit the `User=` and `WorkingDirectory=`/`ExecStart=` paths in the service
file first if your username or install path differ from `pi` /
`/home/pi/nfc-walk-out-music`.

## Using the web interface

1. Connect the Pi to your home Wi-Fi (`sudo raspi-config` or `nmtui`).
2. Browse to `https://<pi-ip>:8443` from any device on the same network and
   log in with the admin credentials.
3. Upload MP3s under **Upload a song**.
4. Under **Assign a tag**, click **Listen for tag scan**, tap the NFC tag on
   the reader, pick a song, and click **Assign**.
5. Scanning that tag from then on will stop whatever is playing and start
   the assigned song on the wired speaker.

## Security notes

- The web UI is only ever exposed on your home LAN — do **not** port-forward
  it to the internet. If you need remote access, use a VPN (e.g. WireGuard/
  Tailscale) rather than exposing port 8443 directly.
- Login is required for every management action (upload, assign, delete);
  sessions use secure, HTTP-only cookies and all forms are CSRF-protected.
- Uploads are restricted to `.mp3` files, filenames are sanitized, and a
  64&nbsp;MB upload size limit is enforced.
- The self-signed certificate encrypts traffic on your LAN but will show a
  browser warning; replace `instance/cert.pem` / `instance/key.pem` with a
  real certificate if you want to avoid that.
- Change the default admin password immediately via `flask --app app.py
  init-admin` before exposing the Pi on your network.

## Project layout

- `app.py` — Flask web app (auth, upload, tag assignment, capture API)
- `nfc_reader.py` — background thread polling the RC522 reader
- `player.py` — MP3 playback via `pygame.mixer` / ALSA
- `storage.py` — JSON-backed tag/song/admin-password storage
- `forms.py` — WTForms definitions (CSRF + validation)
- `templates/`, `static/` — web UI
- `systemd/nfc-walkout-music.service` — run-on-boot service unit
