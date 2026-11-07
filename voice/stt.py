"""Push-to-talk speech transcription with faster-whisper.

``VoiceInput`` records audio only while Space is held, then transcribes the
finished clip on a worker thread. Start it while the OpenCV tracker preview is
running; the Windows keyboard hook checks that the ``Webcam`` window is in
front before starting a recording.
"""

from collections.abc import Callable
import json
import queue
import sys
import threading

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from pynput import keyboard

from .parser import parse_transcript


class VoiceInput:
    """Record on Space-down, transcribe on Space-up, and dispatch commands."""

    def __init__(
        self,
        on_command: Callable[[dict], None] | None = None,
        model_size: str = "tiny",
        sample_rate: int = 16000,
        window_title: str = "Webcam",
    ) -> None:
        if model_size not in {"tiny", "base"}:
            raise ValueError("model_size must be 'tiny' or 'base'")
        self.on_command = on_command
        self.model_size = model_size
        self.sample_rate = sample_rate
        self.window_title = window_title
        self._lock = threading.Lock()
        self._recording = False
        self._chunks: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._jobs: queue.Queue[np.ndarray | None] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._listener: keyboard.Listener | None = None
        self._model: WhisperModel | None = None

    def start(self) -> None:
        """Start the transcription worker and Space-key listener."""
        if self._listener is not None:
            return
        self._worker = threading.Thread(
            target=self._transcription_worker,
            name="gesturecad-whisper",
            daemon=True,
        )
        self._worker.start()
        listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        listener.start()
        self._listener = listener
        print(f"Voice input ready: hold Space to record ({self.model_size} model).")

    def _tracker_window_is_focused(self) -> bool:
        """Best-effort foreground check on Windows; allow other platforms."""
        if sys.platform != "win32":
            return True
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        title_length = user32.GetWindowTextLengthW(hwnd)
        title_buffer = ctypes.create_unicode_buffer(title_length + 1)
        user32.GetWindowTextW(hwnd, title_buffer, title_length + 1)
        return self.window_title.casefold() in title_buffer.value.casefold()

    def _on_key_press(self, key) -> None:
        if key != keyboard.Key.space or not self._tracker_window_is_focused():
            return
        with self._lock:
            if self._recording:
                return
            self._recording = True
            self._chunks = []
        try:
            stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                callback=self._audio_callback,
            )
            stream.start()
            with self._lock:
                self._stream = stream
            print("Recording… release Space to transcribe.")
        except Exception as error:
            with self._lock:
                self._recording = False
                self._stream = None
            print(f"Voice input: microphone could not start: {error}")

    def _audio_callback(self, audio, _frames, _time_info, status) -> None:
        if status:
            print(f"Voice input: audio status: {status}")
        with self._lock:
            if self._recording:
                self._chunks.append(audio.copy())

    def _on_key_release(self, key) -> None:
        if key == keyboard.Key.space:
            self._finish_recording()

    def _finish_recording(self) -> None:
        with self._lock:
            if not self._recording:
                return
            self._recording = False
            stream = self._stream
            self._stream = None
            chunks, self._chunks = self._chunks, []

        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception as error:
                print(f"Voice input: microphone could not stop cleanly: {error}")
        if not chunks:
            print("Voice input: no audio was recorded.")
            return
        audio = np.concatenate(chunks, axis=0).reshape(-1)
        if len(audio) < int(self.sample_rate * 0.15):
            print("Voice input: recording was too short.")
            return
        self._jobs.put(audio)

    def _transcription_worker(self) -> None:
        try:
            self._model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type="int8",
            )
            print("Voice input: speech model loaded.")
        except Exception as error:
            print(f"Voice input: could not load faster-whisper: {error}")
            return

        while True:
            audio = self._jobs.get()
            if audio is None:
                return
            try:
                segments, _info = self._model.transcribe(
                    audio,
                    language="en",
                    beam_size=1,
                    vad_filter=True,
                )
                transcript = " ".join(segment.text.strip() for segment in segments).strip()
                command = parse_transcript(transcript)
                print(f"Transcript: {transcript or '(empty)'}")
                print(
                    "Parsed command: "
                    + (json.dumps(command, separators=(",", ":")) if command else "None")
                )
                if command is not None and self.on_command is not None:
                    self.on_command(command)
            except Exception as error:
                print(f"Voice input: transcription failed: {error}")

    def stop(self) -> None:
        """Stop recording hooks and finish the worker thread."""
        if self._listener is not None:
            self._listener.stop()
            self._listener.join(timeout=2.0)
            self._listener = None
        self._finish_recording()
        self._jobs.put(None)
        if self._worker is not None:
            self._worker.join(timeout=10.0)
            self._worker = None
