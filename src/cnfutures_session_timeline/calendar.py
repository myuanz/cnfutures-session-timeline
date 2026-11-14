import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

from chinese_calendar.constants import holidays

CALENDAR_START = date(min(holidays).year, 1, 1)
CALENDAR_END = date(max(holidays).year, 12, 31)
ONE_DAY = timedelta(days=1)
EXCHANGES = frozenset({"SHFE", "INE", "DCE", "CZCE", "CFFEX", "GFEX"})

CLOSURES_CSV = files("cnfutures_session_timeline").joinpath("extra_closures.csv")


@dataclass(frozen=True)
class ExtraClosure:
    exchange: str
    day: date
    reason: str
    '''extra_closures.csv 中的原始原因。'''


def load_closures(path: Traversable | Path = CLOSURES_CSV) -> dict[tuple[str, date], ExtraClosure]:
    '''按交易所和日期读取额外休市记录。'''
    with path.open("r", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != ["exchange", "date", "reason"]:
            raise ValueError("休市 CSV 列应为: exchange,date,reason")
        closures: dict[tuple[str, date], ExtraClosure] = {}
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
            closures[key] = ExtraClosure(exchange, day, reason)
        return closures


def parse_date(value: date | int | str) -> date:
    '''解析 date、YYYYMMDD 或 YYYY-MM-DD，不接受 datetime。'''
    if isinstance(value, datetime):
        raise ValueError("请传入日期，不要传入 datetime")
    if isinstance(value, date):
        return value
    text = str(value)
    if not (len(text) == 8 and text.isdigit() or
            len(text) == 10 and text[4] == text[7] == "-" and
            text.replace("-", "").isdigit()):
        raise ValueError(f"日期应为 YYYYMMDD 或 YYYY-MM-DD: {value}")
    return date.fromisoformat(text)
