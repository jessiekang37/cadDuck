"""JSON protocol helpers for GestureCAD's localhost UDP bridge."""

import json
import math
from typing import Any


_AXES = {"x", "y", "z"}


def validate_message(message: Any) -> dict[str, Any]:
    """Validate a protocol message and return it as a dictionary.

    Supported message types are translate, scale, rotate, select, command
    (currently ``move``), and undo. Unknown keys and invalid numeric values
    are rejected so malformed packets cannot reach a receiver unchecked.
    """
    if not isinstance(message, dict) or not isinstance(message.get("type"), str):
        raise ValueError("message must be a JSON object with a string 'type'")

    message_type = message["type"]
    schemas = {
        "translate": {"type", "dx", "dy"},
        "scale": {"type", "factor"},
        "rotate": {"type", "axis", "radians"},
        "select": {"type", "name"},
        "command": {"type", "op", "axis", "value"},
        "undo": {"type"},
    }
    if message_type not in schemas:
        raise ValueError(f"unsupported message type: {message_type}")
    if set(message) != schemas[message_type]:
        raise ValueError(f"{message_type} message fields must be {sorted(schemas[message_type])}")

    numeric_fields = {
        "translate": ("dx", "dy"),
        "scale": ("factor",),
        "rotate": ("radians",),
        "command": ("value",),
    }.get(message_type, ())
    for key in numeric_fields:
        value = message[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{key} must be a number")
        if not math.isfinite(value):
            raise ValueError(f"{key} must be finite")

    if message_type == "scale" and message["factor"] <= 0:
        raise ValueError("scale factor must be greater than zero")
    if message_type in {"rotate", "command"}:
        if not isinstance(message["axis"], str) or message["axis"] not in _AXES:
            raise ValueError("axis must be one of x, y, z")
    if message_type == "command" and message["op"] != "move":
        raise ValueError("command op must be 'move'")
    if message_type == "select" and (
        not isinstance(message["name"], str) or not message["name"].strip()
    ):
        raise ValueError("select name must be a non-empty string")
    return message


def encode_message(message: Any) -> bytes:
    """Validate and encode a message as UTF-8 JSON bytes."""
    return json.dumps(validate_message(message), allow_nan=False).encode("utf-8")


def decode_message(payload: bytes | str) -> dict[str, Any]:
    """Decode and validate a UTF-8 JSON datagram."""
    try:
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        message = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid JSON message: {error}") from error
    return validate_message(message)
