# -*- coding: utf-8 -*-
"""分集 Excel 双向同步（/api/fenji/sync_from_excel）测试。

覆盖：
  - 首次同步：新增分集
  - 修改：Excel 里改某集剪辑师 → 识别为 modified
  - 删除（apply_removals=true）：Excel 里删掉的行 → 从工作台移除（精确同步）
  - 删除（默认 false）：不删除，向后兼容（追加合并）
"""
import io
import os
import sys
import pytest

from flask import Flask

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


@pytest.fixture()
def app(tmp_db):
    from enhanced_routes import _register_enhanced_routes
    a = Flask(__name__)
    a.config["TESTING"] = True
    _register_enhanced_routes(a, tmp_db)
    return a


@pytest.fixture()
def client(app):
    return app.test_client()


def _make_excel(sheets):
    """sheets: [ [ (项目名, 分集行str 或 None), ... ], ... ] 单工作表。

    生成一个含表头 + 分集行的 xlsx bytes。列：A=项目名, C=剪辑师：范围。
    """
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "分集"
    ws.append(["项目", "路径", "剪辑师：集数", "时间", "状态"])
    for row in sheets[0]:
        proj, assign = row
        ws.append([proj, "", assign, "", "已分集"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _upload(client, excel_bytes, apply_removals=None):
    data = {"file": (io.BytesIO(excel_bytes), "分集.xlsx")}
    if apply_removals is not None:
        data["apply_removals"] = "true" if apply_removals else "false"
    return client.post("/api/fenji/sync_from_excel", data=data,
                       content_type="multipart/form-data")


class TestSyncFromExcelDiff:
    def _mk_project(self, db, name):
        db.upsert_project(name, "", "", source_root="")

    def test_first_sync_adds_episodes(self, client, tmp_db):
        self._mk_project(tmp_db, "P1")
        xls = _make_excel([[("P1", "张三：1-3"), ("P1", "李四：4-5")]])
        resp = _upload(client, xls)
        assert resp.status_code == 200
        d = resp.get_json()
        assert d["ok"] is True
        assert d["diff_summary"]["added"] == 5
        assert d["diff_summary"]["modified"] == 0
        plan = tmp_db.get_episode_plan("P1")
        assert plan == {"1": "张三", "2": "张三", "3": "张三", "4": "李四", "5": "李四"}

    def test_modify_detected(self, client, tmp_db):
        self._mk_project(tmp_db, "P2")
        tmp_db.set_episode_plan("P2", {"1": "张三", "2": "张三"})
        # Excel 把第2集改成李四
        xls = _make_excel([[("P2", "张三：1"), ("P2", "李四：2")]])
        d = _upload(client, xls).get_json()
        assert d["diff_summary"]["added"] == 0
        assert d["diff_summary"]["modified"] == 1
        plan = tmp_db.get_episode_plan("P2")
        assert plan["2"] == "李四"

    def test_default_no_removal(self, client, tmp_db):
        """默认（追加合并）：Excel 里删掉的行不删除工作台数据。"""
        self._mk_project(tmp_db, "P3")
        tmp_db.set_episode_plan("P3", {"1": "张三", "2": "张三", "3": "张三"})
        # Excel 只有第1、2集（第3集被删）
        xls = _make_excel([[("P3", "张三：1-2")]])
        d = _upload(client, xls).get_json()
        assert d["ok"] is True
        assert d["diff_summary"]["removed"] == 0
        assert d["apply_removals"] is False
        # 第3集仍保留
        plan = tmp_db.get_episode_plan("P3")
        assert "3" in plan

    def test_apply_removals_removes(self, client, tmp_db):
        """apply_removals=true：精确同步，Excel 里删掉的行从工作台移除。"""
        self._mk_project(tmp_db, "P4")
        tmp_db.set_episode_plan("P4", {"1": "张三", "2": "张三", "3": "张三"})
        xls = _make_excel([[("P4", "张三：1-2")]])
        d = _upload(client, xls, apply_removals=True).get_json()
        assert d["ok"] is True
        assert d["apply_removals"] is True
        assert d["diff_summary"]["removed"] == 1
        plan = tmp_db.get_episode_plan("P4")
        assert "3" not in plan
        assert plan == {"1": "张三", "2": "张三"}

    def test_multiple_projects_diff(self, client, tmp_db):
        self._mk_project(tmp_db, "A")
        self._mk_project(tmp_db, "B")
        tmp_db.set_episode_plan("A", {"1": "张三"})
        # A 新增2集(2,3) + 改1集；B 全新增
        xls = _make_excel([[("A", "张三：1-3"), ("B", "李四：1-2")]])
        d = _upload(client, xls).get_json()
        assert d["diff_summary"]["added"] == 4   # A 的 2,3 + B 的 1,2
        assert d["diff_summary"]["modified"] == 0
        # A 的1保留张三
        assert tmp_db.get_episode_plan("A") == {"1": "张三", "2": "张三", "3": "张三"}
        assert tmp_db.get_episode_plan("B") == {"1": "李四", "2": "李四"}
