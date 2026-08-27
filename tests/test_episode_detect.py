# -*- coding: utf-8 -*-
"""自动推断总集数算法测试。"""
import os
import sys
import pytest

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


class TestEpisodeDetection:
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

    def _mk_project(self, eng, tmp_path, name, folders):
        """建项目，folders 为 {相对路径: 集号} 映射，用于建素材目录。"""
        proj = os.path.join(str(tmp_path), "group", name)
        os.makedirs(proj, exist_ok=True)
        eng.db.upsert_project(name, "", proj, source_root="")
        # 建素材文件夹
        mat = os.path.join(proj, "03 视频素材")
        for rel, ep in folders.items():
            p = os.path.join(mat, rel)
            os.makedirs(p, exist_ok=True)
            # 若 rel 本身不含集号，用文件名携带集号
            open(os.path.join(p, "第%d集.mp4" % ep), "w").close()
        return proj

    def test_extract_episode_formats(self):
        from sync import SyncMixin
        f = SyncMixin._extract_episode_number_from_name
        assert f("第10集@王金辉") == 10
        assert f("07_回片场") == 7
        assert f("10@陈婷婷") == 10
        assert f("10-1-v01_花絮.mp4") == 10
        assert f("7-1-v01_剪辑.mp4") == 7
        assert f("第1集 花絮") == 1
        assert f("无集号文件夹") is None

    def test_detect_from_video_mat(self, tmp_path):
        eng = self._engine(tmp_path)
        self._mk_project(eng, tmp_path, "P1", {"第1集 花絮": 1, "第2集 花絮": 2, "第70集 花絮": 70})
        assert eng.auto_detect_total_episodes("P1") == 70

    def test_detect_from_num_underscore(self, tmp_path):
        eng = self._engine(tmp_path)
        self._mk_project(eng, tmp_path, "P2", {"07_回片场": 7, "08_回片场": 8, "09_回片场": 9})
        assert eng.auto_detect_total_episodes("P2") == 9

    def test_detect_nested(self, tmp_path):
        """抽卡素材在二级子文件夹。"""
        eng = self._engine(tmp_path)
        self._mk_project(eng, tmp_path, "P3", {"01_抽卡素材/10@王金辉": 10, "01_抽卡素材/50@李四": 50})
        assert eng.auto_detect_total_episodes("P3") == 50

    def test_no_material_folder(self, tmp_path):
        eng = self._engine(tmp_path)
        proj = os.path.join(str(tmp_path), "group", "P4")
        os.makedirs(proj, exist_ok=True)
        eng.db.upsert_project("P4", "", proj, source_root="")
        assert eng.auto_detect_total_episodes("P4") == 0

    def test_auto_set_only_when_zero(self, tmp_path):
        eng = self._engine(tmp_path)
        self._mk_project(eng, tmp_path, "P5", {"第1集": 1, "第30集": 30})
        ok, msg, det = eng.auto_set_total_episodes("P5")
        assert ok is True and det == 30
        assert eng.db.get_project("P5")["total_episodes"] == 30
        # 再次调用：已有集数则不再覆盖
        ok2, msg2, det2 = eng.auto_set_total_episodes("P5")
        assert "已有" in msg2

    def test_detect_from_production_path(self, tmp_path):
        """制作部项目（只有 production_path，无 group_path）也能推断。"""
        eng = self._engine(tmp_path)
        # 建一个只有 production_path 的项目
        prod = os.path.join(str(tmp_path), "prod", "P6")
        mat = os.path.join(prod, "02_抽卡素材", "01_抽卡素材")
        os.makedirs(mat, exist_ok=True)
        for ep in [1, 2, 66]:
            d = os.path.join(mat, "第%d集 花絮" % ep)
            os.makedirs(d, exist_ok=True)
            open(os.path.join(d, "x.mp4"), "w").close()
        eng.db.upsert_project("P6", prod, "", source_root="")
        assert eng.auto_detect_total_episodes("P6") == 66
