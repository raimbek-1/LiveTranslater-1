"""Qt smoke tests without audio hardware or Windows APIs."""
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication

from livetranslate.core import Subtitle
from livetranslate.ui import MainWindow


def test_window_modes_and_reply_rendering():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.receive(Subtitle('Система', 'Wann kommen Sie?', 'Когда вы придёте?'))
    assert 'Когда вы' in window.preview.text()
    window.mode.setCurrentText('German Only')
    assert 'Когда вы' not in window.preview.text()
    window.mode.setCurrentText('Smart Listening')
    assert 'времени' in window.preview.text()
    window.show_reply(dict(german='Morgen.', russian='Завтра.', pronunciation='mɔʁɡn', tip='Коротко'))
    assert window.speak_button.isEnabled()
    window.private.setChecked(True)
    import sys
    if sys.platform != 'win32':
        assert not window.private.isChecked()
    window.theme.setCurrentIndex(1)
    window.quit()
    app.processEvents()
