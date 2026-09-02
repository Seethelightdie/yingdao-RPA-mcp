# yingdao-rpa-mcp L3 实现计划（真机接入：Windows PC + Tailscale + 微信真机验收）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用户的 Windows PC 上以真实网关运行 yingdao-rpa-mcp，经 Tailscale 让服务器上的闷闷直达，微信里操控**真**影刀机器人（列/跑/传参/状态/停止）。

**Architecture:** PC 端复用同仓库代码（http 绑 0.0.0.0 + token + Windows 防火墙仅放行 Tailscale CGNAT 段 100.64.0.0/10），登录时计划任务自启（**必须用户桌面会话**——keybd_event 与 URL Scheme 离开用户桌面即失效）。Tailscale 组网后服务器 cow 直达 PC。闷闷 mcp.json **切换式**：mock 条目替换为 PC 条目（两个 server 暴露同名工具会冲突），mock 容器保留可回切。AGENT.md 追加影刀工具守则（stop 全局警告是破坏性动作，LLM 必须先确认）。

**Tech Stack:** PowerShell 5.1+（安装/启动/卸载脚本）、Windows schtasks（ONLOGON）、NetSecurity 防火墙规则、Tailscale（服务器 headless `tailscale up` + PC GUI）、CowAgent mcp_client（已核实的 streamable-http + headers 格式）。

**侦察事实（2026-09-02 实测）：**
- 服务器无 tailscale（本计划 Task 2 安装）；cow mcp.json 现条目 `context7` + `yingdao-rpa-mcp`（指向服务器容器 mock）
- L1/L2 已交付：真实网关代码全绿（92 测试）、`WindowsGateway` 依赖注入、stdio/http 双传输、token 鉴权
- **本地 WSL 无 docker、无 Windows**——PowerShell 脚本无法本地执行，正确性 = 静态审查 + Task 3 用户真机执行验证（AGENTS.md 红线 6 的"动作后 5 秒"等已在 L1 测试钉死）
- keybd_event/URL Scheme/影刀目录扫描等 Windows 原语的自动化测试按 spec 永不进 CI——真机验收清单就是它们的"测试"

**范围：** L3 = 组网 + PC 一键安装 + mcp.json 切换 + 真机验收。**不在本计划**：P4（README/LICENSE/examples/CI）、P5（GitHub 发布）、Tailscale 多机组网扩展、嵌入式 Python 全自动安装（winget 引导即可，影刀用户装 Python 门槛低）。

**铁律：** PC token 由 PC 端生成、经用户手动 stdin 管道注入服务器 `pc.env`（不进 shell history、不进会话日志）；mcp.json 修改前备份；验收涉及**真机器人**——stop 是全局停止，验收步骤必须先确认再执行。

---

## File Structure（本计划涉及的文件）

```
/
├── scripts/
│   ├── install-windows.ps1     # 新建：一键安装（python 探测/winget 引导、venv、token、防火墙、计划任务、自检）
│   ├── run-server.ps1          # 新建：启动器（读 .env → 真实网关 http，输出追加 server.log）
│   └── uninstall-windows.ps1   # 新建：对称卸载（停任务/删规则；代码与 .env 保留）
└── docs/superpowers/plans/…l3.md   # 本计划
```

服务器侧（不入库）：Tailscale 安装、`/opt/yingdao-rpa-mcp/pc.env`（PC token）、`/opt/cow/cow/mcp.json` 切换、`/opt/cow/cow/AGENT.md` 追加守则。

---

### Task 1: Windows 三脚本（安装/启动/卸载）

**Files:**
- Create: `scripts/run-server.ps1`
- Create: `scripts/install-windows.ps1`
- Create: `scripts/uninstall-windows.ps1`

**本任务无本地可跑测试**（无 Windows 环境）——正确性保障 = ①双实现者+双审的静态审查 ②Task 3 用户真机执行。脚本设计目标：幂等（可重复执行）、失败信息可行动（中文提示下一步）。

