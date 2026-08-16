# -*- coding: utf-8 -*-
"""融合功能路由（自「项目档案管理器」）：待办事项 / 时间轴 / 数据备份 / 视频缩略图。

统一在 register_routes(app, db) 内用 @app.route 注册，随 app.py 启动加载。
所有路由默认受 _auth_gate 保护（缩略图端点由 app 侧加入 /api/thumbnail/ 公共前缀）。
"""
import os
import json
import logging
import subprocess
import tempfile
from flask import request, jsonify, send_file, abort

logger = logging.getLogger("features")

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_THUMB_DIR = os.path.join(_BASE, "data", "thumbs")


def _yaml_cfg():
    try:
        import yaml
        with open(os.path.join(_BASE, "backend", "config.yaml"), "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _yaml_get(dotted, default=None):
    cur = _yaml_cfg()
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


def _now():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _log_audit(db, project_name, action, detail="", username=""):
    try:
        db.add_audit_log(project_name, action, detail, username)
    except Exception as e:
        logger.warning("写入审计日志失败: %s", e)


def register_routes(app, db):
    # ==================== 项目待办事项 ====================
    @app.route("/api/project/<name>/todos", methods=["GET"])
    def features_todos_get(name):
        return jsonify({"ok": True, "todos": db.get_project_todos(name)})

    @app.route("/api/project/<name>/todos", methods=["POST"])
    def features_todos_add(name):
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "").strip()
        if not text:
            return jsonify({"ok": False, "message": "请输入待办内容"}), 400
        todo_id = db.add_project_todo(name, text, data.get("priority", 0))
        _log_audit(db, name, "添加待办", text)
        return jsonify({"ok": True, "id": todo_id})

    @app.route("/api/project/<name>/todos/<int:todo_id>", methods=["PUT"])
    def features_todos_update(name, todo_id):
        data = request.get_json(silent=True) or {}
        if "done" in data:
            db.update_project_todo(todo_id, done=bool(data.get("done")))
            _log_audit(db, name, "完成待办" if data.get("done") else "取消待办")
        if "text" in data:
            db.update_project_todo(todo_id, text=data.get("text"))
        if "priority" in data:
            db.update_project_todo(todo_id, priority=data.get("priority"))
        return jsonify({"ok": True})

    @app.route("/api/project/<name>/todos/<int:todo_id>", methods=["DELETE"])
    def features_todos_delete(name, todo_id):
        db.delete_project_todo(todo_id)
        _log_audit(db, name, "删除待办")
        return jsonify({"ok": True})

    # ==================== 项目时间轴 ====================
    @app.route("/api/project/<name>/timeline")
    def features_timeline(name):
        events = []
        # 1. 项目创建
        proj = db.get_project(name)
        if proj and proj.get("created_at"):
            events.append({
                "time": proj["created_at"], "type": "create",
                "title": "📁 项目创建",
                "detail": "项目「%s」创建" % name,
                "icon": "📁", "color": "#0071e3",
            })
        # 2. 交付日志
        try:
            logs = db.get_delivery_logs(name, limit=500)
            for l in logs:
                st = (l.get("status") or "").lower()
                if st in ("fail", "error"):
                    icon, color = "❌", "#ff3b30"
                elif st in ("warn", "warning"):
                    icon, color = "⚠️", "#ff9500"
                else:
                    icon, color = "📋", "#34c759"
                events.append({
                    "time": l.get("created_at", ""), "type": "delivery",
                    "title": "📋 交付 " + (l.get("file_name") or ""),
                    "detail": (l.get("message") or l.get("dest_path") or ""),
                    "icon": icon, "color": color,
                })
        except Exception as e:
            logger.warning("时间轴交付日志失败: %s", e)
        # 3. 同步日志
        try:
            logs = db.get_sync_logs(name, limit=200)
            for l in logs:
                icon, color = "🔃", "#5856d6"
                events.append({
                    "time": l.get("created_at", ""), "type": "sync",
                    "title": "🔃 同步 " + (l.get("action") or ""),
                    "detail": (l.get("file_path") or l.get("message") or ""),
                    "icon": icon, "color": color,
                })
        except Exception:
            pass
        # 4. QA 质检
        try:
            qas = db.list_qa_runs_for_project(name, limit=50)
            for q in qas:
                st = (q.get("status") or "").lower()
                if st == "pass":
                    icon, color = "✅", "#34c759"
                elif st == "fail":
                    icon, color = "❌", "#ff3b30"
                else:
                    icon, color = "🔍", "#ff9500"
                events.append({
                    "time": q.get("started_at") or q.get("created_at", ""), "type": "qa",
                    "title": "🔍 质检",
                    "detail": "通过 %s / 失败 %s" % (q.get("passed", 0), q.get("failed", 0)),
                    "icon": icon, "color": color,
                })
        except Exception:
            pass
        # 5. 审计日志
        try:
            for l in db.get_audit_logs(name, limit=100):
                events.append({
                    "time": l.get("created_at", ""), "type": "audit",
                    "title": "🔧 " + (l.get("action") or "操作"),
                    "detail": l.get("detail") or "",
                    "icon": "🔧", "color": "#8e8e93",
                })
        except Exception:
            pass

        # 按时间排序
        events.sort(key=lambda x: x.get("time") or "")
        # 摘要
        summary = {
            "totalEvents": len(events),
            "firstEvent": events[0]["time"] if events else None,
            "lastEvent": events[-1]["time"] if events else None,
            "totalDeliveries": sum(1 for e in events if e["type"] == "delivery"),
        }
        return jsonify({"ok": True, "project": name, "events": events, "summary": summary})

    # ==================== 数据备份 ====================
    @app.route("/api/backup/list")
    def features_backup_list():
        import backup_service
        return jsonify({"ok": True, "backups": backup_service.list_backups()})

    @app.route("/api/backup/create", methods=["POST"])
    def features_backup_create():
        import backup_service
        try:
            b = backup_service.backup_now()
            return jsonify({"ok": True, "backup": b})
        except Exception as e:
            return jsonify({"ok": False, "message": str(e)}), 500

    @app.route("/api/backup/restore", methods=["POST"])
    def features_backup_restore():
        import backup_service
        data = request.get_json(silent=True) or {}
        name = data.get("backupName") or data.get("name") or ""
        if not name:
            return jsonify({"ok": False, "message": "请选择备份文件"}), 400
        try:
            backup_service.restore(name)
            return jsonify({"ok": True, "message": "已恢复，请重启软件生效"})
        except Exception as e:
            return jsonify({"ok": False, "message": str(e)}), 500

    # ==================== 数据洞察（可选增强：大屏 / 日历 / 导出）====================
    @app.route("/api/insights/summary")
    def features_insights_summary():
        """KPI 汇总：项目数、状态分布、集数、交付、质检、成员。"""
        try:
            projs = db.get_all_projects() or []
            status_map = {}
            total_ep = 0
            total_done = 0
            for p in projs:
                st = (p.get("custom_status") or p.get("delivery_status") or "未设置").strip()
                status_map[st] = status_map.get(st, 0) + 1
                total_ep += int(p.get("total_episodes") or 0)
                total_done += int(p.get("current_episodes") or 0)
            # 交付统计（近12个月）
            months = {}
            try:
                logs = db.get_recent_logs(limit=2000)
                for l in logs:
                    ts = l.get("created_at") or ""
                    if len(ts) >= 7 and (l.get("status") or "") != "error":
                        m = ts[:7]
                        months[m] = months.get(m, 0) + 1
            except Exception:
                pass
            # 质检统计
            qa_pass = qa_total = 0
            try:
                runs = db.list_all_qa_runs(limit=500)
                for r in runs:
                    qa_total += 1
                    if (r.get("status") or "") == "pass":
                        qa_pass += 1
            except Exception:
                pass
            # 成员数
            members = 0
            try:
                members = len(db.list_members() or []) if hasattr(db, "list_members") else 0
            except Exception:
                pass
            # 待办统计
            todo_done = todo_total = 0
            try:
                import sqlite3 as _sq
                with db.get_conn() as conn:
                    row = conn.execute("SELECT COUNT(*) c, COALESCE(SUM(done),0) d FROM project_todos").fetchone()
                    todo_total, todo_done = row[0] or 0, row[1] or 0
            except Exception:
                pass
            return jsonify({
                "ok": True,
                "projectCount": len(projs),
                "statusMap": status_map,
                "totalEpisodes": total_ep,
                "doneEpisodes": total_done,
                "deliveryMonths": months,
                "qaPass": qa_pass,
                "qaTotal": qa_total,
                "memberCount": members,
                "todoTotal": todo_total,
                "todoDone": todo_done,
            })
        except Exception as e:
            return jsonify({"ok": False, "message": str(e)}), 500

    @app.route("/api/insights/calendar")
    def features_insights_calendar():
        """交付日历：返回指定月份每天的交付数。?month=YYYY-MM"""
        month = request.args.get("month", "")
        if not month or len(month) != 7:
            from datetime import datetime
            month = datetime.now().strftime("%Y-%m")
        prefix = month + "-"
        days = {}
        try:
            logs = db.get_recent_logs(limit=5000)
            for l in logs:
                ts = l.get("created_at") or ""
                if ts.startswith(prefix):
                    d = ts[:10]
                    days[d] = days.get(d, 0) + 1
        except Exception:
            pass
        return jsonify({"ok": True, "month": month, "days": days})

    @app.route("/api/insights/export")
    def features_insights_export():
        """导出项目档案 CSV（项目名/状态/总集数/已生成/部门/路径/创建时间）。"""
        import io as _io
        import csv as _csv
        projs = db.get_all_projects() or []
        buf = _io.StringIO()
        writer = _csv.writer(buf)
        writer.writerow(["项目名", "部门", "当前状态", "交付状态", "总集数", "已生成集数", "组内路径", "制作路径", "创建时间"])
        for p in projs:
            writer.writerow([
                p.get("name", ""),
                p.get("department", ""),
                p.get("custom_status", ""),
                p.get("delivery_status", ""),
                p.get("total_episodes", 0),
                p.get("current_episodes", 0),
                p.get("group_path", ""),
                p.get("production_path", ""),
                p.get("created_at", ""),
            ])
        data = "\ufeff" + buf.getvalue()  # BOM 便于 Excel 打开中文
        from flask import Response
        return Response(
            data,
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=projects.csv"})

    # ==================== 视频缩略图（ffmpeg）====================
    @app.route("/api/thumbnail")
    def features_thumbnail():
        """生成视频缩略图：?path=绝对路径。生成后返回图片，带缓存。"""
        file_path = request.args.get("path", "")
        if not file_path or not os.path.isfile(file_path):
            return jsonify({"ok": False, "message": "文件不存在"}), 404
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in (".mp4", ".mov", ".mxf", ".avi", ".mkv", ".webm", ".wmv", ".m4v"):
            return jsonify({"ok": False, "message": "非视频文件"}), 400
        # 生成缩略图（缓存到 data/thumbs）
        try:
            os.makedirs(_THUMB_DIR, exist_ok=True)
            import hashlib
            digest = hashlib.md5(file_path.encode("utf-8", "ignore")).hexdigest()
            thumb = os.path.join(_THUMB_DIR, digest + ".jpg")
            if not os.path.exists(thumb):
                _gen_thumbnail(file_path, thumb)
            if os.path.exists(thumb):
                return send_file(thumb, mimetype="image/jpeg", conditional=True)
            return jsonify({"ok": False, "message": "无法生成缩略图"}), 422
        except Exception as e:
            logger.warning("缩略图失败: %s", e)
            return jsonify({"ok": False, "message": str(e)}), 500


def _gen_thumbnail(file_path, out_path):
    """用 ffmpeg 抽取视频中段一帧生成为 JPG 缩略图。"""
    ffmpeg = _resolve_ffmpeg_bin()
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg")
    cmd = [ffmpeg, "-y", "-i", file_path,
           "-vf", "scale=320:-1", "-frames:v", "1", "-q:v", "5", out_path]
    try:
        subprocess.run(cmd, capture_output=True, timeout=20, check=False)
    except Exception:
        pass


def _resolve_ffmpeg_bin():
    """查找 ffmpeg：config.yaml 的 qa.ffmpeg_path → PATH → 常见目录。"""
    p = _yaml_get("qa.ffmpeg_path", "")
    if p and os.path.isfile(p):
        return p
    import shutil
    p = shutil.which("ffmpeg")
    if p:
        return p
    candidates = [
        r"C:\Users\Admin\Desktop\视频检查工具\视频质检工具\dist\视频质检工具\ffmpeg.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None
