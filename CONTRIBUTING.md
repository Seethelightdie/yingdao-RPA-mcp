# 贡献指南

感谢关注本项目！这是一份轻量指南，重要的工程约定都在根目录 [AGENTS.md](AGENTS.md)（强烈建议先读）。

## 开发环境

```bash
git clone https://github.com/Seethelightdie/yingdao-RPA-mcp.git
cd yingdao-RPA-mcp
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q          # 94 个测试，任何 OS 全绿（全 mock，无需 Windows/影刀）
ruff check .
```

## 开发铁律（摘自 AGENTS.md，违反即回滚）

1. **严禁杀进程停止影刀**——唯一停止通道是 `keybd_event` 发送 Ctrl+Alt+Q
2. **严禁向 stdout 打印非协议内容**（stdio 模式下 stdout 是 MCP 专用通道）
3. **严禁硬编码密钥、真实用户名、真实机器人 uuid/路径**——提交前 grep 审计
4. Mock 输出必须带 `mock` 标识，不得冒充真实数据
5. 真实网关动作后默认等待 5 秒验证（可配置），勿"优化"掉

## 测试策略

- **唯一架构接缝**是 `ShadowBotGateway`（Mock / Windows 双实现）——工具层测试走进程内 MCP 客户端 + Mock 网关，全平台可跑
- Windows 原语（keybd_event / URL Scheme / 目录扫描）**不做自动化测试**，走真机验收清单；全局热键绝不进 CI
- 新功能请先写失败测试（TDD），测试只断言外部行为而非实现细节

## 提交规范

- Conventional Commits（`feat:` / `fix:` / `docs:` / `test:` / `chore:`），描述用中文、标识符用英文
- 一个 commit 只做一件事

## 提交 PR 前

- [ ] `pytest -q` 全绿
- [ ] `ruff check .` 无告警
- [ ] 无敏感信息（grep 审计自己的 diff）
- [ ] 涉及用户可见行为的改动已更新 README / CHANGELOG
