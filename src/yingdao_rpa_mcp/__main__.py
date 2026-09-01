"""python -m yingdao_rpa_mcp 入口。

铁律：日志一律走 stderr——stdio 模式下 stdout 是 MCP 协议专用通道。
"""
from __future__ import annotations

import logging
import sys

from .config import load_config
from .errors import ToolError
from .server import build_server


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,  # stdout 是协议专用通道，严禁占用
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    try:
        config = load_config(sys.argv[1:])
        server = build_server(config)
    except ToolError as e:
        print(f"[yingdao-rpa-mcp] {e.code}: {e.message}（{e.hint}）", file=sys.stderr)
        return 2
    if config.transport == "http":
        server.run(transport="http", host=config.host, port=config.port)
    else:
        server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
