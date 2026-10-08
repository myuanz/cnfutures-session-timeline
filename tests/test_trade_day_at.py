from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from cnfutures_session_timeline import ExtraClosure, SessionEvent, SessionTimeline
from cnfutures_session_timeline.calendar import CALENDAR_END, CALENDAR_START


@pytest.fixture
def timeline() -> SessionTimeline:
    return SessionTimeline.load()


@pytest.mark.parametrize("text,product,expected", [
    ("2026-09-18T20:59:59+08:00", "AU", None),
    ("2026-09-18T21:00:00+08:00", "au", date(2026, 9, 21)),
    ("2026-09-19T00:00:00+08:00", "AU", date(2026, 9, 21)),
    ("2026-09-19T02:30:00+08:00", "AU", date(2026, 9, 21)),
    ("2026-09-19T02:30:00.000001+08:00", "AU", None),
    ("2026-09-19T10:00:00+08:00", "AU", None),
    ("2026-09-19T21:00:00+08:00", "AU", None),
    ("2026-09-20T01:00:00+08:00", "AU", None),
    ("2026-09-20T21:00:00+08:00", "AU", None),
    ("2026-09-21T01:00:00+08:00", "AU", None),
    ("2026-09-21T08:59:59+08:00", "AU", None),
    ("2026-09-21T09:00:00+08:00", "AU", date(2026, 9, 21)),
    ("2026-09-21T10:15:00+08:00", "AU", date(2026, 9, 21)),
    ("2026-09-21T10:15:00.000001+08:00", "AU", None),
    ("2026-09-21T10:20:00+08:00", "AU", None),
    ("2026-09-21T10:30:00+08:00", "AU", date(2026, 9, 21)),
    ("2026-09-21T12:00:00+08:00", "AU", None),
    ("2026-09-21T13:30:00+08:00", "AU", date(2026, 9, 21)),
    ("2026-09-21T15:00:00+08:00", "AU", date(2026, 9, 21)),
    ("2026-09-21T15:00:00.000001+08:00", "AU", None),
    ("2026-09-21T21:00:00+08:00", "AU", date(2026, 9, 22)),
    ("2026-09-22T01:00:00+08:00", "CU", date(2026, 9, 22)),
    ("2026-09-22T01:00:00.000001+08:00", "CU", None),
    ("2026-09-21T23:00:00+08:00", "A", date(2026, 9, 22)),
    ("2026-09-21T23:00:00.000001+08:00", "A", None),
    ("2026-09-21T21:00:00+08:00", "IF", None),
    ("2026-09-21T09:15:00+08:00", "IF", None),
    ("2026-09-21T09:30:00+08:00", "IF", date(2026, 9, 21)),
    ("2026-09-24T21:00:00+08:00", "AU", None),
    ("2026-09-25T01:00:00+08:00", "AU", None),
    ("2026-09-27T21:00:00+08:00", "AU", None),
    ("2026-09-28T01:00:00+08:00", "AU", None),
    ("2026-09-28T09:00:00+08:00", "AU", date(2026, 9, 28)),
    ("2024-02-08T21:00:00+08:00", "CU", None),
    ("2024-02-09T09:00:00+08:00", "CU", None),
    ("2020-03-03T21:00:00+08:00", "CU", None),
    ("2020-03-04T09:00:00+08:00", "CU", date(2020, 3, 4)),
    ("2020-05-06T21:00:00+08:00", "CU", date(2020, 5, 7)),
    ("2025-07-08T01:00:00+08:00", "BZ", None),
    ("2025-07-08T09:00:00+08:00", "BZ", date(2025, 7, 8)),
    ("2025-07-08T21:00:00+08:00", "BZ", date(2025, 7, 9)),
])
def test_trade_day_at(timeline: SessionTimeline, text: str, product: str, expected: date | None) -> None:
    assert timeline.trade_day_at(datetime.fromisoformat(text), product) == expected


def test_timezone(timeline: SessionTimeline) -> None:
    for tz in [ZoneInfo("Asia/Shanghai"), timezone(timedelta(hours=8))]:
        assert timeline.trade_day_at(datetime(2026, 9, 18, 21, tzinfo=tz), "AU") == date(2026, 9, 21)
    for tz in [None, timezone.utc, timezone(timedelta(hours=9))]:
        with pytest.raises(ValueError, match="东八区"):
            timeline.trade_day_at(datetime(2026, 9, 18, 21, tzinfo=tz), "AU")


def test_unknown_product_and_pre_listing(timeline: SessionTimeline) -> None:
    dt = datetime.fromisoformat("2025-07-07T21:00:00+08:00")
    with pytest.raises(KeyError, match="没有品种"):
        timeline.trade_day_at(dt, "UNKNOWN")
    with pytest.raises(KeyError, match="尚未上市"):
        timeline.trade_day_at(dt, "BZ")


def test_calendar_coverage(timeline: SessionTimeline) -> None:
    tz = timezone(timedelta(hours=8))
    for day in [CALENDAR_START - timedelta(days=1), CALENDAR_END + timedelta(days=1)]:
        with pytest.raises(ValueError, match="中国日历仅覆盖"):
            timeline.trade_day_at(datetime.combine(day, datetime.min.time(), tz), "AU")
    assert timeline.trade_day_at(datetime(CALENDAR_END.year, 12, 31, 10, tzinfo=tz), "AU") == CALENDAR_END
    with pytest.raises(ValueError, match="中国日历仅覆盖"):
        timeline.trade_day_at(datetime(CALENDAR_END.year, 12, 31, 21, tzinfo=tz), "AU")


def test_extra_closure(timeline: SessionTimeline) -> None:
    events = tuple(event for group in timeline.events.values() for event in group)
    extra = ExtraClosure("SHFE", date(2026, 9, 18), "临时休市")
    custom = SessionTimeline(events, closures={(extra.exchange, extra.day): extra})
    dt = datetime.fromisoformat("2026-09-18T21:00:00+08:00")
    assert custom.trade_day_at(dt, "AU") is None
    assert custom.trade_day_at(dt, "A") == date(2026, 9, 21)


def test_night_uses_target_trade_day_event() -> None:
    timeline = SessionTimeline((
        SessionEvent("SHFE", "AU", date(2026, 9, 1), "day-0900-1500", "上市"),
        SessionEvent("SHFE", "AU", date(2026, 9, 21), "night-2100-0230", "开通夜盘"),
        SessionEvent("SHFE", "AU", date(2026, 9, 22), "delisted", "下架"),
    ), closures={})
    assert timeline.trade_day_at(datetime.fromisoformat("2026-09-18T21:00:00+08:00"), "AU") == date(2026, 9, 21)
    assert timeline.trade_day_at(datetime.fromisoformat("2026-09-21T21:00:00+08:00"), "AU") is None
    assert timeline.trade_day_at(datetime.fromisoformat("2026-09-22T09:00:00+08:00"), "AU") is None
