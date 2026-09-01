import os
from pathlib import Path

import pytest

from yingdao_rpa_mcp.config import Config, load_config
from yingdao_rpa_mcp.errors import CONFIG_ERROR, ToolError


@pytest.fixture(autouse=True)
def _clean_env(tmp_path, monkeypatch):
    """测试隔离：清掉真实 YINGDAO_MCP_* 环境变量，CWD 切到 tmp_path。"""
    for key in list(os.environ):
        if key.startswith("YINGDAO_MCP_"):
            monkeypatch.delenv(key)
    monkeypatch.chdir(tmp_path)


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
    toml.write_text(f'log-dir-x = 1\nlog_dir = "{(tmp_path / "log").as_posix()}"\n',
                    encoding="utf-8")
    cfg = load_config([], config_path=toml)
    assert cfg.log_dir == tmp_path / "log"
    assert not hasattr(cfg, "log_dir_x")  # 未知键被过滤且不报错


# ---- 错误路径 / 类型防御 ----


def test_env_invalid_value_raises(monkeypatch):
    monkeypatch.setenv("YINGDAO_MCP_PORT", "abc")
    with pytest.raises(ToolError) as excinfo:
        load_config([])
    assert excinfo.value.code == CONFIG_ERROR
    assert "整数" in excinfo.value.hint  # hint 须人类可读，不得泄漏私有函数名


def test_bad_toml_raises(tmp_path: Path):
    toml = tmp_path / "config.toml"
    toml.write_text("port = \n", encoding="utf-8")
    with pytest.raises(ToolError) as excinfo:
        load_config([], config_path=toml)
    assert excinfo.value.code == CONFIG_ERROR


def test_toml_unreadable_wrapped_as_tool_error(tmp_path: Path):
    toml = tmp_path / "config.toml"
    toml.mkdir()  # 目录 → open 抛 IsADirectoryError(OSError)
    with pytest.raises(ToolError) as excinfo:
        load_config([], config_path=toml)
    assert excinfo.value.code == CONFIG_ERROR


def test_cli_mock_flag_overrides_toml_false(tmp_path: Path):
    toml = tmp_path / "config.toml"
    toml.write_text("mock = false\n", encoding="utf-8")
    assert load_config(["--mock"], config_path=toml).mock is True
    assert load_config([], config_path=toml).mock is False


def test_toml_port_string_is_coerced(tmp_path: Path):
    toml = tmp_path / "config.toml"
    toml.write_text('port = "9000"\n', encoding="utf-8")
    cfg = load_config([], config_path=toml)
    assert cfg.port == 9000
    assert isinstance(cfg.port, int)


def test_toml_mock_string_false(tmp_path: Path):
    toml = tmp_path / "config.toml"
    toml.write_text('mock = "false"\n', encoding="utf-8")
    assert load_config([], config_path=toml).mock is False


def test_port_out_of_range_raises(tmp_path: Path, monkeypatch):
    toml = tmp_path / "config.toml"
    toml.write_text("port = 70000\n", encoding="utf-8")
    with pytest.raises(ToolError) as excinfo:
        load_config([], config_path=toml)
    assert excinfo.value.code == CONFIG_ERROR
    monkeypatch.setenv("YINGDAO_MCP_PORT", "-1")
    with pytest.raises(ToolError):  # env 入口同样被校验
        load_config([], config_path=toml)
    with pytest.raises(ToolError):  # CLI 入口同样被校验
        load_config(["--port", "99999"], config_path=toml)


def test_negative_wait_seconds_raises(tmp_path: Path):
    toml = tmp_path / "config.toml"
    toml.write_text("wait_seconds = -1\n", encoding="utf-8")
    with pytest.raises(ToolError) as excinfo:
        load_config([], config_path=toml)
    assert excinfo.value.code == CONFIG_ERROR
    with pytest.raises(ToolError):  # CLI 入口同样被校验
        load_config(["--wait-seconds", "-0.5"], config_path=toml)


def test_toml_unknown_key_warns_to_stderr(tmp_path: Path, capsys):
    toml = tmp_path / "config.toml"
    toml.write_text('foo = 1\nport = 9000\n', encoding="utf-8")
    cfg = load_config([], config_path=toml)
    assert cfg.port == 9000
    captured = capsys.readouterr()
    assert "忽略 config.toml 未知键: foo" in captured.err
    assert captured.out == ""
