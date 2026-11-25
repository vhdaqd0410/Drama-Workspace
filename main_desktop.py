# -*- coding: utf-8 -*-
"""🎬 视频工作台 — 桌面端入口（PyWebView + Flask + 系统托盘）

使用方式：
  python main_desktop.py          # 开发调试（有黑窗 + 日志）
  双击 start_desktop.vbs         # 无黑窗启动
  pyinstaller --onefile --noconsole main_desktop.py  # 打包 exe

特性：
  • 系统托盘常驻 — 关闭窗口不退出，托盘右键菜单唤回
  • 任务栏 + 托盘双重入口
  • 通知事件（交付完成/失败）通过 SSE → Toast 推送
"""

import os, sys, time, threading, ctypes, traceback
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))

# 统一版本号来源（backend/version.py）
import version as _version
APP_TITLE = _version.APP_TITLE

# 桌面版标记
os.environ["DRAMA_DESKTOP"] = "1"
os.environ["DRAMA_DESKTOP_CAN_COM"] = "1"
os.environ["DRAMA_DESKTOP_SSE"] = "1"
os.environ["DRAMA_DESKTOP_PRECHECK"] = "1"
os.environ["DRAMA_DESKTOP_NOTIFY"] = "1"
os.environ["DRAMA_DESKTOP_RETRY"] = "1"


# ============ 文件日志（带轮转，防止 desktop.log 无限膨胀）============
_LOG_PATH = os.path.join(BASE_DIR, "desktop.log")
_LOG_MAX_BYTES = 5 * 1024 * 1024   # 单个日志 5MB 触发轮转
_LOG_BACKUPS = 3                    # 保留 3 份历史（desktop.log.1 / .2 / .3）

class _FileLogger:
    """把 print/stdout 输出写入日志文件，超过阈值时轮转旧文件。"""
    def __init__(self, path):
        self.path = path
        self.f = open(path, "a", encoding="utf-8")
        self.bytes = os.path.getsize(path) if os.path.exists(path) else 0
    def _rotate(self):
        """当文件超限时，把当前文件依次滚动为 .1/.2/.3，再开新文件。"""
        try:
            self.f.close()
            for i in range(_LOG_BACKUPS, 0, -1):
                src = f"{self.path}.{i-1}" if i > 1 else self.path
                dst = f"{self.path}.{i}"
                if os.path.exists(src):
                    if os.path.exists(dst):
                        os.remove(dst)
                    os.rename(src, dst)
            self.f = open(self.path, "w", encoding="utf-8")
            self.bytes = 0
        except Exception:
            try:
                self.f = open(self.path, "a", encoding="utf-8")
            except Exception:
                pass
    def write(self, msg):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        self.bytes += len(line.encode("utf-8", errors="replace"))
        try:
            self.f.write(line)
            self.f.flush()
            if self.bytes >= _LOG_MAX_BYTES:
                self._rotate()
        except Exception:
            pass
    def flush(self):
        try: self.f.flush()
        except: pass
    def close(self):
        try: self.f.close()
        except: pass

_is_pythonw = "pythonw" in sys.executable.lower() or sys.executable.lower().endswith("pythonw.exe")

if _is_pythonw:
    _logger = _FileLogger(_LOG_PATH)
    sys.stdout = _logger
    sys.stderr = _logger
    print(f"=== 桌面版启动 (pythonw) ===", flush=True)
else:
    # python 调试模式也把 print 追加到日志（append 模式不覆盖历史，行缓冲保证实时）
    try:
        import io as _io
        _dbg_log = _io.TextIOWrapper(
            open(_LOG_PATH, "ab"), encoding="utf-8",
            line_buffering=True, write_through=True,
        )
        sys.stdout = _dbg_log
        sys.stderr = _dbg_log
    except Exception:
        pass
    print(f"=== 桌面版启动 (python DEBUG) ===", flush=True)


# ============ 单例锁 + 僵尸锁自愈 ============
def _port_alive(port):
    import socket
    try:
        s = socket.socket()
        s.settimeout(0.5)
        s.connect(("127.0.0.1", port))
        s.close()
        return True
    except Exception:
        return False

_MUTEX_NAME = "DramaWorkspace.SingleInstance.Mutex"
_SERVER_PORT = 8089
_mutex = None
try:
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    if _mutex and ctypes.windll.kernel32.GetLastError() == 183:
        if _port_alive(_SERVER_PORT):
            print("⚠️  已有实例在运行，正在激活...")
            try:
                hwnd = ctypes.windll.user32.FindWindowW(None, APP_TITLE)
                if hwnd:
                    ctypes.windll.user32.ShowWindow(hwnd, 9)
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception:
                pass
            sys.exit(0)
        else:
            print("🔄 检测到僵尸锁，正在接管...")
            ctypes.windll.kernel32.CloseHandle(_mutex)
            _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, _MUTEX_NAME)
except Exception as e:
    print(f"⚠️  单例锁失败: {e}")


# ============ 全局引用 ============
_window_ref = [None]
_flask_app = [None]
_tray_ref = [None]

# 分秒帧内嵌窗口（软件内打开审片网页，不跳外部浏览器）
# 用独立 WebView 窗口而非 iframe：分秒帧需要登录，iframe 属于第三方上下文，
# Chrome 的 SameSite cookie 策略会把登录态挡掉；独立窗口是第一方，cookie 正常。
_fm_window_ref = [None]
_FM_ALLOW_HOSTS = ("mediatrack.cn",)


def _fm_url_allowed(url):
    """只允许分秒帧自家域名，避免通过该接口被钓鱼到任意网站。"""
    try:
        from urllib.parse import urlparse
        u = urlparse(url)
        if u.scheme not in ("https", "http"):
            return False
        host = (u.hostname or "").lower()
        return any(host == h or host.endswith("." + h) for h in _FM_ALLOW_HOSTS)
    except Exception:
        return False


def _fm_window_alive(win):
    """判断分秒帧窗口是否还活着。

    重要：用户点 × 关闭窗口后，_fm_window_ref 仍会拿着已销毁的对象。
    以前只看“ref 非空”就当成还在，结果 load_url 在死窗口上空转 ——
    接口返回成功、界面提示已打开，实际什么也没出现。
    """
    if win is None:
        return False
    try:
        # 触碰一下 native 侧，已销毁会报错
        win.get_current_url()
        return True
    except Exception:
        return False


def _on_fm_closed(*_args, **_kwargs):
    """窗口被关闭（用户点 ×）时立即释放引用，并清空上传状态。"""
    if _fm_window_ref[0] is not None:
        print("[fm] 分秒帧窗口已关闭，释放引用")
    _fm_window_ref[0] = None
    try:
        _fmup.reset()
    except Exception:
        pass


# 上传状态统一走 backend/fm_upload.py


def _fm_uploading():
    """当前是否有上传在进行（供关闭保护判断）。"""
    try:
        return _fmup.is_uploading()
    except Exception:
        return False



def _show_fm_window():
    """把分秒帧窗口唤到前台。"""
    w = _fm_window_ref[0]
    if w is None:
        return False
    try:
        if getattr(w, "minimized", False):
            w.restore()
        w.show()
        return True
    except Exception as e:
        print(f"[fm] 唤回窗口失败: {e}")
        return False


# 说明（重要，别再加回“新窗口→同窗跳转”的注入）：
#   曾尝试在分秒帧窗口每次加载后注入脚本，把 window.open / target=_blank 改成同窗跳转，
#   想阻止登录页被丢给系统浏览器。实测结论：
#     - 独立窗口原本就能正常登录（登录走同窗跳转，不靠弹窗），
#       注入反而有风险：若登录依赖 window.open + opener 回调，同窗跳转会把它弄坏。
#     - iframe 里的登录无法靠注入解决：跨域 iframe 的 window.open 会冒泡到顶层 WebView，
#       是否外跳由 pywebview 全局设置决定，而全局关掉会把主窗口 14 处 window.open 一起带走。
#   所以：登录与上传统一走独立窗口，板块里不再做 iframe 登录。


