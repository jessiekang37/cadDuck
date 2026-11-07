"""Parse short English voice commands into GestureCAD protocol messages."""

import re


_SMALL_NUMBERS = {
    "zero": 0,
    "oh": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}
_TENS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_UNIT_METERS = {
    "mm": 0.001,
    "millimeter": 0.001,
    "millimeters": 0.001,
    "millimetre": 0.001,
    "millimetres": 0.001,
    "cm": 0.01,
    "centimeter": 0.01,
    "centimeters": 0.01,
    "centimetre": 0.01,
    "centimetres": 0.01,
    "m": 1.0,
    "meter": 1.0,
    "meters": 1.0,
    "metre": 1.0,
    "metres": 1.0,
    "in": 0.0254,
    "inch": 0.0254,
    "inches": 0.0254,
}
_UNIT_ALIASES = {
    "fourty": "forty",  # Frequent spelling/recognition error.
    "app": "up",  # Common speech recognition substitution for "up".
    "upwards": "up",
    "upward": "up",
    "downwards": "down",
    "downward": "down",
    "buy": "by",
    "write": "right",
    "rite": "right",
    "moved": "move",
    "rotated": "rotate",
    "scaling": "scale",
    "extruded": "extrude",
    "centimeterz": "centimeters",
    "centemeter": "centimeter",
    "centemeters": "centimeters",
    "sentimeter": "centimeter",
    "sentimeters": "centimeters",
    "milimeter": "millimeter",
    "milimeters": "millimeters",
    "inchs": "inches",
}
_DIRECTIONS = {
    "up": ("z", 1),
    "down": ("z", -1),
    "left": ("x", -1),
    "right": ("x", 1),
    "forward": ("y", 1),
    "back": ("y", -1),
    "backward": ("y", -1),
}
_FILLERS = {"please", "now", "it", "the", "a", "an"}


def _tokens(transcript: str) -> list[str]:
    words = re.findall(r"[a-z]+|\d+(?:\.\d+)?", transcript.lower().replace("-", " "))
    if words[:2] == ["you", "do"]:
        words = ["undo", *words[2:]]
    return [_UNIT_ALIASES.get(word, word) for word in words]


def _number(tokens: list[str], start: int) -> tuple[float, int] | None:
    """Read a numeric token or cardinal number words from ``start``."""
    if start >= len(tokens):
        return None
    if re.fullmatch(r"\d+(?:\.\d+)?", tokens[start]):
        return float(tokens[start]), start + 1

    current = 0
    total = 0
    index = start
    saw_number = False
    while index < len(tokens):
        token = tokens[index]
        if token == "and" and saw_number:
            index += 1
            continue
        if token in _SMALL_NUMBERS:
            current += _SMALL_NUMBERS[token]
            saw_number = True
        elif token in _TENS:
            current += _TENS[token]
            saw_number = True
        elif token == "hundred" and saw_number:
            current = max(current, 1) * 100
        elif token == "thousand" and saw_number:
            total += max(current, 1) * 1000
            current = 0
        else:
            break
        index += 1
    if not saw_number:
        return None

    value = float(total + current)
    if index < len(tokens) and tokens[index] == "point":
        decimal_start = index + 1
        decimal_digits: list[str] = []
        while decimal_start < len(tokens):
            token = tokens[decimal_start]
            if re.fullmatch(r"\d", token):
                decimal_digits.append(token)
            elif token in _SMALL_NUMBERS and _SMALL_NUMBERS[token] < 10:
                decimal_digits.append(str(_SMALL_NUMBERS[token]))
            else:
                break
            decimal_start += 1
        if not decimal_digits:
            return None
        value += float("0." + "".join(decimal_digits))
        index = decimal_start
    return value, index


def _unit(tokens: list[str], index: int) -> tuple[float, int]:
    if index < len(tokens) and tokens[index] in _UNIT_METERS:
        return _UNIT_METERS[tokens[index]], index + 1
    return 1.0, index


def _finished(tokens: list[str], index: int) -> bool:
    return all(token in _FILLERS for token in tokens[index:])


def _parse_move(tokens: list[str]) -> dict | None:
    if len(tokens) < 3 or tokens[0] != "move":
        return None
    direction = tokens[1]
    if direction not in _DIRECTIONS:
        return None
    index = 2
    if index < len(tokens) and tokens[index] == "by":
        index += 1
    parsed = _number(tokens, index)
    if parsed is None:
        return None
    amount, index = parsed
    scale, index = _unit(tokens, index)
    if not _finished(tokens, index):
        return None
    axis, sign = _DIRECTIONS[direction]
    return {"type": "command", "op": "move", "axis": axis, "value": sign * amount * scale}


def _parse_rotate(tokens: list[str]) -> dict | None:
    if not tokens or tokens[0] != "rotate":
        return None
    index = 1
    axis = "z"
    if index < len(tokens) and tokens[index] in {"x", "y", "z"}:
        axis = tokens[index]
        index += 1
    if index < len(tokens) and tokens[index] == "by":
        index += 1
    parsed = _number(tokens, index)
    if parsed is None:
        return None
    degrees, index = parsed
    if index < len(tokens) and tokens[index] in {"degree", "degrees"}:
        index += 1
    if not _finished(tokens, index):
        return None
    import math

    return {"type": "rotate", "axis": axis, "radians": math.radians(degrees)}


def _parse_scale(tokens: list[str]) -> dict | None:
    if not tokens or tokens[0] != "scale":
        return None
    index = 1
    if index < len(tokens) and tokens[index] == "by":
        index += 1
    parsed = _number(tokens, index)
    if parsed is None:
        return None
    factor, index = parsed
    if not _finished(tokens, index) or factor <= 0:
        return None
    return {"type": "scale", "factor": factor}


def _parse_extrude(tokens: list[str]) -> dict | None:
    if not tokens or tokens[0] != "extrude":
        return None
    index = 1
    if index < len(tokens) and tokens[index] == "by":
        index += 1
    parsed = _number(tokens, index)
    if parsed is None:
        return None
    amount, index = parsed
    unit_scale, index = _unit(tokens, index)
    if not _finished(tokens, index):
        return None
    return {"type": "command", "op": "extrude", "value": amount * unit_scale}


def parse_transcript(transcript: str) -> dict | None:
    """Return a validated protocol message, or ``None`` if unrecognized.

    Linear values are converted to meters (unspecified units are meters).
    ``rotate`` defaults to the Z axis
    and converts degrees to radians. Move directions map to Blender axes as
    up/down=Z, left/right=X, and forward/back=Y.
    """
    if not isinstance(transcript, str) or not transcript.strip():
        return None
    tokens = _tokens(transcript)
    if not tokens:
        return None

    if tokens in (["undo"], ["undo", "that"], ["undo", "it"]):
        return {"type": "undo"}
    if tokens[0] == "select":
        name_tokens = [token for token in tokens[1:] if token not in _FILLERS]
        if not name_tokens:
            return None
        name = " ".join(name_tokens).title()
        return {"type": "select", "name": name}

    for parser in (_parse_move, _parse_rotate, _parse_scale, _parse_extrude):
        result = parser(tokens)
        if result is not None:
            return result
    return None
