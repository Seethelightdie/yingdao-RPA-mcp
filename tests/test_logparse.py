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
    assert first.name == "示例-远程调度机器人"
    assert first.uuid == "aaaa1111-bbbb-4ccc-8ddd-eeeeffff0001"
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
    exited_uuid = "aaaa1111-bbbb-4ccc-8ddd-eeeeffff0001"
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


def test_taskmanager_without_colon_does_not_crash():
    text = "\n".join([
        "2026-06-07 12:00:00,000 [TaskManager] task continues running",  # 含 "task continue" 无冒号
        "2026-06-07 12:00:00,500 xbot engine running, pid:400,engineid:9",
    ])
    runs = parse_log_text(text)  # 不抛异常
    assert len(runs) == 1
    assert runs[0].name == "未知机器人"


def test_evidence_cap_keeps_latest_20():
    lines = []
    for i in range(25):
        ts = f"2026-06-07 13:{i:02d}:00,000"
        lines.append(f"{ts} [TaskManager]  task continue: True. 压测机器人 cap-uuid Manual")
        lines.append(f"{ts} xbot engine running, pid:{30000 + i},engineid:{i}")
        lines.append(f"{ts} xbot engine exited, ending")
    runs = parse_log_text("\n".join(lines))
    assert len(runs) == 25
    state, code, ev = status_from_runs("cap-uuid", runs)
    assert state == STATE_EXITED and code is None
    assert len(ev) == 21
    assert "共 25 条" in ev[-1]


def test_malformed_lines_bundle():
    text = "\n".join([
        "2026-06-07 14:00:00,000 [TaskManager]  task continue: False. 乙 u-b Manual",  # 不产生 run
        "2026-06-07 14:00:01,000 xbot engine exited, ending",  # exited 无 running → 忽略不崩溃
        "2026-06-07 14:00:02,000 [TaskManager]  task continue: True. 甲 u-a Manual",
        "2026-06-07 14:00:02,500 xbot engine running, pid:abc,engineid:7",  # pid 非数字 → None
        "2026-06-07 14:00:03,000 [TaskManager]  task continue: True. 甲 u-a Manual",
        "2026-06-07 14:00:03,500 xbot engine running, pid:500,engineid:8",
        "2026-06-07 14:00:04,000 xbot engine exited, ending",  # LIFO → 配对末次 pid:500
    ])
    runs = parse_log_text(text)
    assert len(runs) == 2
    assert runs[0].pid is None and runs[0].exited is False
    state, _, _ = status_from_runs("u-a", runs)
    assert state == STATE_EXITED  # last-wins：末次 run 已 exited（首次 run 未 exited）
