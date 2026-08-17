"""同步职责：robocopy 同步、源目录解析、交付路径计算。"""
import os
import os as _os
import re
import shutil
import shutil as _shutil
import subprocess
import subprocess as _sp
import logging
import threading
import time
import fnmatch
from datetime import datetime
from scan import find_dir_recursive
from utils import decode_output

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
        err = decode_output(result.stderr)[:500] \
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
                err = decode_output(result.stderr)[:500] \
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
        """执行 robocopy 增量镜像同步（带独立 cmd 窗口显示进度）"""
        cmd = ["robocopy", src, dst] + ROBOCOPY_MIR

        xf = [p for p in exclude_patterns
              if "*" in p or "." in p]
        xd = [p for p in exclude_patterns
              if "*" not in p and "." not in p]
        if xf:
            cmd += ["/XF"] + xf
        if xd:
            cmd += ["/XD"] + xd

        # 弹出独立 cmd 窗口运行 robocopy，让用户看到进度条
        try:
            proc = subprocess.Popen(
                ["cmd.exe", "/c"] + cmd,
                creationflags=0
            )
        except Exception:
            proc = subprocess.Popen(cmd, creationflags=0)

        try:
            rc = proc.wait(timeout=TIMEOUT_ROBOCOPY_SYNC)
        except subprocess.TimeoutExpired:
            proc.kill()
            return False, "robocopy 超时（超过 %d 秒）" % TIMEOUT_ROBOCOPY_SYNC

        if rc < 8:
            return True, "robocopy 同步成功"
        return False, "robocopy 返回码 %d" % rc

    @staticmethod
    def _count_dir_stats(path):
        """递归统计目录下的文件数量和总大小。"""
        file_count = 0
        total_size = 0
        if not os.path.isdir(path):
            return 0, 0
        for dirpath, _dirnames, filenames in os.walk(path):
            for fn in filenames:
                try:
                    fp = os.path.join(dirpath, fn)
                    total_size += os.path.getsize(fp)
                    file_count += 1
                except OSError:
                    pass
        return file_count, total_size

    def _copy_explorer(self, src, dst, timeout=7200):
        """启动 VBS 独立子进程调用 Shell.Application.CopyHere，弹出原生复制进度窗口。

        用 VBS + wscript.exe 独立子进程而非 Python 直接调用 COM，
        是因为独立 GUI 进程在任何 Session 下都能确保弹出 Shell 进度窗口。
        """
        if not os.path.isdir(src):
            return False, "源目录不存在: " + src

        os.makedirs(dst, exist_ok=True)

        src_count, src_size = self._count_dir_stats(src)
        if src_count == 0:
            return True, "空目录无需复制"

        # 写 VBS 脚本到临时目录
        vbs_path = os.path.join(
            _os.environ.get("TEMP", _os.getcwd()),
            "_sync_copy_helper.vbs"
        )
        try:
            vbs_lines = [
                'Set oS = CreateObject("Shell.Application")',
                'Set oSrc = oS.Namespace(WScript.Arguments(0))',
                'Set oDst = oS.Namespace(WScript.Arguments(1))',
                'If oSrc Is Nothing Then WScript.Quit 1',
                'If oDst Is Nothing Then WScript.Quit 2',
                'oDst.CopyHere oSrc.Items(), 0',
            ]
            with open(vbs_path, "w", encoding="utf-8") as f:
                f.write("\n".join(vbs_lines))
        except Exception as e:
            logger.warning("写 VBS 脚本失败: %s", e)
            return False, "VBS 脚本写入失败"

        try:
            proc = subprocess.Popen(
                ["wscript.exe", vbs_path, src, dst],
                creationflags=0
            )
        except FileNotFoundError:
            try:
                _os.remove(vbs_path)
            except OSError:
                pass
            return False, "wscript.exe 未找到"

        logger.info(
            "已启动 VBS CopyHere (pid=%d), 等待复制完成...", proc.pid)

        start_time = time.time()
        stable_count = 0
        last_count = -1
        last_size = -1

        try:
            while True:
                time.sleep(1.0)
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    proc.kill()
                    logger.warning("VBS CopyHere 超时 (%ds)", timeout)
                    return False, "复制超时"

                rc = proc.poll()
                dst_count, dst_size = self._count_dir_stats(dst)

                if dst_count == last_count and abs(dst_size - last_size) < 1024:
                    stable_count += 1
                else:
                    stable_count = 0
                last_count = dst_count
                last_size = dst_size

                # 进程已退出 + 文件统计稳定 → 复制完成
                if rc is not None:
                    # 进程退出后再等一会儿，确保文件句柄释放
                    for _ in range(3):
                        time.sleep(0.5)
                        nc, ns = self._count_dir_stats(dst)
                        if nc == dst_count and ns == dst_size:
                            break
                        dst_count, dst_size = nc, ns
                    if rc == 0:
                        return True, "资源管理器复制完成 (%d 文件, %.1f MB)" % (
                            dst_count, dst_size / 1024 / 1024)
                    return False, "VBS 退出码 %d" % rc

                # 进程还活着，但文件数稳定了很久 → 可能 CopyHere 完成了
                if dst_count >= src_count and stable_count >= 5:
                    proc.terminate()
                    return True, "资源管理器复制完成 (%d 文件, %.1f MB)" % (
                        dst_count, dst_size / 1024 / 1024)

        finally:
            try:
                _os.remove(vbs_path)
            except OSError:
                pass

    @staticmethod
    def _is_desktop_opt(key):
        return os.environ.get(f"DRAMA_DESKTOP_{key}") == "1"

    def _precheck_copy(self, src, dst):
        """桌面版前置健康检查。返回 (ok: bool, msg: str)。"""
        if not self._is_desktop_opt("PRECHECK"):
            return True, ""
        # 1. UNC / 路径可达（3s 超时）
        try:
            import socket
            import threading
            reachable = [False]
            def _probe():
                try:
                    if os.path.exists(src):
                        reachable[0] = True
                except Exception:
                    pass
            t = threading.Thread(target=_probe, daemon=True)
            t.start()
            t.join(timeout=3.0)
            if not reachable[0]:
                return False, f"源路径不可达：{src}（NAS 断开？）"
        except Exception:
            pass
        # 2. 源文件是否被占用（试独占打开一个文件）
        if os.path.isfile(src):
            try:
                fd = os.open(src, os.O_RDWR | os.O_EXCL)
                os.close(fd)
            except OSError as e:
                return False, f"源文件被占用（可能 Premiere 正在使用）: {e}"
        return True, ""

    def _copy_desktop_com(self, src, dst, timeout=7200):
        """桌面版优化：直接 pywin32 COM 调 Shell.Application.CopyHere。
        比 VBS 子进程更稳：同 Session、无进程存活轮询、无写临时文件。"""
        try:
            import pythoncom
            from win32com.client import Dispatch
        except ImportError:
            return False, "pywin32 不可用"
        if not os.path.isdir(src):
            return False, "源目录不存在: " + src
        os.makedirs(dst, exist_ok=True)
        pythoncom.CoInitialize()
        try:
            shell = Dispatch("Shell.Application")
            folder_src = shell.Namespace(src)
            folder_dst = shell.Namespace(dst)
            if folder_src is None:
                return False, "Shell 找不到源目录"
            if folder_dst is None:
                return False, "Shell 找不到目标目录"
            items = folder_src.Items()
            item_count = items.Count
            logger.info("桌面 COM CopyHere: %s → %s (%d 项)", src, dst, item_count)
            folder_dst.CopyHere(items, 0)  # 0 = 默认（弹系统进度对话框）
            # 等复制完成（轮询目标文件数稳定）
            start = time.time()
            stable = 0
            last_count, last_size = -1, -1
            while True:
                time.sleep(1.0)
                if time.time() - start > timeout:
                    return False, "COM 复制超时"
                dc, ds = self._count_dir_stats(dst)
                if dc == last_count and abs(ds - last_size) < 1024:
                    stable += 1
                else:
                    stable = 0
                last_count, last_size = dc, ds
                if dc >= item_count and stable >= 5:
                    return True, f"桌面 COM 复制完成 ({dc} 文件, {ds/1024/1024:.1f} MB)"
                # 源目录里的每个文件都出现在 dst 里 → 完成
                if self._all_items_in_dst(src, dst):
                    return True, f"桌面 COM 复制完成 ({dc} 文件)"
        finally:
            pythoncom.CoUninitialize()

    def _all_items_in_dst(self, src, dst):
        """检查 src 下的所有文件/子目录是否都在 dst 里出现了（快速完成判定）"""
        try:
            src_names = set(os.listdir(src))
            dst_names = set(os.listdir(dst))
            return src_names.issubset(dst_names)
        except Exception:
            return False

    def _copy_dir(self, src, dst, exclude_patterns):
        # 前置检查（桌面版）
        ok, msg = self._precheck_copy(src, dst)
        if not ok:
            logger.warning("前置检查失败: %s", msg)
            # 不是致命错误，继续尝试（用户可能有特殊情况）
        # 桌面版：优先用 pywin32 COM 直调
        if self._is_desktop_opt("CAN_COM"):
            ok, msg = self._copy_desktop_com(src, dst)
            if ok:
                if exclude_patterns:
                    self._purge_excluded(dst, exclude_patterns)
                return True, msg
            logger.info("桌面 COM 不可用 (%s), fallback VBS", msg)
        # 原有逻辑：VBS 子进程
        ok, msg = self._copy_explorer(src, dst)
        if ok:
            if exclude_patterns:
                self._purge_excluded(dst, exclude_patterns)
            return True, msg
        logger.info("Explorer 复制不可用, fallback robocopy")
        return self._robocopy(src, dst, exclude_patterns)

    @staticmethod
    def _purge_excluded(root_dir, exclude_patterns):
        for dirpath, dirnames, filenames in os.walk(root_dir):
            for fn in filenames:
                for pat in exclude_patterns:
                    if fnmatch.fnmatch(fn, pat):
                        try:
                            os.remove(os.path.join(dirpath, fn))
                        except OSError:
                            pass
                        break
            for dn in list(dirnames):
                for pat in exclude_patterns:
                    if fnmatch.fnmatch(dn, pat):
                        try:
                            shutil.rmtree(os.path.join(dirpath, dn),
                                          ignore_errors=True)
                        except OSError:
                            pass
                        break

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
                    ok, msg = self._copy_dir(src, dst, exclude)
                    if not ok:
                        self.db.add_sync_log(
                            project_name, "同步失败", "production->group",
                            file_path=subdir, status="error", message=msg)
            else:
                self.db.update_project_status(
                    project_name, sync_progress="10% 完整同步项目目录...")
                ok, msg = self._copy_dir(src_root, dst_root, exclude)
                if not ok:
                    self.db.add_sync_log(
                        project_name, "同步失败", "production->group",
                        status="error", message=msg)
        else:
            # full mode — mirror entire project
            self.db.update_project_status(
                project_name, sync_progress="10% 完整同步项目目录...")
            ok, msg = self._copy_dir(src_root, dst_root, exclude)
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
        """在项目目录下递归查找 01上映单集版 目录，带持久化缓存"""
        cache_key = base_path + "|" + project_name
        with self._lock:
            if cache_key in self._output_dir_cache:
                cached = self._output_dir_cache[cache_key]
                # 校验缓存路径仍存在；若全部失效则重新扫描（项目可能已移动/删除）
                if cached:
                    alive = [d for d in cached if os.path.isdir(d)]
                    if alive == cached:
                        return cached
                # 缓存失效，重新扫描
                self._output_dir_cache.pop(cache_key, None)

        dir_name = self._get_output_dir_name(project_name)
        dirs = find_dir_recursive(base_path, dir_name)

        with self._lock:
            self._output_dir_cache[cache_key] = dirs
            # 写盘持久化，重启后免重扫（只在新增条目时写，避免高频重复写盘）
            if len(self._output_dir_cache) > self._last_cache_save_size:
                self._save_output_dir_cache()
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
        # 同时删除持久化缓存文件，避免下次启动加载旧数据
        try:
            if hasattr(self, "_output_dir_cache_file") and os.path.isfile(self._output_dir_cache_file):
                os.remove(self._output_dir_cache_file)
        except Exception:
            pass

    # ============================================================
    # 桌面版任务栏闪烁 + 通知钩子
    # ============================================================

    def _notify_desktop(self, title, message, error=False):
        """桌面版完成/失败时：闪任务栏 + 广播 SSE 事件。
        非桌面版或 NOTIFY 关闭时静默跳过。"""
        if not self._is_desktop_opt("NOTIFY"):
            return
        level = "error" if error else "success"
        logger.info("📣 桌面通知 [%s]: %s — %s", level, title, message)
        self._flash_taskbar()
        self._sse_publish({
            "type": "notify",
            "level": level,
            "title": title,
            "message": message,
            "ts": time.strftime("%H:%M:%S"),
        })

    @staticmethod
    def _flash_taskbar():
        """ctypes 闪任务栏按钮 (FlashWindowEx)"""
        if not os.name == "nt":
            return
        try:
            import ctypes
            from ctypes import wintypes
            class FLASHWINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.UINT),
                    ("hwnd", wintypes.HWND),
                    ("dwFlags", wintypes.DWORD),
                    ("uCount", wintypes.UINT),
                    ("dwTimeout", wintypes.DWORD),
                ]
            # 用 Shell_TrayWnd 作为宿主（闪烁任务栏整体）
            hwnd = ctypes.windll.user32.FindWindowW("Shell_TrayWnd", None)
            if not hwnd:
                return
            info = FLASHWINFO(
                cbSize=ctypes.sizeof(FLASHWINFO),
                hwnd=hwnd,
                dwFlags=3,  # FLASHW_ALL
                uCount=3,
                dwTimeout=0,
            )
            ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
            # 2 秒后停止闪烁
            import threading
            def _stop():
                time.sleep(2.0)
                info.dwFlags = 0  # FLASHW_STOP
                try:
                    ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
                except Exception:
                    pass
            threading.Thread(target=_stop, daemon=True).start()
        except Exception as e:
            logger.debug("任务栏闪烁失败: %s", e)

    def _sse_publish(self, event):
        """向所有 SSE 客户端广播事件。无客户端时静默。"""
        try:
            import json as _json
            clients = getattr(self, "_sse_clients", None)
            if not clients:
                return
            payload = _json.dumps(event, ensure_ascii=False)
            for q in list(clients):
                try:
                    q.put_nowait(payload)
                except Exception:
                    pass
        except Exception:
            pass
