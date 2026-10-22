# -*- coding: utf-8 -*-
"""回归：设置页「已忽略项目」管理面板（误删恢复）。

背景（2026-10-22）：项目被「彻底删除」拉黑后 NAS 目录仍在，
刷新多少次都出不来，且前端没有任何解除入口。
"""
import io
import os
import re
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with io.open(os.path.join(BASE, rel), encoding="utf-8") as f:
        return f.read()


class IgnoredPanelUITests(unittest.TestCase):
    def test_setting_panel_has_block(self):
        html = read("templates/index.html")
        self.assertIn("ignoredProjList", html, "设置页缺少已忽略项目区块")
        self.assertIn("已忽略项目", html)
        self.assertIn("loadIgnoredProjects()", html, "缺少刷新按钮绑定")

    def test_js_functions_exist(self):
        src = read("static/js/team.js")
        self.assertIn("async function loadIgnoredProjects", src)
        self.assertIn("async function unignoreProject", src)

    def test_loadconfig_triggers_panel(self):
        """打开设置页应自动加载清单。"""
        src = read("static/js/team.js")
        i = src.find("async function loadConfig")
        seg = src[i:i + 1500]
        self.assertIn("loadIgnoredProjects()", seg,
                      "loadConfig 未触发清单加载，进设置页看不到数据")

    def test_panel_shows_nas_state(self):
        src = read("static/js/team.js")
        i = src.find("async function loadIgnoredProjects")
        seg = src[i:i + 2600]
        self.assertIn("on_nas", seg, "未展示 NAS 上是否还在")
        self.assertIn("可恢复", seg, "未提示可恢复状态")

    def test_unignore_calls_api_and_refreshes(self):
        src = read("static/js/team.js")
        i = src.find("async function unignoreProject")
        seg = src[i:i + 1200]
        self.assertIn("/unignore", seg, "未调用解除接口")
        self.assertIn("loadIgnoredProjects()", seg, "恢复后未刷新清单")
        self.assertIn("loadProjects", seg, "恢复后未刷新项目列表")

    def test_no_template_string_damage(self):
        """HTML 拼接不能被破坏（此前多次出现模板串碎片）。"""
        src = read("static/js/team.js")
        i = src.find("async function loadIgnoredProjects")
        seg = src[i:i + 2600]
        self.assertEqual(seg.count("`") % 2, 0, "反引号未配对")


if __name__ == "__main__":
    unittest.main()
