# -*- coding: utf-8 -*-
"""回归：分秒帧窗口的上传进度 / 完成提醒 / 关闭保护。

用户需求（2026-11）：
  1. 能检测上传进度
  2. 上传完成后提醒
  3. 有任务在上传时关闭窗口要提示，避免误触中断上传

技术约束：
  上传是分秒帧网页里的腾讯云 COS 分片上传，发生在 WebView2 内部，
  宿主拿不到网络流，只能由页面内注入的 JS hook XHR.upload.onprogress 回传。

重点防的错误：分片上传时 active 会在片与片之间短暂归零，
若把它当"上传完成"，会疯狂误报提醒。所以用静默期确认。
"""
import io
import os
import sys
import time
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "backend"))

import fm_upload  # noqa: E402


def read(rel):
    with io.open(os.path.join(BASE, rel), encoding="utf-8") as f:
        return f.read()


class UploadStateTests(unittest.TestCase):
    def setUp(self):
        fm_upload.reset()
        self.fired = []
        fm_upload.set_done_callback(lambda msg: self.fired.append(msg))

    def tearDown(self):
        fm_upload.reset()

    def test_uploading_when_active(self):
        fm_upload.report(1, 1024, 4096)
        self.assertTrue(fm_upload.is_uploading(), "有任务时应判定在上传")

    def test_idle_when_nothing(self):
        self.assertFalse(fm_upload.is_uploading(), "无任务时不该拦关闭")

    def test_reset_clears_in_flight(self):
        """关窗后必须清状态，否则下次关闭会被一直拦住。"""
        fm_upload.report(1, 100, 200)
        fm_upload.reset()
        self.assertFalse(fm_upload.is_uploading(), "reset 后仍在 in_flight")

    def test_gap_does_not_fire_done(self):
        """分片间隙归零后，若很快又恢复上传，不能报“完成”。"""
        fm_upload.report(1, 1024, 4096)
        fm_upload.report(0, 1024, 4096)      # 片间间隙
        time.sleep(0.4)
        fm_upload.report(1, 4096, 4096)      # 下一片开始
        time.sleep(fm_upload.DONE_QUIET_SECONDS - 0.2)
        self.assertEqual(self.fired, [], "片间间隙误报了上传完成")

    def test_done_fires_after_quiet_period(self):
        """真正结束后，静默期到点应触发一次提醒。"""
        fm_upload.report(1, 1048576, 2097152)
        fm_upload.report(0, 2097152, 2097152)
        deadline = time.time() + fm_upload.DONE_QUIET_SECONDS + 2
        while time.time() < deadline and not self.fired:
            time.sleep(0.1)
        self.assertEqual(len(self.fired), 1, "上传结束后没有提醒")
        self.assertIn("MB", self.fired[0])

    def test_done_fires_only_once(self):
        """多次归零回传不能重复提醒。"""
        fm_upload.report(1, 1024, 2048)
        fm_upload.report(0, 2048, 2048)
        deadline = time.time() + fm_upload.DONE_QUIET_SECONDS + 2
        while time.time() < deadline and not self.fired:
            time.sleep(0.1)
        fm_upload.report(0, 2048, 2048)      # 再来一条归零
        time.sleep(0.5)
        self.assertEqual(len(self.fired), 1, "完成提醒重复触发")

    def test_never_started_no_fire(self):
        """从没开始过上传，不能凭空提醒。"""
        for _ in range(3):
            fm_upload.report(0, 0, 0)
        time.sleep(0.6)
        self.assertEqual(self.fired, [], "零状态回传误报完成")


