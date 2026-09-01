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
    assert set(st) == {"uuid-a"}  # D1: 只聚合当日日志出现过的（uuid-b 未运行，不出现）
    assert st["uuid-a"].state == STATE_RUNNING


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


async def test_relaunch_overwrites_running_state():
    # D5: 同一 uuid 重复 launch 覆盖运行状态，evidence 只反映最后一次启动的 pid
    gw = MockGateway(seed())
    await gw.launch("uuid-a", {})
    old_pid = int((await gw.status("uuid-a"))["uuid-a"].evidence[0].split("pid:")[1].split(",")[0])
    await gw.launch("uuid-a", {})
    st = (await gw.status("uuid-a"))["uuid-a"]
    assert st.state == STATE_RUNNING
    assert len(st.evidence) == 1
    assert int(st.evidence[0].split("pid:")[1].split(",")[0]) == old_pid + 1


async def test_stop_noop_when_nothing_running():
    gw = MockGateway(seed())
    await gw.stop()  # 不抛错
    assert await gw.status(None) == {}  # D1 后语义：无运行记录 → 空 dict


async def test_simulate_exit_nonzero_code():
    gw = MockGateway(seed())
    await gw.launch("uuid-a", {})
    gw.simulate_exit("uuid-a", exit_code=2)
    st = (await gw.status("uuid-a"))["uuid-a"]
    assert st.state == STATE_EXITED
    assert st.exit_code == 2


async def test_status_none_empty_when_no_activity():
    gw = MockGateway(seed())
    assert await gw.status(None) == {}
