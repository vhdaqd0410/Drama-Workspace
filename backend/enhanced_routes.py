"""Additional routes for workbench enhancements."""
import os as _os
import re as _re
import io as _io
import base64 as _b64
import json as _j
import yaml as _y
import logging as _logging
from flask import request, jsonify, send_file
import config as _cfg
from utils import scan_dir
from fenji_exporter import export_from_template, backup_template, list_templates as _list_templates

_logger = _logging.getLogger(__name__)

# 模板/备份存放目录（相对于 backend/ 父目录的 data/fenji_templates 和 data/fenji_backups）
_DATA_DIR = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), 'data')
_TEMPLATE_DIR = _os.path.join(_DATA_DIR, 'fenji_templates')
_BACKUP_DIR = _os.path.join(_DATA_DIR, 'fenji_backups')


def _nas_search_roots():
    """Build [(root, path_key), ...] from config.yaml NAS section."""
    group_root = _cfg.get("nas.group_root", "")
    production_roots = _cfg.get("nas.production_roots", []) or []
    roots = []
    if group_root:
        roots.append((group_root, "group_path"))
    for p in production_roots:
        roots.append((p, "production_path"))
    if group_root:
        roots.append((_os.path.join(group_root, "00已完成"), "group_path"))
    return roots


def _production_labels():
    """Return path -> label map from config."""
    return _cfg.get("nas.production_labels", {}) or {}


# episode_summary 扫描参数：key = 部门标签（production_labels 的 value 或 "group_root"）
_EPISODE_SCAN_OVERRIDES = {
    "group_root": {"skip": ["00已完成", "0000新人"], "depth": 0},
    "AI漫剧二部": {"skip": ["00序列_ID_剧名"], "depth": 0},
    "AI漫剧一部海外": {"skip": ["AAA《xxxxxxxx》文件夹模板", "00序列_ID_剧名"], "depth": 0},
    "AI漫剧九部海外": {"skip": [], "depth": 1},
    "AI漫剧六部中转": {"skip": [], "depth": 0},
}


