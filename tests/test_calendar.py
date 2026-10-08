from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest
from chinese_calendar.constants import Holiday

from cnfutures_session_timeline import COMMODITY_DAY, ExtraClosure, SessionEvent, SessionTimeline, SessionTrim
from cnfutures_session_timeline.calendar import CALENDAR_END, CALENDAR_START, load_closures


@pytest.fixture
def timeline() -> SessionTimeline:
    return SessionTimeline.load()


@pytest.mark.parametrize("day,product,trim", [
    (20260214, "AU", SessionTrim("close", "weekend")),  # 调休上班仍休市
    (20261001, "IF", SessionTrim("close", Holiday.national_day)),
    (20260101, "IC", SessionTrim("close", Holiday.new_years_day)),
    (20200131, "CU", SessionTrim("close", Holiday.spring_festival)),
    (20260927, "AU", SessionTrim("close", Holiday.mid_autumn_festival)),
    (20260920, "AU", SessionTrim("close", "weekend")),
])
def test_closed_day(timeline: SessionTimeline, day: int, product: str, trim: SessionTrim) -> None:
    result = timeline.resolve(day, product)
    assert result.periods == ()
    assert result.trims == (trim,)
    assert result.std_session_event in timeline.events[product]


@pytest.mark.parametrize("product", ["CU", "AU", "SC", "A", "CF", "IF", "SI"])
def test_extra_closure(timeline: SessionTimeline, product: str) -> None:
    result = timeline.resolve(date(2024, 2, 9), product)
    assert result.periods == ()
    assert result.trims == (SessionTrim("close", ExtraClosure(
        result.std_session_event.exchange, date(2024, 2, 9), "除夕日额外休市",
    )),)


@pytest.mark.parametrize("day,holiday", [
    (20150928, Holiday.mid_autumn_festival),
    (20260105, Holiday.new_years_day),
    (20260224, Holiday.spring_festival),
    (20260928, Holiday.mid_autumn_festival),
    (20261008, Holiday.national_day),
    (20200102, Holiday.new_years_day),
])
def test_first_day_after_holiday_has_no_night(timeline: SessionTimeline, day: int, holiday: Holiday) -> None:
    result = timeline.resolve(day, "AU")
    assert result.periods == COMMODITY_DAY
    assert result.std_session_event.session == "night-2100-0230"
    assert result.trims == (SessionTrim("remove_night", holiday),)


@pytest.mark.parametrize("day", [20150929, 20260921, 20260924])
def test_regular_night_and_last_day_before_holiday(timeline: SessionTimeline, day: int) -> None:
    result = timeline.resolve(day, "au")
    assert result.std_session_event.session == "night-2100-0230"
    assert result.trims == ()
    assert result.periods[0].start == time(21)
    assert result.periods[0].end == time(2, 30)
    assert result.periods[1:] == COMMODITY_DAY


def test_covid_schedule_and_reopening(timeline: SessionTimeline) -> None:
    assert timeline.resolve(20200203, "CU").periods == COMMODITY_DAY
    for day in [20200304, 20200506]:
        result = timeline.resolve(day, "CU")
        assert result.periods == COMMODITY_DAY
        assert result.std_session_event.reason == "COVID19暂停夜盘"
        assert result.std_session_event.effective_trade_date == date(2020, 2, 4)
        assert result.trims == ()
    assert timeline.resolve(20200507, "CU").periods[0].start == time(21)


def test_listing_and_night_launch(timeline: SessionTimeline) -> None:
    with pytest.raises(KeyError, match="尚未上市"):
        timeline.resolve(20250707, "BZ")
    first = timeline.resolve(20250708, "BZ")
    assert first.periods == COMMODITY_DAY
    assert first.std_session_event.reason == "上市"
    assert first.std_session_event.effective_trade_date == date(2025, 7, 8)
    assert first.std_session_event.session == "night-2100-2300"
    assert first.trims == (SessionTrim("remove_night", "listing_day"),)
    assert timeline.resolve(20250709, "BZ").periods[0].start == time(21)
    assert timeline.resolve(20130708, "AU").periods[0].start == time(21)


