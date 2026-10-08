from datetime import date, timedelta

import pytest

from finbrief_analyzer.screen.models import Bar
from finbrief_analyzer.screen.rules import (
    Score,
    change_pct,
    high_ratio,
    rank,
    trading_value,
    volume_ratio,
)

LAST = date(2026, 10, 7)


def _bars(closes: list[float], volumes: list[int] | None = None, step: int = 1) -> list[Bar]:
    """Bars ending on LAST, one every `step` calendar days, oldest first."""
    volumes = volumes or [1000] * len(closes)
    count = len(closes)
    return [
        Bar("X", LAST - timedelta(days=(count - 1 - index) * step), close, volume)
        for index, (close, volume) in enumerate(zip(closes, volumes, strict=True))
    ]


def _year(closes: list[float]) -> list[Bar]:
    """Weekly bars, so 53 of them span a full 52 weeks."""
    return _bars(closes, step=7)


def test_high_ratio_is_the_last_close_over_the_highest_close_of_52_weeks() -> None:
    # given: the peak of 200 sits in the middle of the year, the last close is 150
    closes = [100.0] * 26 + [200.0] + [100.0] * 25 + [150.0]

    # when / then
    assert high_ratio(_year(closes)) == pytest.approx(0.75)


def test_high_ratio_is_one_when_the_last_day_is_the_high() -> None:
    # given
    closes = [100.0] * 52 + [120.0]

    # when / then
    assert high_ratio(_year(closes)) == pytest.approx(1.0)


def test_high_ratio_ignores_a_peak_older_than_52_weeks() -> None:
    # given: a peak 60 weeks ago, then a flat year
    closes = [500.0] + [100.0] * 60

    # when / then
    assert high_ratio(_year(closes)) == pytest.approx(1.0)


def test_high_ratio_has_no_score_when_history_is_shorter_than_52_weeks() -> None:
    # given: listed half a year ago; its all-time high is not a 52-week high
    closes = [100.0] * 26

    # when / then
    assert high_ratio(_year(closes)) is None


def test_high_ratio_of_no_bars_has_no_score() -> None:
    # given / when / then
    assert high_ratio([]) is None


def test_volume_ratio_is_the_last_volume_over_the_average_of_the_20_days_before() -> None:
    # given: 20 quiet days at 1,000 shares, then 5,000
    volumes = [1000] * 20 + [5000]

    # when / then
    assert volume_ratio(_bars([100.0] * 21, volumes)) == pytest.approx(5.0)


def test_volume_ratio_leaves_the_last_day_out_of_the_average() -> None:
    # given: if the spike were averaged in, the ratio would be below 21
    volumes = [100] * 20 + [2100]

    # when / then
    assert volume_ratio(_bars([100.0] * 21, volumes)) == pytest.approx(21.0)


def test_volume_ratio_uses_only_the_20_days_before_the_last() -> None:
    # given: a huge day 30 sessions ago must not count
    volumes = [1_000_000] + [1000] * 29 + [2000]

    # when / then
    assert volume_ratio(_bars([100.0] * 31, volumes)) == pytest.approx(2.0)


def test_volume_ratio_has_no_score_when_the_average_is_zero() -> None:
    # given: a suspended stock
    volumes = [0] * 20 + [500]

    # when / then
    assert volume_ratio(_bars([100.0] * 21, volumes)) is None


def test_volume_ratio_has_no_score_with_fewer_than_21_bars() -> None:
    # given / when / then
    assert volume_ratio(_bars([100.0] * 20)) is None


def test_trading_value_is_the_average_of_close_times_volume_before_the_last_day() -> None:
    # given: 20 days at 100 x 1,000, then a day that must not be counted
    bars = _bars([100.0] * 20 + [900.0], [1000] * 20 + [9000])

    # when / then
    assert trading_value(bars) == pytest.approx(100_000.0)


def test_change_pct_is_the_move_from_the_previous_close() -> None:
    # given
    bars = _bars([200.0, 210.0])

    # when / then
    assert change_pct(bars) == pytest.approx(5.0)


def test_change_pct_has_no_value_with_a_single_bar() -> None:
    # given / when / then
    assert change_pct(_bars([200.0])) is None


def test_rules_do_not_depend_on_the_order_of_the_bars() -> None:
    # given
    bars = _bars([100.0] * 20 + [110.0], [1000] * 20 + [3000])

    # when
    shuffled = list(reversed(bars))

    # then
    assert volume_ratio(shuffled) == volume_ratio(bars)
    assert change_pct(shuffled) == change_pct(bars)
    assert trading_value(shuffled) == trading_value(bars)


def test_rank_returns_the_top_scores_in_descending_order() -> None:
    # given
    scores = [Score("A", 0.9, 1.0), Score("B", 0.99, 1.0), Score("C", 0.95, 1.0)]

    # when
    top = rank(scores, top=2)

    # then
    assert [score.symbol for score in top] == ["B", "C"]


def test_rank_breaks_a_tie_by_the_larger_move_of_the_day() -> None:
    # given: several stocks closed exactly at their 52-week high
    scores = [Score("A", 1.0, 0.5), Score("B", 1.0, 4.2), Score("C", 1.0, None)]

    # when
    top = rank(scores, top=3)

    # then: a stock without a previous close goes last among equals
    assert [score.symbol for score in top] == ["B", "A", "C"]


def test_rank_falls_back_to_the_symbol_so_the_result_is_stable() -> None:
    # given: same score, same move
    scores = [Score("B", 1.0, 2.0), Score("A", 1.0, 2.0)]

    # when / then
    assert [score.symbol for score in rank(scores, top=2)] == ["A", "B"]


def test_rank_returns_what_there_is_when_fewer_than_top() -> None:
    # given / when / then
    assert rank([Score("A", 1.0, None)], top=5) == [Score("A", 1.0, None)]
