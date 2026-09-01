"""领域模型：MCP 工具契约的数据载体（字段清单见 .scratch/mvp-v01/spec.md 工具契约）。"""
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
