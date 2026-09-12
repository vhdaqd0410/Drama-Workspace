# -*- coding: utf-8 -*-
"""组员端本地助手 —— 跑在组员自己电脑上。

职责（只干「浏览器干不了」的事）：
  1. 提供 http://127.0.0.1:8091 本地入口
  2. 把主端界面反向代理过来（组员看到的就是主端那套界面 → 天然在线更新）
  3. 提供本地文件接口：建项目、拉素材、开 PR（/local/*）
  4. 保存组员本机配置（本地项目目录、姓名、PR 模板）

不做：不连数据库、不碰 NAS 写操作、不存储任何主端状态。

启动：双击 启动.bat，或 python member_agent.py
"""
import os
import re
import sys
import json
import socket
import threading
import webbrowser
import urllib.request
import urllib.error
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import local_ops  # noqa: E402

CONFIG_PATH = os.path.join(BASE_DIR, "member_config.json")
LOCAL_PORT = 8091
VERSION = "1.0.0"

# 运行期状态
_TASKS = {}          # project -> {status, stage, done, total, message, result}
_TASK_LOCK = threading.Lock()


# ---------------- 配置 ----------------
DEFAULT_CONFIG = {
    "server_url": "",        # 主端地址，如 http://172.16.28.172:8089
    "api_key": "",           # 主端密钥（由主端生成后填入）
    "member_name": "",       # 组员姓名（用于分集匹配）
    "local_root": "",        # 本地项目目录，如 D:\\剪辑项目
    "pr_template": "",       # PR 模板 .prproj 路径
    "pr_exe": "",            # PR 可执行文件（留空自动探测）
    "open_pr": True,         # 拉完是否自动开 PR
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        if os.path.isfile(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f) or {})
    except Exception:
        pass
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ---------------- 主端地址发现 ----------------
def discover_server():
    """从组内 NAS 的 _协作/endpoint.json 读取主端地址（主端定期写入）。"""
    cfg = load_config()
    group_root = cfg.get("group_root") or ""
    # 若配置里没写，尝试常见盘符
    candidates = []
    if group_root:
        candidates.append(group_root)
    for drive in ("O:", "N:", "Z:", "Y:"):
        candidates.append(drive + "\\AI漫剧剪辑一组")
    for root in candidates:
        p = os.path.join(root, "_协作", "endpoint.json")
        try:
            if os.path.isfile(p):
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f) or {}
                host, port = d.get("host"), d.get("port")
                if host and port:
                    return "http://%s:%s" % (host, port), d
        except Exception:
            continue
    return "", None


# ---------------- 转发到主端 ----------------
def call_main(path, method="GET", body=None, timeout=60):
    """带鉴权调用主端 API。返回 (status, text)。"""
    cfg = load_config()
    base = (cfg.get("server_url") or "").rstrip("/")
    if not base:
        return 0, '{"ok":false,"message":"未配置主端地址"}'
    url = base + path
    data = None
    headers = {"X-API-KEY": cfg.get("api_key") or ""}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, json.dumps({"ok": False, "message": "无法连接主端: %s" % e},
                             ensure_ascii=False)


# ---------------- 本地任务：创建项目 ----------------
def _run_create(project_name, cfg):
    def _prog(stage, done, total):
        with _TASK_LOCK:
            _TASKS[project_name] = {
                "status": "running", "stage": stage,
                "done": done, "total": total, "message": "",
            }

    try:
        # 先问主端要项目信息（含 NAS 路径与分集）
        st, txt = call_main("/api/project/" + urllib.parse.quote(project_name))
        if st != 200:
            with _TASK_LOCK:
                _TASKS[project_name] = {"status": "error", "stage": "失败",
                                        "message": "读取项目失败(%s): %s" % (st, txt[:200])}
            return
        try:
            info = json.loads(txt)
            info = info.get("project") or info
        except Exception:
            info = {}

        ok, msg, stats = local_ops.create_local_project(cfg, project_name, info,
                                                       progress_cb=_prog)
        with _TASK_LOCK:
            _TASKS[project_name] = {
                "status": "done" if ok else "error",
                "stage": "完成" if ok else "失败",
                "done": 1, "total": 1, "message": msg, "result": stats,
            }
    except Exception as e:
        with _TASK_LOCK:
            _TASKS[project_name] = {"status": "error", "stage": "异常",
                                    "message": str(e)}


