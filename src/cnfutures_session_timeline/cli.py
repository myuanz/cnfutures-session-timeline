import argparse
import json
import sys
from dataclasses import asdict
from datetime import date, time

from . import SessionTimeline
from .calendar import parse_date


def _json_default(value: object) -> str:
    '''将日期、时间及 datetime 序列化为 ISO 8601 字符串。'''
    if isinstance(value, (date, time)):
        return value.isoformat()
    raise TypeError(f"无法 JSON 序列化: {type(value).__name__}")


def main() -> None:
    '''查询某品种的交易日安排。'''
    parser = argparse.ArgumentParser(description="中国期货交易日 session 查询（北京时间）")
    parser.add_argument("date", help="交易日，YYYYMMDD 或 YYYY-MM-DD；含前置夜盘")
    parser.add_argument("product", help="品种代码，如 AU、IF；不接受合约代码")
    parser.add_argument("--json", action="store_true", help="输出 JSON，供程序调用")
    args = parser.parse_args()
    try:
        day = parse_date(args.date)
        result = SessionTimeline.load().resolve(day, args.product)
    except (ValueError, KeyError) as error:
        message = str(error.args[0])
        if args.json:
            print(json.dumps({"error": message}, ensure_ascii=False), file=sys.stderr)
            raise SystemExit(2) from None
        parser.error(message)
    if args.json:
        print(json.dumps(asdict(result), default=_json_default, ensure_ascii=False))
        return
    print(f"{day} {args.product.upper()}（交易日口径，北京时间）")
    print(f"{'交易' if result.periods else '不交易'}：{result.reason}")
    for period in result.periods:
        print(f"  {period.start:%H:%M} → {period.end:%H:%M}")


if __name__ == "__main__":
    main()
