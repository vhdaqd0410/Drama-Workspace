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
_DATA_DIR = os.path.join(_BASE, "data")


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


def _parse_time_text(text):
    """解析分集目标表格的胶片日期文本（如 '8.15上午10点交'、'8.15'、'2026-8-15'）
    为 'YYYY-MM-DD'。解析失败返回空串。"""
    import re as _re
    from datetime import datetime
    if not text:
        return ""
    s = str(text).strip()
    # 完整日期：2026-8-15 / 2026/8/15
    m = _re.search(r"(20\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        # 短格式：M.D 或 M.D上午/下午…点交
        m = _re.search(r"(\d{1,2})[.月](\d{1,2})", s)
        if not m:
            # 纯数字日期如 815 / 8.15
            m = _re.search(r"(\d{1,2})\s*[-./]\s*(\d{1,2})", s)
            if not m:
                return ""
        y, mo, d = datetime.now().year, int(m.group(1)), int(m.group(2))
    try:
        dt = datetime(y, mo, d)
    except Exception:
        return ""
    return dt.strftime("%Y-%m-%d")


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
    def _parse_ym(s):
        """从 'YYYY-MM-DD HH:MM:SS' 或 'YYYY-MM' 提取月份 'YYYY-MM'。"""
        if not s:
            return ""
        s = str(s).strip()
        return s[:7] if len(s) >= 7 and s[4] == "-" else ""

    @app.route("/api/insights/summary")
    def features_insights_summary():
        """KPI 汇总（以当月为基准）：
        项目数 / 当月项目数 / 当月已完成 / 进行中项目 / 成员
        当月项目状态分布 + 各剪辑当月集数（环形图用）。
        """
        try:
            from datetime import datetime
            now = datetime.now()
            month = now.strftime("%Y-%m")
            projs = db.get_all_projects() or []
            # 当月项目：created_at 落在本月
            month_projs = [p for p in projs if _parse_ym(p.get("created_at")) == month]
            # 当月已完成：delivered_date 落在本月
            month_completed = [p for p in projs if _parse_ym(p.get("delivered_date")) == month]
            # 进行中：状态非"已完成"且非空
            in_progress = [p for p in projs if (p.get("custom_status") or "").strip() not in ("", "已完成")]
            # 当月项目状态分布
            status_map = {}
            for p in month_projs:
                st = (p.get("custom_status") or p.get("delivery_status") or "未设置").strip() or "未设置"
                status_map[st] = status_map.get(st, 0) + 1
            # 各剪辑当月集数：从当月项目 episode_plan（episode->editor）聚合
            editor_eps = {}
            for p in month_projs:
                plan = p.get("episode_plan")
                if isinstance(plan, str):
                    try:
                        plan = json.loads(plan)
                    except Exception:
                        plan = {}
                if isinstance(plan, dict):
                    for ep, editor in plan.items():
                        if not editor:
                            continue
                        try:
                            n = int(ep)
                        except Exception:
                            continue
                        editor_eps[str(editor)] = editor_eps.get(str(editor), 0) + 1
                else:
                    # 兜底：episodes 数组含 editor
                    for e in (p.get("episodes") or []):
                        ed = e.get("editor")
                        if ed:
                            editor_eps[str(ed)] = editor_eps.get(str(ed), 0) + 1
            # 成员数
            members = 0
            try:
                members = len(db.list_members() or []) if hasattr(db, "list_members") else 0
            except Exception:
                pass
            return jsonify({
                "ok": True,
                "month": month,
                "projectCount": len(projs),
                "monthProjectCount": len(month_projs),
                "monthCompleted": len(month_completed),
                "inProgress": len(in_progress),
                "memberCount": members,
                "statusMap": status_map,
                "editorEpisodes": editor_eps,
            })
        except Exception as e:
            return jsonify({"ok": False, "message": str(e)}), 500

    @app.route("/api/insights/calendar")
    def features_insights_calendar():
        """交付日历：按项目 delivered_date 分组，返回每天交付的项目名列表。
        ?month=YYYY-MM，days: {YYYY-MM-DD: [项目名,...]}
        """
        month = request.args.get("month", "")
        if not month or len(month) != 7:
            from datetime import datetime
            month = datetime.now().strftime("%Y-%m")
        prefix = month + "-"
        days = {}
        try:
            projs = db.get_all_projects() or []
            for p in projs:
                dd = (p.get("delivered_date") or "").strip()
                if dd.startswith(prefix):
                    d = dd[:10]
                    days.setdefault(d, []).append(p.get("name") or "")
        except Exception:
            pass
        # 排序每个日期的项目名
        for k in days:
            days[k] = sorted(days[k])
        return jsonify({"ok": True, "month": month, "days": days})

    @app.route("/api/project/<name>/delivered_date", methods=["POST"])
    def features_set_delivered_date(name):
        """设置项目交付/归档日期（交付日历用）。body: {date:'YYYY-MM-DD' 或 ''清空}"""
        data = request.get_json(silent=True) or {}
        date = (data.get("date") or "").strip()
        if date and len(date) == 10 and date[4] == "-" and date[7] == "-":
            db.update_project_status(name, delivered_date=date)
            _log_audit(db, name, "设置交付日期", date)
            return jsonify({"ok": True, "date": date})
        db.update_project_status(name, delivered_date="")
        _log_audit(db, name, "清除交付日期")
        return jsonify({"ok": True, "date": ""})

    @app.route("/api/insights/sync_delivery_dates", methods=["POST"])
    def features_sync_delivery_dates():
        """从分集目标文件表格读取胶片日期（col4），解析为 YYYY-MM-DD，
        更新到项目 delivered_date 并刷新日历。body: {target_path?: 路径}"""
        import openpyxl
        # 目标文件路径：优先 body，其次设置，再扫描 data/fenji_targets
        data = request.get_json(silent=True) or {}
        target = (data.get("target_path") or "").strip()
        if not target:
            try:
                target = db.get_all_settings().get("fj_target_path", "") or ""
            except Exception:
                target = ""
        if not target or not os.path.isfile(target):
            # 尝试自动查找最近的目标文件
            tgt_dir = os.path.join(_DATA_DIR, "fenji_targets")
            if os.path.isdir(tgt_dir):
                xlsx = [f for f in os.listdir(tgt_dir) if f.lower().endswith((".xlsx", ".xlsm", ".xls"))]
                if xlsx:
                    target = os.path.join(tgt_dir, sorted(xlsx)[-1])
        if not target or not os.path.isfile(target):
            return jsonify({"ok": False, "message": "未找到目标文件，请先在分集管理设置目标文件"}), 400

        updated = []
        try:
            wb = openpyxl.load_workbook(target, data_only=True)
            ws = wb[wb.sheetnames[0]]
            # 遍历合并单元格定位项目块，读 col1(项目名) + col4(胶片日期)
            seen_names = set()
            for rng in ws.merged_cells.ranges:
                if rng.min_col == 1 and rng.max_col == 1 and rng.min_row == rng.max_row:
                    pass
            # 更稳：逐行读，取每块第一行的 col1 与 col4
            cur_name = None
            cur_date = ""
            for row in ws.iter_rows(min_row=1, max_row=ws.max_row):
                name = row[0].value if len(row) > 0 else None
                if name and str(name).strip():
                    # 新项目块开始
                    if cur_name and cur_date and cur_name not in seen_names:
                        seen_names.add(cur_name)
                        parsed = _parse_time_text(cur_date)
                        if parsed:
                            db.update_project_status(cur_name, delivered_date=parsed)
                            updated.append({"project": cur_name, "date": parsed})
                    cur_name = str(name).strip()
                    cur_date = row[3].value if len(row) > 3 else None
            # 处理最后一个块
            if cur_name and cur_date and cur_name not in seen_names:
                seen_names.add(cur_name)
                parsed = _parse_time_text(cur_date)
                if parsed:
                    db.update_project_status(cur_name, delivered_date=parsed)
                    updated.append({"project": cur_name, "date": parsed})
            return jsonify({"ok": True, "updated": len(updated), "target": target, "items": updated})
        except Exception as e:
            return jsonify({"ok": False, "message": "解析失败: " + str(e)}), 500

    @app.route("/api/insights/export")
    def features_insights_export():
        """导出项目档案 CSV（项目名/状态/总集数/已生成/部门/路径/交付日期/创建时间）。"""
        import io as _io
        import csv as _csv
        projs = db.get_all_projects() or []
        buf = _io.StringIO()
        writer = _csv.writer(buf)
        writer.writerow(["项目名", "部门", "当前状态", "交付状态", "总集数", "已生成集数", "交付日期", "组内路径", "制作路径", "创建时间"])
        for p in projs:
            writer.writerow([
                p.get("name", ""),
                p.get("department", ""),
                p.get("custom_status", ""),
                p.get("delivery_status", ""),
                p.get("total_episodes", 0),
                p.get("current_episodes", 0),
                p.get("delivered_date", ""),
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
