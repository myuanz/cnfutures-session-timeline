import argparse
import json
import sys
from dataclasses import asdict
from datetime import date, datetime, time

from chinese_calendar.constants import Holiday

from . import ExtraClosure, SessionTimeline
from .calendar import parse_date


def _json_default(value: object) -> str:
    '''将日期、时间及 datetime 序列化为 ISO 8601 字符串。'''
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, Holiday):
        return value.value
    raise TypeError(f"无法 JSON 序列化: {type(value).__name__}")


def main() -> None:
    '''查询某品种的交易日安排。'''
    parser = argparse.ArgumentParser(description="中国期货交易日 session 查询（北京时间）")
    parser.add_argument("date", nargs="?", help="交易日，YYYYMMDD 或 YYYY-MM-DD；含前置夜盘")
    parser.add_argument("product", help="品种代码，如 AU、IF；不接受合约代码")
    parser.add_argument("--trade-day-at", metavar="DATETIME", help="查询自然时间所属交易日，ISO 8601 格式且必须带 +08:00 时区")
    parser.add_argument("--json", action="store_true", help="输出 JSON，供程序调用")
    args = parser.parse_args()

    product = args.product.upper()
    try:
        if args.trade_day_at is not None:
            if args.date is not None:
                raise ValueError("交易日与 --trade-day-at 不能同时传入")
            dt = datetime.fromisoformat(args.trade_day_at)
            trade_day = SessionTimeline.load().trade_day_at(dt, product)
            if args.json:
                print(json.dumps({"trade_day": trade_day}, default=_json_default, ensure_ascii=False))
            else:
                print(trade_day)
            return
        if args.date is None:
            raise ValueError("请传入交易日或使用 --trade-day-at 指定自然时间")
        day = parse_date(args.date)
        result = SessionTimeline.load().resolve(day, product)
    except (ValueError, KeyError) as error:
        message = str(error.args[0])
        if args.json:
            print(json.dumps({"error": message}, ensure_ascii=False), file=sys.stderr)
            raise SystemExit(2) from None
        parser.error(message)
    if args.json:
        print(json.dumps(asdict(result), default=_json_default, ensure_ascii=False))
        return
    event = result.std_session_event
    heading = f"{day} {product}，`{event.reason} @ {event.effective_trade_date}`"
    for trim in result.trims:
        if trim.cause == "listing_day":
            heading += "，上市首日无夜盘"
            continue
        if isinstance(trim.cause, Holiday):
            reason = trim.cause.chinese
        elif isinstance(trim.cause, ExtraClosure):
            reason = trim.cause.reason
        else:
            reason = "周末"
        if trim.action == "close":
            heading += f"，`{reason}` 休市"
        else:
            heading += f"，`{reason}` 后首个工作日无夜盘"
    print(heading)
    for period in result.periods:
        print(f"  {period.start:%H:%M} → {period.end:%H:%M}")


if __name__ == "__main__":
    main()