def _set_clipboard(text):
    """把文本写入 Windows 剪贴板。成功返回 True。

    坑（已踩）：64 位下 HGLOBAL 是 8 字节句柄。如果不显式声明 argtypes，
    ctypes 会按 32 位 int 传递 → GlobalLock 抛
    “OverflowError: int too long to convert” → 被 except 吞掉 → 返回 False，
    表现为页面里点“复制链接”总是失败。所以下面逐个声明签名。
    """
    try:
        import ctypes as _ct
        s = str(text or "")
        if not s:
            return False

        k32 = _ct.windll.kernel32
        u32 = _ct.windll.user32

        k32.GlobalAlloc.restype = _ct.c_void_p
        k32.GlobalAlloc.argtypes = [_ct.c_uint, _ct.c_size_t]
        k32.GlobalLock.restype = _ct.c_void_p
        k32.GlobalLock.argtypes = [_ct.c_void_p]
        k32.GlobalUnlock.restype = _ct.c_bool
        k32.GlobalUnlock.argtypes = [_ct.c_void_p]
        k32.GlobalFree.restype = _ct.c_void_p
        k32.GlobalFree.argtypes = [_ct.c_void_p]
        k32.RtlMoveMemory.restype = None
        k32.RtlMoveMemory.argtypes = [_ct.c_void_p, _ct.c_char_p, _ct.c_size_t]
        u32.OpenClipboard.restype = _ct.c_bool
        u32.OpenClipboard.argtypes = [_ct.c_void_p]
        u32.CloseClipboard.restype = _ct.c_bool
        u32.EmptyClipboard.restype = _ct.c_bool
        u32.SetClipboardData.restype = _ct.c_void_p
        u32.SetClipboardData.argtypes = [_ct.c_uint, _ct.c_void_p]

        data = s.encode("utf-16-le") + b"\x00\x00"

        # 剪贴板可能被其他程序短暂占用，重试几次
        opened = False
        for _ in range(5):
            if u32.OpenClipboard(None):
                opened = True
                break
            time.sleep(0.06)
        if not opened:
            print("[fm] 写剪贴板失败: OpenClipboard 一直被占用")
            return False

        try:
            u32.EmptyClipboard()
            h = k32.GlobalAlloc(0x0042, len(data))   # GMEM_MOVEABLE|GMEM_ZEROINIT
            if not h:
                print("[fm] 写剪贴板失败: GlobalAlloc 返回空")
                return False
            p = k32.GlobalLock(h)
            if not p:
                print("[fm] 写剪贴板失败: GlobalLock 返回空")
                k32.GlobalFree(h)
                return False
            k32.RtlMoveMemory(_ct.c_void_p(p), data, len(data))
            k32.GlobalUnlock(h)
            if not u32.SetClipboardData(13, _ct.c_void_p(h)):   # CF_UNICODETEXT
                print("[fm] 写剪贴板失败: SetClipboardData 返回空")
                k32.GlobalFree(h)
                return False
            # 成功后内存归系统所有，不能再 GlobalFree
        finally:
            u32.CloseClipboard()
        return True
    except Exception as e:
        print(f"[fm] 写剪贴板失败: {type(e).__name__} {e}")
        return False


# 分秒帧上传监控状态：上传发生在网页内部（腾讯云 COS 分片上传），
# Python 看不到网络流，只能由页面内注入的脚本 hook XHR.upload.onprogress 后回传。
# 状态与防抖逻辑放在 backend/fm_upload.py（可独立单测）。
try:
    import fm_upload as _fmup
except Exception:
    from backend import fm_upload as _fmup


def _fm_notify_upload_done(summary):
    """上传完成提醒：优先托盘气泡，退到日志。"""
    try:
        tray = _tray_ref[0]
    except Exception:
        tray = None
    if tray is not None:
        try:
            with _tray_lock:
                tray.notify("分秒帧上传完成", summary)
            print(f"[fm] 已推送上传完成提醒: {summary}")
            return True
        except Exception as e:
            print(f"[fm] 托盘提醒失败: {e}")
    print(f"[fm] 上传完成: {summary}")
    return False


# 分秒帧上传状态（逻辑在 backend/fm_upload.py，可单测）
try:
    import fm_upload as _fmup
except Exception:
    from backend import fm_upload as _fmup


def _fm_notify_upload_done(summary):
    """上传完成提醒：优先托盘气泡，退到日志。"""
    try:
        tray = _tray_ref[0]
    except Exception:
        tray = None
    if tray is not None:
        try:
            with _tray_lock:
                tray.notify("分秒帧上传完成", summary)
            print(f"[fm] 已推送上传完成提醒: {summary}")
            return True
        except Exception as e:
            print(f"[fm] 托盘提醒失败: {e}")
    print(f"[fm] 上传完成: {summary}")
    return False


class _FmBridge:
    """分秒帧窗口的 JS 桥（只提供给该窗口，不影响主窗口）。"""

    def copy_clipboard(self, text):
        """页面里点「复制链接」时调用：由 Python 写剪贴板，绕开浏览器权限限制。"""
        ok = _set_clipboard(text)
        return {"ok": bool(ok)}

    def upload_report(self, payload):
        """页面内上传进度回传（已节流）。用于进度展示、完成提醒、关闭保护。"""
        import json as _json
        try:
            d = _json.loads(payload) if isinstance(payload, str) else (payload or {})
        except Exception:
            return {"ok": False}
        return _fmup.report(d.get("active"), d.get("loaded"), d.get("total"))


def _fm_toolbar_js():
    """生成分秒帧页面内的浮动工具条（右下角，两个小按钮）。

    为什么需要：独立窗口里没有地址栏，用户想复制当前页链接、或跳到另一个分秒帧页
    只能切回工作台。这里在页面内加两个不抢眼的按钮解决。
    风险控制：只用内联样式 + 最高 z-index + 纯图标胶囊，不敢碰页面布局；
    每次页面加载（events.loaded）重新注入，避免整页刷新后工具条消失。
    """
    return r"""
(function(){
  try{
    if (document.getElementById('__fm_bar')) { return; }
    var css = 'position:fixed;right:14px;bottom:14px;z-index:2147483647;'
      + 'display:flex;flex-direction:column;gap:8px;align-items:flex-end;'
      + 'font:12px/1.4 -apple-system,"Segoe UI",sans-serif;'
      + 'opacity:.55;transition:opacity .18s';
    var btnCss = 'display:flex;align-items:center;gap:5px;padding:7px 11px;'
      + 'border-radius:18px;border:1px solid rgba(255,255,255,.18);'
      + 'background:rgba(28,28,32,.88);color:#fff;cursor:pointer;'
      + 'box-shadow:0 2px 10px rgba(0,0,0,.22);white-space:nowrap;'
      + 'font:12px/1.4 -apple-system,"Segoe UI",sans-serif';
    var wrap = document.createElement('div');
    wrap.id = '__fm_bar';
    wrap.style.cssText = css;
    wrap.onmouseenter = function(){ wrap.style.opacity = '1'; };
    wrap.onmouseleave = function(){ wrap.style.opacity = '.55'; };

    function mk(text, title, fn){
      var b = document.createElement('button');
      b.textContent = text;
      b.title = title;
      b.style.cssText = btnCss;
      b.onclick = fn;
      return b;
    }

    // 复制当前页链接：优先走 Python 桥（最稳），再退到浏览器 API
    wrap.appendChild(mk('🔗 复制链接', '复制当前页面链接（存回工作台用）', function(){
      var u = location.href;

      function __fmFallbackCopy(){
        try{
          if (navigator.clipboard && navigator.clipboard.writeText){
            navigator.clipboard.writeText(u).then(function(){ __fmToast('已复制：' + u); },
              function(){ __fmManualCopy(u); });
          } else { __fmManualCopy(u); }
        }catch(e){ __fmManualCopy(u); }
      }
      function __fmManualCopy(txt){
        var ta = document.createElement('textarea');
        ta.value = txt; ta.style.cssText = 'position:fixed;left:-9999px;top:0';
        document.body.appendChild(ta); ta.select();
        var ok = false;
        try{ ok = document.execCommand('copy'); }catch(e){}
        document.body.removeChild(ta);
        __fmToast(ok ? '已复制：' + txt : '复制失败，请手动选中地址');
      }

      // 桥调用要加超时：pywebview 的 Promise 偶尔不 resolve，不能一直卡着不兜底
      var called = false;
      var timer = setTimeout(function(){
        if (called) return;
        called = true;
        __fmFallbackCopy();
      }, 1500);

      try{
        if (window.pywebview && window.pywebview.api && window.pywebview.api.copy_clipboard){
          window.pywebview.api.copy_clipboard(u).then(function(r){
            if (called) return;
            called = true;
            clearTimeout(timer);
            if (r && r.ok) { __fmToast('已复制：' + u); }
            else {
              // 桥明确报失败 → 换浏览器 API 试一次，别再静默
              __fmFallbackCopy();
            }
          }).catch(function(){
            if (called) return;
            called = true;
            clearTimeout(timer);
            __fmFallbackCopy();
          });
          return;
        }
      }catch(e){}
      if (!called) { called = true; clearTimeout(timer); }
      __fmFallbackCopy();
    }));

    // 打开另一个分秒帧链接（在当前窗口内跳转）
    wrap.appendChild(mk('🧭 打开链接', '粘贴一个分秒帧链接并跳转', function(){
      var cur = location.href || 'https://app.mediatrack.cn/';
      var u = window.prompt('输入要打开的分秒帧链接（当前窗口内跳转）：', cur);
      if (!u) return;
      u = String(u).trim();
      if (!u) return;
      // 只接受分秒帧域名，避免被当成任意网址跳板
      var ok = /^https?:\/\/([\w.-]+\.)?mediatrack\.cn(\/|$)/i.test(u);
      if (!ok) { __fmToast('只支持 mediatrack.cn 的链接'); return; }
      location.href = u;
    }));

    // 轻量提示（不依赖页面自己的 toast）
    var tip = document.createElement('div');
    tip.id = '__fm_tip';
    tip.style.cssText = 'display:none;position:fixed;right:14px;bottom:96px;'
      + 'z-index:2147483647;max-width:78vw;padding:9px 13px;border-radius:10px;'
      + 'background:rgba(28,28,32,.93);color:#fff;font:12.5px/1.5 -apple-system,"Segoe UI",sans-serif;'
      + 'box-shadow:0 4px 16px rgba(0,0,0,.28);word-break:break-all';
    document.body.appendChild(wrap);
    document.body.appendChild(tip);

    window.__fmToast = function(msg){
      try{
        tip.textContent = msg;
        tip.style.display = 'block';
        clearTimeout(window.__fmTipTimer);
        window.__fmTipTimer = setTimeout(function(){ tip.style.display = 'none'; }, 3200);
      }catch(e){}
    };
  }catch(e){}
})();
"""


