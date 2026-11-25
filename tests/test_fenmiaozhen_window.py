# -*- coding: utf-8 -*-
"""回归：分秒帧网页内嵌到工作台（软件内独立窗口，不跳外部浏览器）。

需求（2026-11）：把分秒帧网页封装进软件，方便上传成片。

技术事实（本次调研得出，改动时别破坏）：
  1. 分秒帧站点没有 X-Frame-Options / CSP，但 iframe 属于第三方上下文，
     浏览器 SameSite 策略会把登录 cookie 挡掉 → 不用 iframe，用独立 WebView 窗口。
  2. pywebview 的 create_window 只在「非主线程且 GUI 已启动」时才立即创建窗口，
     所以必须从 Flask 请求线程调用（不能放主线程）。
  3. pywebview 默认 private_mode=True → cookie 全在内存，重启就丢登录态，
     必须 private_mode=False + storage_path 落盘。
"""
import io
import os
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with io.open(os.path.join(BASE, rel), encoding="utf-8") as f:
        return f.read()


class EmbedWindowTests(unittest.TestCase):
    def test_open_route_exists(self):
        src = read("main_desktop.py")
        self.assertIn('/api/_self/fenmiaozhen"', src, "缺少内嵌窗口路由")

    def test_close_route_exists(self):
        src = read("main_desktop.py")
        self.assertIn("/api/_self/fenmiaozhen/close", src, "缺少关闭窗口路由")

    def test_host_whitelist(self):
        """只允许分秒帧域名，避免接口被当成任意网址跳板。"""
        src = read("main_desktop.py")
        self.assertIn("_FM_ALLOW_HOSTS", src)
        self.assertIn('"mediatrack.cn"', src)
        seg = src[src.find("def _fm_url_allowed"):][:700]
        self.assertIn("hostname", seg, "未解析主机名校验")
        self.assertIn("endswith", seg, "未做子域匹配")

    def test_create_window_from_request_thread(self):
        """create_window 必须在非主线程调用才立即生效。"""
        src = read("main_desktop.py")
        i = src.find("def _open_fm_window")
        self.assertGreater(i, 0)
        seg = src[i:i + 1600]
        self.assertIn("create_window", seg, "未创建独立窗口")
        self.assertIn("非主线程", seg, "缺少调用线程约束说明")

    def test_reuses_existing_window(self):
        """重复点击应复用窗口（load_url），不能越开越多。"""
        src = read("main_desktop.py")
        i = src.find("def _open_fm_window")
        seg = src[i:i + 1600]
        self.assertIn("_fm_window_ref", seg)
        self.assertIn("load_url", seg, "复用时未切换地址")

    def test_private_mode_persistent(self):
        """登录态要能长期保存，否则每次重启都要重登分秒帧。"""
        src = read("main_desktop.py")
        i = src.find("webview.start(")
        self.assertGreater(i, 0)
        seg = src[max(0, i - 1200):i + 400]
        self.assertIn("private_mode", seg, "未设置 private_mode")
        self.assertIn("storage_path", seg, "未设置持久化目录")
        self.assertIn("webview_profile", seg, "持久化目录未落地")

    def test_profile_dir_writability_guard(self):
        """profile 目录不可写时要回退，不能因此打不开软件。"""
        src = read("main_desktop.py")
        i = src.find("_profile_dir")
        seg = src[i:i + 900]
        self.assertIn("except", seg, "profile 目录失败时无回退")
        self.assertIn("_private", seg)


class PathProtectionTests(unittest.TestCase):
    def test_copy_path_resolved_by_backend(self):
        """剪贴板路径由后端按项目名解析，不接受前端传任意路径。"""
        src = read("main_desktop.py")
        i = src.find("_api_self_fenmiaozhen")
        seg = src[i:i + 2200]
        self.assertIn("get_project", seg, "未按项目名查库")
        self.assertIn("_find_output_dirs", seg, "未解析成片目录")
        self.assertIn("isdir", seg, "未校验目录存在")

    def test_clipboard_write_guarded(self):
        src = read("main_desktop.py")
        i = src.find("_api_self_fenmiaozhen")
        seg = src[i:i + 2600]
        self.assertIn("OpenClipboard", seg)
        self.assertIn("CloseClipboard", seg)
        self.assertIn("except", seg, "剪贴板异常未兜底")


class FrontendTests(unittest.TestCase):
    def test_desktop_uses_embedded_window(self):
        src = read("static/js/project.js")
        self.assertIn("openFenmiaozhenWindow", src, "缺少内嵌打开函数")
        i = src.find("function openFenmiaozhenWindow")
        seg = src[i:i + 700]
        self.assertIn("__IS_DESKTOP__", seg, "未区分桌面版")
        self.assertIn("/api/_self/fenmiaozhen", seg, "桌面版未走内嵌接口")

    def test_browser_fallback(self):
        """浏览器访问仍应新标签页打开，不依赖桌面接口。"""
        src = read("static/js/project.js")
        i = src.find("function openFenmiaozhenWindow")
        seg = src[i:i + 900]
        self.assertIn("window.open", seg, "缺少浏览器回退")

    def test_button_passes_project_name(self):
        """点按钮要带上项目名，后端才能解析成片目录。"""
        src = read("static/js/project.js")
        i = src.find("async function openFenmiaozhen")
        seg = src[i:i + 1600]
        self.assertIn("分秒帧 - ", seg)
        self.assertIn(", name)", seg, "未把项目名传给后端")


if __name__ == "__main__":
    unittest.main()