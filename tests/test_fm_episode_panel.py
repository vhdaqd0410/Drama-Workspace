# -*- coding: utf-8 -*-
"""回归：状态变更自动刷新进度 + 分秒帧窗口内分集面板。

需求（2026-11）：
  1. 手动改项目状态后，自动执行一次「一键刷新进度」。
     目的：改完状态，卡片上的进度/缺集要立刻反映新阶段，不用再手点刷新。
  2. 分秒帧窗口里能看到该项目的分集→剪辑师对应，并有集号查询，
     方便核对要修改的集数到底是谁做的。
     实现：页面内注入「📋 分集」按钮 + 面板，数据经 JS 桥取 DB 的 episode_plan。
"""
import io
import os
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with io.open(os.path.join(BASE, rel), encoding="utf-8") as f:
        return f.read()


class AutoRefreshOnStatusTests(unittest.TestCase):
    def _seg(self):
        src = read("static/js/project.js")
        i = src.find("async function onStatusChange")
        self.assertGreater(i, 0)
        return src[i:i + 4200]

    def test_refresh_after_status_change(self):
        seg = self._seg()
        self.assertIn("refreshProjectStatus", seg, "改状态后没有触发刷新")

    def test_refresh_is_silent(self):
        """静默刷新，避免和“状态已更新”的提示打架。"""
        seg = self._seg()
        self.assertIn("refreshProjectStatus(pname, null, true)", seg,
                      "刷新未以静默模式调用")

    def test_refresh_after_render(self):
        """要先重绘卡片再刷新，否则更新不到新的 DOM。"""
        seg = self._seg()
        p_render = seg.find("renderDashboard()")
        self.assertGreater(p_render, 0)
        tail = seg[p_render:]
        self.assertIn("refreshProjectStatus(pname, null, true)", tail[:700],
                      "渲染之后没有紧跟刷新")

    def test_done_branch_also_refreshes(self):
        """改成“已完成”会提前 return，那条路径也要刷。"""
        seg = self._seg()
        i = seg.find("newStatus === '已完成'")
        self.assertGreater(i, 0)
        branch = seg[i:i + 700]
        self.assertIn("refreshProjectStatus", branch, "已完成分支没刷新")

    def test_refresh_supports_silent(self):
        src = read("static/js/episode.js")
        i = src.find("function refreshProjectStatus")
        seg = src[i:i + 800]
        self.assertIn("silent", seg, "refreshProjectStatus 不支持静默")
        self.assertIn("return data", seg, "未返回数据，便于链式调用")


class EpisodePanelTests(unittest.TestCase):
    def test_bridge_method(self):
        src = read("main_desktop.py")
        self.assertIn("def get_episodes", src, "JS 桥缺 get_episodes")

    def test_episodes_reader(self):
        src = read("main_desktop.py")
        i = src.find("def _fm_episodes")
        self.assertGreater(i, 0, "缺分集读取函数")
        seg = src[i:i + 2000]
        self.assertIn("episode_plan", seg, "未用 episode_plan 作数据源")
        self.assertIn("items.sort", seg, "分集未排序")

    def test_project_tracked(self):
        """窗口要记住关联项目，否则分集面板不知道查谁。"""
        src = read("main_desktop.py")
        self.assertIn("_fm_project_ref", src, "未记录窗口关联项目")
        i = src.find("def _open_fm_window")
        seg = src[i:i + 900]
        self.assertIn("_fm_project_ref[0] = project", seg, "打开窗口时未记录项目")

    def test_route_passes_project(self):
        src = read("main_desktop.py")
        i = src.find("def _api_self_fenmiaozhen")
        seg = src[i:i + 3000]
        self.assertIn("_open_fm_window(url, title, project)", seg, "路由未把项目传给窗口")

    def test_panel_button_injected(self):
        seg = read("static/js/fm-inject.js")
        self.assertIn("📋 分集", seg, "工具条缺分集按钮")
        self.assertIn("__fm_btn_eps", seg, "缺分集按钮元素")
        self.assertIn("togglePanel", seg, "缺面板开关")

    def test_panel_has_search(self):
        """要能按集号查询。"""
        seg = read("static/js/fm-inject.js")
        self.assertIn("__fm_q", seg, "缺查询输入框")
        self.assertIn("render", seg, "缺渲染逻辑")
        self.assertIn("没有匹配的集号", seg, "查询无结果无提示")

    def test_panel_shows_editor(self):
        seg = read("static/js/fm-inject.js")
        self.assertIn("editor", seg, "未展示剪辑师")
        self.assertIn("未分配", seg, "未处理未分配集")

    def test_panel_closable(self):
        seg = read("static/js/fm-inject.js")
        self.assertIn("__fm_close", seg, "面板缺关闭按钮")

    def test_probe_reports_eps(self):
        src = read("main_desktop.py")
        self.assertIn("hasEps", src, "自检未检查分集桥")
        self.assertIn("barBtns", src, "自检未检查工具条按钮")

    def test_probe_script_is_string(self):
        """自检脚本必须是字符串；拼接里混入逗号会变 tuple，evaluate_js 直接报错。"""
        import ast
        src = read("main_desktop.py")
        tree = ast.parse(src)
        node = None
        for f in ast.walk(tree):
            if isinstance(f, ast.FunctionDef) and f.name == "_api_self_fm_probe":
                for sub in ast.walk(f):
                    if isinstance(sub, ast.Assign) and getattr(sub.targets[0], "id", "") == "script":
                        node = sub.value
                        break
        self.assertIsNotNone(node, "未找到 script 赋值")
        self.assertNotIsInstance(node, ast.Tuple, "script 被拼成了 tuple")


if __name__ == "__main__":
    unittest.main()