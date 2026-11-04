import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="LiveTranslate — локальные немецко-русские субтитры")
    parser.add_argument("--setup-models", action="store_true", help="Скачать Whisper base и Argos de→en→ru")
    args = parser.parse_args()
    if args.setup_models:
        from .translation import install_models
        install_models()
        from faster_whisper import WhisperModel
        WhisperModel("base", device="cpu", compute_type="int8")
        print("Модели готовы. Запустите python -m livetranslate")
        return
    from PySide6.QtWidgets import QApplication

    from .ui import MainWindow
    app = QApplication(sys.argv[:1])
    app.setApplicationName("LiveTranslate")
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
