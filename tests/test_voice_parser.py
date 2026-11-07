import math

import pytest

from voice.parser import parse_transcript


@pytest.mark.parametrize(
    ("transcript", "expected"),
    [
        ("move up 5 centimeters", {"type": "command", "op": "move", "axis": "z", "value": 0.05}),
        ("move up five centimeters", {"type": "command", "op": "move", "axis": "z", "value": 0.05}),
        ("move down 2 mm", {"type": "command", "op": "move", "axis": "z", "value": -0.002}),
        ("move left 3 m", {"type": "command", "op": "move", "axis": "x", "value": -3.0}),
        ("move right 4 inches", {"type": "command", "op": "move", "axis": "x", "value": 0.1016}),
        ("move forward 20 centimeters", {"type": "command", "op": "move", "axis": "y", "value": 0.2}),
        ("move back 1 meter", {"type": "command", "op": "move", "axis": "y", "value": -1.0}),
        ("move up by 2.5 cm", {"type": "command", "op": "move", "axis": "z", "value": 0.025}),
        ("move upward five millimetres", {"type": "command", "op": "move", "axis": "z", "value": 0.005}),
        ("move downwards ten inches", {"type": "command", "op": "move", "axis": "z", "value": -0.254}),
        ("rotate 45 degrees", {"type": "rotate", "axis": "z", "radians": math.pi / 4}),
        ("rotate forty five degrees", {"type": "rotate", "axis": "z", "radians": math.pi / 4}),
        ("rotate x by 90 degrees", {"type": "rotate", "axis": "x", "radians": math.pi / 2}),
        ("rotate y 180 degree", {"type": "rotate", "axis": "y", "radians": math.pi}),
        ("rotate 22.5", {"type": "rotate", "axis": "z", "radians": math.radians(22.5)}),
        ("scale by 2", {"type": "scale", "factor": 2.0}),
        ("scale two", {"type": "scale", "factor": 2.0}),
        ("scale by twenty two point five", {"type": "scale", "factor": 22.5}),
        ("select cube", {"type": "select", "name": "Cube"}),
        ("select the coffee mug", {"type": "select", "name": "Coffee Mug"}),
        ("undo", {"type": "undo"}),
        ("undo that", {"type": "undo"}),
        ("extrude 10 millimeters", {"type": "command", "op": "extrude", "value": 0.01}),
        ("extrude by one inch", {"type": "command", "op": "extrude", "value": 0.0254}),
        ("extrude twenty two point five cm", {"type": "command", "op": "extrude", "value": 0.225}),
    ],
)
def test_parses_supported_commands(transcript, expected):
    actual = parse_transcript(transcript)
    assert actual.keys() == expected.keys()
    for key, value in expected.items():
        if isinstance(value, float):
            assert actual[key] == pytest.approx(value)
        else:
            assert actual[key] == value


@pytest.mark.parametrize(
    ("transcript", "expected"),
    [
        ("move app five centimeters", {"type": "command", "op": "move", "axis": "z", "value": 0.05}),
        ("move write two cm", {"type": "command", "op": "move", "axis": "x", "value": 0.02}),
        ("move up fourty five milimeters", {"type": "command", "op": "move", "axis": "z", "value": 0.045}),
        ("move up five sentimeters", {"type": "command", "op": "move", "axis": "z", "value": 0.05}),
        ("rotate fourty five degrees", {"type": "rotate", "axis": "z", "radians": math.pi / 4}),
        ("scale buy two", {"type": "scale", "factor": 2.0}),
        ("you do", {"type": "undo"}),
        ("moved upward five centimeters", {"type": "command", "op": "move", "axis": "z", "value": 0.05}),
        ("rotated z by ninety degrees", {"type": "rotate", "axis": "z", "radians": math.pi / 2}),
        ("scaling by three", {"type": "scale", "factor": 3.0}),
        ("extruded ten millimeters", {"type": "command", "op": "extrude", "value": 0.01}),
    ],
)
def test_common_speech_recognition_errors(transcript, expected):
    actual = parse_transcript(transcript)
    assert actual.keys() == expected.keys()
    for key, value in expected.items():
        if isinstance(value, float):
            assert actual[key] == pytest.approx(value)
        else:
            assert actual[key] == value


@pytest.mark.parametrize(
    "transcript",
    [
        "",
        "hello there",
        "move diagonally five centimeters",
        "move up lots",
        "move up five lightyears",
        "rotate ninety bananas",
        "scale by zero",
        "scale by two times",
        "select",
        "extrude a little",
        "extrude ten furlongs",
        "delete cube",
        "make it bigger",
        "undo everything now please maybe",
    ],
)
def test_unrecognized_or_unsafe_commands_return_none(transcript):
    assert parse_transcript(transcript) is None


def test_decimal_number_words():
    assert parse_transcript("scale twenty two point five") == {
        "type": "scale",
        "factor": 22.5,
    }
