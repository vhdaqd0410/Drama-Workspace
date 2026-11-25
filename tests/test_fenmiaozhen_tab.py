# -*- coding: utf-8 -*-
"""回归：分秒帧板块（tab 内嵌）+ 窗口生命周期修复。

用户反馈（2026-11）：
  1. 关闭分秒帧窗口后再点按钮，提示已打开但窗口不出现。
     → 根因：关窗后 _fm_window_ref 仍持有已销毁对象，代码只看「ref 非空」就当成
       窗口还在，load_url 在死窗口上空转。修法：closed 事件清引用 + 存活探测。
  2. 希望在软件里直接加一个分秒帧板块。
     → tab 内嵌 iframe，同时保留独立窗口作为兜底（iframe 是第三方上下文，
       登录可能被 cookie 策略挡住，不能把用户堵死在一条路上）。
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
        """不能只判断 ref 非空，必须触碰 native 侧。"""
        src = read("main_desktop.py")
        i = src.find("def _fm_window_alive")
        seg = src[i:i + 700]
        self.assertIn("get_current_url", seg, "未触碰 native 侧，死窗口会被误判为存活")
        self.assertIn("except", seg)

    def test_closed_event_releases_ref(self):
        src = read("main_desktop.py")
        self.assertIn("def _on_fm_closed", src, "缺少关闭事件处理")
        self.assertIn("events.closed", src, "未绑定窗口关闭事件")
        seg = src[src.find("def _on_fm_closed"):][:420]
        self.assertIn("_fm_window_ref[0] = None", seg, "关窗后未释放引用")

    def test_open_checks_alive_before_reuse(self):
        """_open_fm_window 里必须先校验存活再复用。"""
        src = read("main_desktop.py")
        i = src.find("def _open_fm_window")
        seg = src[i:i + 1800]
        self.assertIn("_fm_window_alive", seg, "打开前未校验窗口存活")

    def test_no_window_flag(self):
        """只复制路径不开窗的分支（卡片跳板块时用）。"""
        src = read("main_desktop.py")
        self.assertIn("_no_window", src, "缺少仅复制路径的分支")


class TabPanelTests(unittest.TestCase):
    def test_tab_button(self):
        html = read("templates/index.html")
        self.assertIn('data-tab="fenmiaozhen"', html, "缺少分秒帧 tab")

    def test_panel_container(self):
        html = read("templates/index.html")
        self.assertIn('id="tab-fenmiaozhen"', html, "缺少分秒帧面板")
        self.assertIn('id="fmFrame"', html, "缺少内嵌 iframe")

    def test_panel_has_fallback_buttons(self):
        html = read("templates/index.html")
        self.assertIn("fmOpenWindow()", html, "缺少独立窗口兜底入口")
        self.assertIn("fmOpenInBrowser()", html, "缺少浏览器入口")

    def test_script_included(self):
        html = read("templates/index.html")
        self.assertIn("/static/js/fenmiaozhen.js", html, "面板脚本未引入")

    def test_switch_tab_hook(self):
        src = read("static/js/core.js")
        self.assertIn("fenmiaozhen' && typeof fmTabEnter", src, "切 tab 未触发加载钩子")

    def test_host_whitelist_in_frontend(self):
        """iframe 只允许加载分秒帧域名，防止被塞任意网址。"""
        src = read("static/js/fenmiaozhen.js")
        i = src.find("window.fmLoad")
        seg = src[i:i + 900]
        self.assertIn("mediatrack", seg)
        self.assertIn("只允许加载分秒帧网址", seg)

    def test_lazy_load(self):
        """首次进 tab 不主动拉外部网页，避免拖慢首屏。"""
        src = read("static/js/fenmiaozhen.js")
        i = src.find("window.fmTabEnter")
        seg = src[i:i + 400]
        self.assertNotIn("fmLoad(", seg, "进 tab 就自动加载了，应保持懒加载")

    def test_card_button_goes_to_tab(self):
        """桌面版卡片按钮应切到板块，而不是开独立窗口。"""
        src = read("static/js/project.js")
        i = src.find("async function openFenmiaozhen")
        seg = src[i:i + 500]
        self.assertIn("fmOpenForProject", seg, "卡片按钮未接入板块")
        self.assertIn("__IS_DESKTOP__", seg)


if __name__ == "__main__":
    unittest.main()