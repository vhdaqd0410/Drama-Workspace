# -*- coding: utf-8 -*-
"""提成工具插件 (plugins/commission) — 工具箱接入层。

该插件是完整的 tkinter GUI 桌面应用，本接入层主要提供：
  POST /api/commission/launch   启动提成工具 GUI（子进程，保留全部功能）
  GET  /api/commission/info     插件状态与入口信息

保留插件独立能力：双击 plugins/commission/启动工具.vbs 或
python plugins/commission/ai_commission_gui.py 均可直接使用。
"""
import os
import sys
import subprocess
import logging
from flask import jsonify, request

logger = logging.getLogger("commission")

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PLUGIN_DIR = os.path.join(_BASE, "plugins", "commission")
_GUI_SCRIPT = os.path.join(_PLUGIN_DIR, "ai_commission_gui.py")
_LAUNCH_VBS = os.path.join(_PLUGIN_DIR, "启动工具.vbs")


def _plugin_available():
    return os.path.isfile(_GUI_SCRIPT)


def _preferred_python():
    """优先使用插件自带的 Python3.13（已装全部依赖），否则用当前解释器。"""
    for cand in (
        r"C:\Users\Admin\AppData\Local\Programs\Python\Python313\pythonw.exe",
        r"C:\Users\Admin\AppData\Local\Programs\Python\Python313\python.exe",
    ):
        if os.path.isfile(cand):
            return cand
    # 回退到当前进程的解释器
    exe = sys.executable
    return exe.replace("python.exe", "pythonw.exe") if exe.endswith("python.exe") else exe


def register_routes(app, db):
    @app.route("/api/commission/info", methods=["GET"])
    def commission_info():
        return jsonify({
            "ok": True,
            "available": _plugin_available(),
            "plugin_dir": _PLUGIN_DIR,
            "gui": os.path.basename(_GUI_SCRIPT) if _plugin_available() else None,
        })

    @app.route("/api/commission/monthly", methods=["GET"])
    def commission_monthly():
        """提成/绩效全链路报表（功能1）：从分集数据(episode_plan)计算每人绩效+提成。
        ?month=YYYY-MM（默认当月）。返回 rows + summary。
        """
        from datetime import datetime
        month = request.args.get("month", "") or datetime.now().strftime("%Y-%m")
        try:
            from features import aggregate_editor_workload
            from commission_service import compute_commission_breakdown
            workload = aggregate_editor_workload(db, month=month)
            rows, summary = compute_commission_breakdown(workload, month)
            return jsonify({
                "ok": True, "month": month,
                "rows": rows, "summary": summary,
                "mode": "分集数据",
            })
        except Exception as e:
            import traceback; traceback.print_exc()
            return jsonify({"ok": False, "message": str(e)}), 500

    @app.route("/api/commission/person_cards", methods=["GET"])
    def commission_person_cards():
        """个人工作量卡片（功能2）：年度逐月集数 + 角色 + 汇总。?year=YYYY"""
        year = request.args.get("year", "")
        try:
            from commission_service import compute_person_cards
            data = compute_person_cards(db, year=year)
            return jsonify({"ok": True, **data})
        except Exception as e:
            import traceback; traceback.print_exc()
            return jsonify({"ok": False, "message": str(e)}), 500


    @app.route("/api/commission/launch", methods=["POST"])
    def commission_launch():
        """启动提成工具 GUI（子进程，新窗口打开，保留全部功能）。"""
        if not _plugin_available():
            return jsonify({"ok": False, "message": "提成工具插件未安装"}), 500
        py = _preferred_python()
        try:
            kwargs = {}
            if os.name == "nt":
                # 隐藏控制台窗口（GUI 应用）
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.Popen(
                [py, _GUI_SCRIPT],
                cwd=_PLUGIN_DIR,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **kwargs,
            )
            logger.info("已启动提成工具 GUI: %s", _GUI_SCRIPT)
            return jsonify({"ok": True, "message": "已启动提成工具窗口"})
        except Exception as e:
            logger.exception("启动提成工具失败: %s", e)
            return jsonify({"ok": False, "message": f"启动失败: {e}"}), 500
