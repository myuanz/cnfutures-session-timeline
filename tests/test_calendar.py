from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest

from cnfutures_session_timeline import COMMODITY_DAY, SessionEvent, SessionTimeline
from cnfutures_session_timeline.calendar import CALENDAR_END, CALENDAR_START, load_closures


@pytest.fixture
def timeline() -> SessionTimeline:
    return SessionTimeline.load()


@pytest.mark.parametrize("day,product,reason", [
    (20260214, "AU", "周末"),  # 调休上班仍休市
    (20261001, "IF", "国庆节"),
    (20260101, "IC", "元旦"),
    (20200131, "CU", "春节"),
])
def test_closed_day(timeline: SessionTimeline, day: int, product: str, reason: str) -> None:
    result = timeline.resolve(day, product)
    assert result.periods == ()
    assert result.template_name == "closed"
    assert result.reason == reason
    assert result.effective_at == date.fromisoformat(str(day))


@pytest.mark.parametrize("product", ["CU", "AU", "SC", "A", "CF", "IF", "SI"])
def test_extra_closure(timeline: SessionTimeline, product: str) -> None:
    result = timeline.resolve(date(2024, 2, 9), product)
    assert result.periods == ()
    assert result.template_name == "closed"
    assert result.reason == "除夕日额外休市"
    assert result.effective_at == date(2024, 2, 9)


@pytest.mark.parametrize("day", [20150928, 20260105, 20260224, 20260928, 20261008, 20200102])
def test_first_day_after_holiday_has_no_night(timeline: SessionTimeline, day: int) -> None:
    result = timeline.resolve(day, "AU")
    assert result.periods == COMMODITY_DAY
    assert result.template_name == "day-0900-1500"
    assert result.reason == "节假日或额外休市取消前置夜盘"
    assert result.effective_at == date.fromisoformat(str(day))


@pytest.mark.parametrize("day", [20150929, 20260921, 20260924])
def test_regular_night_and_last_day_before_holiday(timeline: SessionTimeline, day: int) -> None:
    result = timeline.resolve(day, "au")
    assert result.template_name == "night-2100-0230"
    assert result.periods[0].start == time(21)
    assert result.periods[0].end == time(2, 30)
    assert result.periods[1:] == COMMODITY_DAY


def test_covid_schedule_and_reopening(timeline: SessionTimeline) -> None:
    assert timeline.resolve(20200203, "CU").periods == COMMODITY_DAY
    for day in [20200304, 20200506]:
        result = timeline.resolve(day, "CU")
        assert result.periods == COMMODITY_DAY
        assert result.reason == "COVID19暂停夜盘"
        assert result.effective_at == date(2020, 2, 4)
    assert timeline.resolve(20200507, "CU").periods[0].start == time(21)


def test_listing_and_night_launch(timeline: SessionTimeline) -> None:
    with pytest.raises(KeyError, match="尚未上市"):
        timeline.resolve(20250707, "BZ")
    first = timeline.resolve(20250708, "BZ")
    assert first.periods == COMMODITY_DAY
    assert first.reason == "上市首日无前置夜盘"
    assert first.template_name == "day-0900-1500"
    assert timeline.resolve(20250709, "BZ").periods[0].start == time(21)
    assert timeline.resolve(20130708, "AU").periods[0].start == time(21)


def test_financial_futures_keep_day_schedule(timeline: SessionTimeline) -> None:
    result = timeline.resolve(20260928, "IF")
    assert result.template_name == "day-0930-1500"
    assert len(result.periods) == 2
    assert result.reason == "调整交易时间"
    assert result.effective_at == date(2016, 1, 4)


@pytest.mark.parametrize("day", [CALENDAR_START - timedelta(days=1), CALENDAR_END + timedelta(days=1)])
def test_reject_unknown_calendar_year(timeline: SessionTimeline, day: date) -> None:
    with pytest.raises(ValueError, match="中国日历仅覆盖"):
        timeline.resolve(day, "AU")


def test_calendar_boundaries() -> None:
    timeline = SessionTimeline((SessionEvent("SHFE", "AU", CALENDAR_START, "day-0900-1500", "上市"),), closures={})
    assert timeline.resolve(CALENDAR_START, "AU").periods == ()
    assert timeline.resolve(CALENDAR_END, "AU").periods == COMMODITY_DAY


def test_invalid_date(timeline: SessionTimeline) -> None:
    with pytest.raises(ValueError, match="datetime"):
        timeline.resolve(datetime(2026, 9, 28, 21), "AU")


def test_extra_closure_is_scoped_to_exchange(tmp_path: Path, timeline: SessionTimeline) -> None:
    path = tmp_path / "closures.csv"
    path.write_text("exchange,date,reason\nshfe,2026-09-22,临时休市\n", encoding="utf-8")
    events = tuple(event for group in timeline.events.values() for event in group)
    custom = SessionTimeline(events, closures=load_closures(path))
    assert custom.resolve(20260922, "AU").periods == ()
    assert custom.resolve(20260923, "AU").periods == COMMODITY_DAY
    assert custom.resolve(20260924, "AU").periods[0].start == time(21)
    for day in [20260922, 20260923]:
        assert custom.resolve(day, "A") == timeline.resolve(day, "A")
    assert timeline.resolve(20260922, "AU").periods[0].start == time(21)


@pytest.mark.parametrize("content, message", [
    ("day,reason\n", "列应为"),
    ("exchange,date,reason\nSHFE,2024-02-09\n", "列数错误"),
    ("exchange,date,reason\nSHFE,2024-02-09,\n", "缺少原因"),
    ("exchange,date,reason\nSHFE,2024-02-09,休市\nSHFE,2024-02-09,重复\n", "休市事件重复"),
    ("exchange,date,reason\nUNKNOWN,2024-02-09,休市\n", "交易所未知"),
])
def test_invalid_closure_csv(tmp_path: Path, content: str, message: str) -> None:
    path = tmp_path / "closures.csv"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_closures(path)


def test_constructor_uses_only_supplied_closures(timeline: SessionTimeline) -> None:
    events = tuple(event for group in timeline.events.values() for event in group)
    custom = SessionTimeline(events, closures={})
    assert custom.resolve(20240209, "AU").periods
    assert not timeline.resolve(20240209, "AU").periods


def test_resolve_matches_jq_calendar_2016_2026(timeline: SessionTimeline) -> None:
    # 2026-10-06 从 JQ get_trade_days('2016-01-01', '2026-12-31') 获取的固定基准。
    path = Path(__file__).parent / "data" / "jq_trade_days_2016_2026.txt"
    trade_days = {date.fromisoformat(line) for line in path.read_text().splitlines()}
    assert len(trade_days) == 2672
    start, end = date(2016, 1, 1), date(2026, 12, 31)
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        for product, events in timeline.events.items():
            if day < events[0].effective_trade_date:
                continue
            assert bool(timeline.resolve(day, product).periods) == (day in trade_days), (day, product)
