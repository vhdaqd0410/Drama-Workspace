# -*- coding: utf-8 -*-
"""版本号 & 配置收敛单元测试。"""
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


# ============================================================
# 1. version.py — 统一版本号来源
# ============================================================

class TestVersion:
    def test_importable(self):
        import version
        assert hasattr(version, "VERSION")
        assert hasattr(version, "APP_TITLE")
        assert hasattr(version, "APP_NAME")

    def test_version_format(self):
        import version
        # 语义化版本号：主.次.修订
        parts = version.VERSION.split(".")
        assert len(parts) == 3
        for p in parts:
            assert p.isdigit()

    def test_app_title_contains_version(self):
        import version
        assert version.VERSION in version.APP_TITLE
        assert version.APP_NAME in version.APP_TITLE

    def test_consistent_across_entrypoints(self):
        """各入口应统一引用 version 模块，避免运行时硬编码漂移。"""
        import version
        base = os.path.dirname(BACKEND)
        # 运行时展示的标题应来自 version.APP_TITLE，而非散落的字面量
        for rel in ("main.py", "main_desktop.py"):
            path = os.path.join(base, rel)
            with open(path, "r", encoding="utf-8") as f:
                src = f.read()
            assert "APP_TITLE" in src, f"{rel} 未引用 APP_TITLE"
            # 不应再出现旧的硬编码窗口/托盘标题字面量（v2.1 时代遗留）
            assert "🎬 视频工作台 v2." not in src, f"{rel} 仍含硬编码版本标题"


# ============================================================
# 2. 配置收敛 — main.py 从 config.yaml 读取服务端口
# ============================================================

class TestConfigConvergence:
    def test_main_loads_server_from_yaml(self):
        """main.py 的 load_server_config 应从 config.yaml 读取，而非 JSON。"""
        sys.path.insert(0, os.path.dirname(BACKEND))
        import main as m
        srv = m.load_server_config()
        assert isinstance(srv.get("port"), int)
        assert srv.get("port") > 0

    def test_main_config_points_to_yaml(self):
        import main as m
        assert os.path.isfile(m.CONFIG_YAML)
        assert m.CONFIG_YAML.endswith("config.yaml")

    def test_enhanced_routes_reads_nas_from_yaml(self):
        """enhanced_routes 的 NAS 路径读取应与 app.py 同源（config.yaml）。"""
        import enhanced_routes as er
        group = er._yaml_get("nas.group_root", "")
        # config.yaml 里配了组内 NAS 根目录；若为空说明读取链路断了
        assert group != "", "enhanced_routes 未能从 config.yaml 读到 group_root"
