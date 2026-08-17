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
        groups = cfg.get("小组", {}) or {}
        return roles, rules, groups
    except Exception as e:
        logger.warning("读取提成配置失败(%s)，使用内置默认: %s", path, e)
        return dict(DEFAULT_ROLES), dict(DEFAULT_RULES), {}


def _normalize_role(role):
    if role == "剪辑组长":
        return "剪辑组长"
    if role == "一卡剪辑":
        return "一卡剪辑"
    if role == "小组长":
        return "一卡剪辑"  # 小组长按一卡口径
    return "二卡剪辑" if role == "二卡剪辑" else "剪辑助理"


def editor_quota_map(cfg_path=None):
    """返回 {剪辑师姓名: {'role': 角色, 'quota': 基准集数}}，用于工作量看板标注卡点。
    组长无基准(0)；其余按角色基准。"""
    roles, rules, groups = load_config(cfg_path)
    out = {}
    for name, role_raw in roles.items():
        role = _normalize_role(role_raw)
        if role == "剪辑组长":
            out[name] = {"role": role, "quota": 0}
        else:
            rule = rules.get(role, rules.get("剪辑助理", DEFAULT_RULES["剪辑助理"]))
            out[name] = {"role": role, "quota": int(rule.get("基准集数", 120) or 120)}
    return out


def compute_commission_breakdown(editor_workload, month=None, cfg_path=None,
                                 group_completed_count=None):
    """从剪辑师集数计算每人绩效+提成。

    editor_workload: [{'name','assigned','projects'}]（来自 aggregate_editor_workload）
    group_completed_count: {组长姓名: 组内当月完成部数}（功能3：组长组奖按组内全部完成部数计）。
                          若不传，组长按"有分集的项目数"计。
    返回:
      rows: [{'name','role','episodes','quota','is_complete','overtime_bonus',
              'shortage_penalty','group_bonus','commission','desc'}]
      summary: {'total_commission','total_people','met_quota','unmet_quota','total_episodes'}
    """
    roles, rules, groups = load_config(cfg_path)
    rows = []
    for ed in editor_workload:
        name = ed.get("name") or ""
        total = int(ed.get("assigned") or 0)
        role = _normalize_role(roles.get(name, "剪辑助理"))
        rule = rules.get(role, rules.get("剪辑助理", DEFAULT_RULES["剪辑助理"]))
        if role == "剪辑组长":
            # 功能3：组长组奖 = 组内当月完成部数 × 每部提成
            # 优先用传入的组内完成部数（数据来源=项目看板本月项目），否则回退到有分集的项目数
            project_count = int(group_completed_count.get(name) if group_completed_count else ed.get("projects") or 0)
            if not project_count:
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


def compute_group_completed(db, month=None, cfg_path=None):
    """功能3：统计每个组长所在组的当月部数（组长组奖基准）。

    口径与项目看板「本月项目」一致：统计 project_month==当月 的所有项目
    （不限定状态），凡该组任一成员出现在该项目 episode_plan 中即计入该组。
    数据来源 = 本月项目（项目看板本月项目里是多少就是多少）。
    返回 {组长姓名: 部数}。
    """
    import json as _json
    from datetime import datetime
    if not month:
        month = datetime.now().strftime("%Y-%m")
    roles, rules, groups = load_config(cfg_path)
    # 组长 -> 成员集合
    leader_members = {}
    for gname, g in (groups or {}).items():
        leader = (g.get("组长") or "").strip()
        members = set(g.get("成员") or [])
        if leader and members:
            leader_members[leader] = members
    try:
        projs = db.get_all_projects() or []
    except Exception:
        projs = []
    result = {leader: 0 for leader in leader_members}
    for p in projs:
        if (p.get("project_month") or "") != month:
            continue
        plan = p.get("episode_plan") or "{}"
        try:
            plan = _json.loads(plan) if isinstance(plan, str) else plan
        except Exception:
            plan = {}
        if not isinstance(plan, dict):
            continue
        editors = set(e for e in plan.values() if e)
        for leader, members in leader_members.items():
            if editors & members:
                result[leader] = result.get(leader, 0) + 1
    return result


def compute_person_cards(db, year=None, cfg_path=None):
    """个人工作量卡片（功能2）：每人年度逐月集数 + 角色 + 汇总。

    db: 项目数据库
    year: 如 '2026'；默认当前年。
    返回 [{'name','role','annual_total','month_count','best_month','best_eps',
            'monthly': {'2026-01': n, ...}}]
    """
    from datetime import datetime
    from collections import defaultdict
    if not year:
        year = str(datetime.now().year)
    roles, _rules, _groups = load_config(cfg_path)
    # 逐月集数
    monthly = defaultdict(lambda: defaultdict(int))  # name -> month -> eps
    try:
        projs = db.get_all_projects() or []
    except Exception:
        projs = []
    for p in projs:
        pm = (p.get("project_month") or "").strip()
        if not pm.startswith(year):
            continue
        plan = p.get("episode_plan") or ""
        if not plan or plan == "{}":
            continue
        try:
            plan = json.loads(plan) if isinstance(plan, str) else plan
        except Exception:
            continue
        if not isinstance(plan, dict):
            continue
        for _ep, ed in plan.items():
            if ed and str(ed).strip():
                monthly[str(ed).strip()][pm] += 1
    # 汇总
    cards = []
    for name, by_month in monthly.items():
        total = sum(by_month.values())
        best_month = max(by_month, key=lambda m: by_month[m]) if by_month else None
        cards.append({
            "name": name,
            "role": _normalize_role(roles.get(name, "剪辑助理")),
            "annual_total": total,
            "month_count": len(by_month),
            "best_month": best_month,
            "best_eps": by_month.get(best_month, 0) if best_month else 0,
            "monthly": dict(by_month),
        })
    cards.sort(key=lambda c: -c["annual_total"])
    return {"year": year, "cards": cards}
