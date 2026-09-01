# yingdao-rpa-mcp L1 实现计划（Mock 网关 + MCP 工具 + 双传输）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付可安装的 `yingdao-rpa-mcp` v0.1 包：5 个 MCP 工具、ShadowBotGateway 唯一接缝（Mock + Windows 双实现）、三级配置、stdio/http 双传输，全部测试在任意 OS 通过（全 mock）。

**Architecture:** 单进程 FastMCP server。工具层只依赖 `ShadowBotGateway` 抽象（唯一架构接缝，5 个动作 scan/launch/status/stop/tail_log）；MockGateway 是产品功能兼测试替身；WindowsGateway 全依赖构造注入，scan/status/tail_log 用临时目录在 Linux 可测。工具层负责"动作后等待验证"编排与结构化错误。

**Tech Stack:** Python ≥3.10、FastMCP ≥2（in-memory Client 测试）、ctypes（Win32 原语，零 Windows 专属第三方依赖）、pytest + pytest-asyncio、ruff。

**范围（Scope）：** 本计划 = 执行阶梯 **L1**（代码全部完成 + 全量 mock 测试）。**不在本计划**：L2（服务器部署 + 远程联调 + token 鉴权）、P4（README/SPEC.md 公开版/COMPARISON/examples/CI yaml）、P5（GitHub 发布）、L3（真机验收 + 日志 fixture 真实采样）。规格来源：`.scratch/mvp-v01/spec.md`（Status: ready-for-agent）；红线见根目录 `AGENTS.md`。

**铁律（执行中随时对照 AGENTS.md）：**
1. stdio 模式下 stdout 是 MCP 协议专用通道——server 日志只能走 stderr。
2. 严禁杀进程停止影刀；唯一停止通道 keybd_event Ctrl+Alt+Q。
3. 真实网关动作后默认等 5 秒验证（mock 默认 0 秒），勿"优化"掉。
4. 严禁硬编码任何真实密钥/PC 用户名/真实 uuid 路径（本文代码中的 uuid 均来自原仓库公开演示数据，可直接使用）。
5. 每个任务结束必须 commit。

---

## File Structure（目标布局）

```
/
├── pyproject.toml                        # 打包、依赖、pytest/ruff 配置
├── src/yingdao_rpa_mcp/
│   ├── __init__.py                       # __version__
│   ├── __main__.py                       # python -m 入口（argparse→config→run）
│   ├── errors.py                         # ToolError + error_payload（统一错误结构）
│   ├── models.py                         # RobotInfo / RobotStatus（领域模型 + to_dict）
│   ├── config.py                         # Config dataclass + 三级覆盖加载（CLI > env > toml）
│   ├── server.py                         # build_server()：5 个 MCP 工具 + 等待编排 + 错误映射
│   ├── gateway/
│   │   ├── __init__.py                   # get_gateway() 工厂（mock/平台分派）
│   │   ├── base.py                       # ShadowBotGateway ABC —— 唯一架构接缝
│   │   ├── mock.py                       # MockGateway（内存状态机 + 假日志）
│   │   └── windows.py                    # WindowsGateway（真实侦察通道，全依赖注入）
│   └── win/
│       ├── params.py                     # build_launch_url / encode_param_value（纯函数）
│       ├── logparse.py                   # today_log_path / parse_log_text / status_from_runs（纯函数）
│       ├── keybd.py                      # send_ctrl_alt_q()（ctypes keybd_event）
│       ├── proclive.py                   # is_pid_alive()（GetExitCodeProcess, STILL_ACTIVE=259）
│       └── launcher.py                   # launch_url()（os.startfile 解析 shadowbot: 协议）
└── tests/
    ├── fixtures/yingdao_sample.log       # 按原仓库实测格式合成的日志样例
    ├── test_errors_models.py
    ├── test_config.py
    ├── test_gateway_factory.py
    ├── test_mock_gateway.py
    ├── test_params.py
    ├── test_logparse.py
    ├── test_windows_gateway.py
    └── test_server_tools.py              # 进程内 FastMCP Client 全工具契约
```

**关键源事实（写代码时以此为准，出处=原仓库 `HnBigVolibear/yingdao_robot_run_api_manage_and_skill`，MIT）：**

- **扫描**：apps 目录 = `users\<用户ID>\apps`；跳过 `_temp` 结尾项；**目录名即 uuid**；元数据按序尝试 `<dir>/xbot_robot/package.json`、`<dir>/package.json`、`<dir>/robot.json`、`<dir>/config.json`；mtime 取 `<dir>/xbot_robot` 子目录；解析键 `name`（缺省用 uuid）、`version`、`description`；按 mtime 降序。
- **启动**：URL = `shadowbot:Run?robot-uuid=<uuid>&<k>=<v>`；参数值只编码 `&`、`=`、`#`、`%`、空格（→`%26`/`%3D`/`%23`/`%25`/`%20`），**中文保持原样**（原仓库已验证影刀支持）；用 `os.startfile(url)` 触发系统协议。
- **日志**：`%LOCALAPPDATA%\ShadowBot\log\YYYYMMDD.log`。行格式（实测）：
  - `[TaskManager]  task continue: True. <机器人名> <uuid> <触发方式>`（行首 23 字符为时间戳）
  - `xbot engine running, pid:<pid>,engineid:<id>`
  - `xbot engine exited, ending`（不含 PID，按 LIFO 与最近的 running 配对）
- **进程存活**：`OpenProcess(0x1000)` → `GetExitCodeProcess` → 返回 259（STILL_ACTIVE）即存活。
- **停止**：keybd_event 依次按下 VK_CONTROL(0x11)、VK_MENU(0x12)、VK_Q(0x51)，睡 0.1s，再逆序释放（KEYEVENTF_KEYUP=0x0002）。SendInput 触发不了影刀全局钩子，必须 keybd_event。

---

### Task 1: 项目脚手架与包骨架

**Files:**
- Create: `pyproject.toml`
- Create: `src/yingdao_rpa_mcp/__init__.py`

- [ ] **Step 1: 确认 git 身份（未配置则先配置本仓库局部身份）**

```bash
cd "/mnt/d/CODE/project/yingdao-rpa-mcp"
git config user.name || true
git config user.email || true
```
Expected: 若两条都有输出则跳过下一命令；若为空，向用户要名字和邮箱后执行：
```bash
git config user.name "用户提供的名字"
git config user.email "用户提供的邮箱"
```

- [ ] **Step 2: 写 pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "yingdao-rpa-mcp"
version = "0.1.0"
description = "影刀（ShadowBot）社区版的 MCP 服务器：侦察代替 API，双传输 + Mock 模式"
requires-python = ">=3.10"
license = { text = "MIT" }
dependencies = [
    "fastmcp>=2.0",
    "tomli; python_version < '3.11'",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "ruff>=0.4"]

[project.scripts]
yingdao-rpa-mcp = "yingdao_rpa_mcp.__main__:main"

