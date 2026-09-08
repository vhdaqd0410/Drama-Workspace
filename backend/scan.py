"""扫描职责：项目发现、分组扫描、部门识别。"""
import os
import re
import time
import logging
from datetime import datetime
from utils import scan_dir

logger = logging.getLogger(__name__)


def _is_active_project(p):
    """项目是否有实际制作痕迹（排除空壳/模板目录）。"""
    s = str(p.get("custom_status") or "").strip()
    d = str(p.get("delivery_status") or "").strip()
    t = int(p.get("total_episodes") or 0)
    return bool(s) or (d and d != "pending") or t > 0


def _is_producing(p):
    """项目是否处于制作中（进行中状态，含分集中/剪辑中/审核中/修改中等）。"""
    s = str(p.get("custom_status") or "").strip()
    return bool(s) and s != "已完成"


def compute_overview_stats(production, group_all, group_completed, now_month=None):
    """统一计算首页概览统计，保证口径一致：
    - 总项目：所有有制作痕迹的项目（跨分组去重）
    - 本月项目：本月(project_month==now_month)且有制作痕迹的项目
    - 本月已完成：本月项目里状态为已完成
    - 制作中：本月项目里处于制作中状态（非空且非已完成）
    - 上月遗留未交：上月(project_month==上个月)且至今仍未完成的项目
    恒等式：本月项目 = 本月已完成 + 制作中
    """
    import time as _t
    if now_month is None:
        now_month = datetime.now().strftime("%Y-%m")

    # 上月 = now_month 减一个月
    try:
        y, m = now_month.split("-")
        y = int(y); m = int(m)
        if m == 1:
            prev_y, prev_m = y - 1, 12
        else:
            prev_y, prev_m = y, m - 1
        last_month = "%04d-%02d" % (prev_y, prev_m)
    except Exception:
        last_month = ""

    # 跨分组去重（按项目名，优先保留信息更全的记录）
    seen = {}
    for bucket in (production, group_all, group_completed):
        for p in bucket:
            name = p.get("name")
            if not name:
                continue
            if name not in seen:
                seen[name] = p
            else:
                ex = seen[name]
                # 已有空壳记录时用新的有制作痕迹记录替换
                if not _is_active_project(ex) and _is_active_project(p):
                    seen[name] = p
    all_projects = list(seen.values())

    total = sum(1 for p in all_projects if _is_active_project(p))

    month_projects = [p for p in all_projects
                      if (p.get("project_month") or "") == now_month and _is_active_project(p)]
    this_month = len(month_projects)
    this_month_done = sum(1 for p in month_projects
                          if str(p.get("custom_status") or "").strip() == "已完成")
    producing = sum(1 for p in month_projects if _is_producing(p))

    # 上月遗留未交：上月挂账、至今仍未完成（不含已完成）
    last_month_left = sum(
        1 for p in all_projects
        if (p.get("project_month") or "") == last_month
        and _is_active_project(p)
        and str(p.get("custom_status") or "").strip() != "已完成"
    )

    # 恒等式校验：本月项目 = 本月已完成 + 制作中
    # （制作中含所有进行中状态，故恒成立）

    return {
        "total": total,
        "this_month": this_month,
        "this_month_done": this_month_done,
        "producing": producing,
        "last_month_left": last_month_left,
        "month": now_month,
        "last_month": last_month,
    }


# ============ 递归扫描项目识别 ============
# 项目编号模式：任意位置 4-6 位连续数字即视为项目编号
# （兼容 00_10018_名称 / H0189-11587《剧名》 / 1234_5678_名称 等各类命名）
_PROJECT_NUM_RE = re.compile(r'\d{4,6}')
# 明确是"分类/汇总"目录的词（不是项目，需继续往下递归或跳过）。
# 注意：不含"海外/国内"——这些词会出现在项目名里（如《...国内版/海外版》），
# 部门区分由源路径(_get_department_label)处理，不应在项目识别时误伤。
_CATEGORY_WORDS = ('类', '合集', '中转', '存档', '备份', '模板')
# 项目级结构子目录：含这些子目录的目录基本可判定为项目
_PROJECT_STRUCT_DIRS = ('01上映单集版', '000交付', '分集', '成片', '制作端对标', '运营对标')


