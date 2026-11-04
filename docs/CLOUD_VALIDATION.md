# Результаты проверки в облаке — 2026-11-04

Среда: Linux x64, Python 3.12.14. Это не проверка Windows-устройств.

Выполнено:

- `pip install -e .`, `pip check`: зависимости установлены, конфликтов нет.
- `python -m livetranslate --help`: CLI запускается.
- `python -m livetranslate --setup-models`: пакеты Argos de→en, en→ru и Whisper base скачаны.
- `python -m pytest -q`: **23 passed**.
- `ruff check src tests`: **All checks passed**.
- Qt offscreen: основное окно создано, режимы переключаются, помощник отображает ответ,
  отказ Private Mode на Linux корректно отображается. Проверен снимок интерфейса 760×800.
- Silero ONNX: реальный inference кадра из 512 нулевых отсчётов при 16 kHz;
  вероятность речи ≈ 0.00167.
- faster-whisper base CPU int8: реальный inference секунды тишины при 16 kHz;
  результат — пустой список сегментов. Это проверка загрузки/runtime, не качества речи.
- Реальные модели Argos/CTranslate2: `Wann haben Sie morgen Zeit?` →
  `Когда у тебя будет время завтра?`. Ошибка регистра вежливости показывает ограничение модели.

Не проверено:

- Распознавание живой немецкой речи, качество и задержка на Windows.
- Микрофон, WASAPI Loopback, синхронный захват двух устройств.
- Реальные RegisterHotKey, display affinity, захват OBS/Teams/Zoom.
- Немецкий системный голос и ответы реальной модели Ollama.
- Сборка и запуск `.exe`: workflow подготовлен, но не запускался из облачного Linux.

Версии проверенного окружения (не универсальный lock-файл):

| Пакет | Версия |
|---|---|
| PySide6 | 6.12.0 |
| numpy | 2.5.4 |
| soxr | 0.5.0.post1 |
| faster-whisper | 1.2.1 |
| silero-vad | 6.2.3 |
| argostranslate | 1.11.0 |
| ctranslate2 | 4.8.5 |
| torch | 2.15.0+cpu |
| torchaudio | 2.11.1+cpu |

GitHub: целевой репозиторий — `raimbek-1/LiveTranslater-1`, подтверждён пользователем.
Ветка реализации: `feat/windows-mvp`, основана на существующем `main`.
Результат сборки Windows и артефакты проверяются отдельно в GitHub Actions.
