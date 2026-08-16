# -*- coding: utf-8 -*-
"""开机自启管理 — Windows 注册表 HKCU\\...\\Run。

提供：
  GET  /api/autostart/status   查询当前是否已开启开机自启
  POST /api/autostart/set      设置开机自启 {enabled: true|false}

通过 `wscript.exe 启动器.vbs` 实现静默启动（无黑窗、可托盘）。
"""
import os
import logging
from flask import jsonify, request

logger = logging.getLogger("autostart")

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "DramaWorkbench"

# 用无黑窗启动器作为自启入口（存在则优先），否则回退到 pythonw main_desktop.py
_LAUNCHERS = ["start_desktop.vbs", "start.vbs", "start.bat"]


def _autostart_command():
    """构造开机自启命令：优先 wscript.exe 启动器.vbs，其次 pythonw main_desktop.py。"""
    for name in _LAUNCHERS:
        p = os.path.join(_BASE, name)
        if os.path.isfile(p) and p.lower().endswith(".vbs"):
            return f'wscript.exe "{p}"'
        if os.path.isfile(p) and p.lower().endswith(".bat"):
            return f'cmd /c ""{p}""'
    main_py = os.path.join(_BASE, "main_desktop.py")
    if os.path.isfile(main_py):
        return f'pythonw "{main_py}"'
    return None


def _reg_enabled():
    """读取注册表 Run 键，返回 (enabled, current_command)。"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as k:
            try:
                val, _ = winreg.QueryValueEx(k, _VALUE_NAME)
                return True, val
            except FileNotFoundError:
                return False, ""
    except Exception:
        # winreg 不可用（非 Windows）时返回 False
        return False, ""


def _set_reg(enabled):
    """写入或删除注册表 Run 项。返回 (ok, message)。"""
    cmd = _autostart_command()
    if not cmd:
        return False, "未找到启动入口脚本"
    try:
        import winreg
        if enabled:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                                    winreg.KEY_WRITE) as k:
                winreg.SetValueEx(k, _VALUE_NAME, 0, winreg.REG_SZ, cmd)
            return True, f"已开启开机自启：{cmd}"
        else:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                                    winreg.KEY_WRITE) as k:
                    winreg.DeleteValue(k, _VALUE_NAME)
            except FileNotFoundError:
                pass
            return True, "已关闭开机自启"
    except Exception as e:
        return False, f"操作注册表失败: {e}"


def register_routes(app, db):
    @app.route("/api/autostart/status", methods=["GET"])
    def autostart_status():
        enabled, cmd = _reg_enabled()
        return jsonify({"ok": True, "enabled": enabled, "command": cmd,
                        "expected": _autostart_command()})

    @app.route("/api/autostart/set", methods=["POST"])
    def autostart_set():
        data = request.get_json(silent=True) or {}
        enabled = bool(data.get("enabled"))
        ok, msg = _set_reg(enabled)
        return jsonify({"ok": ok, "message": msg, "enabled": enabled}), (200 if ok else 500)
