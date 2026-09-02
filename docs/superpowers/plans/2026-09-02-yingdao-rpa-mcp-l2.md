# yingdao-rpa-mcp L2 实现计划（token 鉴权 + 服务器部署 + 闷闷联调）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让云服务器上的闷闷（微信 AI 助手）通过 streamable-http + 静态 token 连上 mock 模式的 yingdao-rpa-mcp，用户在微信里看到 3 个演示机器人。

**Architecture:** 代码侧给 FastMCP 4.x 接 `StaticTokenVerifier`（config 新增 token 字段，None=无鉴权保持 stdio 兼容）；部署侧用 git archive 把仓库送上服务器、`python:3.12-slim` 容器运行（宿主机 python 3.6.8 太老），容器加入 cow 的 `cow_default` 网络以容器名互访；闷闷侧往 `/opt/cow/cow/mcp.json` 加一条 server 配置（该文件已存在 context7 先例，格式已核实）。

**Tech Stack:** FastMCP 4.x `StaticTokenVerifier`、fastmcp `asgi_client(headers=...)`（协议级鉴权测试）、Docker 26.1.3、CowAgent mcp_client（`type: streamable-http` + `headers` 支持已核实）。

**侦察事实（2026-09-02 实测，写死在计划里）：**
- 服务器 `root@<你的服务器IP>`（SSH 免密 ✅）；宿主机 python 3.6.8（不可用）；docker 26.1.3
- cow 容器 python **3.10.18**；网络 `cow_default`（容器 IP 172.18.0.2）
- `/opt/cow/cow/mcp.json` 已存在，格式 `{"mcpServers": {<名>: {"type": "streamable-http", "url": ..., "headers": {"Authorization": "Bearer ..."}}}}`（现有 context7 条目——**其中的真实 key 不得复制进任何文档/commit/日志**）
- CowAgent `mcp_client.py`：streamable-http 支持 `headers` 额外头、`timeout`（默认 120s）、每 agent workspace 一个 mcp.json（主 agent = `/opt/cow/cow/mcp.json`）；401 会触发 OAuth 浏览器流程——所以 token 必须一次配对，避免闷闷进入 OAuth 分支
- FastMCP 4.x：`StaticTokenVerifier(tokens={...}, required_scopes=None)` → `FastMCP(name, auth=verifier)`；无/错 token 时客户端握手抛 `MCPError`（服务端 401）；`asgi_client(server, headers={"Authorization": "Bearer ..."})` 可带头
- WSL 本地**无 docker**——镜像构建只能在服务器上做

**范围：** L2 = token 鉴权代码 + 服务器 mock 部署 + 闷闷接线 + 微信验收。**不在本计划**：P4（README/LICENSE/COMPARISON/examples/CI）、P5（GitHub 发布）、L3（用户 PC 真机 + Tailscale）。

**铁律：** token 是秘密——只在服务器端 `.env`（umask 077）与 cow 的 mcp.json 里落盘，**绝不写入本仓库任何文件/commit/计划文档/聊天日志**；mcp.json 修改前必须备份；重启 cow 前 AGENT.md/技能与 ilink 凭证自动恢复机制已验证（handoff）。

---

## File Structure（本计划涉及的文件）

```
/
├── src/yingdao_rpa_mcp/
│   ├── config.py            # 修改：+token 字段（env/CLI/toml 三入口）
│   └── server.py            # 修改：build_server 按 config.token 接线 auth
├── Dockerfile               # 新建：python:3.12-slim，pip install .，CMD http
├── .dockerignore            # 新建：排除 .venv/.git/.scratch/tests/docs
├── tests/
│   ├── test_config.py       # 修改：+token 三入口测试
│   └── test_server_auth.py  # 新建：asgi_client 401/200 协议级测试
└── docs/superpowers/plans/…l2.md   # 本计划
```

服务器侧（不入库）：`/opt/yingdao-rpa-mcp/`（代码 + .env）、容器 `yingdao-rpa-mcp`；cow 侧：`/opt/cow/cow/mcp.json`。

---

### Task 1: config 新增 token 字段

**Files:**
- Modify: `src/yingdao_rpa_mcp/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: 追加失败测试**

在 `tests/test_config.py` 末尾追加：
```python
def test_token_default_none():
    cfg = load_config([])
    assert cfg.token is None


def test_token_from_env(monkeypatch):
    monkeypatch.setenv("YINGDAO_MCP_TOKEN", "sekrit-token-1")
    assert load_config([]).token == "sekrit-token-1"


def test_token_from_cli():
    assert load_config(["--token", "cli-token"]).token == "cli-token"


