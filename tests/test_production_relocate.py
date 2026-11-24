# -*- coding: utf-8 -*-
"""回归：项目在制作部换位置后的「重新定位」能力。

用户需求（2026-11）：
  1. 项目在制作部的位置变了（未交付），要能改 production_path，方便后续交付/同步
  2. 要有手动设置保底
  3. 点「制作部」发现路径不存在时，自动检索新位置
"""
import io
import os
import shutil
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "backend"))


def read(rel):
    with io.open(os.path.join(BASE, rel), encoding="utf-8") as f:
        return f.read()


class LocateApiTests(unittest.TestCase):
    def test_locate_endpoint_exists(self):
        src = read("backend/app.py")
        self.assertIn("/locate_production", src, "缺少「查找新位置」接口")

    def test_relocate_endpoint_exists(self):
        src = read("backend/app.py")
        self.assertIn("/relocate", src, "缺少「重新定位」接口")

    def test_relocate_validates_path_exists(self):
        """新路径不存在必须拒绝，否则交付会指向空目录。"""
        src = read("backend/app.py")
        i = src.find("def api_project_relocate")
        self.assertGreater(i, 0)
        seg = src[i:i + 2200]
        self.assertIn("os.path.isdir(new_path)", seg, "未校验新路径存在")
        self.assertIn("新路径不存在", seg)

    def test_relocate_writes_audit(self):
        src = read("backend/app.py")
        seg = src[src.find("def api_project_relocate"):][:2600]
        self.assertIn("重新定位制作部路径", seg, "未写审计日志")

    def test_relocate_infers_source_root(self):
        """要从新路径反推 source_root（否则部门/统计会错）。"""
        src = read("backend/app.py")
        seg = src[src.find("def api_project_relocate"):][:2600]
        self.assertIn("matched_root", seg)
        self.assertIn("extract_department", seg)

    def test_db_has_whitelisted_path_update(self):
        src = read("backend/db.py")
        self.assertIn("def update_project_paths", src,
                      "缺少白名单字段的路径更新方法")
        seg = src[src.find("def update_project_paths"):][:900]
        for f in ("production_path", "source_root", "department"):
            self.assertIn(f, seg)


class AutoRelocateOnOpenTests(unittest.TestCase):
    def test_open_prod_auto_locates(self):
        """打开制作部时路径失效 → 自动检索新位置。"""
        src = read("backend/app.py")
        i = src.find('which == "group" or which == "prod"')
        self.assertGreater(i, 0)
        seg = src[i:i + 3000]
        self.assertIn("_locate_production_dir", seg, "未自动检索新位置")

    def test_returns_need_relocate_flag(self):
        """找不到或有多候选时，要返回 need_relocate 让前端介入。"""
        src = read("backend/app.py")
        self.assertIn("need_relocate", src, "未返回重定位提示标记")

    def test_frontend_handles_need_relocate(self):
        src = read("static/js/episode.js")
        self.assertIn("need_relocate", src, "前端未处理重定位提示")
        self.assertIn("locateAndRelocate", src, "缺少自动重定位流程")

    def test_frontend_has_manual_entry(self):
        """要有手动重定位入口（保底）。"""
        core = read("static/js/core.js")
        self.assertIn("relocateProduction", core, "卡片缺少「重新定位」按钮")
        ep = read("static/js/episode.js")
        self.assertIn("async function relocateProduction", ep, "缺少重定位实现")

    def test_doRelocate_retries_open(self):
        """重定位成功后应可重试打开目录。"""
        src = read("static/js/episode.js")
        i = src.find("async function doRelocate")
        seg = src[i:i + 1600]
        self.assertIn("autoOpen", seg, "未支持重定位后重试打开")


if __name__ == "__main__":
    unittest.main()