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
