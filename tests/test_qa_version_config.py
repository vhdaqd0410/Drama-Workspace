# -*- coding: utf-8 -*-
"""回归：质检版本可自由增删 + 逐版本可配质检标准（不写死版本名）。

用户需求（2026-11）：
  1. 交付多了「3.无音乐有字幕」这个版本，要能参与检测
  2. 各版本是否参与检测要可控，能新增其他版本
  3. 质检标准主要区分「有无硬字幕」，其它检查项各版本一致
  4. 不要写死版本名（后续可能去掉某版本、新增别的）
"""
import io
import os
import tempfile
import shutil
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "backend"))


def read(rel):
    with io.open(os.path.join(BASE, rel), encoding="utf-8") as f:
        return f.read()


def _mk(tmp, folders):
    for f in folders:
        d = os.path.join(tmp, f)
        os.makedirs(d)
        if "字幕文件" in f:
            open(os.path.join(d, "01.srt"), "w").write("1")
        else:
            open(os.path.join(d, "01.mp4"), "wb").write(b"x" * 100)


class VersionDiscoveryTests(unittest.TestCase):
    def setUp(self):
        import qa_toolkits
        self.qt = qa_toolkits

    def test_digit_prefix_not_treated_as_subtitle_folder(self):
        """以 3 开头的视频版本不能因为前缀被当成字幕目录。"""
        tmp = tempfile.mkdtemp()
        try:
            _mk(tmp, ["0成片", "1无字幕版", "3.无音乐有字幕", "4字幕文件"])
            r = self.qt.auto_detect_folders(tmp)
            self.assertIn("3.无音乐有字幕", r.get("all_video_folders") or [],
                          "3 开头的视频版本被误判为字幕目录")
            self.assertEqual(r.get("srt_folder"), "4字幕文件")
        finally:
            shutil.rmtree(tmp)

    def test_more_versions_are_discovered(self):
        """目录里出现新版本时，应自动纳入（不依赖写死的名字）。"""
        tmp = tempfile.mkdtemp()
        try:
            _mk(tmp, ["0成片", "1无字幕版", "2无音乐无字幕版", "3.无音乐有字幕", "4字幕文件"])
            r = self.qt.auto_detect_folders(tmp)
            names = r.get("all_video_folders") or []
            for expect in ("0成片", "1无字幕版", "2无音乐无字幕版", "3.无音乐有字幕"):
                self.assertIn(expect, names, "未发现版本 %s" % expect)
        finally:
            shutil.rmtree(tmp)

    def test_version_rules_default_emitted(self):
        """必须输出可编辑的默认质检标准（cp / nohardsub）。"""
        tmp = tempfile.mkdtemp()
        try:
            _mk(tmp, ["0成片", "1无字幕版"])
            r = self.qt.auto_detect_folders(tmp)
            rules = r.get("version_rules_default") or {}
            self.assertEqual(rules.get("0成片"), "cp")
            self.assertEqual(rules.get("1无字幕版"), "nohardsub")
        finally:
            shutil.rmtree(tmp)

    def test_youzimu_not_nozumu(self):
        """「无音乐有字幕」应判为应有硬字幕，不能因含「无字幕」被误判。"""
        tmp = tempfile.mkdtemp()
        try:
            _mk(tmp, ["0成片", "3.无音乐有字幕"])
            r = self.qt.auto_detect_folders(tmp)
            rules = r.get("version_rules_default") or {}
            self.assertEqual(rules.get("3.无音乐有字幕"), "cp",
                             "「无音乐有字幕」被误判为无字幕版本")
        finally:
            shutil.rmtree(tmp)


class SkipHardsubTests(unittest.TestCase):
    def test_skip_hardsub_supported(self):
        src = read("backend/qa_toolkits.py")
        self.assertIn("skip_hardsub_folders", src,
                      "未支持「该版本不判硬字幕」")

    def test_skip_is_honored_in_issue_scan(self):
        src = read("backend/qa_toolkits.py")
        i = src.find("skip_hs_set")
        self.assertGreater(i, 0)
        seg = src[i:i + 500]
        self.assertIn("continue", seg, "skip 集合未生效")

    def test_engine_passes_skip_list(self):
        src = read("backend/qa_engine.py")
        self.assertIn("skip_hardsub_folders", src, "引擎未传递 skip 清单")

    def test_sanitize_opts_includes_skip(self):
        src = read("backend/qa_toolkits.py")
        i = src.find("def _sanitize_opts")
        seg = src[i:i + 500]
        self.assertIn("skip_hardsub_folders", seg, "checkpoint 一致性未包含 skip")


class FrontendControlTests(unittest.TestCase):
    def test_version_rows_have_rule_select(self):
        src = read("static/js/qa.js")
        self.assertIn("qa2State.versionRules", src, "前端未维护逐版本标准")
        for v in ("'cp'", "'nohardsub'", "'none'"):
            self.assertIn(v, src, "缺少标准选项 %s" % v)

    def test_can_add_and_remove_versions(self):
        src = read("static/js/qa.js")
        self.assertIn("qa2AddVersion", src, "缺少「加入检测」")
        self.assertIn("qa2AddVersionSel", src)

    def test_submit_uses_rules(self):
        src = read("static/js/qa.js")
        i = src.find("async function qa2Start")
        seg = src[i:i + 3500] if i > 0 else src
        self.assertIn("versionRules", seg, "提交检测时未使用逐版本标准")
        self.assertIn("skip_hardsub_folders", seg, "提交时未传 skip 清单")


if __name__ == "__main__":
    unittest.main()
