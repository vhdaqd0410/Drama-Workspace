# -*- coding: utf-8 -*-
"""融合功能回归测试：交付联动、全局待办、交付日期同步。"""
import os
import sys
import pytest

# ============================================================
# 1. 交付日期联动：置为已交付时自动补记 delivered_date
# ============================================================

class TestDeliveredDateLinkage:
    def test_delivered_auto_sets_date(self, tmp_db):
        tmp_db.upsert_project("联动A", "", "")
        tmp_db.update_project_status("联动A", delivery_status="delivered",
                                     last_delivered_at="2026-08-20 10:00:00")
        p = tmp_db.get_project("联动A")
        assert p["delivered_date"] == "2026-08-20"

    def test_delivered_uses_today_if_no_timestamp(self, tmp_db):
        tmp_db.upsert_project("联动B", "", "")
        tmp_db.update_project_status("联动B", delivery_status="delivered")
        p = tmp_db.get_project("联动B")
        # 无时间戳时用当天日期（YYYY-MM-DD 格式）
        assert p["delivered_date"] and len(p["delivered_date"]) == 10

    def test_keeps_existing_delivered_date(self, tmp_db):
        tmp_db.upsert_project("联动C", "", "")
        tmp_db.update_project_status("联动C", delivered_date="2026-08-01")
        tmp_db.update_project_status("联动C", delivery_status="delivered",
                                     last_delivered_at="2026-08-20 10:00:00")
        p = tmp_db.get_project("联动C")
        assert p["delivered_date"] == "2026-08-01"  # 已有日期不被覆盖

    def test_not_delivered_no_auto(self, tmp_db):
        tmp_db.upsert_project("联动D", "", "")
        tmp_db.update_project_status("联动D", delivery_status="pending")
        p = tmp_db.get_project("联动D")
        assert not (p.get("delivered_date") or "")


# ============================================================
# 2. 全局待办（get_all_todos）
# ============================================================

class TestGlobalTodos:
    def test_get_all_todos(self, tmp_db):
        tmp_db.upsert_project("待办项目A", "", "")
        tmp_db.upsert_project("待办项目B", "", "")
        tmp_db.add_project_todo("待办项目A", "完成第一集", priority=1)
        tmp_db.add_project_todo("待办项目A", "完成第二集", priority=0)
        tmp_db.add_project_todo("待办项目B", "校色", priority=0)

        todos = tmp_db.get_all_todos()
        assert len(todos) == 3
        # 未完成优先，priority 高的在前
        assert todos[0]["text"] == "完成第一集"

    def test_include_done_flag(self, tmp_db):
        tmp_db.upsert_project("待办项目C", "", "")
        t = tmp_db.add_project_todo("待办项目C", "已完成的待办", priority=0)
        tmp_db.update_project_todo(t, done=1)
        assert len(tmp_db.get_all_todos(include_done=False)) == 0
        assert len(tmp_db.get_all_todos(include_done=True)) == 1

    def test_keyword_filter(self, tmp_db):
        tmp_db.upsert_project("待办项目D", "", "")
        tmp_db.add_project_todo("待办项目D", "配音检查", priority=0)
        tmp_db.add_project_todo("待办项目D", "字幕导出", priority=0)
        assert len(tmp_db.get_all_todos(keyword="配音")) == 1
        assert len(tmp_db.get_all_todos(keyword="不存在的内容")) == 0


# ============================================================
# 3. 交付日期同步（sync_delivery_dates_from_target 解析）
# ============================================================

class TestSyncDeliveryDates:
    def test_parse_short_and_long(self, tmp_db, tmp_path):
        import openpyxl
        p = str(tmp_path / "target.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.merge_cells("A1:A2")
        ws["A1"] = "同步项目A"
        ws["D1"] = "8.15上午10点交"
        ws.merge_cells("A3:A3")
        ws["A3"] = "同步项目B"
        ws["D3"] = "2026-8-20"
        wb.save(p)

        tmp_db.upsert_project("同步项目A", "", "")
        tmp_db.upsert_project("同步项目B", "", "")
        from features import sync_delivery_dates_from_target
        updated = sync_delivery_dates_from_target(p, tmp_db)
        assert len(updated) == 2
        dates = {u["project"]: u["date"] for u in updated}
        assert dates["同步项目A"] == "2026-08-15"
        assert dates["同步项目B"] == "2026-08-20"
        # 验证已写入
        assert tmp_db.get_project("同步项目A")["delivered_date"] == "2026-08-15"
