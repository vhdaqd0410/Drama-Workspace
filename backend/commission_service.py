# -*- coding: utf-8 -*-
"""提成/绩效全链路计算服务（功能1）。

从主应用的「分集数据(episode_plan)」出发，结合角色/提成规则配置，
计算出每人当月：集数 → 绩效(达标/未达标) → 提成（超额/缺集/组长组奖）。
口径：集数以分集数据为准（与统计一致），角色/规则来自提成工具 config.json。

纯函数设计，便于单测；/api/commission/monthly 等路由复用本模块。
"""
import json
import os
import logging

logger = logging.getLogger("commission_service")

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 提成工具配置文件（角色/规则），可被独立工具编辑；缺省回退到内置默认
_PLUGIN_CFG = os.path.join(_BASE, "plugins", "commission", "config.json")

DEFAULT_RULES = {
    "一卡剪辑": {"基准集数": 70, "超额每集": 20, "缺集每集扣": 50,
                "提成构成描述": "基本量70集/月，超出一集20元/集，缺一集-50元/集"},
    "二卡剪辑": {"基准集数": 120, "超额每集": 20, "缺集每集扣": 50,
                "提成构成描述": "基本量120集/月，超出一集20元/集，缺一集-50元/集"},
    "剪辑助理": {"基准集数": 120, "超额每集": 20, "缺集每集扣": 50,
                "提成构成描述": "基本量120集/月，超出一集20元/集，缺一集-50元/集"},
    "剪辑组长": {"每集单价": 20, "组内每部提成": 100,
                "提成构成描述": "20元/集，一部提成100元"},
}

# 缺省角色表（可在插件 config.json 覆盖）
DEFAULT_ROLES = {
    "张大强": "剪辑组长", "任显翔": "小组长", "陈陆杰": "小组长",
    "陈春阳": "一卡剪辑", "程梦": "一卡剪辑", "张靖杰": "一卡剪辑",
    "王田田": "二卡剪辑", "张淯升": "二卡剪辑",
    "金文龙": "剪辑助理", "李钊琦": "剪辑助理", "刘梦真": "剪辑助理",
    "杨倩": "剪辑助理", "陈浩博": "剪辑助理", "袁绍杰": "剪辑助理",
    "王傲雪": "剪辑助理",
}


def load_config(cfg_path=None):
    """加载角色/提成规则配置。返回 (roles, rules)。"""
    path = cfg_path or _PLUGIN_CFG
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f) or {}
        roles = dict(DEFAULT_ROLES)
        roles.update({k: v for k, v in cfg.get("人员角色", {}).items() if v})
        rules = dict(DEFAULT_RULES)
        rules.update(cfg.get("rules", {}) or {})
        return roles, rules
    except Exception as e:
        logger.warning("读取提成配置失败(%s)，使用内置默认: %s", path, e)
        return dict(DEFAULT_ROLES), dict(DEFAULT_RULES)


def _normalize_role(role):
    if role == "剪辑组长":
        return "剪辑组长"
    if role == "一卡剪辑":
        return "一卡剪辑"
    if role == "小组长":
        return "一卡剪辑"  # 小组长按一卡口径
    return "二卡剪辑" if role == "二卡剪辑" else "剪辑助理"


def compute_commission_breakdown(editor_workload, month=None, cfg_path=None):
    """从剪辑师集数计算每人绩效+提成。

    editor_workload: [{'name','assigned','projects'}]（来自 aggregate_editor_workload）
    返回:
      rows: [{'name','role','episodes','quota','is_complete','overtime_bonus',
              'shortage_penalty','group_bonus','commission','desc'}]
      summary: {'total_commission','total_people','met_quota','unmet_quota','total_episodes'}
    """
    roles, rules = load_config(cfg_path)
    rows = []
    for ed in editor_workload:
        name = ed.get("name") or ""
        total = int(ed.get("assigned") or 0)
        role = _normalize_role(roles.get(name, "剪辑助理"))
        rule = rules.get(role, rules.get("剪辑助理", DEFAULT_RULES["剪辑助理"]))
        if role == "剪辑组长":
            # 组长：集数×单价 + 组内每部×项目数（项目数取当月有分集的项目总数）
            project_count = int(ed.get("projects") or 0)
            group_bonus = project_count * int(rule.get("组内每部提成", 100) or 0)
            commission = total * int(rule.get("每集单价", 20) or 0) + group_bonus
            rows.append({
                "name": name, "role": role, "episodes": total,
                "quota": 0, "is_complete": True,
                "overtime_bonus": 0, "shortage_penalty": 0,
                "group_bonus": group_bonus, "project_count": project_count,
                "commission": commission, "desc": rule.get("提成构成描述", ""),
            })
        else:
            quota = int(rule.get("基准集数", 120) or 120)
            if total >= quota:
                overtime = (total - quota) * int(rule.get("超额每集", 20) or 0)
                rows.append({
                    "name": name, "role": role, "episodes": total,
                    "quota": quota, "is_complete": True,
                    "overtime_bonus": overtime, "shortage_penalty": 0,
                    "group_bonus": 0, "project_count": 0,
                    "commission": overtime, "desc": rule.get("提成构成描述", ""),
                })
            else:
                shortage = (quota - total) * int(rule.get("缺集每集扣", 50) or 0)
                rows.append({
                    "name": name, "role": role, "episodes": total,
                    "quota": quota, "is_complete": False,
                    "overtime_bonus": 0, "shortage_penalty": shortage,
                    "group_bonus": 0, "project_count": 0,
                    "commission": -shortage, "desc": rule.get("提成构成描述", ""),
                })
    rows.sort(key=lambda r: -r["commission"])
    summary = {
        "total_commission": sum(r["commission"] for r in rows),
        "total_people": len(rows),
        "met_quota": sum(1 for r in rows if r["is_complete"]),
        "unmet_quota": sum(1 for r in rows if not r["is_complete"]),
        "total_episodes": sum(r["episodes"] for r in rows),
    }
    return rows, summary