class InjectionTests(unittest.TestCase):
    """注入脚本已抽到 static/js/fm-inject.js（便于校验与维护）。"""

    def _inject(self):
        return read("static/js/fm-inject.js")

    def test_inject_file_used(self):
        src = read("main_desktop.py")
        self.assertIn("fm-inject.js", src, "注入改为读文件")
        self.assertIn("def _fm_inject_js", src)

    def test_hook_injected(self):
        seg = self._inject()
        self.assertIn("XMLHttpRequest.prototype.send", seg, "未 hook XHR.send")
        self.assertIn("upload.addEventListener('progress'", seg, "未监听上传进度")

    def test_threshold_filters_small_requests(self):
        """只统计 >1MB 的上传，避免保存评论等小接口干扰。"""
        seg = self._inject()
        self.assertIn("1048576", seg, "缺少大小阈值，会把小请求当上传")

    def test_progress_ui(self):
        seg = self._inject()
        self.assertIn("__fm_up", seg, "缺少进度显示元素")
        self.assertIn("⬆", seg, "缺少上传中提示文案")

    def test_toolbar_copy_and_open(self):
        """窗口内要有复制当前链接、打开链接两个功能。"""
        seg = self._inject()
        self.assertIn("__fm_btn_copy", seg, "缺少复制按钮")
        self.assertIn("__fm_btn_jump", seg, "缺少跳转按钮")
        self.assertIn("copy_clipboard", seg, "复制未走 Python 桥")

    def test_open_link_limited_to_host(self):
        """页面内跳转也要限制域名，别被当成任意网址跳板。"""
        seg = self._inject()
        self.assertIn("mediatrack", seg)
        self.assertIn("只支持", seg)


class ClosingGuardTests(unittest.TestCase):
    def test_closing_handler_registered(self):
        src = read("main_desktop.py")
        self.assertIn("events.closing +=", src, "未绑定关闭事件")

    def test_closing_blocks_when_uploading(self):
        """上传中关闭要确认；弹框失败时也必须阻止关闭，不能把传输掐断。"""
        src = read("main_desktop.py")
        i = src.find("def _on_fm_closing")
        self.assertGreater(i, 0, "缺少关闭保护")
        seg = src[i:i + 1500]
        self.assertIn("_fm_uploading", seg, "未判断是否在上传")
        self.assertIn("create_confirmation_dialog", seg, "未弹确认框")
        self.assertIn("return False", seg, "未实现阻止关闭")
        # 弹框异常分支也要阻止
        tail = seg[seg.find("except"):]
        self.assertIn("return False", tail, "弹框失败时没阻止关闭")

    def test_closing_allowed_when_idle(self):
        src = read("main_desktop.py")
        i = src.find("def _on_fm_closing")
        seg = src[i:i + 1500]
        self.assertIn("return True", seg, "无上传时应放行")

    def test_upload_state_module_used(self):
        src = read("main_desktop.py")
        self.assertIn("fm_upload", src, "未使用上传状态模块")
        self.assertIn("set_done_callback", src, "未注册完成回调")

    def test_reset_on_close(self):
        """关窗要清上传状态，否则残留 in_flight 会让下次关闭一直被拦。"""
        src = read("main_desktop.py")
        i = src.find("def _on_fm_closed")
        seg = src[i:i + 500]
        self.assertIn("_fmup.reset", seg, "关窗后未清理上传状态")


class ProbeApiTests(unittest.TestCase):
    def test_probe_route(self):
        src = read("main_desktop.py")
        self.assertIn("/api/_self/fenmiaozhen/probe", src, "缺少自检接口")

    def test_probe_imports_request(self):
        """probe 里会用 request 取 action，只 import jsonify 会 NameError 500。"""
        src = read("main_desktop.py")
        i = src.find("def _api_self_fm_probe")
        seg = src[i:i + 400]
        self.assertIn("request as _rq", seg, "未导入 request")

    def test_sim_route(self):
        src = read("main_desktop.py")
        self.assertIn("/api/_self/fenmiaozhen/upload_sim", src)

    def test_probe_executes_fixed_script_only(self):
        """自检接口只能跑服务端写死的脚本，不接受外部传 JS。"""
        src = read("main_desktop.py")
        i = src.find("def _api_self_fm_probe")
        seg = src[i:i + 2600]
        self.assertNotIn("get('js')", seg, "不应接受外部 js 参数")
        self.assertNotIn('"js"', seg.split("script =")[0] if "script =" in seg else seg,
                         "参数里不应有 js 字段")


if __name__ == "__main__":
    unittest.main()