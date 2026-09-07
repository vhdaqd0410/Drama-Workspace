# -*- coding: utf-8 -*-
"""海外人名条批量生成工具 (Jianying-Name-Entry) — 工具箱接入层。

该工具是独立的剪映 UIA 自动化桌面应用（F:\OH-WorkSpace\projects\Jianying-Name-Entry），
本接入层只负责「从工作台工具箱启动它」，不复制其源码进工作台仓库：
  GET  /api/jianying-name/info     工具状态 + 入口信息
  POST /api/jianying-name/launch   启动 GUI（子进程，新窗口）
  POST /api/jianying-name/set_path 自定义工具目录（存 settings，便于迁移）

工具目录优先级：settings[jianying_name_path] > 默认 F 盘路径 > 不可用。
启动方式优先级：exe（dist/海外人名条批量生成.exe）> .venv pythonw + gui_batch.pyw > 系统 pythonw。
"""
import os
import sys
import subprocess
import logging
from flask import jsonify, request

logger = logging.getLogger("jianying-name")

# 默认安装目录（用户 F 盘项目）
_DEFAULT_DIRS = [
    r"F:\OH-WorkSpace\projects\Jianying-Name-Entry",
    r"F:\OH-WorkSpace\projects\Jianying-Name-Entry",
]

_EXE_NAME = "海外人名条批量生成.exe"
_GUI_SCRIPT = "gui_batch.pyw"
_BAT = "启动海外人名条.bat"


def _resolve_dir(db):
    """解析工具目录：settings 覆盖优先，否则默认目录。"""
    custom = ""
    try:
        custom = (db.get_setting("jianying_name_path") or "").strip()
    except Exception:
        custom = ""
    if custom and os.path.isdir(custom):
        return custom
    for d in _DEFAULT_DIRS:
        if os.path.isdir(d):
            return d
    return custom or ""


def _resolve_launch_cmd(tool_dir):
    """返回 (cmd_list, cwd, mode) 或 (None, None, reason)。mode: exe|venv|pythonw"""
    if not tool_dir or not os.path.isdir(tool_dir):
        return None, None, "工具目录不存在"

    # 1. 优先打包好的 exe（免环境）
    exe = os.path.join(tool_dir, "dist", _EXE_NAME)
    if os.path.isfile(exe):
        return [exe], tool_dir, "exe"

    # 2. 项目自带 .venv pythonw + gui_batch.pyw
    venv_pyw = os.path.join(tool_dir, ".venv", "Scripts", "pythonw.exe")
    gui = os.path.join(tool_dir, _GUI_SCRIPT)
    if os.path.isfile(venv_pyw) and os.path.isfile(gui):
        return [venv_pyw, gui], tool_dir, "venv"

    # 3. 系统 pythonw
    gui = os.path.join(tool_dir, _GUI_SCRIPT)
    if os.path.isfile(gui):
        exe = sys.executable
        pyw = exe.replace("python.exe", "pythonw.exe") if exe.endswith("python.exe") else exe
        return [pyw, gui], tool_dir, "pythonw"

    return None, None, "未找到可启动入口（exe / gui_batch.pyw）"


def register_routes(app, db):
    @app.route("/api/jianying-name/info", methods=["GET"])
    def jy_info():
        tool_dir = _resolve_dir(db)
        cmd, cwd, mode = _resolve_launch_cmd(tool_dir)
        return jsonify({
            "ok": True,
            "available": bool(cmd),
            "tool_dir": tool_dir,
            "mode": mode,
            "custom_path": (db.get_setting("jianying_name_path") or "").strip(),
        })

    @app.route("/api/jianying-name/launch", methods=["POST"])
    def jy_launch():
        tool_dir = _resolve_dir(db)
        cmd, cwd, mode = _resolve_launch_cmd(tool_dir)
        if not cmd:
            return jsonify({"ok": False, "message": "海外人名条工具未找到，请确认工具目录"}), 500
        try:
            kwargs = {}
            if os.name == "nt":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.Popen(
                cmd, cwd=cwd,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                **kwargs,
            )
            logger.info("已启动海外人名条工具 (mode=%s): %s", mode, cmd)
            return jsonify({"ok": True, "message": "已启动海外人名条工具窗口", "mode": mode})
        except Exception as e:
            logger.exception("启动海外人名条工具失败: %s", e)
            return jsonify({"ok": False, "message": f"启动失败: {e}"}), 500

    @app.route("/api/jianying-name/set_path", methods=["POST"])
    def jy_set_path():
        data = request.get_json(silent=True) or {}
        path = (data.get("path") or "").strip()
        db.set_setting("jianying_name_path", path)
        return jsonify({"ok": True, "path": path})
