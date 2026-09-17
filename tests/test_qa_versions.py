# -*- coding: utf-8 -*-
"""质检版本识别回归测试：无码版应与成片同类（期望有硬字幕）。

背景：交付新增"无码版本"，需纳入硬字幕检测，判定规则与成片一致。
实际目录命名：00成片 / 01无码版 / 01成片-无码版，与"有音乐无字幕版本"等同级。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend'))


def _mk_version_dirs(base, folders):
    """在 base 下创建各版本目录，每个放 2 个假 mp4。"""
    for name in folders:
        d = os.path.join(base, name)
        os.makedirs(d, exist_ok=True)
        for i in (1, 2):
            open(os.path.join(d, f"{i}.mp4"), "w").close()


class TestQAVersionLayout:
    def test_wuma_goes_to_cp_like(self, tmp_path):
        """00成片 + 01无码版 + 有音乐无字幕版本。"""
        import qa_toolkits
        base = str(tmp_path / "p1")
        os.makedirs(base, exist_ok=True)
        _mk_version_dirs(base, ["00成片", "01无码版", "1.有音乐无字幕版本"])

        r = qa_toolkits.auto_detect_folders(base)
        assert r["cp_folder"] == "00成片"
        assert "01无码版" in r["cp_like_folders"]
        assert "00成片" in r["cp_like_folders"]
        # 无码版不应被当成"无字幕版"
        assert "01无码版" not in r["hardsub_folders"]
        assert "1.有音乐无字幕版本" in r["hardsub_folders"]
        # 默认勾选含无码版
        assert r["hardsub_vars_default"].get("01无码版") is True

    def test_wuma_named_with_chengpian_prefix(self, tmp_path):
        """01成片-无码版：含"成片"但是无码版，不能覆盖真正的成片。"""
        import qa_toolkits
        base = str(tmp_path / "p2")
        os.makedirs(base, exist_ok=True)
        _mk_version_dirs(base, ["00成片", "01成片-无码版", "2.无音乐无字幕无bgm"])

        r = qa_toolkits.auto_detect_folders(base)
        assert r["cp_folder"] == "00成片", "真正的成片应是 00成片"
        assert "01成片-无码版" in r["cp_like_folders"]
        assert "01成片-无码版" not in r["hardsub_folders"]

    def test_engine_layout_wuma_cp_like(self, tmp_path):
        """qa_engine._detect_folder_layout 同样识别无码版为成片性质。"""
        from qa_engine import QAEngine
        base = str(tmp_path / "p3")
        os.makedirs(base, exist_ok=True)
        _mk_version_dirs(base, ["00成片", "01无码版", "1.有音乐无字幕版本"])

        layout = QAEngine._detect_folder_layout(base)
        assert layout["cp_folder"] == "00成片"
        assert "01无码版" in layout["cp_like_folders"]
        assert "01无码版" not in layout["hardsub_folders"]

    def test_cp_like_included_in_all_video_folders(self, tmp_path):
        """无码版必须进入待检版本列表（否则不会被检测）。"""
        import detection
        base = str(tmp_path / "p4")
        os.makedirs(base, exist_ok=True)
        _mk_version_dirs(base, ["00成片", "01无码版", "1.有音乐无字幕版本"])
        # 模拟 run_detection_batch 的版本归集逻辑
        cp_folder = "00成片"
        opts_cp_like = ["00成片", "01无码版"]
        opts_hardsub = ["00成片", "01无码版", "1.有音乐无字幕版本"]
        cp_like = [cp_folder]
        for f in opts_cp_like:
            if f and f not in cp_like:
                cp_like.append(f)
        hardsub_only = [f for f in opts_hardsub if f and f not in cp_like]
        all_video_folders = list(cp_like)
        for f in hardsub_only:
            if f not in all_video_folders:
                all_video_folders.append(f)
        assert "01无码版" in all_video_folders
        assert "1.有音乐无字幕版本" in all_video_folders
        assert "01无码版" in cp_like
        assert "01无码版" not in hardsub_only
