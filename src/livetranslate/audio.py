"""Windows-only WASAPI capture; one independent reader/VAD per source."""
import queue
import sys
import time
from threading import Thread

import numpy as np

from .core import FRAME, RATE, Segmenter


def devices():
    if sys.platform != "win32":
        raise RuntimeError("Захват WASAPI доступен только в Windows 10/11")
    import pyaudiowpatch as pa
    with pa.PyAudio() as audio:
        wasapi = audio.get_host_api_info_by_type(pa.paWASAPI)
        return [(int(d["index"]), d["name"], bool(d.get("isLoopbackDevice")))
                for d in audio.get_device_info_generator()
                if d["hostApi"] == wasapi["index"] and d["maxInputChannels"] > 0]


def offer_latest(target, item):
    """Bound latency under overload: discard oldest complete utterance."""
    try:
        target.put_nowait(item)
        return False
    except queue.Full:
        try:
            target.get_nowait()
        except queue.Empty:
            pass
        target.put_nowait(item)
        return True


class Capture(Thread):
    def __init__(self, source, device, stop, utterances, notices):
        super().__init__(daemon=True, name=f"capture-{source}")
        self.source, self.device, self.stop = source, device, stop
        self.utterances, self.notices = utterances, notices

    def run(self):
        try:
            import pyaudiowpatch as pa
            import soxr
            import torch
            from silero_vad import load_silero_vad
            vad = load_silero_vad(onnx=True)
            segmenter = Segmenter()
            pending = np.empty(0, dtype=np.float32)
            with pa.PyAudio() as audio:
                device = (audio.get_device_info_by_index(self.device) if self.device is not None
                          else audio.get_default_wasapi_loopback() if self.source == "Система"
                          else audio.get_device_info_by_index(
                              int(audio.get_host_api_info_by_type(pa.paWASAPI)["defaultInputDevice"])))
                rate = int(device["defaultSampleRate"])
                channels = min(2, int(device["maxInputChannels"]))
                resampler = soxr.ResampleStream(rate, RATE, 1, dtype="float32")
                raw_frames = queue.Queue(maxsize=32)

                def callback(data, frame_count, time_info, flags):
                    if self.stop.is_set():
                        return None, pa.paComplete
                    if flags:
                        self.notices.put(("error", f"{self.source}: переполнение аудиобуфера"))
                        self.stop.set()
                        return None, pa.paAbort
                    try:
                        raw_frames.put_nowait(data)
                    except queue.Full:
                        self.notices.put(("error", f"{self.source}: VAD не успевает за аудио"))
                        self.stop.set()
                        return None, pa.paAbort
                    return None, pa.paContinue

                with audio.open(format=pa.paFloat32, channels=channels, rate=rate, input=True,
                                input_device_index=int(device["index"]),
                                frames_per_buffer=int(rate * 0.032), stream_callback=callback):
                    self.notices.put(("status", f"{self.source}: {device['name']}"))
                    while not self.stop.is_set():
                        try:
                            data = raw_frames.get(timeout=0.1)
                        except queue.Empty:
                            continue
                        mono = np.frombuffer(data, np.float32).reshape(-1, channels).mean(axis=1)
                        pending = np.concatenate((pending, resampler.resample_chunk(mono)))
                        while len(pending) >= FRAME:
                            frame, pending = pending[:FRAME], pending[FRAME:]
                            probability = float(vad(torch.from_numpy(frame.copy()), RATE).item())
                            result = segmenter.push(frame, probability)
                            if result is not None:
                                dropped = offer_latest(self.utterances, (self.source, result, time.monotonic()))
                                if dropped:
                                    self.notices.put(("status", "Перегрузка: пропущена старая реплика"))
        except Exception as exc:
            # Avoid audio/transcript content in diagnostics.
            self.notices.put(("error", f"{self.source}: {type(exc).__name__}: {exc}"))
            self.stop.set()
