"""SyncEngine 薄壳：从四个 Mixin 组装。"""
import os
import json
import threading
import queue
import logging
from scan import ScanMixin, _natural_key, find_dir_recursive, _quick_find_file
from sync import SyncMixin
from deliver import DeliverMixin
from preview import PreviewMixin

logger = logging.getLogger("sync_engine")


class SyncEngine(ScanMixin, SyncMixin, DeliverMixin, PreviewMixin):
    def __init__(self, config, db):
        self.config = config
        self.db = db
        self.nas = config["nas"]
        self.sync_cfg = config.get("sync", {})
        self.output_dir_name = config.get("output_dir_name",
                                          "01上映单集版")
        self.special_projects = config.get("special_projects", {}) or {}
        self._output_dir_cache = {}  # 缓存递归查找结果
        self._deliver_tasks = {}      # project_name -> {status, total, current, pct, started_at, message}
        self._lock = threading.RLock()  # 保护上面两个共享字典
        self._dept_labels = config["nas"].get("production_labels", {})
        self._unc_map = config["nas"].get("unc_map", {})
        self._delivery_check_running = False  # 防止重复后台检测
        # get_delivery_stats 短时缓存：交付文件数量短时间内不变，避免每次 /api/projects
        # 都对"待交付/已完成"项目逐个全目录扫描（N+1 性能瓶颈）。20 秒内命中缓存。
        self._delivery_stats_cache = {}     # project_name -> (ts, result)
        self._delivery_stats_ttl = 20.0     # 秒
        self._delivery_folder = config.get(
            "delivery_folder", r"C:\Users\Admin\Desktop\000交付")
        self._sse_clients = []       # 活跃 SSE 客户端队列列表
        # 持久化缓存：上映单集版目录查找结果落盘，重启后免全量重扫
        self._output_dir_cache_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "output_dirs_cache.json")
        self._last_cache_save_size = -1  # 缓存写盘节流阈值
        self._load_output_dir_cache()

    def _load_output_dir_cache(self):
        """从磁盘加载上映单集版目录缓存（重启后免重扫）。"""
        try:
            if not os.path.isfile(self._output_dir_cache_file):
                return
            with open(self._output_dir_cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._output_dir_cache = data
        except Exception as e:
            logger.warning("加载目录缓存失败，将重新扫描: %s", e)
            self._output_dir_cache = {}

    def _save_output_dir_cache(self):
        """把目录缓存写盘。失败不影响主流程。"""
        try:
            with self._lock:
                data = dict(self._output_dir_cache)
            # 用临时文件 + 替换，避免写入中断损坏缓存
            tmp = self._output_dir_cache_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, self._output_dir_cache_file)
        except Exception as e:
            logger.warning("保存目录缓存失败: %s", e)

