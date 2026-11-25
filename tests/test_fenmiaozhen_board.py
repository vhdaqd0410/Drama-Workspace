# -*- coding: utf-8 -*-
"""回归：分秒帧待办清单（进行中优先 / 已完成折叠 / 缺链接提醒）。

业务口径（用户确定，2026-11）：
  1. 除二部以外的项目全部要传分秒帧。
  2. 清单列出这些项目的「进行中」，未填链接的要有提示可补填。
  3. 已完成分组可以折叠。
  4. 以后把非二部项目的状态改成「审核中」（及二审/三审等）时，要提示输入分秒帧链接。
"""
import io
import os
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with io.open(os.path.join(BASE, rel), encoding="utf-8") as f:
        return f.read()


class BoardApiTests(unittest.TestCase):
    def test_board_route(self):
        src = read("backend/enhanced_routes.py")
        self.assertIn("/api/fenmiaozhen/board", src, "缺少待办清单接口")

    def test_policy_is_configurable(self):
        """排除部门与进行中状态必须来自配置，不能写死在代码里。"""
        yml = read("backend/config.yaml")
        self.assertIn("exclude_dept_keywords", yml, "配置缺排除关键词")
        self.assertIn("active_statuses", yml, "配置缺进行中状态")
        src = read("backend/enhanced_routes.py")
        self.assertIn("_fm_policy", src)

    def test_exclude_default_is_dept2(self):
        src = read("backend/enhanced_routes.py")
        i = src.find("def _fm_policy")
        seg = src[i:i + 1200]
        self.assertIn("二部", seg, "默认应排除二部")

    def test_status_contains_shen(self):
        """二审中/三审中这类动态状态也要进清单，否则会漏传。"""
        src = read("backend/enhanced_routes.py")
        i = src.find("def fenmiaozhen_board")
        seg = src[i:i + 2400]
        self.assertIn("'审' in status", seg, "未覆盖 N审中 状态，会漏传")

    def test_split_active_and_completed(self):
        src = read("backend/enhanced_routes.py")
        i = src.find("def fenmiaozhen_board")
        seg = src[i:i + 2400]
        self.assertIn("active", seg)
        self.assertIn("completed", seg)
        self.assertIn("已完成", seg)

    def test_missing_first_sort(self):
        """未填链接的排最前，方便优先补。"""
        src = read("backend/enhanced_routes.py")
        i = src.find("def fenmiaozhen_board")
        seg = src[i:i + 2600]
        self.assertIn("has_link", seg)
        self.assertIn("active.sort", seg)

    def test_only_production_projects(self):
        """只列制作部项目（有 source_root），避免把组内 NAS 壳项目也拉进来。"""
        src = read("backend/enhanced_routes.py")
        i = src.find("def fenmiaozhen_board")
        seg = src[i:i + 2400]
        self.assertIn("source_root", seg)

    def test_stale_check_uses_os_alias(self):
        """本模块 import os as _os。写成裸 os 会抛 NameError，
        而异常被 except 吞掉后会静默判为“路径正常”，僵尸项目就漏不掉。
        （2026-11 实际踩过：H0168-10492 因此一直留在清单里）"""
        src = read("backend/enhanced_routes.py")
        self.assertIn("import os as _os", src, "模块导入别名变了，请同步修改")
        i = src.find("def fenmiaozhen_board")
        j = src.find("def fenmiaozhen_all_links")
        seg = src[i:j]
        self.assertIn("_os.path.isdir", seg, "未用 _os 别名")
        # 不能出现裸 os.path
        import re
        bare = [m for m in re.findall(r"(?<![_\w])os\.path", seg)]
        self.assertEqual(bare, [], "出现裸 os.path，会 NameError")

    def test_stale_check_not_silent(self):
        """路径检查异常必须落日志，不能静默吞掉。"""
        src = read("backend/enhanced_routes.py")
        i = src.find("def fenmiaozhen_board")
        j = src.find("def fenmiaozhen_all_links")
        seg = src[i:j]
        self.assertIn("_logger.warning", seg, "异常未记录日志")

    def test_stale_excluded_from_active(self):
        """目录失效的项目要从 active 里剔除，单独返回。"""
        src = read("backend/enhanced_routes.py")
        i = src.find("def fenmiaozhen_board")
        seg = src[i:src.find("def fenmiaozhen_all_links")]
        self.assertIn("stale_items", seg)
        self.assertIn("not x.get('stale')", seg)


