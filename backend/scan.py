"""扫描职责：项目发现、分组扫描、部门识别。"""
import os
import logging
from utils import scan_dir

logger = logging.getLogger(__name__)


def _natural_key(text):
    """自然排序键：将数字段转为整数，使 '2' 排在 '10' 前面。"""
    parts = re.split(r'(\d+)', str(text))
    return [int(p) if p.isdigit() else p.lower() for p in parts]

def find_dir_recursive(base_path, target_name, max_depth=6):
    """递归搜索目录树中名为 target_name 的目录，返回所有匹配的绝对路径列表。
    这是整个方案的核心工具函数：不假定输出目录在固定位置，而是逐层搜索。
    """
    found = []
    try:
        for entry in os.scandir(base_path):
            if entry.is_dir():
                if entry.name == target_name:
                    found.append(entry.path)
                elif max_depth > 0:
                    found.extend(
                        find_dir_recursive(entry.path, target_name,
                                           max_depth - 1))
    except PermissionError:
        pass
    except OSError:
        pass
    return found

def _quick_find_file(base_path, filename, max_depth=4, timeout=2.0):
    """浅层快速查找：在 max_depth 层内用 os.scandir 找文件名，超过 timeout 秒直接放弃。
    避免在大的网络盘上 os.walk 阻塞 API。
    """
    deadline = _time.time() + timeout

    def _walk(depth, cur):
        if _time.time() > deadline:
            return None
        try:
            with os.scandir(cur) as entries:
                for e in entries:
                    if e.is_file(follow_symlinks=False) and e.name == filename:
                        return e.path
                    if e.is_dir(follow_symlinks=False) and depth > 0:
                        found = _walk(depth - 1, e.path)
                        if found:
                            return found
        except (PermissionError, OSError):
            pass
        return None

    return _walk(max_depth, base_path)



