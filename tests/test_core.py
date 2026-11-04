import numpy as np
import pytest

from livetranslate.core import FRAME, Mode, Segmenter, Subtitle, listening


def frame(value=0.1):
    return np.full(FRAME, value, np.float32)


def test_silence_does_not_generate_subtitles():
    segmenter = Segmenter()
    assert all(segmenter.push(frame(0), 0.1) is None for _ in range(1000))


def test_endpoint_keeps_preroll_and_short_pause():
    segmenter = Segmenter()
    for _ in range(10):
        segmenter.push(frame(0), 0)
    for _ in range(10):
        assert segmenter.push(frame(), 0.9) is None
    for _ in range(13):
        assert segmenter.push(frame(0), 0) is None
    result = segmenter.push(frame(0), 0)
    assert len(result) == (6 + 10 + 14) * FRAME
    assert result.dtype == np.float32
    assert np.all(result[:6 * FRAME] == 0)
    assert segmenter.push(frame(0), 0) is None


def test_noise_burst_is_discarded():
    segmenter = Segmenter()
    for _ in range(3):
        segmenter.push(frame(), 1)
    results = [segmenter.push(frame(0), 0) for _ in range(14)]
    assert all(x is None for x in results)


def test_long_speech_is_bounded():
    segmenter = Segmenter()
    results = [r for _ in range(400) if (r := segmenter.push(frame(), 1)) is not None]
    assert len(results) == 3
    assert all(len(r) <= 125 * FRAME for r in results)


def test_wrong_frame_rejected():
    with pytest.raises(ValueError):
        Segmenter().push(np.zeros(500), 1)


def test_modes_and_html_injection():
    subtitle = Subtitle("<mic>", 'Wann ist der Termin? <script>alert(1)</script>', 'Когда встреча?')
    full = subtitle.render(Mode.FULL)
    assert 'Когда встреча?' in full
    assert '<script>' not in full and '&lt;script&gt;' in full
    assert '&lt;mic&gt;' in full
    smart = subtitle.render(Mode.SMART)
    assert '<b style=' in smart and 'времени' in smart
    assert 'Когда встреча?' not in smart
    german = subtitle.render(Mode.GERMAN)
    assert 'Когда встреча?' not in german and 'времени' not in german


def test_keyword_order_and_deduplication():
    keys, hint = listening('Wann, WANN können wir morgen kommen?')
    assert keys == ['wann', 'können', 'morgen']
    assert 'времени' in hint
