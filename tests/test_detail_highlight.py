# -*- coding: utf-8 -*-
"""回归：完成明细逗号分隔 + 卡前标黄改为开关。

用户反馈（2026-10-31）：
  1. 完成明细格式变了，应保持原来的「每集逗号分隔」（如 31,32,33...），
     而不是区间合并（31-37）。
  2. 卡前规则变动才标黄，本月没变动就不标。
"""
import io
import os
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with io.open(os.path.join(BASE, rel), encoding="utf-8") as f:
        return f.read()


class DetailFormatTests(unittest.TestCase):
    def test_detail_uses_comma_separated_episodes(self):
        """完成明细必须逐集逗号分隔，不能区间合并。"""
        src = read("backend/commission_report.py")
        i = src.find("def _records_from_db")
        seg = src[i:i + 3000]
        self.assertIn('",".join(str(e) for e in eps)', seg,
                      "完成明细未使用逐集逗号分隔")

    def test_no_compact_episodes_in_detail(self):
        src = read("backend/commission_report.py")
        i = src.find("def _records_from_db")
        seg = src[i:i + 3000]
        self.assertNotIn("_compact_episodes(eps)", seg,
                         "完成明细仍在使用区间合并")


class HighlightSwitchTests(unittest.TestCase):
    def test_build_report_has_highlight_param(self):
        src = read("backend/commission_report.py")
        i = src.find("def build_report")
        seg = src[i:i + 400]
        self.assertIn("highlight_card_rule=False", seg,
                      "build_report 缺少 highlight_card_rule 参数（默认应 False）")

    def test_highlight_is_conditional(self):
        """标黄必须是开关，不能写死。"""
        src = read("backend/commission_report.py")
        i = src.find("highlight_roles")
        seg = src[i - 50:i + 150]
        self.assertIn("if highlight_card_rule else []", seg,
                      "标黄未做成条件开关")

    def test_api_accepts_highlight(self):
        src = read("backend/commission.py")
        i = src.find("def commission_report")
        seg = src[i:i + 800]
        self.assertIn("highlight_card_rule", seg, "接口未接收标黄开关")

    def test_frontend_has_checkbox(self):
        src = read("static/js/tabs.js")
        self.assertIn("chkCardRuleChanged", src, "前端缺少标黄复选框")
        i = src.find("function exportCommissionReport")
        seg = src[i:i + 600]
        self.assertIn("highlight_card_rule", seg, "前端未把开关传给接口")


if __name__ == "__main__":
    unittest.main()
