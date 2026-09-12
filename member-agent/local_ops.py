# -*- coding: utf-8 -*-
"""组员端本地文件操作（跑在组员自己电脑上）。

与主端 local_project.py 的区别：
  - 不依赖主端数据库/同步引擎，所有项目信息通过主端 API 获取
  - 只负责「组员本机」的文件动作：建项目文件夹、从 NAS 拉素材、复制 PR 模板、开 PR

NAS 对组内所有人都是网络盘，所以组员本机可以直接从 NAS 复制，
不需要经过主端中转。
"""
import os
import re
import json
import shutil
import logging
import subprocess

logger = logging.getLogger("local_ops")

# 素材文件夹关键词（与主端保持一致）
_MATERIAL_KEYWORDS = ("抽卡素材", "抽卡", "视频素材", "素材")
_ROUGHCUT_KEYWORDS = ("粗剪", "初剪", "粗减")
_SCRIPT_KEYWORDS = ("剧本", "分集", "脚本")


def extract_episode_number(name):
    """从文件名/文件夹名提取集号。排除结构目录序号（如 01_抽卡素材）。"""
    if not name:
        return None
    m = re.search(r'第\s*(\d{1,3})\s*集', name)
    if m:
        return int(m.group(1))
    if re.match(r'^\d{1,3}_', name):
        return None
    m = re.match(r'^(\d{1,3})\s*[- 　]\s*([\u4e00-\u9fff])', name)
    if m:
        return int(m.group(1))
    return None


def _editor_from_dirname(name):
    """从集号文件夹名提取剪辑师名。"""
    s = re.sub(r'第\s*\d{1,3}\s*集', '', name)
    s = re.sub(r'^\d{1,3}\s*[- 　]', '', s)
    return s.strip().strip('-').strip()


def _next_seq(local_root):
    """本地项目盘的下一可用序号。"""
    max_seq = 0
    try:
        for name in os.listdir(local_root):
            m = re.match(r'^(\d{1,4})', name)
            if m:
                max_seq = max(max_seq, int(m.group(1)))
    except OSError:
        pass
    return max_seq + 1


