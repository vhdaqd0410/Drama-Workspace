# -*- coding: utf-8 -*-
"""回归：回传进度文案口径统一 + 分集页不再串行请求。

背景（用户反馈）：
  1. 二部项目回传时，系统进度条 / 同步素材 / 交付三处进度显示不一致
  2. 回传完成后不弹「复制路径/打开目录」窗，复制路径后状态不自动变审核中
  3. 同步素材完成后经常卡很久才跳到分集页
"""
import io
import os
import re
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with io.open(os.path.join(BASE, rel), encoding="utf-8") as f:
        return f.read()


class ProgressTextTests(unittest.TestCase):
    def test_backend_uses_unified_progress_format(self):
        """后端所有进行中进度必须是「回传 N/M 文件」，前端只认这个格式。"""
        src = read("backend/deliver.py")
        # 找所有进行中的进度写入
        bad = []
        for m in re.finditer(r'sync_progress=(["\'])(.*?)\1', src):
            val = m.group(2)
            if "文件" in val and "回传" not in val:
                bad.append(val)
            # 旧文案：已发起 Shell 批量复制（前端无法解析 → 进度一直 0%）
            if "已发起 Shell" in val:
                bad.append(val)
        self.assertEqual(bad, [], "存在口径不一致的进度文案: %r" % bad)

    def test_progress_has_n_over_m_occurrences(self):
        src = read("backend/deliver.py")
        n = len(re.findall(r'sync_progress=(["\']).*?回传\s*%?[d0-9]*\s*/\s*%?', src))
        self.assertGreaterEqual(n, 4, "至少 4 处进度写入应使用 N/M 格式，实际 %d" % n)

    def test_frontend_parses_n_over_m(self):
        src = read("static/js/deliver-events.js")
        self.assertIn("/回传\\s*(\\d+)\\s*\\/\\s*(\\d+)/", src,
                      "前端必须能解析「回传 N/M」")


class DeliverDoneModalTests(unittest.TestCase):
    def test_modal_accepts_mode_option(self):
        """弹窗必须接受 opts（含 mode），才能用 POST 精确解析目标目录。"""
        src = read("static/js/deliver-events.js")
        self.assertRegex(src, r"function _showDeliverDoneModal\(projectName,\s*opts\)",
                         "弹窗函数应接受 opts 参数")
        self.assertIn("opts.mode", src, "弹窗应读取 opts.mode")

    def test_modal_has_copy_and_open_actions(self):
        src = read("static/js/deliver-events.js")
        for act in ("'open'", "'copy'", "'copyonly'"):
            self.assertIn(act, src, "弹窗缺少动作分支 %s" % act)
        self.assertIn("function deliverDoneAction", src, "缺少统一动作入口")

    def test_copy_triggers_status_advance(self):
        """复制路径后应推进状态（批量回传 → 审核中）。"""
        src = read("static/js/deliver-events.js")
        self.assertIn("ctx.advance", src, "复制后未触发状态推进")
        self.assertIn("审核中", src, "未设置审核中状态")

    def test_batch_done_survives_missing_target(self):
        """回传完成后项目可能被归档而不在列表里，不能因此跳过弹窗/改状态。"""
        src = read("static/js/deliver-events.js")
        self.assertIn("group_completed", src,
                      "应把已完成桶也纳入查找")
        self.assertIn("/api/deliver_status/", src,
                      "找不到 target 时应回退查回传任务状态")


class FenjiLoadTests(unittest.TestCase):
    def test_fenji_loads_requests_in_parallel(self):
        """团队成员与项目列表应并行请求，避免串行等待导致打开卡顿。"""
        src = read("static/js/fenji-init.js")
        self.assertIn("_teamP", src)
        self.assertIn("_lightP", src)
        # 不应再出现「先 await team 再发 light」的串行写法
        self.assertNotIn("const data = await api('GET','/api/projects/light');", src,
                         "项目列表仍为串行请求")

    def test_open_fenji_skips_duplicate_load(self):
        """openFenjiFor 应阻止 switchTab 内的无参重复加载。"""
        src = read("static/js/project.js")
        self.assertIn("_fjSkipAutoLoadUntil", src)
        core = read("static/js/core.js")
        self.assertIn("_fjSkipAutoLoadUntil", core)

    def test_fenji_dropdown_html_is_wellformed(self):
        """下拉框拼接不能出现模板串碎片（曾被破坏过）。"""
        src = read("static/js/fenji-init.js")
        self.assertNotIn("</option>`", src, "存在损坏的模板串碎片")
        self.assertIn("_opts", src, "应使用变量拼装 options")


if __name__ == "__main__":
    unittest.main()
