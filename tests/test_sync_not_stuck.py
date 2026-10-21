# -*- coding: utf-8 -*-
"""回归：同步不会永久卡在 syncing + 完成后必定跳转分集。

用户反馈的现象：
  1. 同步素材完很久不跳分集
  2. H0262/H0286 已同步/已分集，界面仍显示“同步中 / 正在同步项目目录”
根因：
  a) sync_project 没有异常兜底，异常后 sync_status 永久停在 syncing
  b) 工作台重启后遗留的 syncing 无人回收
  c) 前端轮询只认列表里的 target，找不到就永远不跳转
"""
import io
import os
import re
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with io.open(os.path.join(BASE, rel), encoding="utf-8") as f:
        return f.read()


class SyncNeverStuckTests(unittest.TestCase):
    def test_sync_project_has_exception_guard(self):
        """sync_project 必须有异常兜底，失败时把状态从 syncing 收回。"""
        src = read("backend/sync.py")
        i = src.find("def sync_project")
        self.assertGreater(i, 0)
        seg = src[i:i + 2000]
        self.assertIn("except Exception", seg, "sync_project 缺少异常兜底")
        self.assertIn('sync_status="pending"', seg,
                      "异常时未把 sync_status 收回 pending")

    def test_recover_stuck_sync_exists(self):
        """必须提供启动时回收 syncing 的能力。"""
        src = read("backend/sync.py")
        self.assertIn("def recover_stuck_sync", src)
        seg = src[src.find("def recover_stuck_sync"):]
        seg = seg[:1500]
        self.assertIn('"syncing"', seg)
        self.assertIn('sync_status="pending"', seg)

    def test_app_calls_recover_on_startup(self):
        src = read("backend/app.py")
        self.assertIn("recover_stuck_sync()", src,
                      "启动流程未调用 recover_stuck_sync")

    def test_sync_status_endpoint_exists(self):
        """前端需要单项目状态查询，避免列表口径变化导致永远等。"""
        src = read("backend/app.py")
        self.assertIn("/api/sync_status/", src)


class FenjiJumpTests(unittest.TestCase):
    def test_poll_uses_api_status_fallback(self):
        """前端轮询在列表找不到项目时，应回退查 /api/sync_status。"""
        src = read("static/js/project.js")
        i = src.find("async function syncMaterial")
        self.assertGreater(i, 0)
        seg = src[i:i + 5000]
        self.assertIn("/api/sync_status/", seg,
                      "轮询缺少 /api/sync_status 回退，列表里找不到会永不跳转")
        self.assertIn("openFenjiFor(name)", seg, "完成后未跳转分集")

    def test_poll_includes_completed_bucket(self):
        src = read("static/js/project.js")
        seg = src[src.find("async function syncMaterial"):][:5000]
        self.assertIn("group_completed", seg,
                      "轮询应包含已完成桶")

    def test_poll_stops_on_failure(self):
        """同步失败要立刻停止轮询，不能空等到超时。"""
        src = read("static/js/project.js")
        seg = src[src.find("async function syncMaterial"):][:5000]
        self.assertIn("失败", seg)

    def test_sync_polling_lock_expires(self):
        """防重锁必须能过期，否则一次异常会让按钮永久不可用。"""
        src = read("static/js/project.js")
        self.assertIn("_syncPollingAt", src)
        seg = src[src.find("async function syncMaterial"):][:2000]
        self.assertIn("360000", seg, "缺少锁超时")

    def test_sync_material_not_corrupted(self):
        """syncMaterial 曾被编辑破坏，锁住关键结构。"""
        src = read("static/js/project.js")
        i = src.find("async function syncMaterial")
        seg = src[i:i + 3000]
        self.assertEqual(seg.count("`") % 2, 0, "反引号未配对（模板串被切断）")
        self.assertIn("const check = await api('POST'", seg)
        self.assertNotIn("`/api/p`", seg, "存在损坏碎片")


if __name__ == "__main__":
    unittest.main()
