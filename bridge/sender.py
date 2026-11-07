"""Send validated GestureCAD messages to the local Blender add-on."""

import argparse
import json
import socket
from typing import Any

try:
    from .protocol import encode_message
except ImportError:  # Also allow: python bridge/sender.py '{"type":"undo"}'
    from protocol import encode_message


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


class UDPSender:
    """Small reusable UDP sender targeting localhost by default."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
        self.address = (host, port)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, message: dict[str, Any]) -> None:
        self._socket.sendto(encode_message(message), self.address)

    def close(self) -> None:
        self._socket.close()

    def __enter__(self) -> "UDPSender":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("message", help="one protocol message as JSON")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    try:
        message = json.loads(args.message)
        with UDPSender(args.host, args.port) as sender:
            sender.send(message)
    except (json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
