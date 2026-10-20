# -*- coding: utf-8 -*-
"""回归：拷贝等待用轻量指纹，不再每秒对目标目录做递归统计。

背景：桌面版拷贝（COM / VBS CopyHere）等待期间曾每秒调用
`_count_dir_stats(dst)`（os.walk + 逐文件 getsize）。目标在 NAS 上时，
这等于每秒把整个目录树重新拉一遍，和拷贝进程抢 SMB 带宽，
表现为「一拷贝整机就卡」，且随项目文件数增长而恶化。
"""
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import sync as sync_mod  # noqa: E402


def _sync_cls():
    for name in dir(sync_mod):
        obj = getattr(sync_mod, name)
        if isinstance(obj, type) and hasattr(obj, "_quick_dst_signature"):
            return obj
    return None


class CopyWaitIsCheapTests(unittest.TestCase):
    def setUp(self):
        self.cls = _sync_cls()
        self.assertIsNotNone(self.cls, "应存在带 _quick_dst_signature 的同步类")
        self.inst = self.cls.__new__(self.cls)
        self.tmp = tempfile.mkdtemp()
        self.src = os.path.join(self.tmp, "src")
        self.dst = os.path.join(self.tmp, "dst")
        os.makedirs(self.src)
        os.makedirs(self.dst)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_signature_tracks_growth(self):
        """写入中指纹必须变化（否则会过早判定完成、杀掉拷贝进程）。"""
        p = os.path.join(self.dst, "a.mp4")
        with open(p, "wb") as f:
            f.write(b"x" * 100)
        s1 = self.inst._quick_dst_signature(self.dst)
        with open(p, "ab") as f:
            f.write(b"x" * 900)
        s2 = self.inst._quick_dst_signature(self.dst)
        self.assertNotEqual(s1, s2, "文件长大时指纹应变化")
        self.assertEqual(s2[1], 1000)

    def test_signature_sees_subdir_writes(self):
        """顶层名字早已齐了，但子目录还在写 —— 指纹仍要变化。"""
        with open(os.path.join(self.src, "a.mp4"), "wb") as f:
            f.write(b"x" * 10)
        os.makedirs(os.path.join(self.src, "sub"))
        with open(os.path.join(self.src, "sub", "b.mp4"), "wb") as f:
            f.write(b"y" * 10)

        with open(os.path.join(self.dst, "a.mp4"), "wb") as f:
            f.write(b"x" * 10)
        os.makedirs(os.path.join(self.dst, "sub"))
        self.assertTrue(self.inst._all_items_in_dst(self.src, self.dst),
                        "顶层名字此时已齐")
        s_empty = self.inst._quick_dst_signature(self.dst)

        with open(os.path.join(self.dst, "sub", "b.mp4"), "wb") as f:
            f.write(b"y" * 10)
        s_filled = self.inst._quick_dst_signature(self.dst)

        self.assertNotEqual(s_empty, s_filled,
                            "子目录写入时指纹必须变化，否则会误判完成")
        self.assertEqual(s_filled[2], 1)

    def test_empty_signature_is_zero(self):
        self.assertEqual(self.inst._quick_dst_signature(self.dst), (0, 0, 0))

    def test_no_recursive_walk_during_wait(self):
        """核心断言：等待循环里不允许再出现 _count_dir_stats。

        用计数桩验证 COM 路径的等待阶段不调用递归统计。
        """
        calls = {"n": 0}
        real = self.cls._count_dir_stats

        def _counting(path):
            calls["n"] += 1
            return real(path)
        # 造源：1 个文件
        with open(os.path.join(self.src, "a.mp4"), "wb") as f:
            f.write(b"x" * 10)

        # 伪造 Shell.Application，让 CopyHere 立即把文件“拷”好
        dst_holder = self.dst

        class _Items:
            Count = 1

            def __iter__(self):
                return iter([])

        class _Folder:
            def __init__(self, path):
                self.path = path

            def Items(self):
                return _Items()

            def CopyHere(self, items, flags):
                with open(os.path.join(dst_holder, "a.mp4"), "wb") as f:
                    f.write(b"x" * 10)

        class _Shell:
            def Namespace(self, path):
                return _Folder(path)

        fake_com = type(sys)("pythoncom")
        fake_com.CoInitialize = lambda: None
        fake_com.CoUninitialize = lambda: None

        fake_win32 = type(sys)("win32com")
        fake_client = type(sys)("win32com.client")
        fake_client.Dispatch = lambda name: _Shell()
        fake_client.__dict__["Dispatch"] = fake_client.Dispatch

        with patch.dict(sys.modules, {
            "pythoncom": fake_com,
            "win32com": fake_win32,
            "win32com.client": fake_client,
        }):
            # 实例属性覆盖（staticmethod 用 patch.object 会多传 self）
            self.inst._count_dir_stats = staticmethod(_counting)
            try:
                ok, msg = self.inst._copy_desktop_com(self.src, self.dst, timeout=30)
            finally:
                del self.inst._count_dir_stats

        self.assertTrue(ok, msg)
        # 只允许结束时算一次（用于回报大小），绝不能是每秒一次
        self.assertLessEqual(calls["n"], 1,
                             "等待期间不应反复递归统计目标目录（实际调用 %d 次）" % calls["n"])


if __name__ == "__main__":
    unittest.main()
