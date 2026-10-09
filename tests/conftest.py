# -*- coding: utf-8 -*-
"""pytest fixtures：构造临时 config / db / SyncEngine，避免污染真实数据。

另外在这里做一道「测试进程禁止拉起外部程序」的全局硬防线：
曾发生过测试直接调用 create_local_project() 而真实启动 Premiere 的事故，
把临时工程塞进用户的 PR 并污染「最近使用项目」。下面用 autouse fixture
拦截 subprocess.Popen / os.startfile，让任何测试（含以后新写的）都物理上
开不了外部窗口，而不是依赖每个测试自觉传开关。
"""
import os
import sys
import shutil
import subprocess
import tempfile
import yaml
import pytest

# 让 backend 可导入
BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, BACKEND)

# 测试里允许运行的命令行工具（无窗口 / 纯控制台）。不在此列的 executable
# 一律拦截，避免误开 PR、达芬奇、浏览器、资源管理器等 GUI 程序。
_ALLOWED_EXES = {
    "robocopy", "robocopy.exe",
    "cmd", "cmd.exe",
    "mkdir",
    "git", "git.exe",
    "node", "node.exe",
    os.path.basename(sys.executable).lower(),
    "python", "python.exe", "pythonw.exe",
}


def _exe_of(args):
    """从 Popen 的首个参数里取出可执行文件名（小写）。"""
    if isinstance(args, (list, tuple)) and args:
        first = args[0]
    else:
        first = args
    if not isinstance(first, str):
        # bytes / PathLike / shell 字符串等，取 basename 兜底
        try:
            first = os.fspath(first)
            if isinstance(first, bytes):
                first = first.decode("utf-8", "replace")
        except Exception:
            return ""
        return os.path.basename(first).strip('"').split()[0].lower() if first else ""
    first = first.strip().strip('"')
    return os.path.basename(first.split()[0]).lower() if first else ""


@pytest.fixture(autouse=True)
def _ban_external_launch(monkeypatch):
    """所有测试自动生效：禁止启动外部程序（PR / 达芬奇 / 浏览器 / 资源管理器…）。

    只允许控制台工具（robocopy / cmd / mkdir / git / node / python）。
    需要放行新的命令行工具时，把它加进 _ALLOWED_EXES。
    """
    real_popen = subprocess.Popen
    real_startfile = getattr(os, "startfile", None)
    blocked = []

    class _GuardedPopen(real_popen):
        def __init__(self, args, *a, **kw):
            exe = _exe_of(args)
            if exe and exe not in _ALLOWED_EXES:
                blocked.append(exe)
                raise RuntimeError(
                    "[测试防线] 禁止在测试中启动外部程序: %r。\n"
                    "若确需启动，请把该工具加入 tests/conftest.py 的 _ALLOWED_EXES，"
                    "或改为 mock。" % exe
                )
            super().__init__(args, *a, **kw)

    monkeypatch.setattr(subprocess, "Popen", _GuardedPopen, raising=False)

    if real_startfile is not None:
        def _guarded_startfile(path, *a, **kw):
            blocked.append(str(path))
            raise RuntimeError(
                "[测试防线] 禁止在测试中调用 os.startfile 打开外部文件: %r" % path
            )
        monkeypatch.setattr(os, "startfile", _guarded_startfile, raising=False)

    yield blocked


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
