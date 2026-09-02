"""配置：CLI > 环境变量（前缀 YINGDAO_MCP_）> config.toml > 默认值。"""
from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
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
    "token",
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
    # 静态 Bearer token；None=无鉴权；repr=False 防日志泄漏
    token: str | None = field(default=None, repr=False)

    @property
    def resolved_wait(self) -> float:
        if self.wait_seconds is not None:
            return self.wait_seconds
        return _WAIT_MOCK if self.mock else _WAIT_REAL


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_convs() -> dict[str, tuple[str, Callable[[str], Any], str]]:
    return {
        "MOCK": ("mock", _parse_bool, "1/true/yes/on"),
        "TRANSPORT": ("transport", str, "字符串"),
        "HOST": ("host", str, "字符串"),
        "PORT": ("port", int, "整数"),
        "WAIT_SECONDS": ("wait_seconds", float, "数字"),
        "USERS_DIR": ("users_dir", Path, "路径"),
        "LOG_DIR": ("log_dir", Path, "路径"),
        "OUTPUT_DIR": ("output_dir", Path, "路径"),
        "TOKEN": ("token", str, "字符串"),
    }


def _from_env() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for suffix, (key, conv, hint) in _env_convs().items():
        raw = os.environ.get(_ENV_PREFIX + suffix)
        if raw:
            try:
                out[key] = conv(raw)
            except ValueError as e:
                raise ToolError(CONFIG_ERROR, f"环境变量 {_ENV_PREFIX}{suffix} 值非法: {raw}",
                                f"应为 {hint}") from e
    return out


def _coerce_toml_value(key: str, value: Any) -> Any:
    """TOML 原生值 → 与 env 层相同的转换语义；原生正确类型原样通过。"""
    if key == "mock":  # 原生 bool 或字符串（_parse_bool 语义）
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return _parse_bool(value)
    elif key == "port":  # 原生 int 或整数字符串
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, str) or (isinstance(value, float) and value.is_integer()):
            try:
                return int(value)
            except ValueError as e:
                raise ToolError(CONFIG_ERROR, f"config.toml 中 port 值非法: {value!r}",
                                "应为整数") from e
    elif key == "wait_seconds":  # 原生 int/float 或数字字符串
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError as e:
                raise ToolError(CONFIG_ERROR, f"config.toml 中 wait_seconds 值非法: {value!r}",
                                "应为数字") from e
    else:  # host / transport：与 env 层一致，统一 str() 转换
        return str(value)
    raise ToolError(CONFIG_ERROR, f"config.toml 中 {key} 类型非法: {value!r}", "检查值类型")


def _from_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ToolError(CONFIG_ERROR, f"config.toml 解析失败: {path}", "检查 TOML 语法") from e
    except OSError as e:
        raise ToolError(CONFIG_ERROR, f"config.toml 读取失败: {path}", "检查文件权限") from e
    out: dict[str, Any] = {}
    for key in _ALLOWED_KEYS & data.keys():
        value = data[key]
        if key in _PATH_KEYS:
            out[key] = Path(str(value))
        else:
            out[key] = _coerce_toml_value(key, value)
    unknown = sorted(data.keys() - _ALLOWED_KEYS)
    if unknown:
        print(f"[yingdao-rpa-mcp] 忽略 config.toml 未知键: {', '.join(unknown)}", file=sys.stderr)
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
    parser.add_argument("--token", default=None,
                        help="streamable-http 静态 Bearer token（None=无鉴权）")
    return parser


def _validate_merged(merged: dict[str, Any]) -> None:
    """对 CLI / env / toml 三入口合并后的最终值做范围校验。"""
    port = merged.get("port")
    if port is not None and not 1 <= port <= 65535:
        raise ToolError(CONFIG_ERROR, f"port 超出有效范围: {port}", "应为 1-65535 的整数")
    wait = merged.get("wait_seconds")
    if wait is not None and (wait < 0 or wait != wait):  # wait != wait → nan 防护
        raise ToolError(CONFIG_ERROR, f"wait_seconds 不能为负数: {wait}", "应为非负数字")


def load_config(argv: list[str] | None = None, config_path: Path | None = None) -> Config:
    """argv=None 时读 sys.argv[1:]。测试请显式传 []。"""
    args = _build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    toml_path = config_path or args.config or Path("config.toml")
    merged: dict[str, Any] = {}
    merged.update(_from_toml(toml_path))
    merged.update(_from_env())
    merged.update({k: v for k, v in vars(args).items() if v is not None and k != "config"})
    _validate_merged(merged)
    if merged.get("transport") not in (None, "stdio", "http"):
        raise ToolError(CONFIG_ERROR, f"transport 非法: {merged['transport']}",
                        "只支持 stdio / http")
    return Config(**merged)
