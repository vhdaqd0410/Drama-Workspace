"""同步职责：robocopy 同步、源目录解析、交付路径计算。"""
import os
import os as _os
import re
import shutil
import shutil as _shutil
import subprocess
import subprocess as _sp
import logging
from datetime import datetime
from scan import find_dir_recursive

logger = logging.getLogger(__name__)

ROBOCOPY_BASE = ["/E", "/R:1", "/W:1", "/NP", "/NFL", "/NDL"]
ROBOCOPY_MIR = ["/MIR"] + ROBOCOPY_BASE
ROBOCOPY_FAST = ["/MT:8"] + ROBOCOPY_BASE       # 多线程快速复制
ROBOCOPY_XCOPY_CMD = ["cmd", "/c", "xcopy", "/E", "/I", "/Y"]
CMD_MKDIR_CMD = ["cmd", "/c", "mkdir"]
TIMEOUT_MKDIR = 30
TIMEOUT_XCOPY_SMALL = 120
TIMEOUT_XCOPY_BIG = 600
TIMEOUT_ROBOCOPY_FAST = 3600      # 一键交付 → 制作部
TIMEOUT_ROBOCOPY_SYNC = 7200      # 组内 → 制作部同步

def _exec(cmd, timeout, label="", unc_alt=None):
    """统一 subprocess.run 封装。
    cmd: [exe, arg1, ...]
    timeout: 超时秒
    label: 日志标签
    unc_alt: 如果 timeout 触发，用 UNC 路径的备选命令 (list)
    返回 (ok: bool, msg: str, returncode: int)
    """
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout)
        rc = result.returncode
        if rc < 8 and rc != -9:
            return True, "ok", rc
        err = result.stderr.decode("gbk", errors="replace")[:500] \
            if result.stderr else "rc=%d" % rc
        return False, err, rc
    except subprocess.TimeoutExpired:
        if unc_alt:
            logger.warning("%s 超时，尝试 UNC 备选", label)
            try:
                result = subprocess.run(unc_alt, capture_output=True, timeout=timeout)
                rc = result.returncode
                if rc < 8:
                    return True, "ok (unc)", rc
                err = result.stderr.decode("gbk", errors="replace")[:500] \
                    if result.stderr else "rc=%d" % rc
                return False, "UNC 备选失败: " + err, rc
            except Exception as e:
                return False, "UNC 备选异常: " + str(e), -1
        return False, "超时（超过 %d 秒）" % timeout, -1
    except Exception as e:
        return False, str(e), -1

def _exec_popen(cmd, label=""):
    """启动 robocopy Popen 句柄，返回 (proc, pid)。"""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc, proc.pid



