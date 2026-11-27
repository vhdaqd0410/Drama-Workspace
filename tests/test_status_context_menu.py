# -*- coding: utf-8 -*-
"""回归：状态按钮右键菜单（按状态精确定位目录）。

用户需求（2026-11）：
  待交付 → 复制/打开「组内NAS 交付路径」
  审核中 → 打开分秒帧窗口、修改分秒帧链接（非二部）
  修改中 → 列出所有修改目录，可复制/打开
  总则：每个状态给出该阶段真正关心的目录，而不是笼统一个“项目根”。

设计取舍：
  后端 /api/project/<name>/state_paths 负责「状态 → 路径清单」映射，
  前端只渲染。这样业务规则集中在一处，前端不用重复判断。
"""
import io
import os
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with io.open(os.path.join(BASE, rel), encoding="utf-8") as f:
        return f.read()


class StatePathsApiTests(unittest.TestCase):
    def test_route_exists(self):
        src = read("backend/enhanced_routes.py")
        self.assertIn("/state_paths", src, "缺少状态路径接口")

    def _seg(self):
        src = read("backend/enhanced_routes.py")
        i = src.find("def project_state_paths")
        self.assertGreater(i, 0)
        return src[i:src.find("分集导出到 Excel 模板")]

    def test_daijiaofu_has_delivery_dir(self):
        seg = self._seg()
        self.assertIn("待交付", seg)
        self.assertIn("group_deliv", seg, "待交付缺组内NAS交付目录")
        # 待交付分支里必须出现交付目录
        i = seg.find("if status == '待交付'")
        branch = seg[i:i + 900]
        self.assertIn("deliv_name", branch, "待交付未拼交付目录名")

    def test_xiugai_lists_all_revision_folders(self):
        seg = self._seg()
        i = seg.find("elif status == '修改中'")
        self.assertGreater(i, 0)
        branch = seg[i:i + 1100]
        self.assertIn("list_all_revision_folders", branch, "修改中未列修改目录")
        self.assertIn("revs", branch)

    def test_shenhe_has_video_dirs(self):
        seg = self._seg()
        i = seg.find("'审' in status")
        self.assertGreater(i, 0)
        branch = seg[i:i + 900]
        self.assertIn("outs", branch, "审核中未给成片目录")

    def test_group_and_prod_dirs_separated(self):
        """组盘与制作部路径必须分别计算，否则标签与内容不符。"""
        seg = self._seg()
        self.assertIn("outs_prod", seg, "未单独计算制作部成片目录")
        # 制作部成片目录应用 outs_prod，而不是拿 outs 顶替
        i = seg.find("制作部成片目录")
        self.assertGreater(i, 0)
        around = seg[max(0, i - 200):i + 200]
        self.assertIn("outs_prod", around, "制作部成片目录用了组盘的 outs")

    def test_returns_exists_flag(self):
        seg = self._seg()
        self.assertIn("'exists'", seg, "未返回目录是否存在")
        self.assertIn("_os.path.isdir", seg, "未校验目录存在")

    def test_uses_os_alias(self):
        """本模块 import os as _os，写裸 os 会 NameError。"""
        import re
        seg = self._seg()
        bare = re.findall(r"(?<![_\w])os\.path", seg)
        self.assertEqual(bare, [], "出现裸 os.path")


class StatusMenuUiTests(unittest.TestCase):
    def test_script_included(self):
        html = read("templates/index.html")
        self.assertIn("/static/js/status-menu.js", html, "右键菜单脚本未引入")

    def test_bound_to_status_select(self):
        src = read("static/js/core.js")
        self.assertIn("oncontextmenu", src, "状态选择器未绑定右键")
        self.assertIn("statusContextMenu", src)

    def test_menu_css(self):
        html = read("templates/index.html")
        for cls in (".st-menu", ".st-menu-sec", ".st-mi-path", ".st-mi-btns"):
            self.assertIn(cls, html, "缺少 %s 样式" % cls)

    def test_calls_state_paths(self):
        src = read("static/js/status-menu.js")
        self.assertIn("/state_paths", src, "未请求状态路径")

    def test_copy_uses_backend(self):
        """复制路径走后端剪贴板（WebView2 里 navigator.clipboard 不可靠）。"""
        src = read("static/js/status-menu.js")
        seg = src[src.find("function copyText"):][:900]
        self.assertIn("/api/_self/clipboard", seg, "复制未走后端")
        self.assertIn("fallbackCopy", seg, "缺浏览器回退")

    def test_open_uses_open_folder(self):
        src = read("static/js/status-menu.js")
        self.assertIn("/open_folder", src, "打开路径未走 open_folder 接口")

    def test_audit_status_has_fm_actions(self):
        """审核类状态且有权限的部门，要出现分秒帧动作。"""
        src = read("static/js/status-menu.js")
        seg = src[src.find("function render"):][:1200]
        self.assertIn("打开分秒帧窗口", seg, "审核中缺分秒帧入口")
        self.assertIn("修改分秒帧链接", seg, "审核中缺改链接入口")
        self.assertIn("审", seg, "未按状态判断")

    def test_dept2_excluded(self):
        """二部项目不显示分秒帧动作。"""
        src = read("static/js/status-menu.js")
        self.assertIn("isDept2", src)
        self.assertIn("fmDeptExcluded", src, "未复用部门排除规则")

    def test_closes_on_escape_and_outside_click(self):
        src = read("static/js/status-menu.js")
        self.assertIn("Escape", src, "缺 Esc 关闭")
        self.assertIn("addEventListener('click'", src, "缺点外部关闭")

    def test_viewport_bounds(self):
        """菜单不能跑到屏幕外。"""
        src = read("static/js/status-menu.js")
        seg = src[src.find("function position"):][:700]
        self.assertIn("innerWidth", seg)
        self.assertIn("innerHeight", seg)


class ClipboardEndpointTests(unittest.TestCase):
    def test_route_exists(self):
        src = read("main_desktop.py")
        self.assertIn("/api/_self/clipboard", src, "缺少通用剪贴板接口")

    def test_local_only(self):
        """服务监听 0.0.0.0，剪贴板接口必须限本机，防局域网写入。"""
        src = read("main_desktop.py")
        i = src.find("def _api_self_clipboard")
        seg = src[i:i + 900]
        self.assertIn("remote_addr", seg, "未校验来源")
        self.assertIn("127.0.0.1", seg)
        self.assertIn("403", seg)


if __name__ == "__main__":
    unittest.main()