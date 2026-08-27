# -*- coding: utf-8 -*-
"""制作部源项目自动扫描服务。

- 周期性地扫描制作部 NAS 源目录，自动发现新建项目并写入数据库
- 幂等：scan_projects 为 upsert，重复执行安全
- 用 daemon 线程，与 backup_service / delivery_sync_service 同模式
"""
import os
import time
import logging
import threading

logger = logging.getLogger("project_scan")

_timer = None
_sync_engine = None
_lock = threading.Lock()


def _run_once():
    """执行一次扫描。返回发现/更新的项目数；失败返回 0。"""
    global _sync_engine
    if _sync_engine is None:
        return 0
    if not _lock.acquire(blocking=False):
        return 0  # 上一次扫描还在进行，跳过本次
    try:
        names = _sync_engine.scan_projects()
        if names:
            logger.info("定时扫描制作部源完成：共 %d 个项目", len(names))
        return len(names)
    except Exception as e:
        logger.warning("定时扫描制作部源失败: %s", e)
        return 0
    finally:
        _lock.release()


def start_scheduler(sync_engine=None, interval_minutes=10, delay_seconds=120):
    """启动制作部源项目自动扫描后台线程。幂等。"""
    global _timer, _sync_engine
    if sync_engine is not None:
        _sync_engine = sync_engine
    if _timer is not None:
        return
    def _loop():
        time.sleep(delay_seconds)  # 启动后延迟首次执行，避免与冷启动争抢
        while True:
            try:
                _run_once()
            except Exception as e:
                logger.warning("定时扫描循环异常: %s", e)
            time.sleep(interval_minutes * 60)
    _timer = threading.Thread(target=_loop, daemon=True)
    _timer.start()
    logger.info("制作部源自动扫描服务已启动 (每 %d 分钟)", interval_minutes)
