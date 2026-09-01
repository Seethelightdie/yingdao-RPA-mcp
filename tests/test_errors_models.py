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
