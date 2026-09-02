# 远程接入指南：Tailscale 组网，让云上的 AI 助手操控家里的影刀

适用场景：AI 助手跑在云服务器上（比如微信 AI 助手），影刀装在**家里/办公室的 Windows PC** 上。
两边不在同一局域网，又不想把影刀控制端暴露到公网——用 Tailscale 组一个私有网络。

> 全程不需要公网开放任何端口：PC 网关只对 Tailscale 网段（100.64.0.0/10）可达。

## 前置条件

- 云服务器：任意 Linux（本方案在阿里云 2C2G 上验证），有 Docker 则更省心（无 Docker 见文末）
- Windows PC：装有影刀社区版 + Python 3.10+（没有也没关系，安装脚本会用 winget 引导）
- 一台能开网页的浏览器（授权用）

## 步骤一：两端安装 Tailscale

**云服务器（Linux）：**

```bash
curl -fsSL https://tailscale.com/install.sh | sh
nohup tailscale up > /tmp/ts-up.log 2>&1 &
cat /tmp/ts-up.log   # 打印形如 https://login.tailscale.com/a/xxxx 的授权链接
```

浏览器打开授权链接，登录并 Connect（任意账号均可）。

**Windows PC：** 到 <https://tailscale.com/download/windows> 下载安装，
用**同一个账号**登录托盘图标，勾选开机自启。

## 步骤二：⚠️ 必做的 DNS 修复（血泪坑）

Tailscale 在 Linux 端默认 `accept-dns=true`，会**劫持宿主机 `/etc/resolv.conf`**
（指向 100.100.100.100）。它的 MagicDNS 只转发 tailnet 内部名字，**公网域名解析会全部失败**——
表现为：微信收不到消息、容器/系统解析外网域名报 `Temporary failure in name resolution`。

我们连 PC 用的是裸 IP（100.x.y.z），不需要 MagicDNS。**关掉它：**

```bash
tailscale set --accept-dns=false
cat /etc/resolv.conf   # 应还原为你的正常 DNS（如云厂商内网 DNS）
```

如果你用 Docker 跑 AI 助手，**重启一次容器**让它的 resolv.conf 刷新：

```bash
docker restart <你的AI助手容器名>
```

## 步骤三：PC 上一键安装 yingdao-rpa-mcp

把本仓库放到 PC（如 `D:\yingdao-RPA-mcp\`），**管理员 PowerShell** 执行：

```powershell
cd D:\yingdao-RPA-mcp\scripts
Set-ExecutionPolicy -Scope Process Bypass -Force
.\install-windows.ps1
```

脚本会：探测/引导 Python → 创建虚拟环境并安装 → 生成 token（仓库目录 `.env`）→
创建**仅放行 Tailscale 网段**的防火墙规则 → 注册登录自启计划任务 → 启动并自检（预期 401）。

> 管理员权限用于防火墙与计划任务；服务本身以你的**用户会话**运行
> （优雅停止依赖键盘事件与影刀桌面会话，这是设计使然而非缺陷）。

## 步骤四：连通验证 + 配置 AI 助手

```bash
# 云服务器上：确认能看到 PC 节点
tailscale status
# 连通探针：401 = 隧道通、服务在跑、鉴权生效
python3 - <<'PY'
import urllib.request, urllib.error
req = urllib.request.Request('http://<PC的Tailscale IP>:8000/mcp', method='POST',
                             headers={'Content-Type': 'application/json'})
try:
    urllib.request.urlopen(req, timeout=8); print('unexpected 2xx')
except urllib.error.HTTPError as ex:
    print('reachable, status:', ex.code)   # 期望 401
except Exception as ex:
    print('unreachable:', ex)
PY
```

然后把 token 与地址填进 AI 助手的 MCP 配置（见 [../examples/mcp.cow-assistant.json](../examples/mcp.cow-assistant.json)），
重启 AI 助手即可。之后在微信/客户端里说「列出我的影刀机器人」验收。

## 步骤五：PC 开机自启说明

安装脚本已注册 Windows 计划任务 `YingDaoRpaMcp`（**登录时**自启）。为什么是登录时而非开机时：
优雅停止依赖键盘事件、启动依赖影刀桌面会话——这两者都要求**用户桌面会话**。
即：PC 重启后你登录进桌面，网关自动随登录拉起，全程无需手动操作。

## 常见问题

| 现象 | 原因与处理 |
|---|---|
| 公网域名解析失败、AI 助手失联 | 步骤二的 `accept-dns` 坑，执行 `tailscale set --accept-dns=false` 并重启相关容器 |
| 探针超时而非 401 | PC 网关没起（看仓库目录 `server.err.log`）或防火墙规则未创建（重跑安装脚本，需管理员） |
| AI 侧报 `404 Session not found` | 网关进程在 AI 助手两次调用之间被重启过；当前版本已内置 stateless-http 模式，若你在旧版本遇到，重启 AI 助手即可恢复 |
| 启动成功却报 launched:false | 机器人是瞬时任务、影刀异步刷日志晚于验证窗口；v0.1.0 起已内置重试，若仍出现请提 issue 附 `tail_log` 输出 |
