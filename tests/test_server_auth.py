"""协议级鉴权测试：asgi_client 走完整 HTTP 栈，401/200 均在握手期体现。

fastmcp 4.x 实测行为（控制器 2026-09-02 探针）：无/错 token 时客户端握手抛
mcp.shared.exceptions.MCPError（服务端 401，code -32603）；带正确 token 正常。
"""
import pytest
from fastmcp.utilities.tests import asgi_client
from mcp.shared.exceptions import MCPError

from yingdao_rpa_mcp.config import Config
from yingdao_rpa_mcp.gateway.mock import MockGateway
from yingdao_rpa_mcp.server import build_server


def _server_with_token():
    return build_server(Config(mock=True, token="test-token-123"), gateway=MockGateway())


def test_no_token_sets_auth_none():
    server = build_server(Config(mock=True), gateway=MockGateway())
    assert server.auth is None


def test_token_sets_verifier():
    server = _server_with_token()
    assert server.auth is not None  # StaticTokenVerifier 实例


async def test_http_rejects_missing_token():
    with pytest.raises(MCPError):
        async with asgi_client(_server_with_token()) as client:
            _ = client  # 握手期即 401，走不到这里


async def test_http_rejects_wrong_token():
    with pytest.raises(MCPError):
        async with asgi_client(
            _server_with_token(), headers={"Authorization": "Bearer wrong"}
        ) as client:
            _ = client


async def test_http_accepts_valid_token():
    async with asgi_client(
        _server_with_token(), headers={"Authorization": "Bearer test-token-123"}
    ) as client:
        data = (await client.call_tool("list_robots", {})).data
    assert data["mock"] is True
    assert len(data["robots"]) >= 3
