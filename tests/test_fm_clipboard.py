# -*- coding: utf-8 -*-
"""回归：分秒帧窗口「复制当前链接」端到端。

踩过的坑（2026-11，用户报“复制失败，请手动选中地址”）：
  1. _set_clipboard 没声明 Win32 argtypes。64 位下 HGLOBAL 是 8 字节，
     ctypes 按 32 位 int 传 → GlobalLock 抛
     “OverflowError: int too long to convert” → 被 except 吞掉 → 返回 False。
     表现：页面里点复制总是失败，只能手动选中。
  2. 路由里另有一份内联剪贴板代码，同样有这个问题（打开项目复制路径走它）。
     现已统一复用 _set_clipboard。
  3. 桥调用是异步的，验证时必须等一会儿再读剪贴板，否则读到旧值误判失败。
"""
import ctypes
import io
import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "backend"))


def read(rel):
    with io.open(os.path.join(BASE, rel), encoding="utf-8") as f:
        return f.read()


class ClipboardImplTests(unittest.TestCase):
    def test_argtypes_declared(self):
        """必须显式声明 64 位句柄类型，否则 GlobalLock 会溢出。"""
        src = read("main_desktop.py")
        i = src.find("def _set_clipboard")
        j = src.find("class _FmBridge")
        seg = src[i:j]
        for name in ("GlobalAlloc", "GlobalLock", "SetClipboardData", "RtlMoveMemory"):
            self.assertIn(name + ".argtypes", seg, "%s 未声明 argtypes" % name)

    def test_retries_when_clipboard_busy(self):
        """剪贴板可能被别的程序占用，要重试 OpenClipboard。"""
        src = read("main_desktop.py")
        i = src.find("def _set_clipboard")
        seg = src[i:src.find("class _FmBridge")]
        self.assertIn("for _ in range(5)", seg, "OpenClipboard 未重试")

    def test_route_reuses_helper(self):
        """路由里不应再有内联剪贴板代码（那份没声明 argtypes）。"""
        src = read("main_desktop.py")
        i = src.find("def _api_self_fenmiaozhen")
        j = src.find("def _api_self_fm_probe")
        seg = src[i:j]
        self.assertIn("_set_clipboard(copy_path)", seg, "路由未复用 _set_clipboard")
        self.assertNotIn("GlobalAlloc(0x0042", seg, "路由里仍有内联剪贴板代码")

    @unittest.skipUnless(sys.platform == "win32", "仅 Windows")
    def test_writes_and_reads_back(self):
        """真跑一次：写入 + 读回，验证 64 位句柄路径可用。"""
        import time as _t
        src = read("main_desktop.py")
        i = src.find("def _set_clipboard")
        seg = src[i:src.find("class _FmBridge")]
        ns = {"ctypes": ctypes, "time": _t}
        exec(compile(seg, "setclip", "exec"), ns)
        fn = ns["_set_clipboard"]

        text = "workbench-clipboard-test-中文"
        self.assertTrue(fn(text), "写入剪贴板失败（64 位句柄问题复发了？）")

        k32 = ctypes.windll.kernel32
        u32 = ctypes.windll.user32
        k32.GlobalLock.restype = ctypes.c_void_p
        k32.GlobalLock.argtypes = [ctypes.c_void_p]
        k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        u32.OpenClipboard.argtypes = [ctypes.c_void_p]
        u32.GetClipboardData.restype = ctypes.c_void_p
        u32.GetClipboardData.argtypes = [ctypes.c_uint]

        got = ""
        if u32.OpenClipboard(None):
            try:
                h = u32.GetClipboardData(13)
                if h:
                    p = k32.GlobalLock(ctypes.c_void_p(h))
                    if p:
                        got = ctypes.wstring_at(p)
                        k32.GlobalUnlock(ctypes.c_void_p(h))
            finally:
                u32.CloseClipboard()
        self.assertEqual(got.rstrip("\x00"), text, "读回内容与写入不一致")


class BridgeChainTests(unittest.TestCase):
    def test_probe_reports_api_keys(self):
        """自检要能看到页面实际暴露的桥方法名。"""
        src = read("main_desktop.py")
        self.assertIn("apiKeys", src, "自检未返回桥方法名")
        self.assertIn("hasCopy", src)

    def test_sim_copy_waits_before_reading(self):
        """桥调用异步，读剪贴板前必须等一下。"""
        src = read("main_desktop.py")
        i = src.find('elif action == "sim_copy"')
        self.assertGreater(i, 0)
        seg = src[i:i + 1600]
        self.assertIn("time.sleep(0.9)", seg, "没等桥调用完成就读剪贴板")

    def test_frontend_bridge_timeout(self):
        """桥 Promise 偶尔不 resolve，前端要有超时兜底。"""
        src = read("main_desktop.py")
        i = src.find("_fm_toolbar_js")
        seg = src[i:i + 4200]
        self.assertIn("setTimeout", seg, "复制没有超时兜底")
        self.assertIn("1500", seg, "超时时长缺失")

    def test_frontend_falls_back_on_bridge_false(self):
        """桥明确返回 ok:false 时要换浏览器 API 再试，不能直接报失败。"""
        src = read("main_desktop.py")
        i = src.find("_fm_toolbar_js")
        seg = src[i:i + 4600]
        self.assertIn("__fmFallbackCopy", seg)


if __name__ == "__main__":
    unittest.main()