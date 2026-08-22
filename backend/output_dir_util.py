# -*- coding: utf-8 -*-
"""成片/交付目录名的统一解析工具。

此前成片输出目录名（01上映单集版）的解析逻辑在 sync.py(SyncMixin) 与 watcher.py(Watcher)
各有一份拷贝，且新增"项目级 output_dir_name 覆盖"后需两处同步修改，容易漂移。
本模块作为唯一事实来源，两个 Mixin / Watcher 均改为调用这里的函数。

优先级（成片输出目录名）：
    1. 项目级 projects.output_dir_name（成片详情里单独指定）
    2. special_projects[项目].output_dir_name
    3. 全局 config.output_dir_name（默认 01上映单集版）

交付目录名（delivery_folder）：
    1. 项目级 projects.delivery_folder（交付目录项目级覆盖，空 = 用全局）
    2. 全局 config.delivery_folder
"""
import os


def get_output_dir_name(db, config, project_name):
    """返回项目实际生效的成片输出目录名（目录名，非路径）。"""
    # 1. 项目级
    if project_name:
        try:
            proj = db.get_project(project_name) if db else None
            if proj:
                custom = (proj.get("output_dir_name") or "").strip()
                if custom:
                    return custom
        except Exception:
            pass
    # 2. special_projects 配置
    special_projects = {}
    if isinstance(config, dict):
        special_projects = config.get("special_projects", {}) or {}
    sp = special_projects.get(project_name) if project_name else None
    if isinstance(sp, dict) and (sp.get("output_dir_name") or "").strip():
        return sp.get("output_dir_name").strip()
    # 3. 全局默认
    if isinstance(config, dict):
        g = (config.get("output_dir_name") or "").strip()
        if g:
            return g
    return "01上映单集版"


def get_delivery_folder_name(db, config, project_name):
    """返回项目实际生效的交付目录名（默认 000交付，支持项目级覆盖）。"""
    if project_name:
        try:
            proj = db.get_project(project_name) if db else None
            if proj:
                custom = (proj.get("delivery_folder") or "").strip()
                if custom:
                    return custom
        except Exception:
            pass
    g = ""
    if isinstance(config, dict):
        g = (config.get("delivery_folder") or "").strip()
    if not g:
        g = "000交付"
    return os.path.basename(g.rstrip("\\/")) if g else "000交付"
