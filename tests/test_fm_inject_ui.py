# -*- coding: utf-8 -*-
"""回归：分秒帧窗口界面（毛玻璃 / 区间聚合 / 集号·人名·项目ID 查询）。

用户需求（2026-11）：
  1. 相同剪辑师的连续集用区间显示（第 3-6 集），不要一集一行
  2. 半透明毛玻璃效果
  3. 查询支持人名
  4. 支持输入分秒帧项目ID 查分集（可能在网页里跳到别的项目）
  5. 整体整合成一体的界面

技术事实：
  界面代码已从 main_desktop.py 的三引号字符串抽到 static/js/fm-inject.js，
  所以区间聚合这类纯逻辑可以用 node 真跑验证，而不是只看源码里有没有关键字。
"""
import io
import json
import os
import subprocess
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with io.open(os.path.join(BASE, rel), encoding="utf-8") as f:
        return f.read()


def node_available():
    try:
        subprocess.run(["node", "--version"], capture_output=True, timeout=10)
        return True
    except Exception:
        return False


@unittest.skipUnless(node_available(), "需要 node 才能跑 JS 逻辑")
class RangeAggregationTests(unittest.TestCase):
    """区间聚合是展示正确性的核心，必须真跑。"""

    def _run(self, cases):
        js_path = os.path.join(BASE, "static", "js", "fm-inject.js")
        driver = """
const path = %s;
const m = require(path);
const cases = %s;
const out = cases.map(function(c){
  var items = c.items.map(function(x){ return {ep: String(x[0]), editor: x[1]}; });
  var groups = m.groupByEditor(items);
  return groups.map(function(g){
    return { editor: g.editor, ranges: g.ranges, count: g.count, text: m.fmtRanges(g.ranges) };
  });
});
console.log(JSON.stringify(out));
""" % (json.dumps(js_path.replace("\\", "/")), json.dumps(cases, ensure_ascii=False))

        d = tempfile.mkdtemp()
        p = os.path.join(d, "run.js")
        io.open(p, "w", encoding="utf-8").write(driver)
        r = subprocess.run(["node", p], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=40)
        if r.returncode != 0:
            raise AssertionError("node 执行失败: " + (r.stderr or "")[:800])
        return json.loads(r.stdout)

    def test_consecutive_merged_to_range(self):
        out = self._run([{"items": [[1, "张三"], [2, "张三"], [3, "程梦"], [4, "程梦"]]}])[0]
        by = {g["editor"]: g for g in out}
        self.assertEqual(by["张三"]["ranges"], [[1, 2]], "连续集没有合并成区间")
        self.assertEqual(by["程梦"]["ranges"], [[3, 4]])
        self.assertEqual(by["张三"]["text"], "第 1-2 集")

    def test_single_episode_text(self):
        out = self._run([{"items": [[5, "张三"]]}])[0]
        self.assertEqual(out[0]["ranges"], [[5, 5]])
        self.assertEqual(out[0]["text"], "第 5 集", "单集不该写成 5-5")

    def test_gaps_split_into_multiple_ranges(self):
        items = [[1, "张三"], [2, "张三"], [5, "张三"], [6, "张三"], [7, "张三"]]
        out = self._run([{"items": items}])[0]
        self.assertEqual(out[0]["ranges"], [[1, 2], [5, 7]], "断档没有拆成两段")
        self.assertIn("第 5-7 集", out[0]["text"])

    def test_count_is_episode_count(self):
        items = [[1, "张三"], [2, "张三"], [5, "张三"]]
        out = self._run([{"items": items}])[0]
        self.assertEqual(out[0]["count"], 3, "集数统计错了")

    def test_unassigned_grouped(self):
        items = [[1, ""], [2, ""], [3, "张三"]]
        out = self._run([{"items": items}])[0]
        eds = [g["editor"] for g in out]
        self.assertIn("未分配", eds, "空剪辑师未归到“未分配”")

    def test_sorted_by_first_episode(self):
        items = [[10, "乙"], [1, "甲"]]
        out = self._run([{"items": items}])[0]
        self.assertEqual(out[0]["editor"], "甲", "未按起始集号排序")

    def test_duplicate_ep_not_double_counted(self):
        items = [[1, "张三"], [1, "张三"], [2, "张三"]]
        out = self._run([{"items": items}])[0]
        self.assertEqual(out[0]["count"], 2, "重复集号被重复计数")
        self.assertEqual(out[0]["ranges"], [[1, 2]])


class GlassStyleTests(unittest.TestCase):
    def test_backdrop_filter(self):
        src = read("static/js/fm-inject.js")
        self.assertIn("backdrop-filter", src, "缺少毛玻璃")
        self.assertIn("-webkit-backdrop-filter", src, "缺少 webkit 前缀（WebView2 需要）")

    def test_semi_transparent(self):
        src = read("static/js/fm-inject.js")
        self.assertIn("rgba(255,255,255,.", src, "背景不是半透明")

    def test_css_injected_via_style_tag(self):
        """用 <style> 注入而不是内联，hover / 动画才好写。"""
        src = read("static/js/fm-inject.js")
        self.assertIn("createElement('style')", src)
        self.assertIn("__fm_style", src)


class QueryTests(unittest.TestCase):
    def _seg(self):
        src = read("static/js/fm-inject.js")
        i = src.find("function render()")
        return src[i:i + 2200]

    def test_episode_query(self):
        seg = self._seg()
        self.assertIn("isEp", seg, "未识别集号查询")
        self.assertIn("ep >= r[0] && ep <= r[1]", seg, "集号未按区间匹配")

    def test_name_query(self):
        seg = self._seg()
        self.assertIn("toLowerCase()", seg, "人名查询未做大小写不敏感匹配")
        self.assertIn("g.editor", seg, "未按剪辑师匹配")

    def test_fm_project_id_query(self):
        src = read("static/js/fm-inject.js")
        self.assertIn("currentFmId", src, "未读取当前页项目ID")
        self.assertIn("/projects/", src, "未从 URL 解析项目ID")
        self.assertIn("get_episodes('', id", src, "未按项目ID查询")

    def test_current_url_preferred(self):
        """跳到别的项目后，用当前页 ID 而不是窗口记住的项目。"""
        src = read("static/js/fm-inject.js")
        i = src.find("function loadEpisodes")
        seg = src[i:i + 1100]
        self.assertIn("currentFmId()", seg, "未优先用当前页项目ID")

    def test_jump_own_overlay(self):
        """跳转用自建浮层，不用 window.prompt（WebView2 里不稳）。"""
        src = read("static/js/fm-inject.js")
        self.assertIn("__fm_jump", src, "缺少跳转浮层")
        self.assertNotIn("window.prompt(", src, "仍在用 window.prompt")


class BackendIdMappingTests(unittest.TestCase):
    def test_links_index(self):
        src = read("main_desktop.py")
        self.assertIn("def _fm_links_index", src, "缺少链接反查索引")
        seg = src[src.find("def _fm_links_index"):][:1200]
        self.assertIn("/projects/", seg, "未从 URL 解析项目ID")

    def test_episodes_accepts_fm_id(self):
        src = read("main_desktop.py")
        i = src.find("def _fm_episodes")
        seg = src[i:i + 1400]
        self.assertIn("fm_id", seg, "分集读取不支持项目ID")
        self.assertIn("_fm_links_index", seg, "未按项目ID反查本地项目")

    def test_bridge_passes_fm_id(self):
        src = read("main_desktop.py")
        i = src.find("def get_episodes")
        seg = src[i:i + 500]
        self.assertIn("fm_id", seg, "桥未透传项目ID")


if __name__ == "__main__":
    unittest.main()