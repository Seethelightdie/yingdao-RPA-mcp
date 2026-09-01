import pytest

from yingdao_rpa_mcp.config import Config
from yingdao_rpa_mcp.errors import ToolError
from yingdao_rpa_mcp.gateway import get_gateway
from yingdao_rpa_mcp.gateway.base import ShadowBotGateway
from yingdao_rpa_mcp.gateway.mock import MockGateway


def test_mock_config_returns_mock_gateway():
    gw = get_gateway(Config(mock=True))
    assert isinstance(gw, ShadowBotGateway)
    assert isinstance(gw, MockGateway)


def test_seam_has_five_ops():
    ops = {n for n in ShadowBotGateway.__abstractmethods__}
    assert ops == {"scan", "launch", "status", "stop", "tail_log"}


def test_real_gateway_on_linux_raises(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")  # WSL 开发机即 linux，双保险
    with pytest.raises(ToolError) as ei:
        get_gateway(Config(mock=False))
    assert ei.value.code == "GATEWAY_UNAVAILABLE"