# ---------------- HTTP 服务 ----------------
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt, *args):
        pass    # 静音

    # ---- 工具 ----
    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0:
                return {}
            return json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except Exception:
            return {}

    def _raw(self, body, ctype="text/html; charset=utf-8", status=200):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    # ---- GET ----
    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/local/ping":
            return self._json({"ok": True, "version": VERSION})

        if path == "/local/config":
            cfg = load_config()
            cfg.pop("api_key", None)      # 不回显密钥
            return self._json({"ok": True, "config": cfg})

        if path == "/local/discover":
            url, d = discover_server()
            return self._json({"ok": bool(url), "url": url, "raw": d})

        # ★ 拦截本地项目进度查询（前端用主端的路径来查）
        mg = re.match(r"^/api/project/(.+?)/local_project_progress$", path)
        if mg:
            proj = urllib.parse.unquote(mg.group(1))
            with _TASK_LOCK:
                t = dict(_TASKS.get(proj, {}))
            if t:
                return self._json({"ok": True, "task": t})
            # 本机没这个任务记录 → 反代给主端（兼容旧行为）
            return self._proxy()

        if path == "/local/task":
            qs = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            proj = (qs.get("project") or [""])[0]
            with _TASK_LOCK:
                t = dict(_TASKS.get(proj, {}))
            return self._json({"ok": True, "task": t})

        if path == "/local/status":
            return self._json(self.status_payload())

        if path in ("/", "/index.html"):
            return self._serve_setup_or_proxy()

        # 其他一律反代到主端
        return self._proxy()

    def _serve_setup_or_proxy(self):
        cfg = load_config()
        # 未配置主端地址 → 显示引导页
        if not cfg.get("server_url"):
            return self._raw(SETUP_HTML.replace("{{VERSION}}", VERSION))
        return self._proxy()

    # ---- POST ----
    def do_POST(self):
        path = self.path.split("?")[0]

        # ★ 关键拦截：创建本地项目必须在本机执行，不能反代到主端
        m = re.match(r"^/api/project/(.+?)/create_local_project$", path)
        if m:
            proj = urllib.parse.unquote(m.group(1))
            cfg = load_config()
            if not cfg.get("local_root"):
                return self._json({"ok": False,
                                   "message": "请先在助手设置页填写本地项目目录"}, 400)
            with _TASK_LOCK:
                cur = _TASKS.get(proj, {})
                if cur.get("status") == "running":
                    return self._json({"ok": False, "message": "该项目正在创建中"}, 409)
                _TASKS[proj] = {"status": "running", "stage": "准备中",
                                "done": 0, "total": 1, "message": ""}
            threading.Thread(target=_run_create, args=(proj, cfg), daemon=True).start()
            return self._json({"ok": True, "message": "已开始创建本地项目（本机）"})

        # 同理拦截进度查询
        if path == "/local/config":
            data = self._read_body()
            cfg = load_config()
            for k in ("server_url", "api_key", "member_name", "local_root",
                      "pr_template", "pr_exe", "group_root"):
                if k in data:
                    cfg[k] = str(data[k] or "").strip()
            if "open_pr" in data:
                cfg["open_pr"] = bool(data["open_pr"])
            save_config(cfg)
            return self._json({"ok": True})

        if path == "/local/discover_save":
            url, d = discover_server()
            if not url:
                return self._json({"ok": False, "message": "未在 NAS 上找到主端地址文件"})
            cfg = load_config()
            cfg["server_url"] = url
            if d.get("api_secret"):
                cfg["api_key"] = d["api_secret"]
            if d.get("group_root"):
                cfg["group_root"] = d["group_root"]
            save_config(cfg)
            return self._json({"ok": True, "url": url})

        if path == "/local/create":
            data = self._read_body()
            proj = (data.get("project") or "").strip()
            if not proj:
                return self._json({"ok": False, "message": "缺少 project"}, 400)
            cfg = load_config()
            if not cfg.get("local_root"):
                return self._json({"ok": False, "message": "请先在设置里填写本地项目目录"}, 400)
            with _TASK_LOCK:
                cur = _TASKS.get(proj, {})
                if cur.get("status") == "running":
                    return self._json({"ok": False, "message": "该项目正在创建中"}, 409)
                _TASKS[proj] = {"status": "running", "stage": "准备中",
                                "done": 0, "total": 1, "message": ""}
            threading.Thread(target=_run_create, args=(proj, cfg), daemon=True).start()
            return self._json({"ok": True, "message": "已开始创建本地项目"})

        if path == "/local/open_dir":
            data = self._read_body()
            p = (data.get("path") or "").strip()
            if p and os.path.isdir(p):
                try:
                    os.startfile(p)  # noqa
                    return self._json({"ok": True})
                except Exception as e:
                    return self._json({"ok": False, "message": str(e)})
            return self._json({"ok": False, "message": "目录不存在"})

        # 其他 POST 一律反代到主端（打勾等）
        return self._proxy()

    def do_PUT(self):
        return self._proxy()

    def do_DELETE(self):
        return self._proxy()

    # ---- 反代 ----
    def _proxy(self):
        """把请求转发到主端，原样返回（含鉴权头注入）。"""
        cfg = load_config()
        base = (cfg.get("server_url") or "").rstrip("/")
        if not base:
            return self._raw(SETUP_HTML.replace("{{VERSION}}", VERSION))
        url = base + self.path
        headers = {"X-API-KEY": cfg.get("api_key") or ""}
        for h in ("Content-Type", "Accept"):
            if self.headers.get(h):
                headers[h] = self.headers.get(h)
        body = None
        n = int(self.headers.get("Content-Length") or 0)
        if n > 0:
            body = self.rfile.read(n)
        req = urllib.request.Request(url, data=body, headers=headers,
                                     method=self.command)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
                ctype = r.headers.get("Content-Type", "text/html; charset=utf-8")
                return self._raw(data, ctype, r.status)
        except urllib.error.HTTPError as e:
            data = e.read()
            ctype = e.headers.get("Content-Type", "text/html; charset=utf-8")
            return self._raw(data, ctype, e.code)
        except Exception as e:
            return self._json({"ok": False, "message": "主端不可达: %s" % e}, 502)

    # ---- 状态 ----
    def status_payload(self):
        cfg = load_config()
        pr_ok = bool(cfg.get("pr_template") and os.path.isfile(cfg.get("pr_template")))
        root_ok = bool(cfg.get("local_root") and os.path.isdir(cfg.get("local_root")))
        return {
            "ok": True,
            "version": VERSION,
            "server_url": cfg.get("server_url") or "",
            "configured": bool(cfg.get("server_url") and cfg.get("member_name")
                               and cfg.get("local_root")),
            "member_name": cfg.get("member_name") or "",
            "local_root": cfg.get("local_root") or "",
            "local_root_exists": root_ok,
            "pr_template_set": pr_ok,
            "pr_exe": cfg.get("pr_exe") or local_ops._find_pr_exe(),
        }