class BoardUiTests(unittest.TestCase):
    def test_fold_completed(self):
        src = read("static/js/fenmiaozhen.js")
        self.assertIn("showCompleted", src, "缺少已完成折叠状态")
        self.assertIn("fmToggleCompleted", src, "缺少折叠开关")

    def test_only_missing_filter(self):
        src = read("static/js/fenmiaozhen.js")
        self.assertIn("onlyMissing", src, "缺少只看未填链接")
        self.assertIn("fmToggleOnlyMissing", src)

    def test_missing_row_highlight(self):
        src = read("static/js/fenmiaozhen.js")
        self.assertIn("is-miss", src, "未填链接行没有左侧色条")
        self.assertIn("未填", src, "缺少未填链接标记")
        self.assertIn("填写链接", src, "缺少补填入口")

    def test_rows_use_left_color_bar(self):
        """已配置/未配置用左侧色条 + 胶囊区分，比只靠小徒标明显。"""
        src = read("static/js/fenmiaozhen.js")
        self.assertIn("is-ok", src, "缺少已配置行样式")
        self.assertIn("fm-flag ok", src.replace("'", "").replace('"', "") or "fm-flag", "缺少已配标记")
        html = read("templates/index.html")
        self.assertIn(".fm-row.is-ok", html, "缺少绿色色条样式")
        self.assertIn(".fm-row.is-miss", html, "缺少红色色条样式")

    def test_dept_and_status_are_tags(self):
        """部门与状态做成标签，状态颜色复用主页 badge 配色。"""
        src = read("static/js/fenmiaozhen.js")
        self.assertIn("function deptTag", src, "部门未做标签")
        self.assertIn("function statusTag", src, "状态未做标签")
        seg = src[src.find("function statusTag"):][:700]
        self.assertIn("getBadge", seg, "状态颜色未复用主页配色")

    def test_name_clickable_jump(self):
        """项目名可点击回首页定位并高亮。"""
        src = read("static/js/fenmiaozhen.js")
        self.assertIn("fmJumpTo", src, "缺少跳转函数")
        seg = src[src.find("window.fmJumpTo"):][:400]
        self.assertIn("jumpToProject", seg, "未调用现成的定位+高亮函数")

    def test_grid_alignment(self):
        """部门/状态列用 grid 固定列宽对齐，不用 flex 自适应。"""
        html = read("templates/index.html")
        i = html.find(".fm-row{")
        self.assertGreater(i, 0)
        seg = html[i:i + 260]
        self.assertIn("grid-template-columns", seg, "未用 grid 对齐列")

    def test_no_episode_count_column(self):
        """去掉集数列（用户反馈无用）。"""
        src = read("static/js/fenmiaozhen.js")
        i = src.find("function rowHtml")
        seg = src[i:i + 1600]
        self.assertNotIn("fm-row-ep", seg, "集数列没删")

    def test_stale_section(self):
        """僵尸记录（目录失效）单独折叠，不污染主清单。"""
        src = read("static/js/fenmiaozhen.js")
        self.assertIn("目录失效", src, "缺少目录失效区")
        self.assertIn("fmToggleStale", src, "缺少失效区折叠")
        back = read("backend/enhanced_routes.py")
        self.assertIn("stale_items", back, "后端未区分僵尸记录")

    def test_css_for_fold_and_missing(self):
        html = read("templates/index.html")
        self.assertIn(".fm-sec-fold", html, "缺少折叠样式")
        self.assertIn(".fm-row.is-miss", html, "缺少缺链接高亮样式")
        self.assertIn(".fm-flag.miss", html, "缺少缺链接徽标样式")


class StatusChangePromptTests(unittest.TestCase):
    def test_prompt_on_review_status(self):
        """改审核相关状态时，非二部项目要提示填分秒帧链接。"""
        src = read("static/js/project.js")
        i = src.find("async function onStatusChange")
        self.assertGreater(i, 0)
        seg = src[i:i + 3600]
        self.assertIn("fmEnsureLink", seg, "状态改为审核时未提示补链接")
        self.assertIn("'审'", seg, "未覆盖二审/三审等状态")

    def test_skip_submit_state(self):
        """待提交审核走 submitReview，不要再重复弹一次。"""
        src = read("static/js/project.js")
        i = src.find("async function onStatusChange")
        seg = src[i:i + 3600]
        self.assertIn("!== '待提交审核'", seg)

    def test_dept_excluded_helper(self):
        src = read("static/js/fenmiaozhen.js")
        self.assertIn("window.fmDeptExcluded", src, "缺少部门排除判断")
        seg = src[src.find("function deptExcluded"):][:700]
        self.assertIn("exclude_dept_keywords", seg, "未读配置，写死了二部")

    def test_ensure_link_validates_host(self):
        src = read("static/js/fenmiaozhen.js")
        i = src.find("window.fmEnsureLink")
        seg = src[i:i + 1500]
        self.assertIn("isFmUrl", seg, "补链接时未校验域名")

    def test_ensure_link_saves(self):
        src = read("static/js/fenmiaozhen.js")
        i = src.find("window.fmEnsureLink")
        seg = src[i:i + 1500]
        self.assertIn("/api/fenmiaozhen/link/", seg, "补链接未保存")


if __name__ == "__main__":
    unittest.main()