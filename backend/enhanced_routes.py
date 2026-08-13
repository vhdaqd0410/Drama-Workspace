"""Additional routes for workbench enhancements."""
import os as _os
import re as _re
from flask import request, jsonify

def _register_enhanced_routes(app, db, qa_engine=None, sync_engine=None):
    @app.route("/api/project/<path:project_name>", methods=["GET"])
    def api_project_detail(project_name):
        p = None
        try:
            p = db.get_project(project_name)
        except Exception:
            pass
        if p:
            return jsonify({"ok": True, "project": p})
        search_roots = [
            (r"O:\AI漫剧剪辑一组", "group_path"),
            (r"N:\AI漫剧二部中转", "production_path"),
            (r"N:\AI漫剧一部中转\AI漫剧一部海外", "production_path"),
            (r"N:\AI漫剧九部中转\海外", "production_path"),
            (r"N:\AI漫剧六部中转", "production_path"),
            (r"O:\AI漫剧剪辑一组\00已完成", "group_path"),
        ]
        for root, path_key in search_roots:
            candidate = _os.path.join(root, project_name)
            if _os.path.isdir(candidate):
                proj = {
                    "name": project_name,
                    "production_path": candidate if path_key == "production_path" else "",
                    "group_path": candidate if path_key == "group_path" else "",
                    "custom_status": "",
                    "delivery_status": "",
                    "total_episodes": 0,
                    "current_episodes": 0,
                }
                return jsonify({"ok": True, "project": proj})
        return jsonify({"ok": False, "message": "项目不存在"}), 404

    @app.route("/api/project", methods=["POST"])
    def api_project_create():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"ok": False, "message": "项目名不能为空"}), 400
        try:
            db.upsert_project(
                name,
                production_path=data.get("production_path", ""),
                group_path=data.get("group_path", ""),
                source_root=data.get("source_root", ""),
            )
        except Exception as e:
            return jsonify({"ok": False, "message": str(e)}), 500
        return jsonify({"ok": True, "project": name})

    @app.route("/api/project/<path:project_name>", methods=["DELETE"])
    def api_project_delete(project_name):
        try:
            db.delete_project(project_name)
        except Exception as e:
            return jsonify({"ok": False, "message": str(e)}), 500
        return jsonify({"ok": True})

    @app.route("/api/project/<path:project_name>/qa_start", methods=["POST"])
    def api_qa_start(project_name):
        data = request.get_json(silent=True) or {}
        workers = int(data.get("workers", 4))
        project_path = data.get("project_path") or ""
        if not project_path:
            for root in [r"O:\AI漫剧剪辑一组", r"N:\AI漫剧二部中转",
                         r"N:\AI漫剧一部中转\AI漫剧一部海外",
                         r"N:\AI漫剧九部中转\海外", r"N:\AI漫剧六部中转"]:
                candidate = _os.path.join(root, project_name)
                if _os.path.isdir(candidate):
                    project_path = candidate
                    break
        if not project_path:
            return jsonify({"ok": False, "message": "找不到项目路径"}), 404
        if qa_engine is None:
            return jsonify({"ok": False, "message": "QA引擎未初始化"}), 500
        ok = qa_engine.run(project_path, project_name, workers=workers)
        return jsonify({"ok": ok})

    @app.route("/api/project/<path:project_name>/qa_cancel", methods=["POST"])
    def api_qa_cancel(project_name):
        if qa_engine:
            qa_engine.cancel(project_name)
        return jsonify({"ok": True})

    @app.route("/api/project/<path:project_name>/qa_status", methods=["GET"])
    def api_qa_status(project_name):
        if qa_engine is None:
            return jsonify({"ok": False})
        status = qa_engine.get_status(project_name)
        return jsonify({"ok": True, "status": status})

    @app.route("/api/project/<path:project_name>/qa_history", methods=["GET"])
    def api_qa_history(project_name):
        try:
            runs = db.list_qa_runs_for_project(project_name, limit=20)
            return jsonify({"ok": True, "runs": runs})
        except Exception as e:
            return jsonify({"ok": False, "message": str(e)}), 500

    @app.route("/api/projects/episode_summary", methods=["GET"])
    def api_episode_summary():
        result = {"ok": True, "projects": []}
        all_names = set()
        for it in _scan_dir(r"O:\AI漫剧剪辑一组", skip_names=["00已完成", "0000新人"]):
            all_names.add(it["name"])
        for cfg in [(r"N:\AI漫剧二部中转", ["00序列_ID_剧名"], 0),
                     (r"N:\AI漫剧一部中转\AI漫剧一部海外", ["AAA《xxxxxxxx》文件夹模板", "00序列_ID_剧名"], 0),
                     (r"N:\AI漫剧九部中转\海外", [], 1),
                     (r"N:\AI漫剧六部中转", [], 0)]:
            for it in _scan_dir(cfg[0], skip_names=cfg[1], recursive_depth=cfg[2]):
                all_names.add(it["name"])
        for name in all_names:
            try:
                p = db.get_project(name)
                if not p:
                    continue
                total = p.get("total_episodes") or 0
                current = p.get("current_episodes") or 0
                if total > 0 and current < total:
                    result["projects"].append({
                        "name": name, "total": total, "current": current,
                        "missing": total - current,
                    })
            except Exception:
                pass
        result["projects"].sort(key=lambda x: -x["missing"])
        return jsonify(result)

    @app.route("/api/team/members", methods=["GET"])
    def api_team_members_get():
        try:
            if hasattr(db, 'list_team_members'):
                members = db.list_team_members()
            elif hasattr(db, 'list_members'):
                members = db.list_members()
            else:
                members = []
            return jsonify({"ok": True, "members": members})
        except Exception as e:
            return jsonify({"ok": False, "message": str(e)}), 500

    @app.route("/api/team", methods=["GET"])
    def api_team_alias():
        """简洁别名，返回团队成员列表"""
        return api_team_members_get()

    @app.route("/api/team/members", methods=["POST"])
    def api_team_members_add():
        """添加成员"""
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        role = data.get("role") or "editor"
        title = data.get("title") or ""
        department = data.get("department") or ""
        if not name:
            return jsonify({"ok": False, "message": "姓名不能为空"}), 400
        try:
            db.add_member(name=name, role=role, title=title, department=department)
            return jsonify({"ok": True, "message": f"已添加 {name}"})
        except Exception as e:
            return jsonify({"ok": False, "message": str(e)}), 500

    @app.route("/api/team/members/<int:mid>", methods=["PUT"])
    def api_team_members_update(mid):
        """编辑成员：改名、改角色、改称号、改部门"""
        data = request.get_json(silent=True) or {}
        try:
            with db.get_conn() as conn:
                row = conn.execute("SELECT * FROM team_members WHERE id=?", (mid,)).fetchone()
                if not row:
                    return jsonify({"ok": False, "message": "成员不存在"}), 404
                old_name = row["name"]
            if "name" in data and data["name"].strip():
                new_name = data["name"].strip()
                with db.get_conn() as conn:
                    conn.execute("UPDATE team_members SET name=? WHERE id=?", (new_name, mid))
                old_name = new_name
            kwargs = {}
            if "role" in data and data["role"] in ("editor", "reviewer", "pm"):
                kwargs["role"] = data["role"]
            if "title" in data:
                kwargs["title"] = data["title"] or ""
            if "department" in data:
                kwargs["department"] = data["department"] or ""
            if kwargs:
                db.update_member(old_name, **kwargs)
            return jsonify({"ok": True, "message": "已更新"})
        except Exception as e:
            return jsonify({"ok": False, "message": str(e)}), 500

    @app.route("/api/team/members/<int:mid>", methods=["DELETE"])
    def api_team_members_delete(mid):
        """删除成员（按 id）"""
        try:
            with db.get_conn() as conn:
                row = conn.execute("SELECT name FROM team_members WHERE id=?", (mid,)).fetchone()
                if not row:
                    return jsonify({"ok": False, "message": "成员不存在"}), 404
                conn.execute("DELETE FROM team_members WHERE id=?", (mid,))
            return jsonify({"ok": True, "message": "已删除"})
        except Exception as e:
            return jsonify({"ok": False, "message": str(e)}), 500

    @app.route("/api/config", methods=["GET"])
    def api_config_get():
        try:
            import config as _cfg
            cfg = _cfg.load_config()
            return jsonify({"ok": True, "config": cfg})
        except Exception as e:
            return jsonify({"ok": False, "message": str(e)}), 500

    @app.route("/api/config", methods=["POST"])
    def api_config_save():
        data = request.get_json(silent=True) or {}
        try:
            import config as _cfg
            if hasattr(_cfg, 'save_config'):
                _cfg.save_config(data)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "message": str(e)}), 500

    @app.route("/api/project/<path:project_name>/episodes_status", methods=["GET"])
    def api_episodes_status(project_name):
        try:
            if sync_engine is None:
                return jsonify({"ok": False, "message": "sync_engine 不可用"}), 500
            result = sync_engine.get_episode_status(project_name)
            return jsonify(result)
        except Exception as e:
            return jsonify({"ok": False, "message": str(e)}), 500


    @app.route("/api/bulk/import_episodes", methods=["POST"])
    def api_bulk_import_episodes():
        """接收前端分集结果，保存到 DB。"""
        body = request.get_json(silent=True) or {}
        project_name = body.get("project_name") or ""
        total = int(body.get("total_episodes") or 0)
        assign = body.get("assign") or {}
        if not project_name:
            return jsonify({"ok": False, "message": "缺少 project_name"}), 400
        if not isinstance(assign, dict) or len(assign) == 0:
            return jsonify({"ok": False, "message": "assign 为空"}), 400
        try:
            db.set_episode_plan(project_name, assign)
            if total > 0:
                p = db.get_project(project_name)
                cur = int((p or {}).get("current_episodes") or 0)
                db.set_episodes(project_name, total, cur)
            return jsonify({"ok": True, "message": "已保存 " + str(len(assign)) + " 集分集", "count": len(assign)})
        except Exception as e:
            return jsonify({"ok": False, "message": str(e)}), 500

    @app.route("/api/project/<path:project_name>/episodes_plan", methods=["GET"])
    def api_episodes_plan(project_name):
        """读取项目的分集 plan。"""
        try:
            plan = db.get_episode_plan(project_name)
            p = db.get_project(project_name) or {}
            total = int(p.get("total_episodes") or 0)
            return jsonify({"ok": True, "plan": plan, "total_episodes": total, "summary": {}})
        except Exception as e:
            return jsonify({"ok": False, "message": str(e)}), 500

    @app.route("/api/fenji/suggest", methods=["GET"])
    def api_fenji_suggest():
        """自动建议均分方案。"""
        total = int(request.args.get("total") or 0)
        count = int(request.args.get("count") or 0)
        if total <= 0 or count <= 0:
            return jsonify({"ok": False, "message": "参数错误"}), 400
        per = total // count
        rem = total % count
        ranges = []
        cur = 1
        for i in range(count):
            sz = per + (1 if i < rem else 0)
            ranges.append({"start": cur, "end": cur + sz - 1})
            cur += sz
        return jsonify({"ok": True, "ranges": ranges})


def _scan_dir(path, skip_names=None, recursive_depth=0):
    skip = set(skip_names or [])
    skip.add(".DS_Store")
    skip.add("desktop.ini")
    if not _os.path.isdir(path):
        return []
    results = []
    try:
        items = _os.listdir(path)
    except Exception:
        return []
    for item in sorted(items):
        if item in skip:
            continue
        full = _os.path.join(path, item)
        if not _os.path.isdir(full):
            continue
        if recursive_depth > 0:
            try:
                sub = _os.listdir(full)
                has_sub = any(_os.path.isdir(_os.path.join(full, s)) and not s.startswith('.') for s in sub)
            except Exception:
                has_sub = False
            if has_sub:
                results.extend(_scan_dir(full, skip, recursive_depth - 1))
                continue
        results.append({"name": item, "path": full})
    return results
