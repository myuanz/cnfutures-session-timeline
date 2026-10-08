import csv
from bisect import bisect_right
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Literal, cast

from chinese_calendar.constants import Holiday

from .calendar import ONE_DAY, ExtraClosure, holiday_closure, load_closures, night_dates, night_extra_closure, night_holiday, parse_date, validate_date

type SessionTemplateName = Literal[
    "delisted",        # 下架无交易
    "day-0900-1500",   # 常规商品期货昼盘
    "day-0915-1515",
    "day-0930-1500",   # 常规股指期货昼盘
    "day-0930-1515",   # 常规国债昼盘
    "night-2100-2300",
    "night-2100-2330",
    "night-2100-0100",
    "night-2100-0230",
]


@dataclass(frozen=True)
class SessionPeriod:
    start: time
    end: time

    def __repr__(self) -> str:
        return f'SessionPeriod({self.start} -> {self.end})'

COMMODITY_DAY = (
    SessionPeriod(time(9,   0), time(10, 15)),
    SessionPeriod(time(10, 30), time(11, 30)),
    SessionPeriod(time(13, 30), time(15,  0)),
)

SESSION_PERIODS: dict[SessionTemplateName, tuple[SessionPeriod, ...]] = {
    "delisted": (),
    "day-0900-1500": COMMODITY_DAY,
    "day-0915-1515": (
        SessionPeriod(time(9, 15), time(11, 30)),
        SessionPeriod(time(13), time(15, 15)),
    ),
    "day-0930-1500": (
        SessionPeriod(time(9, 30), time(11, 30)),
        SessionPeriod(time(13), time(15)),
    ),
    "day-0930-1515": (
        SessionPeriod(time(9, 30), time(11, 30)),
        SessionPeriod(time(13), time(15, 15)),
    ),
    "night-2100-2300": (SessionPeriod(time(21), time(23)), *COMMODITY_DAY),
    "night-2100-2330": (SessionPeriod(time(21), time(23, 30)), *COMMODITY_DAY),
    "night-2100-0100": (SessionPeriod(time(21), time(1)), *COMMODITY_DAY),
    "night-2100-0230": (SessionPeriod(time(21), time(2, 30)), *COMMODITY_DAY),
}


@dataclass(frozen=True)
class SessionEvent:
    exchange: str
    product: str
    effective_trade_date: date
    session: SessionTemplateName
    reason: str
    source_url: str = ""
    '''交易所公告链接，未整理时为空字符串'''


@dataclass(frozen=True)
class SessionTrim:
    action: Literal["remove_night", "close"]
    cause: Holiday | ExtraClosure | Literal["weekend", "listing_day"]

    def __repr__(self) -> str:
        if self.cause == "listing_day":
            return "上市首日无夜盘"
        if isinstance(self.cause, Holiday):
            reason = self.cause.chinese
        elif isinstance(self.cause, ExtraClosure):
            reason = self.cause.reason
        else:
            reason = "周末"
        return f"{reason} 休市" if self.action == "close" else f"{reason} 后首个工作日无夜盘"


@dataclass(frozen=True)
class ResolvedSession:
    periods: tuple[SessionPeriod, ...]
    std_session_event: SessionEvent
    '''最近一次公告指定的标准 session'''
    trims: tuple[SessionTrim, ...] = ()
    '''因节假日、政策、上市首日等原因造成的 session 缩减'''

    def __repr__(self) -> str:
        periods = ','.join(f'{p.start:%H%M}~{p.end:%H%M}' for p in self.periods)
        event = self.std_session_event
        description = f'{event.reason} @ {event.effective_trade_date}'
        for trim in self.trims:
            description += f'，{trim!r}'
        return f'ResolvedSession(periods=({periods}), {description})'

SESSION_CSV = files("cnfutures_session_timeline").joinpath("future_session_events.csv")