def test_fuel_oil_delisting_and_relisting(timeline: SessionTimeline) -> None:
    source_url = "https://www.shfe.com.cn/publicnotice/notice/201806/t20180626_793285.html"
    assert timeline.resolve(20180626, "FU").periods == COMMODITY_DAY
    for offset in range(19):
        day = date(2018, 6, 27) + timedelta(days=offset)
        result = timeline.resolve(day, "FU")
        assert result.periods == ()
        assert result.std_session_event.session == "delisted"
        assert result.std_session_event.reason == "下架"
        assert result.std_session_event.source_url == source_url
        assert result.trims == ()

    first = timeline.resolve(20180716, "FU")
    assert first.periods == COMMODITY_DAY
    assert first.std_session_event.effective_trade_date == date(2018, 7, 16)
    assert first.std_session_event.reason == "上市"
    assert first.std_session_event.session == "night-2100-2300"
    assert first.std_session_event.source_url == source_url
    assert first.trims == (SessionTrim("remove_night", "listing_day"),)
    following = timeline.resolve(20180717, "FU")
    assert following.periods[0].start == time(21)
    assert following.periods[0].end == time(23)
    assert following.trims == ()


def test_financial_futures_keep_day_schedule(timeline: SessionTimeline) -> None:
    result = timeline.resolve(20260928, "IF")
    assert result.std_session_event.session == "day-0930-1500"
    assert len(result.periods) == 2
    assert result.std_session_event.reason == "调整交易时间"
    assert result.std_session_event.effective_trade_date == date(2016, 1, 4)
    assert result.trims == ()


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
    assert custom.resolve(20260923, "AU").trims == (
        SessionTrim("remove_night", ExtraClosure("SHFE", date(2026, 9, 22), "临时休市")),
    )
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


def test_calendar_trim_precedes_extra_closure(timeline: SessionTimeline) -> None:
    events = tuple(event for group in timeline.events.values() for event in group)
    extra = ExtraClosure("SHFE", date(2026, 9, 28), "临时休市")
    custom = SessionTimeline(events, closures={(extra.exchange, extra.day): extra})
    result = custom.resolve(20260928, "AU")
    assert result.periods == ()
    assert result.std_session_event == timeline.resolve(20260929, "AU").std_session_event
    assert result.trims == (
        SessionTrim("remove_night", Holiday.mid_autumn_festival),
        SessionTrim("close", extra),
    )


def test_overlapping_closures_do_not_repeat_trims(timeline: SessionTimeline) -> None:
    events = tuple(event for group in timeline.events.values() for event in group)
    extra = ExtraClosure("SHFE", date(2026, 9, 25), "临时休市")
    custom = SessionTimeline(events, closures={(extra.exchange, extra.day): extra})
    for day in [20260925, 20260928]:
        assert custom.resolve(day, "AU") == timeline.resolve(day, "AU")


def test_extra_closure_before_weekend_removes_monday_night(timeline: SessionTimeline) -> None:
    events = tuple(event for group in timeline.events.values() for event in group)
    extra = ExtraClosure("SHFE", date(2026, 9, 18), "临时休市")
    custom = SessionTimeline(events, closures={(extra.exchange, extra.day): extra})
    result = custom.resolve(20260921, "AU")
    assert result.periods == COMMODITY_DAY
    assert result.trims == (SessionTrim("remove_night", extra),)
    assert custom.resolve(20260922, "AU") == timeline.resolve(20260922, "AU")


def test_day_only_session_does_not_record_night_trim(timeline: SessionTimeline) -> None:
    events = tuple(event for group in timeline.events.values() for event in group)
    extra = ExtraClosure("INE", date(2026, 9, 22), "临时休市")
    custom = SessionTimeline(events, closures={(extra.exchange, extra.day): extra})
    for day in [20260923, 20260928]:
        result = custom.resolve(day, "EC")
        assert result.periods == COMMODITY_DAY
        assert result.trims == ()


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
            # JQ通用日历包含FU旧合约终止、新合约挂牌之间的工作日。
            delisted = product == "FU" and date(2018, 6, 27) <= day < date(2018, 7, 16)
            assert bool(timeline.resolve(day, product).periods) == (day in trade_days and not delisted), (day, product)
