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
