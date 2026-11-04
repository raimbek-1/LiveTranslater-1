import queue
import sys
import time
from threading import Event

from PySide6.QtCore import QThread, Signal

from .audio import Capture
from .core import Subtitle


class Engine(QThread):
    subtitle = Signal(object)
    status = Signal(str)
    error = Signal(str)

    def __init__(self, sources, model="base"):
        super().__init__()
        self.sources, self.model_name = sources, model
        self.stop_event = Event()

    def stop(self):
        self.stop_event.set()

    def run(self):
        failed = False
        captures = []
        utterances = queue.Queue(maxsize=3)
        notices = queue.Queue()
        try:
            if sys.platform != "win32":
                raise RuntimeError("Для живого захвата требуется Windows 10/11")
            from faster_whisper import WhisperModel

            from .translation import Translator
            self.status.emit("Загрузка моделей… Первый запуск Whisper требует интернет.")
            translator = Translator()
            model = WhisperModel(self.model_name, device="cpu", compute_type="int8",
                                 local_files_only=False)
            if self.stop_event.is_set():
                return
            for source, device in self.sources:
                capture = Capture(source, device, self.stop_event, utterances, notices)
                captures.append(capture)
                capture.start()
            self.status.emit("Слушаю…")
            while not self.stop_event.is_set():
                while not notices.empty():
                    kind, message = notices.get_nowait()
                    (self.error if kind == "error" else self.status).emit(message)
                try:
                    source, audio, ended = utterances.get(timeout=0.1)
                except queue.Empty:
                    continue
                if time.monotonic() - ended > 8:
                    self.status.emit("Пропущена устаревшая реплика: выберите tiny или один источник")
                    continue
                segments, _ = model.transcribe(audio, language="de", task="transcribe", beam_size=1,
                                               condition_on_previous_text=False, vad_filter=False)
                text = " ".join(s.text.strip() for s in segments if s.no_speech_prob < 0.7).strip()
                if text and not self.stop_event.is_set():
                    russian = translator.translate(text)
                    if not self.stop_event.is_set():
                        self.subtitle.emit(Subtitle(source, text, russian, time.monotonic() - ended))
        except Exception as exc:
            failed = True
            self.error.emit(f"{type(exc).__name__}: {exc}")
        finally:
            self.stop_event.set()
            for capture in captures:
                capture.join()
            while not notices.empty():
                kind, message = notices.get_nowait()
                if kind == "error":
                    failed = True
                    self.error.emit(message)
            if not failed:
                self.status.emit("Остановлено")
