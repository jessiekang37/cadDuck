"""Show a mirrored live feed from the default webcam."""

from collections import deque
import time

import cv2

try:
    from .gestures import GestureStateMachine, pinch_ratio
    from .filters import OneEuroFilter
    from .hands import HandTracker
except ImportError:  # Also allow: python tracker/capture.py
    from gestures import GestureStateMachine, pinch_ratio
    from filters import OneEuroFilter
    from hands import HandTracker


def main() -> None:
    camera = cv2.VideoCapture(0)
    if not camera.isOpened():
        camera.release()
        raise SystemExit(
            "Error: Could not open the default webcam. Check that a camera is "
            "connected and not in use by another application."
        )

    previous_frame_time = time.perf_counter()
    try:
        with HandTracker() as tracker:
            gestures = GestureStateMachine()
            pinch_x_filter = OneEuroFilter(min_cutoff=1.0, beta=0.02)
            pinch_y_filter = OneEuroFilter(min_cutoff=1.0, beta=0.02)
            raw_trail = deque(maxlen=60)
            filtered_trail = deque(maxlen=60)
            while True:
                success, frame = camera.read()
                if not success:
                    print("Error: Could not read a frame from the webcam.")
                    break

                frame = cv2.flip(frame, 1)
                current_time = time.perf_counter()
                elapsed = current_time - previous_frame_time
                previous_frame_time = current_time
                fps = 1.0 / elapsed if elapsed > 0 else 0.0
                hands = tracker.process_frame(frame)
                if hands:
                    landmarks, _handedness = hands[0]
                    state = gestures.update(landmarks, now=current_time)
                    ratio_text = f"{pinch_ratio(landmarks):.2f}"
                    raw_x = (landmarks[4, 0] + landmarks[8, 0]) / 2.0
                    raw_y = (landmarks[4, 1] + landmarks[8, 1]) / 2.0
                    filtered_x = pinch_x_filter.filter(raw_x, current_time)
                    filtered_y = pinch_y_filter.filter(raw_y, current_time)
                    height, width = frame.shape[:2]
                    raw_point = (int(raw_x * width), int(raw_y * height))
                    filtered_point = (int(filtered_x * width), int(filtered_y * height))
                    raw_trail.append(raw_point)
                    filtered_trail.append(filtered_point)
                else:
                    state = gestures.update(None, now=current_time)
                    ratio_text = "N/A"
                    pinch_x_filter.reset()
                    pinch_y_filter.reset()
                    raw_trail.clear()
                    filtered_trail.clear()

                # Magenta is the raw pinch midpoint; yellow is the filtered one.
                for trail, color in (
                    (raw_trail, (255, 0, 255)),
                    (filtered_trail, (0, 255, 255)),
                ):
                    for previous, current in zip(trail, list(trail)[1:]):
                        cv2.line(frame, previous, current, color, 2, cv2.LINE_AA)
                if raw_trail:
                    cv2.circle(frame, raw_trail[-1], 5, (255, 0, 255), -1)
                    cv2.circle(frame, filtered_trail[-1], 5, (0, 255, 255), -1)

                cv2.putText(
                    frame,
                    f"FPS: {fps:.1f}",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 0),
                    2,
                    cv2.LINE_AA,
                )
                cv2.putText(
                    frame,
                    "Pinch trail: raw magenta / filtered yellow",
                    (10, 90),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )
                cv2.putText(
                    frame,
                    f"State: {state.value}  Pinch: {ratio_text}",
                    (10, 62),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 255),
                    2,
                    cv2.LINE_AA,
                )
                cv2.imshow("Webcam", frame)

                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        camera.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
