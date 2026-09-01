"""Ctrl+Alt+Q 优雅停止——严禁杀进程。

为什么 keybd_event 而不是 SendInput：影刀通过全局键盘钩子监听停止快捷键，
SendInput 无法触发全局钩子，keybd_event 可以（原仓库实测结论）。
键序（原仓库实测）：按下 Ctrl、Alt、Q → 睡 0.1s → 逆序释放。
"""
from __future__ import annotations

import ctypes
import time

_VK_CONTROL = 0x11
_VK_MENU = 0x12  # Alt
_VK_Q = 0x51
_KEYEVENTF_KEYUP = 0x0002


def send_ctrl_alt_q() -> None:
    """发送后不检查 keybd_event 返回值（失效场景由网关层"动作后等 5 秒验证"兜底）。"""
    user32 = ctypes.windll.user32
    user32.keybd_event(_VK_CONTROL, 0, 0, 0)
    user32.keybd_event(_VK_MENU, 0, 0, 0)
    user32.keybd_event(_VK_Q, 0, 0, 0)
    time.sleep(0.1)
    user32.keybd_event(_VK_Q, 0, _KEYEVENTF_KEYUP, 0)
    user32.keybd_event(_VK_MENU, 0, _KEYEVENTF_KEYUP, 0)
    user32.keybd_event(_VK_CONTROL, 0, _KEYEVENTF_KEYUP, 0)
