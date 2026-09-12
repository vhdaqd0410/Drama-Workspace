# -*- coding: utf-8 -*-
"""阶段A：状态机收口测试 —— 精简 9 状态、审核轮次、旧状态归一化、审计日志。"""
import os
import sys
import pytest

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


class TestReviewStatusHelpers:
    """审核轮次辅助：旧「N审中」仅作读取兼容，新写入统一「审核中」。"""

    def test_is_review_status_still_detects_legacy(self):
        from deliver import DeliverMixin
        m = object.__new__(DeliverMixin)
        assert m._is_review_status("二审中") is True
        assert m._is_review_status("三审中") is True
        assert m._is_review_status("十审中") is True
        assert m._is_review_status("审核中") is False  # 审核中是基础状态
        assert m._is_review_status("修改中") is False
        assert m._is_review_status("") is False

    def test_legacy_review_status_normalizes_to_shenhe(self):
        from deliver import DeliverMixin
        m = object.__new__(DeliverMixin)
        for legacy in ("二审中", "三审中", "十审中"):
            assert m.normalize_status(legacy) == "审核中"

    def test_legacy_map(self):
        from deliver import DeliverMixin
        m = object.__new__(DeliverMixin)
        assert m.normalize_status("待提交审核") == "待审核"
        assert m.normalize_status("交付中") == "待交付"
        assert m.normalize_status("剪辑中") == "剪辑中"
        assert m.normalize_status("") == ""

    def test_wf_statuses_is_nine(self):
        from deliver import DeliverMixin
        assert len(DeliverMixin.WF_STATUSES) == 9
        for s in ("分集中", "剪辑中", "待审核", "审核中", "修改中",
                  "待交付", "待质检", "质检中", "已完成"):
            assert s in DeliverMixin.WF_STATUSES
        # 已废弃的状态不应在新清单里
        for gone in ("待提交审核", "交付中", "二审中", "三审中", "已交付"):
            assert gone not in DeliverMixin.WF_STATUSES

    def test_next_review_status_always_shenhe(self):
        from deliver import DeliverMixin
        m = object.__new__(DeliverMixin)
        for old in ("审核中", "待提交审核", "二审中", "修改中", "三审中"):
            assert m._next_review_status(old) == "审核中"


class TestSetCustomStatus:
    def _mk_project(self, tmp_db, name):
        tmp_db.upsert_project(name, "", "", source_root="")

    def test_accepts_new_statuses(self, engine, tmp_db):
        """精简后的 9 状态应被接受。"""
        self._mk_project(tmp_db, "P1")
        for s in ("分集中", "剪辑中", "待审核", "审核中", "修改中",
                  "待交付", "待质检", "质检中", "已完成"):
            ok, msg = engine.set_custom_status("P1", s)
            assert ok is True, "状态 %s 被拒绝: %s" % (s, msg)

    def test_legacy_status_auto_normalized(self, engine, tmp_db):
        """旧状态写入时自动归一化为新状态。"""
        self._mk_project(tmp_db, "P2")
        engine.set_custom_status("P2", "待提交审核")
        assert tmp_db.get_project("P2")["custom_status"] == "待审核"
        engine.set_custom_status("P2", "二审中")
        assert tmp_db.get_project("P2")["custom_status"] == "审核中"
        engine.set_custom_status("P2", "交付中")
        assert tmp_db.get_project("P2")["custom_status"] == "待交付"

    def test_review_round_increments_on_revision_loop(self, engine, tmp_db):
        """修改中 → 审核中 时审核轮次 +1（替代旧的二审中/三审中）。"""
        self._mk_project(tmp_db, "P3")
        engine.set_custom_status("P3", "审核中")          # 首轮
        assert int(tmp_db.get_project("P3")["review_round"]) == 1
        engine.set_custom_status("P3", "修改中")
        engine.set_custom_status("P3", "审核中")          # 第 2 轮
        assert int(tmp_db.get_project("P3")["review_round"]) == 2
        engine.set_custom_status("P3", "修改中")
        engine.set_custom_status("P3", "审核中")          # 第 3 轮
        assert int(tmp_db.get_project("P3")["review_round"]) == 3
        # 状态名始终保持「审核中」
        assert tmp_db.get_project("P3")["custom_status"] == "审核中"

    def test_review_round_not_bumped_by_repeat_shenhe(self, engine, tmp_db):
        """连续设为审核中不应误增轮次。"""
        self._mk_project(tmp_db, "P4")
        engine.set_custom_status("P4", "审核中")
        engine.set_custom_status("P4", "审核中")
        engine.set_custom_status("P4", "审核中")
        assert int(tmp_db.get_project("P4")["review_round"]) == 1

    def test_rejects_invalid_status(self, engine, tmp_db):
        self._mk_project(tmp_db, "P5")
        ok, msg = engine.set_custom_status("P5", "不存在的状态")
        assert ok is False
        assert "无效" in msg

    def test_status_change_writes_audit_log(self, engine, tmp_db):
        """状态变更应写入审计日志（供时间线）。"""
        self._mk_project(tmp_db, "P6")
        engine.set_custom_status("P6", "剪辑中")
        engine.set_custom_status("P6", "待审核")
        logs = tmp_db.get_audit_logs("P6")
        actions = [l.get("action") for l in logs]
        assert "状态变更" in actions
        details = [l.get("detail") for l in logs if l.get("action") == "状态变更"]
        assert any("剪辑中" in d and "待审核" in d for d in details)