def test_token_from_toml(tmp_path: Path):
    toml = tmp_path / "config.toml"
    toml.write_text('token = "toml-token"\n', encoding="utf-8")
    assert load_config([], config_path=toml).token == "toml-token"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: 4 FAIL（`Config` 无 token 字段 / parser 无 --token）

- [ ] **Step 3: 最小实现**

`src/yingdao_rpa_mcp/config.py` 三处修改：
1. `Config` dataclass 加字段（放 `output_dir` 之后）：
```python
    token: str | None = None          # streamable-http 静态 Bearer token；None=无鉴权
```
2. `_env_convs()` 的映射 dict 加一行：
```python
        "TOKEN": ("token", str),
```
3. `_build_parser()` 加参数（放 `--output-dir` 之后）：
```python
    parser.add_argument("--token", default=None, help="streamable-http 静态 Bearer token（None=无鉴权）")
```
（toml 层：`_ALLOWED_KEYS` 加 `"token"` 即自动透传，无需转换器。）

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/pytest tests/test_config.py -q && .venv/bin/pytest -q`
Expected: test_config 22 passed；全套件 87 passed（83+4）

- [ ] **Step 5: Commit**

```bash
git add src/yingdao_rpa_mcp/config.py tests/test_config.py
git commit -m "feat: 配置新增 token 字段（env/CLI/toml 三入口，None=无鉴权）"
```

---

### Task 2: server.py 接线 StaticTokenVerifier

**Files:**
- Modify: `src/yingdao_rpa_mcp/server.py`（`build_server` 内 `mcp = FastMCP(...)` 处）
- Create: `tests/test_server_auth.py`

- [ ] **Step 1: 写失败测试**

`tests/test_server_auth.py`:
```python
"""协议级鉴权测试：asgi_client 走完整 HTTP 栈，401/200 均在握手期体现。

fastmcp 4.x 实测行为（控制器 2026-09-02 探针）：无/错 token 时客户端握手抛
mcp.shared.exceptions.MCPError（服务端 401，code -32603）；带正确 token 正常。
"""
import pytest
from fastmcp import Client
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


def test_http_rejects_missing_token():
    with pytest.raises(MCPError):
        async with asgi_client(_server_with_token()) as client:
            client  # 握手期即 401，走不到这里


def test_http_rejects_wrong_token():
    with pytest.raises(MCPError):
        async with asgi_client(
            _server_with_token(), headers={"Authorization": "Bearer wrong"}
        ) as client:
            client


def test_http_accepts_valid_token():
    async with asgi_client(
        _server_with_token(), headers={"Authorization": "Bearer test-token-123"}
    ) as client:
        data = (await client.call_tool("list_robots", {})).data
    assert data["mock"] is True
    assert len(data["robots"]) >= 3
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_server_auth.py -v`
Expected: `test_token_sets_verifier` / 两个 reject / accept 共 4 FAIL（当前 token 不接线）；`test_no_token_sets_auth_none` 可能即绿（FastMCP 默认 auth=None）

- [ ] **Step 3: 最小实现**

`src/yingdao_rpa_mcp/server.py`：
1. import 区加：
```python
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
```
2. `build_server` 中 `mcp = FastMCP("yingdao-rpa-mcp")` 改为：
```python
    auth = None
    if config.token:
        auth = StaticTokenVerifier(tokens={config.token: {"client_id": "yingdao-rpa-mcp-client"}})
    mcp = FastMCP("yingdao-rpa-mcp", auth=auth)
```
（模块 docstring 的铁律清单补一行：`- token 经 StaticTokenVerifier 静态校验；None=无鉴权（stdio 场景默认）`）

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/pytest tests/test_server_auth.py -v && .venv/bin/pytest -q`
Expected: 5 passed；全套件 92 passed（87+5）。**注意**：既有进程内 `Client(server)` 测试走内存传输，不经 HTTP 中间件，不受 token 影响——若出现失败，检查是否误改了 `build_server` 签名。

- [ ] **Step 5: Commit**

```bash
git add src/yingdao_rpa_mcp/server.py tests/test_server_auth.py
git commit -m "feat: streamable-http 静态 token 鉴权（StaticTokenVerifier，None=无鉴权）"
```

---

### Task 3: Dockerfile 与 .dockerignore

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

