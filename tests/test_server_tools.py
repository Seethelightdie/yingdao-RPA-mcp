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
