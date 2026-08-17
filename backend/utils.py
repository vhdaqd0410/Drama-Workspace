# -*- coding: utf-8 -*-
"""Shared utility functions used across backend modules."""
import os


def decode_output(data, fallback=None):
    """稳健地把子进程输出(bytes)解码为 str。

    统一编码处理（功能15）：Windows 上 cmd/robocopy 输出常为 GBK，
    ffmpeg/ffprobe 可能为 UTF-8 或本地代码页。先按候选编码逐个尝试解码，
    全部失败再回退到指定/系统编码，避免个别模块各自用 gbk/utf-8 造成乱码。
    fallback: 显式兜底编码（默认用系统首选编码）。
    """
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    candidates = ['utf-8', 'gbk', 'gb18030']
    if fallback and fallback not in candidates:
        candidates.append(fallback)
    for enc in candidates:
        try:
            return bytes(data).decode(enc)
        except (UnicodeDecodeError, ValueError):
            continue
    # 最后兜底：系统首选编码 + errors=replace（保证不抛异常）
    import locale
    try:
        sys_enc = fallback or locale.getpreferredencoding(False) or 'utf-8'
    except Exception:
        sys_enc = 'utf-8'
    return bytes(data).decode(sys_enc, errors='replace')


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
