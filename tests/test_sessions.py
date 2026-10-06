from datetime import date, time
from pathlib import Path

import pytest

from cnfutures_session_timeline import SessionTimeline


def test_resolves_product_session_timeline() -> None:
    timeline = SessionTimeline.load()

    assert timeline.resolve(20141226, "A").template_name == "day-0900-1500"
    assert timeline.resolve(20141229, "A").template_name == "night-2100-0230"
    assert timeline.resolve(20150511, "A").template_name == "night-2100-2330"
    assert timeline.resolve(20150928, "A").template_name == "day-0900-1500"
    assert timeline.resolve(20150929, "A").template_name == "night-2100-2330"
    assert timeline.resolve(20190401, "A").template_name == "night-2100-2300"
    assert timeline.resolve(20200204, "A").template_name == "day-0900-1500"
    assert timeline.resolve(20200507, "A").template_name == "night-2100-2300"


def test_resolved_session_contains_periods_and_source_event() -> None:
    session = SessionTimeline.load().resolve(date(2015, 1, 6), "au")

    assert session.template_name == "night-2100-0230"
    assert session.periods[0].start == time(21)
    assert session.periods[0].end == time(2, 30)
    assert session.effective_at == date(2013, 7, 8)
    assert session.reason == "开通夜盘"


def test_resolves_financial_future_schedule_change() -> None:
    timeline = SessionTimeline.load()

    assert timeline.resolve("20151231", "IF").template_name == "day-0915-1515"
    assert timeline.resolve("20160104", "IF").template_name == "day-0930-1500"


def test_csv_order_does_not_affect_timeline(tmp_path: Path) -> None:
    path = tmp_path / "sessions.csv"
    path.write_text(
        "exchange,product,effective_trade_date,session,reason\n"
        "DCE,A,2020-01-02,night-2100-2300,恢复\n"
        "DCE,A,2019-01-02,day-0900-1500,上市\n",
        encoding="utf-8",
    )

    timeline = SessionTimeline.load(path)

    assert timeline.resolve(20190603, "A").template_name == "day-0900-1500"
    assert timeline.resolve(20200601, "A").template_name == "night-2100-2300"


def test_rejects_duplicate_product_date(tmp_path: Path) -> None:
    path = tmp_path / "sessions.csv"
    path.write_text(
        "exchange,product,effective_trade_date,session,reason\n"
        "DCE,A,2020-01-02,day-0900-1500,上市\n"
        "DCE,A,2020-01-02,night-2100-2300,恢复\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Session 事件重复"):
        SessionTimeline.load(path)


def test_rejects_same_product_on_different_exchanges(tmp_path: Path) -> None:
    path = tmp_path / "sessions.csv"
    path.write_text(
        "exchange,product,effective_trade_date,session,reason\n"
        "DCE,A,2020-01-02,day-0900-1500,上市\n"
        "SHFE,A,2020-01-03,day-0900-1500,上市\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="品种 A 同时属于交易所 DCE 和 SHFE"):
        SessionTimeline.load(path)


def test_unknown_product_and_pre_listing_date_fail() -> None:
    timeline = SessionTimeline.load()

    with pytest.raises(KeyError, match="没有品种 UNKNOWN"):
        timeline.resolve(20260101, "UNKNOWN")
    with pytest.raises(KeyError, match="尚未上市"):
        timeline.resolve(20080714, "A")


@pytest.mark.parametrize("trade_date", [202601, "2026/01/01", "20260230"])
def test_rejects_invalid_compact_date(trade_date: int | str) -> None:
    with pytest.raises(ValueError):
        SessionTimeline.load().resolve(trade_date, "A")