class ScanMixin:
    def _get_department_label(self, source_root):
        """从制作部源路径提取部门标签，优先用 db.extract_department 保持一致"""
        if not source_root:
            return None
        normalized = source_root.replace("/", "\\")
        # 先查配置里的硬编码标签表
        if normalized in self._dept_labels:
            return self._dept_labels[normalized]
        # 用 db 的 extract_department 智能提取（去盘符、去"中转"后缀、合并"海外"）
        if hasattr(self.db, 'extract_department'):
            result = self.db.extract_department(source_root)
            if result:
                return result
        # 最终 fallback
        return os.path.basename(source_root)

    def scan_projects(self):
        """扫描所有制作部 NAS 源中的项目列表，写入数据库。
        自动识别月份子目录（如 7月/8月），进入下一层扫描实际项目。
        """
        roots = self.nas.get("production_roots", [])
        if not roots:
            logger.error("未配置制作部 NAS 路径 (production_roots)")
            return []

        month_pattern = re.compile(r'^\d{1,2}月$')

        all_names = []
        for root in roots:
            if not os.path.isdir(root):
                logger.warning("制作部 NAS 路径不存在，跳过: %s", root)
                continue

            # 先看第一层是否都是月份目录，如果是则进入第二层
            try:
                entries = os.listdir(root)
            except OSError:
                continue

            dirs = [e for e in entries
                    if os.path.isdir(os.path.join(root, e))]
            month_dirs = [d for d in dirs if month_pattern.match(d)]

            if month_dirs and len(month_dirs) / max(len(dirs), 1) > 0.3:
                # 大部分子目录是月份 → 进入每个月目录扫描实际项目
                logger.info("检测到月份子目录结构: %s，进入深层扫描", root)
                scan_dirs = [os.path.join(root, md) for md in month_dirs]
            else:
                # 正常结构 → 第一层就是项目
                scan_dirs = [root]

            for parent in scan_dirs:
                try:
                    children = os.listdir(parent)
                except OSError:
                    continue
                for name in children:
                    full = os.path.join(parent, name)
                    if not os.path.isdir(full):
                        continue
                    # 跳过模板/配置目录（00开头的一般是模板）
                    if name.startswith("00"):
                        continue
                    if month_pattern.match(name):
                        continue
                    is_special = name in self.special_projects
                    sc = self.special_projects.get(name, {})
                    group_path = os.path.join(self.nas["group_root"], name)
                    self.db.upsert_project(
                        name, full, group_path,
                        source_root=root,
                        is_special=1 if is_special else 0,
                        special_config=sc)
                    all_names.append(name)

        logger.info("从 %d 个制作部源扫描到 %d 个项目",
                    len(roots), len(all_names))
        return all_names

    def scan_group_projects(self):
        """扫描组内 NAS 上全部项目目录，写入数据库（标记为 group_only 类型）"""
        group_root = self.nas["group_root"]
        if not os.path.isdir(group_root):
            logger.warning("组内 NAS 路径不存在: %s", group_root)
            return []

        month_pattern = re.compile(r'^\d{1,2}月$')

        all_names = []

        # 先清理旧数据中 source_root 为空的（O盘项目），准备重新扫描
        all_projects = self.db.get_all_projects()
        for proj in all_projects:
            if not proj.get("source_root"):
                self.db.delete_project(proj["name"])

        found = []
        try:
            for name in os.listdir(group_root):
                full = os.path.join(group_root, name)
                if not os.path.isdir(full):
                    continue
                if name.startswith("00"):
                    continue
                if month_pattern.match(name):
                    continue

                # 写入数据库：source_root 为空 = group_only 类型
                self.db.upsert_project(
                    name, "", full,
                    source_root="",
                    is_special=0,
                    special_config={})
                found.append(name)
        except OSError as e:
            logger.error("扫描组内 NAS 失败: %s", e)

        logger.info("组内 NAS 扫描到 %d 个项目", len(found))
        return found

    def check_group_existence(self):
        """检查所有制作部项目在组内 NAS 上是否已存在"""
        group_root = self.nas["group_root"]
        if not os.path.isdir(group_root):
            return

        projects = self.db.get_all_projects()
        for proj in projects:
            group_path = os.path.join(group_root, proj["name"])
            exists = os.path.isdir(group_path)
            # 更新数据库（这里用 extra 字段记录，但我们直接改API层返回）
            proj["on_group"] = exists

    def get_projects_enriched(self):
        """获取所有项目，附带部门标签和组盘标记。
        返回 { production: [...], group_all: [...] }
        group_all 包含 O 盘上所有项目目录（无论制作部是否有同名项目）。
        交付状态从数据库读取，后台异步检测更新（不阻塞 API 响应）。
        """
        group_root = self.nas["group_root"]
        production = []
        group_all = []

        # 从数据库获取所有项目，建立名称索引
        db_projects = {}
        for proj in self.db.get_all_projects():
            db_projects[proj["name"]] = proj

        # 预先扫描 00已完成 目录名，用于过滤 production（手动归档的项目不要重复出现）
        completed_names = set()
        completed_root = os.path.join(group_root, "00已完成")
        if os.path.isdir(completed_root):
            try:
                for _cn in os.listdir(completed_root):
                    if os.path.isdir(os.path.join(completed_root, _cn)):
                        completed_names.add(_cn)
            except OSError:
                pass

        for proj in db_projects.values():
            if proj.get("source_root"):
                custom_status = proj.get("custom_status", "") or ""
                if custom_status == "已完成":
                    continue
                # 目录已被手动移入 00已完成（项目名在 completed_names 里），也跳过
                if proj["name"] in completed_names:
                    continue
                # 优先用 DB 已存的 department 字段（更精确）
                stored_dept = proj.get("department", "")
                if stored_dept and stored_dept not in ("", "AI漫剧六部中转"):
                    dept = stored_dept
                else:
                    dept = self._get_department_label(proj["source_root"])
                proj["department"] = dept
                proj["project_type"] = "production"
                proj["custom_status"] = custom_status
                proj["total_episodes"] = proj.get("total_episodes", 0) or 0
                proj["current_episodes"] = proj.get("current_episodes", 0) or 0
                production.append(proj)

        # 生产部项目名集合，用于交叉对照
        prod_names = {p["name"] for p in production}

        # 扫描 O 盘全部项目目录（实时）
        month_pattern = re.compile(r'^\d{1,2}月$')
        if os.path.isdir(group_root):
            for name in os.listdir(group_root):
                full = os.path.join(group_root, name)
                if not os.path.isdir(full):
                    continue
                if name.startswith("00") or month_pattern.match(name):
                    continue

                # 从数据库获取项目状态（delivery_status 等）
                db_proj = db_projects.get(name)
                # 状态已完成的项目跳过（会单独在 group_completed 展示）
                if db_proj and (db_proj.get("custom_status", "") or "") == "已完成":
                    continue
                entry = {
                    "name": name,
                    "group_path": full,
                    "department": "组内NAS",
                    "source_department": "",
                    "project_type": "group",
                    "has_production_match": name in prod_names,
                    "delivery_status": "pending",
                    "last_delivered_at": "",
                    "sync_status": "pending",
                    "last_synced_at": "",
                    "sync_progress": "",
                    "is_special": 0,
                    "custom_status": "",
                    "created_at": "",
                    "total_episodes": 0,
                    "current_episodes": 0,
                }
                # 从 DB 获取真正的制作部部门名（不要硬编码组内NAS/已完成）
                _dept = ""
                if db_proj:
                    _dept = (
                        db_proj.get("department")
                        or self.db.extract_department(db_proj.get("production_path", ""))
                    )
                else:
                    _fallback = db_projects.get(name)
                    if _fallback:
                        _dept = (
                            _fallback.get("department")
                            or self.db.extract_department(_fallback.get("production_path", ""))
                        )
                # 实在没来源就保留原值（可能是组内NAS/已完成硬编码）
                entry["department"] = _dept or entry.get("department", "")
                entry["source_department"] = entry["department"]
                if db_proj:
                    entry["last_delivered_at"] = db_proj.get("last_delivered_at") or ""
                    entry["sync_status"] = db_proj.get("sync_status", "pending")
                    entry["last_synced_at"] = db_proj.get("last_synced_at") or ""
                    entry["sync_progress"] = db_proj.get("sync_progress") or ""
                    entry["is_special"] = db_proj.get("is_special", 0)
                    entry["custom_status"] = db_proj.get("custom_status", "") or ""
                    entry["created_at"] = db_proj.get("created_at") or ""
                    entry["total_episodes"] = db_proj.get("total_episodes", 0) or 0
                    entry["current_episodes"] = db_proj.get("current_episodes", 0) or 0
                # group_all 项目已经在磁盘上，DB 误标 syncing 自动纠正
                if entry.get("sync_status") == "syncing":
                    try:
                        self.db.update_project_status(
                            entry["name"], sync_status="synced",
                            sync_progress="",
                            last_synced_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                        entry["sync_status"] = "synced"
                        entry["sync_progress"] = ""
                    except Exception:
                        pass

                group_all.append(entry)

        group_all.sort(key=lambda x: _natural_key(x["name"]))

        # 标记 production 项目在组盘是否存在
        group_names = {g["name"] for g in group_all}
        for proj in production:
            proj["on_group"] = proj["name"] in group_names
            proj["need_sync"] = bool(proj.get("production_path")) and not proj["on_group"]
            if proj["need_sync"] and not (proj.get("custom_status") or "").strip():
                proj["custom_status"] = "待同步"
            # 自动纠正：DB 显示 syncing 但磁盘已存在 → 手动拷完/robocopy 已完成
            if proj.get("sync_status") == "syncing" and proj.get("on_group"):
                try:
                    self.db.update_project_status(
                        proj["name"], sync_status="synced",
                        sync_progress="",
                        last_synced_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    proj["sync_status"] = "synced"
                    proj["sync_progress"] = ""
                    logger.info("sync_status auto-correct syncing->synced: %s", proj["name"])
                except Exception as _e:
                    logger.warning("auto-correct failed for %s: %s", proj["name"], _e)

        # 同步 group_all 条目的交付状态（从 production 数据读取）
        prod_status_map = {p["name"]: p for p in production}
        for g in group_all:
            if g["name"] in prod_status_map:
                p = prod_status_map[g["name"]]
                g["delivery_status"] = p.get("delivery_status", "pending")
                g["last_delivered_at"] = p.get("last_delivered_at", "")
                g["custom_status"] = p.get("custom_status", "") or ""
                g["source_department"] = p.get("department", "") or ""
                g["production_path"] = p.get("production_path", "") or ""
                g["total_episodes"] = p.get("total_episodes", 0) or 0
                g["current_episodes"] = p.get("current_episodes", 0) or 0
                g["episode_plan"] = p.get("episode_plan") or "{}"
                if not g.get("created_at"):
                    g["created_at"] = p.get("created_at", "") or ""

        # 后台异步检测交付状态（不阻塞 API 响应）
        self._start_delivery_check_background(production)

        # 扫描 00已完成 子目录
        group_completed = []
        completed_root = os.path.join(group_root, "00已完成")
        if os.path.isdir(completed_root):
            for name in os.listdir(completed_root):
                full = os.path.join(completed_root, name)
                if not os.path.isdir(full):
                    continue
                db_proj = db_projects.get(name)
                entry = {
                    "name": name,
                    "group_path": full,
                    "department": "已完成",
                    "source_department": "",
                    "project_type": "group",
                    "has_production_match": name in prod_names,
                    "delivery_status": "pending",
                    "last_delivered_at": "",
                    "sync_status": "pending",
                    "last_synced_at": "",
                    "sync_progress": "",
                    "is_special": 0,
                    "custom_status": "已完成",
                    "created_at": "",
                    "total_episodes": 0,
                    "current_episodes": 0,
                    "is_completed": True,
                }
                # 从 DB 获取真正的制作部部门名（不要硬编码组内NAS/已完成）
                _dept = ""
                if db_proj:
                    _dept = (
                        db_proj.get("department")
                        or self.db.extract_department(db_proj.get("production_path", ""))
                    )
                else:
                    _fallback = db_projects.get(name)
                    if _fallback:
                        _dept = (
                            _fallback.get("department")
                            or self.db.extract_department(_fallback.get("production_path", ""))
                        )
                # 实在没来源就保留原值（可能是组内NAS/已完成硬编码）
                entry["department"] = _dept or entry.get("department", "")
                entry["source_department"] = entry["department"]
                if db_proj:
                    entry["last_delivered_at"] = db_proj.get("last_delivered_at") or ""
                    entry["sync_status"] = db_proj.get("sync_status", "pending")
                    entry["last_synced_at"] = db_proj.get("last_synced_at") or ""
                    entry["sync_progress"] = db_proj.get("sync_progress") or ""
                    entry["custom_status"] = db_proj.get("custom_status", "") or "已完成"
                    entry["created_at"] = db_proj.get("created_at") or ""
                    entry["total_episodes"] = db_proj.get("total_episodes", 0) or 0
                    entry["current_episodes"] = db_proj.get("current_episodes", 0) or 0
                    # 已完成项目也纠正 syncing
                    if entry.get("sync_status") == "syncing":
                        try:
                            self.db.update_project_status(
                                entry["name"], sync_status="synced",
                                sync_progress="",
                                last_synced_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                            entry["sync_status"] = "synced"
                            entry["sync_progress"] = ""
                        except Exception:
                            pass
                    source_dept = db_proj.get("department", "") or ""
                    if source_dept:
                        entry["source_department"] = source_dept
                group_completed.append(entry)

        group_completed.sort(key=lambda x: _natural_key(x["name"]))

        # 给待交付 / 已完成项目附加交付统计
        for bucket in (production, group_all, group_completed):
            for proj in bucket:
                if proj.get("custom_status") in ("待交付", "已完成"):
                    try:
                        proj["delivery_stats"] = self.get_delivery_stats(proj["name"])
                    except Exception:
                        proj["delivery_stats"] = {"found": False, "total_episodes": 0, "items": [], "overall_pct": 0}

        return {
            "production": production,
            "group_all": group_all,
            "group_completed": group_completed,
        }
