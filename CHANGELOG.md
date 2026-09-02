# Changelog

本项目的所有显著变更都记录在此文件中。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [0.1.0] - 2026-09-02

首个公开版本。核心能力全部经过真机验收（52 台真实影刀机器人环境 + 微信 AI 助手远程操控）。

### Added

- **5 个 MCP 工具**：`list_robots` / `run_robot`（支持中文 `key=value` 传参与产出文件回收）/ `get_status`（三层日志验证）/ `stop_robot`（Ctrl+Alt+Q 优雅停止，全局警告前置）/ `tail_log`
- **双传输**：本地 `stdio`（Claude Desktop 等即插即用）+ 远程 `streamable-http`（配 Tailscale 跨网操控）
- **静态 Bearer token 鉴权** + **stateless-http** 模式（网关进程重启对客户端透明）
- **Mock 模式**：无 Windows / 无影刀环境也可体验全部工具，兼任全量自动化测试替身
- **Windows 一键安装脚本**：Python 探测、虚拟环境、token 生成、防火墙（仅放行 Tailscale 网段）、登录自启计划任务、401 自检
- **run_robot 日志竞态重试**：影刀异步刷日志导致的瞬时任务 `launched:false` 误报已修复（有界重试，不无限等待）
- **统一错误契约**：所有工具错误返回 `code + 中文 message + hint`，永不向协议层抛异常
- 示例配置（`examples/`）、CI（ubuntu + windows 双矩阵）

### 继承（致谢 [yingdao_robot_run_api_manage_and_skill](https://github.com/HnBigVolibear/yingdao_robot_run_api_manage_and_skill)）

- 「侦察代替 API」哲学与四条民间通道：目录扫描 / URL Scheme 启动传参 / 日志三层验证 / keybd_event 优雅停止
- 详见 [docs/COMPARISON.md](docs/COMPARISON.md)
