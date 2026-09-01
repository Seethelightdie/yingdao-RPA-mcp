"""通过 os.startfile 触发系统解析 shadowbot: URL Scheme（需影刀已安装注册协议）。"""
from __future__ import annotations

import os


def launch_url(url: str) -> None:
    os.startfile(url)  # type: ignore[attr-defined]  # 仅 Windows 存在
