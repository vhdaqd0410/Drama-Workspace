# -*- coding: utf-8 -*-
"""集号识别（episode number extraction）单源模块。

从成片文件名中稳健地提取集号，供 deliver.py / preview.py 等多处共用。
此前该逻辑散落在 DeliverMixin 里，与大量文件回传方法混在一起；抽离后
集号识别规则只此一处，避免正则/口径漂移（对应 ROADMAP：统一集号解析）。

纯函数、无文件系统副作用，便于单元测试。
"""
import os
import re

# 集号识别优先级（索引越小越优先）：
#   EP12 / EP_12 / EP-12 / ep12        → 显式 EP 前缀
#   S01E12 / s1e12                      → 季集
#   第12集 / 第12话                      → 中文"第X集"
#   独立数字（_12_ / -12- / .12. / 12$） → 兜底纯数字
EP_PATTERNS = [
    re.compile(r'(?i)(?:^|[^a-z0-9])EP[_\s\-]?(\d{1,3})(?!\d)'),
    re.compile(r'(?i)(?:^|[^a-z0-9])S\d{1,2}E[_\s\-]?(\d{1,3})(?!\d)'),
    re.compile(r'第[_\s\-]*(\d{1,3})[集话]'),
    re.compile(r'(?:[_\-\s]|^)(\d{1,3})(?:[_\-\s\.]|$)'),
]


def extract_episode_number(filename):
    """从单个文件名里提取集号，失败返回 None。

    按 EP_PATTERNS 优先级取第一个命中；同 pattern 一个文件名只取一次，
    避免一个文件名里出现多个独立数字时误判。
    """
    base = os.path.splitext(filename)[0]
    hits = []
    for idx, pat in enumerate(EP_PATTERNS):
        for m in pat.finditer(base):
            try:
                n = int(m.group(1))
            except (TypeError, ValueError):
                continue
            if 1 <= n <= 999:
                hits.append((idx, n))
                break  # 每个 pattern 最多取一次匹配
    if not hits:
        return None
    # 优先级：pattern 索引越小越优先
    hits.sort(key=lambda x: x[0])
    return hits[0][1]


def editor_for_filename(filename, editor_map):
    """根据文件名提取集号，并从 {集号:剪辑师} 映射中返回该集剪辑师。
    集号匹配失败或无映射时返回 ''。editor_map 为空时跳过，避免无谓计算。"""
    if not editor_map:
        return ""
    n = extract_episode_number(filename)
    if n is None:
        return ""
    return editor_map.get(str(n), "")
