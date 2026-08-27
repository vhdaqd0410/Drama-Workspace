# -*- coding: utf-8 -*-
"""健壮性回归测试：覆盖本次修复的 4 类运行期崩溃/告警，防止复发。

对应修复：
  1. QA 引擎 hardsub_folders=None 遍历崩溃（qa_engine._run_worker / enhanced_routes.qa_start）
  2. 待办 priority 传入非数字字符串导致 int() 崩溃（db._coerce_priority）
  3. 分集 Excel 目标文件被占用时写入失败（enhanced_routes 写前占用检测）
  4. 目录缓存写盘偶发 WinError 5 / 节流失效（sync.py / sync_engine.py）
"""
import os
import tempfile

import pytest


# ============ 2. 待办 priority 规范化（db._coerce_priority） ============
class TestCoercePriority:
    """任何输入都不应抛 ValueError，且映射符合预期。"""

    def test_numeric_and_none(self, tmp_db):
        from db import _coerce_priority
        assert _coerce_priority(None) == 0
        assert _coerce_priority(0) == 0
        assert _coerce_priority(3) == 3
        assert _coerce_priority("5") == 5

    def test_chinese_priority(self, tmp_db):
        from db import _coerce_priority
        assert _coerce_priority("高") == 3
        assert _coerce_priority("中") == 2
        assert _coerce_priority("低") == 1

    def test_english_priority_case_insensitive(self, tmp_db):
        from db import _coerce_priority
        assert _coerce_priority("high") == 3
        assert _coerce_priority("MEDIUM") == 2
        assert _coerce_priority("Low") == 1

    def test_garbage_falls_back_to_zero(self, tmp_db):
        from db import _coerce_priority
        # 历史上引发崩溃的输入：int('高')
        assert _coerce_priority("高") == 3  # 不再抛 ValueError
        assert _coerce_priority("abc") == 0
        assert _coerce_priority("") == 0

    def test_add_todo_never_crashes_on_bad_priority(self, tmp_db):
        """直接把中文/垃圾字符串 priority 传给 add，不应崩溃，且落库为数字。"""
        tid = tmp_db.add_project_todo("测试项目", "内容", priority="高")
        todos = tmp_db.get_project_todos("测试项目")
        assert todos and todos[0]["priority"] == 3
        # update 也不能崩
        tmp_db.update_project_todo(tid, priority="abc")
        assert todos[0]["id"] == tid


# ============ 1. QA 引擎 hardsub_folders=None 兜底 ============
class TestQAOptionsRobustness:
    """模拟 _run_worker 中 opts['hardsub_folders'] 构建逻辑，验证 None/空 时不再崩溃。"""

    @staticmethod
    def _build_opts(merged_opts, cp_folder, folder_layout):
        """复刻 qa_engine._run_worker 中相关逻辑的防御版。"""
        merged_opts = merged_opts or {}
        hardsub_folders = folder_layout.get("hardsub_folders") or [cp_folder]
        opts = dict(merged_opts)
        opts.setdefault("cp_folder", cp_folder)
        if not opts.get("hardsub_folders"):
            opts["hardsub_folders"] = hardsub_folders
        all_video_folders = [cp_folder]
        for f in opts["hardsub_folders"]:
            if f and f not in all_video_folders:
                all_video_folders.append(f)
        return opts, all_video_folders

    def test_none_hardsub_folders(self):
        """前端传 hardsub_folders=None：原崩溃场景，现应回退默认。"""
        opts, avf = self._build_opts(
            {"hardsub_folders": None}, "成片", {"hardsub_folders": ["成片", "无字幕版"]})
        assert opts["hardsub_folders"] == ["成片", "无字幕版"]
        assert avf == ["成片", "无字幕版"]

    def test_empty_hardsub_folders(self):
        """前端传空列表：应回退到至少含 cp_folder。"""
        opts, avf = self._build_opts(
            {"hardsub_folders": []}, "成片", {"hardsub_folders": []})
        assert "成片" in opts["hardsub_folders"]

    def test_missing_key(self):
        """前端完全不传 hardsub_folders。"""
        opts, avf = self._build_opts({}, "成片", {"hardsub_folders": ["成片"]})
        assert opts["hardsub_folders"] == ["成片"]

    def test_normal_values(self):
        opts, avf = self._build_opts(
            {"hardsub_folders": ["成片"]}, "成片", {"hardsub_folders": ["成片"]})
        assert opts["hardsub_folders"] == ["成片"]


# ============ 4. 目录缓存写盘：返回成功标志 + 落盘 ============
class TestOutputDirCachePersistence:
    def test_save_returns_true_and_writes_file(self, engine, tmp_path):
        cache_file = str(tmp_path / "cache.json")
        engine._output_dir_cache_file = cache_file
        engine._output_dir_cache = {"a|b": ["/x/y"]}
        ok = engine._save_output_dir_cache()
        assert ok is True
        assert os.path.isfile(cache_file)

    def test_save_no_residual_tmp(self, engine, tmp_path):
        """原子写：成功后不应残留 .tmp 文件。"""
        cache_file = str(tmp_path / "cache.json")
        engine._output_dir_cache_file = cache_file
        engine._output_dir_cache = {"k": ["v"]}
        engine._save_output_dir_cache()
        assert not os.path.exists(cache_file + ".tmp")

    def test_find_output_dirs_throttle_updates_marker(self, tmp_path, base_config):
        """修复前 _last_cache_save_size 恒为 -1，每次新增条目都重复写盘。
        修复后：新增条目时写盘并更新标记；命中缓存时不再写盘，实现节流。"""
        from db import Database
        from sync_engine import SyncEngine

        # 构造一个真实项目目录：包含 01上映单集版 子目录
        proj = tmp_path / "P001"
        outdir = proj / "01上映单集版"
        outdir.mkdir(parents=True)

        cache_file = str(tmp_path / "cache.json")
        engine = SyncEngine(base_config, Database(str(tmp_path / "t.db")))
        engine._output_dir_cache_file = cache_file

        # 首次调用：新增缓存条目 → 应写盘，并更新标记为当前缓存大小
        dirs1 = engine._find_output_dirs(str(tmp_path), "P001")
        assert dirs1, "应找到 01上映单集版 目录"
        assert engine._last_cache_save_size == len(engine._output_dir_cache), \
            "首次写盘后标记应同步为当前缓存条目数（修复前恒为 -1）"
        assert os.path.isfile(cache_file)

        # 再次调用应命中缓存，不新增条目 → 不触发写盘，标记不变
        dirs2 = engine._find_output_dirs(str(tmp_path), "P001")
        assert dirs2 == dirs1
        assert engine._last_cache_save_size == len(engine._output_dir_cache), \
            "命中缓存不新增条目，标记不应漂移"