def _fm_upload_hook_js():
    """注入上传监控：hook XHR.upload.onprogress，把进度回传给 Python 并显示在工具条上。

    为什么这么干：上传是分秒帧网页里的腾讯云 COS 分片上传，发生在 WebView2 内部，
    宿主拿不到网络流。只能从页面 JS 侧 hook XMLHttpRequest。
    过滤：只看 total > 1MB 的上传，避开保存评论/小 API 请求的干扰。
    """
    return r"""
(function(){
  try{
    if (window.__fmUploadHook) { return; }
    window.__fmUploadHook = true;

    var active = {};       // id -> {loaded,total}
    var grandLoaded = 0;   // 累计已传（用于完成后报总量）
    var lastSent = 0;

    function summary(){
      var n = 0, loaded = 0, total = 0;
      for (var k in active){
        var a = active[k]; n++; loaded += a.loaded || 0; total += a.total || 0;
      }
      return { active: n, loaded: loaded, total: total };
    }

    function paint(){
      var s = summary();
      var el = document.getElementById('__fm_up');
      if (!el) return;
      if (s.active > 0){
        var pct = s.total > 0 ? Math.floor(s.loaded * 100 / s.total) : 0;
        el.style.display = 'block';
        el.textContent = '⬆ 上传中 ' + (s.total > 0 ? pct + '%' : (s.loaded/1048576).toFixed(1)+'MB')
          + '（' + s.active + ' 个任务）';
      } else {
        el.style.display = 'none';
      }
    }

    function report(force){
      var now = Date.now();
      if (!force && now - lastSent < 400) return;   // 节流 400ms
      lastSent = now;
      var s = summary();
      if (s.active > 0) grandLoaded = s.loaded;
      if (window.pywebview && window.pywebview.api && window.pywebview.api.upload_report){
        try{
          window.pywebview.api.upload_report(JSON.stringify(s)).then(function(){}).catch(function(){});
        }catch(e){}
      }
      paint();
    }

    var XO = XMLHttpRequest.prototype.open;
    var XS = XMLHttpRequest.prototype.send;

    XMLHttpRequest.prototype.open = function(method, url){
      this.__fmUrl = String(url || '');
      this.__fmId = 'u' + Math.random().toString(36).slice(2);
      return XO.apply(this, arguments);
    };

    XMLHttpRequest.prototype.send = function(){
      var xhr = this;
      var id = xhr.__fmId;
      try{
        if (xhr.upload){
          xhr.upload.addEventListener('progress', function(e){
            // 只统计真实文件上传（>1MB），避开普通小接口
            if (e && e.total && e.total > 1048576){
              active[id] = { loaded: e.loaded || 0, total: e.total || 0 };
              report(false);
            }
          });
          xhr.upload.addEventListener('load', function(){
            if (active[id]) { report(true); }
          });
        }
        xhr.addEventListener('loadend', function(){
          if (active[id]){ delete active[id]; report(true); }
        });
      }catch(e){}
      return XS.apply(this, arguments);
    };
  }catch(e){}
})();
"""


def _fm_progress_ui_js():
    """工具条里的上传进度行（由 paint() 更新）。独立于 hook 注入，
    这样即使 hook 已存在、重新加载后也能补上 UI 节点。"""
    return r"""
(function(){
  try{
    var bar = document.getElementById('__fm_bar');
    if (!bar || document.getElementById('__fm_up')) { return; }
    var up = document.createElement('div');
    up.id = '__fm_up';
    up.style.cssText = 'display:none;padding:6px 11px;border-radius:14px;'
      + 'background:rgba(0,113,227,.92);color:#fff;font:12px/1.4 -apple-system,"Segoe UI",sans-serif;'
      + 'box-shadow:0 2px 10px rgba(0,0,0,.22);white-space:nowrap;text-align:right';
    bar.insertBefore(up, bar.firstChild);
    if (window.__fmUploadHook) {
      // 重新触发一次汇总（状态保留在 hook 内部）
      try{ document.dispatchEvent(new Event('__fm_repaint')); }catch(e){}
    }
  }catch(e){}
})();
"""


def _inject_fm_toolbar(win):
    """给分秒帧窗口注入浮动工具条 + 上传监控（每次页面加载都重新注入）。"""
    def _on_loaded(*_a, **_k):
        try:
            win.evaluate_js(_fm_toolbar_js())
        except Exception as _e:
            print(f"[fm] 注入工具条失败: {_e}")
        try:
            win.evaluate_js(_fm_progress_ui_js())
        except Exception:
            pass
        try:
            win.evaluate_js(_fm_upload_hook_js())
        except Exception as _e:
            print(f"[fm] 注入上传监控失败: {_e}")

    try:
        win.events.loaded += _on_loaded
        return True
    except Exception as _e:
        print(f"[fm] 绑定 loaded 失败: {_e}")
        return False


def _open_fm_window(url, title="分秒帧"):
    """在软件内打开/切换分秒帧窗口。

    关键：pywebview 的 create_window 只在“非主线程且 GUI 已启动”时才立即创建窗口，
    Flask 请求线程正好满足，所以这个函数必须从路由（或后台线程）调用。
    """
    if not _fm_url_allowed(url):
        print(f"[fm] 拒绝非分秒帧地址: {url}")
        return False, "只允许打开分秒帧网址"

    w = _fm_window_ref[0]
    # 关键：先校验窗口真活着，否则用户关窗后再点会“提示已打开但没窗口”
    if not _fm_window_alive(w):
        if w is not None:
            print("[fm] 记录的窗口已失效，准备重建")
        _fm_window_ref[0] = None
        w = None

    if w is not None:
        try:
            w.load_url(url)
            try:
                w.set_title(title)
            except Exception:
                pass
            _show_fm_window()
            print(f"[fm] 复用已有窗口 → {url}")
            return True, ""
        except Exception as e:
            print(f"[fm] 复用窗口失败，将重建: {e}")
            _fm_window_ref[0] = None

    try:
        import webview as _wv
        new_win = _wv.create_window(
            title=title, url=url,
            width=1280, height=860, min_size=(900, 600),
            resizable=True, text_select=True,
            js_api=_FmBridge(),   # 页面里的「复制链接」按钮走这个桥
        )
        if new_win is None:
            return False, "窗口创建被取消"
        # 绑定关闭事件：用户点 × 后自动释放，避免后续误判为“窗口仍在”
        try:
            new_win.events.closed += _on_fm_closed
        except Exception as _be:
            print(f"[fm] 绑定关闭事件失败: {_be}")

        # 上传中关闭保护：避免误点 × 把上传中断了
        def _on_fm_closing(*_a, **_k):
            try:
                if not _fm_uploading():
                    return True
            except Exception:
                return True
            try:
                res = new_win.create_confirmation_dialog(
                    "还有文件正在上传",
                    "关闭窗口会中断上传，已传的部分可能不完整。\n\n确定要关闭吗？")
                if res:
                    print("[fm] 用户确认在传输中关闭窗口")
                    return True
                print("[fm] 已取消关闭（上传进行中）")
                return False
            except Exception as _ce:
                # 弹框失败时宁可不关，避免真的把传输掐断
                print(f"[fm] 关闭确认弹框失败，已阻止关闭: {_ce}")
                return False

        try:
            new_win.events.closing += _on_fm_closing
        except Exception as _ce2:
            print(f"[fm] 绑定关闭保护失败: {_ce2}")

        # 页面内浮动工具条（复制当前链接 / 打开链接）
        _inject_fm_toolbar(new_win)
        _fm_window_ref[0] = new_win
        print(f"[fm] 已新建分秒帧窗口 → {url}")
        return True, ""
    except Exception as e:
        print(f"[fm] 创建窗口失败: {e}")
        return False, str(e)
