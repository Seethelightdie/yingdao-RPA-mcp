# SPEC：yingdao-RPA-mcp 设计文档

> 本文是项目的公开设计文档（PRD）。实现进度、验收记录与过程决策见仓库历史与 CHANGELOG。

## 1. 背景与定位

影刀（ShadowBot）**社区版**不提供官方 API，RPA 机器人只能靠人点界面启动，无法接入 AI 助手工作流。
已有的民间方案解决了"远程一键启动"，但在 AI 助手场景存在四个硬伤：

1. **协议不对口**——主流 AI 助手说的是 MCP，不会主动消费 REST 接口；
2. **跑完没下文**——一次性调用，机器人跑完没有结构化结果返回，AI 无法"跑完汇报"；
3. **停止不可靠**——杀进程会让影刀内部状态机走不完，产出和日志烂尾；
4. **远程不安全也不通**——REST 裸露端口，个人用户没有现成的内网穿透 + 鉴权姿势。

本项目是一个 **MCP 服务器**（FastMCP 实现，单进程 Python）：把影刀社区版的四条"民间侦察通道"
封装成标准 MCP 工具，让任何 MCP 客户端（Claude Desktop、微信 AI 助手等）原生操控影刀。

核心机制继承自
[yingdao_robot_run_api_manage_and_skill](https://github.com/HnBigVolibear/yingdao_robot_run_api_manage_and_skill)（MIT），
继承与补齐的逐项对照见 [docs/COMPARISON.md](docs/COMPARISON.md)。

## 2. 非目标

- 不做 GUI（协议即产品）
- 不支持影刀企业版 / 控制台 API
- 不接入具体聊天软件（本仓库只产出结构化结果，聊天侧由 AI 助手配置完成）
- 不保证影刀未来版本不破坏侦察通道（只文档化兼容性与排查指引）

## 3. 架构

```
MCP 工具层（FastMCP：协议、参数校验、等待编排、错误语义）
        │
        ▼
ShadowBotGateway   ←—— 全项目唯一的架构接缝（5 个动作：scan/launch/status/stop/tail_log）
        │
   ├── MockGateway          产品功能（无 Windows 体验/演示）兼全量自动化测试替身
   └── WindowsGateway       真实侦察通道（仅 Windows 生效，依赖全部构造注入）
```

- **测试跑在最高处**：进程内 MCP 客户端 → server（注入 Mock 网关）→ 断言工具契约与错误语义；
- **工具层与 Mock 不得 import 任何 Win32 专属模块**——侦察细节只存在于真实网关内部；
- **双传输**：stdio（本地 AI 客户端即插即用）+ streamable-http（远程，配 Tailscale）。

### 部署形态

| 形态 | 说明 |
|---|---|
| 本机 stdio | AI 客户端与影刀同机（Claude Desktop 直接拉起 server 子进程） |
| 远程 http | 影刀在 PC，AI 助手在云端：PC 跑 http 网关（登录自启）+ Tailscale 组网 + token 鉴权，详见 [examples/tailscale-setup.md](examples/tailscale-setup.md) |

## 4. MCP 工具面契约

错误统一为 `{"error": {"code", "message"(中文), "hint"}}`，工具永不向协议层抛异常；
成功 payload 顶层带 `"mock"` 标识（Mock 数据不得冒充真实数据）。

| 工具 | 契约 |
|---|---|
| `list_robots()` | `[{uuid, name, path, mtime, version, description}]`，按 mtime 降序，`_temp` 目录跳过；名称匹配由客户端 LLM 完成（不提供 search 工具） |
| `run_robot(uuid, params?, output_dir?)` | `{launched, state, evidence, output_files}`；动作后等待验证（真实 5s / mock 0s，可配置），状态未知时有界重试（影刀异步刷日志竞态）；`output_dir` 内运行窗口新增/修改的文件随结果返回 |
| `get_status(uuid?)` | `{state: running\|exited\|unknown, exit_code?, evidence}`；省略 uuid 时汇总当日日志中出现过的全部机器人 |
| `stop_robot()` | `{stopped, running_before, running_after, evidence}`；Ctrl+Alt+Q **全局停止**（影响所有运行中机器人，工具描述强制警告）；无运行中机器人时 `stopped:false` 不谎报 |
| `tail_log(n)` | 当日日志最后 n 行（1-500）；无日志返回空并附 `note` 原因 |

## 5. 四条侦察通道（真实网关，均继承自原仓库的实测结论）

1. **发现**：扫描 `%LOCALAPPDATA%\ShadowBot\users\<ID>\apps`；目录名即 uuid；按序尝试
   `xbot_robot/package.json` → `package.json` → `robot.json` → `config.json`；mtime 取 `xbot_robot` 子目录
2. **启动**：URL Scheme `shadowbot:Run?robot-uuid=<uuid>&<k>=<v>`；参数值仅编码 `& = # %` 空格，
   **中文保持原样**（影刀实测支持）；经 `os.startfile` 触发系统协议解析
3. **状态**：解析 `%LOCALAPPDATA%\ShadowBot\log\YYYYMMDD.log`——
   `[TaskManager] task continue:` 启动行、`xbot engine running, pid:N,engineid:M`、
   `xbot engine exited, ending`（无 PID，按 LIFO 配对）；未退出进程经 `GetExitCodeProcess`（STILL_ACTIVE=259）补判
4. **停止**：`keybd_event` 发送 Ctrl+Alt+Q（按下 Ctrl→Alt→Q，0.1s 后逆序释放）。
   **为什么不是 SendInput**：影刀通过全局键盘钩子监听，SendInput 触发不了，keybd_event 可以。
   **为什么严禁杀进程**：会导致影刀内部状态损坏、数据丢失

## 6. 配置与安全

- 三级覆盖：CLI > 环境变量（`YINGDAO_MCP_*`）> `config.toml`；全字段见 [examples/config.toml](examples/config.toml)
- http 模式：静态 Bearer token（`StaticTokenVerifier`）+ 绑定地址可控；
  推荐与 Tailscale 组网配合，仅暴露给 tailnet（见安全模型：不设公网暴露面）
- **stateless-http**：网关进程/主机重启对客户端透明（无会话状态可失效）
- stdio 模式下 stdout 是协议专用通道，服务日志一律走 stderr

## 7. 测试策略

- 只测外部行为：94 个自动化测试（进程内 MCP 客户端 + Mock 网关）在任意 OS 全绿，CI 双矩阵（ubuntu + windows）
- 影刀日志解析（LIFO 配对、畸形行容错、evidence 封顶）用按真实格式合成的 fixture 驱动
- Windows 原语（keybd_event / URL Scheme / 目录扫描）**不做自动化测试**（全局热键绝不进 CI），走真机验收清单
- 真机验收基准：52 台真实机器人环境 + 微信 AI 助手远程操控，四项验收全通过

## 8. 路线图

- ✅ v0.1.0：本文所述全部能力（L1 代码 → L2 远程 mock 验收 → L3 真机验收）
- ⏳ 候选：中文传参示例流程、按机器人指定 `output_dir`、真实 exit_code 回填、MCP Registry 提交、英文文档
