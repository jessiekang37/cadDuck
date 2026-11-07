"""Show the mirrored hand-tracking and GestureCAD bridge demo."""

import argparse
from collections import deque
import json
from pathlib import Path
import sys
import time

import cv2

if __package__ in {None, ""}:  # Support: python tracker/demo_capture.py
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from ..bridge.sender import UDPSender
    from .bridge_control import GestureBridgeController, map_to_viewport
    from .filters import OneEuroFilter
    from .gestures import GestureState, GestureStateMachine, pinch_ratio
    from .hands import HandTracker
except ImportError:  # Running as a script from the project root.
    from bridge.sender import UDPSender
    from tracker.bridge_control import GestureBridgeController, map_to_viewport
    from tracker.filters import OneEuroFilter
    from tracker.gestures import GestureState, GestureStateMachine, pinch_ratio
    from tracker.hands import HandTracker


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print bridge JSON instead of sending UDP messages",
    )
    parser.add_argument(
        "--calibrate",
        action="store_true",
        help="show the camera calibration rectangle on the preview",
    )
    parser.add_argument(
        "--calibration-rect",
        type=float,
        nargs=4,
        metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"),
        default=(0.2, 0.2, 0.8, 0.8),
        help="calibration rectangle in normalized frame coordinates (default: 0.2 0.2 0.8 0.8)",
    )
    parser.add_argument(
        "--voice",
        action="store_true",
        help="enable push-to-talk voice commands (hold Space in the Webcam window)",
    )
    parser.add_argument(
        "--stt-model",
        choices=("tiny", "base"),
        default="tiny",
        help="faster-whisper model size for --voice (default: tiny)",
    )
    args = parser.parse_args(argv)
    calibration_rect = tuple(args.calibration_rect)
    try:
        map_to_viewport(0.5, 0.5, calibration_rect)
    except ValueError as error:
        parser.error(str(error))

    camera = cv2.VideoCapture(0)
    if not camera.isOpened():
        camera.release()
        raise SystemExit(
            "Error: Could not open the default webcam. Check that a camera is "
            "connected and not in use by another application."
        )

    sender = None if args.dry_run else UDPSender()
    previous_frame_time = time.perf_counter()
    gesture_states: dict[str, GestureStateMachine] = {}
    pinch_filters: dict[str, tuple[OneEuroFilter, OneEuroFilter]] = {}
    index_filters: dict[str, tuple[OneEuroFilter, OneEuroFilter]] = {}
    last_cursor_uv: tuple[float, float] | None = None
    raw_trail: deque[tuple[int, int]] = deque(maxlen=60)
    filtered_trail: deque[tuple[int, int]] = deque(maxlen=60)
    controller = GestureBridgeController()
    voice_input = None

    try:
        if args.voice:
            from voice.stt import VoiceInput

            def dispatch_voice_command(command: dict) -> None:
                if args.dry_run:
                    print("Would send: " + json.dumps(command, separators=(",", ":")))
                else:
                    sender.send(command)

            voice_input = VoiceInput(
                on_command=dispatch_voice_command,
                model_size=args.stt_model,
            )
            voice_input.start()

        with HandTracker() as tracker:
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
                detected_hands = tracker.process_frame(frame)
                current_keys: set[str] = set()
                grabbed_points: dict[str, tuple[float, float]] = {}
                ratios: list[float] = []
                visible_states: list[GestureState] = []
                filtered_index_tip: tuple[float, float] | None = None

                for hand_index, (landmarks, handedness) in enumerate(detected_hands):
                    hand_key = handedness if handedness != "Unknown" else f"hand-{hand_index}"
                    current_keys.add(hand_key)
                    machine = gesture_states.setdefault(hand_key, GestureStateMachine())
                    hand_state = machine.update(landmarks, now=current_time)
                    visible_states.append(hand_state)
                    ratios.append(pinch_ratio(landmarks))

                    filters = pinch_filters.setdefault(
                        hand_key,
                        (OneEuroFilter(min_cutoff=1.0, beta=0.02),
                         OneEuroFilter(min_cutoff=1.0, beta=0.02)),
                    )
                    raw_x = (landmarks[4, 0] + landmarks[8, 0]) / 2.0
                    raw_y = (landmarks[4, 1] + landmarks[8, 1]) / 2.0
                    filtered_x = filters[0].filter(raw_x, current_time)
                    filtered_y = filters[1].filter(raw_y, current_time)

                    tip_filters = index_filters.setdefault(
                        hand_key,
                        (OneEuroFilter(min_cutoff=1.0, beta=0.02),
                         OneEuroFilter(min_cutoff=1.0, beta=0.02)),
                    )
                    filtered_tip_x = tip_filters[0].filter(
                        landmarks[8, 0], current_time
                    )
                    filtered_tip_y = tip_filters[1].filter(
                        landmarks[8, 1], current_time
                    )
                    if hand_index == 0:
                        filtered_index_tip = (filtered_tip_x, filtered_tip_y)
                    if hand_state is GestureState.GRABBING:
                        grabbed_points[hand_key] = (filtered_x, filtered_y)

                    if hand_index == 0:
                        height, width = frame.shape[:2]
                        raw_trail.append((int(raw_x * width), int(raw_y * height)))
                        filtered_trail.append(
                            (int(filtered_x * width), int(filtered_y * height))
                        )

                for hand_key in set(gesture_states) - current_keys:
                    gesture_states[hand_key].update(None, now=current_time)
                    for coordinate_filter in pinch_filters[hand_key]:
                        coordinate_filter.reset()
                if not detected_hands:
                    raw_trail.clear()
                    filtered_trail.clear()
                    last_cursor_uv = None

                cursor_uv = None
                if filtered_index_tip is not None:
                    cursor_uv = map_to_viewport(
                        filtered_index_tip[0], filtered_index_tip[1], calibration_rect
                    )
                    if (
                        last_cursor_uv is None
                        or abs(cursor_uv[0] - last_cursor_uv[0]) > 0.0005
                        or abs(cursor_uv[1] - last_cursor_uv[1]) > 0.0005
                    ):
                        cursor_message = {
                            "type": "cursor",
                            "u": cursor_uv[0],
                            "v": cursor_uv[1],
                        }
                        if args.dry_run:
                            print(json.dumps(cursor_message, separators=(",", ":")))
                        else:
                            sender.send(cursor_message)
                    last_cursor_uv = cursor_uv

                messages = controller.update(grabbed_points)
                for message in messages:
                    if args.dry_run:
                        print(json.dumps(message, separators=(",", ":")))
                    else:
                        sender.send(message)

                for trail, color in (
                    (raw_trail, (255, 0, 255)),
                    (filtered_trail, (0, 255, 255)),
                ):
                    trail_points = list(trail)
                    for previous, current in zip(trail_points, trail_points[1:]):
                        cv2.line(frame, previous, current, color, 2, cv2.LINE_AA)
                if raw_trail:
                    cv2.circle(frame, raw_trail[-1], 5, (255, 0, 255), -1)
                    cv2.circle(frame, filtered_trail[-1], 5, (0, 255, 255), -1)

                if args.calibrate:
                    height, width = frame.shape[:2]
                    left, top, right, bottom = calibration_rect
                    box_top_left = (int(left * width), int(top * height))
                    box_bottom_right = (int(right * width), int(bottom * height))
                    cv2.rectangle(frame, box_top_left, box_bottom_right, (255, 255, 0), 2)
                    if filtered_index_tip is not None:
                        tip_pixel = (
                            int(filtered_index_tip[0] * width),
                            int(filtered_index_tip[1] * height),
                        )
                        cv2.circle(frame, tip_pixel, 7, (0, 165, 255), 2)
                    cv2.putText(
                        frame,
                        "Calibration: LEFT TOP RIGHT BOTTOM (normalized)",
                        (10, 144),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (255, 255, 0),
                        1,
                        cv2.LINE_AA,
                    )

                if GestureState.GRABBING in visible_states:
                    state_text = f"GRABBING ({len(grabbed_points)} hand(s))"
                elif GestureState.ENGAGED in visible_states:
                    state_text = "ENGAGED"
                else:
                    state_text = "PAUSED"
                ratio_text = f"{ratios[0]:.2f}" if ratios else "N/A"
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
                if args.voice:
                    cv2.putText(
                        frame,
                        "Voice: hold SPACE to record, release to parse",
                        (10, 170),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (255, 255, 255),
                        1,
                        cv2.LINE_AA,
                    )
                cv2.putText(
                    frame,
                    f"State: {state_text}  Pinch: {ratio_text}",
                    (10, 62),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 255),
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
                    f"Bridge: {controller.mode} | {'dry-run' if args.dry_run else 'UDP'}",
                    (10, 116),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )
                cv2.imshow("Webcam", frame)

                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        if voice_input is not None:
            voice_input.stop()
        camera.release()
        cv2.destroyAllWindows()
        if sender is not None:
            sender.close()


if __name__ == "__main__":
    main()
