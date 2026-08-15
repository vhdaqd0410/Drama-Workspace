# -*- coding: utf-8 -*-
"""pytest fixtures：构造临时 config / db / SyncEngine，避免污染真实数据。"""
import os
import sys
import tempfile
import yaml
import pytest

# 让 backend 可导入
BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, BACKEND)


@pytest.fixture()
def base_config():
    """最小可用 config（用临时 group_root）。"""
    tmp = tempfile.mkdtemp(prefix="wb_test_")
    return {
        "nas": {
            "group_root": os.path.join(tmp, "group"),
            "production_roots": [os.path.join(tmp, "prod")],
            "production_labels": {},
            "unc_map": {},
        },
        "sync": {"mode": "full", "exclude_patterns": []},
        "output_dir_name": "01上映单集版",
        "delivery_folder": os.path.join(tmp, "000交付"),
        "watcher": {"enabled": False, "stable_seconds": 30, "extensions": [".mp4"]},
        "special_projects": {},
        "web": {"host": "127.0.0.1", "port": 8089, "api_secret": "test"},
        "logging": {"level": "ERROR"},
        "fenmiaozhen": {"enabled_departments": [], "web_url": "", "desktop_scheme": "", "open_folder": False},
        "players": {"potplayer_path": ""},
    }


@pytest.fixture()
def tmp_db(base_config, tmp_path):
    """临时数据库实例。"""
    from db import Database
    db_path = str(tmp_path / "test.db")
    db = Database(db_path=db_path)
    yield db
    try:
        db.close_all()
    except Exception:
        pass


@pytest.fixture()
def engine(base_config, tmp_db):
    """构造 SyncEngine（临时 config + 临时 db）。"""
    from sync_engine import SyncEngine
    eng = SyncEngine(base_config, tmp_db)
    yield eng
