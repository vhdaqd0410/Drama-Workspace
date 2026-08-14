"""SyncEngine 薄壳：从四个 Mixin 组装。"""
import threading
import queue
from scan import ScanMixin, _natural_key, find_dir_recursive, _quick_find_file
from sync import SyncMixin
from deliver import DeliverMixin
from preview import PreviewMixin


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
        self._delivery_folder = config.get(
            "delivery_folder", r"C:\Users\Admin\Desktop\000交付")
        self._sse_clients = []       # 活跃 SSE 客户端队列列表
