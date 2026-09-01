import subprocess
import sys


def test_help_exits_zero():
    proc = subprocess.run(
        [sys.executable, "-m", "yingdao_rpa_mcp", "--help"],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0
    assert "影刀社区版 MCP 服务器" in proc.stdout
    assert "--mock" in proc.stdout


def test_config_error_exits_2_with_stderr_message():
    proc = subprocess.run(
        [sys.executable, "-m", "yingdao_rpa_mcp", "--port", "99999"],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 2
    assert "CONFIG_ERROR" in proc.stderr
    assert proc.stdout == ""  # stdout 协议通道零污染
