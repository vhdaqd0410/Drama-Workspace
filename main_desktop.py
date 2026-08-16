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


# ============ 文件日志 ============
_LOG_PATH = os.path.join(BASE_DIR, "desktop.log")
class _FileLogger:
    def __init__(self, path):
        self.f = open(path, "w", encoding="utf-8")
    def write(self, msg):
        ts = time.strftime("%H:%M:%S")
        self.f.write(f"[{ts}] {msg}\n")
        try: self.f.flush()
        except: pass
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
_window_visible = [True]
_toggle_menu_item_ref = [None]  # 需要动态改文案的那个菜单项


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
    """显示主窗口并置前台"""
    w = _window_ref[0]
    if w is None:
        return
    try:
        w.restore()
        w.show()
        # 用 Win32 强制前置
        try:
            hwnd = ctypes.windll.user32.FindWindowW(None, APP_TITLE)
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass
        _window_visible[0] = True
        print("[tray] 窗口已显示")
    except Exception as e:
        print(f"[tray] show_window 异常: {e}")


def _hide_window():
    """隐藏主窗口到托盘"""
    w = _window_ref[0]
    if w is None:
        return
    try:
        w.hide()
        _window_visible[0] = False
        print("[tray] 窗口已隐藏（仍在托盘运行）")
    except Exception as e:
        print(f"[tray] hide_window 异常: {e}")


def _toggle_window(icon=None, item=None):
    if _window_visible[0]:
        _hide_window()
    else:
        _show_window()
    _update_tray_label()


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
    # 先停止托盘（避免回调卡死）
    try:
        if _tray_ref[0] is not None:
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


# ============================================================
# 托盘菜单
# 说明：pystray 的 MenuItem.text 是只读属性，不能直接改文案（旧实现会报
# "can't set attribute 'text'"）。正确做法是整体重建菜单并赋回 tray.menu，
# 由后端触发重绘，从而动态切换"隐藏/显示"文案。
# ============================================================
def _build_menu(visible=True):
    import pystray
    toggle_text = "隐藏窗口到托盘" if visible else "显示主窗口"
    toggle_item = pystray.MenuItem(toggle_text, _toggle_window, default=True)
    _toggle_menu_item_ref[0] = toggle_item
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
        pystray.MenuItem("🚪 退出", _do_quit_tray),
    )


def _update_tray_label():
    """根据窗口可见性重建托盘菜单并刷新文案（替换旧的只读 text 赋值方式）。"""
    tray = _tray_ref[0]
    if tray is None:
        return
    try:
        tray.menu = _build_menu(_window_visible[0])
        # 通知后端重绘托盘菜单（部分后端需要，win32 下无害）
        if hasattr(tray, "update_menu"):
            tray.update_menu()
        print(f"[tray] 菜单文案已更新 → {'隐藏窗口到托盘' if _window_visible[0] else '显示主窗口'}")
    except Exception as e:
        print(f"[tray] 更新菜单文案失败: {e}")


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
        _show_window()
        _update_tray_label()
    try:
        w = _window_ref[0]
        if w is not None and hasattr(w, "evaluate_js"):
            w.evaluate_js(js_code)
    except Exception as e:
        print(f"[tray] evaluate_js 失败: {e}")


def _tray_go_insights(icon=None, item=None):
    _trigger_js("try{openInsightsDialog()}catch(e){}")


def _tray_go_todos(icon=None, item=None):
    _trigger_js("try{openGlobalTodos()}catch(e){}")


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
    """根据设置执行启动行为：延迟后触发扫描 / 隐藏窗口。"""
    min_tray, auto_scan = _read_startup_settings()
    print(f"[startup] 启动行为 → 最小化到托盘: {min_tray}, 自动扫描: {auto_scan}")
    # 自动扫描：等服务与界面就绪后延迟触发，避免阻塞首屏
    if auto_scan:
        def _scan():
            time.sleep(6)
            print("[startup] 按设置自动扫描 NAS...")
            _trigger_api("scan")
        threading.Thread(target=_scan, daemon=True).start()
    # 最小化到托盘：延迟到窗口创建完成后执行
    if min_tray:
        def _min():
            time.sleep(2)
            _hide_window()
            _update_tray_label()
            print("[startup] 已按设置最小化到托盘")
        threading.Thread(target=_min, daemon=True).start()


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
                        _show_window()
                        _update_tray_label()
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
        # 先确保窗口显示（后台/托盘时唤回）
        try:
            _show_window()
            _update_tray_label()
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
            # 逾期数上升 → 弹提醒
            if tray is not None and last_overdue >= 0 and overdue > last_overdue:
                new_n = overdue - last_overdue
                names = "、".join(x.get("name","") for x in (d.get("overdue") or [])[:3])
                try:
                    tray.notify(f"新增 {new_n} 个逾期交付：{names}",
                                APP_TITLE + " · 交付提醒")
                except Exception:
                    pass
            # 今日有交付，且当天还没提醒过 → 弹一次
            if tray is not None and today > 0 and tday != notified_day:
                names = "、".join(x.get("name","") for x in (d.get("today_deliver") or [])[:3])
                try:
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
            # 先确保窗口显示（后台/托盘时唤回）
            try:
                _show_window()
                _update_tray_label()
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
        waitress.serve(app, host="127.0.0.1", port=_SERVER_PORT, threads=16)
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

    # 应用启动设置（最小化到托盘 / 自动扫描）
    try:
        _apply_startup_settings()
    except Exception as e:
        print(f"[startup] 应用启动设置异常: {e}")

    # 关闭按钮 → 隐藏到托盘而非退出
    def _on_closing():
        print("[webview] 用户关闭窗口 → 隐藏到托盘")
        _hide_window()
        _update_tray_label()
        return False  # 取消默认关闭行为

    try:
        window.events.closing += _on_closing
    except Exception:
        pass

    try:
        webview.start(gui="edgechromium", debug=False)
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
