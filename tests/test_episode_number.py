# -*- coding: utf-8 -*-
"""集号识别（episode_number）单元测试。

从 deliver.DeliverMixin 抽离后，集号识别规则单源在此模块。
这些测试锁定识别口径，防止正则漂移/回归。
"""
import os
import sys
import pytest

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import episode_number


class TestExtractEpisodeNumber:
    def test_ep_prefix(self):
        assert episode_number.extract_episode_number("EP01.mp4") == 1
        assert episode_number.extract_episode_number("EP_12.mp4") == 12
        assert episode_number.extract_episode_number("ep-5.mp4") == 5

    def test_season_episode(self):
        assert episode_number.extract_episode_number("S01E03.mp4") == 3
        assert episode_number.extract_episode_number("s2e15.mp4") == 15

    def test_chinese_episode(self):
        assert episode_number.extract_episode_number("第8集.mp4") == 8
        assert episode_number.extract_episode_number("第100话.mp4") == 100

    def test_bare_number_fallback(self):
        assert episode_number.extract_episode_number("剧集_12.mp4") == 12
        assert episode_number.extract_episode_number("name-7.mp4") == 7
        assert episode_number.extract_episode_number("07.mp4") == 7

    def test_no_match_returns_none(self):
        assert episode_number.extract_episode_number("片段.mp4") is None
        assert episode_number.extract_episode_number("preview.mp4") is None

    def test_out_of_range_ignored(self):
        # 0 和 >999 不算有效集号
        assert episode_number.extract_episode_number("EP0.mp4") is None
        assert episode_number.extract_episode_number("EP1000.mp4") is None

    def test_priority_ep_over_bare_number(self):
        # 同一文件名里既有 EP 又有数字，应优先 EP 前缀
        assert episode_number.extract_episode_number("EP05_第3集.mp4") == 5

    def test_no_extension_processing(self):
        assert episode_number.extract_episode_number("第2集") == 2


class TestEditorForFilename:
    def test_maps_episode_to_editor(self):
        mapping = {"1": "张三", "2": "李四", "3": "张三"}
        assert episode_number.editor_for_filename("第1集.mp4", mapping) == "张三"
        assert episode_number.editor_for_filename("第3集.mp4", mapping) == "张三"

    def test_no_match_returns_empty(self):
        assert episode_number.editor_for_filename("片段.mp4", {"1": "张三"}) == ""

    def test_empty_map_shortcircuits(self):
        # 空映射时不应做任何正则匹配
        assert episode_number.editor_for_filename("EP01.mp4", {}) == ""
        assert episode_number.editor_for_filename("EP01.mp4", None) == ""


class TestDeliverMixinDelegation:
    """确保 DeliverMixin 的方法委托到单源模块，行为一致。"""

    def test_mixin_methods_delegate(self):
        from deliver import DeliverMixin
        m = object.__new__(DeliverMixin)  # 不初始化完整状态，仅调用纯逻辑方法
        assert m._extract_episode_number("EP07.mp4") == 7
        assert m._editor_for_filename("第2集.mp4", {"2": "李四"}) == "李四"

    def test_mixin_uses_single_source_patterns(self):
        from deliver import DeliverMixin
        assert DeliverMixin._EP_PATTERNS is episode_number.EP_PATTERNS
