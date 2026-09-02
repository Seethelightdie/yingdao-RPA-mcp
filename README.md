<div align="center">

# yingdao-RPA-mcp

**把影刀（ShadowBot）社区版机器人变成 AI 助手里的"原生工具"——
微信里说一句话，就能列出、启动、停止你电脑上的 RPA 流程。**

[![CI](https://github.com/Seethelightdie/yingdao-RPA-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/Seethelightdie/yingdao-RPA-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Platform: Windows](https://img.shields.io/badge/影刀-社区版-green.svg)](https://www.yingdao.com/)

English TL;DR: An MCP (Model Context Protocol) server that exposes Yingdao/ShadowBot
**Community Edition** RPA robots to any AI client. Local `stdio` + remote `streamable-http`
(Tailscale-friendly) with token auth, a built-in Mock mode, graceful-stop-only design
(never kill processes), and 94 cross-platform tests. MIT licensed, unofficial, community-driven.

</div>

---

## 为什么做这个

影刀社区版没有官方 API，机器人只能靠人点界面启动。已有的民间方案（见[致谢](#-致谢)）解决了
"远程一键启动"，但接到 AI 助手上还有四道坎：**协议不对口**（AI 助手说 MCP）、**跑完没下文**（拿不到结构化结果）、
**停止不可靠**（杀进程会烂尾）、**远程不安全**（裸端口）。

本项目把影刀社区版的四条"民间侦察通道"封装成 5 个标准 MCP 工具，在 52 台真实机器人的环境里、
通过微信 AI 助手完成了端到端验收。

## 功能特性

- 🔧 **5 个 MCP 工具**：`list_robots` 列出 / `run_robot` 启动（支持中文传参、产出文件回收）/
  `get_status` 三层日志验证 / `stop_robot` 优雅停止 / `tail_log` 排障
- 🔌 **双传输**：本地 `stdio`（Claude Desktop 即插即用）+ 远程 `streamable-http`（Tailscale 组网跨网操控）
- 🔐 **安全边界**：静态 Bearer token、绑定地址可控、stateless-http（网关重启对客户端透明）、
  Windows 防火墙仅放行 Tailscale 网段
- 🧪 **Mock 模式**：没有 Windows / 没装影刀也能体验全部工具，同时是 94 个自动化测试的替身
- 🛑 **只优雅停止，永不杀进程**：`keybd_event` 发送 Ctrl+Alt+Q（工具描述内置全局停止警告，
  AI 会先向你确认）
- 🇨🇳 **中文友好**：机器人名/传参值支持中文原样，错误信息统一"code + 中文说明 + 下一步提示"
- 📦 **Windows 一键安装**：一条命令完成 Python 探测、虚拟环境、token、防火墙、开机自启、自检

## 5 个工具一览

| 工具 | 作用 |
|---|---|
| `list_robots` | 扫描影刀用户目录，返回 uuid/名称/版本/描述/路径（按修改时间排序） |
| `run_robot` | 启动机器人，支持 `key=value` 传参（值支持中文）；可指定产出目录，返回运行期间新增的文件 |
| `get_status` | 解析影刀当日日志 + 进程存活检测，返回 运行中/已退出/未知 与证据链 |
| `stop_robot` | 发送 Ctrl+Alt+Q 优雅停止（⚠️ 全局生效——会停掉**所有**运行中的机器人，工具描述已强制警告） |
| `tail_log` | 读取影刀当日日志尾部，排障用 |

## 快速开始

### 前置条件

- 影刀社区版已安装（[官网](https://www.yingdao.com/)）
- Python 3.10+（仅本地 stdio / 手动运行需要；一键安装脚本会自动引导）
- 一个支持 MCP 的 AI 客户端（Claude Desktop、微信 AI 助手等）

### 形态一：Mock 模式（先体验，30 秒）

任何系统（含 Linux/macOS）都能跑，不需要影刀：

```bash
pip install -e .
python -m yingdao_rpa_mcp --mock        # stdio，接到任意 MCP 客户端
```

MCP Inspector 里看效果：

```bash
npx @modelcontextprotocol/inspector python -m yingdao_rpa_mcp --mock
```

你会看到 3 个演示机器人，所有返回都带 `"mock": true` 标识。

### 形态二：本机 AI 客户端（Claude Desktop + 真实影刀，stdio）

Claude Desktop 配置文件（`claude_desktop_config.json`）中加入：

```json
{
  "mcpServers": {
    "yingdao-rpa-mcp": {
      "command": "python",
      "args": ["-m", "yingdao_rpa_mcp"]
    }
  }
}
```

重启 Claude Desktop，然后对它说："列出我的影刀机器人"。
（完整样例见 [examples/mcp.claude-desktop.json](examples/mcp.claude-desktop.json)）

### 形态三：远程 AI 助手（Tailscale + token，http）——微信操控家里的影刀

AI 助手在云服务器、影刀在你家 PC？两步：

1. **PC 上一键安装**（管理员 PowerShell，在仓库目录）：
   ```powershell
   .\scripts\install-windows.ps1
   ```
   自动完成：Python 探测 → 虚拟环境 → token 生成 → **防火墙仅放行 Tailscale 网段** → 登录自启 → 401 自检
2. **组网与接线**：按 [examples/tailscale-setup.md](examples/tailscale-setup.md) 走（含一个必踩的 DNS 坑的解法）

之后在微信里说"列出我的影刀机器人"即可。完整配置样例见
[examples/mcp.cow-assistant.json](examples/mcp.cow-assistant.json)。

## 配置参考

优先级：CLI 参数 > 环境变量（前缀 `YINGDAO_MCP_`）> `config.toml`。
全量带注释样例见 [examples/config.toml](examples/config.toml)，常用项：

| 配置 | 默认 | 说明 |
|---|---|---|
| `mock` | `false` | Mock 演示模式 |
| `transport` | `stdio` | `stdio` / `http` |
| `host` / `port` | `127.0.0.1` / `8000` | http 监听地址（远程接入建议 `0.0.0.0` + 防火墙限定来源） |
| `token` | 无 | http 模式建议必配（静态 Bearer）；stdio 无需 |
| `wait_seconds` | 真实 5 / mock 0 | 启动/停止后的验证等待 |
| `users_dir` / `log_dir` | 自动探测 | 影刀目录覆盖（多账号/自定义安装位置时使用） |
| `output_dir` | 无 | 机器人产出文件的默认目录 |

## 架构

```
MCP 工具层（FastMCP：协议、参数校验、等待编排、错误语义）
        │
        ▼
ShadowBotGateway   ←—— 唯一架构接缝（scan / launch / status / stop / tail_log）
        │
   ├── MockGateway      产品功能（无 Windows 体验）兼全量自动化测试替身
   └── WindowsGateway   真实侦察通道（目录扫描 / URL Scheme / 日志三层验证 / keybd_event）
```

设计细节见 [SPEC.md](SPEC.md)；94 个自动化测试全部基于 Mock，任何 OS 可跑（CI 双矩阵验证）。

## 踩坑 FAQ（全部来自真实部署）

<details>
<summary><b>装完 Tailscale 后，服务器/容器解析不了公网域名、AI 助手失联</b></summary>

Tailscale Linux 端默认 `accept-dns=true`，会劫持 `/etc/resolv.conf`（指向 100.100.100.100），
而 MagicDNS 不转发公网域名。解法（我们用裸 IP 连 PC，不需要 MagicDNS）：

```bash
tailscale set --accept-dns=false
# 用 Docker 跑 AI 助手的话，重启一次容器刷新 resolv.conf
```
</details>

<details>
<summary><b>机器人明明跑成功了，却返回 launched:false</b></summary>

瞬时任务（几秒内跑完）的日志由影刀<b>异步落盘</b>，可能晚于验证窗口。v0.1.0 起已内置有界重试；
若仍出现，可用 `tail_log` / `get_status` 二次确认——就像下面这个真实案例：

> 启动检测窗口没赶上（launched: false），但日志显示 14:24:40 启动、14:24:41 正常退出（exitCode 0）。
</details>

<details>
<summary><b>AI 侧报 404 Session not found</b></summary>

网关进程在 AI 客户端两次调用之间被重启过（比如 PC 重启后计划任务拉起了新进程）。
当前版本已默认启用 <b>stateless-http</b>（无会话状态，重启透明）；旧版本遇到时重启 AI 客户端即可。
</details>

<details>
<summary><b>Windows 脚本报一串乱码解析错误</b></summary>

Windows PowerShell 5.1 对无 BOM 的 UTF-8 脚本按 GBK 解码。仓库内的脚本已带 BOM；
如果你自己改编过脚本，请确保以"UTF-8 with BOM"保存。
</details>

<details>
<summary><b>为什么停止机器人必须用 Ctrl+Alt+Q，不能杀进程？</b></summary>

杀进程会让影刀内部状态机走不完，产出和日志烂尾，甚至不可恢复。Ctrl+Alt+Q 是影刀的全局停止快捷键，
必须用 `keybd_event` 发送（影刀靠全局键盘钩子监听，`SendInput` 触发不了）。
⚠️ 它是<b>全局</b>停止——会停掉所有运行中的机器人，AI 调用前必须征得你确认。
</details>

## 与原仓库的关系

核心机制全部继承自 [yingdao_robot_run_api_manage_and_skill](https://github.com/HnBigVolibear/yingdao_robot_run_api_manage_and_skill)，
本项目是其 **MCP 化继任者**。继承/补齐逐项对照见 [docs/COMPARISON.md](docs/COMPARISON.md)——
如果你只想要一个带界面的桌面工具 + 局域网 REST，原仓库仍然是不二之选；想让 AI 原生操控影刀，用本项目。

## 🙏 致谢

本项目的核心机制并非发明，而是**继承**自湖南大白熊的
[yingdao_robot_run_api_manage_and_skill](https://github.com/HnBigVolibear/yingdao_robot_run_api_manage_and_skill)（MIT，含
[skills 技术文档](https://github.com/HnBigVolibear/yingdao_robot_run_api_manage_and_skill/tree/main/skills)）：

- **「侦察代替 API」哲学**——不走企业版接口，用民间通道给社区版赋能
- **机器人发现**：`users\<ID>\apps` 目录扫描（4 个候选 package 路径、`_temp` 跳过、mtime 排序）
- **启动与传参**：`shadowbot:Run?robot-uuid=…&key=value` URL Scheme（含"仅编码 `& = # %` 空格、中文原样"的实测口径）
- **状态验证**：影刀主日志解析（TaskManager / engine running / exited LIFO 配对）+ `GetExitCodeProcess` 存活检测
- **优雅停止**：`keybd_event` 发送 Ctrl+Alt+Q（以及"SendInput 无法触发影刀全局钩子"的实测结论），
  还有"**严禁杀进程**"这条铁律

没有前人踩坑，就没有这个项目。如果你因本项目受益，请也给
[原仓库](https://github.com/HnBigVolibear/yingdao_robot_run_api_manage_and_skill) 一个 Star。

## ⚠️ 免责声明

- 本项目为个人开源作品，与影刀官方（杭州分叉智能科技有限公司）**无任何关联**；
  "影刀 / ShadowBot"商标归其权利人所有
- 本项目使用未公开接口（URL Scheme、本地日志、全局快捷键）自动化操作影刀客户端，
  这些通道可能随影刀版本更新失效，使用风险自担
- 仅供学习交流使用；`stop_robot` 会全局停止所有运行中的机器人，生产环境请自行评估
- 本项目继承的侦察机制同样继承原仓库的[免责立场](https://github.com/HnBigVolibear/yingdao_robot_run_api_manage_and_skill#%EF%B8%8F-免责声明)

## License

[MIT](LICENSE) © 继承自 HnBigVolibear（原仓库）与 Seethelightdie（本项目）的贡献者
