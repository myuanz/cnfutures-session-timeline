import json
import subprocess
import sys
from dataclasses import asdict

from cnfutures_session_timeline import SessionTimeline
from cnfutures_session_timeline.cli import _json_default


def cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "cnfutures_session_timeline", *args],
        capture_output=True, text=True, check=False,
    )


def test_json_matches_resolve() -> None:
    for day in ["20260921", "20240209", "20150928", "20260926", "20260920", "20250708"]:
        result = cli(day, "AU", "--json")
        assert result.returncode == 0
        assert result.stderr == ""
        data = json.loads(result.stdout)
        expected = json.loads(json.dumps(asdict(SessionTimeline.load().resolve(day, "AU")), default=_json_default))
        assert data == expected
        assert list(data) == ["periods", "std_session_event", "trims"]


def test_closed_json_is_success() -> None:
    result = cli("20240209", "CU", "--json")
    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "periods": [],
        "std_session_event": {
            "exchange": "SHFE", "product": "CU", "effective_trade_date": "2020-05-07",
            "session": "night-2100-0100", "reason": "恢复夜盘",
        },
        "trims": [{
            "action": "close",
            "cause": {"exchange": "SHFE", "day": "2024-02-09", "reason": "除夕日额外休市"},
        }],
    }


def test_json_time_format() -> None:
    data = json.loads(cli("20260921", "AU", "--json").stdout)
    assert data["periods"][0] == {"start": "21:00:00", "end": "02:30:00"}


def test_text_output() -> None:
    result = cli("20260929", "au")
    assert result.returncode == 0
    assert result.stdout == (
        "2026-09-29 AU，`恢复夜盘 @ 2020-05-07`\n"
        "  21:00 → 02:30\n"
        "  09:00 → 10:15\n"
        "  10:30 → 11:30\n"
        "  13:30 → 15:00\n"
    )


def test_closed_text_output() -> None:
    result = cli("20240209", "CU")
    assert result.returncode == 0
    assert result.stdout == "2024-02-09 CU，`恢复夜盘 @ 2020-05-07`，`除夕日额外休市` 休市\n"


def test_holiday_text_output() -> None:
    for day in ["20260925", "20260926", "20260927"]:
        result = cli(day, "AU")
        assert result.returncode == 0
        assert result.stdout == f"2026-09-{day[-2:]} AU，`恢复夜盘 @ 2020-05-07`，`中秋` 休市\n"
    result = cli("20260928", "AU")
    assert result.returncode == 0
    assert result.stdout == (
        "2026-09-28 AU，`恢复夜盘 @ 2020-05-07`，`中秋` 后首个工作日无夜盘\n"
        "  09:00 → 10:15\n"
        "  10:30 → 11:30\n"
        "  13:30 → 15:00\n"
    )


def test_day_only_text_output() -> None:
    result = cli("20260924", "EC")
    assert result.returncode == 0
    assert result.stdout == (
        "2026-09-24 EC，`上市 @ 2023-08-18`\n"
        "  09:00 → 10:15\n"
        "  10:30 → 11:30\n"
        "  13:30 → 15:00\n"
    )
    assert cli("20260928", "EC").stdout.splitlines()[0] == "2026-09-28 EC，`上市 @ 2023-08-18`"


def test_listing_day_text_output() -> None:
    result = cli("20250708", "BZ")
    assert result.returncode == 0
    assert result.stdout.splitlines()[0] == "2025-07-08 BZ，`上市 @ 2025-07-08`，上市首日无夜盘"


def test_json_errors() -> None:
    for args in [("20270101", "AU"), ("20260230", "AU"), ("20260928", "UNKNOWN"), ("20250707", "BZ")]:
        result = cli(*args, "--json")
        assert result.returncode == 2
        assert result.stdout == ""
        assert json.loads(result.stderr)["error"]


def test_cli_requires_product_and_has_no_exchange_option() -> None:
    assert cli("20260928").returncode == 2
    assert cli("20260928", "AU", "--exchange", "SHFE").returncode == 2
