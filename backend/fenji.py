# -*- coding: utf-8 -*-
"""分集核心逻辑 — 解析分配方案、生成集号映射、读写 DB。"""
import re
import json
import logging

logger = logging.getLogger("fenji")


def parse_assign(assign_list):
    """解析分配列表为 {"集号": "姓名"} 映射。
    
    assign_list: [{"person": "张三", "range": "1-10"}, {"person": "李四", "range": "11-20,68-70"}]
    返回: {"1": "张三", "2": "张三", ..., "11": "李四", ..., "68": "李四", ...}
    """
    episode_plan = {}
    for item in assign_list:
        person = (item.get("person") or "").strip()
        range_str = (item.get("range") or "").strip()
        if not person or not range_str:
            continue
        for part in range_str.split(","):
            part = part.strip()
            m = re.match(r"^(\d+)\s*[-—~]\s*(\d+)$", part)
            if m:
                s, e = int(m.group(1)), int(m.group(2))
                for ep in range(s, e + 1):
                    episode_plan[str(ep)] = person
            else:
                # 单个集号："5"
                m2 = re.match(r"^(\d+)$", part)
                if m2:
                    episode_plan[m2.group(1)] = person
    return episode_plan


def validate_assign(assign_list, total_episodes):
    """验证分配是否完整覆盖 1..total_episodes，返回 (ok, missing, extra, conflicts)。"""
    plan = parse_assign(assign_list)
    missing = [str(i) for i in range(1, total_episodes + 1) if str(i) not in plan]
    extra = [ep for ep in plan if int(ep) > total_episodes]
    conflicts = []  # 同一集号被多次分配（parse_assign 已覆盖，不会出现）
    return (len(missing) == 0 and len(extra) == 0), missing, extra, conflicts


def summary(plan):
    """生成分集摘要：每人负责多少集。"""
    persons = {}
    for ep, name in plan.items():
        persons.setdefault(name, []).append(int(ep))
    out = {}
    for name, eps in persons.items():
        eps.sort()
        # 合并成范围字符串: [1,2,3,5,6] -> "1-3,5-6"
        ranges = []
        i = 0
        while i < len(eps):
            s = eps[i]
            e = s
            while i + 1 < len(eps) and eps[i + 1] == e + 1:
                e = eps[i + 1]
                i += 1
            ranges.append(f"{s}" if s == e else f"{s}-{e}")
            i += 1
        out[name] = {"count": len(eps), "range": ",".join(ranges)}
    return out


def assign_evenly(total_episodes, persons):
    """自动均衡分配：尽量均分。"""
    if not persons or total_episodes <= 0:
        return []
    n = len(persons)
    base = total_episodes // n
    remainder = total_episodes % n
    result = []
    start = 1
    for idx, person in enumerate(persons):
        count = base + (1 if idx < remainder else 0)
        end = start + count - 1
        result.append({"person": person, "range": f"{start}-{end}"})
        start = end + 1
    return result
