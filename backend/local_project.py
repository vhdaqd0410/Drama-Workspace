# -*- coding: utf-8 -*-
"""本地剪辑项目创建 + 素材拉取。

流程：选择组内项目 → 在本地项目盘创建「序号-项目名」文件夹 + 复制模板结构
     → 根据分集分配(episode_plan)确定"我"负责的集数
     → 只拉取我负责集数的素材（抽卡/粗剪），扁平复制到「01原素材/第N集 剪辑师名/」
     → 拉取整个剧本文件夹。
"""
import os
import re
import json
import shutil
import logging
import subprocess

logger = logging.getLogger("local_project")

# 素材文件夹关键词
_MATERIAL_KEYWORDS = ("抽卡素材", "抽卡", "视频素材", "素材")
# 粗剪文件夹关键词（自动识别，各部门命名可能不同）
_ROUGHCUT_KEYWORDS = ("粗剪", "初剪", "粗减")
# 剧本文件夹关键词
_SCRIPT_KEYWORDS = ("剧本", "分集", "脚本")
# 结构目录词：这些目录是"分类/结构"目录（序号是目录序号，不是集号），应跳过
_STRUCT_WORDS = ("抽卡素材", "抽卡", "单补镜头", "单补", "视频素材", "素材",
                 "前期筹备", "制作明细", "工程成片", "成片交付", "交付",
                 "备注", "评论", "分镜", "剧本", "脚本", "参考", "模板")


def _extract_episode_number(name):
    """从文件/文件夹名提取集号。只认真正的"集号"命名，排除结构目录序号。

    支持：
      - 「第N集 ...」           → N
      - 「N-剪辑师名」/「N 剪辑师名」 → N（数字后跟 -/空格 + 非数字中文）
    排除：
      - 「NN_结构词」（如 01_抽卡素材、02_单补镜头）→ None（结构目录序号，非集号）
    """
    if not name:
        return None
    # 1) 「第N集」最明确
    m = re.search(r'第\s*(\d{1,3})\s*集', name)
    if m:
        return int(m.group(1))
    # 2) 排除结构目录：数字 + 下划线（01_xxx）
    if re.match(r'^\d{1,3}_', name):
        return None
    # 3) 「N-中文」或「N 中文」：数字后跟 -/空格 + 中文
    m = re.match(r'^(\d{1,3})\s*[- 　]\s*([\u4e00-\u9fff])', name)
    if m:
        return int(m.group(1))
    return None


def _extract_editor_from_dirname(name):
    """从集号文件夹名提取剪辑师名（如「1- 张光强」→「张光强」，「第1集 张光强」→「张光强」）。"""
    # 去掉「第N集」
    s = re.sub(r'第\s*\d{1,3}\s*集', '', name)
    # 去掉开头「N-」或「N 」
    s = re.sub(r'^\d{1,3}\s*[- 　]', '', s)
    # 去掉「-」前缀残留
    s = s.strip().strip('-').strip()
    return s


def _next_seq(local_root):
    """扫描本地项目盘现有项目目录，返回下一个可用序号（现有最大序号 + 1）。"""
    max_seq = 0
    try:
        for name in os.listdir(local_root):
            m = re.match(r'^(\d{1,4})', name)
            if m:
                max_seq = max(max_seq, int(m.group(1)))
    except OSError:
        pass
    return max_seq + 1


def _to_unc(path, unc_map):
    """盘符转 UNC（管理员权限下映射盘符无法直接复制）。"""
    path = path.replace("/", "\\")
    for drive, unc in (unc_map or {}).items():
        d = drive.rstrip(":") + ":"
        if path.upper().startswith(d.upper()):
            rest = path[len(d):].lstrip("\\")
            return os.path.join(unc, rest)
    return path


