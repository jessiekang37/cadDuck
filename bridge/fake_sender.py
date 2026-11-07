"""Send a camera-free scripted sequence to the GestureCAD Blender add-on."""

import argparse
import time

try:
    from .sender import DEFAULT_HOST, DEFAULT_PORT, UDPSender
except ImportError:  # Also allow: python bridge/fake_sender.py
    from sender import DEFAULT_HOST, DEFAULT_PORT, UDPSender


SEQUENCE = (
    {"type": "select", "name": "Cube"},
    {"type": "translate", "dx": 0.01, "dy": 0.0},
    {"type": "scale", "factor": 1.1},
    {"type": "rotate", "axis": "z", "radians": 0.1},
    {"type": "command", "op": "move", "axis": "z", "value": 0.05},
    {"type": "undo"},
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--delay", type=float, default=0.5, help="seconds between messages")
    args = parser.parse_args()

    with UDPSender(args.host, args.port) as sender:
        for message in SEQUENCE:
            sender.send(message)
            print(f"sent: {message}")
            time.sleep(args.delay)


if __name__ == "__main__":
    main()
