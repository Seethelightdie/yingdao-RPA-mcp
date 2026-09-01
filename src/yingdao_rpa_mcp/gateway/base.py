"""ShadowBotGateway —— 全项目唯一架构接缝。

其上是 MCP 工具层（协议、参数校验、等待编排、错误语义）；
其下是 MockGateway（产品功能兼测试替身）与 WindowsGateway（真实侦察通道）。
工具层与 Mock 不得 import 任何 Win32 专属模块。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import RobotInfo, RobotStatus


class ShadowBotGateway(ABC):
    @abstractmethod
    async def scan(self) -> list[RobotInfo]:
        """列出机器人，按 mtime 降序。"""

    @abstractmethod
    async def launch(self, uuid: str, params: dict[str, str]) -> None:
        """启动机器人。未知 uuid 抛 ToolError(ROBOT_NOT_FOUND)。"""

    @abstractmethod
    async def status(self, uuid: str | None = None) -> dict[str, RobotStatus]:
        """查询状态。uuid=None 汇总当日日志中出现过的全部机器人。"""

    @abstractmethod
    async def stop(self) -> None:
        """优雅停止（Ctrl+Alt+Q / mock 等价操作）。严禁杀进程。"""

    @abstractmethod
    async def tail_log(self, n: int) -> list[str]:
        """当日日志最后 n 行；当日无日志返回空列表。"""
