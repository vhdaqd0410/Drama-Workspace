# -*- coding: utf-8 -*-
"""回归：同步任务静默死亡要能被判定 + 状态推进要清掉残留同步文案。

用户反馈（2026-10-22）：
  - 同步素材完了不自动跳分集
  - 手动分集完成后仍显示「📦 完整同步项目目录...10%」
根因：
  a) COM CopyHere 等待循环没泵消息 → Shell 复制挂死，状态永远停在 10%
  b) set_custom_status 只改 custom_status，没清 sync_progress → 残留文案一直显示
  c) 前端无法区分「真在同步」和「任务已死」，只能傻等
"""
import io
import os
import re
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with io.open(os.path.join(BASE, rel), encoding="utf-8") as f:
        return f.read()


class ComCopyPumpsMessagesTests(unittest.TestCase):
    def test_com_wait_loop_pumps_messages(self):
        """COM 等待循环必须 PumpWaitingMessages，否则 Shell 复制会挂死。"""
        src = read("backend/sync.py")
        i = src.find("def _copy_desktop_com")
        self.assertGreater(i, 0)
        seg = src[i:i + 3000]
        self.assertIn("PumpWaitingMessages", seg,
                      "COM 等待循环缺少消息泵 → Shell 复制会挂住")
        # 泵消息应该在循环里（CopyHere 之后）
        j = seg.find("CopyHere")
        k = seg.find("PumpWaitingMessages")
        self.assertGreater(k, j, "消息泵应在 CopyHere 之后")

    def test_com_copy_has_stall_detection(self):
        """复制停滞要能主动退出，不能无限挂住。"""
        src = read("backend/sync.py")
        seg = src[src.find("def _copy_desktop_com"):][:3400]
        self.assertIn("last_change", seg, "缺少进度变化时间戳")
        self.assertIn("停滞", seg, "缺少停滞检测")


class StatusClearProgressTests(unittest.TestCase):
    def test_set_custom_status_clears_stale_progress(self):
        """改状态时要清掉残留的同步进度文案。"""
        src = read("backend/deliver.py")
        i = src.find("def set_custom_status")
        self.assertGreater(i, 0)
        seg = src[i:i + 2200]
        self.assertIn("sync_progress", seg,
                      "set_custom_status 未清理 sync_progress（残留“10% 同步中”）")
        self.assertIn("syncing", seg, "未处理仍卡在 syncing 的情况")


class SyncHeartbeatTests(unittest.TestCase):
    def test_engine_has_heartbeat_dict(self):
        src = read("backend/sync_engine.py")
        self.assertIn("_sync_heartbeat", src)

    def test_sync_writes_and_clears_heartbeat(self):
        src = read("backend/sync.py")
        self.assertIn("hb[project_name] = {", src, "同步未写心跳")
        self.assertIn("_sync_heartbeat.pop", src, "同步结束未清心跳")

    def test_status_api_reports_alive_and_recovers(self):
        """/api/sync_status 要报 alive，并能自动收回幽灵 syncing。"""
        src = read("backend/app.py")
        i = src.find("def api_sync_status")
        self.assertGreater(i, 0)
        seg = src[i:i + 2000]
        self.assertIn('"alive"', seg, "接口未返回 alive")
        self.assertIn('sync_status="pending"', seg, "接口未自动收回幽灵任务")

    def test_frontend_stops_when_alive_false(self):
        src = read("static/js/project.js")
        seg = src[src.find("async function syncMaterial"):][:6000]
        self.assertIn("st.alive === false", seg, "前端未用 alive 判死")
        self.assertIn("中断", seg, "未提示同步中断")


if __name__ == "__main__":
    unittest.main()
