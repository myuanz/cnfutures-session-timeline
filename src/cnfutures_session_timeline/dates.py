from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import cache
from typing import TYPE_CHECKING, Literal

from chinese_calendar.constants import Holiday, holidays

from .calendar import CALENDAR_END, CALENDAR_START, ONE_DAY, parse_date

if TYPE_CHECKING:
    from . import ResolvedSession, SessionTimeline


type Gap = Literal["previous", "next", "none"]


@dataclass(frozen=True, slots=True)
class _DateInfo:
    closure: Holiday | Literal["weekend"] | None
    trade_index: int
    previous_index: int
    next_index: int
    morning_index: int | None
    night_index: int | None
    night_check_dates: tuple[date, ...]
    night_holiday: Holiday | None


def _build_date_index() -> tuple[tuple[date, ...], tuple[_DateInfo, ...]]:
    # 2024 年除夕全市场休市，补入交易日使用的春节假期。
    trading_holidays = holidays | {date(2024, 2, 9): Holiday.spring_festival.value}
    days = tuple(CALENDAR_START + i * ONE_DAY for i in range((CALENDAR_END - CALENDAR_START).days + 1))
    closures: tuple[Holiday | Literal["weekend"] | None, ...] = tuple(
        Holiday(trading_holidays[day]) if day in trading_holidays else "weekend" if day.weekday() >= 5 else None
        for day in days
    )
    trade_days = tuple(day for day, closed in zip(days, closures) if closed is None)
    trade_indices = {day: i for i, day in enumerate(trade_days)}
    night_checks = {
        day: tuple(day - n * ONE_DAY for n in range(1, 4 if day.weekday() == 0 else 2))
        for day in trade_days
    }
    night_holidays = {
        day: next((Holiday(trading_holidays[previous]) for previous in checks if previous in trading_holidays), None)
        for day, checks in night_checks.items()
    }

    records: list[_DateInfo] = []
    for day, closed in zip(days, closures):
        index = trade_indices.get(day, -1)
        next_index = bisect_right(trade_days, day)
        night_index = None
        if closed is None:
            # 越界序号保留到查询时报告，区别于没有夜盘。
            night_index = next_index
            if next_index < len(trade_days):
                cause = night_holidays[trade_days[next_index]]
                if cause is not None:
                    night_index = None
        morning_index = index if index >= 0 else records[-1].night_index if records else -1
        records.append(_DateInfo(
            closed, index, next_index - 1, next_index, morning_index, night_index,
            night_checks.get(day, ()), night_holidays.get(day),
        ))
    return trade_days, tuple(records)


_TRADE_DATES, _DATE_INDEX = _build_date_index()
_START_ORDINAL = CALENDAR_START.toordinal()


class CalendarDate(date):
    '''普通的日历上的一天，与 TradeDate 相对'''

    @classmethod
    def from_value(cls, value: date | datetime | int | str) -> CalendarDate:
        day = value.date() if isinstance(value, datetime) else parse_date(value)
        return cls(day.year, day.month, day.day)

    def as_trade_date(self) -> TradeDate | None:
        return TradeDate.from_value(self)

    def session(self, product: str) -> ResolvedSession:
        from . import ResolvedSession, SessionTrim

        if (closed := TradeDate.closure_on(self)) is None:
            return TradeDate(self.year, self.month, self.day).session(product)
        timeline = _default_timeline()
        event = timeline._event_at(self, product)
        cause = timeline.closures.get((event.exchange, self), closed)
        trims = () if event.session == "delisted" else (SessionTrim("close", cause),)
        return ResolvedSession((), event, trims)


class TradeDate(date):
    '''有交易的日子'''

    def __new__(cls, year: int, month: int, day: int) -> TradeDate:
        value = super().__new__(cls, year, month, day)
        if cls.closure_on(value):
            raise ValueError(f"非交易日: {value}")
        return value

    @staticmethod
    def _info_on(day: date) -> _DateInfo:
        index = day.toordinal() - _START_ORDINAL
        if not 0 <= index < len(_DATE_INDEX):
            raise ValueError(f"中国日历仅覆盖 {CALENDAR_START} 至 {CALENDAR_END}: {day}")
        return _DATE_INDEX[index]

    @classmethod
    def closure_on(cls, day: date) -> Holiday | Literal["weekend"] | None:
        """通用日历休市原因，不包含交易所额外休市。"""
        return cls._info_on(day).closure

    @classmethod
    def _from_index(cls, index: int) -> TradeDate:
        if not 0 <= index < len(_TRADE_DATES):
            raise ValueError(f"中国日历仅覆盖 {CALENDAR_START} 至 {CALENDAR_END}")
        day = _TRADE_DATES[index]
        return cls(day.year, day.month, day.day)

    @classmethod
    def from_value(
        cls, value: date | datetime | int | str, *, gap: Gap = "none",
    ) -> TradeDate | None:
        day = value.date() if isinstance(value, datetime) else parse_date(value)
        info = cls._info_on(day)
        if not isinstance(value, datetime):
            return None if info.trade_index < 0 else cls._from_index(info.trade_index)
        if gap not in ("previous", "next", "none"):
            raise ValueError(f"未知 gap: {gap}")
        if value.utcoffset() != timedelta(hours=8):
            raise ValueError("请传入带东八区时区（UTC+08:00）的 datetime")
        clock = value.time()
        if clock < time(15):
            index = info.morning_index
        elif clock >= time(21):
            index = info.night_index
        else:
            index = {"previous": info.previous_index, "next": info.next_index, "none": None}[gap]
        return None if index is None else cls._from_index(index)

    def shift(self, n: int) -> TradeDate:
        return type(self)._from_index(self._info_on(self).trade_index + n)

    @property
    def previous(self) -> TradeDate:
        return self.shift(-1)

    @property
    def next(self) -> TradeDate:
        return self.shift(1)

    @property
    def night_cancellation_holiday(self) -> Holiday | None:
        """返回取消某日夜盘的节假日原因，交易所额外休市由 SessionTimeline 检查。"""
        return self._info_on(self).night_holiday

    def session(self, product: str) -> ResolvedSession:
        return _default_timeline().resolve(self, product)


@cache
def _default_timeline() -> SessionTimeline:
    from . import SessionTimeline

    return SessionTimeline.load()