def _looks_like_project(dirpath, dirname):
    """判断一个目录是否"像项目"（而非分类/汇总目录）。
    依据：1) 名称含项目编号（4-6位连续数字）；2) 内含项目级结构子目录。
    都不满足 → 视为分类目录（继续递归）。"""
    if not dirname or dirname.startswith('.'):
        return False
    # 排除明确的分类/汇总词
    if any(w in dirname for w in _CATEGORY_WORDS):
        return False
    # 1) 名称含项目编号（4-6 位连续数字）
    if _PROJECT_NUM_RE.search(dirname):
        return True
    # 2) 内含项目级结构子目录
    try:
        for entry in os.listdir(dirpath):
            if any(s in entry for s in _PROJECT_STRUCT_DIRS):
                return True
    except OSError:
        pass
    return False


def _is_skippable_dir(dirname):
    """递归扫描时跳过明显非项目、非分类的目录（模板/临时/系统目录）。"""
    if not dirname or dirname.startswith('.'):
        return True
    if dirname.startswith('00') and 'id' in dirname.lower():
        return True  # 00_id_ 等占位/系统目录
    if re.match(r'^\d{4}月$', dirname):  # 月份目录（父层处理）
        return False
    return False


def _is_template_dir(dirname):
    """判断 00 开头的目录是否为"模板/占位目录"（应跳过）。

    七部等部门的项目命名是 00编号_项目名（如 00153_11005_医统天下），
    以 00 开头但确实是项目，不能跳过。而 00模板/0000某人 等是模板/占位。
    精确规则：00 开头且后面紧跟数字 + _ 或 - 分隔（项目编号格式）→ 是项目，保留；
    否则（00 + 中文/字母、0000+中文）→ 模板/占位，跳过。"""
    if not dirname or not dirname.startswith('00'):
        return False
    # 00 + 编号 + 分隔符（_ 或 -）→ 项目编号格式（如 00153_11005_xxx），保留
    if re.match(r'^00\d+[-_]', dirname):
        return False
    # 其余 00 开头的视为模板/占位
    return True


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

        支持两种目录结构：
        - 直接结构：根目录第一层就是项目
        - 嵌套结构：根 → 分类/月份子目录 → 项目（如漫剧七部：分类 → 项目）
        递归扫描并用 _looks_like_project 识别真正的项目文件夹，避免把分类目录当项目。
        可通过 config.yaml 每源配置 recursive_depth 限制递归深度（默认 3）。
        """
        roots = self.nas.get("production_roots", [])
        if not roots:
            logger.error("未配置制作部 NAS 路径 (production_roots)")
            return []

        # 软删除/忽略的项目：扫描时跳过
        ignored_names = set(self.db.get_ignored_projects())

        month_pattern = re.compile(r'^\d{1,2}月$')

        all_names = []
        for root in roots:
            if not os.path.isdir(root):
                logger.warning("制作部 NAS 路径不存在，跳过: %s", root)
                continue

            # 该源可配置的递归深度（默认 3，0 表示只扫第一层）
            src_cfg = (self.nas.get("production_roots_config") or {}).get(root, {}) or {}
            try:
                max_depth = int(src_cfg.get("recursive_depth", 3))
            except (TypeError, ValueError):
                max_depth = 3
            if max_depth < 0:
                max_depth = 3

            def _scan_dir(base, depth):
                """递归扫描 base 目录下的项目。depth 为当前层级（根=0）。"""
                try:
                    entries = os.listdir(base)
                except OSError:
                    return
                dirs = [e for e in entries
                        if os.path.isdir(os.path.join(base, e))
                        and not _is_skippable_dir(e)]
                if not dirs:
                    return
                # 判断这一层是否是"月份子目录"（如 7月/8月）→ 进入下一层
                month_dirs = [d for d in dirs if month_pattern.match(d)]
                is_month_layer = len(month_dirs) / max(len(dirs), 1) > 0.3 if dirs else False

                for name in dirs:
                    full = os.path.join(base, name)
                    if month_pattern.match(name):
                        # 月份目录：跳过（父层逻辑已处理），直接递归内部
                        _scan_dir(full, depth + 1)
                        continue
                    if is_month_layer:
                        # 当前层是月份目录，实际项目在其内部
                        _scan_dir(full, depth + 1)
                        continue
                    # 判断是否为项目
                    if _looks_like_project(full, name):
                        if name in ignored_names:
                            continue  # 软删除/忽略的项目，扫描时跳过
                        is_special = name in self.special_projects
                        sc = self.special_projects.get(name, {})
                        group_path = os.path.join(self.nas["group_root"], name)
                        self.db.upsert_project(
                            name, full, group_path,
                            source_root=root,
                            is_special=1 if is_special else 0,
                            special_config=sc)
                        all_names.append(name)
                    elif depth < max_depth:
                        # 不是项目 → 可能是分类目录，继续向下递归
                        _scan_dir(full, depth + 1)

            _scan_dir(root, 0)

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
        ignored_names = set(self.db.get_ignored_projects())
        try:
            for name in os.listdir(group_root):
                full = os.path.join(group_root, name)
                if not os.path.isdir(full):
                    continue
                # 跳过模板/占位目录（00模板/0000某人等），但保留 00编号_项目 这类项目
                if _is_template_dir(name):
                    continue
                if month_pattern.match(name):
                    continue
                if name in ignored_names:
                    continue  # 软删除/忽略的项目，扫描时跳过

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
        ignored_names = set(self.db.get_ignored_projects())
        if os.path.isdir(group_root):
            for name in os.listdir(group_root):
                full = os.path.join(group_root, name)
                if not os.path.isdir(full):
                    continue
                # 跳过模板/占位目录，但保留 00编号_项目 这类项目
                if _is_template_dir(name) or month_pattern.match(name):
                    continue
                if name in ignored_names:
                    continue  # 软删除/忽略的项目，不展示

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
                    "project_month": "",
                    "is_domestic": 0,
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
                    entry["project_month"] = db_proj.get("project_month") or ""
                    entry["is_domestic"] = int(db_proj.get("is_domestic") or 0)

                group_all.append(entry)

        group_all.sort(key=lambda x: _natural_key(x["name"]))

        # 标记 production 项目在组盘是否存在
        group_names = {g["name"] for g in group_all}
        for proj in production:
            proj["on_group"] = proj["name"] in group_names
            proj["need_sync"] = bool(proj.get("production_path")) and not proj["on_group"]
            if proj["need_sync"] and not (proj.get("custom_status") or "").strip():
                proj["custom_status"] = "待同步"

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
                g["project_month"] = p.get("project_month") or ""
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
                    "project_month": "",
                    "is_domestic": 0,
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
                    entry["project_month"] = db_proj.get("project_month") or ""
                    entry["is_domestic"] = int(db_proj.get("is_domestic") or 0)
                    source_dept = db_proj.get("department", "") or ""
                    if source_dept:
                        entry["source_department"] = source_dept
                    # 关键修复：手动拖入 00已完成 的项目，DB 的 group_path 可能还是旧路径
                    # （旧目录已被移走不存在），回写为磁盘实际位置，保证"组内NAS/已完成"按钮能打开
                    try:
                        old_gp = (db_proj.get("group_path") or "").rstrip("\\/")
                        new_gp = full.rstrip("\\/")
                        if old_gp and old_gp != new_gp:
                            self.db.update_project_status(name, group_path=full)
                            logger.info("已完成项目 group_path 已同步: %s -> %s", name, full)
                    except Exception:
                        pass
                group_completed.append(entry)

        # 给已完成项目补制作部路径：从 DB 读（production 桶已过滤完成项目）
        for gc in group_completed:
            _dproj = db_projects.get(gc["name"])
            if _dproj and _dproj.get("production_path"):
                gc["production_path"] = _dproj.get("production_path", "") or ""
                if gc.get("department") == "已完成" or not gc.get("department"):
                    gc["department"] = _dproj.get("department", "") or gc.get("department", "")

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
