# -*- coding: utf-8 -*-
"""回归：提成表以工作台 DB 分集为准（不再读旧项目文件）。

用户反馈（2026-10-31）：
  1. 刘梦真 10 月实际 204 集，提成表却算 199 集
  2. 11885 项目 66-70 工作台已分给刘梦真，提成表却算给已离职的翟慧莲
根因：提成表读「项目文件」（fenji_targets/*.xlsx），而分集写回项目文件可能失败，
      项目文件残留旧分集。工作台 DB 里是对的。
修复：build_report 直接用 DB episode_plan 构造 records，彻底绕过项目文件。
"""
import io
import os
import re
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with io.open(os.path.join(BASE, rel), encoding="utf-8") as f:
        return f.read()


class RecordsFromDbTests(unittest.TestCase):
    def test_records_from_db_exists(self):
        src = read("backend/commission_report.py")
        self.assertIn("def _records_from_db", src,
                      "缺少直接从 DB 构造 records 的函数")

    def test_build_report_uses_db_not_file(self):
        """build_report 应调用 _records_from_db，而不是 parse_projects(df)。"""
        src = read("backend/commission_report.py")
        i = src.find("def build_report")
        seg = src[i:i + 2500]
        self.assertIn("_records_from_db(", seg, "build_report 未改用 DB 数据源")
        # 不应再读项目文件
        self.assertNotIn("gc.parse_projects(df", seg,
                         "仍在使用项目文件解析（旧口径）")
        self.assertNotIn("pd.read_excel(project_file", seg,
                         "仍在读项目文件")

    def test_parse_iso_date(self):
        """DB 日期是 ISO 格式(2026-10-09)，必须能解析。"""
        src = read("backend/commission_report.py")
        self.assertIn("def _parse_db_date", src)
        seg = src[src.find("def _parse_db_date"):][:600]
        self.assertIn("re.match", seg, "未兼容 ISO 日期格式")

    def test_compact_episodes(self):
        src = read("backend/commission_report.py")
        self.assertIn("def _compact_episodes", src)


class PersonCardsMonthFilterTests(unittest.TestCase):
    def test_compute_person_cards_accepts_month(self):
        src = read("backend/commission_service.py")
        i = src.find("def compute_person_cards")
        seg = src[i:i + 400]
        self.assertIn("month=None", seg, "compute_person_cards 未支持 month 参数")

    def test_person_cards_filters_by_month(self):
        src = read("backend/commission_service.py")
        seg = src[src.find("def compute_person_cards"):][:1500]
        self.assertIn("if month and pm != month", seg,
                      "未按 month 过滤项目")

    def test_api_accepts_month(self):
        src = read("backend/commission.py")
        i = src.find("def commission_person_cards")
        seg = src[i:i + 700]
        self.assertIn('request.args.get("month"', seg, "接口未接收 month")

    def test_frontend_passes_report_month(self):
        """前端个人卡片应跟随 reportMonth 选择。"""
        src = read("static/js/tabs.js")
        i = src.find("async function _loadPersonCards")
        seg = src[i:i + 1200]
        self.assertIn("reportMonth", seg, "前端未读取选中的月份")
        self.assertIn("month=", seg, "前端未把月份传给接口")


if __name__ == "__main__":
    unittest.main()
