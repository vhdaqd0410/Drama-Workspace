"""SyncEngine 薄壳：从四个 Mixin 组装。"""
import os
import json
import threading
import queue
import logging
import time
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
        self._local_project_tasks = {}  # project_name -> {status, stage, done, total, message, result}
        # 同步任务心跳：project_name -> {'started': ts, 'last': ts}
        # 用“最后活动时间”判断同步是否已静默死亡（进程还在、任务没了）。
        self._sync_heartbeat = {}
        self._lock = threading.RLock()  # 保护上面两个共享字典
        self._dept_labels = config["nas"].get("production_labels", {})
        self._unc_map = config["nas"].get("unc_map", {})
        self._delivery_check_running = False  # 防止重复后台检测
        # get_delivery_stats 短时缓存：交付文件数量短时间内不变，避免每次 /api/projects
        # 都对"待交付/已完成"项目逐个全目录扫描（N+1 性能瓶颈）。
        self._delivery_stats_cache = {}     # project_name -> (ts, result)
        self._delivery_stats_ttl = 20.0     # 秒
        # 交付统计持久化缓存：重启后首页不必重新扫 200+ 个 NAS 项目目录
        # （每个项目要 5~15 次 NAS 往返，冷启动累积 40 秒以上）
        self._delivery_stats_disk_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "delivery_stats_cache.json")
        self._delivery_stats_dirty = False
        self._delivery_stats_warming = False
        self._load_delivery_stats_disk_cache()
        self._delivery_folder = config.get(
            "delivery_folder", r"C:\Users\Admin\Desktop\000交付")
        self._sse_clients = []       # 活跃 SSE 客户端队列列表
        # /api/projects 结果缓存：短 TTL + 写操作主动失效，兼顾性能与实时性
        self._projects_cache = {"data": None, "mtime": 0.0}
        self._projects_cache_lock = threading.RLock()
        # 注册项目数据变更钩子：任何写操作后失效缓存
        try:
            from db import register_projects_changed_hook
            register_projects_changed_hook(self.invalidate_projects_cache)
        except Exception:
            pass
        # 持久化缓存：上映单集版目录查找结果落盘，重启后免全量重扫
        self._output_dir_cache_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "output_dirs_cache.json")
        self._last_cache_save_size = -1  # 缓存写盘节流阈值
        self._load_output_dir_cache()

    # ===== 交付统计持久化缓存 =====
    # 背景：get_delivery_stats 每个项目要 5~15 次 NAS 往返（isdir/listdir + 逐子目录计数）。
    # /api/projects 会给所有「待交付/已完成」项目逐个算，208 个已完成项目冷启动
    # 累积 40 秒以上，导致首页长时间转圈。改法：
    #   1. 首页只读缓存（peek），绝不在这里触发扫盘
    #   2. 后台线程预热，算完落盘
    #   3. 重启后直接从磁盘读，立即能出数据

    def _load_delivery_stats_disk_cache(self):
        """从磁盘加载交付统计缓存（重启后免重扫）。"""
        try:
            if not os.path.isfile(self._delivery_stats_disk_file):
                return
            with open(self._delivery_stats_disk_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                now = time.time()
                for name, rec in data.items():
                    if isinstance(rec, dict) and "result" in rec:
                        self._delivery_stats_cache[name] = (
                            float(rec.get("ts") or 0) or now, rec["result"])
        except Exception as e:
            logger.warning("加载交付统计缓存失败，将重新预热: %s", e)

    def save_delivery_stats_disk_cache(self):
        """把交付统计缓存写盘（临时文件 + replace，避免写坏）。"""
        if not self._delivery_stats_dirty:
            return False
        try:
            now = time.time()
            snapshot = {}
            for name, rec in list(self._delivery_stats_cache.items()):
                try:
                    ts, result = rec
                except Exception:
                    continue
                snapshot[name] = {"ts": float(ts), "result": result}
            tmp = self._delivery_stats_disk_file + ".tmp"
            os.makedirs(os.path.dirname(self._delivery_stats_disk_file), exist_ok=True)
            for _attempt in range(2):
                try:
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(snapshot, f, ensure_ascii=False)
                    os.replace(tmp, self._delivery_stats_disk_file)
                    self._delivery_stats_dirty = False
                    return True
                except PermissionError:
                    time.sleep(0.15)
            return False
        except Exception as e:
            logger.warning("保存交付统计缓存失败: %s", e)
            return False

    def peek_delivery_stats(self, project_name, max_age=None):
        """只读交付统计缓存，不扫盘。无缓存返回 None。

        max_age=None 表示不限时效（首页优先快速出数据，旧数据也比转圈好）；
        传入秒数时超过该年龄返回 None。
        """
        rec = self._delivery_stats_cache.get(project_name)
        if not rec:
            return None
        try:
            ts, result = rec
        except Exception:
            return None
        if max_age is not None and (time.time() - float(ts)) > max_age:
            return None
        return result

    def start_delivery_stats_warmup(self, names):
        """后台预热交付统计（不阻塞请求）。已在跑则不重复启动。"""
        if self._delivery_stats_warming:
            return False
        todo = [n for n in (names or []) if n]
        if not todo:
            return False
        self._delivery_stats_warming = True

        def _worker():
            try:
                done = 0
                for name in todo:
                    try:
                        # 已有较新缓存则跳过
                        rec = self._delivery_stats_cache.get(name)
                        if rec and (time.time() - float(rec[0])) < 300:
                            continue
                        result = self.get_delivery_stats(name)
                        self._delivery_stats_cache[name] = (time.time(), result)
                        self._delivery_stats_dirty = True
                        done += 1
                        if done % 25 == 0:
                            self.save_delivery_stats_disk_cache()
                    except Exception as e:
                        logger.debug("预热交付统计失败 %s: %s", name, e)
                if self._delivery_stats_dirty:
                    self.save_delivery_stats_disk_cache()
                if done:
                    logger.info("交付统计预热完成: %d 个项目", done)
                    # 通知前端刷新（卡片进度条从旧值变新值）
                    try:
                        self._sse_publish({"type": "projects_changed",
                                           "reason": "delivery_stats_warmed"})
                    except Exception:
                        pass
            finally:
                self._delivery_stats_warming = False

        t = threading.Thread(target=_worker, name="delivery-stats-warmup", daemon=True)
        t.start()
        return True

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
        """把目录缓存写盘。返回 True 表示成功。

        用临时文件 + 替换，避免写入中断损坏缓存。文件可能被杀软或并发线程短暂
        锁定（WinError 5），做一次短暂重试后再放弃，降低偶发失败噪音。
        """
        try:
            with self._lock:
                data = dict(self._output_dir_cache)
            tmp = self._output_dir_cache_file + ".tmp"
            import time as _t
            for _attempt in range(2):
                try:
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False)
                    os.replace(tmp, self._output_dir_cache_file)
                    return True
                except PermissionError:
                    # 文件被占用，短暂等待后重试一次
                    _t.sleep(0.15)
            logger.warning("保存目录缓存失败(重试后仍失败): 文件被占用 %s",
                           self._output_dir_cache_file)
            return False
        except Exception as e:
            logger.warning("保存目录缓存失败: %s", e)
            return False

