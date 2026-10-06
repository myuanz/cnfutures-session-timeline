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
    for day in ["20260921", "20240209", "20150928"]:
        result = cli(day, "AU", "--json")
        assert result.returncode == 0
        assert result.stderr == ""
        data = json.loads(result.stdout)
        expected = json.loads(json.dumps(asdict(SessionTimeline.load().resolve(day, "AU")), default=_json_default))
        assert data == expected
        assert set(data) == {"template_name", "periods", "reason", "effective_at"}


def test_closed_json_is_success() -> None:
    result = cli("20240209", "CU", "--json")
    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "template_name": "closed", "periods": [], "reason": "除夕日额外休市", "effective_at": "2024-02-09",
    }


def test_json_time_format() -> None:
    data = json.loads(cli("20260921", "AU", "--json").stdout)
    assert data["periods"][0] == {"start": "21:00:00", "end": "02:30:00"}


def test_text_output() -> None:
    result = cli("20150928", "A")
    assert result.returncode == 0
    assert "取消前置夜盘" in result.stdout
    assert "09:00 → 10:15" in result.stdout


def test_json_errors() -> None:
    for args in [("20270101", "AU"), ("20260230", "AU"), ("20260928", "UNKNOWN"), ("20250707", "BZ")]:
        result = cli(*args, "--json")
        assert result.returncode == 2
        assert result.stdout == ""
        assert json.loads(result.stderr)["error"]


def test_cli_requires_product_and_has_no_exchange_option() -> None:
    assert cli("20260928").returncode == 2
    assert cli("20260928", "AU", "--exchange", "SHFE").returncode == 2
