# -*- coding: utf-8 -*-
"""回归：_finalize_run 作用域正确（不放 NameError）+ 质检收尾能产出报告。

事故（2026-11-10）：
  在 _finalize_run 里直接引用 opts（opts 是另一个函数的局部变量），
  质检跑完后抛 NameError: name 'opts' is not defined，
  导致 html 报告生成被中断 → 报告弹不出来。
  类断言测试查不出这类错误，必须真跑一遍收尾流程。
"""
import io
import os
import re
import sys
import tempfile
import shutil
import time
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "backend"))


def read(rel):
    with io.open(os.path.join(BASE, rel), encoding="utf-8") as f:
        return f.read()


class FinalizeScopeTests(unittest.TestCase):
    def test_finalize_run_does_not_reference_opts(self):
        """_finalize_run 函数体内不得引用 opts（它是外部局部变量）。"""
        src = read("backend/qa_engine.py")
        i = src.find("def _finalize_run")
        self.assertGreater(i, 0)
        j = src.find("\n    def ", i + 10)
        seg = src[i:j if j > 0 else len(src)]
        hits = re.findall(r"\bopts\b", seg)
        self.assertEqual(hits, [],
                         "_finalize_run 里引用了未定义的 opts，会抛 NameError")

    def test_finalize_run_accepts_skip_param(self):
        src = read("backend/qa_engine.py")
        seg = src[src.find("def _finalize_run"):][:600]
        self.assertIn("skip_hardsub_folders", seg,
                      "未通过参数接收 skip 清单")


class FinalizeRuntimeTests(unittest.TestCase):
    """真跑一次收尾流程，确保不抛错且能生成报告。"""

    def test_finalize_produces_report(self):
        tmp = tempfile.mkdtemp()
        try:
            for f in ("0成片", "1无字幕版"):
                d = os.path.join(tmp, f)
                os.makedirs(d)
                open(os.path.join(d, "01.mp4"), "wb").write(b"x" * 100)

            import qa_toolkits
            import qa_engine as qe_mod

            # 直接构造一个最小 qa_engine 实例（只需 _finalize_run）
            cls = None
            for n in dir(qe_mod):
                o = getattr(qe_mod, n)
                if isinstance(o, type) and hasattr(o, "_finalize_run"):
                    cls = o
                    break
            self.assertIsNotNone(cls, "找不到带 _finalize_run 的类")

            # 跳过 DB 依赖：用桩 db
            class _FakeDB:
                def update_qa_run(self, *a, **k):
                    pass

                def add_audit_log(self, *a, **k):
                    pass

            inst = cls.__new__(cls)
            inst.db = _FakeDB()
            inst._report_cache = {}
            inst._status_lock = __import__("threading").RLock()

            results = [{
                'video': '01.mp4', 'status': 'pass', 'issues': [], 'details': '',
                'hard_sub': {'0成片': {'has_hardsub': True},
                             '1无字幕版': {'has_hardsub': False}},
                'duration_check': {'status': 'pass'},
                'fps_check': {'status': 'pass'},
                'black_frames': {'0成片': [], '1无字幕版': []},
            }]
            progress_data = {'cp_folder': '0成片'}
            inst._finalize_run(
                None, "UT项目", tmp, None,
                None, None, progress_data,
                results, {'cp_folder': '0成片'}, time.perf_counter(),
                {'0成片': 1, '1无字幕版': 1}, 0, True,
                ['0成片', '1无字幕版'], '', 1,
                skip_hardsub_folders=[],
            )
            hp = progress_data.get('report_html')
            self.assertTrue(hp and os.path.isfile(hp),
                            "收尾流程未产出报告（html_path=%r）" % (hp,))
            self.assertGreater(os.path.getsize(hp), 1000, "报告内容过小")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
