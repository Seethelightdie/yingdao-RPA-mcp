#Requires -RunAsAdministrator
# install-windows.ps1 —— yingdao-rpa-mcp Windows 一键安装（幂等）
# 前提：本目录所在文件夹是仓库根（含 src/、pyproject.toml、scripts/）
# 需要管理员权限（防火墙与计划任务）；安装后服务以"当前用户登录会话"运行（keybd_event/URL Scheme 必需）
$ErrorActionPreference = "Stop"
$repo = $PSScriptRoot | Split-Path
Set-Location $repo
Write-Host "== yingdao-rpa-mcp 安装开始：$repo =="

# --- 1. 探测 Python >= 3.10；缺失则 winget 引导 ---
$py = $null
foreach ($cand in @("py", "python", "python3")) {
    try {
        $v = & $cand -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($v -and [version]$v -ge [version]"3.10") { $py = $cand; break }
    } catch { }
}
if (-not $py) {
    Write-Host "未找到 Python >= 3.10，尝试 winget 安装 Python 3.12（请在 UAC 弹窗确认）..."
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    $v = & python -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
    if (-not $v -or [version]$v -lt [version]"3.10") {
        Write-Error "Python 3.10+ 仍不可用。请手动安装 Python（勾选 Add to PATH）后重新运行本脚本。"
        exit 1
    }
    $py = "python"
}
Write-Host "Python 就绪：$(& $py -c 'import sys; print(sys.version.split()[0])')"

# --- 2. Windows venv（.venv-win，与 WSL 的 .venv 并存）+ 安装本包 ---
if (-not (Test-Path "$repo\.venv-win")) { & $py -m venv "$repo\.venv-win" }
& "$repo\.venv-win\Scripts\python.exe" -m pip install --upgrade pip -q
& "$repo\.venv-win\Scripts\python.exe" -m pip install . -q
& "$repo\.venv-win\Scripts\python.exe" -c "import yingdao_rpa_mcp; print('installed', yingdao_rpa_mcp.__version__)"

# --- 3. token .env（已存在则保留——重复安装不换锁）---
$envFile = "$repo\.env"
if (-not (Test-Path $envFile)) {
    $token = [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
    Set-Content -Path $envFile -Value "YINGDAO_MCP_TOKEN=$token" -NoNewline
    Write-Host "已生成 token：$envFile（配置完 Tailscale 后需要此值提供给服务器，见 L3 计划 Task 3 Step 4）"
} else {
    Write-Host ".env 已存在，保留现有 token"
}

# --- 4. 防火墙：仅放行 Tailscale 网段访问 8000 ---
$ruleName = "yingdao-rpa-mcp (Tailscale only)"
if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP -LocalPort 8000 `
        -RemoteAddress 100.64.0.0/10 -Action Allow | Out-Null
    Write-Host "防火墙规则已创建（仅 Tailscale 100.64.0.0/10 可达 8000）"
} else {
    Write-Host "防火墙规则已存在"
}

# --- 5. 计划任务：登录时自启（用户桌面会话内运行——keybd_event/URL Scheme 必需）---
$taskName = "YingDaoRpaMcp"
$runScript = "$repo\scripts\run-server.ps1"
schtasks /Create /F /TN $taskName /SC ONLOGON /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$runScript`"" | Out-Null
Write-Host "计划任务 $taskName 已注册（每次登录自启）"

# --- 6. 立即启动并自检（预期无 token 访问得到 401）---
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $runScript
Start-Sleep -Seconds 5
try {
    Invoke-WebRequest -Uri "http://127.0.0.1:8000/mcp" -Method POST -UseBasicParsing -TimeoutSec 5 | Out-Null
    Write-Error "意外的 2xx——无 token 不应通过，请检查 server.log"
} catch {
    $code = $_.Exception.Response.StatusCode.value__
    if ($code -eq 401) { Write-Host "自检通过：服务运行中，鉴权生效（401）" }
    else { Write-Host "自检返回 $code，请查看 $repo\server.log 排障" }
}
Write-Host "== 安装完成。下一步：安装并登录 Tailscale（L3 计划 Task 3），运行 uninstall 前请勿删除 .env =="
