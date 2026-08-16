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


# ============================================================
# 4. 分集工作量同步（sync_episode_plan_from_target）
# ============================================================

class TestEpisodePlanSync:
    def test_sync_rebuilds_plan(self, tmp_db, tmp_path):
        import openpyxl
        p = str(tmp_path / "master.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["项目X", None, None, None])
        ws.append([None, None, "张三：1-3", None])
        ws.append([None, None, "李四：4-6", None])
        ws.append(["项目Y", None, None, None])
        ws.append([None, None, "张三：1-2，5", None])
        wb.save(p)

        tmp_db.upsert_project("项目X", "", "")
        tmp_db.upsert_project("项目Y", "", "")
        from features import sync_episode_plan_from_target
        res = sync_episode_plan_from_target(p, tmp_db, clear_stale=False)
        assert res["total_projects"] == 2
        assert res["total_episodes"] == 9   # 项目X 6集 + 项目Y 3集
        px = tmp_db.get_episode_plan("项目X")
        assert px["1"] == "张三" and px["6"] == "李四"
        py = tmp_db.get_episode_plan("项目Y")
        assert py["5"] == "张三"

    def test_clear_stale(self, tmp_db, tmp_path):
        import openpyxl
        p = str(tmp_path / "m.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["项目A", None, None, None])
        ws.append([None, None, "张三：1-2", None])
        wb.save(p)
        tmp_db.upsert_project("项目A", "", "")
        tmp_db.upsert_project("项目B", "", "")   # 不在目标文件
        tmp_db.set_episode_plan("项目B", {"1": "假人", "2": "假人"})
        from features import sync_episode_plan_from_target
        res = sync_episode_plan_from_target(p, tmp_db, clear_stale=True)
        assert "项目B" in res["cleared"]
        assert tmp_db.get_episode_plan("项目B") == {}


# ============================================================
# 5. 统一剪辑师工作量口径（aggregate_editor_workload）
# ============================================================

class TestAggregateEditorWorkload:
    def test_aggregate_all(self, tmp_db):
        tmp_db.upsert_project("P1", "", "")
        tmp_db.upsert_project("P2", "", "")
        tmp_db.set_episode_plan("P1", {"1": "张三", "2": "张三", "3": "李四"})
        tmp_db.set_episode_plan("P2", {"1": "李四"})
        from features import aggregate_editor_workload
        wl = aggregate_editor_workload(tmp_db)
        by_name = {e["name"]: e["assigned"] for e in wl}
        assert by_name["张三"] == 2 and by_name["李四"] == 2
        assert len(wl) == 2

    def test_aggregate_by_month(self, tmp_db):
        tmp_db.upsert_project("P3", "", "")
        tmp_db.upsert_project("P4", "", "")
        tmp_db.update_project_status("P3", project_month="2026-08")
        tmp_db.update_project_status("P4", project_month="2026-07")
        tmp_db.set_episode_plan("P3", {"1": "张三"})
        tmp_db.set_episode_plan("P4", {"2": "李四"})
        from features import aggregate_editor_workload
        wl = aggregate_editor_workload(tmp_db, month="2026-08")
        by_name = {e["name"]: e["assigned"] for e in wl}
        assert by_name.get("张三") == 1
        assert "李四" not in by_name