def _find_pr_exe():
    """探测 Premiere Pro 可执行文件。"""
    candidates = [
        r"C:\Program Files\Adobe\Adobe Premiere Pro 2025\Adobe Premiere Pro.exe",
        r"C:\Program Files\Adobe\Adobe Premiere Pro 2026\Adobe Premiere Pro.exe",
        r"C:\Program Files\Adobe\Adobe Premiere Pro 2024\Adobe Premiere Pro.exe",
        r"C:\Program Files\Adobe\Adobe Premiere Pro 2021\Adobe Premiere Pro.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return ""


def _find_dirs(root, keywords, max_depth=4):
    """递归查找名字含关键词的目录。"""
    found = []

    def _walk(p, depth=0):
        if depth > max_depth:
            return
        try:
            items = os.listdir(p)
        except OSError:
            return
        for s in items:
            full = os.path.join(p, s)
            if not os.path.isdir(full):
                continue
            if any(k in s for k in keywords):
                found.append(full)
            else:
                _walk(full, depth + 1)

    _walk(root)
    return found


def _flatten_copy(src_dir, dst_dir, counter=None):
    """把目录下所有文件扁平复制到目标目录，保留下层文件但去掉中间层级。"""
    n = 0
    if not os.path.isdir(src_dir):
        return 0
    os.makedirs(dst_dir, exist_ok=True)
    for root, dirs, files in os.walk(src_dir):
        for f in files:
            if f.startswith('.') or f.lower() in ('thumbs.db', 'desktop.ini'):
                continue
            src = os.path.join(root, f)
            dst = os.path.join(dst_dir, f)
            if os.path.exists(dst):
                base, ext = os.path.splitext(f)
                i = 2
                while os.path.exists(dst):
                    dst = os.path.join(dst_dir, "%s-%d%s" % (base, i, ext))
                    i += 1
            try:
                shutil.copy2(src, dst)
                n += 1
                if counter:
                    counter[0] += 1
            except Exception as e:
                logger.warning("复制失败 %s -> %s: %s", src, dst, e)
    return n


def _find_episode_dirs(folder, wanted):
    """递归找集号文件夹，返回 {集号: (路径, 剪辑师)}，只保留 wanted 里的集。"""
    result = {}

    def _walk(p, depth=0):
        if depth > 4:
            return
        try:
            items = os.listdir(p)
        except OSError:
            return
        for item in items:
            full = os.path.join(p, item)
            if not os.path.isdir(full):
                continue
            ep = extract_episode_number(item)
            if ep is not None:
                if ep in wanted and ep not in result:
                    result[ep] = (full, _editor_from_dirname(item) or "")
            else:
                _walk(full, depth + 1)

    _walk(folder)
    return result


def _collect_episode_files(folder, wanted):
    """收集「集号-剪辑师.ext」形式的文件。"""
    result = {}
    try:
        items = os.listdir(folder)
    except OSError:
        return result
    for item in items:
        full = os.path.join(folder, item)
        if not os.path.isfile(full) or item.startswith('.'):
            continue
        stem = os.path.splitext(item)[0]
        ep = extract_episode_number(stem)
        if ep is not None and ep in wanted and ep not in result:
            result[ep] = (full, _editor_from_dirname(stem) or "")
    return result


def create_local_project(cfg, project_name, project_info, progress_cb=None):
    """在组员本机创建本地项目并拉取素材。

    cfg: {'local_root':..., 'pr_template':..., 'member_name':..., 'open_pr':bool}
    project_info: 主端 /api/project/<name> 返回的项目数据（含 group_path / episode_plan）
    返回 (ok, message, stats)
    """
    def _prog(stage, done, total):
        if progress_cb:
            try:
                progress_cb(stage, done, total)
            except Exception:
                pass

    local_root = cfg.get("local_root") or ""
    member_name = cfg.get("member_name") or ""
    if not local_root:
        return False, "未配置本地项目目录（请在设置页填写）", {}
    if not member_name:
        return False, "未配置组员姓名（请在设置页填写）", {}

    group_path = (project_info or {}).get("group_path") or ""
    if not group_path:
        return False, "该项目没有组内 NAS 路径", {}
    if not os.path.isdir(group_path):
        return False, "组内 NAS 路径不可访问：%s（请确认网络盘已连接）" % group_path, {}

    # 分集：只要我负责的
    plan_raw = project_info.get("episode_plan") or "{}"
    try:
        plan = json.loads(plan_raw) if isinstance(plan_raw, str) else plan_raw
        plan = plan if isinstance(plan, dict) else {}
    except Exception:
        plan = {}
    my_episodes = sorted(int(k) for k, v in plan.items()
                         if str(v).strip() == member_name)
    if not my_episodes:
        return False, "分集分配里没有「%s」负责的集数" % member_name, {}
    my_set = set(my_episodes)

    # 建本地项目文件夹
    os.makedirs(local_root, exist_ok=True)
    seq = _next_seq(local_root)
    dir_name = "%03d-%s" % (seq, project_name)
    proj_dir = os.path.join(local_root, dir_name)
    os.makedirs(proj_dir, exist_ok=True)
    _prog("创建项目文件夹", 1, 1)

    material_target = os.path.join(proj_dir, "01原素材")
    os.makedirs(material_target, exist_ok=True)

    stats = {"episodes": my_episodes, "material_copied": 0,
             "roughcut_copied": 0, "script_copied": 0,
             "pr_copied": False, "pr_opened": False,
             "local_dir": proj_dir, "material_dirs": []}

    # 拉素材
    material_dirs = _find_dirs(group_path, _MATERIAL_KEYWORDS)
    for md in material_dirs:
        ep_dirs = _find_episode_dirs(md, my_set)
        for ep in my_episodes:
            if ep not in ep_dirs:
                continue
            src_dir, editor = ep_dirs[ep]
            dst_dir = os.path.join(material_target, "第%d集 %s" % (ep, editor or member_name))
            n = _flatten_copy(src_dir, dst_dir)
            if n:
                stats["material_copied"] += n
                stats["material_dirs"].append("第%d集(%d文件)" % (ep, n))
            _prog("拉取素材", len(stats["material_dirs"]), len(my_episodes))

    # 拉粗剪（按集号去重）
    rough_seen = set()
    for rd in _find_dirs(group_path, _ROUGHCUT_KEYWORDS):
        for ep, (src_file, editor) in _collect_episode_files(rd, my_set).items():
            if ep in rough_seen:
                continue
            rough_seen.add(ep)
            dst_dir = os.path.join(material_target, "第%d集 %s" % (ep, editor or member_name))
            os.makedirs(dst_dir, exist_ok=True)
            try:
                shutil.copy2(src_file, os.path.join(dst_dir, os.path.basename(src_file)))
                stats["roughcut_copied"] += 1
            except Exception as e:
                logger.warning("粗剪复制失败: %s", e)
        for ep, (src_dir, editor) in _find_episode_dirs(rd, my_set).items():
            if ep in rough_seen:
                continue
            rough_seen.add(ep)
            dst_dir = os.path.join(material_target, "第%d集 %s" % (ep, editor or member_name))
            n = _flatten_copy(src_dir, dst_dir)
            if n:
                stats["roughcut_copied"] += n

    # 拉剧本
    script_target = os.path.join(proj_dir, "剧本")
    os.makedirs(script_target, exist_ok=True)
    for sd in _find_dirs(group_path, _SCRIPT_KEYWORDS):
        n = _flatten_copy(sd, script_target)
        if n:
            stats["script_copied"] += n

    # PR 模板
    pr_template = cfg.get("pr_template") or ""
    if pr_template and os.path.isfile(pr_template):
        eng_dir = os.path.join(proj_dir, "工程文件")
        os.makedirs(eng_dir, exist_ok=True)
        prproj = os.path.join(eng_dir, dir_name + ".prproj")
        try:
            shutil.copy2(pr_template, prproj)
            stats["pr_copied"] = True
            stats["prproj"] = prproj
            if cfg.get("open_pr", True):
                pr_exe = cfg.get("pr_exe") or _find_pr_exe()
                if pr_exe and os.path.isfile(pr_exe):
                    subprocess.Popen([pr_exe, prproj])
                    stats["pr_opened"] = True
        except Exception as e:
            logger.warning("复制 PR 模板失败: %s", e)

    _prog("完成", len(my_episodes), len(my_episodes))
    msg = ("已创建：%s\n负责集数：%s\n素材 %d 个文件，剧本 %d 个%s"
           % (proj_dir, ",".join(map(str, my_episodes)),
              stats["material_copied"] + stats["roughcut_copied"],
              stats["script_copied"],
              "，已复制 PR 模板" if stats["pr_copied"] else ""))
    return True, msg, stats
