"""shadowbot: URL Scheme 启动链接构造（纯函数，任意平台可测）。

编码口径来自原仓库实测：仅编码 & = # % 空格，中文保持原样。
"""
from __future__ import annotations

_SPECIAL = {"&", "=", "#", "%", " "}


def encode_param_value(value: str) -> str:
    return "".join(f"%{ord(ch):02X}" if ch in _SPECIAL else ch for ch in value)


def build_launch_url(uuid: str, params: dict[str, str] | None = None) -> str:
    url = f"shadowbot:Run?robot-uuid={uuid}"
    for key, value in (params or {}).items():
        url += f"&{encode_param_value(str(key))}={encode_param_value(str(value))}"
    return url