_window_visible = [True]
# 托盘操作串行化锁：pystray 的 update_menu/notify/stop 内部会操作 Win32 菜单/托盘句柄
# （DestroyMenu/CreateMenu/Shell_NotifyIcon），且 pystray 无内部锁。若从热键线程、
# WebView 回调、通知线程等多个线程同时调用，会导致句柄竞争、菜单反复销毁重建，
# 长时间运行后托盘消息循环损坏 → 点击托盘图标无响应（卡死，重启恢复）。
# 用此锁把所有 pystray 方法调用串行化，避免跨线程数据竞争。
# 用 RLock（可重入）防止托盘回调自身重入时死锁。
_tray_lock = threading.RLock()
# 菜单刷新节流状态：update_menu() 每次都会 DestroyMenu+CreateMenu 重建 Win32 菜单句柄，
# 频繁调用（开/关窗口、按热键连续触发）是托盘卡死根源之一。用一次性定时器把短时间内的
# 多次请求合并为一次 update_menu，显著降低菜单重建频率。
_tray_update_timer = None
_tray_update_pending = False


# ============================================================
# 图标生成（Pillow 动态绘制，无外部资源依赖）
# ============================================================
def _build_tray_image(size=64):
    """渐变深蓝紫底 + 白色胶片符号。失败返回 None。"""
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # 圆角矩形背景（紫 → 深蓝 渐变）
        r = max(4, size // 10)
        _bg_top = (120, 70, 200, 255)
        _bg_bot = (30, 100, 220, 255)
        for y in range(size):
            t = y / max(1, size - 1)
            cr = int(_bg_top[0] * (1 - t) + _bg_bot[0] * t)
            cg = int(_bg_top[1] * (1 - t) + _bg_bot[1] * t)
            cb = int(_bg_top[2] * (1 - t) + _bg_bot[2] * t)
            draw.line([(0, y), (size, y)], fill=(cr, cg, cb, 255))

        # 圆角遮罩（PNG 透明圆角）
        mask = Image.new("L", (size, size), 0)
        md = ImageDraw.Draw(mask)
        md.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=255)
        img.putalpha(mask)

        # 白色胶片主体
        fg = (255, 255, 255, 248)
        pad = int(size * 0.22)
        body_l = pad
        body_t = int(size * 0.30)
        body_r = size - pad
        body_b = int(size * 0.72)
        draw.rectangle([body_l, body_t, body_r, body_b], fill=fg)

        # 齿孔（用同一背景色在白色胶片上"挖"出孔位）
        hole_w = max(2, int(size * 0.08))
        hole_h = max(2, int(size * 0.06))
        hole_gap = max(1, int(size * 0.04))
        total_w = body_r - body_l
        n = max(2, (total_w + hole_gap) // (hole_w + hole_gap))
        total_holes_w = n * hole_w + (n - 1) * hole_gap
        start_x = body_l + (total_w - total_holes_w) // 2
        for i in range(n):
            hx = start_x + i * (hole_w + hole_gap)
            # 上排
            ht_y = body_t - hole_h - 1
            draw.rectangle(
                [hx, ht_y, hx + hole_w, body_t - 1],
                fill=_bg_top,
            )
            # 下排
            draw.rectangle(
                [hx, body_b + 1, hx + hole_w, body_b + hole_h + 1],
                fill=_bg_bot,
            )

        return img
    except Exception as e:
        print(f"[tray] 绘制图标失败: {e}")
        return None


def _build_tray_fallback_image(size=64):
    """极简 fallback：纯色方块"""
    try:
        from PIL import Image
        return Image.new("RGBA", (size, size), (50, 80, 200, 255))
    except Exception:
        return None


# ============================================================
# 托盘菜单回调
# ============================================================
def _show_window():
    """显示主窗口并置前台。

    用 pywebview 原生 restore()+show() 即可可靠显示（其内部已做 Show+Activate
    线程调度）。不叠加过多 Win32 置顶操作——SetWindowPos(TOPMOST)/模拟按键
    可能干扰窗口状态，反而导致"任务栏有图标但桌面不显示"。仅用 ShowWindow
    SW_RESTORE 确保非最小化。
    """
    w = _window_ref[0]
    if w is None:
        return
    changed = not _window_visible[0]
    try:
        w.restore()
        w.show()
        # 轻量辅助：确保窗口不是最小化状态（避免任务栏有图标但桌面不显示）
        try:
            hwnd = ctypes.windll.user32.FindWindowW(None, APP_TITLE)
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        except Exception:
            pass
        _window_visible[0] = True
        print("[tray] 窗口已显示")
    except Exception as e:
        print(f"[tray] show_window 异常: {e}")
    # 可见性真正变化时才刷新菜单文案（节流合并，避免频繁重建菜单句柄）
    if changed:
        _update_tray_label()


def _hide_window():
    """隐藏主窗口到托盘"""
    w = _window_ref[0]
    if w is None:
        return
    changed = _window_visible[0]
    try:
        w.hide()
        _window_visible[0] = False
        print("[tray] 窗口已隐藏（仍在托盘运行）")
    except Exception as e:
        print(f"[tray] hide_window 异常: {e}")
    if changed:
        _update_tray_label()


# 托盘操作防抖：双击托盘图标会触发 default 菜单项两次（显示又隐藏），
# 导致用户以为"打不开"。1 秒内合并多次触发，且单击图标总是"显示窗口"。
_toggle_debounce_ts = [0.0]

def _toggle_window(icon=None, item=None):
    now = time.time()
    # 防抖：1 秒内的重复触发（双击）只执行一次
    if now - _toggle_debounce_ts[0] < 1.0:
        return
    _toggle_debounce_ts[0] = now
    # 单击托盘图标总是"显示窗口"（避免双击/误触把已显示的窗口又藏起来）
    _show_window()
    # 注意：这里是托盘菜单回调（托盘线程内），不要在回调里立刻重建菜单，
    # 否则可能销毁正在显示的菜单。文案刷新交给节流版 _update_tray_label
    #（由 _show_window/_hide_window 的调用方在其他线程触发，1 秒延迟合并）。


def _open_data_dir(icon=None, item=None):
    path = os.path.join(BASE_DIR, "backend")
    if os.path.isdir(path):
        try:
            os.startfile(path)
        except Exception:
            pass


def _open_log(icon=None, item=None):
    if os.path.isfile(_LOG_PATH):
        try:
            os.startfile(_LOG_PATH)
        except Exception:
            pass
    else:
        try:
            os.startfile(BASE_DIR)
        except Exception:
            pass


def _open_config(icon=None, item=None):
    cfg = os.path.join(BASE_DIR, "backend", "config.yaml")
    if os.path.isfile(cfg):
        try:
            os.startfile(cfg)
        except Exception:
            pass


def _do_quit_tray(icon=None, item=None):
    print("[tray] 用户请求退出...")
    # 先停止托盘（避免回调卡死）；用 _tray_lock 串行化 stop
    try:
        if _tray_ref[0] is not None:
            with _tray_lock:
                _tray_ref[0].stop()
    except Exception:
        pass
    _tray_ref[0] = None
    # 再关窗口
    threading.Thread(target=_do_quit, daemon=True).start()


def _do_quit():
    time.sleep(0.2)
    try:
        w = _window_ref[0]
        if w is not None:
            print("  → window.destroy()")
            w.destroy()
    except Exception as e:
        print(f"  → window.destroy 异常: {e}")
    time.sleep(2)
    if _mutex:
        try:
            ctypes.windll.kernel32.CloseHandle(_mutex)
        except Exception:
            pass
    print("  → 退出进程")
    os._exit(0)


def _do_restart_tray(icon=None, item=None):
    """托盘菜单「重启软件」：先停止托盘与窗口，再重新拉起 main_desktop.py。"""
    print("[tray] 用户请求重启软件...")
    try:
        if _tray_ref[0] is not None:
            with _tray_lock:
                _tray_ref[0].stop()
    except Exception:
        pass
    _tray_ref[0] = None
    threading.Thread(target=_do_restart, daemon=True).start()


def _do_restart():
    """后台执行：优雅关闭窗口后，用 pythonw 重新拉起 main_desktop.py。"""
    try:
        w = _window_ref[0]
        if w is not None:
            print("  → window.destroy()")
            w.destroy()
    except Exception as e:
        print(f"  → window.destroy 异常: {e}")
    # 等待端口释放（让旧进程完全退出）
    time.sleep(2)

    _spawn = sys.executable
    # 优先用 pythonw（无黑窗）
    _pw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if os.path.exists(_pw):
        _spawn = _pw
    _script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main_desktop.py")
    try:
        import subprocess as _sub
        _sub.Popen([_spawn, _script],
                   cwd=os.path.dirname(_script),
                   creationflags=getattr(_sub, "CREATE_NO_WINDOW", 0))
        print("  → 已重新拉起 main_desktop.py")
    except Exception as e:
        print(f"  → 重新启动失败: {e}")

    if _mutex:
        try:
            ctypes.windll.kernel32.CloseHandle(_mutex)
        except Exception:
            pass
    os._exit(0)


# ============================================================
# 托盘菜单
# 说明：pystray 的 MenuItem 支持 callable 属性（text/visible/enabled），
# 会在菜单显示时动态求值。因此「隐藏/显示」文案用 callable 动态生成，
# 菜单只需构建一次，无需在每次点击时重建，避免反复 update_menu 导致
# 托盘线程与 Win32 句柄竞争而卡死/无响应。
# ============================================================
def _build_menu(visible=True):
    import pystray
    # text 用 callable 动态求值（保留，虽单击已固定为显示，但菜单仍可提示状态）
    toggle_item = pystray.MenuItem(
        lambda item: "🔍 显示主窗口（单击托盘图标亦可）",
        _toggle_window,
        default=True,
    )
    return pystray.Menu(
        pystray.MenuItem(
            APP_TITLE,
            None, enabled=False,
        ),
        pystray.Menu.SEPARATOR,
        # —— 快速操作 ——
        toggle_item,
        pystray.MenuItem("🔄 立即刷新项目", lambda i, it: _trigger_api("scan")),
        pystray.MenuItem("📦 同步交付日期", _tray_sync_delivery),
        pystray.Menu.SEPARATOR,
        # —— 功能跳转 ——
        pystray.MenuItem("📊 数据洞察", _tray_go_insights),
        pystray.MenuItem("📅 交付日历", _tray_go_delivery),
        pystray.MenuItem("📌 全局待办", _tray_go_todos),
        pystray.MenuItem("🔔 通知中心", _tray_go_notifications),
        pystray.Menu.SEPARATOR,
        # —— 打开资源 ——
        pystray.MenuItem("📂 打开数据目录", _open_data_dir),
        pystray.MenuItem("📋 查看日志", _open_log),
        pystray.MenuItem("⚙️ 打开配置文件", _open_config),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("🔄 重启软件", _do_restart_tray),
        pystray.MenuItem("🚪 退出", _do_quit_tray),
    )


# ============================================================
# 托盘菜单刷新
# 说明：菜单文案采用 pystray 的 callable 动态 text，绑定 _window_visible，
# 菜单在显示时自动求值最新文案，因此无需在每次点击时重建整个菜单。
# 这里仅触发一次 update_menu() 让托盘线程重绘（幂等、不阻塞），彻底
# 避免旧实现“tray.menu= 自动 update_menu() + 又显式 update_menu()”
# 导致的菜单重复重建与 Win32 句柄竞争、卡死/无响应。
# ============================================================
def _update_tray_label():
    """请求托盘刷新菜单文案（节流合并版）。

    update_menu() 内部会 DestroyMenu + CreateMenu 重建整个 Win32 菜单句柄，
    从非托盘线程调用（热键线程/WebView回调）会与托盘消息循环竞争，频繁调用
    是托盘卡死（点击无响应）的根本原因之一。

    这里用一次性定时器做节流：1 秒内的多次请求合并为一次 update_menu，
    大幅降低菜单重建频率。文案（动态 text）短暂滞后不影响功能，仅影响
    「隐藏/显示」的文字显示。
    """
    global _tray_update_timer, _tray_update_pending
    if _tray_update_pending:
        return  # 已有待执行的刷新，合并本次请求
    _tray_update_pending = True

    def _do_update():
        global _tray_update_pending
        _tray_update_pending = False
        tray = _tray_ref[0]
        if tray is None:
            return
        try:
            with _tray_lock:
                if hasattr(tray, "update_menu"):
                    tray.update_menu()
        except Exception as e:
            print(f"[tray] 更新菜单文案失败: {e}")

    try:
        _tray_update_timer = threading.Timer(1.0, _do_update)
        _tray_update_timer.daemon = True
        _tray_update_timer.start()
    except Exception as e:
        print(f"[tray] 菜单刷新调度失败: {e}")
        _tray_update_pending = False


def _trigger_api(action):
    """通过 HTTP 请求调 Flask API"""
    try:
        import urllib.request
        key = _api_secret()
        headers = {"X-API-KEY": key} if key else {}
        if action == "scan":
            req = urllib.request.Request(
                f"http://127.0.0.1:{_SERVER_PORT}/api/scan",
                method="POST", headers=headers)
            urllib.request.urlopen(req, timeout=3)
        elif action == "sync_delivery":
            req = urllib.request.Request(
                f"http://127.0.0.1:{_SERVER_PORT}/api/insights/sync_delivery_dates",
                method="POST", headers=headers)
            urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"[tray] trigger_api {action} 失败: {e}")