- [ ] **Step 1: 写 Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["python", "-m", "yingdao_rpa_mcp", "--mock", "--transport", "http", "--host", "0.0.0.0", "--port", "8000"]
```
（CMD 默认 mock+http——L2 服务器部署形态；token 经环境变量 `YINGDAO_MCP_TOKEN` 注入，config 的 env 层自动读取。）

- [ ] **Step 2: 写 .dockerignore**

```
.venv/
venv/
.git/
.scratch/
tests/
docs/
examples/
__pycache__/
*.py[cod]
.ruff_cache/
.pytest_cache/
.env
```

- [ ] **Step 3: 校验与提交**

```bash
.venv/bin/pytest -q          # 92 passed（Dockerfile 不影响套件）
.venv/bin/ruff check .
git add Dockerfile .dockerignore
git commit -m "feat: 容器化部署载体（python:3.12-slim，默认 mock+http）"
```

---

### Task 4: 代码上服务器（git archive）并构建镜像

**Files:** 无仓库改动（纯运维步骤，产物在服务器）

- [ ] **Step 1: git archive 打包当前 HEAD 上传并解包**

```bash
cd "/mnt/d/CODE/project/yingdao-rpa-mcp"
ssh root@<你的服务器IP> "mkdir -p /opt/yingdao-rpa-mcp"
git archive HEAD | ssh root@<你的服务器IP> "tar -x -C /opt/yingdao-rpa-mcp"
ssh root@<你的服务器IP> "ls /opt/yingdao-rpa-mcp/Dockerfile /opt/yingdao-rpa-mcp/src/yingdao_rpa_mcp/server.py"
```
Expected: 两个路径都列出。

- [ ] **Step 2: 服务器端生成 token .env（幂等，umask 077）**

```bash
ssh root@<你的服务器IP> 'cd /opt/yingdao-rpa-mcp && if [ ! -f .env ]; then umask 077 && echo "YINGDAO_MCP_TOKEN=$(openssl rand -hex 24)" > .env; fi && wc -c .env'
```
Expected: 约 57 字节（`YINGDAO_MCP_TOKEN=` + 48 hex + 换行）。**不要 cat 出 token 内容到会话日志。**

- [ ] **Step 3: 服务器端构建镜像**

```bash
ssh root@<你的服务器IP> "cd /opt/yingdao-rpa-mcp && docker build -t yingdao-rpa-mcp:0.1 . 2>&1 | tail -3"
```
Expected: `naming to docker.io/library/yingdao-rpa-mcp:0.1`（或等价成功输出）。

---

### Task 5: 容器运行与网络接线验证

**Files:** 无仓库改动

- [ ] **Step 1: 运行容器（加入 cow_default 网络，env 注入 token 与 mock）**

```bash
ssh root@<你的服务器IP> 'docker rm -f yingdao-rpa-mcp 2>/dev/null; cd /opt/yingdao-rpa-mcp && docker run -d --name yingdao-rpa-mcp --restart unless-stopped --network cow_default --env-file .env -e YINGDAO_MCP_MOCK=1 -p 127.0.0.1:8808:8000 yingdao-rpa-mcp:0.1 && sleep 3 && docker logs yingdao-rpa-mcp 2>&1 | tail -5'
```
Expected: 容器 ID 输出；日志显示 uvicorn 监听 0.0.0.0:8000（`Uvicorn running on http://0.0.0.0:8000`）。`-p 127.0.0.1:8808` 仅供宿主机调试，公网不可达。

- [ ] **Step 2: 服务器端 401/200 探针（经宿主机映射口）**

```bash
ssh root@<你的服务器IP> 'python3 - <<PYEOF
import urllib.request, urllib.error
def probe(headers):
    req = urllib.request.Request("http://127.0.0.1:8808/mcp", method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
print("no-token:", probe({}))
print("bad-token:", probe({"Authorization": "Bearer wrong"}))
PYEOF'
```
Expected: `no-token: 401`、`bad-token: 401`。

- [ ] **Step 3: 服务器端带 token 200 验证（token 从 .env 读取，不回显）**

```bash
ssh root@<你的服务器IP> 'cd /opt/yingdao-rpa-mcp && TOKEN=$(cut -d= -f2 .env) && python3 - "$TOKEN" <<PYEOF
import json, sys, urllib.request
token = sys.argv[1]
body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-03-26", "capabilities": {},
    "clientInfo": {"name": "probe", "version": "0"}}}).encode()
req = urllib.request.Request("http://127.0.0.1:8808/mcp", data=body, method="POST",
                             headers={"Content-Type": "application/json",
                                      "Accept": "application/json, text/event-stream",
                                      "Authorization": "Bearer " + token})
with urllib.request.urlopen(req, timeout=5) as r:
    print("with-token:", r.status)
PYEOF'
```
Expected: `with-token: 200`。

---

### Task 6: 闷闷 mcp.json 接线并重启 cow

**Files:** 无仓库改动（改服务器上的 `/opt/cow/cow/mcp.json`）

- [ ] **Step 1: 备份现有 mcp.json**

```bash
ssh root@<你的服务器IP> "cp /opt/cow/cow/mcp.json /opt/cow/cow/mcp.json.bak-$(date +%Y%m%d%H%M%S) && ls /opt/cow/cow/mcp.json.bak-*"
```
Expected: 列出备份文件名。

