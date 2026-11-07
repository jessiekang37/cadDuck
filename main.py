"""Unified GestureCAD webcam tracker, voice input, and bridge application."""

import argparse
from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
import queue
import time

import cv2

from bridge.sender import UDPSender
from tracker.bridge_control import GestureBridgeController, map_to_viewport
from tracker.filters import OneEuroFilter
from tracker.gestures import GestureState, GestureStateMachine, pinch_ratio
from tracker.hands import HandTracker, MODEL_PATH


CONFIRM_SECONDS = 1.5


class EventLog:
    """Append timestamped JSON events to a newline-delimited JSON file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a", encoding="utf-8")

    def write(self, event: str, **details) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "event": event,
            **details,
        }
        self._file.write(json.dumps(entry, ensure_ascii=False, allow_nan=False) + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()


def _format_command(command: dict) -> str:
    kind = command.get("type")
    if kind == "command" and command.get("op") == "move":
        value = command["value"]
        magnitude = abs(value)
        if magnitude >= 1.0:
            amount, unit = magnitude, "m"
        elif magnitude >= 0.01:
            amount, unit = magnitude * 100, "cm"
        else:
            amount, unit = magnitude * 1000, "mm"
        axis = command["axis"].upper()
        sign = "+" if value >= 0 else "-"
        return f"move {sign}{axis} {amount:g} {unit}"
    if kind == "command" and command.get("op") == "extrude":
        magnitude = abs(command["value"])
        if magnitude >= 1.0:
            amount, unit = magnitude, "m"
        elif magnitude >= 0.01:
            amount, unit = magnitude * 100, "cm"
        else:
            amount, unit = magnitude * 1000, "mm"
        return f"extrude {amount:g} {unit}"
    if kind == "rotate":
        degrees = command["radians"] * 180.0 / 3.141592653589793
        return f"rotate {command['axis'].upper()} {degrees:g} deg"
    if kind == "scale":
        return f"scale x{command['factor']:g}"
    if kind == "select":
        return f"select {command['name']}"
    if kind == "undo":
        return "undo"
    return json.dumps(command, separators=(",", ":"))


def _draw_text(frame, text: str, y: int, color=(255, 255, 255), scale=0.55) -> None:
    height, width = frame.shape[:2]
    max_chars = max(20, int(width / (scale * 13)))
    if len(text) > max_chars:
        text = text[: max_chars - 3] + "..."
    cv2.putText(
        frame,
        text,
        (10, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        color,
        1 if scale < 0.7 else 2,
        cv2.LINE_AA,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print bridge messages instead of sending")
    parser.add_argument("--calibrate", action="store_true", help="show the camera calibration rectangle")
    parser.add_argument(
        "--calibration-rect",
        type=float,
        nargs=4,
        metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"),
        default=(0.2, 0.2, 0.8, 0.8),
        help="normalized camera rectangle; default: 0.2 0.2 0.8 0.8",
    )
    voice_group = parser.add_mutually_exclusive_group()
    voice_group.add_argument("--voice", dest="voice", action="store_true", help="enable push-to-talk voice input")
    voice_group.add_argument("--no-voice", dest="voice", action="store_false", help="disable voice input")
    parser.set_defaults(voice=True)
    parser.add_argument("--stt-model", choices=("tiny", "base"), default="tiny")
    parser.add_argument("--no-confirm", action="store_true", help="send parsed voice commands immediately")
    parser.add_argument("--log-file", default="gesturecad_events.jsonl", help="JSONL event log path")
    args = parser.parse_args(argv)

    calibration_rect = tuple(args.calibration_rect)
    try:
        map_to_viewport(0.5, 0.5, calibration_rect)
    except ValueError as error:
        parser.error(str(error))

    log = EventLog(args.log_file)
    log.write(
        "session_started",
        arguments={
            "voice": args.voice,
            "dry_run": args.dry_run,
            "no_confirm": args.no_confirm,
            "stt_model": args.stt_model if args.voice else None,
            "calibration_rect": calibration_rect,
        },
    )
    camera = cv2.VideoCapture(0)
    if not camera.isOpened():
        camera.release()
        log.write("camera_open_failed")
        log.close()
        raise SystemExit(
            "Error: Could not open the default webcam. Check that a camera is "
            "connected and not in use by another application."
        )

    sender = None
    voice_results: queue.Queue[dict] = queue.Queue()
    voice_input = None
    previous_frame_time = time.perf_counter()
    gesture_states: dict[str, GestureStateMachine] = {}
    previous_gesture_states: dict[str, GestureState] = {}
    pinch_filters: dict[str, tuple[OneEuroFilter, OneEuroFilter]] = {}
    index_filters: dict[str, tuple[OneEuroFilter, OneEuroFilter]] = {}
    raw_trail: deque[tuple[int, int]] = deque(maxlen=60)
    filtered_trail: deque[tuple[int, int]] = deque(maxlen=60)
    controller = GestureBridgeController()
    last_transcript = "(waiting for speech)"
    last_command_text = "(none)"
    pending_command: dict | None = None
    pending_command_text = ""
    pending_send_at: float | None = None
    last_cursor_uv: tuple[float, float] | None = None

    def send_message(message: dict, source: str) -> None:
        if args.dry_run:
            print(json.dumps(message, separators=(",", ":")))
            log.write("bridge_message_dry_run", source=source, message=message)
            return
        try:
            sender.send(message)
            log.write("bridge_message_sent", source=source, message=message)
        except Exception as error:
            log.write("bridge_message_failed", source=source, message=message, error=str(error))
            print(f"Bridge send failed: {error}")

    try:
        if not args.dry_run:
            sender = UDPSender()
        if args.voice:
            from voice.stt import VoiceInput

            voice_input = VoiceInput(
                on_result=lambda transcript, command: voice_results.put(
                    {"kind": "result", "transcript": transcript, "command": command}
                ),
                on_event=lambda event, details: voice_results.put(
                    {"kind": "event", "name": event, "details": details}
                ),
                model_size=args.stt_model,
            )
            voice_input.start()
            log.write("voice_input_started", model=args.stt_model)
        log.write("camera_opened", device=0)

        with HandTracker() as tracker:
            log.write("hand_tracker_started", model_path=str(MODEL_PATH))
            while True:
                success, frame = camera.read()
                if not success:
                    log.write("camera_frame_failed")
                    print("Error: Could not read a frame from the webcam.")
                    break

                frame = cv2.flip(frame, 1)
                now = time.perf_counter()
                elapsed = now - previous_frame_time
                previous_frame_time = now
                fps = 1.0 / elapsed if elapsed > 0 else 0.0
                detected_hands = tracker.process_frame(frame)
                present_keys: set[str] = set()
                grabbed_points: dict[str, tuple[float, float]] = {}
                ratios: list[float] = []
                visible_states: list[GestureState] = []
                filtered_index_tip = None

                for hand_index, (landmarks, handedness) in enumerate(detected_hands):
                    hand_key = handedness if handedness != "Unknown" else f"hand-{hand_index}"
                    present_keys.add(hand_key)
                    machine = gesture_states.setdefault(hand_key, GestureStateMachine())
                    hand_state = machine.update(landmarks, now=now)
                    visible_states.append(hand_state)
                    ratios.append(pinch_ratio(landmarks))
                    if previous_gesture_states.get(hand_key) is not hand_state:
                        log.write("gesture_state_changed", hand=hand_key, state=hand_state.value)
                        previous_gesture_states[hand_key] = hand_state

                    pinch_xy = pinch_filters.setdefault(
                        hand_key,
                        (OneEuroFilter(min_cutoff=1.0, beta=0.02), OneEuroFilter(min_cutoff=1.0, beta=0.02)),
                    )
                    midpoint_x = (landmarks[4, 0] + landmarks[8, 0]) * 0.5
                    midpoint_y = (landmarks[4, 1] + landmarks[8, 1]) * 0.5
                    filtered_x = pinch_xy[0].filter(midpoint_x, now)
                    filtered_y = pinch_xy[1].filter(midpoint_y, now)

                    tip_xy = index_filters.setdefault(
                        hand_key,
                        (OneEuroFilter(min_cutoff=1.0, beta=0.02), OneEuroFilter(min_cutoff=1.0, beta=0.02)),
                    )
                    tip_x = tip_xy[0].filter(landmarks[8, 0], now)
                    tip_y = tip_xy[1].filter(landmarks[8, 1], now)
                    if hand_index == 0:
                        filtered_index_tip = (tip_x, tip_y)
                        height, width = frame.shape[:2]
                        raw_trail.append((int(midpoint_x * width), int(midpoint_y * height)))
                        filtered_trail.append((int(filtered_x * width), int(filtered_y * height)))
                    if hand_state is GestureState.GRABBING:
                        grabbed_points[hand_key] = (filtered_x, filtered_y)

                for hand_key in set(gesture_states) - present_keys:
                    gesture_states[hand_key].update(None, now=now)
                    previous_gesture_states.pop(hand_key, None)
                    for coordinate_filter in (*pinch_filters[hand_key], *index_filters[hand_key]):
                        coordinate_filter.reset()
                    log.write("hand_lost", hand=hand_key)
                    gesture_states.pop(hand_key, None)
                    pinch_filters.pop(hand_key, None)
                    index_filters.pop(hand_key, None)
                if not detected_hands:
                    raw_trail.clear()
                    filtered_trail.clear()
                    last_cursor_uv = None

                if filtered_index_tip is not None:
                    cursor_uv = map_to_viewport(*filtered_index_tip, calibration_rect)
                    if (
                        last_cursor_uv is None
                        or abs(cursor_uv[0] - last_cursor_uv[0]) > 0.0005
                        or abs(cursor_uv[1] - last_cursor_uv[1]) > 0.0005
                    ):
                        send_message({"type": "cursor", "u": cursor_uv[0], "v": cursor_uv[1]}, "tracker")
                    last_cursor_uv = cursor_uv

                for message in controller.update(grabbed_points):
                    send_message(message, "gesture")

                while True:
                    try:
                        voice_event = voice_results.get_nowait()
                    except queue.Empty:
                        break
                    if voice_event["kind"] == "event":
                        log.write(voice_event["name"], **voice_event["details"])
                        continue
                    transcript = voice_event["transcript"]
                    command = voice_event["command"]
                    last_transcript = transcript or "(empty transcript)"
                    log.write("voice_result", transcript=transcript, command=command)
                    if command is None:
                        last_command_text = "Unrecognized"
                        continue
                    if command.get("type") == "cancel":
                        if pending_command is not None:
                            log.write("voice_command_cancelled", command=pending_command, transcript=transcript)
                            last_command_text = "Cancelled: " + pending_command_text
                            pending_command = None
                            pending_command_text = ""
                            pending_send_at = None
                        else:
                            log.write("voice_cancel_without_pending", transcript=transcript)
                            last_command_text = "Cancel: no pending command"
                        continue

                    if pending_command is not None:
                        log.write("voice_command_replaced", command=pending_command, replacement=command)
                    pending_command = command
                    pending_command_text = _format_command(command)
                    last_command_text = pending_command_text
                    if args.no_confirm:
                        log.write("voice_command_confirm_skipped", command=command, no_confirm=True)
                        send_message(command, "voice")
                        last_command_text = "Sent: " + pending_command_text
                        pending_command = None
                        pending_send_at = None
                    else:
                        pending_send_at = now + CONFIRM_SECONDS
                        log.write(
                            "voice_command_confirmation_started",
                            command=command,
                            display=pending_command_text,
                            confirm_seconds=CONFIRM_SECONDS,
                        )

                if pending_command is not None and pending_send_at is not None and now >= pending_send_at:
                    send_message(pending_command, "voice")
                    log.write("voice_command_confirmation_elapsed", command=pending_command)
                    last_command_text = "Sent: " + pending_command_text
                    pending_command = None
                    pending_command_text = ""
                    pending_send_at = None

                for trail, color in ((raw_trail, (255, 0, 255)), (filtered_trail, (0, 255, 255))):
                    points = list(trail)
                    for first, second in zip(points, points[1:]):
                        cv2.line(frame, first, second, color, 2, cv2.LINE_AA)
                if raw_trail:
                    cv2.circle(frame, raw_trail[-1], 5, (255, 0, 255), -1)
                    cv2.circle(frame, filtered_trail[-1], 5, (0, 255, 255), -1)

                if args.calibrate:
                    height, width = frame.shape[:2]
                    left, top, right, bottom = calibration_rect
                    cv2.rectangle(
                        frame,
                        (int(left * width), int(top * height)),
                        (int(right * width), int(bottom * height)),
                        (255, 255, 0),
                        2,
                    )
                    if filtered_index_tip is not None:
                        cv2.circle(
                            frame,
                            (int(filtered_index_tip[0] * width), int(filtered_index_tip[1] * height)),
                            7,
                            (0, 165, 255),
                            2,
                        )

                if GestureState.GRABBING in visible_states:
                    state_text = f"GRABBING ({len(grabbed_points)} hand(s))"
                elif GestureState.ENGAGED in visible_states:
                    state_text = "ENGAGED"
                else:
                    state_text = "PAUSED"
                ratio_text = f"{ratios[0]:.2f}" if ratios else "N/A"
                _draw_text(frame, f"State: {state_text} | Pinch: {ratio_text} | Bridge: {controller.mode}", 26, (0, 255, 255), 0.62)
                _draw_text(frame, f"Last transcript: {last_transcript}", 52)
                if pending_command is not None and pending_send_at is not None:
                    remaining = max(0.0, pending_send_at - now)
                    confirmation_text = f"{pending_command_text} - say 'cancel' to stop ({remaining:.1f}s)"
                    _draw_text(frame, confirmation_text, 78, (0, 200, 255), 0.58)
                else:
                    _draw_text(frame, f"Parsed command: {last_command_text}", 78)
                _draw_text(frame, "Gestures: open palm 0.5s = engage | pinch = grab", 104)
                _draw_text(frame, "Gestures: two pinches = scale/rotate | release = clutch", 128)
                _draw_text(frame, f"FPS: {fps:.1f} | Voice: {'on' if args.voice else 'off'} | {'dry-run' if args.dry_run else 'UDP'}", 152)
                cv2.imshow("Webcam", frame)

                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except Exception as error:
        log.write("session_error", error=str(error))
        raise
    finally:
        if pending_command is not None:
            log.write("voice_command_discarded_on_exit", command=pending_command)
        if voice_input is not None:
            voice_input.stop()
            log.write("voice_input_stopped")
            while True:
                try:
                    voice_event = voice_results.get_nowait()
                except queue.Empty:
                    break
                if voice_event["kind"] == "event":
                    log.write(voice_event["name"], **voice_event["details"])
                else:
                    log.write(
                        "voice_result_discarded_on_exit",
                        transcript=voice_event["transcript"],
                        command=voice_event["command"],
                    )
        camera.release()
        cv2.destroyAllWindows()
        if sender is not None:
            sender.close()
        log.write("session_stopped")
        log.close()


if __name__ == "__main__":
    main()
