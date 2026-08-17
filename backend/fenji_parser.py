# -*- coding: utf-8 -*-
"""分集目标解析 — 统一「剪辑师：集数范围」字符串解析，消除多份重复实现。

此前该逻辑在 fenji.py / features.py / enhanced_routes.py 各写一份，
且正则存在分歧（是否含 '+'、全角 '；'），导致同一行在不同入口解析结果不同。
本模块为唯一实现，各调用方统一从这里取。
"""
import re

# 分隔符：英文逗号、全角逗号、顿号、分号(半/全角)、加号、空白
_SEP_RE = re.compile(r'[,，、;；+\s]+')
# 范围：如 1-3 / 10—15 / 4~7
_RANGE_RE = re.compile(r'^(\d+)\s*[-—~]\s*(\d+)$')
# 单个集号：如 5
_SINGLE_RE = re.compile(r'^(\d+)$')


def parse_assign_line(plan, line):
    """解析一行 '剪辑师：1-3，44-45' 加入 plan 字典（{集号str: 剪辑师}）。

    plan 会被原地更新（多个剪辑师行叠加到同一项目）；重叠集号后者覆盖前者。
    无法解析（缺剪辑师名/缺范围）时静默跳过。
    """
    line = (line or "").strip()
    if '：' in line:
        parts = line.split('：', 1)
    elif ':' in line:
        parts = line.split(':', 1)
    else:
        return
    if len(parts) < 2:
        return
    editor = parts[0].strip()
    ranges = parts[1].strip()
    if not editor or not ranges:
        return
    for r in _SEP_RE.split(ranges):
        r = r.strip()
        if not r:
            continue
        m = _RANGE_RE.match(r)
        if m:
            s, e = int(m.group(1)), int(m.group(2))
            for ep in range(min(s, e), max(s, e) + 1):
                plan[str(ep)] = editor
            continue
        m2 = _SINGLE_RE.match(r)
        if m2:
            plan[m2.group(1)] = editor


def expand_ranges(ranges):
    """展开一段范围文本（可含多个范围，逗号/分号分隔）为集号集合。

    例：'4-7,21-25' -> {4,5,6,7,21,22,23,24,25}。用于独立计数（不去重、不与其他行交互）。
    """
    eps = set()
    for r in _SEP_RE.split(ranges or ''):
        r = r.strip()
        if not r:
            continue
        m = _RANGE_RE.match(r)
        if m:
            s, e = int(m.group(1)), int(m.group(2))
            eps.update(range(min(s, e), max(s, e) + 1))
        elif _SINGLE_RE.match(r):
            eps.add(int(r))
    return eps
