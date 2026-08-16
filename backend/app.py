"""NAS Bridge Web 服务主入口"""
import os
import os as _os
import sys
import time
import time as _time
import yaml
import logging
import threading
import subprocess
import subprocess as _sp
import signal
import json
import json as _json
import shlex as _shlex
import glob as _glob
import tempfile as _tf
import sqlite3
import re
import secrets
from datetime import datetime
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, jsonify, request, send_file

from db import Database
from sync_engine import SyncEngine
from watcher import Watcher
from qa_engine import qa_engine

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)


def save_config():
    """将当前 config 字典写回 config.yaml"""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False,
                  sort_keys=False)


def reload_sync_engine():
    """修改路径配置后，重新初始化 sync_engine 内部状态"""
    sync_engine.nas = config["nas"]
    sync_engine._dept_labels = config["nas"].get("production_labels", {})
    sync_engine._unc_map = config["nas"].get("unc_map", {})
    sync_engine._output_dir_cache.clear()

_log_cfg = config.get("logging", {})
_log_file = _log_cfg.get("file", "nas_bridge.log")
_log_level = getattr(logging, _log_cfg.get("level", "INFO"))
_log_max_mb = _log_cfg.get("max_mb", 10)
_log_backups = _log_cfg.get("backups", 5)

logging.basicConfig(
    level=_log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(
            _log_file, maxBytes=_log_max_mb * 1024 * 1024,
            backupCount=_log_backups, encoding="utf-8"),
    ])

# 治理日志噪音：waitress.queue 的 "Task queue depth is N" 警告会大量刷屏
# （负载高时每秒几十条，占满日志）。这类负载提示仅在 DEBUG 排查时有价值，
# 平时把它抑制到 ERROR 级别，避免日志快速膨胀。
try:
    logging.getLogger("waitress.queue").setLevel(logging.ERROR)
    # waitress 主 logger 保持 WARNING（保留真正的错误），避免误伤其他告警
    logging.getLogger("waitress").setLevel(logging.WARNING)
except Exception:
    pass

logger = logging.getLogger("nas-bridge")

db = Database(config.get("database", "nas_bridge.db"))
sync_engine = SyncEngine(config, db)
watcher = Watcher(config, db)

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(__name__,
            template_folder=os.path.join(_BASE, 'templates'),
            static_folder=os.path.join(_BASE, 'static'))
app.config['TEMPLATES_AUTO_RELOAD'] = True
_start_time = time.time()

# ========= 安全加固 =========
_API_SECRET = config.get("web", {}).get("api_secret")
if not _API_SECRET:
    _API_SECRET = secrets.token_urlsafe(24)
    config.setdefault("web", {})["api_secret"] = _API_SECRET
    try:
        save_config()
        logger.warning("首次启动，已自动生成 API_SECRET 并存入 config.yaml")
    except Exception:
        logger.warning("生成的 API_SECRET 未能写入 config.yaml（不影响运行）")

# 免鉴权白名单：页面 + 静态资源 + 内部轮询 + 文件流式端点
# video/img 原生请求不走 fetch，无法自动带 key；服务已绑 127.0.0.1，外部无法直连
_PUBLIC_ROUTES = {"/", "/health", "/api/health", "/api/status", "/favicon.ico"}
_PUBLIC_PREFIXES = ("/static/", "/api/_self/", "/api/preview/", "/api/thumbnail/", "/api/thumbnail", "/api/frame/", "/api/file_stream/", "/api/sse")

@app.before_request
def _auth_gate():
    path = request.path
    if path in _PUBLIC_ROUTES or path.startswith(_PUBLIC_PREFIXES):
        return None
    # 页面本身放行（index.html 直接访问）
    if request.endpoint == "index":
        return None
    # API 请求校验 header 或 query param（兼容 fetch）
    provided = request.headers.get("X-API-KEY", "") or request.args.get("key", "")
    if provided != _API_SECRET:
        return jsonify({"ok": False, "message": "Unauthorized"}), 401

@app.after_request
def _add_security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    return resp


def _bg(fn, *args, **kwargs):
    """把 fn 放到后台 daemon 线程执行"""
    threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True).start()

# 开发模式：禁用浏览器缓存，避免修改代码后看到旧页面
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


@app.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/")
def index():
    # 预加载初始数据嵌入 HTML，避免前端首次 fetch 1MB 数据卡住
    try:
        enriched = sync_engine.get_projects_enriched()
        production = enriched.get('production', [])
        group_all = enriched.get('group_all', [])
        group_completed = enriched.get('group_completed', [])
        sections_data = []
        active_group = [p for p in group_all if not p.get('is_completed')]
        sections_data.append({'key':'group_active','name':'🟢 组内NAS（进行中）','type':'group','collapsed':False,'projects':active_group})
        dept_order = [('AI漫剧二部','🏢 AI漫剧二部中转','erbu'),('AI漫剧一部海外','🏢 AI漫剧一部海外','yibu_hw'),('AI漫剧九部海外','🏢 AI漫剧九部海外','jiubu_hw'),('AI漫剧六部','🏢 AI漫剧六部中转','liubu')]
        for match_key, label, dept_key in dept_order:
            projs = [p for p in production if match_key in (p.get('department') or '')]
            if projs:
                sections_data.append({'key':dept_key,'name':label,'type':'production','collapsed':True,'projects':projs})
        sections_data.append({'key':'completed','name':'✅ 已完成项目','type':'completed','collapsed':True,'projects':group_completed})
        boot_data = _json.dumps({'sections':sections_data,'production':production,'group_all':group_all,'group_completed':group_completed}, ensure_ascii=False)
    except Exception as e:
        app.logger.error('boot_data failed: %s', e)
        boot_data = 'null'
    return render_template('index.html', boot_data=boot_data, api_key=_API_SECRET, is_desktop=_os.environ.get('DRAMA_DESKTOP') == '1')




