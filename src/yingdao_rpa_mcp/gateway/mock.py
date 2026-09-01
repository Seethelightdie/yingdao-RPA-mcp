"""MockGateway 占位骨架（Task 5 工厂联调用）。

【占位说明】本模块目前只有能让网关工厂实例化的最小骨架：
五个动作一律 raise NotImplementedError。Task 6 将用完整的状态机
（scan/launch/status/stop/tail_log 全部内存态模拟）替换本文件内容，
届时本占位实现整体作废——请勿将其误认为最终实现。
"""
from __future__ import annotations

from ..models import RobotInfo, RobotStatus
from .base import ShadowBotGateway


class MockGateway(ShadowBotGateway):
    async def scan(self) -> list[RobotInfo]:
        raise NotImplementedError("Task 6 实现完整状态机")

    async def launch(self, uuid: str, params: dict[str, str]) -> None:
        raise NotImplementedError("Task 6 实现完整状态机")

    async def status(self, uuid: str | None = None) -> dict[str, RobotStatus]:
        raise NotImplementedError("Task 6 实现完整状态机")

    async def stop(self) -> None:
        raise NotImplementedError("Task 6 实现完整状态机")

    async def tail_log(self, n: int) -> list[str]:
        raise NotImplementedError("Task 6 实现完整状态机")
