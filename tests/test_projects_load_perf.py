# -*- coding: utf-8 -*-
"""回归：首页冷启动性能 + 骨架屏。

背景（2026-11）：用户反馈重启后首页加载极慢。
根因：get_projects_enriched 对每个「待交付/已完成」项目同步调 get_delivery_stats，
每个项目 5~15 次 NAS 往返，208 个已完成项目冷启动累积 40 秒以上。

修法：
  1. 首页只读持久化缓存（peek），绝不触发扫盘
  2. 后台线程预热并落盘
  3. 前端先出骨架屏 + 扫光动画，数据到了再完整显示
"""
import io
import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "backend"))


def read(rel):
    with io.open(os.path.join(BASE, rel), encoding="utf-8") as f:
        return f.read()


class NoSyncScanInProjectsApiTests(unittest.TestCase):
    def test_enriched_does_not_call_get_delivery_stats(self):
        """首页聚合绝不能同步调 get_delivery_stats（会扫 NAS 几十秒）。"""
        src = read("backend/scan.py")
        i = src.find("给待交付 / 已完成项目附加交付统计")
        self.assertGreater(i, 0, "找不到交付统计附加代码段")
        seg = src[i:i + 1600]
        self.assertNotIn("self.get_delivery_stats(proj", seg,
                         "首页仍在同步调用 get_delivery_stats，冷启动会卡死")

    def test_enriched_uses_peek_cache(self):
        src = read("backend/scan.py")
        i = src.find("给待交付 / 已完成项目附加交付统计")
        seg = src[i:i + 1600]
        self.assertIn("peek_delivery_stats", seg, "未改用只读缓存")

    def test_enriched_starts_warmup(self):
        src = read("backend/scan.py")
        i = src.find("给待交付 / 已完成项目附加交付统计")
        seg = src[i:i + 1600]
        self.assertIn("start_delivery_stats_warmup", seg, "未启动后台预热")

    def test_pending_marker(self):
        """无缓存时给 pending 占位，避免前端拿到脏的 found=False。"""
        src = read("backend/scan.py")
        i = src.find("给待交付 / 已完成项目附加交付统计")
        seg = src[i:i + 1600]
        self.assertIn('"pending": True', seg) if '"pending": True' in seg else self.assertIn("'pending': True", seg)


class CachePersistenceTests(unittest.TestCase):
    def test_engine_has_persistent_cache(self):
        src = read("backend/sync_engine.py")
        for name in ("_load_delivery_stats_disk_cache",
                     "save_delivery_stats_disk_cache",
                     "peek_delivery_stats",
                     "start_delivery_stats_warmup"):
            self.assertIn(name, src, "缺少 %s" % name)

    def test_cache_file_path(self):
        src = read("backend/sync_engine.py")
        self.assertIn("delivery_stats_cache.json", src, "缓存未落盘")

    def test_peek_never_scans(self):
        """peek 只读内存，不调 os.listdir/get_delivery_stats。"""
        src = read("backend/sync_engine.py")
        i = src.find("def peek_delivery_stats")
        self.assertGreater(i, 0)
        seg = src[i:src.find("def start_delivery_stats_warmup")]
        self.assertNotIn("os.listdir", seg)
        self.assertNotIn("get_delivery_stats", seg)

    def test_warmup_marks_dirty(self):
        src = read("backend/sync_engine.py")
        i = src.find("def start_delivery_stats_warmup")
        seg = src[i:i + 2600]
        self.assertIn("_delivery_stats_dirty", seg, "预热后未标记待落盘")


