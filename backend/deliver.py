"""交付职责：成片回传、分集计数、交付进度、修改版本。"""
import os
import os as _os
import re
import time
import time as _time
import shutil
import shutil as _shutil
import subprocess
import subprocess as _sp
import logging
import threading
from datetime import datetime
from scan import _natural_key, _quick_find_file

logger = logging.getLogger(__name__)


def _shell_copy_file(src_path, dst_dir):
    """用 Windows Shell.Application 弹出系统原生复制进度对话框复制文件。
    返回 True 表示已成功发起复制请求（复制在后台进行），False 表示失败。
    仅在 Windows 下可用；其他系统 fallback 到 shutil.copy。"""
    if not os.name == 'nt':
        os.makedirs(dst_dir, exist_ok=True)
        shutil.copy2(src_path, os.path.join(dst_dir, os.path.basename(src_path)))
        return True
    try:
        import pythoncom
        from win32com.client import Dispatch
        pythoncom.CoInitialize()
        try:
            shell = Dispatch('Shell.Application')
            folder_src = shell.Namespace(os.path.dirname(src_path))
            item_src = folder_src.ParseName(os.path.basename(src_path))
            if item_src is None:
                raise OSError("Shell 找不到源文件: " + src_path)
            os.makedirs(dst_dir, exist_ok=True)
            folder_dst = shell.Namespace(dst_dir)
            if folder_dst is None:
                raise OSError("Shell 找不到目标目录: " + dst_dir)
            # 0x10 = 自动重命名冲突文件, 0x0 = 默认(弹系统进度对话框)
            folder_dst.CopyHere(item_src, 0x10)
            logger.info('Shell.CopyHere 已发起: %s → %s', src_path, dst_dir)
            return True
        finally:
            pythoncom.CoUninitialize()
    except ImportError:
        logger.warning('pywin32 不可用, fallback 到 shutil.copy')
        os.makedirs(dst_dir, exist_ok=True)
        shutil.copy2(src_path, os.path.join(dst_dir, os.path.basename(src_path)))
        return True
    except Exception as e:
        logger.warning('Shell.CopyHere 失败(%s), fallback 到 cmd copy', e)
        os.makedirs(dst_dir, exist_ok=True)
        dst = os.path.join(dst_dir, os.path.basename(src_path))
        result = subprocess.run(
            ["cmd", "/c", "copy", "/y", src_path, dst],
            capture_output=True, timeout=300)
        if result.returncode != 0:
            err = (result.stderr or result.stdout or b"").decode("gbk", errors="replace").strip()
            raise OSError("cmd copy 失败: " + err)
        return True


def _shell_copy_folder(src_folder, dst_parent_dir):
    """用 Shell.Application 弹出系统原生复制对话框复制整个文件夹。"""
    if not os.name == 'nt':
        dst = os.path.join(dst_parent_dir, os.path.basename(src_folder))
        os.makedirs(dst_parent_dir, exist_ok=True)
        if os.path.isdir(dst):
            shutil.copytree(src_folder, dst, dirs_exist_ok=True)
        else:
            shutil.copytree(src_folder, dst)
        return True
    try:
        import pythoncom
        from win32com.client import Dispatch
        pythoncom.CoInitialize()
        try:
            shell = Dispatch('Shell.Application')
            parent = os.path.dirname(src_folder.rstrip('\\/'))
            folder_src = shell.Namespace(parent)
            item_src = folder_src.ParseName(os.path.basename(src_folder.rstrip('\\/')))
            if item_src is None:
                raise OSError("Shell 找不到源文件夹: " + src_folder)
            os.makedirs(dst_parent_dir, exist_ok=True)
            folder_dst = shell.Namespace(dst_parent_dir)
            folder_dst.CopyHere(item_src, 0x10)
            logger.info('Shell.CopyFolder 已发起: %s → %s', src_folder, dst_parent_dir)
            return True
        finally:
            pythoncom.CoUninitialize()
    except ImportError:
        logger.warning('pywin32 不可用, fallback 到 shutil.copytree')
        dst = os.path.join(dst_parent_dir, os.path.basename(src_folder.rstrip('\\/')))
        os.makedirs(dst_parent_dir, exist_ok=True)
        shutil.copytree(src_folder, dst, dirs_exist_ok=True)
        return True
    except Exception as e:
        logger.warning('Shell.CopyFolder 失败(%s), fallback 到 robocopy', e)
        name = os.path.basename(src_folder.rstrip('\\/'))
        dst = os.path.join(dst_parent_dir, name)
        os.makedirs(dst_parent_dir, exist_ok=True)
        shutil.copytree(src_folder, dst, dirs_exist_ok=True)
        return True


def _shell_copy_files_batch(src_dir, file_names, dst_dir):
    """批量复制多个文件 — 弹一个统一的系统原生进度对话框。
    原理: 临时目录名 = dst_dir 的 basename → CopyHere 到父目录 → Shell 自动合并内容。
    硬链接把文件"挂"到临时目录 (同盘零耗时)。"""
    import tempfile as _tf
    import shutil as _shu
    dst_name = os.path.basename(dst_dir.rstrip("\\/"))
    dst_parent = os.path.dirname(dst_dir.rstrip("\\/"))
    if not dst_name or not dst_parent:
        raise OSError("目标目录无效: " + dst_dir)

    # 构造临时目录: <tmp>/<dst_name>/  名字和目标目录相同
    container = _tf.mkdtemp(prefix='deliver_batch_')
    tmp_folder = os.path.join(container, dst_name)
    os.makedirs(tmp_folder, exist_ok=True)

    for fname in file_names:
        src_path = os.path.join(src_dir, fname) if not os.path.isabs(fname) else fname
        if not os.path.isfile(src_path):
            logger.warning('批量复制跳过不存在的文件: %s', src_path)
            continue
        dest_link = os.path.join(tmp_folder, os.path.basename(fname))
        try:
            os.link(src_path, dest_link)
        except OSError:
            try:
                os.symlink(src_path, dest_link)
            except (OSError, NotImplementedError):
                _shu.copy2(src_path, dest_link)

    if not os.listdir(tmp_folder):
        raise OSError("所有文件都找不到, 没有可复制的内容")

    if not os.name == 'nt':
        os.makedirs(dst_dir, exist_ok=True)
        for fname in os.listdir(tmp_folder):
            _shu.copy2(os.path.join(tmp_folder, fname), os.path.join(dst_dir, fname))
        _shu.rmtree(container, ignore_errors=True)
        return True

    try:
        import pythoncom
        from win32com.client import Dispatch
        pythoncom.CoInitialize()
        try:
            shell = Dispatch('Shell.Application')
            # Namespace 临时容器目录, 拿里面那个同名文件夹 item
            folder_container = shell.Namespace(container)
            tmp_folder_item = folder_container.ParseName(dst_name)
            folder_parent = shell.Namespace(dst_parent)
            folder_parent.CopyHere(tmp_folder_item, 0x10)
            logger.info('Shell.CopyHere 批量已发起: %d 个文件 → %s', len(file_names), dst_dir)
            # 延迟清理: Shell 复制是异步的, 等几秒让它开始 (CopyHere 是 Folder 级别, Shell 会自己处理)
            import threading as _th
            def _cleanup():
                import time as _t
                _t.sleep(15)
                _shu.rmtree(container, ignore_errors=True)
            _th.Thread(target=_cleanup, daemon=True).start()
            return True
        finally:
            pythoncom.CoUninitialize()
    except ImportError:
        logger.warning('pywin32 不可用, fallback 到 shutil')
        os.makedirs(dst_dir, exist_ok=True)
        for fname in os.listdir(tmp_folder):
            _shu.copy2(os.path.join(tmp_folder, fname), os.path.join(dst_dir, fname))
        _shu.rmtree(container, ignore_errors=True)
        return True
    except Exception as e:
        logger.warning('Shell.CopyHere 批量失败(%s), fallback 到 cmd copy', e)
        os.makedirs(dst_dir, exist_ok=True)
        for fname in os.listdir(tmp_folder):
            try:
                _shu.copy2(os.path.join(tmp_folder, fname), os.path.join(dst_dir, fname))
            except Exception:
                pass
        _shu.rmtree(container, ignore_errors=True)
        return True