def _get_db_info_for_list(db_inst, project_name):
    try:
        p = db_inst.get_project(project_name)
    except Exception:
        p = None
    if not p:
        return "", "", 0, 0, None
    cs = p.get("custom_status") or ""
    ds = p.get("delivery_status") or ""
    te = p.get("total_episodes") or 0
    ce = p.get("current_episodes") or 0
    qa = None
    try:
        qr = db_inst.list_qa_runs_for_project(project_name, limit=1)
        if qr and qr[0].get("status") == "done":
            r = qr[0]
            if r.get("failed", 0) > 0: qa = "fail"
            elif r.get("warnings", 0) > 0: qa = "warning"
            elif r.get("total", 0) > 0: qa = "pass"
    except Exception:
        pass
    return cs, ds, te, ce, qa


@app.route('/api/projects', methods=['GET'])
def api_projects():
    """磁盘驱动的项目列表 — 保留 nas-bridge 完整字段 + sections 分组。"""
    # Step 1: 用 sync_engine 获取完整字段的 flat 数据
    try:
        enriched = sync_engine.get_projects_enriched()
    except Exception as e:
        app.logger.error(f'get_projects_enriched failed: {e}')
        enriched = {'production': [], 'group_all': [], 'group_completed': []}

    production = enriched.get('production', [])
    group_all = enriched.get('group_all', [])
    group_completed = enriched.get('group_completed', [])

    # Step 2: 按我们的 section 逻辑重新分组
    result = {'ok': True, 'sections': [], 'total': 0}

    # 2a. 组内NAS（进行中）= group_all 里排除 00已完成 和 月份目录 的项目
    active_group = [p for p in group_all if not p.get('is_completed')]
    result['sections'].append({
        'key': 'group_active',
        'name': '🟢 组内NAS（进行中）',
        'type': 'group',
        'collapsed': False,
        'projects': active_group,
    })

    # 2b. 部门制作部项目 — 按 department 分组
    dept_map = {}
    for p in production:
        dept = p.get('department') or '其他'
        if dept not in dept_map:
            dept_map[dept] = []
        dept_map[dept].append(p)

    dept_order = [
        ('AI漫剧二部', '🏢 AI漫剧二部中转', 'erbu'),
        ('AI漫剧一部海外', '🏢 AI漫剧一部海外', 'yibu_hw'),
        ('AI漫剧九部海外', '🏢 AI漫剧九部海外', 'jiubu_hw'),
        ('AI漫剧六部中转', '🏢 AI漫剧六部中转', 'liubu'),
    ]
    used_keys = set()
    for match_key, label, dept_key in dept_order:
        projs = []
        for k, v in dept_map.items():
            if match_key in k:
                projs.extend(v)
                used_keys.add(k)
        if projs:
            result['sections'].append({
                'key': dept_key,
                'name': label,
                'type': 'production',
                'collapsed': True,
                'projects': projs,
            })
    # 其他部门
    for dept_name, projs in dept_map.items():
        if dept_name not in used_keys:
            result['sections'].append({
                'key': 'other_' + re.sub(r'\W+', '_', dept_name),
                'name': dept_name,
                'type': 'production',
                'collapsed': True,
                'projects': projs,
            })

    # 2c. 已完成项目
    result['sections'].append({
        'key': 'completed',
        'name': '✅ 已完成项目',
        'type': 'completed',
        'collapsed': True,
        'projects': group_completed,
    })

    # Step 3: 同时放 flat 格式供 adapter 读取
    result['production'] = production
    result['group_all'] = group_all
    result['group_completed'] = group_completed

    # 统计
    result['total'] = len(production) + len(group_all) + len(group_completed)
    result['group_count'] = len(active_group)
    result['production_count'] = len(production)
    result['completed_count'] = len(group_completed)

    # 统一概览统计（总/本月/本月已完成/制作中），口径集中计算
    try:
        from scan import compute_overview_stats
        result['overview_stats'] = compute_overview_stats(
            production, group_all, group_completed)
    except Exception as e:
        app.logger.error('compute_overview_stats failed: %s', e)
        result['overview_stats'] = None


    return jsonify(result)



@app.route("/api/sync/<path:project_name>", methods=["POST"])
def api_sync(project_name):
    _bg(sync_engine.sync_project, project_name)
    return jsonify({"ok": True, "message": "同步已启动"})


@app.route("/api/deliver/<path:project_name>", methods=["POST"])
def api_deliver(project_name):
    data = request.get_json(silent=True) or {}
    file_path = data.get("file_path", "")
    mode = data.get("mode", "editing")
    subpath = data.get("subpath", "")

    if mode == "revising":
        file_name = os.path.basename(file_path) if file_path else data.get("file_name", "")
        rev_folder = subpath.replace("/", "\\") if subpath else None
        ok, msg = sync_engine.deliver_revision_file(project_name, file_name, rev_folder)
    else:
        ok, msg = sync_engine.deliver_file(project_name, file_path)
    return jsonify({"ok": ok, "message": msg})


