"""影刀主日志解析（纯函数，任意平台可测）。

日志: %LOCALAPPDATA%\\ShadowBot\\log\\YYYYMMDD.log
关键行（原仓库实测格式）:
  [TaskManager]  task continue: True. <机器人名> <uuid> <触发方式>
  xbot engine running, pid:<pid>,engineid:<id>
  xbot engine exited, ending          ← 不含 PID，按 LIFO 与最近的 running 配对
存活判定由调用方（WindowsGateway）用 GetExitCodeProcess 补充，本模块不接触进程。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..models import STATE_EXITED, STATE_RUNNING, STATE_UNKNOWN


@dataclass
class EngineRun:
    name: str
    uuid: str
    trigger: str
    start_time: str
    pid: int | None
    engine_id: str | None
    exited: bool = False


def today_log_path(log_dir: Path, day: datetime | None = None) -> Path:
    d = day or datetime.now()
    return log_dir / f"{d:%Y%m%d}.log"


def parse_log_text(text: str) -> list[EngineRun]:
    runs: list[EngineRun] = []
    active_pids: list[int] = []
    pending: tuple[str, str, str, str] | None = None  # (name, uuid, trigger, time)

    for raw in text.splitlines():
        line = raw.strip()
        if "[TaskManager]" in line and "task continue" in line:
            time_part = line[:23].strip()
            info = line.split("task continue:", 1)[1].strip()
            tokens = info.split()
            # tokens 形如: ["True.", 机器人名..., uuid, 触发方式]
            if len(tokens) >= 4 and tokens[0] == "True.":
                pending = (" ".join(tokens[1:-2]), tokens[-2], tokens[-1], time_part)
        elif "xbot engine running" in line:
            time_part = line[:23].strip()
            pid = _extract_after(line, "pid:", int)
            engine_id = _extract_after(line, "engineid:", str)
            name, uuid, trigger, t0 = pending if pending else ("未知机器人", "", "", time_part)
            pending = None
            runs.append(EngineRun(name=name, uuid=uuid, trigger=trigger,
                                  start_time=t0, pid=pid, engine_id=engine_id))
            if pid is not None:
                active_pids.append(pid)
        elif "xbot engine exited" in line:
            if active_pids:
                pid = active_pids.pop()
                for run in reversed(runs):
                    if run.pid == pid and not run.exited:
                        run.exited = True
                        break
    return runs


def _extract_after(line: str, marker: str, conv: Callable[[str], int | str]) -> int | str | None:
    if marker not in line:
        return None
    part = line.split(marker, 1)[1].split(",")[0].strip()
    try:
        return conv(part)
    except ValueError:
        return None


def status_from_runs(uuid: str, runs: list[EngineRun]) -> tuple[str, int | None, list[str]]:
    mine = [r for r in runs if r.uuid == uuid]
    if not mine:
        return STATE_UNKNOWN, None, ["日志中未出现该机器人的运行记录"]
    last = mine[-1]
    evidence = [
        f"{r.start_time} {r.name} pid={r.pid} engineid={r.engine_id} "
        f"trigger={r.trigger} {'exited' if r.exited else 'running'}"
        for r in mine
    ]
    if last.exited:
        return STATE_EXITED, None, evidence
    return STATE_RUNNING, None, evidence
