from pathlib import Path

from yingdao_rpa_mcp.config import Config, load_config


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
