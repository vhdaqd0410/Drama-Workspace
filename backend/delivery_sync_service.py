# -*- coding: utf-8 -*-
"""交付日期定时同步服务。

- 周期性地从分集目标表格读取胶片日期，自动更新项目 delivered_date（补录）
- 幂等：仅当存在可用的目标文件时才执行，失败不影响主服务
- 用 daemon 线程，与 backup_service 同模式
"""
import os
import logging
import threading
from datetime import datetime

logger = logging.getLogger("delivery_sync")

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_BASE, "data")
TARGET_DIR = os.path.join(_DATA_DIR, "fenji_targets")

_timer = None


def _settings_value(key):
    """读取 config.yaml 里的 setting（简化读取，供解析目标文件路径用）。"""
    try:
        cfg_path = os.path.join(_BASE, "backend", "config.yaml")
        import yaml
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return cfg.get(key) or cfg.get("settings", {}).get(key) or ""
    except Exception:
        return ""


def _resolve_target():
    """目标文件路径：settings.fj_target_path → 最近的目标文件。"""
    try:
        from db import db as _db
        try:
            t = _db.get_all_settings().get("fj_target_path", "") or ""
        except Exception:
            t = ""
        if not t:
            t = _settings_value("fj_target_path")
        if t and os.path.isfile(t):
            return t
    except Exception:
        pass
    if os.path.isdir(TARGET_DIR):
        xlsx = [f for f in os.listdir(TARGET_DIR)
                if f.lower().endswith((".xlsx", ".xlsm", ".xls"))]
        if xlsx:
            return os.path.join(TARGET_DIR, sorted(xlsx)[-1])
    return ""


def run_once():
    """执行一次交付日期同步，返回本次更新项目数；无目标文件返回 0。"""
    target = _resolve_target()
    if not target:
        logger.info("定时交付同步：未找到目标文件，跳过")
        return 0
    try:
        from features import sync_delivery_dates_from_target
        from db import db as _db
        updated = sync_delivery_dates_from_target(target, _db)
        if updated:
            logger.info("定时交付同步完成：更新 %d 个项目 (%s)", len(updated), target)
        return len(updated)
    except Exception as e:
        logger.warning("定时交付同步失败: %s", e)
        return 0


def start_scheduler(interval_hours=6, delay_seconds=90):
    """启动交付日期定时同步后台线程。幂等。"""
    global _timer
    if _timer is not None:
        return
    def _loop():
        import time
        time.sleep(delay_seconds)  # 启动后延迟首次执行，避免与冷启动争抢
        while True:
            try:
                run_once()
            except Exception as e:
                logger.warning("定时交付同步循环异常: %s", e)
            time.sleep(interval_hours * 3600)
    _timer = threading.Thread(target=_loop, daemon=True)
    _timer.start()
    logger.info("交付日期定时同步服务已启动 (每 %s 小时)", interval_hours)
