"""进程存活检测：OpenProcess + GetExitCodeProcess，STILL_ACTIVE=259。

已知局限：OpenProcess 返回 NULL 时（权限不足/受保护进程）一律视为已退出；
L3 排障时注意区分"真死了"与"看不见"。
"""
from __future__ import annotations

import ctypes

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259


def is_pid_alive(pid: int) -> bool:
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    exit_code = ctypes.c_ulong()
    kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
    kernel32.CloseHandle(handle)
    return exit_code.value == _STILL_ACTIVE