- [ ] **Step 1: 写启动器 run-server.ps1**

```powershell
# run-server.ps1 —— yingdao-rpa-mcp 启动器（计划任务调用；真实网关，无 --mock）
$ErrorActionPreference = "Stop"
$repo = $PSScriptRoot | Split-Path
Set-Location $repo

# 读 .env（Windows 无自动 .env 机制；当前仅 token 一项）
Get-Content "$repo\.env" | ForEach-Object {
    if ($_ -match "^YINGDAO_MCP_TOKEN=(.+)$") { $env:YINGDAO_MCP_TOKEN = $Matches[1] }
}

# 真实网关（Windows + 影刀本机）；输出全部追加到 server.log 供排障
& "$repo\.venv\Scripts\python.exe" -m yingdao_rpa_mcp --transport http --host 0.0.0.0 --port 8000 *>> "$repo\server.log"
```

- [ ] **Step 2: 写安装脚本 install-windows.ps1**

```powershell
#Requires -RunAsAdministrator
# install-windows.ps1 —— yingdao-rpa-mcp Windows 一键安装（幂等）
# 前提：本目录所在文件夹是仓库根（含 src/、pyproject.toml、scripts/）
# 需要管理员权限（防火墙与计划任务）；安装后服务以"当前用户登录会话"运行（keybd_event/URL Scheme 必需）
$ErrorActionPreference = "Stop"
$repo = $PSScriptRoot | Split-Path
Set-Location $repo
Write-Host "== yingdao-rpa-mcp 安装开始：$repo =="

# --- 1. 探测 Python >= 3.10；缺失则 winget 引导 ---
$py = $null
foreach ($cand in @("py", "python", "python3")) {
    try {
        $v = & $cand -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($v -and [version]$v -ge [version]"3.10") { $py = $cand; break }
    } catch { }
}
if (-not $py) {
    Write-Host "未找到 Python >= 3.10，尝试 winget 安装 Python 3.12（请在 UAC 弹窗确认）..."
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    $v = & python -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
    if (-not $v -or [version]$v -lt [version]"3.10") {
        Write-Error "Python 3.10+ 仍不可用。请手动安装 Python（勾选 Add to PATH）后重新运行本脚本。"
        exit 1
    }
    $py = "python"
}
Write-Host "Python 就绪：$(& $py -c 'import sys; print(sys.version.split()[0])')"

# --- 2. venv + 安装本包 ---
if (-not (Test-Path "$repo\.venv")) { & $py -m venv "$repo\.venv" }
& "$repo\.venv\Scripts\python.exe" -m pip install --upgrade pip -q
& "$repo\.venv\Scripts\python.exe" -m pip install . -q
& "$repo\.venv\Scripts\python.exe" -c "import yingdao_rpa_mcp; print('installed', yingdao_rpa_mcp.__version__)"

# --- 3. token .env（已存在则保留——重复安装不换锁）---
$envFile = "$repo\.env"
if (-not (Test-Path $envFile)) {
    $token = [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
    Set-Content -Path $envFile -Value "YINGDAO_MCP_TOKEN=$token" -NoNewline
    Write-Host "已生成 token：$envFile（Task 5 需要此值，配置完 Tailscale 后提供给服务器）"
} else {
    Write-Host ".env 已存在，保留现有 token"
}

# --- 4. 防火墙：仅放行 Tailscale 网段访问 8000 ---
$ruleName = "yingdao-rpa-mcp (Tailscale only)"
if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP -LocalPort 8000 `
        -RemoteAddress 100.64.0.0/10 -Action Allow | Out-Null
    Write-Host "防火墙规则已创建（仅 Tailscale 100.64.0.0/10 可达 8000）"
} else {
    Write-Host "防火墙规则已存在"
}

