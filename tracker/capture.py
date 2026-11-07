"""Show a mirrored live feed from the default webcam."""

import time

import cv2

try:
    from .gestures import GestureStateMachine, pinch_ratio
    from .hands import HandTracker
except ImportError:  # Also allow: python tracker/capture.py
    from gestures import GestureStateMachine, pinch_ratio
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
                else:
                    state = gestures.update(None, now=current_time)
                    ratio_text = "N/A"

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
