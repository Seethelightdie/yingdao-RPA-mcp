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
