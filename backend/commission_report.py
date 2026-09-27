# -*- coding: utf-8 -*-
"""月度提成报表生成服务（工作台内直接产出最终提成表）。

目标：不再需要打开独立提成工具，工作台里选月份即可导出这张最终报表。

数据来源优先级：
  1) 提成工具输入的项目文件（plugins/commission/config.json → app_settings.project_file，
     即工作台 data/fenji_targets/一组AI项目-<月>.xlsx）。它是提成工具原本的输入，
     表头/交片时间/分集格式与该工具完全一致，用它生成可保证口径一致。
  2) 找不到对应月份的项目文件时，回退用工作台 DB 的 episode_plan 现构一张等价的项目表。

生成逻辑复用 plugins/commission/src/generate_commission.py（不复制实现，避免两处漂移），
并按工作台的“月度最终报表”口径输出：
  - 主标题：制作部 + AI剪辑一组 + X月份 + 提成表
  - A列组别：AI剪辑一组
  - P列（超额提成）填提成合计数值；R列（提成合计）填计算过程公式
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

    # 组别与标题（工作台“月度最终报表”口径）
    # 标题：制作部 + AI剪辑一组 + X月份 + 提成表
    group_label = "AI剪辑一组"
    title = "制作部%s%s份提成表" % (group_label, cn_month)

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

    records, group_pids = gc.parse_projects(df, default_year=year)
    if not records:
        return {"ok": False, "error": "项目文件未解析到有效记录：%s" % os.path.basename(project_file)}
    commission_data = gc.compute_commission(records, group_pids)

    opts = {
        "title": title,
        "group_label": group_label,
        "swap_pr": True,
        "full_role": True,       # 职位列用完整角色名（一卡剪辑/二卡剪辑/剪辑助理/剪辑组长）
        "use_rule_desc": True,   # 提成构成用配置原值（不带硬编码后缀）
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
    }
