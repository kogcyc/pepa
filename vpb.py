#!/usr/bin/env python3
"""Voice Workbench: Linux/X11 desktop. See README.md for setup."""
import os
# Native xterm embedding requires X11 (also works through XWayland).
os.environ['QT_QPA_PLATFORM'] = 'xcb'
import sys
import re
import queue
import threading
import shutil
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QProcess, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QSplitter, QPushButton, QLabel, QLineEdit,
    QFrame, QMessageBox, QSizePolicy)
from PySide6.QtWebEngineWidgets import QWebEngineView
from Xlib import display
from phone_upload import PhotoReceiver, local_ipv4

COMMANDS = {'new paragraph':'\n\n', 'new line':'\n', 'question mark':'?',
            'exclamation mark':'!', 'full stop':'.', 'semicolon':';',
            'comma':',', 'period':'.', 'colon':':', 'hyphen':'-'}
PATTERN = re.compile(r'\b('+'|'.join(COMMANDS)+r')\b[,.!?]?', re.I)
def punctuation(text):
    text = PATTERN.sub(lambda m: COMMANDS[m.group(1).lower()], text)
    text = re.sub(r'[ \t]+([,.;:!?])', r'\1', text)
    text = re.sub(r'[ \t]*-[ \t]*', '-', text)
    text = re.sub(r'[ \t]*\n[ \t]*', '\n', text)
    return re.sub(r'([,.;:!?])(?=[A-Za-z])', r'\1 ', text).strip()

def button(label, action, layout):
    b = QPushButton(label); b.clicked.connect(action); layout.addWidget(b)
    return b

class Dictation(QWidget):
    """Compact TALK/CLIP controls; transcription stays off the UI thread."""
    def __init__(self, open_photo):
        super().__init__()
        self.setMinimumHeight(48)
        self.transcript = ''
        self.stream = None; self.model = None; self.busy = False
        self.frames = queue.Queue(); self.results = queue.Queue()
        self.warning = ''
        layout = QVBoxLayout(self); layout.setContentsMargins(6,4,6,4); layout.setSpacing(3)
        row = QHBoxLayout(); layout.addLayout(row)
        self.record = button('TALK', self.start, row)
        self.stop = button('CLIP', self.clip, row)
        button('Phone Photo', open_photo, row)
        self.record.setStyleSheet('QPushButton { background-color: #008800; color: #ffffff; }')
        self.stop.setStyleSheet('QPushButton { background-color: #990000; color: #ffffff; }')
        self.record.setToolTip('Start recording from your default microphone')
        self.stop.setToolTip('Stop, transcribe, and copy; click again to copy the last transcript')
        self.status = QLabel('Ready'); layout.addWidget(self.status)
        self.timer = QTimer(self); self.timer.timeout.connect(self.poll); self.timer.start(100)
    def say(self, text):
        self.status.setText(self.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, max(40,self.width()-16)))
        self.status.setToolTip(text)
    def start(self):
        try:
            import sounddevice as sd
            while not self.frames.empty(): self.frames.get_nowait()
            self.warning = ''
            def capture(data, count, timing, status):
                if status: self.warning = str(status)
                self.frames.put(data.copy())
            self.stream = sd.InputStream(samplerate=16000, channels=1,
                                        dtype='float32', callback=capture)
            self.stream.start(); self.record.setEnabled(False); self.stop.setEnabled(True)
            self.say('Recording…')
        except Exception as exc:
            if self.stream: self.stream.close(); self.stream = None
            self.say('Microphone: '+str(exc))
    def clip(self):
        if self.stream: self.finish()
        elif self.transcript: self.copy()
        else: self.say('Press TALK to record first')
    def finish(self):
        if not self.stream: return
        self.stream.stop(); self.stream.close(); self.stream = None
        chunks = []
        while not self.frames.empty(): chunks.append(self.frames.get_nowait())
        self.stop.setEnabled(False); self.busy = True
        self.say('Transcribing… first use downloads model')
        threading.Thread(target=self.transcribe, args=(chunks,), daemon=True).start()
    def transcribe(self, chunks):
        try:
            import numpy as np
            from faster_whisper import WhisperModel
            if not chunks: raise RuntimeError('No audio recorded')
            audio = np.concatenate(chunks).reshape(-1)
            if len(audio)<1600 or np.max(np.abs(audio))<0.0001:
                raise RuntimeError('No audible speech; check microphone')
            if self.model is None:
                self.model = WhisperModel('base.en',device='cpu',compute_type='int8')
            segments, _ = self.model.transcribe(audio, language='en', vad_filter=True,
                                                condition_on_previous_text=False)
            text = ' '.join(s.text.strip() for s in segments).strip()
            if not text: raise RuntimeError('No speech recognized')
            self.results.put((True, text))
        except Exception as exc: self.results.put((False, str(exc)))
    def poll(self):
        try: ok, text = self.results.get_nowait()
        except queue.Empty: return
        self.busy = False; self.record.setEnabled(True); self.stop.setEnabled(True)
        if ok:
            self.transcript = punctuation(text); self.copy()
            if self.warning: self.say('Copied; audio warning: '+self.warning)
        else: self.say(text)
    def copy(self):
        if self.transcript.strip():
            QApplication.clipboard().setText(self.transcript)
            self.say('Copied — Ctrl+Shift+V to paste')
        else: self.say('No text to copy')
    def shutdown(self):
        if self.stream: self.stream.abort(); self.stream.close(); self.stream = None

