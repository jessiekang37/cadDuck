"""Map grabbed pinch-point motion to GestureCAD bridge messages."""

import math


SENSITIVITY = 2.0
_DISTANCE_EPSILON = 1e-6
_MOTION_EPSILON = 1e-5


def map_to_viewport(
    x: float,
    y: float,
    calibration_rect: tuple[float, float, float, float],
) -> tuple[float, float]:
    """Map normalized image x/y to normalized viewport u/v.

    ``calibration_rect`` is ``(left, top, right, bottom)`` in normalized
    image coordinates. The result is clamped to [0, 1], and viewport v is
    bottom-up while image y is top-down.
    """
    left, top, right, bottom = calibration_rect
    if not (0.0 <= left < right <= 1.0 and 0.0 <= top < bottom <= 1.0):
        raise ValueError("calibration rectangle must be ordered within [0, 1]")
    u = min(1.0, max(0.0, (x - left) / (right - left)))
    v = min(1.0, max(0.0, 1.0 - (y - top) / (bottom - top)))
    return u, v


class GestureBridgeController:
    """Create translation or two-hand scale/rotation messages.

    Coordinates are normalized image coordinates. A change in interaction
    mode or participating hand keys resets the reference and emits nothing
    for that frame, providing a clutch that prevents object jumps.
    """

    def __init__(self, sensitivity: float = SENSITIVITY) -> None:
        self.sensitivity = float(sensitivity)
        self._mode = "idle"
        self._hand_keys: tuple[str, ...] = ()
        self._reference_points: dict[str, tuple[float, float]] = {}
        self._reference_distance: float | None = None
        self._reference_angle: float | None = None

    @property
    def mode(self) -> str:
        """Current bridge interaction mode: idle, translate, or bimanual."""
        return self._mode

    def _set_reference(self, points: dict[str, tuple[float, float]]) -> None:
        keys = tuple(sorted(points))
        self._mode = {0: "idle", 1: "translate", 2: "bimanual"}[len(keys)]
        self._hand_keys = keys
        self._reference_points = {key: points[key] for key in keys}
        self._reference_distance = None
        self._reference_angle = None
        if len(keys) == 2:
            first, second = (self._reference_points[key] for key in keys)
            dx, dy = second[0] - first[0], second[1] - first[1]
            self._reference_distance = math.hypot(dx, dy)
            self._reference_angle = math.atan2(dy, dx)

    def update(
        self, grabbed_points: dict[str, tuple[float, float]]
    ) -> list[dict[str, float | str]]:
        """Return zero or more bridge messages for this frame's grabbed hands."""
        if len(grabbed_points) > 2:
            raise ValueError("at most two grabbed hands are supported")
        keys = tuple(sorted(grabbed_points))
        expected_mode = {0: "idle", 1: "translate", 2: "bimanual"}[len(keys)]
        if expected_mode != self._mode or keys != self._hand_keys:
            self._set_reference(grabbed_points)
            return []
        if not keys:
            return []

        points = {key: grabbed_points[key] for key in keys}
        messages: list[dict[str, float | str]] = []
        if len(keys) == 1:
            key = keys[0]
            previous_x, previous_y = self._reference_points[key]
            current_x, current_y = points[key]
            dx = (current_x - previous_x) * self.sensitivity
            # Image y grows downward; Blender's view-plane y grows upward.
            dy = (previous_y - current_y) * self.sensitivity
            if abs(dx) > _MOTION_EPSILON or abs(dy) > _MOTION_EPSILON:
                messages.append({"type": "translate", "dx": dx, "dy": dy})
            self._reference_points[key] = points[key]
            return messages

        first, second = (points[key] for key in keys)
        dx, dy = second[0] - first[0], second[1] - first[1]
        distance = math.hypot(dx, dy)
        angle = math.atan2(dy, dx)
        previous_distance = self._reference_distance
        previous_angle = self._reference_angle
        if (
            previous_distance is not None
            and previous_distance > _DISTANCE_EPSILON
            and distance > _DISTANCE_EPSILON
        ):
            factor = distance / previous_distance
            if abs(factor - 1.0) > _MOTION_EPSILON:
                messages.append({"type": "scale", "factor": factor})
        if previous_angle is not None:
            angle_delta = math.atan2(
                math.sin(angle - previous_angle), math.cos(angle - previous_angle)
            )
            if abs(angle_delta) > _MOTION_EPSILON:
                messages.append(
                    {"type": "rotate", "axis": "z", "radians": angle_delta}
                )
        self._reference_points = points
        self._reference_distance = distance
        self._reference_angle = angle
        return messages
