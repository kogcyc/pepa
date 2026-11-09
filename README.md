# Talkbench — split layout

Run `talkbench.py`. The window starts divided equally left/right.

Right half: browser at http://localhost:8000, with navigation and Reload.
The Phone Photo panel appears above the browser while the receiver is running.
Left half, from top to bottom:

- 10%: TALK, CLIP, and Phone Photo buttons, plus a small status line.
- 20%: first terminal (for the HTTP server).
- 20%: second terminal (for tissue.py).
- 50%: third terminal (for Codex).

Terminals have no header labels. Each has a Restart button, which closes
its session and opens a fresh shell after confirmation. TALK has a #008800
background and CLIP has a #990000 background, both with white text. Browser navigation, including
Reload, remains available.

Dividers are draggable; percentages describe the initial layout, excluding
splitter handles. Small window sizes respect minimum usable control sizes.
All three terminals automatically open interactive bash prompts in the folder
containing talkbench.py, regardless of the folder you launched the app from.
Your normal bash startup configuration is loaded. Any explicit cd in your
.bashrc can override the starting directory, as in an ordinary terminal.

## Install

Ubuntu / Debian / Linux Mint, in this extracted folder:

```bash
sudo apt install python3-venv xterm libportaudio2 libxcb-cursor0 libxkbcommon-x11-0
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python vpb.py
```

Existing users can keep the same virtual environment. Copy `talkbench.py`,
`phone_upload.py`, and `requirements.txt` into the project directory and rerun
`.venv/bin/pip install -r requirements.txt`.

## Use

In the first terminal, type:

```bash
python3 -m http.server 8000 --bind 127.0.0.1
```

Then press Reload in the browser. The server serves the talkbench.py directory.
The loopback binding limits access to this computer.

In the second terminal, type `python3 tissue.py`.
In the third, type `codex`.
Your own tissue.py and existing Codex CLI installation are required.
On launch, Talkbench starts the three shells at their prompts.

TALK starts microphone recording. CLIP stops it, transcribes locally,
converts spoken punctuation, and copies the text to the clipboard.
CLIP is disabled during transcription. Afterward it can copy the last
transcript again. Paste into terminals with Ctrl+Shift+V; review the text
before pressing Enter. First dictation downloads the base.en model.
Select your headset microphone in the desktop Sound settings.
Hover over the status line for full error messages or status text.

Spoken punctuation includes comma, period, full stop, hyphen, colon,
semicolon, question mark, exclamation mark, new line, and new paragraph.
Each new recording replaces the previous transcript. Spoken words matching
these commands are converted literally. Dictation does not execute commands.

### Send a photo from your phone

1. Connect the computer and phone to the same trusted Wi-Fi network.
2. Click **Phone Photo** and scan the QR code above the browser with the phone’s camera.
3. Open the link, take a picture, and tap **Send to Talkbench**.
4. When the photo arrives, click **Copy photo path** and paste it into Codex
   with Ctrl+Shift+V, or click **Open folder**.

The upload creates `phone-photos/` next to `talkbench.py` on the first
successful transfer. Each photo gets a unique filename. Talkbench saves the
image the phone supplies, up to 32 MiB, in JPEG, PNG, WebP, HEIC, HEIF, or AVIF
format. The same QR code works for more photos while the receiver is running.
Click **Stop** to stop the receiver and give the browser its full height again.
Click **Phone Photo** again to start a new session with a new QR code.

The photo receiver uses HTTP and its own temporary port. If the phone cannot
connect, use the same non-guest network and check the computer’s inbound
firewall. If a VPN or another network adapter leads Talkbench to pick the wrong
address, launch it with your computer’s LAN address, for example:

```bash
TALKBENCH_PHOTO_IP=192.168.1.42 .venv/bin/python talkbench.py
```

The terminals are real xterm sessions: arrow keys, Ctrl+C, ANSI/full-screen
interfaces, and resize work as in a normal terminal. Selecting text copies
it to the clipboard. If a shell exits, use its Restart button to open a fresh shell.
Closing the app hangs up active terminals after confirmation; detached jobs
can survive, as with ordinary terminals.

## Platform and troubleshooting

Requires a Linux graphical desktop with X11 (or XWayland). The Qt xcb backend
is selected for native terminal embedding. Run as your normal desktop user.
PySide6 bundles Qt WebEngine, a Chromium-based browser; its download is large.
Do not disable the browser sandbox or run the app as root.

If the browser is unavailable, check the HTTP terminal and press Reload.
If port 8000 is already in use, stop the other server or choose a different
port and change the browser address to match.
If Codex is not found, check the PATH in your bash configuration.
The clipboard is owned by the app while open; XFCE's clipboard manager may
retain it after closure.

## Validation

Python compilation and local HTTP checks cover the photo page, uploads,
rejected requests, and receiver shutdown. The phone camera and live Qt/X11
workflow should be verified on the computer and phone you’ll use.
