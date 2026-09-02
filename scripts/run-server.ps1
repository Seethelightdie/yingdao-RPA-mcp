# run-server.ps1 —— yingdao-rpa-mcp 启动器（计划任务调用；真实网关，无 --mock）
$repo = $PSScriptRoot | Split-Path
Set-Location $repo

# 读 .env（Windows 无自动 .env 机制；当前仅 token 一项）
Get-Content "$repo\.env" | ForEach-Object {
    if ($_ -match "^YINGDAO_MCP_TOKEN=(.+)$") { $env:YINGDAO_MCP_TOKEN = $Matches[1] }
}

# 后台启动：脱离父进程独立常驻；stdout/stderr 分文件落盘（stderr 是 uvicorn/fastmcp 日志流，属正常）
Start-Process -FilePath "$repo\.venv-win\Scripts\python.exe" `
    -ArgumentList "-m","yingdao_rpa_mcp","--transport","http","--host","0.0.0.0","--port","8000" `
    -WorkingDirectory $repo -WindowStyle Hidden `
    -RedirectStandardOutput "$repo\server.out.log" `
    -RedirectStandardError "$repo\server.err.log"
Write-Host "server 已后台启动（日志：server.err.log）"
