# -*- coding: utf-8 -*-
"""月度提成报表生成服务（工作台内直接产出最终提成表）。

目标：不再需要打开独立提成工具，工作台里选月份即可导出这张最终报表。

数据来源优先级：
  1) 提成工具输入的项目文件（plugins/commission/config.json → app_settings.project_file，
     即工作台 data/fenji_targets/一组AI项目-<月>.xlsx）。它是提成工具原本的输入，
     表头/交片时间/分集格式与该工具完全一致，用它生成可保证口径一致。
  2) 找不到对应月份的项目文件时，回退用工作台 DB 的 episode_plan 现构一张等价的项目表。

生成逻辑复用 plugins/commission/src/generate_commission.py（不复制实现，避免两处漂移），
并按最新模板「AI后期剪辑提成表模板.xlsx」的月度最终报表口径输出：
  - 主标题：后期剪辑部 + YYYY年MM月 + 剪辑X组 + 提成表
  - A列组别：AI剪辑一组
  - O列（任务未完成扣除金额）填计算过程（未达标时）
  - P列（任务超额提成金额）填计算过程（达标时）
  - R列（提成合计）填数值
"""
import os
import re
import sys
import json
import logging
import datetime

logger = logging.getLogger("commission_report")

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PLUGIN_DIR = os.path.join(_BASE, "plugins", "commission")
_PLUGIN_SRC = os.path.join(_PLUGIN_DIR, "src")
_PLUGIN_CFG = os.path.join(_PLUGIN_DIR, "config.json")

_CN_MONTHS = ['', '一月', '二月', '三月', '四月', '五月', '六月',
              '七月', '八月', '九月', '十月', '十一月', '十二月']


