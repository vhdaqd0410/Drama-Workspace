# -*- coding: utf-8 -*-
"""Shared utility functions used across backend modules."""
import os


def scan_dir(path, skip_names=None, recursive_depth=0):
    """扫描目录获取项目文件夹，支持嵌套月份目录展开。

    - path: 起始目录
    - skip_names: 需要跳过的目录名列表
    - recursive_depth: 嵌套递归深度，0 表示不递归
    返回 [{"name": str, "path": str}, ...]
    """
    skip = set(skip_names or [])
    skip.add('.DS_Store')
    skip.add('desktop.ini')
    if not os.path.isdir(path):
        return []
    results = []
    try:
        items = os.listdir(path)
    except Exception:
        return []
    for item in sorted(items):
        if item in skip:
            continue
        full = os.path.join(path, item)
        if not os.path.isdir(full):
            continue
        if recursive_depth > 0:
            try:
                sub = os.listdir(full)
                has_sub = any(
                    os.path.isdir(os.path.join(full, s)) and not s.startswith('.')
                    for s in sub
                )
            except Exception:
                has_sub = False
            if has_sub:
                results.extend(scan_dir(full, skip, recursive_depth - 1))
                continue
        results.append({"name": item, "path": full})
    return results
