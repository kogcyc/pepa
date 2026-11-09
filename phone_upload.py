"""A short-lived HTTP receiver for photos from a phone on the local network."""

from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import ipaddress
import os
import secrets
import socket
import tempfile
import threading
import time

MAX_PHOTO_BYTES = 32 * 1024 * 1024
PHONE_PAGE = """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Send a photo to Talkbench</title>
<style>
  body { font: 1.15rem system-ui; margin: 2rem auto; max-width: 27rem; padding: 0 1rem;
         color-scheme: light dark; }
  button { font: inherit; margin: .5rem 0; max-width: 100%; min-height: 44px; }
</style>
<main>
  <h1>Send a photo</h1>
  <p>Take a new picture or select one from your photo library.</p>
  <button id="take" type="button">Take Photo</button>
  <button id="choose" type="button">Choose Existing Photo</button>
  <input id="camera" type="file" accept="image/*" capture="environment" hidden>
  <input id="library" type="file" accept="image/*" hidden>
  <br>
  <button id="send" type="button" disabled>Send to Talkbench</button>
  <p id="status" role="status" aria-live="polite"></p>
</main>
<script>
const take = document.querySelector('#take');
const choose = document.querySelector('#choose');
const camera = document.querySelector('#camera');
const library = document.querySelector('#library');
const send = document.querySelector('#send');
const feedback = document.querySelector('#status');
let selectedPhoto = null;

take.addEventListener('click', () => camera.click());
choose.addEventListener('click', () => library.click());
for (const input of [camera, library]) {
  input.addEventListener('change', () => {
    const file = input.files[0];
    if (!file) return;
    selectedPhoto = file;
    input.value = '';
    send.disabled = false;
    feedback.textContent = 'Selected: ' + file.name;
  });
}

send.addEventListener('click', async () => {
  const file = selectedPhoto;
  if (!file) return;
  if (file.size > 32 * 1024 * 1024) {
    feedback.textContent = 'Choose a photo under 32 MiB.';
    return;
  }
  take.disabled = choose.disabled = send.disabled = true;
  feedback.textContent = 'Sending…';
  try {
    const response = await fetch(location.pathname, {
      method: 'POST',
      headers: {'Content-Type': 'application/octet-stream'},
      body: file
    });
    const message = await response.text();
    feedback.textContent = message;
    if (response.ok) selectedPhoto = null;
  } catch {
    feedback.textContent = 'Connection lost. Check that Phone Photo is open, then try again.';
  } finally {
    take.disabled = choose.disabled = false;
    send.disabled = !selectedPhoto;
  }
});
</script>
</html>
"""


def local_ipv4():
    address = os.environ.get('TALKBENCH_PHOTO_IP')
    if not address:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
            # Ask the OS which interface it would use. This sends no packets.
            route.connect(('192.0.2.1', 9))
            address = route.getsockname()[0]
    ip = ipaddress.IPv4Address(address)
    if ip.is_loopback or ip.is_unspecified or ip.is_multicast:
        raise ValueError('Choose the computer’s local Wi-Fi or Ethernet IPv4 address.')
    return str(ip)


def photo_extension(header):
    if header.startswith(b'\xff\xd8\xff'):
        return '.jpg'
    if header.startswith(b'\x89PNG\r\n\x1a\n'):
        return '.png'
    if header.startswith(b'RIFF') and header[8:12] == b'WEBP':
        return '.webp'
    if header[4:8] == b'ftyp':
        box_size = min(len(header), int.from_bytes(header[:4], 'big'))
        brands = {header[8:12]} | {header[i:i+4] for i in range(16, box_size - 3, 4)}
        if brands & {b'avif', b'avis'}:
            return '.avif'
        if brands & {b'heic', b'heix', b'hevc', b'hevx', b'heim', b'heis', b'hevm', b'hevs'}:
            return '.heic'
        if brands & {b'mif1', b'msf1'}:
            return '.heif'
    return None


class PhotoHandler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(10)
        super().setup()

    def log_message(self, *args):
        # The session key is part of the URL.
        pass

    def reply(self, code, message, media_type='text/plain'):
        body = message.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', f'{media_type}; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        try:
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionError, TimeoutError):
            pass

    def paired(self):
        if secrets.compare_digest(self.path.encode('utf-8'), self.server.capture_path.encode()):
            return True
        self.reply(HTTPStatus.NOT_FOUND, 'Scan the current QR code in Talkbench.')
        return False

    def do_GET(self):
        if self.paired():
            self.reply(HTTPStatus.OK, PHONE_PAGE, 'text/html')

    def do_POST(self):
        if not self.paired():
            return
        if self.headers.get_content_type() != 'application/octet-stream':
            self.reply(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, 'Use the Talkbench phone page to send a photo.')
            return
        try:
            size = int(self.headers.get('Content-Length', ''))
        except ValueError:
            size = 0
        if size <= 0:
            self.reply(HTTPStatus.BAD_REQUEST, 'Choose a photo first.')
            return
        if size > MAX_PHOTO_BYTES:
            self.reply(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, 'Choose a photo under 32 MiB.')
            return

        temporary = None
        try:
            header = self.rfile.read(min(size, 128))
            extension = photo_extension(header)
            if extension is None:
                self.reply(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, 'Choose a JPEG, PNG, WebP, HEIC, HEIF, or AVIF photo.')
                return
            folder = self.server.folder
            folder.mkdir(exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=folder, prefix='.upload-', delete=False) as photo:
                temporary = Path(photo.name)
                photo.write(header)
                remaining = size - len(header)
                deadline = time.monotonic() + 90
                while remaining:
                    if time.monotonic() > deadline:
                        raise TimeoutError
                    chunk = self.rfile.read1(min(remaining, 65536))
                    if not chunk:
                        raise ConnectionError
                    photo.write(chunk)
                    remaining -= len(chunk)

            stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            path = folder / f'photo-{stamp}-{secrets.token_hex(6)}{extension}'
            with self.server.publish_lock:
                active = not self.server.stopped
                if active:
                    temporary.replace(path)
                    self.server.on_photo(path)
            if not active:
                self.reply(HTTPStatus.GONE, 'Scan a fresh QR code in Talkbench.')
                return
            self.reply(HTTPStatus.CREATED, f'Saved in Talkbench as {path.name}.')
        except (ConnectionError, TimeoutError):
            self.reply(HTTPStatus.REQUEST_TIMEOUT, 'The upload was interrupted. Try again.')
        except OSError:
            self.reply(HTTPStatus.INTERNAL_SERVER_ERROR, 'Talkbench could not save the photo. Check the project folder.')
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


class PhotoReceiver(ThreadingHTTPServer):
    def __init__(self, address, folder, on_photo):
        super().__init__((address, 0), PhotoHandler)
        self.capture_path = '/capture/' + secrets.token_urlsafe(24)
        self.url = f'http://{address}:{self.server_port}{self.capture_path}'
        self.folder = folder
        self.on_photo = on_photo
        self.publish_lock = threading.Lock()
        self.stopped = False
        threading.Thread(target=self.serve_forever, kwargs={'poll_interval': 0.1}, daemon=True).start()

    def stop(self):
        with self.publish_lock:
            self.stopped = True
        self.shutdown()
        self.server_close()
