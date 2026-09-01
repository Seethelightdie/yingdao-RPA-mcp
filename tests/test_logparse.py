from datetime import datetime
from pathlib import Path

from yingdao_rpa_mcp.models import STATE_EXITED, STATE_RUNNING, STATE_UNKNOWN
from yingdao_rpa_mcp.win.logparse import parse_log_text, status_from_runs, today_log_path

FIXTURE = Path(__file__).parent / "fixtures" / "yingdao_sample.log"


def test_today_log_path_format():
    p = today_log_path(Path("/log"), day=datetime(2026, 6, 7, 8, 0, 0))
    assert p == Path("/log/20260607.log")


def test_parse_fixture_two_runs():
    runs = parse_log_text(FIXTURE.read_text(encoding="utf-8"))
    assert len(runs) == 2
    first, second = runs
    assert first.name == "测试skill远程调度系统"
    assert first.uuid == "c6073f48-0629-4eaa-9414-69de74c28757"
    assert first.trigger == "Manual"
    assert first.pid == 28920 and first.engine_id == "3"
    assert first.exited is True  # 有对应 exited 行
    assert second.exited is False  # 尚无 exited 行（存活与否由网关用进程检测补判）
    assert second.pid == 29100 and second.trigger == "Scheduler"


def test_lifo_pairing_two_concurrent_runs():
    text = "\n".join([
        "2026-06-07 12:00:00,000 [TaskManager]  task continue: True. 甲 u-a Manual",
        "2026-06-07 12:00:00,500 xbot engine running, pid:100,engineid:1",
        "2026-06-07 12:00:01,000 [TaskManager]  task continue: True. 乙 u-b Manual",
        "2026-06-07 12:00:01,500 xbot engine running, pid:200,engineid:2",
        "2026-06-07 12:01:00,000 xbot engine exited, ending",  # LIFO → pid 200
    ])
    runs = parse_log_text(text)
    by_pid = {r.pid: r for r in runs}
    assert by_pid[100].exited is False
    assert by_pid[200].exited is True


def test_status_from_runs_branches():
    runs = parse_log_text(FIXTURE.read_text(encoding="utf-8"))
    exited_uuid = "c6073f48-0629-4eaa-9414-69de74c28757"
    running_uuid = "8f5e2b9c-1d3a-4e6b-9c8d-2a4b6c8d0e2f"

    state, code, ev = status_from_runs(exited_uuid, runs)
    assert state == STATE_EXITED and code is None and ev

    state, code, ev = status_from_runs(running_uuid, runs)
    assert state == STATE_RUNNING and code is None

    state, code, ev = status_from_runs("ghost", runs)
    assert state == STATE_UNKNOWN and "未出现" in ev[0]


def test_engine_running_without_taskmanager():
    text = "2026-06-07 12:00:00,500 xbot engine running, pid:300,engineid:5"
    runs = parse_log_text(text)
    assert len(runs) == 1
    assert runs[0].name == "未知机器人" and runs[0].pid == 300
