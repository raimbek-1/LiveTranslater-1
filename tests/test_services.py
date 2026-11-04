import queue
from unittest.mock import Mock

import pytest

from livetranslate.assistant import make_prompt, suggest
from livetranslate.audio import offer_latest
from livetranslate.windows import display_affinity


def test_overload_drops_oldest_utterance():
    target = queue.Queue(maxsize=2)
    assert not offer_latest(target, 'old')
    assert not offer_latest(target, 'middle')
    assert offer_latest(target, 'new')
    assert [target.get_nowait(), target.get_nowait()] == ['middle', 'new']


@pytest.mark.parametrize('level', ['A1', 'A2', 'B1', 'B2'])
def test_level_in_prompt(level):
    assert f'CEFR {level}' in make_prompt('Я приду завтра', level)


@pytest.mark.parametrize('intent,level', [('', 'A1'), ('ok', 'C2'), ('x'*2001, 'B1')])
def test_invalid_reply_input(intent, level):
    with pytest.raises(ValueError):
        make_prompt(intent, level)


def test_reply_uses_only_loopback_and_validates_output(monkeypatch):
    import requests
    session = Mock()
    monkeypatch.setattr(requests, 'Session', lambda: session)
    result = dict(german='Ich komme morgen.', russian='Я приду завтра.', pronunciation='ɪç', tip='Короткий ответ')
    import json
    session.post.return_value.json.return_value = {'response': json.dumps(result)}
    assert suggest('Я приду завтра', 'A1') == result
    assert session.trust_env is False
    assert session.post.call_args.args[0] == 'http://127.0.0.1:11434/api/generate'
    session.close.assert_called_once()
    session.post.return_value.json.return_value = {'response': '{}'}
    with pytest.raises(ValueError):
        suggest('Ответ', 'B1')


def test_capture_exclusion_not_claimed_on_linux():
    import sys
    if sys.platform != 'win32':
        ok, message = display_affinity(0, True)
        assert not ok and 'Windows' in message


def test_private_overlay_checks_api_and_readback(monkeypatch):
    from types import SimpleNamespace

    from livetranslate import windows
    api = Mock()
    api.SetWindowDisplayAffinity.return_value = 1

    def readback(hwnd, value):
        value._obj.value = windows.WDA_EXCLUDEFROMCAPTURE
        return 1

    api.GetWindowDisplayAffinity.side_effect = readback
    monkeypatch.setattr(windows, 'user32', lambda: api)
    monkeypatch.setattr(windows.sys, 'platform', 'win32')
    monkeypatch.setattr(windows.sys, 'getwindowsversion', lambda: SimpleNamespace(build=19045), raising=False)
    assert windows.display_affinity(1234, True)[0]
    api.SetWindowDisplayAffinity.assert_called_once_with(1234, 0x11)
    api.GetWindowDisplayAffinity.side_effect = lambda hwnd, value: 1
    assert not windows.display_affinity(1234, True)[0]


def test_old_windows_does_not_claim_capture_exclusion(monkeypatch):
    from types import SimpleNamespace

    from livetranslate import windows
    api = Mock()
    monkeypatch.setattr(windows, 'user32', lambda: api)
    monkeypatch.setattr(windows.sys, 'platform', 'win32')
    monkeypatch.setattr(windows.sys, 'getwindowsversion', lambda: SimpleNamespace(build=18363), raising=False)
    assert not windows.display_affinity(1234, True)[0]
    api.SetWindowDisplayAffinity.assert_not_called()


def test_hotkey_conflicts_and_cleanup(monkeypatch):
    from livetranslate import windows
    api = Mock()
    api.RegisterHotKey.side_effect = [1, 0, 1]
    monkeypatch.setattr(windows, 'user32', lambda: api)
    monkeypatch.setattr(windows.sys, 'platform', 'win32')
    hotkeys = windows.Hotkeys(1234)
    assert len(hotkeys.register()) == 1
    assert hotkeys.registered == [1, 3]
    hotkeys.close()
    assert api.UnregisterHotKey.call_count == 2
    assert not hotkeys.registered
