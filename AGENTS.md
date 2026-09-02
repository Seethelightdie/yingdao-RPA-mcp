# AGENTS.md

## Agent skills

### Issue tracker

本地 markdown：spec 与 issue 存放在 `.scratch/<feature-slug>/` 下，一票一文件。See `docs/agents/issue-tracker.md`.

### Domain docs

单上下文布局：根 `CONTEXT.md` + `docs/adr/`（惰性创建，缺失时不阻塞）。See `docs/agents/domain.md`.

## 项目一句话

影刀（ShadowBot）社区版的 MCP 服务器：把"侦察代替 API"的四条民间通道封装成标准 MCP 工具，双传输（stdio + streamable-http），自带 Mock 模式。

## 当前阶段

spec 已定稿：`.scratch/mvp-v01/spec.md`（Status: ready-for-agent）。
执行阶梯：L1（mock + stdio 自测）→ L2（远程传输 + 联调验收）→ P4（文档/对比/示例）→ P5（GitHub 发布）→ L3（真机验收）。

## 仓库地图（规划布局，P1 起逐步成形）

```
/
├── src/yingdao_rpa_mcp/     # MCP 工具层 + ShadowBotGateway 接口
│   ├── gateway/             # MockGateway + WindowsGateway（唯一架构接缝的两个实现）
│   ├── tools/               # FastMCP 工具定义
│   └── config.py            # 配置加载（toml/env/CLI 三级覆盖）
├── tests/                   # 全部基于 mock，任何 OS 可跑
├── docs/                    # SPEC.md（公开设计文档）、adr/、agents/
├── examples/                # mcp.json、config.toml 样例、Tailscale 教程
├── .scratch/                # 本地 issue tracker（不入 git）
└── AGENTS.md / SPEC.md / README.md / LICENSE
```

## 环境事实

- **目标运行环境 = Windows + 影刀社区版**。真实网关的四条侦察通道（目录扫描 / URL Scheme / 日志解析 / keybd_event）仅在 Windows 生效。
- **开发环境 = WSL/Linux**：一切自动化测试走 Mock 模式——这是唯一无真机路径。
- Mock 模式是**产品功能**（非 Windows 用户可体验、可演示），不只是测试替身。

## 红线（违反即回滚）

1. **严禁杀进程停止影刀**。唯一停止通道 = keybd_event 发送 Ctrl+Alt+Q（影刀用全局钩子监听，SendInput 不可用）。`stop_robot` 是**全局停止**，会影响所有运行中的机器人——工具描述必须写明，LLM 才能正确向用户确认。
2. **严禁硬编码任何密钥、PC 用户名、真实 uuid 或路径实例**。配置一律占位符 + 可覆盖；提交前 grep 审计（用户名模式、盘符路径、key 前缀）。
3. **免责声明与原仓库致谢不得删除或弱化**。MIT 许可保留原仓库版权行。
4. **严禁把 Mock 数据冒充真实数据返回**。mock 输出必须可辨识（如标记 `mock: true`）。
5. **stdio 模式下严禁向 stdout 打印任何非协议内容**（stdout 是 MCP 专用通道，server 日志一律走 stderr）。
6. 真实网关动作后（启动/停止）**默认等 5 秒再做日志验证**——原仓库验证过的时序，勿"优化"掉；等待时长可配置，mock 默认 0 秒。

## 开发循环

```
pip install -e .        # 或 uv sync
pytest                  # 全量 mock，任何 OS 通过
ruff check .
# 手动冒烟：以 stdio + mock 模式启动 server，逐个调一遍工具
```

## 代码约定

- Python ≥ 3.10，全量类型标注
- 注释与文档用中文，标识符用英文
- 单一职责：Windows 侦察通道细节只允许出现在真实网关实现内部，工具层与 Mock 不得 import 任何 Win32 专属模块
- keybd_event 用 ctypes 标准库实现，不引入 Windows 专属第三方依赖

## 发布前检查清单

- [ ] git 身份已改为真实署名（开发期用占位身份 yingdao-rpa-mcp <noreply@example.com>）
- [ ] grep 审计：无敏感信息（key / 用户名 / 真实 uuid / 真实路径 / 服务器 IP）
- [ ] pytest 全绿（本地 + CI：ubuntu 与 windows matrix）
- [ ] ruff 无告警
- [ ] 真机验收清单逐项通过（启动 / 传参 / 状态 / 全局停止 / 日志尾读）
- [ ] README + SPEC + LICENSE(MIT) + 致谢 + 免责声明齐全
- [ ] 版本 tag + Release 说明