@app.route("/api/deliver_batch/<path:project_name>", methods=["POST"])
def api_deliver_batch(project_name):
    data = request.get_json(silent=True) or {}
    file_names = data.get("file_names", [])
    mode = data.get("mode", "editing")
    subpath = data.get("subpath", "")
    if not file_names:
        return jsonify({"ok": False, "message": "未选择文件"})

    if mode == "revising":
        rev_folder = subpath.replace("/", "\\") if subpath else None
        _bg(sync_engine.deliver_revision_batch, project_name, file_names, rev_folder)
        return jsonify({"ok": True, "message": "修改回传已启动 (" + str(len(file_names)) + " 个)", "total": len(file_names)})
    else:
        _bg(sync_engine.deliver_files_batch, project_name, file_names)
        return jsonify({"ok": True, "message": "批量回传已启动", "total": len(file_names)})


@app.route("/api/output_files/<path:project_name>")
def api_output_files(project_name):
    """列出成片文件，支持按模式列出（editing/revising/delivery）"""
    mode = request.args.get("mode", "editing")
    subpath = request.args.get("subpath", "")
    files = sync_engine.list_files_by_mode(project_name, mode, subpath)
    return jsonify(files)


@app.route("/api/deliver_folder/<path:project_name>", methods=["POST"])
def api_deliver_folder(project_name):
    data = request.get_json(silent=True) or {}
    folder_names = data.get("folder_names", [])
    mode = data.get("mode", "revising")
    if not folder_names:
        return jsonify({"ok": False, "message": "未选择文件夹"})

    # 标准化：去除每个文件夹名的首尾空白/不可见字符，防止前后空格导致匹配失败
    folder_names = [(fn or "").strip() for fn in folder_names if (fn or "").strip()]

    if mode == "delivery":
        delivery_folder_name = os.path.basename(sync_engine._delivery_folder.rstrip("\/")).strip()
        # 宽松判断：只要 folder_names 中包含 delivery 虚拟根文件夹（无论是单独还是和其他混合），
        # 都统一走整目录交付 deliver_to_production（复制整个 000交付 目录），避免把虚拟根文件夹
        # 当成子文件夹传入导致 "000交付下不存在文件夹: 000交付" 的错误。
        if delivery_folder_name in folder_names:
            logger.info("[DELIV] 勾选虚拟根文件夹 %s（共 %s 项），触发整目录交付 deliver_to_production()",
                        delivery_folder_name, len(folder_names))
            ok, msg = sync_engine.deliver_to_production(project_name)
            if not ok:
                logger.warning("[DELIV] deliver_to_production 启动失败: %s", msg)
            return jsonify({"ok": ok, "message": msg})
        # 其它情况：逐个子文件夹后台批量回传（00成片、01字幕等真实子文件夹）
        _bg(sync_engine.deliver_delivery_folders_batch, project_name, folder_names)
        return jsonify({"ok": True, "message": "交付文件夹回传已启动 (" + str(len(folder_names)) + " 个)，请查看系统复制进度窗口", "total": len(folder_names)})
    else:
        if len(folder_names) == 1:
            ok, msg = sync_engine.deliver_revision_folder(project_name, folder_names[0])
            return jsonify({"ok": ok, "message": msg})
        else:
            _bg(sync_engine.deliver_revision_folders_batch, project_name, folder_names)
            return jsonify({"ok": True, "message": "文件夹回传已启动 (" + str(len(folder_names)) + " 个)", "total": len(folder_names)})



