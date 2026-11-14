from datetime import date, datetime, timedelta

import pytest

from cnfutures_session_timeline import CalendarDate, SessionTimeline, TradeDate
from cnfutures_session_timeline.calendar import CALENDAR_END, CALENDAR_START


@pytest.mark.parametrize("value", [20260918, "20260918", "2026-09-18", date(2026, 9, 18), CalendarDate(2026, 9, 18)])
def test_date_conversion(value):
    assert type(CalendarDate.from_value(value)) is CalendarDate
    assert type(TradeDate.from_value(value)) is TradeDate
    assert CalendarDate.from_value(value).as_trade_date() == date(2026, 9, 18)


@pytest.mark.parametrize("text,expected", [
    ("2026-09-18T14:59:59+08:00", date(2026, 9, 18)),
    ("2026-09-18T15:00:00+08:00", None),
    ("2026-09-18T20:59:59+08:00", None),
    ("2026-09-18T21:00:00+08:00", date(2026, 9, 21)),
    ("2026-09-19T10:00:00+08:00", date(2026, 9, 21)),
    ("2026-09-19T15:00:00+08:00", None),
    ("2026-09-19T21:00:00+08:00", None),
    ("2026-09-20T10:00:00+08:00", None),
    ("2026-09-21T00:00:00+08:00", date(2026, 9, 21)),
    ("2026-09-24T21:00:00+08:00", None),
    ("2026-09-25T10:00:00+08:00", None),
    ("2026-09-28T00:00:00+08:00", date(2026, 9, 28)),
    ("2024-02-08T21:00:00+08:00", None),
    ("2024-02-09T00:00:00+08:00", None),
    ("2024-02-09T09:00:00+08:00", None),
    ("2024-02-09T21:00:00+08:00", None),
])
def test_datetime_conversion(text, expected):
    result = TradeDate.from_value(datetime.fromisoformat(text))
    assert result == expected
    if result is not None:
        assert type(result) is TradeDate


@pytest.mark.parametrize("text,previous,following", [
    ("2026-09-18T17:00:00+08:00", 20260918, 20260921),
    ("2026-09-19T17:00:00+08:00", 20260918, 20260921),
    ("2026-09-25T17:00:00+08:00", 20260924, 20260928),
    ("2024-02-09T17:00:00+08:00", 20240208, 20240219),
])
def test_gap(text, previous, following):
    dt = datetime.fromisoformat(text)
    assert TradeDate.from_value(dt) is None
    assert TradeDate.from_value(dt, gap="previous") == TradeDate.from_value(previous)
    assert TradeDate.from_value(dt, gap="next") == TradeDate.from_value(following)


def test_shift():
    day = TradeDate.from_value(20260918)
    assert day.next == date(2026, 9, 21)
    assert day.previous == date(2026, 9, 17)
    assert day.shift(0) == day
    assert day.shift(5) == date(2026, 9, 28)
    assert day.shift(5).shift(-5) == day


def test_invalid_dates_and_boundaries():
    assert TradeDate.from_value(20260919) is None
    with pytest.raises(ValueError, match="非交易日"):
        TradeDate(2026, 9, 19)
    for value in [20260230, "2026/01/01"]:
        with pytest.raises(ValueError):
            CalendarDate.from_value(value)
    for value in [CALENDAR_START - timedelta(days=1), CALENDAR_END + timedelta(days=1)]:
        with pytest.raises(ValueError, match="中国日历仅覆盖"):
            TradeDate.from_value(value)
    with pytest.raises(ValueError, match="东八区"):
        TradeDate.from_value(datetime(2026, 9, 18))
    with pytest.raises(ValueError):
        TradeDate.from_value(CALENDAR_END).next


def test_session_and_resolve_type():
    day = TradeDate.from_value(20260921)
    assert day.session("au") == SessionTimeline.load().resolve(day, "AU")
    for value in [20260921, "20260921", date(2026, 9, 21), CalendarDate(2026, 9, 21), CalendarDate(2026, 9, 19), None]:
        with pytest.raises(TypeError, match="TradeDate"):
            SessionTimeline.load().resolve(value, "AU")


def test_calendar_date_session():
    assert CalendarDate.from_value(20260921).session("AU") == TradeDate.from_value(20260921).session("AU")
    assert CalendarDate.from_value(20260919).session("AU").periods == ()


@pytest.mark.parametrize("text", [
    "2026-09-18T21:00:00+08:00", "2026-09-19T10:00:00+08:00",
    "2026-09-19T17:00:00+08:00", "2026-09-25T21:00:00+08:00",
    "2026-09-25T17:00:00", "1990-01-01T17:00:00Z",
])
def test_calendar_date_preserves_natural_date(text):
    value = datetime.fromisoformat(text)
    result = CalendarDate.from_value(value)
    assert type(result) is CalendarDate
    assert result == value.date()


@pytest.mark.parametrize("day", [20260919, 20260925, 19900101])
def test_calendar_date_preserves_closed_and_uncovered_dates(day):
    result = CalendarDate.from_value(day)
    assert type(result) is CalendarDate
    assert result.strftime("%Y%m%d") == str(day)
