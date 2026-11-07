"""Pure landmark measurements and gesture state transitions."""

from enum import Enum
import time

import numpy as np


WRIST = 0
THUMB_TIP = 4
INDEX_MCP, INDEX_PIP, INDEX_TIP = 5, 6, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP = 9, 10, 12
RING_MCP, RING_PIP, RING_TIP = 13, 14, 16
PINKY_MCP, PINKY_PIP, PINKY_TIP = 17, 18, 20


def _points(landmarks: np.ndarray) -> np.ndarray:
    points = np.asarray(landmarks, dtype=float)
    if points.shape != (21, 3):
        raise ValueError(f"landmarks must have shape (21, 3), got {points.shape}")
    return points


def hand_size(landmarks: np.ndarray) -> float:
    """Return wrist-to-middle-MCP distance as the hand scale."""
    points = _points(landmarks)
    return float(np.linalg.norm(points[WRIST] - points[MIDDLE_MCP]))


def pinch_ratio(landmarks: np.ndarray) -> float:
    """Return thumb-tip to index-tip distance normalized by hand size."""
    points = _points(landmarks)
    scale = hand_size(points)
    if scale == 0:
        raise ValueError("hand_size is zero; landmarks cannot be normalized")
    return float(np.linalg.norm(points[THUMB_TIP] - points[INDEX_TIP]) / scale)


def is_open_palm(landmarks: np.ndarray) -> bool:
    """Return true when index, middle, ring, and pinky fingers are extended.

    Extension is estimated orientation-independently by checking that each
    fingertip is farther from its MCP joint than its PIP joint is.
    """
    points = _points(landmarks)
    fingers = (
        (INDEX_MCP, INDEX_PIP, INDEX_TIP),
        (MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP),
        (RING_MCP, RING_PIP, RING_TIP),
        (PINKY_MCP, PINKY_PIP, PINKY_TIP),
    )
    return all(
        np.linalg.norm(points[tip] - points[mcp])
        > np.linalg.norm(points[pip] - points[mcp])
        for mcp, pip, tip in fingers
    )


class GestureState(str, Enum):
    PAUSED = "PAUSED"
    ENGAGED = "ENGAGED"
    GRABBING = "GRABBING"


class GestureStateMachine:
    """Apply timed palm activation and hysteretic pinch transitions."""

    def __init__(self, engage_seconds: float = 0.5) -> None:
        self.state = GestureState.PAUSED
        self.engage_seconds = engage_seconds
        self._open_since: float | None = None

    def update(
        self, landmarks: np.ndarray | None, now: float | None = None
    ) -> GestureState:
        """Update state from a hand (or ``None`` when no hand is detected).

        ``now`` is seconds on a monotonic clock and can be supplied for
        deterministic timing in tests.
        """
        now = time.monotonic() if now is None else now
        if landmarks is None:
            self.state = GestureState.PAUSED
            self._open_since = None
            return self.state

        points = _points(landmarks)
        palm_open = is_open_palm(points)
        ratio = pinch_ratio(points)

        if self.state is GestureState.PAUSED:
            if palm_open:
                if self._open_since is None:
                    self._open_since = now
                if now - self._open_since >= self.engage_seconds:
                    self.state = GestureState.ENGAGED
            else:
                self._open_since = None
        elif self.state is GestureState.ENGAGED:
            if ratio < 0.25:
                self.state = GestureState.GRABBING
        elif self.state is GestureState.GRABBING and ratio > 0.40:
            self.state = GestureState.ENGAGED

        return self.state
