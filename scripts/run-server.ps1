# run-server.ps1 —— yingdao-rpa-mcp 启动器（计划任务调用；真实网关，无 --mock）
$ErrorActionPreference = "Stop"
$repo = $PSScriptRoot | Split-Path
Set-Location $repo

# 读 .env（Windows 无自动 .env 机制；当前仅 token 一项）
Get-Content "$repo\.env" | ForEach-Object {
    if ($_ -match "^YINGDAO_MCP_TOKEN=(.+)$") { $env:YINGDAO_MCP_TOKEN = $Matches[1] }
}

# 真实网关（Windows + 影刀本机）；输出全部追加到 server.log 供排障
& "$repo\.venv-win\Scripts\python.exe" -m yingdao_rpa_mcp --transport http --host 0.0.0.0 --port 8000 *>> "$repo\server.log"
