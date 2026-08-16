# -*- coding: utf-8 -*-
"""人名条识别插件 — Web 接入层。

把 plugins/nameplate/script_parser.py 的剧本解析能力暴露为工作台 API：
  POST /api/nameplate/parse   上传 .docx 剧本 → 解析前 N 集首次出场人物/场景 → 生成 Excel
  GET  /api/nameplate/output/<file>   下载生成的 Excel
  GET  /api/nameplate/files    列出已生成的解析结果文件

保留插件独立能力：GUI(cli) 仍可通过 start_tool.bat / python script_parser.py 直接使用。
"""
import os
import sys
import glob
import logging
import threading
from datetime import datetime
from flask import jsonify, request, send_file

logger = logging.getLogger("nameplate")

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PLUGIN_DIR = os.path.join(_BASE, "plugins", "nameplate")
_SCRIPT = os.path.join(_PLUGIN_DIR, "script_parser.py")
_OUTPUT_DIR = os.path.join(_BASE, "data", "nameplate_output")

# 解析在后台线程执行，避免阻塞 Flask 请求；用简单锁防并发写同名结果
_parse_lock = threading.Lock()


def _script_available():
    return os.path.isfile(_SCRIPT)


def _get_parser():
    """加载插件脚本模块（进程内调用，保留其全部逻辑）。失败返回 None。"""
    if _SCRIPT not in sys.modules and _PLUGIN_DIR not in sys.path:
        sys.path.insert(0, _PLUGIN_DIR)
    try:
        import script_parser
        return script_parser
    except Exception as e:
        logger.warning("加载 script_parser 失败: %s", e)
        return None


def _sanitize_name(name):
    """去掉路径分隔符/危险字符，避免下载路径穿越。"""
    base = os.path.basename(name or "")
    return os.path.basename(base)


def register_routes(app, db):
    os.makedirs(_OUTPUT_DIR, exist_ok=True)

    # ---- 元信息 ----
    @app.route("/api/nameplate/info", methods=["GET"])
    def nameplate_info():
        return jsonify({
            "ok": True,
            "available": _script_available(),
            "plugin_dir": _PLUGIN_DIR,
            "output_dir": _OUTPUT_DIR,
            "version": "1.0",
        })

    # ---- 列出已生成结果 ----
    @app.route("/api/nameplate/files", methods=["GET"])
    def nameplate_files():
        if not os.path.isdir(_OUTPUT_DIR):
            return jsonify({"ok": True, "files": []})
        files = []
        for p in sorted(glob.glob(os.path.join(_OUTPUT_DIR, "*")),
                        key=os.path.getmtime, reverse=True)[:50]:
            if os.path.isfile(p):
                files.append({
                    "name": os.path.basename(p),
                    "size": os.path.getsize(p),
                    "mtime": datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M:%S"),
                })
        return jsonify({"ok": True, "files": files})

    # ---- 解析 ----
    @app.route("/api/nameplate/parse", methods=["POST"])
    def nameplate_parse():
        if not _script_available():
            return jsonify({"ok": False, "message": "人名条插件未安装"}), 500

        # 支持两种输入：multipart 上传 或 JSON 传 docx 路径
        file = request.files.get("file") if request.files else None
        docx_path = ""
        if file and file.filename:
            # 保存上传文件到临时目录
            tmp_dir = os.path.join(_BASE, "data", "nameplate_uploads")
            os.makedirs(tmp_dir, exist_ok=True)
            docx_path = os.path.join(tmp_dir, _sanitize_name(file.filename))
            file.save(docx_path)
        else:
            body = request.get_json(silent=True) or {}
            docx_path = (body.get("docx_path") or "").strip()

        if not docx_path or not os.path.isfile(docx_path):
            return jsonify({"ok": False, "message": "缺少有效的 .docx 剧本文件"}), 400

        if not docx_path.lower().endswith(".docx"):
            return jsonify({"ok": False, "message": "仅支持 .docx 剧本"}), 400

        max_ep = request.form.get("episodes") or (
            (request.get_json(silent=True) or {}).get("episodes")) or 30
        try:
            max_ep = int(max_ep)
        except (TypeError, ValueError):
            max_ep = 30
        max_ep = max(1, min(max_ep, 200))

        parser = _get_parser()
        if parser is None:
            return jsonify({"ok": False, "message": "人名条解析模块加载失败"}), 500

        base_name = os.path.splitext(os.path.basename(docx_path))[0]
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(_OUTPUT_DIR, f"{base_name}_{stamp}.xlsx")

        # 后台线程解析，立即返回任务状态；也可在前端轮询 files 列表
        def _do_parse():
            try:
                with _parse_lock:
                    data, err = parser.parse_script(docx_path, max_ep)
                    if err:
                        logger.warning("解析失败: %s", err)
                        return
                    parser.make_excel(data, out_path)
                    logger.info("人名条解析完成: %s (%d人物, %d场景)",
                                out_path, len(data.get("people", [])),
                                len(data.get("scenes", [])))
            except Exception as e:
                logger.exception("人名条解析异常: %s", e)
            finally:
                # 清理上传的临时文件
                try:
                    if os.path.exists(docx_path) and os.path.dirname(docx_path).endswith("nameplate_uploads"):
                        os.remove(docx_path)
                except Exception:
                    pass

        threading.Thread(target=_do_parse, daemon=True).start()
        return jsonify({
            "ok": True,
            "message": f"开始解析「{os.path.basename(docx_path)}」前{max_ep}集，完成后可下载",
            "expected_output": os.path.basename(out_path),
        })

    # ---- 下载结果 ----
    @app.route("/api/nameplate/output/<path:filename>", methods=["GET"])
    def nameplate_download(filename):
        safe = _sanitize_name(filename)
        path = os.path.join(_OUTPUT_DIR, safe)
        if not os.path.isfile(path):
            return jsonify({"ok": False, "message": "文件不存在"}), 404
        return send_file(path, as_attachment=True,
                         download_name=safe,
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