# --- 5. 计划任务：登录时自启（用户桌面会话内运行）---
$taskName = "YingDaoRpaMcp"
$runScript = "$repo\scripts\run-server.ps1"
schtasks /Create /F /TN $taskName /SC ONLOGON /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$runScript`"" | Out-Null
Write-Host "计划任务 $taskName 已注册（每次登录自启）"

# --- 6. 立即启动并自检（预期无 token 访问得到 401）---
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $runScript
Start-Sleep -Seconds 5
try {
    Invoke-WebRequest -Uri "http://127.0.0.1:8000/mcp" -Method POST -UseBasicParsing -TimeoutSec 5 | Out-Null
    Write-Error "意外的 2xx——无 token 不应通过，请检查 server.log"
} catch {
    $code = $_.Exception.Response.StatusCode.value__
    if ($code -eq 401) { Write-Host "自检通过：服务运行中，鉴权生效（401）" }
    else { Write-Host "自检返回 $code，请查看 $repo\server.log 排障" }
}
Write-Host "== 安装完成。下一步：安装并登录 Tailscale（见 L3 计划 Task 3），然后运行 uninstall 前请勿删除 .env =="
```

- [ ] **Step 3: 写卸载脚本 uninstall-windows.ps1**

```powershell
# uninstall-windows.ps1 —— 对称卸载（代码与 .env 保留；完全清理请手动删除仓库目录）
schtasks /End /TN YingDaoRpaMcp 2>$null
schtasks /Delete /TN YingDaoRpaMcp /F 2>$null
Get-NetFirewallRule -DisplayName "yingdao-rpa-mcp (Tailscale only)" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
Write-Host "已停止服务并移除计划任务与防火墙规则。如需完全清理，手动删除仓库目录（含 .venv 与 .env）。"
```

- [ ] **Step 4: 门禁与提交**

```bash
.venv/bin/pytest -q        # 92 passed（脚本不影响套件）
.venv/bin/ruff check .     # PowerShell 不归 ruff 管，确认无意外
git add scripts/
git commit -m "feat: Windows 一键安装/启动/卸载脚本（登录自启、Tailscale 限定防火墙）"
```

---

### Task 2: 服务器端安装 Tailscale 并获取授权

**Files:** 无仓库改动（服务器运维）

- [ ] **Step 1: 安装 tailscale**

```bash
ssh root@<你的服务器IP> "curl -fsSL https://tailscale.com/install.sh | sh 2>&1 | tail -3 && tailscale version | head -1"
```
Expected: 打印版本号（如 `1.8x.x`）。

- [ ] **Step 2: 后台启动 tailscale up 并取授权 URL**

```bash
ssh root@<你的服务器IP> "nohup tailscale up > /tmp/ts-up.log 2>&1 & sleep 4; cat /tmp/ts-up.log"
```
Expected: 日志含 `https://login.tailscale.com/a/xxxxxxxx` 授权链接。

- [ ] **Step 3: [用户] 浏览器打开授权链接登录一次**

用户用浏览器（任一账号，Google/GitHub/微软均可）打开该链接并授权。**这是全 L3 唯一一次用户授权动作。**

- [ ] **Step 4: 确认入网并记录服务器 100.x IP**

```bash
ssh root@<你的服务器IP> "sleep 3; tailscale status; tailscale ip -4"
```
Expected: status 列出节点；`tailscale ip -4` 打印 `100.x.y.z`（记录为 **服务器 TS IP**）。此时 PC 尚未入网，status 里可能只有服务器自己——正常。

---

### Task 3: [用户] PC 安装 Tailscale + 一键安装脚本

**Files:** 无仓库改动（用户 PC 操作；控制器逐步引导）

- [ ] **Step 1: [用户] 安装 Tailscale Windows 客户端并登录同一账号**

下载：https://tailscale.com/download/windows —— 安装后托盘图标登录（与 Task 2 授权所用**同一账号**），保持开机自启勾选。

- [ ] **Step 2: [用户] 把仓库拷贝到 PC**

