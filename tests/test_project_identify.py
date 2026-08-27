# -*- coding: utf-8 -*-
"""项目识别修复测试：H0189-11587《剧名》类命名、国内/海外不误伤。"""
import os
import sys
import pytest

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)
import scan as scan_mod
from scan import _looks_like_project, _PROJECT_NUM_RE, _CATEGORY_WORDS


class TestProjectIdentification:
    def _dir(self, tmp_path, name, subdirs=()):
        d = os.path.join(str(tmp_path), name)
        os.makedirs(d, exist_ok=True)
        for s in subdirs:
            os.makedirs(os.path.join(d, s), exist_ok=True)
        return d

    def test_recognize_H_style_name(self, tmp_path):
        """H0189-11587《剧名》类命名应识别为项目。"""
        d = self._dir(tmp_path, "H0189-11587《我落泪情绪零碎》", ["03 视频素材"])
        assert _looks_like_project(d, os.path.basename(d)) is True

    def test_recognize_H_double_number(self, tmp_path):
        d = self._dir(tmp_path, "H0174-10940《风御万界》")
        assert _looks_like_project(d, os.path.basename(d)) is True

    def test_recognize_with_guonei(self, tmp_path):
        """项目名含"国内/海外"（如《...国内版》）不应被误判为分类目录。"""
        d = self._dir(tmp_path, "H0188-11117《某剧》（国内版）")
        assert _looks_like_project(d, os.path.basename(d)) is True

    def test_recognize_with_haiwai(self, tmp_path):
        d = self._dir(tmp_path, "H0128-9680《某剧》（海外版）")
        assert _looks_like_project(d, os.path.basename(d)) is True

    def test_category_words_no_guonei(self):
        """分类词不应包含"国内/海外"（会误伤项目名）。"""
        assert "国内" not in _CATEGORY_WORDS
        assert "海外" not in _CATEGORY_WORDS

    def test_category_still_skipped(self, tmp_path):
        """真正的分类词（模板/存档）仍应跳过。"""
        d = self._dir(tmp_path, "2024模板")
        assert _looks_like_project(d, os.path.basename(d)) is False
        d2 = self._dir(tmp_path, "旧存档")
        assert _looks_like_project(d2, os.path.basename(d2)) is False
