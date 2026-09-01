"""统一错误模型：所有 MCP 工具的错误都以 code + 中文 message + hint 结构返回。"""
from __future__ import annotations

from typing import Any

# 错误码约定（新增错误码必须加在这里）
ROBOT_NOT_FOUND = "ROBOT_NOT_FOUND"
OUTPUT_DIR_NOT_FOUND = "OUTPUT_DIR_NOT_FOUND"
CONFIG_ERROR = "CONFIG_ERROR"
GATEWAY_UNAVAILABLE = "GATEWAY_UNAVAILABLE"
INTERNAL = "INTERNAL"


class ToolError(Exception):
    def __init__(self, code: str, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint


def error_payload(err: ToolError) -> dict[str, Any]:
    return {"code": err.code, "message": err.message, "hint": err.hint}