方式任选：服务器 `git bundle` / 网盘 / `scp -r`（排除 `.venv`、`.git`、`.scratch`）。示例（在 WSL 执行，`<PC用户名>` 替换）：
```bash
cd <本地仓库上级目录> && tar --exclude='.venv' --exclude='.git' --exclude='.scratch' -czf /tmp/yrm.tgz yingdao-rpa-mcp
scp /tmp/yrm.tgz root@<你的服务器IP>:/tmp/ && ssh root@<你的服务器IP> "ls -la /tmp/yrm.tgz"
# 然后用户在 PC 上用 WinSCP/浏览器方式从服务器取 /tmp/yrm.tgz，解压到如 D:\yingdao-rpa-mcp\
```

- [ ] **Step 3: [用户] 管理员 PowerShell 运行安装脚本**

```powershell
cd D:\yingdao-rpa-mcp\scripts
Set-ExecutionPolicy -Scope Process Bypass -Force
.\install-windows.ps1
```
Expected 逐段输出：Python 就绪（或 winget 装完）→ `installed 0.1.0` → token 生成 → 防火墙规则 → 计划任务 → `自检通过：服务运行中，鉴权生效（401）`。
**排障**：自检非 401 → 看 `D:\yingdao-rpa-mcp\server.log`（最常见：非 Windows 环境 GATEWAY_UNAVAILABLE——必须在真 Windows 上跑；影刀未装不影响启动，只影响后续工具调用）。

- [ ] **Step 4: [用户] 记录两样东西**

1. PC 的 Tailscale IP：托盘 Tailscale 图标 → 右键 → 可见本机 IP（`100.x.y.z`），或 PC 上 `tailscale ip -4`
2. PC token：`D:\yingdao-rpa-mcp\.env` 的值（`YINGDAO_MCP_TOKEN=` 后面那段）
把 PC 的 TS IP 告诉控制器；token 留给 Task 5 注入（见该任务的"无痕注入法"）。

---

### Task 4: 服务器侧连通验证

**Files:** 无仓库改动

- [ ] **Step 1: 服务器确认 PC 节点入网**

```bash
ssh root@<你的服务器IP> "tailscale status"
```
Expected: 两行——服务器与 PC 节点（PC 行有其 100.x IP）。记录 PC TS IP 为 **PC_IP**。

- [ ] **Step 2: 连通探针（401 即全通）**

```bash
ssh root@<你的服务器IP> 'python3 - <<PYEOF
import urllib.request, urllib.error
req = urllib.request.Request("http://<PC_IP>:8000/mcp", method="POST",
                             headers={"Content-Type": "application/json"})
try:
    urllib.request.urlopen(req, timeout=8)
    print("unexpected 2xx")
except urllib.error.HTTPError as e:
    print("reachable, status:", e.code)
except Exception as e:
    print("unreachable:", e)
PYEOF'
```
Expected: `reachable, status: 401`（Tailscale 隧道 + 防火墙规则 + 服务运行三重证明）。`<PC_IP>` 用 Task 3 Step 4 的实际值替换。
若 unreachable：①PC 防火墙规则是否创建（install 输出）②Tailscale 两端在线（`tailscale status`）③PC server 是否运行（PC 上 `tasklist | findstr python`）。

---

### Task 5: mcp.json 切换真实条目 + AGENT.md 守则 + 重启 cow

**Files:** 无仓库改动（服务器 `/opt/cow/cow/mcp.json`、`/opt/cow/cow/AGENT.md`）

- [ ] **Step 1: 备份**

```bash
ssh root@<你的服务器IP> "cp /opt/cow/cow/mcp.json /opt/cow/cow/mcp.json.bak-l3-\$(date +%Y%m%d%H%M%S) && cp /opt/cow/cow/AGENT.md /opt/cow/cow/AGENT.md.bak-l3-\$(date +%Y%m%d%H%M%S) && ls /opt/cow/cow/ | grep bak-l3"
```
Expected: 两个备份文件列出。

- [ ] **Step 2: [用户] PC token 无痕注入服务器 pc.env**

