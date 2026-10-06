import csv
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

from chinese_calendar.constants import Holiday, holidays

CALENDAR_START = date(min(holidays).year, 1, 1)
CALENDAR_END = date(max(holidays).year, 12, 31)
ONE_DAY = timedelta(days=1)
EXCHANGES = frozenset({"SHFE", "INE", "DCE", "CZCE", "CFFEX", "GFEX"})

CLOSURES_CSV = files("cnfutures_session_timeline").joinpath("extra_closures.csv")
HOLIDAY_NAMES = {holiday.value: holiday.chinese for holiday in Holiday}


def load_closures(path: Traversable | Path = CLOSURES_CSV) -> dict[tuple[str, date], str]:
    '''按交易所和日期读取额外休市记录。'''
    with path.open("r", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != ["exchange", "date", "reason"]:
            raise ValueError("休市 CSV 列应为: exchange,date,reason")
        closures: dict[tuple[str, date], str] = {}
        for line_number, row in enumerate(reader, start=2):
            if None in row or None in row.values():
                raise ValueError(f"休市 CSV 第 {line_number} 行列数错误")
            exchange = row["exchange"].strip().upper()
            if exchange not in EXCHANGES:
                raise ValueError(f"休市 CSV 第 {line_number} 行交易所未知: {exchange}")
            day = date.fromisoformat(row["date"].strip())
            reason = row["reason"].strip()
            if not reason:
                raise ValueError(f"休市 CSV 第 {line_number} 行缺少原因")
            key = exchange, day
            if key in closures:
                raise ValueError(f"休市事件重复: {exchange} {day}")
            closures[key] = reason
        return closures


def parse_date(value: date | int | str) -> date:
    '''接受 date、YYYYMMDD 或 YYYY-MM-DD，不接受带时间的 datetime。'''
    if isinstance(value, datetime):
        raise ValueError("请传入交易日期，不要传入 datetime")
    if isinstance(value, date):
        return value
    text = str(value)
    if not (len(text) == 8 and text.isdigit() or
            len(text) == 10 and text[4] == text[7] == "-" and
            text.replace("-", "").isdigit()):
        raise ValueError(f"日期应为 YYYYMMDD 或 YYYY-MM-DD: {value}")
    return date.fromisoformat(text)


def validate_date(day: date) -> None:
    if not CALENDAR_START <= day <= CALENDAR_END:
        raise ValueError(f"中国日历仅覆盖 {CALENDAR_START} 至 {CALENDAR_END}: {day}")


def closure_reason(day: date, closures: Mapping[tuple[str, date], str], exchange: str) -> str | None:
    '''期货休市原因，周末调休上班仍然休市。'''
    validate_date(day)
    holiday = holidays.get(day)
    return (HOLIDAY_NAMES[holiday] if holiday else None) or closures.get((exchange, day)) or (
        "周末" if day.weekday() >= 5 else None
    )


def night_date(day: date, closures: Mapping[tuple[str, date], str], exchange: str) -> date | None:
    '''交易日前置夜盘的自然日；跨节假日时返回 None。'''
    previous = day - ONE_DAY
    while True:
        validate_date(previous)
        if previous in holidays or (exchange, previous) in closures:
            return None
        if previous.weekday() < 5:
            return previous
        previous -= ONE_DAY
