# -*- coding: utf-8 -*-
"""剪辑师个人视图 / 离线只读缓存 的统一数据接口。"""
import os
from datetime import datetime
from flask import jsonify, request


def _completed_dir_names(sync_engine):
    """返回组内 NAS 00已完成 目录下的项目名集合。
    用于把"被手动归档（移入 00已完成 文件夹）但 DB 状态为空"的项目视为已完成。
    """
    try:
        if not sync_engine:
            return set()
        nas = sync_engine.config.get("nas", {}) if isinstance(sync_engine.config, dict) else {}
        gr = nas.get("group_root", "")
        if not gr:
            return set()
        comp_root = os.path.join(gr, "00已完成")
        if not os.path.isdir(comp_root):
            return set()
        return set(os.listdir(comp_root))
    except Exception:
        return set()


def register_routes(app, db, sync_engine=None):
    # ================================================================
    # 剪辑师个人视图
    # ================================================================
    @app.route("/api/editor/view", methods=["GET"])
    def api_editor_view():
        """返回按剪辑师聚合的项目 + 集数进度视图。
        结构: { ok, editors: [ { name, projects:[ {project, episodes(该剪辑师负责集), done, missing, status, total} ] } ] }
        若指定 ?editor= 只返回该剪辑师。
        """
        editor_filter = (request.args.get("editor") or "").strip()
        projects = db.get_all_projects()
        # 一次性获取 00已完成 目录下的项目名集合，用于把"被手动归档但状态为空"的项目显示为已完成
        completed_names = _completed_dir_names(sync_engine)
        by_editor = {}
        for p in projects:
            name = p.get("name") or ""
            plan = db.get_episode_plan(name)
            if not plan:
                continue
            # 该剪辑师负责的集号
            eps_by_editor = {}
            for ep, ed in plan.items():
                ed = str(ed or "").strip()
                if not ed:
                    continue
                eps_by_editor.setdefault(ed, []).append(int(ep))
            # 已输出集号（扫描成片目录）
            present = set()
            if sync_engine:
                try:
                    st = sync_engine.get_episode_status(name)
                    if st and st.get("ok"):
                        present = set(st.get("present") or [])
                except Exception:
                    present = set()
            # 状态：若项目在 00已完成 目录（被手动归档）但 DB 状态为空，则显示为已完成
            status = p.get("custom_status") or ""
            if not status and name in completed_names:
                status = "已完成"
            total = int(p.get("total_episodes") or 0)
            for ed, eps in eps_by_editor.items():
                eps_sorted = sorted(set(eps))
                done = [e for e in eps_sorted if e in present]
                missing = [e for e in eps_sorted if e not in present]
                item = {
                    "project": name,
                    "episodes": eps_sorted,
                    "done": done,
                    "missing": missing,
                    "done_count": len(done),
                    "total_count": len(eps_sorted),
                    "status": status,
                    "project_total": total,
                }
                by_editor.setdefault(ed, []).append(item)
        editors = []
        for ed, items in by_editor.items():
            if editor_filter and ed != editor_filter:
                continue
            items.sort(key=lambda x: x["project"])
            editors.append({
                "name": ed,
                "project_count": len(items),
                "episode_count": sum(i["total_count"] for i in items),
                "done_count": sum(i["done_count"] for i in items),
                "projects": items,
            })
        editors.sort(key=lambda x: x["name"])
        return jsonify({"ok": True, "editors": editors})

    @app.route("/api/editor/backfill_completed", methods=["POST"])
    def api_editor_backfill_completed():
        """一键补齐：把位于组内 NAS 00已完成 目录、但 DB custom_status 为空的项目，
        状态补写为「已完成」，使首页/剪辑师/看板口径一致。
        返回补齐的项目数。
        """
        completed_names = _completed_dir_names(sync_engine)
        if not completed_names:
            return jsonify({"ok": True, "updated": 0, "message": "00已完成 目录不存在或无项目"})
        projects = db.get_all_projects()
        updated = 0
        for p in projects:
            name = p.get("name") or ""
            if name not in completed_names:
                continue
            cur = (p.get("custom_status") or "").strip()
            if cur:
                continue
            # 仅当确实为空时补写为已完成
            db.update_project_status(name, custom_status="已完成")
            try:
                db.add_audit_log(name, "补齐已完成状态", "00已完成 目录项目状态补齐")
            except Exception:
                pass
            updated += 1
        return jsonify({"ok": True, "updated": updated,
                        "message": "已补齐 %d 个已完成项目状态" % updated})

    # ================================================================
    # 离线只读缓存
    # ================================================================
    @app.route("/api/offline/cache", methods=["GET"])
    def api_offline_cache():
        """返回用于离线只读缓存的打包数据：项目列表 + 待办 + 分集计划。"""
        projects = db.get_all_projects()
        proj_list = []
        for p in projects:
            name = p.get("name") or ""
            proj_list.append({
                "name": name,
                "custom_status": p.get("custom_status") or "",
                "delivery_status": p.get("delivery_status") or "",
                "department": p.get("department") or "",
                "project_month": p.get("project_month") or "",
                "total_episodes": p.get("total_episodes") or 0,
                "current_episodes": p.get("current_episodes") or 0,
                "episode_plan": db.get_episode_plan(name),
                "due_date": p.get("due_date") or "",
                "delivered_date": p.get("delivered_date") or "",
            })
        # 待办
        todos = db.get_all_todos(include_done=True) or []
        return jsonify({
            "ok": True,
            "cached_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "projects": proj_list,
            "todos": todos,
        })
