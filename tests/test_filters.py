import pytest

from tracker.filters import OneEuroFilter


def test_repeated_timestamp_returns_previous_filtered_value():
    value_filter = OneEuroFilter(min_cutoff=1.0, beta=0.02)
    assert value_filter.filter(0.0, 10.0) == pytest.approx(0.0)
    filtered = value_filter.filter(1.0, 10.01)

    assert value_filter.filter(99.0, 10.01) == pytest.approx(filtered)


def test_decreasing_timestamp_returns_previous_filtered_value():
    value_filter = OneEuroFilter(min_cutoff=1.0, beta=0.02)
    value_filter.filter(0.0, 10.0)
    filtered = value_filter.filter(1.0, 10.01)

    assert value_filter.filter(-99.0, 10.005) == pytest.approx(filtered)
    # A later valid sample continues from the last accepted state.
    assert value_filter.filter(2.0, 10.02) > filtered
