import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .assistant import LEVELS, suggest
from .audio import devices
from .core import Mode
from .engine import Engine
from .windows import Hotkeys, display_affinity


def app_icon():
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setBrush(QColor("#007aff"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(2, 2, 60, 60, 16, 16)
    painter.setPen(QColor("white"))
    font = painter.font()
    font.setPixelSize(26)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "LT")
    painter.end()
    return QIcon(pix)


class Overlay(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.resize(820, 220)
        self.label = QLabel("LiveTranslate · Ожидание речи")
        self.label.setTextFormat(Qt.TextFormat.RichText)
        self.label.setWordWrap(True)
        self.label.setStyleSheet("background:rgba(18,20,26,215); color:white; border-radius:18px;"
                                 "padding:20px; font-size:22px;")
        layout = QVBoxLayout(self)
        layout.addWidget(self.label)
        self.anchor = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.clear)
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.center().x() - 410, screen.bottom() - 260)

    def clear(self):
        self.label.setText("LiveTranslate · Ожидание речи")

    def set_subtitle(self, value):
        self.label.setText(value)
        self.timer.start(15000)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.anchor = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self.anchor is not None:
            self.move(event.globalPosition().toPoint() - self.anchor)

    def mouseReleaseEvent(self, event):
        self.anchor = None