class SessionTimeline:
    def __init__(
        self, events: tuple[SessionEvent, ...], *, closures: Mapping[tuple[str, date], ExtraClosure],
    ) -> None:
        grouped: dict[str, list[SessionEvent]] = {}
        exchanges: dict[str, str] = {}
        seen: set[tuple[str, str, date]] = set()
        self.closures = dict(closures)
        for event in events:
            existing_exchange = exchanges.setdefault(event.product, event.exchange)
            if existing_exchange != event.exchange:
                raise ValueError(
                    f"品种 {event.product} 同时属于交易所 "
                    f"{existing_exchange} 和 {event.exchange}"
                )
            event_key = event.exchange, event.product, event.effective_trade_date
            if event_key in seen:
                raise ValueError(
                    f"Session 事件重复: {event.exchange}.{event.product} "
                    f"{event.effective_trade_date}"
                )
            seen.add(event_key)
            grouped.setdefault(event.product, []).append(event)
        self.events = {
            key: tuple(sorted(values, key=lambda item: item.effective_trade_date))
            for key, values in grouped.items()
        }
        self.dates = {
            key: tuple(event.effective_trade_date for event in values)
            for key, values in self.events.items()
        }

    @classmethod
    def load(cls, path: Traversable | Path = SESSION_CSV) -> "SessionTimeline":
        with path.open("r", encoding="utf-8") as source:
            return cls(cls._read_events(source), closures=load_closures())

    def resolve(
        self,
        trade_date: date | int | str,
        product: str,
    ) -> ResolvedSession:
        '''按交易日解析实际时段，休市返回空区间，上市前报错。'''
        trade_date = parse_date(trade_date)
        validate_date(trade_date)
        product = product.upper()
        events = self.events.get(product)
        if events is None:
            raise KeyError(f"没有品种 {product} 的 Session 时间表")
        index = bisect_right(self.dates[product], trade_date) - 1
        if index < 0:
            raise KeyError(f"品种 {product} 在 {trade_date} 尚未上市")
        event = events[index]
        periods = SESSION_PERIODS[event.session]
        trims: list[SessionTrim] = []

        # 先按节假日、周末裁剪。
        if periods and (closed := holiday_closure(trade_date)):
            periods = ()
            trims.append(SessionTrim("close", closed))
        elif event.session.startswith("night-"):
            if holiday := night_holiday(trade_date):
                periods = periods[1:]
                trims.append(SessionTrim("remove_night", holiday))

        # 再应用该交易所的额外休市，已移除的时段不重复裁剪。
        if periods:
            if extra := self.closures.get((event.exchange, trade_date)):
                periods = ()
                trims.append(SessionTrim("close", extra))
            elif periods[0].start == time(21):
                if extra := night_extra_closure(trade_date, self.closures, event.exchange):
                    periods = periods[1:]
                    trims.append(SessionTrim("remove_night", extra))

        if (
            periods and periods[0].start == time(21)
            and trade_date == event.effective_trade_date
            and (index == 0 or event.reason == "上市")
        ):
            periods = periods[1:]
            trims.append(SessionTrim("remove_night", "listing_day"))
        return ResolvedSession(periods, event, tuple(trims))

    def trade_day_at(self, dt: datetime, product: str) -> date | None:
        '''查询东八区自然时间所属的交易日，包含时段两端，非交易时段返回 None。'''
        if not isinstance(dt, datetime) or dt.utcoffset() != timedelta(hours=8):
            raise ValueError("请传入带东八区时区（UTC+08:00）的 datetime")
        day = dt.date()
        session = self.resolve(day, product)
        candidates = [day]
        # 夜盘及跨午夜时间还可能属于其后的交易日，周五夜盘属于周一。
        if dt.time() >= time(21) or dt.time() <= time(2, 30):
            next_day = day + ONE_DAY
            while next_day.weekday() >= 5:
                next_day += ONE_DAY
            candidates.append(next_day)

        for trade_day in candidates:
            if trade_day != day:
                session = self.resolve(trade_day, product)
            for period in session.periods:
                start_day = trade_day
                if period.start == time(21):
                    start_day = next(previous for previous in night_dates(trade_day) if previous.weekday() < 5)
                end_day = start_day + ONE_DAY if period.end < period.start else start_day
                start = datetime.combine(start_day, period.start, dt.tzinfo)
                end = datetime.combine(end_day, period.end, dt.tzinfo)
                if start <= dt <= end:
                    return trade_day
        return None

    @staticmethod
    def _read_events(source: Iterable[str]) -> tuple[SessionEvent, ...]:
        cols = ["exchange", "product", "effective_trade_date", "session", "reason", "source_url"]
        reader = csv.DictReader(source)
        if reader.fieldnames != cols:
            raise ValueError(f"Session CSV 列应为: {','.join(cols)}")
        result: list[SessionEvent] = []
        for line_number, row in enumerate(reader, start=2):
            if None in row or None in row.values():
                raise ValueError(f"Session CSV 第 {line_number} 行列数错误")
            session_text = row["session"].strip()
            exchange = row["exchange"].strip().upper()
            product = row["product"].strip().upper()
            day = date.fromisoformat(row["effective_trade_date"].strip())
            reason = row["reason"].strip()
            if not reason:
                raise ValueError(f"Session CSV 第 {line_number} 行缺少原因")
            if session_text not in SESSION_PERIODS:
                raise ValueError(
                    f"Session CSV 第 {line_number} 行类型未知: {session_text}"
                )
            result.append(SessionEvent(
                exchange,
                product,
                day,
                cast(SessionTemplateName, session_text),
                reason,
                row["source_url"].strip(),
            ))
        return tuple(result)