class SkeletonUiTests(unittest.TestCase):
    def test_skeleton_css_exists(self):
        html = read("templates/index.html")
        self.assertIn(".sk-wrap", html, "缺少骨架屏样式")
        self.assertIn("@keyframes sk-sweep", html, "缺少扫光动画")

    def test_sweep_is_visible_not_color_fade(self):
        """扫光必须用白色高光带（早前弱色阶+background-position 看不见）。"""
        html = read("templates/index.html")
        i = html.find(".sk-bar::after")
        self.assertGreater(i, 0, "缺少扫光伪元素")
        seg = html[i:i + 420]
        self.assertIn("transform:translateX", seg, "扫光未用 transform 位移")
        self.assertIn("rgba(255,255,255", seg, "扫光未用白色高光带")

    def test_sweep_not_disabled_by_reduced_motion(self):
        """本机系统开了「关闭界面动画」→ 浏览器报 reduced-motion:reduce。
        骨架扫光绝不能再写 media 禁用，否则用户完全看不到动画。"""
        html = read("templates/index.html")
        i = html.find(".sk-bar::after")
        self.assertGreater(i, 0)
        # 扫光定义之后不能出现把 .sk-bar::after 的 animation 禁掉的规则
        after_sweep = html[i:]
        self.assertNotIn(".sk-bar::after{animation:none", after_sweep.replace(" ", ""),
                         "扫光被 reduced-motion 禁用了")


        """整页骨架遮罩（统计/图表/筛选/项目区全盖）。"""
        html = read("templates/index.html")
        self.assertIn('id="dashSkeleton"', html, "缺少整页骨架容器")
        self.assertIn(".dash-sk", html, "缺少整页骨架样式")
        self.assertIn(".dash-sk-stats", html, "骨架缺统计行")
        self.assertIn(".dash-sk-charts", html, "骨架缺图表区")
        self.assertIn(".dash-sk-filter", html, "骨架缺筛选栏")

    def test_skeleton_renderer_exists(self):
        src = read("static/js/core.js")
        self.assertIn("function showProjectsSkeleton", src, "缺少骨架屏渲染函数")
        self.assertIn("function hideProjectsSkeleton", src)

    def test_skeleton_renders_page_frame(self):
        """showProjectsSkeleton 要生成统计/图表/筛选/项目四部分。"""
        src = read("static/js/core.js")
        i = src.find("function showProjectsSkeleton")
        seg = src[i:i + 1800]
        for cls in ("dash-sk-stats", "dash-sk-charts", "dash-sk-filter", "sk-wrap"):
            self.assertIn(cls, seg, "骨架缺 %s" % cls)

    def test_load_projects_shows_skeleton(self):
        src = read("static/js/project.js")
        i = src.find("async function loadProjects")
        self.assertGreater(i, 0)
        seg = src[i:i + 1200]
        self.assertIn("showProjectsSkeleton", seg, "加载时未显示骨架屏")

    def test_skeleton_removed_before_render(self):
        """先渲染真实数据再揭开遮罩，避免中间闪白。"""
        src = read("static/js/project.js")
        i = src.find("async function loadProjects")
        seg = src[i:i + 6000]
        p_render = seg.find("renderDashboard()")
        p_hide = seg.find("hideProjectsSkeleton()")
        self.assertGreater(p_render, 0)
        self.assertGreater(p_hide, 0)
        self.assertLess(p_render, p_hide, "顺序错了：应先渲染再隐藏骨架")

    def test_min_show_duration(self):
        """保证扫光至少跑一程，否则一闪而过看不见。"""
        src = read("static/js/core.js")
        i = src.find("function hideProjectsSkeleton")
        seg = src[i:i + 900]
        self.assertIn("MIN_SHOW", seg, "缺少最短展示时长")

    def test_skeleton_removed_on_error(self):
        src = read("static/js/project.js")
        i = src.find("async function loadProjects")
        j = src.find("_projectsLoading = false", i)
        seg = src[i:j]
        # catch 分支里也要隐藏，避免加载失败时永远停在骨架
        self.assertGreaterEqual(seg.count("hideProjectsSkeleton"), 2,
                                "加载失败时骨架屏不会消失")


class StartupWindowTests(unittest.TestCase):
    def test_min_tray_only_for_autostart(self):
        """min_to_tray 只对开机自启生效；手动启动/托盘重启必须直接显示窗口。"""
        src = read("main_desktop.py")
        i = src.find("def _apply_startup_settings")
        self.assertGreater(i, 0)
        seg = src[i:i + 1600]
        self.assertIn("--autostart", seg, "未区分开机自启与手动启动")
        self.assertIn("if min_tray and _is_autostart", seg,
                      "未把 min_to_tray 限定在开机自启场景")

    def test_vbs_passes_autostart_flag(self):
        """自启入口必须带 --autostart，否则无法区分来源。"""
        d = open(os.path.join(BASE, "start_desktop.vbs"), "rb").read()
        t = d.decode("utf-8-sig", "ignore")
        self.assertIn("--autostart", t, "start_desktop.vbs 未传 --autostart")
        self.assertIn("main_desktop.py", t)


if __name__ == "__main__":
    unittest.main()