def _trigger_js(js_code):
    """显示窗口（若隐藏）并在前端执行 JS，用于托盘菜单跳转功能。"""
    if not _window_visible[0]:
        _show_window()  # 内部按可见性变化触发节流菜单刷新
    try:
        w = _window_ref[0]
        if w is not None and hasattr(w, "evaluate_js"):
            w.evaluate_js(js_code)
    except Exception as e:
        print(f"[tray] evaluate_js 失败: {e}")


def _tray_go_insights(icon=None, item=None):
    _trigger_js("try{openInsightsDialog()}catch(e){}")


def _tray_go_todos(icon=None, item=None):
    _trigger_js("try{openTaskBoard()}catch(e){}")


def _tray_go_notifications(icon=None, item=None):
    _trigger_js("try{openNotifications()}catch(e){}")


def _tray_go_delivery(icon=None, item=None):
    # 交付日历在数据洞察里，直接打开并切到日历
    _trigger_js("try{openInsightsDialog()}catch(e){}")


def _tray_sync_delivery(icon=None, item=None):
    _trigger_api("sync_delivery")
    try:
        w = _window_ref[0]
        if w is not None and hasattr(w, "evaluate_js"):
            w.evaluate_js("try{loadInsightsCalendar()}catch(e){}")
    except Exception as e:
        print(f"[tray] 刷新日历失败: {e}")


# ============================================================
# 启动设置（开机自启关联）：读取 min_to_tray / auto_scan 并应用
# ============================================================
def _api_secret():
    """从 backend/config.yaml 读取 api_secret（用于本机 HTTP 鉴权）。"""
    try:
        import yaml as _y
        cfg_path = os.path.join(BASE_DIR, "backend", "config.yaml")
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = _y.safe_load(f) or {}
        return (cfg.get("web", {}) or {}).get("api_secret", "") or ""
    except Exception:
        return ""


def _read_startup_settings():
    """读取 /api/settings 中的启动行为，返回 (min_to_tray, auto_scan)。"""
    key = _api_secret()
    try:
        import urllib.request, json as _j
        req = urllib.request.Request(
            f"http://127.0.0.1:{_SERVER_PORT}/api/settings",
            headers={"X-API-KEY": key} if key else {})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = _j.loads(resp.read().decode("utf-8", "ignore"))
        s = (data.get("settings") or {}) if data.get("ok") else {}
        min_tray = str(s.get("min_to_tray", "") or "") in ("1", "true", "True")
        auto_scan = str(s.get("auto_scan", "") or "") in ("1", "true", "True")
        return min_tray, auto_scan
    except Exception as e:
        print(f"[startup] 读取启动设置失败: {e}")
        return False, False


