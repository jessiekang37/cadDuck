"""VIDEO-mode MediaPipe Tasks hand tracking for OpenCV BGR frames.

Download the model with ``python tracker/download_model.py``. The model is
stored at ``tracker/hand_landmarker.task`` by default.

Landmark indices: wrist 0; thumb CMC/MCP/IP/tip 1/2/3/4; index MCP/PIP/DIP/tip
5/6/7/8; middle MCP/PIP/DIP/tip 9/10/11/12; ring MCP/PIP/DIP/tip 13/14/15/16;
pinky MCP/PIP/DIP/tip 17/18/19/20.
"""

from pathlib import Path
import time

import cv2
import mediapipe as mp
import numpy as np


MODEL_PATH = Path(__file__).with_name("hand_landmarker.task")
_HAND_CONNECTIONS = mp.tasks.vision.HandLandmarksConnections.HAND_CONNECTIONS


class HandTracker:
    """Track up to two hands in successive video frames.

    ``process_frame`` annotates the supplied BGR frame in place and returns a
    list of ``(landmarks, handedness)`` pairs. Each landmarks array has shape
    ``(21, 3)`` and contains normalized image-space x, y, z coordinates.
    """

    def __init__(self, model_path: str | Path = MODEL_PATH) -> None:
        model_path = Path(model_path)
        if not model_path.is_file():
            raise FileNotFoundError(
                f"Hand Landmarker model not found at {model_path}. "
                "Run 'python tracker/download_model.py' to download it."
            )

        options = mp.tasks.vision.HandLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path)),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_hands=2,
        )
        self._landmarker = mp.tasks.vision.HandLandmarker.create_from_options(options)
        self._last_timestamp_ms = -1

    def process_frame(
        self, frame: np.ndarray, timestamp_ms: int | None = None
    ) -> list[tuple[np.ndarray, str]]:
        """Detect and draw hands on a BGR frame; return landmarks and labels."""
        if timestamp_ms is None:
            timestamp_ms = time.monotonic_ns() // 1_000_000
        timestamp_ms = max(int(timestamp_ms), self._last_timestamp_ms + 1)
        self._last_timestamp_ms = timestamp_ms

        height, width = frame.shape[:2]
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        result = self._landmarker.detect_for_video(image, timestamp_ms)

        hands: list[tuple[np.ndarray, str]] = []
        for hand_index, hand_landmarks in enumerate(result.hand_landmarks):
            points = np.asarray(
                [(point.x, point.y, point.z) for point in hand_landmarks],
                dtype=np.float32,
            )
            handedness = "Unknown"
            if hand_index < len(result.handedness) and result.handedness[hand_index]:
                handedness = result.handedness[hand_index][0].category_name
            hands.append((points, handedness))

            pixels = [
                (int(point[0] * width), int(point[1] * height)) for point in points
            ]
            for connection in _HAND_CONNECTIONS:
                cv2.line(
                    frame,
                    pixels[connection.start],
                    pixels[connection.end],
                    (0, 220, 0),
                    2,
                )
            for x, y in pixels:
                cv2.circle(frame, (x, y), 4, (0, 0, 255), -1)

            wrist_x, wrist_y = pixels[0]
            cv2.putText(
                frame,
                handedness,
                (wrist_x, max(wrist_y - 12, 20)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 0, 0),
                2,
                cv2.LINE_AA,
            )

        return hands

    def close(self) -> None:
        """Release the MediaPipe task resources."""
        self._landmarker.close()

    def __enter__(self) -> "HandTracker":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


def process_frame(
    tracker: HandTracker, frame: np.ndarray, timestamp_ms: int | None = None
) -> list[tuple[np.ndarray, str]]:
    """Module-level helper; re-use one ``HandTracker`` across video frames."""
    return tracker.process_frame(frame, timestamp_ms)
