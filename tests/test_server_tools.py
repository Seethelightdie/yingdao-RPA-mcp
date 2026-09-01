import asyncio
import os
import time
from datetime import datetime

from fastmcp import Client

from yingdao_rpa_mcp.config import Config
from yingdao_rpa_mcp.gateway.base import ShadowBotGateway
from yingdao_rpa_mcp.gateway.mock import MockGateway
from yingdao_rpa_mcp.models import RobotInfo, RobotStatus
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
    """聚合路径契约：uuid 省略时返回"日志出现过"的机器人集合。

    注：Task 6 D1 语义为"当日日志无活动 → status(None) 返回 {}"，
    故本测试先经 run_robot 产生一条运行记录再验证聚合（原稿未 run 直接断言
    {uuid-a, uuid-b}，与 mock 网关的空活动语义冲突，见 Task 11 报告）。
    """
    server = build_server(Config(mock=True), gateway=MockGateway(seed()))
    async with Client(server) as client:
        await client.call_tool("run_robot", {"uuid": "uuid-a", "params": {}})
        data = (await client.call_tool("get_status", {})).data
    assert {s["uuid"] for s in data["statuses"]} == {"uuid-a"}


async def test_tail_log():
    server = build_server(Config(mock=True), gateway=MockGateway(seed()))
    async with Client(server) as client:
        await client.call_tool("run_robot", {"uuid": "uuid-a", "params": {}})
        data = (await client.call_tool("tail_log", {"n": 1})).data
    assert len(data["lines"]) == 1
    assert "engine running" in data["lines"][0]
    assert "note" not in data  # 非空结果不加原因标注


async def test_tail_log_empty_has_note():
    """spec:98 + base.py 契约：空结果的原因标注由工具层补充。"""
    server = build_server(Config(mock=True), gateway=MockGateway(seed()))
    async with Client(server) as client:
        data = (await client.call_tool("tail_log", {"n": 10})).data
    assert data["lines"] == []
    assert "note" in data


async def test_unknown_robot_error_is_dict_not_exception():
    async with Client(make_server()) as client:
        data = (await client.call_tool("run_robot", {"uuid": "ghost", "params": {}})).data
    assert data["error"]["code"] == "ROBOT_NOT_FOUND"
    assert data["error"]["hint"]


class ExitedGateway(ShadowBotGateway):
    """测试桩：启动后立即退出——验证真实网关"5 秒窗口内跑完"的编排。"""

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


async def test_run_robot_exited_reports_launched_with_exited_state():
    cfg = Config(mock=True, wait_seconds=0.01)
    async with Client(build_server(cfg, gateway=ExitedGateway())) as client:
        data = (await client.call_tool("run_robot", {"uuid": "u"})).data
    assert data["launched"] is True   # 观测到启动（哪怕瞬间跑完）
    assert data["state"] == "exited"  # 是否仍在跑看 state


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
            # Linux 粗时钟粒度（CLK_TCK=100）：紧贴 started 写文件，mtime 可能倒退一个 tick
            await asyncio.sleep(0.05)
            new = out / "report_今日.xlsx"
            new.write_text("new")  # mtime = now > 窗口起点 → 应被捕获

    async with Client(build_server(cfg, gateway=SlowMock(seed()))) as client:
        data = (await client.call_tool("run_robot", {"uuid": "uuid-a", "params": {}})).data
    assert data["output_files"] == [str(out / "report_今日.xlsx")]


async def test_run_robot_output_files_none_when_unconfigured():
    async with Client(make_server()) as client:
        data = (await client.call_tool("run_robot", {"uuid": "uuid-a", "params": {}})).data
    assert data["launched"] is True
    assert data["output_files"] is None  # 未配置产出目录 → null（区别于 []）


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
    assert data["evidence"] == ["停止前运行中: 无", "停止后运行中: 无"]


async def test_stop_stops_running_robot():
    server = build_server(Config(mock=True), gateway=MockGateway(seed()))
    async with Client(server) as client:
        await client.call_tool("run_robot", {"uuid": "uuid-a", "params": {}})
        data = (await client.call_tool("stop_robot", {})).data
    assert data["stopped"] is True
    assert data["running_before"] == ["uuid-a"]
    assert data["running_after"] == []
