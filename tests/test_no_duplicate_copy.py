# -*- coding: utf-8 -*-
"""回归：同步完成后不应再次执行复制。

用户反馈（2026-10-22 起）：同步素材完成后，过一段时间又会执行一次复制任务。

根因（三条）：
  1) _copy_dir 是 COM → VBS → robocopy 三级 fallback，
     COM 报失败时不管实际是否已拷完，直接再跑一遍 VBS/robocopy。
  2) COM 等待循环的完成条件过严（requires stable>=6），
     Shell 刷元数据会让指纹一直变 → 判超时失败 → 触发重拷。
  3) sync_project 没有防重，重复点同步/前端重试会并发对同一目标拷贝。
"""
import io
import os
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with io.open(os.path.join(BASE, rel), encoding="utf-8") as f:
        return f.read()


class AlreadyCompleteGuardTests(unittest.TestCase):
    def test_helper_exists(self):
        src = read("backend/sync.py")
        self.assertIn("def _dst_already_complete", src,
                      "缺少「目标是否已完整」的判断")

    def test_copy_dir_checks_before_fallback(self):
        """每级 fallback 前都要先校验是否已拷完。"""
        src = read("backend/sync.py")
        i = src.find("def _copy_dir")
        self.assertGreater(i, 0)
        seg = src[i:i + 3000]
        # 入口预检 + COM 后 + VBS 后，至少 3 处
        n = seg.count("_dst_already_complete")
        self.assertGreaterEqual(n, 3,
                                "fallback 链路缺少已完整校验（实际 %d 处）" % n)
        self.assertIn("无需复制", seg)

    def test_helper_checks_file_sizes(self):
        """不能只看名字，文件大小也要对得上（否则半截文件会被误判完成）。"""
        src = read("backend/sync.py")
        i = src.find("def _dst_already_complete")
        seg = src[i:i + 1200]
        self.assertIn("getsize", seg, "未比对文件大小")


class ComWaitConditionTests(unittest.TestCase):
    def test_stable_threshold_not_too_strict(self):
        """完成阈值不能过硬，否则元数据刷写会导致误判超时→重拷。"""
        src = read("backend/sync.py")
        seg = src[src.find("def _copy_desktop_com"):][:3400]
        self.assertIn("stable >= 3", seg, "完成阈值应放宽到连续 3 轮")
        self.assertNotIn("stable >= 6", seg, "旧的严格阈值仍在（易误判失败）")

    def test_metadata_flapping_tolerated(self):
        """顶层已齐但指纹持续变化时，应容忍并判完成。"""
        src = read("backend/sync.py")
        seg = src[src.find("def _copy_desktop_com"):][:3600]
        self.assertIn("last_change", seg)
        self.assertRegex(seg, r"ready\s+and\s+\(time\.time\(\)\s*-\s*last_change\)\s*>\s*30",
                         "缺少「顶层齐后容忍元数据抖动」的分支")


class SyncDedupTests(unittest.TestCase):
    def test_concurrent_sync_is_deduped(self):
        """同一项目并发同步应被去重，避免对同一目标重复拷贝。"""
        src = read("backend/sync.py")
        i = src.find("def sync_project")
        self.assertGreater(i, 0)
        seg = src[i:i + 1800]
        self.assertIn("_sync_heartbeat", seg, "未用心跳做并发去重")
        self.assertIn("同步已在进行中", seg, "缺少去重提示")


if __name__ == "__main__":
    unittest.main()
