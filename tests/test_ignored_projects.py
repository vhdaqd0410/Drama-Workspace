# -*- coding: utf-8 -*-
"""回归：删除项目时 NAS 没删成，不应该把项目永久拉黑。

用户反馈（2026-10-22）：
  组内 NAS 上明明有 O:\\AI漫剧剪辑一组\\779-12403-... 这个项目，
  刷新工作台多少次都出不来。
根因：
  18:51 执行过「彻底删除(含NAS文件夹)」，但 NAS 文件夹因权限/占用没删掉，
  代码仍然把项目写进 ignored_projects 忽略清单。
  get_projects_enriched 遇到忽略清单直接 continue，
  于是「目录还在、却永远扫不出来」。
"""
import io
import os
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with io.open(os.path.join(BASE, rel), encoding="utf-8") as f:
        return f.read()


class DeleteIgnoreGuardTests(unittest.TestCase):
    def test_hard_delete_failure_skips_ignore(self):
        """彻底删除但 NAS 没删成时，不能加忽略清单。"""
        src = read("backend/enhanced_routes.py")
        i = src.find("def api_project_delete")
        self.assertGreater(i, 0)
        seg = src[i:i + 4000]
        self.assertIn("deleted_nas", seg, "未记录 NAS 是否删除成功")
        # 关键分支：hard + 没删成 → 不加 ignore
        self.assertRegex(
            seg,
            r'if\s+mode\s*==\s*["\']hard["\']\s+and\s+not\s+deleted_nas',
            "缺少「彻底删除但 NAS 未清理」的保护分支")
        self.assertIn("remove_ignored_project", seg,
                      "未回滚忽略标记")

    def test_soft_delete_still_ignores(self):
        """软删除仍应正常加入忽略清单（保留 NAS 文件夹）。"""
        src = read("backend/enhanced_routes.py")
        seg = src[src.find("def api_project_delete"):][:4000]
        self.assertIn("add_ignored_project", seg)


class UnignoreApiTests(unittest.TestCase):
    def test_unignore_endpoint_exists(self):
        src = read("backend/enhanced_routes.py")
        self.assertIn("/unignore", src, "缺少解除忽略的接口")

    def test_unignore_invalidates_cache(self):
        src = read("backend/enhanced_routes.py")
        i = src.find("def api_project_unignore")
        self.assertGreater(i, 0)
        seg = src[i:i + 1200]
        self.assertIn("invalidate_projects_cache", seg,
                      "解除忽略后未让列表缓存失效，刷新也看不到")

    def test_ignored_list_endpoint(self):
        src = read("backend/enhanced_routes.py")
        self.assertIn("/api/ignored_projects", src,
                      "缺少忽略清单查询接口（用户无法自查）")

    def test_ignored_list_reports_nas_existence(self):
        """清单要标注项目是否还在 NAS 上，便于识别「误拉黑」。"""
        src = read("backend/enhanced_routes.py")
        i = src.find("def api_ignored_projects")
        self.assertGreater(i, 0)
        seg = src[i:i + 1200]
        self.assertIn("on_nas", seg, "未返回 on_nas 字段")


if __name__ == "__main__":
    unittest.main()