class ReplyWorker(QThread):
    ready = Signal(object)
    failed = Signal(str)

    def __init__(self, intent, level, model):
        super().__init__()
        self.intent, self.level, self.model = intent, level, model

    def run(self):
        try:
            self.ready.emit(suggest(self.intent, self.level, self.model))
        except Exception as exc:
            self.failed.emit(f"Ollama: {type(exc).__name__}. Запустите Ollama и загрузите выбранную модель.")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.engine = None
        self.reply_worker = None
        self.last = None
        self.quitting = False
        self.setWindowTitle("LiveTranslate")
        self.setWindowIcon(app_icon())
        self.resize(760, 800)
        self.overlay = Overlay()
        self.overlay.show()
        body = QWidget()
        self.setCentralWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)
        title = QLabel("LiveTranslate")
        title.setStyleSheet("font-size:30px; font-weight:600;")
        layout.addWidget(title)
        layout.addWidget(QLabel("Немецкий → Русский · локальная обработка · без записи разговоров"))
        self.mode = QComboBox()
        self.mode.addItems([m.value for m in Mode])
        self.mode.currentTextChanged.connect(self.render)
        self.theme = QComboBox()
        self.theme.addItems(["Светлая", "Тёмная"])
        self.theme.currentIndexChanged.connect(self.apply_theme)
        row = QHBoxLayout()
        row.addWidget(self.mode)
        row.addWidget(self.theme)
        layout.addLayout(row)
        self.mic = QCheckBox("Микрофон")
        self.system = QCheckBox("Системное аудио (WASAPI Loopback)")
        self.system.setChecked(True)
        self.mic_device = QComboBox()
        self.sys_device = QComboBox()
        self.mic_device.addItem("Микрофон по умолчанию", None)
        self.sys_device.addItem("Динамики по умолчанию", None)
        try:
            for index, name, loopback in devices():
                (self.sys_device if loopback else self.mic_device).addItem(name, index)
        except Exception as exc:
            self.device_error = str(exc)
        for checkbox, combo in ((self.mic, self.mic_device), (self.system, self.sys_device)):
            row = QHBoxLayout()
            row.addWidget(checkbox)
            row.addWidget(combo, 1)
            layout.addLayout(row)
        self.model = QComboBox()
        self.model.addItems(["base", "tiny", "small"])
        row = QHBoxLayout()
        row.addWidget(QLabel("Whisper CPU int8"))
        row.addWidget(self.model)
        self.start = QPushButton("Начать · Ctrl+Alt+S")
        self.start.clicked.connect(self.toggle)
        row.addWidget(self.start, 1)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.private = QCheckBox("Private Overlay · Ctrl+Alt+P")
        self.private.toggled.connect(self.set_private)
        self.visible_overlay = QCheckBox("Субтитры · Ctrl+Alt+O")
        self.visible_overlay.setChecked(True)
        self.visible_overlay.toggled.connect(self.set_overlay)
        row.addWidget(self.private)
        row.addWidget(self.visible_overlay)
        layout.addLayout(row)
        self.privacy_status = QLabel("Private Overlay выключен")
        self.privacy_status.setWordWrap(True)
        layout.addWidget(self.privacy_status)
        self.status = QLabel(getattr(self, "device_error", "Готово. До запуска установите модели: --setup-models"))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.preview = QLabel("Здесь появится последняя реплика")
        self.preview.setTextFormat(Qt.TextFormat.RichText)
        self.preview.setWordWrap(True)
        self.preview.setMinimumHeight(100)
        layout.addWidget(self.preview)
        layout.addWidget(QLabel("Помощник ответа · только введённый текст отправляется в локальный Ollama"))
        self.intent = QLineEdit()
        self.intent.setPlaceholderText("Что вы хотите ответить по-русски?")
        self.intent.setMaxLength(2000)
        layout.addWidget(self.intent)
        row = QHBoxLayout()
        self.level = QComboBox()
        self.level.addItems(LEVELS)
        self.ollama = QLineEdit("qwen2.5:3b")
        self.ollama.setPlaceholderText("Модель Ollama")
        self.reply_button = QPushButton("Сформулировать")
        self.reply_button.clicked.connect(self.reply)
        row.addWidget(self.level)
        row.addWidget(self.ollama)
        row.addWidget(self.reply_button)
        layout.addLayout(row)
        self.answer = QTextEdit()
        self.answer.setReadOnly(True)
        self.answer.setPlaceholderText("Немецкий ответ · перевод · IPA · подсказка")
        layout.addWidget(self.answer, 1)
        self.speak_button = QPushButton("Произнести немецкий ответ")
        self.speak_button.clicked.connect(self.speak)
        self.speak_button.setEnabled(False)
        layout.addWidget(self.speak_button)
        self.german_reply = ""
        self.speech = None
        self.tray = QSystemTrayIcon(app_icon(), self)
        menu = QMenu()
        for text, callback in (("Открыть", self.showNormal), ("Начать / остановить", self.toggle),
                               ("Показать / скрыть субтитры", self.visible_overlay.toggle),
                               ("Выход", self.quit)):
            action = QAction(text, menu)
            action.triggered.connect(callback)
            menu.addAction(action)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip("LiveTranslate · остановлено")
        self.tray.activated.connect(lambda reason: self.showNormal()
                                   if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self.tray.show()
        self.hotkeys = Hotkeys(int(self.winId()))
        failures = self.hotkeys.register()
        if failures:
            self.status.setText("; ".join(failures))
        self.apply_theme()

    def apply_theme(self):
        dark = self.theme.currentIndex() == 1
        bg, fg, card, border = (("#17181c", "#f4f4f7", "#25262c", "#41434b") if dark else
                                ("#f5f5f7", "#1d1d1f", "#ffffff", "#d5d5db"))
        self.setStyleSheet(f"QMainWindow, QWidget {{background:{bg};color:{fg};font-family:'Segoe UI';"
                           "font-size:13px;}"
                           f"QLineEdit,QTextEdit,QComboBox {{background:{card};border:1px solid {border};"
                           "border-radius:8px;padding:8px;}"
                           "QPushButton {background:#007aff;color:white;border:0;border-radius:9px;padding:10px;}"
                           "QPushButton:disabled {background:#777;} QCheckBox {spacing:8px;}")

    def toggle(self):
        if self.engine is not None:
            self.engine.stop()
            self.start.setEnabled(False)
            self.status.setText("Остановка после текущего вычисления…")
            return
        sources = []
        if self.mic.isChecked():
            sources.append(("Микрофон", self.mic_device.currentData()))
        if self.system.isChecked():
            sources.append(("Система", self.sys_device.currentData()))
        if not sources:
            self.status.setText("Выберите хотя бы один источник аудио")
            return
        self.engine = Engine(sources, self.model.currentText())
        self.engine.subtitle.connect(self.receive)
        self.engine.status.connect(self.status.setText)
        self.engine.error.connect(self.report_error)
        self.engine.finished.connect(self.stopped)
        self.start.setText("Остановить · Ctrl+Alt+S")
        for control in (self.mic, self.system, self.mic_device, self.sys_device, self.model):
            control.setEnabled(False)
        self.tray.setToolTip("LiveTranslate · слушает")
        self.engine.start()

    def report_error(self, message):
        self.status.setText(message)
        self.tray.showMessage("LiveTranslate", message, QSystemTrayIcon.MessageIcon.Warning)

    def stopped(self):
        self.engine.deleteLater()
        self.engine = None
        self.start.setText("Начать · Ctrl+Alt+S")
        self.start.setEnabled(True)
        for control in (self.mic, self.system, self.mic_device, self.sys_device, self.model):
            control.setEnabled(True)
        self.tray.setToolTip("LiveTranslate · остановлено")
        self.last = None
        self.preview.clear()
        self.overlay.clear()
        if self.quitting:
            self.finish_quit()

    def receive(self, subtitle):
        self.last = subtitle
        self.render()
        self.status.setText(f"{subtitle.source} · {subtitle.latency:.1f} с после завершения фрагмента")

    def render(self, *_):
        if self.last:
            value = self.last.render(Mode(self.mode.currentText()))
            self.preview.setText(value)
            self.overlay.set_subtitle(value)

    def set_private(self, enabled):
        ok, message = display_affinity(int(self.overlay.winId()), enabled)
        self.privacy_status.setText(message)
        if not ok and enabled:
            self.private.blockSignals(True)
            self.private.setChecked(False)
            self.private.blockSignals(False)

    def set_overlay(self, visible):
        self.overlay.setVisible(visible)
        if visible and self.private.isChecked():
            self.set_private(True)

    def reply(self):
        if not self.intent.text().strip():
            self.answer.setPlainText("Введите смысл ответа по-русски")
            return
        self.reply_worker = ReplyWorker(self.intent.text(), self.level.currentText(), self.ollama.text())
        self.reply_worker.ready.connect(self.show_reply)
        self.reply_worker.failed.connect(self.answer.setPlainText)
        self.reply_worker.finished.connect(self.reply_finished)
        self.reply_button.setEnabled(False)
        self.answer.setPlainText("Готовлю ответ…")
        self.reply_worker.start()

    def reply_finished(self):
        self.reply_worker.deleteLater()
        self.reply_worker = None
        self.reply_button.setEnabled(True)
        if self.quitting and self.engine is None:
            self.finish_quit()

    def show_reply(self, result):
        self.german_reply = result["german"]
        self.answer.setPlainText("\n\n".join(result[k] for k in ("german", "russian", "pronunciation", "tip")))
        self.speak_button.setEnabled(True)

    def speak(self):
        try:
            from PySide6.QtTextToSpeech import QTextToSpeech
            if self.speech is None:
                self.speech = QTextToSpeech(self)
            voices = [v for v in self.speech.availableVoices() if v.locale().name().startswith("de")]
            if not voices:
                self.answer.append("\nУстановите немецкий голос в параметрах речи Windows.")
                return
            self.speech.setVoice(voices[0])
            self.speech.say(self.german_reply)
        except Exception as exc:
            self.answer.append(f"\nСинтез речи недоступен: {type(exc).__name__}")

    def nativeEvent(self, event_type, message):
        if sys.platform == "win32":
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            if msg.message == 0x0312:  # WM_HOTKEY, processed on GUI thread
                callback = {1: self.toggle, 2: self.visible_overlay.toggle, 3: self.private.toggle}.get(msg.wParam)
                if callback:
                    callback()
                    return True, 0
        return super().nativeEvent(event_type, message)

    def closeEvent(self, event):
        if QSystemTrayIcon.isSystemTrayAvailable() and not self.quitting:
            self.hide()
            event.ignore()
        else:
            event.ignore()
            self.quit()

    def quit(self):
        self.quitting = True
        self.hide()
        self.overlay.hide()
        if self.engine:
            self.engine.stop()
        if self.engine is None and self.reply_worker is None:
            self.finish_quit()
        else:
            self.tray.showMessage("LiveTranslate", "Завершение текущего вычисления…")

    def finish_quit(self):
        if self.reply_worker is not None:
            return
        self.hotkeys.close()
        self.tray.hide()
        QApplication.quit()