class DeliverMixin:
    _EP_PATTERNS = [
        re.compile(r'(?i)(?:^|[^a-z0-9])EP[_\s\-]?(\d{1,3})(?!\d)'),
        re.compile(r'(?i)(?:^|[^a-z0-9])S\d{1,2}E[_\s\-]?(\d{1,3})(?!\d)'),
        re.compile(r'第[_\s\-]*(\d{1,3})[集话]'),
        re.compile(r'(?:[_\-\s]|^)(\d{1,3})(?:[_\-\s\.]|$)'),
    ]

    def deliver_file(self, project_name, file_path):
        """手动回传成片：从组内NAS 01上映单集版 → 制作部NAS对应项目的01上映单集版"""
        proj = self.db.get_project(project_name)
        if not proj:
            return False, "项目不存在"

        # 如果传了绝对路径直接使用；否则在 group 项目下查找
        src = file_path
        if not os.path.isabs(file_path):
            # 在组内项目目录下递归找 01上映单集版
            group_output_dirs = self._find_output_dirs(
                proj["group_path"], project_name)
            for od in group_output_dirs:
                candidate = os.path.join(od, file_path)
                if os.path.isfile(candidate):
                    src = candidate
                    break
            else:
                # 简单兜底：在 group_path 下浅层（4 层内）快速找文件名，超时或找不到直接让用户用完整路径
                found = _quick_find_file(proj["group_path"], file_path, max_depth=4)
                if not found:
                    return False, "未在组内项目目录中找到文件: " + file_path + \
                        "，请使用完整路径重试"
                src = found

        if not os.path.isfile(src):
            return False, "文件不存在: " + src

        filename = os.path.basename(src)

        # 在制作部项目目录下递归查找 01上映单集版
        prod_output_dirs = self._find_output_dirs(
            proj["production_path"], project_name)

        if not prod_output_dirs:
            return False, "制作部项目目录中未找到 %s 目录" % \
                self._get_output_dir_name(project_name)

        # 使用第一个匹配的制作部输出目录
        dst_dir = prod_output_dirs[0]
        dst = os.path.join(dst_dir, filename)

        try:
            file_size = os.path.getsize(src)
            _shell_copy_file(src, dst_dir)

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.db.add_delivery_log(
                project_name, filename, src, dst, file_size,
                "success", "手动回传成功")
            self.db.update_project_status(
                project_name, delivery_status="delivered",
                last_delivered_at=now)
            return True, "回传成功: " + dst
        except Exception as e:
            self.db.add_delivery_log(
                project_name, filename, src, dst, 0,
                "error", str(e))
            return False, str(e)

    def deliver_files_batch(self, project_name, file_names):
        """批量回传成片 — Shell 弹一个统一的系统原生进度对话框"""
        proj = self.db.get_project(project_name)
        if not proj:
            return [{"name": n, "ok": False, "message": "项目不存在", "index": i + 1, "total": len(file_names)} for i, n in enumerate(file_names)]

        # 收集所有源路径 → 按目录分组
        file_map = []  # [(abs_src_path, fname)]
        for fname in file_names:
            src = fname if os.path.isabs(fname) else None
            if not src:
                group_output_dirs = self._find_output_dirs(proj.get("group_path", ""), project_name)
                for od in group_output_dirs:
                    candidate = os.path.join(od, fname)
                    if os.path.isfile(candidate):
                        src = candidate
                        break
            if not src:
                found = _quick_find_file(proj.get("group_path", ""), fname, max_depth=4)
                src = found
            if src and os.path.isfile(src):
                file_map.append((src, fname))

        if not file_map:
            self.db.update_project_status(
                project_name, delivery_status="error",
                sync_progress="批量回传失败: 所有文件都找不到")
            return [{"name": n, "ok": False, "message": "文件不存在", "index": i + 1, "total": len(file_names)} for i, n in enumerate(file_names)]

        # 确定目标目录
        prod_output_dirs = self._find_output_dirs(proj.get("production_path", ""), project_name)
        if not prod_output_dirs:
            self.db.update_project_status(
                project_name, delivery_status="error",
                sync_progress="批量回传失败: 制作部目录中未找到 01上映单集版")
            return [{"name": n, "ok": False, "message": "制作部目录中未找到对应输出目录", "index": i + 1, "total": len(file_names)} for i, n in enumerate(file_names)]

        dst_dir = prod_output_dirs[0]
        os.makedirs(dst_dir, exist_ok=True)

        # 按源目录分组 (避免跨盘问题, 硬链接只能同盘)
        by_src_dir = {}
        for src_path, fname in file_map:
            sd = os.path.dirname(src_path)
            by_src_dir.setdefault(sd, []).append(src_path)

        self.db.update_project_status(
            project_name, delivery_status="delivering",
            sync_progress="已发起 Shell 批量复制 ({} 个文件) — 看系统进度对话框".format(len(file_map)))

        # 每个源目录独立发起一次批量 Shell.CopyHere
        errors = []
        for src_dir, paths in by_src_dir.items():
            try:
                _shell_copy_files_batch(src_dir, paths, dst_dir)
            except Exception as e:
                logger.error('Shell 批量复制失败 %s → %s: %s', src_dir, dst_dir, e)
                errors.append(str(e))

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if errors:
            self.db.update_project_status(
                project_name, delivery_status="error",
                sync_progress="部分失败: " + "; ".join(errors[:2]),
                last_delivered_at=now)
        else:
            # Shell.CopyHere 是异步的, 此时只表示"已发起"
            # 保持 delivering 状态一会儿, 让用户看 Shell 对话框
            def _mark_done():
                import time as _t
                _t.sleep(5)
                self.db.update_project_status(
                    project_name, delivery_status="delivered",
                    sync_progress="", last_delivered_at=now)
            import threading as _th
            _th.Thread(target=_mark_done, daemon=True).start()

        # 返回结果列表 (所有已成功发起)
        results = []
        for i, (src_path, fname) in enumerate(file_map):
            ok = fname not in errors
            results.append({
                "name": fname,
                "ok": ok,
                "message": "已发起 Shell 批量复制" if ok else "失败: " + str(errors[0] if errors else "未知"),
                "index": i + 1, "total": len(file_map),
            })
            self.db.add_delivery_log(
                project_name, fname, src_path,
                os.path.join(dst_dir, fname),
                os.path.getsize(src_path) if os.path.isfile(src_path) else 0,
                "success" if ok else "error",
                "Shell 批量回传" if ok else "批量失败: " + str(errors[0] if errors else "未知"))

        return results

    def list_output_files(self, project_name):
        """列出项目所有 01上映单集版 目录中的文件（group → production fallback）。
        每个文件带 delivered 字段: True 表示制作部已有同名文件, False 表示未回传。"""
        proj = self.db.get_project(project_name)
        if not proj:
            return []

        group_path = proj.get("group_path", "")
        production_path = proj.get("production_path", "")

        output_dirs = self._find_output_dirs(group_path, project_name) if group_path else []
        if not output_dirs and production_path:
            output_dirs = self._find_output_dirs(production_path, project_name)

        if not output_dirs:
            return []

        # 预先扫描制作部目标目录, 拿到所有 (文件名, 大小) 集合
        dest_info = {}  # filename -> (size, mtime)
        if production_path:
            dest_dirs = self._find_output_dirs(production_path, project_name)
            for dd in dest_dirs:
                try:
                    for name in os.listdir(dd):
                        full = os.path.join(dd, name)
                        if os.path.isfile(full):
                            try:
                                dest_info[name] = (
                                    os.path.getsize(full),
                                    os.path.getmtime(full),
                                )
                            except OSError:
                                pass
                except OSError:
                    continue

        files = []
        seen = set()
        for od in output_dirs:
            try:
                for name in os.listdir(od):
                    if name in seen:
                        continue
                    seen.add(name)
                    full = os.path.join(od, name)
                    if os.path.isfile(full):
                        ext = os.path.splitext(name)[1].lower()
                        size = os.path.getsize(full)
                        delivered = name in dest_info
                        dest_size = dest_info.get(name, (0, 0))[0] if delivered else 0
                        size_match = delivered and abs(size - dest_size) < 1024  # 允许 1KB 误差
                        status = "delivered" if delivered else "pending"
                        if delivered and not size_match:
                            status = "size_mismatch"
                        files.append({
                            "name": name,
                            "path": full,
                            "size": size,
                            "size_mb": round(size / 1024 / 1024, 1),
                            "ext": ext,
                            "mtime": datetime.fromtimestamp(
                                os.path.getmtime(full)).strftime(
                                "%Y-%m-%d %H:%M"),
                            "parent_dir": os.path.basename(od) if od else "",
                            "delivered": delivered,
                            "delivery_status": status,  # delivered / pending / size_mismatch
                            "dest_size": dest_size,
                        })
            except OSError:
                continue

        files.sort(key=lambda x: _natural_key(x["name"]))
        return files

    def check_delivery_status(self, project_name):
        """比较组内NAS和制作部NAS的成片目录文件列表，自动判断交付状态。
        返回 'delivered' / 'partial' / 'pending' / None（无法判断）
        """
        proj = self.db.get_project(project_name)
        if not proj:
            return None

        prod_path = proj.get("production_path", "")
        group_path = proj.get("group_path", "")

        if not prod_path or not group_path:
            return None

        source_dirs = self._find_output_dirs(group_path, project_name)
        if not source_dirs:
            return None  # 组内没有成片目录

        # 获取源文件名集合
        source_files = set()
        for sd in source_dirs:
            try:
                for name in os.listdir(sd):
                    if os.path.isfile(os.path.join(sd, name)):
                        source_files.add(name)
            except OSError:
                continue

        if not source_files:
            return None  # 没有成片文件

        dest_dirs = self._find_output_dirs(prod_path, project_name)
        if not dest_dirs:
            return "pending"  # 制作部没有成片目录

        # 获取目标文件名集合
        dest_files = set()
        for dd in dest_dirs:
            try:
                for name in os.listdir(dd):
                    if os.path.isfile(os.path.join(dd, name)):
                        dest_files.add(name)
            except OSError:
                continue

        # 检查所有源文件是否都存在于目标
        if source_files.issubset(dest_files):
            return "delivered"
        elif source_files & dest_files:
            return "partial"
        else:
            return "pending"

    def _start_delivery_check_background(self, production):
        """在后台线程中检测交付状态，避免阻塞 API 响应"""
        if self._delivery_check_running:
            return
        self._delivery_check_running = True

        def _check():
            try:
                for proj in production:
                    name = proj["name"]
                    current_status = proj.get("delivery_status", "pending")
                    if current_status == "delivering":
                        continue  # 正在回传中，跳过
                    auto_status = self.check_delivery_status(name)
                    if auto_status and auto_status != current_status:
                        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        delivered_at = proj.get("last_delivered_at") or ""
                        if auto_status == "delivered" and not delivered_at:
                            delivered_at = now
                        self.db.update_project_status(
                            name,
                            delivery_status=auto_status,
                            last_delivered_at=delivered_at or None)
                        logger.info("交付状态更新: %s %s -> %s",
                                    name, current_status, auto_status)
            except Exception as e:
                logger.error("后台交付状态检测失败: %s", e)
            finally:
                self._delivery_check_running = False

        threading.Thread(target=_check, daemon=True).start()

    def _move_to_completed(self, project_name):
        """将组内NAS上的项目目录移动到 O盘/00已完成/ 子目录。
        用于设为"已完成"时归档项目。
        """
        proj = self.db.get_project(project_name)
        if not proj:
            return False, "项目不存在"

        group_root = self.nas.get("group_root", "")
        group_path = proj.get("group_path", "")
        if not group_path or not os.path.isdir(group_path):
            # 组内路径不存在（可能本来就只有制作部NAS侧的记录），跳过
            return True, "项目无组内NAS目录，跳过移动"

        target_root = os.path.join(group_root, "00已完成")
        project_dir_name = os.path.basename(group_path.rstrip("\\/"))
        target_path = os.path.join(target_root, project_dir_name)

        # 已经在 00已完成 下了？跳过
        norm_target_root = os.path.normpath(target_root).rstrip("\\/")
        norm_group_path = os.path.normpath(group_path).rstrip("\\/")
        if norm_group_path.startswith(norm_target_root + os.sep) or norm_group_path == norm_target_root:
            return True, "项目已在 00已完成 下，跳过移动"

        # 目标已存在同名目录（用户可能已手动移动过）
        if os.path.isdir(target_path):
            return True, "00已完成 下已存在同名目录，跳过移动"

        # 确保 00已完成 目录存在
        try:
            os.makedirs(target_root, exist_ok=True)
        except (PermissionError, OSError):
            unc_target_root = self._to_unc(target_root)
            result = subprocess.run(
                ["cmd", "/c", "mkdir", unc_target_root],
                capture_output=True, timeout=30)
            if result.returncode != 0 and not os.path.isdir(target_root):
                return False, "无法创建 00已完成 目录"

        # 执行移动
        moved = False
        try:
            shutil.move(group_path, target_path)
            moved = True
        except Exception as e:
            logger.warning("直接 shutil.move 失败，尝试 cmd move: %s", e)

        if not moved:
            src_unc = self._to_unc(group_path)
            dst_unc = self._to_unc(target_path)
            result = subprocess.run(
                ["cmd", "/c", "move", "/-y", src_unc, dst_unc],
                capture_output=True, timeout=300)
            if result.returncode != 0 or not os.path.isdir(target_path):
                err = (result.stderr or result.stdout or b"Unknown")
                err_text = err.decode("gbk", errors="replace").strip()
                return False, "移动失败: " + err_text

        # 更新 DB 中的 group_path
        self.db.update_project_status(project_name, group_path=target_path)
        # 清缓存
        with self._lock:
            self._output_dir_cache.clear()

        logger.info("项目已移入 00已完成: %s -> %s", group_path, target_path)
        self.db.add_sync_log(
            project_name, "移入已完成", "group",
            file_path=target_path, status="success",
            message="已移入 00已完成")
        return True, "项目已移入 00已完成"

    def set_custom_status(self, project_name, status):
        """设置项目的自定义状态（剪辑中/审核中/修改中/待交付/已完成）。
        - 设为"修改中"时，在01上映单集版目录中新建以日期命名的文件夹（如0810修改）。
        - 设为"待交付"时，自动将交付文件夹模板复制到项目根目录。
        - 设为"已完成"时，自动将组内NAS项目移动到 00已完成 子目录。
        """
        valid_statuses = ["", "分集中", "剪辑中", "审核中", "修改中", "交付中", "待交付", "待质检", "质检中", "已完成"]
        if status not in valid_statuses:
            return False, "无效的状态: " + str(status)

        proj = self.db.get_project(project_name)
        if not proj:
            return False, "项目不存在"

        old_status = proj.get("custom_status", "")
        self.db.update_project_status(project_name, custom_status=status)
        logger.info("项目状态变更: %s %s -> %s", project_name, old_status, status)

        # 设为"修改中"时，在01上映单集版目录中新建日期文件夹
        if status == "修改中":
            ok, msg = self._create_revision_folder(project_name)
            if not ok:
                return True, "状态已更新为修改中，但创建修改文件夹失败: " + msg
            return True, "状态已更新为修改中，" + msg

        # 设为"待交付"时，自动复制交付文件夹到项目根目录
        if status == "待交付":
            ok, msg = self._copy_delivery_folder(project_name)
            if not ok:
                return True, "状态已更新为待交付，但交付文件夹复制失败: " + msg
            return True, "状态已更新为待交付，交付文件夹已复制到项目根目录"

        # 设为"已完成"时，自动将组内NAS项目移入 00已完成 子目录
        if status == "已完成":
            ok, msg = self._move_to_completed(project_name)
            if not ok:
                return True, "状态已更新为已完成，但移动项目失败: " + msg
            return True, "状态已更新为已完成，" + msg

        return True, "状态已更新为: " + status

    def _create_revision_folder(self, project_name):
        """在项目的01上映单集版目录中新建以日期命名的修改文件夹（如0810修改）。
        如果同名文件夹已存在则不重复创建。
        管理员进程无法直接写映射盘符，用 UNC 路径 + cmd mkdir 兜底。
        """
        proj = self.db.get_project(project_name)
        if not proj:
            return False, "项目不存在"

        group_path = proj.get("group_path", "")
        if not group_path:
            return False, "项目无组内路径"

        # 查找01上映单集版目录
        output_dirs = self._find_output_dirs(group_path, project_name)
        if not output_dirs:
            return False, "未找到%s目录" % self._get_output_dir_name(project_name)

        output_dir = output_dirs[0]

        # 生成日期文件夹名：MMDD修改
        now = datetime.now()
        folder_name = "%02d%02d修改" % (now.month, now.day)
        folder_path = os.path.join(output_dir, folder_name)

        # 检查是否已存在（用 UNC 路径检查，绕过权限隔离）
        unc_path = self._to_unc(folder_path)
        if os.path.isdir(unc_path) or os.path.isdir(folder_path):
            return True, "修改文件夹已存在: " + folder_name

        try:
            # 方案1：直接 Python makedirs（非管理员模式可用）
            try:
                os.makedirs(folder_path, exist_ok=True)
            except (PermissionError, OSError):
                # 方案2：管理员权限隔离，用 cmd mkdir + UNC 路径兜底
                result = subprocess.run(
                    ["cmd", "/c", "mkdir", unc_path],
                    capture_output=True, timeout=30)
                if result.returncode != 0 and not os.path.isdir(folder_path):
                    raise OSError(
                        "无法创建文件夹（权限被拒绝）。"
                        "请确保程序以非管理员模式运行（双击 start.bat 启动即可）。")

            logger.info("创建修改文件夹: %s", folder_path)
            self.db.add_sync_log(
                project_name, "创建修改文件夹", "group",
                file_path=folder_path, status="success",
                message="已创建: " + folder_name)
            return True, "已创建修改文件夹: " + folder_name
        except Exception as e:
            self.db.add_sync_log(
                project_name, "创建修改文件夹失败", "group",
                file_path=folder_path, status="error", message=str(e))
            return False, str(e)

    def _copy_delivery_folder(self, project_name):
        """将交付文件夹整个复制到项目根目录下（组内NAS侧）。
        结果结构：项目根目录/000交付/00成片/...
        不修改项目原有任何文件。
        """
        proj = self.db.get_project(project_name)
        if not proj:
            return False, "项目不存在"

        group_path = proj.get("group_path", "")
        if not group_path:
            return False, "项目无组内路径"

        src = self._delivery_folder
        if not os.path.isdir(src):
            return False, "交付文件夹不存在: " + src

        # 目标：项目根目录/000交付（保留文件夹名，整体复制进去）
        folder_name = os.path.basename(src.rstrip("\\/"))
        dst = os.path.join(group_path, folder_name)

        logger.info("复制交付文件夹: %s -> %s", src, dst)
        self.db.add_sync_log(
            project_name, "复制交付文件夹", "delivery_folder->group",
            file_path=src, status="info",
            message="源: " + src + " -> 目标: " + dst)

        try:
            # 注意：不能用 /MIR 镜像模式！这里用 /E 纯增量复制
            cmd = ["robocopy", src, dst] + ROBOCOPY_BASE
            dst_unc = self._to_unc(dst)
            unc_alt = None
            if dst_unc != dst:
                unc_alt = ["robocopy", src, dst_unc] + ROBOCOPY_BASE
            ok, msg, rc = _exec(cmd, TIMEOUT_XCOPY_BIG,
                                label="copy_delivery_folder", unc_alt=unc_alt)
            if ok:
                self.db.add_sync_log(
                    project_name, "交付文件夹复制完成", "delivery_folder->group",
                    file_path=src, status="success", message="已复制到: " + dst)
                return True, "复制完成"
            else:
                self.db.add_sync_log(
                    project_name, "交付文件夹复制失败", "delivery_folder->group",
                    file_path=src, status="error", message=msg)
                return False, "robocopy 返回码 %d: %s" % (rc, msg)
        except Exception as e:
            self.db.add_sync_log(
                project_name, "交付文件夹复制异常", "delivery_folder->group",
                file_path=src, status="error", message=str(e))
            return False, str(e)

    def deliver_to_production(self, project_name):
        """一键交付：把组内NAS项目下的 000交付 整个复制到制作部NAS对应项目的 000交付 目录。
        异步执行，进度通过 get_deliver_status 查询。
        """
        proj = self.db.get_project(project_name)
        if not proj:
            return False, "项目不存在"

        group_path = proj.get("group_path", "") or ""
        prod_path = proj.get("production_path", "") or ""
        if not prod_path:
            return False, "该项目无制作部NAS路径，无法一键交付"

        folder_name = os.path.basename(self._delivery_folder.rstrip("\\/"))
        src = os.path.join(group_path, folder_name)
        if not os.path.isdir(src):
            return False, "组内NAS项目下不存在 %s 目录" % folder_name

        dst = os.path.join(prod_path, folder_name)

        with self._lock:
            existing = self._deliver_tasks.get(project_name)
            if existing and existing.get("status") in ("running", "starting"):
                return False, "已有交付任务在进行中"

        total_files = 0
        try:
            for _, _, files in os.walk(src):
                total_files += len(files)
        except OSError:
            pass

        run_id = self.db.insert_deliver_run(
            project_name, src, dst, total_files,
            status="running", message="正在准备...",
            started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        with self._lock:
            self._deliver_tasks[project_name] = {
                "run_id": run_id,
                "status": "starting",
                "total": total_files,
                "current": 0,
                "pct": 0,
                "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "message": "正在准备...",
                "src": src,
                "dst": dst,
            }

        self.db.add_sync_log(
            project_name, "一键交付启动", "group->production",
            file_path=src, status="info",
            message="目标: " + dst + "，共 " + str(total_files) + " 个文件")

        threading.Thread(
            target=self._run_deliver_to_production,
            args=(project_name, src, dst),
            daemon=True).start()
        threading.Thread(
            target=self._poll_deliver_progress,
            args=(project_name,),
            daemon=True).start()

        return True, "交付已启动，共 %d 个文件" % total_files

    def deliver_initial_version(self, project_name):
        """把组内 NAS 的 01上映单集版 目录整体推送到制作部 NAS，完成后状态自动变为"审核中"。
        触发场景：剪辑中的项目点击"统计"后发现集数已达标。
        """
        proj = self.db.get_project(project_name)
        if not proj:
            return False, "项目不存在"

        if proj.get("custom_status") != "剪辑中":
            return False, "仅剪辑中的项目可执行初版交付"

        src, err = self.get_source_dir(project_name)
        if not src:
            return False, "组内成片目录未找到: " + str(err)

        dst, err = self.get_dest_dir(project_name)
        if not dst:
            # 制作部成片目录还不存在，自动创建
            prod_path = proj.get("production_path", "")
            dst = os.path.join(prod_path, self._get_output_dir_name(project_name))
            try:
                os.makedirs(dst, exist_ok=True)
            except Exception as e:
                return False, "无法创建制作部成片目录: " + str(e)

        with self._lock:
            existing = self._deliver_tasks.get(project_name)
            if existing and existing.get("status") in ("running", "starting"):
                return False, "已有交付任务在进行中"

        total_files = 0
        try:
            for _, _, files in os.walk(src):
                total_files += len(files)
        except OSError:
            pass

        run_id = self.db.insert_deliver_run(
            project_name, src, dst, total_files,
            status="running", message="初版交付 - 正在准备...",
            started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        with self._lock:
            self._deliver_tasks[project_name] = {
                "run_id": run_id,
                "task_type": "initial_version",
                "status": "starting",
                "total": total_files,
                "current": 0,
                "pct": 0,
                "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "message": "初版交付 - 正在准备...",
                "src": src,
                "dst": dst,
            }

        self.db.add_sync_log(
            project_name, "初版交付启动", "group->production",
            file_path=src, status="info",
            message="目标: " + dst + "，共 " + str(total_files) + " 个文件")

        threading.Thread(
            target=self._run_deliver_initial_version,
            args=(project_name, src, dst),
            daemon=True).start()
        threading.Thread(
            target=self._poll_deliver_progress,
            args=(project_name,),
            daemon=True).start()

        return True, "初版交付已启动，共 %d 个文件" % total_files

    def _run_deliver_initial_version(self, project_name, src, dst):
        with self._lock:
            task = self._deliver_tasks.get(project_name, {})
            task["status"] = "running"
            task["message"] = "初版交付 - 正在复制..."
        proc = None
        use_com = self._is_desktop_opt("CAN_COM")
        try:
            os.makedirs(dst, exist_ok=True)

            if use_com:
                ok, msg = self._copy_desktop_com(src, dst, timeout=TIMEOUT_ROBOCOPY_FAST)
                if ok:
                    with self._lock:
                        task["current"] = task["total"]
                        task["pct"] = 100
                        task["status"] = "done"
                        task["message"] = "初版交付完成（系统复制）"
                        task["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self.db.update_project_status(
                        project_name,
                        custom_status="审核中",
                        delivery_status="delivered",
                        last_delivered_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    )
                    self.db.add_sync_log(
                        project_name, "初版交付完成→审核中", "group->production",
                        file_path=src, status="success",
                        message="成片已推送到: " + dst + "（Shell 系统复制）")
                    self._notify_desktop("✅ 初版交付完成", project_name + " 已推送到制作部，状态→审核中")
                else:
                    logger.info("初版交付 COM 失败 (%s), fallback robocopy", msg)
                    raise RuntimeError("COM 复制失败，fallback robocopy: " + msg)
            else:
                cmd = ["robocopy", src, dst] + ROBOCOPY_FAST
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                with self._lock:
                    task["proc_pid"] = proc.pid
                stdout, stderr = proc.communicate(timeout=TIMEOUT_ROBOCOPY_FAST)
                rc = proc.returncode
                success = rc < 8
                if success:
                    with self._lock:
                        task["current"] = task["total"]
                        task["pct"] = 100
                        task["status"] = "done"
                        task["message"] = "初版交付完成，状态→审核中"
                        task["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self.db.update_project_status(
                        project_name,
                        custom_status="审核中",
                        delivery_status="delivered",
                        last_delivered_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    )
                    self.db.add_sync_log(
                        project_name, "初版交付完成→审核中", "group->production",
                        file_path=src, status="success",
                        message="成片已推送到: " + dst + "，robocopy rc=" + str(rc))
                    self._notify_desktop("✅ 初版交付完成", project_name + " 已推送到制作部，状态→审核中")
                else:
                    err = stderr.decode("gbk", errors="replace")[:500] \
                        if stderr else "robocopy rc=%d" % rc
                    with self._lock:
                        task["status"] = "error"
                        task["message"] = "初版交付失败: " + err
                    self._cleanup_partial_dst(dst)
                    self.db.add_sync_log(
                        project_name, "初版交付失败", "group->production",
                        file_path=src, status="error", message=err)
                    self._notify_desktop("❌ 初版交付失败", project_name + ": " + err, error=True)
        except subprocess.TimeoutExpired:
            if proc:
                proc.kill()
                proc.wait()
            with self._lock:
                task["status"] = "error"
                task["message"] = "初版交付超时（超过1小时）"
            self._cleanup_partial_dst(dst)
            self._notify_desktop("⚠️ 初版交付超时", project_name, error=True)
        except Exception as e:
            if proc:
                try:
                    proc.kill()
                except Exception:
                    pass
            with self._lock:
                task["status"] = "error"
                task["message"] = "初版交付异常: " + str(e)
            if not use_com:
                self._cleanup_partial_dst(dst)
            self._notify_desktop("❌ 初版交付异常", project_name + ": " + str(e), error=True)
        finally:
            run_id = task.get("run_id")
            if run_id:
                try:
                    with self._lock:
                        final_status = task.get("status", "unknown")
                        final_msg = task.get("message", "")
                    self.db.finish_deliver_run(
                        run_id, final_status, final_msg,
                        finished_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                except Exception as _e:
                    logger.warning("finish_deliver_run 失败: %s", _e)

    def _poll_deliver_progress(self, project_name):
        """独立后台线程：周期性 os.walk 目标目录更新进度（不在 API 请求里做，避免卡死）"""
        for _ in range(240):  # 最多 240*2=480s
            _time.sleep(2)
            with self._lock:
                task = self._deliver_tasks.get(project_name)
                if not task:
                    break
                if task.get("status") not in ("running", "starting"):
                    break
                dst = task.get("dst", "")
            if not dst:
                continue
            try:
                cur = 0
                for _, _, files in os.walk(dst):
                    cur += len(files)
                with self._lock:
                    task["current"] = cur
                    if task["total"] > 0:
                        task["pct"] = min(round(cur / task["total"] * 100), 99)
                    else:
                        task["pct"] = 0
            except OSError:
                pass

    def _run_deliver_to_production(self, project_name, src, dst):
        with self._lock:
            task = self._deliver_tasks.get(project_name, {})
            task["status"] = "running"
            task["message"] = "正在复制..."
        proc = None
        use_com = self._is_desktop_opt("CAN_COM")
        try:
            if use_com:
                ok, msg = self._copy_desktop_com(src, dst, timeout=3600)
                if ok:
                    with self._lock:
                        task["current"] = task["total"]
                        task["pct"] = 100
                        task["status"] = "done"
                        task["message"] = "交付完成（系统复制）"
                        task["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self.db.update_project_status(
                        project_name,
                        delivery_status="delivered",
                        last_delivered_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        custom_status="已完成",
                    )
                    self.db.add_sync_log(
                        project_name, "一键交付完成", "group->production",
                        file_path=src, status="success",
                        message="已交付到: " + dst + "（Shell 系统复制）")
                    self._notify_desktop("✅ 一键交付完成", project_name + " 已全部推送到制作部")
                else:
                    logger.info("一键交付 COM 失败 (%s), fallback robocopy", msg)
                    raise RuntimeError("COM 复制失败，fallback robocopy: " + msg)
            else:
                cmd = ["robocopy", src, dst] + ROBOCOPY_FAST
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                with self._lock:
                    task["proc_pid"] = proc.pid
                stdout, stderr = proc.communicate(timeout=3600)
                rc = proc.returncode
                success = rc < 8
                if success:
                    with self._lock:
                        task["current"] = task["total"]
                        task["pct"] = 100
                        task["status"] = "done"
                        task["message"] = "交付完成"
                        task["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self.db.update_project_status(
                        project_name,
                        delivery_status="delivered",
                        last_delivered_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        custom_status="已完成",
                    )
                    self.db.add_sync_log(
                        project_name, "一键交付完成", "group->production",
                        file_path=src, status="success",
                        message="已交付到: " + dst + "，robocopy rc=" + str(rc))
                    self._notify_desktop("✅ 一键交付完成", project_name + " 已全部推送到制作部")
                else:
                    err = stderr.decode("gbk", errors="replace")[:500] \
                        if stderr else "robocopy rc=%d" % rc
                    with self._lock:
                        task["status"] = "error"
                        task["message"] = "交付失败: " + err
                    self._cleanup_partial_dst(dst)
                    self.db.add_sync_log(
                        project_name, "一键交付失败", "group->production",
                        file_path=src, status="error", message=err)
                    self._notify_desktop("❌ 一键交付失败", project_name + ": " + err, error=True)
        except subprocess.TimeoutExpired:
            if proc:
                proc.kill()
                proc.wait()
            with self._lock:
                task["status"] = "error"
                task["message"] = "交付超时（超过1小时）"
            self._cleanup_partial_dst(dst)
            self._notify_desktop("⚠️ 一键交付超时", project_name, error=True)
        except Exception as e:
            if proc:
                try:
                    proc.kill()
                except Exception:
                    pass
            with self._lock:
                task["status"] = "error"
                task["message"] = "交付异常: " + str(e)
            if not use_com:
                self._cleanup_partial_dst(dst)
            self._notify_desktop("❌ 一键交付异常", project_name + ": " + str(e), error=True)
        finally:
            run_id = task.get("run_id")
            if run_id:
                try:
                    with self._lock:
                        final_status = task.get("status", "unknown")
                        final_msg = task.get("message", "")
                    self.db.finish_deliver_run(
                        run_id, final_status, final_msg,
                        finished_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                except Exception as _e:
                    logger.warning("finish_deliver_run 失败: %s", _e)

    def shutdown(self, wait=False):
        """优雅停机：终止所有在跑的 robocopy 子进程"""
        pids = []
        with self._lock:
            for name, task in list(self._deliver_tasks.items()):
                if task.get("status") == "running" and task.get("proc_pid"):
                    pids.append((name, task["proc_pid"]))
        for name, pid in pids:
            try:
                # Windows: taskkill /F /T /PID 终止整个进程树
                _sp.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                        capture_output=True, timeout=5)
                logger.warning("已终止交付子进程 PID=%s (%s)", pid, name)
            except Exception as e:
                logger.warning("终止 PID=%s 失败: %s", pid, e)
        # 把所有 running 任务标为 aborted
        with self._lock:
            for name, task in self._deliver_tasks.items():
                if task.get("status") == "running":
                    task["status"] = "aborted"
                    task["message"] = "服务关闭时中止"
        logger.info("SyncEngine.shutdown() 完成，清理了 %d 个交付进程", len(pids))

    def get_deliver_status(self, project_name):
        """查询交付任务状态（纯内存读取，不做文件系统操作）"""
        with self._lock:
            task = self._deliver_tasks.get(project_name)
            if not task:
                return {"status": "idle"}
            resp = {k: v for k, v in task.items() if k not in ("src",)}
        return resp

    def set_episodes(self, project_name, total, current):
        """设置项目集数（总集数和当前已输出集数）。
        当 current >= total 且 total > 0 时，返回通知标志。
        """
        proj = self.db.get_project(project_name)
        if not proj:
            return False, "项目不存在", False
        try:
            total = int(total) if total else 0
            current = int(current) if current else 0
        except (ValueError, TypeError):
            return False, "集数必须为整数", False
        if total < 0 or current < 0:
            return False, "集数不能为负数", False
        if current > total and total > 0:
            current = total  # 不超过总集数

        self.db.update_project_status(
            project_name, total_episodes=total, current_episodes=current)
        logger.info("集数设置: %s 总%d集 当前%d集", project_name, total, current)

        completed = total > 0 and current >= total
        return True, "集数已更新", completed

    def auto_count_episodes(self, project_name):
        """自动统计01上映单集版目录中的成片文件数量作为当前集数"""
        proj = self.db.get_project(project_name)
        if not proj:
            return 0
        group_path = proj.get("group_path", "")
        if not group_path:
            return 0
        output_dirs = self._find_output_dirs(group_path, project_name)
        if not output_dirs:
            return 0
        count = 0
        video_exts = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv', '.m4v'}
        for od in output_dirs:
            try:
                for name in os.listdir(od):
                    full = os.path.join(od, name)
                    if os.path.isfile(full):
                        ext = os.path.splitext(name)[1].lower()
                        if ext in video_exts:
                            count += 1
            except OSError:
                continue
        return count

    def _extract_episode_number(self, filename):
        """从单个文件名里提取集号，失败返回 None。"""
        base = os.path.splitext(filename)[0]
        hits = []
        for idx, pat in enumerate(self._EP_PATTERNS):
            for m in pat.finditer(base):
                try:
                    n = int(m.group(1))
                except (TypeError, ValueError):
                    continue
                if 1 <= n <= 999:
                    hits.append((idx, n))
                    break  # 每个 pattern 最多取一次匹配，避免一个文件名里出现多个独立数字
        if not hits:
            return None
        # 优先级：pattern 索引越小越优先
        hits.sort(key=lambda x: x[0])
        return hits[0][1]

    def _collect_video_filenames(self, project_name, which="group"):
        """收集项目视频文件名列表。which: group=组内成片, dest=制作部成片"""
        proj = self.db.get_project(project_name)
        if not proj:
            return []
        if which == "dest":
            root = proj.get("production_path", "")
            dirs = self._find_output_dirs(root, project_name) if root else []
        else:
            root = proj.get("group_path", "")
            dirs = self._find_output_dirs(root, project_name) if root else []
        if not dirs:
            return []
        video_exts = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv', '.m4v'}
        names = []
        for d in dirs:
            try:
                for name in os.listdir(d):
                    full = os.path.join(d, name)
                    if os.path.isfile(full) and os.path.splitext(name)[1].lower() in video_exts:
                        names.append(name)
            except OSError:
                continue
        return names

    def get_episode_status(self, project_name):
        """返回项目剪辑进度详情，供前端渲染：
        {
            ok, project_name,
            total: int (来自 DB),
            current_count: int (实际视频文件数),
            present: [1, 2, 3, ...],          # 从文件名识别的集号
            missing: [4, 27, ...],             # 缺失集号
            unnamed: [文件名...],               # 文件名里没识别出集号的
            editor_plan: {"1": "张三", ...},
            editor_missing: [
                {"episode": 4, "editor": null},
                {"episode": 27, "editor": "王五"},
            ]
        }
        """
        proj = self.db.get_project(project_name)
        if not proj:
            return {"ok": False, "message": "项目不存在"}

        total = int(proj.get("total_episodes") or 0)
        editor_plan = self.db.get_episode_plan(project_name)

        video_names = self._collect_video_filenames(project_name, which="group")
        if not video_names:
            video_names = self._collect_video_filenames(project_name, which="dest")
        current_count = len(video_names)

        present_set = set()
        unnamed = []
        for name in video_names:
            n = self._extract_episode_number(name)
            if n is not None:
                present_set.add(n)
            else:
                unnamed.append(name)

        present = sorted(present_set)

        # 如果 DB 里没设 total 或 total 小于扫描到的最大集号，用 max(present) 自动回填
        if present:
            max_present = max(present)
            if total < max_present:
                logger.info("项目 %s 总集数 DB=%d < 磁盘集数 %d，自动修正并回写", project_name, total, max_present)
                self.db.update_project_status(
                    project_name,
                    total_episodes=max_present,
                    current_episodes=current_count)
                total = max_present

        missing = []
        if total > 0:
            missing = [i for i in range(1, total + 1) if i not in present_set]

        editor_missing = [
            {"episode": ep, "editor": editor_plan.get(str(ep)) or editor_plan.get(ep) or None}
            for ep in missing
        ]

        return {
            "ok": True,
            "project_name": project_name,
            "total": total,
            "current_count": current_count,
            "present": present,
            "missing": missing,
            "unnamed": unnamed,
            "editor_plan": editor_plan,
            "editor_missing": editor_missing,
        }

    def list_all_revision_folders(self, project_name):
        """列出项目01上映单集版目录中所有修改文件夹（MMDD修改格式）。
        返回 [{"name": "MMDD修改", "path": full_path}, ...] 按日期倒序排列。
        """
        proj = self.db.get_project(project_name)
        if not proj:
            return []
        group_path = proj.get("group_path", "")
        if not group_path:
            return []
        output_dirs = self._find_output_dirs(group_path, project_name)
        if not output_dirs:
            return []

        rev_pattern = re.compile(r'^(\d{4})(修改)?$')
        candidates = []
        for od in output_dirs:
            try:
                for name in os.listdir(od):
                    full = os.path.join(od, name)
                    if os.path.isdir(full):
                        m = rev_pattern.match(name)
                        if m:
                            candidates.append({"name": name, "path": full, "date": m.group(1)})
            except OSError:
                continue

        candidates.sort(key=lambda x: x["date"], reverse=True)
        return candidates

    def find_revision_folder(self, project_name):
        """查找项目01上映单集版目录中最近的修改文件夹（MMDD修改格式）。
        返回 (folder_path, folder_name) 或 (None, None)。
        """
        folders = self.list_all_revision_folders(project_name)
        if not folders:
            return None, None
        return folders[0]["path"], folders[0]["name"]

    def get_delivery_stats(self, project_name):
        """返回项目 000交付 子文件夹的统计信息，用于卡片首页渲染。
        Returns:
            {
                "found": bool,                # 000交付 目录是否存在
                "total_episodes": int,        # 项目总集数（来自 DB）
                "items": [
                    {"key": "成片", "label": "成片", "type": "episode", "current": 60, "total": 60},
                    {"key": "有音乐", "label": "有音乐无字幕版本", "type": "episode", "current": 60, "total": 60},
                    {"key": "无音乐", "label": "无音乐无bgm版本", "type": "episode", "current": 60, "total": 60},
                    {"key": "字幕", "label": "字幕文件", "type": "episode", "exclude": ["无字幕"], "current": 60, "total": 60},
                    {"key": "截图", "label": "工程截图", "type": "screenshot", "current": 5, "total": 5},
                ],
                "overall_pct": int,            # 综合完成百分比
            }
        """
        proj = self.db.get_project(project_name)
        group_path = ""
        if proj:
            group_path = proj.get("group_path", "") or ""

        if not group_path:
            return {"found": False, "total_episodes": 0, "items": [], "overall_pct": 0}

        folder_name = os.path.basename(self._delivery_folder.rstrip("\\/"))
        base = os.path.join(group_path, folder_name)
        total_episodes = (proj.get("total_episodes", 0) or 0) if proj else 0

        items = [
            {"key": "成片", "label": "成片", "type": "episode", "current": 0, "total": total_episodes},
            {"key": "有音乐", "label": "有音乐无字幕版本", "type": "episode", "current": 0, "total": total_episodes},
            {"key": "无音乐", "label": "无音乐无bgm版本", "type": "episode", "current": 0, "total": total_episodes},
            {"key": "字幕", "label": "字幕文件", "type": "episode", "exclude": ["无字幕"], "current": 0, "total": total_episodes},
            {"key": "截图", "label": "工程截图", "type": "screenshot", "current": 0, "total": 5},
        ]

        found_folders = set()
        if os.path.isdir(base):
            try:
                for name in os.listdir(base):
                    full = os.path.join(base, name)
                    if not os.path.isdir(full):
                        continue
                    low = name.lower()
                    matched_idx = -1
                    for idx, it in enumerate(items):
                        if it.get("exclude"):
                            skip = False
                            for ex in it["exclude"]:
                                if ex.lower() in low:
                                    skip = True
                                    break
                            if skip:
                                continue
                        if it["key"].lower() in low:
                            matched_idx = idx
                            break
                    if matched_idx >= 0:
                        found_folders.add(name)
                        cnt = 0
                        try:
                            for sub in os.listdir(full):
                                if os.path.isfile(os.path.join(full, sub)):
                                    cnt += 1
                        except OSError:
                            pass
                        items[matched_idx]["current"] = cnt
            except OSError:
                pass

        # 综合完成率（只算项目已设置了 total_episodes 的 episode 项 + 截图）
        checked_items = [it for it in items if it["type"] == "screenshot" or it["total"] > 0]
        total_cur = sum(it["current"] for it in checked_items)
        total_max = sum(it["total"] for it in checked_items)
        overall_pct = round(total_cur / total_max * 100) if total_max > 0 else 0

        return {
            "found": len(found_folders) > 0,
            "total_episodes": total_episodes,
            "items": items,
            "overall_pct": overall_pct,
        }

    def deliver_revision_file(self, project_name, file_name, rev_folder_name=None):
        """将修改文件夹中的单个文件回传到制作部NAS的对应修改文件夹中。
        目标：制作部NAS/项目/01上映单集版/MMDD修改/
        rev_folder_name: 指定修改文件夹名（如 "0810修改"），为 None 时使用最新的。
        """
        proj = self.db.get_project(project_name)
        if not proj:
            return False, "项目不存在"

        if rev_folder_name:
            folders = self.list_all_revision_folders(project_name)
            rev_path = None
            rev_name = rev_folder_name
            for f in folders:
                if f["name"] == rev_folder_name:
                    rev_path = f["path"]
                    break
            if not rev_path:
                return False, "未找到修改文件夹: " + rev_folder_name
        else:
            rev_path, rev_name = self.find_revision_folder(project_name)
            if not rev_path:
                return False, "未找到修改文件夹"

        src = os.path.join(rev_path, file_name)
        if not os.path.isfile(src):
            for name in os.listdir(rev_path):
                if name == file_name and os.path.isfile(os.path.join(rev_path, name)):
                    src = os.path.join(rev_path, name)
                    break
            else:
                return False, "文件不存在于修改文件夹: " + file_name

        prod_path = proj.get("production_path", "")
        if not prod_path:
            return False, "该项目无制作部路径"

        prod_output_dirs = self._find_output_dirs(prod_path, project_name)
        if not prod_output_dirs:
            return False, "制作部项目中未找到%s目录" % self._get_output_dir_name(project_name)

        dst_dir = os.path.join(prod_output_dirs[0], rev_name)
        dst = os.path.join(dst_dir, file_name)

        try:
            file_size = os.path.getsize(src)

            # 创建目标修改文件夹（用 UNC 路径兜底）
            try:
                os.makedirs(dst_dir, exist_ok=True)
            except (PermissionError, OSError):
                dst_dir_unc = self._to_unc(dst_dir)
                result = subprocess.run(
                    ["cmd", "/c", "mkdir", dst_dir_unc],
                    capture_output=True, timeout=30)
                if result.returncode != 0 and not os.path.isdir(dst_dir):
                    raise OSError("无法创建修改文件夹: " + dst_dir)

            # Shell 原生复制（弹系统进度对话框）
            try:
                _shell_copy_file(src, dst_dir)
            except Exception:
                raise

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.db.add_delivery_log(
                project_name, file_name, src, dst, file_size,
                "success", "修改回传成功 -> " + rev_name)
            self.db.update_project_status(
                project_name, delivery_status="delivered",
                last_delivered_at=now)
            return True, "修改回传成功: " + dst
        except Exception as e:
            self.db.add_delivery_log(
                project_name, file_name, src, dst, 0,
                "error", str(e))
            return False, str(e)

    def deliver_revision_batch(self, project_name, file_names, rev_folder_name=None):
        """批量回传修改文件 — Shell 弹一个统一的系统原生进度对话框"""
        proj = self.db.get_project(project_name)
        if not proj:
            return [{"name": n, "ok": False, "message": "项目不存在", "index": i + 1, "total": len(file_names)} for i, n in enumerate(file_names)]

        # 找源修改文件夹
        if rev_folder_name:
            folders = self.list_all_revision_folders(project_name)
            rev_path, rev_name = None, rev_folder_name
            for f in folders:
                if f["name"] == rev_folder_name:
                    rev_path = f["path"]
                    break
            if not rev_path:
                return [{"name": n, "ok": False, "message": "未找到修改文件夹: " + rev_folder_name, "index": i + 1, "total": len(file_names)} for i, n in enumerate(file_names)]
        else:
            rev_path, rev_name = self.find_revision_folder(project_name)
            if not rev_path:
                return [{"name": n, "ok": False, "message": "未找到修改文件夹", "index": i + 1, "total": len(file_names)} for i, n in enumerate(file_names)]

        # 找目标目录: 制作部/项目/01上映单集版/MMDD修改/
        prod_output_dirs = self._find_output_dirs(proj.get("production_path", ""), project_name)
        if not prod_output_dirs:
            return [{"name": n, "ok": False, "message": "制作部项目中未找到对应输出目录", "index": i + 1, "total": len(file_names)} for i, n in enumerate(file_names)]

        dst_dir = os.path.join(prod_output_dirs[0], rev_name)
        try:
            os.makedirs(dst_dir, exist_ok=True)
        except Exception:
            pass

        # 筛选实际存在的文件
        existing = []
        for fname in file_names:
            src = os.path.join(rev_path, fname)
            if os.path.isfile(src):
                existing.append(src)
            else:
                for name in os.listdir(rev_path):
                    if name == fname and os.path.isfile(os.path.join(rev_path, name)):
                        existing.append(os.path.join(rev_path, name))
                        break

        if not existing:
            self.db.update_project_status(
                project_name, delivery_status="error",
                sync_progress="修改批量回传失败: 所有文件都找不到")
            return [{"name": n, "ok": False, "message": "文件不存在于修改文件夹", "index": i + 1, "total": len(file_names)} for i, n in enumerate(file_names)]

        self.db.update_project_status(
            project_name, delivery_status="delivering",
            sync_progress="已发起 Shell 批量复制 ({} 个文件) — 看系统进度对话框".format(len(existing)))

        errors = []
        try:
            _shell_copy_files_batch(rev_path, existing, dst_dir)
        except Exception as e:
            logger.error('Shell 修改批量复制失败 %s → %s: %s', rev_path, dst_dir, e)
            errors.append(str(e))

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if errors:
            self.db.update_project_status(
                project_name, delivery_status="error",
                sync_progress="部分失败: " + errors[0],
                last_delivered_at=now)
        else:
            def _mark_done():
                import time as _t
                _t.sleep(5)
                self.db.update_project_status(
                    project_name, delivery_status="delivered",
                    sync_progress="", last_delivered_at=now)
            import threading as _th
            _th.Thread(target=_mark_done, daemon=True).start()

        results = []
        for i, fname in enumerate(file_names):
            found = any(os.path.basename(p) == fname for p in existing)
            results.append({
                "name": fname, "ok": found and not errors,
                "message": "已发起 Shell 批量复制" if (found and not errors) else ("文件不存在" if not found else errors[0]),
                "index": i + 1, "total": len(file_names),
            })
        return results

    def deliver_revision_folder(self, project_name, rev_folder_name):
        """将整个修改文件夹（含全部文件）回传到制作部NAS的对应修改文件夹。"""
        proj = self.db.get_project(project_name)
        if not proj:
            return False, "项目不存在"

        folders = self.list_all_revision_folders(project_name)
        rev_path = None
        for f in folders:
            if f["name"] == rev_folder_name:
                rev_path = f["path"]
                break
        if not rev_path or not os.path.isdir(rev_path):
            return False, "未找到修改文件夹: " + rev_folder_name

        prod_path = proj.get("production_path", "")
        if not prod_path:
            return False, "该项目无制作部路径"

        prod_output_dirs = self._find_output_dirs(prod_path, project_name)
        if not prod_output_dirs:
            return False, "制作部项目中未找到%s目录" % self._get_output_dir_name(project_name)

        dst_dir = os.path.join(prod_output_dirs[0], rev_folder_name)

        try:
            try:
                os.makedirs(dst_dir, exist_ok=True)
            except (PermissionError, OSError):
                dst_dir_unc = self._to_unc(dst_dir)
                result = subprocess.run(
                    ["cmd", "/c", "mkdir", dst_dir_unc],
                    capture_output=True, timeout=30)
                if result.returncode != 0 and not os.path.isdir(dst_dir):
                    raise OSError("无法创建目标文件夹: " + dst_dir)

            # Shell 原生文件夹复制（弹系统进度对话框）
            try:
                _shell_copy_folder(rev_path, os.path.dirname(dst_dir))
            except Exception:
                raise

            file_count = 0
            total_size = 0
            for root, _, files in os.walk(rev_path):
                for fn in files:
                    file_count += 1
                    try:
                        total_size += os.path.getsize(os.path.join(root, fn))
                    except OSError:
                        pass

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.db.add_delivery_log(
                project_name, rev_folder_name + "/(整个文件夹)",
                rev_path, dst_dir, total_size,
                "success", "文件夹修改回传成功 -> " + rev_folder_name + " (" + str(file_count) + " 个文件)")
            self.db.update_project_status(
                project_name, delivery_status="delivered",
                last_delivered_at=now)
            return True, "文件夹修改回传成功: " + dst_dir + " (" + str(file_count) + " 个文件)"
        except Exception as e:
            self.db.add_delivery_log(
                project_name, rev_folder_name + "/(整个文件夹)",
                rev_path, dst_dir, 0,
                "error", str(e))
            return False, str(e)

    def deliver_revision_folders_batch(self, project_name, folder_names):
        """批量回传多个修改文件夹 — Shell 弹一个统一的系统原生进度对话框"""
        proj = self.db.get_project(project_name)
        if not proj:
            return [{"name": n, "ok": False, "message": "项目不存在", "index": i + 1, "total": len(folder_names)} for i, n in enumerate(folder_names)]

        prod_output_dirs = self._find_output_dirs(proj.get("production_path", ""), project_name)
        if not prod_output_dirs:
            return [{"name": n, "ok": False, "message": "制作部项目中未找到对应输出目录", "index": i + 1, "total": len(folder_names)} for i, n in enumerate(folder_names)]

        prod_output = prod_output_dirs[0]
        folders_on_dest = self.list_all_revision_folders_on_destination(project_name)
        dest_set = {f["name"]: f["path"] for f in folders_on_dest}

        def _get_dst_dir(rev_name):
            if rev_name in dest_set:
                return dest_set[rev_name]
            return os.path.join(prod_output, rev_name)

        valid_pairs = []  # [(src_folder_path, rev_folder_name)]
        for fn in folder_names:
            folders = self.list_all_revision_folders(project_name)
            for f in folders:
                if f["name"] == fn:
                    valid_pairs.append((f["path"], f["name"]))
                    break
            else:
                rev_path, rev_name = self.find_revision_folder(project_name)
                if rev_path and rev_name == fn:
                    valid_pairs.append((rev_path, rev_name))

        if not valid_pairs:
            self.db.update_project_status(
                project_name, delivery_status="error",
                sync_progress="修改文件夹批量回传失败: 所有文件夹都找不到")
            return [{"name": n, "ok": False, "message": "未找到修改文件夹: " + n, "index": i + 1, "total": len(folder_names)} for i, n in enumerate(folder_names)]

        self.db.update_project_status(
            project_name, delivery_status="delivering",
            sync_progress="已发起 Shell 批量复制 ({} 个文件夹) — 看系统进度对话框".format(len(valid_pairs)))

        errors = []
        for src, rev_name in valid_pairs:
            dst_dir = _get_dst_dir(rev_name)
            try:
                os.makedirs(dst_dir, exist_ok=True)
            except Exception:
                pass
            try:
                _shell_copy_folder(src, os.path.dirname(dst_dir.rstrip("\\/")))
            except Exception as e:
                logger.error('Shell 修改文件夹批量复制失败 %s → %s: %s', src, dst_dir, e)
                errors.append(str(e))

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if errors:
            self.db.update_project_status(
                project_name, delivery_status="error",
                sync_progress="部分失败: " + errors[0],
                last_delivered_at=now)
        else:
            def _mark_done():
                import time as _t
                _t.sleep(5)
                self.db.update_project_status(
                    project_name, delivery_status="delivered",
                    sync_progress="", last_delivered_at=now)
            import threading as _th
            _th.Thread(target=_mark_done, daemon=True).start()

        results = []
        found_names = {n for _, n in valid_pairs}
        for i, fn in enumerate(folder_names):
            ok = fn in found_names and not errors
            results.append({
                "name": fn, "ok": ok,
                "message": "已发起 Shell 批量文件夹复制" if ok else ("未找到修改文件夹" if fn not in found_names else errors[0]),
                "index": i + 1, "total": len(folder_names),
            })
        return results