class PhonePhotoPanel(QFrame):
    received = Signal(str)

    def __init__(self, folder, parent):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.folder = folder
        self.receiver = None
        self.latest = None
        layout = QHBoxLayout(self)
        self.qr = QLabel()
        layout.addWidget(self.qr, alignment=Qt.AlignmentFlag.AlignVCenter)
        details = QVBoxLayout()
        layout.addLayout(details, 1)
        heading = QHBoxLayout()
        details.addLayout(heading)
        heading.addWidget(QLabel('Phone Photo'), 1)
        button('Stop', self.stop, heading)
        instructions = QLabel('On the same Wi-Fi, scan this code with your phone’s camera.')
        instructions.setWordWrap(True)
        details.addWidget(instructions)
        self.url = QLineEdit()
        self.url.setReadOnly(True)
        details.addWidget(self.url)
        self.status = QLabel()
        self.status.setWordWrap(True)
        details.addWidget(self.status)
        row = QHBoxLayout()
        details.addLayout(row)
        self.copy_path = button('Copy photo path', self.copy_latest, row)
        self.copy_path.setEnabled(False)
        self.open_folder = button('Open folder', self.browse_folder, row)
        self.open_folder.setEnabled(folder.is_dir())
        self.received.connect(self.photo_arrived, Qt.ConnectionType.QueuedConnection)
        self.hide()

    def start(self):
        if self.receiver is not None:
            return
        try:
            import qrcode
        except ImportError:
            QMessageBox.warning(self.window(), 'Phone Photo',
                                'Install the updated requirements to enable Phone Photo.')
            return

        try:
            self.receiver = PhotoReceiver(local_ipv4(), self.folder,
                                          lambda path: self.received.emit(str(path)))
            qr = qrcode.QRCode()
            qr.add_data(self.receiver.url)
            qr.make(fit=True)
            matrix = qr.get_matrix()
            scale = 4
            size = len(matrix) * scale
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.white)
            painter = QPainter(pixmap)
            try:
                for y, row in enumerate(matrix):
                    for x, dark in enumerate(row):
                        if dark:
                            painter.fillRect(x * scale, y * scale, scale, scale, Qt.GlobalColor.black)
            finally:
                painter.end()
            self.qr.setPixmap(pixmap)
        except (OSError, ValueError) as exc:
            self.stop()
            QMessageBox.warning(self.window(), 'Phone Photo',
                                'Could not start the photo receiver. Check the computer’s network connection.\n' + str(exc))
            return
        self.url.setText(self.receiver.url)
        self.status.setText('Ready to receive a photo.')
        self.show()

    def photo_arrived(self, path):
        self.latest = Path(path)
        self.status.setText('Received ' + str(self.latest.relative_to(self.folder.parent)))
        self.copy_path.setEnabled(True)
        self.open_folder.setEnabled(True)

    def copy_latest(self):
        if self.latest is not None:
            QApplication.clipboard().setText(str(self.latest))
            self.status.setText('Copied path. Use Ctrl+Shift+V to paste it into a terminal.')

    def browse_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.folder)))

    def stop(self):
        if self.receiver is not None:
            self.receiver.stop()
            self.receiver = None
        self.qr.clear()
        self.url.clear()
        self.hide()