def _episode_summary_scan_tasks():
    """Build [(path, skip_names, depth), ...] from config NAS + scan overrides."""
    tasks = []
    group_root = _cfg.get("nas.group_root", "")
    production_roots = _cfg.get("nas.production_roots", []) or []
    labels = _production_labels()

    if group_root:
        o = _EPISODE_SCAN_OVERRIDES["group_root"]
        tasks.append((group_root, o["skip"], o["depth"]))

    for root in production_roots:
        label = labels.get(root, "")
        o = _EPISODE_SCAN_OVERRIDES.get(label, {"skip": [], "depth": 0})
        tasks.append((root, o["skip"], o["depth"]))
    return tasks

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
        search_roots = _nas_search_roots()
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
            for root, _pk in _nas_search_roots():
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
        for path, skip, depth in _episode_summary_scan_tasks():
            for it in scan_dir(path, skip_names=skip, recursive_depth=depth):
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
            cfg = _cfg.load_config()
            return jsonify({"ok": True, "config": cfg})
        except Exception as e:
            return jsonify({"ok": False, "message": str(e)}), 500

    @app.route("/api/config", methods=["POST"])
    def api_config_save():
        data = request.get_json(silent=True) or {}
        try:
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

    # ===========================
    # 分秒帧上传相关路由
    # ===========================
    _FM_LINKS_FILE = _os.path.join(
        _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
        'data', 'fenmiaozhen_links.json'
    )

    def _fm_load_links():
        try:
            with open(_FM_LINKS_FILE, 'r', encoding='utf-8') as _f:
                return _j.load(_f)
        except (FileNotFoundError, Exception):
            return {}

    def _fm_save_links(data):
        _os.makedirs(_os.path.dirname(_FM_LINKS_FILE), exist_ok=True)
        with open(_FM_LINKS_FILE, 'w', encoding='utf-8') as _f:
            _j.dump(data, _f, ensure_ascii=False, indent=2)

    @app.route('/api/fenmiaozhen/config', methods=['GET'])
    def fenmiaozhen_config():
        _cp = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'config.yaml')
        with open(_cp, 'r', encoding='utf-8') as _f:
            _cfg = _y.safe_load(_f) or {}
        fm = _cfg.get('fenmiaozhen', {}) or {}
        return jsonify(
            ok=True,
            enabled_departments=fm.get('enabled_departments', []),
            web_url=fm.get('web_url', 'https://www.mediatrack.cn/project/new'),
        )

    @app.route('/api/fenmiaozhen/link/<path:name>', methods=['GET'])
    def fenmiaozhen_get_link(name):
        links = _fm_load_links()
        url = links.get(name, '')
        return jsonify(ok=True, url=url, has_link=bool(url))

    @app.route('/api/fenmiaozhen/link/<path:name>', methods=['POST'])
    def fenmiaozhen_save_link(name):
        try:
            body = request.get_json(force=True, silent=True) or {}
            url = (body.get('url') or '').strip()
        except Exception:
            url = ''
        if not url:
            return jsonify(ok=False, msg='链接不能为空'), 400
        links = _fm_load_links()
        links[name] = url
        _fm_save_links(links)
        return jsonify(ok=True, url=url)

    # ============================================================
    # 分集导出到 Excel 模板（从独立分集程序搬过来）
    # ============================================================
    @app.route('/api/fenji/templates', methods=['GET'])
    def fenji_list_templates():
        names = _list_templates(_TEMPLATE_DIR)
        return jsonify(ok=True, templates=names, dir=_TEMPLATE_DIR)

    @app.route('/api/fenji/upload_template', methods=['POST'])
    def fenji_upload_template():
        _os.makedirs(_TEMPLATE_DIR, exist_ok=True)
        if 'file' not in request.files:
            return jsonify(ok=False, msg='无文件'), 400
        f = request.files['file']
        if not f.filename:
            return jsonify(ok=False, msg='文件名为空'), 400
        safe_name = _os.path.basename(f.filename)  # 防路径穿越
        save_path = _os.path.join(_TEMPLATE_DIR, safe_name)
        f.save(save_path)
        size = _os.path.getsize(save_path)
        return jsonify(ok=True, name=safe_name, size=size, dir=_TEMPLATE_DIR)

    @app.route('/api/fenji/export_excel', methods=['POST'])
    def fenji_export_excel():
        """
        前端传 JSON:
        {
          template_b64: "...",        // 二选一：base64 编码的模板内容
          template_name: "xxx.xlsx",  // 二选一：已上传到服务端的模板文件名
          originalTemplateName: "xxx.xlsx",  // 备份时用的原始文件名
          projectName: "溯回时光见旧人",
          path: "O:\\...\\溯回时光见旧人",
          timeText: "8.15下午18点交",
          statusText: "已分集",
          assign: [{"person": "张三", "range": "1-25"}, ...]
        }
        返回: {ok, file_b64, fileName, backup: {name, saved}}
        """
        body = request.get_json(silent=True) or {}
        assign = body.get('assign') or []
        if not assign:
            return jsonify(ok=False, msg='assign 为空'), 400

        # 1. 获取模板 bytes
        tpl_bytes = None
        original_name = (body.get('originalTemplateName')
                         or body.get('template_name')
                         or '模板.xlsx')

        tpl_b64 = body.get('template_b64') or body.get('template')
        if tpl_b64:
            try:
                tpl_bytes = _b64.b64decode(tpl_b64)
            except Exception as e:
                return jsonify(ok=False, msg=f'template_b64 解码失败: {e}'), 400
        else:
            tpl_name = body.get('template_name') or ''
            if not tpl_name:
                return jsonify(ok=False, msg='必须提供 template_b64 或 template_name'), 400
            safe = _os.path.basename(tpl_name)
            tpl_path = _os.path.join(_TEMPLATE_DIR, safe)
            if not _os.path.isfile(tpl_path):
                return jsonify(ok=False, msg=f'模板文件不存在: {safe}'), 404
            with open(tpl_path, 'rb') as f:
                tpl_bytes = f.read()

        # 2. 备份原模板
        backup_name, backup_path = '', ''
        try:
            backup_name, backup_path = backup_template(tpl_bytes, original_name, _BACKUP_DIR)
        except Exception as e:
            _logger.warning('备份模板失败: %s', e)

        # 3. 追加 + 美化
        try:
            new_bytes = export_from_template(
                tpl_bytes,
                project_name=body.get('projectName', ''),
                path=body.get('path', ''),
                assign_list=assign,
                time_text=body.get('timeText', ''),
                status_text=body.get('statusText', '已分集'),
            )
        except Exception as e:
            _logger.exception('export_excel 失败')
            return jsonify(ok=False, msg=f'导出失败: {e}'), 500

        # 4. 把追加后的结果写回模板文件 —— 这样下次再导出时旧数据还在
        #    只有从磁盘模板读取时才写回（前端传 template_b64 的临时情况跳过）
        if tpl_name and not tpl_b64:
            try:
                with open(tpl_path, 'wb') as f:
                    f.write(new_bytes)
                _logger.info('已写回模板 %s (大小 %d 字节)', tpl_name, len(new_bytes))
            except Exception as e:
                _logger.warning('写回模板失败: %s', e)

        out_name = _re.sub(r'\.[^.]+$', '', original_name) + '_已分集.xlsx'
        return jsonify({
            'ok': True,
            'file_b64': _b64.b64encode(new_bytes).decode('ascii'),
            'fileName': out_name,
            'backup': {'name': backup_name, 'saved': backup_path},
        })

    @app.route('/api/fenji/save_to_folder', methods=['POST'])
    def fenji_save_to_folder():
        """把已生成的 Excel 文件保存到指定文件夹。"""
        body = request.get_json(silent=True) or {}
        folder = (body.get('folder') or '').strip()
        file_b64 = body.get('fileB64') or body.get('file_b64') or ''
        fname = body.get('fileName') or '分集结果.xlsx'
        open_excel = bool(body.get('open'))

        if not folder:
            return jsonify(ok=False, msg='未指定文件夹'), 400
        if not file_b64:
            return jsonify(ok=False, msg='无文件内容'), 400
        if not _os.path.isdir(folder):
            return jsonify(ok=False, msg=f'文件夹不存在: {folder}'), 400

        try:
            file_bytes = _b64.b64decode(file_b64)
        except Exception as e:
            return jsonify(ok=False, msg=f'base64 解码失败: {e}'), 400

        safe_fname = _os.path.basename(fname)
        save_path = _os.path.join(folder, safe_fname)
        with open(save_path, 'wb') as f:
            f.write(file_bytes)

        if open_excel:
            try:
                import subprocess
                subprocess.Popen(['start', save_path], shell=True)
            except Exception:
                pass
        return jsonify(ok=True, saved=save_path)