def _apply_startup_settings():
    """根据设置执行启动行为：延迟后触发扫描 / 隐藏窗口。

    关键区分：min_to_tray 只对【开机自启】生效。
    原因：该设置本意是开机时不弹窗打扰，但以前无论怎么启动都会隐藏窗口，
    导致用户手动双击或托盘「重启软件」后窗口自动消失，还得再从托盘叫回来。
    现在靠 --autostart 参数（由 start_desktop.vbs 传入）区分：
      - 开机自启（--autostart）→ 按设置最小化到托盘
      - 手动启动 / 托盘重启 → 直接正常显示窗口
    """
    min_tray, auto_scan = _read_startup_settings()
    _is_autostart = "--autostart" in sys.argv
    print(f"[startup] 启动行为 → 最小化到托盘: {min_tray} "
          f"(本次是开机自启: {_is_autostart}), 自动扫描: {auto_scan}")
    # 自动扫描：等服务与界面就绪后延迟触发，避免阻塞首屏
    if auto_scan:
        def _scan():
            time.sleep(6)
            print("[startup] 按设置自动扫描 NAS...")
            _trigger_api("scan")
        threading.Thread(target=_scan, daemon=True).start()
    # 最小化到托盘：仅开机自启时执行（延迟到窗口创建完成后）
    if min_tray and _is_autostart:
        def _min():
            time.sleep(2)
            _hide_window()  # 内部按可见性变化触发节流菜单刷新
            print("[startup] 已按设置最小化到托盘（开机自启）")
        threading.Thread(target=_min, daemon=True).start()
    elif min_tray:
        print("[startup] 本次为手动启动/重启，保持窗口显示（不隐藏到托盘）")


# ============================================================
# 全局热键：即使窗口隐藏到托盘，按快捷键也能唤回窗口
# 支持在设置界面自定义（wakeup_shortcut），未配置则用默认候选
# ============================================================
_MOD_ALT = 0x0001
_MOD_CTRL = 0x0002
_MOD_SHIFT = 0x0004

# 键名 → 虚拟键码（覆盖常用键）
_VK_MAP = {
    'a': 0x41, 'b': 0x42, 'c': 0x43, 'd': 0x44, 'e': 0x45, 'f': 0x46,
    'g': 0x47, 'h': 0x48, 'i': 0x49, 'j': 0x4A, 'k': 0x4B, 'l': 0x4C,
    'm': 0x4D, 'n': 0x4E, 'o': 0x4F, 'p': 0x50, 'q': 0x51, 'r': 0x52,
    's': 0x53, 't': 0x54, 'u': 0x55, 'v': 0x56, 'w': 0x57, 'x': 0x58,
    'y': 0x59, 'z': 0x5A,
    '0': 0x30, '1': 0x31, '2': 0x32, '3': 0x33, '4': 0x34,
    '5': 0x35, '6': 0x36, '7': 0x37, '8': 0x38, '9': 0x39,
    'space': 0x20, 'enter': 0x0D, 'esc': 0x1B, 'tab': 0x09,
    'f1': 0x70, 'f2': 0x71, 'f3': 0x72, 'f4': 0x73, 'f5': 0x74,
    'f6': 0x75, 'f7': 0x76, 'f8': 0x77, 'f9': 0x78, 'f10': 0x79,
    'f11': 0x7A, 'f12': 0x7B,
}

# 默认候选热键组合（Ctrl+Alt 常被系统/输入法占用，按优先级尝试）
_HOTKEY_CANDIDATES = [
    ("Ctrl+Shift+B", _MOD_CTRL | _MOD_SHIFT, 0x42),
    ("Ctrl+Shift+G", _MOD_CTRL | _MOD_SHIFT, 0x47),
    ("Alt+Shift+B", _MOD_ALT | _MOD_SHIFT, 0x42),
    ("Alt+G", _MOD_ALT, 0x47),
    ("Ctrl+Alt+W", _MOD_ALT | _MOD_CTRL, 0x57),
]


def _parse_hotkey_str(s):
    """把 'ctrl+shift+b' 解析为 (label, mod, vk)。失败返回 None。"""
    s = (s or "").strip().lower()
    if not s:
        return None
    parts = [p.strip() for p in s.split('+') if p.strip()]
    if not parts:
        return None
    mod = 0
    modifiers = []
    key_part = None
    for p in parts:
        if p in ('ctrl', 'control'):
            mod |= _MOD_CTRL
            modifiers.append('Ctrl')
        elif p == 'alt':
            mod |= _MOD_ALT
            modifiers.append('Alt')
        elif p == 'shift':
            mod |= _MOD_SHIFT
            modifiers.append('Shift')
        else:
            key_part = p
    if key_part is None or key_part not in _VK_MAP:
        return None
    vk = _VK_MAP[key_part]
    label = '+'.join(modifiers + [key_part.upper()])
    return (label, mod, vk)


def _read_shortcut(setting_key):
    """从数据库读取用户配置的快捷键。"""
    try:
        import sqlite3 as _sq
        _db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "data", "workbench.db")
        conn = _sq.connect(_db_path, timeout=3)
        try:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key=?", (setting_key,)
            ).fetchone()
            return row[0] if row else ''
        finally:
            conn.close()
    except Exception:
        return ''


def _register_one_hotkey(user32, hotkey_id, cfg_key, candidates, what):
    """注册一个全局热键。返回 (label, mod, vk) 或 None。"""
    user_cfg = _read_shortcut(cfg_key)
    parsed = _parse_hotkey_str(user_cfg)
    lst = [parsed] if parsed else candidates
    for label, mod, vk in lst:
        if user32.RegisterHotKey(None, hotkey_id, mod, vk):
            return (label, mod, vk)
    return None


def _run_global_hotkey():
    """后台线程：注册两个系统级全局热键（唤醒窗口 + 全局搜索）。"""
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32

        # 热键 ID
        HOTKEY_ID_WAKE = 0x5E11
        HOTKEY_ID_SEARCH = 0x5E12

        # 全局唤醒热键（配置 wakeup_shortcut，否则默认候选）
        wake = _register_one_hotkey(user32, HOTKEY_ID_WAKE, 'wakeup_shortcut',
                                    _HOTKEY_CANDIDATES, '唤醒窗口')
        if wake:
            print(f"[hotkey] 全局唤醒热键已注册: {wake[0]}")
        else:
            print("[hotkey] 全局唤醒热键注册失败（可能被占用）")

        # 全局搜索热键（配置 global_search_shortcut，否则默认 Ctrl+Alt+S）
        search_candidates = [
            ("Ctrl+Alt+S", _MOD_ALT | _MOD_CTRL, 0x53),   # S
            ("Ctrl+Shift+S", _MOD_CTRL | _MOD_SHIFT, 0x53),
            ("Ctrl+Alt+P", _MOD_ALT | _MOD_CTRL, 0x50),   # P
            ("Ctrl+Shift+P", _MOD_CTRL | _MOD_SHIFT, 0x50),
            ("Alt+F", _MOD_ALT, 0x46),                     # F
        ]
        search = _register_one_hotkey(user32, HOTKEY_ID_SEARCH, 'global_search_shortcut',
                                      search_candidates, '全局搜索')
        if search:
            print(f"[hotkey] 全局搜索热键已注册: {search[0]}")
        else:
            print("[hotkey] 全局搜索热键注册失败（可能被占用）")

        # 最小消息循环，等待 WM_HOTKEY
        msg = wintypes.MSG()
        WM_HOTKEY = 0x0312
        while True:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0:
                break
            if msg.message == WM_HOTKEY:
                wparam = msg.wParam
                if wparam == HOTKEY_ID_WAKE and wake:
                    print(f"[hotkey] {wake[0]} 按下，唤回窗口")
                    try:
                        _show_window()  # 内部按可见性变化触发节流菜单刷新
                    except Exception:
                        pass
                elif wparam == HOTKEY_ID_SEARCH and search:
                    print(f"[hotkey] {search[0]} 按下，唤起全局搜索")
                    try:
                        _trigger_global_search()
                    except Exception:
                        pass
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
    except Exception as e:
        print(f"[hotkey] 全局热键线程异常: {e}")


def _trigger_global_search():
    """按下全局搜索热键：确保窗口显示，并通知前端打开搜索框。"""
    try:
        # 先确保窗口显示（后台/托盘时唤回）；内部按可见性变化触发节流菜单刷新
        try:
            _show_window()
        except Exception:
            pass
        # 通过 HTTP 调用后端接口，发布 SSE 事件给前端
        import urllib.request
        req = urllib.request.Request(
            f"http://127.0.0.1:{_SERVER_PORT}/api/_self/global_search",
            method="POST")
        urllib.request.urlopen(req, timeout=3)
    except Exception as e:
        print(f"[hotkey] 触发全局搜索失败: {e}")


