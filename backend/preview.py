"""预览职责：预览路径查找、文件列表。"""
import os
import os as _os
import re
import logging

logger = logging.getLogger(__name__)


class PreviewMixin:
    def _list_dir_contents(self, root_path):
        """通用：列出目录下所有文件，返回 [dict, ...]
        每个 dict: name, path, size, size_mb, ext, mtime
        """
        files = []
        if not root_path or not os.path.isdir(root_path):
            return files
        try:
            for name in os.listdir(root_path):
                full = os.path.join(root_path, name)
                if os.path.isfile(full):
                    ext = os.path.splitext(name)[1].lower()
                    size = os.path.getsize(full)
                    files.append({
                        "name": name,
                        "path": full,
                        "size": size,
                        "size_mb": round(size / 1024 / 1024, 1),
                        "ext": ext,
                        "mtime": datetime.fromtimestamp(
                            os.path.getmtime(full)).strftime(
                            "%Y-%m-%d %H:%M"),
                    })
        except OSError:
            pass
        files.sort(key=lambda x: _natural_key(x["name"]))
        return files

    def list_files_by_mode(self, project_name, mode="editing", subpath=""):
        """按模式列出文件。
        - editing: 01上映单集版根目录的文件（剪辑中）
        - revising: 01上映单集版/MMDD修改/ 目录的文件（修改中）
        - delivery: 000交付/[subpath] 目录的文件夹和文件（待交付/已完成）
        """
        proj = self.db.get_project(project_name)
        group_path = ""
        if proj:
            group_path = proj.get("group_path", "") or ""
        else:
            # 项目未在 DB 登记 —— 尝试从组内 NAS 反查路径
            group_root = self.config.get("nas", {}).get("group_root", "")
            for candidate in (
                os.path.join(group_root, "00已完成", project_name),
                os.path.join(group_root, project_name),
            ):
                if candidate and os.path.isdir(candidate):
                    group_path = candidate
                    break

        if not group_path:
            if mode == "delivery":
                return {"folders": [], "files": [], "breadcrumbs": []}
            return []

        # 根据 mode 决定要扫描的 root 目录
        scan_root = group_path
        if mode == "source":
            root, _ = self.get_source_dir(project_name)
            if root:
                scan_root = root
        elif mode == "dest":
            root, _ = self.get_dest_dir(project_name)
            if root:
                scan_root = root
        elif mode == "editing":
            return self.list_output_files(project_name)

        elif mode == "revising":
            result = {"folders": [], "files": [], "breadcrumbs": []}
            result["breadcrumbs"].append({"name": "修改文件夹", "path": ""})

            if not subpath:
                folders = self.list_all_revision_folders(project_name)
                for f in folders:
                    result["folders"].append({"name": f["name"], "path": f["name"]})
                return result

            # subpath = "MMDD修改" → 列出该文件夹内的文件
            rev_folder_name = subpath.replace("/", "\\").strip("\\")
            folders = self.list_all_revision_folders(project_name)
            rev_path = None
            rev_name = None
            for f in folders:
                if f["name"] == rev_folder_name:
                    rev_path = f["path"]
                    rev_name = f["name"]
                    break

            if rev_path and os.path.isdir(rev_path):
                result["breadcrumbs"].append({"name": rev_name, "path": rev_name})
                files = self._list_dir_contents(rev_path)
                for f in files:
                    f["parent_dir"] = rev_name
                result["files"] = files

            return result

        elif mode == "delivery":
            folder_name = os.path.basename(self._delivery_folder.rstrip("\\/"))
            base = os.path.join(group_path, folder_name)
            target = base
            if subpath:
                safe_sub = subpath.replace("/", "\\").strip("\\")
                target = os.path.normpath(os.path.join(base, safe_sub))
                if not target.startswith(os.path.normpath(base)):
                    target = base

            result = {
                "folders": [],
                "files": [],
                "breadcrumbs": [],
                "total_episodes": (proj.get("total_episodes", 0) or 0) if proj else 0,
                "screenshot_expected": 5,
                "project_name": project_name,
            }

            # 构建面包屑
            rel = os.path.relpath(target, group_path) if os.path.isdir(target) else folder_name
            parts = rel.replace("/", "\\").split("\\")
            bc_path = ""
            for i, part in enumerate(parts):
                if i == 0:
                    result["breadcrumbs"].append({"name": part, "path": ""})
                else:
                    bc_path = os.path.join(bc_path, part) if bc_path else part
                    result["breadcrumbs"].append({"name": part, "path": bc_path})

            if not os.path.isdir(target):
                return result

            try:
                for name in os.listdir(target):
                    full = os.path.join(target, name)
                    if os.path.isdir(full):
                        rel_to_base = os.path.relpath(full, base)
                        try:
                            file_count = sum(1 for sn in os.listdir(full) if os.path.isfile(os.path.join(full, sn)))
                        except OSError:
                            file_count = 0
                        result["folders"].append({
                            "name": name,
                            "path": rel_to_base.replace("/", "\\"),
                            "file_count": file_count,
                        })
            except OSError:
                pass

            files = self._list_dir_contents(target)
            for f in files:
                rel = os.path.relpath(f["path"], base)
                f["rel_path"] = rel.replace("/", "\\")
            result["files"] = files

            result["folders"].sort(key=lambda x: _natural_key(x["name"]))
            result["files"].sort(key=lambda x: _natural_key(x["name"]))
            return result

        return []

    def _find_file_by_episode_num(self, root, ep_num):
        if not root or not _os.path.isdir(root):
            return None
        target = str(ep_num).strip()
        for r, dirs, files in _os.walk(root):
            for f in files:
                n = self._extract_episode_number(f)
                if n is not None and str(n) == target:
                    return _os.path.join(r, f)
            if r[len(root):].count(_os.sep) >= 3:
                dirs.clear()
        return None

    def _search_dir_for_file(self, root, filename):
        if not root or not _os.path.isdir(root):
            return None
        p2 = _os.path.join(root, filename)
        if _os.path.isfile(p2):
            return p2
        for r, dirs, files in _os.walk(root):
            if filename in files:
                return _os.path.join(r, filename)
            if r[len(root):].count(_os.sep) >= 3:
                dirs.clear()
        return self._find_file_by_episode_num(root, filename)

    def get_file_path_for_preview(self, project_name, filename, mode="editing", subpath=""):
        tried = set()
        """根据模式获取文件的实际路径用于预览"""
        if mode == "editing":
            files = self.list_output_files(project_name)
            for f in files:
                if f["name"] == filename:
                    return f["path"]
            for f in files:
                n = self._extract_episode_number(f["name"])
                if n is not None and str(n) == str(filename).strip():
                    return f["path"]
        elif mode == "revising":
            rev_folder = subpath if subpath else ""
            data = self.list_files_by_mode(project_name, "revising", rev_folder)
            files = data["files"] if isinstance(data, dict) else data
            for f in files:
                if f["name"] == filename:
                    return f["path"]
        elif mode == "delivery":
            proj = self.db.get_project(project_name)
            if not proj:
                return None
            group_path = proj.get("group_path", "")
            folder_name = os.path.basename(self._delivery_folder.rstrip("\\/"))
            base = os.path.join(group_path, folder_name)
            if subpath:
                target = os.path.normpath(os.path.join(base, subpath.replace("/", "\\").strip("\\")))
            else:
                target = base
            full = os.path.join(target, filename)
            if os.path.isfile(full):
                return full
        # Cross-mode fallback
        for getter in (self.get_source_dir, self.get_dest_dir):
            root, err = getter(project_name)
            if root and root not in tried:
                tried.add(root)
                r = self._search_dir_for_file(root, filename)
                if r: return r

        return None
