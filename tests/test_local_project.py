# -*- coding: utf-8 -*-
"""本地剪辑项目创建测试：模拟组内项目 + 分集分配 + 素材/剧本，验证拉取正确。"""
import os
import json
import sys
import pytest

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


class TestLocalProject:
    def _engine(self, tmp_path):
        from sync_engine import SyncEngine
        from db import Database
        group_root = os.path.join(str(tmp_path), "group")
        os.makedirs(group_root, exist_ok=True)
        cfg = {
            "nas": {"group_root": group_root, "production_roots": [], "unc_map": {}},
            "sync": {"mode": "full"},
            "output_dir_name": "01上映单集版",
            "delivery_folder": os.path.join(str(tmp_path), "000交付"),
            "watcher": {"enabled": False},
        }
        return SyncEngine(cfg, Database(os.path.join(str(tmp_path), "t.db")))

    def _mk_group_project(self, tmp_path, eng, name, editors):
        """建组内项目 + episode_plan + 素材/剧本目录（结构：抽卡素材/01_抽卡素材/集号-剪辑师/文件）。"""
        proj = os.path.join(str(tmp_path), "group", name)
        os.makedirs(proj, exist_ok=True)
        # 素材文件夹：02_抽卡素材/01_抽卡素材/集号-剪辑师/文件（模拟真实结构）
        mat = os.path.join(proj, "02_抽卡素材", "01_抽卡素材")
        os.makedirs(mat, exist_ok=True)
        # 剧本文件夹
        script = os.path.join(proj, "05 剧本文档")
        os.makedirs(script, exist_ok=True)
        # 建素材（按集）+ 剧本文件
        ep_plan = {}
        for ed, eps in editors.items():
            for ep in eps:
                ep_plan[str(ep)] = ed
                d = os.path.join(mat, "%d- %s" % (ep, ed))
                os.makedirs(d, exist_ok=True)
                open(os.path.join(d, "%d-1-V01.mp4" % ep), "w").close()
        open(os.path.join(script, "全剧剧本.docx"), "w").close()
        # 写入项目
        eng.db.upsert_project(name, "", proj, source_root="")
        eng.db.update_project_status(name, episode_plan=json.dumps(ep_plan, ensure_ascii=False))
        return proj

    def _mk_roughcut(self, tmp_path, name, editors):
        """在组内项目里建粗剪文件夹：02_抽卡素材/03_粗剪/集号-剪辑师.mp4（文件形式）。"""
        proj = os.path.join(str(tmp_path), "group", name)
        rc = os.path.join(proj, "02_抽卡素材", "03_粗剪")
        os.makedirs(rc, exist_ok=True)
        for ed, eps in editors.items():
            for ep in eps:
                open(os.path.join(rc, "%d-%s.mp4" % (ep, ed)), "w").close()
        return rc

    def _setup_settings(self, eng, tmp_path, my_editor):
        local_root = os.path.join(str(tmp_path), "local")
        eng.db.set_setting("local_project_root", local_root)
        eng.db.set_setting("local_project_template", "")
        eng.db.set_setting("my_editor_name", my_editor)

    def test_create_and_pull_material(self, tmp_path):
        from local_project import create_local_project, _next_seq
        eng = self._engine(tmp_path)
        self._mk_group_project(tmp_path, eng, "测试项目", {"张三": [1, 2, 3], "李四": [4, 5, 6]})
        self._setup_settings(eng, tmp_path, "张三")

        ok, msg, stats = create_local_project(eng, "测试项目")
        assert ok is True, msg
        # 我负责 1-3 集，应拉 3 个素材文件
        assert stats["material_copied"] == 3
        assert stats["script_copied"] == 1
        # 序号应为 001
        assert stats["seq"] == 1
        assert stats["local_dir_name"] == "001-测试项目"
        # 本地项目文件夹存在
        local_proj = os.path.join(str(tmp_path), "local", "001-测试项目")
        assert os.path.isdir(local_proj)
        # 素材在 01原素材/第N集 剪辑师/，有第1/2/3集，没有第4/5/6集
        mat_dir = os.path.join(local_proj, "01原素材")
        assert os.path.isdir(mat_dir)
        assert os.path.isdir(os.path.join(mat_dir, "第1集 张三"))
        assert os.path.isdir(os.path.join(mat_dir, "第3集 张三"))
        assert not os.path.isdir(os.path.join(mat_dir, "第4集 李四"))

    def test_seq_increments(self, tmp_path):
        from local_project import create_local_project, _next_seq
        eng = self._engine(tmp_path)
        self._mk_group_project(tmp_path, eng, "项目A", {"张三": [1]})
        self._setup_settings(eng, tmp_path, "张三")
        local_root = os.path.join(str(tmp_path), "local")

        # 预置一些已有序号目录
        os.makedirs(local_root, exist_ok=True)
        for i in [1, 2, 3]:
            os.makedirs(os.path.join(local_root, "%03d-旧项目" % i), exist_ok=True)
        assert _next_seq(local_root) == 4

        ok, msg, stats = create_local_project(eng, "项目A")
        assert ok is True
        assert stats["seq"] == 4
        assert stats["local_dir_name"] == "004-项目A"
        assert os.path.isdir(os.path.join(local_root, "004-项目A"))

        # 再建一个，序号应为 5
        self._mk_group_project(tmp_path, eng, "项目B", {"张三": [1]})
        ok2, msg2, stats2 = create_local_project(eng, "项目B")
        assert ok2 is True
        assert stats2["seq"] == 5
        assert stats2["local_dir_name"] == "005-项目B"

    def test_no_editor_match(self, tmp_path):
        from local_project import create_local_project
        eng = self._engine(tmp_path)
        self._mk_group_project(tmp_path, eng, "测试项目", {"张三": [1, 2, 3]})
        self._setup_settings(eng, tmp_path, "不存在的剪辑师")
        ok, msg, stats = create_local_project(eng, "测试项目")
        assert ok is False
        assert "未找到" in msg or "负责的集数" in msg

    def test_no_local_root(self, tmp_path):
        from local_project import create_local_project
        eng = self._engine(tmp_path)
        self._mk_group_project(tmp_path, eng, "测试项目", {"张三": [1, 2, 3]})
        eng.db.set_setting("local_project_root", "")
        eng.db.set_setting("my_editor_name", "张三")
        ok, msg, stats = create_local_project(eng, "测试项目")
        assert ok is False
        assert "本地项目盘" in msg

    def test_only_pull_my_episodes(self, tmp_path):
        """只拉我负责的集，结构目录（01_抽卡素材）不误判为集号。"""
        from local_project import create_local_project
        eng = self._engine(tmp_path)
        # 我(张三)负责 1、2 集，其他人负责 3-6 集
        self._mk_group_project(tmp_path, eng, "测试项目",
                               {"张三": [1, 2], "李四": [3, 4, 5, 6]})
        self._setup_settings(eng, tmp_path, "张三")

        ok, msg, stats = create_local_project(eng, "测试项目")
        assert ok is True, msg
        # 只拉 2 个文件（第1、2集各1个文件）
        assert stats["material_copied"] == 2
        # 素材目录里只有第1、2集，没有第3-6集
        mat_dir = os.path.join(str(tmp_path), "local", "001-测试项目", "01原素材")
        names = os.listdir(mat_dir)
        assert len(names) == 2
        assert "第1集 张三" in names
        assert "第2集 张三" in names
        assert not any("第3集" in n or "第4集" in n for n in names)

    def test_pull_roughcut_files(self, tmp_path):
        """粗剪文件（03_粗剪/集号-剪辑师.mp4）应正确拉取到 01原素材/第N集。"""
        from local_project import create_local_project
        eng = self._engine(tmp_path)
        self._mk_group_project(tmp_path, eng, "测试项目",
                               {"张三": [1, 2], "李四": [3, 4, 5, 6]})
        self._mk_roughcut(tmp_path, "测试项目",
                          {"张三": [1, 2], "李四": [3, 4, 5, 6]})
        self._setup_settings(eng, tmp_path, "张三")

        ok, msg, stats = create_local_project(eng, "测试项目")
        assert ok is True, msg
        # 只拉我负责的 2 个粗剪文件（第1、2集），不是全部 6 个
        assert stats["roughcut_copied"] == 2
        # 粗剪文件在 01原素材/第N集 剪辑师/ 里
        mat_dir = os.path.join(str(tmp_path), "local", "001-测试项目", "01原素材")
        assert "1-张三.mp4" in os.listdir(os.path.join(mat_dir, "第1集 张三"))
        assert "2-张三.mp4" in os.listdir(os.path.join(mat_dir, "第2集 张三"))