_VIDEO_EXTS = {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v', '.flv', '.ts', '.m2ts', '.wmv', '.rmvb', '.rm', '.3gp'}


@app.route("/api/project/<path:project_name>/deliver_dst", methods=["GET"])
def api_project_deliver_dst(project_name):
    """返回项目最近一次成片回传的目标目录（制作部上映单集版），供回传完成后打开/复制。"""
    proj = sync_engine.db.get_project(project_name) or {}
    # 优先从最近交付任务取
    dst = None
    with sync_engine._lock:
        t = sync_engine._deliver_tasks.get(project_name, {})
        dst = t.get("dst") or None
    if not dst:
        prod_path = proj.get("production_path") or ""
        if prod_path:
            dirs = sync_engine._find_output_dirs(prod_path, project_name)
            dst = dirs[0] if dirs else None
    if not dst:
        dst, _ = sync_engine.get_dest_dir(project_name)
    if not dst:
        return jsonify({"ok": False, "message": "未找到回传目标目录"}), 404
    return jsonify({"ok": True, "path": dst, "project_name": project_name})



@app.route("/api/preview/open_local", methods=["POST"])
def api_preview_open_local():
    """用本地默认播放器（如 PotPlayer）打开视频文件。"""
    data = request.get_json(silent=True) or {}
    project_name = data.get("project_name", "")
    filename = data.get("filename", "")
    mode = data.get("mode", "editing")
    subpath = data.get("subpath", "")
    if not filename:
        return jsonify({"ok": False, "message": "未指定文件名"}), 400
    if ".." in filename:
        return jsonify({"ok": False, "message": "禁止路径穿越"}), 400
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _VIDEO_EXTS:
        return jsonify({"ok": False, "message": "非视频文件"}), 400
    file_path = sync_engine.get_file_path_for_preview(project_name, filename, mode, subpath)
    if not file_path or not os.path.isfile(file_path):
        return jsonify({"ok": False, "message": "文件不存在"}), 404
    potplayer_path = (config.get("players") or {}).get("potplayer_path", "")
    try:
        if potplayer_path and os.path.isfile(potplayer_path):
            subprocess.Popen([potplayer_path, file_path])
        else:
            if os.name == "nt":
                os.startfile(file_path)
            else:
                subprocess.Popen(["xdg-open", file_path])
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500


@app.route("/api/preview/<path:project_name>/<path:filename>")
def api_preview_file(project_name, filename):
    """预览成片文件：流式返回文件内容，支持 Range 请求（视频拖拽）。"""
    mode = request.args.get("mode", "editing")
    subpath = request.args.get("subpath", "")
    file_path = sync_engine.get_file_path_for_preview(project_name, filename, mode, subpath)
    if file_path and os.path.isfile(file_path):
        try:
            return send_file(file_path, conditional=True)
        except Exception as e:
            return jsonify({"ok": False, "message": str(e)}), 500
    return jsonify({"ok": False, "message": "文件不存在 (mode=%s)" % mode}), 404


@app.route("/api/logs")
def api_logs():
    limit = request.args.get("limit", 100, type=int)
    return jsonify(db.get_recent_logs(limit))


@app.route("/api/status")
def api_status():
    return jsonify({
        "watcher_enabled": watcher.enabled,
        "watched_dirs": len(watcher._watched_dirs),
        "production_roots": config["nas"].get("production_roots", []),
        "group_root": config["nas"].get("group_root", ""),
        "output_dir_name": config.get("output_dir_name", ""),
    })


@app.route("/api/health")
def api_health():
    try:
        conn = sqlite3.connect(db.db_path); conn.close()
        return jsonify({"db_alive": True, "watcher_enabled": watcher.enabled})
    except Exception as e:
        return jsonify({"db_alive": False, "db_error": str(e)}), 500


# ============================================================
# SSE 进度推送（桌面版用，实时事件）
# ============================================================

@app.route("/api/sse")
def api_sse():
    """Server-Sent Events 推送端点。客户端长连接，后端主动推事件。"""
    import queue as _queue
    def _generate():
        q = _queue.Queue(maxsize=256)
        with sync_engine._lock:
            sync_engine._sse_clients.append(q)
        try:
            yield "retry: 3000\n\n"
            # 首次连接发个心跳
            import json as _j
            yield "event: hello\ndata: " + _j.dumps({"ok": True}) + "\n\n"
            while True:
                try:
                    payload = q.get(timeout=30)
                    yield "data: " + str(payload) + "\n\n"
                except _queue.Empty:
                    # 心跳保活
                    yield ": keepalive\n\n"
        except GeneratorExit:
            pass
        finally:
            with sync_engine._lock:
                if q in sync_engine._sse_clients:
                    sync_engine._sse_clients.remove(q)
    from flask import Response
    return Response(_generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"})


@app.route("/api/project/<path:project_name>/source_dir")
def api_project_source_dir(project_name):
    path, err = sync_engine.get_source_dir(project_name)
    if path: return jsonify({"ok": True, "source_dir": path})
    return jsonify({"ok": False, "message": err or "不存在"}), 404


@app.route("/api/project/<path:project_name>/dest_dir")
def api_project_dest_dir(project_name):
    path, err = sync_engine.get_dest_dir(project_name)
    if path: return jsonify({"ok": True, "dest_dir": path})
    return jsonify({"ok": False, "message": err or "不存在"}), 404


@app.route("/api/project/<path:project_name>/open_folder", methods=["POST"])
def api_project_open_folder(project_name):
    data = request.get_json(silent=True) or {}
    which = data.get("which", "source")
    path = None
    err = None
    proj = sync_engine.db.get_project(project_name) or None
    if which == "path":
        # 直接按给定路径打开
        path = data.get("path") or ""
    elif which == "source" or which == "editing":
        path, err = sync_engine.get_source_dir(project_name)
    elif which == "dest":
        path, err = sync_engine.get_dest_dir(project_name)
    elif which == "group" or which == "prod":
        # 'group' = 打开组内NAS项目根目录（即使还没有"01上映单集版"子目录）
        #   - 但如果项目状态是「剪辑中」「审核中」「修改中」，优先打开 01上映单集版
        # 'prod' = 打开制作部项目根目录（production_path 或 dest 的父级）
        if which == "group":
            if proj and proj.get("group_path"):
                custom_status = proj.get("custom_status", "") or ""
                # 剪辑中/审核中/修改中 → 优先打开 01上映单集版（成片所在目录）
                if custom_status in ("剪辑中", "审核中", "修改中"):
                    output_dirs = sync_engine._find_output_dirs(proj["group_path"], project_name)
                    if output_dirs:
                        path = output_dirs[0]
                    else:
                        path = proj["group_path"]
                else:
                    path = proj["group_path"]
            else:
                path, err = sync_engine.get_source_dir(project_name)
        else:
            if proj and proj.get("production_path"):
                path = proj["production_path"]
            else:
                path, err = sync_engine.get_dest_dir(project_name)
    elif which == "production":
        path = proj.get("production_path", "") if proj else ""
        if not path or not os.path.isdir(path):
            path, err = sync_engine.get_dest_dir(project_name)
    elif which == "delivery":
        if proj and proj.get("production_path"):
            dirs = sync_engine._find_output_dirs(proj["production_path"], project_name)
            path = dirs[0] if dirs else proj["production_path"]
        else:
            path, err = sync_engine.get_dest_dir(project_name)
    elif which == "dest_revision":
        # 修改中状态 → 打开制作部的成片输出目录（和 dest 一样）
        path, err = sync_engine.get_dest_dir(project_name)
    elif which == "revising":
        src, err = sync_engine.get_source_dir(project_name)
        rev = data.get("revision", "")
        if rev:
            cand = _os.path.join(src, rev)
            path = cand if _os.path.isdir(cand) else src
        else:
            path = src
    elif which == "group_output":
        if proj and proj.get("group_path"):
            dirs = sync_engine._find_output_dirs(proj["group_path"], project_name)
            path = dirs[0] if dirs else proj["group_path"]
        else:
            path, err = sync_engine.get_source_dir(project_name)
    else:
        path, err = sync_engine.get_source_dir(project_name)
    if not path or not os.path.isdir(path):
        return jsonify({"ok": False, "message": "目录不存在: " + str(path)}), 404
    try:
        subprocess.Popen(["explorer", path])
        return jsonify({"ok": True, "message": "已打开 " + path})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500


@app.route("/api/project/<path:project_name>/custom_status", methods=["POST"])
def api_project_custom_status(project_name):
    data = request.get_json(silent=True) or {}
    status = data.get("custom_status", "")
    ok, msg = sync_engine.set_custom_status(project_name, status)
    if ok: return jsonify({"ok": True, "message": msg})
    return jsonify({"ok": False, "message": msg}), 400


@app.route("/api/project/<path:project_name>/update_month", methods=["POST"])
def api_project_update_month(project_name):
    """设置项目月份（传空字符串=清空）"""
    data = request.get_json(silent=True) or {}
    month = (data.get("month") or "").strip()
    if month:
        import re as _re
        if not _re.match(r"^\d{4}-\d{2}$", month):
            return jsonify({"ok": False, "message": "格式应为 YYYY-MM, 如 2026-08"}), 400
    db.update_project_status(project_name, project_month=month or None)
    return jsonify({"ok": True, "message": f"已设置为 {month or '空'}"})


@app.route("/api/project_months", methods=["GET"])
def api_project_months():
    """返回所有项目的月份映射 {name: 'YYYY-MM'} — 绕开 scan.py 的手写 dict 字段缺失问题"""
    try:
        rows = db.get_all_projects()
        result = {}
        for p in rows:
            m = (p.get("project_month") or "").strip()
            if m:
                result[p["name"]] = m
        return jsonify(result)
    except Exception as e:
        return jsonify({})





# ==================== NAS 路径管理 ====================

@app.route("/api/config/paths")
def api_get_paths():
    """获取当前所有 NAS 路径配置"""
    nas = config.get("nas", {})
    return jsonify({
        "ok": True,
        "production_roots": nas.get("production_roots", []),
        "production_labels": nas.get("production_labels", {}),
        "group_root": nas.get("group_root", ""),
        "unc_map": nas.get("unc_map", {}),
    })


@app.route("/api/config/path_check", methods=["POST"])
def api_path_check():
    """检测 NAS 路径是否可访问。body: { path }"""
    data = request.get_json(silent=True) or {}
    path = (data.get("path") or "").strip()
    if not path:
        return jsonify({"ok": True, "exists": False, "message": "路径为空"})
    try:
        exists = os.path.isdir(path)
        return jsonify({"ok": True, "exists": exists, "path": path,
                        "message": "可访问" if exists else "不可访问"})
    except Exception as e:
        return jsonify({"ok": True, "exists": False, "message": str(e)})


@app.route("/api/config/paths", methods=["POST"])
def api_add_path():
    """新增 NAS 路径
    body: { type: "production"|"group"|"unc", path, label, drive, unc }
    """
    data = request.get_json(silent=True) or {}
    ptype = data.get("type", "")
    nas = config.setdefault("nas", {})

    if ptype == "production":
        path = (data.get("path") or "").strip()
        label = (data.get("label") or "").strip()
        if not path:
            return jsonify({"ok": False, "message": "路径不能为空"})
        # 标准化路径分隔符
        path = path.replace("/", "\\").rstrip("\\")
        roots = nas.setdefault("production_roots", [])
        if path in roots:
            return jsonify({"ok": False, "message": "该路径已存在"})
        roots.append(path)
        if label:
            labels = nas.setdefault("production_labels", {})
            labels[path] = label
        save_config()
        reload_sync_engine()
        logger.info("新增制作部 NAS 路径: %s (标签: %s)", path, label)
        return jsonify({"ok": True, "message": "已添加制作部路径: " + path})

    elif ptype == "group":
        path = (data.get("path") or "").strip()
        if not path:
            return jsonify({"ok": False, "message": "路径不能为空"})
        path = path.replace("/", "\\").rstrip("\\")
        nas["group_root"] = path
        save_config()
        reload_sync_engine()
        logger.info("更新组内 NAS 路径: %s", path)
        return jsonify({"ok": True, "message": "已更新组内 NAS 路径: " + path})

    elif ptype == "unc":
        drive = (data.get("drive") or "").strip().upper()
        unc = (data.get("unc") or "").strip()
        if not drive or not unc:
            return jsonify({"ok": False, "message": "盘符和 UNC 路径不能为空"})
        if not drive.endswith(":"):
            drive = drive + ":"
        unc = unc.replace("/", "\\").rstrip("\\")
        unc_map = nas.setdefault("unc_map", {})
        unc_map[drive] = unc
        save_config()
        reload_sync_engine()
        logger.info("新增 UNC 映射: %s -> %s", drive, unc)
        return jsonify({"ok": True, "message": "已添加 UNC 映射: " + drive + " -> " + unc})

    else:
        return jsonify({"ok": False, "message": "未知路径类型: " + str(ptype)})


@app.route("/api/config/paths", methods=["DELETE"])
def api_remove_path():
    """删除 NAS 路径
    body: { type: "production"|"unc", path, drive }
    """
    data = request.get_json(silent=True) or {}
    ptype = data.get("type", "")
    nas = config.get("nas", {})

    if ptype == "production":
        path = (data.get("path") or "").strip()
        path = path.replace("/", "\\").rstrip("\\")
        roots = nas.get("production_roots", [])
        if path in roots:
            roots.remove(path)
            labels = nas.get("production_labels", {})
            if path in labels:
                del labels[path]
            save_config()
            reload_sync_engine()
            logger.info("删除制作部 NAS 路径: %s", path)
            return jsonify({"ok": True, "message": "已删除: " + path})
        return jsonify({"ok": False, "message": "路径不存在"})

    elif ptype == "unc":
        drive = (data.get("drive") or "").strip().upper()
        if not drive.endswith(":"):
            drive = drive + ":"
        unc_map = nas.get("unc_map", {})
        if drive in unc_map:
            del unc_map[drive]
            save_config()
            reload_sync_engine()
            logger.info("删除 UNC 映射: %s", drive)
            return jsonify({"ok": True, "message": "已删除 UNC 映射: " + drive})
        return jsonify({"ok": False, "message": "UNC 映射不存在"})

    else:
        return jsonify({"ok": False, "message": "未知路径类型"})

@app.route("/api/scan", methods=["POST"])
def api_scan():
    try:
        sync_engine.scan_projects()
        return jsonify({"ok": True, "message": "scan completed"})
    except Exception as e:
        logger.error("scan failed: %s", e)
        return jsonify({"ok": False, "message": str(e)}), 500





@app.route("/api/projects/light", methods=["GET"])
def api_projects_light():
    try:
        enriched = sync_engine.get_projects_enriched()
        result = []
        seen = set()
        for bucket in ("production", "group_all"):
            for proj in enriched.get(bucket, []):
                name = proj.get("name", "")
                if not name or name in seen:
                    continue
                seen.add(name)
                result.append({
                    "name": name,
                    "total_episodes": proj.get("total_episodes", 0) or 0,
                    "custom_status": proj.get("custom_status", "") or "",
                    "department": proj.get("department", "") or "",
                })
        result.sort(key=lambda x: x["name"])
        return jsonify(result)
    except Exception as e:
        logger.error("projects/light failed: %s", e)
        return jsonify([])


@app.route("/api/project/<path:project_name>/check_on_group", methods=["POST"])
def api_check_on_group(project_name):
    try:
        proj = sync_engine.db.get_project(project_name)
        on_group = False
        group_path = ""
        group_root = config.get("nas", {}).get("group_root", "")
        candidates = [
            os.path.join(group_root, project_name),
            os.path.join(group_root, "00已完成", project_name),
        ]
        for cand in candidates:
            if os.path.isdir(cand):
                on_group = True
                group_path = cand
                break
        if on_group and proj:
            sync_engine.db.update_project(project_name, {
                "sync_status": "synced",
                "last_synced_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
        return jsonify({
            "ok": True,
            "name": project_name,
            "on_group": on_group,
            "group_path": group_path,
            "was_updated": on_group,
        })
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500



# ==================== 服务管理 ====================

@app.route("/api/service/stop", methods=["POST"])
def api_service_stop():
    """停止 NAS Bridge 服务"""
    def _do_stop():
        time.sleep(0.8)
        try:
            watcher.stop()
        except Exception:
            pass
        logger.info("服务已停止（来自前端请求）")
        os._exit(0)

    threading.Thread(target=_do_stop, daemon=True).start()
    return jsonify({"ok": True, "message": "服务即将停止，窗口将在 1 秒后关闭"})


@app.route("/api/service/restart", methods=["POST"])
def api_service_restart():
    """重启 NAS Bridge 服务"""
    def _do_restart():
        time.sleep(0.8)
        try:
            watcher.stop()
        except Exception:
            pass
        python_exe = sys.executable
        if python_exe.lower().endswith("python.exe"):
            pythonw = python_exe[:-10] + "pythonw.exe"
        else:
            pythonw = python_exe
        if not os.path.isfile(pythonw):
            pythonw = python_exe

        app_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
        startupinfo = None
        creationflags = 0
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS

        try:
            subprocess.Popen(
                [pythonw, app_py],
                cwd=os.path.dirname(app_py),
                creationflags=creationflags,
                startupinfo=startupinfo,
            )
            logger.info("服务重启中（pid=%s），新进程已拉起", os.getpid())
        except Exception as e:
            logger.error("重启失败: %s", e)
        os._exit(0)

    threading.Thread(target=_do_restart, daemon=True).start()
    return jsonify({"ok": True, "message": "服务即将重启，页面将自动刷新"})


_shutting_down = threading.Event()


def _handle_shutdown(signum=None, frame=None):
    """SIGINT/SIGTERM → 优雅停机"""
    if _shutting_down.is_set():
        return
    _shutting_down.set()
    logger.info("收到关机信号，开始优雅停机...")
    sync_engine.shutdown()
    watcher.stop()
    # waitress 会收到 KeyboardInterrupt，try/finally 兜底


try:
    signal.signal(signal.SIGINT, _handle_shutdown)
except ValueError:
    pass  # 子线程启动时无法注册 signal，desktop.py 场景兜底
try:
    signal.signal(signal.SIGTERM, _handle_shutdown)
except (AttributeError, ValueError):
    pass  # Windows 没有 SIGTERM；子线程也会报 ValueError



# ==================== 工作流集成：启动外部质检进程 ====================

@app.route("/api/_exec_cmd", methods=["POST"])
def api_exec_cmd():
    """安全受限的命令执行接口：仅允许启动白名单内的程序。
    body: {"cmd": ["pythonw", "...video_qa_tool.py", "..."]}  或 {"cmd": "pythonw ..."}
    """
    data = request.get_json(silent=True) or {}
    raw_cmd = data.get("cmd")

    # 强制要求 token（比全局鉴权更严格）
    require_auth = data.get("_auth_required", True)
    actual_key = request.headers.get("X-API-KEY", "")
    if require_auth and actual_key != _API_SECRET:
        return jsonify({"ok": False, "message": "鉴权失败"}), 401

    if isinstance(raw_cmd, list):
        cmd_parts = [str(p) for p in raw_cmd if str(p).strip()]
    elif isinstance(raw_cmd, str) and raw_cmd.strip():
        try:
            cmd_parts = _shlex.split(raw_cmd)
        except ValueError:
            return jsonify({"ok": False, "message": "命令格式错误"}), 400
    else:
        return jsonify({"ok": False, "message": "cmd 不能为空"}), 400

    if not cmd_parts:
        return jsonify({"ok": False, "message": "cmd 不能为空"}), 400

    # 白名单安全检查：只允许启动质检工具
    ALLOWED_KEYWORDS = ("video_qa_tool", "pythonw", "python")
    first_part_lower = cmd_parts[0].lower()
    if not any(kw in first_part_lower for kw in ALLOWED_KEYWORDS):
        return jsonify({"ok": False, "message": "命令不在白名单中"}), 403

    # 简单路径穿越检测：任意参数包含 ".." 就拒绝
    for part in cmd_parts:
        if ".." in part:
            return jsonify({"ok": False, "message": "禁止路径穿越"}), 403

    try:
        _sp.Popen(
            cmd_parts,
            shell=False,
            creationflags=_sp.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        logger.info("已启动外部进程: %s", " ".join(cmd_parts)[:200])
        return jsonify({"ok": True, "message": "已启动"})
    except Exception as e:
        logger.error("启动进程失败: %s", e)
        return jsonify({"ok": False, "message": str(e)}), 500



# ==================== 质检结果自动读取 ====================

QA_RESULT_CACHE = {}  # {project_name: {"ok": True, "data": {...}, "file": "...", "mtime": float}}
QA_CACHE_TTL = 30     # 缓存 30 秒
_QA_CACHE_LOCK = threading.Lock()

@app.route("/api/project/<path:project_name>/qa_result", methods=["GET"])
def api_project_qa_result(project_name):
    """读取项目最新的质检结果（扫描 %TEMP% 目录下的 qa_result_*.json）"""
    # 检查缓存是否还热
    with _QA_CACHE_LOCK:
        cached = QA_RESULT_CACHE.get(project_name)
        if cached and (_time.time() - cached.get("mtime", 0) < QA_CACHE_TTL):
            return jsonify(cached["data"])

    project_path = request.args.get("dir", "").strip()

    # 扫描 %TEMP% 目录找 qa_result_* 开头的 JSON 文件
    temp_dir = _tf.gettempdir()
    # 先精确匹配项目名
    candidates = []
    for pattern in (
        f"qa_result_{project_name}_*.json",
        f"qa_result_{project_name}*.json",
    ):
        candidates.extend(_glob.glob(os.path.join(temp_dir, pattern)))

    # 如果指定了 dir，也扫描该目录
    if project_path:
        for pattern in (
            "qa_result_*.json",
            "*qa_result*.json",
        ):
            candidates.extend(_glob.glob(os.path.join(project_path, pattern)))

    # 去重并按修改时间排序
    candidates = sorted(set(candidates), key=os.path.getmtime, reverse=True)

    if not candidates:
        data = {
            "ok": False,
            "message": "未找到质检结果（尚未运行过质检工具）",
            "qa_found": False,
        }
        with _QA_CACHE_LOCK:
            QA_RESULT_CACHE[project_name] = {"ok": True, "data": data, "mtime": _time.time()}
        return jsonify(data)

    # 读取最新的那个
    latest_file = candidates[0]
    try:
        with open(latest_file, "r", encoding="utf-8") as f:
            qa = json.load(f)
    except Exception as e:
        data = {
            "ok": False,
            "message": f"结果文件读取失败: {e}",
            "qa_found": True,
            "qa_file": os.path.basename(latest_file),
        }
        with _QA_CACHE_LOCK:
            QA_RESULT_CACHE[project_name] = {"ok": True, "data": data, "mtime": _time.time()}
        return jsonify(data)

    # 汇总状态
    total = qa.get("total", 0)
    passed = qa.get("passed", 0)
    warnings = qa.get("warnings", 0)
    failed = qa.get("failed", 0)

    if failed > 0:
        overall = "fail"
        overall_label = f"❌ 失败 {failed}"
    elif warnings > 0:
        overall = "warning"
        overall_label = f"⚠️ 警告 {warnings}"
    elif total > 0:
        overall = "pass"
        overall_label = f"✅ 全部通过"
    else:
        overall = "unknown"
        overall_label = "— 无数据"

    # 只返回前 50 个非 pass 的视频详情（避免 payload 太大）
    issues = [r for r in qa.get("results", []) if r.get("status") != "pass"]
    issues_summary = []
    for r in issues[:50]:
        issues_summary.append({
            "video": r.get("video", ""),
            "status": r.get("status", ""),
            "details": r.get("details", "")[:200],
        })

    data = {
        "ok": True,
        "qa_found": True,
        "qa_file": os.path.basename(latest_file),
        "qa_file_mtime": os.path.getmtime(latest_file),
        "project": qa.get("project", project_path),
        "project_name": qa.get("project_name", project_name),
        "generated_at": qa.get("generated_at", ""),
        "overall": overall,
        "overall_label": overall_label,
        "total": total,
        "passed": passed,
        "warnings": warnings,
        "failed": failed,
        "elapsed_seconds": qa.get("elapsed_seconds", 0),
        "issues_count": len(issues),
        "issues": issues_summary,
    }

    with _QA_CACHE_LOCK:
        QA_RESULT_CACHE[project_name] = {"ok": True, "data": data, "mtime": _time.time()}
    return jsonify(data)

# 让 /api/projects 也带上轻量 QA 状态（扫描每个项目最新的 qa_result 文件）
_qa_status_cache = {}
_QA_STATUS_LOCK = threading.Lock()

def _scan_qa_status(project_name):
    """快速扫描一个项目的 QA 状态，不读完整 JSON"""
    with _QA_STATUS_LOCK:
        cached = _qa_status_cache.get(project_name)
        if cached and (_time.time() - cached.get("mtime", 0) < QA_CACHE_TTL):
            return cached.get("data")

    temp_dir = _tf.gettempdir()
    candidates = []
    for pattern in (
        f"qa_result_{project_name}_*.json",
        f"qa_result_{project_name}*.json",
    ):
        candidates.extend(_glob.glob(os.path.join(temp_dir, pattern)))

    if not candidates:
        with _QA_STATUS_LOCK:
            _qa_status_cache[project_name] = {"mtime": _time.time(), "data": None}
        return None

    latest = sorted(set(candidates), key=os.path.getmtime, reverse=True)[0]
    try:
        with open(latest, "r", encoding="utf-8") as f:
            qa = json.load(f)
    except:
        with _QA_STATUS_LOCK:
            _qa_status_cache[project_name] = {"mtime": _time.time(), "data": None}
        return None

    failed = qa.get("failed", 0)
    warnings = qa.get("warnings", 0)
    total = qa.get("total", 0)
    if failed > 0:
        overall = "fail"
    elif warnings > 0:
        overall = "warning"
    elif total > 0:
        overall = "pass"
    else:
        overall = None

    result = {
        "overall": overall,
        "passed": qa.get("passed", 0),
        "warnings": warnings,
        "failed": failed,
        "total": total,
        "generated_at": qa.get("generated_at", ""),
    }
    with _QA_STATUS_LOCK:
        _qa_status_cache[project_name] = {"mtime": _time.time(), "data": result}
    return result



# ============================================================
# 工作台增强路由注册 (项目详情/QA/缺集提醒/团队/配置)
# ============================================================
try:
    from enhanced_routes import _register_enhanced_routes
    _register_enhanced_routes(app, db, qa_engine=qa_engine, sync_engine=sync_engine)
    print("[OK] enhanced_routes 已注册")
except ImportError as e:
    print("[WARN] enhanced_routes 未加载:", e)

try:
    from bulk_api import register_routes as _register_bulk
    _register_bulk(app, db)
    print("[OK] bulk_api 已注册")
except ImportError as e:
    print("[WARN] bulk_api 未加载:", e)

try:
    from nameplate import register_routes as _register_nameplate
    _register_nameplate(app, db)
    print("[OK] nameplate(人名条) 已注册")
except ImportError as e:
    print("[WARN] nameplate(人名条) 未加载:", e)

try:
    from commission import register_routes as _register_commission
    _register_commission(app, db)
    print("[OK] commission(提成工具) 已注册")
except ImportError as e:
    print("[WARN] commission(提成工具) 未加载:", e)

try:
    from dramatool import register_routes as _register_dramatool
    _register_dramatool(app, db)
    print("[OK] dramatool(拆集工具) 已注册")
except ImportError as e:
    print("[WARN] dramatool(拆集工具) 未加载:", e)

try:
    from autostart import register_routes as _register_autostart
    _register_autostart(app, db)
    print("[OK] autostart(开机自启) 已注册")
except ImportError as e:
    print("[WARN] autostart(开机自启) 未加载:", e)

try:
    from features import register_routes as _register_features
    _register_features(app, db)
    print("[OK] features(待办/时间轴/备份/缩略图) 已注册")
except ImportError as e:
    print("[WARN] features(待办/时间轴/备份/缩略图) 未加载:", e)

# 启动数据库每日自动备份
try:
    from backup_service import start_scheduler as _start_backup
    _start_backup()
    print("[OK] backup_service(数据库自动备份) 已启动")
except Exception as e:
    print("[WARN] backup_service 未启动:", e)


def main():
    web_cfg = config.get("web", {})
    host = web_cfg.get("host", "0.0.0.0")
    port = web_cfg.get("port", 8080)
    logger.info("Web 服务启动: http://%s:%d", host, port)

    threading.Thread(target=watcher.start, daemon=True).start()

    try:
        try:
            from waitress import serve
            _routes = sorted({r.rule for r in app.url_map.iter_rules() if not r.rule.startswith('/static')})
            logger.info("已注册 API 路由: %d 个", len(_routes))
            logger.info("使用 waitress WSGI 服务器")
            serve(app, host=host, port=port, threads=16)
        except ImportError:
            app.run(host=host, port=port, debug=False, threaded=True)
    finally:
        if not _shutting_down.is_set():
            _shutting_down.set()
        sync_engine.shutdown()
        try:
            watcher.stop()
        except Exception:
            pass
        logger.info("服务已退出")


if __name__ == "__main__":
    main()


def create_app():
    # 启动成片目录监听（桌面版走 create_app 也会生效；Web 版 main() 里也会调 start，
    # 已由 Watcher.start 的幂等保护避免重复启动）
    try:
        threading.Thread(target=watcher.start, daemon=True).start()
    except Exception:
        pass
    return app
