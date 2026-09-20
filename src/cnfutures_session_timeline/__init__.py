import csv
from bisect import bisect_right
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, time
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Literal, cast

type SessionTemplateName = Literal[
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


@dataclass(frozen=True)
class ResolvedSession:
    template_name: SessionTemplateName
    periods: tuple[SessionPeriod, ...]
    reason: str
    effective_at: date

    def __repr__(self) -> str:
        period_str = ','.join(f'{p.start.strftime(f'%H%M')}~{p.end.strftime(f'%H%M')}' for p in self.periods)
        return f'ResolvedSession(periods=({period_str}), {self.reason} @ {self.effective_at})'

class SessionTimeline:
    def __init__(self, events: tuple[SessionEvent, ...]) -> None:
        grouped: dict[str, list[SessionEvent]] = {}
        exchanges: dict[str, str] = {}
        seen: set[tuple[str, str, date]] = set()
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
        self.exchanges = exchanges
        self.events = {
            key: tuple(sorted(values, key=lambda item: item.effective_trade_date))
            for key, values in grouped.items()
        }
        self.dates = {
            key: tuple(event.effective_trade_date for event in values)
            for key, values in self.events.items()
        }

    @classmethod
    def load(cls, path: Traversable | Path | None = None) -> "SessionTimeline":
        if path is None:
            path = files("cnfutures_session_timeline").joinpath("future_session_events.csv")
        with path.open("r", encoding="utf-8") as source:
            return cls(cls._read_events(source))

    def resolve(
        self,
        trade_date: date | int | str,
        product: str,
        exchange: str | None = None,
    ) -> ResolvedSession:
        if not isinstance(trade_date, date):
            trade_date_text = str(trade_date)
            if len(trade_date_text) != 8:
                raise ValueError(f"交易日应为 8 位 YYYYMMDD: {trade_date}")
            trade_date = date.fromisoformat(trade_date_text)
        product = product.upper()
        events = self.events.get(product)
        if events is None:
            raise KeyError(f"没有品种 {product} 的 Session 时间表")
        expected_exchange = self.exchanges[product]
        if exchange is not None and exchange.upper() != expected_exchange:
            raise KeyError(
                f"品种 {product} 属于交易所 {expected_exchange}，"
                f"不是 {exchange.upper()}"
            )
        index = bisect_right(self.dates[product], trade_date) - 1
        if index < 0:
            raise KeyError(f"品种 {product} 在 {trade_date} 尚未上市")
        event = events[index]
        return ResolvedSession(
            event.session,
            SESSION_PERIODS[event.session],
            event.reason,
            event.effective_trade_date,
        )

    @staticmethod
    def _read_events(source: Iterable[str]) -> tuple[SessionEvent, ...]:
        cols = ["exchange", "product", "effective_trade_date", "session", "reason"]
        reader = csv.DictReader(source)
        if reader.fieldnames != cols:
            raise ValueError(f"Session CSV 列应为: {','.join(cols)}")
        result: list[SessionEvent] = []
        for line_number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(f"Session CSV 第 {line_number} 行列数错误")
            session_text = row["session"].strip()
            if session_text not in SESSION_PERIODS:
                raise ValueError(
                    f"Session CSV 第 {line_number} 行类型未知: {session_text}"
                )
            reason = row["reason"].strip()
            if not reason:
                raise ValueError(f"Session CSV 第 {line_number} 行缺少原因")
            result.append(SessionEvent(
                row["exchange"].strip().upper(),
                row["product"].strip().upper(),
                date.fromisoformat(row["effective_trade_date"].strip()),
                session_text,
                reason,
            ))
        return tuple(result)
