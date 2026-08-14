# -*- coding: utf-8 -*-
"""批量操作 + 任务中心 + 月度报告 API"""
import json
import sqlite3
from datetime import datetime


def register_routes(app, db):
    # ================================================================
    # 批量操作
    # ================================================================

    @app.route("/api/bulk/update_month", methods=["POST"])
    def bulk_update_month():
        body = request_json()
        names = body.get("names") or []
        month = body.get("month", "")
        if not names:
            return jsonify({"ok": False, "msg": "未选择项目"}), 400
        try:
            cur = db.conn.cursor()
            if month:
                cur.execute(
                    "UPDATE projects SET project_month=? WHERE name IN ({})".format(
                        ",".join(["?"] * len(names))
                    ),
                    [month] + list(names),
                )
            else:
                cur.execute(
                    "UPDATE projects SET project_month=NULL WHERE name IN ({})".format(
                        ",".join(["?"] * len(names))
                    ),
                    list(names),
                )
            db.conn.commit()
            affected = cur.rowcount
            return jsonify({"ok": True, "updated": affected})
        except Exception as e:
            return jsonify({"ok": False, "msg": str(e)}), 500

    @app.route("/api/bulk/update_status", methods=["POST"])
    def bulk_update_status():
        body = request_json()
        names = body.get("names") or []
        status = body.get("custom_status") or ""
        if not names or not status:
            return jsonify({"ok": False, "msg": "参数缺失"}), 400
        try:
            cur = db.conn.cursor()
            cur.execute(
                "UPDATE projects SET custom_status=? WHERE name IN ({})".format(
                    ",".join(["?"] * len(names))
                ),
                [status] + list(names),
            )
            db.conn.commit()
            return jsonify({"ok": True, "updated": cur.rowcount})
        except Exception as e:
            return jsonify({"ok": False, "msg": str(e)}), 500

    # ================================================================
    # 任务中心
    # ================================================================

    @app.route("/api/activity_log", methods=["GET"])
    def api_activity_log():
        from flask import request as _r
        limit = int(_r.args.get("limit", 200))
        project = _r.args.get("project", "").strip()
        type_filter = _r.args.get("type", "").strip()
        status_filter = _r.args.get("status", "").strip()

        params = []

        sync_where = []
        if project:
            sync_where.append("project_name LIKE ?")
            params.append("%" + project + "%")
        if status_filter:
            sync_where.append("status = ?")
            params.append(status_filter)
        sync_sql = "SELECT 'sync' as type, id, project_name, direction as action, '' as file_name, '' as source_path, '' as dest_path, file_size, status, message, created_at FROM sync_logs"
        if sync_where:
            sync_sql += " WHERE " + " AND ".join(sync_where)

        del_where = []
        if project:
            del_where.append("project_name LIKE ?")
            params.append("%" + project + "%")
        if status_filter:
            del_where.append("status = ?")
            params.append(status_filter)
        del_sql = "SELECT 'deliver' as type, id, project_name, '' as action, file_name, source_path, dest_path, file_size, status, message, created_at FROM delivery_logs"
        if del_where:
            del_sql += " WHERE " + " AND ".join(del_where)

        if type_filter == "sync":
            union_sql = sync_sql
        elif type_filter == "deliver":
            union_sql = del_sql
        else:
            union_sql = f"({sync_sql}) UNION ALL ({del_sql})"

        sql = f"SELECT * FROM ({union_sql}) ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        try:
            cur = db.conn.cursor()
            cur.execute(sql, params)
            rows = [dict_row(r, cur) for r in cur.fetchall()]

            cur.execute(
                "SELECT * FROM deliver_runs WHERE status IN ('pending','running','syncing') ORDER BY id DESC LIMIT 20"
            )
            active_runs = [dict_row(r, cur) for r in cur.fetchall()]

            return jsonify({"ok": True, "logs": rows, "active_runs": active_runs})
        except Exception as e:
            import traceback; traceback.print_exc()
            return jsonify({"ok": False, "msg": str(e)}), 500

    # ================================================================
    # 月度报告
    # ================================================================

    @app.route("/api/report/monthly", methods=["GET"])
    def api_report_monthly():
        from flask import request as _r
        month = _r.args.get("month", "").strip()
        if not month:
            month = datetime.now().strftime("%Y-%m")

        try:
            cur = db.conn.cursor()

            cur.execute(
                """
                SELECT name, department, custom_status, delivery_status,
                       total_episodes, current_episodes, project_month
                FROM projects
                WHERE project_month = ?
                  AND (IFNULL(custom_status,'') <> ''
                       OR IFNULL(delivery_status,'pending') <> 'pending'
                       OR IFNULL(total_episodes,0) > 0)
                ORDER BY department, name
                """,
                (month,),
            )
            projects_rows = [dict_row(r, cur) for r in cur.fetchall()]

            cur.execute(
                """
                SELECT department,
                       COUNT(*) as total,
                       SUM(CASE WHEN custom_status='已完成' THEN 1 ELSE 0 END) as completed,
                       SUM(CASE WHEN custom_status IN ('剪辑中','审核中','修改中') THEN 1 ELSE 0 END) as editing,
                       SUM(CASE WHEN delivery_status='delivered' THEN 1 ELSE 0 END) as delivered,
                       SUM(IFNULL(total_episodes,0)) as total_eps
                FROM projects
                WHERE project_month = ?
                  AND (IFNULL(custom_status,'') <> ''
                       OR IFNULL(delivery_status,'pending') <> 'pending'
                       OR IFNULL(total_episodes,0) > 0)
                GROUP BY department
                ORDER BY total DESC
                """,
                (month,),
            )
            summary_by_dept = [dict_row(r, cur) for r in cur.fetchall()]

            cur.execute(
                """
                SELECT COALESCE(SUM(file_size),0) as total_bytes,
                       COUNT(*) as file_count,
                       COUNT(DISTINCT project_name) as project_count
                FROM delivery_logs
                WHERE created_at LIKE ? || '%'
                  AND status = 'success'
                """,
                (month,),
            )
            delivery_stats = dict_row(cur.fetchone(), cur) or {}

            return jsonify(
                {
                    "ok": True,
                    "month": month,
                    "projects": projects_rows,
                    "summary_by_department": summary_by_dept,
                    "delivery_stats": delivery_stats,
                    "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        except Exception as e:
            import traceback; traceback.print_exc()
            return jsonify({"ok": False, "msg": str(e)}), 500

    @app.route("/api/report/monthly/export", methods=["GET"])
    def api_report_export():
        from flask import request as _r
        from flask import send_file

        month = _r.args.get("month", "").strip()
        if not month:
            month = datetime.now().strftime("%Y-%m")

        try:
            report = api_report_monthly()
            data = report.get_json()
            if not data.get("ok"):
                return jsonify(data), 500

            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill
            import io as _io

            wb = Workbook()
            ws1 = wb.active
            ws1.title = "汇总"

            header_font = Font(bold=True, color="FFFFFF")
            header_fill = PatternFill("solid", fgColor="4472C4")
            title_font = Font(bold=True, size=14)

            ws1["A1"] = f"视频工作台 月度报告 — {month}"
            ws1["A1"].font = title_font
            ws1.merge_cells("A1:F1")
            ws1["A3"] = "生成时间：" + data.get("generated_at", "")

            ds = data.get("delivery_stats", {})
            ws1["A5"] = "回传概览"
            ws1["A5"].font = Font(bold=True)
            ws1["A6"] = "总回传数据量"
            ws1["B6"] = (ds.get("total_bytes") or 0)
            ws1["C6"] = "总回传文件数"
            ws1["D6"] = (ds.get("file_count") or 0)
            ws1["E6"] = "涉及项目数"
            ws1["F6"] = (ds.get("project_count") or 0)

            ws1["A8"] = "按部门汇总"
            ws1["A8"].font = Font(bold=True)

            headers = ["部门", "项目数", "已完成", "制作中", "已交付", "总集数"]
            for col_idx, h in enumerate(headers, 1):
                cell = ws1.cell(row=9, column=col_idx, value=h)
                cell.font = header_font
                cell.fill = header_fill

            row = 10
            for dept in data.get("summary_by_department", []):
                vals = [
                    dept.get("department") or "(未分类)",
                    dept.get("total", 0),
                    dept.get("completed", 0),
                    dept.get("editing", 0),
                    dept.get("delivered", 0),
                    dept.get("total_eps", 0),
                ]
                for ci, v in enumerate(vals):
                    ws1.cell(row=row, column=ci + 1, value=v)
                row += 1

            for col in ["A", "B", "C", "D", "E", "F"]:
                ws1.column_dimensions[col].width = 16

            ws2 = wb.create_sheet("项目清单")
            headers2 = ["项目名称", "部门", "状态", "交付状态", "总集数", "当前集数", "月份"]
            for ci, h in enumerate(headers2, 1):
                cell = ws2.cell(row=1, column=ci, value=h)
                cell.font = header_font
                cell.fill = header_fill

            for ri, p in enumerate(data.get("projects", []), 2):
                ws2.cell(row=ri, column=1, value=p.get("name", ""))
                ws2.cell(row=ri, column=2, value=p.get("department", "") or "")
                ws2.cell(row=ri, column=3, value=p.get("custom_status", "") or "")
                ws2.cell(row=ri, column=4, value=p.get("delivery_status", "") or "")
                ws2.cell(row=ri, column=5, value=p.get("total_episodes", 0) or 0)
                ws2.cell(row=ri, column=6, value=p.get("current_episodes", 0) or 0)
                ws2.cell(row=ri, column=7, value=p.get("project_month", "") or "")

            for col in ["A", "B", "C", "D", "E", "F", "G"]:
                ws2.column_dimensions[col].width = 22

            buf = _io.BytesIO()
            wb.save(buf)
            buf.seek(0)
            filename = f"video_workbench_report_{month}.xlsx"
            return send_file(
                buf,
                as_attachment=True,
                download_name=filename,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        except Exception as e:
            import traceback; traceback.print_exc()
            return jsonify({"ok": False, "msg": str(e)}), 500


def request_json():
    from flask import request
    try:
        return request.get_json(force=True) or {}
    except Exception:
        return {}


def dict_row(row, cursor):
    if row is None:
        return None
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}