用户在**本机终端**执行（stdin 管道不进 history；粘贴 `.env` 的完整一行后回车 Ctrl-D）：
```bash
ssh root@<你的服务器IP> 'umask 077; cat > /opt/yingdao-rpa-mcp/pc.env && echo written && stat -c %a /opt/yingdao-rpa-mcp/pc.env'
# 此时终端等待输入：粘贴  YINGDAO_MCP_TOKEN=<PC的token值>  然后回车，再按 Ctrl-D
```
Expected: `written` 与 `600`。**不要让 token 出现在任何后续输出。**

- [ ] **Step 3: 切换 mcp.json 条目（服务器端读 pc.env，不回显）**

```bash
ssh root@<你的服务器IP> 'PC_IP=<PC_IP> && docker exec -i chatgpt-on-wechat python3 - "$PC_IP" <<PYEOF
import json, sys
path = "/home/agent/cow/mcp.json"
with open(path, encoding="utf-8") as f:
    cfg = json.load(f)
# 读 PC token：从挂载卷宿主路径读 pc.env（cow-data 挂载不含 /opt/yingdao-rpa-mcp，改为由服务器侧注入）
import sys
token = sys.argv[1] if len(sys.argv) > 1 else ""
PYEOF'
```
⚠️ 上面写法不通——容器看不到宿主 `/opt/yingdao-rpa-mcp/pc.env`。**正确做法（控制器定稿）**：分两步——先在宿主读 token 到变量，再经 argv 传入容器：
```bash
ssh root@<你的服务器IP> 'PC_IP=<PC_IP> && TOKEN=$(cut -d= -f2 /opt/yingdao-rpa-mcp/pc.env) && docker exec chatgpt-on-wechat python3 - "$PC_IP" "$TOKEN" <<PYEOF
import json, sys
pc_ip, token = sys.argv[1], sys.argv[2]
path = "/home/agent/cow/mcp.json"
with open(path, encoding="utf-8") as f:
    cfg = json.load(f)
cfg["mcpServers"]["yingdao-rpa-mcp"] = {
    "type": "streamable-http",
    "url": "http://%s:8000/mcp" % pc_ip,
    "headers": {"Authorization": "Bearer " + token},
    "timeout": 300,
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
print("servers:", sorted(cfg["mcpServers"]))
print("url host:", pc_ip)   # 只打 IP，不打 token
PYEOF'
```
Expected: `servers: ['context7', 'yingdao-rpa-mcp']` 与 `url host: <PC_IP>`（条目名不变——工具集同名替换，mock 容器保留可回切）。heredoc 若被 ssh 吞（L2 Task 6 已遇到），沿用其解法：本地写脚本 → scp 到服务器 /tmp → `ssh root@... 'PC_IP=... TOKEN=$(...) docker exec -i chatgpt-on-wechat python3 - < /tmp/脚本'`。

- [ ] **Step 4: AGENT.md 追加影刀工具守则**

```bash
ssh root@<你的服务器IP> 'cat >> /opt/cow/cow/AGENT.md <<MDEOF

## 影刀机器人工具使用守则（yingdao-rpa-mcp）

- 「列出/找机器人」→ list_robots；名称匹配由你在返回结果中完成，不编造机器人
- 「跑一下 X」→ 先复述机器人名称请用户确认 → run_robot(uuid, params)；params 值支持中文
- run_robot 返回 launched=true 且 state=running → 告知已启动；用户问结果时用 get_status 轮询直到 exited，再汇报 evidence 摘要；output_files 非空时提示可以把文件发给用户
- 「停掉机器人」→ **必须先警告：这会停掉所有正在运行的机器人**，等用户明确确认后才调 stop_robot；stopped=false 时如实说明并建议稍后 get_status 复查
- payload 里 mock=true 表示演示数据；真实环境该字段为 false——汇报时如实区分
- 排障：tail_log 看影刀当日日志尾部
MDEOF
tail -5 /opt/cow/cow/AGENT.md'
```
Expected: 追加成功，tail 可见守则末尾。

