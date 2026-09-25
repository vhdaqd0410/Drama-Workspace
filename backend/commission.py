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
import json
import tempfile
import subprocess
import logging
from flask import jsonify, request

logger = logging.getLogger("commission")

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PLUGIN_DIR = os.path.join(_BASE, "plugins", "commission")
_GUI_SCRIPT = os.path.join(_PLUGIN_DIR, "ai_commission_gui.py")
_LAUNCH_VBS = os.path.join(_PLUGIN_DIR, "启动工具.vbs")
_CONFIG_PATH = os.path.join(_PLUGIN_DIR, "config.json")

# 允许设置的角色与字段（卡前/卡后/助理/组长），以及数值边界
_RULE_ROLES = {
    "一卡剪辑": ("基准集数", "超额每集", "缺集每集扣"),
    "二卡剪辑": ("基准集数", "超额每集", "缺集每集扣"),
    "剪辑助理": ("基准集数", "超额每集", "缺集每集扣"),
    "剪辑组长": ("每集单价", "组内每部提成"),
}
_RULE_ROLE_ALIAS = {
    "卡前": "一卡剪辑", "一卡": "一卡剪辑", "一卡剪辑": "一卡剪辑",
    "卡后": "二卡剪辑", "二卡": "二卡剪辑", "二卡剪辑": "二卡剪辑",
    "助理": "剪辑助理", "剪辑助理": "剪辑助理",
    "组长": "剪辑组长", "剪辑组长": "剪辑组长",
}


def _read_rules():
    """读取 config.json 的 rules（不存在则返回空 dict）。"""
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        rules = d.get("rules", {}) or {}
        return rules if isinstance(rules, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning("读取提成规则失败: %s", e)
        return {}


def _build_desc(role, rule):
    """根据角色规则生成“提成构成描述”文案，保证与数值联动。"""
    try:
        if role == "剪辑组长":
            return "%s元/集，一部提成%s元" % (rule.get("每集单价", 20), rule.get("组内每部提成", 100))
        return "基本量%s集/月，超出一集%s元/集，缺一集-%s元/集" % (
            rule.get("基准集数", 120), rule.get("超额每集", 20), rule.get("缺集每集扣", 50))
    except Exception:
        return ""


def _merge_rules(rules, rules_in):
    """将前端传入的规则合并进 rules（就地修改），返回错误列表。
    仅接受已知角色/字段，数值须为非负整数。
    """
    errs = []
    for role_key, fields in (rules_in or {}).items():
        role = _RULE_ROLE_ALIAS.get(str(role_key).strip())
        if not role:
            errs.append("未知角色: %s" % role_key)
            continue
        if not isinstance(fields, dict):
            errs.append("%s 配置必须是对象" % role)
            continue
        allowed = _RULE_ROLES[role]
        target = rules.setdefault(role, {})
        for field, val in fields.items():
            if field == "提成构成描述":
                continue
            if field not in allowed:
                errs.append("%s 不支持字段: %s" % (role, field))
                continue
            try:
                iv = int(val)
            except Exception:
                errs.append("%s.%s 必须是整数" % (role, field))
                continue
            if iv < 0:
                errs.append("%s.%s 不能为负数" % (role, field))
                continue
            if field in ("基准集数", "每集单价") and iv <= 0:
                errs.append("%s.%s 必须大于 0" % (role, field))
                continue
            target[field] = iv
        # 补齐默认值后重建描述
        for f in allowed:
            target.setdefault(f, 0)
        target["提成构成描述"] = _build_desc(role, target)
    return errs


def _write_rules(rules):
    """原子写回 config.json（保留其它字段）。"""
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        d = json.load(f)
    d["rules"] = rules
    dir_path = os.path.dirname(_CONFIG_PATH)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json",
                                     dir=dir_path, delete=False) as tmp:
        json.dump(d, tmp, ensure_ascii=False, indent=2)
        tmp_path = tmp.name
    try:
        os.replace(tmp_path, _CONFIG_PATH)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _clear_rule_caches():
    """清掉插件侧可能存在的规则缓存（按 mtime 缓存会自动失效，这里作双保险）。"""
    try:
        src = os.path.join(_PLUGIN_DIR, "src")
        if src not in sys.path:
            sys.path.insert(0, src)
        import features as _f  # type: ignore
        if hasattr(_f, "_RULES_CACHE"):
            _f._RULES_CACHE["mtime"] = None
            _f._RULES_CACHE["rules"] = None
    except Exception:
        pass


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

    @app.route("/api/commission/rules", methods=["GET"])
    def commission_get_rules():
        """读取提成规则（plugins/commission/config.json 的 rules）。
        这是工作台与提成工具共用的唯一真源，修改后两边同时生效。
        """
        return jsonify({"ok": True, "rules": _read_rules(),
                        "config_path": _CONFIG_PATH})

    @app.route("/api/commission/rules", methods=["PUT"])
    def commission_set_rules():
        """更新提成规则。body: {"一卡剪辑": {"基准集数": 40, "超额每集": 20,
        "缺集每集扣": 50}, "二卡剪辑": {...}, "剪辑助理": {...},
        "剪辑组长": {"每集单价": 20, "组内每部提成": 100}}
        仅允许已知角色与已知字段，写前校验，原子落盘并同步“提成构成描述”文案。
        """
        data = request.get_json(silent=True) or {}
        rules_in = data.get("rules") or data
        if not isinstance(rules_in, dict):
            return jsonify({"ok": False, "message": "rules 必须是对象"}), 400
        try:
            rules = _read_rules()
            errs = _merge_rules(rules, rules_in)
            if errs:
                return jsonify({"ok": False, "message": "；".join(errs)}), 400
            _write_rules(rules)
            # 清掉 features/提成工具的规则缓存，避免旧值残留
            _clear_rule_caches()
            return jsonify({"ok": True, "rules": rules})
        except Exception as e:
            logger.exception("保存提成规则失败: %s", e)
            return jsonify({"ok": False, "message": f"保存失败: {e}"}), 500

    @app.route("/api/commission/monthly", methods=["GET"])
    def commission_monthly():
        """提成/绩效全链路报表（功能1）：从分集数据(episode_plan)计算每人绩效+提成。
        ?month=YYYY-MM（默认当月）。返回 rows + summary。
        """
        from datetime import datetime
        month = request.args.get("month", "") or datetime.now().strftime("%Y-%m")
        try:
            from features import aggregate_editor_workload
            from commission_service import compute_commission_breakdown, compute_group_completed
            workload = aggregate_editor_workload(db, month=month)
            # 功能3：组长组奖按组内当月全部完成部数计（数据来自项目本月完成数）
            group_completed = compute_group_completed(db, month=month)
            rows, summary = compute_commission_breakdown(
                workload, month, group_completed_count=group_completed, db=db)
            return jsonify({
                "ok": True, "month": month,
                "rows": rows, "summary": summary,
                "group_completed": group_completed,
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
