"""Mock 网关：内存假机器人 + 假日志（行格式仿真，便于 tail_log/状态证据演示）。

产品功能（非 Windows 体验/演示），也是全量自动化测试替身。
mock 输出必须可辨识：假日志带 Mock 触发标记、证据行带 (mock) 后缀；
payload 级 "mock": true 标识由工具层（server.py）负责。
"""
from __future__ import annotations

from datetime import datetime

from ..errors import ROBOT_NOT_FOUND, ToolError
from ..models import (
    STATE_EXITED,
    STATE_RUNNING,
    STATE_UNKNOWN,
    RobotInfo,
    RobotStatus,
)
from .base import ShadowBotGateway


def _default_robots() -> list[RobotInfo]:
    """原仓库公开演示数据（HnBigVolibear/yingdao_robot_run_api_manage_and_skill）。"""
    return [
        RobotInfo(uuid="3d1c3cc8-a4e4-48c4-984f-61be9e94a031", name="演示-数据采集机器人",
                  path="mock://apps/3d1c3cc8", mtime=datetime(2024, 1, 15, 10, 30, 0),
                  version="2.1.0", description="自动采集网页数据并导出到Excel"),
        RobotInfo(uuid="8f5e2b9c-1d3a-4e6b-9c8d-2a4b6c8d0e2f", name="演示-报表生成机器人",
                  path="mock://apps/8f5e2b9c", mtime=datetime(2024, 1, 20, 14, 45, 0),
                  version="1.5.2", description="每日自动生成业务报表并发送邮件"),
        RobotInfo(uuid="b2c3d4e5-f6a7-8901-bcde-f23456789012", name="演示-文件整理机器人",
                  path="mock://apps/b2c3d4e5", mtime=datetime(2024, 1, 10, 16, 0, 0),
                  version="1.0.0", description="自动整理和归档文件"),
    ]


class MockGateway(ShadowBotGateway):
    def __init__(self, robots: list[RobotInfo] | None = None) -> None:
        self._robots = list(robots) if robots is not None else _default_robots()
        self._running: dict[str, dict] = {}          # uuid -> {"pid", "started", "engine_id"}
        self._finished: dict[str, list[dict]] = {}   # uuid -> [run]
        self._log: list[str] = []
        self._next_pid = 28000

    def _find(self, uuid: str) -> RobotInfo:
        for r in self._robots:
            if r.uuid == uuid:
                return r
        raise ToolError(ROBOT_NOT_FOUND, f"未找到机器人 {uuid}", "先用 list_robots 查看可用机器人")

    async def scan(self) -> list[RobotInfo]:
        return sorted(self._robots, key=lambda r: r.mtime or datetime.min, reverse=True)

    async def launch(self, uuid: str, params: dict[str, str]) -> None:
        robot = self._find(uuid)
        now = datetime.now().isoformat(timespec="seconds")
        pid = self._next_pid
        self._next_pid += 1
        self._running[uuid] = {"pid": pid, "started": now, "engine_id": pid % 100}
        self._log.append(f"{now} [TaskManager]  task continue: True. {robot.name} {uuid} Mock")
        self._log.append(f"{now} xbot engine running, pid:{pid},engineid:{pid % 100}")

    async def status(self, uuid: str | None = None) -> dict[str, RobotStatus]:
        known = {r.uuid for r in self._robots} | set(self._running) | set(self._finished)
        targets = [uuid] if uuid is not None else sorted(known)
        result: dict[str, RobotStatus] = {}
        for u in targets:
            if u in self._running:
                run = self._running[u]
                result[u] = RobotStatus(
                    uuid=u, state=STATE_RUNNING,
                    evidence=[f"{run['started']} xbot engine running, "
                              f"pid:{run['pid']},engineid:{run['engine_id']} (mock)"],
                )
            elif u in self._finished and self._finished[u]:
                run = self._finished[u][-1]
                result[u] = RobotStatus(
                    uuid=u, state=STATE_EXITED, exit_code=run["exit_code"],
                    evidence=[f"{run['started']} xbot engine exited, ending "
                              f"(mock, exit={run['exit_code']})"],
                )
            else:
                result[u] = RobotStatus(
                    uuid=u, state=STATE_UNKNOWN,
                    evidence=["Mock 日志中未出现该机器人的运行记录"],
                )
        return result

    def simulate_exit(self, uuid: str, exit_code: int = 0) -> None:
        """模拟机器人跑完退出（演示与测试用）。"""
        run = self._running.pop(uuid, None)
        if run is None:
            return
        now = datetime.now().isoformat(timespec="seconds")
        self._log.append(f"{now} xbot engine exited, ending")
        self._finished.setdefault(uuid, []).append({**run, "exit_code": exit_code})

    async def stop(self) -> None:
        for uuid in list(self._running):
            self.simulate_exit(uuid)

    async def tail_log(self, n: int) -> list[str]:
        if n <= 0:
            return []
        return self._log[-n:]