def _copy_tree_robust(src, dst, unc_map=None):
    """稳健复制目录：优先 shutil.copytree，失败则用 robocopy(UNC) 兜底。"""
    if not os.path.isdir(src):
        return False, "源不存在: " + src
    try:
        shutil.copytree(src, dst)
        return True, ""
    except Exception:
        try:
            unc_src = _to_unc(src, unc_map)
            unc_dst = _to_unc(dst, unc_map)
            cmd = ["robocopy", unc_src, unc_dst, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP"]
            r = subprocess.run(cmd, capture_output=True, timeout=600)
            if r.returncode <= 7:
                return True, ""
            return False, "robocopy 失败 code=%d" % r.returncode
        except Exception as e2:
            return False, str(e2)


def _copy_file_robust(src, dst, unc_map=None):
    """复制单个文件。"""
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(_to_unc(src, unc_map), dst)
        return True
    except Exception:
        return False


def _flatten_copy(src_dir, dst_dir, unc_map=None):
    """把 src_dir 下所有文件扁平复制到 dst_dir（保留子目录里的文件，但去掉中间层级）。"""
    count = 0
    if not os.path.isdir(src_dir):
        return 0
    for root, dirs, files in os.walk(src_dir):
        for f in files:
            src = os.path.join(root, f)
            # 跳过临时/缓存文件
            if f.startswith('.') or f.lower() in ('thumbs.db', 'desktop.ini'):
                continue
            dst = os.path.join(dst_dir, f)
            # 同名去重
            if os.path.exists(dst):
                base, ext = os.path.splitext(f)
                i = 2
                while os.path.exists(dst):
                    dst = os.path.join(dst_dir, "%s-%d%s" % (base, i, ext))
                    i += 1
            if _copy_file_robust(src, dst, unc_map):
                count += 1
    return count


def create_local_project(sync_engine, project_name, progress_cb=None):
    """创建本地剪辑项目并拉取素材。返回 (ok, message, stats)。

    progress_cb(stage, done, total) 可选，用于进度上报。
    """
    def _prog(stage, done, total):
        if progress_cb:
            try:
                progress_cb(stage, done, total)
            except Exception:
                pass

    db = sync_engine.db
    proj = db.get_project(project_name)
    if not proj:
        return False, "项目不存在", {}

    group_path = proj.get("group_path", "") or ""
    if not group_path or not os.path.isdir(group_path):
        return False, "该项目无组内 NAS 路径（请先同步素材到组内）", {}

    local_root = db.get_setting("local_project_root", "").strip()
    template_dir = db.get_setting("local_project_template", "").strip()
    my_editor = db.get_setting("my_editor_name", "").strip()

    if not local_root:
        return False, "未配置本地项目盘根目录（请到设置页配置）", {}
    if not my_editor:
        return False, "未配置「我的剪辑师名」（请到设置页配置）", {}

    # 1. 确定"我"负责的集数
    ep_plan_raw = proj.get("episode_plan") or "{}"
    try:
        ep_plan = json.loads(ep_plan_raw) if isinstance(ep_plan_raw, str) else ep_plan_raw
    except Exception:
        ep_plan = {}
    my_episodes = sorted(int(k) for k, v in (ep_plan or {}).items()
                         if str(v).strip() == my_editor)
    if not my_episodes:
        return False, "分集分配里未找到剪辑师「%s」负责的集数" % my_editor, {}
    my_ep_set = set(my_episodes)

    # 2. 创建本地项目文件夹（序号 + 项目名）
    seq = _next_seq(local_root)
    local_dir_name = "%03d-%s" % (seq, project_name)
    local_proj_dir = os.path.join(local_root, local_dir_name)
    os.makedirs(local_proj_dir, exist_ok=True)
    _prog("创建项目文件夹", 1, 1)

    # 3. 复制模板结构（若有）
    template_copied = False
    if template_dir and os.path.isdir(template_dir):
        ok, err = _copy_tree_robust(template_dir, local_proj_dir, sync_engine._unc_map)
        template_copied = ok
        if not ok:
            logger.warning("复制模板失败: %s", err)

    # 原素材目标目录（参考项目结构 01原素材）
    material_target = os.path.join(local_proj_dir, "01原素材")
    os.makedirs(material_target, exist_ok=True)

    unc_map = sync_engine._unc_map
    stats = {"episodes": my_episodes, "material_copied": 0, "roughcut_copied": 0,
             "script_copied": 0, "template_copied": template_copied,
             "material_dirs": []}

    # 4. 定位素材/粗剪/剧本文件夹（递归查找，支持多层嵌套）
    def _find_dirs(root, keywords):
        found = []
        def _walk(p, depth=0):
            if depth > 4:
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

    material_dirs = _find_dirs(group_path, _MATERIAL_KEYWORDS)
    roughcut_dirs = _find_dirs(group_path, _ROUGHCUT_KEYWORDS)
    script_dirs = _find_dirs(group_path, _SCRIPT_KEYWORDS)

    # 5. 递归查找"集号文件夹"，只收集我负责的集
    def _find_episode_dirs(folder):
        """递归查找 folder 下的集号文件夹，返回 {集号: (源目录, 剪辑师名)}。
        跳过结构目录（_extract_episode_number 返回 None 的），递归其内部。"""
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
                ep = _extract_episode_number(item)
                if ep is not None:
                    # 只记录我负责的集（同集多个文件夹取第一个）
                    if ep in my_ep_set and ep not in result:
                        editor = _extract_editor_from_dirname(item) or my_editor
                        result[ep] = (full, editor)
                else:
                    _walk(full, depth + 1)
        _walk(folder)
        return result

    def _collect_episode_files(folder):
        """收集 folder 下按「集号-剪辑师.扩展名」命名的文件（如 1-张光强.mp4），
        返回 {集号: (文件路径, 剪辑师名)}。用于粗剪等"每集一个文件"的结构。"""
        result = {}
        try:
            items = os.listdir(folder)
        except OSError:
            return result
        for item in items:
            full = os.path.join(folder, item)
            if not os.path.isfile(full):
                continue
            if item.startswith('.'):
                continue
            # 去掉扩展名后提取集号/剪辑师
            stem = os.path.splitext(item)[0]
            ep = _extract_episode_number(stem)
            if ep is not None and ep in my_ep_set and ep not in result:
                editor = _extract_editor_from_dirname(stem) or my_editor
                result[ep] = (full, editor)
        return result

    # 6. 拉取素材：对每个素材目录，找集号文件夹，扁平复制到 01原素材/第N集 剪辑师
    for md in material_dirs:
        ep_dirs = _find_episode_dirs(md)
        for ep in my_episodes:
            if ep not in ep_dirs:
                continue
            src_dir, editor = ep_dirs[ep]
            dst_dir = os.path.join(material_target, "第%d集 %s" % (ep, editor))
            n = _flatten_copy(src_dir, dst_dir, unc_map)
            if n > 0:
                stats["material_copied"] += n
                stats["material_dirs"].append("第%d集 %s (%d 文件)" % (ep, editor, n))
            _prog("拉取素材", len(stats["material_dirs"]), len(my_episodes))

    # 7. 拉取粗剪（全局按集号去重，避免「03_粗剪」与「N-剪辑师/粗剪」子目录重复）
    # 支持两种结构：文件形式「N-剪辑师.mp4」、文件夹形式「N-剪辑师/xxx」
    # 粗剪与素材放在一起，统一放入 01原素材/第N集 剪辑师/
    rough_seen = set()  # 已处理的集号（全局去重）
    for rd in roughcut_dirs:
        # 文件形式：粗剪目录下直接是「集号-剪辑师.mp4」
        for ep, (src_file, editor) in _collect_episode_files(rd).items():
            if ep in rough_seen:
                continue
            rough_seen.add(ep)
            dst_dir = os.path.join(material_target, "第%d集 %s" % (ep, editor))
            if _copy_file_robust(src_file, os.path.join(dst_dir, os.path.basename(src_file)), unc_map):
                stats["roughcut_copied"] += 1
        # 文件夹形式：粗剪目录下是「集号-剪辑师/xxx」
        for ep, (src_dir, editor) in _find_episode_dirs(rd).items():
            if ep in rough_seen:
                continue
            rough_seen.add(ep)
            dst_dir = os.path.join(material_target, "第%d集 %s" % (ep, editor))
            n = _flatten_copy(src_dir, dst_dir, unc_map)
            if n > 0:
                stats["roughcut_copied"] += n

    # 8. 拉取整个剧本文件夹
    for sd in script_dirs:
        dst = os.path.join(local_proj_dir, "剧本", os.path.basename(sd))
        ok, err = _copy_tree_robust(sd, dst, unc_map)
        if ok:
            stats["script_copied"] += 1

    _prog("完成", len(my_episodes), len(my_episodes))

    detail_lines = "、".join(stats["material_dirs"]) if stats["material_dirs"] else "无"
    msg = ("已创建本地项目：%s\n负责集数：%s\n"
           "拉取素材：%s\n剧本 %d 个%s"
           % (local_proj_dir, ",".join(map(str, my_episodes)),
              detail_lines, stats["script_copied"],
              "，模板已复制" if template_copied else ""))
    stats["seq"] = seq
    stats["local_dir_name"] = local_dir_name
    stats["local_proj_dir"] = local_proj_dir
    return True, msg, stats