[tool.hatch.build.targets.wheel]
packages = ["src/yingdao_rpa_mcp"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

- [ ] **Step 3: 写包骨架**

`src/yingdao_rpa_mcp/__init__.py`:
```python
__version__ = "0.1.0"
```

- [ ] **Step 4: 安装并冒烟**

```bash
cd "/mnt/d/CODE/project/yingdao-rpa-mcp"
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
python -c "import yingdao_rpa_mcp, fastmcp; print(yingdao_rpa_mcp.__version__)"
```
Expected: 打印 `0.1.0`，无 ImportError。

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/ .gitignore AGENTS.md docs/
git commit -m "chore: 项目脚手架、依赖与包骨架"
```

---

### Task 2: 统一错误模型 errors.py

**Files:**
- Create: `src/yingdao_rpa_mcp/errors.py`
- Test: `tests/test_errors_models.py`

- [ ] **Step 1: 写失败测试**

`tests/test_errors_models.py`:
```python
from yingdao_rpa_mcp.errors import ToolError, error_payload


def test_tool_error_carries_fields():
    err = ToolError("ROBOT_NOT_FOUND", "未找到机器人 abc", "先用 list_robots 查看")
    assert err.code == "ROBOT_NOT_FOUND"
    assert "abc" in err.message
    assert err.hint


def test_error_payload_shape():
    err = ToolError("CONFIG_ERROR", "配置错误", "检查 config.toml")
    payload = error_payload(err)
    assert payload == {"code": "CONFIG_ERROR", "message": "配置错误", "hint": "检查 config.toml"}


def test_error_payload_hint_default():
    payload = error_payload(ToolError("INTERNAL", "boom"))
    assert payload["hint"] == ""
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_errors_models.py -v
```
Expected: FAIL，`ModuleNotFoundError: No module named 'yingdao_rpa_mcp.errors'`

- [ ] **Step 3: 写实现**

`src/yingdao_rpa_mcp/errors.py`:
```python
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
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_errors_models.py -v
```
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/yingdao_rpa_mcp/errors.py tests/test_errors_models.py
git commit -m "feat: 统一错误模型 ToolError"
```

---

### Task 3: 领域模型 models.py

**Files:**
- Create: `src/yingdao_rpa_mcp/models.py`
- Modify: `tests/test_errors_models.py`（追加测试，文件名不改）

- [ ] **Step 1: 追加失败测试**

在 `tests/test_errors_models.py` 末尾追加：
```python
from datetime import datetime

from yingdao_rpa_mcp.models import (
    STATE_EXITED,
    STATE_RUNNING,
    STATE_UNKNOWN,
    RobotInfo,
    RobotStatus,
)


def test_robot_info_to_dict():
    info = RobotInfo(uuid="u-1", name="报表机器人", path="C:/apps/u-1",
                     mtime=datetime(2026, 6, 7, 10, 58, 3), version="1.5.2", description="生成报表")
    d = info.to_dict()
    assert d["uuid"] == "u-1"
    assert d["name"] == "报表机器人"
    assert d["mtime"] == "2026-06-07T10:58:03"
    assert d["version"] == "1.5.2"


def test_robot_info_mtime_none():
    d = RobotInfo(uuid="u-2", name="u-2", path="/x").to_dict()
    assert d["mtime"] is None


def test_robot_status_states():
    assert {STATE_RUNNING, STATE_EXITED, STATE_UNKNOWN} == {"running", "exited", "unknown"}
    st = RobotStatus(uuid="u-1", state=STATE_EXITED, exit_code=0, evidence=["已退出"])
    d = st.to_dict()
    assert d == {"uuid": "u-1", "state": "exited", "exit_code": 0, "evidence": ["已退出"]}
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_errors_models.py -v
```
Expected: FAIL，`No module named 'yingdao_rpa_mcp.models'`

- [ ] **Step 3: 写实现**

`src/yingdao_rpa_mcp/models.py`:
```python
"""领域模型。字段与 spec 工具契约一一对应。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

STATE_RUNNING = "running"
STATE_EXITED = "exited"
STATE_UNKNOWN = "unknown"


@dataclass
class RobotInfo:
    uuid: str
    name: str
    path: str
    mtime: datetime | None = None
    version: str = ""
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "path": self.path,
            "mtime": self.mtime.isoformat() if self.mtime else None,
            "version": self.version,
            "description": self.description,
        }


@dataclass
class RobotStatus:
    uuid: str
    state: str  # running | exited | unknown
    exit_code: int | None = None
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "uuid": self.uuid,
            "state": self.state,
            "exit_code": self.exit_code,
            "evidence": list(self.evidence),
        }
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_errors_models.py -v
```
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/yingdao_rpa_mcp/models.py tests/test_errors_models.py
git commit -m "feat: 领域模型 RobotInfo/RobotStatus"
```

---

### Task 4: 三级配置加载 config.py

**Files:**
- Create: `src/yingdao_rpa_mcp/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: 写失败测试**

`tests/test_config.py`:
```python
from pathlib import Path

from yingdao_rpa_mcp.config import Config, load_config


def test_defaults():
    cfg = load_config([])
    assert cfg.mock is False
    assert cfg.transport == "stdio"
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8000
    assert cfg.wait_seconds is None
    assert cfg.resolved_wait == 5.0  # 真实网关默认等 5 秒


def test_mock_default_wait_is_zero():
    assert Config(mock=True).resolved_wait == 0.0


def test_explicit_wait_overrides_mock_zero():
    assert Config(mock=True, wait_seconds=2.5).resolved_wait == 2.5


def test_toml_layer(tmp_path: Path):
    toml = tmp_path / "config.toml"
    toml.write_text('mock = true\nport = 9000\n', encoding="utf-8")
    cfg = load_config([], config_path=toml)
    assert cfg.mock is True
    assert cfg.port == 9000
    assert cfg.resolved_wait == 0.0


def test_env_overrides_toml(tmp_path: Path, monkeypatch):
    toml = tmp_path / "config.toml"
    toml.write_text("port = 9000\n", encoding="utf-8")
    monkeypatch.setenv("YINGDAO_MCP_PORT", "9100")
    monkeypatch.setenv("YINGDAO_MCP_MOCK", "1")
    cfg = load_config([], config_path=toml)
    assert cfg.port == 9100
    assert cfg.mock is True


def test_cli_overrides_all(tmp_path: Path, monkeypatch):
    toml = tmp_path / "config.toml"
    toml.write_text("port = 9000\n", encoding="utf-8")
    monkeypatch.setenv("YINGDAO_MCP_PORT", "9100")
    cfg = load_config(["--port", "9200", "--users-dir", "/tmp/users"], config_path=toml)
    assert cfg.port == 9200
    assert cfg.users_dir == Path("/tmp/users")


def test_path_fields_are_path(tmp_path: Path):
    toml = tmp_path / "config.toml"
    toml.write_text(f'log-dir-x = 1\nlog_dir = "{(tmp_path / "log").as_posix()}"\n', encoding="utf-8")
    cfg = load_config([], config_path=toml)
    assert cfg.log_dir == tmp_path / "log"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_config.py -v
```
Expected: FAIL，`No module named 'yingdao_rpa_mcp.config'`

- [ ] **Step 3: 写实现**

`src/yingdao_rpa_mcp/config.py`:
```python
"""配置：CLI > 环境变量（前缀 YINGDAO_MCP_）> config.toml > 默认值。"""
from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

from .errors import CONFIG_ERROR, ToolError

_ENV_PREFIX = "YINGDAO_MCP_"
_WAIT_REAL = 5.0
_WAIT_MOCK = 0.0

_ALLOWED_KEYS = {"mock", "transport", "host", "port", "wait_seconds", "users_dir", "log_dir", "output_dir"}
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
    parser.add_argument("--config", type=Path, default=None, help="config.toml 路径（默认 ./config.toml）")
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
        raise ToolError(CONFIG_ERROR, f"transport 非法: {merged['transport']}", "只支持 stdio / http")
    return Config(**merged)
```

注意：实现里用到 `sys`，在文件头部 import 区补 `import sys`。

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_config.py -v
```
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/yingdao_rpa_mcp/config.py tests/test_config.py
git commit -m "feat: 三级配置加载（CLI > env > toml）"
```

---

### Task 5: 网关接缝 base.py 与工厂

**Files:**
- Create: `src/yingdao_rpa_mcp/gateway/base.py`
- Create: `src/yingdao_rpa_mcp/gateway/__init__.py`
- Create: `tests/test_gateway_factory.py`

- [ ] **Step 1: 写失败测试**

`tests/test_gateway_factory.py`:
```python
import pytest

from yingdao_rpa_mcp.config import Config
from yingdao_rpa_mcp.errors import ToolError
from yingdao_rpa_mcp.gateway import get_gateway
from yingdao_rpa_mcp.gateway.base import ShadowBotGateway
from yingdao_rpa_mcp.gateway.mock import MockGateway


def test_mock_config_returns_mock_gateway():
    gw = get_gateway(Config(mock=True))
    assert isinstance(gw, ShadowBotGateway)
    assert isinstance(gw, MockGateway)


def test_seam_has_five_ops():
    ops = {n for n in ShadowBotGateway.__abstractmethods__}
    assert ops == {"scan", "launch", "status", "stop", "tail_log"}


def test_real_gateway_on_linux_raises(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")  # WSL 开发机即 linux，双保险
    with pytest.raises(ToolError) as ei:
        get_gateway(Config(mock=False))
    assert ei.value.code == "GATEWAY_UNAVAILABLE"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_gateway_factory.py -v
```
Expected: FAIL，`No module named 'yingdao_rpa_mcp.gateway'`

- [ ] **Step 3: 写实现**

`src/yingdao_rpa_mcp/gateway/base.py`:
```python
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
```

`src/yingdao_rpa_mcp/gateway/__init__.py`:
```python
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
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_gateway_factory.py -v
```
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/yingdao_rpa_mcp/gateway/ tests/test_gateway_factory.py
git commit -m "feat: ShadowBotGateway 接缝与网关工厂"
```

---

### Task 6: MockGateway 状态机

**Files:**
- Create: `src/yingdao_rpa_mcp/gateway/mock.py`
- Create: `tests/test_mock_gateway.py`

- [ ] **Step 1: 写失败测试**

`tests/test_mock_gateway.py`:
```python
from datetime import datetime

import pytest

from yingdao_rpa_mcp.errors import ROBOT_NOT_FOUND, ToolError
from yingdao_rpa_mcp.gateway.mock import MockGateway
from yingdao_rpa_mcp.models import STATE_EXITED, STATE_RUNNING, STATE_UNKNOWN, RobotInfo


def seed() -> list[RobotInfo]:
    return [
        RobotInfo(uuid="uuid-a", name="报表机器人", path="/mock/a",
                  mtime=datetime(2026, 6, 7, 10, 0, 0)),
        RobotInfo(uuid="uuid-b", name="采集机器人", path="/mock/b",
                  mtime=datetime(2026, 6, 8, 9, 0, 0)),
    ]


async def test_scan_sorted_by_mtime_desc():
    gw = MockGateway(seed())
    robots = await gw.scan()
    assert [r.uuid for r in robots] == ["uuid-b", "uuid-a"]  # 6/8 在 6/7 之后


async def test_default_robots_available():
    gw = MockGateway()
    assert len(await gw.scan()) >= 3  # 原仓库演示数据


async def test_launch_unknown_uuid_raises():
    gw = MockGateway(seed())
    with pytest.raises(ToolError) as ei:
        await gw.launch("no-such", {})
    assert ei.value.code == ROBOT_NOT_FOUND


async def test_launch_then_status_running():
    gw = MockGateway(seed())
    await gw.launch("uuid-a", {"name": "张三"})
    st = await gw.status("uuid-a")
    assert st["uuid-a"].state == STATE_RUNNING
    assert any("engine running" in e for e in st["uuid-a"].evidence)
    assert any("张三" not in e for e in st["uuid-a"].evidence)  # 传参不进状态证据


async def test_status_unknown_uuid():
    gw = MockGateway(seed())
    st = await gw.status("ghost")
    assert st["ghost"].state == STATE_UNKNOWN


async def test_status_none_aggregates_all():
    gw = MockGateway(seed())
    await gw.launch("uuid-a", {})
    st = await gw.status(None)
    assert {"uuid-a", "uuid-b"} <= set(st)


async def test_simulate_exit_then_exited():
    gw = MockGateway(seed())
    await gw.launch("uuid-a", {})
    gw.simulate_exit("uuid-a", exit_code=0)
    st = await gw.status("uuid-a")
    assert st["uuid-a"].state == STATE_EXITED
    assert st["uuid-a"].exit_code == 0
    assert any("engine exited" in e for e in st["uuid-a"].evidence)


async def test_stop_stops_all_running():
    gw = MockGateway(seed())
    await gw.launch("uuid-a", {})
    await gw.launch("uuid-b", {})
    await gw.stop()
    st = await gw.status(None)
    assert all(s.state == STATE_EXITED for s in st.values())


async def test_tail_log_returns_recent_lines():
    gw = MockGateway(seed())
    await gw.launch("uuid-a", {})
    lines = await gw.tail_log(1)
    assert len(lines) == 1
    assert "engine running" in lines[0]
    assert await gw.tail_log(0) == []
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_mock_gateway.py -v
```
Expected: FAIL，`No module named 'yingdao_rpa_mcp.gateway.mock'`

- [ ] **Step 3: 写实现**

`src/yingdao_rpa_mcp/gateway/mock.py`:
```python
"""Mock 网关：内存假机器人 + 假日志（行格式仿真，便于 tail_log/状态证据演示）。

产品功能（非 Windows 体验/演示），也是全量自动化测试替身。
mock 输出必须可辨识：工具层在 payload 加 "mock": true（见 server.py）。
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
                    evidence=[f"{run['started']} pid={run['pid']} engineid={run['engine_id']} running(mock)"],
                )
            elif u in self._finished and self._finished[u]:
                run = self._finished[u][-1]
                result[u] = RobotStatus(
                    uuid=u, state=STATE_EXITED, exit_code=run["exit_code"],
                    evidence=[f"{run['started']} pid={run['pid']} exited(mock, exit={run['exit_code']})"],
                )
            else:
                result[u] = RobotStatus(uuid=u, state=STATE_UNKNOWN, evidence=["Mock 日志中未出现该机器人的运行记录"])
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
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_mock_gateway.py -v
```
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/yingdao_rpa_mcp/gateway/mock.py tests/test_mock_gateway.py
git commit -m "feat: Mock 网关状态机"
```

---

### Task 7: 启动 URL 构造 win/params.py

**Files:**
- Create: `src/yingdao_rpa_mcp/win/params.py`
- Create: `tests/test_params.py`

- [ ] **Step 1: 写失败测试**

`tests/test_params.py`:
```python
from yingdao_rpa_mcp.win.params import build_launch_url, encode_param_value


def test_encode_special_chars_only():
    assert encode_param_value("a&b=c#d%e f") == "a%26b%3Dc%23d%25e%20f"


def test_chinese_kept_as_is():
    assert encode_param_value("张三") == "张三"  # 原仓库已验证影刀支持中文原样


def test_url_without_params():
    assert build_launch_url("abc-123") == "shadowbot:Run?robot-uuid=abc-123"


def test_url_with_params():
    url = build_launch_url("abc-123", {"name": "张三", "note": "a&b"})
    assert url == "shadowbot:Run?robot-uuid=abc-123&name=张三&note=a%26b"


def test_url_multi_params_ordered():
    url = build_launch_url("u", {"b": "2", "a": "1"})
    assert url == "shadowbot:Run?robot-uuid=u&b=2&a=1"  # 按调用方传入顺序（dict 保序）
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_params.py -v
```
Expected: FAIL，`No module named 'yingdao_rpa_mcp.win.params'`

- [ ] **Step 3: 写实现**

`src/yingdao_rpa_mcp/win/params.py`:
```python
"""shadowbot: URL Scheme 启动链接构造（纯函数，任意平台可测）。

编码口径来自原仓库实测：仅编码 & = # % 空格，中文保持原样。
"""
from __future__ import annotations

_SPECIAL = {"&", "=", "#", "%", " "}


def encode_param_value(value: str) -> str:
    return "".join("%{0:02X}".format(ord(ch)) if ch in _SPECIAL else ch for ch in value)


def build_launch_url(uuid: str, params: dict[str, str] | None = None) -> str:
    url = f"shadowbot:Run?robot-uuid={uuid}"
    for key, value in (params or {}).items():
        url += f"&{encode_param_value(str(key))}={encode_param_value(str(value))}"
    return url
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_params.py -v
```
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/yingdao_rpa_mcp/win/params.py tests/test_params.py
git commit -m "feat: shadowbot URL Scheme 构造与参数编码"
```

---

### Task 8: 影刀日志解析 win/logparse.py

**Files:**
- Create: `src/yingdao_rpa_mcp/win/logparse.py`
- Create: `tests/fixtures/yingdao_sample.log`
- Create: `tests/test_logparse.py`

- [ ] **Step 1: 写日志 fixture（按原仓库实测行格式合成，L3 真机采集后替换/追加）**

`tests/fixtures/yingdao_sample.log`:
```
2026-06-07 10:57:59,000 ShadowBot start
2026-06-07 10:58:03,123 [TaskManager]  task continue: True. 测试skill远程调度系统 c6073f48-0629-4eaa-9414-69de74c28757 Manual
2026-06-07 10:58:03,678 xbot engine running, pid:28920,engineid:3
2026-06-07 10:59:10,000 xbot engine exited, ending
2026-06-07 11:02:00,111 [TaskManager]  task continue: True. 演示-报表生成机器人 8f5e2b9c-1d3a-4e6b-9c8d-2a4b6c8d0e2f Scheduler
2026-06-07 11:02:00,500 xbot engine running, pid:29100,engineid:4
```

- [ ] **Step 2: 写失败测试**

`tests/test_logparse.py`:
```python
from datetime import datetime
from pathlib import Path

from yingdao_rpa_mcp.models import STATE_EXITED, STATE_RUNNING, STATE_UNKNOWN
from yingdao_rpa_mcp.win.logparse import parse_log_text, status_from_runs, today_log_path

FIXTURE = Path(__file__).parent / "fixtures" / "yingdao_sample.log"


def test_today_log_path_format():
    p = today_log_path(Path("/log"), day=datetime(2026, 6, 7, 8, 0, 0))
    assert p == Path("/log/20260607.log")


def test_parse_fixture_two_runs():
    runs = parse_log_text(FIXTURE.read_text(encoding="utf-8"))
    assert len(runs) == 2
    first, second = runs
    assert first.name == "测试skill远程调度系统"
    assert first.uuid == "c6073f48-0629-4eaa-9414-69de74c28757"
    assert first.trigger == "Manual"
    assert first.pid == 28920 and first.engine_id == "3"
    assert first.exited is True  # 有对应 exited 行
    assert second.exited is False  # 尚无 exited 行（存活与否由网关用进程检测补判）
    assert second.pid == 29100 and second.trigger == "Scheduler"


def test_lifo_pairing_two_concurrent_runs():
    text = "\n".join([
        "2026-06-07 12:00:00,000 [TaskManager]  task continue: True. 甲 u-a Manual",
        "2026-06-07 12:00:00,500 xbot engine running, pid:100,engineid:1",
        "2026-06-07 12:00:01,000 [TaskManager]  task continue: True. 乙 u-b Manual",
        "2026-06-07 12:00:01,500 xbot engine running, pid:200,engineid:2",
        "2026-06-07 12:01:00,000 xbot engine exited, ending",  # LIFO → pid 200
    ])
    runs = parse_log_text(text)
    by_pid = {r.pid: r for r in runs}
    assert by_pid[100].exited is False
    assert by_pid[200].exited is True


def test_status_from_runs_branches():
    runs = parse_log_text(FIXTURE.read_text(encoding="utf-8"))
    exited_uuid = "c6073f48-0629-4eaa-9414-69de74c28757"
    running_uuid = "8f5e2b9c-1d3a-4e6b-9c8d-2a4b6c8d0e2f"

    state, code, ev = status_from_runs(exited_uuid, runs)
    assert state == STATE_EXITED and code is None and ev

    state, code, ev = status_from_runs(running_uuid, runs)
    assert state == STATE_RUNNING and code is None

    state, code, ev = status_from_runs("ghost", runs)
    assert state == STATE_UNKNOWN and "未出现" in ev[0]


def test_engine_running_without_taskmanager():
    text = "2026-06-07 12:00:00,500 xbot engine running, pid:300,engineid:5"
    runs = parse_log_text(text)
    assert len(runs) == 1
    assert runs[0].name == "未知机器人" and runs[0].pid == 300
```

- [ ] **Step 3: 跑测试确认失败**

```bash
pytest tests/test_logparse.py -v
```
Expected: FAIL，`No module named 'yingdao_rpa_mcp.win.logparse'`

- [ ] **Step 4: 写实现**

`src/yingdao_rpa_mcp/win/logparse.py`:
```python
"""影刀主日志解析（纯函数，任意平台可测）。

日志: %LOCALAPPDATA%\\ShadowBot\\log\\YYYYMMDD.log
关键行（原仓库实测格式）:
  [TaskManager]  task continue: True. <机器人名> <uuid> <触发方式>
  xbot engine running, pid:<pid>,engineid:<id>
  xbot engine exited, ending          ← 不含 PID，按 LIFO 与最近的 running 配对
存活判定由调用方（WindowsGateway）用 GetExitCodeProcess 补充，本模块不接触进程。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..models import STATE_EXITED, STATE_RUNNING, STATE_UNKNOWN


@dataclass
class EngineRun:
    name: str
    uuid: str
    trigger: str
    start_time: str
    pid: int | None
    engine_id: str | None
    exited: bool = False


def today_log_path(log_dir: Path, day: datetime | None = None) -> Path:
    d = day or datetime.now()
    return log_dir / f"{d:%Y%m%d}.log"


def parse_log_text(text: str) -> list[EngineRun]:
    runs: list[EngineRun] = []
    active_pids: list[int] = []
    pending: tuple[str, str, str, str] | None = None  # (name, uuid, trigger, time)

    for raw in text.splitlines():
        line = raw.strip()
        if "[TaskManager]" in line and "task continue" in line:
            time_part = line[:23].strip()
            info = line.split("task continue:", 1)[1].strip()
            tokens = info.split()
            # tokens 形如: ["True.", 机器人名..., uuid, 触发方式]
            if len(tokens) >= 4 and tokens[0] == "True.":
                pending = (" ".join(tokens[1:-2]), tokens[-2], tokens[-1], time_part)
        elif "xbot engine running" in line:
            time_part = line[:23].strip()
            pid = _extract_after(line, "pid:", int)
            engine_id = _extract_after(line, "engineid:", str)
            name, uuid, trigger, t0 = pending if pending else ("未知机器人", "", "", time_part)
            pending = None
            runs.append(EngineRun(name=name, uuid=uuid, trigger=trigger,
                                  start_time=t0, pid=pid, engine_id=engine_id))
            if pid is not None:
                active_pids.append(pid)
        elif "xbot engine exited" in line:
            if active_pids:
                pid = active_pids.pop()
                for run in reversed(runs):
                    if run.pid == pid and not run.exited:
                        run.exited = True
                        break
    return runs


def _extract_after(line: str, marker: str, conv):
    if marker not in line:
        return None
    part = line.split(marker, 1)[1].split(",")[0].strip()
    try:
        return conv(part)
    except ValueError:
        return None


def status_from_runs(uuid: str, runs: list[EngineRun]) -> tuple[str, int | None, list[str]]:
    mine = [r for r in runs if r.uuid == uuid]
    if not mine:
        return STATE_UNKNOWN, None, ["日志中未出现该机器人的运行记录"]
    last = mine[-1]
    evidence = [
        f"{r.start_time} {r.name} pid={r.pid} engineid={r.engine_id} "
        f"trigger={r.trigger} {'exited' if r.exited else 'running'}"
        for r in mine
    ]
    if last.exited:
        return STATE_EXITED, None, evidence
    return STATE_RUNNING, None, evidence
```

- [ ] **Step 5: 跑测试确认通过**

```bash
pytest tests/test_logparse.py -v
```
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add src/yingdao_rpa_mcp/win/logparse.py tests/fixtures/ tests/test_logparse.py
git commit -m "feat: 影刀主日志解析（TaskManager/engine running/exited, LIFO 配对）"
```

---

### Task 9: Win32 原语 keybd.py / proclive.py / launcher.py

这三个模块是**薄封装**（真实副作用仅 Windows 生效），不做自动化测试（keybd_event 是全局热键，严禁进 CI）；正确性由 L3 真机验收清单覆盖。它们必须能在 Linux 上被 import（Win32 调用全部在函数体内）。

**Files:**
- Create: `src/yingdao_rpa_mcp/win/keybd.py`
- Create: `src/yingdao_rpa_mcp/win/proclive.py`
- Create: `src/yingdao_rpa_mcp/win/launcher.py`

- [ ] **Step 1: 写 keybd.py**

`src/yingdao_rpa_mcp/win/keybd.py`:
```python
"""Ctrl+Alt+Q 优雅停止——严禁杀进程。

为什么 keybd_event 而不是 SendInput：影刀通过全局键盘钩子监听停止快捷键，
SendInput 无法触发全局钩子，keybd_event 可以（原仓库实测结论）。
键序（原仓库实测）：按下 Ctrl、Alt、Q → 睡 0.1s → 逆序释放。
"""
from __future__ import annotations

import time

_VK_CONTROL = 0x11
_VK_MENU = 0x12  # Alt
_VK_Q = 0x51
_KEYEVENTF_KEYUP = 0x0002


def send_ctrl_alt_q() -> None:
    user32 = ctypes.windll.user32
    user32.keybd_event(_VK_CONTROL, 0, 0, 0)
    user32.keybd_event(_VK_MENU, 0, 0, 0)
    user32.keybd_event(_VK_Q, 0, 0, 0)
    time.sleep(0.1)
    user32.keybd_event(_VK_Q, 0, _KEYEVENTF_KEYUP, 0)
    user32.keybd_event(_VK_MENU, 0, _KEYEVENTF_KEYUP, 0)
    user32.keybd_event(_VK_CONTROL, 0, _KEYEVENTF_KEYUP, 0)
```

注意：文件头部 import 区补 `import ctypes`。

- [ ] **Step 2: 写 proclive.py**

`src/yingdao_rpa_mcp/win/proclive.py`:
```python
"""进程存活检测：OpenProcess + GetExitCodeProcess，STILL_ACTIVE=259。"""
from __future__ import annotations

import ctypes

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259


def is_pid_alive(pid: int) -> bool:
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    exit_code = ctypes.c_ulong()
    kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
    kernel32.CloseHandle(handle)
    return exit_code.value == _STILL_ACTIVE
```

- [ ] **Step 3: 写 launcher.py**

`src/yingdao_rpa_mcp/win/launcher.py`:
```python
"""通过 os.startfile 触发系统解析 shadowbot: URL Scheme（需影刀已安装注册协议）。"""
from __future__ import annotations

import os


def launch_url(url: str) -> None:
    os.startfile(url)  # type: ignore[attr-defined]  # 仅 Windows 存在
```

- [ ] **Step 4: 冒烟验证 Linux 可 import**

```bash
python -c "
from yingdao_rpa_mcp.win import keybd, proclive, launcher
print('import ok')
"
```
Expected: 打印 `import ok`（函数体内的 ctypes.windll / os.startfile 不应在 import 时执行）。

- [ ] **Step 5: Commit**

```bash
git add src/yingdao_rpa_mcp/win/keybd.py src/yingdao_rpa_mcp/win/proclive.py src/yingdao_rpa_mcp/win/launcher.py
git commit -m "feat: Win32 原语（keybd_event 停止/进程存活/URL 启动）"
```

---

### Task 10: WindowsGateway（真实网关，依赖注入）

**Files:**
- Create: `src/yingdao_rpa_mcp/gateway/windows.py`
- Create: `tests/test_windows_gateway.py`

**设计**：`scan/status/tail_log` 只依赖注入的目录（Linux 用临时目录 + fixture 可全测）；`launch/stop` 调用注入的函数（测试注入假函数记录调用），默认绑定 Task 9 的真实原语。

- [ ] **Step 1: 写失败测试**

`tests/test_windows_gateway.py`:
```python
import json
from datetime import datetime

from yingdao_rpa_mcp.gateway.windows import WindowsGateway
from yingdao_rpa_mcp.models import STATE_EXITED, STATE_RUNNING
from yingdao_rpa_mcp.win.logparse import today_log_path

FIXTURE = (Path(__file__).parent / "fixtures" / "yingdao_sample.log").read_text(encoding="utf-8")


def make_gateway(tmp_path, alive_pids=None, log_text=None):
    users = tmp_path / "users"
    logdir = tmp_path / "log"
    (users / "user1" / "apps").mkdir(parents=True)
    logdir.mkdir()
    calls = {"launch": [], "stop": 0}
    gw = WindowsGateway(
        users_dir=users,
        log_dir=logdir,
        launch_fn=lambda url: calls["launch"].append(url),
        stop_fn=lambda: calls.__setitem__("stop", calls["stop"] + 1),
        alive_fn=lambda pid: (alive_pids or set()).__contains__(pid),
    )
    if log_text is not None:
        today_log_path(logdir).write_text(log_text, encoding="utf-8")
    return gw, calls


def make_apps(tmp_path):
    """构造真实目录结构：uuid 为目录名，4 个候选 json、_temp 跳过、mtime 取 xbot_robot。"""
    apps = tmp_path / "users" / "user1" / "apps"
    a = apps / "uuid-a"
    (a / "xbot_robot").mkdir(parents=True)
    (a / "xbot_robot" / "package.json").write_text(
        json.dumps({"name": "报表机器人", "version": "1.5.2", "description": "d"}), encoding="utf-8")
    b = apps / "uuid-b"
    b.mkdir(parents=True)
    (b / "xbot_robot").mkdir()  # mtime 取自 xbot_robot 子目录；无 package.json → 落到第 2 候选
    (b / "package.json").write_text(json.dumps({"name": "采集机器人"}), encoding="utf-8")
    c = apps / "uuid-c"
    c.mkdir(parents=True)
    (c / "config.json").write_text("{}", encoding="utf-8")  # 命中第 4 候选，无 name → 名字=uuid
    temp = apps / "uuid-temp_temp"
    temp.mkdir()
    return apps


async def test_scan_structure(tmp_path):
    apps = make_apps(tmp_path)
    os.utime(apps / "uuid-a" / "xbot_robot", (1000000, 1000000))
    os.utime(apps / "uuid-b" / "xbot_robot", (2000000, 2000000))
    gw, _ = make_gateway(tmp_path)
    robots = await gw.scan()
    by_uuid = {r.uuid: r for r in robots}
    assert "uuid-temp_temp" not in by_uuid  # _temp 跳过
    assert by_uuid["uuid-a"].name == "报表机器人"      # 第 1 候选 xbot_robot/package.json
    assert by_uuid["uuid-b"].name == "采集机器人"      # 第 2 候选 package.json
    assert by_uuid["uuid-c"].name == "uuid-c"          # 第 4 候选无 name 字段 → 名字=uuid
    assert [r.uuid for r in robots][0] == "uuid-b"     # mtime 降序（b 的 2000000 > a 的 1000000）


async def test_launch_builds_url_and_records(tmp_path):
    gw, calls = make_gateway(tmp_path)
    await gw.launch("uuid-a", {"name": "张三", "note": "a&b"})
    assert calls["launch"] == ["shadowbot:Run?robot-uuid=uuid-a&name=张三&note=a%26b"]


async def test_stop_calls_primitives(tmp_path):
    gw, calls = make_gateway(tmp_path)
    await gw.stop()
    assert calls["stop"] == 1


async def test_status_uses_log_and_liveness(tmp_path):
    gw, _ = make_gateway(tmp_path, alive_pids={29100}, log_text=FIXTURE)
    st = await gw.status()
    assert st["c6073f48-0629-4eaa-9414-69de74c28757"].state == STATE_EXITED
    assert st["8f5e2b9c-1d3a-4e6b-9c8d-2a4b6c8d0e2f"].state == STATE_RUNNING  # pid 29100 存活


async def test_status_dead_pid_means_exited(tmp_path):
    gw, _ = make_gateway(tmp_path, alive_pids=set(), log_text=FIXTURE)
    st = await gw.status()
    assert st["8f5e2b9c-1d3a-4e6b-9c8d-2a4b6c8d0e2f"].state == STATE_EXITED  # 进程已死


async def test_status_single_uuid(tmp_path):
    gw, _ = make_gateway(tmp_path, alive_pids={29100}, log_text=FIXTURE)
    st = await gw.status("c6073f48-0629-4eaa-9414-69de74c28757")
    assert set(st) == {"c6073f48-0629-4eaa-9414-69de74c28757"}
    assert st["c6073f48-0629-4eaa-9414-69de74c28757"].state == STATE_EXITED


async def test_tail_log_missing_file(tmp_path):
    gw, _ = make_gateway(tmp_path)
    assert await gw.tail_log(10) == []  # 当日无日志返回空列表（spec 契约）


async def test_tail_log_reads_today(tmp_path):
    gw, _ = make_gateway(tmp_path, log_text=FIXTURE)
    lines = await gw.tail_log(3)
    assert len(lines) == 3
    assert "engine running" in lines[-1]
```

注意：文件顶部 import 区补 `import os` 与 `from pathlib import Path`。

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_windows_gateway.py -v
```
Expected: FAIL，`No module named 'yingdao_rpa_mcp.gateway.windows'`

- [ ] **Step 3: 写实现**

`src/yingdao_rpa_mcp/gateway/windows.py`:
```python
"""真实网关：继承原仓库"侦察代替 API"的四条通道 + 日志尾读。

依赖全部构造注入：scan/status/tail_log 在任意平台用临时目录可测；
launch/stop 真实副作用仅 Windows 生效（L3 真机验收清单覆盖）。
严禁在此出现杀进程逻辑——停止只走 Ctrl+Alt+Q。
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from ..models import RobotInfo, RobotStatus
from ..win.logparse import parse_log_text, status_from_runs, today_log_path
from ..win.params import build_launch_url
from .base import ShadowBotGateway

_PACKAGE_CANDIDATES = ("xbot_robot/package.json", "package.json", "robot.json", "config.json")


def default_users_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        profile = os.environ.get("USERPROFILE", "")
        local = str(Path(profile) / "AppData" / "Local") if profile else ""
    return Path(local) / "ShadowBot" / "users"


def default_log_dir() -> Path:
    return default_users_dir().parent / "log"


def _default_launch(url: str) -> None:
    from ..win.launcher import launch_url

    launch_url(url)


def _default_stop() -> None:
    from ..win.keybd import send_ctrl_alt_q

    send_ctrl_alt_q()


def _default_alive(pid: int) -> bool:
    from ..win.proclive import is_pid_alive

    return is_pid_alive(pid)


class WindowsGateway(ShadowBotGateway):
    def __init__(
        self,
        users_dir: Path,
        log_dir: Path,
        launch_fn=None,
        stop_fn=None,
        alive_fn=None,
    ) -> None:
        self.users_dir = users_dir
        self.log_dir = log_dir
        self._launch = launch_fn or _default_launch
        self._stop = stop_fn or _default_stop
        self._alive = alive_fn or _default_alive

    @classmethod
    def from_config(cls, config):  # noqa: ANN001（避免循环 import，Config 为鸭子类型）
        return cls(
            users_dir=config.users_dir or default_users_dir(),
            log_dir=config.log_dir or default_log_dir(),
        )

    # ---- scan ----
    async def scan(self) -> list[RobotInfo]:
        robots: list[RobotInfo] = []
        for apps_dir in self._apps_dirs():
            for item in apps_dir.iterdir():
                if item.name.endswith("_temp") or not item.is_dir():
                    continue
                robots.append(self._read_robot(item))
        robots.sort(key=lambda r: r.mtime or datetime.min, reverse=True)
        return robots

    def _apps_dirs(self) -> list[Path]:
        if not self.users_dir.exists():
            return []
        dirs = []
        for user_id in sorted(self.users_dir.iterdir()):
            apps = user_id / "apps"
            if user_id.is_dir() and apps.is_dir():
                dirs.append(apps)
        return dirs

    def _read_robot(self, robot_dir: Path) -> RobotInfo:
        xbot = robot_dir / "xbot_robot"
        mtime = datetime.fromtimestamp(xbot.stat().st_mtime) if xbot.is_dir() else None
        for candidate in _PACKAGE_CANDIDATES:
            package = robot_dir / candidate
            if not package.is_file():
                continue
            try:
                data = json.loads(package.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict):
                return RobotInfo(
                    uuid=robot_dir.name,
                    name=str(data.get("name", robot_dir.name)),
                    path=str(robot_dir),
                    mtime=mtime,
                    version=str(data.get("version", "1.0.0")),
                    description=str(data.get("description", "")),
                )
        return RobotInfo(uuid=robot_dir.name, name=robot_dir.name, path=str(robot_dir), mtime=mtime)

    # ---- launch / stop ----
    async def launch(self, uuid: str, params: dict[str, str]) -> None:
        self._launch(build_launch_url(uuid, params))

    async def stop(self) -> None:
        self._stop()

    # ---- status / tail_log ----
    async def status(self, uuid: str | None = None) -> dict[str, RobotStatus]:
        log_file = today_log_path(self.log_dir)
        if not log_file.exists():
            return {}
        runs = parse_log_text(log_file.read_text(encoding="utf-8", errors="replace"))
        for run in runs:
            if not run.exited and run.pid is not None and not self._alive(run.pid):
                run.exited = True  # 日志未标记退出且进程已死 → 已退出（GetExitCodeProcess）
        if uuid is not None:
            state, exit_code, evidence = status_from_runs(uuid, runs)
            return {uuid: RobotStatus(uuid=uuid, state=state, exit_code=exit_code, evidence=evidence)}
        result: dict[str, RobotStatus] = {}
        for run in runs:  # 保持日志出现顺序
            if run.uuid in result:
                continue
            state, exit_code, evidence = status_from_runs(run.uuid, runs)
            result[run.uuid] = RobotStatus(uuid=run.uuid, state=state, exit_code=exit_code, evidence=evidence)
        return result

    async def tail_log(self, n: int) -> list[str]:
        log_file = today_log_path(self.log_dir)
        if not log_file.exists():
            return []
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        if n <= 0:
            return []
        return lines[-n:]
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_windows_gateway.py -v
```
Expected: 8 passed

- [ ] **Step 5: 全量回归**

```bash
pytest -v
```
Expected: 全部通过（此前各任务测试无回归）。

- [ ] **Step 6: Commit**

```bash
git add src/yingdao_rpa_mcp/gateway/windows.py tests/test_windows_gateway.py
git commit -m "feat: Windows 真实网关（扫描/启动/状态/停止/日志，依赖注入）"
```

---

### Task 11: MCP 工具 server.py（list_robots / get_status / tail_log）

**Files:**
- Create: `src/yingdao_rpa_mcp/server.py`
- Create: `tests/test_server_tools.py`

- [ ] **Step 1: 写失败测试（前三个工具）**

`tests/test_server_tools.py`:
```python
from datetime import datetime

from fastmcp import Client

from yingdao_rpa_mcp.config import Config
from yingdao_rpa_mcp.gateway.mock import MockGateway
from yingdao_rpa_mcp.models import RobotInfo
from yingdao_rpa_mcp.server import build_server


def seed() -> list[RobotInfo]:
    return [
        RobotInfo(uuid="uuid-a", name="报表机器人", path="/mock/a",
                  mtime=datetime(2026, 6, 7, 10, 0, 0)),
        RobotInfo(uuid="uuid-b", name="采集机器人", path="/mock/b",
                  mtime=datetime(2026, 6, 8, 9, 0, 0)),
    ]


def make_server(mock=True):
    cfg = Config(mock=mock)
    return build_server(cfg, gateway=MockGateway(seed()))


async def test_list_robots_contract():
    async with Client(make_server()) as client:
        data = (await client.call_tool("list_robots", {})).data
    assert data["mock"] is True  # AGENTS.md 红线：mock 输出必须可辨识
    assert [r["uuid"] for r in data["robots"]] == ["uuid-b", "uuid-a"]
    assert data["robots"][0]["mtime"] == "2026-06-08T09:00:00"


async def test_get_status_single_unknown():
    async with Client(make_server()) as client:
        data = (await client.call_tool("get_status", {"uuid": "ghost"})).data
    assert data["status"]["state"] == "unknown"
    assert "未出现" in data["status"]["evidence"][0]


async def test_get_status_running_after_run():
    server = build_server(Config(mock=True), gateway=MockGateway(seed()))
    # 经工具流转：先 run 再查
    async with Client(server) as client:
        await client.call_tool("run_robot", {"uuid": "uuid-a", "params": {}})
        data = (await client.call_tool("get_status", {"uuid": "uuid-a"})).data
    assert data["status"]["state"] == "running"


async def test_get_status_aggregate():
    server = build_server(Config(mock=True), gateway=MockGateway(seed()))
    async with Client(server) as client:
        data = (await client.call_tool("get_status", {})).data
    assert {s["uuid"] for s in data["statuses"]} == {"uuid-a", "uuid-b"}


async def test_tail_log():
    server = build_server(Config(mock=True), gateway=MockGateway(seed()))
    async with Client(server) as client:
        await client.call_tool("run_robot", {"uuid": "uuid-a", "params": {}})
        data = (await client.call_tool("tail_log", {"n": 1})).data
    assert len(data["lines"]) == 1
    assert "engine running" in data["lines"][0]


async def test_unknown_tool_error_is_dict_not_exception():
    async with Client(make_server()) as client:
        data = (await client.call_tool("run_robot", {"uuid": "ghost", "params": {}})).data
    assert data["error"]["code"] == "ROBOT_NOT_FOUND"
    assert data["error"]["hint"]
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_server_tools.py -v
```
Expected: FAIL，`cannot import name 'build_server'`

- [ ] **Step 3: 写实现**

`src/yingdao_rpa_mcp/server.py`:
```python
"""MCP 工具层：5 个工具 + 等待编排 + 统一错误结构。

铁律：
- 工具永不抛异常，错误一律返回 {"error": {code, message, hint}}（对 LLM 更友好）；
- 成功 payload 顶层带 "mock": true/false（mock 输出必须可辨识，AGENTS.md 红线）；
- stdio 模式下本模块严禁 print 到 stdout。
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

from fastmcp import FastMCP

from .config import Config
from .errors import INTERNAL, OUTPUT_DIR_NOT_FOUND, ToolError, error_payload
from .gateway import get_gateway
from .gateway.base import ShadowBotGateway
from .models import STATE_RUNNING, STATE_UNKNOWN, RobotStatus


def list_new_files(output_dir: Path, since_ts: float) -> list[str]:
    """产出文件机制（spec story 9 的 v0.1 口径）：运行窗口内新增/修改的文件。"""
    if not output_dir.is_dir():
        raise ToolError(OUTPUT_DIR_NOT_FOUND, f"产出目录不存在: {output_dir}",
                        "先创建目录，或检查 config.toml / run_robot 的 output_dir 参数")
    return sorted(
        str(p) for p in output_dir.iterdir()
        if p.is_file() and p.stat().st_mtime >= since_ts
    )


def build_server(config: Config, gateway: ShadowBotGateway | None = None) -> FastMCP:
    gw = gateway if gateway is not None else get_gateway(config)
    mcp = FastMCP("yingdao-rpa-mcp")

    def ok(payload: dict) -> dict:
        return {"mock": config.mock, **payload}

    def fail(err: ToolError) -> dict:
        return {"mock": config.mock, "error": error_payload(err)}

    @mcp.tool
    async def list_robots() -> dict:
        """列出本机影刀机器人（uuid/名称/路径/修改时间，按修改时间降序）。名称匹配由你在返回结果中完成，无需再调用搜索工具。"""
        try:
            robots = await gw.scan()
            return ok({"robots": [r.to_dict() for r in robots]})
        except ToolError as e:
            return fail(e)
        except Exception as e:  # noqa: BLE001 — 工具边界兜底
            return fail(ToolError(INTERNAL, str(e), "查看 server stderr 日志"))

    @mcp.tool
    async def run_robot(uuid: str, params: dict[str, str] | None = None,
                        output_dir: str | None = None) -> dict:
        """启动指定影刀机器人并等待验证。params 为 key=value 传参（值支持中文）。
        传 output_dir 时返回运行窗口内新增/修改的产出文件。
        ⚠️ 启动前请先与用户确认机器人身份（用 list_robots 的结果）。"""
        try:
            started = time.time()
            await gw.launch(uuid, params or {})
            await asyncio.sleep(config.resolved_wait)
            statuses = await gw.status(uuid)
            status = statuses.get(uuid) or RobotStatus(
                uuid=uuid, state=STATE_UNKNOWN, evidence=["日志中未出现该机器人的运行记录"])
            out_dir = Path(output_dir) if output_dir else config.output_dir
            output_files = list_new_files(out_dir, started) if out_dir else []
            return ok({
                "uuid": uuid,
                "launched": status.state == STATE_RUNNING,
                "state": status.state,
                "evidence": status.evidence,
                "output_files": output_files,
            })
        except ToolError as e:
            return fail(e)
        except Exception as e:  # noqa: BLE001
            return fail(ToolError(INTERNAL, str(e), "查看 server stderr 日志"))

    @mcp.tool
    async def get_status(uuid: str | None = None) -> dict:
        """查询机器人运行状态（running/exited/unknown）。省略 uuid 时汇总当日日志中出现过的全部机器人。判断"机器人是否跑完"用本工具轮询。"""
        try:
            statuses = await gw.status(uuid)
            if uuid is not None:
                status = statuses.get(uuid) or RobotStatus(
                    uuid=uuid, state=STATE_UNKNOWN, evidence=["日志中未出现该机器人的运行记录"])
                return ok({"status": status.to_dict()})
            return ok({"statuses": [s.to_dict() for s in statuses.values()]})
        except ToolError as e:
            return fail(e)
        except Exception as e:  # noqa: BLE001
            return fail(ToolError(INTERNAL, str(e), "查看 server stderr 日志"))

    @mcp.tool
    async def stop_robot() -> dict:
        """【全局停止】向影刀发送 Ctrl+Alt+Q 优雅停止，会停止当前运行的全部机器人（不止一个）。
        严禁杀进程。当前没有机器人运行时返回 stopped=false（不谎报成功）。
        调用前必须先向用户确认："这会停掉所有正在运行的机器人"。"""
        try:
            before = await gw.status()
            running_before = sorted(u for u, s in before.items() if s.state == STATE_RUNNING)
            await gw.stop()
            await asyncio.sleep(config.resolved_wait)
            after = await gw.status()
            running_after = sorted(u for u, s in after.items() if s.state == STATE_RUNNING)
            return ok({
                "stopped": bool(running_before) and not running_after,
                "running_before": running_before,
                "running_after": running_after,
                "evidence": [
                    f"停止前运行中: {running_before or '无'}",
                    f"停止后运行中: {running_after or '无'}",
                ],
            })
        except ToolError as e:
            return fail(e)
        except Exception as e:  # noqa: BLE001
            return fail(ToolError(INTERNAL, str(e), "查看 server stderr 日志"))

    @mcp.tool
    async def tail_log(n: int = 50) -> dict:
        """读取影刀当日日志最后 n 行（1-500）。当日无日志返回空列表。排障时先用它看原始日志。"""
        try:
            clamped = max(1, min(n, 500))
            return ok({"lines": await gw.tail_log(clamped)})
        except ToolError as e:
            return fail(e)
        except Exception as e:  # noqa: BLE001
            return fail(ToolError(INTERNAL, str(e), "查看 server stderr 日志"))

    return mcp
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_server_tools.py -v
```
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/yingdao_rpa_mcp/server.py tests/test_server_tools.py
git commit -m "feat: MCP 工具层（5 工具 + 等待编排 + mock 标识 + 错误结构）"
```

---

### Task 12: run_robot / stop_robot 的编排行为测试

Task 11 已实现这两个工具的代码；本任务补齐**编排语义**测试（等待时长、产出文件、无机器人时停止不谎报）。

**Files:**
- Modify: `tests/test_server_tools.py`（追加）
- Modify: `src/yingdao_rpa_mcp/server.py`（仅当测试暴露问题时修复）

- [ ] **Step 1: 追加失败测试**

在 `tests/test_server_tools.py` 末尾追加：
```python
import os
import time

from yingdao_rpa_mcp.gateway.base import ShadowBotGateway
from yingdao_rpa_mcp.models import RobotStatus


class ExitedGateway(ShadowBotGateway):
    """测试桩：启动后立即退出——验证 launched=False 编排（真实网关秒退场景）。"""

    async def scan(self):
        return [RobotInfo(uuid="u", name="x", path="/x")]

    async def launch(self, uuid, params):
        self.launched = True

    async def status(self, uuid=None):
        return {"u": RobotStatus(uuid="u", state="exited", evidence=["已退出"])}

    async def stop(self):
        pass

    async def tail_log(self, n):
        return []


async def test_run_robot_exited_immediately_reports_not_launched():
    cfg = Config(mock=True, wait_seconds=0.01)
    async with Client(build_server(cfg, gateway=ExitedGateway())) as client:
        data = (await client.call_tool("run_robot", {"uuid": "u"})).data
    assert data["launched"] is False
    assert data["state"] == "exited"
    assert data["evidence"] == ["已退出"]


async def test_run_robot_output_dir_new_files(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    old = out / "old.xlsx"
    old.write_text("old")
    past = time.time() - 100
    os.utime(old, (past, past))  # 旧文件：窗口外
    cfg = Config(mock=True, wait_seconds=0.0, output_dir=out)

    class SlowMock(MockGateway):
        async def launch(self, uuid, params):
            await super().launch(uuid, params)
            new = out / "report_今日.xlsx"
            new.write_text("new")  # mtime = now > 窗口起点 → 应被捕获

    async with Client(build_server(cfg, gateway=SlowMock(seed()))) as client:
        data = (await client.call_tool("run_robot", {"uuid": "uuid-a", "params": {}})).data
    assert data["output_files"] == [str(out / "report_今日.xlsx")]


async def test_run_robot_output_dir_missing_is_error(tmp_path):
    cfg = Config(mock=True, wait_seconds=0.0, output_dir=tmp_path / "nope")
    async with Client(build_server(cfg, gateway=MockGateway(seed()))) as client:
        data = (await client.call_tool("run_robot", {"uuid": "uuid-a", "params": {}})).data
    assert data["error"]["code"] == "OUTPUT_DIR_NOT_FOUND"


async def test_stop_no_robot_running_reports_false():
    async with Client(make_server()) as client:
        data = (await client.call_tool("stop_robot", {})).data
    assert data["stopped"] is False
    assert data["running_before"] == []


async def test_stop_stops_running_robot():
    server = build_server(Config(mock=True), gateway=MockGateway(seed()))
    async with Client(server) as client:
        await client.call_tool("run_robot", {"uuid": "uuid-a", "params": {}})
        data = (await client.call_tool("stop_robot", {})).data
    assert data["stopped"] is True
    assert data["running_before"] == ["uuid-a"]
    assert data["running_after"] == []
```

- [ ] **Step 2: 跑测试**

```bash
pytest tests/test_server_tools.py -v
```
Expected: 11 passed（6 旧 + 5 新）。若 `test_run_robot_output_dir_new_files` 失败，检查 `list_new_files` 的 `>= since_ts` 边界与 `SlowMock.launch` 的写入时机。

- [ ] **Step 3: Commit**

```bash
git add tests/test_server_tools.py src/yingdao_rpa_mcp/server.py
git commit -m "test: run_robot/stop_robot 编排语义（等待、产出文件、无运行不谎报）"
```

---

### Task 13: CLI 入口 + 全量收尾

**Files:**
- Create: `src/yingdao_rpa_mcp/__main__.py`
- Create: `tests/test_entry.py`

- [ ] **Step 1: 写失败测试**

`tests/test_entry.py`:
```python
import subprocess
import sys


def test_help_exits_zero():
    proc = subprocess.run(
        [sys.executable, "-m", "yingdao_rpa_mcp", "--help"],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0
    assert "影刀社区版 MCP 服务器" in proc.stdout
    assert "--mock" in proc.stdout
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_entry.py -v
```
Expected: FAIL（`__main__` 不存在，退出码非 0）

- [ ] **Step 3: 写实现**

`src/yingdao_rpa_mcp/__main__.py`:
```python
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
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_entry.py -v
```
Expected: 1 passed

- [ ] **Step 5: stdio + mock 手动冒烟（MCP Inspector，眼见为实）**

```bash
npx -y @modelcontextprotocol/inspector python -m yingdao_rpa_mcp --mock
```
Expected: 浏览器打开 Inspector → Connect → Tools 里能看到 5 个工具 → `list_robots` 返回 3 个演示机器人且 `mock: true` → `run_robot`（uuid 取列表里的）返回 `launched: true`。

- [ ] **Step 6: 全量测试 + ruff**

```bash
pytest -v
ruff check .
```
Expected: 全部 passed；ruff 无告警（有则修复后重跑）。

- [ ] **Step 7: Commit**

```bash
git add src/yingdao_rpa_mcp/__main__.py tests/test_entry.py
git commit -m "feat: python -m 入口（stdio/http，日志走 stderr）"
```

- [ ] **Step 8: 汇报**

向用户汇报：L1 完成（5 工具 + 双网关 + 双传输 + N 个测试全绿 + Inspector 冒烟通过），下一步是 L2（服务器部署 + 闷闷联调，另立计划）。

---

## Self-Review 记录（写计划时已核）

1. **Spec 覆盖**：5 工具契约（Task 11/12）、mock 标识（Task 11 Step 3 `ok()`）、三级配置（Task 4）、等待可配置 mock=0（Task 4 `resolved_wait` + Task 12）、产出文件机制（Task 12）、全局停止警告进工具描述（Task 11 `stop_robot` docstring）、无机器人不谎报（Task 12）、tail_log 仅当日（Task 8/10）、LIFO 日志配对（Task 8）、keybd_event 键序（Task 9）、4 候选 package 路径与 _temp 跳过（Task 10）、stdout 红线（Task 13）、mock 可辨识（Task 11 测试）。**未覆盖（有意）**：token 鉴权、CI yaml、README/examples → L2/P4/P5 计划。
2. **占位符扫描**：无 TBD/TODO；所有代码步骤含完整代码；唯一交互步骤是 Task 1 Step 1 的 git 身份（需用户提供，属用户数据非技术占位）。
3. **类型一致性**：`resolved_wait`（property，Task 4 定义，Task 11 使用）；`simulate_exit(uuid, exit_code=0)`（Task 6 定义，Task 12 未用，mock 经 `stop`/工具流转）；`status_from_runs -> (state, exit_code, evidence)`（Task 8 定义，Task 10 使用）；`build_server(config, gateway=None)`（Task 11 定义，全测试使用）；`ShadowBotGateway` 五方法名在 Task 5 测试断言锁定。