# ============================================================
# 托盘启动（daemon 线程，独立于 WebView 主线程）
# ============================================================
def _run_tray():
    try:
        import pystray
    except ImportError:
        print("[tray] pystray 未安装，跳过托盘")
        return

    img = _build_tray_image(64)
    if img is None:
        img = _build_tray_fallback_image(64)

    menu = _build_menu()
    tray = pystray.Icon(
        "drama_workspace",
        img,
        APP_TITLE,
        menu,
    )
    _tray_ref[0] = tray
    print("[tray] 托盘已启动")

    try:
        tray.run()
    except Exception as e:
        print(f"[tray] 托盘异常: {e}")


# ============================================================
# 托盘通知：定期拉取 /api/notifications，交付提醒变化时弹气泡
# ============================================================
def _run_tray_notifier():
    import time as _time
    import json as _j
    import urllib.request
    key = _api_secret()
    headers = {"X-API-KEY": key} if key else {}
    last_overdue = -1          # 上次逾期数（-1 表示首次，不弹）
    last_today = -1
    notified_day = ""          # 避免当天重复提醒今日交付
    while True:
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{_SERVER_PORT}/api/notifications",
                headers=headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                d = _j.loads(resp.read().decode("utf-8"))
            overdue = len(d.get("overdue") or [])
            today = len(d.get("today_deliver") or [])
            tday = d.get("today") or ""
            tray = _tray_ref[0]
            # 逾期数上升 → 弹提醒（用 _tray_lock 串行化，避免跨线程操作托盘句柄）
            if tray is not None and last_overdue >= 0 and overdue > last_overdue:
                new_n = overdue - last_overdue
                names = "、".join(x.get("name","") for x in (d.get("overdue") or [])[:3])
                try:
                    with _tray_lock:
                        tray.notify(f"新增 {new_n} 个逾期交付：{names}",
                                    APP_TITLE + " · 交付提醒")
                except Exception:
                    pass
            # 今日有交付，且当天还没提醒过 → 弹一次
            if tray is not None and today > 0 and tday != notified_day:
                names = "、".join(x.get("name","") for x in (d.get("today_deliver") or [])[:3])
                try:
                    with _tray_lock:
                        tray.notify(f"今日有 {today} 部交付：{names}",
                                    APP_TITLE + " · 交付提醒")
                except Exception:
                    pass
                notified_day = tday
            last_overdue = overdue
            last_today = today
        except Exception as e:
            pass  # 后端未就绪时静默重试
        _time.sleep(600)  # 每 10 分钟检查一次


# ============================================================
# Flask /api/quit 注册
# ============================================================
def _register_quit_api(flask_app):
    @flask_app.route("/api/quit", methods=["POST", "GET"])
    def _api_quit():
        try:
            from flask import jsonify
        except ImportError:
            return '{"ok":false}', 500
        print("👋 /api/quit 被调用")
        threading.Thread(target=_do_quit, daemon=True).start()
        return jsonify({"ok": True})

    # 全局搜索热键触发接口：发布 SSE search 事件，前端收到后打开搜索框
    @flask_app.route("/api/_self/global_search", methods=["POST"])
    def _api_global_search():
        try:
            from flask import jsonify
            # 先确保窗口显示（后台/托盘时唤回）；内部按可见性变化触发节流菜单刷新
            try:
                _show_window()
            except Exception:
                pass
            # 发布 SSE 事件，通知前端打开搜索框
            published = False
            try:
                from backend.app import sync_engine
                if sync_engine:
                    sync_engine._sse_publish({"type": "search"})
                    published = len(sync_engine._sse_clients) > 0
            except Exception:
                pass
            return jsonify({"ok": True, "sse_clients": published})
        except Exception:
            return '{"ok":true}', 200

    # Premiere CEP 面板跳转定位：先唤回窗口（托盘/最小化时），再广播 SSE jump 事件
    @flask_app.route("/api/_self/jump", methods=["POST", "GET"])
    def _api_self_jump():
        try:
            from flask import jsonify, request as _req
            project = (_req.args.get("project") or _req.form.get("project") or "").strip()
            if not project:
                return jsonify({"ok": False, "message": "缺少 project 参数"}), 400
            # 先确保窗口显示（后台/托盘时唤回），否则跳转高亮发生在不可见窗口里
            try:
                _show_window()
            except Exception:
                pass
            published = False
            try:
                from backend.app import sync_engine
                if sync_engine:
                    sync_engine._sse_publish({"type": "jump", "project": project})
                    published = len(sync_engine._sse_clients) > 0
            except Exception:
                pass
            return jsonify({"ok": True, "project": project, "sse_clients": published})
        except Exception:
            return '{"ok":false}', 200


    # 分秒帧内嵌窗口：软件内打开审片网页（不跳外部浏览器）
    # body: { url, title?, copy_path? }
    #   copy_path：可选，传入项目成片目录路径时自动复制到剪贴板，
    #   方便在分秒帧的上传对话框里直接 Ctrl+V 定位到目录。
    @flask_app.route("/api/_self/fenmiaozhen", methods=["POST"])
    def _api_self_fenmiaozhen():
        try:
            from flask import jsonify, request as _req
        except ImportError:
            return '{"ok":false}', 500
        body = _req.get_json(silent=True) or {}
        url = (body.get("url") or "").strip()
        title = (body.get("title") or "分秒帧").strip() or "分秒帧"
        project = (body.get("project") or "").strip()
        if not url:
            return jsonify({"ok": False, "message": "缺少 url"}), 400
        if not _fm_url_allowed(url):
            return jsonify({"ok": False, "message": "只允许打开分秒帧网址"}), 400

        # 成片目录路径由后端自己解析（不接受前端传任意路径，防越权）
        copy_path = ""
        if project:
            try:
                from backend.app import sync_engine as _se
                _proj = _se.db.get_project(project) or {}
                _base = (_proj.get("group_path") or "").strip()
                if not (_base and os.path.isdir(_base)):
                    _base = (_proj.get("production_path") or "").strip()
                if _base and os.path.isdir(_base):
                    _dirs = _se._find_output_dirs(_base, project) or []
                    _cand = _dirs[0] if _dirs else _base
                    if os.path.isdir(_cand):
                        copy_path = _cand
            except Exception as _pe:
                print(f"[fm] 解析成片目录失败: {_pe}")

        copied = False
        if copy_path:
            # 复用已修好的 _set_clipboard（内联版在 64 位下有句柄截断问题）
            if os.path.isdir(copy_path):
                copied = _set_clipboard(copy_path)

        # 仅复制路径、不开窗口（卡片点分秒帧时先跳 tab，只把上传目录准备好）
        if body.get("_no_window"):
            return jsonify({"ok": True, "no_window": True,
                            "path_copied": copied,
                            "copy_path": copy_path if copied else ""})

        # 创建/切换窗口必须在非主线程（Flask 请求线程满足条件）
        ok, msg = _open_fm_window(url, title)
        return jsonify({"ok": bool(ok), "message": msg,
                        "path_copied": copied, "copy_path": copy_path if copied else ""})

    # 分秒帧窗口自检（只读）：确认工具条/上传监控/JS 桥是否已注入。
    # 安全：只执行服务端写死的检查脚本，不接受外部传入任意 JS。
    @flask_app.route("/api/_self/fenmiaozhen/probe", methods=["POST"])
    def _api_self_fm_probe():
        try:
            from flask import jsonify, request as _rq
        except ImportError:
            return '{"ok":false}', 500
        w = _fm_window_ref[0]
        if w is None:
            return jsonify({"ok": False, "message": "窗口不存在"})
        script = (
            "(function(){return JSON.stringify({"
            "bar: !!document.getElementById('__fm_bar'),"
            "up: !!document.getElementById('__fm_up'),"
            "hook: !!window.__fmUploadHook,"
            "bridge: !!(window.pywebview && window.pywebview.api),"
            "apiKeys: Object.keys((window.pywebview && window.pywebview.api) || {}),"
            "hasCopy: !!(window.pywebview && window.pywebview.api && window.pywebview.api.copy_clipboard),"
            "url: location.href"
            "});})()"
        )
        # 可选：从可见页面侧真实发起一次进度回传（验证页面→Python 链路）
        action = (_rq.get_json(silent=True) or {}).get("action")
        sim_out = None
        if action == "sim_report":
            sim_js = (
                "window.pywebview.api.upload_report("
                "'{\"active\":1,\"loaded\":5242880,\"total\":20971520}'"
                ").then(function(r){return JSON.stringify(r);})"
            )
            try:
                sim_out = w.evaluate_js(sim_js)
            except Exception as _se:
                sim_out = "ERR " + str(_se)
        elif action == "sim_copy":
            sim_js = (
                "window.pywebview.api.copy_clipboard("
                "'https://app.mediatrack.cn/from-page-test'"
                ").then(function(r){return JSON.stringify(r);})"
            )
            try:
                sim_out = w.evaluate_js(sim_js)
            except Exception as _se:
                sim_out = "ERR " + str(_se)
            # 桥调用是异步的：必须等一会儿再读剪贴板，否则读到的是上一次的旧值
            time.sleep(0.9)
            # 直接读回剪贴板，确认页面请求真的写进去了
            try:
                import ctypes as _c
                _u = _c.windll.user32
                _k = _c.windll.kernel32
                _k.GlobalLock.restype = _c.c_void_p
                _k.GlobalLock.argtypes = [_c.c_void_p]
                _u.OpenClipboard.argtypes = [_c.c_void_p]
                _u.GetClipboardData.restype = _c.c_void_p
                _u.GetClipboardData.argtypes = [_c.c_uint]
                clip = ""
                if _u.OpenClipboard(None):
                    try:
                        _h = _u.GetClipboardData(13)
                        if _h:
                            _p = _k.GlobalLock(_c.c_void_p(_h))
                            if _p:
                                clip = _c.wstring_at(_p)
                                _k.GlobalUnlock(_c.c_void_p(_h))
                    finally:
                        _u.CloseClipboard()
                sim_out = {"bridge": sim_out, "clipboard": clip.rstrip("\x00")}
            except Exception as _ce:
                sim_out = {"bridge": sim_out, "clipboard_err": str(_ce)}

        try:
            raw = w.evaluate_js(script)
            return jsonify({"ok": True, "result": raw,
                            "sim": sim_out,
                            "upload_state": _fmup.snapshot(),
                            "uploading": _fmup.is_uploading()})
        except Exception as e:
            return jsonify({"ok": False, "message": str(e)})

    # 上传状态模拟（仅自检用：不写业务数据，只翻转瞬态状态机）
    @flask_app.route("/api/_self/fenmiaozhen/upload_sim", methods=["POST"])
    def _api_self_fm_upload_sim():
        try:
            from flask import jsonify, request as _rq
        except ImportError:
            return '{"ok":false}', 500
        b = _rq.get_json(silent=True) or {}
        return jsonify(_fmup.report(b.get("active"), b.get("loaded"), b.get("total")))

    # 关闭分秒帧窗口（不销毁主窗口）
    @flask_app.route("/api/_self/fenmiaozhen/close", methods=["POST"])
    def _api_self_fenmiaozhen_close():
        try:
            from flask import jsonify
        except ImportError:
            return '{"ok":false}', 500
        w = _fm_window_ref[0]
        if w is None:
            return jsonify({"ok": True, "message": "窗口不存在"})
        try:
            w.destroy()
        except Exception as e:
            print(f"[fm] 关闭窗口失败: {e}")
        _fm_window_ref[0] = None
        return jsonify({"ok": True})


