"""配置：CLI > 环境变量（前缀 YINGDAO_MCP_）> config.toml > 默认值。"""
from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

from .errors import CONFIG_ERROR, ToolError

_ENV_PREFIX = "YINGDAO_MCP_"
_WAIT_REAL = 5.0
_WAIT_MOCK = 0.0

_ALLOWED_KEYS = {
    "mock", "transport", "host", "port", "wait_seconds", "users_dir", "log_dir", "output_dir",
}
_PATH_KEYS = {"users_dir", "log_dir", "output_dir"}


@dataclass
class Config:
    mock: bool = False
    transport: str = "stdio"  # stdio | http
    host: str = "127.0.0.1"
    port: int = 8000
    wait_seconds: float | None = None  # None → 按 mock 取默认（真实 5s / mock 0s）
    users_dir: Path | None = None      # 覆盖 %LOCALAPPDATA%\ShadowBot\users
    log_dir: Path | None = None        # 覆盖 %LOCALAPPDATA%\ShadowBot\log
    output_dir: Path | None = None     # 默认产出目录（run_robot 未显式传时使用）

    @property
    def resolved_wait(self) -> float:
        if self.wait_seconds is not None:
            return self.wait_seconds
        return _WAIT_MOCK if self.mock else _WAIT_REAL


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_convs() -> dict[str, tuple[str, Callable[[str], Any]]]:
    return {
        "MOCK": ("mock", _parse_bool),
        "TRANSPORT": ("transport", str),
        "HOST": ("host", str),
        "PORT": ("port", int),
        "WAIT_SECONDS": ("wait_seconds", float),
        "USERS_DIR": ("users_dir", Path),
        "LOG_DIR": ("log_dir", Path),
        "OUTPUT_DIR": ("output_dir", Path),
    }


def _from_env() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for suffix, (key, conv) in _env_convs().items():
        raw = os.environ.get(_ENV_PREFIX + suffix)
        if raw:
            try:
                out[key] = conv(raw)
            except ValueError as e:
                raise ToolError(CONFIG_ERROR, f"环境变量 {_ENV_PREFIX}{suffix} 值非法: {raw}",
                                f"应为 {conv.__name__} 类型") from e
    return out


def _from_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ToolError(CONFIG_ERROR, f"config.toml 解析失败: {path}", "检查 TOML 语法") from e
    out: dict[str, Any] = {}
    for key in _ALLOWED_KEYS & data.keys():
        value = data[key]
        if key in _PATH_KEYS:
            value = Path(str(value))
        out[key] = value
    return out


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="yingdao-rpa-mcp", description="影刀社区版 MCP 服务器")
    parser.add_argument("--config", type=Path, default=None,
                        help="config.toml 路径（默认 ./config.toml）")
    parser.add_argument("--mock", action="store_true", default=None, help="启用 Mock 模式")
    parser.add_argument("--transport", choices=["stdio", "http"], default=None)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--wait-seconds", type=float, default=None, dest="wait_seconds")
    parser.add_argument("--users-dir", type=Path, default=None, dest="users_dir")
    parser.add_argument("--log-dir", type=Path, default=None, dest="log_dir")
    parser.add_argument("--output-dir", type=Path, default=None, dest="output_dir")
    return parser


def load_config(argv: list[str] | None = None, config_path: Path | None = None) -> Config:
    """argv=None 时读 sys.argv[1:]。测试请显式传 []。"""
    args = _build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    toml_path = config_path or args.config or Path("config.toml")
    merged: dict[str, Any] = {}
    merged.update(_from_toml(toml_path))
    merged.update(_from_env())
    merged.update({k: v for k, v in vars(args).items() if v is not None and k != "config"})
    if merged.get("transport") not in (None, "stdio", "http"):
        raise ToolError(CONFIG_ERROR, f"transport 非法: {merged['transport']}",
                        "只支持 stdio / http")
    return Config(**merged)
