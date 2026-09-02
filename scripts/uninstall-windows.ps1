# uninstall-windows.ps1 —— 对称卸载（代码与 .env 保留；完全清理请手动删除仓库目录）
schtasks /End /TN YingDaoRpaMcp 2>$null
schtasks /Delete /TN YingDaoRpaMcp /F 2>$null
Get-NetFirewallRule -DisplayName "yingdao-rpa-mcp (Tailscale only)" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
Write-Host "已停止服务并移除计划任务与防火墙规则。如需完全清理，手动删除仓库目录（含 .venv 与 .env）。"
