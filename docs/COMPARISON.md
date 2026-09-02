# 与原仓库的关系：继承与补齐对照表

本项目不是凭空发明的。它的核心机制**全部继承**自
[湖南大白熊的 yingdao_robot_run_api_manage_and_skill](https://github.com/HnBigVolibear/yingdao_robot_run_api_manage_and_skill)（MIT），
并在其"侦察代替 API"哲学之上做了 **MCP 化重构**。这张表说清楚：什么被继承了，什么被补齐了。

> 原仓库 README 里那句"没错！别找了！这里就是你想要的影刀 Skill ^_^"至今仍然成立——
> 本项目只是把同一件事接到了 MCP 这个更通用的协议上。

## 一句话对比

- **原仓库**：Flet 桌面壳 + Flask REST 接口 + AI Skill 脚本——让特定 Agent 能一键启动影刀
- **本项目**：FastMCP 服务器——让**任何** MCP 客户端（Claude Desktop、微信 AI 助手、自建 Agent…）
  原生操控影刀，且跑完能拿到结构化结果

## 逐项对照

| 维度 | 原仓库 | 本项目 | 关系 |
|---|---|---|---|
| 机器人发现 | 扫描 `users\<ID>\apps`，4 个候选 package 路径、`_temp` 跳过、mtime 排序 | 同一套扫描逻辑，封装为 `list_robots` 工具 | ✅ 继承 |
| 启动 | `shadowbot:Run?robot-uuid=…` URL Scheme | `run_robot` 工具，同一 URL Scheme | ✅ 继承 |
| 传参 | `&key=value`，特殊字符编码、中文原样（实测口径） | 同一编码口径（仅编码 `& = # %` 空格），支持任意 MCP 客户端传入 | ✅ 继承 |
| 状态检测 | 影刀主日志解析（TaskManager / engine running / exited LIFO 配对）+ `GetExitCodeProcess` 存活检测 | 同一套解析，封装为 `get_status` 工具；另加有界重试补"瞬时任务日志落盘竞态" | ✅ 继承 + 补齐 |
| 停止 | `keybd_event` 发送 Ctrl+Alt+Q（SendInput 无法触发全局钩子），**严禁杀进程** | `stop_robot` 工具，同一键序与红线，工具描述内置全局停止警告 | ✅ 继承 |
| 动作后验证 | 等待 5 秒再查状态 | 继承（真实网关默认 5 秒，可配置；另加日志未落盘时的重试） | ✅ 继承 + 补齐 |
| 协议 | REST（localhost:16666）+ AI Skill 脚本 | MCP：stdio（本地）+ streamable-http（远程） | 🔨 重构 |
| AI 客户端 | 特定 Skill 宿主（Trae 等） | 任意 MCP 客户端（Claude Desktop / 微信 AI 助手 / 自建 Agent） | 🔨 补齐 |
| 远程接入 | 局域网 REST，无鉴权 | Tailscale 组网 + Bearer token 鉴权 + 防火墙网段限定 | 🔨 补齐 |
| 会话健壮性 | — | stateless-http：网关进程/主机重启对客户端透明 | 🔨 补齐 |
| 结果回传 | 启动即返回，跑完无下文 | 结构化结果（launched/state/evidence/exitCode）+ 产出文件列表，AI 侧轮询闭环 | 🔨 补齐 |
| 错误契约 | 文本返回 | 统一 `code + 中文 message + hint`，永不向协议层抛异常 | 🔨 补齐 |
| Mock 模式 | 无 | 内置：无 Windows/无影刀环境体验全部工具，兼任 94 个自动化测试的替身 | 🔨 补齐 |
| GUI 管理界面 | Flet 桌面应用（列表/按钮/接口文档页） | 无（协议即产品） | ➖ 取舍 |
| 影刀企业版支持 | 不支持 | 不支持（同口径） | ➖ 相同 |

## 使用建议

- 只想要一个桌面工具 + 局域网 REST、习惯 GUI 操作 → **继续用原仓库**，它做得很好
- 想让 AI 助手（微信/Claude Desktop/任何 MCP 客户端）原生操控影刀、需要远程与安全边界 → **用本项目**
- 两者不冲突：原仓库管"人用"，本项目管"AI 用"，可以共存于同一台影刀机器

## 致谢方式

- [LICENSE](../LICENSE) 保留原仓库 MIT 版权行
- 本 README 与项目文档在描述技术机制处均注明继承来源
- 如果你因本项目受益，也请顺手给 [原仓库](https://github.com/HnBigVolibear/yingdao_robot_run_api_manage_and_skill) 一个 Star——前人的踩坑值得被看见
