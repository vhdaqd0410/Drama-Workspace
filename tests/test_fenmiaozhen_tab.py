# -*- coding: utf-8 -*-
"""回归：分秒帧板块（项目清单）+ 独立窗口登录通道。

实测结论（2026-11，改方向的原因，别退回 iframe）：
  1. 软件内独立窗口可以正常登录分秒帧。
  2. iframe 板块点登录必定跳系统浏览器：
     跨域 iframe 的 window.open 冒泡到顶层 WebView，pywebview 的处理是把
     NewWindowRequested 交给 webbrowser.open。
  3. 全局关掉 OPEN_EXTERNAL_LINKS_IN_BROWSER 不可行：主窗口有 14 处 window.open
     （质检报告下载等），会全部变成同窗导航，把工作台主界面带走。
  4. 往分秒帧窗口注入「window.open → 同窗跳转」也撤掉了：独立窗口本来就能登录，
     注入反而可能弄坏依赖弹窗+opener 的登录流程。
  → 结论：登录和上传统一走独立窗口；板块负责「项目↔链接清单 + 一键打开 + 复制成片路径」。
"""
import io
import os
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with io.open(os.path.join(BASE, rel), encoding="utf-8") as f:
        return f.read()


class WindowLifecycleTests(unittest.TestCase):
    def test_alive_check_function(self):
        src = read("main_desktop.py")
        self.assertIn("def _fm_window_alive", src, "缺少窗口存活校验")

    def test_alive_check_actually_probes(self):
        src = read("main_desktop.py")
        i = src.find("def _fm_window_alive")
        seg = src[i:i + 700]
        self.assertIn("get_current_url", seg, "死窗口会被误判为存活")
        self.assertIn("except", seg)

    def test_closed_event_releases_ref(self):
        src = read("main_desktop.py")
        self.assertIn("def _on_fm_closed", src)
        self.assertIn("events.closed", src)
        seg = src[src.find("def _on_fm_closed"):][:420]
        self.assertIn("_fm_window_ref[0] = None", seg)

    def test_open_checks_alive_before_reuse(self):
        src = read("main_desktop.py")
        i = src.find("def _open_fm_window")
        seg = src[i:i + 1800]
        self.assertIn("_fm_window_alive", seg)

    def test_no_window_flag(self):
        src = read("main_desktop.py")
        self.assertIn("_no_window", src, "缺少只复制路径不开窗的分支")

    def test_no_injection_hook(self):
        """注入「window.open 同窗跳转」已撤掉，别再加回来。"""
        src = read("main_desktop.py")
        self.assertNotIn("_FM_REDIRECT_JS", src, "注入脚本又回来了，会威胁已可用的登录")
        self.assertNotIn("window.__fmRedirectHook = true", src)


class LoginChannelTests(unittest.TestCase):
    def test_global_setting_untouched(self):
        """不能动 pywebview 全局 OPEN_EXTERNAL_LINKS_IN_BROWSER。"""
        src = read("main_desktop.py")
        self.assertNotIn("OPEN_EXTERNAL_LINKS_IN_BROWSER'] = False", src,
                         "全局关掉会把主窗口 14 处 window.open 变成同窗导航")

    def test_persistent_profile_for_login(self):
        src = read("main_desktop.py")
        i = src.find("webview.start(")
        seg = src[max(0, i - 1200):i + 400]
        self.assertIn("private_mode", seg, "登录态需要持久化")
        self.assertIn("storage_path", seg)
        self.assertIn("webview_profile", seg)


class TabListTests(unittest.TestCase):
    def test_tab_button(self):
        html = read("templates/index.html")
        self.assertIn('data-tab="fenmiaozhen"', html, "缺少分秒帧 tab")

    def test_panel_is_list_not_iframe(self):
        """板块用清单，不再用 iframe 承载登录。"""
        html = read("templates/index.html")
        self.assertIn('id="tab-fenmiaozhen"', html)
        self.assertIn('id="fmListWrap"', html, "缺少项目清单容器")
        self.assertNotIn('id="fmFrame"', html, "iframe 又回来了（登录在里面无法完成）")

    def test_panel_has_open_window_entry(self):
        html = read("templates/index.html")
        self.assertIn("fmOpenWindow()", html, "缺少打开独立窗口入口")

    def test_script_included(self):
        html = read("templates/index.html")
        self.assertIn("/static/js/fenmiaozhen.js", html)

    def test_switch_tab_hook(self):
        src = read("static/js/core.js")
        self.assertIn("fenmiaozhen' && typeof fmTabEnter", src)

    def test_host_whitelist(self):
        src = read("static/js/fenmiaozhen.js")
        self.assertIn("mediatrack", src)
        self.assertIn("只允许分秒帧网址", src)

    def test_list_render_escapes(self):
        """项目名直接拼进 onclick，必须转义，避免名字里的引号破坏 DOM。"""
        src = read("static/js/fenmiaozhen.js")
        i = src.find("window.fmRenderList")
        seg = src[i:i + 2200]
        self.assertIn("esc(", seg, "未做转义")
        self.assertIn("JSON.stringify", seg, "onclick 参数未安全编码")

    def test_card_button_opens_window(self):
        """卡片按钮在桌面版应直接开独立窗口（已验证可登录）。"""
        src = read("static/js/project.js")
        i = src.find("async function openFenmiaozhen")
        seg = src[i:i + 500]
        self.assertIn("fmOpenForProject", seg)
        self.assertIn("__IS_DESKTOP__", seg)


class LinkApiTests(unittest.TestCase):
    def test_all_links_api(self):
        src = read("backend/enhanced_routes.py")
        self.assertIn("/api/fenmiaozhen/links", src, "缺少全量链接接口")

    def test_delete_link_api(self):
        src = read("backend/enhanced_routes.py")
        self.assertIn("DELETE", src, "缺少移除链接接口")
        self.assertIn("/api/fenmiaozhen/link/", src)


if __name__ == "__main__":
    unittest.main()