# ============================================================
# Flask + waitress
# ============================================================
_server_ready = threading.Event()

def _run_server():
    try:
        from backend.app import create_app
        app = create_app()
        _flask_app[0] = app
        _register_quit_api(app)
        import waitress
        # 监听地址：从 config.yaml 读取 web.host（默认 0.0.0.0，便于通过 Tailscale 等内网访问）。
        # 若仅本机使用可改回 127.0.0.1。
        _host = "0.0.0.0"
        try:
            import yaml as _y
            _cfg_path = os.path.join(BASE_DIR, "backend", "config.yaml")
            if os.path.isfile(_cfg_path):
                with open(_cfg_path, "r", encoding="utf-8") as _f:
                    _cfg = _y.safe_load(_f) or {}
                _h = (_cfg.get("web", {}) or {}).get("host") or ""
                if _h:
                    _host = _h
        except Exception:
            pass
        # waitress 线程池：SSE 长连接 + NAS 扫描/同步等耗时操作会占用线程，
        # 16 线程在长时间运行/多连接时可能被占满导致 HTTP 请求排队无响应。
        # 提高到 32 并设置超时，避免资源耗尽。
        waitress.serve(app, host=_host, port=_SERVER_PORT, threads=32)
    except SystemExit:
        pass
    except Exception as e:
        print(f"[server] Flask 异常: {e}")
        traceback.print_exc()
    finally:
        _server_ready.set()


# ============================================================
# 主流程
# ============================================================
def _main():
    import webview

    # 1. Flask daemon
    threading.Thread(target=_run_server, daemon=True).start()

    # 2. 等 Flask 就绪
    print("🚀 视频工作台 启动中...")
    deadline = time.time() + 10
    import urllib.request
    while time.time() < deadline:
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{_SERVER_PORT}/api/health", timeout=0.5)
            break
        except Exception:
            time.sleep(0.15)
    print(f"✅ 服务就绪 http://127.0.0.1:{_SERVER_PORT}")

    # 3. 托盘 daemon（后台线程跑 pystray 主循环）
    threading.Thread(target=_run_tray, daemon=True).start()
    print("✅ 系统托盘已就绪")

    # 3.4 托盘交付提醒（后台定期拉取通知，变化时弹气泡）
    try:
        threading.Thread(target=_run_tray_notifier, daemon=True).start()
        print("📣 托盘交付提醒已启动")
    except Exception as e:
        print(f"[tray] 交付提醒启动失败: {e}")

    # 3.5 全局热键（唤回窗口，实际组合见线程日志）
    try:
        threading.Thread(target=_run_global_hotkey, daemon=True).start()
    except Exception as e:
        print(f"[hotkey] 全局热键启动失败: {e}")

    # 4. WebView 窗口（主线程阻塞）
    window = webview.create_window(
        title=APP_TITLE,
        url=f"http://127.0.0.1:{_SERVER_PORT}/",
        width=1400, height=900,
        min_size=(1100, 700),
        text_select=True,
        resizable=True,
    )
    _window_ref[0] = window

    # 注册分秒帧上传完成后的提醒回调（托盘气泡）
    try:
        _fmup.set_done_callback(_fm_notify_upload_done)
        print("[fm] 上传完成提醒已就绪")
    except Exception as e:
        print(f"[fm] 上传完成提醒注册失败: {e}")

    # 应用启动设置（最小化到托盘 / 自动扫描）
    try:
        _apply_startup_settings()
    except Exception as e:
        print(f"[startup] 应用启动设置异常: {e}")

    # 关闭按钮 → 隐藏到托盘而非退出
    def _on_closing():
        print("[webview] 用户关闭窗口 → 隐藏到托盘")
        _hide_window()  # 内部按可见性变化触发节流菜单刷新
        return False  # 取消默认关闭行为

    try:
        window.events.closing += _on_closing
    except Exception:
        pass

    # WebView profile：必须持久化，否则分秒帧每次重启都要重新登录
    # （pywebview 默认 private_mode=True，cookie/localStorage 全在内存里，退出即丢）
    _profile_dir = os.path.join(BASE_DIR, "data", "webview_profile")
    _private = True
    try:
        os.makedirs(_profile_dir, exist_ok=True)
        _probe = os.path.join(_profile_dir, ".writetest")
        with open(_probe, "w", encoding="utf-8") as _pf:
            _pf.write("ok")
        os.remove(_probe)
        _private = False
        print(f"[webview] 使用持久化 profile: {_profile_dir}")
    except Exception as _pe:
        print(f"[webview] profile 目录不可用，回退到私密模式: {_pe}")

    try:
        webview.start(gui="edgechromium", debug=False,
                      private_mode=_private,
                      storage_path=(None if _private else _profile_dir))
    finally:
        print("👋 WebView 主线程退出，清理中...")
        if _mutex:
            try:
                ctypes.windll.kernel32.CloseHandle(_mutex)
            except Exception:
                pass
        os._exit(0)


if __name__ == "__main__":
    try:
        _main()
    except Exception as e:
        print(f"❌ 致命错误: {e}")
        traceback.print_exc()
        if not _is_pythonw:
            input("按回车退出...")
        sys.exit(1)
    finally:
        try:
            if _is_pythonw and _logger:
                _logger.close()
        except:
            pass