def _load_plugin_cfg():
    try:
        with open(_PLUGIN_CFG, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception as e:
        logger.warning("读取提成插件配置失败: %s", e)
        return {}


def _plugin_module():
    """导入插件的生成模块（复用其全部解析/计算/写表逻辑）。"""
    if _PLUGIN_SRC not in sys.path:
        sys.path.insert(0, _PLUGIN_SRC)
    import generate_commission as gc  # type: ignore
    return gc


def _resolve_project_file(month, db=None):
    """找到指定月份对应的项目文件（提成工具输入）。

    month: 'YYYY-MM'。
    优先 config.json 的 app_settings.project_file（若月份匹配），
    否则在 data/fenji_targets 下按月份中文名/数字找。
    返回绝对路径或 ''。
    """
    if not month:
        return ""
    try:
        y, m = month.split("-")
        m_num = int(m)
    except Exception:
        return ""
    cn = _CN_MONTHS[m_num] if 1 <= m_num <= 12 else ""

    cfg = _load_plugin_cfg()
    pf = ((cfg.get("app_settings") or {}).get("project_file") or "").strip()
    # 归一化路径（配置里可能是正斜杠）
    pf_norm = os.path.normpath(pf) if pf else ""
    if pf_norm and os.path.isfile(pf_norm):
        # 判断该文件月份是否匹配（文件名含 中文月份 或 YYYY-MM 或 数字月）
        base = os.path.basename(pf_norm)
        if (cn and cn in base) or (month in base) or re.search(r"(%d)\s*月" % m_num, base):
            return pf_norm

    # 回退：在 fenji_targets 目录里找该月份的项目文件
    targets_dir = os.path.join(_BASE, "data", "fenji_targets")
    if os.path.isdir(targets_dir):
        cands = []
        for fn in os.listdir(targets_dir):
            if not fn.lower().endswith((".xlsx", ".xls")):
                continue
            if fn.startswith("~$"):
                continue
            if (cn and cn in fn) or re.search(r"(%d)\s*月" % m_num, fn) or ("%s-%s" % (y, m) in fn):
                cands.append(os.path.join(targets_dir, fn))
        if cands:
            # 优先“项目”文件（含“项目”），其次修改时间最新
            cands.sort(key=lambda p: (("项目" not in os.path.basename(p)),
                                      -os.path.getmtime(p)))
            return cands[0]
    return ""


def validate_report_data(records, df, project_file, db=None, month=None):
    """按「提成表填写注意事项」校验数据，返回问题列表 issues（每条为可读字符串）。

    校验项：
      1) 项目ID不能出现错误（非空、可提取）
      2) 项目名字统一（同一ID不出现两个名字）
      3) 同一项目的集数不同时出现在两个人列表里（不重叠）
      4) 项目日期准确（有交付日期且可解析）
      5) 每人集数与后台（工作台 DB episode_plan）一致，且无重复
    """
    import re as _re
    from collections import defaultdict as _dd
    issues = []

    # ---- 2) 同一ID多个名字；1) ID 可用性 ----
    id2names = _dd(set)
    id2proj = _dd(set)
    for r in records:
        pid = r.get("项目ID") or ""
        nm = r.get("AI项目名称") or ""
        if not pid:
            issues.append("项目ID缺失：%s" % nm)
        id2names[pid].add(nm)
        id2proj[nm].add(pid)
    for pid, names in id2names.items():
        if pid and len(names) > 1:
            issues.append("同一项目ID %s 出现多个名称：%s" % (pid, " / ".join(sorted(names))))
    for nm, pids in id2proj.items():
        if len(pids) > 1:
            issues.append("同名项目 %s 对应多个ID：%s" % (nm, " / ".join(sorted(pids))))

    # ---- 3) 同项目集数跨人不重叠；5) 重复 ----
    proj_eps = _dd(lambda: _dd(set))  # 项目名 -> 人 -> 集号集合
    for r in records:
        if not r.get("参与剪辑", True):
            continue
        nm = r.get("AI项目名称") or ""
        person = r.get("身份证姓名") or ""
        eps = set()
        for e in str(r.get("完成明细") or "").split(","):
            if e.strip().isdigit():
                eps.add(int(e.strip()))
        proj_eps[nm][person] |= eps
    for nm, persons in proj_eps.items():
        seen = {}
        for person, eps in persons.items():
            for e in eps:
                if e in seen and seen[e] != person:
                    issues.append("重叠：项目 %s 第%d集 同时给了 %s 和 %s" % (nm, e, seen[e], person))
                seen[e] = person

    # ---- 4) 日期准确 ----
    for r in records:
        if r.get("参与剪辑", True) and not r.get("结束日期"):
            issues.append("项目 %s 缺交付日期" % (r.get("AI项目名称")))

    # ---- 5) 与后台（工作台 DB episode_plan）逐人集数比对 ----
    if db is not None and month:
        db_map = {}
        try:
            for p in db.get_all_projects():
                if (p.get("project_month") or "") == month:
                    plan = p.get("episode_plan") or "{}"
                    try:
                        plan = json.loads(plan) if isinstance(plan, str) else plan
                    except Exception:
                        plan = {}
                    db_map[p.get("name")] = {int(k): v for k, v in plan.items() if v}
        except Exception as e:
            logger.warning("读取后台分集失败: %s", e)
        if db_map:
            for nm, persons in proj_eps.items():
                if nm not in db_map:
                    continue
                db_by_person = _dd(set)
                for ep, who in db_map[nm].items():
                    db_by_person[who].add(int(ep))
                names = set(persons) | set(db_by_person)
                for person in names:
                    f_eps = persons.get(person, set())
                    d_eps = db_by_person.get(person, set())
                    if f_eps != d_eps:
                        only_f = sorted(f_eps - d_eps)
                        only_d = sorted(d_eps - f_eps)
                        detail = []
                        if only_f:
                            detail.append("表多出%s" % only_f[:15])
                        if only_d:
                            detail.append("表缺少%s" % only_d[:15])
                        issues.append("集数不符：项目 %s / %s：%s（与后台不一致）" % (nm, person, "，".join(detail)))
    return issues


def _load_domestic_projects(db, month=None):
    """读工作台 DB 中标了「国内」（is_domestic=1）的项目，返回 (ids, names)。"""
    ids, names = set(), set()
    if db is None:
        return ids, names
    try:
        for p in db.get_all_projects():
            if month and (p.get("project_month") or "") and (p.get("project_month") or "") != month:
                continue
            if int(p.get("is_domestic") or 0) == 1:
                nm = (p.get("name") or "").strip()
                if nm:
                    names.add(nm)
                    import re as _re
                    nums = [m for m in _re.findall(r"\d+", nm) if not m.startswith("0")]
                    if nums:
                        ids.add(max(nums, key=lambda x: (len(x), int(x))))
    except Exception as e:
        logger.warning("读取国内标记项目失败: %s", e)
    return ids, names


def _load_resigned_members(db):
    """读团队表里填了离职日期（resign_date）的成员，返回 {姓名: 日期}。

    同时并入已归档的离职成员（团队表里已被次月清理掉、但历史报表仍需标注的），
    在册数据优先（同名以当前在册值为准）。
    """
    out = {}
    if db is None:
        return out
    # 1) 归档（先取，随后被在册数据覆盖）
    try:
        if hasattr(db, "get_resigned_archive"):
            out.update(db.get_resigned_archive() or {})
    except Exception as e:
        logger.warning("读离职成员归档失败: %s", e)
    # 2) 在册成员里带离职日期的
    try:
        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT name, resign_date FROM team_members "
                "WHERE resign_date IS NOT NULL AND resign_date != ''"
            ).fetchall()
        for r in rows:
            try:
                d = dict(r) if not isinstance(r, dict) else r
                nm = (d.get("name") or "").strip()
                rd = (d.get("resign_date") or "").strip()
            except Exception:
                try:
                    nm = (r[0] or "").strip(); rd = (r[1] or "").strip()
                except Exception:
                    continue
            if nm and rd:
                out[nm] = rd
    except Exception as e:
        logger.warning("读取离职成员失败: %s", e)
    return out


