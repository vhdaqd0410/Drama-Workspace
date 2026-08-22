"""成片目录监听器 - 递归查找并监听所有 01上映单集版 目录"""
import os
import time
import shutil
import logging
import threading

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    Observer = None
    FileSystemEventHandler = object

from sync_engine import find_dir_recursive
from output_dir_util import get_output_dir_name as _resolve_output_dir_name

logger = logging.getLogger(__name__)


class StableFileDetector:
    """文件稳定检测器：文件大小连续 N 秒不变则认为写入完成"""

    def __init__(self, stable_seconds=30):
        self.stable_seconds = stable_seconds
        self._tracked = {}
        self._lock = threading.Lock()

    def update(self, path):
        try:
            size = os.path.getsize(path)
        except OSError:
            return False
        now = time.time()
        with self._lock:
            prev = self._tracked.get(path)
            if prev and prev[0] == size:
                if now - prev[1] >= self.stable_seconds:
                    del self._tracked[path]
                    return True
            else:
                self._tracked[path] = (size, now)
        return False


class DeliveryHandler(FileSystemEventHandler):
    def __init__(self, watcher):
        self.watcher = watcher

    def on_created(self, event):
        if not event.is_directory:
            self.watcher._check_file(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self.watcher._check_file(event.src_path)


class Watcher:
    """成片目录监听器 — 递归查找并监听所有 01上映单集版"""

    def __init__(self, config, db):
        self.config = config
        self.db = db
        self.nas = config["nas"]
        self.output_dir_name = config.get("output_dir_name",
                                          "01上映单集版")
        self.watcher_cfg = config.get("watcher", {})
        self.special_projects = config.get("special_projects", {}) or {}
        self.enabled = self.watcher_cfg.get("enabled", True)
        self.stable_seconds = self.watcher_cfg.get("stable_seconds", 30)
        self.extensions = [
            e.lower() for e in self.watcher_cfg.get(
                "extensions", [".mp4", ".mov"])]
        self.detector = StableFileDetector(self.stable_seconds)
        if Observer is None:
            self.enabled = False
            self.observer = None
            logger.warning('watchdog 未安装，Watcher 已禁用 (pip install watchdog)')
        else:
            self.observer = Observer()
        self._watched_dirs = {}
        self._timer = None
        self._retry_queue = []   # [(file_path, retry_count), ...]
        self._max_retries = 3
        self._started = False    # 幂等保护，防止重复启动

    def _get_output_dir_name(self, project_name):
        # 统一走 output_dir_util 解析，避免与 sync.py 的拷贝漂移
        try:
            return _resolve_output_dir_name(self.db, self.config, project_name)
        except Exception:
            pass
        if project_name in self.special_projects:
            return self.special_projects[project_name].get(
                "output_dir_name", self.output_dir_name)
        return self.output_dir_name

    def start(self):
        if not self.enabled:
            logger.info("成片监听已禁用")
            return
        if self._started:
            return  # 幂等：已启动则忽略
        self._started = True
        self._refresh_watches()
        self._timer = threading.Timer(60, self._refresh_loop)
        self._timer.daemon = True
        self._timer.start()
        self.observer.start()
        logger.info("成片监听已启动")

    def stop(self):
        if self._timer:
            self._timer.cancel()
        self.observer.stop()
        self.observer.join()
        logger.info("成片监听已停止")

    def is_alive(self):
        return self.observer.is_alive() if self.enabled else False

    def _refresh_loop(self):
        self._refresh_watches()
        self._process_retry_queue()
        self._timer = threading.Timer(60, self._refresh_loop)
        self._timer.daemon = True
        self._timer.start()

    def _refresh_watches(self):
        """扫描组内 NAS，递归查找每个项目的 01上映单集版 目录并设置监听"""
        group_root = self.nas["group_root"]
        if not os.path.isdir(group_root):
            return

        for name in os.listdir(group_root):
            proj_dir = os.path.join(group_root, name)
            if not os.path.isdir(proj_dir):
                continue

            dir_name = self._get_output_dir_name(name)
            output_dirs = find_dir_recursive(proj_dir, dir_name)

            for od in output_dirs:
                if od not in self._watched_dirs:
                    handler = DeliveryHandler(self)
                    watch = self.observer.schedule(
                        handler, od, recursive=True)
                    self._watched_dirs[od] = watch
                    # debug 级别：每次启动会一次性监听数百个目录，用 info 会刷屏撑大日志
                    logger.debug("监听成片目录: %s", od)

    def _check_file(self, file_path):
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in self.extensions:
            return
        if not self.detector.update(file_path):
            return
        def _try_deliver():
            try:
                self._deliver(file_path)
            except Exception:
                already = any(qp == file_path for qp, _ in self._retry_queue)
                if not already:
                    self._retry_queue.append((file_path, 1))
        threading.Thread(target=_try_deliver, daemon=True).start()

    def _deliver(self, file_path):
        """自动回传成片到制作部 NAS 对应项目的 01上映单集版 目录"""
        group_root = self.nas["group_root"]
        try:
            rel = os.path.relpath(file_path, group_root)
        except ValueError:
            return

        parts = rel.split(os.sep)
        if not parts:
            return

        project_name = parts[0]
        proj = self.db.get_project(project_name)
        if not proj:
            logger.warning("回传失败：项目未注册 %s", project_name)
            return

        filename = os.path.basename(file_path)

        # 递归查找制作部 NAS 中该项目的 01上映单集版 目录
        dir_name = self._get_output_dir_name(project_name)
        prod_output_dirs = find_dir_recursive(
            proj["production_path"], dir_name)

        if not prod_output_dirs:
            logger.warning("回传失败：制作部项目目录中未找到 %s: %s",
                          dir_name, proj["production_path"])
            self.db.add_delivery_log(
                project_name, filename, file_path, "",
                0, "error", "制作部未找到 %s 目录" % dir_name)
            return

        dst_dir = prod_output_dirs[0]
        dst = os.path.join(dst_dir, filename)

        try:
            file_size = os.path.getsize(file_path)
            shutil.copy2(file_path, dst)
            now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            self.db.add_delivery_log(
                project_name, filename, file_path, dst, file_size,
                "success", "自动监听回传成功")
            self.db.update_project_status(
                project_name, delivery_status="delivered",
                last_delivered_at=now)
            logger.info("自动回传成功: %s -> %s", filename, dst)
        except Exception as e:
            self.db.add_delivery_log(
                project_name, filename, file_path, dst, 0,
                "error", "自动回传失败: " + str(e))
            logger.error("自动回传失败: %s", e)

    def _process_retry_queue(self):
        """处理 _deliver 失败的自动回传重试队列，最多重试 _max_retries 次"""
        if not self._retry_queue:
            return
        remaining = []
        for file_path, count in self._retry_queue:
            if count > self._max_retries:
                logger.error("放弃自动回传（已重试 %d 次）: %s",
                             self._max_retries, os.path.basename(file_path))
                continue
            logger.info("自动回传重试 (%d/%d): %s", count, self._max_retries,
                        os.path.basename(file_path))
            try:
                self._deliver(file_path)
            except Exception as e:
                logger.warning("重试调度异常: %s", e)
            # _deliver 内部如果再次失败会重新入队 count+1
            # 我们这里显式追加一次，确保 count 正确递增
            if os.path.isfile(file_path):
                remaining.append((file_path, count + 1))
        self._retry_queue = remaining
