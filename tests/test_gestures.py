import numpy as np
import pytest

from tracker.gestures import (
    GestureState,
    GestureStateMachine,
    hand_size,
    is_open_palm,
    pinch_ratio,
)


def make_hand(*, open_palm=False, pinch_distance=0.5):
    points = np.zeros((21, 3), dtype=float)
    points[0] = (0, 0, 0)
    points[9] = (0, 1, 0)
    for mcp, pip, tip, x in (
        (5, 6, 8, -0.45),
        (9, 10, 12, -0.15),
        (13, 14, 16, 0.15),
        (17, 18, 20, 0.45),
    ):
        if mcp != 9:
            points[mcp] = (x, 0.5, 0)
        if open_palm:
            points[pip] = points[mcp] + (0, 0.5, 0)
            points[tip] = points[mcp] + (0, 1.1, 0)
        else:
            points[pip] = points[mcp] + (0, 0.35, 0)
            points[tip] = points[mcp] + (0, 0.2, 0)
    points[4] = (0, 0, 0)
    points[8] = (pinch_distance, 0, 0)
    return points


def test_hand_size_and_normalized_pinch_ratio():
    hand = make_hand(pinch_distance=0.5)
    assert hand_size(hand) == pytest.approx(1.0)
    assert pinch_ratio(hand) == pytest.approx(0.5)


def test_open_palm_requires_all_four_fingers_extended():
    assert is_open_palm(make_hand(open_palm=True))
    assert not is_open_palm(make_hand(open_palm=False))


def test_open_palm_must_be_held_before_engaging():
    machine = GestureStateMachine()
    hand = make_hand(open_palm=True)
    assert machine.update(hand, now=1.0) is GestureState.PAUSED
    assert machine.update(hand, now=1.49) is GestureState.PAUSED
    assert machine.update(hand, now=1.5) is GestureState.ENGAGED


def test_pinch_hysteresis_prevents_state_flicker():
    machine = GestureStateMachine()
    machine.state = GestureState.ENGAGED
    assert machine.update(make_hand(pinch_distance=0.24), now=1) is GestureState.GRABBING
    assert machine.update(make_hand(pinch_distance=0.3), now=2) is GestureState.GRABBING
    assert machine.update(make_hand(pinch_distance=0.4), now=3) is GestureState.GRABBING
    assert machine.update(make_hand(pinch_distance=0.41), now=4) is GestureState.ENGAGED


def test_missing_hand_resets_to_paused():
    machine = GestureStateMachine()
    machine.state = GestureState.ENGAGED
    assert machine.update(None) is GestureState.PAUSED