def build_report(month, output_dir=None, db=None):
    """生成月度提成表，返回 {ok, path, month, title, records, people, projects, error}。

    month: 'YYYY-MM'
    output_dir: 输出目录（默认桌面）
    """
    if not month:
        return {"ok": False, "error": "缺少月份"}
    try:
        y_str, m_str = month.split("-")
        year, m_num = int(y_str), int(m_str)
    except Exception:
        return {"ok": False, "error": "月份格式应为 YYYY-MM"}

    gc = _plugin_module()
    import pandas as pd

    project_file = _resolve_project_file(month, db=db)
    if not project_file:
        return {"ok": False, "error": "未找到 %s 对应的项目文件（%s月），请先在分集页确认数据"
                % (month, m_num)}

    # 读项目表 → 解析
    df = pd.read_excel(project_file, header=None)
    # 用数据文件真实月份覆盖（与插件 main() 一致）
    data_cn, data_month_num = gc.get_month_from_data(df)
    cn_month = data_cn if data_cn else _CN_MONTHS[m_num]
    out_month_num = data_month_num if data_month_num else m_num

    # 组别与标题（最新模板口径）
    # 主标题：后期剪辑部 + YYYY年MM月 + 剪辑一组 + 提成表
    #         （模板 B1 为「后期剪辑部2026年09月剪辑X组提成表」，X→一）
    # A列组别：AI剪辑一组（模板 A4 为「A\nI\n剪\n辑\nx\n组」）
    group_label = "AI剪辑一组"
    title = "后期剪辑部%04d年%02d月剪辑一组提成表" % (year, out_month_num)

    # 输出文件
    if not output_dir:
        output_dir = os.path.join(os.path.expanduser("~"), "Desktop")
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "AI后期剪辑提成一组%s.xlsx" % cn_month)

    # 覆盖前先备份（同名旧报表可能已有手工调整）
    if os.path.isfile(out_path):
        try:
            import shutil as _shutil
            bak_dir = os.path.join(_PLUGIN_DIR, "backup")
            os.makedirs(bak_dir, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            _shutil.copy2(out_path, os.path.join(
                bak_dir, "%s_%s.xlsx" % (os.path.splitext(os.path.basename(out_path))[0], stamp)))
        except Exception as _be:
            logger.warning("备份旧提成表失败: %s", _be)

    # 模板
    tpl = os.path.join(_PLUGIN_DIR, "data", "AI后期剪辑提成一组模板.xlsx")
    if not os.path.isfile(tpl):
        tpl = os.path.join(_PLUGIN_DIR, "AI后期剪辑提成一组最新.xlsx")
    if not os.path.isfile(tpl):
        return {"ok": False, "error": "找不到提成表模板（AI后期剪辑提成一组模板.xlsx）"}

    # 让插件模块的全局月份/年份与数据一致（影响标题回落、日期解析）
    try:
        gc.TEMPLATE_DATE = "%04d年%02d月" % (year, out_month_num)
        gc.TEMPLATE_YEAR = year
        gc.OUTPUT_MONTH = cn_month
    except Exception:
        pass

    # 工作台数据传导：国内标记（项目类型→AI真人）、离职成员（标红+备注）
    dom_ids, dom_names = _load_domestic_projects(db, month=month)
    resigned = _load_resigned_members(db)

    records, group_pids = gc.parse_projects(df, default_year=year,
                                            domestic_ids=dom_ids, domestic_names=dom_names)
    if not records:
        return {"ok": False, "error": "项目文件未解析到有效记录：%s" % os.path.basename(project_file)}

    # 按「提成表填写注意事项」校验数据（不阻断生成，但把问题带回前端提示）
    issues = []
    try:
        issues = validate_report_data(records, df, project_file, db=db, month=month)
    except Exception as _ve:
        logger.warning("提成表数据校验异常: %s", _ve)
    if issues:
        logger.warning("提成表数据校验发现 %d 处问题", len(issues))

    commission_data = gc.compute_commission(records, group_pids)

    opts = {
        "title": title,
        "group_label": group_label,
        "full_role": False,      # 职位列显示 组长/卡前/卡后（三种口径）
        "use_rule_desc": True,   # 提成构成用配置原值（不带硬编码后缀）
        "highlight_roles": ["一卡剪辑"],  # 本月卡前（一卡剪辑）规则一律全标黄
        "resigned": resigned,            # {姓名: 离职日期}，命中者标红+备注写离职日期
    }
    # 只产出这张 xlsx（不生成仪表盘 HTML，避免桌面多余文件）
    _orig_html = getattr(gc, "generate_html_dashboard", None)
    try:
        gc.generate_html_dashboard = lambda *a, **k: ""
    except Exception:
        pass
    try:
        final_path, html_path = gc.generate_excel(
            records, commission_data, tpl, out_path, auto_open=False, opts=opts)
    finally:
        if _orig_html is not None:
            try:
                gc.generate_html_dashboard = _orig_html
            except Exception:
                pass
    # A列（组别）列宽确保“AI剪辑一组”不竖排
    try:
        from openpyxl import load_workbook
        _wb = load_workbook(final_path)
        _ws = _wb["Sheet1"] if "Sheet1" in _wb.sheetnames else _wb.active
        if (_ws.column_dimensions["A"].width or 0) < 14:
            _ws.column_dimensions["A"].width = 14
        _wb.save(final_path)
    except Exception as _we:
        logger.warning("调整组别列宽失败: %s", _we)

    people = [r for r in gc.NAME_ORDER if r in commission_data]
    projects = len({r["项目ID"] for r in records if r.get("项目ID")})
    subtotal = sum(cd.get("total_commission", 0) for cd in commission_data.values())
    return {
        "ok": True,
        "path": final_path,
        "html": html_path,
        "month": month,
        "cn_month": cn_month,
        "title": title,
        "source_file": project_file,
        "people": len(people),
        "projects": projects,
        "records": len(records),
        "total_commission": subtotal,
        "issues": issues,
        "issue_count": len(issues),
    }
