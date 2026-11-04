import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from livetranslate.audio import audio_session


def test_simultaneous_readers_share_lifetime(monkeypatch):
    factory = Mock()
    monkeypatch.setitem(sys.modules, 'pyaudiowpatch', SimpleNamespace(PyAudio=factory))
    entered, leaving = Barrier(2), Barrier(2)

    def reader(_):
        with audio_session() as audio:
            entered.wait(timeout=5)
            factory.assert_called_once()
            audio.terminate.assert_not_called()
            leaving.wait(timeout=5)
            return audio

    with ThreadPoolExecutor(2) as workers:
        readers = list(workers.map(reader, range(2)))
    assert readers[0] is readers[1]
    factory.return_value.terminate.assert_called_once()


def test_exception_releases_session_and_next_start_reinitializes(monkeypatch):
    first, second = Mock(), Mock()
    factory = Mock(side_effect=[first, second])
    monkeypatch.setitem(sys.modules, 'pyaudiowpatch', SimpleNamespace(PyAudio=factory))
    with pytest.raises(ValueError):
        with audio_session():
            raise ValueError('capture failed')
    first.terminate.assert_called_once()
    with audio_session() as audio:
        assert audio is second
    second.terminate.assert_called_once()


def test_failed_initialization_can_retry(monkeypatch):
    recovered = Mock()
    factory = Mock(side_effect=[OSError('unavailable'), recovered])
    monkeypatch.setitem(sys.modules, 'pyaudiowpatch', SimpleNamespace(PyAudio=factory))
    with pytest.raises(OSError):
        with audio_session():
            pass
    with audio_session() as audio:
        assert audio is recovered
    audio.terminate.assert_called_once()


def test_com_is_released_on_capture_exception(monkeypatch):
    from livetranslate import audio as module

    com = Mock()
    monkeypatch.setattr(module.sys, 'platform', 'win32')
    monkeypatch.setattr(module.ctypes, 'OleDLL', lambda _: com, raising=False)
    monkeypatch.setitem(sys.modules, 'pyaudiowpatch', SimpleNamespace(PyAudio=Mock()))
    with pytest.raises(ValueError):
        with audio_session():
            raise ValueError('capture failed')
    com.CoInitializeEx.assert_called_once_with(None, 0)
    com.CoUninitialize.assert_called_once()


def test_existing_com_apartment_is_not_uninitialized(monkeypatch):
    from livetranslate import audio as module

    com = Mock()
    error = OSError('COM already uses another apartment')
    error.winerror = -2147417850
    com.CoInitializeEx.side_effect = error
    monkeypatch.setattr(module.sys, 'platform', 'win32')
    monkeypatch.setattr(module.ctypes, 'OleDLL', lambda _: com, raising=False)
    monkeypatch.setitem(sys.modules, 'pyaudiowpatch', SimpleNamespace(PyAudio=Mock()))
    with audio_session():
        pass
    com.CoUninitialize.assert_not_called()
