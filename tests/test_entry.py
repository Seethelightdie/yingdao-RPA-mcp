import os
import subprocess
import sys

# CI 的 windows runner 是美式 locale（cp1252 管道）：子进程若按系统编码输出，
# 中文帮助文本会整体丢失/乱码。强制子进程 UTF-8（PEP 540 UTF-8 模式），父进程按 UTF-8 解码。
_CHILD_ENV = {**os.environ, "PYTHONUTF8": "1"}


def test_help_exits_zero():
    proc = subprocess.run(
        [sys.executable, "-m", "yingdao_rpa_mcp", "--help"],
        capture_output=True, text=True, encoding="utf-8", env=_CHILD_ENV, timeout=60,
    )
    assert proc.returncode == 0
    assert "影刀社区版 MCP 服务器" in proc.stdout
    assert "--mock" in proc.stdout


def test_config_error_exits_2_with_stderr_message():
    proc = subprocess.run(
        [sys.executable, "-m", "yingdao_rpa_mcp", "--port", "99999"],
        capture_output=True, text=True, encoding="utf-8", env=_CHILD_ENV, timeout=60,
    )
    assert proc.returncode == 2
    assert "CONFIG_ERROR" in proc.stderr
    assert proc.stdout == ""  # stdout 协议通道零污染