# ---------------- 引导页 ----------------
SETUP_HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>剪辑助手 · 首次设置</title>
<style>
  *{box-sizing:border-box}
  body{margin:0;font-family:-apple-system,"Microsoft YaHei",sans-serif;background:#f5f6fa;color:#1d1d1f;padding:32px 16px}
  .wrap{max-width:620px;margin:0 auto}
  .card{background:#fff;border-radius:16px;padding:26px 28px;box-shadow:0 6px 28px rgba(0,0,0,.08);margin-bottom:18px}
  h1{font-size:20px;margin:0 0 4px}
  .sub{color:#86868b;font-size:13px;margin-bottom:22px}
  label{display:block;font-size:13px;font-weight:600;margin:16px 0 6px}
  input[type=text]{width:100%;padding:10px 12px;border:1px solid #d2d2d7;border-radius:10px;font-size:14px;font-family:inherit}
  input[type=text]:focus{outline:none;border-color:#0071e3;box-shadow:0 0 0 3px rgba(0,113,227,.12)}
  .hint{font-size:12px;color:#86868b;margin-top:5px;line-height:1.55}
  button{background:#0071e3;color:#fff;border:none;border-radius:10px;padding:11px 20px;font-size:14px;font-weight:600;cursor:pointer;font-family:inherit}
  button:hover{background:#0062c4}
  button.ghost{background:#f0f0f5;color:#1d1d1f}
  button.ghost:hover{background:#e4e4ea}
  .row{display:flex;gap:10px;align-items:center;margin-top:20px;flex-wrap:wrap}
  .ok{color:#2e7d32;font-weight:600}
  .warn{color:#c2410c;font-weight:600}
  .status{font-size:13px;padding:10px 12px;border-radius:10px;background:#f5f6fa;margin-top:10px}
  .status.good{background:#eaf7ee;color:#2e7d32}
  .status.bad{background:#fff4e5;color:#c2410c}
</style></head><body>
<div class="wrap">
  <div class="card">
    <h1>🎬 剪辑助手 <span style="font-size:12px;color:#86868b">v{{VERSION}}</span></h1>
    <div class="sub">首次使用需要填三项，之后开机自动运行，不用再管。</div>

    <label>① 主端地址</label>
    <div class="row" style="margin-top:0">
      <input type="text" id="server" placeholder="http://172.16.28.172:8089" style="flex:1">
      <button class="ghost" onclick="autoDetect()">自动检测</button>
    </div>
    <div class="hint">通常可以点「自动检测」，从 NAS 上读取主端地址。</div>

    <label>② 你的姓名</label>
    <input type="text" id="name" placeholder="与分集表里分配给你的名字一致">
    <div class="hint">用于匹配分集里分配给你负责的集数。</div>

    <label>③ 本地项目目录</label>
    <input type="text" id="root" placeholder="D:\\剪辑项目">
    <div class="hint">本地项目将创建在这个目录下（建议非系统盘）。</div>

    <label>④ 交付密钥（主端生成后发给你）</label>
    <input type="text" id="key" placeholder="从组长那里获取">
    <div class="hint">只保存在这台电脑上，不会上传。</div>

    <div class="row">
      <button onclick="save()">保存并进入</button>
      <span id="msg"></span>
    </div>
  </div>

  <div class="card">
    <h1 style="font-size:15px">环境自检</h1>
    <div id="env" class="status">检测中…</div>
  </div>
</div>
<script>
async function api(p, body){
  const r = await fetch(p, body ? {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)} : {});
  return r.json();
}
async function load(){
  const d = await api('/local/config');
  if(d.ok && d.config){
    document.getElementById('server').value = d.config.server_url || '';
    document.getElementById('name').value   = d.config.member_name || '';
    document.getElementById('root').value   = d.config.local_root || '';
  }
  const s = await api('/local/status');
  const el = document.getElementById('env');
  let h = [];
  h.push(s.server_url ? '<div class="ok">✅ 主端地址已配置</div>' : '<div class="warn">⬜ 主端地址未配置</div>');
  h.push(s.member_name ? '<div class="ok">✅ 姓名：'+s.member_name+'</div>' : '<div class="warn">⬜ 未填姓名</div>');
  h.push(s.local_root_exists ? '<div class="ok">✅ 本地目录可用：'+s.local_root+'</div>' : '<div class="warn">⬜ 本地目录不存在（保存时会自动创建）</div>');
  h.push(s.pr_exe ? '<div class="ok">✅ 已找到 Premiere：'+s.pr_exe+'</div>' : '<div class="warn">⬜ 未找到 Premiere（不影响拉素材）</div>');
  el.innerHTML = h.join('');
  el.className = 'status';
}
async function autoDetect(){
  const d = await api('/local/discover_save', {});
  if(d.ok){ document.getElementById('server').value = d.url; document.getElementById('msg').innerHTML='<span class="ok">✅ 已检测到主端</span>'; }
  else { document.getElementById('msg').innerHTML='<span class="warn">未检测到，请手动填写</span>'; }
}
async function save(){
  const server = document.getElementById('server').value.trim();
  const name = document.getElementById('name').value.trim();
  const root = document.getElementById('root').value.trim();
  const key = document.getElementById('key').value.trim();
  if(!server || !name || !root){ document.getElementById('msg').innerHTML='<span class="warn">请把①②③填完</span>'; return; }
  await api('/local/config', {server_url:server, member_name:name, local_root:root, api_key:key});
  const s = await api('/local/status');
  if(!s.configured){ document.getElementById('msg').innerHTML='<span class="warn">保存后仍未就绪，请检查</span>'; return; }
  location.href = '/';
}
load();
</script>
</body></html>"""


def _port_in_use(port):
    s = socket.socket()
    s.settimeout(0.4)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except Exception:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def main():
    if _port_in_use(LOCAL_PORT):
        print("助手已在运行（端口 %d 被占用），直接打开页面" % LOCAL_PORT)
        try:
            webbrowser.open("http://127.0.0.1:%d/" % LOCAL_PORT)
        except Exception:
            pass
        return

    srv = ThreadingHTTPServer(("127.0.0.1", LOCAL_PORT), Handler)
    url = "http://127.0.0.1:%d/" % LOCAL_PORT
    print("=" * 52)
    print("  剪辑助手 v%s" % VERSION)
    print("  本地入口: %s" % url)
    print("  配置目录: %s" % BASE_DIR)
    print("  按 Ctrl+C 退出")
    print("=" * 52)
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")


if __name__ == "__main__":
    main()
