# -*- coding: utf-8 -*-
"""数据库自动备份服务（融合自「项目档案管理器」backupService）。

- 每日自动备份 SQLite 数据库到 data/backups/，保留最近 MAX_BACKUPS 份
- 手动备份 / 恢复
- 恢复前先备份当前数据库（可反悔）
"""
import os
import shutil
import logging
import threading
from datetime import datetime

logger = logging.getLogger("backup")

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_BASE, "data")
BACKUP_DIR = os.path.join(_DATA_DIR, "backups")
MAX_BACKUPS = 7

_timer = None


def _db_path():
    # 以 config.yaml 的 database 为准（与 app.py 同源）；缺失则回退到 data/workbench.db
    cfg_path = os.path.join(_BASE, "backend", "config.yaml")
    try:
        import yaml
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        dbp = cfg.get("database") or ""
        if dbp:
            return dbp
    except Exception:
        pass
    return os.path.join(_DATA_DIR, "workbench.db")


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def list_backups():
    """返回备份列表，按新到旧：[{name, size, mtime}]"""
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        out = []
        for f in os.listdir(BACKUP_DIR):
            if f.startswith("archive-") and f.endswith(".db"):
                p = os.path.join(BACKUP_DIR, f)
                try:
                    st = os.stat(p)
                    out.append({
                        "name": f,
                        "size": st.st_size,
                        "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    })
                except Exception:
                    pass
        out.sort(key=lambda x: x["name"], reverse=True)
        return out
    except Exception:
        return []


def backup_now():
    """立即可备份，返回最新备份 dict 或 None。"""
    dbp = _db_path()
    if not os.path.isfile(dbp):
        return None
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        backup_path = os.path.join(BACKUP_DIR, "archive-" + _today() + ".db")
        # 今日已备份则跳过
        if not os.path.exists(backup_path):
            shutil.copy2(dbp, backup_path)
            logger.info("已备份到 %s", backup_path)
        # 清理超限旧备份
        backups = sorted([f for f in os.listdir(BACKUP_DIR)
                          if f.startswith("archive-") and f.endswith(".db")],
                         reverse=True)
        for old in backups[MAX_BACKUPS:]:
            try:
                os.remove(os.path.join(BACKUP_DIR, old))
            except Exception:
                pass
        lst = list_backups()
        return lst[0] if lst else {"name": os.path.basename(backup_path),
                                   "size": os.path.getsize(backup_path),
                                   "mtime": _today()}
    except Exception as e:
        logger.error("备份失败: %s", e)
        raise


def restore(backup_name):
    """从备份恢复数据库。先备份当前库（可反悔）。"""
    if not backup_name or not backup_name.startswith("archive-") or not backup_name.endswith(".db"):
        raise ValueError("无效的备份文件名")
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    if not os.path.isfile(backup_path):
        raise FileNotFoundError("备份文件不存在")
    dbp = _db_path()
    os.makedirs(BACKUP_DIR, exist_ok=True)
    # 备份当前数据库（防止恢复后反悔）
    pre = os.path.join(BACKUP_DIR, "archive-pre-restore-" + str(int(datetime.now().timestamp())) + ".db")
    try:
        if os.path.isfile(dbp):
            shutil.copy2(dbp, pre)
    except Exception:
        pass
    # 关闭 WAL 后替换
    try:
        import sqlite3
        sqlite3.connect(dbp).close()
    except Exception:
        pass
    shutil.copy2(backup_path, dbp)
    logger.info("已从 %s 恢复数据库", backup_name)
    return True


def _check_and_backup():
    try:
        backup_now()
    except Exception as e:
        logger.error("定时备份异常: %s", e)


def start_scheduler():
    """启动每日备份后台线程。幂等。"""
    global _timer
    if _timer is not None:
        return
    def _loop():
        # 启动后 60s 首次检查，之后每 6 小时检查一次（今日已备份则跳过）
        while True:
            _check_and_backup()
            import time
            time.sleep(6 * 60 * 60)
    _timer = threading.Thread(target=_loop, daemon=True)
    _timer.start()
    logger.info("数据备份服务已启动")
