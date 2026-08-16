# -*- coding: utf-8 -*-
"""拆集重命名工具插件 (plugins/dramatool) — 工具箱接入层。

该插件是完整的 tkinter(GUI) 拆集/重命名桌面应用，本接入层主要提供：
  POST /api/dramatool/launch   启动拆集工具 GUI（子进程，保留全部功能）
  GET  /api/dramatool/info     插件状态与入口信息

保留插件独立能力：双击 plugins/dramatool/run.bat 或
python plugins/dramatool/src/main.py 均可直接使用。
"""
import os
import sys
import subprocess
import logging
from flask import jsonify

logger = logging.getLogger("dramatool")

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PLUGIN_DIR = os.path.join(_BASE, "plugins", "dramatool")
_MAIN_SCRIPT = os.path.join(_PLUGIN_DIR, "src", "main.py")
_RUN_BAT = os.path.join(_PLUGIN_DIR, "run.bat")


def _plugin_available():
    return os.path.isfile(_MAIN_SCRIPT)


def _preferred_python():
    """优先使用插件自带 .venv 的 pythonw（依赖完整），否则用当前解释器。"""
    for cand in (
        os.path.join(_PLUGIN_DIR, ".venv", "Scripts", "pythonw.exe"),
        os.path.join(_PLUGIN_DIR, ".venv", "Scripts", "python.exe"),
    ):
        if os.path.isfile(cand):
            return cand
    exe = sys.executable
    return exe.replace("python.exe", "pythonw.exe") if exe.endswith("python.exe") else exe


def register_routes(app, db):
    @app.route("/api/dramatool/info", methods=["GET"])
    def dramatool_info():
        return jsonify({
            "ok": True,
            "available": _plugin_available(),
            "plugin_dir": _PLUGIN_DIR,
            "entry": os.path.relpath(_MAIN_SCRIPT, _PLUGIN_DIR) if _plugin_available() else None,
        })

    @app.route("/api/dramatool/launch", methods=["POST"])
    def dramatool_launch():
        """启动拆集工具 GUI（子进程，新窗口打开，保留全部功能）。"""
        if not _plugin_available():
            return jsonify({"ok": False, "message": "拆集工具插件未安装"}), 500
        py = _preferred_python()
        try:
            kwargs = {}
            if os.name == "nt":
                # 隐藏控制台窗口（GUI 应用）
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.Popen(
                [py, _MAIN_SCRIPT],
                cwd=_PLUGIN_DIR,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **kwargs,
            )
            logger.info("已启动拆集工具 GUI: %s", _MAIN_SCRIPT)
            return jsonify({"ok": True, "message": "已启动拆集工具窗口"})
        except Exception as e:
            logger.exception("启动拆集工具失败: %s", e)
            return jsonify({"ok": False, "message": f"启动失败: {e}"}), 500