- [ ] **Step 2: 服务器端注入 yingdao-rpa-mcp 条目（token 不经过会话日志）**

```bash
ssh root@<你的服务器IP> 'cd /opt/yingdao-rpa-mcp && TOKEN=$(cut -d= -f2 .env) && docker exec chatgpt-on-wechat python3 - "$TOKEN" <<PYEOF
import json, sys
path = "/home/agent/cow/mcp.json"
with open(path, encoding="utf-8") as f:
    cfg = json.load(f)
cfg["mcpServers"]["yingdao-rpa-mcp"] = {
    "type": "streamable-http",
    "url": "http://yingdao-rpa-mcp:8000/mcp",
    "headers": {"Authorization": "Bearer " + sys.argv[1]},
    "timeout": 300,
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
print("servers:", sorted(cfg["mcpServers"]))
PYEOF'
```
Expected: `servers: ['context7', 'yingdao-rpa-mcp']`（context7 原样保留）。URL 用容器名——同网络 DNS 解析。

- [ ] **Step 3: 重启 cow 并验证 MCP 初始化日志**

```bash
ssh root@<你的服务器IP> "docker restart chatgpt-on-wechat && sleep 25 && docker logs --since 1m chatgpt-on-wechat 2>&1 | grep -i mcp | tail -8"
```
Expected: 出现 `[MCP] Server 'yingdao-rpa-mcp' initialized successfully`（且无 failed 字样）。若失败：`docker logs chatgpt-on-wechat 2>&1 | grep -iA3 'yingdao'` 排查（常见：网络未通、token 不匹配、路径错）。

- [ ] **Step 4: 容器到容器连通性验证（闷闷视角）**

```bash
ssh root@<你的服务器IP> 'docker exec chatgpt-on-wechat python3 - <<PYEOF
import urllib.request, urllib.error
req = urllib.request.Request("http://yingdao-rpa-mcp:8000/mcp", method="POST",
                             headers={"Content-Type": "application/json"})
try:
    urllib.request.urlopen(req, timeout=5)
    print("unexpected 2xx")
except urllib.error.HTTPError as e:
    print("reachable, status:", e.code)  # 401 = 网络通、鉴权生效
PYEOF'
```
Expected: `reachable, status: 401`（无 token 探测即证明 DNS 通、端口通、鉴权在工作）。

---

### Task 7: 微信人工验收与记录

**Files:**
- Modify: `.scratch/mvp-v01/spec.md`（Comments 追加验收记录）

- [ ] **Step 1: 用户微信验收（人工，需要用户参与）**

请用户在微信对闷闷说：**「列出我的影刀机器人」**
Expected: 闷闷通过 yingdao-rpa-mcp 工具返回 3 个演示机器人（演示-数据采集/报表生成/文件整理机器人），并在回答中体现这是演示数据。
备用话术：「跑一下演示-报表生成机器人」「影刀机器人什么状态」。

- [ ] **Step 2: 记录验收结果**

验收通过后在 `.scratch/mvp-v01/spec.md` 的 `## Comments` 追加：
```markdown
- 2026-09-02 L2 验收：服务器容器（cow_default 网络 + 静态 token）部署成功；闷闷 mcp.json 接线；微信真机验收通过/未通过（结果与现象记录于此）。遗留：真实影刀接入属 L3。
```

- [ ] **Step 3: 提交记录**

```bash
git add .scratch/mvp-v01/spec.md
git commit -m "docs: L2 微信验收记录"
```
（`.scratch/` 在 .gitignore 中——此命令预期无实际入库；若 git 报 nothing to commit，跳过即可，记录已存在于工作区。）

---

## Self-Review 记录（写计划时已核）

1. **Spec 覆盖**：story 15 token 鉴权（Task 1/2）；spec"远程 streamable-http + 部署形态"（Task 3-5）；"闷闷联调/微信 mock 验收"（Task 6/7，对应执行阶梯 L2）。Out of Scope 未越界（无 Tailscale/真机/README）。spec"绑定地址可控"（story 19）：容器内 0.0.0.0（bridge 内）+ 宿主 127.0.0.1 映射，公网不可达——已满足语义。
2. **占位符扫描**：无 TBD/TODO；token 为运行时生成秘密，全部命令为"服务器端自生成/自读取"形态，不出现字面 token。Task 3 Step 2 的笔误说明行已在正文中明确"实际文件不要这行"。
3. **类型一致性**：`config.token: str | None`（Task 1）→ `server.py` `config.token` 判断（Task 2）→ 容器 env `YINGDAO_MCP_TOKEN`（Task 5，env 层 Task 4 已有约定 `YINGDAO_MCP_` 前缀）；`build_server` 签名未变；mcp.json 键名与 CowAgent 实测格式逐字对齐。
