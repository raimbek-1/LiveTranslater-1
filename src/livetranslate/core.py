"""Platform-independent segmentation and subtitle presentation."""
import html
import re
from collections import deque
from dataclasses import dataclass
from enum import Enum

import numpy as np

RATE = 16000
FRAME = 512


class Mode(str, Enum):
    FULL = "Full Translation"
    SMART = "Smart Listening"
    GERMAN = "German Only"


class Segmenter:
    """512-sample frames, 192 ms pre-roll, 448 ms endpoint, 4 s hard limit.

    Probability comes from a separate, stateful Silero model per audio source.
    Hard splits retain 192 ms overlap to reduce clipped words.
    """
    def __init__(self, silence_frames=14, max_frames=125, min_frames=5):
        if silence_frames < 1 or max_frames <= silence_frames or min_frames < 1:
            raise ValueError("Invalid segmentation limits")
        self.silence_frames = silence_frames
        self.max_frames = max_frames
        self.min_frames = min_frames
        self.pre = deque(maxlen=6)
        self.active = []
        self.silent = 0
        self.voiced = 0

    def push(self, frame, probability):
        if len(frame) != FRAME:
            raise ValueError("Expected 512 samples at 16 kHz")
        frame = np.asarray(frame, dtype=np.float32).copy()
        speech = probability >= 0.5
        if not self.active:
            if not speech:
                self.pre.append(frame)
                return None
            self.active = list(self.pre)
            self.pre.clear()
        self.active.append(frame)
        self.voiced += int(speech)
        self.silent = 0 if speech else self.silent + 1
        forced = len(self.active) >= self.max_frames
        if self.silent < self.silence_frames and not forced:
            return None
        result = np.concatenate(self.active) if self.voiced >= self.min_frames else None
        tail = self.active[-6:] if forced else []
        self.active = []
        self.pre.extend(tail)
        self.silent = self.voiced = 0
        return result


WORDS = {
    "wann": "когда", "warum": "почему", "wo": "где", "wohin": "куда",
    "wer": "кто", "was": "что", "wie": "как", "welche": "какие",
    "können": "мочь", "könnten": "могли бы", "müssen": "должны",
    "möchten": "хотели бы", "termin": "встреча / запись", "zeit": "время",
    "heute": "сегодня", "morgen": "завтра", "bitte": "пожалуйста",
    "verstehen": "понимать", "wiederholen": "повторить", "brauchen": "нуждаться",
    "kosten": "стоить", "rechnung": "счёт", "hilfe": "помощь",
}
QUESTIONS = {
    "wann": "Спрашивают о времени. Ответьте: Am … / Um …",
    "warum": "Спрашивают о причине. Ответьте: Weil … (глагол в конце).",
    "wo": "Спрашивают о месте. Ответьте: In … / Bei …",
    "wohin": "Спрашивают о направлении. Ответьте: Nach … / Zu …",
    "wer": "Спрашивают о человеке.",
    "wie": "Спрашивают о способе или состоянии; учитывайте слова после wie.",
    "was": "Спрашивают о действии или предмете.",
}


def listening(text):
    tokens = re.findall(r"[\wÄÖÜäöüß]+", text.lower())
    keys = list(dict.fromkeys(t for t in tokens if t in WORDS))
    hint = next((QUESTIONS[t] for t in tokens if t in QUESTIONS), "")
    if not hint and "?" in text:
        hint = "Возможно, вопрос да/нет. Ответьте Ja / Nein и добавьте короткое пояснение."
    return keys, hint


@dataclass(frozen=True)
class Subtitle:
    source: str
    german: str
    russian: str
    latency: float = 0.0

    def render(self, mode):
        text = html.escape(self.german)
        keys, hint = listening(self.german)
        if mode == Mode.SMART:
            for key in keys:
                text = re.sub(r"\b" + re.escape(key) + r"\b",
                              lambda m: f'<b style="color:#74bdff">{m.group()}</b>',
                              text, flags=re.IGNORECASE)
        lines = [f'<small>{html.escape(self.source)}</small>', text]
        if mode == Mode.FULL:
            lines.append(html.escape(self.russian))
        elif mode == Mode.SMART:
            lines.append(" · ".join(f"{k}: {WORDS[k]}" for k in keys))
            if hint:
                lines.append(html.escape(hint))
        return "<br>".join(x for x in lines if x)
