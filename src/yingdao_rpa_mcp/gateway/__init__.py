"""网关工厂：mock 开关与平台分派。"""
from __future__ import annotations

import sys

from ..config import Config
from ..errors import GATEWAY_UNAVAILABLE, ToolError
from .base import ShadowBotGateway

__all__ = ["ShadowBotGateway", "get_gateway"]


def get_gateway(config: Config) -> ShadowBotGateway:
    if config.mock:
        from .mock import MockGateway

        return MockGateway()
    if sys.platform == "win32":
        from .windows import WindowsGateway

        return WindowsGateway.from_config(config)
    raise ToolError(
        GATEWAY_UNAVAILABLE,
        "当前平台没有可用的真实影刀网关",
        "真实网关仅支持 Windows（影刀社区版）；其他平台请加 --mock 或设置 YINGDAO_MCP_MOCK=1",
    )