- [ ] **Step 5: 重启 cow 并验证**

```bash
ssh root@<你的服务器IP> "docker restart chatgpt-on-wechat && sleep 25 && docker logs --since 2m chatgpt-on-wechat 2>&1 | grep -i mcp | tail -8"
```
Expected: `Server 'yingdao-rpa-mcp' ready — 5 tool(s)`（此时后端已是 PC 真实网关）、`2/2 server(s) ready`。

---

### Task 6: 微信真机验收清单 + 记录

**Files:**
- Modify: `.scratch/mvp-v01/spec.md`（Comments 追加验收记录）

- [ ] **Step 1: [用户] 微信真机验收（逐项，控制器陪同排障）**

准备：PC 上影刀客户端已登录；最好有一个**简单无害的测试机器人**（如"弹窗/写一行日志"流程）用于跑/停验收。逐项执行并把每项结果记下来：
1. **列表**：「列出我的影刀机器人」→ 返回 PC 上**真实**机器人列表（数量与影刀客户端一致，payload mock=false）
2. **启动**：「跑一下 <测试机器人>」→ 确认话术后，PC 影刀客户端实际弹出运行，闷闷报 launched=true
3. **状态**：「影刀机器人什么状态」→ state 与影刀客户端实际一致
4. **停止**：「停掉影刀机器人」→ 闷闷先警告全局停止并等确认 → 执行后影刀实际停止，stopped=true
5. **传参**（若测试机器人支持）：中文 key=value → 影刀收到参数正确
- [ ] **Step 2: 记录与收尾**

```bash
cd <repo>
cat >> .scratch/mvp-v01/spec.md <<'EOF'
- 2026-09-02 L3 真机验收：<逐项结果记录>。Tailscale 组网（服务器 100.x / PC 100.x）；mcp.json 已切换 PC 真实网关（mock 容器保留可回切：把 url 换回 http://yingdao-rpa-mcp:8000/mcp 并恢复旧 token）。执行阶梯 L1✅ L2✅ L3✅，下一步 P4（文档包）。
EOF
git add -A && git commit -m "docs: L3 真机验收记录" || true
```
Expected: 记录落盘（.scratch 不入库属设计约定）。

- [ ] **Step 3: 回切开关（写进记录，供随时使用）**

mock 回切 = 把 mcp.json 条目 url 改回 `http://yingdao-rpa-mcp:8000/mcp`、token 换回 `/opt/yingdao-rpa-mcp/.env` 的值，`docker restart chatgpt-on-wechat`。PC 真机回切 = 再执行 Task 5 Step 3。

---

## Self-Review 记录（写计划时已核）

1. **Spec/阶梯覆盖**：handoff 阶梯 L3 = 一键脚本（嵌入式 python+计划任务自启）✅ Task 1（python 探测+winget 引导替代嵌入式，架构决策已注明理由）+ 计划任务 ONLOGON ✅；Tailscale 服务器端安装+用户授权一次 ✅ Task 2；微信真机验收 ✅ Task 6。spec story 覆盖：真实网关全部工具（L1 已实现）、绑定面可控（防火墙限 CGNAT 段）、安全（token 必配）。
2. **占位符扫描**：`<PC_IP>`/`<PC用户名>` 是用户环境实测值占位（每处出现都标注了来源步骤与替换说明），token 全部走"服务器端/PC 端自生成 + stdin 管道"，零字面秘密——符合"No Placeholders"对运行时秘密的豁免精神且每个步骤可执行。
3. **类型一致性**：`.env` 键名 `YINGDAO_MCP_TOKEN` 与 L1 config env 前缀一致；run-server.ps1 不带 `--mock`（真实网关）；mcp.json 条目名保持 `yingdao-rpa-mcp`（切换式，工具同名替换而非并存——与 CowAgent 单名注册行为一致）；脚本间引用（schtasks TR → run-server.ps1 路径、install → repo 根假设）自洽。