class Terminal(QWidget):
    """Real xterm/PTY, including ANSI, full-screen TUIs, Ctrl+C and resize."""
    def __init__(self):
        super().__init__(); self.proc = None; self.cwd = str(Path.home())
        layout = QVBoxLayout(self); layout.setContentsMargins(2,2,2,2)
        row = QHBoxLayout(); layout.addLayout(row); row.addStretch()
        button('Restart', self.restart, row)
        self.host = QWidget(); self.host.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.host.setMinimumSize(180,40); layout.addWidget(self.host,1)
        self.note = QLabel('Starting shell…'); self.note.setWordWrap(True)
        self.note.setVisible(False); layout.addWidget(self.note)
        self.connection = display.Display()
        self.timer = QTimer(self); self.timer.timeout.connect(self.fit); self.timer.start(200)
    def start(self):
        if self.proc and self.proc.state()!=QProcess.ProcessState.NotRunning: return
        if not Path(self.cwd).is_dir():
            self.error('The app directory no longer exists.'); return
        if not shutil.which('xterm'):
            self.error('Missing xterm: sudo apt install xterm'); return
        self.proc = QProcess(self); self.proc.setWorkingDirectory(self.cwd)
        self.proc.finished.connect(self.ended)
        self.proc.errorOccurred.connect(lambda _: self.error('Terminal: '+self.proc.errorString()))
        self.note.setVisible(False)
        self.proc.start('xterm', ['-into',str(int(self.host.winId())), '-fa','Monospace',
            '-fs','10', '-bg','#101010','-fg','#eeeeee', '-sb', '-sl','10000',
            '-xrm','XTerm*selectToClipboard: true',
            '-xrm','XTerm*VT100.translations: #override \\n Ctrl Shift <Key>V: insert-selection(CLIPBOARD) \\n Ctrl Shift <Key>C: copy-selection(CLIPBOARD)',
            '-e','bash','-i'])
        self.host.setToolTip('Working directory: '+self.cwd+'\nCtrl+C interrupts; Ctrl+Shift+V pastes')
    def error(self, message):
        self.note.setText(message); self.note.setVisible(True)
    def restart(self):
        if self.proc and self.proc.state()!=QProcess.ProcessState.NotRunning:
            if QMessageBox.question(self,'Restart terminal?',
                'Close this terminal session and start a new shell?',
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes: return
        self.stop(); self.start()
    def fit(self):
        if not self.proc or self.proc.state()==QProcess.ProcessState.NotRunning: return
        try:
            parent = self.connection.create_resource_object('window',int(self.host.winId()))
            # X coordinates are physical pixels; Qt geometry is logical pixels.
            scale = self.host.devicePixelRatioF()
            w,h = max(1,int(self.host.width()*scale)),max(1,int(self.host.height()*scale))
            for child in parent.query_tree().children:
                geo = child.get_geometry()
                if geo.width!=w or geo.height!=h:
                    child.configure(x=0,y=0,width=w,height=h,border_width=0)
            self.connection.flush()
        except Exception: pass  # xterm can exit between querying and resizing
    def ended(self, *args):
        self.error('Shell closed. Press Restart to open a new shell.')
    def stop(self):
        if self.proc and self.proc.state()!=QProcess.ProcessState.NotRunning:
            self.proc.terminate()  # xterm hangs up its PTY and child shell
            if not self.proc.waitForFinished(1000):
                self.proc.kill(); self.proc.waitForFinished(1000)
    def shutdown(self):
        self.timer.stop(); self.stop(); self.connection.close()

class Browser(QWidget):
    def __init__(self, phone_photo):
        super().__init__(); layout = QVBoxLayout(self); layout.setContentsMargins(2,2,2,2)
        layout.addWidget(phone_photo)
        row = QHBoxLayout(); layout.addLayout(row)
        self.web = QWebEngineView()
        button('←',self.web.back,row); button('→',self.web.forward,row)
        button('Reload',self.web.reload,row)
        self.address = QLineEdit('http://localhost:8000'); row.addWidget(self.address,1)
        button('Go',self.navigate,row); self.address.returnPressed.connect(self.navigate)
        layout.addWidget(self.web,1)
        self.status = QLabel('Start the HTTP server, then press Reload.'); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.web.urlChanged.connect(lambda url:self.address.setText(url.toString()))
        self.web.loadFinished.connect(lambda ok:self.status.setText('Loaded' if ok else 'Page unavailable. Start the HTTP server and Reload.'))
        self.navigate()
    def navigate(self): self.web.setUrl(QUrl.fromUserInput(self.address.text()))

class Workbench(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle('Talkbench'); self.resize(1440,940)
        self.cwd = str(Path(__file__).resolve().parent)
        center = QWidget(); self.setCentralWidget(center)
        layout = QHBoxLayout(center); layout.setContentsMargins(0,0,0,0)
        self.phone_photo = PhonePhotoPanel(Path(self.cwd) / 'phone-photos', self)
        self.dictation = Dictation(self.phone_photo.start)
        self.server = Terminal()
        self.tissue = Terminal()
        self.codex = Terminal()
        self.terminals = [self.server,self.tissue,self.codex]
        for term in self.terminals: term.cwd = self.cwd
        self.left = QSplitter(Qt.Orientation.Vertical)
        self.left.setChildrenCollapsible(False)
        for pane in [self.dictation,*self.terminals]:
            self.left.addWidget(pane)
            pane.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Ignored)
        for i in range(4): self.left.setStretchFactor(i,1)
        self.browser = Browser(self.phone_photo)
        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.split.setChildrenCollapsible(False)
        self.split.addWidget(self.left); self.split.addWidget(self.browser)
        self.split.setStretchFactor(0,1); self.split.setStretchFactor(1,1)
        layout.addWidget(self.split)
        QTimer.singleShot(0,self.startup)
    def startup(self):
        self.split.setSizes([self.width()//2,self.width()//2])
        usable = max(1,self.left.height()-3*self.left.handleWidth())
        self.left.setSizes([int(usable*p) for p in (.10,.20,.20,.50)])
        for term in self.terminals: term.start()
    def closeEvent(self,event):
        running = self.dictation.busy or self.dictation.stream is not None or any(
            t.proc and t.proc.state()!=QProcess.ProcessState.NotRunning for t in self.terminals)
        if running and QMessageBox.question(self,'Close workbench?',
            'Close the terminals and discard any active dictation? Running terminal jobs will be hung up.',
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:
            event.ignore(); return
        self.phone_photo.stop()
        self.dictation.shutdown()
        for term in self.terminals: term.shutdown()
        event.accept()

def main():
    if not os.environ.get('DISPLAY'):
        sys.exit('Run this in your Linux desktop session (X11/XWayland DISPLAY required).')
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = Workbench(); window.show(); sys.exit(app.exec())

if __name__=='__main__': main()
