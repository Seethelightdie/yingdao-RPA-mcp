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
    found: list[str] = []
    for p in output_dir.iterdir():
        if not p.is_file():
            continue
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue  # 文件被写锁/消失（Windows 常见）时跳过该文件，不炸整个调用
        if mtime >= since_ts:
            found.append(str(p))
    return sorted(found)


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
        except Exception as e:  # 工具边界兜底
            return fail(ToolError(INTERNAL, str(e), "查看 server stderr 日志"))

    @mcp.tool
    async def run_robot(uuid: str, params: dict[str, str] | None = None,
                        output_dir: str | None = None) -> dict:
        """启动指定影刀机器人并等待验证。params 为 key=value 传参（值支持中文）。
        传 output_dir 时返回运行窗口内新增/修改的产出文件；output_dir 未配置时
        output_files 为 null。
        launched=true 表示日志中观测到启动（含瞬间跑完的情况）；是否仍在运行看 state。
        ⚠️ 启动前请先与用户确认机器人身份（用 list_robots 的结果）。"""
        try:
            started = time.time()
            await gw.launch(uuid, params or {})
            await asyncio.sleep(config.resolved_wait)
            statuses = await gw.status(uuid)
            status = statuses.get(uuid) or RobotStatus(
                uuid=uuid, state=STATE_UNKNOWN, evidence=["日志中未出现该机器人的运行记录"])
            # 空字符串视为未传
            out_dir = Path(output_dir) if output_dir else config.output_dir
            output_files = list_new_files(out_dir, started) if out_dir else None
            return ok({
                "uuid": uuid,
                "launched": status.state != STATE_UNKNOWN,
                "state": status.state,
                "evidence": status.evidence,
                "output_files": output_files,
            })
        except ToolError as e:
            return fail(e)
        except Exception as e:
            return fail(ToolError(INTERNAL, str(e), "查看 server stderr 日志"))

    @mcp.tool
    async def get_status(uuid: str | None = None) -> dict:
        """查询机器人运行状态（running/exited/unknown）。
        省略 uuid 时汇总当日日志中出现过的全部机器人。判断"机器人是否跑完"用本工具轮询。"""
        try:
            statuses = await gw.status(uuid)
            if uuid is not None:
                status = statuses.get(uuid) or RobotStatus(
                    uuid=uuid, state=STATE_UNKNOWN, evidence=["日志中未出现该机器人的运行记录"])
                return ok({"status": status.to_dict()})
            return ok({"statuses": [s.to_dict() for s in statuses.values()]})
        except ToolError as e:
            return fail(e)
        except Exception as e:
            return fail(ToolError(INTERNAL, str(e), "查看 server stderr 日志"))

    @mcp.tool
    async def stop_robot() -> dict:
        """⚠️【全局停止】向影刀发送 Ctrl+Alt+Q 优雅停止，会停止当前运行的全部机器人（不止一个）。
        严禁杀进程。当前没有机器人运行时返回 stopped=false（不谎报成功）。
        调用前必须先向用户确认："这会停掉所有正在运行的机器人"。
        返回 stopped=false 时可能是停止耗时超过验证窗口，请稍后用 get_status 复查。"""
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
        except Exception as e:
            return fail(ToolError(INTERNAL, str(e), "查看 server stderr 日志"))

    @mcp.tool
    async def tail_log(n: int = 50) -> dict:
        """读取影刀当日日志最后 n 行（1-500）。当日无日志返回空列表。排障时先用它看原始日志。"""
        try:
            clamped = max(1, min(n, 500))
            lines = await gw.tail_log(clamped)
            payload: dict = {"lines": lines}
            if not lines:
                payload["note"] = "当日无日志（影刀今天可能未运行或未安装）"
            return ok(payload)
        except ToolError as e:
            return fail(e)
        except Exception as e:
            return fail(ToolError(INTERNAL, str(e), "查看 server stderr 日志"))

    return mcp
