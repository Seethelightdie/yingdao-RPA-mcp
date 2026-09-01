"""真实网关：继承原仓库"侦察代替 API"的四条通道 + 日志尾读。

依赖全部构造注入：scan/status/tail_log 在任意平台用临时目录可测；
launch/stop 真实副作用仅 Windows 生效（L3 真机验收清单覆盖）。
严禁在此出现杀进程逻辑——停止只走 Ctrl+Alt+Q。
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from ..config import Config  # config→gateway 无循环依赖，可安全做类型引用
from ..errors import ROBOT_NOT_FOUND, ToolError
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
        launch_fn: Callable[[str], None] | None = None,
        stop_fn: Callable[[], None] | None = None,
        alive_fn: Callable[[int], bool] | None = None,
    ) -> None:
        self.users_dir = users_dir
        self.log_dir = log_dir
        self._launch = launch_fn or _default_launch
        self._stop = stop_fn or _default_stop
        self._alive = alive_fn or _default_alive

    @classmethod
    def from_config(cls, config: Config) -> WindowsGateway:
        return cls(
            users_dir=config.users_dir or default_users_dir(),
            log_dir=config.log_dir or default_log_dir(),
        )

    # ---- scan ----
    async def scan(self) -> list[RobotInfo]:
        robots: list[RobotInfo] = []
        for apps_dir in self._apps_dirs():
            try:
                items = list(apps_dir.iterdir())
            except OSError:  # 他人用户目录可能 PermissionError：跳过继续（缺了就降级）
                continue
            for item in items:
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
        # 口径差异：无任何可解析 package → 原仓库 fallback 版本"未知"；dict 分支缺 version 用"1.0.0"
        return RobotInfo(uuid=robot_dir.name, name=robot_dir.name, path=str(robot_dir),
                         mtime=mtime, version="未知")

    # ---- launch / stop ----
    async def launch(self, uuid: str, params: dict[str, str]) -> None:
        # launch 前先 scan 校验 uuid 存在（base.py 契约，对齐 MockGateway）；
        # scan 每次扫盘，但 launch 是低频动作，可接受
        if not any(r.uuid == uuid for r in await self.scan()):
            raise ToolError(ROBOT_NOT_FOUND, f"未找到机器人 {uuid}",
                            "先用 list_robots 查看可用机器人")
        self._launch(build_launch_url(uuid, params))

    async def stop(self) -> None:
        self._stop()

    # ---- status / tail_log ----
    def _today_log_text(self) -> str | None:
        """当日日志全文；None=当日无日志（影刀未运行/未安装）。"""
        log_file = today_log_path(self.log_dir)
        if not log_file.exists():
            return None
        return log_file.read_text(encoding="utf-8", errors="replace")

    async def status(self, uuid: str | None = None) -> dict[str, RobotStatus]:
        text = self._today_log_text()
        runs = parse_log_text(text) if text is not None else []
        for run in runs:
            # 无 pid 的 run 无法补判，保守视为仍在运行
            if not run.exited and run.pid is not None and not self._alive(run.pid):
                run.exited = True  # 日志未标记退出且进程已死 → 已退出（GetExitCodeProcess）
        if uuid is not None:
            state, exit_code, evidence = status_from_runs(uuid, runs)
            return {
                uuid: RobotStatus(uuid=uuid, state=state, exit_code=exit_code, evidence=evidence),
            }
        result: dict[str, RobotStatus] = {}
        for run in runs:  # 保持日志出现顺序
            if run.uuid in result:
                continue
            state, exit_code, evidence = status_from_runs(run.uuid, runs)
            result[run.uuid] = RobotStatus(
                uuid=run.uuid, state=state, exit_code=exit_code, evidence=evidence)
        return result

    async def tail_log(self, n: int) -> list[str]:
        text = self._today_log_text()
        if text is None:
            return []
        lines = text.splitlines()
        if n <= 0:
            return []
        return lines[-n:]