class SyncMixin:
    def _to_unc(self, path):
        """将盘符路径转为 UNC 路径（管理员进程用 cmd+UNC 绕过权限隔离）"""
        path = path.replace("/", "\\")
        for drive, unc in self._unc_map.items():
            d = drive.rstrip(":") + ":"
            if path.upper().startswith(d.upper()):
                rest = path[len(d):].lstrip("\\")
                return os.path.join(unc, rest)
        return path

    def _robocopy(self, src, dst, exclude_patterns):
        """执行 robocopy 增量镜像同步"""
        cmd = ["robocopy", src, dst] + ROBOCOPY_MIR

        xf = [p for p in exclude_patterns
              if "*" in p or "." in p]
        xd = [p for p in exclude_patterns
              if "*" not in p and "." not in p]
        if xf:
            cmd += ["/XF"] + xf
        if xd:
            cmd += ["/XD"] + xd

        ok, msg, rc = _exec(cmd, TIMEOUT_ROBOCOPY_SYNC, label="robocopy_sync")
        if ok:
            return True, "同步成功"
        return False, "robocopy 返回码 %d: %s" % (rc, msg)

    def sync_project(self, project_name):
        """将单个项目完整从制作部 NAS 同步到组内 NAS"""
        proj = self.db.get_project(project_name)
        if not proj:
            return False, "项目不存在"

        src_root = proj["production_path"]
        dst_root = proj["group_path"]

        self.db.update_project_status(
            project_name, sync_status="syncing", sync_progress="5% 准备中...")
        self.db.add_sync_log(
            project_name, "开始同步", "production->group",
            status="info", message="源: " + src_root)

        os.makedirs(dst_root, exist_ok=True)

        sync_mode = self.sync_cfg.get("mode", "full")
        exclude = self.sync_cfg.get("exclude_patterns", [])

        if sync_mode == "partial":
            sync_subdirs = self.sync_cfg.get("sync_subdirs", [])
            if sync_subdirs:
                total = len(sync_subdirs)
                for i, subdir in enumerate(sync_subdirs, 1):
                    src = os.path.join(src_root, subdir)
                    dst = os.path.join(dst_root, subdir)
                    if not os.path.isdir(src):
                        logger.warning("源子目录不存在，跳过: %s", src)
                        continue
                    pct = 5 + int(90 * (i - 1) / max(total, 1))
                    progress = "%d%% 同步中 (%d/%d): %s" % (pct, i, total, subdir)
                    self.db.update_project_status(
                        project_name, sync_progress=progress)
                    self.db.add_sync_log(
                        project_name, "同步子目录", "production->group",
                        file_path=subdir, status="info", message=progress)
                    ok, msg = self._robocopy(src, dst, exclude)
                    if not ok:
                        self.db.add_sync_log(
                            project_name, "同步失败", "production->group",
                            file_path=subdir, status="error", message=msg)
            else:
                self.db.update_project_status(
                    project_name, sync_progress="10% 完整同步项目目录...")
                ok, msg = self._robocopy(src_root, dst_root, exclude)
                if not ok:
                    self.db.add_sync_log(
                        project_name, "同步失败", "production->group",
                        status="error", message=msg)
        else:
            # full mode — mirror entire project
            self.db.update_project_status(
                project_name, sync_progress="10% 完整同步项目目录...")
            ok, msg = self._robocopy(src_root, dst_root, exclude)
            if not ok:
                self.db.add_sync_log(
                    project_name, "同步失败", "production->group",
                    status="error", message=msg)

        self.db.update_project_status(
            project_name, sync_status="syncing", sync_progress="98% 收尾中...")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # 同步完成后, 若无有效 workflow 状态, 自动标记为"分集中"
        cur_status = (proj.get("custom_status") or "").strip()
        workflow_set = {"分集中", "剪辑中", "审核中", "修改中",
                        "待质检", "质检中", "待交付", "交付中", "已交付", "已完成"}
        if not cur_status or cur_status in ("待同步",):
            self.db.update_project_status(
                project_name, sync_status="synced",
                sync_progress="", last_synced_at=now,
                custom_status="分集中")
        else:
            self.db.update_project_status(
                project_name, sync_status="synced",
                sync_progress="", last_synced_at=now)
        self.db.add_sync_log(
            project_name, "同步完成", "production->group",
            status="success", message="所有素材同步完成")
        return True, "同步完成"

    def get_dest_dir(self, project_name):
        """获取项目的成片回传目标目录（制作部NAS侧的01上映单集版）"""
        proj = self.db.get_project(project_name)
        if not proj:
            return None, "项目不存在"
        prod_path = proj.get("production_path", "")
        if not prod_path:
            return None, "该项目无制作部路径（仅组内项目）"
        dirs = self._find_output_dirs(prod_path, project_name)
        if not dirs:
            return None, "制作部项目中未找到 %s 目录" % self._get_output_dir_name(project_name)
        return dirs[0], None

    def get_source_dir(self, project_name):
        """获取项目的成片源目录（组内NAS侧的01上映单集版）"""
        proj = self.db.get_project(project_name)
        if not proj:
            return None, "项目不存在"
        group_path = proj.get("group_path", "")
        if not group_path:
            return None, "该项目无组内路径"
        dirs = self._find_output_dirs(group_path, project_name)
        if not dirs:
            return None, "组内项目中未找到 %s 目录" % self._get_output_dir_name(project_name)
        return dirs[0], None

    def _get_output_dir_name(self, project_name):
        """获取项目的成片输出目录名"""
        if project_name in self.special_projects:
            return self.special_projects[project_name].get(
                "output_dir_name", self.output_dir_name)
        return self.output_dir_name

    def _find_output_dirs(self, base_path, project_name):
        """在项目目录下递归查找 01上映单集版 目录，带缓存"""
        cache_key = base_path + "|" + project_name
        with self._lock:
            if cache_key in self._output_dir_cache:
                return self._output_dir_cache[cache_key]

        dir_name = self._get_output_dir_name(project_name)
        dirs = find_dir_recursive(base_path, dir_name)

        with self._lock:
            self._output_dir_cache[cache_key] = dirs
        return dirs

    def _cleanup_partial_dst(self, dst):
        """交付失败/超时后清理目标目录，避免留下半成品"""
        if not dst or not os.path.exists(dst):
            return
        try:
            _shutil.rmtree(dst, ignore_errors=True)
            logger.warning("已清理交付失败的半成品目录: %s", dst)
        except Exception as e:
            logger.warning("清理半成品目录失败 %s: %s", dst, e)

    def clear_cache(self):
        with self._lock:
            self._output_dir_cache.clear()
